# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An expense has lines, as in Moneybird (huismus-intern/besluiten.md,
2026-11-02): each its own description, gross amount, VAT for information
and category. The expense's amount is the sum of its lines, computed in
one place (huismus/expenses/lines.py)."""

from datetime import date

import pytest
from django.db import IntegrityError, models, transaction
from hypothesis import given
from hypothesis import strategies as st

from huismus.expenses.lines import ExpenseLineInput, expense_totals, save_lines, split_gross
from huismus.expenses.models import Expense, ExpenseCategory, ExpenseLine

pytestmark = pytest.mark.django_db


def _expense(**fields):
    return Expense.objects.create(date=date(2026, 3, 1), amount_cents=0, **fields)


def test_line_amounts_are_integer_cents():
    assert isinstance(ExpenseLine._meta.get_field("amount_cents"), models.BigIntegerField)
    assert isinstance(ExpenseLine._meta.get_field("vat_info_cents"), models.BigIntegerField)


def test_the_expense_amount_is_the_sum_of_its_lines():
    expense = _expense()
    software = ExpenseCategory.objects.create(name="Software")

    save_lines(
        expense,
        [
            ExpenseLineInput("Hosting", 1210, 210, software),
            ExpenseLineInput("Domein", 1500, None, None),
        ],
    )

    expense.refresh_from_db()
    assert expense.amount_cents == 2710
    assert expense.vat_info_cents == 210
    assert [(line.position, line.description, line.category) for line in expense.lines.all()] == [
        (0, "Hosting", software),
        (1, "Domein", None),
    ]


def test_without_any_vat_the_expense_has_none():
    assert expense_totals([ExpenseLineInput("a", 100, None, None)]) == (100, None)


@given(st.lists(st.tuples(st.integers(-(10**9), 10**9), st.none() | st.integers(0, 10**8))))
def test_totals_are_plain_sums(lines):
    # Gross amounts (invariant 7): nothing is added or subtracted.
    inputs = [ExpenseLineInput("", amount, vat, None) for amount, vat in lines]
    vats = [vat for _amount, vat in lines if vat is not None]

    assert expense_totals(inputs) == (sum(a for a, _v in lines), sum(vats) if vats else None)


def test_saving_again_replaces_the_lines():
    expense = _expense()
    save_lines(
        expense,
        [ExpenseLineInput("Oud", 100, None, None), ExpenseLineInput("Ook oud", 50, None, None)],
    )

    save_lines(expense, [ExpenseLineInput("Nieuw", 300, None, None)])

    assert list(expense.lines.values_list("description", "amount_cents")) == [("Nieuw", 300)]
    assert Expense.objects.get().amount_cents == 300


def test_a_category_in_use_on_a_line_cannot_be_deleted():
    category = ExpenseCategory.objects.create(name="Software")
    save_lines(_expense(), [ExpenseLineInput("Hosting", 100, None, category)])

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            category.delete()


def test_deleting_an_expense_deletes_its_lines():
    expense = _expense()
    save_lines(expense, [ExpenseLineInput("Hosting", 100, None, None)])

    expense.delete()

    assert ExpenseLine.objects.count() == 0


def test_a_gross_total_is_split_over_the_lines_by_their_subtotal():
    # Moneybird states its lines without VAT and the document's total with
    # it; the cent left by rounding goes on the last line.
    assert split_gross(4894, [3234, 810]) == [3914, 980]


def test_one_line_gets_the_whole_total():
    assert split_gross(1694, [1383]) == [1694]


def test_lines_without_a_subtotal_put_the_total_on_the_last_line():
    assert split_gross(500, [0, 0]) == [0, 500]


@given(
    st.integers(-(10**9), 10**9),
    st.lists(st.integers(0, 10**8), min_size=1, max_size=20),
)
def test_the_split_always_adds_up_to_the_total(total, subtotals):
    split = split_gross(total, subtotals)

    assert len(split) == len(subtotals)
    assert sum(split) == total
