#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The release test in the window on macOS (SPEC.md M11, issue #117), run by
# .github/workflows/release.yml on a fresh runner:
#
#   1. Huismus.app from the new .dmg, opened with its window on an empty
#      administration: onboarding, one invoice issued, its PDF downloaded.
#      Playwright can't reach a WKWebView, so it drives the same server with
#      a token this script hands the app (desktop/app.py), and a screenshot
#      of the window shows it opened.
#   2. The previous release from its .dmg, with records from its own
#      demo_data, updates itself to the new version at its start, through
#      its own path. Then the records must be the same, a backup from
#      before the update must hold them, and the overview says so.
#
# Only on a runner of GitHub: it uses this Mac's own administration and
# /Applications, as a user's app does.
#
# scripts/window-test-mac.sh NEW.dmg NEW_VERSION PREVIOUS.dmg PREVIOUS_TAG SHOTS
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${GITHUB_ACTIONS:-}" != true ]; then
    echo "Alleen op een runner van GitHub: dit test op de echte administratie van deze Mac." >&2
    exit 1
fi
new_dmg=$1 new_version=$2 previous_dmg=$3 previous_tag=$4 shots=$5
support="$HOME/Library/Application Support"
data="$support/Huismus"
log="$HOME/Library/Logs/Huismus/huismus.log"
app=/Applications/Huismus.app
test=(uv run --group desktop python scripts/window_test.py)
mkdir -p "$shots"

install_dmg() {
    local mount
    mount=$(mktemp -d)
    hdiutil attach -nobrowse -readonly -mountpoint "$mount" "$1" >/dev/null
    rm -rf "$app"
    ditto "$mount/Huismus.app" "$app"
    hdiutil detach "$mount" -quiet
}

quit_app() {
    osascript -e 'quit app "Huismus"' >/dev/null 2>&1 || true
    for _ in $(seq 60); do
        pgrep -x Huismus >/dev/null || return 0
        sleep 1
    done
    echo "::warning::Huismus sloot niet; gestopt"
    pkill -x Huismus || true
    sleep 2
}

start_with_token() {
    # A new token, known to this script and the app only; masked in the log.
    token=$(python3 -c 'import secrets; print(secrets.token_urlsafe(32))')
    echo "::add-mask::$token"
    HUISMUS_RELEASE_TEST_TOKEN="$token" "$app/Contents/MacOS/Huismus" >/dev/null 2>&1 &
}

show_log() {
    echo "--- huismus.log"
    cat "$log" 2>/dev/null || true
}
trap show_log ERR

echo "== 1. De nieuwe versie op een lege administratie"
install_dmg "$new_dmg"
rm -rf "$data" "$data.lock" "$log"
start_with_token
"${test[@]}" mac-window "$shots/00-venster.png"
HUISMUS_RELEASE_TEST_TOKEN="$token" "${test[@]}" first-invoice --server --shots "$shots"
"${test[@]}" mac-window "$shots/12-venster.png"
quit_app

echo "== 2. Bijwerken vanaf $previous_tag"
rm -rf "$data" "$data.lock" "$support/Huismus back-ups" "$support/.huismus-update" "$log"
install_dmg "$previous_dmg"
# Records made by the previous version's own code, on the place its app uses.
previous="$RUNNER_TEMP/previous"
git fetch --quiet --depth=1 origin "refs/tags/$previous_tag:refs/tags/$previous_tag"
git worktree add --quiet --detach "$previous" "$previous_tag"
(
    cd "$previous"
    export HUISMUS_DATA_DIR="$data" HUISMUS_DESKTOP=true
    # Without Django's checks: they load every page, the PDF too, and this
    # runner has no Pango outside the app. Making records needs no PDF.
    uv run --no-dev python manage.py migrate --verbosity 0 --skip-checks
    uv run --no-dev python manage.py demo_data --yes --skip-checks
)
"${test[@]}" records "$data/db.sqlite3" >"$RUNNER_TEMP/before.json"
cat "$RUNNER_TEMP/before.json"
"${test[@]}" pending-update "$data" "$new_dmg" "$new_version"

# As a user opens it. It backs up, closes, is replaced, and opens again.
open "$app"
for _ in $(seq 600); do
    starts=$(cat "$log" 2>/dev/null | grep -c "Huismus draait op" || true)
    if [ "$starts" -ge 2 ] && pgrep -x Huismus >/dev/null \
        && ! grep -q '"to_version"' "$data/update-status.json"; then
        updated=yes
        break
    fi
    sleep 1
done
if [ "${updated:-}" != yes ]; then
    echo "::error::Bijwerken was na 600 s niet klaar"
    show_log
    echo "--- update-status.json"
    cat "$data/update-status.json" || true
    pgrep -lf Huismus || true
    "${test[@]}" mac-window "$shots/20-venster-niet-bijgewerkt.png" || true
    exit 1
fi
version=$(defaults read "$app/Contents/Info.plist" CFBundleShortVersionString)
if [ "$version" != "$new_version" ]; then
    echo "::error::Na het bijwerken staat versie $version er, niet $new_version"
    exit 1
fi
"${test[@]}" mac-window "$shots/20-venster-bijgewerkt.png"
quit_app

# Driven once more with a token of this script's own: the overview and pages.
# A log of its own, so the test reads this start's address, not an earlier one.
mv "$log" "$RUNNER_TEMP/huismus-bijwerken.log"
start_with_token
HUISMUS_RELEASE_TEST_TOKEN="$token" "${test[@]}" updated "$new_version" --server --shots "$shots/bijwerken"
quit_app

"${test[@]}" records "$data/db.sqlite3" >"$RUNNER_TEMP/after.json"
diff -u "$RUNNER_TEMP/before.json" "$RUNNER_TEMP/after.json"
backups=("$support/Huismus back-ups"/huismus-backup-*.tar.gz)
if [ ! -f "${backups[0]}" ]; then
    echo "::error::Geen back-up van vóór de update"
    exit 1
fi
"${test[@]}" records "${backups[0]}" | diff -u "$RUNNER_TEMP/before.json" -
echo "Bijgewerkt naar $new_version: gegevens gelijk, back-up van ervoor in ${backups[0]##*/}"
