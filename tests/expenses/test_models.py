# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db import IntegrityError, models, transaction

from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db


def test_amount_cents_is_an_integer_field_not_float_or_decimal():
    # Invariant 1/7: no float, no Decimal in storage — a gross euro
    # amount is always whole cents.
    field = Expense._meta.get_field("amount_cents")
    assert isinstance(field, models.BigIntegerField)


def test_vat_info_cents_is_optional_and_informational_only():
    # Invariant 7: KOR has no input VAT deduction — this field exists
    # only so a user can record what VAT was shown on a receipt, never
    # subtracted from amount_cents anywhere.
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)
    assert expense.vat_info_cents is None


def test_category_is_protected_from_deletion_when_in_use():
    category = ExpenseCategory.objects.create(name="Software")
    create_expense([ExpenseLineInput("", 1000, None, category)], date="2026-01-15")

    with pytest.raises(IntegrityError):
        with transaction.atomic():
            category.delete()


def test_category_can_be_deleted_when_unused():
    category = ExpenseCategory.objects.create(name="Software")
    category.delete()
    assert ExpenseCategory.objects.count() == 0


def test_multiple_expenses_without_source_are_allowed():
    Expense.objects.create(date="2026-01-15", amount_cents=1000)
    Expense.objects.create(date="2026-01-16", amount_cents=2000)
    assert Expense.objects.count() == 2


def test_duplicate_source_and_external_id_is_rejected():
    Expense.objects.create(date="2026-01-15", amount_cents=1000, source="import", external_id="123")
    with pytest.raises(IntegrityError):
        with transaction.atomic():
            Expense.objects.create(
                date="2026-01-16", amount_cents=2000, source="import", external_id="123"
            )


def test_same_external_id_allowed_for_a_different_source():
    Expense.objects.create(date="2026-01-15", amount_cents=1000, source="import", external_id="123")
    Expense.objects.create(date="2026-01-16", amount_cents=2000, source="other", external_id="123")
    assert Expense.objects.count() == 2


def test_category_ordering_uses_sort_order_then_name():
    ExpenseCategory.objects.create(name="Zebra", sort_order=1)
    ExpenseCategory.objects.create(name="Aap", sort_order=1)
    ExpenseCategory.objects.create(name="Beer", sort_order=0)

    names = list(ExpenseCategory.objects.values_list("name", flat=True))
    assert names == ["Beer", "Aap", "Zebra"]


def test_expense_str_prefers_supplier():
    expense = Expense(date="2026-01-15", amount_cents=1234, supplier="Acme BV")
    assert "Acme BV" in str(expense)


def test_expense_str_falls_back_to_description():
    expense = Expense(date="2026-01-15", amount_cents=1234, description="Kantoorartikelen")
    assert "Kantoorartikelen" in str(expense)
