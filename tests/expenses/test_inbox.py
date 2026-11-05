# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The receipts folder (SPEC.md M20): Huismus fetches new receipts from a
folder into the tray, never twice, and never removes a file from the
folder before it is in Huismus."""

import email.utils
import hashlib
import os
import time
from io import BytesIO
from pathlib import Path

import pytest
from django.utils import timezone, translation
from PIL import Image

from huismus.core import cloud_backups
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME
from huismus.core.models import Attachment
from huismus.expenses import inbox
from huismus.expenses.models import Expense
from tests.cloud_fakes import ADDRESS, PASSWORD, USERNAME, FakeDropbox, FakeWebDAV

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


def _jpg() -> bytes:
    out = BytesIO()
    Image.new("RGB", (4, 4), "white").save(out, "JPEG")
    return out.getvalue()


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    return settings.DATA_DIR


@pytest.fixture(autouse=True)
def settled(monkeypatch):
    # A file written by a test is seconds old; the minute's wait is
    # tested on its own below.
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)


@pytest.fixture
def folder(data_dir, tmp_path):
    folder = tmp_path / "iCloud Drive" / "Huismus bonnetjes"
    folder.mkdir(parents=True)
    inbox.choose_folder(folder)
    return folder


def test_nothing_happens_without_a_receipts_folder(data_dir):
    assert inbox.fetch() is None
    assert not Attachment.objects.exists()


def test_a_new_receipt_goes_to_the_tray_and_moves_to_fetched(folder):
    (folder / "tankstation.pdf").write_bytes(PDF)

    result = inbox.fetch()

    assert result.fetched == 1
    receipt = Attachment.objects.in_tray().get()
    assert receipt.kind == "receipt"
    assert receipt.source == inbox.SOURCE
    assert receipt.filename == "tankstation.pdf"
    assert receipt.sha256 == hashlib.sha256(PDF).hexdigest()
    assert receipt.file.read() == PDF
    assert not (folder / "tankstation.pdf").exists()
    assert (folder / "Opgehaald" / "tankstation.pdf").read_bytes() == PDF
    assert inbox.load().last_check


def test_a_photo_is_a_receipt_too(folder):
    (folder / "lunch.JPG").write_bytes(_jpg())
    assert inbox.fetch().fetched == 1


def test_the_same_receipt_twice_is_fetched_once(folder):
    (folder / "bon.pdf").write_bytes(PDF)
    inbox.fetch()
    (folder / "bon nog een keer.pdf").write_bytes(PDF)

    result = inbox.fetch()

    assert result.fetched == 0
    assert Attachment.objects.count() == 1
    # It is in Huismus, so it may leave the folder too.
    assert (folder / "Opgehaald" / "bon nog een keer.pdf").exists()


def test_a_receipt_already_on_an_expense_is_not_fetched_again(folder):
    expense = Expense.objects.create(date="2026-11-05", amount_cents=500)
    Attachment.objects.create(
        expense=expense, file=_content("bon.pdf"), kind="receipt", sha256=_sha(PDF)
    )
    (folder / "bon.pdf").write_bytes(PDF)

    assert inbox.fetch().fetched == 0
    assert not Attachment.objects.in_tray().exists()


def test_a_name_taken_in_fetched_gets_a_number(folder):
    (folder / "Opgehaald").mkdir()
    (folder / "Opgehaald" / "bon.pdf").write_bytes(b"%PDF-1.4 ouder")
    (folder / "bon.pdf").write_bytes(PDF)

    inbox.fetch()

    assert (folder / "Opgehaald" / "bon.pdf").read_bytes() == b"%PDF-1.4 ouder"
    assert (folder / "Opgehaald" / "bon-2.pdf").read_bytes() == PDF


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("foto.heic", b"....ftypheic", inbox.WRONG_TYPE),
        ("kapot.jpg", b"geen foto", inbox.DAMAGED),
        ("nep.pdf", b"geen pdf", inbox.DAMAGED),
    ],
)
def test_a_file_that_is_no_receipt_stays_in_the_folder(folder, name, content, reason):
    (folder / name).write_bytes(content)

    result = inbox.fetch()

    assert result.fetched == 0
    assert not Attachment.objects.exists()
    assert (folder / name).exists()
    assert inbox.load().skipped == [{"name": name, "reason": reason}]


def test_a_file_that_is_too_big_stays_in_the_folder(folder, monkeypatch):
    monkeypatch.setattr(inbox, "MAX_RECEIPT_BYTES", 10)
    (folder / "groot.pdf").write_bytes(PDF)

    inbox.fetch()

    assert (folder / "groot.pdf").exists()
    assert inbox.load().skipped == [{"name": "groot.pdf", "reason": inbox.TOO_BIG}]


def test_a_skipped_file_is_tried_again_and_forgotten_once_fetched(folder):
    # A photo that was still syncing: half a file the first time.
    (folder / "bon.jpg").write_bytes(_jpg()[:20])
    inbox.fetch()
    (folder / "bon.jpg").write_bytes(_jpg())

    assert inbox.fetch().fetched == 1
    assert inbox.load().skipped == []


def test_hidden_files_and_folders_are_left_alone(folder):
    # iCloud's placeholder for a file not downloaded yet, and macOS's own.
    (folder / ".bon.pdf.icloud").write_bytes(b"x")
    (folder / ".DS_Store").write_bytes(b"x")
    (folder / "Oud").mkdir()

    result = inbox.fetch()

    assert result.fetched == 0
    assert inbox.load().skipped == []
    assert (folder / ".bon.pdf.icloud").exists()


def test_a_folder_that_is_gone_is_a_failure_and_fetches_nothing(folder):
    folder.rename(folder.with_name("weg"))

    assert inbox.fetch() is None

    status = inbox.load()
    assert status.failed
    assert status.failure_reason == inbox.UNREACHABLE


def test_a_look_that_works_clears_the_failure(folder):
    folder.rename(folder.with_name("weg"))
    inbox.fetch()
    folder.with_name("weg").rename(folder)

    inbox.fetch()

    assert not inbox.load().failed


def test_if_saving_in_huismus_fails_the_file_stays_in_the_folder(folder, monkeypatch):
    (folder / "bon.pdf").write_bytes(PDF)

    def broken(*args, **kwargs):
        raise OSError("schijf vol")

    monkeypatch.setattr(inbox, "_store", broken)

    assert inbox.fetch() is None
    assert (folder / "bon.pdf").exists()
    assert not (folder / "Opgehaald").exists()


def test_if_moving_fails_the_next_look_moves_it_without_fetching_again(folder, monkeypatch):
    (folder / "bon.pdf").write_bytes(PDF)
    real_done = inbox.LocalFolder.done

    def refuse(self, name):
        raise PermissionError("alleen-lezen")

    monkeypatch.setattr(inbox.LocalFolder, "done", refuse)
    inbox.fetch()
    assert (folder / "bon.pdf").exists()

    monkeypatch.setattr(inbox.LocalFolder, "done", real_done)
    inbox.fetch()

    assert Attachment.objects.count() == 1
    assert (folder / "Opgehaald" / "bon.pdf").exists()


def test_nothing_is_fetched_with_the_sample_data(folder, data_dir):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"x")
    (folder / "bon.pdf").write_bytes(PDF)

    assert inbox.fetch() is None
    assert (folder / "bon.pdf").exists()


def test_turning_it_off_forgets_the_folder_but_keeps_the_tray(folder):
    (folder / "bon.pdf").write_bytes(PDF)
    inbox.fetch()

    inbox.turn_off()

    assert inbox.load().source == ""
    assert Attachment.objects.in_tray().count() == 1


def test_a_symlink_in_the_folder_is_not_followed(folder, tmp_path):
    elsewhere = tmp_path / "elders.pdf"
    elsewhere.write_bytes(PDF)
    (folder / "link.pdf").symlink_to(elsewhere)

    assert inbox.fetch().fetched == 0
    assert elsewhere.exists()
    assert (folder / "link.pdf").is_symlink()


def test_a_failed_look_forgets_what_was_skipped(folder):
    (folder / "foto.heic").write_bytes(b"heic")
    inbox.fetch()
    folder.rename(folder.with_name("weg"))

    inbox.fetch()

    assert inbox.load().skipped == []


def test_the_folder_that_is_gone_is_named(folder):
    folder.rename(folder.with_name("weg"))
    inbox.fetch()

    assert str(folder) in inbox.failure_sentence(inbox.load())


def test_a_disk_problem_in_huismus_is_not_blamed_on_the_folder(folder, monkeypatch):
    (folder / "bon.pdf").write_bytes(PDF)

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(inbox, "_store", full)
    inbox.fetch()

    assert inbox.load().failure_reason == inbox.STORAGE
    assert "Huismus kon een bonnetje niet bewaren" in inbox.failure_sentence(inbox.load())


def test_is_due_every_few_minutes(folder):
    assert inbox.is_due()
    inbox.fetch()
    assert not inbox.is_due()


# -- Dropbox ------------------------------------------------------------------


@pytest.fixture
def dropbox(data_dir, monkeypatch):
    fake = FakeDropbox()
    fake.install(monkeypatch)
    cloud_backups.link_dropbox("refresh-1")
    inbox.choose_dropbox()
    return fake


def test_dropbox_receipts_come_from_the_bonnetjes_folder(dropbox):
    dropbox.files["Bonnetjes/bon.pdf"] = PDF
    # A backup in the same app folder is no receipt.
    dropbox.files["huismus-backup-20261105-120000.tar.gz.age"] = b"age"

    result = inbox.fetch()

    assert result.fetched == 1
    assert Attachment.objects.in_tray().get().file.read() == PDF
    assert "Bonnetjes/bon.pdf" not in dropbox.files
    assert dropbox.files["Bonnetjes/Opgehaald/bon.pdf"] == PDF
    assert "huismus-backup-20261105-120000.tar.gz.age" in dropbox.files


def test_dropbox_makes_the_bonnetjes_folder_again_if_it_was_removed(dropbox):
    dropbox.folders.clear()
    assert inbox.fetch().fetched == 0
    assert "Bonnetjes" in dropbox.folders


def test_dropbox_unlinked_is_a_failure(dropbox):
    dropbox.refresh_tokens.clear()

    assert inbox.fetch() is None
    assert inbox.load().failure_reason == cloud_backups.REFUSED


def test_dropbox_is_no_choice_without_a_link(data_dir):
    with pytest.raises(inbox.FolderError):
        inbox.choose_dropbox()


def test_unlinking_dropbox_turns_the_receipts_folder_off(dropbox):
    cloud_backups.unlink()
    dropbox.files["Bonnetjes/bon.pdf"] = PDF

    assert not inbox.is_on()
    assert inbox.fetch() is None
    assert not inbox.load().failed


def test_linking_dropbox_again_leaves_it_off(dropbox):
    cloud_backups.unlink()
    inbox.cloud_unlinked()
    cloud_backups.link_dropbox("refresh-1")

    assert not inbox.is_on()


def test_at_start_it_looks_even_within_ten_minutes(folder):
    inbox.fetch()
    (folder / "bon.pdf").write_bytes(PDF)

    assert inbox.fetch_if_due() is None
    assert inbox.fetch_if_due(at_start=True).fetched == 1


def test_the_backups_leave_the_bonnetjes_folder_alone(dropbox, monkeypatch):
    """Backups and receipts share Apps › Huismus: listing and the keeping
    rule only ever see Huismus's own backup files."""
    old = "huismus-backup-20200101-120000.tar.gz.age"
    dropbox.files["Bonnetjes/" + old] = b"geen back-up"
    dropbox.files["Bonnetjes/Opgehaald/bon.pdf"] = PDF

    assert cloud_backups.archives() == []
    cloud_backups.prune(cloud_backups.remote(), timezone.now())

    assert "Bonnetjes/" + old in dropbox.files
    assert "Bonnetjes/Opgehaald/bon.pdf" in dropbox.files


