#!/usr/bin/env bash
#
# Draait automatisch aan het eind van elke beurt van Claude.
# Staat de poort op rood, dan kan de beurt niet afgesloten worden:
# Claude krijgt de fouten terug en moet ze eerst oplossen.
#
# Hoe vaak achter elkaar de poort al blokkeerde, telt dit script per sessie.
# Na MAX_POGINGEN blokkeert hij één laatste keer met de opdracht om rood te
# melden in plaats van "klaar" te zeggen, en laat dan los. Zo kan een rode
# poort niet uitgezeten worden, en blijft Claude ook niet eindeloos hangen.
#
# De teller (een bestand in $TMPDIR per sessie) gaat terug naar nul zodra de
# poort groen is, of nadat de hook heeft losgelaten. Een volgende beurt in
# dezelfde sessie begint dus weer bij poging 1.

MAX_POGINGEN=5

input=$(cat)
sessie=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("session_id", "onbekend"))
except ValueError:
    print("onbekend")
')
teller="${TMPDIR:-/tmp}/huismus-poort-${sessie}"

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0

# Niets te keuren: geen wijzigingen en HEAD staat al op GitHub, waar CI
# dezelfde poort draait. Een beurt met alleen een vraag kost zo geen
# minuten wachten.
if [ -z "$(git status --porcelain)" ] && [ -n "$(git branch -r --contains HEAD 2>/dev/null)" ]; then
  rm -f "$teller"
  exit 0
fi

# Precies deze stand was de vorige keer al groen: niet opnieuw draaien.
vingerafdruk=$(
  {
    git rev-parse HEAD
    git diff HEAD
    git ls-files --others --exclude-standard -z | xargs -0 -r sha1sum
  } | sha1sum
)
groen="$(git rev-parse --git-dir)/huismus-verify-groen"
if [ -f "$groen" ] && [ "$(cat "$groen")" = "$vingerafdruk" ]; then
  rm -f "$teller"
  exit 0
fi

# In de cloud: de Chromium van de container (zie session-start.sh).
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] && [ -x /opt/pw-browsers/chromium ]; then
  export HUISMUS_CHROMIUM_EXECUTABLE="${HUISMUS_CHROMIUM_EXECUTABLE:-/opt/pw-browsers/chromium}"
fi

if output=$(./scripts/verify.sh 2>&1); then
  echo "$vingerafdruk" > "$groen"
  rm -f "$teller"
  exit 0
fi

pogingen=$(( $(cat "$teller" 2>/dev/null || echo 0) + 1 ))

if [ "$pogingen" -gt "$MAX_POGINGEN" ]; then
  # De vorige blokkade zei al: meld rood. Nu loslaten.
  rm -f "$teller"
  exit 0
fi
echo "$pogingen" > "$teller"

if [ "$pogingen" -eq "$MAX_POGINGEN" ]; then
  echo "De verify-poort staat na $MAX_POGINGEN pogingen nog steeds op rood. Stop hiermee." >&2
  echo "Zeg NIET dat het klaar is. Meld dat de poort rood staat, laat de fout hieronder zien," >&2
  echo "en vertel wat je geprobeerd hebt en wat volgens jou de oorzaak is." >&2
else
  echo "De verify-poort staat op rood (poging $pogingen van $MAX_POGINGEN)." >&2
  echo "Los de oorzaak op; verzwak nooit een check of test om groen te krijgen:" >&2
fi
printf '%s\n' "$output" | tail -n 80 >&2
exit 2
