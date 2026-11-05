# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Backups straight to a cloud service: Dropbox or WebDAV (SPEC.md M15,
step 2; huismus-intern/besluiten.md, 2026-10-31).

Once a day, like the folder (core.auto_backups), Huismus makes a backup,
encrypts it with the recovery code and uploads it to the one service the
user linked. Encrypted in the open age format, so the file can also be
opened without Huismus (`age -d`, with the recovery code as passphrase).

What this installation knows about the link (which service, its secrets,
how the last upload went) is in data/cloud-backup.json, and the recovery
code in data/cloud-backup-code: both owner-only (core.private_files), both
left out of every backup (core.backup skips names starting with
FILE_PREFIX), like the mail password. Unlinking keeps the code: linking
again later encrypts with the same one.

Huismus only talks to the service the user linked, and only from here
(SPEC.md principle 6, like the update check).
"""

import base64
import hashlib
import json
import logging
import re
import secrets
import sqlite3
import tarfile
import tempfile
import threading
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from defusedxml import ElementTree
from django.conf import settings
from django.db import connections
from django.utils import timezone
from django.utils.translation import gettext as _
from pyrage import DecryptError, passphrase

from . import maintenance
from .backup import CLOUD_FILE_PREFIX, BackupError, create_backup, sample_data_in_use
from .private_files import write_owner_only

FILE_PREFIX = CLOUD_FILE_PREFIX
CONFIG_FILE_NAME = f"{FILE_PREFIX}.json"
CODE_FILE_NAME = f"{FILE_PREFIX}-code"

DROPBOX, WEBDAV = "dropbox", "webdav"
# Why an upload or a check failed; the views turn these into sentences.
REFUSED, UNREACHABLE, NOT_WEBDAV, FULL, OTHER = (
    "refused",
    "unreachable",
    "not_webdav",
    "full",
    "other",
)

# core.backup's archive name with ".age" after it. Huismus only ever
# removes files with such a name from the cloud.
CLOUD_ARCHIVE_NAME = re.compile(r"^huismus-backup-(\d{8}-\d{6})(?:-(\d+))?\.tar\.gz\.age$")
# WebDAV: the folder on the given address where the backups go.
WEBDAV_FOLDER = "Huismus"
TIMEOUT = 60  # seconds per network step; an upload sends in steps too

# The recovery code: 24 characters without the ones that look alike
# (0/O, 1/I/L), shown in six groups of four (huismus-intern/besluiten.md).
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 24

_lock = threading.Lock()
# One upload at a time: the hourly thread and "Ik heb de code bewaard".
_upload_lock = threading.Lock()
logger = logging.getLogger("huismus.backups")


class CloudError(Exception):
    """A service said no, or couldn't be reached; reason is one of the
    constants above, the message is for the log."""

    def __init__(self, reason: str, message: str = ""):
        super().__init__(message or reason)
        self.reason = reason


class NotFound(CloudError):
    """Dropbox: no such file or folder."""


class CodeError(ValueError):
    """A recovery code that isn't one; the message is for the user."""


@dataclass
class Config:
    service: str = ""  # DROPBOX or WEBDAV; "" when nothing is linked
    code_confirmed: bool = False  # the user saw and saved the code
    dropbox_refresh_token: str = ""
    webdav_url: str = ""
    webdav_username: str = ""
    webdav_password: str = ""
    last_success: str = ""  # ISO timestamps, as in core.auto_backups
    last_failure: str = ""
    failure_reason: str = ""
    last_size: int = 0

    @property
    def last_success_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_success) if self.last_success else None

    @property
    def last_failure_at(self) -> datetime | None:
        return datetime.fromisoformat(self.last_failure) if self.last_failure else None

    @property
    def failed(self) -> bool:
        failure, success = self.last_failure_at, self.last_success_at
        return failure is not None and (success is None or failure > success)

    @property
    def service_label(self) -> str:
        return {DROPBOX: "Dropbox", WEBDAV: "WebDAV"}.get(self.service, "")


@dataclass(frozen=True)
class RemoteFile:
    name: str
    size: int

    @property
    def created_at(self) -> datetime | None:
        match = CLOUD_ARCHIVE_NAME.match(self.name)
        return datetime.strptime(match[1], "%Y%m%d-%H%M%S") if match else None

    @property
    def order(self) -> tuple:
        """created_at, then the number after it: of two in one second, the
        one with -2 is the later. Only for Huismus's own archives."""
        number = CLOUD_ARCHIVE_NAME.match(self.name)[2]
        return self.created_at, int(number or 1)