def test_a_file_still_syncing_waits_for_the_next_look(folder, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 60)
    (folder / "bon.pdf").write_bytes(PDF)

    assert inbox.fetch().fetched == 0
    assert inbox.load().skipped == []

    old = time.time() - 120
    os.utime(folder / "bon.pdf", (old, old))
    assert inbox.fetch().fetched == 1


def test_the_folder_names_stay_after_switching_language(folder):
    with translation.override("en"):
        inbox.choose_folder(folder)
    (folder / "bon.pdf").write_bytes(PDF)

    with translation.override("nl"):
        inbox.fetch()

    assert (folder / "Picked up" / "bon.pdf").exists()


def test_dropbox_folder_name_follows_the_language_when_set_up(data_dir, monkeypatch):
    fake = FakeDropbox()
    fake.install(monkeypatch)
    cloud_backups.link_dropbox("refresh-1")
    with translation.override("en"):
        inbox.choose_dropbox()

    assert "Receipts" in fake.folders
    assert inbox.place() == "Dropbox › Apps › Huismus › Receipts"


def test_choosing_dropbox_makes_the_folder_at_once(dropbox):
    assert "Bonnetjes" in dropbox.folders


def test_fetching_now_runs_in_the_background(folder, monkeypatch):
    started = []
    monkeypatch.setattr(inbox, "_start", started.append)
    (folder / "bon.pdf").write_bytes(PDF)

    assert inbox.fetch_in_background()
    assert inbox.fetching()
    # A second click starts nothing new.
    assert inbox.fetch_in_background()
    assert len(started) == 1

    started[0]()

    assert not inbox.fetching()
    assert Attachment.objects.in_tray().count() == 1


