# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Small secrets kept in a file of their own in DATA_DIR, readable only by
Huismus: the mail password (business.smtp) and the AI connection's key
(assistants.key). Not in the database, so not in a backup."""

import os
from pathlib import Path


def write_owner_only(path: Path, value: str | bytes) -> None:
    """Written to a temporary file first and then renamed, so a half-written
    secret never exists; the file is created owner-only, never briefly
    readable."""
    temporary = path.with_name(path.name + ".tmp")
    temporary.unlink(missing_ok=True)
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    if isinstance(value, bytes):
        with os.fdopen(descriptor, "wb") as file:
            file.write(value)
    else:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(value)
    temporary.replace(path)
