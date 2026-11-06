# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The receipts folder (SPEC.md M20, "Bonnetjes onderweg"; choices in
huismus-intern/besluiten.md, 2026-11-05).

On the road you save a photo or scan of a receipt in a folder that syncs
(iCloud Drive, Google Drive, OneDrive, Dropbox). Every ten minutes Huismus
looks in that folder and puts each new receipt in the tray: an Attachment
of kind "receipt" that belongs to no expense yet. From the tray the user
makes an expense of it (expenses.views).

Three places to look, one at a time:

- LocalFolder: a folder on this computer (the desktop app), or one linked
  into the container (Docker), checked like the backup folder
  (core.auto_backups.check_folder).
- CloudFolder: Bonnetjes next to the backups of the one cloud service
  linked at Back-ups (core.cloud_backups): in Dropbox's app folder Apps ›
  Huismus, or in the folder Huismus on a WebDAV server (Nextcloud, kDrive,
  Koofr). Only outgoing requests, like the backups; Huismus stays
  unreachable from the internet.

Order matters, so nothing is ever lost: a receipt is first saved in
Huismus (the file in data/ and its row), and only then moved in the folder
to Opgehaald. If saving fails it stays where it was; if moving fails, the
next look finds it again, sees the same sha256 in Huismus, and only moves
it. A file that is no receipt (another type, too big, damaged) stays in
the folder and is tried again at every look; the page names it.

Which folder, and how the last look went, belong to this installation,
not to the administration: a small file in data/ that no backup carries,
like the backup folder's (core.backup).
"""

import errno
import json
import logging
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path, PurePosixPath

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import connections
from django.utils import timezone
from django.utils.translation import gettext as _

from huismus.core import auto_backups, cloud_backups, maintenance
from huismus.core.auto_backups import FolderError
from huismus.core.backup import RECEIPTS_FOLDER_FILE_NAME, sample_data_in_use
from huismus.core.models import Attachment

from . import reading
from .receipts import (
    MAX_RECEIPT_BYTES,
    RASTER_FORMATS,
    sha256_of,
    stored_receipt,
    validate_receipt,
)

# Status.source, stored in data/: never rename these values.
FOLDER, DROPBOX, WEBDAV = "folder", "dropbox", "webdav"
SOURCE = "bonnetjesmap"  # Attachment.source of a receipt fetched from here
# How often to look; "Nu ophalen" looks at once.
INTERVAL = timedelta(minutes=10)
# A file in a plain folder that changed less than this ago may still be
# syncing: it waits for the next look, without a word.
SETTLE_SECONDS = 60
# Docker: where the help says to link a receipts folder (docs/hulp/docker.nl.md).
LINKED_FOLDER = Path("/bonnetjes")

# Why a look failed: core.cloud_backups' reasons, and for a folder UNREACHABLE.
UNREACHABLE, REFUSED, FULL, NOT_WEBDAV, OTHER = (
    cloud_backups.UNREACHABLE,
    cloud_backups.REFUSED,
    cloud_backups.FULL,
    cloud_backups.NOT_WEBDAV,
    cloud_backups.OTHER,
)
# Saving in Huismus itself failed (data/ full, say): not the folder's fault.
STORAGE = "storage"
# Why a file was left in the folder.
WRONG_TYPE, TOO_BIG, DAMAGED, UNREADABLE = "wrong_type", "too_big", "damaged", "unreadable"
ACCEPTED_EXTENSIONS = {"pdf", *RASTER_FORMATS}

_status_lock = threading.Lock()
# One look at a time: every ten minutes, and "Nu ophalen".
_fetch_lock = threading.Lock()
logger = logging.getLogger("huismus.receipts")


@dataclass
class Status:
    source: str = ""  # FOLDER, DROPBOX, WEBDAV, or "" when off
    folder: str = ""  # FOLDER: the path
    # The names Huismus gave its folders, in the language of the moment it
    # was set up; kept, so switching languages later makes no second one.
    done_folder: str = ""  # "Opgehaald", inside the receipts folder
    dropbox_folder: str = ""  # DROPBOX: "/Bonnetjes" in Apps › Huismus
    webdav_folder: str = ""  # WEBDAV: "/Bonnetjes" in the folder Huismus
    last_check: str = ""  # ISO timestamps, as in core.auto_backups
    last_failure: str = ""
    failure_reason: str = ""
    last_fetched: int = 0  # new receipts at the last look that worked
    skipped: list = field(default_factory=list)  # [{"name": …, "reason": …}]
    # What came in after this moment is "2 nieuwe bonnetjes" on the
    # overview. Set when a place is chosen (_start_over), by the first look
    # with a status file from before the notice (_fetch), and by a visit to
    # the receipts without an expense that had something new (seen).
    seen_until: str = ""

    @property
    def last_check_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_check) if self.last_check else None

    @property
    def last_failure_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_failure) if self.last_failure else None

    @property
    def failed(self) -> bool:
        """The last look failed (after the last one that worked)."""
        failure, check = self.last_failure_at, self.last_check_at
        return failure is not None and (check is None or failure > check)


@dataclass(frozen=True)
class Result:
    fetched: int
    skipped: list


def _status_path() -> Path:
    return Path(settings.DATA_DIR) / RECEIPTS_FOLDER_FILE_NAME


def load() -> Status:
    try:
        data = json.loads(_status_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return Status()
    return Status(**{key: data[key] for key in Status.__dataclass_fields__ if key in data})


def _update(**changes) -> Status:
    with _status_lock:
        status = load()
        for key, value in changes.items():
            setattr(status, key, value)
        path = _status_path()
        # The temporary name starts with the file's name too, so a backup
        # written at this moment leaves it out as well.
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
        temporary.replace(path)
        return status


# -- Choosing -----------------------------------------------------------------


def done_folder_name() -> str:
    return _("Opgehaald")


def choose_folder(folder: Path) -> None:
    """Made at once, so it shows up on the phone before the first receipt."""
    try:
        folder.mkdir(exist_ok=True)
    except OSError as error:
        raise FolderError(
            _("Huismus kan de map %(folder)s niet maken.") % {"folder": folder}
        ) from error
    _start_over(source=FOLDER, folder=str(folder))


def choose_dropbox() -> None:
    """Bonnetjes in Dropbox › Apps › Huismus, made at once. FolderError
    without a linked Dropbox, or when Dropbox can't be reached."""
    folder = _make_cloud_folder(DROPBOX, _("Koppel eerst Dropbox bij Back-ups."))
    _start_over(source=DROPBOX, dropbox_folder=folder)


