# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A receipt from the tray onto an expense there is (#127;
huismus-intern/besluiten.md, 2026-11-22): "Kies bestaande uitgave" in the
tray and "Hoort bij een uitgave die er al is?" in Verwerken open the same
page, "Bij welke uitgave hoort dit bonnetje?".

The receipt large on the left, as in Verwerken; on the right the expense
Huismus found it looks like (`read_similar`), a search field and the
expenses without a receipt. "Kiezen" puts it on that expense and goes back
where the user came from, the tray or the next one in Verwerken
(`terug`), with a notice that links to the expense and offers "Ongedaan
maken". Every form is a plain POST, the search a plain GET."""

from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl, urlencode, urlsplit

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Exists, OuterRef, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import Resolver404, resolve, reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from huismus.core.forms import amount_with_decimal_point
from huismus.core.models import Attachment

from . import adding, batch
from .models import Expense, ExpenseLine

# How many expenses the list shows at first, and how many more each "Meer laden" adds.
PAGE_SIZE = 20

# Where "Kiezen" and "Ongedaan maken" go back to: the only two places.
TRAY, PROCESS = "bakje", "verwerken"

# The query parameter that shows the notice after "Kiezen": the receipt's pk.
ATTACHED = "gekoppeld"

RECEIPT_GONE = gettext_lazy("Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave.")


def _where(request) -> tuple[str, int]:
    """`terug` and `klaar` from the link or the form."""
    data = request.POST if request.method == "POST" else request.GET
    back = PROCESS if data.get("terug") == PROCESS else TRAY
    try:
        done = max(int(data.get("klaar") or 0), 0)
    except ValueError:
        done = 0
    return back, done


def _with(url: str, **params) -> str:
    query = urlencode({key: value for key, value in params.items() if value})
    if not query:
        return url
    return f"{url}{'&' if '?' in url else '?'}{query}"


def _amount_cents(text: str) -> int | None:
    """ "12,50" or "€ 12,50" as cents, for searching on the amount; None
    when the search is no amount."""
    amount = amount_with_decimal_point(text.replace("€", "").strip())
    if amount is None:
        return None
    try:
        return int((Decimal(amount) * 100).to_integral_value())
    except InvalidOperation:
        return None


def _with_receipt_mark():
    return Expense.objects.annotate(
        has_receipt=Exists(Attachment.objects.filter(expense=OuterRef("pk"), kind="receipt"))
    )


def _expenses(query: str, similar: Expense | None):
    """With a search: every expense that matches, as the expense list
    searches, and on the gross total. Without: the ones without a receipt.
    Newest first, without the one shown as "Lijkt op dit bonnetje"."""
    expenses = _with_receipt_mark()
    if query:
        in_lines = ExpenseLine.objects.filter(description__icontains=query).values("expense_id")
        found = Q(supplier__icontains=query) | Q(description__icontains=query) | Q(pk__in=in_lines)
        cents = _amount_cents(query)
        if cents is not None:
            found |= Q(amount_cents=cents)
        expenses = expenses.filter(found)
    else:
        expenses = expenses.filter(has_receipt=False)
    if similar is not None:
        expenses = expenses.exclude(pk=similar.pk)
    return expenses.order_by("-date", "-pk")


def _back_url(back: str, done: int) -> str:
    if back == PROCESS:
        # Verwerken opens at the top of what is left.
        return _with(reverse("expenses:process"), klaar=done)
    return reverse("expenses:tray")


