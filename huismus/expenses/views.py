# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Count, Exists, F, OuterRef, ProtectedError, Q, Subquery, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.core.models import Attachment

from . import batch, inbox, reading
from .forms import (
    ExpenseCategoryForm,
    ExpenseForm,
    ExpenseLineFormSet,
    ExpenseLineFormSetWithEmptyLine,
    NewExpenseReceiptForm,
    ReceiptUploadForm,
)
from .lines import save_lines
from .models import Expense, ExpenseCategory, ExpenseLine
from .receipts import sha256_of

# How many expenses the list shows at first, and how many more each "Meer
# laden" adds.
LIST_PAGE_SIZE = 50


def _int_param(request, name, default=None):
    try:
        return int(request.GET[name])
    except (KeyError, ValueError):
        return default


@login_required
def expense_list(request):
    """Expenses with a year filter (default this year, or "alle"), a
    category filter, search on supplier or description, "Meer laden", and
    the total of everything that matches (not just the rows shown).
    ?nakijken=1 shows only what an AI assistant filled in, of every year."""
    this_year = timezone.localdate().year
    to_check = request.GET.get("nakijken") == "1"
    if request.GET.get("jaar") == "alle" or (to_check and "jaar" not in request.GET):
        year = None
    else:
        year = _int_param(request, "jaar", this_year)
    category_pk = _int_param(request, "categorie")
    query = request.GET.get("q", "").strip()
    shown = max(_int_param(request, "toon", LIST_PAGE_SIZE), LIST_PAGE_SIZE)

    years_with_expenses = {d.year for d in Expense.objects.dates("date", "year")}
    years = sorted(years_with_expenses | {this_year}, reverse=True)

    expenses = Expense.objects.all()
    if to_check:
        expenses = expenses.filter(needs_review=True)
        # What the overview called new to check is seen now.
        reading.seen()
    if year is not None:
        expenses = expenses.filter(date__year=year)
    if category_pk is not None:
        # An expense with a line in this category (huismus-intern/besluiten.md,
        # 2026-11-02). By pk, not a join: a join repeats an expense per
        # matching line, and the sum below would count it twice.
        expenses = expenses.filter(
            pk__in=ExpenseLine.objects.filter(category_id=category_pk).values("expense_id")
        )
    if query:
        in_lines = ExpenseLine.objects.filter(description__icontains=query).values("expense_id")
        expenses = expenses.filter(
            Q(supplier__icontains=query) | Q(description__icontains=query) | Q(pk__in=in_lines)
        )
    total = expenses.count()
    if category_pk is None:
        total_cents = expenses.aggregate(total=Sum("amount_cents"))["total"] or 0
    else:
        # Only the lines in this category, as the year overview counts.
        total_cents = (
            ExpenseLine.objects.filter(category_id=category_pk, expense__in=expenses).aggregate(
                total=Sum("amount_cents")
            )["total"]
            or 0
        )

    rows = (
        expenses.prefetch_related("lines__category")
        .annotate(has_receipt=Exists(Attachment.objects.filter(expense=OuterRef("pk"))))
        .annotate(shown_cents=_shown_cents(category_pk))
        .order_by("-date", "-pk")[:shown]
    )
    params = {
        "q": query,
        "jaar": year or "alle",
        "categorie": category_pk or "",
        "nakijken": "1" if to_check else "",
    }
    more_url = None
    if total > shown:
        more_url = "?" + urlencode(
            {k: v for k, v in {**params, "toon": shown + LIST_PAGE_SIZE}.items() if v}
        )
    return render(
        request,
        "expenses/list.html",
        {
            "expenses": rows,
            "total": total,
            "total_cents": total_cents,
            "more_url": more_url,
            "query": query,
            "year": year,
            "years": years,
            "category_pk": category_pk,
            "categories": ExpenseCategory.objects.all(),
            "has_any": Expense.objects.exists(),
            # "Bonnetjes (3)" once the receipts folder is on or the tray
            # holds something (huismus-intern/besluiten.md, 2026-11-05).
            "tray_count": Attachment.objects.in_tray().count(),
            "receipts_folder_on": inbox.is_on(),
            "to_check": to_check,
            # "Verwerken (24)": the whole stack, whatever the filters
            # (huismus/expenses/batch.py).
            "process_count": batch.count(),
        },
    )


class TrayReceiptGone(Exception):
    """The receipt from the tray no longer waits for an expense: made into
    an expense or removed meanwhile, in another tab."""


