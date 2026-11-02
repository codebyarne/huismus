# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Daily backups on every installation: the desktop app (SPEC.md M11) and
Docker (M15); huismus-intern/besluiten.md, 2026-10-28, 2026-10-29 and 2026-10-30.

Once a day Huismus writes a backup archive (core.backup) to a folder the
user picks once: in the desktop app often one that a sync app puts in the
cloud, on Docker one linked into the container (LINKED_FOLDER). Only
archives go there, never the live database. The chosen folder and how the
last attempt went belong to this computer, not to the administration, so
they live in a small file next to the database that no backup carries
(STATUS_FILE_NAME): after a restore the folder stays chosen.

Restoring first backs up the current state, and while it runs the app
serves no pages (core.maintenance). The desktop app runs the daily
backup from its own hourly thread (desktop/app.py), Docker from one that
gunicorn starts (gunicorn.conf.py, start_hourly_thread).
"""

import errno
import json
import logging
import re
import sqlite3
import sys
import tarfile
import threading
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.db import connections
from django.utils import timezone
from django.utils.translation import gettext as _

from . import cloud_backups, maintenance
from .backup import (
    BEFORE_SAMPLE_DATA_FILE_NAME,
    FALLBACK_DIR_NAME,
    STATUS_FILE_NAME,
    BackupError,
    create_backup,
    restore_backup,
    sample_data_in_use,
)

# The names core.backup.create_backup gives its archives. Huismus only
# ever removes files with such a name.
ARCHIVE_NAME = re.compile(r"^huismus-backup-(\d{8}-\d{6})(?:-\d+)?\.tar\.gz$")
KEEP_ALL_DAYS = 30
WARN_AFTER_DAYS = 7
# Where the backup of the current state goes when restoring before a
# folder was chosen. In the desktop app next to the administration, not
# in it; on Docker only the volume outlives the container, so in data/
# (core.backup never puts that folder in an archive).
FALLBACK_FOLDER_NAME = "Huismus back-ups"
# Docker: the place in the container where the docs say to link a folder
# of a NAS, USB drive or server (docs/hulp/back-ups.nl.md). Huismus never
# creates it.
LINKED_FOLDER = Path("/backups")

# Google Drive for desktop shows up as a drive of its own, G: unless the
# user chose another letter; then it's "Andere map…" (huismus-intern/besluiten.md).
# Never every drive: a network drive that's gone can hang.
GOOGLE_DRIVE_ON_WINDOWS = Path("G:/")

UNREACHABLE, FULL, OTHER = "unreachable", "full", "other"

_status_lock = threading.Lock()
# The daily thread and "Nu back-up maken" never write at the same time.
_backup_lock = threading.Lock()
logger = logging.getLogger("huismus.backups")


class FolderError(ValueError):
    """A folder that can't be chosen; the message is for the user."""


class RestoreError(Exception):
    """Restoring stopped; the message is for the user."""


@dataclass
class Status:
    folder: str = ""
    last_success: str = ""  # ISO timestamps, so the file stays readable
    last_failure: str = ""
    failure_reason: str = ""  # UNREACHABLE, FULL or OTHER

    @property
    def last_success_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_success) if self.last_success else None

    @property
    def last_failure_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_failure) if self.last_failure else None

    @property
    def failed(self) -> bool:
        """The last attempt failed (after the last one that worked)."""
        failure, success = self.last_failure_at, self.last_success_at
        return failure is not None and (success is None or failure > success)


@dataclass(frozen=True)
class Archive:
    path: Path
    created_at: datetime
    size: int


def _status_path() -> Path:
    return Path(settings.DATA_DIR) / STATUS_FILE_NAME


