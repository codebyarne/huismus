# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revenue/expenses/profit summary for a calendar year (SPEC.md section
6). Read-only: a query over what's already there, not a new kind of
write, so there's no dry-run concept here the way imports/expenses
imports have.

Revenue is without VAT, the stored `subtotal_cents` of each document
(SPEC.md M18): the VAT on an invoice isn't the business's own money.
Under the KOR the VAT is 0, so nothing changes there.

Revenue counts on `Document.issue_date` (accrual), not a payment date
(cash) — the same date every other part of this app already treats as
authoritative for a document (numbering, snapshots, PDF dates), not a
tax position on which basis is "correct" for any particular purpose.
huismus-intern/STATUS.md's M6 plan flags this explicitly as a computation choice, not
an assertion, for Arne to weigh in on if his own bookkeeping expects a
cash-basis view instead.
"""

from dataclasses import dataclass, field

from django.db.models import Sum
from django.db.models.functions import ExtractQuarter
from django.utils.translation import gettext_lazy as _

from huismus.documents.models import Document

from .models import Expense, ExpenseLine


@dataclass
class QuarterTotals:
    quarter: int
    revenue_cents: int = 0
    expenses_cents: int = 0

    @property
    def profit_cents(self) -> int:
        return self.revenue_cents - self.expenses_cents


@dataclass
class CategoryTotal:
    name: str
    amount_cents: int


@dataclass
class YearOverview:
    year: int
    revenue_cents: int = 0
    expenses_cents: int = 0
    quarters: list[QuarterTotals] = field(default_factory=list)
    by_category: list[CategoryTotal] = field(default_factory=list)

    @property
    def profit_cents(self) -> int:
        return self.revenue_cents - self.expenses_cents


def _totals_by_quarter(queryset, date_field: str, amount_field: str) -> dict[int, int]:
    rows = (
        queryset.annotate(quarter=ExtractQuarter(date_field))
        .values("quarter")
        .annotate(total=Sum(amount_field))
    )
    return {row["quarter"]: row["total"] or 0 for row in rows}


def compute_year_overview(year: int) -> YearOverview:
    invoice_totals = _totals_by_quarter(
        Document.objects.filter(kind="invoice", status="issued", issue_date__year=year),
        "issue_date",
        "subtotal_cents",
    )
    credit_note_totals = _totals_by_quarter(
        Document.objects.filter(kind="credit_note", status="issued", issue_date__year=year),
        "issue_date",
        "subtotal_cents",
    )
    expense_totals = _totals_by_quarter(
        Expense.objects.filter(date__year=year), "date", "amount_cents"
    )

    quarters = [
        QuarterTotals(
            quarter=q,
            # A credit note reduces recognised revenue, not a separate
            # expense line (invariant-adjacent to how documents.totals
            # treats a credit note as crediting an invoice, not billing
            # against it).
            revenue_cents=invoice_totals.get(q, 0) - credit_note_totals.get(q, 0),
            expenses_cents=expense_totals.get(q, 0),
        )
        for q in range(1, 5)
    ]

    # Per line: an expense can have lines in more than one category.
    by_category_qs = (
        ExpenseLine.objects.filter(expense__date__year=year)
        .values("category__name")
        .annotate(total=Sum("amount_cents"))
        .order_by("-total")
    )
    by_category = [
        CategoryTotal(
            name=row["category__name"] or str(_("Zonder categorie")),
            amount_cents=row["total"] or 0,
        )
        for row in by_category_qs
    ]

    return YearOverview(
        year=year,
        revenue_cents=sum(q.revenue_cents for q in quarters),
        expenses_cents=sum(q.expenses_cents for q in quarters),
        quarters=quarters,
        by_category=by_category,
    )


# The per-quarter chart on the year overview has four gridlines above zero.
CHART_STEPS = 4


def chart_step(max_cents: int) -> int:
    """The distance between gridlines, in cents: the smallest "round"
    amount (1, 2, 2.5 or 5 times a power of ten, in euros) of which
    CHART_STEPS cover the highest bar. With nothing to show, € 1.000."""
    if max_cents <= 0:
        return 100000
    magnitude = 100  # € 1
    while True:
        # 1, 2, 2.5 and 5 times the magnitude (which is always a multiple
        # of 100, so the 2.5 step stays a whole number of cents).
        for step in (magnitude, 2 * magnitude, magnitude * 5 // 2, 5 * magnitude):
            if step * CHART_STEPS >= max_cents:
                return step
        magnitude *= 10