def bind_forms(request, instance, *, upload: bool):
    """The expense form, its lines and (for a new expense without a receipt
    from the tray) the upload field, bound to the POST or fresh. Shared by
    the expense page and Verwerken (process_views)."""
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=instance)
        formset = ExpenseLineFormSet(request.POST, instance=instance, prefix="lines")
        receipt_form = NewExpenseReceiptForm(request.POST, request.FILES) if upload else None
    else:
        form = ExpenseForm(instance=instance)
        formset_class = (
            ExpenseLineFormSetWithEmptyLine if request.GET.get("regel") else ExpenseLineFormSet
        )
        formset = formset_class(instance=instance, prefix="lines")
        receipt_form = NewExpenseReceiptForm() if upload else None
    return form, formset, receipt_form


def all_valid(*forms) -> bool:
    """Every form checked, so each shows its own errors."""
    return all([form.is_valid() for form in forms if form is not None])


def save_expense(form, formset, *, receipt_form=None, tray_receipt=None) -> Expense:
    """Saves a valid expense form with its lines, through save_lines(), the
    one place that sets the expense's amount, and with its receipt: an
    uploaded one, or one from the tray. Saving is checking it: "Nakijken"
    goes. TrayReceiptGone, and nothing saved, when the receipt from the
    tray no longer waits."""
    # Not a form field: form.save() saves this same instance.
    form.instance.needs_review = False
    with transaction.atomic():
        saved = form.save()
        save_lines(saved, formset.line_inputs())
        uploaded = receipt_form and receipt_form.cleaned_data["file"]
        if uploaded:
            Attachment.objects.create(
                expense=saved, file=uploaded, kind="receipt", sha256=sha256_of(uploaded)
            )
        if tray_receipt is not None:
            # Out of the tray, onto the expense. Only if it still waits:
            # two tabs never put it on two expenses. If not, the exception
            # undoes the new expense too.
            taken = Attachment.objects.in_tray().filter(pk=tray_receipt.pk)
            if not taken.update(expense=saved):
                raise TrayReceiptGone()
    return saved


def _expense_form(request, expense):
    """The new and edit page: the expense and its lines."""
    # "Uitgave maken" from the tray used to open this page with
    # ?bonnetje=<pk>; it is Verwerken now (huismus/expenses/process_views.py).
    if expense is None and request.GET.get("bonnetje", "").isdigit():
        return redirect(batch.Item(batch.RECEIPT, int(request.GET["bonnetje"])).url())
    # A new expense's amount 0 lasts only until save_lines(), in the same
    # transaction, sets the sum of its lines.
    instance = expense or Expense(amount_cents=0)
    # The stack as it was, before saving takes this one out of it.
    stack = batch.items()
    current = batch.Item(batch.EXPENSE, expense.pk) if expense else None
    # A new expense takes its receipt along in the same form. An existing
    # one has the Bonnetjes section with its own upload (receipt_upload).
    form, formset, new_receipt_form = bind_forms(request, instance, upload=expense is None)
    if request.method == "POST" and all_valid(form, formset, new_receipt_form):
        saved = save_expense(form, formset, receipt_form=new_receipt_form)
        if "klopt" in request.POST and current is not None:
            # "Klopt" in the notice saves the form too, so nothing the user
            # just changed is lost; then on to the next one in Verwerken.
            messages.success(request, _("Uitgave nagekeken."))
            return redirect(_next_in_stack(current, stack))
        messages.success(request, _("Uitgave opgeslagen."))
        url = reverse("expenses:edit", kwargs={"pk": saved.pk})
        # "Regel toevoegen" (form.html) is a submit button named
        # regel_toevoegen. With JS, app.js adds the line on the spot and
        # nothing is sent; without JS it saves, and ?regel=1 brings the page
        # back with an empty line (ExpenseLineFormSetWithEmptyLine).
        if "regel_toevoegen" in request.POST:
            url += "?regel=1"
        return redirect(url)
    context = {
        "form": form,
        "formset": formset,
        "expense": expense,
        "new_receipt_form": new_receipt_form,
        # A browser doesn't keep a chosen file when the page comes back
        # with an error, so a valid receipt has to be chosen again.
        "choose_receipt_again": bool(
            new_receipt_form
            and new_receipt_form.is_bound
            and not new_receipt_form.errors
            and request.FILES.get("receipt-file")
        ),
    }
    if expense:
        context["receipt_form"] = ReceiptUploadForm()
        # "Huismus las dit bonnetje met Mistral." (SPEC.md M20, part 3): the
        # service it was read with then, not the one in the settings now.
        context["read_by"] = reading.read_by(expense)
    # "Hierna nog 2." and "Overslaan": the next in Verwerken, without saving.
    if expense and expense.needs_review:
        skip_to = batch.next_item(current, stack)
        context["skip_to"] = skip_to.url() if skip_to else None
        context["left_after"] = len(stack) - 1
    return render(request, "expenses/form.html", context)


def _next_in_stack(current, stack, done: int = 1) -> str:
    """Where "Klopt" goes: the next one in Verwerken, or after the last one
    Verwerken's "Niets meer te verwerken."."""
    following = batch.next_item(current, stack)
    return following.url(done) if following else reverse("expenses:process")


