# Design van Huismus

**De bron is `huismus/core/static/core/huismus.css`** (tokens en componenten) met
`huismus/templates/icons.svg` (iconen). Daaruit volgt de rest:

1. **`componenten.html`** in deze map: elke kleur, knop, melding, statuslabel en
   elk icoon, met de echte CSS en iconen van de app (geen kopie). Met een
   themaknop voor licht en donker. Niet naast elkaar: de app lost `light-dark()`
   in de tokens op `:root` op, dus een donker blok binnen een lichte pagina
   blijft licht zonder een kopie van de CSS. `tests/core/test_design_system.py` houdt hem
   gelijk met de CSS: een klasse die niet meer bestaat, of een nieuwe knop-,
   label-, meldingsvariant, kleur of icoon die op de pagina ontbreekt, maakt de
   poort rood.
2. **Het Design System in Claude**:
   privé; de link staat in `huismus-intern/werkwijze.md`. Een kopie van 1, gemaakt met
   `scripts/design_system_export.py`, om in Claude nieuwe designs mee te maken.
   Het noemt zelf uit welke commit het gebouwd is (README daar, en
   `lastChange`). Laatst bijgewerkt: 2026-11-21, uit commit `88c96105` (de componenten van
   Helder op `main`, iconen in de voorbeelden, het menu Licht/Donker werkt).
   De voorbeelden zetten `color-scheme` zelf, omdat Claude Design dat anders doet
   naar zijn eigen thema (`THEME_STYLE` in het script).

Bekijken: start vanuit de root van de repo `python3 -m http.server 8000` en open
http://localhost:8000/docs/design/componenten.html (de pagina laadt
`../../huismus/core/static/core/huismus.css`, dus niet als los bestand openen).

Archief: de oplevering uit Claude Design van september 2026 staat in
`archief/2026-09-claude-design/`. `ronde-3/` bevat de gekeurde designs van
ronde 3 (met een eigen schets-CSS, `hm.css`). Beide zijn naslag, geen bron.

Het logo "Tegel" staat in `icons/`: `tegel.svg` (licht), `tegel-donker.svg`, `tegel-klein.svg`
(vereenvoudigd, voor een tabblad) en `mus.svg` (de losse mus van een lege toestand). In de app
komt het uit `icons.svg#mus`; `scripts/make_app_icons.py` maakt er de app-iconen van. De letters
(Inter en Bricolage Grotesque, SIL OFL 1.1) staan in `huismus/core/static/core/fonts/`.

Ronde 7 is het concept voor de site in de nieuwe huisstijl: `ronde-7/site-prompt.md`
(de prompt voor Claude Design) en `ronde-7/fotos.md` (de foto's van mensen).
Ronde 8 is datzelfde concept in "Helder", zoals het gebouwd is: `ronde-8/README.md`.
`icons/logo.svg` en `logo-donker.svg` zijn het logo met het woord "Huismus" als één
tekening (`scripts/make_wordmark.py`).

## Een nieuw design maken

- Een HTML-bestand in een map per ronde (`docs/design/ronde-4/` enz.) dat de
  echte CSS laadt (`<link rel="stylesheet" href="../../../core/static/core/huismus.css">`)
  en de klassen van `componenten.html` gebruikt. Of in Claude, met het Design
  System hierboven.
- Fictieve data, Nederlandse teksten, screenshots op 390 en 1440 px, licht en
  donker. De `product-owner`-agent keurt het (zie `/mijlpaal`, stap 3).

## Als je `huismus.css` of `icons.svg` wijzigt

1. Zet de nieuwe of gewijzigde component op `componenten.html` (de test zegt wat
   ontbreekt).
2. Werk het Design System in Claude bij:
   `uv run python scripts/design_system_export.py <map> <commit>` en publiceer de
   gewijzigde bestanden onder `project/` naar de link hierboven (met de Artifact-tool
   van Claude Code: `url` de link, `root` de map, `file_path` het volledige pad van een
   van de bestanden). `project/design-system.json` maakt het script niet: lees hem uit het
   Design System, pas alleen `lastChange` aan en stuur hem mee in de laatste publicatie.
   Kijk daarna in de browser bij Components, in Licht en in Donker. Nieuwe iconen eerst als asset
   uploaden (`upload/Icons/<naam>.svg`) en in de index (`project/design-system.json`)
   opnemen. Pas de datum hierboven aan.
3. Lukt stap 2 niet in je sessie, zeg dat dan in de melding aan de eigenaar.

## Domeinregels in de UI

1. **Kleur alleen waar je iets moet doen; de rest is rustig** (besluiten
   2026-10-30 en 2026-11-15). Een gekleurd vlak alleen voor wat aandacht vraagt
   (te laat, over de KOR-grens). Afgerond is rustig: alleen een vinkje of slotje
   in gedempte tekst. Onbetaald en verstuurd zijn gewone tekst, een concept een
   gestippeld randje.
2. **Uitgegeven is definitief**: `.paper-final`, `.paper-stamp`, en in lijsten
   "Definitief" met een slotje in gedempte tekst (`.pill-final`, geen vlak).
   Geen invoervelden; corrigeren alleen via een creditnota.
3. **Uitgeven is onomkeerbaar**: een bevestigingsdialoog met het nummer dat
   wordt toegekend.
4. **Concepten hebben geen nummer**: `<span class="draft-no">Concept</span>`
   of "bij uitgeven".
5. **Betaalstatus wordt afgeleid**: `.pill-unpaid` (wit met een randje, open
   stip), `.pill-partial` (hetzelfde randje, half gevulde stip), `.pill-paid` (petrol vlak met een
   vinkje), `.pill-credited`; voorbij de vervaldatum `.pill-overdue` ("Te laat",
   warm rood vlak). Offertes: `.pill-quote-sent` (wit met een randje),
   `.pill-quote-accepted` (petrol), `.pill-quote-declined` (rood),
   `.pill-quote-expired` (grijs).
6. **Een geïmporteerd document** krijgt `.pill-import` en de originele pdf is
   primair.
7. **De import is standaard een proefdraai.** Het rapport stelt gerust of wijst
   precies aan wat afwijkt.
8. **Meldingen** (`.hint-banner`) zijn smalle regels in één neutrale tint; alleen
   het icoon zegt de soort: een gevuld rondje met een uitroepteken (`.is-bad`), een
   driehoek (`.is-warn`), petrol (`.is-info`) voor nieuws, grijs voor de rest. De
   link aan het eind is petrol. Geen geel in de app.
9. **KOR**: de hint `.kor-note` in de editor; de tekst zelf, die de gebruiker
   in Instellingen zet, onder elke factuur.
10. **Totalen komen van de server**, elk formulier werkt zonder JavaScript.
