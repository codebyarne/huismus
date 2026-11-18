# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Tabs and search for the invoice list (SPEC.md M8).

Filtering happens in Python, on documents loaded with
Document.objects.with_payment_totals(). A freelancer under the KOR has at most a
few hundred invoices, and this way the tabs use payment_state itself instead
of a second, SQL version of the same rule.
"""

from django.utils.text import capfirst, format_lazy
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

# (slug in the URL, label). The first one is the default.
INVOICE_TABS = [
    ("alle", _("Alle")),
    ("concepten", _("Concepten")),
    ("openstaand", _("Openstaand")),
    ("betaald", _("Betaald")),
    ("creditnotas", _("Creditnota's")),
]


# The order of the invoice list (#186): what needs the user first. The list
# shows no heading per group (the owner, 2026-11-17); the Status column says it.
INVOICE_GROUPS = ("te-laat", "wacht", "concept", "betaald", "creditnotas")
GROUP_RANK = {group: rank for rank, group in enumerate(INVOICE_GROUPS)}


def invoice_group(document):
    """Which group of the invoice list a document belongs to. Drafts of
    either kind are "not sent yet"; fully credited invoices count as paid,
    like the tab Betaald."""
    if document.status == "draft":
        return "concept"
    if document.kind == "credit_note":
        return "creditnotas"
    if document.is_overdue:
        return "te-laat"
    if document.payment_state in ("unpaid", "partial"):
        return "wacht"
    return "betaald"


def grouped(documents):
    """The documents with .group set, sorted by group in INVOICE_GROUPS
    order. Within a group they keep the order they came in."""
    for document in documents:
        document.group = invoice_group(document)
    return sorted(documents, key=lambda d: GROUP_RANK[d.group])


def waiting_label(document, today):
    """The status of an invoice in the group "Wacht op betaling": how long
    until it is due, "Deels betaald" in front if part is paid. Without a due
    date only the payment state."""
    partial = document.payment_state == "partial"
    if document.due_date is None:
        return _("Deels betaald") if partial else _("Onbetaald")
    days = (document.due_date - today).days
    if days == 0:
        when = _("vandaag te betalen")
    else:
        when = ngettext("nog %(days)s dag", "nog %(days)s dagen", days) % {"days": days}
    if partial:
        return format_lazy("{}, {}", _("Deels betaald"), when)
    return capfirst(when)


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

# Tab -> the quote statuses it shows, as the user reads them
# (Document.shown_status): a sent quote past its date is under "afgewezen".
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
    return statuses is None or document.shown_status in statuses


def expiry_hint(quote, *, today):
    """For a quote still waiting for an answer: ("soon", days_left) from
    EXPIRY_HINT_DAYS before its expiry date, else None. After that date it
    reads as expired (Document.shown_status) and needs no hint."""
    if quote.status != "sent" or quote.expiry_date is None:
        return None
    days_left = (quote.expiry_date - today).days
    if 0 <= days_left <= EXPIRY_HINT_DAYS:
        return ("soon", days_left)
    return None


# What a column of the invoice list sorts on. A credit note's amount counts
# as money going back, as the list shows it.
INVOICE_SORT_KEYS = {
    "klant": lambda d: contact_name(d).casefold(),
    "nummer": lambda d: d.number or "",
    "datum": lambda d: (d.issue_date is not None, d.issue_date),
    "status": lambda d: GROUP_RANK[d.group],
    "bedrag": lambda d: -d.total_cents if d.kind == "credit_note" else d.total_cents,
}

# The order of quote statuses when sorting on Status: what still needs the
# user first.
QUOTE_STATUS_RANK = {
    status: rank for rank, status in enumerate(("draft", "sent", "accepted", "declined", "expired"))
}


# What a column of the quote list sorts on. Status goes by what the row
# shows, so the rows that read Verlopen stay together.
QUOTE_SORT_KEYS = {
    "klant": lambda q: contact_name(q).casefold(),
    "nummer": lambda q: q.number or "",
    "geldig": lambda q: (q.expiry_date is not None, q.expiry_date),
    "status": lambda q: QUOTE_STATUS_RANK[q.shown_status],
    "totaal": lambda q: q.total_cents,
}
