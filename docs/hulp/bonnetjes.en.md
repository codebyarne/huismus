# Receipts on the road

On the road, take a photo or scan of a receipt and save it in a folder that
syncs, such as iCloud Drive or Dropbox. Huismus picks it up within 10
minutes. At home you make an expense of it in one click, with the receipt
already attached.

## Setting up a receipts folder

Go to **Settings → Receipts folder** and choose where Huismus looks.

- **In the desktop app** you choose a folder on your laptop. Huismus suggests
  a folder `Huismus receipts` in iCloud Drive, Google Drive, OneDrive or
  Dropbox, if they are on your laptop. Huismus makes the folder right away,
  so you see it on your phone too.
- **In Docker, on a Raspberry Pi for example,** you choose **Dropbox**. For
  that you first link Dropbox under **Settings → Backups**. Huismus then
  looks in **Apps › Huismus › Receipts** in your Dropbox. Huismus fetches the
  receipts itself and stays unreachable from the internet.
- Do you use Syncthing or Nextcloud? Then choose a plain folder that such a
  program keeps in sync. In Docker you link it first, see
  [Huismus in Docker](docker.en.md).

Huismus looks every 10 minutes. Don't want to wait? Click **Pick up now**.

## Saving a receipt on your phone

**iPhone:** open the photo, tap the share icon and choose **Save to Files**.
Choose the folder, for example iCloud Drive › Huismus receipts.

Tip: in the Files app you can scan a receipt straight away. Open the folder,
tap the three dots and choose **Scan Documents**. That makes a PDF. Huismus
doesn't pick up HEIC photos yet, and a scan is always a PDF.

**Android:** share the photo with the app of your service, such as Google
Drive, OneDrive or Dropbox, and choose the folder.

Huismus picks up PDFs, JPGs and PNGs, up to 10 MB per file.

## What Huismus does with the file

Huismus first saves the receipt in your administration. Then it moves it in
your folder to the **Picked up** folder. That way you see what came in, and
Huismus never picks anything up twice.

If something doesn't work, the file just stays in your folder. For example
a HEIC photo, or a file bigger than 10 MB. The Receipts folder page then
says which file it is and why.

## Making an expense of a receipt

On **Expenses** there is a **Receipts** button, with how many receipts have
no expense yet. Click **Create expense** next to a receipt: you get the
usual form, with the receipt already at the top. Fill in the rest and click
**Save**.

Don't need a receipt? Remove it from the list. The file stays in the
**Picked up** folder.
