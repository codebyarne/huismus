# CLAUDE.md — Huismus

Self-hosted invoicing for Dutch freelancers using the KOR, or charging VAT (SPEC.md M18). Full details in `SPEC.md`; read it before starting any milestone. If code and spec disagree, stop and ask.

## Project in one paragraph

Django + SQLite + HTMX app that runs in one Docker container on a Raspberry Pi. It creates quotes, invoices and credit notes as PDFs, tracks expenses, and, most importantly, imports a user's complete Moneybird export 1-to-1. AGPL-3.0-or-later. UI is Dutch first (gettext), English second.

## Commands

```
uv sync                                      # install
SECRET_KEY=dev DEBUG=true uv run python manage.py runserver
uv run python manage.py createsuperuser      # first-run login account
uv run playwright install chromium           # once: browser for tests/e2e
uv run pytest                                # tests (incl. browser tests in Chromium)
uv run pytest -n auto                        # same, on every core (what the gate does)
uv run pytest tests/e2e --browser webkit --browser firefox  # Safari/Firefox engines (CI: all three on main when templates, CSS, JS or translations change)
uv run ruff check . && uv run ruff format --check .
SECRET_KEY=dev DEBUG=true uv run python manage.py makemigrations --check
uv run python manage.py makemessages -l nl -l en --no-location  # after adding UI strings
uv run python manage.py compilemessages --ignore=.venv           # to see translations locally
uv run python manage.py demo_data --yes --history  # lege database: 9 jaar nepdata (~80 facturen), voor handmatig kijken
./scripts/site-beelden.sh                    # schermafbeeldingen voor de site opnieuw maken (docs/site/)
./scripts/promo-film.sh                      # promofilmpje (factuur maken, 16 s mp4) naar ~/Downloads
./scripts/demo-server.sh                     # app met 9 jaar nepdata in een tijdelijke map, los van data/ (:8790, demo / demo-wachtwoord-123)
./scripts/verify.sh                          # de poort: draait alle checks hierboven
docker build -t huismus .                    # native arch only locally; CI/release builds arm64 + amd64
```

`DEBUG=true` is only needed for local development outside of `pytest`
(which uses `huismus.config.settings_test`). Without a `SECRET_KEY` in the
environment, Huismus creates one on first start in `data/secret-key`
(owner-only, left out of backups; `huismus/config/secret_key.py`, SPEC.md M11); one
from the environment wins, as on the Pi. `SECRET_KEY=dev` in the commands
above is therefore optional.

## How to work

- Work **one milestone at a time** in the order of `SPEC.md` section 6. Each milestone must work end to end (model, UI, tests) before the next one starts.
- Before coding a milestone, write a short plan and list open questions. Do not silently resolve open questions from `SPEC.md` section 13.
- For invoicing logic (totals, numbering, immutability, credit notes) **write the tests first**.
- Keep changes small and reviewable. One concern per commit. Conventional commit messages.

## Hard rules (invariants)

1. **Money is integer cents.** No `float`, no `Decimal` in storage. VAT rates are basis points. Quantities may be `Decimal`.
2. **Issued documents are immutable.** Never write code that edits or deletes an issued document or its lines. Corrections = credit note. This is enforced in the model layer and by SQLite triggers; do not weaken either. The one exception is the user's explicit "Toch bewerken" (`huismus/documents/reopening.py`, SPEC.md invariant 1): back to draft with the same number. Do not add other paths.
3. **Numbers are gap-free** and allocated only inside the transaction that issues the document.
4. **One totals function** for everything (UI, PDF, import validation). Do not recompute totals elsewhere.
5. **Snapshots.** Issued documents store business, contact and KOR text snapshots. Never render an issued document from live settings or contact data. Eén uitzondering (SPEC.md invariant 4): een document zonder logo in de snapshot krijgt het huidige logo.
6. **Import must be idempotent, dry-run by default, and verify every total to the cent.** Never guess column meanings: detect by headers, warn on unknown ones, fail clearly on missing required ones.
7. **Expenses are gross amounts** (no input VAT deduction under the KOR).

