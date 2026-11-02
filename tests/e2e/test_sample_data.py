# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Probeer met nepdata" in a real browser (huismus/core/sample_data.py): from the
empty overview to nine years of made-up records and back. The pages in
both languages and at every width: test_every_page.py."""

import time

import pytest
from django.db import connection
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.core import sample_data
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)


def test_try_the_sample_data_and_clear_it_again(app):
    app.goto(app.base + "/")
    expect(app.locator("h1")).to_have_text("Welkom bij Huismus")
    app.get_by_role("button", name="Probeer met nepdata").click()

    expect(app.locator("#nepdata-melding")).to_contain_text("verzonnen gegevens")
    expect(app.locator(".kpi-hero")).to_be_visible()
    app.goto(app.base + "/facturen/?jaar=alle")
    expect(app.locator("#nepdata-melding")).to_be_visible()
    assert Document.objects.filter(kind="invoice").count() > 50

    app.locator("#nepdata-melding").click()
    expect(app.locator("h1")).to_have_text("Nepdata leegmaken?")
    app.get_by_role("link", name="Annuleren").click()
    expect(app).to_have_url(app.base + "/")
    expect(app.locator("#nepdata-melding")).to_be_visible()

    app.locator("#nepdata-melding").click()
    app.get_by_role("button", name="Leegmaken").click()

    expect(app).to_have_url(app.base + "/")
    expect(app.locator(".toast")).to_contain_text("De nepdata is weg.")
    expect(app.locator("h1")).to_have_text("Welkom bij Huismus")
    expect(app.locator("#nepdata-melding")).to_have_count(0)
    # This test's own connection still has the file from before open; the
    # app's request threads each open a new one.
    connection.close()
    assert not Document.objects.exists()
    assert Settings.load().business_name == "Voorbeeld BV"  # the app fixture's
    assert not sample_data.in_use()


def test_the_sample_data_s_pages_have_no_known_kind_of_ui_bug(app):
    from tests.e2e.test_every_page import WIDTHS, _data_texts, _dutch_ui_texts, _problems_on

    dutch = _dutch_ui_texts()
    found = []

    def check(paths):
        data = sorted(_data_texts(), key=len, reverse=True)
        for width in WIDTHS:
            app.set_viewport_size({"width": width, "height": 800})
            for language in ["nl", "en"]:
                app.context.add_cookies(
                    [{"name": "django_language", "value": language, "url": app.base}]
                )
                for path in paths:
                    english = dutch if language == "en" else []
                    for problem in _problems_on(app, path, language, english, data):
                        found.append(f"{language} {path} @ {width}px — {problem}")

    check(["/"])  # the welcome card with the button
    app.context.add_cookies([{"name": "django_language", "value": "nl", "url": app.base}])
    app.goto(app.base + "/")
    app.get_by_role("button", name="Probeer met nepdata").click()
    expect(app.locator("#nepdata-melding")).to_be_visible()
    check(["/", "/facturen/", "/nepdata/leegmaken/"])
    assert found == [], "\n".join(found)


def double_click(app, button):
    """Two real clicks 100 ms apart, as a person double-clicks: Playwright's
    own dblclick() is so fast that the browser merges both into one request."""
    button.scroll_into_view_if_needed()
    box = button.bounding_box()
    x, y = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    app.mouse.click(x, y)
    app.wait_for_timeout(100)
    app.mouse.click(x, y)


def test_a_double_click_on_leegmaken_sends_it_once(app, monkeypatch):
    # The real restore takes a moment on a Pi; here it is too quick for the
    # second click to land while it runs.
    slow = sample_data.restore_backup
    monkeypatch.setattr(sample_data, "restore_backup", lambda path: (time.sleep(1), slow(path)))
    app.goto(app.base + "/")
    app.get_by_role("button", name="Probeer met nepdata").click()
    app.locator("#nepdata-melding").click()
    expect(app.locator("h1")).to_have_text("Nepdata leegmaken?")
    app.wait_for_load_state("networkidle")
    posts = []
    app.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)

    double_click(app, app.get_by_role("button", name="Leegmaken"))

    expect(app.locator(".toast")).to_contain_text("De nepdata is weg.", timeout=10_000)
    expect(app.locator("h1")).to_have_text("Welkom bij Huismus")
    assert posts == [app.base + "/nepdata/leegmaken/"]

    # Not stuck for the next time: a new page has a working button.
    app.get_by_role("button", name="Probeer met nepdata").click()
    app.locator("#nepdata-melding").click()
    app.get_by_role("button", name="Leegmaken").click()
    expect(app.locator(".toast")).to_contain_text("De nepdata is weg.")
    assert len(posts) == 3  # and filling, and clearing once more
    # The app replaced the database file; this test's own connection still
    # has the old one open (and the cleanup after the test would empty that).
    connection.close()
    assert not sample_data.in_use()
