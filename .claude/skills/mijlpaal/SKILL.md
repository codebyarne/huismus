---
name: mijlpaal
description: Bouwt één mijlpaal of feature van Huismus van begin tot live, zonder de eigenaar tussendoor te vragen, behalve voor de escalatielijst in CLAUDE.md. Gebruik als de eigenaar zegt "bouw <feature>" of /mijlpaal <onderwerp>.
---

# /mijlpaal <onderwerp>

Eén onderwerp, van plan tot live op de Pi. Je werkt door tot het af is of tot
iets op de **escalatielijst** (`CLAUDE.md`, "Autonoom werken") staat. Een
productvraag of een design gaat naar de `product-owner`-agent, niet naar de eigenaar.

## 1. Begin

- Eigen worktree en branch vanaf de nieuwste `origin/main` (`CLAUDE.md`,
  "Parallelle sessies"). Kijk met `git worktree list` en de open PR's of een
  andere sessie hetzelfde scherm aanpakt; zo ja: stop en stem af.
- Koppel de privé-repo `huismus-intern` (`CLAUDE.md`, "Privé: huismus-intern")
  en pull hem.
- Lees `SPEC.md`, `huismus-intern/besluiten.md` en het plan in de opdracht.
- Geen onderwerp meegekregen? Neem het bovenste open onderwerp uit
  `huismus-intern/backlog.md` dat geen `(wacht: …)` heeft. Is er geen: meld dat en stop.

## 2. Plan en spec

- Schrijf een kort plan: wat de gebruiker merkt, welke schermen, welke
  modellen, welke tests. Lijst open vragen.
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
  wijzigt, of `deploy/`): niet mergen, de eigenaar vragen (zie 9).

## 7. Mergen en live

- CI groen (op een PR alleen `verify (chromium)`), geen conflict, geen open vraag van
  de eigenaar → zelf mergen met rebase (`CLAUDE.md`, "Mergen").
- Wacht tot de Pi de nieuwe versie draait: vergelijk
  `docker inspect huismus --format '{{.Config.Image}}'` via
  de Pi (`huismus-intern/werkwijze.md`) met `origin/main`, en lees het deploylog
  (`~/.pm2/logs/huismus-webhook-out.log`) tot "Huismus <sha> draait."
- Alleen documentatie gewijzigd (`.md`, `docs/`): geen CI en geen deploy
  (`CLAUDE.md`, "Mergen"). De Pi draait dan de vorige code-commit; niets te
  controleren.

## 8. Melden

- Een regel in `huismus-intern/STATUS.md` en je onderwerp afgevinkt in
  `huismus-intern/backlog.md` (naar "Klaar"): een commit in `huismus-intern`,
  gepusht vóór stap 10. Niets daarvan in de PR van Huismus.
- Workflow gewijzigd (`CLAUDE.md`, `.claude/`, `scripts/verify.sh`, CI, `deploy/`)?
  Werk ook `codebyarne/agentic-playbook` bij en zet `Playbook: …` in een commit
  (`CLAUDE.md`, "Playbook bijhouden").
- Pushmelding aan de eigenaar: wat er live ging, in één of twee zinnen producttaal,
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

1. `git -C <huismus-intern> pull --rebase` en lees `huismus-intern/backlog.md`. Stop
   zonder opvolger als er `PAUZE` staat, als er geen open onderwerp zonder
   `(wacht: …)` is, of als je onderwerp nog niet op `main` staat (zie de
   uitzondering hieronder).
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
mag je de opvolger al starten: zet eerst `(wacht: eigenaar)` achter je onderwerp
in `huismus-intern/backlog.md` (commit en push in `huismus-intern`), zodat de opvolger
het overslaat. Na zijn antwoord bouw je je eigen onderwerp af (en haal je
die markering weg), maar je start geen tweede opvolger.
