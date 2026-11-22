# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An expense that a model filled in or changed, marked "Nakijken" (SPEC.md
M20, parts 2b and 3; M16, #273 part 2): from the AI assistant
(assistants.tools), and, in part 3's second step, from the user's own AI
service reading a receipt.

Both go through the expense page's own forms, so the amounts get the same
validation as typed ones (the notation, VAT required without the KOR), and
through save_lines() for the totals (invariant 7: gross amounts).
"""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import ProtectedError
from django.utils.translation import gettext_lazy

from huismus.core import form_messages
from huismus.core.models import TRAY_FOLDER, Attachment

from .forms import ExpenseForm, ExpenseLineFormSet
from .lines import save_lines
from .models import Expense, ExpenseCategory

# The same words as "Uitgave maken" in the app (expenses.views).
RECEIPT_GONE = gettext_lazy("Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave.")


class NotAdded(Exception):
    """The form refused it, or the receipt no longer waits; the message
    says why."""


@dataclass(frozen=True)
class Line:
    description: str
    amount: str  # gross, in euros as typed: "42,35"
    vat_info: str | None  # None: the receipt shows no VAT
    category: ExpenseCategory | None
    vat_rate: str | None = None  # a VatRate value; None: not given
    # A name typed as on the expense page: an existing category in any
    # case, or else a new one, made when the expense is saved
    # (ExpenseLineForm.category_to_save).
    new_category: str = ""


def _line_data(index: int, line: Line) -> dict:
    return {
        f"lines-{index}-description": line.description,
        f"lines-{index}-amount_cents": line.amount,
        f"lines-{index}-vat_info_cents": "" if line.vat_info is None else line.vat_info,
        f"lines-{index}-category": str(line.category.pk) if line.category else "",
        f"lines-{index}-new_category": line.new_category,
        f"lines-{index}-vat_rate": line.vat_rate or "",
    }


def _management(total: int, initial: int) -> dict:
    return {
        "lines-TOTAL_FORMS": str(total),
        "lines-INITIAL_FORMS": str(initial),
        "lines-MIN_NUM_FORMS": "1",
        "lines-MAX_NUM_FORMS": "1000",
    }


def _bound_forms(expense: Expense, data: dict):
    """The expense page's forms, bound and checked: NotAdded with their
    errors."""
    form = ExpenseForm(data, instance=expense)
    formset = ExpenseLineFormSet(data, instance=expense, prefix="lines")
    if not (form.is_valid() and formset.is_valid()):
        # The formset's own error: "at least one line with an amount".
        raise NotAdded(
            form_messages.as_text(form, *formset.forms) or " ".join(formset.non_form_errors())
        )
    return form, formset


def _take_from_tray(receipt: Attachment, expense: Expense) -> None:
    """Out of the tray, onto the expense, as "Uitgave maken" does: only if
    it still waits, so one receipt never goes onto two expenses. Call it
    inside the transaction that saves the expense."""
    if not Attachment.objects.in_tray().filter(pk=receipt.pk).update(expense=expense):
        raise NotAdded(str(RECEIPT_GONE))


def add_expense(
    *,
    date: str,
    supplier: str,
    description: str,
    lines: list[Line],
    receipt: Attachment | None = None,
    source: str = "",
) -> Expense:
    """Validates and saves like "Opslaan" on the expense page
    (expenses.views._expense_form). With a receipt, it goes onto the new
    expense in the same transaction, only if it still waits; else nothing
    is saved."""
    data = {
        "date": date,
        "supplier": supplier,
        "description": description,
        **_management(len(lines), 0),
    }
    for index, line in enumerate(lines):
        data.update(_line_data(index, line))
    # The amount 0 lasts only until save_lines() sets the sum of the lines.
    # needs_review: "Nakijken" in Huismus until the user says it's right.
    expense = Expense(amount_cents=0, needs_review=True, source=source)
    form, formset = _bound_forms(expense, data)
    with transaction.atomic():
        saved = form.save()
        save_lines(saved, formset.line_inputs())
        if receipt is not None:
            _take_from_tray(receipt, saved)
    return saved


def change_expense(
    expense: Expense,
    *,
    date: str | None = None,
    supplier: str | None = None,
    description: str | None = None,
    lines: list[Line] | None = None,
) -> Expense:
    """Validates and saves like "Opslaan" on the expense page: what is left
    out (None) stays as it is; lines, when given, replace all lines. Unlike
    Opslaan by the user it is "Nakijken" afterwards, also when it had been
    checked: the user says whether the change is right."""
    data = {
        "date": expense.date.isoformat() if date is None else date,
        "supplier": expense.supplier if supplier is None else supplier,
        "description": expense.description if description is None else description,
    }
    expense.needs_review = True
    if lines is None:
        # Only the expense's own fields: its lines and amounts are not
        # posted again, so a stored amount never goes back through a form.
        form = ExpenseForm(data, instance=expense)
        if not form.is_valid():
            raise NotAdded(form_messages.as_text(form))
        return form.save()
    # Every saved line marked for deletion and the new ones after them, as
    # the page posts after the user replaced them all. A form marked DELETE
    # is not validated (Django formsets): its id is all it needs.
    existing = list(expense.lines.all())
    data.update(_management(len(existing) + len(lines), len(existing)))
    for index, saved_line in enumerate(existing):
        data[f"lines-{index}-id"] = str(saved_line.pk)
        data[f"lines-{index}-DELETE"] = "on"
    for index, line in enumerate(lines, start=len(existing)):
        data.update(_line_data(index, line))
    form, formset = _bound_forms(expense, data)
    with transaction.atomic():
        saved = form.save()
        save_lines(saved, formset.line_inputs())
    return saved


def attach_receipt(expense: Expense, receipt: Attachment, *, to_check: bool = True) -> None:
    """A receipt from the tray onto an expense there is. `to_check`: the
    expense goes on "Nakijken" again, when an AI assistant did it (#273);
    the user's own choice in the tray (#127) leaves it as it was."""
    with transaction.atomic():
        _take_from_tray(receipt, expense)
        if to_check:
            Expense.objects.filter(pk=expense.pk).update(needs_review=True)


def came_from_tray(receipt: Attachment) -> bool:
    """A receipt that was in the tray keeps its place there (core.models
    attachment_upload_to); one uploaded on the expense page doesn't."""
    return receipt.kind == "receipt" and receipt.file.name.startswith(TRAY_FOLDER)


def detach_receipt(expense: Expense, receipt: Attachment) -> bool:
    """ "Ongedaan maken" after the tray's "Kiezen" (#127): the receipt back
    into the tray, only while it still hangs on this expense and came from
    the tray. False, and nothing changed, otherwise."""
    if not came_from_tray(receipt):
        return False
    # One update: it only moves the receipt if it still hangs there.
    taken = Attachment.objects.filter(pk=receipt.pk, expense=expense, kind="receipt")
    return bool(taken.update(expense=None))


def delete_expense(expense: Expense) -> None:
    """As Verwijderen on the expense page: its receipts and other
    attachments go with it, files included. A bank line it was linked to
    waits again (bank.signals)."""
    # Attachment.expense is on_delete=CASCADE, so the row disappears on
    # its own, but nothing removes the file it points at unless we do it
    # here first, as receipt_delete() has to as well.
    for attachment in expense.attachments.all():
        attachment.file.delete(save=False)
    expense.delete()


class CategoryInUse(Exception):
    """A category with expenses can't be deleted (ExpenseLine.category is
    PROTECT): the user gives them another category first."""


CATEGORY_IN_USE = gettext_lazy(
    "Er horen nog uitgaven bij deze categorie. Geef ze eerst een andere categorie, "
    "dan kun je hem verwijderen."
)


def delete_category(category: ExpenseCategory) -> None:
    try:
        category.delete()
    except ProtectedError as error:
        raise CategoryInUse(str(CATEGORY_IN_USE)) from error
