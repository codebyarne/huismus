# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank → Bankafschrift inlezen (#77). Its own menu item since the owner's
decision of 2026-11-21 (first a button on Facturen); texts and choices by
the product-owner agent 2026-11-20, huismus-intern/besluiten.md.

One page (direction D, owner 2026-11-21): what the latest statement held,
then three sections that fold: Te doen (lines that fit an invoice),
Geboekt, and Niet herkend (lines that fit nothing, folded: often private
money, nothing to do). Every action is a plain POST that comes back to the
page.
"""

from dataclasses import dataclass

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST

from huismus.documents.models import Document

from . import reading
from .lines import StatementLine, StatementReadError
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


def summary_text(summary: dict) -> str:
    """'12 bijschrijvingen gelezen. 5 geboekt, 2 om te bevestigen. 2 waren
    al ingelezen. Van rekening NL…': only the parts that aren't 0."""
    read = summary.get("read", 0)
    sentences = [
        ngettext("%(count)s bijschrijving gelezen.", "%(count)s bijschrijvingen gelezen.", read)
        % {"count": read}
    ]
    # Literal ngettext calls, so makemessages finds every text.
    texts = {
        "booked": lambda n: ngettext("%(count)s geboekt", "%(count)s geboekt", n),
        "proposed": lambda n: ngettext(
            "%(count)s om te bevestigen", "%(count)s om te bevestigen", n
        ),
        "open": lambda n: ngettext("%(count)s om zelf te kiezen", "%(count)s om zelf te kiezen", n),
        "already_booked": lambda n: ngettext(
            "%(count)s stond al geboekt", "%(count)s stonden al geboekt", n
        ),
    }
    parts = []
    for key, text in texts.items():
        count = summary.get(key, 0)
        if count:
            parts.append(text(count) % {"count": count})
    if parts:
        sentences.append(_capitalize(", ".join(parts)) + ".")
    outgoing = summary.get("outgoing", 0)
    if outgoing:
        sentences.append(
            ngettext(
                "%(count)s afschrijving: die koppel je later aan je uitgaven.",
                "%(count)s afschrijvingen: die koppel je later aan je uitgaven.",
                outgoing,
            )
            % {"count": outgoing}
        )
    seen = summary.get("seen_before", 0)
    if seen:
        sentences.append(
            ngettext("%(count)s was al ingelezen.", "%(count)s waren al ingelezen.", seen)
            % {"count": seen}
        )
    for iban in summary.get("accounts", []):
        sentences.append(_("Van rekening %(iban)s.") % {"iban": _grouped(iban)})
    return " ".join(sentences)


def _capitalize(text: str) -> str:
    return text[:1].upper() + text[1:]


def _grouped(iban: str) -> str:
    return " ".join(iban[i : i + 4] for i in range(0, len(iban), 4))


def _as_line(transaction) -> StatementLine:
    return StatementLine(
        account_iban=transaction.account_iban,
        booked_on=transaction.booked_on,
        amount_cents=transaction.amount_cents,
        counterparty_name=transaction.counterparty_name,
        counterparty_iban=transaction.counterparty_iban,
        description=transaction.description,
        reference=transaction.reference,
    )


@dataclass
class Waiting:
    """A line that waits for the user, with what the page shows of it."""

    line: BankTransaction
    # The open invoices to choose from, the ones that fit first.
    choices: list[OpenInvoice]
    several_numbers: bool = False
    # For Klopt dit?: the proposed invoice, and how much the payment is
    # more (positive) or less (negative) than what is open on it.
    proposal: OpenInvoice | None = None
    difference_cents: int = 0

    @property
    def short_cents(self) -> int:
        return -self.difference_cents


def _waiting(open_invoices) -> tuple[list[Waiting], list[Waiting], list[Waiting]]:
    """The lines that wait: (proposals, lines to choose for, not recognised),
    the first two under Te doen. The proposal is the stored one; matching runs
    again to order the choices and to see whether any invoice fits at all,
    since what is open changed since the statement was read."""
    by_pk = {invoice.pk: invoice for invoice in open_invoices}
    proposed, to_choose, unknown = [], [], []
    for line in BankTransaction.objects.waiting():
        found = match(_as_line(line), open_invoices)
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
            proposed.append(item)
        elif first or found.candidates or found.several_numbers:
            # A proposal whose invoice was paid meanwhile is a line to choose for.
            to_choose.append(item)
        else:
            # Nothing fits: often private money. It waits without asking.
            unknown.append(item)
    return proposed, to_choose, unknown


def to_do_count() -> int:
    """The lines under Te doen, for the overview (core.todo): a line that
    fits nothing doesn't ask for anything."""
    proposed, to_choose, _unknown = _waiting(reading.open_invoices())
    return len(proposed) + len(to_choose)


@dataclass
class Report:
    """The tiles at the top: what the statement held."""

    total: int  # every line in the file
    fitting: int  # lines that fit an invoice: booked, already there, or waiting
    incoming_cents: int
    incoming: int
    outgoing: int
    first_day: object
    last_day: object

    @property
    def fitting_percent(self) -> int:
        return round(100 * self.fitting / self.total) if self.total else 0


def _report(statement, waiting_pks) -> Report | None:
    if statement is None:
        return None
    lines = list(statement.transactions.all())
    summary = statement.summary
    outgoing = summary.get("outgoing", 0)
    fitting = sum(
        1
        for t in lines
        if t.state in (State.BOOKED, State.CONFIRMED, State.ALREADY_BOOKED) or t.pk in waiting_pks
    )
    days = [t.booked_on for t in lines]
    return Report(
        total=len(lines) + outgoing,
        fitting=fitting,
        incoming_cents=sum(t.amount_cents for t in lines),
        incoming=len(lines),
        outgoing=outgoing,
        first_day=min(days) if days else None,
        last_day=max(days) if days else None,
    )


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
            except StatementReadError:
                error = NOT_A_STATEMENT
            else:
                if result.statement is None:
                    messages.info(
                        request,
                        _("Niets nieuws: alle bijschrijvingen in dit bestand waren al ingelezen."),
                    )
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

    open_invoices = reading.open_invoices()
    proposed, to_choose, unknown = _waiting(open_invoices)
    booked = []
    if statement is not None:
        lines = statement.transactions.select_related("payment__document", "proposed_document")
        booked = [
            t for t in lines if t.state in (State.BOOKED, State.CONFIRMED, State.ALREADY_BOOKED)
        ]
    to_do = proposed + to_choose
    return render(
        request,
        "bank/statement.html",
        {
            "nav_section": "bank",
            "error": error,
            "statement": statement,
            "summary": summary_text(statement.summary) if statement and requested else "",
            "report": _report(statement, {item.line.pk for item in to_do}),
            "booked": booked,
            "to_do": to_do,
            "unknown": unknown,
            "skipped_count": BankTransaction.objects.filter(state=State.SKIPPED).count(),
            "here": request.get_full_path(),
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
    if line.state == State.PROPOSED and line.proposed_document_id:
        _book(request, line, line.proposed_document)
    return _back(request)


@login_required
@require_POST
def book(request, pk):
    line = _line(pk)
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


@login_required
@require_POST
def undo(request, pk):
    try:
        reading.undo(_line(pk))
    except ValueError:
        messages.error(request, _("Deze betaling was al teruggedraaid."))
        return _back(request)
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