@login_required
def choose(request, pk):
    back, done = _where(request)
    receipt = Attachment.objects.in_tray().select_related("read_similar").filter(pk=pk).first()
    if receipt is None:
        messages.error(request, RECEIPT_GONE)
        return redirect(_back_url(back, done))

    if request.method == "POST":
        expense = get_object_or_404(Expense, pk=request.POST.get("uitgave") or 0)
        current = batch.Item(batch.RECEIPT, receipt.pk)
        # The stack before attaching: afterwards this receipt is out of it,
        # and next_item() needs where it was to find the one after it.
        stack = batch.items()
        try:
            adding.attach_receipt(expense, receipt, to_check=False)
        except adding.NotAdded:
            messages.error(request, RECEIPT_GONE)
            return redirect(_back_url(back, done))
        if back == PROCESS:
            following = batch.next_item(current, stack)
            url = following.url(done + 1) if following else reverse("expenses:process")
        else:
            url = reverse("expenses:tray")
        return redirect(_with(url, **{ATTACHED: receipt.pk}))

    query = request.GET.get("q", "").strip()
    try:
        shown = max(int(request.GET.get("toon") or PAGE_SIZE), PAGE_SIZE)
    except ValueError:
        shown = PAGE_SIZE
    similar = receipt.read_similar
    expenses = _expenses(query, similar)
    total = expenses.count()
    params = {"terug": back if back == PROCESS else "", "klaar": done or "", "q": query}
    more_url = _with("?", **{**params, "toon": shown + PAGE_SIZE}) if total > shown else None
    return render(
        request,
        "expenses/attach.html",
        {
            "receipt": receipt,
            "similar": similar,
            "similar_rows": _with_receipt_mark().filter(pk=similar.pk) if similar else [],
            "expenses": expenses[:shown],
            "query": query,
            "more_url": more_url,
            "back": back,
            "done": done,
            "back_url": _back_url(back, done),
            "has_any": Expense.objects.exists(),
            "make_url": batch.Item(batch.RECEIPT, receipt.pk).url(done),
        },
    )


def _back_after_undo(url: str, receipt: Attachment) -> str:
    """Where "Ongedaan maken" goes: the tray as it was, or in Verwerken
    this receipt again with `klaar` one less (Kiezen counted it as done),
    so "3 van 24" is as before Kiezen. Never below 0."""
    parts = urlsplit(url)
    if resolve(parts.path).view_name == "expenses:tray":
        return parts.path
    try:
        done = max(int(dict(parse_qsl(parts.query)).get("klaar") or 0) - 1, 0)
    except ValueError:
        done = 0
    return batch.Item(batch.RECEIPT, receipt.pk).url(done)


# The pages "Ongedaan maken" may go back to.
PLACES = ("expenses:tray", "expenses:process", "expenses:process_item")


def _tray_or_process(url: str) -> str:
    """Only back to the tray or Verwerken, nowhere else: the page as Huismus
    builds it from the path and query, never the address as it came in, so
    "//elders.example/..." can't lead to another site (#342). The tray when
    `url` is no such page."""
    parts = urlsplit(url)
    try:
        match = resolve(parts.path)
    except Resolver404:
        match = None
    if parts.scheme or parts.netloc or match is None or match.view_name not in PLACES:
        return reverse("expenses:tray")
    return reverse(match.view_name, args=match.args, kwargs=match.kwargs) + (
        f"?{parts.query}" if parts.query else ""
    )


@login_required
def undo(request, pk):
    """ "Ongedaan maken" in the notice after "Kiezen": back into the tray,
    and back to the page the notice was on (`plek`: the tray or Verwerken).
    The receipt and the expense come from the notice's form; detach_receipt
    checks that it still hangs there and came from the tray, so at most a
    receipt goes back where it was, never anything deleted."""
    target = _tray_or_process(request.POST.get("plek", ""))
    if request.method != "POST":
        return redirect(target)
    receipt = get_object_or_404(Attachment, pk=pk)
    expense = get_object_or_404(Expense, pk=request.POST.get("uitgave") or 0)
    if adding.detach_receipt(expense, receipt):
        messages.success(request, _("Het bonnetje staat weer bij de bonnetjes zonder uitgave."))
        target = _back_after_undo(target, receipt)
    else:
        messages.error(request, _("Dit bonnetje hangt niet meer aan die uitgave."))
    return redirect(target)


def attached_notice(request) -> dict:
    """The notice after "Kiezen", on the tray and in Verwerken: the receipt
    of `?gekoppeld=` with its expense, while it still hangs there."""
    pk = request.GET.get(ATTACHED, "")
    if not pk.isdigit():
        return {}
    receipt = (
        Attachment.objects.filter(pk=pk, kind="receipt", expense__isnull=False)
        .select_related("expense")
        .first()
    )
    if receipt is None or not adding.came_from_tray(receipt):
        return {}
    return {"attached": receipt, "attached_expense": receipt.expense}