def choose_webdav() -> None:
    """Bonnetjes in the folder Huismus on the WebDAV server of the backups,
    made at once. FolderError without WebDAV set up, or when it can't be
    reached."""
    folder = _make_cloud_folder(WEBDAV, _("Stel eerst WebDAV in bij Back-ups."))
    _start_over(source=WEBDAV, webdav_folder=folder)


def _make_cloud_folder(service_name: str, not_linked: str) -> str:
    """Makes Bonnetjes, in the language of this moment, next to the
    backups of the linked service; its path."""
    if cloud_backups.load().service != service_name:
        raise FolderError(not_linked)
    service = cloud_backups.remote()
    folder = "/" + _("Bonnetjes")
    try:
        try:
            service.files_in(folder)
        except cloud_backups.NotFound:
            service.create_folder(folder)
    except cloud_backups.CloudError as error:
        raise FolderError(_cloud_sentence(service_name, error.reason)) from error
    return folder


def turn_off() -> None:
    """Huismus stops looking. The tray keeps what it fetched."""
    _start_over(source="")


def cloud_unlinked() -> None:
    """Unlinking Dropbox or WebDAV at Back-ups (core.cloud_views.unlink)
    turns the receipts folder off when it was there: linking again later
    doesn't quietly turn it back on."""
    if load().source in (DROPBOX, WEBDAV):
        turn_off()


def _start_over(**changes) -> None:
    """A new place (or none): its own field in changes, the others' wiped,
    and nothing remembered of the last look."""
    _update(
        folder="",
        dropbox_folder="",
        webdav_folder="",
        seen_until=timezone.now().isoformat(),
        done_folder=done_folder_name(),
        last_check="",
        last_failure="",
        failure_reason="",
        last_fetched=0,
        skipped=[],
    )
    _update(**changes)


def is_on(status: Status | None = None) -> bool:
    """A folder is chosen; Dropbox or WebDAV only while it is still the
    service linked at Back-ups (unlinking it there turns this off too)."""
    status = status or load()
    if status.source in (DROPBOX, WEBDAV):
        return cloud_backups.load().service == status.source
    return status.source == FOLDER


def place(status: Status | None = None) -> str:
    """Where Huismus looks, as the user knows it."""
    status = status or load()
    if status.source == FOLDER:
        return auto_backups.folder_label(status.folder)
    if status.source == DROPBOX:
        return "Dropbox › Apps › Huismus › " + status.dropbox_folder.strip("/")
    if status.source == WEBDAV:
        # As the backups' place: "https://… › Huismus", then the folder.
        backups = cloud_backups.place(cloud_backups.load())
        return f"{backups} › {status.webdav_folder.strip('/')}"
    return ""


