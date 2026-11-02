# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hulp in a real browser (huismus-intern/besluiten.md 2026-10-31): reaching it from
the sidebar and the phone's Meer menu, and a link from a screen landing on
the right heading. The pages in both languages and at every width:
test_every_page.py."""

import pytest
from playwright.sync_api import expect

from huismus.core import auto_backups

pytestmark = pytest.mark.django_db(transaction=True)


def test_help_from_the_sidebar(app):
    app.goto(app.base + "/")
    app.locator(".sidebar").get_by_role("link", name="Hulp").click()

    expect(app.locator("h1")).to_have_text("Hulp")
    app.locator("main").get_by_role("link", name="Mailen", exact=True).click()
    expect(app.locator("h1")).to_have_text("Mailen")
    expect(app.get_by_role("heading", name="Gmail")).to_be_visible()


def test_help_from_the_meer_menu_on_a_phone(app):
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/")
    app.locator(".tabbar").get_by_role("button", name="Meer").click()
    app.locator("#meer-menu").get_by_role("link", name="Hulp").click()

    expect(app.locator("h1")).to_have_text("Hulp")
    # A wide code block scrolls by itself, not the page.
    app.locator("main").get_by_role("link", name="Back-ups", exact=True).click()
    expect(app.locator("pre").first).to_be_visible()
    assert app.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


def test_how_to_link_a_folder_lands_on_its_heading(app, settings, tmp_path, monkeypatch):
    settings.DESKTOP = False
    monkeypatch.setattr(auto_backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")
    monkeypatch.setattr(auto_backups, "MOUNTINFO", tmp_path / "geen-proc")

    app.goto(app.base + "/instellingen/back-ups/map/")
    app.locator("#map-koppelen").get_by_role("link", name="Zo werkt het →").click()

    expect(app).to_have_url(app.base + "/hulp/back-ups/#een-map-koppelen")
    heading = app.get_by_role("heading", name="Een map koppelen")
    expect(heading).to_be_in_viewport()
