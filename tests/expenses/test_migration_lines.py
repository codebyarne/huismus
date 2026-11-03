# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every existing expense gets one line with its amount, VAT and category
(huismus-intern/besluiten.md, 2026-11-02: approved by the owner, escalation
point 3). Totals per year and per category stay the same."""

from datetime import date

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

BEFORE = [("expenses", "0001_initial")]
AFTER = [("expenses", "0002_expense_lines")]


def test_each_expense_becomes_one_line_with_its_amount_vat_and_category():
    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)
    old = executor.loader.project_state(BEFORE).apps
    Category = old.get_model("expenses", "ExpenseCategory")
    Expense = old.get_model("expenses", "Expense")
    software = Category.objects.create(name="Software")
    with_category = Expense.objects.create(
        date=date(2025, 4, 1),
        supplier="Hoster",
        description="Hosting april",
        category=software,
        amount_cents=1210,
        vat_info_cents=210,
    )
    without = Expense.objects.create(date=date(2026, 1, 2), amount_cents=500)

    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)

    new = executor.loader.project_state(AFTER).apps
    Line = new.get_model("expenses", "ExpenseLine")
    first = Line.objects.get(expense_id=with_category.pk)
    assert (first.position, first.description, first.amount_cents, first.vat_info_cents) == (
        0,
        "",
        1210,
        210,
    )
    assert first.category.name == "Software"
    second = Line.objects.get(expense_id=without.pk)
    assert (second.amount_cents, second.vat_info_cents, second.category_id) == (500, None, None)
    kept = new.get_model("expenses", "Expense").objects.get(pk=with_category.pk)
    assert (kept.amount_cents, kept.description, kept.supplier) == (1210, "Hosting april", "Hoster")


def test_the_migration_can_be_reversed_without_losing_a_category():
    executor = MigrationExecutor(connection)
    executor.migrate(AFTER)
    new = executor.loader.project_state(AFTER).apps
    software = new.get_model("expenses", "ExpenseCategory").objects.create(name="Software")
    expense = new.get_model("expenses", "Expense").objects.create(
        date=date(2025, 4, 1), amount_cents=1210
    )
    new.get_model("expenses", "ExpenseLine").objects.create(
        expense=expense, position=0, amount_cents=1210, category=software
    )

    executor = MigrationExecutor(connection)
    executor.migrate(BEFORE)

    old = executor.loader.project_state(BEFORE).apps
    assert old.get_model("expenses", "Expense").objects.get().category.name == "Software"
    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
