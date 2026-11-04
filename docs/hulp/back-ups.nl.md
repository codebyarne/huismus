# Back-ups

Huismus maakt elke dag een back-up van je administratie, op elke plek die je
aanzet: een map, Dropbox of WebDAV. Een back-up is één bestand met je
facturen, offertes, klanten, uitgaven, bonnetjes en logo. Je
mailwachtwoord en de sleutel voor AI-assistenten gaan er bewust niet in mee.

Je vindt alles onder **Instellingen → Back-ups**. Daar staan de drie plekken
onder elkaar, met bij elke plek of hij aan staat en wanneer de laatste
back-up was. Met **Nu back-up maken** maak je er meteen een, op elke plek
die aan staat.

## Een map kiezen

Open **Instellingen → Back-ups** en kies bij **Map** voor **Instellen**. Je
kiest één keer een map, daarna gaat het vanzelf:

- **Wanneer:** meteen na het kiezen, en daarna elke dag. In de desktop-app
  alleen op dagen dat Huismus open staat, op een server altijd.
- **Hoeveel:** Huismus bewaart alles van de laatste 30 dagen, daarvoor één
  per maand, en altijd de nieuwste. Hij ruimt alleen zijn eigen back-ups op
  (`huismus-backup-<datum>-<tijd>.tar.gz`). De rest van de map laat hij
  staan.
- **Als het misgaat:** op het overzicht staat een rode melding als de
  laatste back-up mislukte, bijvoorbeeld omdat de map vol of niet bereikbaar
  was. Een oranje melding zegt dat je nog geen map hebt, of dat er al 7
  dagen geen back-up was.

In de desktop-app stelt Huismus de mappen van iCloud Drive, Google Drive,
OneDrive en Dropbox voor. Je kunt ook **Andere map…** kiezen, bijvoorbeeld
een USB-stick.

