# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Updates in Docker, in a real browser: "Nu zoeken" looks on
GitHub right away (SPEC.md M11, core.update_views.check). The desktop app's
updates are in test_desktop_app.py."""

import json

import pytest
from playwright.sync_api import expect

pytestmark = pytest.mark.django_db(transaction=True)


def test_nu_zoeken_shows_a_new_version_right_away(app, tmp_path, monkeypatch):
    from huismus.core import updates

    listing = tmp_path / "releases.json"
    listing.write_text(json.dumps([]))
    monkeypatch.setenv("HUISMUS_RELEASES_URL", listing.as_uri())
    monkeypatch.setattr(updates, "current_version", lambda: "1.3.0")

    app.goto(app.base + "/instellingen/updates/")
    app.get_by_role("button", name="Nu zoeken").click()
    expect(app.locator("body")).to_contain_text("Je gebruikt de nieuwste versie.")
    expect(app.locator("#nieuwe-versie")).to_have_count(0)

    # A release comes out: the next look finds it, without waiting a day.
    listing.write_text(
        json.dumps(
            [
                {
                    "tag_name": "v1.3.1",
                    "html_url": "https://github.com/codebyarne/huismus/releases/tag/v1.3.1",
                    "assets": [],
                }
            ]
        )
    )
    app.get_by_role("button", name="Nu zoeken").click()
    expect(app.locator("body")).to_contain_text("Er is een nieuwe versie: Huismus 1.3.1.")
    expect(app.locator("#nieuwe-versie")).to_contain_text("docker compose pull")


def test_on_a_phone_the_new_version_is_in_sight_without_scrolling(app, history, settings, tmp_path):
    """The owner on the Pi: on a phone the three figures stack, and the notice
    below them fell out of sight (BUGS-BY-HAND.md, 2026-11-06). Every notice on
    the overview comes before the figures."""
    from huismus.core import updates

    settings.DATA_DIR = tmp_path
    updates.update_status(
        available={
            "version": "1.3.1",
            "page_url": "https://github.com/codebyarne/huismus/releases/tag/v1.3.1",
            "asset_url": "",
            "asset_name": "",
            "sha256": "",
        }
    )
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/")

    banner = app.locator("#nieuwe-versie")
    expect(banner).to_be_in_viewport()
    first_figure = app.locator(".kpi").first.bounding_box()
    notices = app.locator(".hint-banner")
    assert notices.count() >= 2
    for box in (notices.nth(i).bounding_box() for i in range(notices.count())):
        assert box["y"] < first_figure["y"]


@pytest.mark.parametrize("width", [360, 1440])
def test_after_an_update_the_notice_goes_once_closed(
    app, history, settings, tmp_path, monkeypatch, width
):
    """ "Huismus is bijgewerkt" (issue #149): the close button takes away
    only the notice, and it stays away; on a phone the button stays beside
    the text and the link goes below it."""
    from huismus.core import updates

    settings.DATA_DIR = tmp_path
    # A long version number on the narrowest phone.
    monkeypatch.setattr(updates, "current_version", lambda: "10.12.13")
    updates.update_status(seen_version="0.0.1")
    app.set_viewport_size({"width": width, "height": 844})
    app.goto(app.base + "/")

    notice = app.locator("#bijgewerkt")
    expect(notice).to_contain_text("Huismus is bijgewerkt naar 10.12.13.")
    expect(notice).to_be_in_viewport()
    close = notice.get_by_role("button", name="Sluiten")
    link = notice.get_by_role("link", name="Wat is er nieuw")
    box, close_box, link_box = (x.bounding_box() for x in (notice, close, link))
    assert close_box["x"] + close_box["width"] <= box["x"] + box["width"]
    assert close_box["y"] < link_box["y"] if width == 360 else close_box["x"] > link_box["x"]

    close.click()
    expect(notice).to_have_count(0)
    app.reload()
    expect(app.locator("#bijgewerkt")).to_have_count(0)


def test_after_an_update_whats_new_is_one_click_away(app, history, settings, tmp_path):
    from huismus.core import updates

    settings.DATA_DIR = tmp_path
    updates.update_status(seen_version="0.0.1")
    app.goto(app.base + "/")

    app.locator("#bijgewerkt").get_by_role("link", name="Wat is er nieuw").click()
    expect(app.locator("h1")).to_contain_text("Wat is er nieuw")
    app.goto(app.base + "/")
    expect(app.locator("#bijgewerkt")).to_have_count(0)
