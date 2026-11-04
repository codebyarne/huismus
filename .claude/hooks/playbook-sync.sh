#!/usr/bin/env bash
#
# Draait aan het eind van elke beurt, na de verify-poort. Huismus is het
# project waar de werkwijze uit `codebyarne/agentic-playbook` vandaan komt:
# elke verbetering aan de workflow hier hoort daar ook te landen (afgesproken
# zie CLAUDE.md "Playbook bijhouden").
#
# Raakt deze branch een workflowbestand (WORKFLOW hieronder) en heeft geen
# commit sinds origin/main een regel "Playbook: ...", dan blokkeert de hook
# de beurt met de opdracht om de playbook bij te werken, of te noteren
# waarom dat niet hoeft. Hoogstens MAX_KEER per sessie, daarna laat hij los,
# zodat een sessie zonder toegang tot de playbook niet blijft hangen.

MAX_KEER=2

# Bestanden en mappen die de werkwijze vastleggen (geen productcode).
WORKFLOW='^(CLAUDE\.md|\.claude/|scripts/verify\.sh|\.github/workflows/)'

input=$(cat)
sessie=$(printf '%s' "$input" | python3 -c '
import json, sys
try:
    print(json.load(sys.stdin).get("session_id", "onbekend"))
except ValueError:
    print("onbekend")
')
teller="${TMPDIR:-/tmp}/huismus-playbook-${sessie}"

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
basis=$(git merge-base HEAD origin/main 2>/dev/null) || exit 0

gewijzigd=$(
  {
    git diff --name-only "$basis"
    git ls-files --others --exclude-standard
  } | grep -E "$WORKFLOW" | sort -u
)
if [ -z "$gewijzigd" ]; then
  rm -f "$teller"
  exit 0
fi

if git log --format=%B "$basis..HEAD" | grep -qE '^Playbook: '; then
  rm -f "$teller"
  exit 0
fi

keer=$(( $(cat "$teller" 2>/dev/null || echo 0) + 1 ))
if [ "$keer" -gt "$MAX_KEER" ]; then
  exit 0
fi
echo "$keer" > "$teller"

{
  echo "Deze branch wijzigt de workflow van Huismus:"
  printf '%s\n' "$gewijzigd" | sed 's/^/  /'
  echo
  echo "Werk ook codebyarne/agentic-playbook bij (CLAUDE.md, \"Playbook bijhouden\"):"
  echo "het generieke deel, in het Engels, zonder namen van Huismus, de eigenaar of anderen,"
  echo "op een eigen branch met een PR, en ./scripts/verify.sh daar groen."
  echo "Zet daarna in een commit hier de regel:"
  echo "  Playbook: <url van de PR of commit>"
  echo "Is de wijziging alleen voor Huismus (bijv. een pad, een poort, een tekst), dan:"
  echo "  Playbook: n.v.t. — <waarom>"
  if [ "$keer" -eq "$MAX_KEER" ]; then
    echo
    echo "Dit is de laatste herinnering. Lukt het niet (geen toegang tot de playbook),"
    echo "meld dan aan de eigenaar dat de playbook nog bijgewerkt moet worden en waarmee."
  fi
} >&2
exit 2
