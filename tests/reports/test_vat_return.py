# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT return report (SPEC.md M21, part 4; issue #78; product-owner
agent 2026-11-07, huismus-intern/besluiten.md, "Btw-aangifterapport").

Only reads what is stored: the VAT per rate of issued invoices and credit
notes (DocumentVatRow) and the VAT the user entered on expense lines. What
it can't put in a box, it names under "Niet meegeteld"."""

from datetime import date

import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.reopening import reopen
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import VatRate
from huismus.reports.periods import Period
from huismus.reports.vat_return import compute_vat_return

pytestmark = pytest.mark.django_db

TODAY = date(2026, 11, 7)
Q3 = Period.parse("2026-Q3", today=TODAY)


def _settings(*, kor=False):
    settings = Settings.load()
    for key, value in {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "vat_number": "NL000099998B57",
        "kor_enabled": kor,
        "kor_text": "Vrijgesteld van btw (voorbeeldtekst).",
        "reverse_charge_text": "Btw verlegd (voorbeeldtekst).",
    }.items():
        setattr(settings, key, value)
    settings.save()
    return settings


@pytest.fixture(autouse=True)
def kor_off():
    _settings(kor=False)


def _invoice(day, *lines, country="NL"):
    """lines: (unit_price_cents, rate_bp, reverse_charge). Issued."""
    document = Document.objects.create(
        kind="invoice",
        status="draft",
        issue_date=day,
        contact=Contact.objects.create(company_name="Klant BV", country=country),
    )
    for position, (price, rate, reverse_charge) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position}",
            quantity="1",
            unit_price_cents=price,
            tax_rate_bp=rate,
            reverse_charge=reverse_charge,
        )
    return issue(document)


def _credit_note(invoice, day):
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))
    credit_note.issue_date = day
    credit_note.save()
    return issue(credit_note)


def _imported_without_rows(day, *, subtotal, tax, kind="invoice"):
    """An imported document whose stated totals aren't those of its lines:
    issued without VAT rows (SPEC.md M21, part 1)."""
    document = Document.objects.create(
        kind=kind,
        status="draft",
        number=f"MB-{Document.objects.count() + 1}",
        issue_date=day,
        contact=Contact.objects.create(company_name="Oude klant"),
        subtotal_cents=subtotal,
        tax_cents=tax,
        total_cents=subtotal + tax,
    )
    Document.objects.filter(pk=document.pk).update(status="issued")
    return document


def _expense(day, *lines):
    """lines: (gross, vat, rate)."""
    return create_expense(
        [ExpenseLineInput("Iets", gross, vat, None, rate) for gross, vat, rate in lines],
        date=day,
        supplier="Leverancier",
    )


def _box(report, code):
    return next(box for box in report.boxes if box.code == code)


def _amounts(report, code):
    box = _box(report, code)
    return box.revenue_cents, box.tax_cents


def test_sales_per_rate_go_in_their_boxes():
    _invoice(date(2026, 7, 1), (10000, 2100, False), (5000, 900, False), (2000, 0, False))
    _invoice(date(2026, 9, 30), (1000, 2100, False))

    report = compute_vat_return(Q3)

    assert _amounts(report, "1a") == (11000, 2310)
    assert _amounts(report, "1b") == (5000, 450)
    assert _amounts(report, "1e") == (2000, 0)
    assert report.owed_cents == 2310 + 450
    assert not report.not_counted


def test_a_credit_note_counts_negative_in_its_own_period():
    invoice = _invoice(date(2026, 6, 30), (10000, 2100, False))
    _credit_note(invoice, date(2026, 7, 2))

    q2 = compute_vat_return(Period.parse("2026-Q2", today=TODAY))
    q3 = compute_vat_return(Q3)

    assert _amounts(q2, "1a") == (10000, 2100)
    assert _amounts(q3, "1a") == (-10000, -2100)
    assert q3.owed_cents == -2100
    year = compute_vat_return(Period.parse("2026", today=TODAY))
    assert _amounts(year, "1a") == (0, 0)


def test_drafts_and_quotes_dont_count():
    Document.objects.create(kind="invoice", status="draft", issue_date=date(2026, 7, 5))
    Document.objects.create(kind="quote", status="sent", issue_date=date(2026, 7, 5))

    report = compute_vat_return(Q3)

    assert all(box.revenue_cents == 0 and box.tax_cents == 0 for box in report.boxes)
    assert report.is_empty


def test_a_document_back_in_draft_doesnt_count_and_is_named():
    invoice = _invoice(date(2026, 8, 1), (10000, 2100, False))
    reopen(invoice)

    report = compute_vat_return(Q3)

    assert _amounts(report, "1a") == (0, 0)
    assert [d.number for d in report.back_in_draft] == [invoice.number]


