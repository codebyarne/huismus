# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""manage.py migrate_with_backup: on Docker a backup before a new version's
migrations (SPEC.md M15, docker/entrypoint.sh)."""

from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from huismus.core import auto_backups as backups
from huismus.core import updates
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME
from huismus.core.management.commands import migrate_with_backup

pytestmark = pytest.mark.django_db

COMMAND = "huismus.core.management.commands.migrate_with_backup"


@pytest.fixture
def data_dir(settings, tmp_path):
    settings.DESKTOP = False
    data = tmp_path / "data"
    data.mkdir()
    settings.DATA_DIR = data
    return data


@pytest.fixture
def new_version():
    """A new image: migrations it brings that this database lacks."""
    with patch(f"{COMMAND}.pending_migrations", return_value=["0042_iets_nieuws"]):
        yield


@pytest.fixture
def migrate():
    with patch(f"{COMMAND}.call_command") as migrate:
        yield migrate


def _archives(folder):
    return sorted(folder.glob("huismus-backup-*.tar.gz"))


def test_a_new_version_backs_up_first_then_migrates(data_dir, new_version, migrate):
    archives_when_migrating = []
    migrate.side_effect = lambda *args, **kwargs: archives_when_migrating.extend(
        _archives(data_dir / "backups")
    )

    call_command("migrate_with_backup")

    assert len(archives_when_migrating) == 1


def test_the_backup_goes_to_the_chosen_folder(data_dir, tmp_path, new_version, migrate):
    folder = tmp_path / "nas"
    folder.mkdir()
    backups.choose_folder(folder)

    call_command("migrate_with_backup")

    assert len(_archives(folder)) == 1
    assert not (data_dir / "backups").exists()


def test_the_log_says_the_version_and_where_the_backup_is(data_dir, new_version, migrate, capsys):
    call_command("migrate_with_backup")

    out = capsys.readouterr().out
    assert f"bijgewerkt naar {updates.current_version()}" in out
    assert str(_archives(data_dir / "backups")[0]) in out


def test_same_version_no_backup(data_dir, migrate):
    with patch(f"{COMMAND}.pending_migrations", return_value=[]):
        call_command("migrate_with_backup")

    assert not (data_dir / "backups").exists()
    migrate.assert_called_once()


def test_a_new_installation_no_backup(data_dir, new_version, migrate):
    with patch(f"{COMMAND}.has_administration", return_value=False):
        call_command("migrate_with_backup")

    assert not (data_dir / "backups").exists()
    migrate.assert_called_once()


def test_sample_data_no_backup(data_dir, new_version, migrate):
    (data_dir / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"")

    call_command("migrate_with_backup")

    assert not (data_dir / "backups").exists()
    migrate.assert_called_once()


def test_no_backup_no_migrations(data_dir, new_version, migrate):
    error = backups.SafetyBackupError(data_dir / "backups")
    with (
        patch.object(backups, "safety_backup", side_effect=error),
        pytest.raises(CommandError, match="vorige versie"),
    ):
        call_command("migrate_with_backup")

    migrate.assert_not_called()


def test_pending_migrations_of_an_up_to_date_database():
    assert migrate_with_backup.pending_migrations() == []


def test_the_test_database_is_an_administration():
    assert migrate_with_backup.has_administration()


def test_the_entrypoint_uses_it(settings):
    entrypoint = (settings.BASE_DIR / "docker" / "entrypoint.sh").read_text()

    assert "manage.py migrate_with_backup" in entrypoint
    assert "manage.py migrate --noinput" not in entrypoint