## Conventions

- Python 3.12+, type hints, `ruff` for lint and format.
- All user-facing strings use gettext (`gettext_lazy` in models/forms, `{% translate %}` in templates). Dutch is the source language for review; provide English too.
- No SPA, no JS framework, no JS build step. Server-rendered templates + HTMX; plain CSS
  (`huismus/core/static/core/huismus.css`, components in `docs/design/componenten.html`). Vanilla ES modules
  are allowed for progressive enhancement only: every form still works as a plain POST
  without JS, and JS never computes money or totals (rule 4).
- Add a dependency only with a stated reason; prefer the standard library and Django built-ins.
- Every schema change gets a migration; never edit an applied migration.
- Domain terms stay Dutch in the UI (factuur, offerte, creditnota, klant), English in code (`Invoice`, `Quote`, `CreditNote`, `Contact`).
- Every text a user reads (UI, messages, errors, help pages, docs) follows `docs/schrijfwijzer.md`: je/jij, short, concrete, in the voice described there; `tests/core/test_schrijfwijzer.py` checks the measurable part.

## Privacy and safety

- **Never** put real customer data, real invoices, IBANs, or Moneybird exports in the repo, tests, fixtures, logs or issues. Fixtures and demo data are fictional or fully anonymised.
- Never ask for or store API tokens or passwords in chat or in files. Secrets come from environment variables.
- `.env`, `data/`, `data-import/`, `*.sqlite3` and real exports are gitignored, and `scripts/verify.sh` fails if any of them end up tracked. If you see them staged, stop.
- Do not write legal or tax claims into UI text or code comments. Legal invoice requirements live in `docs/invoice-requirements.md` with source links; UI text for the KOR notice is a user-configurable setting.

## Testing expectations

- `hypothesis` tests for totals and rounding (half-up, per document and rate group).
- Concurrency test for number allocation (no gaps, no duplicates).
- Immutability tests at both model and trigger level.
- Import tests use fixtures in `tests/fixtures/moneybird/`, including dry-run and re-import (zero changes) cases.
- PDF smoke test: renders, contains number and total.
- Browser tests (`tests/e2e`, pytest-playwright) for what server-side tests can't see: HTMX, JS, language switching. Add one for every new interactive path.
- UI-bugs zitten vaak pas op een echte administratie. `tests/e2e/test_walkthrough.py` loopt de hele app door op `huismus/core/demo_history.py` (9 jaar nepdata) in drie schermbreedtes; gebruik de `history` fixture voor alles met lijsten, filters of doorklikken.
- `tests/e2e/test_every_page.py` bezoekt elke pagina in beide talen en drie breedtes en vangt hele soorten UI-bugs (templatesyntax, onvertaalde tekst, opzij scrollen, dubbele menu-items). Nieuwe pagina → toevoegen aan `_pages()`.
- Een bug die iemand met de hand vond: test die faalt, fix, en een check die de hele *soort* vangt. Bijhouden in `BUGS-BY-HAND.md`.
- Een test die één keer faalt, bij herhaling groen is en niet binnen een uur na te doen valt, krijgt géén issue (besluit eigenaar 2026-11-05). Noem hem in je melding en ga door. Pas oppakken als hij terugkomt (een falende browsertest toont dan "Wat de pagina deed", `tests/e2e/page_log.js`) of als een gebruiker het merkt. Een fout die je wél kunt nadoen, los je gewoon op.
- A milestone is not done until tests pass in CI and the Docker image builds for both architectures.

## Definition of done (per milestone)

Works in the running container, has tests, has Dutch and English strings, is documented in the README or `docs/`, and leaves `SPEC.md` accurate. If the spec needs to change, propose the change and update it in the same PR.

## Releases

Een merge naar `main` rolt niets uit. Gebruikers krijgen een nieuwe versie pas bij
een release: een tag `vX.Y.Z` bouwt in `.github/workflows/release.yml` de
desktop-apps (die werken zichzelf bij) en het Docker-image
`ghcr.io/codebyarne/huismus` (Docker-gebruikers werken zelf bij, en Huismus zegt het
als er een nieuwe versie is). Hoe: `docs/desktop.md`, "Een release maken".

