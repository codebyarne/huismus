#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# The release test in the window on Windows (SPEC.md M11, issue #117), run
# by .github/workflows/release.yml in Git Bash on a fresh runner:
#
#   1. The app the new installer puts in place, opened with its window on an
#      empty administration: onboarding, one invoice issued, its PDF
#      downloaded. Playwright drives the app's own WebView2 window, through
#      remote debugging on 127.0.0.1 that only this script switches on
#      (WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS; the app never sets it).
#   2. The previous release from its installer, with records from its own
#      demo_data, updates itself to the new version at its start, through
#      its own path. Then the records must be the same, a backup from
#      before the update must hold them, and the overview says so.
#
# Only on a runner of GitHub: it uses this computer's own administration.
#
# scripts/window-test-windows.sh NEW.exe NEW_VERSION PREVIOUS.exe PREVIOUS_TAG SHOTS
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "${GITHUB_ACTIONS:-}" != true ]; then
    echo "Alleen op een runner van GitHub: dit test op de echte administratie van deze computer." >&2
    exit 1
fi
new_installer=$1 new_version=$2 previous_installer=$3 previous_tag=$4 shots=$5
data="$APPDATA/Huismus"
log="$LOCALAPPDATA/Huismus/huismus.log"
exe="$LOCALAPPDATA/Programs/Huismus/Huismus.exe"
cdp=http://127.0.0.1:9222
test=(uv run python scripts/window_test.py)
mkdir -p "$shots"
# For the app and what it starts (the update's script, the new version).
export WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS="--remote-debugging-port=9222 --remote-debugging-address=127.0.0.1"

running() {
    tasklist //FI "IMAGENAME eq Huismus.exe" //NH | grep -qi "Huismus.exe"
}

quit_app() {
    # As closing the window: WM_CLOSE, which pywebview handles.
    taskkill //IM Huismus.exe >/dev/null 2>&1 || true
    for _ in $(seq 60); do
        running || return 0
        sleep 1
    done
    echo "::warning::Huismus sloot niet; gestopt"
    taskkill //F //IM Huismus.exe >/dev/null 2>&1 || true
    sleep 2
}

show_log() {
    echo "--- huismus.log"
    cat "$log" 2>/dev/null || true
}
trap show_log ERR

echo "== 1. De nieuwe versie op een lege administratie"
"$new_installer" //VERYSILENT //SUPPRESSMSGBOXES //NORESTART
rm -rf "$data" "$data.lock" "$log"
"$exe" &
"${test[@]}" first-invoice --cdp "$cdp" --shots "$shots"
quit_app

echo "== 2. Bijwerken vanaf $previous_tag"
rm -rf "$data" "$data.lock" "$APPDATA/Huismus back-ups" "$APPDATA/.huismus-update" "$log"
"$previous_installer" //VERYSILENT //SUPPRESSMSGBOXES //NORESTART
# Records made by the previous version's own code, on the place its app uses.
previous="$RUNNER_TEMP/previous"
git fetch --quiet --depth=1 origin "refs/tags/$previous_tag:refs/tags/$previous_tag"
git worktree add --quiet --detach "$previous" "$previous_tag"
(
    cd "$previous"
    export HUISMUS_DATA_DIR="$data" HUISMUS_DESKTOP=true
    uv run --no-dev python manage.py migrate --verbosity 0
    uv run --no-dev python manage.py demo_data --yes
)
"${test[@]}" records "$data/db.sqlite3" >"$RUNNER_TEMP/before.json"
cat "$RUNNER_TEMP/before.json"
"${test[@]}" pending-update "$data" "$new_installer" "$new_version"

# As a user opens it. It backs up, closes, the installer replaces it, and
# the new version opens, with the same remote debugging.
"$exe" &
for _ in $(seq 300); do
    if [ "$(grep -c "Huismus draait op" "$log" 2>/dev/null)" -ge 2 ] && running \
        && ! grep -q '"to_version"' "$data/update-status.json"; then
        break
    fi
    sleep 1
done
"${test[@]}" updated "$new_version" --cdp "$cdp" --shots "$shots/bijwerken"
quit_app

"${test[@]}" records "$data/db.sqlite3" >"$RUNNER_TEMP/after.json"
diff -u "$RUNNER_TEMP/before.json" "$RUNNER_TEMP/after.json"
backups=("$APPDATA/Huismus back-ups"/huismus-backup-*.tar.gz)
if [ ! -f "${backups[0]}" ]; then
    echo "::error::Geen back-up van vóór de update"
    exit 1
fi
"${test[@]}" records "${backups[0]}" | diff -u "$RUNNER_TEMP/before.json" -
echo "Bijgewerkt naar $new_version: gegevens gelijk, back-up van ervoor in ${backups[0]##*/}"
