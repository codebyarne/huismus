# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Updates, "Bijwerken" and the overview's banner in the
desktop app (SPEC.md M11, huismus/core/update_views.py), and the notice
Huismus in Docker gives instead."""

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
# In Docker a release has no file (core.updates.newest_release).
DOCKER_RELEASE = {
    "version": "1.3.1",
    "page_url": "https://github.com/codebyarne/huismus/releases/tag/v1.3.1",
    "asset_url": "",
    "asset_name": "",
    "sha256": "",
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


@pytest.fixture
def docker(client, settings, tmp_path):
    settings.DATA_DIR = tmp_path
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.login(username="pi", password="s3cret-pass")
    return client


def test_docker_never_looks_during_a_page(docker):
    # Only gunicorn's hourly thread looks (core.updates.start_hourly_thread).
    with patch("huismus.core.updates._fetch") as fetch:
        _overview(docker)
        docker.get(reverse("business:overview"))
        docker.get(reverse("business:updates"))
    fetch.assert_not_called()


def test_docker_has_no_bijwerken_button(docker):
    updates.update_status(available=DOCKER_RELEASE)

    page = docker.get(reverse("business:updates")).content.decode()
    assert "Je gebruikt Huismus 1.3.0." in page
    assert "Huismus 1.3.1 is er" in page and "Wat is er nieuw in 1.3.1?" in page
    assert "Bijwerken naar" not in page
    assert docker.get(reverse("business:updates_install")).status_code == 404


def test_docker_says_what_to_type(docker):
    updates.update_status(available=DOCKER_RELEASE)

    page = docker.get(reverse("business:updates")).content.decode()
    assert "Bijwerken doe je zelf." in page
    assert "docker compose pull" in page and "docker compose up -d" in page
    assert "compose.yaml</code> aan" not in page
    assert "/hulp/docker/#bijwerken" in page


def test_docker_a_new_x_y_needs_a_new_tag_first(docker):
    updates.update_status(available={**DOCKER_RELEASE, "version": "1.4.0"})

    page = docker.get(reverse("business:updates")).content.decode()
    assert "Voor 1.4 pas je eerst je <code>compose.yaml</code> aan" in page
    assert "ghcr.io/codebyarne/huismus:1.4" in page
    assert "docker compose pull" in page


def test_docker_shows_the_notice_and_the_card(docker):
    page = docker.get(reverse("business:overview")).content.decode()
    assert "Huismus zegt het als er een nieuwe versie is." in page
    assert "Versie 1.3.0" in page
    assert 'id="nieuwe-versie"' not in _overview(docker)

    updates.update_status(available=DOCKER_RELEASE)

    assert "Er is een nieuwe versie: Huismus 1.3.1." in _overview(docker)
    assert "wordt gedownload" not in _overview(docker)
    assert "Huismus 1.3.1 is er" in docker.get(reverse("business:overview")).content.decode()


def test_docker_switch_turns_the_looking_off(docker):
    updates.update_status(available=DOCKER_RELEASE)
    page = docker.get(reverse("business:updates")).content.decode()
    assert "Zoeken naar nieuwe versies" in page

    docker.post(reverse("business:updates"), {})

    assert updates.load_status().enabled is False
    assert 'id="nieuwe-versie"' not in _overview(docker)


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


def test_wat_is_er_nieuw_opens_the_page_on_the_site(desktop, docker):
    # The installed Huismus doesn't have the new version's text yet; the
    # site's copy of the help page is rebuilt with every release.
    updates.update_status(available=RELEASE)
    for page in (
        desktop.get(reverse("business:updates")),
        desktop.get(reverse("business:updates_install")),
        docker.get(reverse("business:updates")),
    ):
        html = page.content.decode()
        assert 'href="https://huismus.arnekrijnsen.com/hulp/nieuw/"' in html
        assert "releases/tag" not in html


def test_wat_is_er_nieuw_opens_the_english_page_in_english(docker):
    updates.update_status(available=DOCKER_RELEASE)
    docker.cookies["django_language"] = "en"
    html = docker.get(reverse("business:updates")).content.decode()
    assert "What's new in 1.3.1?" in html
    assert 'href="https://huismus.arnekrijnsen.com/en/help/nieuw/"' in html


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