De Raspberry Pi van de eigenaar is een gewone Docker-installatie (besluit
2026-11-04): Compose met `:latest`, en de eigenaar werkt met de hand bij volgens
`docs/hulp/docker.nl.md`. Huismus zelf is nooit vanaf internet bereikbaar.
Adres van de Pi: `huismus-intern/werkwijze.md`.

Releases gaan **één keer per week, op woensdag** (besluit 2026-11-04): Claude
maakt dan zelf een release van wat er die week op `main` kwam (het laatste cijfer
omhoog, 0.1.x) en meldt welke versie klaarstaat en wat erin zit, in gewone taal.
Eerst: `verify-e2e` op die `main`, en de WebKit- en Firefox-jobs op `main` groen.
De release-PR (versie in `pyproject.toml`) zet bovenaan `docs/hulp/nieuw.nl.md` en
`nieuw.en.md` wat de gebruiker er nu mee kan, volgens `docs/schrijfwijzer.md`:
wat je ziet of doet, niet hoe het gebouwd is; interne wijzigingen (tests, CI) laat
je weg. Die pagina staat onder Hulp in elke installatie.
Kwam er die week alleen documentatie bij, dan is er geen release.

Tussendoor alleen een release voor een bug die facturen, nummers of gegevens
raakt, of die de app onbruikbaar maakt; meld waarom die niet tot woensdag kon
wachten.

Omdat werk tot een week op `main` ligt voordat iemand het krijgt, moet `main`
altijd uit te brengen zijn: merge alleen wat af is. Een groot stuk knip je in
delen die elk los werken; een scherm dat nog niet af is, krijgt pas een link in
het menu als het af is. Geen feature flags: één gebruiker per installatie, en
elke schakelaar verdubbelt wat er getest moet worden.

Werk als agent altijd op een eigen branch en lever via een pull request. Push nooit
rechtstreeks naar `main` (`.claude/settings.json` weigert het ook).

### Parallelle sessies

Er draaien vaak meerdere sessies tegelijk. Zonder afspraken botsen die: half-af
werk van de een maakt de poort van de ander rood, en mijlpaal- of migratienummers
worden twee keer uitgedeeld.

- **Elke sessie werkt in een eigen worktree** (`.claude/worktrees/`, eigen branch
  vanaf de nieuwste `origin/main`). Nooit in de hoofdmap van de repo werken als een
  andere sessie daar bezig is, en nooit op de lokale `main` committen.
- **Eén onderwerp per sessie.** Merk je dat een andere sessie hetzelfde onderwerp of
  hetzelfde scherm (template, view) aanpakt, stop dan en stem af: stuur die sessie
  een bericht of vraag het de eigenaar. Twee sessies op hetzelfde scherm werken na elkaar,
  niet tegelijk.
- **Gedeelde nummers pas vlak voor gebruik.** Een mijlpaalnummer in `SPEC.md` of een
  migratienummer kies je pas na `git fetch origin` en met de nieuwste `origin/main`
  erbij. Rebase vlak voor de PR nog een keer; botst een migratienummer, hernummer dan
  die van jou (nog niet uitgerold), nooit een die al op `main` staat.
- **Klein en snel terug naar `main`.** Een PR die groen is wordt dezelfde dag
  gemerged (zie Mergen hieronder; een grote wijziging met UI wacht op de eigenaar), zodat de volgende sessie vanaf de nieuwste stand
  begint. Werk dat dagen naast `main` blijft liggen, wordt later een grote rebase.
- **Vertaalbestanden** (`locale/*/django.po`) botsen bijna altijd bij een rebase.
  Neem dan de versie van `main`, draai `makemessages` opnieuw en vul je eigen
  vertalingen weer in; voeg niet beide kanten blind samen.

### Mergen

