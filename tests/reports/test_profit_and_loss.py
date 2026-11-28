# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The profit and loss statement per year (issue #109, SPEC.md M28): the
year overview's figures in the headings of the tax return, nothing
counted anew (CLAUDE.md, hard rule 4)."""

from datetime import date

import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate
from huismus.reports.profit_and_loss import compute_profit_and_loss
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def _document(kind, day, subtotal_cents, vat_cents=0):
    return Document.objects.create(
        kind=kind,
        status="issued",
        number=f"{kind}-{day}",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=day,
        subtotal_cents=subtotal_cents,
        total_cents=subtotal_cents + vat_cents,
    )


def _expense(day, *lines):
    """lines: (gross, vat, rate, category)."""
    return create_expense(
        [ExpenseLineInput("", gross, vat, category, rate) for gross, vat, rate, category in lines],
        date=day,
    )


@pytest.fixture
def year():
    office = ExpenseCategory.objects.create(name="Kantoor")
    travel = ExpenseCategory.objects.create(name="Reizen")
    _document("invoice", date(2026, 3, 1), 100000, 21000)
    _document("invoice", date(2026, 9, 1), 50000, 10500)
    _document("credit_note", date(2026, 10, 1), 20000, 4200)
    _document("invoice", date(2025, 12, 31), 99999)  # another year
    Document.objects.create(kind="invoice", status="draft", contact=Contact.objects.create())
    _expense(
        date(2026, 1, 10), (12100, 2100, VatRate.HIGH, office), (1090, 90, VatRate.LOW, travel)
    )
    _expense(date(2026, 5, 2), (60000, 0, VatRate.ZERO, travel))
    _expense(date(2026, 7, 3), (2420, None, "", None))  # no category
    return office, travel


def test_revenue_is_the_year_overviews_revenue_without_vat(year):
    statement = compute_profit_and_loss(2026)

    assert statement.revenue_cents == 100000 + 50000 - 20000
    assert statement.revenue_cents == compute_year_overview(2026).revenue_cents


@pytest.mark.parametrize("kor", [False, True])
def test_costs_and_profit_equal_the_year_overview(year, kor):
    _kor(kor)
    overview = compute_year_overview(2026)

    statement = compute_profit_and_loss(2026)

    assert statement.costs_cents == overview.expenses_cents
    assert statement.profit_cents == overview.profit_cents
    assert sum(line.amount_cents for line in statement.cost_lines) == statement.costs_cents


def test_without_the_kor_costs_are_without_vat(year):
    _kor(False)

    statement = compute_profit_and_loss(2026)

    by_name = {line.name: line.amount_cents for line in statement.cost_lines}
    assert by_name == {"Kantoor": 10000, "Reizen": 61000, "Zonder categorie": 2420}
    assert statement.costs_without_vat


def test_with_the_kor_costs_are_what_was_paid(year):
    _kor(True)

    statement = compute_profit_and_loss(2026)

    by_name = {line.name: line.amount_cents for line in statement.cost_lines}
    assert by_name == {"Kantoor": 12100, "Reizen": 61090, "Zonder categorie": 2420}
    assert not statement.costs_without_vat


def test_the_largest_category_comes_first_and_no_category_last(year):
    _kor(False)

    statement = compute_profit_and_loss(2026)

    assert [line.name for line in statement.cost_lines] == ["Reizen", "Kantoor", "Zonder categorie"]


def test_a_category_called_like_the_no_category_line_is_still_a_category():
    # Sorting looks at whether there is a category, not at the name.
    named = ExpenseCategory.objects.create(name="Zonder categorie")
    _expense(date(2026, 1, 1), (500, None, "", None))
    _expense(date(2026, 1, 2), (100, None, "", named))

    statement = compute_profit_and_loss(2026)

    assert [(line.amount_cents, line.uncategorised) for line in statement.cost_lines] == [
        (100, False),
        (500, True),
    ]


def test_an_empty_year_has_no_cost_lines_and_no_profit():
    statement = compute_profit_and_loss(2026)

    assert statement.revenue_cents == 0
    assert statement.cost_lines == []
    assert statement.costs_cents == 0
    assert statement.profit_cents == 0


def test_a_loss_is_a_negative_profit():
    _expense(date(2026, 4, 1), (5000, None, "", None))

    assert compute_profit_and_loss(2026).profit_cents == -5000
