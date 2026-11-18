# Wat staat waar in docs/

## Voor gebruikers

[`hulp/`](hulp/): de uitleg bij het gebruik, één bestand per onderwerp per
taal (`<onderwerp>.nl.md`, `<onderwerp>.en.md`). Huismus toont dezelfde
bestanden in de app onder **Hulp** (`huismus/core/help.py`), zodat de uitleg hoort
bij de versie die iemand draait. Een nieuw onderwerp: beide bestanden, met
een `# Titel` op de eerste regel, en de naam in een groep in `GROUPS` in `huismus/core/help.py`
(die bepaalt de kopjes en de volgorde op **Hulp**, in de app en op de site).
Geen verwijzingen naar SPEC.md, broncode of GitHub, en geen tekst over wet of
belasting (`CLAUDE.md`); een link naar een ander onderwerp schrijf je als
`back-ups.nl.md#kopje`. `tests/core/test_help.py` controleert dat.

Dezelfde bestanden staan ook op de Huismus-site (`mijnhuismus.nl`),
met een rondleiding door de app, de downloadknoppen, een pagina over
installeren en een pagina voor wie wil meebouwen. De site is vooral voor
mensen die geen techneut zijn: de app voor Mac en Windows komt eerst, zelf
draaien op een server staat als tweede route lager op de pagina.

[`site/`](site/): de schermafbeeldingen en animaties van de app op de site,
per taal en voor licht en donker. Ze komen van een verzonnen administratie
(`huismus/core/site_data.py`). Ziet een scherm op de site er anders uit dan in
de app, maak ze dan opnieuw en commit ze:

```
./scripts/site-beelden.sh
```

Twee promofilms (1920×1080 mp4, donker, in de huisstijl van de app en de site),
van dezelfde verzonnen administratie. Ze komen in `~/Downloads/huismus-films/`,
niet in de repo:

```
./scripts/promo-film.sh              # allebei
./scripts/promo-film.sh bonnetjes    # 29 seconden, zonder stem
./scripts/promo-film.sh overzicht    # 63 seconden, met stem en ondertitels
```

- **bonnetjes:** een dag bonnetjes gaat als foto naar je cloudmap, Huismus haalt
  ze op en leest ze, en in Verwerken zeg je drie keer "Klopt". De AI-dienst is
  een nepservertje in het script: er gaat niets naar buiten.
- **overzicht:** wat Huismus is, voor wie, en wat je ermee doet, in het verhaal
  van de homepage. Het script staat in
  [`design/films/script-overzicht.md`](design/films/script-overzicht.md). Je
  krijgt drie versies (met stem, met stem en Nederlandse ondertitels in beeld,
  zonder stem met muziek en ondertitels) en losse ondertitels in het Nederlands
  en Engels (`.vtt`). De stem is een proefstem van macOS; een eigen opname per
  shot zet je in `scripts/promo/film/stem/`, zie het script.

`scripts/promo_film.py` neemt de echte schermen op, Remotion monteert ze
(`scripts/promo/film/`, draait op Node en hoort niet bij de app), en
`scripts/promo_geluid.py` maakt de stem, de ondertitels en de muziek. De letters
en het logo komen uit de app zelf. Het klikgeluid is CC0, van Kenney. Bij elke
film schrijft het script om de drie seconden een beeld naar `stills/`, om na te
kijken.

Op de site staan ze als kleine versies (1280×720) in `docs/site/film-*.nl.mp4`, elk
met een stilstaand beeld: de overzichtsfilm zonder stem op de homepage, onder
"Voor wie", en de bonnetjesfilm boven het hulpstuk "Bonnetjes onderweg". Alleen
op de Nederlandse pagina's, want de koppen en de app in de films zijn
Nederlands. Er speelt niets vanzelf. Ziet een scherm er anders uit, maak ze dan
opnieuw en commit ze:

```
./scripts/promo-film.sh site
```

De oudere film van een factuur maken, met een camera boven de browser en een
klik- of toetsgeluid bij elke klik en toets, bestaat nog. Muziek eronder is
optioneel (let op de licentie):

```
./scripts/promo-film.sh factuur ~/Downloads/huismus-factuur.mp4 muziek.mp3
```

Zelf bekijken:

```
SECRET_KEY=dev DEBUG=true uv run python manage.py build_site _site
python3 -m http.server 8797 -d _site
```

Bezoeken tellen: de site telt met [GoatCounter](https://www.goatcounter.com),
zonder cookies en zonder JS, maar alleen als de repo de variabele
`HUISMUS_SITE_COUNTER` heeft (GitHub → Settings → Secrets and variables →
Actions → Variables) met de code van het account, het deel vóór
`.goatcounter.com`. De downloadknoppen gaan naar `/download/mac/` en
`/download/windows/`; een bezoek daar is een download. Het aantal downloads
per bestand staat ook bij elke release op GitHub.

Bij elke release zet `.github/workflows/pages.yml` hem online, en met de hand
(workflow_dispatch) vanaf `main`. Hoe hij gemaakt wordt: `huismus/core/site.py`.

## Voor beheerders

- [`tailscale.md`](tailscale.md): Huismus via HTTPS in je tailnet.
- [`backups.md`](backups.md): back-ups met de hand maken en terugzetten.
- [`email.md`](email.md): waar het mailwachtwoord staat, mailen in tests.

## Voor ontwikkelaars

- [`architectuur.md`](architectuur.md): de projectkaart: apps, modellen
  en hun relaties, wat doet welke map, en waar de harde regels wonen.
- [`desktop.md`](desktop.md): hoe de desktop-app werkt, gebouwd en
  uitgebracht wordt.
- [`frontend.md`](frontend.md): hoe de schermen in elkaar zitten.
- [`design/`](design/): het ontwerp en de componentenpagina.
- [`invoice-requirements.md`](invoice-requirements.md): factuureisen met
  bronnen.
- [`belastingregels.md`](belastingregels.md): KOR, btw-tarieven,
  voorbelasting, btw-aangifte en bewaarplicht, met bronnen.

De backlog staat openbaar in de
[issues](https://github.com/codebyarne/huismus/issues). De productbesluiten,
het logboek per mijlpaal en de registratie
bij Google, Microsoft en Dropbox staan in een privé-repo van de maintainer,
`huismus-intern`. Code en commentaar verwijzen ernaar als
`huismus-intern/besluiten.md` met een datum; het besluit zelf staat in
`SPEC.md` als het het ontwerp raakt.
