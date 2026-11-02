# Front-end

Hoe de schermen van Huismus in elkaar zitten (M8). De componenten staan op
`docs/design/componenten.html`, die de echte `huismus.css` laadt
(`docs/design/README.md`). Het oorspronkelijke ontwerp van september 2026 staat
als archief in `docs/design/archief/2026-09-claude-design/`; wijzig de app, niet die map.

## Uitgangspunten

- **Server-rendered.** Django-templates maken alle HTML. Er is geen SPA, geen
  framework en geen build-stap.
- **HTMX** voor wat dynamisch is: `hx-boost` op `<body>` voor paginawissels,
  live zoeken, en de live totalen in de editor.
- **Vanilla JavaScript alleen als verbetering** (`huismus/core/static/core/app.js`,
  één ES-module). Elk formulier werkt ook als gewone POST zonder JS, en JS
  rekent nooit met geld (CLAUDE.md, harde regel 4).
- **Eén stylesheet**, `huismus/core/static/core/huismus.css`, met design tokens als
  CSS custom properties bovenaan. Licht en donker via `light-dark()`.
  Aanvullingen die niet uit het ontwerp komen staan onderaan (§18).
- **Iconen** als SVG-sprite in `huismus/templates/icons.svg`, gebruikt als
  `<svg class="i"><use href="#naam"/></svg>`.
- **Geen inline JavaScript.** Elke pagina krijgt een Content-Security-Policy
  (`huismus/core/middleware.py`): scripts alleen uit eigen bestanden, geen
  `<script>`-blokken, geen `onclick=` en geen externe bronnen. Inline
  `style=""` mag wel. De browsertests falen op een overtreding, want die
  verschijnt als fout in de console.

## Bouwstenen

| Wat | Waar | Waarvoor |
|---|---|---|
| App-shell | `huismus/templates/base.html` | Zijbalk, mobiele onder- en bovenbalk, toasts; `data-theme` uit Instellingen → Weergave (`huismus/core/appearance_views.py`). Blocks: `content`, `content_class`, `actionbar`, `main_attrs`. |
| Actieve navigatie | `huismus/core/context_processors.py` | Bepaalt één keer welk menu-item actief is, voor zijbalk en onderbalk. |
| Formuliervelden | `{% field form.x %}` in `huismus/core/templatetags/forms.py` | Label, widget met de juiste klasse, helptekst en fouten (met `aria-invalid`/`aria-describedby`). Opties: `span`, `money`, `suffix`, `optional`, `label`, `help`. |
| Foutsamenvatting | `{% form_errors form formset %}` | "Nog niet opgeslagen", met links naar de velden met een fout. |
| Bedragen | `money`, `whole_euros` (core), `money_for` (documents) | `€ 1.815,00`; `money_for` zet een minteken voor creditnota's. |
| Statuspillen | `pill pill-<status>` | Betaalstatus, offertestatus, "Definitief", "Geïmporteerd". |

## Patronen

**Live zoeken zonder partial-templates.** Een lijst rendert altijd de hele
pagina. Het zoekformulier haalt met `hx-select` alleen het resultaat eruit,
en met `hx-select-oob` de tab-tellers. Zo is er één template per lijst, en
werkt de pagina ook met een gewone GET.

**Live totalen in de editor.** Elke wijziging post het niet-opgeslagen
formulier naar `…/voorbeeld/`. Die view rekent met `documents.editing.
preview_totals()` (via `compute_totals`, de ene totalenfunctie) en
antwoordt met out-of-band swaps: regeltotalen, totalen, adres en de
samenvatting in de uitgeefdialoog. Er wordt niets opgeslagen. De
"Uitgeven"/"Verzenden"-knop in de dialoog verstuurt het editorformulier zelf
(`actie=uitgeven`), zodat eerst wordt opgeslagen en daarna uitgegeven.

