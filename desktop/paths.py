# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where the desktop app keeps things: the system's own places (SPEC.md M11)."""

import os
import sys
from pathlib import Path


def data_dir() -> Path:
    """The administration. HUISMUS_DATA_DIR wins, as on Docker, so a
    developer can start the app on a copy instead of their own."""
    if os.environ.get("HUISMUS_DATA_DIR"):
        return Path(os.environ["HUISMUS_DATA_DIR"])
    if sys.platform == "win32":
        return Path(os.environ["APPDATA"]) / "Huismus"
    return Path.home() / "Library" / "Application Support" / "Huismus"


def log_file() -> Path:
    """Outside data_dir, so a log never ends up in a backup."""
    if sys.platform == "win32":
        return Path(os.environ["LOCALAPPDATA"]) / "Huismus" / "huismus.log"
    return Path.home() / "Library" / "Logs" / "Huismus" / "huismus.log"


def lock_file(data: Path) -> Path:
    """Next to the administration, not in it (and so not in a backup)."""
    return data.with_name(data.name + ".lock")


def bundle_dir() -> Path:
    """Huismus's own files: inside the packaged app, or the repository."""
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parent.parent
