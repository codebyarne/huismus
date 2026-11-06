#!/usr/bin/env bash
#
# Start Huismus met 9 jaar nepdata (huismus/core/demo_history.py) in een tijdelijke
# map, los van data/. Voor handmatig kijken en voor de verify-e2e-agent:
# één commando, en de echte administratie wordt nooit aangeraakt.
#
#   ./scripts/demo-server.sh            # http://127.0.0.1:8790, login demo / demo-wachtwoord-123
#   PORT=9000 ./scripts/demo-server.sh
#   HUISMUS_DESKTOP=true ./scripts/demo-server.sh   # zoals de desktop-app (SPEC.md M11):
#                                                   # open de start-URL die hij print
#   HUISMUS_RELEASES_URL=file://$PWD/tests/fixtures/releases/releases.json  # updates tegen een
#                                                   # nep-releaselijst (docs/desktop.md)
#
# De map wordt verwijderd zodra de server stopt.
set -euo pipefail
cd "$(dirname "$0")/.."
# uv staat vaak niet in het PATH van een niet-interactieve shell (zoals die van
# een agent); zelfde regel als in scripts/verify.sh.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

port="${PORT:-8790}"
HUISMUS_DATA_DIR="$(mktemp -d)"
trap 'rm -rf "$HUISMUS_DATA_DIR"' EXIT
# huismus/config/settings.py leest de database en bestanden uit HUISMUS_DATA_DIR.
export HUISMUS_DATA_DIR SECRET_KEY=demo-only DEBUG=true
# Mailen werkt in de demo, maar de console-backend print elke mail in deze
# terminal: er gaat nooit iets naar een echte mailserver.
export HUISMUS_EMAIL_BACKEND=django.core.mail.backends.console.EmailBackend
# De desktopstand wil het venstertoken (huismus/core/desktop.py); hier een vast token.
if [ "${HUISMUS_DESKTOP:-}" = "true" ]; then
  export HUISMUS_WINDOW_TOKEN=demo-token
fi

uv run python manage.py migrate --verbosity 0
uv run python manage.py demo_data --yes --history
DJANGO_SUPERUSER_PASSWORD=demo-wachtwoord-123 uv run python manage.py createsuperuser \
  --noinput --username demo --email demo@example.invalid
uv run python manage.py shell -c "from huismus.business.models import Settings
s = Settings.load(); s.smtp_provider = 'gmail'; s.smtp_host = 'smtp.gmail.com'; s.smtp_port = 587
s.smtp_security = 'starttls'; s.smtp_username = 'demo@example.invalid'; s.save()
from huismus.business import smtp; smtp.set_password('demo-niet-echt')"

echo
echo "Huismus met nepdata: http://127.0.0.1:$port  (demo / demo-wachtwoord-123)"
if [ "${HUISMUS_DESKTOP:-}" = "true" ]; then
  echo "Desktopstand: begin bij http://127.0.0.1:$port/desktop/start/?token=demo-token"
fi
# runserver_with_receipts: runserver plus het ophalen uit de bonnetjesmap
# (SPEC.md M20), zoals in Docker en de desktop-app.
uv run python manage.py runserver_with_receipts "127.0.0.1:$port" --noreload
