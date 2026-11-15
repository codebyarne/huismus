# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Overzicht page shows (SPEC.md M8). Only reads existing data:
payment state and outstanding amounts come from Document's own
with_payment_totals(), revenue and costs from huismus.reports.year_overview."""

from django.db.models import F, Q
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.business.topics import business_is_complete
from huismus.contacts.models import Contact
from huismus.documents.models import Document


def outstanding_invoices():
    """Issued invoices the customer still owes money on: how many, the
    total still open, how many of them are overdue and how much of the
    total that is. has_issued: whether there is any issued invoice at all.

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
    overdue = [d for d in open_invoices if d.is_overdue]
    return {
        "count": len(open_invoices),
        "total_cents": sum(d.outstanding_cents for d in open_invoices),
        "overdue_count": len(overdue),
        "overdue_cents": sum(d.outstanding_cents for d in overdue),
        "has_issued": bool(open_invoices) or issued.exists(),
    }


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
