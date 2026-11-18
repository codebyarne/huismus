#!/usr/bin/env bash
#
# Maak de promofilms van Huismus opnieuw (1920x1080 mp4, donker, in de
# huisstijl van de app en de site). Draai dit als een scherm in een film er
# anders uit is gaan zien. Duurt een paar minuten per film.
#
#   ./scripts/promo-film.sh              # bonnetjes en overzicht
#   ./scripts/promo-film.sh bonnetjes    # bonnetjes naar je cloudmap, Huismus leest ze, jij zegt Klopt (29 s)
#   ./scripts/promo-film.sh overzicht    # wat Huismus is en wat je ermee doet, met stem (63 s)
#   ./scripts/promo-film.sh overzicht ergens/anders
#   ./scripts/promo-film.sh site         # allebei, en de films op de site (docs/site/film-*) opnieuw, zonder geluid: commit die
#   ./scripts/promo-film.sh site-met-geluid   # hetzelfde, met het geluid erbij (pas als de eigenaar het gehoord heeft)
#   ./scripts/promo-film.sh factuur [bestand.mp4] [muziek.mp3]   # een factuur maken, met een camera boven de browser
#
# Standaard naar ~/Downloads/huismus-films/:
#
#   huismus-bonnetjes.mp4
#   huismus-overzicht.mp4               stem en muziek
#   huismus-overzicht-ondertiteld.mp4   stem en muziek, Nederlandse ondertitels in beeld
#   huismus-overzicht-zonder-stem.mp4   muziek en ondertitels in beeld
#   huismus-overzicht.nl.vtt, .en.vtt   losse ondertitels
#   stills/<film>/                      elke drie seconden een beeld, om na te kijken
#
# scripts/promo_film.py neemt de echte schermen op (nepdata, in een tijdelijke
# map, los van data/; de AI-dienst is een nepservertje in dat script, er gaat
# niets naar buiten). Remotion monteert ze in scripts/promo/film/, met de
# letters en het logo van de app zelf. Remotion draait op Node en hoort niet
# bij de app: npm installeert het de eerste keer in die map. Het rendert met
# de Chromium van Playwright (uv run playwright install chromium).
#
# De stem van de overzichtsfilm is een proefstem (macOS `say`, op deze
# computer). Een eigen opname per shot gaat in scripts/promo/film/stem/, met
# de naam van het shot (01-huismus.wav, 02-voor-wie.wav, ...: de namen staan
# in scripts/promo/film/src/overzicht.json; .mp3, .m4a en .aiff mogen ook).
# Draai dit daarna opnieuw: de montage blijft, de ondertitels schuiven mee.
# Eigen muziek: scripts/promo/film/muziek.mp3 (let op de licentie). Het
# script van de film: docs/design/films/script-overzicht.md.
#
# ffmpeg komt uit het pakket imageio-ffmpeg en numpy maakt de muziek, alleen
# voor dit commando: geen afhankelijkheden van Huismus zelf.
set -euo pipefail
cd "$(dirname "$0")/.."
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
film="${1:-alle}"
python=(uv run --with imageio-ffmpeg --with numpy python)

if [ "$film" = factuur ]; then
    exec "${python[@]}" scripts/promo_film.py factuur "${2:-$HOME/Downloads/huismus-films/huismus-factuur.mp4}" "${@:3}"
fi
case "$film" in
    alle | site | site-met-geluid) films=(bonnetjes overzicht) ;;
    bonnetjes | overzicht) films=("$film") ;;
    *) echo "promo-film.sh [bonnetjes|overzicht|site|site-met-geluid|factuur] [map]" >&2; exit 2 ;;
esac
site="$film"
out="${2:-$HOME/Downloads/huismus-films}"
mkdir -p "$out"
out="$(cd "$out" && pwd)"

