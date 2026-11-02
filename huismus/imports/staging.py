# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uploaded import files, kept between the dry run and the commit (SPEC.md M8).

The dry run stores the uploads under data/import-staging/<token>/; "Nu echt
doorvoeren" sends only the token, so the commit reads exactly the files
the dry run checked and the user doesn't choose them again. These are
files in the user's own data/ directory, not database rows: a dry run
still leaves the database byte-identical (SPEC.md section 7).

A staging is removed after its commit, and any staging older than MAX_AGE
the next time something is staged.
"""

import re
import shutil
import time
import uuid
from datetime import timedelta
from pathlib import Path, PurePosixPath, PureWindowsPath

from django.conf import settings

MAX_AGE = timedelta(hours=24)
_TOKEN = re.compile(r"[0-9a-f]{32}")


def _root() -> Path:
    return Path(settings.DATA_DIR) / "import-staging"


def _safe_name(name: str) -> str:
    """Just the file's own name: browsers send a basename, but the name is
    client input and must never lead outside the staging directory."""
    return PureWindowsPath(PurePosixPath(name).name).name or "bestand"


def stage(uploads) -> str:
    """Stores `uploads` (objects with .name and .read()) and returns the
    token that finds them again."""
    purge_stale()
    token = uuid.uuid4().hex
    directory = _root() / token
    directory.mkdir(parents=True)
    for index, upload in enumerate(uploads):
        target = directory / _safe_name(upload.name)
        if target.exists():  # two uploads with the same name: keep both
            target = directory / f"{index}__{target.name}"
        target.write_bytes(upload.read())
    return token


def staged_path(token) -> Path | None:
    """The directory of a staging, or None for anything that isn't the
    token of an existing one."""
    if not isinstance(token, str) or not _TOKEN.fullmatch(token):
        return None
    directory = _root() / token
    return directory if directory.is_dir() else None


def discard(token) -> None:
    directory = staged_path(token)
    if directory is not None:
        shutil.rmtree(directory)


def purge_stale() -> None:
    root = _root()
    if not root.is_dir():
        return
    cutoff = time.time() - MAX_AGE.total_seconds()
    for directory in root.iterdir():
        if directory.is_dir() and directory.stat().st_mtime < cutoff:
            shutil.rmtree(directory)
