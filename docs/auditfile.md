# Auditfile Financieel (XAF 4.0)

Naslag voor de auditfile die Huismus in de export zet (issue #123, `SPEC.md`
M26). Hier staat wat de Belastingdienst over het formaat publiceert, met de
bron erbij, en welke rekeningen Huismus gebruikt. **Dit is geen
boekhoudkundig of fiscaal advies.** Wat hier niet staat, beweert Huismus niet,
in de app, de hulp of de site: niet vanaf wanneer een versie verplicht is, en
niet welke pakketten een versie inlezen. Daar is geen officiële bron voor
gevonden.

Gelezen op 23 november 2026.

## 1. De bron: XAF 4.0.3

De Belastingdienst publiceert de auditfile op ODB (Ondersteuning Digitaal
Berichtenverkeer). Bij de auditfiles staat als actuele documentatie van de
Auditfile Financieel alleen versie 4.0.3:

- [XML Auditfile Financieel (XAF) 4.0.3](https://odb.belastingdienst.nl/documentatie/xml-auditfile-financieel-xaf-4-0-3/),
  met één zip:
  `https://odb.belastingdienst.nl/wp-content/uploads/2025/04/XMLAuditfile-Financieel-XAF-v-4.0.3.zip`
  (sha256 `49ba39862d10277130b170002933bfdfe804b33c145a5b4f975341c7578c9f1c`).
- [Achtergrond informatie XAF4.0](https://odb.belastingdienst.nl/auditfiles/achtergrond-informatie-xaf4-0/)
  (publicatiedatum 20-02-2025): "Deze versie is een doorontwikkeling van
  versie 3.2, die dateert uit 2014." en "Een significant verschil tussen XAF 4.0
  en XAF 3.2 is de reductie van het aantal datavelden van 250 naar 90."

Uit de zip, volgens het productoverzicht daarin (versie 4.0.3, 10-04-2025):

- `XmlAuditfileFinancieel4.0.xsd` (versie 4.0, 06-02-2025). Een kopie staat in
  `tests/fixtures/xaf/`, ongewijzigd (sha256
  `a6f35d4639deb3c4a4dc1b060cbf946558c8d3291a84ff6a75de2a0f6590dd82`). De tests
  valideren elke auditfile van Huismus ertegen.
- `XMLAuditfileFinancieelVersie_4.0_Toelichting.pdf` (29-01-2025): de uitleg
  hieronder.
- `XAF_4_0_Test_100425.XAF`: een testbestand. Het valideert tegen het XSD.

Het testbestand en het XSD gebruiken de namespace
`http://www.odb.belastingdienst.nl/Belastingdienst/BCPP/1.1/structures/XmlauditfileXAF_4.0`.
De toelichting noemt in paragraaf 3.7 een andere
(`http://www.odb.belastingdienst.nl/XAF/4.0`); Huismus volgt het XSD en het
testbestand, want daartegen wordt gevalideerd.

## 2. Wat een XAF 4.0 bevat

Uit de toelichting, paragraaf 3.2 "Structuur Auditfile Financieel" (R =
verplicht, O = facultatief):

```
Header 1..1, R
Company 1..1, R
  Street Address 0..*, O
  Customers Suppliers 0..1, O
    Customer Supplier 0..*, O
  General Ledger 0..1, O
    Ledger Account 1..*, R
  VAT Codes 0..1, O
  Periods 0..1, O
  Opening Balance 0..1, O
  Transactions 0..1, O
    Journal 0..*, O
      Transaction 0..*, O
        Transaction Line 0..*, O
          VAT 0..99, O
```

En daaronder, letterlijk:

- "Een bericht bevat informatie over 1 bedrijf (company)."
- "Een bericht bevat altijd stamgegevens (klanten/leveranciers,
  grootboekrekeningen, Btw codes, periodes)."
- "Een bericht bevat altijd een openingsbalans."
- "Een bericht bevat een of meerdere transacties. Transacties worden onder het
  betreffende journaal opgenomen. Een transactie bestaat uit een of meerdere
  transactieregels."

Verder uit de toelichting:

- **Tekenset** (3.3): UTF-8 of ISO-8859-1. Huismus schrijft UTF-8.
- **Datum** (3.5): `YYYY-MM-DD`.
- **Getallen** (3.6): "een punt als decimaal scheidingsteken.
  Duizendtal scheidingstekens (komma) en spaties zijn niet toegestaan."
  Bedragen hebben in het XSD twee decimalen (`TypeAmount2decimals`); of een
  bedrag debet of credit is, zegt een eigen veld (`amntTp`: `D` of `C`).
  Huismus schrijft daarom elk bedrag positief met de kant erbij.
- **Adres** (3.11): "Wanneer in het adres de straat en huisnummer niet
  gescheiden kunnen worden doorgegeven is het toegestaan deze gegevens in
  straatnaam te plaatsen. Het huisnummer wordt dan meegeleverd door hier NA in
  te vullen." Huismus bewaart een adresregel, geen los huisnummer, en doet dat.
- **RGS** (3.12): "Ten behoeve van koppeling met RGS is in de header van de
  auditfile het veld RGSversion opgenomen en onder het General Ledger element
  de RGScode van die is gekoppeld aan de grootboekrekening."
- **Btw-codes** (3.13): per btw-soort een id, een omschrijving en de rekeningen
  voor af te dragen en te vorderen btw. "Btw percentage en btw bedrag worden bij
  de transacties vermeld."
- **Openingsbalans** (3.15): "Een openingsbalans regel (obLine) bevat het saldo
  van de grootboekrekening op de openingsbalans." In het testbestand van de
  Belastingdienst is het totaal debet van de openingsbalans gelijk aan het
  totaal credit.

Verplicht volgens het XSD, en wat Huismus erin zet:

| Veld | Huismus |
|---|---|
| `header/fiscalYear`, `startDate`, `endDate` | het jaar, 1 januari, 31 december |
| `header/curCode` | de valuta van de instellingen (EUR) |
| `header/dateCreated` | de dag van de export |
| `header/softwareDesc`, `softwareVersion` | Huismus en zijn versie |
| `company/companyName` | de bedrijfsnaam |
| `company/taxRegistrationCountry` | het land van het bedrijf |
| `company/taxRegIdent` | het btw-nummer, leeg als het er niet is |
| `ledgerAccount/accID`, `accDesc`, `accTp` | zie sectie 3 |
| `transaction/nr`, `periodNumber`, `trDt` | volgnummer per dagboek, de maand, de datum |
| `trLine/nr`, `accID`, `docRef`, `effDate`, `amnt`, `amntTp` | per regel |

## 3. Rekeningschema

Een vast schema, met per rekening een code uit het Referentie GrootboekSchema
(RGS). Bron: de definitieve versie
[RGS 3.8](https://www.referentiegrootboekschema.nl/definitieve-versie-rgs-38),
bestand `RGS 3.8-def.xlsx` (sha256
`5c47edd7a2dd23900e85f392dea9dd027ea45d44bf6973bf6400d4760e48e07a`), blad
`MKB-RGS3.8-def`. De omschrijving in de laatste kolom staat zo in dat blad.
`header/RGSVersion` is `3.8`.

| Rekening | Naam in Huismus | Soort | RGS-code | Omschrijving in RGS 3.8 |
|---|---|---|---|---|
| 1100 | Debiteuren | B | BVorDebHad | Handelsdebiteuren nominaal |
| 1200 | Bank | B | BLimBanRba | Rekening-courant bank |
| 1290 | Beginbalans, nog in te delen | B | BVorTusTov | Tussenrekeningen overig |
| 1510 | Btw 1a hoog tarief | B | BSchBepBtwOla | 1a. Omzetbelasting leveringen/diensten belast met hoog tarief |
| 1520 | Btw 1b laag tarief | B | BSchBepBtwOlv | 1b. Omzetbelasting leveringen/diensten belast met laag tarief |
| 1530 | Btw 2a verlegd naar jou | B | BSchBepBtwOlw | 2a. Omzetbelasting leveringen/diensten waarbij de omzetbelasting naar u is verlegd |
| 1540 | Btw 4a uit landen buiten de EU | B | BSchBepBtwOlb | 4a. Omzetbelasting leveringen/diensten uit landen buiten de EU |
| 1550 | Btw 4b uit landen binnen de EU | B | BSchBepBtwOlu | 4b. Omzetbelasting leveringen/diensten uit landen binnen EU |
| 1560 | Voorbelasting | B | BSchBepBtwVoo | 5b. Voorbelasting |
| 1590 | Btw, niet in een rubriek | B | BSchBepBtwOvm | Overige mutaties omzetbelasting |
| 8010 | Omzet 1a hoog tarief | P | WOmzNodOdh | 1a. Netto-omzet uit verleende diensten belast met hoog tarief |
| 8020 | Omzet 1b laag tarief | P | WOmzNodOdl | 1b. Netto-omzet uit verleende diensten belast met laag tarief |
| 8050 | Omzet 1e 0% of niet bij jou belast | P | WOmzNodOdg | 1e. Netto-omzet uit verleende diensten belast met 0% of niet bij u belast |
| 8080 | Omzet 3b binnen de EU | P | WOmzNodOdi | 3b. Netto-omzet uit verleende diensten naar landen binnen de EU |
| 8090 | Omzet, niet in een rubriek | P | WOmzNoo | Overige netto-omzet |
| 4001 en verder | de naam van de uitgavencategorie | P | WBedAlkOal | Algemene kosten |
| 4999 | Kosten zonder categorie | P | WBedAlkOal | Algemene kosten |

Soort: B = balans, P = winst en verlies (`accTp`). Elke uitgavencategorie
krijgt een eigen rekening, in de volgorde van de lijst. Categorieën zijn
namen die de gebruiker kiest; een RGS-code per naam zou een gok zijn, dus
krijgen ze allemaal "Algemene kosten" en deelt de boekhouder in
(product-owner-agent 2026-11-23).

Welke omzet en btw in welke rubriek vallen, volgt het btw-aangifterapport
(`huismus/reports/vat_return.py`, bron `docs/belastingregels.md`, "Rubrieken
in detail"). Wat dat rapport onder "Niet meegeteld" zet (een factuur met
KOR-tekst, een import zonder btw per tarief, een ander tarief, btw verlegd naar
een klant buiten de EU of zonder land), staat op "Omzet, niet in een rubriek"
en "Btw, niet in een rubriek".

## 4. Wat Huismus boekt

Huismus slaat geen boekingen op. Bij elke export leidt hij ze af uit wat vastligt
(product-owner-agent 2026-11-13). Bedragen komen uit de opgeslagen totalen en
de opgeslagen btw per tarief van een uitgegeven document (harde regel 4), en
uit de bedragen van een uitgave zoals de gebruiker ze invoerde (harde regel 7).

| Dagboek | Wat | Debet | Credit |
|---|---|---|---|
| Verkoop (`VK`) | factuur, op de factuurdatum | Debiteuren: totaal incl. btw | Omzet en btw per rubriek |
| Verkoop (`VK`) | creditnota | andersom | |
| Bank (`BNK`) | betaling, op de betaaldatum | Bank | Debiteuren |
| Inkoop (`IK`) | uitgave, op de datum van de uitgave | Kosten per categorie, voorbelasting | Bank: het bruto bedrag |

Bij een uitgave met btw verlegd (2a, 4a, 4b) boekt Huismus de btw twee keer,
zoals het btw-aangifterapport hem telt: als voorbelasting (debet) en als af te
dragen btw in de rubriek (credit). De kosten zijn dan het bruto bedrag.

Met de KOR, of zonder btw om een andere reden, telt de btw op uitgaven nergens
(harde regel 7): de kosten zijn bruto en er is geen voorbelasting. Dat geldt dan
voor elk jaar, net als in het jaaroverzicht en het btw-aangifterapport.

De openingsbalans op 1 januari: per klant wat er openstond, uit alle facturen,
creditnota's en betalingen van vóór dat jaar, op Debiteuren, tegenover
"Beginbalans, nog in te delen". Het totaal is het eindsaldo van Debiteuren in
de auditfile van het jaar ervoor.

## 5. Wat er niet in staat

Banksaldo, eigen vermogen, privé-opnames en -stortingen, investeringen en
afschrijving: Huismus kent ze niet (`huismus-intern/besluiten.md`,
2026-11-13). Huismus weet ook niet of je een uitgave privé betaalde; elke
uitgave staat tegenover Bank. Een echte beginstand komt met #126, investeringen
met #124.
