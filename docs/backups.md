# Backups

Hoe Huismus back-ups maakt en terugzet, op elke installatie: de desktop-app,
een Raspberry Pi, een NAS of een andere server met Docker (`SPEC.md` M11 en
M15). De uitleg voor gebruikers (een map kiezen, terugzetten, een map
koppelen in Docker) staat in [`docs/hulp/back-ups.nl.md`](hulp/back-ups.nl.md),
en in de app onder Hulp. Hier staat wat je als ontwikkelaar of beheerder
nog meer wilt weten.

**Dit is geen vervanging voor je eigen boekhoudkundige verplichtingen.**
Het beschrijft alleen hoe je de technische data (database, bonnetjes,
logo) veilig bewaart.

## Hoe het werkt

Een back-up is één `.tar.gz` met een veilige kopie van de database en alles
wat verder in `data/` staat (bonnetjes, logo), zonder het mailwachtwoord
(`docs/email.md`), de sleutel voor AI-assistenten, de geheime sleutel en de
koppeling met een clouddienst en de herstelcode (`data/cloud-backup*`).
Wanneer en hoeveel: `huismus/core/auto_backups.py`; maken en terugzetten:
`huismus/core/backup.py`; de pagina's: `huismus/core/backup_views.py`. Op Docker weigert
Huismus een map die niet aan de container gekoppeld is (`/proc/self/mountinfo`).

Voor een update: de desktop-app maakt een back-up voordat hij een nieuwe
versie installeert (`huismus/core/updates.py`). Docker draait bij elke start
`manage.py migrate_with_backup` (`docker/entrypoint.sh`): staan er migraties
klaar op een bestaande administratie, dan eerst dezelfde back-up
(`auto_backups.safety_backup`), en lukt die niet, dan migreert hij niet en
stopt de container. Het pad staat in de log. Gebruikers: `docs/hulp/docker.nl.md`.

Naar Dropbox of WebDAV (`SPEC.md` M15 stap 2): `huismus/core/cloud_backups.py` maakt
elke dag een eigen archief, versleutelt het met de herstelcode in het open
formaat age (`pyrage`) en uploadt het als `….tar.gz.age`; de schermen staan
in `huismus/core/cloud_views.py`. Het archief gaat in z'n geheel door het geheugen
(een paar keer de grootte van de back-up). Openen zonder Huismus:
`age -d bestand.tar.gz.age > bestand.tar.gz`, met de herstelcode zonder
spaties als wachtwoord. Uitleg voor gebruikers: `docs/hulp/back-ups.nl.md`.

## Met de hand

Zonder de app kan het ook, met hetzelfde soort archief:

```
docker exec huismus python manage.py backup /app/data/backups
docker cp huismus:/app/data/backups ./huismus-backups
```

`manage.py backup` gebruikt SQLite's eigen online-backup-API: een gewone
kopie van de databasebestanden is niet veilig terwijl Huismus draait (de
database staat in WAL-modus, `huismus/core/sqlite.py`). `data/backups` gaat zelf
nooit mee in een back-up.

Terugzetten met de hand **overschrijft alle huidige data**. Stop de
container eerst, of zorg in elk geval dat niets tegelijk in de database
schrijft:

```
docker exec huismus python manage.py restore /app/data/backups/huismus-backup-20260926-131018.tar.gz --yes
```

Zonder `--yes` weigert het commando. Terugzetten is een overlay: een bestand
in `data/` dat niet in het archief zit, blijft staan. De database zelf wordt
altijd helemaal vervangen.

---

# Backups (English)

How Huismus makes and restores backups. For users:
[`docs/hulp/back-ups.en.md`](hulp/back-ups.en.md), and in the app under
Help. **This is not a substitute for your own bookkeeping obligations.**

## By hand

```
docker exec huismus python manage.py backup /app/data/backups
docker cp huismus:/app/data/backups ./huismus-backups
docker exec huismus python manage.py restore /app/data/backups/<archive>.tar.gz --yes
```

`manage.py backup` uses SQLite's online backup API, which is safe against
a live database in WAL mode; a plain file copy is not. Restoring by hand
overwrites all current data (stop the container first) and refuses without
`--yes`. It is an overlay: files in `data/` that aren't in the archive stay.

