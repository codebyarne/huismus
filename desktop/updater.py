# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Replacing the installed app with a downloaded new version (SPEC.md M11).

core.updates downloads and checks the file and makes the backup; then it
calls the installer the shell registered (desktop/app.py). An app can't
replace itself while it runs, so the installer writes a small script that
waits until this process has ended and opens the app again after:

- on macOS a shell script that copies Huismus.app out of the .dmg in place
  of the old one, keeping the old one until the copy is complete;
- on Windows a PowerShell script that runs the downloaded installer
  without any window or question (desktop/huismus.iss).

Then the window closes. Only tested by hand, on a Mac and on Windows
(SPEC.md M11, "Done when").

Before that, on macOS, minimum_macos reads which macOS the downloaded app
needs, so core.updates never installs one that wouldn't open (issue #155).
"""

import os
import plistlib
import re
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

# Every failure ends with the old app opened again, unchanged; its next
# start sees the update didn't happen and says so (desktop/app.py).
SCRIPT = """#!/bin/sh
# Written by Huismus to install an update (desktop/updater.py).
while kill -0 {pid} 2>/dev/null; do sleep 0.5; done
give_up() {{ rm -f {package} "$0"; open {app}; exit 1; }}
# Checked once more: the file waited in a folder of the user's own.
echo "{sha256}  "{package} | shasum -a 256 -c - >/dev/null || give_up
mount=$(mktemp -d) || give_up
hdiutil attach -nobrowse -readonly -mountpoint "$mount" {package} || give_up
if [ -d "$mount/Huismus.app" ] && rm -rf {old} && mv {app} {old}; then
  if ditto "$mount/Huismus.app" {app}; then
    rm -rf {old}
  else
    rm -rf {app}
    mv {old} {app}
  fi
fi
hdiutil detach "$mount" -quiet
rm -f {package} "$0"
open {app}
"""

# Every failure (a different SHA-256, an installer that stops) ends with the
# old app opened again, as on macOS: its next start sees the version didn't
# change and the overview says the update wasn't installed
# (_updated_if_pending in desktop/app.py). Get-FileHash gives capitals; -eq
# compares without case.
WINDOWS_SCRIPT = """# Written by Huismus to install an update (desktop/updater.py).
$package = {package}
$quiet = '/VERYSILENT', '/SUPPRESSMSGBOXES', '/NORESTART'
try {{
  Wait-Process -Id {pid} -ErrorAction SilentlyContinue
  # Checked once more: the file waited in a folder of the user's own.
  $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $package).Hash
  if ($hash -eq '{sha256}') {{
    Start-Process -Wait -FilePath $package -ArgumentList $quiet
  }}
}} finally {{
  Remove-Item -LiteralPath $package -ErrorAction SilentlyContinue
  Remove-Item -LiteralPath $PSCommandPath -ErrorAction SilentlyContinue
  Start-Process -FilePath {exe}
}}
"""


def app_bundle() -> Path | None:
    """Huismus.app around the running program, or None outside one."""
    if not getattr(sys, "frozen", False) or sys.platform != "darwin":
        return None
    # Huismus.app/Contents/MacOS/Huismus
    bundle = Path(sys.executable).resolve().parents[2]
    return bundle if bundle.suffix == ".app" else None


def installed_app() -> Path | None:
    """What an update replaces: Huismus.app on macOS, the folder with
    Huismus.exe on Windows (whose installer then replaces its contents).
    None outside the packaged app."""
    if sys.platform == "win32":
        if not getattr(sys, "frozen", False):
            return None
        return Path(sys.executable).resolve().parent
    return app_bundle()


def minimum_macos(package: Path) -> str:
    """The LSMinimumSystemVersion of Huismus.app in the downloaded .dmg,
    like "15.0"; "" when it names none. Mounted read-only and out of
    sight, as the install script does; an error when that fails
    (core.updates then holds nothing back)."""
    with tempfile.TemporaryDirectory(prefix="huismus-dmg-") as mount:
        subprocess.run(
            ["hdiutil", "attach", "-nobrowse", "-readonly", "-mountpoint", mount, str(package)],
            check=True,
            capture_output=True,
            timeout=120,
        )
        try:
            return minimum_macos_of(Path(mount) / "Huismus.app")
        finally:
            subprocess.run(["hdiutil", "detach", mount, "-quiet"], capture_output=True, timeout=60)


def minimum_macos_of(app: Path) -> str:
    """The LSMinimumSystemVersion in app's Info.plist, "" without one."""
    with (app / "Contents" / "Info.plist").open("rb") as file:
        info = plistlib.load(file)
    minimum = info.get("LSMinimumSystemVersion", "")
    return minimum if isinstance(minimum, str) else ""


def script(package: Path, sha256: str, app: Path, pid: int) -> str:
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("geen SHA-256")
    return SCRIPT.format(
        pid=pid,
        sha256=sha256,
        package=shlex.quote(str(package)),
        app=shlex.quote(str(app)),
        old=shlex.quote(str(app.with_name(app.name + ".oud"))),
    )


def windows_script(package: Path, sha256: str, app: Path, pid: int) -> str:
    """app is the folder with Huismus.exe (installed_app)."""
    if not re.fullmatch(r"[0-9a-f]{64}", sha256):
        raise ValueError("geen SHA-256")
    return WINDOWS_SCRIPT.format(
        pid=pid,
        sha256=sha256,
        package=_powershell_quote(str(package)),
        exe=_powershell_quote(str(app / "Huismus.exe")),
    )


def _powershell_quote(text: str) -> str:
    """A PowerShell string that takes text literally: between single
    quotes, in which only a quote needs doubling. PowerShell counts the
    typographic single quotes as quotes too."""
    for quote in "'\u2018\u2019\u201a\u201b":
        text = text.replace(quote, quote * 2)
    return f"'{text}'"


def start(package: Path, sha256: str, app: Path) -> None:
    """Starts the script in the background, apart from this process, so it
    outlives the app it replaces. The caller then closes the window."""
    if sys.platform == "win32":
        _start_on_windows(package, sha256, app)
        return
    with tempfile.NamedTemporaryFile(
        "w", prefix="huismus-update-", suffix=".sh", delete=False
    ) as file:
        file.write(script(package, sha256, app, os.getpid()))
    subprocess.Popen(["/bin/sh", file.name], start_new_session=True)


def _start_on_windows(package: Path, sha256: str, app: Path) -> None:
    # With a byte order mark: Windows PowerShell reads a file without one
    # in the old code page, which garbles a name like "José".
    with tempfile.NamedTemporaryFile(
        "w", prefix="huismus-update-", suffix=".ps1", delete=False, encoding="utf-8-sig"
    ) as file:
        file.write(windows_script(package, sha256, app, os.getpid()))
    subprocess.Popen(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-WindowStyle",
            "Hidden",
            "-File",
            file.name,
        ],
        creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP,
        close_fds=True,
    )
