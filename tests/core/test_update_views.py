# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Updates, "Bijwerken" and the overview's banner in the
desktop app (SPEC.md M11, huismus/core/update_views.py)."""

from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core import updates

pytestmark = pytest.mark.django_db

RELEASE = {
    "version": "1.4.0",
    "page_url": "https://github.com/codebyarne/huismus/releases/tag/v1.4.0",
    "asset_url": "https://example.invalid/Huismus-1.4.0-macos.dmg",
    "asset_name": "Huismus-1.4.0-macos.dmg",
    "sha256": "ab" * 32,
}


@pytest.fixture(autouse=True)
def old_version():
    with patch("huismus.core.updates.current_version", return_value="1.3.0"):
        yield


@pytest.fixture
def desktop(settings, tmp_path, client):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "token"
    client.cookies["huismus_window"] = "token"
    return client


def _overview(client):
    Contact.objects.get_or_create(company_name="Klant BV")
    return client.get("/").content.decode()


def test_docker_has_no_update_pages_and_never_looks(client, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.login(username="pi", password="s3cret-pass")

    assert client.get(reverse("business:updates")).status_code == 404
    assert client.get(reverse("business:updates_install")).status_code == 404
    with patch("huismus.core.updates._fetch") as fetch:
        assert "Updates" not in client.get(reverse("business:overview")).content.decode()
    fetch.assert_not_called()


def test_the_page_shows_the_version_and_the_switch(desktop):
    page = desktop.get(reverse("business:updates")).content.decode()
    assert "Je gebruikt Huismus 1.3.0." in page
    assert 'name="enabled" role="switch" checked' in page
    assert 'id="nieuwe-versie"' not in page


def test_turning_it_off_hides_the_new_version(desktop):
    updates.update_status(available=RELEASE)
    assert 'id="nieuwe-versie"' in _overview(desktop)

    desktop.post(reverse("business:updates"), {})

    assert updates.load_status().enabled is False
    assert 'id="nieuwe-versie"' not in _overview(desktop)
    page = desktop.get(reverse("business:overview")).content.decode()
    assert "Versie 1.3.0" in page


def test_the_banner_and_the_card_name_the_new_version(desktop):
    updates.update_status(available=RELEASE)

    # Found, not downloaded yet (core.updates.prepare): that's what it says.
    assert "Huismus 1.4.0 is gevonden en wordt gedownload." in _overview(desktop)
    # Downloading failed (no internet): the plain notice.
    updates.update_status(download_failed=timezone.localtime().isoformat())
    assert "Er is een nieuwe versie: Huismus 1.4.0." in _overview(desktop)
    assert "Huismus 1.4.0 is er" in desktop.get(reverse("business:overview")).content.decode()
    page = desktop.get(reverse("business:updates")).content.decode()
    assert "Bijwerken naar 1.4.0" in page and "Wat is er nieuw in 1.4.0?" in page


def test_the_banner_goes_below_the_backup_banner(desktop):
    updates.update_status(available=RELEASE)
    page = _overview(desktop)
    assert page.index('id="back-upmelding"') < page.index('id="nieuwe-versie"')


def test_updating_is_confirmed_first(desktop):
    updates.update_status(available=RELEASE)
    page = desktop.get(reverse("business:updates_install")).content.decode()
    assert "Bijwerken naar 1.4.0?" in page
    assert "Huismus maakt eerst een back-up van je administratie." in page


def test_after_bijwerken_the_app_takes_over(desktop):
    updates.update_status(available=RELEASE)
    with patch("huismus.core.updates.install") as install:
        response = desktop.post(reverse("business:updates_install"))
    install.assert_called_once()
    assert "Huismus werkt zichzelf bij…" in response.content.decode()


def test_on_windows_updating_by_hand_means_installing_it(desktop, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    updates.update_status(available=RELEASE)
    with patch("huismus.core.updates.install", side_effect=updates.UpdateError("not-writable")):
        response = desktop.post(reverse("business:updates_install"), follow=True)
    page = response.content.decode()
    assert "Download de nieuwe versie en installeer hem." in page
    assert "Programma's" not in page


@pytest.mark.parametrize(
    "code, sentence",
    [
        ("digest", "niet controleren"),
        ("download", "niet downloaden"),
        ("backup", "geen back-up maken"),
        ("not-writable", "Nieuwe versie downloaden"),
    ],
)
def test_a_failed_update_says_why_on_the_updates_page(desktop, code, sentence):
    updates.update_status(available=RELEASE)
    with patch("huismus.core.updates.install", side_effect=updates.UpdateError(code)):
        response = desktop.post(reverse("business:updates_install"), follow=True)
    page = response.content.decode()
    assert 'id="bijwerken-mislukt"' in page and sentence in page


def test_after_an_update_the_overview_says_so_once(desktop):
    updates.update_status(just_updated="1.4.0")
    assert "Bijgewerkt naar 1.4.0." in _overview(desktop)
    assert "Bijgewerkt naar 1.4.0." not in _overview(desktop)


def test_an_update_that_didnt_get_installed_is_said_once(desktop):
    updates.update_status(not_installed="1.4.0")
    page = _overview(desktop)
    assert "Bijwerken naar 1.4.0 is niet gelukt. Je gebruikt nog versie 1.3.0." in page
    assert "is niet gelukt" not in _overview(desktop)
