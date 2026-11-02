#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Tells how a deploy went (docs/deploy.md), to whichever is set up in
# .env.webhook:
#   GITHUB_STATUS_TOKEN  a commit status "deploy/pi" on GitHub
#   NTFY_URL             a push message to the phone (ntfy), for the outcome
#
# Usage: deploy/notify.sh <commit-sha> pending|success|failure <message>
# Called by deploy/deploy.sh. A notification that fails is logged and
# otherwise ignored: it must never turn a good deploy into a failed one.
set -uo pipefail

sha="${1:?gebruik: deploy/notify.sh <commit-sha> <state> <bericht>}"
state="${2:?}"
message="${3:?}"
repo="$(cd "$(dirname "$0")/.." && pwd)"

setting() { grep "^$1=" "$repo/.env.webhook" 2>/dev/null | head -n1 | cut -d= -f2-; }

# A file with the headers, so a secret never appears on curl's command line
# (which every user on the Pi can see in the process list).
headers="$(mktemp)"
trap 'rm -f "$headers"' EXIT

# send <name> <curl arguments...>
send() {
  local name="$1"
  shift
  curl --silent --show-error --fail --max-time 10 --output /dev/null "$@" \
    || echo "Let op: melding naar $name niet verstuurd."
}

token="$(setting GITHUB_STATUS_TOKEN)"
if [ -n "$token" ]; then
  # owner/name from the remote: git@github.com:owner/name.git or
  # https://github.com/owner/name.git
  slug="$(git -C "$repo" remote get-url origin | sed -E 's#^.*github\.com[:/]##; s#\.git$##')"
  printf 'Authorization: Bearer %s\nAccept: application/vnd.github+json\n' "$token" > "$headers"
  # The description is cut to GitHub's limit of 140 characters; quotes and
  # backslashes would break the JSON, and deploy.sh's messages have neither.
  description="${message:0:140}"
  send GitHub "https://api.github.com/repos/$slug/statuses/$sha" \
    --header "@$headers" \
    --data "{\"state\":\"$state\",\"context\":\"deploy/pi\",\"description\":\"$description\"}"
fi

ntfy="$(setting NTFY_URL)"
if [ -n "$ntfy" ] && [ "$state" != pending ]; then
  if [ "$state" = success ]; then
    printf 'Title: Huismus staat live\nTags: white_check_mark\n' > "$headers"
  else
    printf 'Title: Huismus-deploy mislukt\nTags: warning\nPriority: high\n' > "$headers"
  fi
  send ntfy "$ntfy" --header "@$headers" --data "$message"
fi
exit 0