# -- WebDAV -------------------------------------------------------------------


@pytest.fixture
def webdav(data_dir, monkeypatch):
    fake = FakeWebDAV()
    fake.install(monkeypatch)
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    inbox.choose_webdav()
    yield fake
    fake.close()


def test_choosing_webdav_makes_the_folder_next_to_the_backups(webdav):
    assert {"Huismus", "Huismus/Bonnetjes"} <= webdav.folders
    assert inbox.place() == "https://dav.test/remote.php/dav/files/sanne › Huismus › Bonnetjes"


def test_webdav_receipts_come_from_the_bonnetjes_folder(webdav):
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    webdav.files["Huismus/Bonnetjes/foto bon.jpg"] = _jpg()
    # A backup next to it is no receipt, and a folder in it is no file.
    webdav.files["Huismus/huismus-backup-20261105-120000.tar.gz.age"] = b"age"
    webdav.folders.add("Huismus/Bonnetjes/Oud")

    result = inbox.fetch()

    assert result.fetched == 2
    assert result.skipped == []
    assert Attachment.objects.in_tray().count() == 2
    assert webdav.files["Huismus/Bonnetjes/Opgehaald/bon.pdf"] == PDF
    assert "Huismus/Bonnetjes/Opgehaald/foto bon.jpg" in webdav.files
    assert "Huismus/Bonnetjes/bon.pdf" not in webdav.files
    assert "Huismus/huismus-backup-20261105-120000.tar.gz.age" in webdav.files


