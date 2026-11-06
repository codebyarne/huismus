# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""An expense that a model filled in, marked "Nakijken" (SPEC.md M20, parts
2b and 3): from the AI assistant (assistants.tools.add_expense), and,
in part 3's second step, from the user's own AI service reading a receipt.

Both go through the expense page's own forms, so the amounts get the same
validation as typed ones (the notation, VAT required without the KOR), and
through save_lines() for the totals (invariant 7: gross amounts).
"""

from dataclasses import dataclass

from django.db import transaction
from django.utils.translation import gettext_lazy

from huismus.core import form_messages
from huismus.core.models import Attachment

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
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "1",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, line in enumerate(lines):
        data[f"lines-{index}-description"] = line.description
        data[f"lines-{index}-amount_cents"] = line.amount
        data[f"lines-{index}-vat_info_cents"] = "" if line.vat_info is None else line.vat_info
        data[f"lines-{index}-category"] = str(line.category.pk) if line.category else ""
    # The amount 0 lasts only until save_lines() sets the sum of the lines.
    # needs_review: "Nakijken" in Huismus until the user says it's right.
    expense = Expense(amount_cents=0, needs_review=True, source=source)
    form = ExpenseForm(data, instance=expense)
    formset = ExpenseLineFormSet(data, instance=expense, prefix="lines")
    if not (form.is_valid() and formset.is_valid()):
        # The formset's own error: "at least one line with an amount".
        raise NotAdded(
            form_messages.as_text(form, *formset.forms) or " ".join(formset.non_form_errors())
        )
    with transaction.atomic():
        saved = form.save()
        save_lines(saved, formset.line_inputs())
        if receipt is not None:
            # Out of the tray, onto the expense, as "Uitgave maken" does.
            if not Attachment.objects.in_tray().filter(pk=receipt.pk).update(expense=saved):
                raise NotAdded(str(RECEIPT_GONE))
    return saved
