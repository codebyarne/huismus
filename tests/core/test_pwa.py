# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Installing Huismus as an app (huismus/core/pwa.py): manifest, service worker,
offline page."""

import json

import pytest
from django.contrib.staticfiles import finders
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_the_manifest_describes_a_standalone_app(client):
    response = client.get(reverse("pwa_manifest"))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/manifest+json"
    manifest = json.loads(response.content)
    assert manifest["name"] == "Huismus"
    assert manifest["display"] == "standalone"
    assert manifest["start_url"] == reverse("home")
    assert manifest["scope"] == "/"


def test_every_manifest_icon_exists(client):
    icons = json.loads(client.get(reverse("pwa_manifest")).content)["icons"]

    assert {icon["purpose"] for icon in icons} == {"any", "maskable"}
    for icon in icons:
        # In tests static files are served straight from disk (settings_test).
        path = icon["src"].removeprefix("/static/")
        assert finders.find(path), icon["src"]


def test_the_manifest_follows_the_language(client):
    client.cookies["django_language"] = "en"

    manifest = json.loads(client.get(reverse("pwa_manifest")).content)

    assert manifest["lang"] == "en"
    assert manifest["description"].startswith("Self-hosted")


def test_the_service_worker_covers_the_whole_app(client):
    response = client.get(reverse("pwa_service_worker"))

    assert reverse("pwa_service_worker") == "/sw.js"
    assert response["Content-Type"].startswith("text/javascript")
    assert response["Cache-Control"] == "no-cache"
    assert reverse("pwa_offline").encode() in response.content


def test_the_offline_page_needs_no_login_and_no_other_files(client):
    response = client.get(reverse("pwa_offline"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "Huismus is niet bereikbaar" in html
    # Shown when the server can't be reached, so it can't load anything
    # from it: no stylesheet, script or image links.
    assert "<link" not in html
    assert "<script" not in html
    assert "<img" not in html


def test_pages_link_the_manifest_and_the_home_screen_icon(client):
    html = client.get(reverse("login")).content.decode()

    assert f'<link rel="manifest" href="{reverse("pwa_manifest")}">' in html
    assert "core/icons/apple-touch-icon.png" in html
    assert 'name="theme-color"' in html


# Addresses outside Huismus: in the installed app iOS opens those in a sheet
# with "Gereed", so a new tab there is fine.
_ELSEWHERE = ("{{ whats_new_url }}", "{{ authorize_url }}", "{{ release.page_url }}")


def test_every_new_tab_inside_huismus_has_a_way_back_in_the_installed_app():
    # In the app on the home screen a new tab of Huismus's own takes over the
    # screen with no back button (a receipt in Verwerken, the owner on an
    # iPhone, BUGS-BY-HAND.md). Each such link or button needs app.js's
    # answer there: a dialog over the page (data-view-receipt,
    # data-preview-pdf) or a sheet (data-file).
    import re
    from pathlib import Path

    templates = Path(__file__).resolve().parents[2] / "huismus" / "templates"
    stranded = []
    for path in templates.rglob("*.html"):
        if path.parts[-2] == "site":  # the public site: no app there
            continue
        for tag in re.findall(r"<(?:a|button)\b[^>]*target=\"_blank\"[^>]*>", path.read_text()):
            href = re.search(r'href="([^"]*)"', tag)
            if href and href.group(1) in _ELSEWHERE:
                continue
            if not re.search(r"data-(view-receipt|preview-pdf|file)\b", tag):
                stranded.append(f"{path.relative_to(templates)}: {tag[:120]}")
    assert not stranded, stranded
