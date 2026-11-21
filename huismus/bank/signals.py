# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A deleted expense makes its bank line wait again (product-owner agent
2026-11-21, "afschrijvingen in richting D" point 6): the statement stays
the source, and the line goes back to Te doen or Niet herkend. The
expense's page asks nothing extra for it."""

from django.db.models.signals import pre_delete
from django.dispatch import receiver

from huismus.expenses.models import Expense

from .models import BankTransaction


@receiver(pre_delete, sender=Expense)
def line_waits_again(sender, instance, **kwargs):
    BankTransaction.objects.filter(expense=instance).update(
        expense=None, state=BankTransaction.State.OPEN
    )
