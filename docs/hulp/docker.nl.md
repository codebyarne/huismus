# Huismus in Docker

Draai je Huismus op een Raspberry Pi, een NAS of een eigen server? Dan
gebruik je de Docker-image. Hier lees je hoe je hem installeert, waar je
gegevens staan en hoe je bijwerkt naar een nieuwe versie.

Geen server in huis? Dan kan Huismus ook op een server die je huurt:
[Op een VPS](vps.nl.md).

## Installeren

Zet dit in een bestand `compose.yaml`, in een map op je Pi of NAS:

```yaml
services:
  huismus:
    image: ghcr.io/codebyarne/huismus:0.1
    restart: unless-stopped
    environment:
      ALLOWED_HOSTS: huismus.local
      DJANGO_SUPERUSER_USERNAME: <gebruikersnaam>
      DJANGO_SUPERUSER_PASSWORD: <wachtwoord>
    volumes:
      - huismus-data:/app/data
      - /pad/naar/je/backupmap:/backups
    ports:
      - "127.0.0.1:8000:8000"
volumes:
  huismus-data:
```

Start Huismus in die map met:

```
docker compose up -d
```

Wat de regels doen:

- `image` is de versie die je draait. Met `0.1` krijg je bij het bijwerken
  de verbeteringen van versie 0.1. Een nieuwe versie, zoals 0.2, kies je
  zelf (zie [Bijwerken](#bijwerken)).
- `ALLOWED_HOSTS` is de naam die je in de adresbalk typt. Huismus
  beantwoordt alleen die naam.
- `DJANGO_SUPERUSER_…` maakt bij de eerste start je account om in te
  loggen. Daarna mag je deze regels weghalen.
- `huismus-data:/app/data` is waar je administratie staat (zie
  [Waar je gegevens staan](#waar-je-gegevens-staan)).
- `/pad/naar/je/backupmap:/backups` is de map voor je back-ups. Hoe je die
  kiest en klaarzet: [Een map koppelen](back-ups.nl.md#een-map-koppelen).
- `127.0.0.1:8000` houdt Huismus op het apparaat zelf. Een reverse proxy
  met HTTPS stuurt het verkeer door. Zet Huismus niet rechtstreeks op
  internet.

Liever zonder Compose? Dit doet hetzelfde:

```
docker run -d --name huismus --restart unless-stopped \
  -e ALLOWED_HOSTS=huismus.local \
  -e DJANGO_SUPERUSER_USERNAME=<gebruikersnaam> \
  -e DJANGO_SUPERUSER_PASSWORD=<wachtwoord> \
  -v huismus-data:/app/data \
  -v /pad/naar/je/backupmap:/backups \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/codebyarne/huismus:0.1
```

## Waar je gegevens staan

Alles van je administratie staat in `huismus-data`: de database, je
bonnetjes en je logo. De container zelf bewaart niets. Je kunt hem dus
gewoon weggooien en opnieuw starten, zolang je dezelfde `huismus-data` en
dezelfde back-upmap meegeeft. Dat is precies wat er bij bijwerken gebeurt.

## Bijwerken

Huismus kijkt elke dag of er een nieuwe versie is en zegt het dan op het
overzicht. Wil je niet wachten, kies dan **Nu zoeken** bij
**Instellingen → Updates**. Bijwerken doe je zelf, wanneer jij wilt:

```
docker compose pull
docker compose up -d
```

Compose haalt de nieuwste image van je versie op en vervangt de container.
Je gegevens en back-ups blijven staan.

Naar een nieuwe versie, zoals van 0.1 naar 0.2? Verander de regel `image`
in `compose.yaml` in `ghcr.io/codebyarne/huismus:0.2` en doe dan hetzelfde.

Met `docker run` haal je eerst de nieuwe image op, en vervang je daarna de
container met dezelfde `-v`-regels:

```
docker pull ghcr.io/codebyarne/huismus:0.1
docker stop huismus
docker rm huismus
docker run -d --name huismus … ghcr.io/codebyarne/huismus:0.1
```

Geen melding willen? Zet bij **Instellingen → Updates** het zoeken naar
nieuwe versies uit. Huismus kijkt dan niet meer op GitHub.

### Wat Huismus doet bij een nieuwe versie

Brengt een nieuwe versie wijzigingen in de database mee, dan maakt Huismus
bij het starten eerst een back-up. Die komt in de map die je bij
**Instellingen → Back-ups** koos, en anders in `backups` in `huismus-data`.
Daarna past Huismus de database aan en start hij.

Lukt die back-up niet, bijvoorbeeld omdat de map vol of niet bereikbaar
is? Dan verandert Huismus niets aan je administratie en start hij niet.
Maak ruimte of koppel de map opnieuw, en start Huismus opnieuw. Of ga terug
naar de vorige versie.

## Als Huismus niet start

Kijk eerst in het logboek van de container:

```
docker logs huismus
```

Met Compose: `docker compose logs huismus`. Daar staat wat er misging, en
bij een update ook waar de back-up van vooraf staat.

## Terug naar de vorige versie

Ging er iets mis na het bijwerken, ga dan terug naar de versie die je
daarvoor had, met het hele versienummer. In het logboek staat naar welke
versie Huismus werd bijgewerkt, bijvoorbeeld 0.1.2. De vorige is dan 0.1.1.

1. Zet in `compose.yaml` de oude versie: `ghcr.io/codebyarne/huismus:0.1.1`.
2. Zet de back-up van vóór het bijwerken terug. In het logboek staat welke
   het is. Zo ziet dat eruit, met de naam uit het logboek:

   ```
   docker compose run --rm --entrypoint python huismus manage.py restore /backups/huismus-backup-<datum>-<tijd>.tar.gz --yes
   ```

   Stond de back-up in `huismus-data`, dan begint het pad met
   `/app/data/backups/` in plaats van `/backups/`.
3. Start Huismus: `docker compose up -d`.

Start Huismus wel, dan kan het ook in de app: **Instellingen → Back-ups →
Een back-up terugzetten…**.
