#!/usr/bin/env bash
#
# Maak het promofilmpje van Huismus opnieuw: zestien stille seconden die in een
# lus spelen (1920x1080 mp4, voor LinkedIn en dergelijke). Een nieuwe factuur
# krijgt een klant en een regel, Huismus telt op, en hij wordt uitgegeven.
# Draai dit als dat scherm er anders uit is gaan zien. Duurt een paar minuten.
#
#   ./scripts/promo-film.sh                    # naar ~/Downloads/huismus-factuur.mp4
#   ./scripts/promo-film.sh ergens/anders.mp4
#   ./scripts/promo-film.sh ergens/anders.mp4 muziek.mp3   # met muziek eronder
#
# Elke klik en toetsaanslag krijgt een zacht tikje (scripts/promo-geluiden/, CC0). Muziek is optioneel: elk
# geluidsbestand, zachter onder de tikjes gemengd en aan het eind uitgefaded.
# Let op de licentie van de muziek voordat je het filmpje post.
#
# Alles draait in een tijdelijke map op nepdata, los van data/
# (scripts/promo_film.py). ffmpeg komt uit het pakket imageio-ffmpeg, alleen
# voor dit commando: geen afhankelijkheid van Huismus zelf.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
out="${1:-$HOME/Downloads/huismus-factuur.mp4}"
uv run --with imageio-ffmpeg python scripts/promo_film.py "$out" "${@:2}"
