# Importeren uit een ander pakket of Excel

Staat je administratie in een ander pakket dan Moneybird, of in Excel? Dan
zet je je klanten, facturen, offertes en uitgaven in het sjabloon van
Huismus en importeer je ze in één keer. Huismus doet eerst een proefdraai en
slaat pas iets op als jij dat kiest.

De import is bedoeld voor een Huismus die nog leeg is, of nieuw. Wat er al
staat, verandert hij niet.

## Het sjabloon invullen

1. Open **Importeren** en kies **Uit een ander pakket of Excel**.
2. Klik op **Sjabloon downloaden**. Je krijgt een zip met zeven
   CSV-bestanden en een LEESMIJ.
3. Open de bestanden in Excel of Numbers. In elk bestand staat één
   voorbeeld. Vervang het door je eigen gegevens en laat de eerste rij met
   de kolomnamen staan.
4. Een bestand dat je niet nodig hebt, haal je weg. Een kolom die je niet
   nodig hebt ook, behalve de verplichte hieronder.
5. Maak er weer één zip van en sleep die naar het vak. Klik op **Proefdraai
   starten**.

Een voorbeeld dat je laat staan, slaat Huismus over.

## Wat de proefdraai laat zien

De proefdraai slaat niets op. Je ziet per bestand wat Huismus herkent, hoeveel
klanten, facturen, offertes en uitgaven nieuw zijn, en wat er niet klopt:

- **Geweigerd**: een factuur waarvan de omzet of btw per tarief niet klopt
  met de regels, of een uitgave die niet de som van haar regels is. Die
  komt niet in Huismus. Verbeter het bestand en probeer het opnieuw.
- **Overgeslagen**: een factuur zonder regels, of voor een klantnummer dat
  niet in het klantenbestand en niet in Huismus staat.
- **Bedragen kloppen niet met de regels**: het totaal in het bestand wijkt
  af van wat de regels samen zijn. Huismus neemt het totaal uit het bestand
  over en noemt het verschil.
- **Misschien dubbel**: staan er al uitgaven in Huismus, dan komen die uit
  het bestand erbij. Heeft een nieuwe uitgave dezelfde datum en hetzelfde
  bedrag als een bestaande, dan noemt de proefdraai hem. Huismus importeert
  hem wel; is hij dubbel, verwijder hem dan daarna.
- **Zonder btw-tarief**: gebruik je de
  kleineondernemersregeling (KOR) niet, dan telt Huismus de btw van
  een uitgaveregel pas mee in het rapport Btw-aangifte als de regel een
  btw-tarief heeft. De proefdraai zegt hoeveel regels er geen hebben. Het
  tarief kies je daarna bij de uitgave.
- **Let op**: een kolom die Huismus niet kent, of een pdf of bonnetje dat
  nergens bij hoort.

Vul eerst je bedrijfsgegevens in bij **Instellingen**. Een geïmporteerde
factuur krijgt de bedrijfsgegevens van dat moment mee.

Ziet het er goed uit, klik dan op **Nu echt importeren**. Importeer je
dezelfde zip later nog eens, dan verandert er niets.

## De bestanden en hun kolommen

Huismus herkent een bestand aan zijn kolomnamen, niet aan de bestandsnaam.
De namen mogen in het Nederlands of in het Engels, zoals het sjabloon ze
geeft. Ontbreekt een verplichte kolom, dan stopt de import en zegt hij welke.

- **klanten.csv**: verplicht zijn **klantnummer**, **bedrijfsnaam** en
  **achternaam**. Elke klant heeft een bedrijfsnaam of een naam.
- **contactpersonen.csv**: de personen bij een klant. Verplicht:
  **klantnummer** en **naam**.
- **facturen.csv**: een rij per factuur en creditnota. Verplicht: **soort**
  (factuur of creditnota), **nummer**, **factuurdatum**, **klantnummer**,
  **bedrag excl. btw**, **btw** en **totaal incl. btw**. Een creditnota
  schrijf je met negatieve bedragen, met in **gecrediteerde factuur** het
  nummer van de factuur waar hij bij hoort.