def _shown_cents(category_pk):
    """The amount a row of the list shows: the whole expense, or with a
    category filter only its lines in that category, so the rows add up to
    the total below them (huismus-intern/besluiten.md, 2026-11-02)."""
    if category_pk is None:
        return F("amount_cents")
    in_category = (
        ExpenseLine.objects.filter(expense=OuterRef("pk"), category_id=category_pk)
        .values("expense")
        .annotate(total=Sum("amount_cents"))
        .values("total")
    )
    return Subquery(in_category)


@login_required
def expense_create(request):
    return _expense_form(request, None)


@login_required
def expense_edit(request, pk):
    return _expense_form(request, get_object_or_404(Expense, pk=pk))


@login_required
def expense_delete(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == "POST":
        # Attachment.expense is on_delete=CASCADE, so the row disappears
        # on its own — but nothing removes the file it points at unless
        # we do it here first, same as receipt_delete() already has to.
        for attachment in expense.attachments.all():
            attachment.file.delete(save=False)
        expense.delete()
        messages.success(request, _("Uitgave verwijderd."))
    return redirect("expenses:list")


@login_required
def receipt_upload(request, pk):
    expense = get_object_or_404(Expense, pk=pk)
    if request.method == "POST":
        form = ReceiptUploadForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded = form.cleaned_data["file"]
            Attachment.objects.create(
                expense=expense, file=uploaded, kind="receipt", sha256=sha256_of(uploaded)
            )
            messages.success(request, _("Bonnetje toegevoegd."))
        else:
            # The form's own reason: "Dit bonnetje is groter dan 10 MB. …"
            messages.error(request, form.errors["file"][0])
    if request.POST.get("verwerken") and expense.needs_review:
        # From Verwerken ("Geen bonnetje bij deze uitgave."): back there.
        done = _int_param_post(request, "klaar")
        return redirect(batch.Item(batch.EXPENSE, expense.pk).url(done))
    return redirect("expenses:edit", pk=expense.pk)


def _int_param_post(request, name) -> int:
    try:
        return max(int(request.POST.get(name, 0)), 0)
    except ValueError:
        return 0


@login_required
def receipt_delete(request, pk, attachment_pk):
    expense = get_object_or_404(Expense, pk=pk)
    attachment = get_object_or_404(Attachment, pk=attachment_pk, expense=expense)
    if request.method == "POST":
        # Storage delete first: if it fails, the row (and the file) stay
        # around to try again, rather than losing track of an orphaned
        # file with no Attachment row left pointing at it.
        attachment.file.delete(save=False)
        attachment.delete()
        messages.success(request, _("Bonnetje verwijderd."))
    return redirect("expenses:edit", pk=expense.pk)


def _render_categories(request, *, new_form=None, editing=None, edit_form=None):
    """The categories page. `editing` is the category shown as an inline form
    (from ?bewerk=<pk>, or after a failed save with its errors)."""
    categories = ExpenseCategory.objects.annotate(
        expense_count=Count("lines__expense", distinct=True)
    )
    if editing is not None and edit_form is None:
        edit_form = ExpenseCategoryForm(instance=editing)
    return render(
        request,
        "expenses/category_list.html",
        {
            "categories": categories,
            "form": new_form or ExpenseCategoryForm(),
            "editing_pk": editing.pk if editing else None,
            "edit_form": edit_form,
        },
    )


@login_required
def category_list(request):
    if request.method == "POST":
        form = ExpenseCategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, _("Categorie aangemaakt."))
            return redirect("expenses:category_list")
        return _render_categories(request, new_form=form)
    editing = None
    if "bewerk" in request.GET:
        editing = ExpenseCategory.objects.filter(pk=_int_param(request, "bewerk")).first()
    return _render_categories(request, editing=editing)


@login_required
def category_edit(request, pk):
    """Saves the inline edit row. A GET (an old link, or no JS) opens the
    list with this category's row in edit mode."""
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method != "POST":
        return redirect(reverse("expenses:category_list") + f"?bewerk={category.pk}")
    form = ExpenseCategoryForm(request.POST, instance=category)
    if form.is_valid():
        form.save()
        messages.success(request, _("Categorie opgeslagen."))
        return redirect("expenses:category_list")
    return _render_categories(request, editing=category, edit_form=form)


@login_required
def category_delete(request, pk):
    category = get_object_or_404(ExpenseCategory, pk=pk)
    if request.method == "POST":
        try:
            category.delete()
            messages.success(request, _("Categorie verwijderd."))
        except ProtectedError:
            messages.error(
                request,
                _(
                    "Er horen nog uitgaven bij deze categorie. Geef ze eerst een "
                    "andere categorie, dan kun je hem verwijderen."
                ),
            )
    return redirect("expenses:category_list")
