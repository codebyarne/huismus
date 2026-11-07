# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The AI connection's key (SPEC.md M16).

One key for the address /mcp, kept in data/mcp-key, owner-only and left
out of backups (core.backup skips every file starting with FILE_NAME),
like the mail password. No key: /mcp refuses everything.

A second file, data/mcp-key-used, records that a request with this key
came in, for the page's "Gekoppeld". A new key starts without it.
"""

import secrets
from pathlib import Path

from django.conf import settings

from huismus.core.private_files import write_owner_only

FILE_NAME = "mcp-key"
# So a key can be recognised in a config file; the rest is random.
PREFIX = "hm_"


def _path() -> Path:
    return Path(settings.DATA_DIR) / FILE_NAME


def _used_path() -> Path:
    return Path(settings.DATA_DIR) / f"{FILE_NAME}-used"


def current() -> str:
    try:
        return _path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def create() -> str:
    """A new key, replacing the old one: whoever had that is locked out."""
    key = PREFIX + secrets.token_urlsafe(32)
    write_owner_only(_path(), key)
    # After the new key is in place: a request with the old one can no
    # longer mark it used.
    _used_path().unlink(missing_ok=True)
    return key


def remove() -> None:
    _used_path().unlink(missing_ok=True)
    _path().unlink(missing_ok=True)


def matches(value: str) -> bool:
    key = current()
    return bool(key) and bool(value) and secrets.compare_digest(value.encode(), key.encode())


def mark_used() -> None:
    _used_path().touch()


def is_used() -> bool:
    return _used_path().exists()