Draait Huismus op een server, zoals een Raspberry Pi of een NAS? Dan moet je
de map eerst aan Huismus koppelen. Hoe dat gaat, lees je onder
[Een map koppelen](#een-map-koppelen).

Kies een map op een ander apparaat of in de cloud. Een back-up op dezelfde
schijf als Huismus helpt niet als die schijf kapotgaat.

## In de cloud: Dropbox of WebDAV

Huismus kan ook elke dag een back-up rechtstreeks naar de cloud sturen,
naast de map of in plaats daarvan. Dat is vooral handig op een Raspberry Pi
of NAS: daar staat geen Dropbox-app die een map voor je naar de cloud
kopieert.

Open **Instellingen → Back-ups** en kies:

- **Dropbox:** kies **Koppelen**, open Dropbox, log in en kies
  **Toestaan**. Dropbox laat dan een code zien. Die plak je in Huismus.
  Huismus kan alleen bij zijn eigen map in je Dropbox: **Apps › Huismus**.
- **WebDAV:** kies **Instellen**. Dit werkt met Nextcloud, kDrive, Koofr,
  Hetzner Storage Box, pCloud en andere opslag die WebDAV kent. Je vult
  drie dingen in: het adres (dat begint met `https://` en staat in de
  instellingen van je opslag, vaak onder WebDAV), je gebruikersnaam en een
  app-wachtwoord dat je daar apart voor Huismus maakt. Huismus zet de
  back-ups in een map `Huismus`.

Je gebruikt één cloud tegelijk. Na het koppelen krijg je een herstelcode
(zie hieronder). Zodra je hebt aangegeven dat je die bewaard hebt, gaat de
eerste back-up naar de cloud. Dat gebeurt op de achtergrond, dus je kunt
gewoon verder. Zolang hij bezig is, staat er **Bezig met een back-up…**.

Daarna gaat het net als bij de map: elke dag een back-up, de laatste 30
dagen bewaard en daarvoor één per maand. Lukt een back-up niet, dan staat
er **Mislukt** bij de dienst en zie je een rode melding op het overzicht.
Onder **Beheren** zie je je herstelcode, stel je de dienst opnieuw in of
ontkoppel je hem. Ontkoppelen laat de back-ups in de cloud gewoon staan.

### Je herstelcode

Huismus versleutelt elke back-up voordat hij naar de cloud gaat. Daarvoor
gebruikt hij een herstelcode van 24 letters en cijfers. Je ziet die code
bij het eerste koppelen, en de back-ups gaan pas naar de cloud als je zegt
dat je hem bewaard hebt.

Bewaar de code in je wachtwoordmanager, of print hem. Zonder de code kun je
een back-up uit de cloud niet terugzetten op een andere computer. Zolang
deze installatie draait, vind je hem onder **Beheren → Herstelcode
bekijken**. De code zelf gaat niet mee in een back-up.

Op een nieuwe computer koppel je dezelfde cloud en kies je **Heb je al een
herstelcode van een eerdere installatie?**. Daarna staan de back-ups uit de
cloud bij **Een back-up terugzetten…**.

Een back-up in de cloud (`huismus-backup-<datum>-<tijd>.tar.gz.age`) is
versleuteld in het open formaat [age](https://age-encryption.org). Je kunt
hem dus ook zonder Huismus openen, met het programma `age` en je
herstelcode als wachtwoord (de 24 tekens zonder spaties):
`age -d huismus-backup-….tar.gz.age > huismus-backup.tar.gz`.

## Een back-up terugzetten

Kies onder **Instellingen → Back-ups** voor **Een back-up terugzetten…**.
Kies een back-up uit de lijst, of een ander bestand, zoals een back-up van
een andere computer. Huismus maakt eerst nog een back-up van hoe het nu is,
en zet daarna terug. Zolang dat duurt, staat op elke pagina "Huismus zet een
back-up terug".

Daarna ben je in deze browser nog ingelogd. Op andere apparaten moet je
misschien opnieuw inloggen. Een back-up van een nieuwere versie van Huismus
kun je niet terugzetten; werk Huismus dan eerst bij.

Zet je terug op een andere computer, vul dan je mailwachtwoord opnieuw in en
koppel je AI-assistenten opnieuw. Die gaan niet mee in een back-up.

## Een map koppelen

Dit stuk is alleen voor wie Huismus in Docker draait, bijvoorbeeld op een
Raspberry Pi of een NAS. Gebruik je de desktop-app, dan kun je het
overslaan.

### Waarom

Huismus draait in Docker in een eigen afgeschermd hokje, een container. Hij
ziet daar niets van de schijven en mappen van je Pi of NAS. En wat hij in
dat hokje zelf opslaat, is weg zodra de container vervangen wordt, en dat
gebeurt bij elke update.

Een back-up moet dus in een map buiten de container staan. Daarvoor koppel
je een map: je geeft Huismus één map van je Pi of NAS, die hij binnen de
container ziet als `/backups`. Alles wat Huismus daarin zet, staat in het
echt in jouw map, en blijft daar ook na een update.

### Stap voor stap

1. **Kies een map** op je Pi of NAS, bijvoorbeeld op een USB-schijf of een
   gedeelde map van je NAS. Zie de voorbeelden hieronder.
2. **Geef Huismus die map.** Dat doe je bij het starten van de container,
   met `-v /pad/naar/je/backupmap:/backups` (zie de voorbeelden hieronder).
   Het deel vóór de dubbele punt is jouw map, het deel erna is de naam die
   Huismus ziet. Die laatste blijft altijd `/backups`.
3. **Laat Huismus erin schrijven.** In de container is Huismus de gebruiker
   `huismus`, niet de beheerder (root). Vraag zijn nummer op met
   `docker exec huismus id -u` en maak hem eigenaar van de map,
   bijvoorbeeld `sudo chown 999 /pad/naar/je/backupmap`;
   vervang 999 door het nummer van de vorige opdracht.
4. **Kies de map in Huismus.** Open **Instellingen → Back-ups → Map**.
   Huismus stelt de gekoppelde map vanzelf voor. Opslaan, en de eerste
   back-up staat er meteen in.

Kan Huismus niet in de map schrijven, dan zegt de pagina Back-ups dat de
map niet bereikbaar is. Kijk dan stap 3 nog eens na.

### Voorbeelden

Met `docker run`:

```
docker run -d --name huismus \
  -e ALLOWED_HOSTS=huismus.local \
  -v huismus-data:/app/data \
  -v /pad/naar/je/backupmap:/backups \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/codebyarne/huismus:0.1
```

Met Docker Compose:

```yaml
services:
  huismus:
    image: ghcr.io/codebyarne/huismus:0.1
    environment:
      ALLOWED_HOSTS: huismus.local
    volumes:
      - huismus-data:/app/data
      - /pad/naar/je/backupmap:/backups
    ports:
      - "127.0.0.1:8000:8000"
volumes:
  huismus-data:
```

Wat je invult voor `/pad/naar/je/backupmap`:

- **Synology of een andere NAS:** een gedeelde map, zoals
  `/volume1/backups/huismus`. Wil je de back-ups ook in de cloud? Laat de
  NAS die map dan kopiëren, bij Synology met Cloud Sync of Hyper Backup.
- **Raspberry Pi met een USB-stick:** de map waar de stick altijd
  verschijnt, zoals `/mnt/usb/huismus`. Zet de stick daarvoor in
  `/etc/fstab`, anders is hij na een herstart weg.
- **Een map op een andere computer in je netwerk:** maak die eerst
  bereikbaar op je Pi of NAS (met SMB of NFS), en gebruik dan dat pad.

## Test je back-ups

Een back-up die je nooit hebt teruggezet, is een aanname, geen garantie.
Zet er dus af en toe een terug op een andere plek, bijvoorbeeld in de
desktop-app op een andere computer, en kijk of je facturen er staan.
