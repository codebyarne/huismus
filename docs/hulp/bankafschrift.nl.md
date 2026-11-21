# Bankafschrift inlezen

Download het afschrift van je bankrekening en lees het in Huismus in. Huismus
koppelt wat erbij komt aan je facturen en wat eraf gaat aan je uitgaven. Wat
zeker is, boekt Huismus zelf.
Je bankgegevens blijven op je eigen computer: Huismus maakt geen verbinding
met je bank.

## Zo lees je een afschrift in

1. Download bij je bank een afschrift als **CAMT.053** of **MT940**. Hieronder
   staat per bank waar dat zit.
2. Ga in Huismus naar **Bank**.
3. Sleep het bestand naar het vak, of klik op **Bestand kiezen**. Een zip
   met meer afschriften kan ook.
4. Klik op **Inlezen**.

Kies bij je bank de periode sinds de vorige keer. Overlapt die met een
afschrift dat je al inlas, dan is dat geen probleem: hetzelfde afschrift
nog een keer inlezen verandert niets.

## Wat Huismus doet

Elke bijschrijving legt Huismus naast je facturen die nog openstaan. Elke
afschrijving legt Huismus naast je uitgaven die nog geen bankregel hebben.

Bovenaan zie je wat er in het afschrift stond: hoeveel betalingen, hoeveel
daarvan bij je administratie horen, wat er bij kwam en wat er af ging.
Daaronder drie delen, die je elk in- en uitklapt. Bij en af staan door
elkaar, op datum, zoals op je afschrift.

- **Te doen.** Past er een factuur, maar niet zeker? Bijvoorbeeld het nummer
  klopt maar het bedrag niet, of het bedrag en de naam kloppen maar er staat
  geen nummer bij. Dan stelt Huismus die factuur voor. Klik op
  **Bevestigen**, of kies een **Andere factuur**. Passen er meer facturen?
  Kies dan zelf en klik op **Boeken**. Of klik op **Overslaan**.
- **Geboekt.** Staat het factuurnummer in de omschrijving en is het bedrag
  precies wat er openstaat? Dan boekt Huismus de betaling zelf. Had je de
  betaling al zelf geregistreerd, dan staat er "stond al geboekt" en boekt
  Huismus hem niet nog een keer.
- **Niet herkend.** Past er geen enkele factuur of uitgave? Dan is het vaak
  privé, of geld van of naar je spaarrekening. Dit deel staat dicht: je hoeft
  er niets mee. Is het toch een betaling van een klant? Klap het open, klik
  op **Als factuurbetaling markeren** en kies de factuur. Heb je zakelijk
  iets betaald, maar staat de uitgave nog niet in Huismus? Klik dan op
  **Uitgave maken** (zie hieronder). Met **Alles**, **Bij** en **Af** zie je
  één kant.

Gebruik je je rekening ook privé? Dan staat het meeste onder **Niet
herkend**. Dat is goed zo.

Wat onder **Te doen** staat, blijft op de pagina, ook als je later terugkomt.
Op het overzicht staat het bovenaan bij **Te doen**.

## Afschrijvingen en je uitgaven

Huismus kijkt bij een afschrijving naar je uitgaven die nog geen bankregel
hebben, met precies hetzelfde bedrag (met btw, tot op de cent). Alleen
uitgaven van 45 dagen voor tot 7 dagen na de datum op je afschrift tellen
mee.

- **Geboekt.** Is er precies één zo'n uitgave, past de naam van de
  leverancier en liggen de datums hooguit 7 dagen uit elkaar? Dan koppelt
  Huismus de afschrijving zelf aan die uitgave.
- **Te doen, met een voorstel.** Past de naam, maar betaalde je de rekening
  later? Of kloppen bedrag en datum, maar geeft de bank een andere naam, zoals
  bij pinnen? Dan stelt Huismus die uitgave voor. Klik op **Bevestigen**, of
  kies een **Andere uitgave**.
