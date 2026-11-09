# Huismus

Huismus is boekhouding voor Nederlandse zzp'ers, met of zonder KOR. Je maakt
er offertes, facturen en creditnota's mee als pdf, en je legt je uitgaven vast
met het bonnetje erbij, ook vanuit een map die meesynchroniseert met je
telefoon. Reken je btw, dan zie je per kwartaal de bedragen voor je
btw-aangifte. Kom je van Moneybird, dan neem je al je jaren mee. Meer op
[huismus.arnekrijnsen.com](https://huismus.arnekrijnsen.com).

Huismus is een onafhankelijk project en hoort niet bij Moneybird.

Huismus draait bij jou: als app op je Mac of Windows-pc, of in één
Docker-container op een Raspberry Pi, een NAS of een andere server. Je
administratie staat op dat apparaat, in een SQLite-database.

## Even proberen

Zo zie je Huismus het snelst, met 9 jaar verzonnen administratie:

```
uv sync
./scripts/demo-server.sh
```

Open http://127.0.0.1:8790 en log in met `demo` / `demo-wachtwoord-123`.
Alles staat in een tijdelijke map. Stop je de server (Ctrl-C), dan is die
weg. Je hebt Python 3.12 of nieuwer, uv en Pango nodig (zie
[Ontwikkelen](#ontwikkelen)).

Heb je Huismus al geïnstalleerd? Kies dan op het lege overzicht **Probeer
met nepdata**. Je krijgt dezelfde 9 jaar verzonnen administratie, met een
melding op elke pagina. Met **Nepdata leegmaken** haal je de nepdata weer weg.
Zolang de nepdata erin staat, maakt Huismus geen back-ups.

## Installeren

### Op je Mac of Windows-pc

Download de desktop-app bij de
[releases](https://github.com/codebyarne/huismus/releases):
`Huismus-<versie>-macos.dmg` of `Huismus-<versie>-windows.exe`. Je hebt geen
Docker of server nodig. De app werkt op macOS 14 of nieuwer met een
Apple-chip, en op Windows 10 of nieuwer. De app is nog niet ondertekend, dus de eerste keer
waarschuwt je computer. Hoe je hem dan toch opent:
[de desktop-app](docs/hulp/desktop-app.nl.md).

### Met Docker

Op een Raspberry Pi, een NAS of een andere server gebruik je de image
`ghcr.io/codebyarne/huismus`, voor Intel/AMD en ARM. Het makkelijkst is
Docker Compose: het hele voorbeeld staat in
[Huismus in Docker](docs/hulp/docker.nl.md). Met `docker run`:

```
docker run -d --name huismus --restart unless-stopped \
  -e ALLOWED_HOSTS=huismus.local \
  -e DJANGO_SUPERUSER_USERNAME=<gebruikersnaam> \
  -e DJANGO_SUPERUSER_PASSWORD=<wachtwoord> \
  -v huismus-data:/app/data \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/codebyarne/huismus:0.1
```

Wat de regels doen:

- `ALLOWED_HOSTS` is de naam die je in de adresbalk typt. Huismus
  beantwoordt alleen die naam. Voor elke andere naam krijg je een kale "Bad
  Request (400)", zonder regel in de log. Met dit voorbeeld werkt
  `http://localhost:8000` dus niet.
- `-v huismus-data:/app/data` koppelt een map aan de container. Daar staat
  alles: de database en de bestanden die je uploadt, zoals bonnetjes en je
  logo. Zorg dat die map in je
  back-ups zit, of laat Huismus zelf back-ups maken
  ([back-ups](docs/hulp/back-ups.nl.md)).
- `127.0.0.1:` houdt poort 8000 op het apparaat zelf. Een reverse proxy op
  hetzelfde apparaat stuurt het verkeer door. Zo kan niemand anders op je
  netwerk de app over gewone HTTP bereiken en zich voordoen als die proxy.

Huismus is bedoeld voor je eigen netwerk of een VPN, zoals Tailscale, achter
een reverse proxy met HTTPS. Zet het niet rechtstreeks op internet. Via het
netwerk log je alleen over HTTPS in. De hele opzet met Tailscale staat in
[`docs/tailscale.md`](docs/tailscale.md). Na 10 mislukte inlogpogingen
binnen een kwartier weigert Huismus elke login tot dat kwartier voorbij is.

### Bijwerken in Docker

Huismus in Docker kijkt niet zelf of er een nieuwe versie is. Met Compose
werk je bij met:

```
docker compose pull
docker compose up -d
```

Je gegevens en back-ups blijven staan. Brengt de nieuwe versie wijzigingen
in de database mee, dan maakt Huismus bij het starten eerst een back-up.
Met `docker run`, naar een nieuwe versie en terug naar de vorige:
[Huismus in Docker](docs/hulp/docker.nl.md#bijwerken).

### Docker op je eigen computer

Om de container even te proberen, zonder reverse proxy:

```
docker run -d --name huismus \
  -e ALLOWED_HOSTS=localhost \
  -e DJANGO_SUPERUSER_USERNAME=<gebruikersnaam> \
  -e DJANGO_SUPERUSER_PASSWORD=<wachtwoord> \
  -v huismus-data:/app/data \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/codebyarne/huismus:0.1
```

Open http://localhost:8000. Browsers behandelen `localhost` als veilig, dus
hier log je ook zonder HTTPS in (getest in Chromium).

Nepdata erin zetten kan ook vanaf de opdrachtregel:

```
docker exec huismus python manage.py demo_data --yes
```

Dat vult een lege database met verzonnen klanten, facturen en uitgaven. Het
commando weigert als er al klanten of documenten zijn, dus gebruik het
alleen op een nieuwe installatie.

### Als app op je telefoon

Je kunt Huismus op het beginscherm van je telefoon of laptop zetten,
zonder app store. Dat werkt alleen over HTTPS. Hoe:
[Huismus op je telefoon](docs/hulp/telefoon.nl.md).

## Hulp bij het gebruik

De uitleg staat in de app onder **Hulp**, bij de versie die je draait, en
hier in [`docs/hulp/`](docs/hulp/):

- [Back-ups](docs/hulp/back-ups.nl.md), ook een map koppelen in Docker
- [Mailen](docs/hulp/mailen.nl.md), ook met een app-wachtwoord van Gmail
- [AI-assistenten](docs/hulp/ai-assistenten.nl.md)
- [De desktop-app](docs/hulp/desktop-app.nl.md)
- [Huismus in Docker](docs/hulp/docker.nl.md): installeren en bijwerken
- [Huismus op je telefoon](docs/hulp/telefoon.nl.md)

Wat er voor beheerders en ontwikkelaars in `docs/` staat:
[`docs/README.md`](docs/README.md).

## Ontwikkelen

Je hebt nodig: Python 3.12 of nieuwer, [uv](https://docs.astral.sh/uv/) en
Pango, voor de pdf's via WeasyPrint. Op macOS: `brew install pango`. Op
Debian of Ubuntu: `apt install libpango-1.0-0 libpangoft2-1.0-0`.

```
uv sync
SECRET_KEY=dev DEBUG=true uv run python manage.py migrate
uv run python manage.py createsuperuser
SECRET_KEY=dev DEBUG=true uv run python manage.py runserver
```

Een `SECRET_KEY` hoef je niet in te stellen. Zonder maakt Huismus er bij de
eerste start zelf een in `data/secret-key`. Alleen Huismus kan dat bestand
lezen, en het gaat niet mee in een back-up. Zet je er een in de omgeving,
dan wint die. Zet je een back-up terug op een andere computer, dan log je
daar opnieuw in. Je verliest geen gegevens.

De code van de app staat in `huismus/`. De rest van de hoofdmap is
gereedschap eromheen: tests, docs, de desktop-app, Docker en scripts. Hoe de
code in elkaar zit: [`docs/architectuur.md`](docs/architectuur.md). De
schermen zijn Django-templates met HTMX en één stylesheet, zonder
build-stap: [`docs/frontend.md`](docs/frontend.md), en het ontwerp staat in
[`docs/design/`](docs/design/). Het hele ontwerp staat in `SPEC.md`, de
regels voor het project in `CLAUDE.md`. De desktop-app bouwen:
[`docs/desktop.md`](docs/desktop.md). De Docker-image zelf bouwen:
`docker build -t huismus .`.

Tests en checks:

```
uv run playwright install chromium   # eenmalig, voor de browsertests
uv run pytest
./scripts/verify.sh                  # de poort: alles in één commando
```

De browsertests (`tests/e2e`) draaien lokaal in Chromium. CI draait ze ook
in WebKit (Safari) en Firefox. Lokaal kan dat zo:

```
uv run playwright install webkit firefox
uv run pytest tests/e2e --browser webkit --browser firefox
```

## Status

Huismus is in ontwikkeling. `SPEC.md` sectie 6 zegt welke mijlpalen er zijn,
de [releases](https://github.com/codebyarne/huismus/releases) wat er in elke
versie zit.

---

## Huismus (English)

Huismus makes your quotes, invoices and credit notes as PDFs and keeps track
of your expenses. It's for Dutch freelancers under the KOR scheme, or
charging VAT: then you choose 0, 9 or 21% per invoice line. Coming from
Moneybird? Bring your whole export along. Huismus is an independent project,
not affiliated with Moneybird.

Huismus runs on your own device: as an app on your Mac or Windows PC, or in
one Docker container on a Raspberry Pi, a NAS or another server. Your
records live on that device, in an SQLite database.

### Quick try

The fastest way to see Huismus, with 9 years of made-up records:

```
uv sync
./scripts/demo-server.sh
```

Open http://127.0.0.1:8790 and log in with `demo` / `demo-wachtwoord-123`.
Everything lives in a temporary folder that's gone once you stop the server
(Ctrl-C). You need Python 3.12 or newer, uv and Pango (see
[Development](#development)). The receipts folder works here too: under
**Settings → Receipts folder** choose any folder on your computer, and a
receipt you put in it shows up within seconds.

Already installed Huismus? Choose **Try with sample data** on the empty
overview. You get the same 9 years of made-up records, with a banner on
every page. **Clear sample data** removes it again. While the sample
data is in, Huismus makes no backups.

### Installing

#### On your Mac or Windows PC

Download the desktop app from the
[releases](https://github.com/codebyarne/huismus/releases):
`Huismus-<version>-macos.dmg` or `Huismus-<version>-windows.exe`. You don't
need Docker or a server. The app works on macOS 14 or newer with an Apple
chip, and on Windows 10 or newer. The app isn't signed yet, so your computer warns
you the first time. How to open it anyway:
[the desktop app](docs/hulp/desktop-app.en.md).

#### With Docker

On a Raspberry Pi, a NAS or another server, use the image
`ghcr.io/codebyarne/huismus`, for Intel/AMD and ARM. Docker Compose is the
easiest: the full example is in
[Huismus in Docker](docs/hulp/docker.en.md). With `docker run`, use the same
command as in the Dutch section above. What the lines do:

- `ALLOWED_HOSTS` is the name you type in the address bar. Huismus only
  answers to that name. Any other name gets a bare "Bad Request (400)",
  with nothing in the log. So with the example above,
  `http://localhost:8000` doesn't work.
- `-v huismus-data:/app/data` links a folder to the container. Everything
  lives there: the database and the files you upload, like receipts and
  your logo. Make sure that
  folder is in your backups, or let Huismus make its own
  ([backups](docs/hulp/back-ups.en.md)).
- `127.0.0.1:` keeps port 8000 on the device itself. A reverse proxy on the
  same device forwards the traffic. That way nobody else on your network can
  reach the app over plain HTTP and pose as that proxy.

Huismus is meant for your own network or a VPN, like Tailscale, behind a
reverse proxy with HTTPS. Don't put it straight on the internet. Over the
network, you can only log in over HTTPS. The full Tailscale setup is in
[`docs/tailscale.md`](docs/tailscale.md) (Dutch). After 10 failed logins
within a quarter of an hour, Huismus refuses every login until that quarter
has passed.

#### Updating in Docker

Huismus in Docker doesn't check for new versions by itself. With Compose,
you update with:

```
docker compose pull
docker compose up -d
```

Your data and backups stay where they are. When the new version brings
changes to the database, Huismus first makes a backup when it starts. With
`docker run`, moving to a new version and going back to the previous one:
[Huismus in Docker](docs/hulp/docker.en.md#updating).

#### Docker on your own computer

To try the container without a reverse proxy, use
`-e ALLOWED_HOSTS=localhost` and open http://localhost:8000. Browsers treat
`localhost` as secure, so you can log in there without HTTPS (tested in Chromium).

You can also add sample data from the command line:

```
docker exec huismus python manage.py demo_data --yes
```

That fills an empty database with made-up customers, invoices and expenses.
The command refuses if there are customers or documents already, so only
use it on a new install.

#### As an app on your phone

You can put Huismus on the home screen of your phone or laptop, without an
app store. That only works over HTTPS. How:
[Huismus on your phone](docs/hulp/telefoon.en.md).

### Help

The help is in the app under **Help**, for the version you run, and here in
[`docs/hulp/`](docs/hulp/):

- [Backups](docs/hulp/back-ups.en.md), including linking a folder in Docker
- [Mail](docs/hulp/mailen.en.md), including a Gmail app password
- [AI assistants](docs/hulp/ai-assistenten.en.md)
- [The desktop app](docs/hulp/desktop-app.en.md)
- [Huismus in Docker](docs/hulp/docker.en.md): installing and updating
- [Huismus on your phone](docs/hulp/telefoon.en.md)

What's in `docs/` for administrators and developers:
[`docs/README.md`](docs/README.md) (Dutch).

### Development

You need Python 3.12 or newer, [uv](https://docs.astral.sh/uv/) and Pango,
for the PDFs via WeasyPrint. On macOS: `brew install pango`. On Debian or
Ubuntu: `apt install libpango-1.0-0 libpangoft2-1.0-0`. Then run the same
commands as in the Dutch section above.

You don't need to set a `SECRET_KEY`. Without one, Huismus makes its own on
first start, in `data/secret-key`. Only Huismus can read that file, and it
stays out of backups. One set in the environment wins. Restore a backup on
another computer and you log in again there. You don't lose any data.

The app's code lives in `huismus/`. The rest of the top folder is tooling
around it: tests, docs, the desktop app, Docker and scripts. How the code
fits together: [`docs/architectuur.md`](docs/architectuur.md). The screens
are Django templates with HTMX and a single stylesheet, with no build step:
[`docs/frontend.md`](docs/frontend.md), and the design is in
[`docs/design/`](docs/design/). The full design is in `SPEC.md`, the project
rules in `CLAUDE.md`. Building the desktop app:
[`docs/desktop.md`](docs/desktop.md). These docs are in Dutch. Building the
Docker image yourself: `docker build -t huismus .`.

Tests and checks:

```
uv run playwright install chromium   # once, for the browser tests
uv run pytest
./scripts/verify.sh                  # the gate: everything in one command
```

The browser tests (`tests/e2e`) run in Chromium locally. CI also runs them
in WebKit (Safari) and Firefox:
`uv run pytest tests/e2e --browser webkit --browser firefox`, after
`uv run playwright install webkit firefox`.

### Status

Huismus is in development. `SPEC.md` section 6 lists the milestones, the
[releases](https://github.com/codebyarne/huismus/releases) what's in each
version.
