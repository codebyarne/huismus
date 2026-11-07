---
name: mijlpaal
description: Bouwt één mijlpaal of feature van Huismus van begin tot release, zonder de eigenaar tussendoor te vragen, behalve voor de escalatielijst in CLAUDE.md. Gebruik als de eigenaar zegt "bouw <feature>" of /mijlpaal <onderwerp>.
---

# /mijlpaal <onderwerp>

Eén onderwerp, van plan tot release. Je werkt door tot het af is of tot
iets op de **escalatielijst** (`CLAUDE.md`, "Autonoom werken") staat. Een
productvraag of een design gaat naar de `product-owner`-agent, niet naar de eigenaar.

## 1. Begin

- Eigen worktree en branch vanaf de nieuwste `origin/main` (`CLAUDE.md`,
  "Parallelle sessies"). Kijk met `git worktree list` en de open PR's of een
  andere sessie hetzelfde scherm aanpakt; zo ja: stop en stem af.
- Koppel de privé-repo `huismus-intern` (`CLAUDE.md`, "Privé: huismus-intern")
  en pull hem.
- Lees `SPEC.md`, `huismus-intern/besluiten.md` en het plan in de opdracht.
- Geen onderwerp meegekregen? Neem het bovenste issue uit de wachtrij op het
  bord (`CLAUDE.md`, "Backlog: GitHub Issues"). Is er geen: meld dat en stop.
- Lees het issue en zijn reacties: dat is de opdracht, naast `SPEC.md`. Zet het
  op het bord op `In Progress`.

## 2. Plan en spec

- Schrijf een kort plan: wat de gebruiker merkt, welke schermen, welke
  modellen, welke tests. Lijst open vragen.
- Loopt er iets zonder klik van de gebruiker (achtergrond, bij het openen),
  zet dan in het plan de tijdlijn van wat de gebruiker ziet: elke stand, ook
  "bezig" en "mislukt", met de tekst op het scherm. Die tijdlijn gaat mee naar
  `product-owner`.
- Zet in het plan per platform wat de gebruiker krijgt: **Docker** (in de
  browser, ook op een telefoon), de **Mac-app** en de **Windows-app**
  (`CLAUDE.md`, "Elk platform"). Werkt het overal hetzelfde, dan zeg je dat in
  één regel. Verschilt het (een map kiezen, een ander programma openen, iets op
  de achtergrond, bestanden en rechten), dan beschrijf je per platform wat er
  gebeurt. Een platform overslaan kan alleen met een besluit van
  `product-owner`, met de reden in het plan.
- Elke open vraag naar `product-owner`. `ESCALEREN` → vraag de eigenaar (zie 9) en
  bouw intussen alleen wat er niet van afhangt.
- Werk `SPEC.md` bij (mijlpaalnummer pas nu kiezen, na `git fetch`). Dit gaat
  mee in dezelfde PR als de code.

## 3. Design (alleen als een gebruiker iets nieuws ziet)

- Maak het design als HTML die de echte `huismus/core/static/core/huismus.css` laadt
  (geen eigen kopie van de CSS), met de componenten van
  `docs/design/componenten.html` en het Design System in Claude
  (`docs/design/README.md`), fictieve data, nl. Zet het in een map voor de
  ronde onder `docs/design/`. Screenshots op 390 px en 1440 px, licht en donker.
- Laat `product-owner` keuren. Afgekeurd → aanpassen en opnieuw, tot
  goedgekeurd. Hij legt het vast in `huismus-intern/besluiten.md`.

## 4. Bouwen

