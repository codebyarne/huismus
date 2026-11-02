> **Archief.** Dit is de oplevering uit Claude Design van september 2026 (ronde 1
> en 2), bewaard als naslag. Niet meer bijwerken en niet als bron gebruiken. De
> bron is `core/static/core/huismus.css`; de componenten staan op
> `docs/design/componenten.html` en in het Design System in Claude (zie
> `docs/design/README.md`). Teksten, kleuren en statuslabels hieronder kunnen
> verouderd zijn.


# Handoff: Huismus front-end (Django-templates)

## Overzicht
Complete front-end voor Huismus: self-hosted facturatie voor Nederlandse zzp'ers onder de KOR, met import vanuit Moneybird. Eén gebruiker, draait op een Raspberry Pi, op laptop en telefoon. Richting "Zomerochtend": hemelsblauw (#1B6AC9) en abrikoos (#F4A259) op warme neutralen.

## Over deze bestanden
- **`huismus.css`, `factuur-pdf.css` en `icons.svg` zijn productieklaar.** Het is plain CSS met custom properties, zonder build-stap, framework of externe bronnen. Neem ze 1-op-1 over naar `static/`.
- **`html/*.html` zijn statische referentieschermen**: de gewenste markup met fictieve data. Zet ze om naar Django-templates. Gebruik daarbij dezelfde class-namen en structuur, vervang de voorbeelddata door templatevariabelen en voeg `{% csrf_token %}` toe aan elke `<form method="post">`.
- Inline `style="…"` in de schermen is layout-lijm voor het prototype. Verplaats herbruikbare stukken naar `huismus.css`. Eenmalige afstanden mogen blijven staan.
- De schermen bevatten al `hx-*`-attributen waar HTMX thuishoort (live zoeken, regel toevoegen, meer laden). Die zijn indicatief; kies de echte endpoints zelf.

## Fidelity
**High-fidelity.** Kleuren, typografie, spacing, statussen en teksten zijn definitief. De teksten zijn in het Nederlands; Engels komt via `{% trans %}`.

## Harde randvoorwaarden
- Django-templates + HTMX (`hx-boost` voor paginawissels). Vanilla ES-modules alleen voor verbeteringen. JS is nooit de bron van waarheid.
- **Elk formulier werkt zonder JS** als gewone POST.
- **Totalen komen altijd van de server.** De editor rekent niets in JS. Na het wijzigen van een regel ververst HTMX `#totalen` (zet `.htmx-request` of `.is-refreshing` op `.totals`, zie `offerte.html`).
- Geen CDN of webfonts: gebruik de systeemfontstack uit de tokens.
- WCAG AA, zichtbare focus, elk veld met een `<label>`, fouten via `aria-invalid` + `aria-describedby`.

