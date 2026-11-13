#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Packs the Windows app for the Microsoft Store (SPEC.md M11, "Microsoft
# Store"): dist/Huismus-<version>-windows.msix, from the dist/Huismus folder
# scripts/build-windows.sh made. Same Huismus.exe as the installer.
#
# Unsigned: the Store signs what it publishes. To install it yourself, sign a
# copy (release.yml does that with a throwaway certificate to check it).
# Needs the Windows SDK's makeappx.exe (on GitHub's Windows runners), and the
# identity Partner Center reserved in MSIX_IDENTITY_NAME, MSIX_PUBLISHER and
# MSIX_PUBLISHER_DISPLAY_NAME (desktop/msix.py, docs/desktop.md).
set -euo pipefail
cd "$(dirname "$0")/.."

version=$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)
sdk=$(ls -d "/c/Program Files (x86)/Windows Kits/10/bin/10."*/x64 | sort -V | tail -n 1)
makeappx="${MAKEAPPX:-$sdk/makeappx.exe}"

test -f dist/Huismus/Huismus.exe || { echo "Eerst scripts/build-windows.sh" >&2; exit 1; }
rm -rf build/msix "dist/Huismus-$version-windows.msix"
mkdir -p build
cp -r dist/Huismus build/msix
uv run python -m desktop.msix "$version" build/msix

"$makeappx" pack //o //d "$(cygpath -w build/msix)" //p "$(cygpath -w "dist/Huismus-$version-windows.msix")"
echo "Klaar: dist/Huismus-$version-windows.msix"
