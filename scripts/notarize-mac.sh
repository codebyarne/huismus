#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Has Apple notarize the Mac app that scripts/build-mac.sh signed with the
# Developer ID, so that it opens with a double-click (decided 2026-11-12).
# Run by release.yml; set up once with scripts/mac-ondertekenen.sh.
#
# First the app, so it carries its own ticket (the updater copies it out of
# the .dmg), then a new .dmg around it, which gets one too.
#
# Needs: HUISMUS_SIGN_IDENTITY, and an App Store Connect API key in
# APPLE_API_KEY_PATH (the .p8 file), APPLE_API_KEY_ID and APPLE_API_ISSUER.
set -euo pipefail
cd "$(dirname "$0")/.."

notarize() {
    local file=$1 result id
    result=$(xcrun notarytool submit "$file" --wait --output-format json \
        --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER")
    if ! grep -q '"status" *: *"Accepted"' <<<"$result"; then
        echo "Apple keurde $file af: $result" >&2
        id=$(sed -n 's/.*"id" *: *"\([^"]*\)".*/\1/p' <<<"$result" | head -n 1)
        if [ -n "$id" ]; then
            xcrun notarytool log "$id" \
                --key "$APPLE_API_KEY_PATH" --key-id "$APPLE_API_KEY_ID" --issuer "$APPLE_API_ISSUER" >&2
        fi
        exit 1
    fi
}

zip=build/Huismus-notarize.zip
rm -f "$zip"
ditto -c -k --keepParent dist/Huismus.app "$zip"
notarize "$zip"
xcrun stapler staple dist/Huismus.app

rm -f dist/Huismus.dmg
hdiutil create -volname Huismus -srcfolder dist/Huismus.app -ov -format UDZO dist/Huismus.dmg >/dev/null
codesign --force --sign "$HUISMUS_SIGN_IDENTITY" --timestamp dist/Huismus.dmg
notarize dist/Huismus.dmg
xcrun stapler staple dist/Huismus.dmg

# What a Mac checks when someone opens the download: both must pass.
spctl --assess --type execute --verbose=2 dist/Huismus.app
spctl --assess --type open --context context:primary-signature --verbose=2 dist/Huismus.dmg
echo "Genotariseerd: dist/Huismus.app en dist/Huismus.dmg"
