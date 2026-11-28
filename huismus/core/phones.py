# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Phones linked to the desktop app over the user's own Wi-Fi (issue #143,
SPEC.md M11).

Instellingen → Op je telefoon makes a one-time code, shown as a QR code.
The phone that opens it gets a cookie of its own, long-lived, and from then
on reaches Huismus over Wi-Fi while the app is open (huismus/core/phone_server.py).

Kept in a file in DATA_DIR, readable only by Huismus, and never in a backup
(core.backup): a link belongs to this computer, like the SECRET_KEY. The
file holds only SHA-256 hashes of the code and the cookies, so reading it
gives nobody access. One process serves Huismus on the desktop, so a lock
around each change is enough.
"""

import hashlib
import ipaddress
import json
import secrets
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from .private_files import write_owner_only

FILE_NAME = "telefoons.json"
CODE_LIFETIME = timedelta(minutes=10)
# A phone that isn't used for this long links again (PO, 2026-11-28).
UNUSED_LIFETIME = timedelta(days=90)
# "Laatst gebruikt" is written at most this often, not at every request.
LAST_SEEN_STEP = timedelta(hours=1)

_lock = threading.Lock()


def _path() -> Path:
    return Path(settings.DATA_DIR) / FILE_NAME


def _hash(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _matches(value, stored: str) -> bool:
    if not isinstance(value, str) or not value or not stored:
        return False
    return secrets.compare_digest(_hash(value), stored)


def _load() -> dict:
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {"code": None, "devices": []}
    if not isinstance(data, dict) or not isinstance(data.get("devices"), list):
        return {"code": None, "devices": []}
    return data


def _save(data: dict) -> None:
    write_owner_only(_path(), json.dumps(data, indent=1))


def _now(now):
    return now or datetime.now(UTC)


def _drop_unused(data: dict, now: datetime) -> bool:
    kept = [
        device
        for device in data["devices"]
        if now - datetime.fromisoformat(device["last_seen"]) <= UNUSED_LIFETIME
    ]
    changed = len(kept) != len(data["devices"])
    data["devices"] = kept
    return changed


def is_on() -> bool:
    """Listening on Wi-Fi makes sense: a code waits, or a phone is linked."""
    data = _load()
    return bool(data["code"] or data["devices"])


def new_code(now=None) -> str:
    """The code in the QR code: once, for ten minutes. A new one replaces
    the one before, so there is never more than one."""
    code = secrets.token_urlsafe(32)
    with _lock:
        data = _load()
        data["code"] = {
            "hash": _hash(code),
            "expires": (_now(now) + CODE_LIFETIME).isoformat(),
        }
        _save(data)
    return code


def code_waiting(now=None) -> bool:
    code = _load()["code"]
    return bool(code) and datetime.fromisoformat(code["expires"]) >= _now(now)


def pair(code, name, now=None) -> str | None:
    """The phone's cookie when code is the code waiting, else None. The
    code is used up in the same change, so two scans can't both link."""
    now = _now(now)
    with _lock:
        data = _load()
        waiting = data["code"]
        if not waiting or not _matches(code, waiting["hash"]):
            return None
        data["code"] = None
        if datetime.fromisoformat(waiting["expires"]) < now:
            _save(data)
            return None
        token = secrets.token_urlsafe(32)
        data["devices"].append(
            {
                "id": secrets.token_hex(8),
                "name": str(name),
                "hash": _hash(token),
                "linked": now.isoformat(),
                "last_seen": now.isoformat(),
            }
        )
        _save(data)
    return token


def device_for(token, now=None) -> dict | None:
    """The linked phone with this cookie, or None."""
    if not isinstance(token, str) or not token:
        return None
    now = _now(now)
    with _lock:
        data = _load()
        changed = _drop_unused(data, now)
        found = next((d for d in data["devices"] if _matches(token, d["hash"])), None)
        refreshed = False
        if found and now - datetime.fromisoformat(found["last_seen"]) >= LAST_SEEN_STEP:
            found["last_seen"] = now.isoformat()
            changed = refreshed = True
        if changed:
            _save(data)
    if found is None:
        return None
    # refreshed: the cookie can move along too (core.desktop).
    return {key: value for key, value in found.items() if key != "hash"} | {"refreshed": refreshed}


def devices(now=None) -> list[dict]:
    """The linked phones, the oldest first, without their hashes."""
    now = _now(now)
    with _lock:
        data = _load()
        if _drop_unused(data, now):
            _save(data)
    return [
        {key: value for key, value in device.items() if key != "hash"} for device in data["devices"]
    ]


def unpair(device_id: str) -> None:
    with _lock:
        data = _load()
        data["devices"] = [d for d in data["devices"] if d["id"] != device_id]
        _save(data)


def turn_off() -> None:
    """Every link and the waiting code gone: linking again means scanning
    again (PO, 2026-11-28). The port stays, see saved_port."""
    with _lock:
        port = _load().get("port")
        if port:
            _save({"code": None, "devices": [], "port": port})
        else:
            _path().unlink(missing_ok=True)


def saved_port() -> int | None:
    """The port Huismus listened on last time, tried first the next time,
    so a bookmark on the phone breaks as little as possible (PO, 2026-11-28)."""
    port = _load().get("port")
    return port if isinstance(port, int) and 0 < port < 65536 else None


def save_port(port: int) -> None:
    with _lock:
        data = _load()
        if data.get("port") != port:
            data["port"] = port
            _save(data)


def phone_name(user_agent: str):
    """Only the kind of device, from the browser: enough to tell two
    phones apart in the list, nothing more about the phone."""
    agent = user_agent or ""
    if "iPhone" in agent:
        return _("iPhone")
    if "iPad" in agent:
        return _("iPad")
    if "Android" in agent:
        return _("Android-telefoon") if "Mobile" in agent else _("Android-tablet")
    return _("Telefoon")


_HOME_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
]


def is_home_network(address: str) -> bool:
    """An IPv4 address of a network at home or at the office (RFC 1918).
    Not loopback, link-local or 100.64/10 (carrier NAT, Tailscale): Huismus
    is never reachable from the internet (SPEC.md 9)."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    return ip.version == 4 and any(ip in network for network in _HOME_NETWORKS)
