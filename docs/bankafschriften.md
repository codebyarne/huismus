# Bankafschriften: welke bestanden de Nederlandse banken geven

Voor issue #77 (SPEC.md M23): je downloadt een afschrift bij je bank en
leest het in Huismus in. Hier staat welk formaat elke bank geeft, waar je het
downloadt, en wat Huismus eruit leest. Alles gelezen op **2026-11-20**, bij de
bank zelf (hulppagina of formaatbeschrijving) of bij de Betaalvereniging,
tenzij er staat dat iets niet nagekeken is. Een bank verandert haar menu's:
klopt iets niet meer, pas het dan hier aan, met de nieuwe datum.

## Kort

- **CAMT.053** (XML) geven alle banken hieronder behalve bunq. Huismus leest
  elke versie (`camt.053.001.02` uit 2009, die alle banken beschrijven, en
  `camt.053.001.08` uit 2019, die Rabobank aanraadt).
- **MT940** (tekst) geven ING, Rabobank, ABN AMRO, bunq, Knab, Triodos en
  Revolut Business. Huismus leest de Nederlandse varianten. Voor bunq is het
  het enige formaat dat Huismus leest.
- **SNS, ASN en RegioBank** geven alleen nog CAMT.053, in een zip. Huismus
  leest de zip zonder uitpakken.
- **Rabobank** stopte per 15 november 2026 met het onderhoud van MT940. De
  einddatum is uitgesteld; het formaat blijft voorlopig beschikbaar.
- CSV en PDF leest Huismus niet: elke bank heeft er een eigen indeling voor.

## Per bank

### ING

