# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

pytestmark = pytest.mark.django_db


def test_backup_command_writes_an_archive_to_the_given_directory(tmp_path):
    call_command("backup", str(tmp_path / "out"))

    archives = list((tmp_path / "out").glob("huismus-backup-*.tar.gz"))
    assert len(archives) == 1


def test_restore_command_without_yes_refuses_and_changes_nothing(tmp_path):
    call_command("backup", str(tmp_path / "out"))
    archive = next((tmp_path / "out").glob("huismus-backup-*.tar.gz"))

    with pytest.raises(CommandError, match="--yes"):
        call_command("restore", str(archive))


def test_restore_command_rejects_a_missing_archive():
    with pytest.raises(CommandError, match="bestaat niet"):
        call_command("restore", "/tmp/does-not-exist-huismus.tar.gz", "--yes")


def test_restore_command_with_yes_restores(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "before"
    (tmp_path / "before").mkdir()
    call_command("backup", str(tmp_path / "out"))
    archive = next((tmp_path / "out").glob("huismus-backup-*.tar.gz"))

    settings.DATA_DIR = tmp_path / "after"
    (tmp_path / "after").mkdir()

    call_command("restore", str(archive), "--yes")

    assert any((tmp_path / "after").iterdir())


def test_restore_command_rejects_an_archive_without_a_database(tmp_path):
    import tarfile

    bogus = tmp_path / "not-a-backup.tar.gz"
    (tmp_path / "readme.txt").write_text("hello")
    with tarfile.open(bogus, "w:gz") as tar:
        tar.add(tmp_path / "readme.txt", arcname="readme.txt")

    with pytest.raises(CommandError, match="db.sqlite3"):
        call_command("restore", str(bogus), "--yes")
