# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The list "Te doen" on the Overzicht page (#189): what waits for the
user, the most urgent first. Overdue invoices, quotes without an answer,
draft invoices, then receipts and expenses to check.

Nothing is stored and nothing is counted anew: the view hands in what the
overview already has (core.dashboard.outstanding_invoices, the sent quotes,
the drafts, expenses.batch.counts). Here they only become rows with a text
and a place to go."""

from dataclasses import dataclass

from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from huismus.core.templatetags.money import money
from huismus.documents.listing import contact_name

# Rows per kind. What doesn't fit becomes one closing row ("Nog 4 facturen
# te laat") that goes to the list (huismus-intern/besluiten.md, 2026-11-18).
MAX_PER_KIND = 3
# From this many days a row names the date instead of counting days, like
# the "Te laat" pill in the lists (huismus-intern/besluiten.md, 2026-11-15).
DAYS_BECOME_A_DATE = 100

OVERDUE, QUOTE, DRAFT, RECEIPTS, TO_CHECK, MORE = (
    "te-laat",
    "offerte",
    "concept",
    "bonnetjes",
    "nakijken",
    "meer",
)


@dataclass(frozen=True)
class TodoItem:
    kind: str
    title: str
    detail: str
    # The button: what it says and where it goes.
    action: str
    action_url: str
    icon: str
    # Where the title goes, when that is another place than the button.
    url: str = ""

    @property
    def is_late(self) -> bool:
        """The only rows in raspberry: an invoice past its due date."""
        return self.kind == OVERDUE


@dataclass(frozen=True)
class Todo:
    items: list[TodoItem]
    # Everything that waits, also what has no row of its own.
    count: int


def _short_date(date) -> str:
    return date_format(date, "SHORT_DATE_FORMAT")


def _more(title: str, detail: str, url: str, icon: str) -> TodoItem:
    """The closing row of a kind with more than MAX_PER_KIND."""
    return TodoItem(MORE, title, detail, _("Bekijken"), url, icon)


def _overdue_item(invoice) -> TodoItem:
    days = invoice.days_overdue
    values = {"number": invoice.number, "days": days}
    if days >= DAYS_BECOME_A_DATE:
        title = _("Factuur %(number)s is te laat sinds %(date)s") % {
            **values,
            "date": _short_date(invoice.due_date),
        }
    else:
        title = (
            ngettext(
                "Factuur %(number)s is %(days)s dag te laat",
                "Factuur %(number)s is %(days)s dagen te laat",
                days,
            )
            % values
        )
    parts = [contact_name(invoice), money(invoice.outstanding_cents)]
    last_reminder = invoice.emails.filter(succeeded=True, reminder=True).order_by("sent_at").last()
    if last_reminder:
        parts.append(
            _("laatste herinnering: %(date)s") % {"date": _short_date(last_reminder.sent_at)}
        )
    return TodoItem(
        kind=OVERDUE,
        title=title,
        detail=" · ".join(parts),
        action=_("Herinnering sturen"),
        action_url=reverse("documents:reminder", args=[invoice.pk]),
        icon="clock",
        url=reverse("documents:edit", args=[invoice.pk]),
    )


def _quote_item(quote, hint, today) -> TodoItem:
    values = {"number": quote.number}
    days = (today - quote.issue_date).days if quote.issue_date else 0
    if days >= DAYS_BECOME_A_DATE:
        title = _("Offerte %(number)s wacht sinds %(date)s op antwoord") % {
            **values,
            "date": _short_date(quote.issue_date),
        }
    elif days > 0:
        title = ngettext(
            "Offerte %(number)s wacht %(days)s dag op antwoord",
            "Offerte %(number)s wacht %(days)s dagen op antwoord",
            days,
        ) % {**values, "days": days}
    else:
        # Sent today, or dated ahead.
        title = _("Offerte %(number)s wacht op antwoord") % values
    parts = [contact_name(quote), money(quote.total_cents)]
    # hint: documents.listing.expiry_hint, ("soon", days left) or None.
    if hint:
        days_left = hint[1]
        if days_left == 0:
            parts.append(_("verloopt vandaag"))
        else:
            parts.append(
                ngettext("verloopt over %(days)s dag", "verloopt over %(days)s dagen", days_left)
                % {"days": days_left}
            )
    return TodoItem(
        kind=QUOTE,
        title=title,
        detail=" · ".join(parts),
        action=_("Bekijken"),
        action_url=reverse("quotes:edit", args=[quote.pk]),
        icon="tag",
    )


def _draft_item(draft) -> TodoItem:
    customer = contact_name(draft)
    if customer:
        title = _("Je concept voor %(customer)s staat klaar") % {"customer": customer}
    else:
        title = _("Je concept heeft nog geen klant")
    # Back in draft through "Toch bewerken", it kept its number
    # (documents.reopening): it was sent before, so the row names it.
    state = draft.number or _("nog niet verstuurd")
    return TodoItem(
        kind=DRAFT,
        title=title,
        detail=f"{money(draft.total_cents)} · {state}",
        action=_("Afmaken"),
        action_url=reverse("documents:edit", args=[draft.pk]),
        icon="file",
    )


def build_todo(*, overdue, waiting_quotes, drafts, tray_count, to_check_count, today) -> Todo:
    """`overdue`: overdue invoices, the longest overdue first.
    `waiting_quotes`: (quote, expiry hint) pairs. `drafts`: draft invoices."""
    overdue, waiting_quotes, drafts = list(overdue), list(waiting_quotes), list(drafts)
    items = [_overdue_item(invoice) for invoice in overdue[:MAX_PER_KIND]]
    rest = len(overdue) - MAX_PER_KIND
    if rest > 0:
        items.append(
            _more(
                ngettext("Nog %(count)s factuur te laat", "Nog %(count)s facturen te laat", rest)
                % {"count": rest},
                _("Ze staan bij Facturen onder Openstaand."),
                reverse("documents:list") + "?tab=openstaand&jaar=alle",
                "clock",
            )
        )

    items += [_quote_item(quote, hint, today) for quote, hint in waiting_quotes[:MAX_PER_KIND]]
    rest = len(waiting_quotes) - MAX_PER_KIND
    if rest > 0:
        items.append(
            _more(
                ngettext(
                    "Nog %(count)s offerte wacht op antwoord",
                    "Nog %(count)s offertes wachten op antwoord",
                    rest,
                )
                % {"count": rest},
                _("Ze staan bij Offertes."),
                reverse("quotes:list"),
                "tag",
            )
        )

    items += [_draft_item(draft) for draft in drafts[:MAX_PER_KIND]]
    rest = len(drafts) - MAX_PER_KIND
    if rest > 0:
        items.append(
            _more(
                ngettext("Nog %(count)s concept", "Nog %(count)s concepten", rest)
                % {"count": rest},
                _("Ze staan bij Facturen onder Concepten."),
                reverse("documents:list") + "?tab=concepten",
                "file",
            )
        )

    if tray_count:
        items.append(
            TodoItem(
                kind=RECEIPTS,
                title=ngettext(
                    "%(count)s bonnetje zonder uitgave",
                    "%(count)s bonnetjes zonder uitgave",
                    tray_count,
                )
                % {"count": tray_count},
                detail=_("Maak er een uitgave van."),
                action=_("Verwerken"),
                action_url=reverse("expenses:tray"),
                icon="receipt",
            )
        )
    if to_check_count:
        items.append(
            TodoItem(
                kind=TO_CHECK,
                title=ngettext(
                    "%(count)s uitgave om na te kijken",
                    "%(count)s uitgaven om na te kijken",
                    to_check_count,
                )
                % {"count": to_check_count},
                detail=_("Kijk of het bedrag en de datum kloppen."),
                action=_("Nakijken"),
                action_url=reverse("expenses:list") + "?nakijken=1",
                icon="receipt",
            )
        )

    return Todo(
        items=items,
        count=len(overdue) + len(waiting_quotes) + len(drafts) + tray_count + to_check_count,
    )
