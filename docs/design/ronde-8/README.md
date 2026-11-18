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

## Herontwerp (18 november, na de eerste reviews)

De eerste bouw volgde ronde 7 op de voet. Een art director die de site niet maakte, vond
dat hij nog niet leest als een verzorgde marketingsite: geen blikvanger in het eerste
scherm, de app te klein om te lezen, tien keer hetzelfde witte vel, hele vensters met
steeds dezelfde zijbalk, en het functieoverzicht dubbel. De `product-owner`-agent keurde
het herontwerp hieronder (huismus-intern/besluiten.md, 2026-11-18).

| Blok | Nu |
|---|---|
| Kop van de pagina | blijft staan bij scrollen, half doorzichtig; taalkeuze zonder vlag |
| Kop van de homepage | gecentreerd, één kolom; de kop groter (tot 88 px), de vier punten als één regel met vinkjes |
| Het overzicht | groot op een petrol vlak (tot 1120 px breed), onderaan afgesneden; op de telefoon het telefoonscherm |
| Voor wie | de vijf foto's samen, de meubelmaker over de hele breedte, elk met alleen het beroep eronder; de twee zinnen over de KOR als tekst |
| Film (19 november, alleen Nederlands) | tussen "Voor wie" en "Overstappen": de kicker "Film", de kop "Huismus in één minuut" en de overzichtsfilm, gecentreerd, hooguit 960 px breed; altijd donker, zoals het deelplaatje; speelt pas als je op afspelen drukt. De bonnetjesfilm staat boven het hulpstuk "Bonnetjes onderweg" |
| Overstappen | de petrol band zonder foto; links tekst en de drie stappen, rechts de animatie |
| Van jou | zonder wit vel; de kaart met schakelaars als object |
| Het hele jaar | een wit vlak tot de rand met vier kaarten van ongelijke breedte, elk met een leesbaar stuk van de app: de factuur maken, Uitgaven op de telefoon, de KOR-grens met de kwartalen, het jaar met de knop CSV downloaden |
| Functies | van de homepage af; een strook "Komt eraan: … Verwacht in …" naar de pagina Functies |
| Open en eigen server | twee kaarten naast elkaar |
| Slot | de mus op de dakgoot en de downloadknoppen |
| Kickers | een klein kopje boven elke grote kop: Voor wie, Overstappen, Privacy, Het hele jaar, Open |
| Functies (pagina) | "Kan nu" als rijen (groep links, functies rechts), "Komt eraan" als vier kolommen |
| Gewone pagina's | de leeskolom gecentreerd; Hulp als lijst per groep; Installeren met Mac en Windows naast elkaar |

**Framboos** (`#B4184F`, in donker `#FF7BA5`, op petrol `#FF9DBE`) is de tweede kleur naast
petrol, hooguit één keer per scherm: de streep onder "je eigen computer" in de kop (alleen
versiering), de markering "Verwacht in …" op de petrol band, de stip in de strook naar
Functies en de eerstvolgende maand op Functies. Niet op knoppen, koppen, vlakken, iconen,
links, het logo, het menu of de voet, en niet op Hulp, Installeren en Meebouwen. De app
verandert hiervoor niet: daar blijft framboos de kleur van "te laat" (advies van de
PO-agent; de vraag gaat mee naar de eigenaar).

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
| De mus | op de schermafdruk en in het slot, de oude tekening | alleen in het slot, de nieuwe ronde mus, stil |
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
