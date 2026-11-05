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
