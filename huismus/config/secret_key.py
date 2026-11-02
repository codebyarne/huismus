# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The SECRET_KEY when the environment has none (SPEC.md M11): created on
first start and kept in DATA_DIR, readable only by Huismus. Like the mail
password, it stays out of backups (core.backup). Plain Python: settings.py
reads it before Django is set up."""

import os
import secrets
from pathlib import Path

FILE_NAME = "secret-key"


def load_or_create(data_dir: Path) -> str:
    path = data_dir / FILE_NAME
    try:
        return _read(path)
    except FileNotFoundError:
        pass
    # Written in full to a temporary file, owner-only from the start, then
    # linked into place: os.link fails when another process (a second
    # gunicorn worker) got there first, and then that one's key is used.
    temporary = data_dir / f"{FILE_NAME}.{secrets.token_hex(4)}.tmp"
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        file.write(secrets.token_urlsafe(50))
    try:
        os.link(temporary, path)
    except FileExistsError:
        pass
    finally:
        temporary.unlink()
    return _read(path)


def _read(path: Path) -> str:
    key = path.read_text(encoding="utf-8").strip()
    if not key:
        raise RuntimeError(f"{path} is leeg. Verwijder het: Huismus maakt dan een nieuwe sleutel.")
    return key
