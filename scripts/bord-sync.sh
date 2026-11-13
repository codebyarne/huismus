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
# Direct GraphQL en niet `gh project`: dat eist voor elk token ook read:org en
# read:discussion, en het token voor de Action heeft alleen `project`.
board_gql() {
  if [[ -n "${GH_PROJECT_TOKEN:-}" ]]; then
    GH_TOKEN="$GH_PROJECT_TOKEN" gh api graphql "$@"
  else
    gh api graphql "$@"
  fi
}

run() {
  if [[ -n "${DRY_RUN:-}" ]]; then
    echo "zou doen: $*"
  else
    "$@"
  fi
}

# Alle items in de volgorde van het bord, als [{id, status, repo, number, labels}].
board_items() {
  # shellcheck disable=SC2016  # $project en $endCursor zijn GraphQL-variabelen
  board_gql --paginate -f project="$PROJECT_ID" -f query='
    query($project: ID!, $endCursor: String) {
      node(id: $project) { ... on ProjectV2 {
        items(first: 100, after: $endCursor) {
          pageInfo { hasNextPage endCursor }
          nodes {
            id
            status: fieldValueByName(name: "Status") {
              ... on ProjectV2ItemFieldSingleSelectValue { name }
            }
            content { ... on Issue {
              number
              repository { nameWithOwner }
              labels(first: 30) { nodes { name } }
            } }
          }
        }
      } }
    }' --jq '.data.node.items.nodes[] | {
      id,
      status: .status.name,
      repo: .content.repository.nameWithOwner,
      number: .content.number,
      labels: [.content.labels.nodes[]?.name]
    }' | jq -s .
}

set_in_progress() {
  # shellcheck disable=SC2016
  board_gql -f project="$PROJECT_ID" -f item="$1" -f field="$STATUS_FIELD" \
    -f option="$IN_PROGRESS" -f query='
    mutation($project: ID!, $item: ID!, $field: ID!, $option: String!) {
      updateProjectV2ItemFieldValue(input: {
        projectId: $project, itemId: $item, fieldId: $field,
        value: { singleSelectOptionId: $option }
      }) { clientMutationId }
    }' --silent
}

add_to_board() {
  local issue_id
  issue_id=$(gh api "repos/$REPO/issues/$1" --jq .node_id)
  # shellcheck disable=SC2016
  board_gql -f project="$PROJECT_ID" -f content="$issue_id" -f query='
    mutation($project: ID!, $content: ID!) {
      addProjectV2ItemById(input: { projectId: $project, contentId: $content }) {
        item { id }
      }
    }' --jq .data.addProjectV2ItemById.item.id
}

items=$(board_items)

if [[ -n "${BEZIG_ISSUE:-}" ]]; then
  item=$(jq -r --argjson n "$BEZIG_ISSUE" --arg repo "$REPO" \
    '.[] | select(.repo == $repo and .number == $n) | .id' <<<"$items")
  if [[ -z "$item" ]]; then
    item=$(run add_to_board "$BEZIG_ISSUE")
  fi
  echo "#$BEZIG_ISSUE is bezig: op het bord naar In Progress"
  run set_in_progress "$item"
  if [[ -z "${DRY_RUN:-}" ]]; then items=$(board_items); fi
fi

# Het bord kent de staat van een issue niet; een gesloten issue kan nog even op
# Todo staan tot de regel "Item closed" van het bord het op Done zet.
open_issues=$(gh api --paginate "repos/$REPO/issues?state=open&per_page=100" \
  --jq '[.[] | select(.pull_request | not) | .number]' | jq -s 'add // []')

# Dezelfde wachtrij als in CLAUDE.md: bovenste Todo-issue zonder wacht, idee of pauze.
next=$(jq -r --argjson open "$open_issues" --arg repo "$REPO" '
  [.[]
   | select(.repo == $repo and .status == "Todo")
   | select(.number as $n | $open | index($n))
   | select(.labels | any(. == "wacht" or . == "idee" or . == "pauze") | not)
  ][0].number // empty' <<<"$items")

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