def test_an_import_without_rows_is_named_with_moneybirds_amounts():
    _imported_without_rows(date(2026, 8, 3), subtotal=12345, tax=2592)
    _imported_without_rows(date(2026, 8, 4), subtotal=1000, tax=210, kind="credit_note")

    report = compute_vat_return(Q3)

    assert _amounts(report, "1a") == (0, 0)
    assert [(row.revenue_cents, row.tax_cents) for row in report.without_rows] == [
        (12345, 2592),
        (-1000, -210),
    ]
    assert report.not_counted == 2


def test_another_rate_is_named_and_the_rest_of_the_invoice_counts():
    invoice = _invoice(date(2026, 7, 10), (10000, 600, False), (1000, 2100, False))

    report = compute_vat_return(Q3)

    assert _amounts(report, "1a") == (1000, 210)
    assert [(r.number, r.rate_bp, r.revenue_cents, r.tax_cents) for r in report.other_rates] == [
        (invoice.number, 600, 10000, 600)
    ]


def test_reverse_charge_is_split_by_the_customers_country():
    _invoice(date(2026, 7, 1), (1000, 0, True), country="NL")
    _invoice(date(2026, 7, 1), (2000, 0, True), country="de")
    _invoice(date(2026, 7, 1), (4000, 0, True), country="US")
    _invoice(date(2026, 7, 1), (8000, 0, True), country="")

    report = compute_vat_return(Q3)

    assert _amounts(report, "1e") == (1000, 0)
    assert _amounts(report, "3b") == (2000, 0)
    assert [(r.country, r.revenue_cents) for r in report.reverse_charge_elsewhere] == [
        ("US", 4000),
        ("", 8000),
    ]


def test_an_invoice_with_the_kor_text_is_named_not_counted():
    _settings(kor=True)
    _invoice(date(2026, 7, 1), (10000, 0, False))
    _settings(kor=False)

    report = compute_vat_return(Q3)

    assert _amounts(report, "1e") == (0, 0)
    assert [(d.revenue_cents, d.tax_cents) for d in report.kor_documents] == [(10000, 0)]


def test_input_vat_and_reverse_charged_purchases():
    _expense(date(2026, 7, 1), (12100, 2100, VatRate.HIGH), (1090, 90, VatRate.LOW))
    _expense(date(2026, 7, 2), (5000, 0, VatRate.ZERO))
    _expense(date(2026, 7, 3), (10000, 2100, VatRate.REVERSE_NL))
    _expense(date(2026, 7, 4), (20000, 4200, VatRate.REVERSE_NON_EU))
    _expense(date(2026, 8, 5), (30000, 6300, VatRate.REVERSE_EU))

    report = compute_vat_return(Q3)

    assert _amounts(report, "2a") == (10000, 2100)
    assert _amounts(report, "4a") == (20000, 4200)
    assert _amounts(report, "4b") == (30000, 6300)
    assert report.owed_cents == 2100 + 4200 + 6300
    assert report.reverse_charged_input_vat_cents == 2100 + 4200 + 6300
    assert report.input_vat_cents == 2100 + 90 + 2100 + 4200 + 6300
    assert report.balance_cents == -(2100 + 90)
    # Stored amounts are only read (hard rule 7).
    assert report.not_counted == 0


def test_expense_lines_without_a_rate_or_vat_are_named():
    expense = _expense(
        date(2026, 7, 1), (3000, 500, ""), (2000, None, VatRate.HIGH), (1210, 210, VatRate.HIGH)
    )

    report = compute_vat_return(Q3)

    assert report.input_vat_cents == 210
    assert [(line.expense_id, line.amount_cents) for line in report.lines_missing] == [
        (expense.pk, 3000),
        (expense.pk, 2000),
    ]


def test_only_the_period_counts():
    _invoice(date(2026, 6, 30), (1000, 2100, False))
    _invoice(date(2026, 10, 1), (1000, 2100, False))
    _expense(date(2026, 6, 30), (1210, 210, VatRate.HIGH))
    _expense(date(2026, 10, 1), (3000, 500, ""))

    report = compute_vat_return(Q3)

    assert _amounts(report, "1a") == (0, 0)
    assert report.input_vat_cents == 0
    assert report.not_counted == 0
    assert report.is_empty
    assert compute_vat_return(Period.parse("2026-06", today=TODAY)).input_vat_cents == 210


def test_with_the_kor_on_expense_vat_counts_nowhere():
    # CLAUDE.md, hard rule 7: under the KOR no expense line is read. The
    # page shows only a notice then (decided by the owner, 2026-11-07).
    _settings(kor=True)
    _expense(date(2026, 7, 2), (3000, 500, ""))
    _expense(date(2026, 7, 3), (1210, 210, VatRate.HIGH), (10000, 2100, VatRate.REVERSE_NL))

    report = compute_vat_return(Q3)

    assert report.kor_on
    assert report.input_vat_cents == 0
    assert _amounts(report, "2a") == (0, 0)
    assert report.lines_missing == []


def test_the_boxes_are_in_the_order_of_the_return():
    report = compute_vat_return(Q3)

    assert [box.code for box in report.boxes] == ["1a", "1b", "1e", "2a", "3b", "4a", "4b"]
