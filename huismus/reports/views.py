# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth.decorators import login_required
from django.shortcuts import render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.business.kor_limit import kor_limit_status
from huismus.core.csv_files import Amount, csv_response
from huismus.documents.models import Document
from huismus.expenses.models import Expense

from .year_overview import CHART_STEPS, chart_step, compute_year_overview


def _requested_year(request) -> int:
    try:
        return int(request.GET.get("jaar", timezone.localdate().year))
    except ValueError:
        return timezone.localdate().year


@login_required
def year_overview(request):
    year = _requested_year(request)
    overview = compute_year_overview(year)

    # Per-quarter bar chart: bar heights as whole percentages of the axis
    # (a negative quarter, more credited than invoiced, draws as empty).
    highest = max(
        [q.revenue_cents for q in overview.quarters] + [q.expenses_cents for q in overview.quarters]
    )
    step = chart_step(highest)
    axis_cents = step * CHART_STEPS

    def percent(cents):
        return max(0, cents) * 100 // axis_cents

    bars = [
        {
            "quarter": q,
            "revenue_percent": percent(q.revenue_cents),
            "expenses_percent": percent(q.expenses_cents),
        }
        for q in overview.quarters
    ]
    ticks = [step * n for n in range(CHART_STEPS, -1, -1)]

    # Horizontal bars per category, relative to the largest category.
    largest = max((c.amount_cents for c in overview.by_category), default=0)
    categories = [
        {"category": c, "percent": c.amount_cents * 100 // largest if largest else 0}
        for c in overview.by_category
    ]

    invoices = Document.objects.filter(status="issued", issue_date__year=year)
    return render(
        request,
        "reports/year_overview.html",
        {
            "overview": overview,
            "year": year,
            "this_year": timezone.localdate().year,
            # None while the KOR is off: then there is no card. The limit set
            # now, also for earlier years (no history is kept).
            "kor_limit": kor_limit_status(year),
            "bars": bars,
            "ticks": ticks,
            "categories": categories,
            "invoice_count": invoices.filter(kind="invoice").count(),
            "credit_note_count": invoices.filter(kind="credit_note").count(),
            "expense_count": Expense.objects.filter(date__year=year).count(),
        },
    )


@login_required
def year_overview_csv(request):
    year = _requested_year(request)
    overview = compute_year_overview(year)
    lines = [(f"Q{quarter.quarter}", quarter) for quarter in overview.quarters]
    lines.append((_("totaal"), overview))
    # Without the KOR: costs without VAT and a column with the input VAT,
    # as on the page (SPEC.md M21, part 3).
    if overview.shows_input_vat:
        header = [_("kwartaal"), _("omzet"), _("kosten zonder btw"), _("voorbelasting"), _("winst")]
        rows = [
            [
                label,
                Amount(totals.revenue_cents),
                Amount(totals.expenses_cents),
                Amount(totals.input_vat_cents),
                Amount(totals.profit_cents),
            ]
            for label, totals in lines
        ]
    else:
        header = [_("kwartaal"), _("omzet"), _("kosten"), _("winst")]
        rows = [
            [
                label,
                Amount(totals.revenue_cents),
                Amount(totals.expenses_cents),
                Amount(totals.profit_cents),
            ]
            for label, totals in lines
        ]
    return csv_response(f"jaaroverzicht-{year}.csv", header, rows)
