#!/usr/bin/env bash
#
# Maak een promofilmpje van Huismus opnieuw: rond de twintig seconden die in
# een lus spelen (1920x1080 mp4, voor LinkedIn en dergelijke). Draai dit als
# een scherm in het filmpje er anders uit is gaan zien. Duurt een paar minuten.
#
#   ./scripts/promo-film.sh bonnetjes    # bonnetjes naar je cloudmap, Huismus leest ze, jij zegt Klopt
#   ./scripts/promo-film.sh factuur      # een factuur maken en uitgeven
#   ./scripts/promo-film.sh factuur ergens/anders.mp4 muziek.mp3
#
# Standaard naar ~/Downloads/huismus-<film>.mp4.
#
# bonnetjes: scripts/promo_film.py neemt de echte schermen op (nepdata, in een
# tijdelijke map, los van data/), Remotion monteert ze in scripts/promo/film/
# (titels, bewegingen, in de stijl van Huismus). Remotion draait op Node en
# hoort niet bij de app: npm installeert het de eerste keer in die map. Het
# rendert met de Chromium van Playwright (uv run playwright install chromium).
#
# factuur: gefilmd met een camera boven de browser, met klik- en
# toetsgeluiden; muziek is optioneel (let op de licentie). ffmpeg komt uit
# het pakket imageio-ffmpeg, alleen voor dit commando.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
film="${1:-bonnetjes}"
out="${2:-$HOME/Downloads/huismus-$film.mp4}"

if [ "$film" != bonnetjes ]; then
    exec uv run --with imageio-ffmpeg python scripts/promo_film.py "$film" "$out" "${@:3}"
fi

remotion=scripts/promo/film
uv run --with imageio-ffmpeg python scripts/promo_film.py opname "$remotion/public/opname"
[ -d "$remotion/node_modules" ] || (cd "$remotion" && npm ci --silent)
# Remotion's own browser does not start everywhere; Playwright's does.
chromium=$(find "$HOME/Library/Caches/ms-playwright" "$HOME/.cache/ms-playwright" \
    -path '*chromium_headless_shell-*' -name chrome-headless-shell -type f 2>/dev/null | sort | tail -1 || true)
mix="$(mktemp -d)/film.mp4"
(cd "$remotion" && npx remotion render src/index.ts bonnetjes "$mix" \
    --codec=h264 --crf=16 --pixel-format=yuv420p --color-space=bt709 --audio-bitrate=192k --log=error ${chromium:+--browser-executable="$chromium"})
# Even loud as other clips in a feed, without touching the picture.
ffmpeg=$(uv run --with imageio-ffmpeg python -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
"$ffmpeg" -hide_banner -y -loglevel error -i "$mix" -c:v copy \
    -af loudnorm=I=-15:TP=-1.5:LRA=9 -ar 48000 -c:a aac -b:a 192k -movflags +faststart "$out"
rm -rf "$(dirname "$mix")"
echo "$out"
