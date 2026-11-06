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
