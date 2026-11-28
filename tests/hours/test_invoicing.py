# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An invoice from the hours (#81): the lines per description or per day,
which hours count, the claim that keeps hours off a second invoice, and
what deleting the draft or crediting the invoice does to them
(product-owner agent 2026-11-28, huismus-intern/besluiten.md,
"Maandfactuur uit uren (#81)")."""

import threading
from datetime import date
from decimal import Decimal

import pytest
from django.db import close_old_connections
from django.utils import translation
from hypothesis import given, settings
from hypothesis import strategies as st
from hypothesis.extra.django import TestCase

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note, delete_draft
from huismus.documents.issuing import issue
from huismus.documents.models import Document
from huismus.documents.reopening import reopen
from huismus.documents.totals import line_total_cents
from huismus.hours.entries import period_total
from huismus.hours.invoicing import (
    PER_DAY,
    PER_DESCRIPTION,
    AlreadyInvoiced,
    NothingToInvoice,
    billable_months,
    create_invoice,
    propose,
)
from huismus.hours.models import TimeEntry
from tests.support import clean_up_issued_documents_for_flush

pytestmark = pytest.mark.django_db

NOVEMBER = date(2026, 11, 1)


@pytest.fixture
def studio():
    return Contact.objects.create(company_name="Studio Noordlicht")


def _entry(contact, day, hours, rate=9000, description=""):
    return TimeEntry.objects.create(
        date=date(2026, 11, day) if isinstance(day, int) else day,
        contact=contact,
        hours=Decimal(hours),
        rate_cents=rate,
        description=description,
    )


def _lines(document):
    return [
        (line.description, line.quantity, line.unit, line.unit_price_cents, line.tax_rate_bp)
        for line in document.lines.order_by("position")
    ]


# --- the lines ----------------------------------------------------------------


def test_one_line_per_description_in_the_order_of_its_first_day(studio):
    _entry(studio, 5, "2", description="Overleg")
    _entry(studio, 3, "1.5", description="Ontwerp")
    _entry(studio, 4, "3", description="Ontwerp")
    _entry(studio, 6, "1", description="")

    proposal = propose(studio, NOVEMBER, PER_DESCRIPTION)

    assert [(line.description, line.hours) for line in proposal.lines] == [
        ("Ontwerp", Decimal("4.5")),
        ("Overleg", Decimal("2")),
        ("Uren", Decimal("1")),
    ]


def test_a_description_with_two_rates_gets_a_line_per_rate(studio):
    _entry(studio, 3, "2", rate=9000, description="Ontwerp")
    _entry(studio, 4, "1", rate=7500, description="Ontwerp")
    _entry(studio, 5, "1", rate=9000, description="Ontwerp")

    proposal = propose(studio, NOVEMBER, PER_DESCRIPTION)

    assert [(line.description, line.hours, line.rate_cents) for line in proposal.lines] == [
        ("Ontwerp", Decimal("3"), 9000),
        ("Ontwerp", Decimal("1"), 7500),
    ]


def test_one_line_per_day_names_the_day_and_each_description_once(studio):
    _entry(studio, 3, "2", description="Ontwerp")
    _entry(studio, 3, "1", description="Overleg")
    _entry(studio, 3, "0.5", description="Ontwerp")
    _entry(studio, 4, "1", description="")
    _entry(studio, 2, "1", description="Ontwerp")

    proposal = propose(studio, NOVEMBER, PER_DAY)

    assert [(line.description, line.hours) for line in proposal.lines] == [
        ("2 november: Ontwerp", Decimal("1")),
        ("3 november: Ontwerp; Overleg", Decimal("3.5")),
        ("4 november", Decimal("1")),
    ]


def test_the_lines_are_in_the_language_of_the_invoice(studio):
    _entry(studio, 3, "2", description="Design")
    _entry(studio, 4, "1")
    with translation.override("nl"):
        per_day = propose(studio, NOVEMBER, PER_DAY, language="en")
        per_description = propose(studio, NOVEMBER, PER_DESCRIPTION, language="en")

    assert [line.description for line in per_day.lines] == ["3 November: Design", "4 November"]
    assert [line.description for line in per_description.lines] == ["Design", "Hours"]


def test_only_unbilled_hours_with_a_rate_of_that_customer_and_month_count(studio):
    other = Contact.objects.create(company_name="Bakkerij De Korenaar")
    counted = _entry(studio, 3, "2")
    _entry(studio, 4, "1.5", rate=None, description="Overleg")
    _entry(studio, date(2026, 10, 31), "1")
    _entry(other, 3, "1")
    draft = Document.objects.create(kind="invoice", status="draft", contact=studio)
    TimeEntry.objects.filter(pk=_entry(studio, 5, "4").pk).update(invoice=draft)

    proposal = propose(studio, NOVEMBER, PER_DESCRIPTION)

    assert proposal.entries == [counted]
    assert proposal.hours == Decimal("2")
    assert proposal.unrated_hours == Decimal("1.5")


def test_the_months_to_choose_are_those_with_hours_to_invoice(studio):
    other = Contact.objects.create(company_name="Bakkerij De Korenaar")
    _entry(studio, date(2026, 9, 2), "1")
    _entry(studio, date(2026, 11, 2), "1")
    _entry(studio, date(2026, 10, 2), "1", rate=None)
    _entry(other, date(2026, 10, 5), "1")

    assert billable_months(studio) == [date(2026, 11, 1), date(2026, 9, 1)]
    assert billable_months() == [date(2026, 11, 1), date(2026, 10, 1), date(2026, 9, 1)]


# --- the amounts --------------------------------------------------------------


def test_the_difference_with_hours_is_named_only_when_there_is_one(studio):
    # Each entry is worth € 16,665 → € 16,67, so € 50,01 on Uren; the line of
    # 1,5 hours is € 49,995 → € 50,00.
    for day in (3, 4, 5):
        _entry(studio, day, "0.5", rate=3333)

    grouped = propose(studio, NOVEMBER, PER_DESCRIPTION)
    per_day = propose(studio, NOVEMBER, PER_DAY)

    assert grouped.totals.subtotal_cents == 5000
    assert grouped.hours_page_cents == 5001
    assert grouped.difference_cents == 5001
    assert per_day.totals.subtotal_cents == 5001
    assert per_day.difference_cents is None


class TestLinesAddUp(TestCase):
    """Whatever the hours and rates, the lines carry every hour once, and
    each line is worth what an invoice line of those hours is (invariant 3)."""

    @settings(max_examples=40, deadline=None)
    @given(
        st.lists(
            st.tuples(
                st.integers(min_value=1, max_value=28),
                st.decimals(min_value="0.01", max_value="24", places=2),
                st.sampled_from([9000, 7500, 3333, 1]),
                st.sampled_from(["", "Ontwerp", "Overleg"]),
            ),
            min_size=1,
            max_size=12,
        ),
        st.sampled_from([PER_DAY, PER_DESCRIPTION]),
    )
    def test_lines(self, rows, per):
        contact = Contact.objects.create(company_name="Studio Noordlicht")
        for day, hours, rate, description in rows:
            _entry(contact, day, hours, rate=rate, description=description)

        proposal = propose(contact, NOVEMBER, per)

        assert sum(line.hours for line in proposal.lines) == sum(row[1] for row in rows)
        assert proposal.totals.line_totals_cents == [
            line_total_cents(line.hours, line.rate_cents) for line in proposal.lines
        ]
        assert proposal.hours_page_cents == period_total((row[1], row[2]) for row in rows)[1]


# --- the draft ----------------------------------------------------------------


def test_the_draft_has_the_lines_and_the_month_and_holds_the_hours(studio):
    settings_ = Settings.load()
    settings_.prices_include_vat = True
    settings_.save()
    first = _entry(studio, 3, "2", description="Ontwerp")
    second = _entry(studio, 4, "1.5", description="Ontwerp")

    with translation.override("en"):
        invoice = create_invoice(studio, NOVEMBER, PER_DESCRIPTION)

    assert (invoice.kind, invoice.status, invoice.number) == ("invoice", "draft", "")
    assert invoice.contact == studio
    assert invoice.language == "nl"
    assert invoice.intro_text == "Uren november 2026"
    assert invoice.prices_include_vat is False
    assert _lines(invoice) == [("Ontwerp", Decimal("3.5"), "uur", 9000, 2100)]
    assert (invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents) == (31500, 6615, 38115)
    assert set(invoice.time_entries.all()) == {first, second}


def test_under_the_kor_the_lines_get_no_vat(studio):
    settings_ = Settings.load()
    settings_.kor_enabled = True
    settings_.save()
    _entry(studio, 3, "2")

    invoice = create_invoice(studio, NOVEMBER, PER_DAY)

    assert [line.tax_rate_bp for line in invoice.lines.all()] == [0]
    assert invoice.tax_cents == 0


def test_hours_already_on_an_invoice_never_go_on_a_second(studio):
    _entry(studio, 3, "2")
    create_invoice(studio, NOVEMBER, PER_DAY)

    with pytest.raises(NothingToInvoice):
        create_invoice(studio, NOVEMBER, PER_DAY)
    assert Document.objects.count() == 1


def test_new_hours_after_the_draft_go_on_a_new_draft(studio):
    _entry(studio, 3, "2")
    create_invoice(studio, NOVEMBER, PER_DAY)
    later = _entry(studio, 10, "1")

    second = create_invoice(studio, NOVEMBER, PER_DAY)

    assert list(second.time_entries.all()) == [later]


def test_deleting_the_draft_frees_the_hours(studio):
    entry = _entry(studio, 3, "2")
    invoice = create_invoice(studio, NOVEMBER, PER_DAY)

    delete_draft(invoice)

    entry.refresh_from_db()
    assert entry.invoice is None
    assert propose(studio, NOVEMBER, PER_DAY).entries == [entry]


def test_an_issued_and_credited_invoice_keeps_its_hours(studio):
    entry = _entry(studio, 3, "2")
    invoice = issue(create_invoice(studio, NOVEMBER, PER_DAY))
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))
    issue(credit_note)

    entry.refresh_from_db()
    assert entry.invoice == invoice
    assert propose(studio, NOVEMBER, PER_DAY).entries == []


def test_reopening_the_invoice_keeps_its_hours(studio):
    entry = _entry(studio, 3, "2")
    invoice = issue(create_invoice(studio, NOVEMBER, PER_DAY))

    reopen(invoice)

    entry.refresh_from_db()
    assert entry.invoice == invoice
    assert entry.locked


def test_hours_changed_between_reading_and_claiming_make_nothing(studio, monkeypatch):
    """The claim takes only hours as they were read: a change in another
    tab at that moment makes no draft with the old number of hours."""
    from huismus.hours import invoicing

    entry = _entry(studio, 3, "2")
    read = invoicing.propose

    def read_then_changed(*args, **kwargs):
        proposal = read(*args, **kwargs)
        TimeEntry.objects.filter(pk=entry.pk).update(hours=Decimal("3"))
        return proposal

    monkeypatch.setattr(invoicing, "propose", read_then_changed)
    with pytest.raises(AlreadyInvoiced):
        create_invoice(studio, NOVEMBER, PER_DAY)
    assert Document.objects.count() == 0


def test_an_archived_customer_can_be_invoiced(studio):
    _entry(studio, 3, "2")
    studio.archived = True
    studio.save()

    invoice = issue(create_invoice(studio, NOVEMBER, PER_DAY))

    assert invoice.contact == studio
    assert invoice.status == "issued"


@pytest.mark.django_db(transaction=True)
def test_two_requests_at_once_put_the_hours_on_one_invoice():
    # An installation always has its settings row; two threads creating it
    # at once is another race, not this one.
    Settings.load()
    contact = Contact.objects.create(company_name="Studio Noordlicht")
    for day in (3, 4, 5):
        _entry(contact, day, "2")
    barrier = threading.Barrier(2)
    made = []
    refused = []
    errors = []

    def click():
        try:
            barrier.wait()
            made.append(create_invoice(contact, NOVEMBER, PER_DAY))
        except AlreadyInvoiced as exc:
            refused.append(exc)
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=click) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert (len(made), len(refused)) == (1, 1)
    assert Document.objects.count() == 1
    assert TimeEntry.objects.filter(invoice=made[0]).count() == 3
    clean_up_issued_documents_for_flush()
