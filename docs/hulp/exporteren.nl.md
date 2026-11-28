# Exporteren

Wil je je administratie buiten Huismus gebruiken, bijvoorbeeld voor je
boekhouder of in een spreadsheet? Download dan een export: één ZIP met je
facturen, offertes, klanten en uitgaven als CSV, de pdf's en bonnetjes, en
een auditfile per jaar. Die kun je openen zonder Huismus.

## Een export downloaden

Open **Instellingen → Exporteren**. Kies **Alles** of één jaar en klik op
**ZIP downloaden**. Op het **Jaaroverzicht** brengt **Exporteren →** je
naar dezelfde pagina, met dat jaar al gekozen.

Een jaar telt op factuurdatum, net als op het jaaroverzicht. Een uitgave telt
op haar eigen datum. Klanten gaan altijd allemaal mee, ook gearchiveerde.

## Wat erin zit

- **facturen.csv**: een rij per factuur en creditnota, met de klant zoals op
  de factuur, de bedragen, de omzet en btw per tarief, en of hij betaald is.
- **offertes.csv**: een rij per offerte, met de status en de factuur die
  eruit kwam.
- **regels.csv**: de regels van alle facturen, creditnota's en offertes.
- **klanten.csv**: al je klanten.
- **contactpersonen.csv**: de contactpersonen bij je klanten.
- **uitgaven.csv** en **uitgaveregels.csv**: je uitgaven, en per regel de
  categorie.
- **uren.csv**: je uren, met de klant, het tarief en het bedrag. Alleen als
  je in die periode uren hebt.
- **kilometers.csv**: je ritten, met van, naar, doel en kilometers. Alleen
  als je in die periode ritten hebt.
- **pdf/facturen**, **pdf/creditnotas** en **pdf/offertes**: elke pdf, met
  het nummer als naam. Het is dezelfde pdf als die je met **Downloaden**
  krijgt. Voor een factuur uit Moneybird is dat de originele pdf.
- **bonnetjes**: elk bonnetje, met het nummer van de uitgave ervoor.
- **auditfile-2025.xaf**: de auditfile van dat jaar. Kies je **Alles**, dan
  zit er een auditfile per jaar in. Zie [De auditfile](#de-auditfile).

Concepten gaan niet mee. Een factuur die je met **Toch bewerken** weer
concept hebt gemaakt ook niet, tot je hem opnieuw uitgeeft.

## De bedragen

Een creditnota staat negatief in de export. Tel je de kolom **bedrag excl.
btw** van een jaar op, dan krijg je de omzet van het jaaroverzicht.

Per btw-tarief staan er twee kolommen, bijvoorbeeld **omzet 21%** en **btw
21%**. Regels met verlegde btw staan in **omzet btw verlegd**. Een factuur
uit Moneybird met afwijkende btw (bijvoorbeeld door een korting) toont in
Huismus één regel "Btw". Bij zo'n factuur blijven de kolommen per tarief
leeg en staan alleen de totalen er.

## De auditfile

Een auditfile is het bestand dat een boekhoudprogramma inleest: je
boekhouder of een ander pakket krijgt je jaar dan in één keer binnen.
Huismus maakt hem in versie 4.0 (XAF), zoals de Belastingdienst die
beschrijft op
[odb.belastingdienst.nl](https://odb.belastingdienst.nl/documentatie/xml-auditfile-financieel-xaf-4-0-3/).

Erin staan je klanten, je facturen en creditnota's, de betalingen en je
uitgaven, geboekt op een vast rekeningschema. De omzet en de kosten zijn
gelijk aan het jaaroverzicht. Reken je btw, dan is de btw per rubriek gelijk
aan het btw-aangifterapport. Elke uitgavencategorie krijgt een eigen
rekening met de naam van de categorie.

Wat er niet in staat, omdat Huismus het niet bijhoudt:

- je banksaldo, je eigen vermogen en wat je privé opnam of stortte;
- investeringen en afschrijving;
- of je een uitgave privé betaalde: elke uitgave staat tegenover de bank.

Aan het begin van het jaar staat alleen wat klanten je toen nog moesten
betalen. Het bedrag ertegenover staat op **Beginbalans, nog in te delen**;
dat deelt je boekhouder zelf in. Een echte beginstand invullen komt later.

## Openen in een spreadsheet

De CSV's gebruiken een puntkomma tussen de kolommen en een komma in
bedragen ("1234,56"), zonder punt voor de duizendtallen. Datums staan als
2026-11-02. Excel en Numbers in het Nederlands openen ze meteen goed. Een
Engelse spreadsheet vraagt soms welk scheidingsteken je wilt: kies dan de
puntkomma.

Begint een tekst met `=`, `+`, `-` of `@`, dan zet Huismus er een `'` voor.
Anders ziet een spreadsheet het als formule en voert die uit.

Een export kun je ook weer importeren, in een nieuwe Huismus: zie
[Importeren uit een ander pakket of Excel](importeren.nl.md).

Een export is geen back-up. Een back-up zet je terug in Huismus; een export
is om je gegevens ergens anders te gebruiken. Hoe back-ups werken, lees je
bij [Back-ups](back-ups.nl.md).
