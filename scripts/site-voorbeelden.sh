#!/usr/bin/env bash
#
# Maak de voorbeelden voor de Huismus-site opnieuw (docs/site/voorbeelden/):
# een factuur met en zonder btw, een offerte en een urenstaat, elk als Word,
# Excel en pdf, in het Nederlands en Engels, met verzonnen gegevens. Draai dit
# als de pdf van Huismus of een voorbeeld verandert, en commit de bestanden.
#
#   ./scripts/site-voorbeelden.sh
#
# Alles draait in een tijdelijke map, los van data/ (scripts/site_voorbeelden.py).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
# Zonder gecompileerde vertalingen zijn de Engelse voorbeelden Nederlands.
uv run python manage.py compilemessages --ignore=.venv > /dev/null
uv run python scripts/site_voorbeelden.py docs/site/voorbeelden