Claude mergt een eigen PR zelf naar `main`, zonder te vragen, zodra:
CI op de laatste commit groen is (op een PR draait alleen `verify (chromium)`;
WebKit en Firefox draaien na de merge op `main`, als de wijziging templates,
CSS, JS, vertalingen of de browsertests raakt; maak geen release van een
`main` die daar rood staat), er geen
merge-conflict is, en er geen open review-opmerking of vraag van de eigenaar ligt.
Merge-methode: rebase (`main` heeft een rechte historie, geen
merge-commits). Een merge rolt niets uit; dat doet pas een release (zie
Releases).

Claude mergt alleen eigen PR's. Een PR van iemand anders mergt alleen de
eigenaar, ook als hij groen is.

Eerst vragen blijft nodig bij: een migratie die bestaande gegevens wijzigt
of verwijdert, wijzigingen in `scripts/verify.sh`, een grote wijziging met UI
(zie "Flow voorleggen" hieronder), en als de eigenaar bij de PR zegt zelf te
willen kijken.

### Flow voorleggen

Een grote wijziging met UI gaat pas naar `main` als de eigenaar de flow heeft
gezien en goedgekeurd (besluit eigenaar 2026-11-05). De `product-owner`-agent keurt
het design vooraf; de eigenaar keurt wat er echt gebouwd is.

- **Groot** is: een nieuw scherm, of een taak waarvan de stappen veranderen (een
  stap erbij, eraf of in een andere volgorde, een nieuwe weg naar iets). Niet: een
  tekst, een kleur of uitlijning, of een bugfix die het oude gedrag terugbrengt.
  Twijfel je, leg het dan voor.
- **Hoe:** de screenshots van `verify-e2e`, op volgorde van de stappen, elk met één
  zin wat de gebruiker daar doet en ziet, op telefoon en desktop. Stuur ze met
  SendUserFile en vraag in producttaal of het zo live mag, met je advies. Geen
  code, geen PR-link als enige uitleg.
- **Intussen:** de PR blijft open en wordt niet gemerged, ook als hij groen is. Geef
  het issue het label `wacht` (zie "Backlog") en ga door met werk dat er niet van
  afhangt (`/mijlpaal`, stap 10).
- **Daarna:** goedgekeurd → mergen zoals hierboven. Wil de eigenaar iets anders:
  aanpassen, `verify-e2e` opnieuw, en opnieuw voorleggen.

## Klaar is groen

`./scripts/verify.sh` is de poort van dit project. Eén commando dat ja of nee
zegt. Een wijziging is pas klaar als dat script groen afsluit — niet als het er
goed uitziet, en niet omdat de regels hierboven het voorschrijven.

De poort wordt afgedwongen door `.claude/hooks/verify-gate.sh`: die draait
automatisch aan het eind van elke beurt. Rood betekent dat de beurt niet
afgesloten kan worden en Claude de fouten terugkrijgt. Na vijf pogingen
moet Claude melden dat de poort rood staat, niet dat het klaar is. Hij slaat
de poort over als er niets te keuren is (schone werkboom en HEAD al op
GitHub) of als precies deze stand de vorige keer al groen was.

In een Claude Code-cloudsessie zet `.claude/hooks/session-start.sh` de container
klaar: gettext, `uv sync` en de meegeleverde Chromium voor de browsertests
(`HUISMUS_CHROMIUM_EXECUTABLE`, zie `tests/e2e/conftest.py`).

Sinds M0 bewaakt de poort: dat er geen echte administratie in git belandt,
ruff (lint + format), pytest, en `makemigrations --check`. De regel blijft: als
een invariant belangrijk genoeg is om in dit document te staan, hoort hij op
termijn in de poort.

## Backlog: GitHub Issues

De backlog staat openbaar in de issues van `codebyarne/huismus`; de volgorde staat
op het bord "Huismus" (besluiten eigenaar 2026-11-06; daarvoor
`huismus-intern/backlog.md`, dat nu alleen nog verwijst).
Iedereen kan meelezen en met een GitHub-account een issue of reactie plaatsen.

