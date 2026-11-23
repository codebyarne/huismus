# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Revenue/expenses/profit summary for a calendar year (SPEC.md section
6). Read-only: a query over what's already there, not a new kind of
write, so there's no dry-run concept here the way imports/expenses
imports have.

Revenue is without VAT, the stored `subtotal_cents` of each document
(SPEC.md M18): the VAT on an invoice isn't the business's own money.
Under the KOR the VAT is 0, so nothing changes there.

Costs are gross, what was paid (CLAUDE.md, hard rule 7). With the KOR
off they are read without VAT and the input VAT is apart (SPEC.md M21,
part 3; product-owner agent 2026-11-07): per expense line at 21, 9 or 0%,
costs = gross - VAT and input VAT = VAT; a reverse charged line or one
without a rate stays gross. Stored amounts are never changed, only read.

Revenue counts on `Document.issue_date` (accrual), not a payment date
(cash) — the same date every other part of this app already treats as
authoritative for a document (numbering, snapshots, PDF dates), not a
tax position on which basis is "correct" for any particular purpose.
huismus-intern/STATUS.md's M6 plan flags this explicitly as a computation choice, not
an assertion, for the owner to weigh in on if their own bookkeeping expects a
cash-basis view instead.
"""

from dataclasses import dataclass, field

from django.db.models import Sum
from django.db.models.functions import ExtractMonth, ExtractQuarter
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.documents.models import Document
from huismus.expenses.models import Expense, ExpenseLine, VatRate

# The rates whose VAT is in what was paid, and so is input VAT without the
# KOR. Reverse charge isn't: the supplier charged none. A line with one of
# these rates and no VAT amount (a foreign-currency import has none) adds
# no input VAT: its costs stay gross.
INPUT_VAT_RATES = (VatRate.HIGH, VatRate.LOW, VatRate.ZERO)


@dataclass
class QuarterTotals:
    quarter: int
    revenue_cents: int = 0
    # Without VAT when the KOR is off (input_vat_cents apart), else gross.
    expenses_cents: int = 0
    input_vat_cents: int = 0

    @property
    def profit_cents(self) -> int:
        return self.revenue_cents - self.expenses_cents


@dataclass
class CategoryTotal:
    name: str
    amount_cents: int
    # The lines without a category, whatever a category happens to be called.
    uncategorised: bool = False


@dataclass
class YearOverview:
    year: int
    revenue_cents: int = 0
    expenses_cents: int = 0
    input_vat_cents: int = 0
    # The KOR is off: costs are without VAT and input VAT is shown.
    shows_input_vat: bool = False
    # January first. The quarters' and the year's revenue are sums of these
    # (the bars on the overview, #215): one count, read three ways.
    monthly_revenue_cents: list[int] = field(default_factory=lambda: [0] * 12)
    quarters: list[QuarterTotals] = field(default_factory=list)
    by_category: list[CategoryTotal] = field(default_factory=list)

    @property
    def profit_cents(self) -> int:
        return self.revenue_cents - self.expenses_cents

    @property
    def costs_label(self):
        """What the costs are called on the page: the one place that says."""
        return _("Kosten zonder btw") if self.shows_input_vat else _("Kosten")


def _totals_by_period(queryset, date_field: str, amount_field: str, extract) -> dict[int, int]:
    """Sums per quarter (ExtractQuarter) or month (ExtractMonth) number."""
    rows = (
        queryset.annotate(period=extract(date_field))
        .values("period")
        .annotate(total=Sum(amount_field))
    )
    return {row["period"]: row["total"] or 0 for row in rows}


def _revenue_by_month(year: int) -> list[int]:
    """Revenue per month, January first: issued invoices minus issued
    credit notes, by issue date. A credit note takes off revenue, so a
    month can be below zero."""
    issued = Document.objects.filter(status="issued", issue_date__year=year)
    invoices = _totals_by_period(
        issued.filter(kind="invoice"), "issue_date", "subtotal_cents", ExtractMonth
    )
    credit_notes = _totals_by_period(
        issued.filter(kind="credit_note"), "issue_date", "subtotal_cents", ExtractMonth
    )
    return [invoices.get(month, 0) - credit_notes.get(month, 0) for month in range(1, 13)]


def _totals_by_category(lines, amount_field: str = "amount_cents") -> dict[str | None, int]:
    rows = lines.values("category__name").annotate(total=Sum(amount_field))
    return {row["category__name"]: row["total"] or 0 for row in rows}


def compute_year_overview(year: int) -> YearOverview:
    monthly_revenue = _revenue_by_month(year)
    expense_totals = _totals_by_period(
        Expense.objects.filter(date__year=year), "date", "amount_cents", ExtractQuarter
    )
    shows_input_vat = not Settings.load().no_vat
    input_vat_lines = ExpenseLine.objects.filter(
        expense__date__year=year, vat_rate__in=INPUT_VAT_RATES
    )
    input_vat = (
        _totals_by_period(input_vat_lines, "expense__date", "vat_info_cents", ExtractQuarter)
        if shows_input_vat
        else {}
    )

    quarters = [
        QuarterTotals(
            quarter=q,
            # The quarter's three months.
            revenue_cents=sum(monthly_revenue[(q - 1) * 3 : q * 3]),
            expenses_cents=expense_totals.get(q, 0) - input_vat.get(q, 0),
            input_vat_cents=input_vat.get(q, 0),
        )
        for q in range(1, 5)
    ]

    # Per line: an expense can have lines in more than one category. Gross
    # per category, then without the KOR minus its input VAT, as above.
    gross_by_category = _totals_by_category(ExpenseLine.objects.filter(expense__date__year=year))
    input_vat_by_category = (
        _totals_by_category(input_vat_lines, "vat_info_cents") if shows_input_vat else {}
    )
    by_category = sorted(
        (
            CategoryTotal(
                name=name or str(_("Zonder categorie")),
                amount_cents=gross - input_vat_by_category.get(name, 0),
                uncategorised=name is None,
            )
            for name, gross in gross_by_category.items()
        ),
        key=lambda category: -category.amount_cents,
    )

    return YearOverview(
        year=year,
        revenue_cents=sum(q.revenue_cents for q in quarters),
        expenses_cents=sum(q.expenses_cents for q in quarters),
        input_vat_cents=sum(q.input_vat_cents for q in quarters),
        shows_input_vat=shows_input_vat,
        monthly_revenue_cents=monthly_revenue,
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
