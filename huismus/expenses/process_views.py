# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verwerken (`/uitgaven/verwerken/`; huismus-intern/besluiten.md, 2026-11-06,
"Verwerken: één stapel, het bonnetje groot naast de velden"): the stack of
huismus/expenses/batch.py one at a time, the receipt large beside the
expense's fields and "3 van 24" at the top.

An expense to check has its own fields and "Klopt"; a receipt from the tray
the empty fields of a new expense and "Opslaan", which puts the receipt on
it. Both save through the expense page's own forms (views.save_expense) and
go on to the next one; "Overslaan" goes there without saving. Every form is
a plain POST: `klaar`, the number done in this round, is a hidden field."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from huismus.core.models import Attachment

from . import batch, reading
from .forms import ExpenseLineFormSet, ReceiptUploadForm
from .models import Expense
from .views import TrayReceiptGone, all_valid, bind_forms, save_expense


def _done(request) -> int:
    """`klaar` from the link or the form: how many were done in this round."""
    value = request.POST.get("klaar") if request.method == "POST" else request.GET.get("klaar")
    try:
        return max(int(value or 0), 0)
    except ValueError:
        return 0


def _start(done: int = 0) -> str:
    url = reverse("expenses:process")
    return f"{url}?klaar={done}" if done else url


@login_required
def process(request):
    """The top of the stack, or "Niets meer te verwerken." when it is empty."""
    stack = batch.items()
    if stack:
        return redirect(stack[0].url(_done(request)))
    # Opening Verwerken makes the overview's "nieuwe uitgaven" seen.
    reading.seen()
    return render(request, "expenses/process.html", {"empty": True})


def _one_more_line(request, instance):
    """ "Regel toevoegen" without JS: the same page with what was typed and
    one empty line more, saving nothing (app.js adds it on the spot)."""
    data = request.POST.copy()
    data["lines-TOTAL_FORMS"] = str(int(data.get("lines-TOTAL_FORMS") or 0) + 1)
    return ExpenseLineFormSet(data, instance=instance, prefix="lines")


@login_required
def process_item(request, kind, pk):
    if kind not in (batch.EXPENSE, batch.RECEIPT):
        raise Http404
    reading.seen()
    done = _done(request)
    stack = batch.items()
    current = batch.Item(kind, pk)
    receipt_state = {}
    if kind == batch.EXPENSE:
        expense = Expense.objects.filter(pk=pk, needs_review=True).first()
        if expense is None:
            # Checked meanwhile, in another tab or on its own page.
            return redirect(_start(done))
        instance, tray_receipt = expense, None
        receipt = expense.attachments.filter(kind="receipt").order_by("pk").first()
    else:
        expense = None
        tray_receipt = Attachment.objects.in_tray().filter(pk=pk).first()
        if tray_receipt is None:
            messages.error(
                request, _("Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave.")
            )
            return redirect(_start(done))
        # A new expense's amount 0 lasts only until save_lines() sets it.
        instance, receipt = Expense(amount_cents=0), tray_receipt
        # The tray's own line: "Niet gelezen: …" or "Huismus leest dit bonnetje…".
        receipt_state = {
            "waiting": tray_receipt.read_at is None and reading.active(),
            "reason": reading.reason_sentence(tray_receipt),
        }

    form, formset, _upload = bind_forms(request, instance, upload=False)
    if request.method == "POST":
        if "regel_toevoegen" in request.POST:
            formset = _one_more_line(request, instance)
        elif all_valid(form, formset):
            try:
                save_expense(form, formset, tray_receipt=tray_receipt)
            except TrayReceiptGone:
                messages.error(
                    request, _("Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave.")
                )
                return redirect(_start(done))
            messages.success(
                request, _("Uitgave nagekeken.") if expense else _("Uitgave opgeslagen.")
            )
            following = batch.next_item(current, stack)
            # After the last one: "Niets meer te verwerken.".
            return redirect(following.url(done + 1) if following else reverse("expenses:process"))
        # An error: the same item, the same count, with the errors.

    position, total = batch.position(current, stack, done)
    skip_to = batch.next_item(current, stack)
    return render(
        request,
        "expenses/process.html",
        {
            "kind": kind,
            "expense": expense,
            "tray_receipt": tray_receipt,
            "receipt": receipt,
            **receipt_state,
            "form": form,
            "formset": formset,
            "done": done,
            "position": position,
            "total": total,
            # Overslaan: the next one, nothing saved, `klaar` the same.
            "skip_to": skip_to.url(done) if skip_to else None,
            "read_by": reading.read_by(expense) if expense else "",
            # "Geen bonnetje bij deze uitgave.": the expense page's own upload.
            "receipt_form": ReceiptUploadForm() if expense and receipt is None else None,
        },
    )