- **Bord = wachtrij.** Het GitHub Project "Huismus" (`gh project … 1 --owner
  codebyarne`) bepaalt de volgorde: de eigenaar sleept wat eerst moet naar boven.
  De wachtrij voor `/mijlpaal` is het bovenste item op het bord met Status `Todo`
  dat een issue is zonder het label `wacht`, `idee` of `pauze`. Zo vraag je het op
  (de lijst komt in de volgorde van het bord):

  ```
  gh project item-list 1 --owner codebyarne --limit 500 --format json --jq '[.items[] | select(.content.type == "Issue" and .status == "Todo" and ((.labels // []) | any(. == "wacht" or . == "idee" or . == "pauze") | not))][0] | "#\(.content.number) \(.title)"'
  ```

  Een open issue dat niet op het bord staat, zit niet in de wachtrij. Het label
  `voorrang` is vervallen: naar boven slepen doet dat werk.
- **Status op het bord:** begin je aan een issue, zet het dan op `In Progress`.
  `Done` volgt vanzelf als het issue sluit; zo niet, zet het zelf. Het item-id
  (`PVTI_…`) staat in `.id` van `gh project item-list`:

  ```
  gh project item-edit --project-id PVT_kwHOELVXCM4BqhnM --id <item-id> --field-id PVTSSF_lAHOELVXCM4BqhnMzho4YqM --single-select-option-id 47fc9ee4  # Done: 98236657
  ```
- **Nieuw issue:** zet het meteen op het bord met
  `gh project item-add 1 --owner codebyarne --url <issue-url>`. Het komt onderaan;
  de eigenaar schuift het omhoog als het eerder moet.
- **`wacht`:** het onderwerp wacht op iets buiten de code (een beslissing, een
  apparaat, een externe dienst). Zeg in het issue waarop, in een regel "**Wacht
  op:** …". Weg met het label zodra het niet meer wacht.
- **`idee`:** binnengekomen via het formulier "Idee of iets wat je mist". Het gaat
  pas in de wachtrij als de `product-owner`-agent het aanneemt, het label
  weghaalt en het op het bord zet.
- **Stoppen:** een open issue met het label `pauze` (titel "PAUZE") stopt de keten
  van `/mijlpaal`. Sluiten zet hem weer aan.
- **Afronden:** de PR die het live zet, zegt `Closes #<nummer>`.
- **Schrijven:** een issue is openbaar, dus volgens "Wat er niet in deze repo
  hoort" hieronder: geen namen, geen echte gegevens, geen adressen van apparaten,
  geen verwijzing naar de inhoud van `huismus-intern`. Het waarom van een besluit
  blijft in `huismus-intern/besluiten.md`; het issue zegt wat er gebouwd wordt.

## Privé: huismus-intern

De repo is openbaar. Wat privé is, staat in de privé-repo
`codebyarne/huismus-intern`: `besluiten.md` (productbesluiten), `STATUS.md` (logboek per mijlpaal) en
`cloud-registratie.md` en `werkwijze.md` (de Pi en de eigenaar). Code en docs verwijzen ernaar als
`huismus-intern/<bestand>`.

- **Waar:** in een cloudsessie koppel je hem met `add_repo`
  (`codebyarne/huismus-intern`, toegang `push`); hij staat dan in
  `/home/user/huismus-intern`. Lokaal staat hij naast de hoofdmap van deze repo
  (`../huismus-intern`, vanuit een worktree drie mappen hoger).
- **Schrijven:** `git -C <map> pull --rebase` vlak voor je schrijft, één besluit of
  regel per commit, en direct naar zijn `main` pushen met `git -C <map> push`.
  Dat mag: hij heeft geen CI en geen release. Geen PR nodig.
- **Wat er niet in deze repo hoort:** namen van mensen (testers, klanten, de
  eigenaar), persoonlijke notities, adressen van apparaten. Twijfel je, zet het in
  `huismus-intern`.

## Reviewers

