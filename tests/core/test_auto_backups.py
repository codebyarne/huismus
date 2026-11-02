# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Daily backups in the desktop app (SPEC.md M11, huismus/core/auto_backups.py).
On Docker: tests/core/test_docker_backups.py."""

import errno
import shutil
import sqlite3
import tarfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from django.db import connections
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.core import auto_backups as backups
from huismus.core import maintenance
from huismus.core.backup import STATUS_FILE_NAME, create_backup

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def desktop(settings):
    settings.DESKTOP = True


def _at(*args) -> datetime:
    return timezone.make_aware(datetime(*args))


@pytest.fixture
def data_dir(settings, tmp_path):
    data = tmp_path / "Huismus"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def folder(data_dir, tmp_path):
    (tmp_path / "iCloud").mkdir()
    chosen = backups.check_folder(str(tmp_path / "iCloud" / "Huismus"))
    backups.choose_folder(chosen)
    return chosen


def _archive(folder: Path, when: datetime) -> Path:
    path = folder / f"huismus-backup-{when:%Y%m%d-%H%M%S}.tar.gz"
    path.write_bytes(b"")
    return path


# -- Choosing a folder ------------------------------------------------------


def test_choosing_a_folder_creates_only_its_last_part(data_dir, tmp_path):
    (tmp_path / "iCloud").mkdir()
    chosen = backups.check_folder(str(tmp_path / "iCloud" / "Huismus"))
    backups.choose_folder(chosen)

    assert chosen.is_dir()
    assert backups.chosen_folder() == chosen


def test_a_folder_on_a_missing_drive_is_refused(data_dir, tmp_path):
    with pytest.raises(backups.FolderError, match="bestaat niet"):
        backups.check_folder(str(tmp_path / "USB-stick" / "Huismus"))
    assert not (tmp_path / "USB-stick").exists()


@pytest.mark.parametrize("where", ["data", "data/backups", "."])
def test_the_live_database_never_goes_into_the_folder(data_dir, where):
    # The administration itself, a folder in it, or a folder holding it.
    target = data_dir if where == "data" else data_dir / "backups"
    if where == ".":
        target = data_dir.parent
    with pytest.raises(backups.FolderError, match="buiten je administratie"):
        backups.check_folder(str(target))


def test_on_windows_the_suggestions_are_where_the_sync_apps_put_them(tmp_path, monkeypatch):
    monkeypatch.setattr("sys.platform", "win32")
    home = tmp_path / "jan"
    (home / "OneDrive").mkdir(parents=True)
    (home / "OneDrive - Bedrijf").mkdir()
    (home / "iCloudDrive").mkdir()
    (home / "Dropbox").mkdir()
    google = tmp_path / "G"
    (google / "Mijn Drive").mkdir(parents=True)
    monkeypatch.setattr(backups, "GOOGLE_DRIVE_ON_WINDOWS", google)

    found = backups.suggestions(home)

    assert [name for name, _path in found] == [
        "OneDrive",
        "OneDrive - Bedrijf",
        "iCloud Drive",
        "Google Drive",
        "Dropbox",
    ]
    assert found[3][1] == google / "Mijn Drive" / "Huismus"


def test_a_relative_path_or_nothing_is_refused(data_dir):
    with pytest.raises(backups.FolderError):
        backups.check_folder("")
    with pytest.raises(backups.FolderError, match="hele pad"):
        backups.check_folder("Huismus")


def test_suggestions_are_the_sync_folders_found(tmp_path):
    home = tmp_path
    (home / "Library" / "Mobile Documents" / "com~apple~CloudDocs").mkdir(parents=True)
    (home / "Library" / "CloudStorage" / "GoogleDrive-a@example.org" / "My Drive").mkdir(
        parents=True
    )
    (home / "Library" / "CloudStorage" / "OneDrive-Persoonlijk").mkdir(parents=True)

    found = backups.suggestions(home)

    assert [name for name, _path in found] == ["iCloud Drive", "Google Drive", "OneDrive"]
    assert all(path.name == "Huismus" for _name, path in found)
    assert backups.suggestions(tmp_path / "leeg") == []


def test_two_backups_in_one_second_both_stay(folder):
    with patch("huismus.core.backup.timezone.localtime", return_value=_at(2026, 10, 29, 9, 12)):
        first, second = create_backup(folder), create_backup(folder)
    assert first != second and first.exists() and second.exists()
    assert backups.ARCHIVE_NAME.match(second.name)


def test_the_status_is_not_in_a_backup(folder, data_dir):
    archive = create_backup(folder)

    with tarfile.open(archive) as tar:
        assert STATUS_FILE_NAME not in tar.getnames()


# -- Daily backups ----------------------------------------------------------


def test_a_backup_is_due_once_a_day(folder):
    morning = _at(2026, 10, 29, 9, 12)
    assert backups.is_due(morning)

    assert backups.run_if_due(morning) is not None
    assert not backups.is_due(morning + timedelta(hours=5))
    assert backups.run_if_due(morning + timedelta(hours=5)) is None
    assert backups.is_due(morning + timedelta(days=1))
    assert len(list(folder.glob("huismus-backup-*.tar.gz"))) == 1


def test_no_folder_no_backup(data_dir):
    assert not backups.is_due()
    assert backups.run_if_due() is None


def test_no_backup_while_restoring(folder):
    with maintenance.gate.exclusive(timeout=0):
        assert backups.run_if_due() is None
    assert backups.run_if_due() is not None


def test_an_unreachable_folder_is_recorded_and_tried_again(folder):
    folder.rmdir()  # the USB drive is gone
    now = _at(2026, 10, 29, 9, 0)

    assert backups.run_if_due(now) is None
    status = backups.load_status()
    assert status.failed and status.failure_reason == backups.UNREACHABLE
    assert not folder.exists()  # not quietly created again

    folder.mkdir()
    assert backups.run_if_due(now + timedelta(hours=1)) is not None
    assert not backups.load_status().failed


def test_a_full_folder_is_recorded_and_leaves_no_half_archive(folder):
    with patch("huismus.core.backup._write_archive") as write:

        def full(path, *args):
            path.write_bytes(b"half")
            raise OSError(errno.ENOSPC, "No space left on device")

        write.side_effect = full
        assert backups.make_backup() is None

    assert backups.load_status().failure_reason == backups.FULL
    assert list(folder.iterdir()) == []


def test_a_damaged_snapshot_is_a_failure_too(folder):
    with patch(
        "huismus.core.backup._write_archive", side_effect=sqlite3.DatabaseError("malformed")
    ):
        assert backups.make_backup() is None

    status = backups.load_status()
    assert status.failed and status.failure_reason == backups.OTHER


# -- Keeping and removing ---------------------------------------------------


def test_prune_keeps_30_days_then_one_a_month(folder):
    now = _at(2026, 10, 29, 9, 0)
    naive = datetime(2026, 10, 29, 9, 0)
    recent = [_archive(folder, naive - timedelta(days=d)) for d in range(0, 30)]
    extra_today = _archive(folder, naive - timedelta(hours=2))  # before a restore
    september_old = [_archive(folder, datetime(2026, 9, d, 9, 0)) for d in (1, 15, 28)]
    august = [_archive(folder, datetime(2026, 8, d, 9, 0)) for d in (3, 30)]
    someone_elses = folder / "notities.txt"
    someone_elses.write_text("van mij")

    removed = backups.prune(folder, now)

    assert all(path.exists() for path in recent) and extra_today.exists()
    # Older than 30 days: the newest of each month stays.
    assert september_old[2].exists()
    assert not september_old[0].exists() and not september_old[1].exists()
    assert august[1].exists() and not august[0].exists()
    assert someone_elses.exists()
    assert sorted(removed) == sorted([*september_old[:2], august[0]])


def test_prune_counts_the_newest_for_its_month(folder):
    newest = _archive(folder, datetime(2026, 1, 20, 9, 0))
    same_month = _archive(folder, datetime(2026, 1, 5, 9, 0))

    backups.prune(folder, _at(2026, 10, 29))

    assert newest.exists() and not same_month.exists()


def test_prune_always_keeps_the_newest(folder):
    only = _archive(folder, datetime(2024, 1, 1, 9, 0))
    old = _archive(folder, datetime(2023, 12, 31, 9, 0))
    older = _archive(folder, datetime(2023, 12, 1, 9, 0))

    backups.prune(folder, _at(2026, 10, 29))

    assert only.exists() and old.exists() and not older.exists()


# -- The overview's warning -------------------------------------------------


def test_warning_without_a_folder(data_dir):
    assert backups.warning()["kind"] == "none"


def test_no_warning_after_a_recent_backup(folder):
    now = _at(2026, 10, 29, 9, 0)
    backups.make_backup(now)
    assert backups.warning(now + timedelta(days=7)) is None
    assert backups.warning(now + timedelta(days=7, minutes=1))["kind"] == "old"


def test_a_failure_goes_before_everything_else(folder):
    now = _at(2026, 10, 29, 9, 0)
    backups.make_backup(now - timedelta(days=10))
    shutil.rmtree(folder)
    backups.make_backup(now)

    warning = backups.warning(now)
    assert warning["kind"] == "failed" and warning["level"] == "bad"
    assert warning["reason"] == backups.UNREACHABLE


# -- Restoring --------------------------------------------------------------


@pytest.mark.django_db(transaction=True)
def test_restore_backs_up_the_current_state_first(folder, data_dir):
    Contact.objects.create(company_name="Oud BV")
    old = backups.make_backup()
    Contact.objects.create(company_name="Nieuw BV")

    before = backups.restore(old)

    assert before.parent == folder and before != old
    # restore_backup puts the database in DATA_DIR, which the test's
    # database isn't in: read the restored file itself.
    restored = sqlite3.connect(data_dir / Path(connections["default"].settings_dict["NAME"]).name)
    names = restored.execute("SELECT company_name FROM contacts_contact").fetchall()
    restored.close()
    assert names == [("Oud BV",)]
    assert backups.chosen_folder() == folder  # the status is this computer's


@pytest.mark.django_db(transaction=True)
def test_restore_without_a_folder_keeps_the_state_before_next_to_the_data(data_dir, tmp_path):
    archive = create_backup(tmp_path / "van-de-pi")

    before = backups.restore(archive)

    assert before.parent == data_dir.parent / "Huismus back-ups"
    assert [a.path for a in backups.archives()] == [before]


def test_restore_waits_for_running_requests(folder):
    finished = threading.Event()
    order = []

    def slow_request():
        with maintenance.gate.request():
            finished.wait(5)
            order.append("request")

    other = threading.Thread(target=slow_request)
    with maintenance.gate.request():  # the restoring request itself
        other.start()
        while maintenance.gate._running < 2:
            pass
        threading.Timer(0.2, finished.set).start()
        with maintenance.gate.exclusive(timeout=5):
            order.append("restore")
            with maintenance.gate.request() as open_:
                assert not open_
    other.join()
    assert order == ["request", "restore"]


@pytest.mark.django_db(transaction=True)
def test_no_restore_without_the_backup_of_the_state_before(folder):
    archive = backups.make_backup()
    with (
        patch("huismus.core.auto_backups.create_backup", side_effect=OSError(errno.ENOSPC, "vol")),
        patch("huismus.core.auto_backups.restore_backup") as restore_backup,
    ):
        with pytest.raises(backups.RestoreError, match="Er is niets teruggezet"):
            backups.restore(archive)
    restore_backup.assert_not_called()
    assert not maintenance.gate._closed


@pytest.mark.django_db(transaction=True)
def test_a_restored_database_without_the_triggers_is_put_back(folder):
    archive = backups.make_backup()
    with (
        patch(
            "huismus.core.auto_backups._triggers",
            side_effect=[{("immutable", "CREATE TRIGGER immutable ...")}, set(), set()],
        ),
        patch("huismus.core.auto_backups.restore_backup") as restore_backup,
    ):
        with pytest.raises(backups.RestoreError, match="bescherming van uitgegeven documenten"):
            backups.restore(archive)
    restored = [call.args[0] for call in restore_backup.call_args_list]
    assert restored[0] == archive and restored[1] != archive  # then the state before


@pytest.mark.django_db(transaction=True)
def test_a_trigger_with_the_right_name_but_an_empty_body_is_refused(folder):
    # A database that says it protects issued documents but doesn't
    # (CLAUDE.md rule 2): the same trigger name with a harmless body.
    archive = backups.make_backup()
    real = backups._triggers()
    name, sql = sorted(real)[0]
    emptied = (real - {(name, sql)}) | {(name, f'CREATE TRIGGER "{name}" WHEN 0 ...')}
    with (
        patch("huismus.core.auto_backups._triggers", side_effect=[real, emptied, emptied]),
        patch("huismus.core.auto_backups.restore_backup") as restore_backup,
    ):
        with pytest.raises(backups.RestoreError, match="bescherming van uitgegeven documenten"):
            backups.restore(archive)
    assert restore_backup.call_count == 2  # then the state before


def test_the_triggers_are_read_with_their_sql():
    triggers = backups._triggers()

    assert triggers and all(sql.upper().startswith("CREATE TRIGGER") for _name, sql in triggers)


def test_a_second_restore_at_the_same_time_is_refused():
    with maintenance.gate.exclusive(timeout=0):
        with pytest.raises(maintenance.Busy):
            with maintenance.gate.exclusive(timeout=0):
                pass


def test_requests_that_dont_finish_stop_the_restore_and_open_the_gate():
    with maintenance.gate.request(), maintenance.gate.request():
        with pytest.raises(maintenance.Busy):
            with maintenance.gate.exclusive(timeout=0.05):
                pass
        with maintenance.gate.request() as open_:
            assert open_


def test_a_sync_folder_is_named_after_its_service(data_dir, tmp_path, monkeypatch):
    home = tmp_path / "home"
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    icloud.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))

    assert backups.folder_label(icloud / "Huismus") == "iCloud Drive › Huismus"
    assert backups.folder_label(icloud / "Werk" / "Huismus") == "iCloud Drive › Werk › Huismus"
    assert backups.folder_label(tmp_path / "USB") == str(tmp_path / "USB")
    assert backups.folder_label(backups.fallback_folder()) == (
        "Huismus back-ups, naast je administratie"
    )
