# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backup/restore for SPEC.md section 6 (M7): one portable archive with a
consistent SQLite snapshot plus everything else under DATA_DIR (uploaded
logos, receipts). A plain file copy of the database isn't safe under WAL
(huismus/core/sqlite.py) — a concurrent writer can leave the copy torn mid-write —
so this uses sqlite3's own online backup API instead, which is safe to run
against a live connection.
"""

import shutil
import sqlite3
import tarfile
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.utils import timezone

from huismus.assistants import key as assistant_key
from huismus.business import smtp
from huismus.config import secret_key
from huismus.expenses import ai_service

DB_NAME_IN_ARCHIVE = "db.sqlite3"
# Kept by core.auto_backups; here so this module needs nothing from it.
STATUS_FILE_NAME = "backup-status.json"
# Kept by core.cloud_backups, which imports this module.
CLOUD_FILE_PREFIX = "cloud-backup"
UPDATE_STATUS_FILE_NAME = "update-status.json"
# Kept by expenses.inbox: which receipts folder, and how the last look went.
RECEIPTS_FOLDER_FILE_NAME = "receipts-folder.json"
# The state from before "Probeer met nepdata" (core.sample_data).
BEFORE_SAMPLE_DATA_FILE_NAME = "voor-nepdata.tar.gz"
# data/backups: on Docker where the backup before a restore goes when no
# folder was chosen (core.auto_backups.fallback_folder).
FALLBACK_DIR_NAME = "backups"
# Where restore_backup unpacks an archive first: inside DATA_DIR, the one
# place that is sure to be writable (in Docker only the volume is) and on
# the same disk, so putting the files in place is a rename.
RESTORING_PREFIX = ".huismus-restoring-"


class BackupError(Exception):
    pass


def sample_data_in_use() -> bool:
    """The state from before "Probeer met nepdata" is kept until it is
    cleared again (core.sample_data); here, so core.auto_backups can ask
    without importing the models."""
    return (Path(settings.DATA_DIR) / BEFORE_SAMPLE_DATA_FILE_NAME).exists()


def create_backup(output_dir: Path) -> Path:
    """Writes a timestamped .tar.gz to output_dir and returns its path."""
    output_dir.mkdir(parents=True, exist_ok=True)
    # Django's local time, the clock the desktop app's status and overview
    # use too (core.auto_backups reads it back from the name).
    timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    archive_path = output_dir / f"huismus-backup-{timestamp}.tar.gz"
    # Two in the same second (the desktop app's backup before a restore,
    # right after another): never overwrite the first.
    count = 1
    while archive_path.exists():
        count += 1
        archive_path = output_dir / f"huismus-backup-{timestamp}-{count}.tar.gz"
    # Written under another name first: a backup cut off halfway (a full
    # disk, a USB drive pulled out) never looks like a finished archive.
    partial_path = output_dir / f".{archive_path.name}.partial"

    data_dir = Path(settings.DATA_DIR)
    db_name = Path(connections["default"].settings_dict["NAME"]).name

    try:
        _write_archive(partial_path, output_dir, data_dir, db_name)
        partial_path.replace(archive_path)
    except BaseException:
        partial_path.unlink(missing_ok=True)
        raise
    return archive_path


def _write_archive(archive_path: Path, output_dir: Path, data_dir: Path, db_name: str) -> None:
    with tarfile.open(archive_path, "w:gz") as tar, _snapshot_database() as snapshot_path:
        tar.add(snapshot_path, arcname=DB_NAME_IN_ARCHIVE)
        for item in sorted(data_dir.iterdir()):
            # Skip the live db file and its WAL/SHM sidecars — the online
            # backup above already folds their contents into one
            # consistent db.sqlite3, so archiving them raw too would just
            # add a second, less trustworthy copy of the same data.
            if item.name == db_name or item.name.startswith(db_name + "-"):
                continue
            # Not the backups themselves when they're written inside data/
            # (docs/backups.md suggests data/backups): every archive would
            # otherwise contain all earlier ones, including the one being
            # written right now.
            if item.resolve() == output_dir.resolve() or item.name == FALLBACK_DIR_NAME:
                continue
            if _belongs_to_this_installation(item.name):
                continue
            tar.add(item, arcname=item.name)


def _belongs_to_this_installation(name: str) -> bool:
    """Files in DATA_DIR that are this installation's own, not the
    administration's: a backup leaves them out, and a restore never takes
    them from an archive either. Otherwise a crafted "backup" could bring
    its own cloud link or SECRET_KEY along."""
    # A restore cut off halfway leaves its unpacked archive behind.
    if name.startswith(RESTORING_PREFIX):
        return True
    # Uploads waiting between an import's dry run and its commit
    # (imports.staging): temporary, and removed within a day.
    if name == "import-staging":
        return True
    # The mail password (business.smtp): a backup is copied to other places
    # and should not carry it. After a restore on a new machine it is typed
    # in again.
    if name.startswith(smtp.password_path().name):
        return True
    # Likewise the generated SECRET_KEY (config.secret_key), and a temporary
    # file of it left by a start that was cut off.
    if name.startswith(secret_key.FILE_NAME):
        return True
    # And the AI connection's key (assistants.key): a restored backup should
    # not let an old key in.
    if name.startswith(assistant_key.FILE_NAME):
        return True
    # The AI service that reads receipts (expenses.ai_service): its key.
    if name.startswith(ai_service.FILE_PREFIX):
        return True
    # The link to a cloud service and the recovery code (core.cloud_backups):
    # secrets of this installation, and a backup encrypted with a code must
    # never carry that code.
    if name.startswith(CLOUD_FILE_PREFIX):
        return True
    # The desktop app's backup folder and status, and its update setting,
    # belong to this computer, not to the administration (core.auto_backups,
    # core.updates).
    if name.startswith((STATUS_FILE_NAME, UPDATE_STATUS_FILE_NAME)):
        return True
    # So does the receipts folder (expenses.inbox), like the backup folder.
    # The receipts it fetched are the administration's and do go along.
    if name.startswith(RECEIPTS_FOLDER_FILE_NAME):
        return True
    # The way back from the sample data is not part of any administration
    # (core.sample_data).
    return name == BEFORE_SAMPLE_DATA_FILE_NAME


def restore_backup(archive_path: Path) -> None:
    """Replaces the database and every path an archive contains with that
    archive's own copy. An overlay, not a wipe: something already in
    DATA_DIR that the archive says nothing about (e.g. a file added since
    the backup was taken) is left alone, not deleted to force an exact
    match — the one exception is the database itself, which is always
    replaced wholesale since a partial/merged database makes no sense.

    Destructive by design regardless — this is what a restore is for — so
    the management command wrapping this refuses to call it without an
    explicit confirmation flag. Extraction happens into a scratch
    directory first, and DATA_DIR is only touched after every member has
    been read out of the archive without error — a truncated download, a
    corrupt archive, or a disk-full mid-extraction is caught here, before
    anything real is deleted, rather than leaving the user with a half-
    overwritten (or missing) database.
    """
    data_dir = Path(settings.DATA_DIR)
    db_name = Path(connections["default"].settings_dict["NAME"]).name

    with tarfile.open(archive_path, "r:gz") as tar:
        if DB_NAME_IN_ARCHIVE not in tar.getnames():
            raise BackupError(f"{archive_path} bevat geen {DB_NAME_IN_ARCHIVE} — geen backup?")

        with tempfile.TemporaryDirectory(dir=data_dir, prefix=RESTORING_PREFIX) as scratch:
            scratch_path = Path(scratch)
            tar.extractall(scratch_path, filter="data")

            # Only now, with a fully extracted archive sitting safely
            # outside DATA_DIR, start replacing what's actually live. A
            # stale -wal/-shm from the database generation being replaced
            # is not valid against the db.sqlite3 taking its place, so
            # those go first; they have no equivalent among the archive's
            # own members to land on top of them.
            for suffix in ("-wal", "-shm"):
                (data_dir / f"{db_name}{suffix}").unlink(missing_ok=True)

            for item in scratch_path.iterdir():
                # An archive from before data/backups was left out (an old
                # docs/backups.md said to back up into it) must not wipe
                # it: it holds the backup made just before this restore.
                if item.name == FALLBACK_DIR_NAME:
                    continue
                if _belongs_to_this_installation(item.name):
                    continue
                # DB_NAME_IN_ARCHIVE only ever differs from db_name under
                # the pytest test runner, which points DATABASES at
                # test_db.sqlite3 instead (huismus/config/settings_test.py) —
                # production always names its database db.sqlite3, so
                # this rename is a no-op there.
                target_name = db_name if item.name == DB_NAME_IN_ARCHIVE else item.name
                target = data_dir / target_name
                if target.is_dir():
                    shutil.rmtree(target)
                else:
                    target.unlink(missing_ok=True)
                shutil.move(str(item), str(target))


@contextmanager
def _snapshot_database():
    """Yields a temp-file path holding a consistent copy of the live
    database, via sqlite3's backup() API rather than a raw file copy.
    """
    with tempfile.TemporaryDirectory(prefix="huismus-backup-") as tmp_dir:
        snapshot_path = Path(tmp_dir) / DB_NAME_IN_ARCHIVE
        source = sqlite3.connect(connections["default"].settings_dict["NAME"])
        try:
            dest = sqlite3.connect(snapshot_path)
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        yield snapshot_path


def archive_created_at(archive_path: Path) -> datetime:
    """When an archive's database snapshot was taken, from the archive
    itself rather than its file name (an uploaded file can be called
    anything). Raises BackupError for a file that isn't a backup."""
    try:
        with tarfile.open(archive_path, "r:gz") as tar:
            member = tar.getmember(DB_NAME_IN_ARCHIVE)
    except KeyError:
        raise BackupError(f"{archive_path} bevat geen {DB_NAME_IN_ARCHIVE}") from None
    except (tarfile.TarError, OSError, EOFError) as error:
        raise BackupError(f"{archive_path} is geen backup-archief: {error}") from error
    return datetime.fromtimestamp(member.mtime)


