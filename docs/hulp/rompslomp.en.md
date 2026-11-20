# Moving from Rompslomp

Are your books in Rompslomp? Then you get your data out, have an AI
assistant convert it to the Huismus template, and import it. Huismus does a
trial run first and only saves something when you choose to.

## Getting your data out of Rompslomp

Rompslomp has no export with everything in it. You download a file per part:

1. **Customers:** open **Contacten**, click **Export** and choose **Download
   als .xls**. [This is how Rompslomp describes it in its
   help](https://rompslomp.nl/support/contacten/contactgegevens-exporteren).
2. **Invoices:** open **Facturen**, click **Exporteer**, choose **Alle
   boekjaren** and **Download als .xls**. Get the PDFs of your invoices there
   too. [This is how Rompslomp describes it in its help](https://rompslomp.nl/support/algemeen/backup-maken).
3. **Expenses and receipts:** open **Uitgaven**, click **Exporteer** and choose
   **Download als .xls**. Then choose **Download alle bijlagen**: you get a
   zip with your receipts. [This is how Rompslomp describes it in its
   help](https://rompslomp.nl/support/uitgaven/uitgave-exporteren).
4. **Audit file:** open **Instellingen**, tab **Exporteren**, and export the
   audit file, for every financial year. The assistant uses it to check
   whether an invoice is missing. [This is how Rompslomp describes it in its
   help](https://rompslomp.nl/support/boekhouding/auditfile).

How to export quotes and credit notes isn't in Rompslomp's help. Nor is
whether the invoice lines are in the .xls. If they aren't, the assistant reads them from the
PDFs.

## Converting with an AI assistant

1. In Huismus, open **Import**, choose **From another package or Excel** and
   click **Download template**.
2. Open an AI assistant, such as ChatGPT or Claude. This is an ordinary chat
   you add files to, not the connection under
   [AI assistants](ai-assistenten.en.md).
3. Add the template and all your files from Rompslomp to the chat. Copy the
   instructions below and paste them in.

You do let that service read your books.

```text
I'm moving from Rompslomp to Huismus. Convert my data to the Huismus import template.

What I'm giving you:
- the Huismus import template (a zip);
- my export from Rompslomp: contacts, invoices and expenses as .xls, the PDFs of my invoices, a zip with attachments, and the audit file.

Where it goes:
- Contacts that are customers → customers.csv, their contact persons → contact-persons.csv.
- Invoices and credit notes → invoices.csv, their lines → lines.csv. If the lines aren't in the .xls, read them from the PDF.
- Expenses → expenses.csv and expense-lines.csv, the attachments → the receipts folder.
- Use the audit file only to check whether an invoice is missing or a total differs.

How to fill in the template:
- First read README.txt in the template. Write amounts, dates and folder names as it says.
- Keep the first row with column names of each file exactly as it is. Replace the example row with my data.
- Don't make anything up. If something isn't in my files, leave the cell empty. If you don't know which column goes where, ask me first.
- Copy amounts exactly as they are in my files, to the cent. Don't recalculate totals and don't round anything.
- Copy invoice and credit note numbers exactly. Don't renumber anything.
- Give every customer a customer number and use that number for their invoices and quotes too.
- A credit note gets "credit note" as its kind, negative amounts, and in "credited invoice" the number of the invoice it belongs to.
- For every invoice line, copy the VAT rate, also when it is 0. If an invoice line has no rate, don't fill one in but ask me.
- For every expense, copy the VAT rate and the VAT amount, also when they are 0. If an expense has no rate, leave it empty.
- Leave out drafts.
- Put the PDFs of invoices and credit notes in the folders README.txt names, with the number as the file name. Receipts go in the receipts folder, with their file name in the receipts column of expenses.csv. Separate several receipts for one expense with " | ".
- Give everything back to me as one zip, with the same file names as the template. Leave out a file that stays empty.

Below the zip, give me a list: what you couldn't copy, what you left empty, and where my files contradict each other.
```

You get a zip back. Read the list below it: what the assistant couldn't
copy, you add yourself or leave out.

## Importing and checking

In Huismus, drag the zip to the box under **From another package or Excel**
and click **Start trial run**. The trial run saves nothing. Huismus checks
every invoice, to the cent, and tells you what doesn't add up. What you see
then is explained in [Importing from another package or
Excel](importeren.en.md#what-the-trial-run-shows).

If everything is right, click **Import now**. Then compare your revenue per
year under **Reports › Year overview** with the one in Rompslomp.

## Cancelling afterwards

Cancel Rompslomp only when everything is in Huismus, you've checked it and you
have a [backup](back-ups.en.md). Also keep what you got out of Rompslomp with
your own files.

According to Rompslomp, cancelling deletes your account, and everything is
gone within 30 days. [This is how Rompslomp describes it in its
help](https://rompslomp.nl/support/rompslomp-account/abonnement-opzeggen).
