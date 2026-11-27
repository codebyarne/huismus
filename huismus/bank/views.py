# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank → Bankafschrift inlezen (#77). Its own menu item since the owner's
decision of 2026-11-21 (first a button on Facturen); texts and choices by
the product-owner agent 2026-11-20, huismus-intern/besluiten.md.

One page (direction D, owner 2026-11-21): what the latest statement held,
then three sections that fold: Te doen (lines that fit an invoice or an
expense), Geboekt, and Niet herkend (lines that fit nothing, folded: often
private money, nothing to do). Money going out (#257) sits in the same
sections as money coming in, on date; Niet herkend has tabs Alles · Bij · Af
and shows 20 lines at a time (product-owner agent 2026-11-21). Every
action is a plain POST that comes back to the page, on the same tab.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST

from huismus.core.templatetags.money import money
from huismus.documents.models import Document
from huismus.expenses.models import Expense

from . import balances, expense_matching, reading
from .expense_matching import OpenExpense
from .lines import StatementReadError
from .matching import OpenInvoice, match
from .models import BankStatement, BankTransaction

State = BankTransaction.State

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

# Lazy: translated in the language of the request, not when Python loads this.
NOT_A_STATEMENT = gettext_lazy(
    "Huismus herkent dit bestand niet als bankafschrift. "
    "Download het bij je bank als CAMT.053 of MT940."
)
TOO_BIG = gettext_lazy("Dit bestand is groter dan 50 MB. Kies bij je bank een kortere periode.")


def summary_text(summary: dict, waiting: int = 0) -> str:
    """'15 betalingen gelezen van rekening NL91 …: 6 erbij, 9 eraf. Huismus
    boekte er 4 en 1 stond al geboekt. 9 wachten hieronder op je.' Only the
    parts that aren't 0 (product-owner agent 2026-11-21, ronde 9 point 6).
    `waiting`: this statement's lines under Te doen now; a line under Niet
    herkend doesn't wait for anything."""
    read = summary.get("read", 0)
    accounts = summary.get("accounts", [])
    if len(accounts) == 1:
        first = ngettext(
            "%(count)s betaling gelezen van rekening %(iban)s",
            "%(count)s betalingen gelezen van rekening %(iban)s",
            read,
        ) % {"count": read, "iban": _grouped(accounts[0])}
    else:
        first = ngettext("%(count)s betaling gelezen", "%(count)s betalingen gelezen", read) % {
            "count": read
        }
    sides = []
    if summary.get("incoming"):
        sides.append(_("%(count)s erbij") % {"count": summary["incoming"]})
    if summary.get("outgoing"):
        sides.append(_("%(count)s eraf") % {"count": summary["outgoing"]})
    sentences = [first + (": " + ", ".join(sides) if sides else "") + "."]
    booked, already = summary.get("booked", 0), summary.get("already_booked", 0)
    if booked and already:
        sentences.append(
            ngettext(
                "Huismus boekte er %(booked)s en %(count)s stond al geboekt.",
                "Huismus boekte er %(booked)s en %(count)s stonden al geboekt.",
                already,
            )
            % {"booked": booked, "count": already}
        )
    elif booked:
        sentences.append(_("Huismus boekte er %(booked)s.") % {"booked": booked})
    elif already:
        sentences.append(
            ngettext("%(count)s stond al geboekt.", "%(count)s stonden al geboekt.", already)
            % {"count": already}
        )
    if waiting:
        sentences.append(
            ngettext(
                "%(count)s wacht hieronder op je.", "%(count)s wachten hieronder op je.", waiting
            )
            % {"count": waiting}
        )
    seen = summary.get("seen_before", 0)
    if seen:
        sentences.append(
            ngettext("%(count)s was al ingelezen.", "%(count)s waren al ingelezen.", seen)
            % {"count": seen}
        )
    return " ".join(sentences)


def _grouped(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


@dataclass
class Waiting:
    """A line that waits for the user, with what the page shows of it."""

    line: BankTransaction
    # What to choose from: open invoices (money in) or expenses without a
    # bank line (money out), the ones that fit first.
    choices: list
    several_numbers: bool = False
    # For Klopt dit?: the proposed invoice or expense, and (an invoice) how
    # much the payment is more (positive) or less (negative) than what is
    # open on it.
    proposal: OpenInvoice | OpenExpense | None = None
    difference_cents: int = 0
    # Money out only: an expense without a bank line has exactly this
    # amount, in the window of expense_matching, and is chosen first in the
    # list: "Er is al een uitgave met dit bedrag."
    same_amount: bool = False

    @property
    def short_cents(self) -> int:
        return -self.difference_cents


# How many expenses with another amount the list adds: the closest in
# date. Years of expenses in one list helps nobody.
OTHER_EXPENSE_CHOICES = 50


def _expense_choices(line, first, open_expenses) -> list[OpenExpense]:
    """`first`, then every expense with the line's amount, also from
    outside the window (one that is old must be choosable, product-owner
    agent 2026-11-21 point 1), then 50 others closest in date."""
    gross = -line.amount_cents
    choices = list(first)
    by_date = sorted(open_expenses, key=lambda e: abs((line.booked_on - e.date).days))
    choices += [e for e in by_date if e.gross_cents == gross and e not in choices]
    others = [e for e in by_date if e not in choices]
    return choices + others[:OTHER_EXPENSE_CHOICES]


def _waiting_incoming(line, open_invoices, by_pk) -> tuple[str, Waiting]:
    found = match(reading.as_statement_line(line), open_invoices)
    stored = by_pk.get(line.proposed_document_id)
    first = [stored] if stored else []
    first += [found.invoice] if found.invoice else []
    choices = []
    for invoice in first + list(found.candidates) + open_invoices:
        if invoice not in choices:
            choices.append(invoice)
    item = Waiting(line, choices, several_numbers=found.several_numbers)
    if line.state == State.PROPOSED and stored is not None:
        item.proposal = stored
        item.difference_cents = line.amount_cents - stored.outstanding_cents
        return "proposed", item
    if first or found.candidates or found.several_numbers:
        # A proposal whose invoice was paid meanwhile is a line to choose for.
        return "choose", item
    # Nothing fits: often private money. It waits without asking.
    return "unknown", item


def _waiting_outgoing(line, open_expenses, by_pk, others) -> tuple[str, Waiting]:
    """The list to choose from: the stored proposal (or the expense undone
    from), then what matching found, then the rest (_expense_choices)."""
    as_line = reading.as_statement_line(line)
    found = expense_matching.match(as_line, open_expenses, others)
    stored = by_pk.get(line.proposed_expense_id)
    # Whatever matching found has the line's amount: sure, likely or choose.
    with_amount = [e for e in [found.expense, *found.candidates] if e is not None]
    first = ([stored] if stored else []) + [e for e in with_amount if e != stored]
    choices = _expense_choices(line, first, open_expenses)
    item = Waiting(line, choices, same_amount=bool(with_amount))
    if line.state == State.PROPOSED and stored is not None:
        item.proposal = stored
        return "proposed", item
    if first:
        # Undone, or an expense with the amount: the user chooses.
        return "choose", item
    return "unknown", item


def _waiting(open_invoices, open_expenses):
    """The lines that wait: (proposals, lines to choose for, not recognised),
    the first two under Te doen. The proposal is the stored one; matching runs
    again to order the choices and to see whether anything fits at all,
    since what is open changed since the statement was read."""
    invoices = {invoice.pk: invoice for invoice in open_invoices}
    expenses = {expense.pk: expense for expense in open_expenses}
    lines = list(BankTransaction.objects.waiting())
    going_out = {line.pk: reading.as_statement_line(line) for line in lines if line.is_outgoing}
    found = {"proposed": [], "choose": [], "unknown": []}
    for line in lines:
        if line.is_outgoing:
            others = [other for pk, other in going_out.items() if pk != line.pk]
            kind, item = _waiting_outgoing(line, open_expenses, expenses, others)
        else:
            kind, item = _waiting_incoming(line, open_invoices, invoices)
        found[kind].append(item)
    return found["proposed"], found["choose"], found["unknown"]


def to_do_and_unknown() -> tuple[list[Waiting], list[Waiting]]:
    """Te doen, on date with money in and out together as on the statement,
    and Niet herkend. The page and the AI connection (#273) read this."""
    proposed, to_choose, unknown = _waiting(reading.open_invoices(), reading.open_expenses())
    to_do = sorted(proposed + to_choose, key=lambda item: (item.line.booked_on, item.line.pk))
    return to_do, unknown


def booked_lines(statement) -> list[BankTransaction]:
    """Geboekt: a statement's lines that are booked, by Huismus, by the
    user, or before the statement came in."""
    if statement is None:
        return []
    lines = statement.transactions.select_related("payment__document", "expense")
    return [t for t in lines if t.state in (State.BOOKED, State.CONFIRMED, State.ALREADY_BOOKED)]


def to_do_count() -> int:
    """The lines under Te doen, for the overview (core.todo): a line that
    fits nothing doesn't ask for anything."""
    proposed, to_choose, _unknown = _waiting(reading.open_invoices(), reading.open_expenses())
    return len(proposed) + len(to_choose)


@dataclass
class Report:
    """The tiles at the top: what the statement held."""

    total: int  # every line read from the file
    fitting: int  # lines that fit an invoice or expense: booked, already there, or in Te doen
    incoming_cents: int
    incoming: int
    outgoing_cents: int  # without sign: what went out
    outgoing: int
    first_day: object
    last_day: object

    @property
    def fitting_percent(self) -> int:
        return round(100 * self.fitting / self.total) if self.total else 0


def _report(statement, to_do_pks) -> Report | None:
    if statement is None:
        return None
    lines = list(statement.transactions.all())
    coming_in = [t for t in lines if not t.is_outgoing]
    going_out = [t for t in lines if t.is_outgoing]
    fitting = sum(
        1
        for t in lines
        if t.state in (State.BOOKED, State.CONFIRMED, State.ALREADY_BOOKED) or t.pk in to_do_pks
    )
    days = [t.booked_on for t in lines]
    return Report(
        total=len(lines),
        fitting=fitting,
        incoming_cents=sum(t.amount_cents for t in coming_in),
        incoming=len(coming_in),
        outgoing_cents=sum(t.gross_cents for t in going_out),
        outgoing=len(going_out),
        first_day=min(days) if days else None,
        last_day=max(days) if days else None,
    )


def gap_notices() -> list[str]:
    """One warning per account where a statement is missing (#159;
    product-owner agent 2026-11-27, point 3): the first gap, and how many
    there are when more."""
    notices = []
    per_account: dict[str, list[balances.Gap]] = {}
    for gap in balances.gaps():
        per_account.setdefault(gap.account_iban, []).append(gap)
    for account, found in per_account.items():
        first = found[0]
        values = {
            "iban": _grouped(account),
            "end": date_format(first.closed_on, "SHORT_DATE_FORMAT"),
            "start": date_format(first.opened_on, "SHORT_DATE_FORMAT"),
            "closing": money(first.closing_cents),
            "opening": money(first.opening_cents),
            "count": len(found),
        }
        if len(found) == 1:
            text = _(
                "Er mist een afschrift van %(iban)s tussen %(end)s en %(start)s. Het saldo "
                "was %(closing)s en begint daarna op %(opening)s. Lees dat afschrift ook in."
            )
        else:
            text = _(
                "Er missen afschriften van %(iban)s: het saldo sluit %(count)s keer niet aan. "
                "De eerste keer is tussen %(end)s en %(start)s. Lees de afschriften van die "
                "periodes in."
            )
        notices.append(text % values)
    return notices


# Niet herkend: which side (?kant=), and how many lines (?toon=), 20 more
# per "Toon meer" (product-owner agent 2026-11-21, point 3).
SHOW_STEP = 20


def _unknown_url(request, side, show=None) -> str:
    """This page with another tab or more lines in Niet herkend; the
    statement shown stays."""
    query = request.GET.copy()
    query["kant"] = side
    query.pop("toon", None)
    if show:
        query["toon"] = show
    return f"?{query.urlencode()}#niet-herkend"


def _unknown_view(request, unknown):
    incoming = [item for item in unknown if not item.line.is_outgoing]
    outgoing = [item for item in unknown if item.line.is_outgoing]
    # The tabs only when both sides have lines; else the one side is all.
    tabs = bool(incoming and outgoing)
    side = request.GET.get("kant", "") if tabs else ""
    shown = {"bij": incoming, "af": outgoing}.get(side, unknown)
    count = request.GET.get("toon", "")
    # Never fewer than the first 20, whatever ?toon= says.
    limit = max(int(count), SHOW_STEP) if count.isdigit() else SHOW_STEP
    return {
        "unknown": shown[:limit],
        "unknown_total": len(unknown),
        "unknown_tabs": tabs,
        "unknown_side": side,
        "unknown_incoming": len(incoming),
        "unknown_outgoing": len(outgoing),
        "unknown_more": len(shown) - limit if len(shown) > limit else 0,
        "unknown_more_url": _unknown_url(request, side, limit + SHOW_STEP),
        "unknown_all_url": _unknown_url(request, ""),
        "unknown_in_url": _unknown_url(request, "bij"),
        "unknown_out_url": _unknown_url(request, "af"),
        # Opened by a tab or Toon meer, or coming back from an action there.
        "unknown_open": "kant" in request.GET or "toon" in request.GET,
    }


@login_required
def statement_page(request):
    error = None
    if request.method == "POST":
        upload = request.FILES.get("bestand")
        if upload is None:
            error = NOT_A_STATEMENT
        elif upload.size > MAX_UPLOAD_BYTES:
            error = TOO_BIG
        else:
            try:
                result = reading.read_statement(upload.name, upload.read())
            except reading.UnzippedTooBigError:
                error = _(
                    "Deze zip is uitgepakt groter dan %(max_mb)s MB, te groot om in te "
                    "lezen. Kies bij je bank een kortere periode."
                ) % {"max_mb": reading.MAX_UNZIPPED_BYTES // 1024**2}
            except StatementReadError:
                error = NOT_A_STATEMENT
            else:
                if result.statement is None:
                    if result.balances_added:
                        nothing_new = _(
                            "Niets nieuws: alle betalingen in dit bestand waren al ingelezen. "
                            "Het saldo is bijgewerkt."
                        )
                    else:
                        nothing_new = _(
                            "Niets nieuws: alle betalingen in dit bestand waren al ingelezen."
                        )
                    messages.info(request, nothing_new)
                    return redirect("bank:statement")
                return redirect(f"{reverse('bank:statement')}?afschrift={result.statement.pk}")

    # ?afschrift= is where reading a file redirects to: then the page opens
    # with its summary. Without it, the latest statement's bookings show,
    # without a summary.
    statement = None
    requested = request.GET.get("afschrift", "")
    if requested.isdigit():
        statement = BankStatement.objects.filter(pk=requested).first()
    if statement is None:
        statement = BankStatement.objects.first()

    to_do, unknown = to_do_and_unknown()
    booked = booked_lines(statement)
    to_do_pks = {item.line.pk for item in to_do}
    waiting_here = sum(1 for item in to_do if statement and item.line.statement_id == statement.pk)
    return render(
        request,
        "bank/statement.html",
        {
            "nav_section": "bank",
            "error": error,
            "statement": statement,
            "summary": summary_text(statement.summary, waiting_here)
            if statement and requested
            else "",
            "report": _report(statement, to_do_pks),
            # The latest balance per account, whatever statement is shown
            # (product-owner agent 2026-11-27, point 1).
            "balances": [
                {"balance": b, "iban": _grouped(b.account_iban)} for b in balances.latest()
            ],
            "gap_notices": gap_notices(),
            "booked": booked,
            "to_do": to_do,
            "skipped_count": BankTransaction.objects.filter(state=State.SKIPPED).count(),
            "here": request.get_full_path(),
            **_unknown_view(request, unknown),
        },
    )


@login_required
def skipped_page(request):
    return render(
        request,
        "bank/skipped.html",
        {
            "nav_section": "bank",
            "lines": BankTransaction.objects.filter(state=State.SKIPPED).order_by("-booked_on"),
            "here": request.get_full_path(),
        },
    )


def _back(request):
    target = request.POST.get("terug", "")
    if url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
        return redirect(target)
    return redirect("bank:statement")


def _line(pk):
    return get_object_or_404(BankTransaction, pk=pk)


@login_required
@require_POST
def confirm(request, pk):
    line = _line(pk)
    if line.state == State.PROPOSED and line.proposed_expense_id:
        _link(request, line, line.proposed_expense)
    elif line.state == State.PROPOSED and line.proposed_document_id:
        _book(request, line, line.proposed_document)
    return _back(request)


@login_required
@require_POST
def book(request, pk):
    line = _line(pk)
    if line.is_outgoing:
        expense_pk = request.POST.get("uitgave", "")
        expense = Expense.objects.filter(pk=expense_pk if expense_pk.isdigit() else None).first()
        if expense is None:
            messages.error(request, _("Kies een uitgave."))
        else:
            _link(request, line, expense)
        return _back(request)
    invoice_pk = request.POST.get("factuur", "")
    invoice = Document.objects.filter(
        pk=invoice_pk if invoice_pk.isdigit() else None, kind="invoice", status="issued"
    ).first()
    if invoice is None:
        messages.error(request, _("Kies een factuur."))
    else:
        _book(request, line, invoice)
    return _back(request)


def _book(request, line, invoice):
    try:
        reading.book(line, invoice)
    except ValueError:
        # Booked meanwhile (another tab, a double click).
        messages.error(request, _("Deze bijschrijving is al geboekt."))
        return
    messages.success(
        request, _("Betaling geboekt op factuur %(number)s.") % {"number": invoice.number}
    )


def _link(request, line, expense):
    try:
        reading.link_expense(line, expense)
    except ValueError:
        # Linked meanwhile (another tab, a double click), or the expense
        # has its bank line already.
        messages.error(request, _("Deze afschrijving of uitgave is al geboekt."))
        return
    messages.success(request, _("Afschrijving geboekt bij de uitgave."))


@login_required
@require_POST
def undo(request, pk):
    line = _line(pk)
    try:
        reading.undo(line)
    except ValueError:
        messages.error(request, _("Deze betaling was al teruggedraaid."))
        return _back(request)
    if line.is_outgoing:
        messages.success(
            request,
            _(
                "Koppeling teruggedraaid. De uitgave blijft staan en de afschrijving "
                "staat weer bij Te doen."
            ),
        )
    else:
        messages.success(request, _("Betaling teruggedraaid. Hij staat weer bij Te doen."))
    return _back(request)


@login_required
@require_POST
def skip(request, pk):
    try:
        reading.skip(_line(pk))
    except ValueError:
        pass  # already skipped or booked: nothing left to skip

    return _back(request)


@login_required
@require_POST
def restore(request, pk):
    try:
        reading.unskip(_line(pk))
    except ValueError:
        pass  # already back: nothing to restore
    return _back(request)