- **regels.csv**: de regels van je facturen, creditnota's en offertes.
  Verplicht: **soort**, **nummer**, **omschrijving**, **prijs per eenheid**
  en **btw-tarief (%)**. Een leeg **aantal** is een vaste prijs.
- **offertes.csv**: verplicht zijn **nummer**, **datum**, **klantnummer**,
  **status** (verzonden, geaccepteerd, afgewezen of verlopen) en de drie
  bedragen.
- **uitgaven.csv**: verplicht zijn **uitgavenummer**, **datum** en **bedrag
  (bruto)**. Het uitgavenummer kies je zelf, bijvoorbeeld 1, 2, 3.
- **uitgaveregels.csv**: alleen nodig als een uitgave meer regels heeft, of
  een categorie of btw-tarief. Verplicht: **uitgavenummer** en **bedrag
  (bruto)**.

Vul je bij een factuur **betaald** en **laatst betaald op** in, dan maakt
Huismus daar één betaling van. Zonder datum maakt Huismus geen betaling: de
factuur staat dan open, en de proefdraai noemt hem.

## Bedragen, datums en tekens

- Tussen de kolommen staat een puntkomma. Excel en Numbers in het
  Nederlands doen dat vanzelf als je opslaat als CSV.
- Een bedrag schrijf je als 1234,56. Ook 1.234,56 en 1234.56 leest Huismus.
- Een datum schrijf je als 2026-03-14 of 14-03-2026. Ook 14-3-2026 mag.
  Schuine strepen en een jaar van twee cijfers leest Huismus niet.
- Huismus importeert alleen euro's.

Kan Huismus een bedrag of datum niet lezen, dan stopt de import en zegt hij
in welk bestand, welke rij en welke kolom.

## Pdf's en bonnetjes

Heb je de pdf's van je facturen? Zet ze in de zip in **pdf/facturen**,
**pdf/creditnotas** en **pdf/offertes**, met het nummer als naam,
bijvoorbeeld `2025-0012.pdf`. Huismus bewaart zo'n pdf als het origineel bij
de factuur. Zonder pdf maakt Huismus hem zelf.

Bonnetjes zet je in de map **bonnetjes**. In **uitgaven.csv** zet je de
bestandsnaam in de kolom **bonnetjes**. Meer bonnetjes bij één uitgave
scheid je met ` | `.

## Hulp van een AI-assistent

Een AI-assistent kan de export van je oude pakket omzetten naar het
sjabloon. Geef hem het sjabloon en je export, en vraag hem de bestanden te
vullen. Je laat die dienst dan wel je administratie lezen. De proefdraai
laat zien of het resultaat klopt: elk totaal wordt tot op de cent
nagerekend.

Per pakket staat er een handleiding met een opdracht die je zo kunt kopiëren:
[Rompslomp](rompslomp.nl.md), [Tellow](tellow.nl.md),
[e-Boekhouden.nl](e-boekhouden.nl.md), [Jortt](jortt.nl.md) en
[Excel](excel.nl.md).

## Een export uit Huismus importeren

De zip van **Instellingen → Exporteren** heeft dezelfde vorm als het
sjabloon. Zo neem je je administratie mee naar een nieuwe Huismus. Wat de
export bevat, lees je bij [Exporteren](exporteren.nl.md).

Importeer een export niet in de Huismus waar hij uit komt. Facturen herkent
Huismus aan hun nummer, maar je uitgaven komen er dan dubbel in. Wil je
terug naar een eerdere stand, zet dan een back-up terug: zie
[Back-ups](back-ups.nl.md).

## Wat niet meegaat

- Concepten.
- Losse deelbetalingen: per factuur komt er één betaling.
- Het adres van de klant op het moment van de factuur. De factuur krijgt het
  adres van de klant van nu. Op de originele pdf staat het oude adres nog.
- De taal van een factuur: elke factuur krijgt de taal uit je instellingen.

Kom je uit Moneybird? Dan is er een eigen import die de export van
Moneybird leest zoals hij is: zie
[Overstappen uit Moneybird](moneybird.nl.md).
