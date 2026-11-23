# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Recurring invoices (#82, SPEC.md M27): a series makes a draft each period,
when the user opens Huismus. Never a number: issuing stays a click."""

import datetime
import threading

import pytest
from django.db import close_old_connections

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, RecurringInvoice
from huismus.documents.recurring import (
    RecurringError,
    change_series,
    first_date_after,
    following_date,
    latest_in_series,
    make_due_drafts,
    planned_on,
    series_of,
    start_series,
    stop_series,
)
from tests.support import clean_up_issued_documents_for_flush

pytestmark = pytest.mark.django_db

D = datetime.date


def _configure_settings():
    settings = Settings.load()
    settings.business_name = "Voorbeeld"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Utrecht"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()


def _issued_invoice(price_cents=5000):
    _configure_settings()
    invoice = Document.objects.create(
        kind="invoice",
        status="draft",
        contact=Contact.objects.create(company_name="Bakkerij Vos"),
        intro_text="Onderhoud website",
        attention="Mila Vos",
        reference="PO-12",
        issue_date=D(2026, 10, 1),
    )
    DocumentLine.objects.create(
        document=invoice,
        position=0,
        description="Hosting en onderhoud",
        unit_price_cents=price_cents,
        tax_rate_bp=2100,
    )
    issue(invoice)
    return invoice


# --- following_date -------------------------------------------------------


@pytest.mark.parametrize(
    ("current", "frequency", "day", "expected"),
    [
        (D(2026, 1, 15), "month", 15, D(2026, 2, 15)),
        (D(2026, 12, 1), "month", 1, D(2027, 1, 1)),
        # The end of a short month, then back to the day the series started on.
        (D(2026, 1, 31), "month", 31, D(2026, 2, 28)),
        (D(2026, 2, 28), "month", 31, D(2026, 3, 31)),
        (D(2028, 1, 31), "month", 31, D(2028, 2, 29)),
        (D(2026, 11, 30), "quarter", 30, D(2027, 2, 28)),
        (D(2027, 2, 28), "quarter", 30, D(2027, 5, 30)),
        (D(2028, 2, 29), "year", 29, D(2029, 2, 28)),
        (D(2029, 2, 28), "year", 29, D(2030, 2, 28)),
        (D(2026, 3, 1), "year", 1, D(2027, 3, 1)),
    ],
)
def test_following_date(current, frequency, day, expected):
    assert following_date(current, frequency, day) == expected


@pytest.mark.parametrize(
    ("start", "frequency", "today", "expected"),
    [
        # The first date in the rhythm after today, never today or before.
        (D(2026, 10, 1), "month", D(2026, 10, 1), D(2026, 11, 1)),
        (D(2026, 10, 1), "month", D(2026, 11, 1), D(2026, 12, 1)),
        (D(2025, 3, 15), "month", D(2026, 11, 23), D(2026, 12, 15)),
        (D(2025, 3, 15), "quarter", D(2026, 11, 23), D(2026, 12, 15)),
        (D(2024, 1, 31), "quarter", D(2026, 11, 23), D(2027, 1, 31)),
        (D(2025, 3, 15), "year", D(2026, 11, 23), D(2027, 3, 15)),
    ],
)
def test_first_date_after(start, frequency, today, expected):
    assert first_date_after(start, frequency, today) == expected


# --- starting a series ----------------------------------------------------


def test_start_series_from_an_issued_invoice():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    assert (series.frequency, series.next_date, series.day) == ("month", D(2026, 11, 1), 1)
    assert series_of(invoice) == series
    assert latest_in_series(series) == invoice


def test_a_draft_cannot_start_a_series():
    _configure_settings()
    draft = Document.objects.create(kind="invoice", status="draft")
    with pytest.raises(RecurringError):
        start_series(draft, "month", D(2026, 11, 1))


def test_a_credit_note_cannot_start_a_series():
    invoice = _issued_invoice()
    credit_note = Document.objects.create(
        kind="credit_note", status="draft", related_document=invoice, contact=invoice.contact
    )
    DocumentLine.objects.create(
        document=credit_note, position=0, description="Terug", unit_price_cents=100
    )
    issue(credit_note)
    with pytest.raises(RecurringError):
        start_series(credit_note, "month", D(2026, 11, 1))


def test_an_invoice_is_in_one_series_at_most():
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    with pytest.raises(RecurringError):
        start_series(invoice, "year", D(2027, 10, 1))


# --- making drafts --------------------------------------------------------


def test_nothing_before_the_date():
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    assert make_due_drafts(D(2026, 10, 31)) == []
    assert Document.objects.count() == 1


def test_on_the_date_a_draft_copy_without_number():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))

    [draft] = make_due_drafts(D(2026, 11, 1))

    assert draft.kind == "invoice"
    assert draft.status == "draft"
    assert draft.number == ""
    assert draft.issue_date is None and draft.due_date is None
    assert draft.contact == invoice.contact
    assert (draft.intro_text, draft.attention, draft.reference) == (
        "Onderhoud website",
        "Mila Vos",
        "PO-12",
    )
    [line] = draft.lines.all()
    assert (line.description, line.unit_price_cents, line.tax_rate_bp) == (
        "Hosting en onderhoud",
        5000,
        2100,
    )
    assert draft.total_cents == 6050
    assert series_of(draft) == series
    assert planned_on(draft) == D(2026, 11, 1)
    assert planned_on(invoice) is None
    series.refresh_from_db()
    assert series.next_date == D(2026, 12, 1)
    # The issued invoice it came from is untouched.
    invoice.refresh_from_db()
    assert (invoice.status, invoice.number) == ("issued", "2026-0001")


def test_running_twice_makes_nothing_twice():
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    assert len(make_due_drafts(D(2026, 11, 3))) == 1
    assert make_due_drafts(D(2026, 11, 3)) == []
    assert Document.objects.filter(status="draft").count() == 1


def test_catches_up_one_draft_per_missed_period():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    drafts = make_due_drafts(D(2027, 1, 20))
    assert [planned_on(draft) for draft in drafts] == [
        D(2026, 11, 1),
        D(2026, 12, 1),
        D(2027, 1, 1),
    ]
    series.refresh_from_db()
    assert series.next_date == D(2027, 2, 1)


def test_the_next_draft_copies_the_latest_in_the_series():
    """A price changed in this month's draft goes on in the next one."""
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    [november] = make_due_drafts(D(2026, 11, 1))
    line = november.lines.get()
    line.unit_price_cents = 6000
    line.save()

    [december] = make_due_drafts(D(2026, 12, 1))

    assert december.lines.get().unit_price_cents == 6000


