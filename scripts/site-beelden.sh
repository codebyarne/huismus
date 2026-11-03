#!/usr/bin/env bash
#
# Maak de beelden voor de Huismus-site opnieuw (docs/site/): schermafbeeldingen
# en korte animaties van de app, in het Nederlands en Engels, licht en donker.
# Draai dit als een scherm dat op de site staat er anders uit is gaan zien, en
# commit de nieuwe beelden. Duurt een paar minuten.
#
#   ./scripts/site-beelden.sh
#
# Alles draait in een tijdelijke map, los van data/ (scripts/site_beelden.py).
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
uv run python scripts/site_beelden.py docs/site
