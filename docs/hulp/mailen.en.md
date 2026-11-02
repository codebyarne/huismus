# Mail

You mail an invoice, credit note or quote straight from Huismus, with the
PDF attached. You can do that once the invoice or credit note is issued, or
the quote is sent. The mail goes through your own Gmail or the mail server
of your own domain. No other service sits in between.

Mailing doesn't change the document. Every attempt goes on the document's
timeline, failed ones too, with the error message.

## Setting up mail

You set everything up under **Settings → Mail**. First choose what you mail
through: **Gmail** or **Other** (the mail server of your own domain). Then
fill in the details, as described below for each choice.

Huismus never shows your password, only whether there is one. If you leave
the field empty when you save, Huismus keeps the password it already had.
If you choose **Not set up** under "Mail through", mailing is off and
Huismus erases the password.

Your mail password isn't part of a backup. Otherwise anyone with a copy of
your backup could get into your mailbox. If you restore a backup on another
computer, enter the password there again.

## Gmail

Gmail doesn't accept your ordinary password from a program like Huismus.
So you make an **app password**: a separate 16-character password, just for
Huismus. You can revoke it at any time.

1. Turn on 2-Step Verification for your Google account, if it isn't on yet:
   <https://myaccount.google.com/signinoptions/two-step-verification>.
   Without it, Google doesn't give out app passwords.
2. Go to <https://myaccount.google.com/apppasswords>.
3. Give it a name, for example `Huismus`, and choose **Create**.
4. Google shows the password once, in groups of four characters. Copy it
   and paste it into Huismus only.
5. In Huismus, under **Settings → Mail**, choose **Gmail**. Enter your Gmail
   address as the username and paste the app password under Password. The
   spaces can stay, Huismus removes them. Huismus fills in the server, port
   and security itself.
6. Save and choose **Send test mail**.

Don't see the app passwords page? On a Google Workspace account the
administrator may have turned it off. Ask them to turn it on, or choose
**Other** and mail through another mail server.

**Sender.** Gmail always sends from the address of the account you log in
with, even if you enter something else under "Sender". To send from another
address, first add it in Gmail under Settings → Accounts → "Send mail as".

**Revoking.** You delete the password on the same app passwords page. From
then on Huismus can't mail. To mail again later, make a new app password
and enter it under **Settings → Mail**.

## Your own domain (Other)

If you mail from an address on your own domain, you need the details from
your hosting provider. They call them "outgoing mail" or "SMTP". Usually
they are:

| Field | Usually |
|---|---|
| SMTP server | `smtp.<yourdomain>` or `mail.<yourdomain>` |
| Port and security | 587 with STARTTLS, or 465 with SSL/TLS |
| Username | your full e-mail address |
| Password | the password of that mailbox |

Choose **Other**, fill in the fields, save and choose **Send test mail**. If
you leave "Sender" empty, Huismus mails from your business e-mail address.

## Changing the standard text

Every mail starts with a subject and a text you set yourself, under
**Settings → Mail → Standard texts**. There's a text for each kind of
document (invoice, credit note, quote), in Dutch and in English. A document
in English gets the English text. Before you send a mail, you can still
change all of it.

Placeholders put the document's details into the text. They have Dutch
names, in the English texts too:

| Placeholder | Becomes |
|---|---|
| `{nummer}` | the document's number |
| `{bedrag}` | the document's total |
| `{naam}` | the customer's first name, or else the customer's name |
| `{bedrijf}` | your business name |
| `{vervaldatum}` | only on an invoice: the due date |
| `{geldig_tot}` | only on a quote: until when it's valid |

You can't save a typo such as `{klant}`. That way it never ends up in a
mail to a customer. If a quote has no end date, Huismus leaves out the line
with `{geldig_tot}`. If you empty a text, Huismus uses its own text again.

## When mailing fails

The error message is on the screen and on the document's timeline. Your
password is never in it. These are the most common ones:

| The message mentions | What's usually wrong |
|---|---|
| `535` or `Username and Password not accepted` | The password or username is wrong. With Gmail you need an app password, not your ordinary password. |
| `timed out` or `Connection refused` | The server or port is wrong, or your network blocks the connection to the outside. Huismus waits 20 seconds at most. |
| `SSL` or `wrong version number` | Port and security don't match: 587 goes with STARTTLS, 465 with SSL/TLS. |

A failed attempt sends nothing and changes nothing about the document. Fix
the setting and try again.