**Imports zonder bestanden opnieuw te kiezen.** Een proefdraai bewaart de
uploads in `data/import-staging/<token>/` (`huismus/imports/staging.py`). De stap
daarna stuurt alleen het token. Na doorvoeren wordt de staging verwijderd;
achtergebleven stagings na 24 uur. Backups slaan deze map over.

**Dialogen** zijn native `<dialog>`, geopend met `command="show-modal"`
(met een kleine fallback in `app.js` voor browsers zonder invoker commands).

## Installeren als app (PWA)

Huismus is een *Progressive Web App*: de browser biedt "Zet op beginscherm"
of "App installeren" aan, en daarna opent Huismus in een eigen venster met
eigen icoon. Het is dezelfde site; alles komt nog steeds van de server.

| Wat | Waar |
|---|---|
| Manifest (naam, iconen, `standalone`) | `/manifest.webmanifest`, `huismus/core/pwa.py` |
| Iconen (PNG, ook voor iOS) | `huismus/core/static/core/icons/`, getekend door `scripts/make_app_icons.py` |
| Kleur van de titelbalk | `theme-color` in `huismus/templates/base.html` (= `--surface`) |
| Service worker | `/sw.js`, template `huismus/templates/core/sw.js`, geregistreerd in `app.js` |
| Offline-pagina | `/offline/`, `huismus/templates/core/offline.html` |

De service worker bewaart **één** pagina: de offline-pagina. Lukt het openen
van een pagina niet (geen wifi, VPN uit, server uit), dan toont hij die in
plaats van de foutmelding van de browser. Al het andere gaat ongewijzigd naar
de server: er staan nooit facturen of klantgegevens op het apparaat, en
formulieren, htmx-verzoeken en downloads laat hij met rust.

- `/sw.js` staat in de root en niet onder `/static/`, omdat een service worker
  alleen pagina's onder zijn eigen adres afhandelt.
- Manifest, service worker en offline-pagina vragen geen login: de browser
  haalt het manifest op zonder cookies, en de offline-pagina is er juist
  voor als inloggen niet kan.
- De offline-pagina is één bestand met de stijl inline, omdat hij zonder
  server getoond wordt. Hij wordt bewaard in de taal die actief was toen de
  service worker zich installeerde.
- Wijzig je de offline-pagina, verhoog dan `CACHE` in `sw.js`; een andere
  `sw.js` laat de browser de nieuwe versie ophalen.
- Installeren en de service worker werken alleen via HTTPS (of op
  `localhost`).

## Een scherm toevoegen

1. Zoek de component op `docs/design/componenten.html` (of een voorbeeld in
   `docs/design/archief/2026-09-claude-design/html/`) en neem de markup en
   klassen over. Inline `style` alleen voor eenmalige afstanden.
2. Formulieren: `{% field %}` en `{% form_errors %}`.
3. Nieuwe CSS onderaan `huismus.css` (§18), met een regel uitleg. Een nieuwe
   knop-, label- of meldingsvariant komt ook op `docs/design/componenten.html`;
   `tests/test_design_system.py` faalt anders.
4. Alle tekst via `{% translate %}`; daarna `makemessages` en de Engelse
   vertaling in `huismus/locale/en/`.
5. Geen juridische of fiscale claims in UI-tekst (CLAUDE.md).

## Grote schermen

Het ontwerp is gemaakt voor een laptop (± 1440 px). Vanaf 1600, 1920 en 2400 px
schaalt de hele interface met CSS `zoom` (1,1 / 1,2 / 1,4), zodat tekst, knoppen
en afstanden samen meegroeien. Schermhoogtes (`100vh`) worden door dezelfde
factor gedeeld (`--zoom`); gebruik bij een nieuwe schermhoogte dus
`calc(100vh / var(--zoom, 1))`.

## Lokaal ontwikkelen

`whitenoise.runserver_nostatic` staat aan, zodat CSS en JS onder
`runserver` met `max-age=0` worden geserveerd: na een wijziging zie je
direct de nieuwe versie.