def load_status() -> Status:
    try:
        data = json.loads(_status_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return Status()
    return Status(**{key: data.get(key, "") for key in Status.__dataclass_fields__})


def _save_status(status: Status) -> None:
    path = _status_path()
    # The temporary name starts with STATUS_FILE_NAME too, so a backup
    # written at this moment leaves it out as well.
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
    temporary.replace(path)


def _update_status(**changes) -> Status:
    with _status_lock:
        status = load_status()
        for key, value in changes.items():
            setattr(status, key, value)
        _save_status(status)
        return status


def chosen_folder() -> Path | None:
    folder = load_status().folder
    return Path(folder) if folder else None


def fallback_folder() -> Path:
    data_dir = Path(settings.DATA_DIR)
    if settings.DESKTOP:
        return data_dir.parent / FALLBACK_FOLDER_NAME
    return data_dir / FALLBACK_DIR_NAME


def staged_upload() -> Path:
    """Where an uploaded backup waits between "Verder" and "Terugzetten",
    one at a time: beside the fallback folder's archives, never in a
    backup itself. The folder may not exist yet."""
    if settings.DESKTOP:
        return Path(settings.DATA_DIR).parent / ".huismus-terugzetten.tar.gz"
    return fallback_folder() / ".huismus-terugzetten.tar.gz"


# -- Choosing the folder ---------------------------------------------------


def sync_folders(home: Path | None = None) -> list[tuple[str, Path]]:
    """The sync apps' folders on this computer, with the service's name."""
    home = home or Path.home()
    if sys.platform == "win32":
        found = _windows_sync_folders(home, GOOGLE_DRIVE_ON_WINDOWS)
    else:
        found = _mac_sync_folders(home)
    if (home / "Dropbox").is_dir() and not any(name == "Dropbox" for name, _ in found):
        found.append(("Dropbox", home / "Dropbox"))
    return [(name, path) for name, path in found if path.is_dir()]


def _mac_sync_folders(home: Path) -> list[tuple[str, Path]]:
    found = []
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if icloud.is_dir():
        found.append(("iCloud Drive", icloud))
    cloud_storage = home / "Library" / "CloudStorage"
    if cloud_storage.is_dir():
        for place in sorted(cloud_storage.iterdir()):
            if place.name.startswith("GoogleDrive"):
                found.extend(_google_drive(place))
            elif place.name.startswith("OneDrive"):
                found.append(("OneDrive", place))
            elif place.name.startswith("Dropbox"):
                found.append(("Dropbox", place))
    return found


def _windows_sync_folders(home: Path, google_drive: Path) -> list[tuple[str, Path]]:
    # OneDrive names its folders itself, "OneDrive - Bedrijf" for a work
    # account; that name is how the user knows it.
    found = [(place.name, place) for place in sorted(home.glob("OneDrive*")) if place.is_dir()]
    if (home / "iCloudDrive").is_dir():
        found.append(("iCloud Drive", home / "iCloudDrive"))
    return found + _google_drive(google_drive)


def _google_drive(place: Path) -> list[tuple[str, Path]]:
    try:
        return [
            ("Google Drive", place / drive)
            for drive in ("My Drive", "Mijn Drive")
            if (place / drive).is_dir()
        ]
    except OSError:
        # G: there but unreadable (a drive that's gone, no access): no
        # suggestion, and the page still opens.
        return []


def suggestions(home: Path | None = None) -> list[tuple[str, Path]]:
    """In the desktop app each sync folder found, with a "Huismus" folder
    in it (huismus-intern/besluiten.md: only the ones found). On Docker the linked
    folder, if there is one."""
    if not settings.DESKTOP:
        return [(_("Gekoppelde map"), LINKED_FOLDER)] if LINKED_FOLDER.is_dir() else []
    return [(name, path / "Huismus") for name, path in sync_folders(home)]


def folder_label(folder) -> str:
    """How the app names a folder: "iCloud Drive › Huismus" rather than its
    path with "com~apple~CloudDocs" (huismus-intern/besluiten.md, 2026-10-29). A
    folder elsewhere keeps the path the user typed."""
    folder = Path(folder)
    if folder == fallback_folder():
        if settings.DESKTOP:
            return _("Huismus back-ups, naast je administratie")
        return _("Huismus back-ups, bij je administratie")
    if not settings.DESKTOP:
        return str(folder)
    for name, root in sync_folders():
        if folder == root or root in folder.parents:
            return " › ".join([name, *folder.relative_to(root).parts])
    return str(folder)


def check_folder(text: str) -> Path:
    """The folder the user typed or picked, or FolderError. Huismus creates
    only its last part: a missing drive or a typo must not quietly put
    backups on the internal disk (huismus-intern/besluiten.md, 2026-10-29)."""
    text = text.strip()
    if not text:
        raise FolderError(_("Kies een map."))
    folder = Path(text).expanduser()
    if not folder.is_absolute():
        raise FolderError(_("Vul het hele pad naar de map in."))
    folder = folder.resolve()
    if folder.exists() and not folder.is_dir():
        raise FolderError(_("Dit is een bestand, geen map."))
    if not folder.parent.is_dir():
        raise FolderError(
            _("De map %(parent)s bestaat niet. Is de schijf aangesloten?")
            % {"parent": folder.parent}
        )
    data_dir = Path(settings.DATA_DIR).resolve()
    if folder == data_dir or data_dir in folder.parents or folder in data_dir.parents:
        raise FolderError(_("Kies een map buiten je administratie."))
    if not settings.DESKTOP and _inside_container(folder):
        raise FolderError(
            _(
                "Deze map is weg zodra Huismus wordt bijgewerkt."
                " Koppel een map van je NAS of een USB-schijf en kies die."
            )
        )
    return folder


MOUNTINFO = Path("/proc/self/mountinfo")


def _inside_container(folder: Path) -> bool:
    """Whether folder lies in the container's own files, which are gone
    when the container is replaced, rather than on something linked in
    (a volume, a NAS share). Best effort: Docker's own files are an
    overlay mounted at "/" with its usual storage driver; with another
    one (btrfs, zfs), or without /proc, nothing counts as inside: better
    a folder that works than one refused wrongly (huismus-intern/besluiten.md,
    2026-10-30)."""
    try:
        lines = MOUNTINFO.read_text().splitlines()
    except OSError:
        return False
    mounts = {}
    for line in lines:
        # "<id> <parent> <dev> <root> <mount point> <options> ... - <type> ..."
        fields = line.split()
        if "-" not in fields or len(fields) < 5:
            continue
        mount_point = Path(fields[4].replace("\\040", " "))
        mounts[mount_point] = fields[fields.index("-") + 1]
    # The deepest mount point that holds the folder is where it is stored.
    holding = [point for point in mounts if point == folder or point in folder.parents]
    if not holding:
        return False
    deepest = max(holding, key=lambda point: len(point.parts))
    return deepest == Path("/") and mounts[deepest] == "overlay"


def choose_folder(folder: Path) -> None:
    """Saves the folder (from check_folder). Errors only if the last part
    can't be created; the first backup is make_backup's job."""
    try:
        folder.mkdir(exist_ok=True)
    except OSError as error:
        raise FolderError(
            _("Huismus kan de map %(folder)s niet maken.") % {"folder": folder}
        ) from error
    _update_status(folder=str(folder), last_failure="", failure_reason="")


# -- Making backups ---------------------------------------------------------


def make_backup(now: datetime | None = None) -> Path | None:
    """A backup in the chosen folder, recorded in the status and followed
    by the clean-up. Returns its path, or None after a failure (which is
    recorded, and logged). None, and nothing recorded, while the sample
    data is in use: made-up records never go into the backup folder
    (huismus-intern/besluiten.md, 2026-10-30)."""
    folder = chosen_folder()
    if folder is None or sample_data_in_use():
        return None
    now = now or timezone.localtime()
    try:
        with _backup_lock:
            if not folder.is_dir():
                # create_backup would make it, also on a drive that is gone.
                raise FileNotFoundError(errno.ENOENT, "map niet gevonden", str(folder))
            path = create_backup(folder)
    except (OSError, BackupError, sqlite3.Error, tarfile.TarError) as error:
        # Never silently: every failure gets the overview's red banner.
        logger.warning("Back-up mislukt: %s", error)
        _update_status(last_failure=now.isoformat(), failure_reason=_reason(error))
        return None
    _update_status(last_success=now.isoformat())
    prune(folder, now)
    return path


def _reason(error: Exception) -> str:
    if not isinstance(error, OSError):
        return OTHER
    if error.errno in (errno.ENOSPC, errno.EDQUOT):
        return FULL
    if isinstance(error, (FileNotFoundError, PermissionError)) or error.errno in (
        errno.ENOENT,
        errno.EACCES,
        errno.EPERM,
        errno.EROFS,
        errno.EIO,
        errno.ENXIO,
        errno.ENODEV,
    ):
        return UNREACHABLE
    return OTHER


def is_due(now: datetime | None = None) -> bool:
    """A folder is chosen and today has no backup that worked yet."""
    status = load_status()
    if not status.folder:
        return False
    now = now or timezone.localtime()
    last = status.last_success_at
    return last is None or timezone.localtime(last).date() < now.date()


def run_if_due(now: datetime | None = None) -> Path | None:
    """What the desktop app calls at start and every hour after
    (desktop/app.py), and Docker's hourly thread: the folder's backup and
    the cloud's (core.cloud_backups), each if today has none yet. Never
    while a backup is being restored."""
    with maintenance.gate.request() as open_:
        if not open_:
            return None
        made = make_backup(now) if is_due(now) else None
        if cloud_backups.is_due(now):
            cloud_backups.upload_backup(now)
        return made


def start_hourly_thread() -> threading.Thread:
    """On Docker: a backup when the server starts and then every hour if
    today has none yet, as in the desktop app (huismus-intern/besluiten.md,
    2026-10-30). gunicorn calls this once in its one worker
    (gunicorn.conf.py); with more workers, each would make its own."""

    def every_hour():
        while True:
            try:
                run_if_due()
            except Exception:
                logger.exception("Back-up mislukt")
            time.sleep(60 * 60)

    thread = threading.Thread(target=every_hour, name="huismus-backups", daemon=True)
    thread.start()
    return thread


def prune(folder: Path, now: datetime) -> list[Path]:
    """Removes what to_remove says from the folder; only Huismus's own
    archives (ARCHIVE_NAME). Returns what was removed."""
    dated = []
    for path in folder.iterdir():
        match = ARCHIVE_NAME.match(path.name)
        if match:
            dated.append((datetime.strptime(match[1], "%Y%m%d-%H%M%S"), path))
    removed = to_remove(dated, now)
    for path in removed:
        path.unlink(missing_ok=True)
    return removed


def to_remove(dated: list, now: datetime) -> list:
    """Of (created, item) pairs, the items to remove: keep every archive
    of the last 30 days, then the newest of each month, and always the
    newest of all. The folder's rule, and the cloud's
    (core.cloud_backups.prune)."""
    dated = sorted(dated, key=lambda pair: pair[0], reverse=True)
    cutoff = timezone.localtime(now).replace(tzinfo=None) - timedelta(days=KEEP_ALL_DAYS)
    # Newest first, so the first archive of a month past the cutoff is
    # that month's newest.
    kept_months = set()
    removed = []
    for index, (created, item) in enumerate(dated):
        if created >= cutoff:
            continue
        month = (created.year, created.month)
        if index == 0 or month not in kept_months:
            kept_months.add(month)
            continue
        removed.append(item)
    return removed


def archives() -> list[Archive]:
    """Huismus's archives in the chosen folder and the fallback folder,
    newest first. Unreadable folders count as empty."""
    found = []
    for folder in (chosen_folder(), fallback_folder()):
        if folder is None or not folder.is_dir():
            continue
        try:
            entries = list(folder.iterdir())
        except OSError:
            continue
        for path in entries:
            match = ARCHIVE_NAME.match(path.name)
            if match:
                created = datetime.strptime(match[1], "%Y%m%d-%H%M%S")
                found.append(Archive(path, created, path.stat().st_size))
    found.sort(key=lambda archive: archive.created_at, reverse=True)
    return found


# -- Restoring --------------------------------------------------------------


class SafetyBackupError(Exception):
    def __init__(self, folder: Path):
        super().__init__(str(folder))
        self.folder = folder


def safety_backup() -> Path:
    """The backup before a restore or an update: in the chosen folder, or
    without one next to the administration (huismus-intern/besluiten.md, 2026-10-29).
    SafetyBackupError when it can't be made.

    While the sample data is in use, none: the way back is the state from
    before it (core.sample_data), and made-up records never go into an
    archive (huismus-intern/besluiten.md, 2026-10-30)."""
    if sample_data_in_use():
        return Path(settings.DATA_DIR) / BEFORE_SAMPLE_DATA_FILE_NAME
    folder = chosen_folder()
    if folder is None or not folder.is_dir():
        folder = fallback_folder()
    try:
        folder.mkdir(exist_ok=True)
        with _backup_lock:
            path = create_backup(folder)
    except (OSError, BackupError, sqlite3.Error, tarfile.TarError) as error:
        logger.exception("Back-up vooraf mislukt")
        raise SafetyBackupError(folder) from error
    if folder == chosen_folder():
        _update_status(last_success=timezone.localtime().isoformat())
    return path


def restore(archive_path: Path) -> Path:
    """Backs up the current state, then restores archive_path and runs the
    migrations (a backup can be from an older Huismus). No page is served
    meanwhile. Returns where the backup of the state before went.

    The caller checked the archive (core.backup.unknown_migrations), and
    is itself a request: it waits for the others to finish. RestoreError
    when it stops; after the backup of the state before, its message says
    where that backup is, the way back.

    Restoring during "Probeer met nepdata" ends the sample data: the
    administration is the restored one now, and clearing would throw it
    away again (core.sample_data)."""
    try:
        with maintenance.gate.exclusive():
            try:
                before = safety_backup()
            except SafetyBackupError as error:
                raise RestoreError(
                    _("Huismus kon eerst geen back-up maken in %(folder)s. Er is niets teruggezet.")
                    % {"folder": folder_label(error.folder)}
                ) from error
            triggers = _triggers()
            try:
                # The database file is replaced under this connection.
                connections.close_all()
                restore_backup(archive_path)
                call_command("migrate", interactive=False, verbosity=0)
            except Exception as error:
                logger.exception("Terugzetten mislukt")
                raise RestoreError(
                    _(
                        "Terugzetten is niet gelukt. De stand van daarvoor staat in %(file)s;"
                        " zet die terug om verder te gaan waar je was."
                    )
                    % {"file": before}
                ) from error
            if not triggers <= _triggers():
                # The triggers that keep issued documents unchanged (CLAUDE.md
                # rule 2) come with the migrations; a database that says it has
                # them but doesn't is not Huismus's own. Back to how it was.
                logger.error("Teruggezette database mist triggers: %s", triggers - _triggers())
                connections.close_all()
                restore_backup(before)
                call_command("migrate", interactive=False, verbosity=0)
                raise RestoreError(
                    _(
                        "Deze back-up is niet compleet: de bescherming van uitgegeven"
                        " documenten ontbreekt. Er is niets teruggezet."
                    )
                )
            # A real administration replaced the sample data: the way back
            # from it (core.sample_data) is no longer the way back.
            (Path(settings.DATA_DIR) / BEFORE_SAMPLE_DATA_FILE_NAME).unlink(missing_ok=True)
    except maintenance.Busy as error:
        raise RestoreError(
            _("Huismus is al bezig met terugzetten. Probeer het zo nog eens.")
        ) from error
    return before


def _triggers() -> set[tuple[str, str]]:
    """Each trigger's name and its SQL: a trigger with the right name but
    an emptied body protects nothing."""
    with connections["default"].cursor() as cursor:
        cursor.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'")
        return set(cursor.fetchall())


# -- What the overview says -------------------------------------------------


def last_success() -> datetime | None:
    """The last backup that worked, in the folder or in the cloud."""
    found = [load_status().last_success_at, cloud_backups.load().last_success_at]
    found = [moment for moment in found if moment is not None]
    return max(found) if found else None


def first_step() -> str:
    """What has to happen before the first backup (huismus-intern/besluiten.md,
    2026-10-31): in the desktop app choose a folder; on Docker first link
    one into the container (`-v …:/backups`), or choose the linked one.
    "Linked" means /backups exists, as in suggestions(): Huismus never
    creates it, so it is there only when the user linked it."""
    if settings.DESKTOP:
        return "choose"
    return "choose_linked" if LINKED_FOLDER.is_dir() else "link"


def warning(now: datetime | None = None) -> dict | None:
    """The overview's banner, the worst first: the last backup failed
    (red), no folder chosen yet, or more than 7 days since the last one
    (amber). None when all is well, and while the sample data is in use:
    then Huismus makes no backups (huismus-intern/besluiten.md, 2026-10-30)."""
    if sample_data_in_use():
        return None
    status = load_status()
    now = now or timezone.localtime()
    cloud = cloud_backups.load()
    if status.failed:
        return {
            "kind": "failed",
            "level": "bad",
            "reason": status.failure_reason,
            "at": timezone.localtime(status.last_failure_at),
            "folder": folder_label(status.folder),
        }
    if cloud.service and cloud.failed:
        return {
            "kind": "cloud_failed",
            "level": "bad",
            "reason": cloud.failure_reason,
            "at": timezone.localtime(cloud.last_failure_at),
            "service": cloud.service_label,
            "sentence": cloud_backups.failure_sentence(cloud),
        }
    # A cloud is a place for backups too (huismus-intern/besluiten.md, 2026-10-31),
    # once its code is saved: before that nothing goes there.
    if not status.folder and not cloud_backups.is_ready():
        return {"kind": "none", "level": "warn", "step": first_step()}
    last = last_success()
    if last is not None and now - last > timedelta(days=WARN_AFTER_DAYS):
        return {"kind": "old", "level": "warn", "at": timezone.localtime(last)}
    return None
