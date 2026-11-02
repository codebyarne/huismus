#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Builds the Windows desktop app (SPEC.md M11): dist/Huismus (the app's
# folder, with Huismus.exe) and dist/Huismus-<version>-windows.exe (the
# installer), for x64. Runs in Git Bash, as on GitHub's Windows runners.
#
# Needs Pango from MSYS2's UCRT64 environment, which goes inside the app
# (`pacman -S mingw-w64-ucrt-x86_64-pango mingw-w64-ucrt-x86_64-gettext-tools`),
# and Inno Setup 6. PANGO_BIN is MSYS2's ucrt64\bin (default C:\msys64\ucrt64\bin).
set -euo pipefail
cd "$(dirname "$0")/.."

pango_bin=$(cygpath -u "${PANGO_BIN:-C:\msys64\ucrt64\bin}")
iscc="${ISCC:-/c/Program Files (x86)/Inno Setup 6/ISCC.exe}"
version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)

export SECRET_KEY=build-time-only-not-used DEBUG=false
uv sync --locked --group desktop
# msgfmt comes from MSYS2 as well.
PATH="$PATH:$pango_bin" uv run python manage.py compilemessages --ignore=.venv >/dev/null
rm -rf staticfiles build/pyinstaller dist/Huismus dist/Huismus-*-windows.exe
uv run python manage.py collectstatic --noinput >/dev/null

# The app icon, from the PWA's largest one (Pillow is a dependency anyway).
mkdir -p build
uv run python -c "
from PIL import Image
Image.open('huismus/core/static/core/icons/icon-512.png').save(
    'build/Huismus.ico', sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
)"

# PyInstaller's WeasyPrint hook finds Pango and the libraries it needs on
# the PATH; MSYS2's folder is there only for this build.
PATH="$pango_bin:$PATH" \
    uv run pyinstaller desktop/huismus.spec --noconfirm --distpath dist --workpath build/pyinstaller

"$iscc" //Q "//DVersion=$version" desktop/huismus.iss
echo "Klaar: dist/Huismus en dist/Huismus-$version-windows.exe"