def suggestions() -> list[tuple[str, Path]]:
    """Desktop app: a "Huismus bonnetjes" folder in each sync folder found.
    Docker: the folder linked at /bonnetjes, if there is one."""
    if not settings.DESKTOP:
        return [(_("Gekoppelde map"), LINKED_FOLDER)] if LINKED_FOLDER.is_dir() else []
    name = _("Huismus bonnetjes")
    return [(service, path / name) for service, path in auto_backups.sync_folders()]


def failure_sentence(status: Status) -> str:
    """Why the last look failed, for Bonnetjesmap and the tray."""
    if status.failure_reason == STORAGE:
        return _("Huismus kon een bonnetje niet bewaren. Is de schijf van Huismus vol?")
    if status.source in (DROPBOX, WEBDAV):
        return _cloud_sentence(status.source, status.failure_reason)
    return _("De map %(folder)s is niet bereikbaar. Is de schijf aangesloten?") % {
        "folder": place(status)
    }


def _cloud_sentence(service: str, reason: str) -> str:
    if service == WEBDAV:
        return _webdav_sentence(reason)
    return _dropbox_sentence(reason)


def _webdav_sentence(reason: str) -> str:
    # Refused and full say what Back-ups says (core.cloud_backups.failure_sentence).
    if reason == REFUSED:
        return _("Het wachtwoord werd geweigerd. Stel WebDAV opnieuw in bij Back-ups.")
    if reason == UNREACHABLE:
        return _("Huismus kon WebDAV niet bereiken.")
    if reason == FULL:
        return _("De opslag in %(service)s is vol.") % {"service": "WebDAV"}
    if reason == NOT_WEBDAV:
        return _("Op dit adres staat geen WebDAV meer. Stel WebDAV opnieuw in bij Back-ups.")
    return _("WebDAV gaf een fout. Huismus probeert het over 10 minuten opnieuw.")


def _dropbox_sentence(reason: str) -> str:
    if reason == REFUSED:
        return _("Dropbox weigert de toegang. Koppel Dropbox opnieuw bij Back-ups.")
    if reason == UNREACHABLE:
        return _("Huismus kon Dropbox niet bereiken.")
    if reason == FULL:
        return _("De opslag in Dropbox is vol.")
    return _("Dropbox gaf een fout. Huismus probeert het over 10 minuten opnieuw.")


def skip_sentence(reason: str) -> str:
    """Why a file stayed in the folder."""
    if reason == WRONG_TYPE:
        return _("Kies een PDF-, PNG-, JPG- of HEIC-bestand.")
    if reason == TOO_BIG:
        return _("Dit bonnetje is groter dan %(max_mb)s MB. Kies een kleiner bestand.") % {
            "max_mb": MAX_RECEIPT_BYTES // (1024 * 1024)
        }
    if reason == DAMAGED:
        return _("Huismus kan dit bestand niet openen.")
    return _("Huismus kan dit bestand niet lezen.")


# -- The places -----------------------------------------------------------------


class LocalFolder:
    def __init__(self, path: Path, done_folder: str):
        self.path = path
        self.done_folder = done_folder

    def names(self) -> list[tuple[str, int]]:
        """The files directly in the folder, with their size: not in its
        folders, no symlinks, nothing that changed in the last minute.
        OSError when the folder can't be read (a drive that's gone)."""
        if not self.path.is_dir():
            raise FileNotFoundError(errno.ENOENT, "map niet gevonden", str(self.path))
        settled = time.time() - SETTLE_SECONDS
        found = []
        with os.scandir(self.path) as entries:
            for entry in entries:
                if not entry.is_file(follow_symlinks=False):
                    continue
                info = entry.stat(follow_symlinks=False)
                if info.st_mtime <= settled:
                    found.append((entry.name, info.st_size))
        return found

    def read(self, name: str) -> bytes:
        return (self.path / name).read_bytes()

    def done(self, name: str) -> None:
        """To Opgehaald; a name taken there gets -2, -3: never overwritten."""
        done = self.path / self.done_folder
        done.mkdir(exist_ok=True)
        stem, suffix = os.path.splitext(name)
        target, count = done / name, 1
        while target.exists():
            count += 1
            target = done / f"{stem}-{count}{suffix}"
        os.replace(self.path / name, target)


