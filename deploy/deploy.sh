#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
#
# Deploys one commit of Huismus on the Pi (docs/deploy.md):
#   1. main moves to exactly that commit (the one CI tested)
#   2. a new image is built — the running container keeps serving meanwhile
#   3. a backup of the running data is copied off the volume
#   4. the container is replaced (migrations run on start, see
#      docker/entrypoint.sh) and must answer within a minute; if it doesn't,
#      the previous image is started again.
# How it went goes to GitHub and the phone (deploy/notify.sh), if set up.
#
# Called by deploy/webhook.py; by hand: deploy/deploy.sh <commit-sha>
set -euo pipefail

# Everything inside main(), called on the last line: bash reads a script
# as it runs, and the git merge below replaces this very file. Wrapped in
# a function, the whole script is read before any of it runs.
main() {
sha="${1:?gebruik: deploy/deploy.sh <commit-sha>}"
repo="$(cd "$(dirname "$0")/.." && pwd)"
backups="$HOME/huismus-backups/voor-deploy"
keep_backups=10

log() { echo "[$(date '+%F %T')] $*"; }
notify() {
  if [ -x "$repo/deploy/notify.sh" ]; then "$repo/deploy/notify.sh" "$sha" "$@"; fi
}

# One deploy at a time; a second one waits its turn.
exec 9>/tmp/huismus-deploy.lock
flock 9

# Set once the outcome has been reported. Any other way out of this script
# (set -e stops it at the first failing command, e.g. a broken build) is
# reported as a failure.
reported=""
trap '[ -n "$reported" ] || notify failure "Deploy van ${sha:0:12} afgebroken; zie pm2 logs huismus-webhook."' EXIT

cd "$repo"
git fetch --quiet origin main
if [ "$(git rev-parse HEAD)" != "$sha" ] && git merge-base --is-ancestor "$sha" HEAD; then
  log "Er draait al een nieuwere versie dan ${sha:0:12}; niets te doen."
  reported="overgeslagen"
  exit 0
fi
git merge --ff-only --quiet "$sha"
notify pending "Deploy naar de Pi bezig"

tag="huismus:${sha:0:12}"
log "Image $tag bouwen"
docker build --quiet -t "$tag" -t huismus:latest . >/dev/null

previous=""
if docker container inspect huismus >/dev/null 2>&1; then
  previous="$(docker inspect -f '{{.Config.Image}}' huismus)"
  log "Backup van de huidige data (draait op $previous)"
  mkdir -p "$backups"
  docker exec huismus python manage.py backup /tmp/deploy-backup >/dev/null
  docker cp huismus:/tmp/deploy-backup/. "$backups/"
  docker exec huismus rm -rf /tmp/deploy-backup
  # Only the newest few: these are a safety net for a deploy, not the
  # real backups (docs/backups.md).
  ls -1t "$backups"/huismus-backup-*.tar.gz | tail -n +$((keep_backups + 1)) | xargs -r rm --
fi

start() {
  docker rm -f huismus >/dev/null 2>&1 || true
  docker run -d --name huismus --restart unless-stopped \
    --env-file "$repo/.env" \
    -v huismus-data:/app/data \
    -p 127.0.0.1:8000:8000 \
    "$1" >/dev/null
}

# The login page, with a host from ALLOWED_HOSTS: anything else gets a 400.
host="$(grep '^ALLOWED_HOSTS=' "$repo/.env" | cut -d= -f2 | cut -d, -f1)"
answers() {
  for _ in $(seq 30); do
    # Quiet: while gunicorn starts, every attempt is refused.
    curl -fs -o /dev/null -H "Host: $host" http://127.0.0.1:8000/login/ && return 0
    sleep 2
  done
  return 1
}

log "Container vervangen door $tag"
start "$tag"
if answers; then
  log "Huismus ${sha:0:12} draait."
  reported="gelukt"
  notify success "Huismus ${sha:0:12} draait."
  # Old images: keep this one and the one before it.
  docker images huismus --format '{{.Repository}}:{{.Tag}}' \
    | grep -v -x -e "$tag" -e "${previous:-none}" -e huismus:latest \
    | xargs -r docker rmi >/dev/null 2>&1 || true
  exit 0
fi

log "FOUT: $tag antwoordt niet. Laatste logregels:"
docker logs --tail 40 huismus 2>&1 || true
if [ -n "$previous" ]; then
  log "Terug naar $previous. Let op: migraties van $tag kunnen al gedraaid hebben;"
  log "de backup van vlak ervoor staat in $backups."
  start "$previous"
fi
reported="mislukt"
if [ -n "$previous" ]; then
  notify failure "${sha:0:12} antwoordde niet; $previous draait weer."
else
  notify failure "${sha:0:12} antwoordde niet, en er was geen vorige versie."
fi
exit 1
}

main "$@"
