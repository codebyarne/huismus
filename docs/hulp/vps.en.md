# On a VPS

No Raspberry Pi or NAS at home, but you'd still like to use Huismus on
your phone, tablet and laptop? Then you can run it on a VPS, a server you
rent from a hosting company. With Tailscale, only your own devices can
reach it.

## What you need

- **A VPS with Linux** that you can install Docker on, for example at
  Hetzner or TransIP. It costs a few euros a month. The smallest VPS is
  enough.
- **A Tailscale account.** Tailscale makes a private network of your
  devices, even when they're far apart. It's free for personal use.
- **Some experience with the terminal.** You log in to the VPS with SSH
  and type a few commands.

Ordinary web hosting, like a package for a WordPress website, won't work.
There you can only upload files (with PHP or FTP), and Huismus has to run
as its own program all the time.

## What to know first

- Your administration lives on a computer of the hosting company, not at
  your home.
- Huismus doesn't encrypt your administration on the VPS. Only the backups
  to Dropbox or WebDAV are encrypted.
- Whoever can get into the VPS can get to your administration. So pick a
  company you trust, and keep the password or key of your VPS safe.
- You keep the VPS itself up to date: Linux, Docker and Tailscale. Updating
  Huismus works as on the page [Huismus in Docker](docker.en.md#updating).

## Installing

1. **Docker.** Install Docker on the VPS following Docker's own
   instructions for the Linux on your VPS (usually Ubuntu or Debian).

2. **Tailscale.** Install Tailscale on the VPS following Tailscale's
   instructions, and add the VPS to your network with:

   ```
   sudo tailscale up
   ```

   Name the VPS `huismus` in Tailscale. In Tailscale's admin console, under
   DNS, turn on **MagicDNS** and **HTTPS certificates**. The VPS then gets
   its own address, such as `huismus.your-tailnet.ts.net`. That address
   only works on devices running Tailscale with your account.

3. **Huismus.** Put this in a file `compose.yaml`, in a folder on the VPS.
   Replace `your-tailnet` with the address Tailscale gave you:

   ```yaml
   services:
     huismus:
       image: ghcr.io/codebyarne/huismus:0.1
       restart: unless-stopped
       environment:
         ALLOWED_HOSTS: huismus.your-tailnet.ts.net
         CSRF_TRUSTED_ORIGINS: https://huismus.your-tailnet.ts.net
         DJANGO_SUPERUSER_USERNAME: <username>
         DJANGO_SUPERUSER_PASSWORD: <password>
       volumes:
         - huismus-data:/app/data
       ports:
         - "127.0.0.1:8000:8000"
   volumes:
     huismus-data:
   ```

   Start Huismus in that folder with:

   ```
   docker compose up -d
   ```

   `127.0.0.1:8000` keeps Huismus on the VPS itself. Nobody outside can
   reach it, even with the firewall off. What the other lines do is under
   [Installing](docker.en.md#installing) on the Docker page.

4. **HTTPS through Tailscale.** Let Tailscale pass Huismus on to your own
   devices:

   ```
   sudo tailscale serve --bg 8000
   ```

   `tailscale serve status` shows the address.

5. **The firewall.** The port on `127.0.0.1` is what protects Huismus. A
   firewall is a second lock for everything else on the VPS. With `ufw`
   (on Ubuntu and Debian) you let in only SSH and Tailscale:

   ```
   sudo ufw allow OpenSSH
   sudo ufw allow in on tailscale0
   sudo ufw enable
   ```

   Does your hosting company have a firewall in its control panel too? Open
   only SSH there.

6. **Opening it.** Turn on Tailscale on your phone, tablet or laptop and
   open `https://huismus.your-tailnet.ts.net`. Log in with the username and
   password from `compose.yaml`. After that you can remove those two lines.
   On your phone, put Huismus on your home screen as an app:
   [On your phone](telefoon.en.md#installing-huismus-as-an-app).

## Never open to the internet

Huismus is made for your own network. So don't open it up to everyone on a
VPS. That happens if you:

- use `tailscale funnel` instead of `tailscale serve`. Funnel puts Huismus
  on the internet;
- give the port without `127.0.0.1` (`8000:8000`);
- let a reverse proxy (such as nginx or Caddy) pass Huismus on to the
  outside.

A server that can be reached from the internet gets tried all day long.

## Backups

A backup on the same VPS doesn't help if the VPS breaks or you cancel the
subscription. So let Huismus send an encrypted backup to Dropbox or WebDAV
every day:
[In the cloud: Dropbox or WebDAV](back-ups.en.md#in-the-cloud-dropbox-or-webdav).
