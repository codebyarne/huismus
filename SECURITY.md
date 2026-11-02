# Beveiliging

Huismus is een klein, door vrijwilligers onderhouden project. Er is geen
beveiligingsteam en geen garantie op een reactietermijn — wel de
toezegging dat een serieus gemeld probleem serieus wordt bekeken.

## Een kwetsbaarheid melden

**Meld een kwetsbaarheid niet via een publieke issue.** Gebruik in plaats
daarvan GitHub's privé-meldingsfunctie voor kwetsbaarheden: ga naar het
tabblad "Security" van deze repository en kies "Report a vulnerability".
Dat maakt een privégesprek met de maintainer aan, zichtbaar voor niemand
anders, totdat er samen besloten wordt iets openbaar te maken.

Beschrijf zo mogelijk:
- Wat de kwetsbaarheid is en waar (bestand/regel of URL/formulier).
- Stappen om het te reproduceren.
- Wat je verwacht dat er zou moeten gebeuren, en wat er in plaats
  daarvan gebeurt.

## Wat binnen scope valt

Huismus is bedoeld om binnen een LAN of VPN te draaien, niet rechtstreeks
op het open internet (zie README). Een kwetsbaarheid die alleen relevant
is als iemand die aanbeveling negeert, is nog steeds het melden waard —
verdedigen in de diepte blijft de bedoeling. Denk aan: authenticatie-
omzeiling, SQL-injectie, padtraversal (bijvoorbeeld via bestandsuploads
of het import-/backup-pad), XXE in de SVG-logo- of UBL-import, of een
manier om onveranderlijkheid van uitgegeven documenten te omzeilen.

## Ondersteunde versies

Alleen de nieuwste getagde release en de `main`-branch krijgen
beveiligingsupdates.

---

# Security (English)

Huismus is a small, volunteer-maintained project. There's no security
team and no guaranteed response time — but a genuine, well-described
report will be taken seriously.

## Reporting a vulnerability

**Do not report a vulnerability via a public issue.** Instead, use
GitHub's private vulnerability reporting: go to this repository's
"Security" tab and choose "Report a vulnerability." That opens a private
conversation with the maintainer, visible to no one else until you both
decide to disclose something publicly.

Where possible, describe:
- What the vulnerability is and where (file/line, or URL/form).
- Steps to reproduce it.
- What you expected to happen, versus what actually happens.

## What's in scope

Huismus is meant to run inside a LAN or VPN, not directly on the open
internet (see the README). A vulnerability that's only relevant if
someone ignores that recommendation is still worth reporting — defense
in depth is still the intent. Think: authentication bypass, SQL
injection, path traversal (e.g. via file uploads or the import/backup
path), XXE in the SVG logo or UBL import, or a way to bypass the
immutability of issued documents.

## Supported versions

Only the latest tagged release and the `main` branch receive security
updates.
