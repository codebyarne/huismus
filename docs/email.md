# Mailen vanuit Huismus

Huismus mailt een uitgegeven factuur, een uitgegeven creditnota en een
verzonden offerte via SMTP, met de PDF als bijlage (SPEC.md M10). De uitleg
voor gebruikers (Gmail, eigen domein, standaardteksten, foutmeldingen) staat
in [`docs/hulp/mailen.nl.md`](hulp/mailen.nl.md), en in de app onder Hulp.
Hier alleen wat een ontwikkelaar of beheerder extra wil weten.

## Het wachtwoord

Huismus bewaart het SMTP-wachtwoord niet in de database maar in een los
bestand, `data/smtp-password`, dat alleen Huismus kan lezen
(`huismus/business/smtp.py`). Dat bestand gaat bewust niet mee in een back-up
(`docs/backups.md`): back-ups gaan van de Pi af, en met het wachtwoord erin
zou elke kopie toegang tot de mailbox geven.

## Tests en demo

De tests gebruiken Django's locmem-backend: elke mail komt in een lijst in
het geheugen terecht, er gaat nooit iets het net op. `scripts/demo-server.sh`
gebruikt de console-backend: daar kun je mailen, maar elke mail wordt
alleen in de terminal getoond.
