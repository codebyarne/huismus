# Script: de overzichtsfilm

Wat Huismus is, voor wie, en wat je ermee doet, in ongeveer een minuut. De film volgt
het verhaal van de homepage (`huismus/templates/site/index.html`): wat het is, voor wie,
overstappen, het hele jaar (factuur, bonnetjes, btw en jaar), privacy, downloaden.

- **Beeld:** 1920×1080, donker, in "Helder" met het logo "Tegel". Links de kop van het
  shot met drie punten, rechts het echte scherm van Huismus op nepdata.
- **Stem:** Nederlands, je en jij, volgens `docs/schrijfwijzer.md`. Niets over wet of
  belasting: de film zegt wat je op het scherm ziet.
- **Ondertitels:** Nederlands en Engels als losse `.vtt`, en een versie met de
  Nederlandse in beeld.
- **Muziek:** een rustige baan onder de stem, door het script zelf gemaakt.

De bron is `scripts/promo/film/src/overzicht.json`: daar staan de tijden en de tekst
waar de film mee gemaakt wordt. Wijzig je de tekst, wijzig hem daar en hier.
Opnieuw maken: `./scripts/promo-film.sh overzicht`.

## De shots

| # | Tijd | Shot (bestand van de stem) | Beeld | Stem | Ondertitel Engels |
|---|---|---|---|---|---|
| 1 | 0:00 – 0:05,5 | `01-huismus` | Het logo, dan de kop van de site: "Je boekhouding op je eigen computer", met de framboos streep. | Dit is Huismus. Je boekhouding, op je eigen computer. | This is Huismus. Your bookkeeping, on your own computer. |
| 2 | 0:05,5 – 0:13 | `02-voor-wie` | Het hele venster van Huismus, dan het Overzicht: de omzet van dit jaar en Te doen. Links: Gratis, Geen abonnement, Geen account, Met of zonder KOR. | Een gratis app voor zzp’ers die hun boekhouding zelf doen. Zonder abonnement en zonder account. | A free app for freelancers who do their own bookkeeping. No subscription and no account. |
| 3 | 0:13 – 0:23,5 | `03-overstappen` | Importeren uit Moneybird: de proefdraai met vier jaren, de facturen die een cent afwijken, dan "Je administratie is verhuisd". | Kom je van Moneybird? Neem al je jaren mee. Huismus rekent eerst elke factuur na, tot op de cent, en laat zien wat afwijkt. Dan pas importeer je. | Coming from Moneybird? Bring all your past years with you. Huismus first checks every invoice, to the cent, and shows you any differences. Only then do you import. |
| 4 | 0:23,5 – 0:32 | `04-factuur` | Een conceptfactuur: een regel erbij, het totaal, de vraag "Factuur definitief uitgeven?" met het nummer, de uitgegeven factuur. | Een factuur maak je zo: kies een klant en typ wat je deed. Huismus rekent het totaal uit en geeft hem een nummer. | This is how you make an invoice: pick a customer and type what you did. Huismus adds up the total and numbers the invoice. |
| 5 | 0:32 – 0:39 | `05-bonnetjes` | Verwerken: de foto van een bonnetje naast wat Huismus las, dan Klopt en het volgende bonnetje. Links ook: "Een AI naar keuze leest hem". | Bonnetjes zet je als foto in een map. Huismus haalt ze op, en jij kijkt ze na. | Drop photos of your receipts in a folder. Huismus picks them up, and you check them. |
| 6 | 0:39 – 0:50 | `06-jaar` | Het jaaroverzicht: omzet, kosten en winst, dan de KOR-grens. Bij de derde zin de btw-aangifte van een kwartaal uit de geïmporteerde jaren (die rekenen btw). | Je ziet je omzet, je kosten en je winst van het hele jaar. Met de KOR zie je hoe ver je van je grens bent. Zonder KOR staan je btw-bedragen per kwartaal klaar. | You see your revenue, costs and profit for the whole year. With the KOR you see how far you are from your threshold. Without the KOR your VAT amounts are ready each quarter. |
| 7 | 0:50 – 0:56,5 | `07-van-jou` | De kaart "Wat er met je gegevens gebeurt" van de site: Jouw computer, en de vier schakelaars die uit staan. | Alles staat op je eigen computer. Je gegevens gaan alleen ergens heen als jij dat aanzet. | Everything is on your own computer. Your data only goes somewhere when you switch that on. |
| 8 | 0:56,5 – 1:03 | `08-download` | Het logo, "Download Huismus gratis", "Voor Mac en Windows", en mijnhuismus.nl als knop. | Download Huismus gratis, voor Mac en Windows, op mijnhuismus.nl. | Download Huismus for free, for Mac and Windows, at mijnhuismus.nl. |

In elk shot begint de stem een halve seconde na het beeld (shot 1: 0,9 s, shot 8:
0,6 s). De laatste ondertitel van een shot blijft staan tot vlak voor het volgende.
150 woorden; met de proefstem blijft er per shot anderhalve tot twee seconden
over, genoeg voor een stem die rustiger spreekt.

## Een andere stem

De stem in de film is een proefstem: Xander van macOS (`say`), op de computer die de
film maakt. Er gaat niets naar een dienst.

De definitieve stem neem je per shot op, één bestand per regel van de tabel, met de
naam uit de derde kolom: `scripts/promo/film/stem/01-huismus.wav` tot en met
`08-download.wav` (`.mp3`, `.m4a` en `.aiff` mogen ook). Draai daarna
`./scripts/promo-film.sh overzicht`. Staat er voor een shot een opname, dan gebruikt
de film die; anders de proefstem. De montage verandert niet: elk shot houdt zijn tijd,
de stilte voor en na een opname gaat eraf, elk shot wordt even hard gemaakt, en de
ondertitels schuiven mee met hoe lang de opname duurt. Is een opname langer dan zijn
shot, dan stopt het script en zegt het hoeveel.

De versie zonder stem (`huismus-overzicht-zonder-stem.mp4`, muziek en ondertitels in
beeld) is bedoeld voor de site zolang de stem een proefstem is.
