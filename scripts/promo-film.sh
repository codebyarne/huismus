#!/usr/bin/env bash
#
# Maak een promofilmpje van Huismus opnieuw: tien à twintig seconden die in een
# lus spelen (1920x1080 mp4, voor LinkedIn en dergelijke). Draai dit als een
# scherm in het filmpje er anders uit is gaan zien. Duurt een paar minuten.
#
#   ./scripts/promo-film.sh factuur      # een factuur maken en uitgeven
#   ./scripts/promo-film.sh bonnetjes    # Huismus las de bonnetjes, Verwerken, Klopt
#   ./scripts/promo-film.sh bonnetjes ergens/anders.mp4 muziek.mp3
#
# Standaard naar ~/Downloads/huismus-<film>.mp4. Elke klik en toetsaanslag
# klinkt (scripts/promo/geluiden/, CC0). Muziek is optioneel: elk
# geluidsbestand, zachter onder de klikken gemengd en aan het eind uitgefaded.
# Let op de licentie van de muziek voordat je het filmpje post.
#
# Alles draait in een tijdelijke map op nepdata, los van data/
# (scripts/promo_film.py). ffmpeg komt uit het pakket imageio-ffmpeg, alleen
# voor dit commando: geen afhankelijkheid van Huismus zelf.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
film="${1:-factuur}"
out="${2:-$HOME/Downloads/huismus-$film.mp4}"
uv run --with imageio-ffmpeg python scripts/promo_film.py "$film" "$out" "${@:3}"
