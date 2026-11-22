# Moving from Tellow

Are your books in Tellow? Then you get your data out, have an AI
assistant convert it to the Huismus template, and import it. Huismus does a
trial run first and only saves something when you choose to.

## Getting your data out of Tellow

Tellow has one screen for exporting:

1. Open **<span lang="nl">Rapportage</span>** and choose **<span lang="nl">Exporteren</span>**.
2. Choose **<span lang="nl">CSV</span>** and the whole period you used Tellow. Export **<span lang="nl">Bedrijven</span>**,
   **<span lang="nl">Personen</span>**, **<span lang="nl">Verkoop - Facturen</span>** and **<span lang="nl">Inkoop - Facturen</span>**.
3. Then choose **<span lang="nl">Auditfile</span>**, for the same period. The assistant uses it to
   check whether an invoice is missing.

[This is how Tellow describes it in its help](https://help.tellow.nl/nl/articles/3000768-hoe-exporteer-ik-gegevens-uit-tellow).

How to export quotes, credit notes, the PDFs of your invoices and your
receipts in one go isn't in Tellow's help. Nor is which columns and invoice
lines are in the CSV. If
you have no PDFs, Huismus makes them itself, with your business details of
today. So keep the PDFs your customers received yourself as well.

## Converting with an AI assistant

1. In Huismus, open **Import**, choose **From another package or Excel** and
   click **Download template**.
2. Open an AI assistant, such as ChatGPT or Claude. This is an ordinary chat
   you add files to, not the connection under
   [AI assistants](ai-assistenten.en.md).
3. Add the template and all your files from Tellow to the chat. Copy the
   instructions below and paste them in.

You do let that service read your books.

```text
I'm moving from Tellow to Huismus. Convert my data to the Huismus import template.

What I'm giving you:
- the Huismus import template (a zip);
- my export from Tellow as CSV: Bedrijven, Personen, Verkoop - Facturen and Inkoop - Facturen, and the audit file. Maybe PDFs of invoices and receipts too.

Where it goes:
- Bedrijven and Personen I invoice → customers.csv, people at a company → contact-persons.csv.
- Verkoop - Facturen → invoices.csv, their lines → lines.csv. If there are no lines, read them from the PDF if I gave you one; otherwise one line per invoice with the total per VAT rate.
- Inkoop - Facturen → expenses.csv and expense-lines.csv.
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
year under **Reports › Year overview** with the one in Tellow.

## When you cancel

According to Tellow, you cancel by email, and afterwards you can't log in
any more. [This is how Tellow describes it in its help](https://help.tellow.nl/nl/articles/6389787-hoe-kan-ik-mijn-abonnement-annuleren).
