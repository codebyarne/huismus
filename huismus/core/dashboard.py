# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Overzicht page shows (SPEC.md M8). Only reads existing data:
payment state and outstanding amounts come from Document's own
with_payment_totals(), revenue and costs from huismus.reports.year_overview."""

from dataclasses import dataclass

from django.db.models import F, Q
from django.urls import reverse
from django.utils.dates import MONTHS, MONTHS_3
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.business.topics import business_is_complete
from huismus.contacts.models import Contact
from huismus.documents.models import Document


def outstanding_invoices():
    """Issued invoices the customer still owes money on: how many, the
    total still open, how many of them are overdue and how much of the
    total that is. has_issued: whether there is any issued invoice at all.
    overdue: the overdue invoices themselves, the one that fell due last
    first, for "Te doen" on the overview (core.todo): after an import
    there can be open invoices of years ago, and those must not push last
    week's out of sight (huismus-intern/besluiten.md, 2026-11-18).

    The menu shows this on every page, so the query leaves out invoices
    that are settled (payments plus credit notes reach the total). The
    second clause keeps an invoice of € 0 with nothing paid, which
    payment_state calls "unpaid". The query only narrows: which invoices
    are open is still decided by Document.payment_state, and a test checks
    that the filter leaves out none of them."""
    issued = Document.objects.filter(kind="invoice", status="issued")
    invoices = issued.with_payment_totals().filter(
        Q(total_cents__gt=F("paid_cents") + F("credited_cents"))
        | Q(paid_cents__lte=0, credited_cents__lte=0)
    )
    open_invoices = [d for d in invoices if d.payment_state in ("unpaid", "partial")]
    overdue = sorted(
        (d for d in open_invoices if d.is_overdue), key=lambda d: (d.due_date, d.pk), reverse=True
    )
    return {
        "count": len(open_invoices),
        "total_cents": sum(d.outstanding_cents for d in open_invoices),
        "overdue_count": len(overdue),
        "overdue_cents": sum(d.outstanding_cents for d in overdue),
        "overdue": overdue,
        "has_issued": bool(open_invoices) or issued.exists(),
    }


@dataclass(frozen=True)
class MonthBar:
    """One month of the bars in the overview's petrol block (#215)."""

    month: int
    revenue_cents: int
    # Of the height of the year's best month, rounded down; 0 for a month
    # at or below zero.
    height_percent: int
    is_current: bool
    # A month still to come without revenue: drawn as a dashed line.
    is_ahead: bool

    @property
    def name(self):
        return MONTHS[self.month]

    @property
    def short(self):
        return MONTHS_3[self.month]

    @property
    def letter(self) -> str:
        """For a phone, where twelve names don't fit."""
        return str(self.short)[0]


def month_bars(monthly_revenue_cents: list[int], *, current_month: int) -> list[MonthBar]:
    """The year overview's revenue per month (YearOverview.
    monthly_revenue_cents) as twelve bars. Nothing is counted here: only
    how high each bar is drawn, in whole percents."""
    top = max(max(monthly_revenue_cents), 0)
    return [
        MonthBar(
            month=month,
            revenue_cents=cents,
            height_percent=max(cents, 0) * 100 // top if top else 0,
            is_current=month == current_month,
            is_ahead=month > current_month and cents == 0,
        )
        for month, cents in enumerate(monthly_revenue_cents, start=1)
    ]


def onboarding_steps():
    """The checklist on the first-time Overzicht, each step done or not,
    from what already exists."""
    settings = Settings.load()
    # Under the KOR its text goes on every invoice; without it, the VAT number.
    if settings.kor_enabled:
        kor_or_vat_done = bool(settings.kor_text.strip())
    else:
        kor_or_vat_done = bool(settings.vat_number.strip())
    return [
        {
            "key": "business",
            "title": _("Bedrijfsgegevens invullen"),
            "help": _("Naam, adres, KvK-nummer en IBAN. Dit komt op elke factuur."),
            "done": business_is_complete(settings),
            "url": reverse("business:topic", args=["bedrijf"]),
        },
        {
            "key": "logo",
            "title": _("Logo toevoegen"),
            "help": _("PNG, JPG of SVG. Mag ook later."),
            "done": bool(settings.logo),
            "url": reverse("business:topic", args=["huisstijl"]),
        },
        {
            "key": "kor",
            "title": _("KOR of btw instellen"),
            "help": _(
                "Gebruik je de KOR, dan komt die tekst op elke factuur. "
                "Reken je btw, dan komt je btw-nummer erop."
            ),
            "done": kor_or_vat_done,
            "url": reverse("business:topic", args=["kor"]),
        },
        {
            "key": "contact",
            "title": _("Eerste klant toevoegen"),
            "help": _("De klant aan wie je factureert."),
            "done": Contact.objects.exists(),
            "url": reverse("contacts:create"),
        },
        {
            "key": "invoice",
            "title": _("Eerste factuur maken"),
            "help": _("Eerst als concept. Pas bij uitgeven krijgt hij een nummer."),
            "done": Document.objects.filter(kind="invoice").exists(),
            "url": reverse("documents:create"),
        },
    ]
