# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Koppel met Claude: Huismus as an extension of the Claude app, in the
desktop app only (SPEC.md M16; besluit 2026-11-02).

The Claude app installs an extension from one file, Huismus.mcpb: a zip
with manifest.json and a program it runs with its own Node
(bridge/server.js, which passes each message on to /mcp). The format is
MANIFEST.md in the modelcontextprotocol/mcpb repository.

The file carries the key, as Claude Code's config does: "Nieuwe sleutel"
and "Ontkoppelen" lock the Claude app out too. It carries the address as
well, but the port can differ at the next start (desktop/server.py), so
the desktop app writes its address to ADDRESS_FILE_SUFFIX at every start
and the program reads that first.
"""

import io
import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

from django.conf import settings
from django.contrib.staticfiles import finders
from django.utils.translation import gettext as _

from huismus.core.private_files import write_owner_only
from huismus.core.updates import current_version

BRIDGE = Path(__file__).resolve().parent / "bridge" / "server.js"
FILE_NAME = "Huismus.mcpb"
# Next to the administration, not in it, so not in a backup (like
# desktop/paths.lock_file).
ADDRESS_FILE_SUFFIX = ".address"
DOWNLOAD_URL = "https://claude.ai/download"


def address_file() -> Path:
    data = Path(settings.DATA_DIR)
    return data.with_name(data.name + ADDRESS_FILE_SUFFIX)


def write_address(url: str) -> None:
    """desktop/app.py, once the server runs: the address the program uses.
    No key in it."""
    address_file().write_text(url + "/mcp", encoding="utf-8")


def manifest(address: str, secret: str) -> dict:
    return {
        "manifest_version": "0.3",
        "name": "huismus",
        "display_name": "Huismus",
        "version": current_version(),
        "description": _("Je facturen, offertes en klanten uit Huismus op deze computer."),
        "author": {"name": "Huismus"},
        "license": "AGPL-3.0-or-later",
        "icon": "icon.png",
        "server": {
            "type": "node",
            "entry_point": "server/index.js",
            "mcp_config": {
                "command": "node",
                "args": ["${__dirname}/server/index.js"],
                "env": {
                    "HUISMUS_KEY": secret,
                    "HUISMUS_ADDRESS": address,
                    "HUISMUS_ADDRESS_FILE": str(address_file()),
                    "HUISMUS_NOT_OPEN": _(
                        "Huismus is niet open. Open de Huismus-app op deze computer."
                    ),
                    "HUISMUS_NOT_CONNECTED": _(
                        "Huismus is niet meer gekoppeld. Kies in Huismus opnieuw Koppel met Claude."
                    ),
                },
            },
        },
        # The tools come from Huismus itself, at every start.
        "tools_generated": True,
        "compatibility": {"platforms": ["darwin", "win32"], "runtimes": {"node": ">=18.0.0"}},
    }


def bundle(address: str, secret: str) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest(address, secret), indent=2))
        archive.write(BRIDGE, "server/index.js")
        archive.write(finders.find("core/icons/icon-512.png"), "icon.png")
    return buffer.getvalue()


def _saved() -> Path:
    return Path(tempfile.gettempdir()) / "huismus-claude" / FILE_NAME


def save(content: bytes) -> Path:
    """In a folder of the user's own, owner-only: the file holds the key.
    The same file every time, so there is only ever one."""
    path = _saved()
    path.parent.mkdir(mode=0o700, exist_ok=True)
    write_owner_only(path, content)
    return path


def remove_saved() -> None:
    """desktop/app.py at every start: by then the Claude app has its own copy."""
    _saved().unlink(missing_ok=True)


def open_in_claude(path: Path) -> bool:
    """Opens the file in the Claude app, which asks whether to install it.
    False when the Claude app is not there. The desktop app runs on macOS
    and Windows only."""
    if sys.platform == "win32":
        # As a double-click would: Windows has no "open with this app" by
        # name, and only the Claude app claims .mcpb.
        try:
            os.startfile(path)
        except OSError:
            return False
        return True
    # By name, so not another app that claims .mcpb.
    return subprocess.run(["open", "-a", "Claude", str(path)], capture_output=True).returncode == 0
