# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the Overzicht page shows (SPEC.md M8). Only reads existing data:
payment state and outstanding amounts come from Document's own
with_payment_totals(), revenue and costs from huismus.expenses.year_overview."""

from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.business.topics import business_is_complete
from huismus.contacts.models import Contact
from huismus.documents.models import Document


def outstanding_invoices():
    """Issued invoices the customer still owes money on: how many, the
    total still open, and how many of them are overdue."""
    invoices = Document.objects.filter(kind="invoice", status="issued").with_payment_totals()
    open_invoices = [d for d in invoices if d.payment_state in ("unpaid", "partial")]
    return {
        "count": len(open_invoices),
        "total_cents": sum(d.outstanding_cents for d in open_invoices),
        "overdue_count": sum(1 for d in open_invoices if d.is_overdue),
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
