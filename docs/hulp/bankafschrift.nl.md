# Bankafschrift inlezen

Download het afschrift van je bankrekening en lees het in Huismus in. Huismus
kijkt welke facturen er betaald zijn en boekt de betalingen die zeker zijn.
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

Huismus kijkt nu alleen naar geld dat binnenkwam. Afschrijvingen telt het,
maar koppelt het nog niet aan je uitgaven. Elke bijschrijving legt Huismus
naast je facturen die nog openstaan.

Bovenaan zie je wat er in het afschrift stond: hoeveel betalingen, hoeveel
daarvan bij je facturen horen, en wat er bij kwam. Daaronder drie delen, die
je elk in- en uitklapt.

- **Te doen.** Past er een factuur, maar niet zeker? Bijvoorbeeld het nummer
  klopt maar het bedrag niet, of het bedrag en de naam kloppen maar er staat
  geen nummer bij. Dan stelt Huismus die factuur voor. Klik op
  **Bevestigen**, of kies een **Andere factuur**. Passen er meer facturen?
  Kies dan zelf en klik op **Boeken**. Of klik op **Overslaan**.
- **Geboekt.** Staat het factuurnummer in de omschrijving en is het bedrag
  precies wat er openstaat? Dan boekt Huismus de betaling zelf. Had je de
  betaling al zelf geregistreerd, dan staat er "stond al geboekt" en boekt
  Huismus hem niet nog een keer.
- **Niet herkend.** Past er geen enkele factuur? Dan is het vaak privé, of
  geld van je spaarrekening. Dit deel staat dicht: je hoeft er niets mee.
  Is het toch een betaling van een klant? Klap het open, klik op **Als
  factuurbetaling markeren** en kies de factuur.

Gebruik je je rekening ook privé? Dan staat het meeste onder **Niet
herkend**. Dat is goed zo.

Wat onder **Te doen** staat, blijft op de pagina, ook als je later terugkomt.
Op het overzicht staat het bovenaan bij **Te doen**.

Noemt een overboeking meer dan één factuur? Registreer de betaling dan zelf
op elke factuur, met **Betaling registreren**, en sla de regel hier over.

## Een betaling terugdraaien

Klopt een betaling toch niet? Klik op **Terugdraaien**, op de pagina van het
afschrift of op de factuur zelf. De betaling verdwijnt en de regel staat weer
bij **Te doen**. Een betaling die je zelf had geregistreerd, draait
Huismus nooit terug.

Een regel die je oversloeg, vind je onder **Overgeslagen**. Met
**Terugzetten** staat hij weer op de pagina.

Contant betaald? Dat staat niet op je afschrift. Zet de factuur dan zelf op
betaald.

Huismus bewaart elk afschrift dat je inleest. Het gaat mee in je back-ups.

## Waar je het afschrift vindt

Zo heet het bij de banken zelf (nagekeken op 20 november 2026). Kies
**CAMT.053** als je bank het heeft, anders **MT940**.

- **ING:** bij een zakelijke rekening, in Mijn ING Zakelijk. Een particuliere
  rekening bij ING geeft alleen CSV en pdf. Die leest Huismus niet; registreer
  een betaling dan op de factuur.
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