class CloudFolder:
    """A folder next to the backups in Dropbox or on a WebDAV server. A file
    in Dropbox is whole once it is listed (Dropbox commits an upload at
    once). Not every WebDAV server waits like that, so a file it says it
    changed in the last minute waits for the next look, as in a folder on
    this computer; a server that gives no time isn't waited for."""

    def __init__(
        self, service: cloud_backups.Dropbox | cloud_backups.WebDAV, folder: str, done_folder: str
    ):
        self.service = service
        self.folder = folder
        self.done_folder = done_folder

    def names(self) -> list[tuple[str, int]]:
        """The files in the folder. Removed meanwhile: made again (empty),
        so the next receipt has a place."""
        try:
            found = self.service.files_in(self.folder)
        except cloud_backups.NotFound:
            self.service.create_folder(self.folder)
            return []
        settled = timezone.now() - timedelta(seconds=SETTLE_SECONDS)
        return [
            (file.name, file.size)
            for file in found
            if file.modified is None or file.modified <= settled
        ]

    def read(self, name: str) -> bytes:
        return self.service.read(f"{self.folder}/{name}")

    def done(self, name: str) -> None:
        # A name taken in Opgehaald gets another one, never overwritten:
        # "bon (1).jpg" in Dropbox, "bon-2.jpg" on WebDAV.
        self.service.move(f"{self.folder}/{name}", f"{self.folder}/{self.done_folder}/{name}")


def _place(status: Status):
    if status.source == FOLDER:
        return LocalFolder(Path(status.folder), status.done_folder)
    folder = status.dropbox_folder if status.source == DROPBOX else status.webdav_folder
    return CloudFolder(cloud_backups.remote(), folder, status.done_folder)


# -- Fetching -----------------------------------------------------------------------


def is_due(now: datetime | None = None) -> bool:
    """On, and ten minutes since the last look (or none yet)."""
    status = load()
    if not is_on(status):
        return False
    last = max(filter(None, [status.last_check_at, status.last_failure_at]), default=None)
    now = now or timezone.localtime()
    return last is None or now - last >= INTERVAL


def fetch(now: datetime | None = None) -> Result | None:
    """One look in the receipts folder. Result with how many receipts went
    to the tray and which files were left; None when nothing was looked at:
    off, the sample data in use (made-up and real records never mix),
    another look running, or a failure (recorded, and logged)."""
    if not _can_look():
        return None
    if not _fetch_lock.acquire(blocking=False):
        return None
    try:
        return _fetch(load(), now or timezone.localtime())
    finally:
        _fetch_lock.release()


def _can_look() -> bool:
    """On, and not with the sample data (made-up and real records never mix)."""
    return is_on() and not sample_data_in_use()


def fetching() -> bool:
    """A look is running: every ten minutes, or after "Nu ophalen"."""
    return _fetch_lock.locked()


def _start(work) -> None:
    """Runs work in its own thread; tests replace this to run it at once."""

    def run():
        try:
            work()
        finally:
            # A thread's own database connections stay open otherwise.
            connections.close_all()

    threading.Thread(target=run, name="huismus-receipts-now", daemon=True).start()


def fetch_in_background() -> bool:
    """ "Nu ophalen": a look without making the page wait for Dropbox
    (huismus-intern/besluiten.md, 2026-11-05). The lock is taken here, so
    the page that follows already sees fetching(). True when a look is
    running now, this one or one that already was."""
    if not _can_look():
        return False
    if not _fetch_lock.acquire(blocking=False):
        return True

    # From here the lock is held; the thread releases it when it is done
    # (or this function, if the thread doesn't start).

    def work():
        try:
            with maintenance.gate.request() as open_:
                if open_:
                    _fetch(load(), timezone.localtime())
        except Exception:
            logger.exception("Bonnetjes ophalen mislukt")
        finally:
            _fetch_lock.release()
        # Then the new receipts are read (SPEC.md M20, part 3), with the
        # look's lock free again, so "Bezig met ophalen…" doesn't stay up
        # while a service reads.
        reading.read_when_open()

    try:
        _start(work)
    except Exception:
        _fetch_lock.release()
        raise
    return True


def _fetch(status: Status, now: datetime) -> Result | None:
    place = _place(status)
    fetched, skipped = 0, []
    try:
        for name, size in sorted(place.names()):
            if name.startswith("."):
                # Hidden: iCloud's ".bon.jpg.icloud" for a file not
                # downloaded yet, macOS's .DS_Store.
                continue
            upload, reason = _receipt(place, name, size)
            if reason is not None:
                skipped.append({"name": name, "reason": reason})
                continue
            try:
                new = _store(upload)
            except OSError as error:
                # Huismus's own disk, not the folder: the file stays there.
                return _failed(now, STORAGE, error)
            fetched += new
            _done(place, name)
    except (OSError, cloud_backups.CloudError) as error:
        reason = error.reason if isinstance(error, cloud_backups.CloudError) else UNREACHABLE
        return _failed(now, reason, error)
    _update(
        last_check=now.isoformat(),
        last_fetched=fetched,
        skipped=skipped,
        # A status file from before the notice: new from this look on.
        seen_until=status.seen_until or now.isoformat(),
    )
    return Result(fetched, skipped)


