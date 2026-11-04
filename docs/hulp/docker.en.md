# Huismus in Docker

Running Huismus on a Raspberry Pi, a NAS or your own server? Then you use
the Docker image. This page covers installing it, where your data lives and
how to update to a new version.

## Installing

Put this in a file called `compose.yaml`, in a folder on your Pi or NAS:

```yaml
services:
  huismus:
    image: ghcr.io/codebyarne/huismus:0.1
    restart: unless-stopped
    environment:
      ALLOWED_HOSTS: huismus.local
      DJANGO_SUPERUSER_USERNAME: <username>
      DJANGO_SUPERUSER_PASSWORD: <password>
    volumes:
      - huismus-data:/app/data
      - /path/to/your/backup/folder:/backups
    ports:
      - "127.0.0.1:8000:8000"
volumes:
  huismus-data:
```

Start Huismus from that folder with:

```
docker compose up -d
```

What the lines do:

- `image` is the version you run. With `0.1`, updating gets you the fixes
  for version 0.1. You pick a new version, like 0.2, yourself (see
  [Updating](#updating)).
- `ALLOWED_HOSTS` is the name you type in the address bar. Huismus answers
  only to that name.
- `DJANGO_SUPERUSER_…` creates your login account on the first start. You
  can remove these lines after that.
- `huismus-data:/app/data` is where your administration lives (see
  [Where your data lives](#where-your-data-lives)).
- `/path/to/your/backup/folder:/backups` is the folder for your backups.
  How to pick and prepare it: [Linking a folder](back-ups.en.md#linking-a-folder).
- `127.0.0.1:8000` keeps Huismus on the device itself. A reverse proxy with
  HTTPS forwards the traffic. Don't put Huismus straight on the internet.

Rather not use Compose? This does the same:

```
docker run -d --name huismus --restart unless-stopped \
  -e ALLOWED_HOSTS=huismus.local \
  -e DJANGO_SUPERUSER_USERNAME=<username> \
  -e DJANGO_SUPERUSER_PASSWORD=<password> \
  -v huismus-data:/app/data \
  -v /path/to/your/backup/folder:/backups \
  -p 127.0.0.1:8000:8000 \
  ghcr.io/codebyarne/huismus:0.1
```

## Where your data lives

Everything in your administration is in `huismus-data`: the database, your
receipts and your logo. The container itself keeps nothing. So you can
throw it away and start a new one, as long as you give it the same
`huismus-data` and the same backup folder. That's exactly what happens when
you update.

## Updating

Huismus checks once a day for a new version and tells you on the
overview. You update it yourself, whenever you like:

```
docker compose pull
docker compose up -d
```

Compose fetches the newest image of your version and replaces the
container. Your data and backups stay where they are.

Moving to a new version, like from 0.1 to 0.2? Change the `image` line in
`compose.yaml` to `ghcr.io/codebyarne/huismus:0.2` and do the same.

With `docker run`, first pull the new image, then replace the container
with the same `-v` lines:

```
docker pull ghcr.io/codebyarne/huismus:0.1
docker stop huismus
docker rm huismus
docker run -d --name huismus … ghcr.io/codebyarne/huismus:0.1
```

Don't want the notice? Turn off looking for new versions in
**Settings → Updates**. Huismus then stops checking GitHub.

### What Huismus does with a new version

When a new version brings changes to the database, Huismus first makes a
backup when it starts. It goes to the folder you chose under **Settings →
Backups**, or otherwise to `backups` in `huismus-data`. Then Huismus
updates the database and starts.

If that backup fails, for example because the folder is full or can't be
reached, Huismus changes nothing in your administration and doesn't start.
Free up space or link the folder again, and start Huismus again. Or go back
to the previous version.

## If Huismus doesn't start

Look at the container's log first:

```
docker logs huismus
```

With Compose: `docker compose logs huismus`. It says what went wrong, and
after an update also where the backup from before it is.

## Going back to the previous version

If something went wrong after updating, go back to the version you had
before, with its full version number. The log says which version Huismus
was updated to, for example 0.1.2. The previous one is then 0.1.1.

1. Set the old version in `compose.yaml`: `ghcr.io/codebyarne/huismus:0.1.1`.
2. Restore the backup from before the update. The log says which one it
   is. It looks like this, with the name from the log:

   ```
   docker compose run --rm --entrypoint python huismus manage.py restore /backups/huismus-backup-<date>-<time>.tar.gz --yes
   ```

   If the backup was in `huismus-data`, the path starts with
   `/app/data/backups/` instead of `/backups/`.
3. Start Huismus: `docker compose up -d`.

If Huismus does start, you can also do it in the app: **Settings → Backups
→ Restore a backup…**.