- **Te doen, zelf kiezen.** Is er een uitgave met hetzelfde bedrag, maar past
  verder niets? Dan staat ze bovenaan de keuzelijst. Is het die? Klik op
  **Boeken**. Zo maak je geen tweede uitgave voor hetzelfde bonnetje.

Alleen het bedrag is voor Huismus nooit genoeg. En Huismus maakt nooit zelf
een uitgave.

### Een uitgave maken van een afschrijving

Klik op **Uitgave maken**. Je krijgt een nieuwe uitgave met de datum, de
naam, de omschrijving en het bedrag van je bank. Vul de categorie aan, en
zonder de kleineondernemersregeling (KOR) de btw en het tarief: die kent de
bank niet. Voeg het bonnetje
toe, nu of later. Klik op **Opslaan**: je bent terug op **Bank** en de
afschrijving staat bij **Geboekt**.

Op de pagina van de uitgave staat daarna "Afgeschreven op …", met de naam
uit je afschrift.

Is een afschrijving geen uitgave, zoals geld naar je spaarrekening of iets
privé? Laat hem staan onder **Niet herkend**, of klik op **Overslaan**.

Noemt een overboeking meer dan één factuur? Registreer de betaling dan zelf
op elke factuur, met **Betaling registreren**, en sla de regel hier over.

## Terugdraaien

Klopt een betaling toch niet? Klik op **Terugdraaien**, op de pagina van het
afschrift of op de factuur zelf. De betaling verdwijnt en de regel staat weer
bij **Te doen**. Een betaling die je zelf had geregistreerd, draait
Huismus nooit terug.

Bij een afschrijving kan het ook, op **Bank** of op de pagina van de uitgave.
Dan gaat alleen de koppeling weg: de uitgave blijft staan. Verwijder je een
uitgave met een afschrijving, dan staat die afschrijving weer op **Bank**.

Een regel die je oversloeg, vind je onder **Overgeslagen**. Met
**Terugzetten** staat hij weer op de pagina.

Contant betaald? Dat staat niet op je afschrift. Zet de factuur zelf op
betaald. Een uitgave met bonnetje telt gewoon mee, ook zonder bankregel.

Las je een afschrift in voordat Huismus afschrijvingen kende? Lees hetzelfde
bestand dan nog een keer in. Huismus voegt alleen de afschrijvingen toe.

Huismus bewaart elk afschrift dat je inleest. Het gaat mee in je back-ups.

## Waar je het afschrift vindt

Zo heet het bij de banken zelf (nagekeken op 20 november 2026). Kies
**CAMT.053** als je bank het heeft, anders **MT940**.

- **ING:** bij een zakelijke rekening, in Mijn ING Zakelijk. Een particuliere
  rekening bij ING geeft alleen CSV en pdf. Die leest Huismus niet; registreer
  betalingen van klanten dan zelf op de factuur.
- **Rabobank:** **Transacties downloaden** › je rekening › kies het
  downloadformaat CAMT.053 en de periode › **Downloaden**. "Vanaf de laatste
  download" kan ook.
- **ABN AMRO:** **Zelf regelen** › **Bij- en afschrijvingen downloaden** ›
  rekening › periode › CAMT.053. In de app: Profiel › Rekeningen en betalen ›
  Afschriften en jaaroverzicht.
- **bunq:** Profiel › Accounting › **Export Statement**, en kies MT940. bunq
  heeft geen CAMT.053.
- **Knab, Triodos:** download de transacties als CAMT.053.
- **SNS, ASN, RegioBank:** **transacties downloaden** (RegioBank: **Bij- en
  afschrijvingen downloaden**) › CAMT.053 › **Downloaden**. Je krijgt een zip;
  uitpakken is niet nodig.
- **Revolut Business:** Statements › Account statement › kies je
  euro-rekening, de periode en XML (CAMT.053) › **Generate**.

Huismus leest alleen bedragen in euro's.
