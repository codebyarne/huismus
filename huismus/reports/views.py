# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from huismus.business.kor_limit import kor_limit_status
from huismus.business.models import Settings
from huismus.core.csv_files import Amount, csv_response
from huismus.core.profile import profile
from huismus.documents.models import Document
from huismus.expenses.models import Expense
from huismus.mileage.listing import year_mileage
from huismus.mileage.trips import DEDUCTION_SOURCE

from .icp import compute_icp
from .icp_csv import header as icp_header
from .icp_csv import rows as icp_rows
from .periods import MONTH, QUARTER, YEAR, Period
from .vat_return import EXEMPT_NOTE, KOR_NOTE, NOT_COUNTED_TITLES, compute_vat_return
from .vat_return_csv import header as vat_return_header
from .vat_return_csv import rows as vat_return_rows
from .year_overview import CHART_STEPS, chart_step, compute_year_overview

# What the ICP page says instead of figures (huismus-intern/besluiten.md,
# 2026-11-28, "Plan Opgaaf ICP" and "Opgaaf ICP (#168)"): only what Huismus
# does, nothing about whether a return is due; the source for that is
# missing (docs/belastingregels.md).
KOR_NOTE_ICP = _(
    "De KOR staat aan. Dan telt Huismus geen btw, dus dit overzicht heeft geen bedragen. "
    "Of je een opgaaf ICP moet doen, lees je bij de Belastingdienst."
)
EXEMPT_NOTE_ICP = _(
    "Je rekent geen btw. Dan telt Huismus geen btw, dus dit overzicht heeft geen bedragen. "
    "Of je een opgaaf ICP moet doen, lees je bij de Belastingdienst."
)


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
            "show_icp": profile().shows_icp,
            # Kilometers (#125): the distance, the trips, and what you may
            # deduct as information, never in the profit.
            "mileage": year_mileage(year),
            "deduction_source": DEDUCTION_SOURCE,
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


def _period_name(period: Period) -> str:
    if period.kind == QUARTER:
        return _("%(quarter)se kwartaal %(year)s") % {"quarter": period.number, "year": period.year}
    if period.kind == MONTH:
        return date_format(period.first_day, "F Y")
    return str(period.year)


# The quarters as the VAT return under the KOR names them.
QUARTER_MONTHS = [_("jan–mrt"), _("apr–jun"), _("jul–sep"), _("okt–dec")]


def _kor_year(today) -> dict:
    """With the KOR on there is no return to fill in: the page shows this
    year's revenue per quarter and how close it is to the KOR limit, the
    same figures as the year overview (one function for both). A quarter
    still to come has no figure (None)."""
    year = today.year
    current_quarter = (today.month - 1) // 3 + 1
    overview = compute_year_overview(year)
    return {
        "year": year,
        "quarters": [
            {
                "months": months,
                "revenue_cents": (
                    None if quarter.quarter > current_quarter else quarter.revenue_cents
                ),
            }
            for months, quarter in zip(QUARTER_MONTHS, overview.quarters, strict=True)
        ],
        "limit": kor_limit_status(year),
    }


@login_required
def vat_return(request):
    today = timezone.localdate()
    period = Period.parse(request.GET.get("periode"), today=today)
    report = compute_vat_return(period)
    return render(
        request,
        "reports/vat_return.html",
        {
            "kor_year": _kor_year(today) if report.kor_on else None,
            "report": report,
            "period": period,
            "period_name": _period_name(period),
            "kor_note": EXEMPT_NOTE if Settings.load().vat_exempt else KOR_NOTE,
            "titles": NOT_COUNTED_TITLES,
            "show_icp": profile().shows_icp,
            "kinds": [
                (period.as_kind(QUARTER), _("Kwartaal")),
                (period.as_kind(MONTH), _("Maand")),
                (period.as_kind(YEAR), _("Jaar")),
            ],
        },
    )


@login_required
def vat_return_csv(request):
    """The page as a CSV (SPEC.md M21, part 5). With the KOR on the page has
    no figures and no button; this address then leads back to it."""
    period = Period.parse(request.GET.get("periode"), today=timezone.localdate())
    report = compute_vat_return(period)
    if report.kor_on:
        return redirect(f"{reverse('reports:vat_return')}?periode={period}")
    return csv_response(f"btw-aangifte-{period}.csv", vat_return_header(), vat_return_rows(report))


# The source of the ICP page: where the user checks their own case
# (docs/belastingregels.md, "Opgaaf ICP").
ICP_SOURCE = (
    "https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/"
    "btw/zakendoen_met_het_buitenland/goederen_en_diensten_naar_andere_eu_landen/"
    "opgaaf_icp/opgaaf_icp"
)


def _icp_period(request, today) -> Period:
    """A quarter or a month: the services may go "per maand, per kwartaal
    of per jaar", but a year needs a licence, so Huismus offers no year
    (huismus-intern/product/profiel-en-functies.md, row Opgaaf ICP)."""
    period = Period.parse(request.GET.get("periode"), today=today)
    return period.as_kind(QUARTER) if period.kind == YEAR else period


@login_required
def icp(request):
    """The summary for the ICP return (issue #168)."""
    period = _icp_period(request, timezone.localdate())
    report = compute_icp(period)
    return render(
        request,
        "reports/icp.html",
        {
            "report": report,
            "period": period,
            "period_name": _period_name(period),
            "kor_note": EXEMPT_NOTE_ICP if Settings.load().vat_exempt else KOR_NOTE_ICP,
            "belastingdienst_url": ICP_SOURCE,
            "show_icp": profile().shows_icp,
            "kinds": [
                (period.as_kind(QUARTER), _("Kwartaal")),
                (period.as_kind(MONTH), _("Maand")),
            ],
        },
    )


@login_required
def icp_csv(request):
    """The page as a CSV. With the KOR on the page has no figures and no
    button; this address then leads back to it."""
    period = _icp_period(request, timezone.localdate())
    report = compute_icp(period)
    if report.kor_on:
        return redirect(f"{reverse('reports:icp')}?periode={period}")
    return csv_response(f"opgaaf-icp-{period}.csv", icp_header(), icp_rows(report))