def test_webdav_a_name_taken_in_fetched_gets_a_number(webdav):
    webdav.folders.add("Huismus/Bonnetjes/Opgehaald")
    webdav.files["Huismus/Bonnetjes/Opgehaald/bon.pdf"] = b"%PDF-1.4\n% een ouder bonnetje\n"
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF

    assert inbox.fetch().fetched == 1

    assert webdav.files["Huismus/Bonnetjes/Opgehaald/bon.pdf"] != PDF
    assert webdav.files["Huismus/Bonnetjes/Opgehaald/bon-2.pdf"] == PDF


def test_webdav_the_same_receipt_twice_is_only_moved(webdav):
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    inbox.fetch()
    webdav.files["Huismus/Bonnetjes/nog een keer.pdf"] = PDF

    assert inbox.fetch().fetched == 0
    assert Attachment.objects.in_tray().count() == 1
    assert "Huismus/Bonnetjes/Opgehaald/nog een keer.pdf" in webdav.files


def test_webdav_a_file_that_is_no_receipt_stays(webdav):
    webdav.files["Huismus/Bonnetjes/foto.heic"] = b"heic"

    result = inbox.fetch()

    assert result.skipped == [{"name": "foto.heic", "reason": inbox.WRONG_TYPE}]
    assert "Huismus/Bonnetjes/foto.heic" in webdav.files


def test_webdav_a_file_still_being_written_waits_for_the_next_look(webdav, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 60)
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    webdav.modified["Huismus/Bonnetjes/bon.pdf"] = email.utils.format_datetime(
        timezone.now(), usegmt=True
    )

    assert inbox.fetch().fetched == 0
    assert inbox.load().skipped == []
    assert "Huismus/Bonnetjes/bon.pdf" in webdav.files

    webdav.modified["Huismus/Bonnetjes/bon.pdf"] = "Thu, 05 Nov 2026 08:00:00 GMT"
    assert inbox.fetch().fetched == 1


