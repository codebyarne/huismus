# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stack, one after the other (huismus-intern/besluiten.md, 2026-11-06,
"Stapel nakijken of verwerken"): the next expense to check, and the next
receipt without an expense.

"Next" is in the order of the list the stack comes from, newest first:
the first one after this one, and after the last one of that order the
top one that is left. Without a "previous": you skip forward and come
round again."""

from django.db.models import Q, QuerySet

from huismus.core.models import Attachment

from .models import Expense


def _next(others: QuerySet, after: Q, order: tuple[str, ...]):
    """The first of `others` after this one in `order`, else the first."""
    others = others.order_by(*order)
    return others.filter(after).first() or others.first()


def _to_check_except(expense: Expense) -> QuerySet:
    return Expense.objects.filter(needs_review=True).exclude(pk=expense.pk)


def next_to_check(expense: Expense, date=None) -> Expense | None:
    """The next expense to check after this one, in the order of Nakijken
    (date, newest first). `date` is where this one was in that order, when
    the user just changed its date."""
    date = date or expense.date
    after = Q(date__lt=date) | Q(date=date, pk__lt=expense.pk)
    return _next(_to_check_except(expense), after, ("-date", "-pk"))


def to_check_after(expense: Expense) -> int:
    """How many more to check besides this one: "Hierna nog 2."."""
    return _to_check_except(expense).count()


def _tray_except(receipt: Attachment) -> QuerySet:
    return Attachment.objects.in_tray().exclude(pk=receipt.pk)


def next_receipt(receipt: Attachment) -> Attachment | None:
    """The next receipt without an expense after this one, in the order of
    the tray (picked up, newest first)."""
    after = Q(created_at__lt=receipt.created_at) | Q(
        created_at=receipt.created_at, pk__lt=receipt.pk
    )
    return _next(_tray_except(receipt), after, ("-created_at", "-pk"))


def receipts_after(receipt: Attachment) -> int:
    """How many more receipts wait besides this one."""
    return _tray_except(receipt).count()
