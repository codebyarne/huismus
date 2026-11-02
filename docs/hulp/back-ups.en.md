# Backups

Huismus backs up your administration every day, to every place you turn on:
a folder, Dropbox or WebDAV. A backup is one file with your invoices,
quotes, customers, expenses, receipts and logo. Your mail password and the
key for AI assistants are left out on purpose.

Everything is under **Settings → Backups**. The three places are listed
there, each showing whether it's on and when the last backup was. **Back up
now** makes one right away, in every place that's on.

## Choosing a folder

Open **Settings → Backups** and choose **Set up** next to **Folder**. You
choose a folder once, and from then on it happens by itself:

- **When:** right after you choose, then every day. In the desktop app only
  on days Huismus is open; on a server always.
- **How many:** Huismus keeps everything from the last 30 days, one a month
  before that, and always the newest. It only cleans up its own backups
  (`huismus-backup-<date>-<time>.tar.gz`) and leaves the rest of the folder
  alone.
- **When something's wrong:** the overview shows a red notice if the last
  backup failed, for example because the folder was full or couldn't be
  reached. An orange notice means you haven't chosen a folder yet, or there
  hasn't been a backup for 7 days.

In the desktop app Huismus suggests the folders of iCloud Drive, Google
Drive, OneDrive and Dropbox. You can also choose **Other folder…**, such as
a USB stick.

Running Huismus on a server, like a Raspberry Pi or a NAS? Then you first
link the folder to Huismus. [Linking a folder](#linking-a-folder) explains
how.

Choose a folder on another device or in the cloud. A backup on the same disk
as Huismus won't help if that disk breaks.

## In the cloud: Dropbox or WebDAV

Huismus can also send a backup straight to the cloud every day, next to the
folder or instead of it. That's especially useful on a Raspberry Pi or NAS,
where there's no Dropbox app to copy a folder to the cloud for you.

Open **Settings → Backups** and choose:

- **Dropbox:** choose **Connect**, open Dropbox, sign in and choose
  **Allow**. Dropbox then shows a code; paste it into Huismus. Huismus can
  only reach its own folder in your Dropbox: **Apps › Huismus**.
- **WebDAV:** choose **Set up**. This works with Nextcloud, kDrive, Koofr,
  Hetzner Storage Box, pCloud and other storage that speaks WebDAV. You
  enter three things: the address (it starts with `https://` and is in your
  storage's settings, often under WebDAV), your user name, and an app
  password you create there just for Huismus. Huismus puts the backups in a
  folder called `Huismus`.

You use one cloud at a time. After connecting you get a recovery code (see
below). As soon as you've said you saved it, the first backup goes to the
cloud. That happens in the background, so you can carry on. While it runs,
you see **Making a backup…**.

From then on it works like the folder: a backup every day, the last 30 days
kept and one a month before that. If a backup fails, the service says
**Failed** and the overview shows a red notice. Under **Manage** you can see
your recovery code, set the service up again or disconnect it.
Disconnecting leaves the backups in the cloud where they are.

### Your recovery code

Huismus encrypts every backup before it goes to the cloud, using a recovery
code of 24 letters and digits. You see the code when you first connect, and
backups only go to the cloud once you've said you saved it.

Keep the code in your password manager, or print it. Without it you can't
restore a backup from the cloud on another computer. While this
installation runs, you can find it under **Manage → View recovery code**.
The code itself never goes into a backup.

On a new computer, connect the same cloud and choose **Do you already have a
recovery code from an earlier installation?**. The backups from the cloud
then show up under **Restore a backup…**.

A backup in the cloud (`huismus-backup-<date>-<time>.tar.gz.age`) is
encrypted in the open [age](https://age-encryption.org) format, so you can
also open it without Huismus: use the `age` program with your recovery code
as the passphrase (the 24 characters without spaces):
`age -d huismus-backup-….tar.gz.age > huismus-backup.tar.gz`.

## Restoring a backup

Under **Settings → Backups**, choose **Restore a backup…**. Pick a backup
from the list, or another file, such as a backup from another computer.
Huismus first makes one more backup of how things are now, then restores.
While that runs, every page says "Huismus is restoring a backup".

Afterwards you're still logged in in this browser. On other devices you may
have to log in again. You can't restore a backup from a newer version of
Huismus; update Huismus first.

Restoring on another computer? Enter your mail password again and connect
your AI assistants again. They don't go into a backup.

## Linking a folder

This part is only for running Huismus in Docker, for example on a Raspberry
Pi or a NAS. Using the desktop app? Then you can skip it.

### Why

In Docker, Huismus runs in its own sealed-off box, a container. From in
there it can't see the disks and folders of your Pi or NAS. And anything it
stores inside the box itself is gone as soon as the container is replaced,
which happens on every update.

So a backup has to live in a folder outside the container. That's what
linking a folder does: you give Huismus one folder of your Pi or NAS, which
it sees inside the container as `/backups`. Whatever Huismus puts there is
really in your folder, and stays there after an update.

### Step by step

1. **Pick a folder** on your Pi or NAS, for example on a USB drive or a
   shared folder on your NAS. See the examples below.
2. **Give Huismus that folder.** You do that when you start the container,
   with `-v /path/to/your/backup/folder:/backups` (see the examples below).
   The part before the colon is your folder; the part after it is the name
   Huismus sees, and that's always `/backups`.
3. **Let Huismus write to it.** Inside the container Huismus is the user
   `huismus`, not the administrator (root). Find its number with
   `docker exec huismus id -u` and make it the owner of the folder, for
   example `sudo chown 999 /path/to/your/backup/folder`;
   replace 999 with the number from the previous command.
4. **Choose the folder in Huismus.** Open **Settings → Backups → Folder**.
   Huismus suggests the linked folder by itself. Save, and the first backup
   is in there right away.

If Huismus can't write to the folder, the Backups page says the folder
can't be reached. Check step 3 again.

### Examples

With `docker run`:

```
docker run -d --name huismus \
  -e ALLOWED_HOSTS=huismus.local \
  -v huismus-data:/app/data \
  -v /path/to/your/backup/folder:/backups \
  -p 127.0.0.1:8000:8000 \
  huismus
```

With Docker Compose:

```yaml
services:
  huismus:
    image: huismus
    environment:
      ALLOWED_HOSTS: huismus.local
    volumes:
      - huismus-data:/app/data
      - /path/to/your/backup/folder:/backups
    ports:
      - "127.0.0.1:8000:8000"
volumes:
  huismus-data:
```

What to use for `/path/to/your/backup/folder`:

- **Synology or another NAS:** a shared folder, such as
  `/volume1/backups/huismus`. Want the backups in the cloud too? Let the NAS
  copy that folder, on Synology with Cloud Sync or Hyper Backup.
- **Raspberry Pi with a USB stick:** the folder where the stick always
  shows up, such as `/mnt/usb/huismus`. Add the stick to `/etc/fstab` for
  that, or it's gone after a restart.
- **A folder on another computer in your network:** make it reachable on
  your Pi or NAS first (with SMB or NFS), then use that path.

## Test your backups

A backup you've never restored is an assumption, not a guarantee. So now and
then, restore one somewhere else, for example in the desktop app on another
computer, and check that your invoices are there.