Vijf subagents in `.claude/agents/`, elk met precies één opdracht:

- `review-invarianten` — toetst een wijziging aan de zeven harde regels
  hierboven. Gebruik deze bij alles wat domeinlogica raakt.
- `review-uitlegbaarheid` — kijkt of de code uit te leggen valt aan een
  ervaren developer. Stijl laat hij met rust, daar is ruff voor.
- `review-spec` — kijkt of een wijziging doet wat `SPEC.md` en het plan
  vragen: niets ontbrekend, niets extra.
- `verify-e2e` — gebruikt de app via Playwright zoals een gebruiker, op
  `scripts/demo-server.sh`, en levert screenshots. Groene tests zijn niet
  genoeg voor iets wat een gebruiker ziet: draai deze voordat je "klaar" zegt.
- `product-owner` — neemt productbeslissingen en keurt designs namens de eigenaar,
  binnen `SPEC.md` en eerdere besluiten, en legt elk besluit vast in
  `huismus-intern/besluiten.md`. Zie "Autonoom werken".

## Autonoom werken

De eigenaar is product owner en leest geen code. Een mijlpaal of feature bouw
je met `/mijlpaal <onderwerp>` (`.claude/skills/mijlpaal/`) van plan tot release,
zonder tussendoor te vragen. Een productvraag of een design gaat naar de
`product-owner`-agent; die beslist of keurt, en schrijft het in
`huismus-intern/besluiten.md`, waar de eigenaar het achteraf kan terugdraaien.

**Eén onderwerp per sessie, daarna een verse sessie.** Een volle context maakt
een sessie traag. Na het melden start `/mijlpaal` zelf een nieuwe cloudsessie
voor het volgende issue uit de wachtrij (zie "Backlog"; stap 10 van de skill).
Een open issue met het label `pauze` of een lege wachtrij stopt de keten.

**Escalatielijst.** Alleen dit vraag je aan de eigenaar zelf, in producttaal en met
een advies:

1. tekst over wet of belasting (in de UI, de PDF of de docs);
2. alles wat geld kost: betaalde diensten, abonnementen, certificaten;
3. een migratie die bestaande gegevens wijzigt of verwijdert;
4. wijzigingen in `scripts/verify.sh`;
5. de repo of een release openbaar maken;
6. iets wat een van de zeven harde regels raakt of afzwakt;
7. Huismus of de laptop bereikbaar maken vanaf internet (een tunnel, een
   open poort);
8. iets wat `SPEC.md` of een eerder besluit van de eigenaar tegenspreekt;
9. de flow van een grote wijziging met UI, voordat die naar `main` gaat (zie
   "Flow voorleggen").

Ga intussen door met werk dat er niet van afhangt. Na elke mijlpaal krijgt
de eigenaar een melding: welke versie klaarstaat en wat er nieuw is, de besluiten
van de PO-agent, en screenshots.

## Playbook bijhouden

De werkwijze van Huismus is de bron van `codebyarne/agentic-playbook` (generiek,
Engels, voor Cursor en Claude Code). Elke keer dat we hier de workflow bijschaven,
werkt dezelfde sessie ook de playbook bij: het generieke deel, zonder namen van
Huismus, de eigenaar of anderen (de poort daar weigert ze), op een eigen branch met een PR,
met `./scripts/verify.sh` daar groen.

- Workflow is: `CLAUDE.md`, alles in `.claude/` (agents, skills, hooks, settings),
  `scripts/verify.sh` en `.github/workflows/`. Ook een nieuwe afspraak met
  de eigenaar over hoe we werken, of een les uit `BUGS-BY-HAND.md` die een hele soort vangt.
- In een cloudsessie: koppel de playbook met `add_repo` (`codebyarne/agentic-playbook`).
- Zet in een commit van de Huismus-PR de regel `Playbook: <url van de PR of commit>`,
  of `Playbook: n.v.t. — <waarom>` als het alleen voor Huismus geldt.
  `.claude/hooks/playbook-sync.sh` herinnert eraan aan het eind van de beurt.
