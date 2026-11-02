# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Never two copies of the app on the same administration (SPEC.md M11).

A lock on a small file next to the administration (paths.lock_file),
held for as long as the app runs; the system lets go of it when the
process ends, also after a crash. The file holds the process id, so a
second start on Windows can bring the first one's window forward
(desktop/windows.py).
"""

import os
import sys
from pathlib import Path

# On Windows a locked byte can't be read by anyone else, so the lock sits
# past the process id (Windows may lock beyond the end of a file).
_WINDOWS_LOCK_OFFSET = 1024


class AlreadyOpen(Exception):
    pass


def acquire(path: Path):
    """The open lock file; keep it until the app ends. AlreadyOpen when
    another process holds it."""
    # Read-write without emptying it: the holder's id must survive a
    # second start that fails to get the lock.
    lock = os.fdopen(os.open(path, os.O_RDWR | os.O_CREAT, 0o600), "r+")
    try:
        _lock(lock)
    except OSError:
        lock.close()
        raise AlreadyOpen() from None
    # Padded instead of truncated, which Windows may refuse on a locked file.
    lock.seek(0)
    lock.write(f"{os.getpid():<20}")
    lock.flush()
    return lock


def holder(path: Path) -> int | None:
    """The process id of the app that holds the lock, if it says."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _lock(file) -> None:
    if sys.platform == "win32":
        import msvcrt

        file.seek(_WINDOWS_LOCK_OFFSET)
        msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
    else:
        import fcntl

        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)
