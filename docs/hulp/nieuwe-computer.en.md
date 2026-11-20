# Moving to a new computer

Moving Huismus to a new computer, Raspberry Pi, NAS or server? You take your
administration along with a backup. A few settings belong to the device, and
you set those up again there.

## Moving in four steps

1. **Make a backup on the old computer.** Choose **Settings → Backups → Back
   up now**. Do your backups go to Dropbox or WebDAV? Then keep your recovery
   code at hand. You find it under **Manage → View recovery code**.
2. **Install Huismus on the new computer.** How that works is in
   [The desktop app](desktop-app.en.md) and
   [Huismus in Docker](docker.en.md).
3. **Restore the backup.** Choose **Settings → Backups → Restore a backup…**
   and pick the file. Is your backup in the cloud? Then connect the same
   cloud first and choose **Do you already have a recovery code from an
   earlier installation?**. There's more in
   [Backups](back-ups.en.md#restoring-a-backup).
4. **Stop using the old computer for Huismus.** Otherwise you have two
   administrations that drift apart, with the same invoice numbers for
   different invoices.

## What comes along

Everything in your administration: your invoices, quotes and credit notes,
your customers, your expenses and receipts, your logo and your settings.
Your login comes along too: your username and password stay the same. In the
desktop app, that also goes for the app's password.

## What you set up again

This is left out of a backup on purpose. These are keys and passwords that
shouldn't travel with a copy of your backup, and folders that have a
different name on every computer.

- **Your backup folder or cloud.** Choose a folder again under **Settings →
  Backups**, or connect Dropbox or WebDAV again with your recovery code.
  Until you do, Huismus makes no backups. The overview says so with an
  orange notice.
- **Your mail password.** Enter it again under **Settings → Mail**. The rest
  of your mail settings is already there. After restoring, Huismus tells you
  if your password is missing.
- **Your receipts folder.** Choose it again under **Settings → Receipts
  folder**. Receipts that Huismus had already picked up are in your
  administration as before.
- **The AI service that reads your receipts.** Choose the service again
  under **Settings → Reading receipts with AI** and enter your key.
- **Your AI assistants.** Choose **Connect** under **Settings → AI
  assistants** and give your assistant the new key. The old key doesn't work
  on the new computer.
- **Updates.** Had you turned off **Update automatically**, or in Docker
  **Look for new versions**? Then turn it off again under **Settings →
  Updates**.
- **Logging in on your other devices.** After restoring, you stay logged in
  in the browser you did it in. On other devices you log in again.

## Running Huismus in Docker?

What's in your `compose.yaml` or in your command isn't part of a backup
either: the address and the folders you link to Huismus. Set that up again
on the new server, as described in [Huismus in Docker](docker.en.md). You
link a folder for your backups as described in
[Linking a folder](back-ups.en.md#linking-a-folder).

Does the new server have a different address? Then put Huismus on your
phone's home screen again. How that works is in
[On your phone](telefoon.en.md).
