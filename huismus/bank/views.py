# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Facturen → Bankafschrift inlezen (#77; texts and choices by the
product-owner agent 2026-11-20, huismus-intern/besluiten.md).

One page: the drop zone, the summary of the statement just read, what
Huismus booked from it, and every line that still waits (from any
statement). Every action is a plain POST that comes back to the page.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from django.views.decorators.http import require_POST

from huismus.documents.models import Document

from . import reading
from .lines import StatementLine, StatementReadError
from .matching import match
from .models import BankStatement, BankTransaction

State = BankTransaction.State

MAX_UPLOAD_BYTES = 50 * 1024 * 1024

NOT_A_STATEMENT = _(
    "Huismus herkent dit bestand niet als bankafschrift. "
    "Download het bij je bank als CAMT.053 of MT940."
)


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


def _waiting(open_invoices):
    """The lines that wait for the user, each with what the page needs."""
    by_pk = {invoice.pk: invoice for invoice in open_invoices}
    proposed, to_choose = [], []
    lines = BankTransaction.objects.waiting().select_related("proposed_document")
    for line in lines:
        found = match(_as_line(line), open_invoices)
        first = [by_pk[line.proposed_document_id]] if line.proposed_document_id in by_pk else []
        if found.invoice:
            first.append(found.invoice)
        ordered = []
        for invoice in first + list(found.candidates) + open_invoices:
            if invoice not in ordered:
                ordered.append(invoice)
        line.choices = ordered
        line.several_numbers = found.several_numbers
        proposal = by_pk.get(line.proposed_document_id)
        if line.state == State.PROPOSED and proposal is not None:
            line.proposal = proposal
            line.difference_cents = line.amount_cents - proposal.outstanding_cents
            line.short_cents = -line.difference_cents
            proposed.append(line)
        else:
            # A proposal whose invoice was paid meanwhile is a line to choose for.
            to_choose.append(line)
    return proposed, to_choose


@login_required
def statement_page(request):
    error = None
    if request.method == "POST":
        upload = request.FILES.get("bestand")
        if upload is None or upload.size > MAX_UPLOAD_BYTES:
            error = NOT_A_STATEMENT
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

    statement = None
    requested = request.GET.get("afschrift", "")
    if requested.isdigit():
        statement = BankStatement.objects.filter(pk=requested).first()
    if statement is None:
        statement = BankStatement.objects.first()

    open_invoices = reading.open_invoices()
    proposed, to_choose = _waiting(open_invoices)
    booked = already = []
    if statement is not None:
        lines = statement.transactions.select_related("payment__document", "proposed_document")
        booked = [t for t in lines if t.state in (State.BOOKED, State.CONFIRMED)]
        already = [t for t in lines if t.state == State.ALREADY_BOOKED]
    return render(
        request,
        "bank/statement.html",
        {
            "nav_section": "documents",
            "error": error,
            "statement": statement,
            "summary": summary_text(statement.summary) if statement and requested else "",
            "booked": booked,
            "already": already,
            "proposed": proposed,
            "to_choose": to_choose,
            "skipped_count": BankTransaction.objects.filter(state=State.SKIPPED).count(),
            "here": request.get_full_path(),
        },
        status=400 if error else 200,
    )


@login_required
def skipped_page(request):
    return render(
        request,
        "bank/skipped.html",
        {
            "nav_section": "documents",
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
        return _back(request)
    messages.success(request, _("Betaling teruggedraaid. Hij staat weer bij Zelf kiezen."))
    return _back(request)


@login_required
@require_POST
def skip(request, pk):
    try:
        reading.skip(_line(pk))
    except ValueError:
        pass
    return _back(request)


@login_required
@require_POST
def skip_all(request):
    _proposed, to_choose = _waiting(reading.open_invoices())
    for line in to_choose:
        reading.skip(line)
    return _back(request)


@login_required
@require_POST
def restore(request, pk):
    try:
        reading.unskip(_line(pk))
    except ValueError:
        pass
    return _back(request)
