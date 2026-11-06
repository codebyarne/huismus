# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The stack of Verwerken (huismus/expenses/batch.py; huismus-intern/besluiten.md,
2026-11-06): first the expenses to check, newest first, then the receipts
without an expense, newest first; after the last one, the top one left.
The screen itself: tests/expenses/test_process.py."""

import datetime
import hashlib

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.core.models import Attachment
from huismus.expenses import batch, inbox
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


@pytest.fixture(autouse=True)
def kor_on(settings, tmp_path):
    from huismus.business.models import Settings

    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    business = Settings.load()
    business.kor_enabled = True
    business.save()


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _to_check(supplier, day, needs_review=True):
    expense = create_expense(
        [ExpenseLineInput(description="", amount_cents=1210, vat_info_cents=None, category=None)],
        date=datetime.date(2026, 11, day),
        supplier=supplier,
        needs_review=needs_review,
    )
    return expense


def _form(expense, **extra):
    line = expense.lines.get()
    return {
        "date": expense.date.isoformat(),
        "supplier": expense.supplier,
        "description": expense.description,
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": line.description,
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": "",
        "lines-0-category": "",
        **extra,
    }


def _in_tray(name):
    content = PDF + name.encode()
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
    )


# --- The order ---------------------------------------------------------


def _e(expense):
    return batch.Item(batch.EXPENSE, expense.pk)


def _r(receipt):
    return batch.Item(batch.RECEIPT, receipt.pk)


def test_first_the_expenses_to_check_then_the_receipts_each_newest_first():
    older_receipt = _in_tray("oud.pdf")
    newer_receipt = _in_tray("nieuw.pdf")
    oldest = _to_check("Oud", 3)
    newest = _to_check("Nieuw", 5)
    _to_check("Al nagekeken", 4, needs_review=False)

    assert batch.items() == [_e(newest), _e(oldest), _r(newer_receipt), _r(older_receipt)]
    assert batch.count() == 4


def test_on_the_same_day_the_newer_one_comes_first():
    first = _to_check("Eerst", 5)
    second = _to_check("Tweede", 5)
    assert batch.items() == [_e(second), _e(first)]


def test_next_follows_the_order_and_comes_round_again():
    newest = _to_check("Nieuw", 5)
    oldest = _to_check("Oud", 3)
    receipt = _in_tray("bon.pdf")
    stack = batch.items()

    assert batch.next_item(_e(newest), stack) == _e(oldest)
    assert batch.next_item(_e(oldest), stack) == _r(receipt)
    # After the last one: the top one that is left.
    assert batch.next_item(_r(receipt), stack) == _e(newest)


def test_next_goes_by_where_it_was_also_when_saving_took_it_out():
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)
    third = _to_check("Hornbach", 3)
    stack = batch.items()
    # Checked, with a new date that would put it at the top.
    Expense.objects.filter(pk=second.pk).update(needs_review=False, date=datetime.date(2026, 11, 9))

    assert batch.next_item(_e(second), stack) == _e(third)
    assert first.pk != third.pk


def test_next_skips_what_left_the_stack_meanwhile_and_takes_what_came_in():
    first = _to_check("Gamma", 5)
    gone = _to_check("Praxis", 4)
    stack = batch.items()
    Expense.objects.filter(pk=gone.pk).update(needs_review=False)
    Expense.objects.filter(pk=first.pk).update(needs_review=False)
    assert batch.next_item(_e(first), stack) is None
    arrived = _in_tray("nieuw.pdf")
    assert batch.next_item(_e(first), stack) == _r(arrived)


def test_nothing_next_when_it_is_the_only_one():
    only = _to_check("Enige", 5)
    assert batch.next_item(_e(only), batch.items()) is None


def test_the_position_counts_the_ones_done_in_this_round():
    a, b, c = _to_check("A", 5), _to_check("B", 4), _to_check("C", 3)
    stack = batch.items()
    assert batch.position(_e(a), stack, 0) == (1, 3)
    assert batch.position(_e(b), stack, 0) == (2, 3)  # after Overslaan
    # After Klopt on A, of 3: A is no longer in the stack, one is done.
    Expense.objects.filter(pk=a.pk).update(needs_review=False)
    stack = batch.items()
    assert batch.position(_e(b), stack, 1) == (2, 3)
    assert batch.position(_e(c), stack, 1) == (3, 3)


# --- The expense page's own notice ----------------------------------------


def test_klopt_on_the_expense_page_goes_on_in_verwerken(logged_in):
    first = _to_check("Gamma", 5)
    receipt = _in_tray("bon.pdf")

    response = logged_in.post(reverse("expenses:edit", args=[first.pk]), _form(first, klopt="1"))

    assert (
        response.url == reverse("expenses:process_item", args=["bonnetje", receipt.pk]) + "?klaar=1"
    )
    first.refresh_from_db()
    assert not first.needs_review


def test_the_notice_counts_the_whole_stack_and_skips_in_verwerken(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)
    _in_tray("bon.pdf")

    page = logged_in.get(reverse("expenses:edit", args=[first.pk])).content.decode()

    assert "Hierna nog 2." in page
    skip = f'href="{reverse("expenses:process_item", args=["uitgave", second.pk])}"'
    assert skip in page and ">Overslaan<" in page
    first.refresh_from_db()
    assert first.needs_review


def test_the_last_one_has_no_count_and_no_skip(logged_in):
    only = _to_check("Gamma", 5)
    page = logged_in.get(reverse("expenses:edit", args=[only.pk])).content.decode()
    assert "Klopt alles?" in page
    assert "Hierna nog" not in page and "Overslaan" not in page


def test_in_english(logged_in):
    first = _to_check("Gamma", 5)
    _to_check("Praxis", 4)
    _to_check("Hornbach", 3)
    logged_in.cookies["django_language"] = "en"
    page = logged_in.get(reverse("expenses:edit", args=[first.pk])).content.decode()
    assert "2 more after this one." in page and ">Skip<" in page


def test_a_new_expense_without_a_receipt_is_unchanged(logged_in):
    _in_tray("nieuw.pdf")
    page = logged_in.get(reverse("expenses:create")).content.decode()
    assert "Hierna nog" not in page and 'name="receipt-file"' in page
