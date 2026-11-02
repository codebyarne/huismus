# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# PyInstaller recipe for Huismus.app and, on Windows, the Huismus folder
# with Huismus.exe that desktop/huismus.iss turns into an installer
# (SPEC.md M11). Run through scripts/build-mac.sh or
# scripts/build-windows.sh, which first compile the translations and
# collect the static files that this takes along.
#
# Django finds its apps, templates and migrations by name at run time,
# which PyInstaller cannot see, so they are listed here. huismus/config/settings.py
# puts BASE_DIR where this lands everything: the bundle's own folder.
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent
# collect_submodules below imports the huismus package to find its modules.
sys.path.insert(0, str(ROOT))

hiddenimports = ["desktop.app"]
datas = [
    # The help pages (huismus/core/help.py).
    (str(ROOT / "docs" / "hulp"), "docs/hulp"),
    (str(ROOT / "staticfiles"), "staticfiles"),
    (str(ROOT / "desktop" / "fonts.conf"), "desktop"),
    (str(ROOT / "desktop" / "fonts-windows.conf"), "desktop"),
    # The version, for huismus.core.updates.
    (str(ROOT / "pyproject.toml"), "."),
]
# All of Huismus's code is one package: the apps, the settings, and the
# templates, translations and static files inside it (docs/architectuur.md).
hiddenimports += collect_submodules("huismus")
datas += collect_data_files("huismus")
# Django's own: admin and auth templates, its translations, and modules it
# loads by dotted path from the settings.
hiddenimports += collect_submodules(
    "django", filter=lambda name: not name.startswith(("django.contrib.gis", "django.test"))
)
datas += collect_data_files("django")
# Also named in the settings only: middleware and static file storage.
hiddenimports += collect_submodules("whitenoise")

a = Analysis(
    [str(ROOT / "desktop" / "__main__.py")],
    pathex=[str(ROOT)],
    hiddenimports=hiddenimports,
    datas=datas,
    excludes=["tkinter", "pytest", "hypothesis", "playwright"],
)
WINDOWS = sys.platform == "win32"
if not WINDOWS:
    # Pillow's wheel brings its own, older harfbuzz and freetype, and
    # PyInstaller keeps one file per name: here a link to Pillow's copy.
    # Then Pango's libharfbuzz.dylib (which WeasyPrint opens) loads Pillow's
    # libharfbuzz.0.dylib, another version, and every PDF crashes the app.
    # So these two names get Homebrew's copy, next to Pango's; Pillow works
    # with the newer ones too.
    pango_libs = Path(next(src for name, src, _ in a.binaries if name == "libharfbuzz.dylib")).parent
    pillows = {
        name
        for name, src, kind in a.datas
        if kind == "SYMLINK"
        and src.startswith("PIL/")
        and name.startswith(("libharfbuzz.", "libfreetype."))
    }
    a.datas = [entry for entry in a.datas if entry[0] not in pillows]
    a.binaries += [(name, str(pango_libs / name), "BINARY") for name in sorted(pillows)]
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Huismus",
    console=False,
    icon=str(ROOT / "build" / "Huismus.ico") if WINDOWS else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Huismus")
if not WINDOWS:
    app = BUNDLE(
        coll,
        name="Huismus.app",
        icon=str(ROOT / "build" / "Huismus.icns"),
        bundle_identifier="nl.huismus.desktop",
        version=__import__("tomllib").loads((ROOT / "pyproject.toml").read_text())["project"]["version"],
        info_plist={
            "CFBundleDisplayName": "Huismus",
            "NSHighResolutionCapable": True,
            "LSMinimumSystemVersion": "14.0",
            "CFBundleDevelopmentRegion": "nl",
            "CFBundleLocalizations": ["nl", "en"],
        },
    )