def test_a_deleted_draft_leaves_the_series_running():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    [november] = make_due_drafts(D(2026, 11, 1))
    november.delete()

    [december] = make_due_drafts(D(2026, 12, 1))

    assert latest_in_series(series) == december
    assert december.lines.get().unit_price_cents == 5000


def test_a_stopped_series_makes_nothing():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    stop_series(series, D(2026, 10, 20))
    assert make_due_drafts(D(2027, 1, 1)) == []
    series.refresh_from_db()
    assert series.stopped_on == D(2026, 10, 20)


def test_a_stopped_invoice_can_start_a_new_series():
    invoice = _issued_invoice()
    old = start_series(invoice, "month", D(2026, 11, 1))
    stop_series(old, D(2026, 10, 20))
    assert series_of(invoice) == old

    new = start_series(invoice, "quarter", D(2027, 1, 1))

    assert series_of(invoice) == new
    [draft] = make_due_drafts(D(2027, 1, 1))
    assert series_of(draft) == new
    assert make_due_drafts(D(2027, 1, 1)) == []


def test_change_series_frequency_and_date():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    change_series(series, "quarter", D(2027, 1, 31))
    series.refresh_from_db()
    assert (series.frequency, series.next_date, series.day) == ("quarter", D(2027, 1, 31), 31)


def test_the_vat_of_a_copy_follows_the_settings():
    """Under the KOR now, the copied lines are 0% (documents.vat.vat_for_copy)."""
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    settings = Settings.load()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.save()

    [draft] = make_due_drafts(D(2026, 11, 1))

    assert draft.lines.get().tax_rate_bp == 0
    assert draft.total_cents == 5000


def test_a_made_draft_issues_with_the_next_number():
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    [draft] = make_due_drafts(D(2026, 11, 1))
    issue(draft)
    assert draft.number == "2026-0002"


def test_a_series_is_never_deleted_while_it_has_invoices():
    invoice = _issued_invoice()
    series = start_series(invoice, "month", D(2026, 11, 1))
    with pytest.raises(Exception):  # noqa: B017, PT011 — PROTECT, any database error
        series.delete()
    assert RecurringInvoice.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_two_requests_at_once_make_one_draft():
    """Two pages opened at the same moment: each period becomes one draft."""
    invoice = _issued_invoice()
    start_series(invoice, "month", D(2026, 11, 1))
    barrier = threading.Barrier(2)
    made = []
    errors = []

    def open_page():
        try:
            barrier.wait()
            made.extend(make_due_drafts(D(2026, 11, 1)))
        except Exception as exc:  # pragma: no cover - reported below
            errors.append(exc)
        finally:
            close_old_connections()

    threads = [threading.Thread(target=open_page) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert errors == []
    assert len(made) == 1
    assert Document.objects.filter(status="draft").count() == 1
    clean_up_issued_documents_for_flush()
