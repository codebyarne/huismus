#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Builds the macOS desktop app (SPEC.md M11): dist/Huismus.app and
# dist/Huismus.dmg, ad-hoc signed, for the architecture of this Mac.
# Needs Pango from Homebrew (`brew install pango`), which goes inside the app.
set -euo pipefail
cd "$(dirname "$0")/.."

export SECRET_KEY=build-time-only-not-used DEBUG=false
uv sync --locked --group desktop
uv run python manage.py compilemessages --ignore=.venv >/dev/null
rm -rf staticfiles build/pyinstaller dist/Huismus.app dist/Huismus.dmg
uv run python manage.py collectstatic --noinput >/dev/null

# The app icon, from the PWA's largest one.
iconset=build/Huismus.iconset
mkdir -p "$iconset"
for size in 16 32 128 256 512; do
    sips -z "$size" "$size" huismus/core/static/core/icons/icon-512.png --out "$iconset/icon_${size}x${size}.png" >/dev/null
    double=$((size * 2))
    if [ "$double" -le 512 ]; then
        sips -z "$double" "$double" huismus/core/static/core/icons/icon-512.png --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
    fi
done
iconutil -c icns "$iconset" -o build/Huismus.icns

# PyInstaller's WeasyPrint hook finds Pango and its libraries only where
# the system looks, and Homebrew's lib folder is not one of those places.
DYLD_FALLBACK_LIBRARY_PATH="$(brew --prefix)/lib" \
    uv run pyinstaller desktop/huismus.spec --noconfirm --distpath dist --workpath build/pyinstaller

# PyInstaller gives the app the macOS SDK version of its Python library: 12.1
# for the python.org Python on the release runner. WebKit then treats the
# window as an app from macOS 12 and leaves out newer web features, such as
# popovers: the menus Nieuw and Meer stood open over every page (v0.1.0).
# The app gets the SDK of the Xcode it is built with instead, and never an
# SDK older than the oldest macOS it runs on (LSMinimumSystemVersion).
app_exe=dist/Huismus.app/Contents/MacOS/Huismus
minos=$(vtool -show-build "$app_exe" | awk '/minos/ {print $2; exit}')
vtool -set-build-version macos "$minos" "$(xcrun --show-sdk-version)" -replace \
    -output "$app_exe.sdk" "$app_exe" 2>/dev/null
mv "$app_exe.sdk" "$app_exe"
chmod +x "$app_exe"
sdk=$(vtool -show-build "$app_exe" | awk '/sdk/ {print $2; exit}')
minimum=$(/usr/libexec/PlistBuddy -c "Print :LSMinimumSystemVersion" dist/Huismus.app/Contents/Info.plist)
if [ "${sdk%%.*}" -lt "${minimum%%.*}" ]; then
    echo "Huismus.app is built against macOS SDK $sdk, older than macOS $minimum" >&2
    exit 1
fi

# Ad hoc, without an Apple Developer ID (decided 2026-10-27): Apple Silicon
# starts nothing unsigned. Without --options runtime: the hardened runtime
# only loads libraries signed by the same team, and ad hoc has no team.
codesign --force --deep --sign - dist/Huismus.app

# The app on its own, with a PDF, as the release does (release.yml): a
# library that only clashes inside the app shows here, not in the tests.
dist/Huismus.app/Contents/MacOS/Huismus --check

hdiutil create -volname Huismus -srcfolder dist/Huismus.app -ov -format UDZO dist/Huismus.dmg >/dev/null
echo "Klaar: dist/Huismus.app en dist/Huismus.dmg"
