# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Nakijken" in a real browser (SPEC.md M20 part 2b): what an AI assistant
filled in is marked on Uitgaven; "Klopt" in the notice saves the form,
with what the user just changed, and goes on to the next one to check."""

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


def test_check_three_expenses_from_the_assistant_one_after_the_other(app):
    """ "Klopt" goes on to the next one, "Overslaan" skips one without
    saving, and after the last one you're back on the list
    (huismus-intern/besluiten.md, 2026-11-06, huismus/expenses/batch.py)."""
    _from_the_assistant("Bouwmarkt", 4235)
    skipped = _from_the_assistant("NS", 1890)
    last = _from_the_assistant("Kantoorwinkel", 2599)
    # Newest first, as on the list: Kantoorwinkel, NS, Bouwmarkt.

    app.goto(app.base + "/uitgaven/")
    expect(app.locator(".pill-check")).to_have_count(3)
    app.locator("#naar-nakijken").click()
    expect(app.locator("#filter-nakijken")).to_contain_text("Alleen uitgaven om na te kijken.")
    # The filter line lines up with the rows.
    line = app.locator("#filter-nakijken").bounding_box()
    cell = app.locator("tbody td").first.bounding_box()
    assert abs(line["x"] - cell["x"]) <= 2, (line, cell)

    app.get_by_role("link", name="Kantoorwinkel", exact=True).click()
    expect(app.locator("#nakijken")).to_contain_text("Klopt alles? Hierna nog 2.")
    app.get_by_label("Leverancier").fill("Kantoorwinkel Noord")
    app.get_by_role("button", name="Klopt").click()

    expect(app.locator("#toasts")).to_contain_text("Uitgave nagekeken.")
    expect(app.get_by_label("Leverancier")).to_have_value("NS")
    expect(app.locator("#nog-nakijken")).to_have_text("Hierna nog 1.")
    last.refresh_from_db()
    assert (last.supplier, last.needs_review) == ("Kantoorwinkel Noord", False)

    app.get_by_role("link", name="Overslaan").click()
    expect(app.get_by_label("Leverancier")).to_have_value("Bouwmarkt")
    skipped.refresh_from_db()
    assert skipped.needs_review

    app.get_by_role("button", name="Klopt").click()
    # Round again to the one skipped, now the only one: no count, no skip.
    expect(app.get_by_label("Leverancier")).to_have_value("NS")
    expect(app.locator("#nakijken")).to_be_visible()
    expect(app.locator("#overslaan")).to_have_count(0)
    expect(app.locator("#nog-nakijken")).to_have_count(0)

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
