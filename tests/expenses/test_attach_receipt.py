# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A receipt from the tray onto an expense there is (#127; adding.attach_receipt)."""

import pytest
from django.core.files.base import ContentFile

from huismus.core.models import Attachment
from huismus.expenses import adding
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _expense():
    category = ExpenseCategory.objects.create(name="Kantoor")
    expense = Expense.objects.create(date="2026-03-03", supplier="Drukkerij", amount_cents=1250)
    expense.lines.create(category=category, amount_cents=1250)
    return expense


def _receipt():
    return Attachment.objects.create(
        file=ContentFile(b"%PDF-1.4", name="bon.pdf"), kind="receipt", sha256="a" * 64
    )


def test_the_receipt_leaves_the_tray_for_the_expense():
    expense, receipt = _expense(), _receipt()

    adding.attach_receipt(expense, receipt, to_check=False)

    receipt.refresh_from_db()
    assert receipt.expense == expense
    assert not Attachment.objects.in_tray().exists()


def test_the_users_own_choice_leaves_nakijken_as_it_was():
    expense, receipt = _expense(), _receipt()

    adding.attach_receipt(expense, receipt, to_check=False)

    expense.refresh_from_db()
    assert not expense.needs_review


def test_an_assistant_puts_it_on_nakijken():
    expense, receipt = _expense(), _receipt()

    adding.attach_receipt(expense, receipt)

    expense.refresh_from_db()
    assert expense.needs_review


def test_one_receipt_never_goes_onto_two_expenses():
    first, second, receipt = _expense(), _expense(), _receipt()
    adding.attach_receipt(first, receipt, to_check=False)

    with pytest.raises(adding.NotAdded):
        adding.attach_receipt(second, receipt, to_check=False)

    receipt.refresh_from_db()
    assert receipt.expense == first
    assert not second.attachments.exists()


def test_the_amounts_stay_as_they_were():
    expense, receipt = _expense(), _receipt()

    adding.attach_receipt(expense, receipt, to_check=False)

    expense.refresh_from_db()
    assert expense.amount_cents == 1250
    assert [line.amount_cents for line in expense.lines.all()] == [1250]