- Domeinlogica (geld, nummering, onveranderlijkheid, creditnota's, import):
  **tests eerst** (`CLAUDE.md`).
- Kleine commits, één onderwerp per commit, conventionele berichten.
- Wijzig je `huismus.css`: werk `docs/design/componenten.html` bij (de test
  bewaakt het) en daarna het Design System in Claude, zoals
  `docs/design/README.md` beschrijft. Lukt dat laatste niet, zeg het in de
  melding aan de eigenaar.
- Elke tekst die een gebruiker leest, schrijf je volgens
  `docs/schrijfwijzer.md`.
- Nieuwe teksten in nl en en (`makemessages`, vertalingen invullen,
  `compilemessages`). Nieuwe pagina → in `_pages()` van
  `tests/e2e/test_every_page.py`. Nieuw interactief pad → een browsertest.

## 5. Controleren

Alles moet slagen voordat je verder gaat:

1. `./scripts/verify.sh` groen.
2. `review-invarianten` (als het domeinlogica raakt), `review-uitlegbaarheid`,
   `review-spec`. Elke bevinding oplossen of met reden afwijzen.
3. `verify-e2e` op de demo-server, met de stappen die een gebruiker zet.
   Faalt een stap: oplossen en opnieuw.

## 6. Pull request

- Rebase op de nieuwste `origin/main` (vertaalbestanden: zie `CLAUDE.md`).
  Push de branch, open de PR. Beschrijving in producttaal: wat de gebruiker
  merkt, de PO-besluiten, wat niet getest kon worden.
- Raakt de PR iets van de escalatielijst (zoals een migratie die data
  wijzigt, of `scripts/verify.sh`): niet mergen, de eigenaar vragen (zie 9).
- Een grote wijziging met UI (een nieuw scherm, of andere stappen in een taak):
  leg de flow voor aan de eigenaar volgens `CLAUDE.md`, "Flow voorleggen". De
  screenshots van `verify-e2e` op volgorde, met per stap één zin, telefoon en
  desktop, via SendUserFile; vraag of het zo live mag (zie 9). Niet mergen voor
  hij ja zegt. Intussen: het label `wacht` op het issue, met "**Wacht op:** de
  eigenaar keurt de flow", en stap 10.
- Komt de PR uit een issue: `Closes #<nummer>` in de beschrijving.

## 7. Mergen en release

- CI groen (op een PR alleen `verify (chromium)`), geen conflict, geen open vraag van
  de eigenaar, en bij een grote wijziging met UI de flow goedgekeurd → zelf mergen met rebase (`CLAUDE.md`, "Mergen").
- Een merge rolt niets uit (`CLAUDE.md`, "Releases"). Wacht tot CI op `main` groen is
  (ook WebKit en Firefox, als die draaien), draai `review-veiligheid` over alles
  sinds de vorige release (hoog of middel: eerst oplossen; laag: een issue), en maak
  dan een release volgens
  `docs/desktop.md`, "Een release maken": een PR `chore(release): X.Y.Z` die alleen
  de versie in `pyproject.toml` (en `uv.lock`) een patch ophoogt, mergen als CI groen
  is, en daarna die commit taggen met `vX.Y.Z` en de tag pushen.
- Wacht tot de workflow Release groen is en de release op GitHub staat. Mislukt hij:
  oplossen, niet de tag verplaatsen; een nieuwe patch is goedkoper dan uitleg.
- Alleen documentatie gewijzigd (`.md`, `docs/`): geen release (`CLAUDE.md`,
  "Releases").

## 8. Melden

- Een regel in `huismus-intern/STATUS.md`: een commit in `huismus-intern`,
  gepusht vóór stap 10. Niets daarvan in de PR van Huismus. Het issue sluit
  vanzelf met de merge (`Closes #…`); sluit het anders zelf, met de PR erbij.
- Iets gevonden wat later moet? Een nieuw issue, openbaar geschreven, en op het
  bord (`CLAUDE.md`, "Backlog: GitHub Issues").
- Workflow gewijzigd (`CLAUDE.md`, `.claude/`, `scripts/verify.sh`, CI)?
  Werk ook `codebyarne/agentic-playbook` bij en zet `Playbook: …` in een commit
  (`CLAUDE.md`, "Playbook bijhouden").
- Pushmelding aan de eigenaar: welke versie klaarstaat en wat er nieuw is, in één of
  twee zinnen producttaal, met hoe de Pi bijwerkt (`docker compose pull &&
  docker compose up -d`),
  plus de PO-besluiten van deze mijlpaal. Stuur de belangrijkste screenshots
  mee met SendUserFile.

## 9. Escaleren

Eén vraag tegelijk, in producttaal, met jouw advies als eerste optie
(AskUserQuestion of de vraag in de wrap-up). Nooit "kijk de PR door" of een
git-commando: de eigenaar leest geen code. Ga intussen door met wat er niet van
afhangt.

## 10. Volgende sessie

Een lange sessie wordt traag. Bouw daarom nooit een tweede onderwerp in deze
sessie, maar geef het door aan een nieuwe:

1. Kijk in de wachtrij op het bord (`CLAUDE.md`, "Backlog: GitHub Issues"). Stop zonder
   opvolger als er een open issue met het label `pauze` is, als de wachtrij leeg
   is, of als je onderwerp nog niet op `main` staat (zie de uitzondering
   hieronder).
2. Start één nieuwe cloudsessie met `create_session` (claude-code-remote):
   `source_url` `https://github.com/codebyarne/huismus`, titel
   `Mijlpaal: <onderwerp>`, en als `prompt` alleen `/mijlpaal <onderwerp>`.
   Omgeving, model en rechten erft hij van deze sessie.
3. Zet in je laatste bericht aan de eigenaar welk onderwerp de nieuwe sessie
   oppakt, en stop. Een sessie start hoogstens één opvolger, ook als ze
   later nog een keer wakker wordt.

Zonder `create_session` (een lokale sessie): noem het volgende onderwerp in
je melding en start niets.

Wacht je onderwerp op de eigenaar (stap 9) en hangt het volgende er niet van af, dan
mag je de opvolger al starten: geef je issue eerst het label `wacht`, zodat de
opvolger het overslaat. Na zijn antwoord bouw je je eigen onderwerp af (en haal je
het label weg), maar je start geen tweede opvolger.
