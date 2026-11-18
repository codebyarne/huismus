# Ronde 8: de site in "Helder"

Ronde 7 was het concept voor de site in petrol op warme neutralen. Op 18 november 2026
kreeg de app de richting "Helder" en het logo "Tegel". Ronde 8 is hetzelfde verhaal in
die richting: de homepage en de pagina Functies van mijnhuismus.nl.

Het ontwerp is de site zelf: `huismus/templates/site/` met `site.css`, op de tokens van
`huismus/core/static/core/huismus.css`. Het canvas toont schermafbeeldingen van wat er
gebouwd is, op 390 en 1440 px, licht en donker. De link naar het canvas staat in
`huismus-intern/werkwijze.md`.

Bekijken:

```
SECRET_KEY=dev uv run python manage.py build_site /tmp/huismus-site
python3 -m http.server 8791 --directory /tmp/huismus-site
```

en open http://localhost:8791/.

## Wat blijft van ronde 7

- Het verhaal en de volgorde: de kop met foto 1 en het overzicht, de vier punten,
  Overstappen als petrol band, "Je administratie is van jou", het hele jaar in vier
  beelden, voor wie, het functieoverzicht, open, en het slot met de downloadknoppen.
- De teksten van `../ronde-7/site-prompt.md`, met de Engelse erbij.
- De vijf foto's van `../ronde-7/fotos/`. Niemand op de foto's is een gebruiker.
- Het functieoverzicht met maand en jaar, uit één lijst voor de homepage en Functies
  (`huismus/core/site_features.py`).

## Wat anders is in "Helder"

| | Ronde 7 | Ronde 8 |
|---|---|---|
| Achtergrond | warm wit `#FBF8F3`, donker `#191613` | koel bijna-wit `#F1F5F4`, donker `#061415` |
| Vlakken | witte kaarten met een rand en een schaduw | witte vellen met ronde hoeken, zonder rand |
| Petrol band | over de volle breedte | een vel met ronde hoeken binnen de pagina, `#0B4F51` |
| Letters | systeemletters, koppen rond | koppen in Bricolage Grotesque, tekst in Inter, als bestanden mee |
| Logo | de mus naast het woord, als tekst | de tegel met het woord als één tekening (`../icons/logo.svg`) |
| De mus | op de schermafdruk en in het slot, de oude tekening | dezelfde plekken, de nieuwe ronde mus, stil |
| Menu | een balk met een rand | los op de achtergrond; het huidige scherm als wit kaartje, zoals in de app |
| Schermen op de foto's | de app met het donkere menu | het overzicht en de proefdraai in "Helder" |
| Deelplaatje | een uitsnede van het overzicht, licht | één plaat in donker: logo, kop en het overzicht |

## Wat de keuring van ronde 7 vroeg, en hoe het er nu staat

- De schermafdruk in de kop heeft de volle breedte van zijn kolom en ligt niet over de
  foto. De foto staat eronder, over de hele breedte.
- De cijfers 1, 2 en 3 in de band zijn licht petrol, niet geel.
- De band is lager: de animatie is hooguit 640 px breed en staat naast de drie stappen.
  Op de telefoon zijn de stappen één lijst.
- De vier punten staan op 1440 px op één regel.
- Elke link en knop heeft zichtbare focus; op petrol is dat een witte ring.
- "Kan nu" en "Komt eraan" bovenaan Functies zijn twee gelijke knoppen.

## Zonder JavaScript

De site laadt niets van buiten en heeft geen script. Het menu op de telefoon en de
taalkeuze zijn popovers. Een browser die geen popovers kent, toont het menu als een rij
die omloopt.

## De beelden opnieuw maken

`./scripts/site-beelden.sh` maakt alles in `docs/site/`: de schermafbeeldingen en
animaties van de app, het deelplaatje (`delen.nl.png`, `delen.en.png`) en de foto's met
het scherm van de app op de laptop (`fotos/`, `scripts/site_fotos.py`). Het logo met het
woord maakt `scripts/make_wordmark.py`.

## Nog niet

De schermen zonder de KOR (de btw-aangifte, een bonnetje verwerken) staan nog niet op
de site: de verzonnen administratie voor de beelden werkt met de KOR. Dat is deel 5 van
issue #130.
