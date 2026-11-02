# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Walk through the whole app like a user, on a real-size administration.

The bugs these catch are in the seams between pages, not in one page: a
menu covered by something, a list that hides most of the data, a click that
lands on the wrong thing after a page swap. Runs in every browser engine
at phone, small-laptop and desktop width (CLAUDE.md: CI runs all three).
"""

import re

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)

WIDTHS = [390, 1024, 1440]
# (label in the menu, path). Quotes and "Importeren" sit under "Meer" on a phone.
SECTIONS = [
    ("Overzicht", "/"),
    ("Facturen", "/facturen/"),
    ("Offertes", "/offertes/"),
    ("Klanten", "/contacten/"),
    ("Uitgaven", "/uitgaven/"),
    ("Importeren", "/importeren/"),
    ("Instellingen", "/instellingen/"),
]
# What every menu item must be reachable by: the sidebar, or the tab bar and
# the "Meer" popover on a phone.
MENU_LINKS = ".sidebar .nav > a, .tabbar > a:not(.fab), #meer-menu a"


def _open_menu_item(page, label):
    """Click a menu item the way the width allows."""
    if page.viewport_size["width"] < 800:
        tab = page.locator(".tabbar > a", has_text=label)
        if tab.count():
            tab.click()
        else:
            # A page swap that lands just after opening the menu closes it
            # again: open it and pick the item once more.
            for attempt in range(3):
                page.locator(".tabbar button", has_text="Meer").click()
                try:
                    # exact: a label must not also pick a longer one that contains it.
                    menu = page.locator("#meer-menu")
                    menu.get_by_role("link", name=label, exact=True).click(timeout=1500)
                    break
                except PlaywrightTimeoutError:
                    if attempt == 2:
                        raise
    else:
        page.locator(".sidebar .nav > a", has_text=label).first.click()


def _assert_nothing_covers_the_menu(page):
    """The centre of every visible menu item must hit that item itself.
    A stretched row link once covered the whole screen in Safari."""
    # A page swap runs a 180 ms view transition, during which every hit test
    # answers "html". Look again for up to two seconds before calling it a bug.
    covered = []
    for _ in range(20):
        covered = _covered_menu_items(page)
        if not covered:
            return
        page.wait_for_timeout(100)
    raise AssertionError(f"covered menu items on {page.url}: {covered}")


def _covered_menu_items(page):
    return page.evaluate(
        """(selector) => {
            const out = [];
            for (const link of document.querySelectorAll(selector)) {
                const box = link.getBoundingClientRect();
                // Skip what isn't on screen: the sidebar on a phone, the closed "Meer" menu.
                if (!box.width || !box.height || !link.checkVisibility()) continue;
                if (box.right <= 0 || box.bottom <= 0) continue;
                if (box.left >= innerWidth || box.top >= innerHeight) continue;
                const x = box.x + box.width / 2;
                const y = box.y + box.height / 2;
                const top = document.elementFromPoint(x, y);
                if (!link.contains(top)) {
                    out.push(link.textContent.trim() + " <- " + top?.outerHTML.slice(0, 80));
                }
            }
            return out;
        }""",
        MENU_LINKS,
    )


@pytest.mark.parametrize("width", WIDTHS)
def test_every_menu_item_works_twice_in_a_row_with_a_full_administration(app, history, width):
    app.set_viewport_size({"width": width, "height": 800})
    # The second click of a double click replaces the first one's request.
    # WebKit reports that cancelled request as an htmx send error; for a
    # user it is harmless, so this test does not count it.
    app.tolerate.append("htmx:")
    for label, path in SECTIONS:
        for _ in range(2):
            app.goto(app.base + "/contacten/")
            _open_menu_item(app, label)
            expect(app).to_have_url(app.base + path)
            _open_menu_item(app, label)  # the double click
            expect(app).to_have_url(app.base + path)
            expect(app.locator("h1").first).to_be_visible()
            _assert_nothing_covers_the_menu(app)
            # Let the double click's second request finish: leaving the page
            # now would abort it and the browser logs that as an error.
            app.wait_for_load_state("networkidle")


@pytest.mark.parametrize("width", WIDTHS)
def test_a_row_opens_its_document_and_the_menu_still_works_after(app, history, width):
    app.set_viewport_size({"width": width, "height": 800})
    for label, path, detail in [
        ("Facturen", "/facturen/", r"/facturen/\d+/"),
        ("Offertes", "/offertes/", r"/offertes/\d+/"),
        ("Klanten", "/contacten/", r"/contacten/\d+/"),
    ]:
        app.goto(app.base + path)
        app.locator("tr.is-link .row-link").first.click()
        expect(app).to_have_url(re.compile(detail))
        _open_menu_item(app, label)
        expect(app).to_have_url(app.base + path)
        app.wait_for_load_state("networkidle")


def test_the_invoice_list_shows_every_year_not_only_this_one(app, history):
    app.goto(app.base + "/facturen/")
    total = Document.objects.filter(kind="invoice").count()
    expect(app.locator("tr.is-link")).to_have_count(min(total, 50))
    # The year filter narrows; it must not be what hides the older invoices.
    expect(app.locator("select[name=jaar]")).to_have_value("alle")
