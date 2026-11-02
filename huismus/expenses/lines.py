# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one place that writes an expense's lines and its totals.

An expense has lines, as in Moneybird (huismus-intern/besluiten.md,
2026-11-02). Its amount is the sum of the lines' gross amounts, its VAT
the sum of what the lines state for information (invariant 7: never
subtracted). Every writer (the form, both imports, the demo data) goes
through save_lines(), so Expense.amount_cents can't drift from its lines.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from huismus.documents.totals import round_half_up_cents

from .models import Expense, ExpenseCategory, ExpenseLine


@dataclass(frozen=True)
class ExpenseLineInput:
    description: str
    amount_cents: int  # gross
    vat_info_cents: int | None
    category: ExpenseCategory | None


def expense_totals(lines) -> tuple[int, int | None]:
    """(amount, VAT) of an expense with these lines: plain sums. The VAT
    is None when no line states any."""
    vats = [line.vat_info_cents for line in lines if line.vat_info_cents is not None]
    return sum(line.amount_cents for line in lines), (sum(vats) if vats else None)


def save_lines(expense, lines: list[ExpenseLineInput]) -> None:
    """Replaces all lines of a saved expense (their ids change) and stores
    its totals, in one transaction, so it never ends up with no lines."""
    with transaction.atomic():
        expense.lines.all().delete()
        ExpenseLine.objects.bulk_create(
            ExpenseLine(
                expense=expense,
                position=position,
                description=line.description,
                amount_cents=line.amount_cents,
                vat_info_cents=line.vat_info_cents,
                category=line.category,
            )
            for position, line in enumerate(lines)
        )
        expense.amount_cents, expense.vat_info_cents = expense_totals(lines)
        expense.save(update_fields=["amount_cents", "vat_info_cents", "updated_at"])


def create_expense(lines: list[ExpenseLineInput], **fields):
    """A new expense with these lines; `fields`: date, supplier, description,
    source, external_id."""
    with transaction.atomic():
        expense = Expense.objects.create(amount_cents=0, **fields)
        save_lines(expense, lines)
    return expense


def split_gross(total_cents: int, subtotals: list[int]) -> list[int]:
    """`total_cents` (gross, what was paid) over lines in proportion to
    their subtotals, half-up per line, with the cents left by rounding on
    the last line, so the lines always add up to exactly the total. For
    Moneybird's incoming documents, whose lines have no gross amount
    (huismus/imports/commit.py)."""
    weight = sum(subtotals)
    if weight == 0:
        return [0] * (len(subtotals) - 1) + [total_cents]
    shares = [
        round_half_up_cents(Decimal(total_cents) * subtotal / weight) for subtotal in subtotals[:-1]
    ]
    return [*shares, total_cents - sum(shares)]
