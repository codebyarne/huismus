# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabs and search for the invoice list (SPEC.md M8).

Filtering happens in Python, on documents loaded with
Document.objects.with_payment_totals(). A freelancer under the KOR has at most a
few hundred invoices, and this way the tabs use payment_state itself instead
of a second, SQL version of the same rule.
"""

from django.utils.translation import gettext_lazy as _

# (slug in the URL, label). The first one is the default.
INVOICE_TABS = [
    ("alle", _("Alle")),
    ("concepten", _("Concepten")),
    ("openstaand", _("Openstaand")),
    ("betaald", _("Betaald")),
    ("creditnotas", _("Creditnota's")),
]


def in_tab(document, tab):
    if tab == "concepten":
        return document.status == "draft"
    if tab == "openstaand":
        return document.payment_state in ("unpaid", "partial")
    if tab == "betaald":
        # Settled either way: nothing left to pay.
        return document.payment_state in ("paid", "credited")
    if tab == "creditnotas":
        return document.kind == "credit_note"
    return True


def contact_name(document):
    """The customer as the list shows it: from the snapshot once a document
    is issued (invariant 5), from the live contact while it's a draft."""
    if document.contact_snapshot:
        return document.contact_snapshot.get("display_name", "")
    return document.contact.display_name if document.contact else ""


def matches_search(document, query):
    """Case-insensitive match on the number or the customer name."""
    if not query:
        return True
    haystack = f"{document.number} {contact_name(document)}".lower()
    return query.lower() in haystack


# --- Quotes ---

QUOTE_TABS = [
    ("alle", _("Alle")),
    ("concepten", _("Concepten")),
    ("wachten", _("Wachten op antwoord")),
    ("geaccepteerd", _("Geaccepteerd")),
    ("afgewezen", _("Afgewezen of verlopen")),
]

# Tab -> the quote statuses it shows.
_QUOTE_TAB_STATUSES = {
    "concepten": {"draft"},
    "wachten": {"sent"},
    "geaccepteerd": {"accepted"},
    "afgewezen": {"declined", "expired"},
}

# A quote waiting for an answer gets a hint this many days before it expires.
EXPIRY_HINT_DAYS = 7


def in_quote_tab(document, tab):
    statuses = _QUOTE_TAB_STATUSES.get(tab)
    return statuses is None or document.status in statuses


def expiry_hint(quote, *, today):
    """For a sent quote: ("soon", days_left) from EXPIRY_HINT_DAYS before its
    expiry date, ("past", None) once that date has passed, else None."""
    if quote.status != "sent" or quote.expiry_date is None:
        return None
    days_left = (quote.expiry_date - today).days
    if days_left < 0:
        return ("past", None)
    if days_left <= EXPIRY_HINT_DAYS:
        return ("soon", days_left)
    return None
