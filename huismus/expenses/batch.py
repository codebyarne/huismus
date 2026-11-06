# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stack of Verwerken (huismus-intern/besluiten.md, 2026-11-06,
"Verwerken: één stapel, het bonnetje groot naast de velden"): everything
that waits for the user, one after the other.

First the expenses to check (the order of Nakijken: date, newest first),
then the receipts without an expense (the order of the tray: picked up,
newest first). "Next" is the first one after this one in that order, and
after the last one the top one that is left. Without a "previous": you skip
forward and come round again.

Nothing is stored: the stack is what the database holds now. "3 van 24"
counts the ones done in this round from `?klaar=`, a number that only the
links and the form carry (position())."""

from dataclasses import dataclass

from django.urls import reverse

from huismus.core.models import Attachment

from .models import Expense

EXPENSE, RECEIPT = "uitgave", "bonnetje"


@dataclass(frozen=True)
class Item:
    """One thing in the stack: an expense to check or a receipt."""

    kind: str
    pk: int

    def url(self, done: int = 0) -> str:
        url = reverse("expenses:process_item", kwargs={"kind": self.kind, "pk": self.pk})
        return f"{url}?klaar={done}" if done else url


def items() -> list[Item]:
    """The whole stack, in its order."""
    expenses = Expense.objects.filter(needs_review=True).order_by("-date", "-pk")
    receipts = Attachment.objects.in_tray().order_by("-created_at", "-pk")
    return [Item(EXPENSE, pk) for pk in expenses.values_list("pk", flat=True)] + [
        Item(RECEIPT, pk) for pk in receipts.values_list("pk", flat=True)
    ]


def count() -> int:
    """ "Verwerken (24)" on Uitgaven."""
    return Expense.objects.filter(needs_review=True).count() + Attachment.objects.in_tray().count()


def next_item(current: Item, before: list[Item]) -> Item | None:
    """The next one after `current`, by where it was in `before` (the stack
    as it was before this one was saved: saving can take it out, or change
    its date). Of those, the first that is still in the stack now; else the
    top one that is left, so one that came in meanwhile comes along too."""
    now = items()
    if current in before:
        at = before.index(current)
        for item in before[at + 1 :] + before[:at]:
            if item in now:
                return item
    return next((item for item in now if item != current), None)


def position(current: Item, stack: list[Item], done: int) -> tuple[int, int]:
    """ "3 van 24": the ones done in this round, plus where this one is in
    what is left, of the ones done plus what is left."""
    at = stack.index(current) + 1 if current in stack else 1
    total = done + max(len(stack), 1)
    return min(done + at, total), total
