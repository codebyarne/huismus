# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Looking sooner (SPEC.md M20): something new in the receipts folder
starts a look at once, next to the look every ten minutes. One round of the
watching thread at a time, so nothing sleeps here."""

import os
import time

import pytest

from huismus.core import cloud_backups, maintenance
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME
from huismus.core.models import Attachment
from huismus.expenses import inbox, watch
from tests.cloud_fakes import FakeDropbox

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    return settings.DATA_DIR


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)


@pytest.fixture
def folder(data_dir, tmp_path):
    folder = tmp_path / "iCloud Drive" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    inbox.choose_folder(folder)
    return folder


@pytest.fixture
def dropbox(data_dir, monkeypatch):
    fake = FakeDropbox()
    fake.install(monkeypatch)
    cloud_backups.link_dropbox("refresh-1")
    inbox.choose_dropbox()
    return fake


def longpolls(fake: FakeDropbox) -> int:
    return sum(call.endswith("/longpoll") for call in fake.calls)


# -- A folder -------------------------------------------------------------------


def test_a_new_file_in_the_folder_is_fetched_at_the_next_glance(folder):
    state = watch.Watch()
    assert watch.round_(state) == watch.FOLDER_SECONDS
    assert not Attachment.objects.exists()

    (folder / "bon.pdf").write_bytes(PDF)
    watch.round_(state)

    assert Attachment.objects.in_tray().get().filename == "bon.pdf"
    assert (folder / "Opgehaald" / "bon.pdf").exists()


def test_the_first_glance_only_remembers_what_is_there(folder):
    # The look at start, or after choosing the folder, takes those.
    (folder / "bon.pdf").write_bytes(PDF)

    watch.round_(watch.Watch())

    assert not Attachment.objects.exists()


def test_a_file_still_syncing_waits_for_its_minute(folder, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 60)
    state = watch.Watch()
    watch.round_(state)
    (folder / "bon.pdf").write_bytes(PDF)

    watch.round_(state)
    assert not Attachment.objects.exists()

    a_minute_ago = time.time() - 61
    os.utime(folder / "bon.pdf", (a_minute_ago, a_minute_ago))
    watch.round_(state)
    assert Attachment.objects.in_tray().count() == 1


def test_a_file_that_is_no_receipt_starts_one_look_not_one_every_glance(folder, monkeypatch):
    looks = []
    monkeypatch.setattr(inbox, "fetch_when_open", lambda: looks.append(1))
    state = watch.Watch()
    watch.round_(state)
    (folder / "notities.txt").write_text("geen bonnetje")

    for _ in range(3):
        watch.round_(state)

    assert looks == [1]


def test_hidden_files_start_no_look(folder, monkeypatch):
    # iCloud's ".bon.jpg.icloud" for a file not downloaded yet.
    looks = []
    monkeypatch.setattr(inbox, "fetch_when_open", lambda: looks.append(1))
    state = watch.Watch()
    watch.round_(state)
    (folder / ".bon.jpg.icloud").write_bytes(b"x")

    watch.round_(state)

    assert looks == []


def test_while_a_look_runs_the_next_glance_tries_again(folder, monkeypatch):
    looks = []
    monkeypatch.setattr(inbox, "fetch_when_open", lambda: looks.append(1))
    state = watch.Watch()
    watch.round_(state)
    (folder / "bon.pdf").write_bytes(PDF)

    monkeypatch.setattr(inbox, "fetching", lambda: True)
    watch.round_(state)
    assert looks == []

    monkeypatch.setattr(inbox, "fetching", lambda: False)
    watch.round_(state)
    assert looks == [1]


def test_a_folder_that_is_gone_starts_no_look(folder, monkeypatch):
    looks = []
    monkeypatch.setattr(inbox, "fetch_when_open", lambda: looks.append(1))
    state = watch.Watch()
    watch.round_(state)
    folder.rename(folder.with_name("weg"))

    assert watch.round_(state) == watch.FOLDER_SECONDS
    assert looks == []
    # Nothing red from the watching itself: the look every ten minutes says it.
    assert not inbox.load().failed


def test_no_look_while_a_backup_is_restored(folder):
    state = watch.Watch()
    watch.round_(state)
    (folder / "bon.pdf").write_bytes(PDF)

    with maintenance.gate.exclusive():
        watch.round_(state)

    assert not Attachment.objects.exists()
    assert (folder / "bon.pdf").exists()


def test_nothing_is_watched_with_the_sample_data(folder, data_dir):
    state = watch.Watch()
    watch.round_(state)
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")
    (folder / "bon.pdf").write_bytes(PDF)

    watch.round_(state)

    assert not Attachment.objects.exists()


def test_nothing_is_watched_when_off(data_dir):
    assert watch.round_(watch.Watch()) == watch.FOLDER_SECONDS


def test_another_folder_starts_over(folder, tmp_path):
    state = watch.Watch()
    watch.round_(state)
    other = tmp_path / "Dropbox" / "Huismus bonnetjes"
    other.mkdir(parents=True)
    (other / "bon.pdf").write_bytes(PDF)
    inbox.choose_folder(other)

    watch.round_(state)

    # Like a first glance: choosing it started its own look.
    assert not Attachment.objects.exists()


# -- Dropbox ------------------------------------------------------------------------


def test_a_receipt_in_dropbox_is_fetched_after_the_wait(dropbox):
    state = watch.Watch()
    assert watch.round_(state) == 0  # nothing changed: wait again at once
    assert not Attachment.objects.exists()

    dropbox.files["Bonnetjes/bon.pdf"] = PDF
    watch.round_(state)

    assert Attachment.objects.in_tray().get().filename == "bon.pdf"
    assert "Bonnetjes/Opgehaald/bon.pdf" in dropbox.files
    assert longpolls(dropbox) == 2


def looks(fake: FakeDropbox) -> int:
    return sum(call.endswith("files/list_folder") for call in fake.calls)


def test_the_looks_own_move_wakes_one_more_look_that_finds_nothing(dropbox):
    state = watch.Watch()
    watch.round_(state)
    before = looks(dropbox)
    dropbox.files["Bonnetjes/bon.pdf"] = PDF
    watch.round_(state)

    watch.round_(state)  # the move to Opgehaald
    assert Attachment.objects.count() == 1
    watch.round_(state)  # quiet now
    watch.round_(state)

    assert Attachment.objects.count() == 1
    assert looks(dropbox) - before == 2  # not one per wait


def test_the_wait_carries_no_token(dropbox):
    # FakeDropbox fails the test when it does.
    watch.round_(watch.Watch())


def test_dropbox_asking_to_back_off_is_honoured(dropbox):
    dropbox.longpoll_extra = {"backoff": 30}

    assert watch.round_(watch.Watch()) == 30


def test_a_failing_wait_waits_longer_each_time(dropbox, monkeypatch):
    def unreachable(request, timeout=None):
        raise cloud_backups.CloudError(cloud_backups.UNREACHABLE, "geen netwerk")

    monkeypatch.setattr(cloud_backups, "_open", unreachable)
    state = watch.Watch()

    pauses = [watch.round_(state) for _ in range(6)]

    assert pauses == [60, 120, 240, 480, 600, 600]
    assert not inbox.load().failed  # the look every ten minutes says it


def test_a_cursor_dropbox_forgot_gives_a_new_one(dropbox):
    state = watch.Watch()
    watch.round_(state)
    dropbox.cursors.clear()

    assert watch.round_(state) == watch.RETRY_SECONDS
    dropbox.files["Bonnetjes/bon.pdf"] = PDF
    watch.round_(state)  # a new cursor, after the receipt
    assert not Attachment.objects.exists()
    dropbox.files["Bonnetjes/bon2.pdf"] = PDF + b"2"
    watch.round_(state)

    assert Attachment.objects.count() == 2


def test_unlinking_dropbox_stops_the_wait(dropbox):
    state = watch.Watch()
    watch.round_(state)
    cloud_backups.unlink()
    before = longpolls(dropbox)

    watch.round_(state)

    assert longpolls(dropbox) == before


def test_a_wait_that_ends_after_turning_off_starts_no_look(dropbox, monkeypatch):
    state = watch.Watch()
    watch.round_(state)
    dropbox.files["Bonnetjes/bon.pdf"] = PDF
    wait = cloud_backups.Dropbox.wait_for_change

    def turned_off_meanwhile(self, cursor, seconds):
        answer = wait(self, cursor, seconds)
        inbox.turn_off()
        return answer

    monkeypatch.setattr(cloud_backups.Dropbox, "wait_for_change", turned_off_meanwhile)
    watch.round_(state)

    assert not Attachment.objects.exists()