# -- What this installation knows ------------------------------------------


def _config_path() -> Path:
    return Path(settings.DATA_DIR) / CONFIG_FILE_NAME


def _code_path() -> Path:
    return Path(settings.DATA_DIR) / CODE_FILE_NAME


def load() -> Config:
    try:
        data = json.loads(_config_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return Config()
    defaults = asdict(Config())
    return Config(**{key: data.get(key, default) for key, default in defaults.items()})


def _save(config: Config) -> None:
    write_owner_only(_config_path(), json.dumps(asdict(config), indent=2))


def _update(**changes) -> Config:
    with _lock:
        config = load()
        for key, value in changes.items():
            setattr(config, key, value)
        _save(config)
        return config


def link_dropbox(refresh_token: str) -> None:
    _link(service=DROPBOX, dropbox_refresh_token=refresh_token)


def link_webdav(url: str, username: str, password: str) -> None:
    _link(service=WEBDAV, webdav_url=url, webdav_username=username, webdav_password=password)


def _link(**fields) -> None:
    """A new link starts without the old one's secrets or history. Whether
    the code is confirmed carries over: it is the same code."""
    with _lock:
        config = Config(code_confirmed=load().code_confirmed and bool(code()), **fields)
        _save(config)


def unlink() -> None:
    """Forgets the service; what is in the cloud stays there. The code
    stays too (huismus-intern/besluiten.md, 2026-10-31)."""
    config = load()
    if config.service == DROPBOX and config.dropbox_refresh_token:
        try:
            Dropbox(config.dropbox_refresh_token).revoke()
        except CloudError:
            # Revoked already, or Dropbox unreachable: the link is gone
            # here either way, and the user can remove it at Dropbox.
            pass
    with _lock:
        _save(Config(code_confirmed=config.code_confirmed))


def is_linked() -> bool:
    return bool(load().service)


def is_ready() -> bool:
    """Linked, and the user saw the recovery code: then uploads start."""
    config = load()
    return bool(config.service) and config.code_confirmed and bool(code())


# -- The recovery code -------------------------------------------------------


def code() -> str:
    """The code, normalised (core.cloud_backups.normalise_code); "" if none."""
    try:
        return _code_path().read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""


def new_code() -> str:
    """A new code, only when there is none: one that encrypted backups in
    the cloud must never be replaced unasked."""
    with _lock:
        existing = code()
        if existing:
            return existing
        value = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
        write_owner_only(_code_path(), value)
        return value


def use_code(text: str) -> None:
    """The code of an earlier installation, typed in (CodeError if it isn't
    one). Replaces this installation's code, and counts as confirmed."""
    value = normalise_code(text)
    with _lock:
        write_owner_only(_code_path(), value)
        config = load()
        config.code_confirmed = True
        _save(config)


def confirm_code() -> None:
    _update(code_confirmed=True)


def normalise_code(text: str) -> str:
    """Spaces, dashes and small letters don't matter when typing it in."""
    value = re.sub(r"[\s-]", "", text).upper()
    if len(value) != CODE_LENGTH or any(char not in CODE_ALPHABET for char in value):
        raise CodeError(_("Dit is geen herstelcode. Een herstelcode heeft 24 letters en cijfers."))
    return value


def grouped(value: str) -> str:
    """K7QM 8XWR 3HTP V9CN 4FJD 2BYE: how the code is shown."""
    return " ".join(value[index : index + 4] for index in range(0, len(value), 4))


def encrypt(data: bytes, recovery_code: str) -> bytes:
    return passphrase.encrypt(data, recovery_code)


def decrypt(data: bytes, recovery_code: str) -> bytes:
    """CodeError when the data was encrypted with another code (or isn't
    an age file at all)."""
    try:
        return passphrase.decrypt(data, recovery_code)
    except DecryptError as error:
        raise CodeError(_("Deze back-up is met een andere herstelcode versleuteld.")) from error


# -- Talking to a service ----------------------------------------------------


def _open(request: urllib.request.Request) -> tuple[int, bytes]:
    """One HTTP request; the status and body, also for an error status. The
    one place this module goes on the network, so tests replace it."""
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise CloudError(UNREACHABLE, str(error)) from error
    except (ValueError, UnicodeError) as error:
        # An address urllib can't even send to: a host name with a part
        # longer than 63 characters, or "https://./".
        raise CloudError(UNREACHABLE, str(error)) from error


def _oauth_refusal(body: bytes) -> str:
    """Why a token request was refused, for the log: only the kind of
    error and its short description ("invalid_grant: code has expired"),
    never the rest of the answer (huismus-intern/besluiten.md, 2026-11-01)."""
    try:
        data = json.loads(body)
    except ValueError:
        return "refused"
    if not isinstance(data, dict):
        return "refused"
    kind = str(data.get("error", "refused"))[:60]
    description = str(data.get("error_description", ""))[:200]
    return f"{kind}: {description}" if description else kind


def _json(body: bytes) -> dict:
    """A service's JSON answer; CloudError when it isn't what was asked."""
    try:
        data = json.loads(body)
    except ValueError as error:
        raise CloudError(OTHER, f"geen JSON: {body[:200]!r}") from error
    if not isinstance(data, dict):
        raise CloudError(OTHER, f"onverwacht antwoord: {body[:200]!r}")
    return data


def _reason_for(status: int) -> str:
    if status in (401, 403):
        return REFUSED
    if status == 507:
        return FULL
    return OTHER


class WebDAV:
    """Nextcloud, kDrive, Koofr, Hetzner Storage Box, pCloud and others:
    plain HTTP verbs on a folder WEBDAV_FOLDER below the given address."""

    def __init__(self, url: str, username: str, password: str):
        self.base = url if url.endswith("/") else url + "/"
        self.folder = self.base + WEBDAV_FOLDER + "/"
        token = base64.b64encode(f"{username}:{password}".encode()).decode()
        self.auth = f"Basic {token}"

    def _request(self, method: str, url: str, data: bytes | None = None, **headers) -> tuple:
        request = urllib.request.Request(url, data=data, method=method)
        request.add_header("Authorization", self.auth)
        for name, value in headers.items():
            request.add_header(name.replace("_", "-"), value)
        return _open(request)

    def check(self) -> None:
        """Can Huismus write here? Makes the folder if it isn't there."""
        status, _body = self._request("PROPFIND", self.base, Depth="0")
        if status in (404, 405, 501):
            raise CloudError(NOT_WEBDAV, f"PROPFIND {status}")
        if status >= 400:
            raise CloudError(_reason_for(status), f"PROPFIND {status}")
        status, _body = self._request("MKCOL", self.folder)
        # 405: the folder exists already.
        if status >= 400 and status != 405:
            raise CloudError(_reason_for(status), f"MKCOL {status}")

    def upload(self, name: str, data: bytes) -> None:
        def put():
            url = self.folder + urllib.parse.quote(name)
            return self._request("PUT", url, data, Content_Type="application/octet-stream")

        status, _body = put()
        if status == 404 or status == 409:
            # The folder is gone (removed by the user): make it, once more.
            self.check()
            status, _body = put()
        if status >= 400:
            raise CloudError(_reason_for(status), f"PUT {status}")

    def list(self) -> list[RemoteFile]:
        status, body = self._request("PROPFIND", self.folder, Depth="1")
        if status == 404:
            return []
        if status >= 400:
            raise CloudError(_reason_for(status), f"PROPFIND {status}")
        found = []
        try:
            root = ElementTree.fromstring(body)
        except ElementTree.ParseError as error:
            raise CloudError(NOT_WEBDAV, str(error)) from error
        for response in root.iter("{DAV:}response"):
            href = response.findtext("{DAV:}href") or ""
            name = urllib.parse.unquote(href.rstrip("/").rsplit("/", 1)[-1])
            length = response.findtext(".//{DAV:}getcontentlength")
            if CLOUD_ARCHIVE_NAME.match(name):
                found.append(RemoteFile(name, int(length) if length and length.isdigit() else 0))
        return found

    def download(self, name: str) -> bytes:
        status, body = self._request("GET", self.folder + urllib.parse.quote(name))
        if status >= 400:
            raise CloudError(_reason_for(status), f"GET {status}")
        return body

    def delete(self, name: str) -> None:
        status, _body = self._request("DELETE", self.folder + urllib.parse.quote(name))
        if status >= 400 and status != 404:
            raise CloudError(_reason_for(status), f"DELETE {status}")


class Dropbox:
    """Dropbox with access to its app folder only (Apps › Huismus), signed
    in with PKCE: no app secret (huismus-intern/cloud-registratie.md)."""

    AUTHORIZE = "https://www.dropbox.com/oauth2/authorize"
    TOKEN = "https://api.dropboxapi.com/oauth2/token"
    API = "https://api.dropboxapi.com/2/"
    CONTENT = "https://content.dropboxapi.com/2/"
    # Dropbox takes at most 150 MB in one upload; bigger goes in parts.
    CHUNK = 64 * 1024 * 1024

    def __init__(self, refresh_token: str):
        self.refresh_token = refresh_token
        self._access_token = ""

    # Signing in -------------------------------------------------------

    @staticmethod
    def new_verifier() -> str:
        return secrets.token_urlsafe(64)

    @classmethod
    def authorize_url(cls, verifier: str) -> str:
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
        query = {
            "client_id": settings.DROPBOX_APP_KEY,
            "response_type": "code",
            "code_challenge": challenge.decode().rstrip("="),
            "code_challenge_method": "S256",
            # A refresh token, so the nightly upload needs no one to sign in.
            "token_access_type": "offline",
        }
        return f"{cls.AUTHORIZE}?{urllib.parse.urlencode(query)}"

    @classmethod
    def exchange(cls, authorization_code: str, verifier: str) -> str:
        """The refresh token for the code Dropbox showed the user."""
        data = cls._token(
            grant_type="authorization_code",
            code=authorization_code.strip(),
            code_verifier=verifier,
        )
        if not data.get("refresh_token"):
            raise CloudError(OTHER, "geen refresh_token")
        return data["refresh_token"]

    @classmethod
    def _token(cls, **fields) -> dict:
        fields["client_id"] = settings.DROPBOX_APP_KEY
        request = urllib.request.Request(
            cls.TOKEN, data=urllib.parse.urlencode(fields).encode(), method="POST"
        )
        status, body = _open(request)
        if status == 400:
            # A wrong or used code, or a revoked link: "invalid_grant".
            raise CloudError(REFUSED, _oauth_refusal(body))
        if status >= 400:
            raise CloudError(_reason_for(status), f"token {status}")
        return _json(body)

    def _access(self) -> str:
        if not self._access_token:
            data = self._token(grant_type="refresh_token", refresh_token=self.refresh_token)
            if not data.get("access_token"):
                raise CloudError(OTHER, "geen access_token")
            self._access_token = data["access_token"]
        return self._access_token

    # Calls --------------------------------------------------------------

    def _call(self, url: str, data: bytes, arg: dict | None = None) -> bytes:
        request = urllib.request.Request(url, data=data, method="POST")
        request.add_header("Authorization", f"Bearer {self._access()}")
        if arg is None:
            request.add_header("Content-Type", "application/json")
        else:
            request.add_header("Content-Type", "application/octet-stream")
            # Dropbox wants this header in ASCII; json.dumps escapes the rest.
            request.add_header("Dropbox-API-Arg", json.dumps(arg))
        status, body = _open(request)
        if status == 409 and b"insufficient_space" in body:
            raise CloudError(FULL, body.decode(errors="replace"))
        if status == 409 and b"not_found" in body:
            raise NotFound(OTHER, body.decode(errors="replace"))
        if status >= 400:
            raise CloudError(_reason_for(status), f"{url} {status}: {body[:200]!r}")
        return body

    def _api(self, endpoint: str, arguments: dict | None) -> dict:
        data = b"null" if arguments is None else json.dumps(arguments).encode()
        body = self._call(self.API + endpoint, data)
        return _json(body) if body and body != b"null" else {}

    def upload(self, name: str, data: bytes) -> None:
        commit = {"path": f"/{name}", "mode": "add", "autorename": False, "mute": True}
        if len(data) <= self.CHUNK:
            self._call(self.CONTENT + "files/upload", data, commit)
            return
        started = self._call(self.CONTENT + "files/upload_session/start", data[: self.CHUNK], {})
        session = _json(started).get("session_id")
        if not session:
            raise CloudError(OTHER, "geen session_id")
        offset = self.CHUNK
        while len(data) - offset > self.CHUNK:
            cursor = {"cursor": {"session_id": session, "offset": offset}}
            self._call(
                self.CONTENT + "files/upload_session/append_v2",
                data[offset : offset + self.CHUNK],
                cursor,
            )
            offset += self.CHUNK
        self._call(
            self.CONTENT + "files/upload_session/finish",
            data[offset:],
            {"cursor": {"session_id": session, "offset": offset}, "commit": commit},
        )

    def list(self) -> list[RemoteFile]:
        try:
            page = self._api("files/list_folder", {"path": ""})
        except NotFound:
            return []
        entries = list(page.get("entries", []))
        while page.get("has_more"):
            page = self._api("files/list_folder/continue", {"cursor": page.get("cursor")})
            entries.extend(page.get("entries", []))
        return [
            RemoteFile(entry["name"], entry.get("size", 0))
            for entry in entries
            if entry.get(".tag") == "file" and CLOUD_ARCHIVE_NAME.match(entry.get("name", ""))
        ]

    def download(self, name: str) -> bytes:
        return self._call(self.CONTENT + "files/download", b"", {"path": f"/{name}"})

    def delete(self, name: str) -> None:
        try:
            self._api("files/delete_v2", {"path": f"/{name}"})
        except NotFound:
            pass

    def revoke(self) -> None:
        self._api("auth/token/revoke", None)

    # The receipts folder (huismus/expenses/inbox.py), a folder in the same
    # app folder: any file in it, not only backups. Paths start with "/".

    def files_in(self, folder: str) -> "list[RemoteFile]":
        """The files directly in folder; NotFound when it doesn't exist."""
        page = self._api("files/list_folder", {"path": folder})
        entries = list(page.get("entries", []))
        while page.get("has_more"):
            page = self._api("files/list_folder/continue", {"cursor": page.get("cursor")})
            entries.extend(page.get("entries", []))
        return [
            RemoteFile(entry["name"], entry.get("size", 0))
            for entry in entries
            if entry.get(".tag") == "file"
        ]

    def create_folder(self, folder: str) -> None:
        self._api("files/create_folder_v2", {"path": folder, "autorename": False})

    def read(self, path: str) -> bytes:
        return self._call(self.CONTENT + "files/download", b"", {"path": path})

    def move(self, source: str, destination: str) -> None:
        """Moves a file; Dropbox makes the folder, and gives the file
        another name ("bon (1).jpg") when the name is taken."""
        self._api(
            "files/move_v2",
            {"from_path": source, "to_path": destination, "autorename": True},
        )


def remote(config: Config | None = None) -> WebDAV | Dropbox | None:
    config = config or load()
    if config.service == DROPBOX:
        return Dropbox(config.dropbox_refresh_token)
    if config.service == WEBDAV:
        return WebDAV(config.webdav_url, config.webdav_username, config.webdav_password)
    return None


# -- Uploading ---------------------------------------------------------------


def is_due(now: datetime | None = None) -> bool:
    """Ready, and today has no upload that worked yet."""
    if not is_ready():
        return False
    now = now or timezone.localtime()
    last = load().last_success_at
    return last is None or timezone.localtime(last).date() < now.date()


def upload_backup(now: datetime | None = None) -> RemoteFile | None:
    """A new backup, encrypted and uploaded, then the clean-up in the
    cloud. None after a failure, which is recorded and logged; None and
    nothing recorded while not ready, while the sample data is in use
    (made-up records never leave this computer), or while another upload
    is running.

    The archive goes through memory whole, encrypted and all: a few times
    the size of a backup, fine for an administration with receipts.

    Not behind core.maintenance's gate itself: its caller is, the hourly
    run_if_due, and upload_in_background for a page."""
    if not is_ready() or sample_data_in_use():
        return None
    if not _upload_lock.acquire(blocking=False):
        return None
    try:
        return _upload(load(), now or timezone.localtime())
    finally:
        _upload_lock.release()


def uploading() -> bool:
    """An upload is running: the nightly one, or the first after linking."""
    return _upload_lock.locked()


def _start(work) -> None:
    """Runs work in its own thread; tests replace this to run it at once."""

    def run():
        try:
            work()
        finally:
            # A thread's own database connections stay open otherwise.
            connections.close_all()

    threading.Thread(target=run, name="huismus-cloud-upload", daemon=True).start()


def upload_in_background() -> bool:
    """upload_backup, without making the page wait for it: after linking,
    a backup with receipts can take minutes to encrypt and send (besluit
    2026-11-01: "Ik heb de code bewaard" seemed to hang). True when an
    upload is now running, this one or one that already was; uploading()
    says when it is done, and load() how it went.

    The lock is taken here, not in the thread, so that the page that
    follows already sees uploading(). A restore waits for it, as for the
    hourly one (core.auto_backups.run_if_due)."""
    if not is_ready() or sample_data_in_use():
        return False
    if not _upload_lock.acquire(blocking=False):
        return True

    def work():
        try:
            with maintenance.gate.request() as open_:
                if open_:
                    _upload(load(), timezone.localtime())
                else:
                    # A restore is running; the hourly one tries again.
                    logger.warning("Back-up naar de cloud overgeslagen: er wordt teruggezet")
        except Exception:
            logger.exception("Back-up naar de cloud mislukt")
        finally:
            _upload_lock.release()

    try:
        _start(work)
    except Exception:
        _upload_lock.release()
        raise
    return True


def _upload(config: Config, now: datetime) -> RemoteFile | None:
    service = remote(config)
    try:
        with tempfile.TemporaryDirectory(prefix="huismus-cloud-") as scratch:
            archive = create_backup(Path(scratch))
            data = encrypt(archive.read_bytes(), code())
        name = _free_name(service, archive.name)
        service.upload(name, data)
    except (CloudError, OSError, BackupError, sqlite3.Error, tarfile.TarError) as error:
        logger.warning("Back-up naar %s mislukt: %s", config.service_label, error)
        reason = error.reason if isinstance(error, CloudError) else OTHER
        _update(last_failure=now.isoformat(), failure_reason=reason)
        return None
    _update(last_success=now.isoformat(), last_size=len(data))
    try:
        prune(service, now)
    except (CloudError, OSError) as error:
        # The backup is there; an old one more is no reason for red.
        logger.warning("Opruimen in %s mislukt: %s", config.service_label, error)
    return RemoteFile(name, len(data))


def _free_name(service, archive_name: str) -> str:
    """archive_name with ".age" after it, or with -2, -3 like core.backup
    when the cloud already has a backup from the same second: uploading
    under the same name would replace that one. (core.backup's own -2
    never comes up here: it makes the archive in an empty folder.)"""
    taken = {file.name for file in service.list()}
    stem = archive_name.removesuffix(".tar.gz")
    name, count = f"{stem}.tar.gz.age", 1
    while name in taken:
        count += 1
        name = f"{stem}-{count}.tar.gz.age"
    return name


def prune(service, now: datetime) -> list[str]:
    """The folder's rule in the cloud (core.auto_backups.to_remove): only
    Huismus's own encrypted archives."""
    from .auto_backups import to_remove

    # Newest first already: to_remove sorts on the second alone and keeps
    # this order within one, so of two in one second the later stays.
    found = sorted(service.list(), key=lambda file: file.order, reverse=True)
    dated = [(file.created_at, file.name) for file in found]
    removed = to_remove(dated, now)
    for name in removed:
        service.delete(name)
    return removed


def archives() -> list[RemoteFile]:
    """The backups in the cloud, newest first; empty when nothing is
    linked. CloudError when the service can't be reached."""
    service = remote()
    if service is None:
        return []
    found = service.list()
    found.sort(key=lambda file: file.order, reverse=True)
    return found


def fetch(name: str, destination: Path) -> Path:
    """Downloads and decrypts one backup to destination (a .tar.gz).
    CodeError for another code, CloudError when the service fails, and
    FileNotFoundError for a name that isn't one of Huismus's."""
    if not CLOUD_ARCHIVE_NAME.match(name):
        raise FileNotFoundError(name)
    data = remote().download(name)
    destination.parent.mkdir(exist_ok=True)
    destination.write_bytes(decrypt(data, code()))
    return destination


def failure_sentence(config: Config) -> str:
    """Why the last upload failed, for the overview and Back-ups."""
    service = config.service_label
    if config.failure_reason == REFUSED:
        if config.service == WEBDAV:
            return _("Het wachtwoord werd geweigerd. Stel WebDAV opnieuw in.")
        return _("%(service)s weigert de toegang. Koppel %(service)s opnieuw.") % {
            "service": service
        }
    if config.failure_reason == UNREACHABLE:
        return _("%(service)s is niet bereikbaar.") % {"service": service}
    if config.failure_reason == FULL:
        return _("De opslag in %(service)s is vol.") % {"service": service}
    if config.failure_reason == NOT_WEBDAV:
        return _("Op dit adres staat geen WebDAV meer. Stel WebDAV opnieuw in.")
    return ""


def place(config: Config) -> str:
    """Where the backups go: "Dropbox › Apps › Huismus"."""
    if config.service == DROPBOX:
        return "Dropbox › Apps › Huismus"
    if config.service == WEBDAV:
        return f"{config.webdav_url.rstrip('/')} › {WEBDAV_FOLDER}"
    return ""
