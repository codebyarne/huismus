# Receipts on the road

On the road, take a photo or scan of a receipt and save it in a folder that
syncs, such as iCloud Drive or Dropbox. Huismus usually picks it up within a
few minutes. At home you make an expense of it in one click, with the receipt
already attached.

## Setting up a receipts folder

Go to **Settings → Receipts folder** and choose where Huismus looks.

- **In the desktop app** you choose a folder on your laptop. Huismus suggests
  a folder `Huismus receipts` in iCloud Drive, Google Drive, OneDrive or
  Dropbox, if they are on your laptop. Huismus makes the folder right away,
  so you see it on your phone too.
- **In Docker, on a Raspberry Pi for example,** you choose **Dropbox** or
  **WebDAV**. For that you first set it up under **Settings → Backups**.
  Huismus fetches the receipts itself and stays unreachable from the internet.
  - With **Dropbox**, Huismus looks in **Apps › Huismus › Receipts** in your
    Dropbox.
  - With **WebDAV**, such as Nextcloud, kDrive or Koofr, Huismus looks in the
    folder **Huismus › Receipts**, next to your backups. You see that folder
    in your storage service's app on your phone too.
- Do you use Syncthing? Then choose a plain folder that Syncthing keeps in
  sync. In Docker you link it first, see [Huismus in Docker](docker.en.md).

Huismus looks right away when something changes in the folder or in
Dropbox. It picks up a file in a folder once it hasn't changed for a minute,
so it's fully synced. To be safe it also looks every 10 minutes. With
WebDAV it only looks every 10 minutes. When
something comes in, the overview says, for example, **2 new receipts**. Don't
want to wait? Click **Pick up now**.

## Saving a receipt on your phone

**iPhone:** open the photo, tap the share icon and choose **Save to Files**.
Choose the folder, for example iCloud Drive › Huismus receipts.

Tip: in the Files app you can scan a receipt straight away. Open the folder,
tap the three dots and choose **Scan Documents**. That makes a PDF.

**Android:** share the photo with the app of your service, such as Google
Drive, OneDrive, Dropbox or Nextcloud, and choose the folder.

Huismus picks up PDFs, JPGs, PNGs and HEIC photos from an iPhone, up to
10 MB per file. Huismus keeps a HEIC photo as a JPG. The original is in the
**Picked up** folder.

## What Huismus does with the file

Huismus first saves the receipt in your administration. Then it moves it in
your folder to the **Picked up** folder. That way you see what came in, and
Huismus never picks anything up twice.

If something doesn't work, the file just stays in your folder. For example
a Word file, or a file bigger than 10 MB. The Receipts folder page then
says which file it is and why.

## Making an expense of a receipt

On **Expenses** there is a **Receipts** button, with how many receipts have
no expense yet. Click **Create expense** next to a receipt: you get the
usual form, with the receipt already at the top. Fill in the rest and click
**Save**. If another receipt is waiting, you get the next one right away.
Want to do one later? Click **Skip**.

Don't need a receipt? Remove it from the list. The file stays in the
**Picked up** folder.

## Let your AI assistant process them

If you've connected an AI assistant (see [AI assistants](ai-assistenten.en.md)),
say: **Process my receipts in Huismus.** It reads each receipt and makes the
expense, with the receipt attached. If it can't read a receipt, it says so
and the receipt stays with the receipts without an expense. What your
assistant filled in is under **To check** on **Expenses**. Open the top
one and click **Looks right** if it's all correct: you get the next one
right away. **Skip** leaves one for later.

Your assistant only sees your receipts when you ask it to. Want Huismus to
have them read by itself? See below.

## Receipt reading

Huismus can also have your receipts read by itself, without you asking. It
does that with an AI service you choose, with your own key. Every receipt
that comes in then becomes an expense marked **To check**. You check it and
click **Looks right**.

Go to **Settings → Receipt reading** and choose a service:

- **Anthropic (Claude), Google Gemini, Mistral or OpenAI.** Create an account
  and an API key on the service's site. Huismus fills in the address and a
  model that can read images. You pay the service yourself, a small amount
  per receipt. Check the service's site for what it costs.
- **Ollama**, on your own computer or network. Your receipts then stay off the
  internet, and you need no key. Choose a model that can read images. If
  Huismus runs in Docker, use the address of the computer with Ollama on
  your network, for example `http://192.168.1.20:11434/v1`.
- **Another service.** Any service that works with OpenAI-compatible apps.
  Fill in the address, the model and your key.

When you click **Save**, Huismus first tries the service with one small
image. If that doesn't work, Huismus says why and saves nothing. You won't
see your key again after that, and it doesn't go into your backups.

After saving, Huismus also reads the receipts without an expense that were
already there. On the overview you then see, for example, **2 new expenses
to check**.

### What Huismus leaves

Huismus never guesses an amount. A receipt stays with the receipts without an
expense, with the reason, when:

- it isn't clear enough, or isn't a receipt;
- there's more than one receipt on it;
- there's no total on it, or the amounts don't add up to the total;
- the VAT isn't on it, while you don't use the KOR;
- it looks like an expense you already have: the same day and the same amount.

Make that expense yourself, with **Create expense**. Huismus never sends the
same receipt to the service twice.

Can't Huismus read for a while, because the service refuses your key or can't
be reached? You'll see that in red with the receipts without an expense. The
receipts wait, and Huismus tries again the next time it looks in your
receipts folder.

Turn it off with **Turn off** on the same page. Huismus then forgets the
service and your key.
