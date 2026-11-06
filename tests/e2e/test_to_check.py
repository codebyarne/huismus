# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Nakijken" in a real browser (SPEC.md M20 part 2b): what an AI assistant
filled in is marked on Uitgaven; "Klopt" in the notice saves the form,
with what the user just changed, and goes on to the next one."""

import datetime

import pytest
from playwright.sync_api import expect

from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)


def _from_the_assistant(supplier, cents):
    return create_expense(
        [ExpenseLineInput("", cents, 0, None)],
        date=datetime.date.today(),
        supplier=supplier,
        needs_review=True,
    )


def test_check_two_expenses_from_the_assistant(app):
    first = _from_the_assistant("Bouwmarkt", 4235)
    _from_the_assistant("NS", 1890)

    app.goto(app.base + "/uitgaven/")
    expect(app.locator(".pill-check")).to_have_count(2)
    app.locator("#naar-nakijken").click()
    expect(app.locator("#filter-nakijken")).to_contain_text("Alleen uitgaven om na te kijken.")

    app.get_by_role("link", name="Bouwmarkt", exact=True).click()
    expect(app.locator("#nakijken")).to_contain_text("Klopt alles?")
    app.get_by_label("Leverancier").fill("Bouwmarkt Noord")
    app.get_by_role("button", name="Klopt").click()

    expect(app.locator("#toasts")).to_contain_text("Uitgave nagekeken.")
    expect(app.locator("#filter-nakijken")).to_be_visible()
    expect(app.locator("#naar-nakijken")).to_have_text("Nakijken (1)")
    first.refresh_from_db()
    assert (first.supplier, first.needs_review) == ("Bouwmarkt Noord", False)

    app.get_by_role("link", name="NS", exact=True).click()
    app.get_by_role("button", name="Klopt").click()
    expect(app.locator("#toasts")).to_contain_text("Uitgave nagekeken.")
    expect(app.locator("h1")).to_have_text("Uitgaven")
    expect(app.locator("#naar-nakijken")).to_have_count(0)
    assert not Expense.objects.filter(needs_review=True).exists()


def test_enter_in_a_field_is_not_klopt(app):
    """The notice's button comes before the form; Enter still does what it
    did on every expense (a line is added), and the mark stays."""
    expense = _from_the_assistant("Bouwmarkt", 4235)

    app.goto(app.base + f"/uitgaven/{expense.pk}/")
    app.get_by_label("Leverancier").press("Enter")

    expect(app.locator("[name='lines-1-amount_cents']")).to_be_visible()
    expect(app.locator("#nakijken")).to_be_visible()
    expense.refresh_from_db()
    assert expense.needs_review
