#!/usr/bin/env bash
# Houdt twee labels gelijk met het bord "Huismus", zodat een cloudsessie de
# wachtrij kan volgen zonder zelf bij het bord te kunnen (CLAUDE.md, "Backlog").
#
#   volgende  staat op precies één open issue: het bovenste van de wachtrij.
#   bezig     zet een sessie zelf op een issue; met BEZIG_ISSUE=<nummer> zet dit
#             script dat issue op het bord op In Progress.
#
# Draait in .github/workflows/bord.yml. Lokaal kan ook, met je eigen gh-login:
#   DRY_RUN=1 ./scripts/bord-sync.sh     # zegt alleen wat het zou doen
set -euo pipefail
cd "$(dirname "$0")/.."

REPO=codebyarne/huismus
PROJECT_ID=PVT_kwHOELVXCM4BqhnM
STATUS_FIELD=PVTSSF_lAHOELVXCM4BqhnMzho4YqM
IN_PROGRESS=47fc9ee4
# "@me" en niet codebyarne: met een naam zoekt gh project eerst op of het een
# gebruiker of organisatie is, en dat mag het token met alleen `project` niet
# ("unknown owner type"). Het token en de lokale login zijn allebei van de eigenaar.
OWNER="@me"

run() {
  if [[ -n "${DRY_RUN:-}" ]]; then
    echo "zou doen: $*"
  else
    "$@"
  fi
}

board_items() {
  ./scripts/bord.sh item-list 1 --owner "$OWNER" --limit 500 --format json
}

items=$(board_items)

if [[ -n "${BEZIG_ISSUE:-}" ]]; then
  item=$(jq -r --argjson n "$BEZIG_ISSUE" --arg repo "$REPO" \
    '.items[] | select(.content.type == "Issue" and .content.repository == $repo and .content.number == $n) | .id' \
    <<<"$items")
  if [[ -z "$item" ]]; then
    item=$(run ./scripts/bord.sh item-add 1 --owner "$OWNER" \
      --url "https://github.com/$REPO/issues/$BEZIG_ISSUE" --format json --jq .id)
  fi
  echo "#$BEZIG_ISSUE is bezig: op het bord naar In Progress"
  run ./scripts/bord.sh item-edit --project-id "$PROJECT_ID" --id "$item" \
    --field-id "$STATUS_FIELD" --single-select-option-id "$IN_PROGRESS"
  [[ -z "${DRY_RUN:-}" ]] && items=$(board_items)
fi

# Het bord kent de staat van een issue niet; een gesloten issue kan nog even op
# Todo staan tot de regel "Item closed" van het bord het op Done zet.
open_issues=$(gh api --paginate "repos/$REPO/issues?state=open&per_page=100" \
  --jq '[.[] | select(.pull_request | not) | .number]' | jq -s 'add // []')

# Dezelfde wachtrij als in CLAUDE.md: bovenste Todo-issue zonder wacht, idee of pauze.
next=$(jq -r --argjson open "$open_issues" --arg repo "$REPO" '
  [.items[]
   | select(.content.type == "Issue" and .content.repository == $repo and .status == "Todo")
   | select(.content.number as $n | $open | index($n))
   | select((.labels // []) | any(. == "wacht" or . == "idee" or . == "pauze") | not)
  ][0].content.number // empty' <<<"$items")

labelled=$(gh api "repos/$REPO/issues?labels=volgende&state=all&per_page=100" --jq '.[].number')

for n in $labelled; do
  if [[ "$n" != "$next" ]]; then
    echo "#$n is niet meer de volgende"
    run gh api -X DELETE "repos/$REPO/issues/$n/labels/volgende" --silent
  fi
done

if [[ -z "$next" ]]; then
  echo "De wachtrij is leeg"
elif grep -qx "$next" <<<"$labelled"; then
  echo "#$next is al de volgende"
else
  echo "#$next is de volgende"
  run gh api -X POST "repos/$REPO/issues/$next/labels" -f 'labels[]=volgende' --silent
fi
