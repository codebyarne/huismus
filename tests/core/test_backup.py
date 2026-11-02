# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import sqlite3
import tarfile
from unittest.mock import patch

import pytest
from django.db import connections

from huismus.business import smtp
from huismus.contacts.models import Contact
from huismus.core.backup import BackupError, create_backup, restore_backup

pytestmark = pytest.mark.django_db


def _live_db_name() -> str:
    return connections["default"].settings_dict["NAME"].split("/")[-1]


def test_create_backup_writes_a_timestamped_tar_gz(tmp_path):
    archive_path = create_backup(tmp_path / "out")

    assert archive_path.exists()
    assert archive_path.parent == tmp_path / "out"
    assert archive_path.name.startswith("huismus-backup-")
    assert archive_path.name.endswith(".tar.gz")


@pytest.mark.django_db(transaction=True)
def test_create_backup_snapshot_is_a_consistent_copy_of_the_database(tmp_path):
    # The default django_db marker wraps a test in a transaction that never
    # commits to disk, so a second, independent sqlite3 connection (what
    # the backup's online-copy API opens) would never see this row. Needs
    # transaction=True to actually write it to the file being backed up.
    Contact.objects.create(company_name="Backup Test BV")

    archive_path = create_backup(tmp_path / "out")

    with tarfile.open(archive_path, "r:gz") as tar:
        tar.extract("db.sqlite3", tmp_path / "extracted", filter="data")

    conn = sqlite3.connect(tmp_path / "extracted" / "db.sqlite3")
    try:
        row = conn.execute(
            "SELECT company_name FROM contacts_contact WHERE company_name = ?",
            ("Backup Test BV",),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Backup Test BV",)


def test_create_backup_includes_data_dir_files_alongside_the_database(settings, tmp_path):
    data_dir = tmp_path / "data"
    (data_dir / "receipts").mkdir(parents=True)
    (data_dir / "receipts" / "bon.png").write_bytes(b"receipt-bytes")
    settings.DATA_DIR = data_dir

    archive_path = create_backup(tmp_path / "out")

    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
    assert "receipts/bon.png" in names


def test_create_backup_does_not_archive_the_live_database_file_a_second_time(settings, tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    db_name = _live_db_name()
    (data_dir / db_name).write_bytes(b"decoy-raw-copy")
    (data_dir / f"{db_name}-wal").write_bytes(b"decoy-wal")
    settings.DATA_DIR = data_dir

    archive_path = create_backup(tmp_path / "out")

    with tarfile.open(archive_path, "r:gz") as tar:
        names = tar.getnames()
    assert db_name not in names
    assert f"{db_name}-wal" not in names
    assert names.count("db.sqlite3") == 1


@pytest.mark.django_db(transaction=True)  # see the comment on the first use of this marker above
def test_restore_backup_replaces_the_database_and_media_files(settings, tmp_path):
    before = tmp_path / "before"
    (before / "receipts").mkdir(parents=True)
    (before / "receipts" / "bon.png").write_bytes(b"receipt-bytes")
    settings.DATA_DIR = before
    Contact.objects.create(company_name="Restore Test BV")

    archive_path = create_backup(tmp_path / "out")

    after = tmp_path / "after"
    after.mkdir()
    settings.DATA_DIR = after

    restore_backup(archive_path)

    assert (after / "receipts" / "bon.png").read_bytes() == b"receipt-bytes"
    db_name = _live_db_name()
    conn = sqlite3.connect(after / db_name)
    try:
        row = conn.execute(
            "SELECT company_name FROM contacts_contact WHERE company_name = ?",
            ("Restore Test BV",),
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Restore Test BV",)


def test_restore_backup_removes_stale_wal_and_shm_sidecars_first(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "before"
    (tmp_path / "before").mkdir()
    archive_path = create_backup(tmp_path / "out")

    after = tmp_path / "after"
    after.mkdir()
    db_name = _live_db_name()
    (after / db_name).write_bytes(b"stale-main")
    (after / f"{db_name}-wal").write_bytes(b"stale-wal")
    (after / f"{db_name}-shm").write_bytes(b"stale-shm")
    settings.DATA_DIR = after

    restore_backup(archive_path)

    assert not (after / f"{db_name}-wal").exists()
    assert not (after / f"{db_name}-shm").exists()
    assert (after / db_name).read_bytes() != b"stale-main"


def test_restore_backup_leaves_the_live_database_untouched_if_extraction_fails(settings, tmp_path):
    # Regression: restore_backup() used to delete the live db.sqlite3 (and
    # its -wal/-shm sidecars) *before* extracting the archive over it — a
    # disk-full mid-extraction would leave the user with no working
    # database at all, not even the one being replaced. Extraction now
    # happens into a scratch directory first, so a failure there (any
    # failure — this mocks tarfile itself to isolate the "before real data
    # is touched" property from any one specific way extraction can fail)
    # should leave the live db file exactly as it was.
    settings.DATA_DIR = tmp_path / "before"
    (tmp_path / "before").mkdir()
    archive_path = create_backup(tmp_path / "out")

    after = tmp_path / "after"
    after.mkdir()
    db_name = _live_db_name()
    (after / db_name).write_bytes(b"pre-existing-live-database")
    settings.DATA_DIR = after

    with patch("tarfile.TarFile.extractall", side_effect=OSError("disk full (simulated)")):
        with pytest.raises(OSError, match="disk full"):
            restore_backup(archive_path)

    assert (after / db_name).read_bytes() == b"pre-existing-live-database"


def test_restore_backup_rejects_an_archive_without_a_database(settings, tmp_path):
    bogus = tmp_path / "not-a-backup.tar.gz"
    (tmp_path / "readme.txt").write_text("hello")
    with tarfile.open(bogus, "w:gz") as tar:
        tar.add(tmp_path / "readme.txt", arcname="readme.txt")

    settings.DATA_DIR = tmp_path / "data"
    (tmp_path / "data").mkdir()

    with pytest.raises(BackupError):
        restore_backup(bogus)


def test_backups_written_inside_the_data_dir_are_not_archived_again(settings, tmp_path):
    # docs/backups.md suggests `backup /app/data/backups`: without this,
    # every backup would contain all earlier ones and keep growing.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings.DATA_DIR = data_dir
    (data_dir / "logo").mkdir()
    (data_dir / "logo" / "logo.png").write_bytes(b"png")
    backups = data_dir / "backups"

    first = create_backup(backups)
    second = create_backup(backups)

    with tarfile.open(second) as tar:
        names = tar.getnames()
    assert "logo/logo.png" in names
    assert not any(name.startswith("backups") for name in names)
    assert first.name not in " ".join(names)


def test_import_staging_is_not_archived(settings, tmp_path):
    # Uploads kept between an import's dry run and its commit (imports.staging).
    data_dir = tmp_path / "data"
    (data_dir / "import-staging" / "abc").mkdir(parents=True)
    (data_dir / "import-staging" / "abc" / "export.zip").write_bytes(b"zip")
    settings.DATA_DIR = data_dir

    with tarfile.open(create_backup(tmp_path / "out")) as tar:
        assert not any(name.startswith("import-staging") for name in tar.getnames())


def test_the_smtp_password_is_not_archived(settings, tmp_path):
    # SPEC.md M10: a backup copied elsewhere never carries the mail password.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings.DATA_DIR = data_dir
    smtp.set_password("niet-in-de-backup")

    with tarfile.open(create_backup(tmp_path / "out")) as tar:
        assert smtp.password_path().name not in tar.getnames()


def test_the_generated_secret_key_is_not_archived(settings, tmp_path):
    # SPEC.md M11: like the mail password. Restoring on another computer
    # means signing in again; no data is lost.
    from huismus.config import secret_key

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings.DATA_DIR = data_dir
    secret_key.load_or_create(data_dir)

    with tarfile.open(create_backup(tmp_path / "out")) as tar:
        assert secret_key.FILE_NAME not in tar.getnames()


def test_the_ai_connections_key_is_not_archived(settings, tmp_path):
    # SPEC.md M16: like the mail password; a restored backup lets no old
    # key in.
    from huismus.assistants import key

    data_dir = tmp_path / "data"
    data_dir.mkdir()
    settings.DATA_DIR = data_dir
    key.create()
    key.mark_used()

    with tarfile.open(create_backup(tmp_path / "out")) as tar:
        assert not any(name.startswith(key.FILE_NAME) for name in tar.getnames())


def test_an_old_archive_with_a_backups_folder_leaves_data_backups_alone(settings, tmp_path):
    # Archives made before data/backups was left out carry it; restoring
    # one must keep the backup made just before (core.auto_backups).
    data = tmp_path / "data"
    (data / "backups").mkdir(parents=True)
    (data / "backups" / "huismus-backup-20261030-120000.tar.gz").write_bytes(b"van zojuist")
    settings.DATA_DIR = data
    old = create_backup(tmp_path / "out")
    with tarfile.open(old) as tar:
        names = tar.getnames()
    assert "backups" not in names  # new archives leave it out ...
    repacked = tmp_path / "oud.tar.gz"
    with tarfile.open(old) as source, tarfile.open(repacked, "w:gz") as tar:
        for member in source.getmembers():
            tar.addfile(member, source.extractfile(member))
        (tmp_path / "oud-backups").mkdir()
        tar.add(tmp_path / "oud-backups", arcname="backups")  # ... old ones had it

    restore_backup(repacked)

    assert (data / "backups" / "huismus-backup-20261030-120000.tar.gz").exists()


def test_restoring_unpacks_inside_the_data_dir(settings, tmp_path):
    # In Docker only the volume is writable, not the folder above it.
    data = tmp_path / "volume" / "data"
    data.mkdir(parents=True)
    settings.DATA_DIR = data
    archive = create_backup(tmp_path / "out")
    unpacked_in = []
    real = tarfile.TarFile.extractall

    def extractall(self, path, **kwargs):
        unpacked_in.append(path.parent)
        return real(self, path, **kwargs)

    with patch.object(tarfile.TarFile, "extractall", extractall):
        restore_backup(archive)

    assert unpacked_in == [data]
    assert not [p for p in data.iterdir() if p.name.startswith(".huismus-restoring-")]


@pytest.mark.parametrize(
    "name",
    [
        "secret-key",
        "smtp-password",
        "mcp-key",
        "cloud-backup.json",
        "cloud-backup-code",
        "backup-status.json",
        "update-status.json",
        "voor-nepdata.tar.gz",
        "import-staging",
    ],
)
def test_a_restore_never_takes_what_a_backup_leaves_out(settings, tmp_path, name):
    # A crafted archive ("here's your backup") with its own cloud link or
    # SECRET_KEY must not set up this installation: those files belong to
    # the computer, not to the administration, and a backup never has them.
    data = tmp_path / "data"
    data.mkdir()
    settings.DATA_DIR = data
    (data / name).write_text("van deze installatie")
    honest = create_backup(tmp_path / "out")
    crafted = tmp_path / "nagemaakt.tar.gz"
    planted = tmp_path / "planted"
    planted.write_text("van een ander")
    with tarfile.open(honest) as source, tarfile.open(crafted, "w:gz") as tar:
        for member in source.getmembers():
            tar.addfile(member, source.extractfile(member))
        tar.add(planted, arcname=name)

    restore_backup(crafted)

    assert (data / name).read_text() == "van deze installatie"