def test_webdav_a_time_without_a_zone_is_read_as_utc(webdav, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 60)
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    webdav.modified["Huismus/Bonnetjes/bon.pdf"] = "Thu, 05 Nov 2026 08:00:00 -0000"

    assert inbox.fetch().fetched == 1


def test_webdav_without_a_time_does_not_wait(webdav, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 60)
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    webdav.modified["Huismus/Bonnetjes/bon.pdf"] = "gisteren"

    assert inbox.fetch().fetched == 1


def test_webdav_hidden_files_are_left_alone(webdav):
    webdav.files["Huismus/Bonnetjes/.bon.pdf"] = PDF

    assert inbox.fetch().fetched == 0
    assert inbox.load().skipped == []
    assert "Huismus/Bonnetjes/.bon.pdf" in webdav.files


def test_webdav_makes_the_folders_again_if_they_were_removed(webdav):
    webdav.folders.clear()

    assert inbox.fetch().fetched == 0
    assert {"Huismus", "Huismus/Bonnetjes"} <= webdav.folders


def test_webdav_a_refused_password_is_a_failure(webdav):
    webdav.password = "ingetrokken"
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF

    assert inbox.fetch() is None

    status = inbox.load()
    assert status.failed
    assert status.failure_reason == cloud_backups.REFUSED
    assert "WebDAV" in inbox.failure_sentence(status)
    assert not Attachment.objects.exists()


def test_webdav_unreachable_is_a_failure(webdav):
    webdav.close()

    assert inbox.fetch() is None
    assert inbox.failure_sentence(inbox.load()) == "Huismus kon WebDAV niet bereiken."


def test_webdav_if_moving_fails_the_next_look_moves_it(webdav, monkeypatch):
    webdav.files["Huismus/Bonnetjes/bon.pdf"] = PDF
    real_move = cloud_backups.WebDAV.move

    def refused(self, source, destination):
        raise cloud_backups.CloudError(cloud_backups.OTHER, "MOVE 500")

    monkeypatch.setattr(cloud_backups.WebDAV, "move", refused)
    assert inbox.fetch().fetched == 1
    assert "Huismus/Bonnetjes/bon.pdf" in webdav.files

    monkeypatch.setattr(cloud_backups.WebDAV, "move", real_move)
    assert inbox.fetch().fetched == 0
    assert "Huismus/Bonnetjes/Opgehaald/bon.pdf" in webdav.files
    assert Attachment.objects.count() == 1


def test_webdav_is_no_choice_without_it_set_up(data_dir):
    with pytest.raises(inbox.FolderError):
        inbox.choose_webdav()


def test_unlinking_webdav_turns_the_receipts_folder_off(webdav):
    cloud_backups.unlink()
    inbox.cloud_unlinked()
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)

    assert not inbox.is_on()
    assert inbox.load().source == ""


def test_webdav_is_off_while_dropbox_is_linked_instead(webdav):
    cloud_backups.unlink()
    cloud_backups.link_dropbox("refresh-1")

    assert not inbox.is_on()


def test_the_backups_leave_the_webdav_bonnetjes_folder_alone(webdav):
    webdav.files["Huismus/Bonnetjes/Opgehaald/bon.pdf"] = PDF

    assert cloud_backups.archives() == []
    cloud_backups.prune(cloud_backups.remote(), timezone.now())

    assert "Huismus/Bonnetjes/Opgehaald/bon.pdf" in webdav.files


def test_webdav_folder_name_follows_the_language_when_set_up(webdav):
    with translation.override("en"):
        inbox.choose_webdav()
    webdav.files["Huismus/Receipts/bon.pdf"] = PDF

    with translation.override("nl"):
        inbox.fetch()

    assert inbox.place().endswith("› Huismus › Receipts")
    assert "Huismus/Receipts/Picked up/bon.pdf" in webdav.files


def _content(name):
    from django.core.files.base import ContentFile

    return ContentFile(PDF, name=name)


def _sha(data):
    return hashlib.sha256(data).hexdigest()


def test_status_file_is_in_the_data_dir(folder, data_dir):
    assert (Path(data_dir) / "receipts-folder.json").exists()
