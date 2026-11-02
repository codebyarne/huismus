# Deployen naar de Raspberry Pi

Hoe de installatie van de maintainer automatisch bijwerkt: een push naar
`main` op GitHub → CI draait → alleen als CI groen is, bouwt de Pi precies
die commit en vervangt de container. Een push die alleen documentatie
wijzigt (`.md`-bestanden, `docs/`) start geen CI en dus ook geen deploy. Voor een eigen installatie zonder
automatische updates volstaat de README (`docker run`) en
`docs/tailscale.md`.

```
push naar main ─▶ GitHub CI ─▶ groen? ─▶ webhook (workflow_run)
                                            │  Tailscale Funnel-pad
                                            ▼
                               Pi: deploy/webhook.py (127.0.0.1:9002)
                                            │
                                            ▼
                               deploy/deploy.sh <commit>
                               build · backup · container vervangen · check
```

## Wat waar staat op de Pi

| Wat | Waar |
|---|---|
| Repo (clone van `main`) | `~/huismus` |
| App-instellingen (`SECRET_KEY`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`) | `~/huismus/.env` |
| Webhook-secret (`WEBHOOK_SECRET`), en voor meldingen `GITHUB_STATUS_TOKEN` en `NTFY_URL` | `~/huismus/.env.webhook` |
| Data (database, bonnetjes, logo) | Docker-volume `huismus-data` |
| Backups van vlak vóór elke deploy (laatste 10) | `~/huismus-backups/voor-deploy/` |
| Container | `huismus`, op `127.0.0.1:8000` |
| Webhook | PM2-proces `huismus-webhook`, `127.0.0.1:9002` |
| Huismus zelf | `https://<pi>.<tailnet>.ts.net:9443`, alleen binnen je tailnet |
| Webhook-pad van buitenaf | `https://<pi>.<tailnet>.ts.net/deploy-huismus`, via Funnel |

`.env` en `.env.webhook` vallen onder `.gitignore` en `.dockerignore`: ze
komen niet in git en niet in het image. Zet geheimen altijd op de Pi zelf,
nooit via een chatgesprek.

## Wat een deploy doet

`deploy/deploy.sh <commit>`, aangeroepen door de webhook:

1. `main` gaat fast-forward naar precies de commit die CI heeft getest (een
   oudere dan wat al draait wordt overgeslagen).
2. Het image `huismus:<commit>` wordt gebouwd; de oude container blijft
   intussen gewoon draaien.
3. Een backup van de draaiende data (`manage.py backup`) wordt uit de
   container gekopieerd naar `~/huismus-backups/voor-deploy/`.
4. De container wordt vervangen; bij het starten draaien de migraties.
5. Antwoordt de loginpagina niet binnen een minuut, dan start het vorige
   image weer. Migraties van de mislukte versie kunnen dan al gedraaid
   hebben; de backup van stap 3 is het vangnet.

Eén deploy tegelijk (`flock`); een tweede wacht op zijn beurt.

## Meldingen: wanneer staat het live?

`deploy/notify.sh` vertelt hoe een deploy ging, aan wat er in
`.env.webhook` is ingesteld. Beide zijn optioneel; zonder instelling wordt
er niets verstuurd. Lukt een melding niet, dan staat dat in het log, maar de
deploy zelf slaagt of faalt daar nooit door.

| Instelling | Wat je krijgt |
|---|---|
| `GITHUB_STATUS_TOKEN` | Op GitHub, bij de commit: een status `deploy/pi` met "bezig", "gelukt" of "mislukt". Ook Claude kan die lezen en melden wanneer een merge live staat. |
| `NTFY_URL` | Een pushbericht op je telefoon (app [ntfy](https://ntfy.sh)) als de deploy klaar is: "Huismus staat live" of, met hoge prioriteit, "Huismus-deploy mislukt". |

Ook een deploy die halverwege stopt (bijvoorbeeld een kapotte build) wordt
als mislukt gemeld. Een commit die ouder is dan wat er al draait, wordt
overgeslagen zonder melding.

**GitHub-token.** GitHub → Settings → Developer settings → Fine-grained
tokens → Generate new token. Repository access: alleen `huismus`.
Permissions: alleen **Commit statuses: Read and write**. Zet een vervaldatum
en vernieuw hem op tijd; een verlopen token geeft alleen een regel "melding
naar GitHub niet verstuurd" in het log.

**ntfy.** Installeer de ntfy-app en abonneer je op een onderwerp met een
lange, willekeurige naam, bijvoorbeeld uit `openssl rand -hex 12`. Op
`ntfy.sh` kan iedereen die de naam kent meelezen; het bericht bevat alleen
de commit en de uitkomst, geen administratie.

Op de Pi, in `~/huismus` (de waarden typ je daar zelf, niet in een chat):

```
echo "GITHUB_STATUS_TOKEN=<token>" >> .env.webhook
echo "NTFY_URL=https://ntfy.sh/<jouw-onderwerp>" >> .env.webhook
```

`deploy.sh` leest ze bij elke deploy opnieuw; de webhook hoeft niet opnieuw
te starten.

Testen zonder deploy: `deploy/notify.sh "$(git rev-parse HEAD)" success "Testbericht"`
(dit zet ook echt de status `deploy/pi` op die commit).

De backups van stap 3 staan op dezelfde SD-kaart. Ze beschermen tegen een
mislukte deploy, niet tegen een kapotte kaart. De dagelijkse back-up stel
je in de app in (Instellingen → Back-ups), met een map op een ander
apparaat die je op `/backups` koppelt: zie `docs/backups.md`.

## Eenmalige setup

Op de Pi (Docker, Tailscale en PM2 zijn er al voor de andere projecten):

```
git clone git@github.com:codebyarne/huismus.git ~/huismus
cd ~/huismus

# App-instellingen
cat > .env <<EOF
SECRET_KEY=$(openssl rand -base64 48)
ALLOWED_HOSTS=<pi>.<tailnet>.ts.net
CSRF_TRUSTED_ORIGINS=https://<pi>.<tailnet>.ts.net:9443
EOF
echo "WEBHOOK_SECRET=$(openssl rand -hex 32)" > .env.webhook
chmod 600 .env .env.webhook

# Eerste deploy met de hand, daarna het inlogaccount
deploy/deploy.sh "$(git rev-parse HEAD)"
docker exec -it huismus python manage.py createsuperuser

# Huismus in je tailnet (geen Funnel!), en het webhook-pad publiek
tailscale serve --bg --https=9443 http://127.0.0.1:8000
tailscale funnel --bg --set-path=/deploy-huismus http://127.0.0.1:9002

# Webhook onder PM2
pm2 start deploy/webhook.py --name huismus-webhook --interpreter python3
pm2 save
```

De `SECRET_KEY` in `.env` mag ook weg: zonder maakt Huismus er zelf een in
`data/secret-key`. Haal je hem later weg (of laat je hem leeg), dan krijgt
Huismus een andere sleutel en moet je opnieuw inloggen; gegevens gaan er niet
door verloren.

Controleer met `tailscale serve status --json` dat poort 9443 **niet** onder
`AllowFunnel` staat: Huismus hoort niet op het internet.

Op GitHub: repo → Settings → Webhooks → Add webhook:

- Payload URL: `https://<pi>.<tailnet>.ts.net/deploy-huismus`
- Content type: `application/json`
- Secret: de waarde van `WEBHOOK_SECRET`
- Events: alleen **Workflow runs**

## Beheer

```
pm2 logs huismus-webhook          # webhook én deploy-uitvoer
docker logs -f huismus            # de app zelf
deploy/deploy.sh <commit>         # een deploy met de hand
docker images huismus             # het huidige en het vorige image
```

Terug naar een eerdere versie: `deploy/deploy.sh` accepteert alleen commits
die niet ouder zijn dan wat er draait. Start voor een terugval het vorige
image met de hand (`docker images huismus` toont het), en herstel zo nodig
een backup (`docs/backups.md`).

## Problemen oplossen

**"Kan geen verbinding maken met de server" op een apparaat in het tailnet.**
Door de Funnel voor het webhook-pad bestaat `<pi>.<tailnet>.ts.net` ook in
publieke DNS, en daar verwijst de naam naar de Funnel-servers van Tailscale.
Die antwoorden niet op poort 9443. Zoekt een apparaat de naam buiten Tailscale
om op, dan krijgt het deze fout, ook al is de Tailscale-verbinding in orde.
Test: laadt `http://<tailscale-ip-van-de-pi>:9443` wel, dan ligt het aan DNS.

- iPhone/Mac: zet iCloud Privé-relay uit, of alleen voor dat netwerk via
  "Beperk IP-adrestracking". Privé-relay regelt DNS voor Safari zelf.
- Zet "Use Tailscale DNS" aan in de Tailscale-app.
- Kijk of een DNS-profiel of -app (NextDNS, AdGuard) Tailscale DNS overschrijft.

Gebruik het IP-adres niet als vaste oplossing: het certificaat,
`ALLOWED_HOSTS` en `CSRF_TRUSTED_ORIGINS` horen bij de naam.
