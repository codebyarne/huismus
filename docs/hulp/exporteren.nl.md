# Exporteren

Wil je je administratie buiten Huismus gebruiken, bijvoorbeeld voor je
boekhouder of in een spreadsheet? Download dan een export: één ZIP met je
facturen, offertes, klanten en uitgaven als CSV, en de pdf's en bonnetjes
erbij. Die kun je openen zonder Huismus.

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
- **uitgaven.csv** en **uitgaveregels.csv**: je uitgaven, en per regel de
  categorie.
- **pdf/facturen**, **pdf/creditnotas** en **pdf/offertes**: elke pdf, met
  het nummer als naam. Het is dezelfde pdf als die je met **Downloaden**
  krijgt. Voor een factuur uit Moneybird is dat de originele pdf.
- **bonnetjes**: elk bonnetje, met het nummer van de uitgave ervoor.

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

## Openen in een spreadsheet

De CSV's gebruiken een puntkomma tussen de kolommen en een komma in
bedragen ("1234,56"), zonder punt voor de duizendtallen. Datums staan als
2026-11-02. Excel en Numbers in het Nederlands openen ze meteen goed. Een
Engelse spreadsheet vraagt soms welk scheidingsteken je wilt: kies dan de
puntkomma.

Een export is geen back-up. Een back-up zet je terug in Huismus; een export
is om je gegevens ergens anders te gebruiken. Hoe back-ups werken, lees je
bij [Back-ups](back-ups.nl.md).