def unknown_migrations(archive_path: Path) -> set[tuple[str, str]]:
    """Migrations the archive's database has applied that this version of
    Huismus doesn't have: a backup from a newer version, which this one
    can't run on. Raises BackupError for a file that isn't a backup, or
    whose database is damaged (SQLite's own quick_check)."""
    from django.db.migrations.loader import MigrationLoader

    with tempfile.TemporaryDirectory(prefix="huismus-inspect-") as scratch:
        try:
            with tarfile.open(archive_path, "r:gz") as tar:
                tar.extract(DB_NAME_IN_ARCHIVE, scratch, filter="data")
        except KeyError:
            raise BackupError(f"{archive_path} bevat geen {DB_NAME_IN_ARCHIVE}") from None
        except (tarfile.TarError, OSError, EOFError) as error:
            raise BackupError(f"{archive_path} is geen backup-archief: {error}") from error
        connection = sqlite3.connect(Path(scratch) / DB_NAME_IN_ARCHIVE)
        try:
            (check,) = connection.execute("PRAGMA quick_check").fetchone()
            if check != "ok":
                raise BackupError(f"{archive_path}: database beschadigd ({check})")
            applied = set(connection.execute("SELECT app, name FROM django_migrations"))
        except sqlite3.DatabaseError as error:
            raise BackupError(f"{archive_path} bevat geen Huismus-database: {error}") from error
        finally:
            connection.close()
    known = set(MigrationLoader(None, ignore_no_migrations=True).disk_migrations)
    return applied - known
