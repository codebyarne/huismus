#!/usr/bin/env bash
#
# DE POORT van Huismus.
#
# Eén commando dat ja of nee zegt. "Klaar" betekent niet dat het er goed
# uitziet — het betekent dat dit script groen afsloot.
#
# De controles groeien mee met het project. Wat hieronder aan staat werkt
# vandaag. De rest staat klaar en zet je aan zodra M0 er is: haal het
# commentaarteken weg, meer is het niet.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# The hook that runs this script does not necessarily inherit an interactive
# shell's PATH. Add uv's common install locations so the gate does not fail
# with "uv: command not found" regardless of who calls it.
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"

status=0
stap() { printf '\n— %s\n' "$1"; }
faal() { echo "  FOUT: $*"; status=1; }
ok()   { echo "  ok — $*"; }

# ---------------------------------------------------------------
# 1. Geen echte administratie in git
#    De belangrijkste controle van dit project. Huismus wordt publiek
#    onder AGPL; data-import/ bevat een echte Moneybird-administratie.
# ---------------------------------------------------------------
stap "Echte administratie mag niet in git"
if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  gelekt=$(git ls-files -- 'data-import/*' 'data/*' '*.sqlite3' '.env' 2>/dev/null)
  if [ -n "$gelekt" ]; then
    faal "deze bestanden staan in git en horen daar niet thuis:"
    echo "$gelekt" | sed 's/^/        /'
  else
    ok "geen administratiebestanden in git"
  fi
  if [ -d data-import ] && ! git check-ignore -q data-import; then
    faal "data-import/ wordt niet door .gitignore genegeerd"
  fi
else
  echo "  overgeslagen — nog geen git repo"
fi

# ---------------------------------------------------------------
# 2. Vanaf M0
# ---------------------------------------------------------------
stap "Lint en formatting"
uv run ruff check .            || faal "ruff check"
uv run ruff format --check .   || faal "ruff format"

stap "Tests"
uv run pytest -q -n auto       || faal "pytest"  # -n: pytest-xdist, alle cores

stap "Migraties compleet"
SECRET_KEY=verify-only DEBUG=true uv run python manage.py makemigrations --check \
  || faal "ontbrekende migratie"

echo
if [ $status -eq 0 ]; then
  echo "POORT GROEN"
else
  echo "POORT ROOD"
fi
exit $status