## Schermen (html/)
| Bestand | Route | Belangrijkste punten |
|---|---|---|
| inloggen.html | /login/ | Eén account, geen registreren of wachtwoord vergeten |
| overzicht.html | / | KPI's (openstaand als primaire kaart), hint bij open concept, laatste facturen, offertes die wachten |
| overzicht-eerste-keer.html | / (leeg) | Moneybird-import als primaire actie, onboarding-checklist (voorstel) |
| facturen.html | /facturen/ | Tabs, zoeken, jaarfilter (voorstel); nummer of "Concept"; betaalstatus-pill |
| factuur-concept.html | /facturen/<id>/bewerken/ | Document als vel papier, regels inline, fout per regel, KOR-hint, sticky actiebalk, `<dialog id="uitgeven">` |
| factuur-uitgegeven.html | /facturen/<id>/ | Alleen-lezen `.paper-final` + stempel, snapshot-hint, betaalvoortgang, betalingen, slide-over `<dialog id="betaling" class="sheet">`, creditnota-dialoog, tijdlijn (voorstel) |
| factuur-uitgegeven-import.html | idem | Variant met herkomstlabel en twee PDF's: "Origineel uit Moneybird" (primair) en "Opnieuw gegenereerd" |
| offerte.html | /offertes/<id>/ | Stepper voor de levenscyclus, statusacties per status, "Omzetten naar factuur" met dialoog |
| contacten.html | /contacten/ | Live zoeken (`hx-trigger="input changed delay:300ms"`, ververst alleen `#contacten-tabel`), actief/gearchiveerd |
| contact.html | /contacten/<id>/ | Gegroepeerde velden, contactpersonen herhaalbaar, IBAN-fout, documenten van het contact (voorstel) |
| uitgave.html | /uitgaven/<id>/ | Bruto bedrag + "btw ter info", KOR-uitleg, bonnetjes met dropzone, verwijderen met bevestiging |
| jaaroverzicht.html | /uitgaven/jaaroverzicht/<jaar>/ | Jaarnavigatie, CSV, KPI's, staafgrafiek in CSS (`--v` = percentage van de schaal), tabel per kwartaal, horizontale balken per categorie, disclaimer |
| moneybird-import.html | /importeren/ | Dropzone voor meerdere bestanden, herkende bestandstypes (voorstel), "Echt doorvoeren" standaard uit, stappen voor de export |
| moneybird-proefdraai.html | /importeren/ (POST, proefdraai) | Banner "Proefdraai: er is niets opgeslagen", `<details class="report">` per onderdeel (groen, `is-warn` of `is-bad`), CTA voor echt doorvoeren |
| moneybird-doorgevoerd.html | /importeren/ (POST, echt) | Vieringsmoment met de mus, samenvatting, vervolgstappen |
| instellingen.html | /instellingen/ | Secties met ankernav, KvK-fout, IBAN-check, KOR-toggle + tekst, logo-upload, nummerformaat met "Volgende: …", live voorbeeld (voorstel) |
| factuur-pdf.html + factuur-pdf.css | WeasyPrint | A4, adresblok voor vensterenvelop, tabellen, zwart-wit printbaar, logo van de gebruiker. Vervangen: de pdf volgt sinds 2026-10-30 de opmaak van een Moneybird-factuur (`templates/pdf/invoice.css`, `huismus-intern/besluiten.md`) |
| componenten.html | n.v.t. | Referentie van alle componenten en tokens |
| **Ronde 2** | | |
| offertes.html, offertes-leeg.html | /offertes/ | Tabs (Alle · Concepten · Wachten op antwoord · Geaccepteerd · Afgewezen of verlopen), `.due-hint` bij verzonden offertes die binnen 7 dagen verlopen (amber) of verlopen zijn (`.is-past`, rood), lege toestand |
| factuur-nieuw.html | /facturen/nieuw/ | Lege begintoestand: contactkiezer heeft focus en is open, één lege regel, totaal € 0,00, datum vandaag, "Uitgeven" uit tot er een contact en een regel is |
| factuur-nieuw-geen-contacten.html | idem | Geen contacten: de combobox legt uit wat er moet gebeuren en biedt "Nieuw contact “…”" met `?terug=factuur` |
| contact-nieuw-vanuit-factuur.html | /contacten/nieuw/?terug=factuur | Nieuw contact vanuit de factuur: naam uit de zoekopdracht staat al ingevuld, info-melding en de knop "Opslaan en terug naar factuur" |
| creditnota-concept.html | /facturen/<id>/bewerken/ (soort=creditnota) | `.doc-ref` "Crediteert factuur 2026-0012", klant staat vast, negatieve aantallen, `.credit-room` met "Nog te crediteren" |
| creditnota-concept-fout.html | idem | Maximum overschreden: flash-fout, regels met `aria-invalid`, `.credit-room.is-over`, "Uitgeven" uitgeschakeld (server valideert ook) |
| creditnota-uitgegeven.html | /facturen/<id>/ | Alleen-lezen met stempel en verwijzing, geen betaalblok, blok "Effect op factuur 2026-0012" |
| factuur-gecrediteerd.html | /facturen/<id>/ | Originele factuur met blok "Creditnota's" en nog openstaand bedrag na creditering (factuur − creditnota's − betalingen) |
| creditnota-pdf.html | WeasyPrint | Titel "Creditnota", meta "Crediteert factuur 2026-0012", negatieve bedragen, blok "Verrekening" in plaats van betaalinstructie. Vervangen, zie factuur-pdf.html |
| uitgaven.html, uitgaven-leeg.html | /uitgaven/ | Filters jaar + categorie + zoeken, paperclip bij bonnetje, `.sum-row` met totaal van de getoonde uitgaven, lege toestand |
| categorieen.html | /uitgaven/categorieen/ | Inline bewerken (`tr.is-editing`, HTMX `outerHTML`), nieuwe categorie onderaan, verwijderen alleen zonder uitgaven. Met uitgaven: gedimde prullenbak die een uitlegdialoog opent |
| uitgaven-import-1…4.html | /uitgaven/importeren/ | Wizard met `.steps`: 1 bestand, 2 kolommen koppelen (`.mapping` + `.preview-table`, één categorie), 3 proefdraairapport (nieuw, al aanwezig, fouten per rij), 4 doorgevoerd. Het bestand blijft server-side bewaard tussen de stappen |
| fout-404/403/500/csrf.html | handler404 enz. | Eén sjabloon met de mus. Binnen de app-shell als de gebruiker is ingelogd |
| fout-*-uitgelogd.html | idem | Losse pagina in de stijl van het inlogscherm als de gebruiker niet is ingelogd |

Mobiel (≤ 760 px): de zijbalk wordt `.mtop` (vaste topbalk) + `.tabbar` (onderbalk met FAB "Nieuwe factuur" en een "Meer"-popover). Tabellen met `.stackable` stapelen via een container query. Elke `<td>` krijgt `data-cell="primary|secondary|amount|status|action|hide"`.

## Domeinregels in de UI
1. Uitgegeven is definitief: `.paper-final`, `.paper-stamp`, `.pill-final` met slotje, geen invoervelden. Corrigeren alleen via een creditnota.
2. Uitgeven is onomkeerbaar: bevestigingsdialoog met het nummer dat wordt toegekend.
3. Concepten hebben geen nummer: toon `<span class="draft-no">Concept</span>` of "bij uitgeven".
4. Betaalstatus wordt afgeleid: `.pill-unpaid`, `.pill-partial` of `.pill-paid`. `.pill-overdue` ("Vervallen") is een voorstel.
5. Een geïmporteerd document krijgt `.pill-import` en de originele PDF is primair.
6. De import is standaard een proefdraai. Het rapport stelt gerust of wijst precies aan wat afwijkt.
7. KOR: de hint `.kor-note` in de editor, de tekst zelf onder elke factuur.

## CSS-aanvullingen ronde 2 (`huismus.css` §17)
- `.due-hint` (+ `.is-past`): kleine vervalhint met klokje
- `.doc-ref`: pil die naar een gekoppeld document verwijst
- `.credit-room` (+ `.is-over`): overzicht factuurbedrag, gecrediteerd, betaald en nog open
- `.sum-row`: totaalregel onder een lijst
- `.table tr.is-editing`, `.table .order`: rij die in de tabel wordt bewerkt
- `.combo-list .combo-empty` en `.combo-action`: lege combobox en de actie "Nieuw contact"
- `.error-page`, `.error-code`: foutpagina's
Verder uit de controle van ronde 1: `.num` breekt niet af, velden stapelen in smalle kaarten via een container query op `.card-pad`, en er zijn mobiele regels voor `.actionbar`, `.steps`, `.file-item` en `.paper`.
- `.split-even`: twee even brede kolommen (wizard stap 2)
- `.aside-first` op de zijkolom van een document: op mobiel komt betaalstatus en creditering vóór het vel
- `td[data-cell="order"]`: extra rij in een gestapelde tabel (volgorde bij categorieën)
- Mobiel: secundaire paginaknoppen compact zonder icoon, primaire knop bovenaan over de volle breedte. De regels van een alleen-lezen document staan op één regel ("12 uur × € 95,00 · 0%")
Geen nieuwe kleurtokens. Placeholders krijgen een vaste kleur (#938979), omdat `light-dark()` in pseudo-elementen niet in elke browser werkt.

## Interacties
- Dialogen: native `<dialog>`, geopend met `command="show-modal" commandfor="id"` en gesloten met `command="close"`. Neem een kleine fallback op voor browsers zonder invoker commands (zie onderaan).
- Menu "+ Nieuw": `popover` + `popovertarget`, gepositioneerd met CSS anchor positioning (`anchor-name: --nieuw`).
- Laadtoestand: `.btn` met een `<span class="spinner">` erin. HTMX zet `.htmx-request`, waardoor het label verdwijnt en de spinner verschijnt. Gebruik `.htmx-indicator` voor losse indicatoren.
- View transitions: `@view-transition { navigation: auto; }` staat in de CSS. Zet voor HTMX `htmx.config.globalViewTransitions = true`.
- Toasts: `.toasts` > `.toast.flash-success|info|warning|error` rechtsboven. Succes en info verdwijnen na 5 s, fouten blijven staan. Django-messages kunnen hierop mappen.
- Nog te bouwen als losse ES-modules: sneltoetsen (`n` nieuw, `/` zoeken, `⌘K` palette), combobox voor de contactkiezer (markup in componenten.html), regels verslepen (`.grip`, `.line.is-dragging`), Tab of Enter in de laatste cel voegt een regel toe (`hx-post`), drag-and-drop met preview (`.dropzone.is-over`).
- Respecteer `prefers-reduced-motion` (staat al in de CSS).

## Design tokens
Alles staat bovenin `huismus.css` (§1). Licht en donker in één waarde via `light-dark()`. Forceer een thema met `<html data-theme="dark|light">`.
- Neutraal: `--bg #FBF8F3`, `--surface #FFF`, `--surface-2 #F4EFE7`, `--border #E6DED2`, `--border-strong #CEC3B3`, `--text #2A2520`, `--text-muted #6B6258`
- Primair: `--primary #1B6AC9`, `--primary-hover #1559AB`, `--primary-soft #E3EEFB`, `--primary-ink #14539E`
- Accent: `--accent #F4A259`, `--accent-soft #FDEBD8`, `--accent-ink #86470F`. Alleen voor hints, het importlabel en vieren; nooit voor knoppen.
- Status: ok `#1E7A45`/`#E2F3E8`, warn `#8F5600`/`#FCEFD6`, bad `#B8302A`/`#FBE4E2`, draft `#5E574F`/`#EFEAE3`
- Type: 12 · 13 · 15 (basis) · 17 · 22 · 28 · 36 px. Gewichten 550/620/700. Bedragen met `tabular-nums`.
- Spacing: raster van 4 px (`--s-1` … `--s-16`). Radius: 6 · 10 · 14 · 20 · pill. Schaduwen: `--sh-1`, `--sh-2`, `--sh-paper`, `--sh-pop`.

## Assets
- `icons.svg`: sprite met `<symbol>`s in Lucide-stijl (ISC-licentie) plus het merkteken `#mus`. Zet de sprite in `base.html` direct na `<body>` met `{% include "icons.svg" %}` en gebruik `<svg class="i"><use href="#naam"/></svg>`. Het merkteken kleurt mee via `--mark-body` en `--mark-accent`.
- Favicon: gebruik `#mus` als losse SVG op 16/32 px (vleugel en oog mogen dan weg).
- Illustraties: de mus op een dakgoot (`.empty-art`) en de viering (`.celebrate`) zijn in CSS en SVG gemaakt, zonder afbeeldingen.

## Aannames om te controleren
- "Creditnota maken" levert een bewerkbaar concept op.
- Een verzonden offerte blijft bewerkbaar. Het offertenummer wordt toegekend bij verzenden.
- De stappen voor de Moneybird-export zijn algemeen gehouden. Controleer menu- en bestandsnamen.
- Een creditnota neemt de klant van de originele factuur over. Die is niet te wijzigen.
- "Nog open" op een factuur is factuurbedrag min creditnota's min betalingen. Het maximum voor creditnota's is het factuurbedrag, los van wat er al betaald is.

## Voorstellen (vragen backendwerk)
Vervallen-status · filtertabs, zoeken en jaarfilter op facturen · tijdlijn op de factuur · documenten per contact · onboarding-checklist · bestandsherkenning vóór de proefdraai · bestanden bewaren na de proefdraai · live voorbeeld van de factuurkop · ⌘K met globaal zoeken.

## Fallback voor invoker commands
```js
document.addEventListener('click', e => {
  const b = e.target.closest('[commandfor]');
  if (!b || 'command' in HTMLButtonElement.prototype) return;
  const el = document.getElementById(b.getAttribute('commandfor'));
  if (b.getAttribute('command') === 'show-modal') el?.showModal();
  if (b.getAttribute('command') === 'close') el?.close();
});
```