remotion=scripts/promo/film
# The app's own letters and logo: the films have no copy of their own.
mkdir -p "$remotion/public/huisstijl"
cp huismus/core/static/core/fonts/*.woff2 docs/design/icons/logo-donker.svg \
    docs/design/icons/tegel-donker.svg "$remotion/public/huisstijl/"
"${python[@]}" scripts/promo_film.py opname "$remotion/public/opname"
# Both films are in one Remotion project, so the overview film's sound is
# always made: its subtitles are part of the code Remotion bundles.
"${python[@]}" scripts/promo_geluid.py "$remotion/public/opname" "$out"
[ -d "$remotion/node_modules" ] || (cd "$remotion" && npm ci --silent)
# Remotion's own browser does not start everywhere; Playwright's does.
chromium=$(find "$HOME/Library/Caches/ms-playwright" "$HOME/.cache/ms-playwright" \
    -path '*chromium_headless_shell-*' -name chrome-headless-shell -type f 2>/dev/null | sort | tail -1 || true)
ffmpeg=$("${python[@]}" -c "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())")
work="$(mktemp -d)"
trap 'rm -rf "$work"' EXIT

# render <composition> <file.mp4> [props as JSON]
render() {
    local props="${3:-}"
    (cd "$remotion" && npx remotion render src/index.ts "$1" "$work/film.mp4" --props="${props:-"{}"}" \
        --codec=h264 --crf=16 --pixel-format=yuv420p --color-space=bt709 --audio-bitrate=192k \
        --log=error ${chromium:+--browser-executable="$chromium"})
    # Even loud as other clips in a feed, without touching the picture.
    "$ffmpeg" -hide_banner -y -loglevel error -i "$work/film.mp4" -c:v copy \
        -af loudnorm=I=-15:TP=-1.5:LRA=9 -ar 48000 -c:a aac -b:a 192k -movflags +faststart "$2"
    echo "$2"
}

# stills <file.mp4> <name>: a picture every three seconds, to look the film over.
stills() {
    rm -rf "$out/stills/$2"
    mkdir -p "$out/stills/$2"
    "$ffmpeg" -hide_banner -y -loglevel error -i "$1" -vf "fps=1/3,scale=1280:-2" "$out/stills/$2/%03d.png"
}

for film in "${films[@]}"; do
    if [ "$film" = bonnetjes ]; then
        render bonnetjes "$out/huismus-bonnetjes.mp4"
        stills "$out/huismus-bonnetjes.mp4" bonnetjes
    else
        render overzicht "$out/huismus-overzicht.mp4" '{"stem": true, "ondertitels": false}'
        render overzicht "$out/huismus-overzicht-ondertiteld.mp4" '{"stem": true, "ondertitels": true}'
        render overzicht "$out/huismus-overzicht-zonder-stem.mp4" '{"stem": false, "ondertitels": true}'
        stills "$out/huismus-overzicht-ondertiteld.mp4" overzicht
    fi
done

# web <film.mp4> <name> <poster.mp4> <second>: the film as the site shows it
# (docs/site/film-<name>.nl.mp4: 1280x720, small, starts playing before it is
# all there) and the still it shows until you press play, taken from
# <poster.mp4> at <second>. Dutch only: the titles and the screens are Dutch.
# Without a sound track, unless this was called as site-met-geluid: nobody
# has listened to the music yet (owner, 2026-11-19).
web() {
    local sound=(-an)
    [ "$site" = site-met-geluid ] && sound=(-c:a aac -b:a 96k)
    "$ffmpeg" -hide_banner -y -loglevel error -i "$1" -vf scale=1280:-2 -c:v libx264 -crf 28 \
        -preset slow -pix_fmt yuv420p "${sound[@]}" -movflags +faststart "docs/site/film-$2.nl.mp4"
    "$ffmpeg" -hide_banner -y -loglevel error -ss "$4" -i "$3" -frames:v 1 -vf scale=1280:-2 \
        -c:v libwebp -quality 82 "docs/site/film-$2.nl.webp"
    echo "docs/site/film-$2.nl.mp4"
}

if [ "$site" = site ] || [ "$site" = site-met-geluid ]; then
    # The version without the voice, while that is a trial voice: subtitles in
    # the picture. The still is from the version without them.
    web "$out/huismus-overzicht-zonder-stem.mp4" overzicht "$out/huismus-overzicht.mp4" 11
    web "$out/huismus-bonnetjes.mp4" bonnetjes "$out/huismus-bonnetjes.mp4" 1.1
fi
