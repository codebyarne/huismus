# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest

from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, ExpenseCategory
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


def _contact():
    return Contact.objects.create(company_name="Klant BV")


def _issued_invoice(*, issue_date, total_cents):
    return Document.objects.create(
        kind="invoice",
        status="issued",
        number=f"F-{issue_date}",
        contact=_contact(),
        issue_date=issue_date,
        subtotal_cents=total_cents,  # 0% VAT: under the KOR
        total_cents=total_cents,
    )


def _issued_credit_note(*, issue_date, total_cents):
    return Document.objects.create(
        kind="credit_note",
        status="issued",
        number=f"C-{issue_date}",
        contact=_contact(),
        issue_date=issue_date,
        subtotal_cents=total_cents,  # 0% VAT: under the KOR
        total_cents=total_cents,
    )


def test_empty_year_is_all_zero():
    overview = compute_year_overview(2026)
    assert overview.revenue_cents == 0
    assert overview.expenses_cents == 0
    assert overview.profit_cents == 0
    assert len(overview.quarters) == 4


def test_revenue_sums_issued_invoices_in_the_year():
    _issued_invoice(issue_date="2026-01-15", total_cents=10000)
    _issued_invoice(issue_date="2026-06-01", total_cents=5000)
    _issued_invoice(issue_date="2025-12-31", total_cents=9999)  # different year

    overview = compute_year_overview(2026)

    assert overview.revenue_cents == 15000


def test_a_draft_invoice_is_not_revenue():
    Document.objects.create(kind="invoice", status="draft", contact=_contact(), total_cents=10000)
    overview = compute_year_overview(2026)
    assert overview.revenue_cents == 0


def test_credit_notes_reduce_revenue():
    _issued_invoice(issue_date="2026-01-15", total_cents=10000)
    _issued_credit_note(issue_date="2026-02-01", total_cents=3000)

    overview = compute_year_overview(2026)

    assert overview.revenue_cents == 7000


def test_expenses_sum_gross_amounts_in_the_year():
    Expense.objects.create(date="2026-01-10", amount_cents=2000)
    Expense.objects.create(date="2026-03-01", amount_cents=1500)
    Expense.objects.create(date="2025-12-31", amount_cents=9999)  # different year

    overview = compute_year_overview(2026)

    assert overview.expenses_cents == 3500


def test_profit_is_revenue_minus_expenses():
    _issued_invoice(issue_date="2026-01-15", total_cents=10000)
    Expense.objects.create(date="2026-01-10", amount_cents=4000)

    overview = compute_year_overview(2026)

    assert overview.profit_cents == 6000


def test_quarterly_breakdown_assigns_each_document_and_expense_correctly():
    _issued_invoice(issue_date="2026-01-01", total_cents=1000)  # Q1
    _issued_invoice(issue_date="2026-04-01", total_cents=2000)  # Q2
    _issued_invoice(issue_date="2026-07-01", total_cents=3000)  # Q3
    _issued_invoice(issue_date="2026-10-01", total_cents=4000)  # Q4
    Expense.objects.create(date="2026-02-01", amount_cents=100)  # Q1

    overview = compute_year_overview(2026)

    by_quarter = {q.quarter: q for q in overview.quarters}
    assert by_quarter[1].revenue_cents == 1000
    assert by_quarter[1].expenses_cents == 100
    assert by_quarter[2].revenue_cents == 2000
    assert by_quarter[3].revenue_cents == 3000
    assert by_quarter[4].revenue_cents == 4000
    assert by_quarter[1].profit_cents == 900


def test_category_breakdown_groups_expenses_by_category():
    software = ExpenseCategory.objects.create(name="Software")
    travel = ExpenseCategory.objects.create(name="Reiskosten")
    create_expense([ExpenseLineInput("", 1000, None, software)], date="2026-01-01")
    create_expense([ExpenseLineInput("", 500, None, software)], date="2026-02-01")
    create_expense([ExpenseLineInput("", 750, None, travel)], date="2026-03-01")

    overview = compute_year_overview(2026)

    totals = {c.name: c.amount_cents for c in overview.by_category}
    assert totals["Software"] == 1500
    assert totals["Reiskosten"] == 750


def test_category_breakdown_groups_uncategorised_expenses_together():
    create_expense([ExpenseLineInput("", 1000, None, None)], date="2026-01-01")
    create_expense([ExpenseLineInput("", 500, None, None)], date="2026-02-01")

    overview = compute_year_overview(2026)

    assert len(overview.by_category) == 1
    assert overview.by_category[0].amount_cents == 1500


# --- chart_step (M8): a readable axis for the per-quarter bar chart. ---


@pytest.mark.parametrize(
    ("max_cents", "step_cents"),
    [
        (791500, 200000),  # € 7.915 -> axis up to € 8.000 in steps of € 2.000
        (400000, 100000),  # exactly 4 steps of € 1.000
        (400001, 200000),
        (9000, 2500),  # € 90 -> steps of € 25
        (0, 100000),  # nothing yet: a calm default axis
    ],
)
def test_chart_step(max_cents, step_cents):
    from huismus.reports.year_overview import chart_step

    assert chart_step(max_cents) == step_cents


def test_revenue_is_without_vat():
    """The VAT on an invoice isn't the business's own money (SPEC.md M18)."""
    Document.objects.create(
        kind="invoice",
        status="issued",
        number="F-btw",
        contact=_contact(),
        issue_date="2026-02-01",
        subtotal_cents=100000,
        tax_cents=21000,
        total_cents=121000,
    )
    Document.objects.create(
        kind="credit_note",
        status="issued",
        number="C-btw",
        contact=_contact(),
        issue_date="2026-03-01",
        subtotal_cents=10000,
        tax_cents=2100,
        total_cents=12100,
    )
    overview = compute_year_overview(2026)
    assert overview.revenue_cents == 90000
    assert overview.quarters[0].revenue_cents == 90000
