#!/usr/bin/env bash
# `gh project` voor het bord "Huismus", lokaal en in een cloudsessie.
#
# Een cloudsessie kan via de GitHub-koppeling van Claude niet bij een Project
# op een persoonlijk account. Daarom staat er in de cloud-omgeving een klassiek
# token met alleen het recht `project` als GH_PROJECT_TOKEN. Alleen dit script
# gebruikt het; de rest van `gh` (issues, PR's) blijft op de gewone koppeling.
# Lokaal is GH_PROJECT_TOKEN er niet en gebruikt gh je eigen login.
#
# Voorbeeld: ./scripts/bord.sh item-list 1 --owner codebyarne --format json
set -euo pipefail

if [[ -n "${GH_PROJECT_TOKEN:-}" ]]; then
  export GH_TOKEN="$GH_PROJECT_TOKEN"
fi

exec gh project "$@"
