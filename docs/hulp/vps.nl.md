# Op een VPS

Geen Raspberry Pi of NAS in huis, maar wil je Huismus wel op je telefoon,
tablet en laptop gebruiken? Dan kun je hem draaien op een VPS, een server
die je huurt bij een hostingbedrijf. Met Tailscale kunnen alleen jouw eigen
apparaten erbij.

## Wat je nodig hebt

- **Een VPS met Linux** waarop je Docker kunt installeren, bijvoorbeeld bij
  Hetzner of TransIP. Dat kost een paar euro per maand. De kleinste VPS is
  genoeg.
- **Een Tailscale-account.** Tailscale maakt een eigen netwerk van je
  apparaten, ook als ze ver uit elkaar staan. Voor eigen gebruik is het
  gratis.
- **Wat ervaring met de terminal.** Je logt in op de VPS met SSH en typt
  een paar commando's.

Een gewoon webhostingpakket, zoals voor een website met WordPress, werkt
niet. Daar kun je alleen bestanden neerzetten (met PHP of FTP), en Huismus
moet als eigen programma de hele tijd draaien.

## Wat je vooraf moet weten

- Je administratie staat op een computer van het hostingbedrijf, niet bij
  jou thuis.
- Huismus versleutelt je administratie op de VPS niet. Alleen de back-ups
  naar Dropbox of WebDAV zijn versleuteld.
- Wie bij de VPS kan, kan bij je administratie. Kies dus een bedrijf dat je
  vertrouwt, en bewaar je wachtwoord of sleutel van de VPS goed.
- De VPS zelf werk jij bij: Linux, Docker en Tailscale. Huismus bijwerken
  gaat zoals op de pagina [Huismus in Docker](docker.nl.md#bijwerken).

## Installeren

1. **Docker.** Installeer Docker op de VPS volgens de uitleg van Docker
   zelf, voor de Linux die op je VPS staat (meestal Ubuntu of Debian).

2. **Tailscale.** Installeer Tailscale op de VPS volgens de uitleg van
   Tailscale, en meld de VPS aan met:

   ```
   sudo tailscale up
   ```

   Geef de VPS in Tailscale de naam `huismus`. Zet in de beheeromgeving van
   Tailscale, bij DNS, **MagicDNS** en **HTTPS-certificaten** aan. De VPS
   krijgt dan een eigen adres, zoals `huismus.jouw-tailnet.ts.net`. Dat
   adres werkt alleen op apparaten waarop Tailscale aanstaat met jouw
   account.

3. **Huismus.** Zet dit in een bestand `compose.yaml`, in een map op de VPS.
   Vul bij `jouw-tailnet` het adres in dat Tailscale je gaf:

   ```yaml
   services:
     huismus:
       image: ghcr.io/codebyarne/huismus:0.1
       restart: unless-stopped
       environment:
         ALLOWED_HOSTS: huismus.jouw-tailnet.ts.net
         CSRF_TRUSTED_ORIGINS: https://huismus.jouw-tailnet.ts.net
         DJANGO_SUPERUSER_USERNAME: <gebruikersnaam>
         DJANGO_SUPERUSER_PASSWORD: <wachtwoord>
       volumes:
         - huismus-data:/app/data
       ports:
         - "127.0.0.1:8000:8000"
   volumes:
     huismus-data:
   ```

   Start Huismus in die map met:

   ```
   docker compose up -d
   ```

   `127.0.0.1:8000` houdt Huismus op de VPS zelf. Van buiten kan niemand
   erbij, ook niet als de firewall uit staat. Wat de andere regels doen,
   staat bij [Installeren](docker.nl.md#installeren) op de pagina over
   Docker.

4. **HTTPS via Tailscale.** Laat Tailscale Huismus doorgeven aan je eigen
   apparaten:

   ```
   sudo tailscale serve --bg 8000
   ```

   Met `tailscale serve status` zie je het adres.

5. **De firewall.** De poort op `127.0.0.1` is de bescherming. Een firewall
   is een tweede slot voor al het andere op de VPS. Met `ufw` (op Ubuntu en
   Debian) laat je alleen SSH en Tailscale binnen:

   ```
   sudo ufw allow OpenSSH
   sudo ufw allow in on tailscale0
   sudo ufw enable
   ```

   Heeft je hostingbedrijf ook een firewall in de beheeromgeving? Zet daar
   alleen SSH open.

6. **Openen.** Zet Tailscale aan op je telefoon, tablet of laptop en open
   `https://huismus.jouw-tailnet.ts.net`. Log in met de gebruikersnaam en
   het wachtwoord uit `compose.yaml`. Daarna mag je die twee regels
   weghalen. Op je telefoon zet je Huismus als app op je beginscherm:
   [Op je telefoon](telefoon.nl.md#huismus-als-app-installeren).

## Nooit open op internet

Huismus is gemaakt voor je eigen netwerk. Zet hem op een VPS dus niet open
voor iedereen. Dat gebeurt als je:

- `tailscale funnel` gebruikt in plaats van `tailscale serve`. Funnel zet
  Huismus op internet;
- de poort zonder `127.0.0.1` opgeeft (`8000:8000`);
- een reverse proxy (zoals nginx of Caddy) Huismus naar buiten laat
  doorgeven.

Een server die vanaf internet bereikbaar is, wordt de hele dag door
geprobeerd.

## Back-ups

Een back-up op dezelfde VPS helpt niet als de VPS kapotgaat of je het
abonnement opzegt. Laat Huismus daarom elke dag een versleutelde back-up
naar Dropbox of WebDAV sturen:
[In de cloud: Dropbox of WebDAV](back-ups.nl.md#in-de-cloud-dropbox-of-webdav).
