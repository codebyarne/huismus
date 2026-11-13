# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Updates in the desktop app (SPEC.md M11; huismus-intern/besluiten.md, 2026-10-29).

The app looks in GitHub Releases for a newer version: the one outgoing
request Huismus makes (SPEC.md principle 6), and it can be turned off. It
fetches only the public release list and sends nothing but a User-Agent.
When it finds a newer version it downloads it in the background and
checks it against the SHA-256 GitHub lists for the file (prepare). The
next time the app opens, before the window shows Huismus, it makes a
backup and hands the file to the desktop shell, which replaces the app
and starts it again (install_at_start, desktop/updater.py); never in the
middle of a session. "Bijwerken" on Instellingen → Updates does the same
right away. The first start of the new version runs the migrations; if
they fail, the shell offers to restore that backup
(huismus-intern/besluiten.md, 2026-11-04).

On a Mac a new version may ask a newer macOS than this one has (0.1.4 asked
15 instead of 14). After downloading, the shell reads the minimum from the
new app (minimum_os, desktop/updater.py); on an older macOS the current
version stays and Instellingen → Updates says to update macOS first
(needs_macos; issue #155).

Whether to look and what was found belong to this computer, like the
backup folder: a small file next to the database that no backup carries
(UPDATE_STATUS_FILE_NAME).

Huismus in Docker looks too, from gunicorn's worker (start_hourly_thread),
but only to say so: the overview and Instellingen → Updates name the new
version and what to type. It never downloads or replaces anything; the
user updates with `docker compose pull` (huismus-intern/besluiten.md,
2026-11-04).
"""

import hashlib
import json
import logging
import os
import platform
import re
import sys
import threading
import time
import tomllib
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .backup import UPDATE_STATUS_FILE_NAME

logger = logging.getLogger("huismus.updates")

RELEASES_URL = "https://api.github.com/repos/codebyarne/huismus/releases"
# The file a release carries for each platform (built by release.yml).
ASSET_NAMES = {
    "darwin": "Huismus-{version}-macos.dmg",
    "win32": "Huismus-{version}-windows.exe",
}
CHECK_EVERY = timedelta(hours=24)
TIMEOUT_SECONDS = 15
# Far above a real release (about 45 MB) and its list.
MAX_DOWNLOAD_BYTES = 500_000_000
MAX_LIST_BYTES = 5_000_000
VERSION_TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")

_status_lock = threading.Lock()


class UpdateError(Exception):
    """Updating stopped before anything changed. Its code (str(error)) says
    why; core.update_views turns it into a sentence."""


@dataclass
class Release:
    version: str
    page_url: str
    asset_url: str
    asset_name: str
    sha256: str  # "" when GitHub lists none: then it can't be installed


@dataclass
class Status:
    enabled: bool = True
    last_check: str = ""  # ISO timestamp
    available: dict = field(default_factory=dict)  # a Release, or {}
    # Set just before the app replaces itself; read by the new version's
    # first start (desktop/app.py), then cleared.
    pending: dict = field(default_factory=dict)  # from_version, to_version, backup
    # For the overview's toast after the next start: the version that didn't
    # get installed (desktop/app.py).
    not_installed: str = ""
    # The checked file that waits for the next start (prepare): version,
    # path, sha256, minimum_os (the oldest macOS it opens on, "" if unknown).
    downloaded: dict = field(default_factory=dict)
    # When downloading last failed (ISO timestamp): tried again a day later.
    download_failed: str = ""
    # The version that didn't get installed automatically once: the next
    # starts leave it to the button on Updates (install_at_start).
    auto_failed: str = ""
    # The version whose "Huismus is bijgewerkt" notice was closed or whose
    # "Wat is er nieuw" was opened: the overview's notice stays until then
    # (updated_to). "" until the overview first had something to say.
    seen_version: str = ""

    @property
    def release(self) -> Release | None:
        return Release(**self.available) if self.available else None


def current_version() -> str:
    """From pyproject.toml, which the desktop app carries too
    (desktop/huismus.spec)."""
    pyproject = Path(settings.BASE_DIR) / "pyproject.toml"
    return tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"]


def asset_name(version: str) -> str:
    """This computer's file in a release. The macOS one anywhere else too:
    Docker never updates, and the tests run on Linux."""
    return ASSET_NAMES.get(sys.platform, ASSET_NAMES["darwin"]).format(version=version)


def _parse(version: str) -> tuple[int, int, int] | None:
    match = VERSION_TAG.match(version if version.startswith("v") else f"v{version}")
    return tuple(int(part) for part in match.groups()) if match else None


def is_newer(version: str, than: str) -> bool:
    new, old = _parse(version), _parse(than)
    return new is not None and old is not None and new > old


# -- The status file ----------------------------------------------------------


def _status_path() -> Path:
    return Path(settings.DATA_DIR) / UPDATE_STATUS_FILE_NAME


def load_status() -> Status:
    try:
        data = json.loads(_status_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Status()
    except ValueError:
        # Damaged: don't look for updates rather than assume it was on.
        logger.warning("%s is beschadigd; zoeken naar updates staat uit", _status_path())
        return Status(enabled=False)
    known = {key: data[key] for key in Status.__dataclass_fields__ if key in data}
    return Status(**known)


def update_status(**changes) -> Status:
    with _status_lock:
        status = load_status()
        for key, value in changes.items():
            setattr(status, key, value)
        path = _status_path()
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
        temporary.replace(path)
        return status


# -- Looking for a new version ------------------------------------------------


def _test_list() -> str:
    """HUISMUS_RELEASES_URL: a fake list for tests and the demo server.
    Never in the packaged app (huismus-intern/besluiten.md, 2026-10-29)."""
    if getattr(sys, "frozen", False):
        return ""
    return os.environ.get("HUISMUS_RELEASES_URL", "")


def releases_url() -> str:
    return _test_list() or RELEASES_URL


def _fetch(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "Huismus"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return response.read(MAX_LIST_BYTES)


def newest_release(releases: list, current: str) -> Release | None:
    """The newest release that isn't a draft or pre-release, is newer than
    the current version, and has a file for this platform. In Docker any
    such release counts: its image is published with it, and it carries no
    file to download."""
    best = None
    for entry in releases:
        if entry.get("draft") or entry.get("prerelease"):
            continue
        tag = entry.get("tag_name", "")
        if not is_newer(tag, current):
            continue
        version = tag.removeprefix("v")
        wanted = asset_name(version)
        asset = next((a for a in entry.get("assets", []) if a.get("name") == wanted), None)
        if not settings.DESKTOP:
            asset, wanted = {}, ""
        elif asset is None:
            continue
        digest = asset.get("digest") or ""
        release = Release(
            version=version,
            page_url=entry.get("html_url", ""),
            asset_url=asset.get("browser_download_url", ""),
            asset_name=wanted,
            sha256=digest.removeprefix("sha256:").lower() if digest.startswith("sha256:") else "",
        )
        if best is None or is_newer(release.version, best.version):
            best = release
    return best


def check(now: datetime | None = None) -> Release | None:
    """Fetches the release list and records what's available. Silent on a
    network error (no internet): the last result stays."""
    try:
        return look_now(now)
    except UpdateError:
        return load_status().release


def look_now(now: datetime | None = None) -> Release | None:
    """check(), but UpdateError("look") when GitHub can't be reached, so
    "Nu zoeken" on Instellingen → Updates can say so."""
    now = now or timezone.localtime()
    try:
        releases = json.loads(_fetch(releases_url()))
    except (OSError, ValueError) as error:
        logger.info("Zoeken naar een nieuwe versie lukte niet: %s", error)
        raise UpdateError("look") from error
    release = newest_release(releases if isinstance(releases, list) else [], current_version())
    update_status(last_check=now.isoformat(), available=asdict(release) if release else {})
    return release


def check_if_due(now: datetime | None = None) -> None:
    """At start and once a day after (desktop/app.py, start_hourly_thread),
    if it's on."""
    status = load_status()
    if not status.enabled:
        return
    now = now or timezone.localtime()
    last = datetime.fromisoformat(status.last_check) if status.last_check else None
    if last is None or now - last >= CHECK_EVERY:
        check(now)


def available() -> Release | None:
    """What the overview and Instellingen → Updates show: a newer version,
    found earlier, and only while looking is on."""
    status = load_status()
    release = status.release
    if not status.enabled or release is None:
        return None
    # Found by an older version than this one (after updating by hand).
    return release if is_newer(release.version, current_version()) else None


# -- "Huismus is bijgewerkt" ---------------------------------------------------


def updated_to() -> str:
    """The version the overview's notice says Huismus was updated to: the
    running one, until it's seen (seen). In the desktop app after it
    updated itself, in Docker after `docker compose pull`. Without a seen
    version an administration from before this notice gets it once; a new
    one never does, as the overview marks the version seen first
    (core.views._updated_to). "" when there is nothing to say."""
    seen_version = load_status().seen_version
    current = current_version()
    if not seen_version or is_newer(current, seen_version):
        return current
    if seen_version != current:
        # An older version put back by hand: nothing new about it, and the
        # next newer one gets the notice again.
        seen()
    return ""


def seen() -> None:
    """The notice was closed, or "Wat is er nieuw" opened."""
    if load_status().seen_version != current_version():
        update_status(seen_version=current_version())


# -- Downloading ahead ---------------------------------------------------------


def _update_folder() -> Path:
    folder = Path(settings.DATA_DIR).parent / ".huismus-update"
    folder.mkdir(exist_ok=True)
    return folder


def _forget_download(status: Status) -> None:
    if status.downloaded.get("path"):
        Path(status.downloaded["path"]).unlink(missing_ok=True)
    update_status(downloaded={})


def prepare(now: datetime | None = None) -> None:
    """After a check (desktop/app.py): downloads and checks a newer
    version, so the next start can install it. Silent when that fails;
    tried again a day later. Never in Docker."""
    release = available()
    if release is None or not settings.DESKTOP:
        return
    status = load_status()
    if status.downloaded.get("version") == release.version and _waiting_file(status):
        return
    now = now or timezone.localtime()
    if status.download_failed:
        if now - datetime.fromisoformat(status.download_failed) < CHECK_EVERY:
            return
    if status.downloaded:
        # An older new version: this one replaces it.
        _forget_download(status)
    try:
        path = download(release, _update_folder())
    except UpdateError as error:
        logger.info("Downloaden van %s lukte niet: %s", release.version, error)
        update_status(download_failed=now.isoformat())
        return
    _keep_download(release, path)


def _keep_download(release: Release, path: Path) -> str:
    """Records the checked file for the next start, with the oldest macOS
    it opens on, and returns that minimum."""
    minimum = _read_minimum_os(path)
    update_status(
        downloaded={
            "version": release.version,
            "path": str(path),
            "sha256": release.sha256,
            "minimum_os": minimum,
        },
        download_failed="",
    )
    return minimum


def _waiting_file(status: Status) -> Path | None:
    path = Path(status.downloaded.get("path", ""))
    return path if status.downloaded and path.is_file() else None


def waiting() -> Release | None:
    """The new version that is downloaded and will be installed at the
    next start: what the overview and Updates say "staat klaar" about.
    Not while it needs a newer macOS (needs_macos)."""
    release = available()
    status = load_status()
    if release is None or status.auto_failed == release.version or needs_macos():
        return None
    if status.downloaded.get("version") != release.version or not _waiting_file(status):
        return None
    return release


def downloading() -> Release | None:
    """A newer version found and not downloaded yet: what the overview
    says "wordt gedownload" about. Not after a failed download (no
    internet; tried again a day later) or a failed automatic install: then
    the plain notice."""
    release = available()
    status = load_status()
    if release is None or status.auto_failed == release.version or status.download_failed:
        return None
    if not settings.DESKTOP or needs_macos():
        return None
    return None if waiting() is not None else release


# -- A newer macOS ------------------------------------------------------------

# Set by the desktop shell on a Mac (desktop/app.py, App.boot): a function
# that reads the oldest macOS a downloaded package opens on
# (LSMinimumSystemVersion), "" when it names none. None on Windows, in
# Docker and in tests: then nothing is held back.
minimum_os = None


def _read_minimum_os(package: Path) -> str:
    """The minimum from minimum_os, or "" when there is no reader or it
    can't read the package: then updating goes as before, and installing
    would fail on that package anyway."""
    if minimum_os is None:
        return ""
    try:
        return minimum_os(package) or ""
    except Exception:
        logger.exception("Huismus kon niet lezen welke macOS %s nodig heeft", package)
        return ""


def this_macos() -> str:
    """This Mac's macOS version, like "14.6.1"; "" anywhere else."""
    return platform.mac_ver()[0] if sys.platform == "darwin" else ""


def _macos_parts(version: str) -> tuple[int, ...] | None:
    parts = version.split(".")
    if not all(part.isdigit() for part in parts):
        return None
    while len(parts) > 1 and parts[-1] == "0":
        parts.pop()
    return tuple(int(part) for part in parts)


def older_macos(this: str, minimum: str) -> bool:
    """True when this macOS is older than minimum. False when either is
    unknown: then nothing is held back."""
    this_parts, minimum_parts = _macos_parts(this), _macos_parts(minimum)
    if this_parts is None or minimum_parts is None:
        return False
    return this_parts < minimum_parts


# The names macOS shows next to its number, for "macOS 15 (Sequoia)"
# (huismus-intern/besluiten.md, 2026-11-13). Another number gets no name.
MACOS_NAMES = {"15": "Sequoia", "26": "Tahoe"}


def macos_label(version: str) -> str:
    """ "15 (Sequoia)" for "15", or the number alone."""
    name = MACOS_NAMES.get(version)
    return f"{version} ({name})" if name else version


def needs_macos(minimum: str | None = None) -> str:
    """The macOS the downloaded new version needs, as the user reads it
    ("15", not "15.0"), when this Mac's is older; "" otherwise. Without
    minimum, the one recorded for the available version."""
    if minimum is None:
        release = available()
        downloaded = load_status().downloaded
        if release is None or downloaded.get("version") != release.version:
            return ""
        minimum = downloaded.get("minimum_os", "")
    if not older_macos(this_macos(), minimum):
        return ""
    return ".".join(str(part) for part in _macos_parts(minimum))


def start_hourly_thread() -> threading.Thread:
    """On Docker: a look for a new version when the server starts and then
    once a day, if it's on. gunicorn calls this once in its one worker
    (gunicorn.conf.py), next to the backups' thread."""
    thread = threading.Thread(target=look_every_hour, name="huismus-updates", daemon=True)
    thread.start()
    return thread


def look_every_hour() -> None:
    while True:
        try:
            check_if_due()
        except Exception:
            logger.exception("Zoeken naar een nieuwe versie mislukt")
        time.sleep(60 * 60)


def turn_off() -> None:
    """The switch off: no more requests, and a waiting version goes."""
    _forget_download(update_status(enabled=False))


# -- Installing ---------------------------------------------------------------

# Set by the desktop shell once its server runs (desktop/app.py, App.boot):
# a function that takes the checked file, starts replacing the app and
# closes it, or raises UpdateError. None outside the packaged app (on
# Docker, in tests, on the demo server): then install() says updating only
# works in the app.
installer = None
# Also set by the desktop shell: raises UpdateError when the app can't
# replace itself where it is, so no download or backup is spent on it.
precheck = None


def download(release: Release, folder: Path) -> Path:
    """Downloads the release's file to folder and checks its SHA-256.
    UpdateError, and no file left, when either fails."""
    if not release.sha256:
        raise UpdateError("no-digest")
    # Only HTTPS, also after GitHub's redirect to its file storage; a fake
    # list (tests, the demo server) may use file:// instead.
    https = release.asset_url.startswith("https://")
    if not https and not _test_list():
        raise UpdateError("not-https")
    target = folder / release.asset_name
    digest = hashlib.sha256()
    size = 0
    try:
        request = urllib.request.Request(release.asset_url, headers={"User-Agent": "Huismus"})
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if https and not response.geturl().startswith("https://"):
                raise UpdateError("not-https")
            with target.open("wb") as file:
                while chunk := response.read(1 << 16):
                    size += len(chunk)
                    if size > MAX_DOWNLOAD_BYTES:
                        raise UpdateError("download")
                    digest.update(chunk)
                    file.write(chunk)
    except UpdateError:
        target.unlink(missing_ok=True)
        raise
    except OSError as error:
        target.unlink(missing_ok=True)
        raise UpdateError("download") from error
    if digest.hexdigest() != release.sha256.lower():
        target.unlink(missing_ok=True)
        raise UpdateError("digest")
    return target


def _downloaded(release: Release) -> Path | None:
    """The file prepare() downloaded for this release, if it still has the
    right SHA-256."""
    status = load_status()
    path = _waiting_file(status)
    if path is None or status.downloaded.get("version") != release.version:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as file:
        while chunk := file.read(1 << 16):
            digest.update(chunk)
    if digest.hexdigest() != release.sha256.lower():
        path.unlink(missing_ok=True)
        return None
    return path


def release_page(version: str) -> str:
    """Where a version can be downloaded by hand (the previous one, after
    a failed update)."""
    return f"https://github.com/codebyarne/huismus/releases/tag/v{version}"


def install(release: Release) -> None:
    """ "Bijwerken": download and check, back up, then hand over to the
    desktop shell, which closes the app, replaces it and starts the new
    version. UpdateError when something stops it; until the hand-over
    nothing has changed."""
    from . import auto_backups

    if installer is None:
        raise UpdateError("no-installer")
    if precheck is not None:
        precheck()
    waiting_file = _downloaded(release)
    package = waiting_file or download(release, _update_folder())
    # Read again, also for a file downloaded ahead: the last check before
    # anything changes. Kept, so Updates can say which macOS it needs.
    if needs_macos(_keep_download(release, package)):
        raise UpdateError("macos")
    try:
        backup = auto_backups.safety_backup()
    except auto_backups.SafetyBackupError as error:
        if waiting_file is None:
            package.unlink(missing_ok=True)
        raise UpdateError("backup") from error
    update_status(
        pending={
            "from_version": current_version(),
            "to_version": release.version,
            "backup": str(backup),
        }
    )
    try:
        installer(package, release.sha256)
    except Exception as error:
        # Nothing replaced: no update to look for at the next start.
        update_status(pending={})
        package.unlink(missing_ok=True)
        if isinstance(error, UpdateError):
            raise
        logger.exception("De installer kon niet beginnen")
        raise UpdateError("install") from error


def install_at_start() -> bool:
    """At the start of the app, before the window shows Huismus
    (desktop/app.py): installs the version that waits, if any. True when
    the shell took over and closes. A version that fails here isn't tried
    again at the next start; the overview says once that it didn't work.
    A failed backup is the exception: nothing was tried, so the next start
    tries again, and the overview's backup warning says what's wrong with
    the folder (huismus-intern/besluiten.md, 2026-11-04)."""
    release = waiting()
    if release is None or installer is None:
        return False
    try:
        install(release)
    except UpdateError as error:
        logger.warning("Automatisch bijwerken naar %s lukte niet: %s", release.version, error)
        if str(error) in ("backup", "macos"):
            # Nothing was tried. A failed backup: the overview's backup
            # warning says why. A newer macOS: Updates says so, and it's
            # installed once macOS is updated.
            return False
        update_status(auto_failed=release.version, not_installed=release.version)
        return False
    return True
