# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""docs/design/componenten.html in a browser: the app's own CSS and icons load,
the theme switch shows it dark, and nothing scrolls sideways on a phone. Its contents are
checked in tests/core/test_design_system.py."""

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
from playwright.sync_api import expect

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def page_url():
    # The page refers to ../../huismus/core/static and ../../templates: serve the repo root.
    handler = functools.partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    handler.log_message = lambda *args: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_port}/docs/design/componenten.html"
    server.shutdown()


@pytest.mark.parametrize("width", [390, 1440])
def test_the_component_page_uses_the_app_s_css_and_fits(page, page_url, width):
    page.set_viewport_size({"width": width, "height": 900})
    failed = []
    page.on("requestfailed", lambda request: failed.append(request.url))
    page.on("response", lambda r: r.status >= 400 and failed.append(r.url))
    page.goto(page_url)

    assert not failed
    # The page has no CSS of its own: a background on <body> means huismus.css applies.
    assert page.evaluate("getComputedStyle(document.body).backgroundColor") != "rgba(0, 0, 0, 0)"
    icon = page.locator('#iconen use[href$="#home"]').bounding_box()
    assert icon and icon["width"] > 0
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 0


def test_the_theme_switch_makes_the_page_dark_and_shows_its_choice(page, page_url):
    page.goto(page_url)
    background = page.evaluate("getComputedStyle(document.body).backgroundColor")
    expect(page.locator('input[name="thema"][value=""]')).to_be_checked()

    page.locator('label:has(input[name="thema"][value="dark"])').click()

    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    expect(page.locator("body")).not_to_have_css("background-color", background)
    page.reload()
    expect(page.locator('input[name="thema"][value=""]')).to_be_checked()
