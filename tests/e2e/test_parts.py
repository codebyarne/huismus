# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen › Onderdelen (#260) in a real browser: switch Offertes and
Uitgaven off, and see them leave the sidebar, the tab bar and its menus."""

import pytest
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db(transaction=True)


def _switch_off_quotes_and_expenses(app):
    app.goto(app.base + "/instellingen/")
    app.get_by_role("link", name="Onderdelen").click()
    app.get_by_label("Offertes").uncheck()
    app.get_by_label("Uitgaven").uncheck()
    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    settings = Settings.load()
    assert (settings.show_quotes, settings.show_expenses, settings.show_bank) == (False, False, True)


def test_parts_switched_off_leave_the_sidebar(app):
    app.set_viewport_size({"width": 1440, "height": 900})
    _switch_off_quotes_and_expenses(app)
    sidebar = app.locator(".sidebar nav.nav").first
    expect(sidebar.get_by_role("link", name="Offertes")).to_have_count(0)
    expect(sidebar.get_by_role("link", name="Uitgaven")).to_have_count(0)
    expect(sidebar.get_by_role("link", name="Bank")).to_be_visible()


def test_parts_switched_off_leave_the_tab_bar_and_its_menus(app):
    app.set_viewport_size({"width": 390, "height": 844})
    _switch_off_quotes_and_expenses(app)
    tabbar = app.locator("nav.tabbar")
    # Klanten takes the fourth place.
    expect(tabbar.get_by_role("link", name="Klanten")).to_be_visible()
    expect(tabbar.get_by_role("link", name="Uitgaven")).to_have_count(0)

    tabbar.get_by_role("button", name="Nieuw").click()
    plus = app.locator("#plus-menu")
    expect(plus.get_by_role("link", name="Factuur")).to_be_visible()
    expect(plus.get_by_role("link", name="Offerte")).to_have_count(0)
    expect(plus.get_by_role("link", name="Uitgave")).to_have_count(0)
    app.keyboard.press("Escape")

    tabbar.get_by_role("button", name="Meer").click()
    meer = app.locator("#meer-menu")
    expect(meer.get_by_role("link", name="Bank")).to_be_visible()
    expect(meer.get_by_role("link", name="Offertes")).to_have_count(0)
    expect(meer.get_by_role("link", name="Categorieën")).to_have_count(0)
    expect(meer.get_by_role("link", name="Klanten")).to_have_count(0)


def test_a_part_with_data_stays_and_says_why(app):
    Expense.objects.create(date="2026-01-01", amount_cents=1000)
    app.goto(app.base + "/instellingen/onderdelen/")
    box = app.get_by_label("Uitgaven")
    expect(box).to_be_checked()
    expect(box).to_be_disabled()
    expect(box).to_have_accessible_description(
        "Je hebt uitgaven of bonnetjes, dus Uitgaven blijft in het menu."
    )