def _failed(now: datetime, reason: str, error: Exception) -> None:
    """Recorded for the red line. What was skipped last time is forgotten:
    whether those files are still there can't be seen now."""
    logger.warning("Bonnetjes ophalen mislukt: %s", error)
    _update(last_failure=now.isoformat(), failure_reason=reason, skipped=[])


def _receipt(place, name: str, size: int) -> tuple[ContentFile | None, str | None]:
    """The file as an upload, checked like one (validate_receipt) and as
    Huismus keeps it (stored_receipt), or the reason it stays in the folder."""
    extension = PurePosixPath(name).suffix.lower().lstrip(".")
    if extension not in ACCEPTED_EXTENSIONS:
        return None, WRONG_TYPE
    if size > MAX_RECEIPT_BYTES:
        return None, TOO_BIG
    try:
        upload = ContentFile(place.read(name), name=name)
    except (OSError, cloud_backups.NotFound):
        return None, UNREADABLE
    try:
        validate_receipt(upload)
        # A HEIC becomes a JPG here; the original moves to Opgehaald.
        return stored_receipt(upload), None
    except ValidationError:
        return None, DAMAGED


def _store(upload: ContentFile) -> bool:
    """Saves the receipt in the tray; False when Huismus already has a
    receipt with the same content (in the tray or on an expense)."""
    sha256 = sha256_of(upload)
    if Attachment.objects.filter(kind="receipt", sha256=sha256).exists():
        return False
    Attachment.objects.create(file=upload, kind="receipt", sha256=sha256, source=SOURCE)
    return True


def _done(place, name: str) -> None:
    """Moves a receipt that is in Huismus to Opgehaald. A failure is no
    reason for red: the next look finds it again and moves it then."""
    try:
        place.done(name)
    except (OSError, cloud_backups.CloudError) as error:
        logger.warning("Bonnetje %s niet verplaatst: %s", name, error)


# -- "2 nieuwe bonnetjes" ---------------------------------------------------------


def new_receipts() -> int:
    """Receipts the folder brought in since the last visit to the tray that
    still wait for an expense; 0 when the folder is off or with the sample
    data. Only reads: the overview asks every 30 seconds."""
    status = load()
    if not status.seen_until or not is_on(status) or sample_data_in_use():
        return 0
    receipts = Attachment.objects.in_tray().filter(
        source=SOURCE, created_at__gt=datetime.fromisoformat(status.seen_until)
    )
    if reading.is_on() and not reading.load().failed:
        # Huismus reads them: only those it left in the tray are new here;
        # the others become "n nieuwe uitgaven om na te kijken".
        receipts = receipts.filter(read_at__isnull=False)
    return receipts.count()


def seen() -> None:
    """The tray was opened: nothing is new any more. Written only when
    something was, so an ordinary visit writes nothing. A receipt fetched
    between the count and the write counts as seen: the tray, rendered
    after this, shows it."""
    if new_receipts():
        _update(seen_until=timezone.now().isoformat())


def fetch_when_open() -> Result | None:
    """A look now, unless a backup is being restored: what expenses.watch
    starts when something new is in the folder."""
    with maintenance.gate.request() as open_:
        result = fetch() if open_ else None
    reading.read_when_open()
    return result


def fetch_if_due(at_start: bool = False) -> Result | None:
    """What the thread calls: a look if it's time (or the app just
    started), never while a backup is being restored."""
    with maintenance.gate.request() as open_:
        if not open_ or not (at_start or is_due()):
            return None
        result = fetch()
    # Also after a look that brought nothing: a receipt left waiting by a
    # failing service is tried again (SPEC.md M20, part 3).
    reading.read_when_open()
    return result


def start_thread() -> threading.Thread:
    """At start, then every minute whether it's time (INTERVAL). The
    desktop app (desktop/app.py) and gunicorn's one worker
    (gunicorn.conf.py) start it once."""

    def every_minute():
        at_start = True
        while True:
            try:
                fetch_if_due(at_start)
            except Exception:
                logger.exception("Bonnetjes ophalen mislukt")
            finally:
                connections.close_all()
            at_start = False
            time.sleep(60)

    thread = threading.Thread(target=every_minute, name="huismus-receipts", daemon=True)
    thread.start()
    return thread
