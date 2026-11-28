# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The summary for the ICP return (issue #168; docs/belastingregels.md,
"Opgaaf ICP"): per VAT number of the customer, the total of the services
reverse charged to a customer in another EU country. It is a specification
of box 3b, so its total is always that of 3b over the same period."""

from datetime import date

import pytest

from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.reports.icp import compute_icp, normalised_vat_number
from huismus.reports.periods import Period
from huismus.reports.vat_return import compute_vat_return

from .test_vat_return import TODAY, _credit_note, _settings

pytestmark = pytest.mark.django_db

Q3 = Period.parse("2026-Q3", today=TODAY)


@pytest.fixture(autouse=True)
def kor_off():
    _settings(kor=False)


def _invoice(
    day,
    price,
    *,
    country="DE",
    vat_number="DE123456789",
    name="Kunde GmbH",
    reverse_charge=True,
    rate=0,
    delivered=None,
):
    document = Document.objects.create(
        kind="invoice",
        status="draft",
        issue_date=day,
        delivery_date=delivered,
        contact=Contact.objects.create(company_name=name, country=country, vat_number=vat_number),
    )
    DocumentLine.objects.create(
        document=document,
        position=0,
        description="Advies",
        quantity="1",
        unit_price_cents=price,
        tax_rate_bp=rate,
        reverse_charge=reverse_charge,
    )
    return issue(document)


def test_one_line_per_vat_number_with_the_total_of_the_period():
    _invoice(date(2026, 7, 1), 100_00)
    _invoice(date(2026, 8, 1), 250_50)
    _invoice(date(2026, 9, 1), 75_00, country="BE", vat_number="BE0123456789", name="Klant BV")

    report = compute_icp(Q3)

    assert [(c.vat_number, c.country, c.name, c.amount_cents) for c in report.customers] == [
        ("BE0123456789", "BE", "Klant BV", 75_00),
        ("DE123456789", "DE", "Kunde GmbH", 350_50),
    ]
    assert report.total_cents == 425_50


def test_the_total_is_that_of_box_3b():
    _invoice(date(2026, 7, 1), 100_00)
    _invoice(date(2026, 8, 1), 33_33, vat_number="")
    # Not in 3b: Dutch VAT, a Dutch customer reverse charged, outside the EU.
    _invoice(date(2026, 8, 2), 500_00, reverse_charge=False, rate=2100, country="NL")
    _invoice(date(2026, 8, 3), 40_00, country="NL", vat_number="NL000099998B57")
    _invoice(date(2026, 8, 4), 60_00, country="US", vat_number="")

    box_3b = next(box for box in compute_vat_return(Q3).boxes if box.code == "3b")
    assert compute_icp(Q3).total_cents == box_3b.revenue_cents == 133_33


def test_a_service_counts_in_the_period_it_was_delivered():
    """ "Intracommunautaire diensten geeft u aan in het tijdvak waarin u de
    dienst hebt geleverd." The invoice date doesn't matter."""
    _invoice(date(2026, 10, 2), 100_00, delivered=date(2026, 9, 30))
    _invoice(date(2026, 9, 2), 70_00, delivered=date(2026, 10, 1))
    _invoice(date(2026, 8, 2), 10_00)

    assert compute_icp(Q3).total_cents == 110_00


def test_a_credit_note_counts_negative_for_its_customer():
    invoice = _invoice(date(2026, 7, 1), 100_00)
    _invoice(date(2026, 7, 2), 40_00)
    _credit_note(invoice, date(2026, 8, 1))

    report = compute_icp(Q3)
    assert [c.amount_cents for c in report.customers] == [40_00]


def test_spaces_and_dots_in_a_vat_number_do_not_make_another_customer():
    _invoice(date(2026, 7, 1), 10_00, vat_number="de 123.456.789")
    _invoice(date(2026, 7, 2), 20_00, vat_number="DE123456789")

    assert [(c.vat_number, c.amount_cents) for c in compute_icp(Q3).customers] == [
        ("DE123456789", 30_00)
    ]


def test_normalised_vat_number_adds_no_country_code():
    assert normalised_vat_number(" fr-12 345 678 901 ") == "FR12345678901"
    assert normalised_vat_number("123456789") == "123456789"


def test_the_vat_number_is_the_one_on_the_invoice():
    """Invariant 5: what the issued invoice says, not the customer now."""
    invoice = _invoice(date(2026, 7, 1), 10_00, vat_number="DE111111111")
    invoice.contact.vat_number = "DE999999999"
    invoice.contact.save()

    assert compute_icp(Q3).customers[0].vat_number == "DE111111111"


def test_without_a_vat_number_the_invoices_are_named_apart():
    """They are in 3b, so they stay in the total, under a line of their own."""
    without = _invoice(date(2026, 7, 1), 12_00, vat_number="")
    _invoice(date(2026, 7, 2), 30_00)

    report = compute_icp(Q3)
    assert [c.vat_number for c in report.customers] == ["DE123456789"]
    assert [(m.document.pk, m.amount_cents) for m in report.without_vat_number] == [
        (without.pk, 12_00)
    ]
    assert report.without_vat_number_cents == 12_00
    assert report.total_cents == 42_00


def test_an_empty_period():
    _invoice(date(2026, 4, 1), 10_00)

    report = compute_icp(Q3)
    assert report.customers == []
    assert report.without_vat_number == []
    assert report.is_empty


def test_with_the_kor_nothing_is_counted():
    _invoice(date(2026, 7, 1), 10_00)
    _settings(kor=True)

    report = compute_icp(Q3)
    assert report.kor_on
    assert report.customers == []
    assert report.total_cents == 0