- **Zakelijk** (Mijn ING Zakelijk): MT940, CAMT.053, "Camt.053 met batch
  details", CSV en PDF. Je kiest het bestandstype bij het downloaden. Een
  precies menupad voor zakelijk staat niet op de pagina's van ING die we lazen.
  [Bestandsformaten](https://www.ing.nl/zakelijk/betalen/betalingen-doen/bestandsformaten)
- **Particulier**: alleen CSV en PDF. Volgens ING zijn MT940 en CAMT.053
  alleen voor zakelijke rekeningen.
  [CSV-beschrijving](https://assets.ing.com/m/d2beb3f085411bc8/original/ING_CSV_Mijn_ING_Januari2026_tcm162-201483.pdf),
  [Afschriften downloaden](https://www.ing.nl/particulier/digitaal-bankieren/afschriften-downloaden)
- CAMT.053: versie `.001.02`.
  [Formaatbeschrijving CAMT.053](https://assets.ing.com/m/586dcf23e7912c2c/original/ING-Format-Description-CAMT053-Mijn-ING-Zakelijk-NL-v1-3_tcm162-127774.pdf)
- MT940: de betaler staat in `:86:` als `/CNTP/<IBAN>/<BIC>/<naam>/<plaats>/`,
  de omschrijving als `/REMI/USTD//<tekst>/`, een betalingskenmerk als
  `/REMI/STRD/CUR/<kenmerk>/` (en ook in `:61:`). Eén rekening per bestand.
  [Formaatbeschrijving MT940](https://assets.ing.com/m/d89af1a167ae39c/original/MT940-formaatbeschrijving-V266331_1118_tcm162-147668.pdf)

### Rabobank

- **Zakelijk**: CAMT.053, CSV, MT940 Structured (`.swi`) en PDF, via
  **Transacties downloaden** › Betaal- en spaarrekeningen › rekening(en) ›
  Downloadformaat en periode › Downloaden. "Vanaf de laatste download" kan
  ook. [Zakelijk rekeningafschrift](https://www.rabobank.nl/bedrijven/service/financiele-overzichten/zakelijk-rekeningafschrift-ontvangen)
- CAMT.053: `.001.08` en `.001.02`. De versies uit 2009 blijven tot november
  2029. [Kanalen](https://media.rabobank.com/asset/bc86cb09-cf41-4936-9bef-2b6c32d9cf7d/2026-10-01-Kanalen.pdf),
  [Informatie over bestandsformaten](https://www.rabobank.nl/bedrijven/service/online-bankieren/informatie-over-bestandsformaten)
- MT940: zou per 15 november 2026 stoppen; op 21 oktober 2026 uitgesteld,
  zonder nieuwe datum. Het wordt niet meer onderhouden.
  [Informatie over bestandsformaten](https://www.rabobank.nl/bedrijven/service/online-bankieren/informatie-over-bestandsformaten)
- MT940: de IBAN van de betaler staat op de regel onder `:61:`, de naam in
  `:86:` als `/ORDP//NAME/<naam>`, de omschrijving als `/REMI/<tekst>`, een
  kenmerk als `/REMI//CDTRREFTP//CD/SCOR/ISSR/CUR/CDTRREF/<kenmerk>`. Meer
  rekeningen en dagen per bestand.
  [Formaatbeschrijving MT940 Structured](https://media.rabobank.com/asset/2da2a993-ae7e-420b-b5eb-4f7355733902/Format-description-MT940S-Structured.pdf)
- Particulier: niet apart nagekeken.

### ABN AMRO

- **Zakelijk** (Internet Bankieren): **Zelf regelen** › Bij- en
  afschrijvingen downloaden › rekeningen › periode (tot 18 maanden terug) ›
  formaat XLS, PDF, TXT, MT940 of CAMT.053.
  [Bestanden downloaden](https://www.abnamro.nl/nl/zakelijk/internet-bankieren/bestanden-downloaden.html)
- **Particulier**: dezelfde formaten; in de app via Profiel › Rekeningen en
  betalen › Afschriften en jaaroverzicht › Bij- en afschrijvingen.
  [Downloaden](https://www.abnamro.nl/nl/prive/betalen/bij-en-afschrijvingen/downloaden.html)
- CAMT.053: `.001.02`; geeft betalingskenmerk en omschrijving apart, MT940
  niet. [Keuze formaat](https://www.abnamro.nl/nl/zakelijk/producten/betalen/sepa/rapportages/keuze-formaat.html)
- MT940: `:86:` als `/TRTP/…/IBAN/…/BIC/…/NAME/…/REMI/…/EREF/…`; oudere
  bestanden met `IBAN: … NAAM: … OMSCHRIJVING: …`. Een rond bedrag staat er
  zonder decimalen ("1210"). Het rekeningnummer in `:25:` is vaak zonder IBAN.
  [Formaatverschillen MT940](https://assets.abnamro.com/api/public/content/sepa-formaatverschillen-mt940-mt942.pdf)

### bunq

- PDF, CSV of MT940, geen CAMT.053. In de app: Profiel › Accounting › Export
  Statement, of rekening › Instellingen › Export statement.
  [How do I export a bank statement](https://help.bunq.com/articles/how-do-i-export-a-bank-statement)
- Het verschil tussen zakelijk en particulier noemt bunq niet. Welke
  `:86:`-variant bunq gebruikt, staat niet op die pagina: Huismus leest dan
  de hele tekst als omschrijving.

### Knab (zakelijk)

- CAMT.053, Excel, CSV en MT940 (gestructureerd), in de Persoonlijke
  Bankomgeving. Het menupad is niet nagekeken bij Knab zelf.
  [Bankkoppeling](https://www.knab.nl/zakelijk/boekhouden/bankkoppeling)

### Triodos

- CSV, Excel, CAMT.053, MT940 (gestructureerd) en PDF, in de app en
  Internet Bankieren. Het menupad is niet nagekeken bij Triodos zelf.
  [In welke bestandstypen](https://www.triodos.nl/veelgestelde-vragen/in-welke-bestandstypen-kan-ik-overzichten-downloaden?id=ecea2482a3bc)
- CAMT.053: `.001.02`.
  [Formaatbeschrijving CAMT.053](https://www.triodos.nl/downloads/camt053-formaatbeschrijving?id=78266bc3bd46)
- MT940 (oudere beschrijving): `:86:` met `>NN`-velden: `>21` de IBAN,
  `>22` tot `>27` naam, adres, omschrijving en kenmerk als één tekst. Of de
  huidige "MT940 (structured)" nog zo is, is niet nagekeken.
  [Formaatbeschrijving MT940](https://www.triodos.nl/downloads/mt940-formaatbeschrijving?id=833b31cfd216)

### SNS, ASN en RegioBank (de Volksbank)

- Alleen CAMT.053 (`.001.02`), als zip. MT940 is vervangen.
  - SNS: Mijn SNS › rekeningoverzicht › transacties downloaden › periode ›
    CAMT.053 › Downloaden.
    [CAMT.053 voor boekhoudpakketten](https://www.snsbank.nl/zakelijk/zzp/camt053-voor-boekhoudpakketten.html)
  - ASN: ASN Online Bankieren › rekeningoverzicht › transacties downloaden ›
    CAMT.053 › Downloaden.
    [CAMT.053](https://www.asnbank.nl/zakelijk/boekhoudpakket-koppelen/camt053.html)
  - RegioBank: Mijn RegioBank Zakelijk › rekening › Bij- en afschrijvingen
    downloaden › CAMT.053 › Downloaden.
    [CAMT.053](https://www.regiobank.nl/zakelijk/service/koppeling-boekhoudpakket/camt.053.html)

### Revolut Business

- PDF, CSV, XML (CAMT.053) en TXT (MT940): Home › … › Statements › Account
  statement › rekening › periode › bestandstype › Generate. Eén afschrift per
  valutarekening; Huismus leest alleen euro's.
  [How to get a monthly statement](https://help.revolut.com/business/help/managing-my-business/viewing-my-account-statements/how-to-get-a-monthly-statement/)

## Wat Huismus eruit leest

Alleen geboekte bijschrijvingen in euro's: bedrag, boekdatum, naam en IBAN
van de betaler, de omschrijving en een betalingskenmerk. Afschrijvingen,
terugboekingen en nog niet geboekte regels laat Huismus weg.

- **CAMT.053** (`huismus/bank/camt.py`), per `Ntry` met `CdtDbtInd` CRDT en
  status BOOK: `Amt`, `BookgDt`, `RltdPties/Dbtr/Nm` (of `Dbtr/Pty/Nm` in
  `.001.08`), `DbtrAcct/Id/IBAN`, `RmtInf/Ustrd` en
  `RmtInf/Strd/CdtrRefInf/Ref`. Een verzamelboeking met meer `TxDtls` geeft
  een regel per transactie. Bron voor de velden: de
  [richtlijn van de Betaalvereniging](https://www.betaalvereniging.nl/wp-content/uploads/IG-Bank-to-Customer-Statement-CAMT-053-v2.0.pdf)
  en de [formaatbeschrijving van Rabobank](https://media.rabobank.com/m/51aef0ab9e13e87c/original/Formaatbeschrijving_CAMT-053_v1-5-4_FEB2021_NL-pdf.pdf).
- **MT940** (`huismus/bank/mt940.py`): `:61:` en `:86:` in de varianten
  hierboven.
- Een **betalingskenmerk** is 7 tot 16 cijfers en komt als gestructureerde
  referentie mee. [Betaalvereniging](https://www.betaalvereniging.nl/en/knowledge-base/special-accounts-and-services/payment-reference/)

Wissel je van formaat (eerst MT940, daarna CAMT.053) voor een periode die je
al inlas, dan kan dezelfde betaling twee keer verschijnen: de banken schrijven
de omschrijving in beide formaten net anders. Huismus boekt hem dan niet
nog eens als de factuur al betaald is; de regel staat bij Zelf kiezen.

## Waarom geen bibliotheek

Voor MT940 bestaat `mt-940` (BSD), maar die leest de Nederlandse `:86:` niet
en valt bij een onbekend teken terug op een verkeerde codering. Voor CAMT.053
zijn de pakketten jong of groot. Beide lezers zijn klein en gebruiken alleen
de standaardbibliotheek en `defusedxml`, dat Huismus al had.
