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
   `lastChange`). Laatst bijgewerkt: 2026-10-30, uit commit `e81ea8d`.

Bekijken: start vanuit de root van de repo `python3 -m http.server 8000` en open
http://localhost:8000/docs/design/componenten.html (de pagina laadt
`../../huismus/core/static/core/huismus.css`, dus niet als los bestand openen).

Archief: de oplevering uit Claude Design van september 2026 staat in
`archief/2026-09-claude-design/`. `ronde-3/` bevat de gekeurde designs van
ronde 3 (met een eigen schets-CSS, `hm.css`). Beide zijn naslag, geen bron.

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
   van Claude Code: `url` de link, `root` de map). Nieuwe iconen eerst als asset
   uploaden (`upload/Icons/<naam>.svg`) en in de index (`project/design-system.json`)
   opnemen. Pas de datum hierboven aan.
3. Lukt stap 2 niet in je sessie, zeg dat dan in de melding aan de eigenaar.

## Domeinregels in de UI

1. **Kleur alleen waar je iets moet doen; de rest is rustig** (besluit
   2026-10-30). Een gekleurd vlak alleen voor wat aandacht vraagt (Vervallen,
   Onbetaald, over de KOR-grens). Afgerond is rustig: alleen een stip of slotje
   in gedempte tekst.
2. **Uitgegeven is definitief**: `.paper-final`, `.paper-stamp`, en in lijsten
   "Definitief" met een slotje in gedempte tekst (`.pill-final`, geen vlak).
   Geen invoervelden; corrigeren alleen via een creditnota.
3. **Uitgeven is onomkeerbaar**: een bevestigingsdialoog met het nummer dat
   wordt toegekend.
4. **Concepten hebben geen nummer**: `<span class="draft-no">Concept</span>`
   of "bij uitgeven".
5. **Betaalstatus wordt afgeleid**: `.pill-unpaid` en `.pill-partial` (amber
   vlak), `.pill-paid` (groene stip, geen vlak), `.pill-credited`; voorbij de
   vervaldatum `.pill-overdue` ("Vervallen", rood vlak, het enige wat opvalt).
6. **Een geïmporteerd document** krijgt `.pill-import` en de originele pdf is
   primair.
7. **De import is standaard een proefdraai.** Het rapport stelt gerust of wijst
   precies aan wat afwijkt.
8. **Meldingen op het overzicht** zijn rustige kaarten (`.hint-banner`): kleur
   alleen in de streep, het icoon en de link. Rood (`.is-bad`) boven de
   KOR-grens of als iets mislukt, amber (`.is-warn`) om op te letten, blauw
   (`.is-info`) voor informatie, abrikoos (geen klasse) voor een herinnering.
9. **KOR**: de hint `.kor-note` in de editor; de tekst zelf, die de gebruiker
   in Instellingen zet, onder elke factuur.
10. **Totalen komen van de server**, elk formulier werkt zonder JavaScript.
