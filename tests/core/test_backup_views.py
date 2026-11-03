# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Back-ups, terugzetten, and the overview's backup banner
in the desktop app (SPEC.md M11) and on Docker (M15); huismus/core/backup_views.py."""

import io
import sqlite3
import tarfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core import auto_backups as backups
from huismus.core.backup import create_backup

pytestmark = pytest.mark.django_db


# Docker without a linked folder: the same sentence on the folder page, the
# row on Back-ups and the banner (huismus-intern/besluiten.md, 2026-11-01).
LINK_FIRST = {
    "nl": "Huismus in Docker ziet alleen mappen die je eraan koppelt."
    " Koppel eerst een map, bijvoorbeeld van je NAS of een USB-schijf.",
    "en": "In Docker, Huismus only sees folders you link to it."
    " Link a folder first, for example on your NAS or a USB drive.",
}


@pytest.fixture
def data_dir(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def desktop(settings, data_dir, client):
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "token"
    client.cookies["huismus_window"] = "token"
    return client


@pytest.fixture
def drive(tmp_path):
    (tmp_path / "iCloud").mkdir()
    return tmp_path / "iCloud" / "Huismus"


@pytest.fixture
def docker(client, data_dir, tmp_path, monkeypatch):
    """Signed in on Docker (SPEC.md M15), with a folder linked in."""
    get_user_model().objects.create_user(username="pi", password="s3cret-pass")
    client.login(username="pi", password="s3cret-pass")
    linked = tmp_path / "backups"
    linked.mkdir()
    monkeypatch.setattr(backups, "LINKED_FOLDER", linked)
    # The test machine's own disks, whatever they are, are not a container.
    monkeypatch.setattr(backups, "MOUNTINFO", tmp_path / "geen-proc")
    return client


def test_docker_offers_the_linked_folder(docker, tmp_path):
    page = docker.get(reverse("business:backups_folder")).content.decode()

    assert "Huismus maakt elke dag een back-up in deze map." in page
    assert "Gekoppelde map" in page and f'value="{tmp_path / "backups"}" checked' in page
    assert "Gevonden op deze computer" not in page
    assert 'id="map-koppelen"' not in page


def test_docker_without_a_linked_folder_says_how(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")

    page = docker.get(reverse("business:backups_folder")).content.decode()

    assert 'id="map-koppelen"' in page and 'href="/hulp/back-ups/#een-map-koppelen"' in page
    assert LINK_FIRST["nl"] in page
    assert "Een gekoppelde map, bijvoorbeeld op je NAS" in page

    docker.cookies["django_language"] = "en"
    page = docker.get(reverse("business:backups_folder")).content.decode()
    assert 'href="/hulp/back-ups/#linking-a-folder"' in page
    assert LINK_FIRST["en"] in page


def test_docker_without_a_linked_folder_says_the_same_on_the_overview_row(
    docker, tmp_path, monkeypatch
):
    """The row "Map" on Back-ups says what the folder page and the banner say."""
    monkeypatch.setattr(backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")

    assert LINK_FIRST["nl"] in docker.get(reverse("business:backups")).content.decode()
    docker.cookies["django_language"] = "en"
    assert LINK_FIRST["en"] in docker.get(reverse("business:backups")).content.decode()


def test_docker_with_a_folder_chosen_no_longer_says_to_link_one(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")
    (tmp_path / "usb").mkdir()
    backups.choose_folder(backups.check_folder(str(tmp_path / "usb" / "Huismus")))

    page = docker.get(reverse("business:backups_folder")).content.decode()

    assert 'id="map-koppelen"' not in page


def test_docker_choosing_the_linked_folder_makes_a_backup(docker, tmp_path):
    linked = tmp_path / "backups"
    response = docker.post(reverse("business:backups_folder"), {"folder": str(linked)}, follow=True)

    assert "Er staat nu een back-up in de map." in response.content.decode()
    assert len(list(linked.glob("huismus-backup-*.tar.gz"))) == 1


def test_docker_refuses_a_folder_inside_the_container(docker, tmp_path):
    (tmp_path / "mountinfo").write_text("1 0 0:1 / / rw - overlay overlay rw\n")
    with patch.object(backups, "MOUNTINFO", tmp_path / "mountinfo"):
        response = docker.post(
            reverse("business:backups_folder"),
            {"folder": "other", "other_path": str(tmp_path / "in-de-container")},
        )

    assert "Deze map is weg zodra Huismus wordt bijgewerkt." in response.content.decode()
    assert backups.chosen_folder() is None


def test_docker_shows_the_card_and_the_banner(docker):
    settings_page = docker.get(reverse("business:overview")).content.decode()
    assert "Back-ups" in settings_page and "Nog geen map gekozen" in settings_page
    # Updates and Wachtwoord stay the desktop app's.
    assert reverse("business:updates") not in settings_page

    assert 'id="back-upmelding"' in _overview(docker)


def test_docker_restores_an_upload(docker, data_dir, tmp_path):
    archive = create_backup(tmp_path / "van-de-laptop")
    url = reverse("business:backups_restore")
    with archive.open("rb") as file:
        upload = io.BytesIO(file.read())
    upload.name = archive.name

    confirm = docker.post(url, {"step": "check", "file": upload})
    assert "Huismus back-ups, bij je administratie" in confirm.content.decode()
    with patch.object(backups, "restore") as restore:
        docker.post(url, {"step": "confirm", "archive": "upload"})

    restored = restore.call_args.args[0]
    assert restored.parent == data_dir / "backups"


def _forget_every_login(*args, **kwargs):
    """What restoring a backup from before this login does: the sessions
    go back with the database (huismus-intern/besluiten.md, 2026-10-31)."""
    from django.contrib.sessions.models import Session

    Session.objects.all().delete()


def _restore_confirmed(client, data_dir, tmp_path, **restore):
    archive = create_backup(tmp_path / "van-de-laptop")
    url = reverse("business:backups_restore")
    with archive.open("rb") as file:
        upload = io.BytesIO(file.read())
    upload.name = archive.name
    client.post(url, {"step": "check", "file": upload})
    with patch.object(backups, "restore", **restore):
        return client.post(url, {"step": "confirm", "archive": "upload"}, follow=True)


def test_after_restoring_you_stay_signed_in(docker, data_dir, tmp_path):
    response = _restore_confirmed(docker, data_dir, tmp_path, side_effect=_forget_every_login)

    assert response.redirect_chain[-1][0] == reverse("home")
    assert "Teruggezet naar vandaag" in response.content.decode()
    assert docker.get(reverse("home")).status_code == 200


def test_after_restoring_a_backup_without_you_the_login_page_says_it(docker, data_dir, tmp_path):
    def other_administration(*args, **kwargs):
        _forget_every_login()
        get_user_model().objects.filter(username="pi").delete()
        get_user_model().objects.create_user(username="iemand-anders", password="x-pass-123")

    response = _restore_confirmed(docker, data_dir, tmp_path, side_effect=other_administration)

    assert reverse("login") in response.redirect_chain[-1][0]
    assert "Teruggezet naar vandaag" in response.content.decode()


def test_after_restoring_an_inactive_user_is_not_signed_in(docker, data_dir, tmp_path):
    def inactive(*args, **kwargs):
        _forget_every_login()
        get_user_model().objects.filter(username="pi").update(is_active=False)

    response = _restore_confirmed(docker, data_dir, tmp_path, side_effect=inactive)

    assert reverse("login") in response.redirect_chain[-1][0]


def test_the_overview_shows_the_three_places_as_equals(desktop, drive):
    # Besluit 2026-11-01: the folder had "heel veel prio" over the cloud.
    page = desktop.get(reverse("business:backups")).content.decode()
    rows = [page.index(f'id="plek-{place}"') for place in ("map", "dropbox", "webdav")]
    assert rows == sorted(rows)
    assert "Kies een map, dan gaat het vanzelf." in page
    assert 'name="other_path"' not in page  # the form is on the folder's own page
    assert "Nu back-up maken" not in page  # nothing is on yet

    backups.choose_folder(drive)
    page = desktop.get(reverse("business:backups")).content.decode()
    row = page.split('id="plek-map"')[1].split('id="plek-dropbox"')[0]
    assert ">Aan<" in row and "Wijzigen" in row and "Nu back-up maken" in page


def test_choosing_a_folder_makes_the_first_backup(desktop, drive):
    response = desktop.post(
        reverse("business:backups_folder"),
        {"folder": "other", "other_path": str(drive)},
        follow=True,
    )

    assert backups.chosen_folder() == drive
    assert len(list(drive.glob("huismus-backup-*.tar.gz"))) == 1
    page = response.content.decode()
    assert "Er staat nu een back-up in de map." in page
    assert "Laatste back-up: vandaag" in page


def test_a_folder_on_a_missing_drive_shows_an_error_at_the_field(desktop, tmp_path):
    response = desktop.post(
        reverse("business:backups_folder"),
        {"folder": "other", "other_path": str(tmp_path / "USB" / "Huismus")},
    )

    assert response.status_code == 200
    assert 'aria-invalid="true"' in response.content.decode()
    assert "Is de schijf aangesloten?" in response.content.decode()
    assert backups.chosen_folder() is None


def test_backup_now_and_the_list(desktop, drive):
    backups.choose_folder(drive)
    response = desktop.post(reverse("business:backups"), {"action": "now"}, follow=True)
    assert "Back-up gemaakt in de map." in response.content.decode()

    page = desktop.get(reverse("business:backups_folder")).content.decode()
    assert "Back-ups in deze map" in page
    assert page.split('id="back-ups-in-map"')[1].count('class="f-meta"') == 1


def test_the_overview_card_follows_the_status(desktop, drive):
    card = 'href="/instellingen/back-ups/"'
    page = desktop.get(reverse("business:overview")).content.decode()
    assert card in page and "Nog geen map gekozen" in page

    backups.choose_folder(drive)
    backups.make_backup()
    page = desktop.get(reverse("business:overview")).content.decode()
    assert "Laatste back-up: vandaag" in page

    drive.rename(drive.with_name("weg"))
    backups.make_backup()
    page = desktop.get(reverse("business:overview")).content.decode()
    assert "Mislukt" in page


# -- The overview's banner ---------------------------------------------------


def _overview(client):
    # The overview's figures start once there is something.
    Contact.objects.get_or_create(company_name="Klant BV")
    return client.get("/").content.decode()


def test_banner_without_a_folder(desktop):
    page = _overview(desktop)
    assert 'id="back-upmelding"' in page
    assert "Je hebt nog geen back-up. Kies een map, dan gaat het vanzelf." in page


def test_banner_without_a_folder_in_english(desktop):
    desktop.cookies["django_language"] = "en"
    page = _overview(desktop)
    assert "You have no backup yet. Choose a folder, and it happens by itself." in page


# On Docker you first link a folder into the container yourself (`-v …:/backups`),
# so "choose a folder" alone isn't what has to happen (huismus-intern/besluiten.md, 2026-10-31).


def test_banner_on_docker_without_a_linked_folder_says_to_link_one(docker, tmp_path, monkeypatch):
    monkeypatch.setattr(backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")

    page = _overview(docker)
    assert (
        "Je hebt nog geen back-up. Huismus in Docker ziet alleen mappen die je eraan koppelt."
        " Koppel eerst een map, bijvoorbeeld van je NAS of een USB-schijf." in page
    )
    assert "Kies een map, dan gaat het vanzelf." not in page
    assert "Back-ups instellen" in page

    docker.cookies["django_language"] = "en"
    page = _overview(docker)
    assert (
        "You have no backup yet. In Docker, Huismus only sees folders you link to it."
        " Link a folder first, for example on your NAS or a USB drive." in page
    )
    assert "Set up backups" in page


def test_banner_on_docker_with_a_linked_folder_says_to_choose_it(docker):
    page = _overview(docker)
    assert "Je hebt nog geen back-up. Kies de gekoppelde map, dan gaat het vanzelf." in page
    assert "Back-ups instellen" in page

    docker.cookies["django_language"] = "en"
    page = _overview(docker)
    assert "You have no backup yet. Choose the linked folder, and it happens by itself." in page


def test_banner_after_a_failure_names_the_folder(desktop, drive):
    backups.choose_folder(drive)
    drive.rmdir()
    backups.make_backup()

    page = _overview(desktop)
    assert "hint-banner is-bad" in page
    assert f"de map {drive} is niet bereikbaar." in page


def test_banner_after_seven_days_without_a_backup(desktop, drive):
    backups.choose_folder(drive)
    backups.make_backup(timezone.localtime() - timedelta(days=8))

    page = _overview(desktop)
    assert "hint-banner is-warn" in page and "Je laatste back-up is van" in page


def test_no_banner_after_todays_backup(desktop, drive):
    backups.choose_folder(drive)
    backups.make_backup()

    page = _overview(desktop)
    assert 'id="back-upmelding"' not in page
    assert 'id="laatste-back-up"' in page


# -- Terugzetten --------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_restore_asks_first_and_then_restores(desktop, drive, data_dir):
    backups.choose_folder(drive)
    archive = backups.make_backup()
    url = reverse("business:backups_restore")

    confirm = desktop.post(url, {"step": "check", "archive": archive.name})
    assert confirm.status_code == 200
    page = confirm.content.decode()
    assert "Terugzetten naar vandaag" in page and str(drive) in page

    response = desktop.post(url, {"step": "confirm", "archive": archive.name}, follow=True)
    assert response.redirect_chain[-1][0] == "/"
    assert "Teruggezet naar vandaag" in response.content.decode()
    # The state before is a second archive in the folder.
    assert len(list(drive.glob("huismus-backup-*.tar.gz"))) == 2


def test_restore_never_takes_a_path_from_the_form(desktop, drive, tmp_path):
    other = create_backup(tmp_path / "elders")

    response = desktop.post(
        reverse("business:backups_restore"), {"step": "confirm", "archive": str(other)}
    )
    assert "Kies een back-up." in response.content.decode()


def test_an_uploaded_file_that_isnt_a_backup_touches_nothing(desktop, data_dir):
    upload = io.BytesIO(b"geen archief")
    upload.name = "foto.tar.gz"

    response = desktop.post(reverse("business:backups_restore"), {"step": "check", "file": upload})

    assert "Dit bestand is geen back-up van Huismus." in response.content.decode()
    assert not (data_dir / "db.sqlite3").exists()
    assert not (data_dir.parent / ".huismus-terugzetten.tar.gz").exists()


def test_a_backup_from_a_newer_huismus_is_refused(desktop, tmp_path):
    database = tmp_path / "db.sqlite3"
    connection = sqlite3.connect(database)
    connection.execute("CREATE TABLE django_migrations (app TEXT, name TEXT, applied TEXT)")
    connection.execute("INSERT INTO django_migrations VALUES ('documents', '9999_toekomst', '')")
    connection.commit()
    connection.close()
    archive = tmp_path / "nieuw.tar.gz"
    with tarfile.open(archive, "w:gz") as tar:
        tar.add(database, arcname="db.sqlite3")

    with archive.open("rb") as upload:
        response = desktop.post(
            reverse("business:backups_restore"), {"step": "check", "file": upload}
        )

    assert "nieuwere versie van Huismus" in response.content.decode()


@pytest.mark.django_db(transaction=True)
def test_an_uploaded_backup_is_restored_with_its_own_date(desktop, data_dir, tmp_path):
    archive = create_backup(tmp_path / "van-de-pi")
    url = reverse("business:backups_restore")

    with archive.open("rb") as upload:
        confirm = desktop.post(url, {"step": "check", "file": upload})
    assert "Terugzetten naar vandaag" in confirm.content.decode()
    staged = Path(data_dir.parent / ".huismus-terugzetten.tar.gz")
    assert staged.exists()

    desktop.post(url, {"step": "confirm", "archive": "upload"})

    assert not staged.exists()
    # No folder chosen: the state before went next to the administration.
    assert len(list((data_dir.parent / "Huismus back-ups").iterdir())) == 1


def test_while_restoring_every_page_says_to_wait(desktop):
    from huismus.core import maintenance

    with maintenance.gate.exclusive(timeout=0):
        response = desktop.get("/")
    assert response.status_code == 503
    assert "Huismus zet een back-up terug" in response.content.decode()
    assert desktop.get("/").status_code != 503


def test_a_failed_backup_goes_above_the_kor_banner_the_others_below(desktop, drive):
    kor = {"level": "near", "percent": 90, "bar_percent": 90, "revenue_cents": 1, "limit_cents": 1}
    with patch("huismus.core.views.kor_limit_status", return_value=kor):
        page = _overview(desktop)
        assert page.index('id="kor-melding"') < page.index('id="back-upmelding"')

        backups.choose_folder(drive)
        drive.rmdir()
        backups.make_backup()
        page = _overview(desktop)
        assert page.index('id="back-upmelding"') < page.index('id="kor-melding"')


def test_the_backups_page_says_when_the_folder_is_gone_now(desktop, drive):
    backups.choose_folder(drive)
    backups.make_backup()
    for archive in drive.iterdir():
        archive.unlink()
    drive.rmdir()  # after today's backup: the overview waits for the next attempt

    page = desktop.get(reverse("business:backups_folder")).content.decode()
    assert 'id="map-weg"' in page and "is nu niet bereikbaar" in page
    overview = desktop.get(reverse("business:backups")).content.decode()
    assert "is nu niet bereikbaar" in overview.split('id="plek-map"')[1]
