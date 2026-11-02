# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Daily backups on Docker (SPEC.md M15, huismus/core/auto_backups.py): the linked
folder, refusing a folder inside the container, the hourly thread, and
the backup before a restore in data/backups. The pages: tests/core/
test_backup_views.py."""

import tarfile
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from huismus.core import auto_backups as backups
from huismus.core.backup import create_backup

pytestmark = pytest.mark.django_db

# A container: Docker's own files at "/", the data volume and a NAS share
# linked in. The fields are the kernel's (proc(5), mountinfo).
CONTAINER_MOUNTS = """\
640 520 0:57 / / rw,relatime master:1 - overlay overlay rw,lowerdir=/var/lib/docker/...
641 640 0:60 / /proc rw,nosuid - proc proc rw
650 640 179:2 /var/lib/docker/volumes/huismus-data/_data /app/data rw - ext4 /dev/root rw
651 640 0:70 /share/Huismus /backups rw - cifs //nas/share rw
652 640 0:71 / /mnt/usb\\040stick rw - vfat /dev/sda1 rw
"""


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DESKTOP = False
    data = tmp_path / "data"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def container(tmp_path, monkeypatch):
    mountinfo = tmp_path / "mountinfo"
    mountinfo.write_text(CONTAINER_MOUNTS)
    monkeypatch.setattr(backups, "MOUNTINFO", mountinfo)


@pytest.fixture
def linked(tmp_path, monkeypatch):
    folder = tmp_path / "backups"
    folder.mkdir()
    monkeypatch.setattr(backups, "LINKED_FOLDER", folder)
    return folder


def test_the_linked_folder_is_the_suggestion(data_dir, linked):
    assert backups.suggestions() == [("Gekoppelde map", linked)]


def test_no_linked_folder_no_suggestion(data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(backups, "LINKED_FOLDER", tmp_path / "niet-gekoppeld")

    assert backups.suggestions() == []


@pytest.mark.parametrize("path", ["/tmp/huismus", "/app/backups", "/root"])
def test_a_folder_inside_the_container_is_refused(container, path):
    assert backups._inside_container(Path(path))


@pytest.mark.parametrize("path", ["/backups", "/backups/Huismus", "/mnt/usb stick/Huismus"])
def test_a_linked_folder_is_not_inside_the_container(container, path):
    assert not backups._inside_container(Path(path))


def test_the_container_refusal_reaches_the_field(data_dir, monkeypatch, tmp_path):
    # check_folder resolves the path, so the mounts are this test's own.
    (tmp_path / "mountinfo").write_text(
        f"1 0 0:1 / / rw - overlay overlay rw\n2 1 0:2 / {data_dir} rw - ext4 /dev/root rw\n"
    )
    monkeypatch.setattr(backups, "MOUNTINFO", tmp_path / "mountinfo")

    with pytest.raises(backups.FolderError, match="is weg zodra"):
        backups.check_folder(str(tmp_path / "Huismus-back-ups"))


def test_outside_a_container_nothing_is_refused(data_dir, tmp_path, monkeypatch):
    # A server without Docker: "/" is a real disk.
    (tmp_path / "mountinfo").write_text("1 0 8:1 / / rw - ext4 /dev/sda1 rw\n")
    monkeypatch.setattr(backups, "MOUNTINFO", tmp_path / "mountinfo")

    assert backups.check_folder(str(tmp_path / "Huismus")) == tmp_path / "Huismus"


def test_unknown_mounts_refuse_nothing(data_dir, tmp_path, monkeypatch):
    monkeypatch.setattr(backups, "MOUNTINFO", tmp_path / "geen-proc")

    assert not backups._inside_container(Path("/tmp"))


def test_the_desktop_app_never_looks_at_mounts(settings, data_dir, tmp_path, monkeypatch):
    settings.DESKTOP = True
    (tmp_path / "mountinfo").write_text("1 0 0:1 / / rw - overlay overlay rw\n")
    monkeypatch.setattr(backups, "MOUNTINFO", tmp_path / "mountinfo")

    assert backups.check_folder(str(tmp_path / "Huismus")) == tmp_path / "Huismus"


def test_the_fallback_folder_is_in_the_volume_and_never_in_a_backup(data_dir, tmp_path):
    assert backups.fallback_folder() == data_dir / "backups"
    assert backups.folder_label(data_dir / "backups") == "Huismus back-ups, bij je administratie"

    (data_dir / "backups").mkdir()
    (data_dir / "backups" / "huismus-backup-20261001-030000.tar.gz").write_bytes(b"oud")
    backups.staged_upload().write_bytes(b"upload")
    archive = create_backup(tmp_path / "elders")

    with tarfile.open(archive) as tar:
        assert not [name for name in tar.getnames() if name.startswith("backups")]


@pytest.mark.django_db(transaction=True)
def test_restore_without_a_folder_keeps_the_state_before_in_the_volume(data_dir, tmp_path):
    archive = create_backup(tmp_path / "van-de-laptop")

    before = backups.restore(archive)

    assert before.parent == data_dir / "backups"
    assert before in [a.path for a in backups.archives()]


def test_the_hourly_thread_makes_the_daily_backup(data_dir):
    ran = threading.Event()

    def sleep(seconds):
        assert seconds == 60 * 60
        ran.set()
        threading.Event().wait()  # one round is enough

    with (
        patch.object(backups, "run_if_due") as run_if_due,
        patch.object(backups.time, "sleep", sleep),
    ):
        thread = backups.start_hourly_thread()
        assert ran.wait(5)

    assert thread.daemon
    run_if_due.assert_called_once_with()


def test_a_failing_round_does_not_stop_the_thread(data_dir):
    rounds = []
    second = threading.Event()

    def sleep(seconds):
        if len(rounds) == 2:
            second.set()
            threading.Event().wait()

    def run_if_due():
        rounds.append(1)
        raise OSError("schijf weg")

    with (
        patch.object(backups, "run_if_due", run_if_due),
        patch.object(backups.time, "sleep", sleep),
    ):
        backups.start_hourly_thread()
        assert second.wait(5)


def test_gunicorn_starts_the_thread_in_its_worker():
    import runpy

    config = runpy.run_path(str(Path(__file__).parents[2] / "gunicorn.conf.py"))
    with patch.object(backups, "start_hourly_thread") as start:
        config["post_worker_init"](worker=None)

    assert config["workers"] == 1
    assert config["timeout"] >= 300  # a backup or restore on a Pi
    start.assert_called_once_with()
