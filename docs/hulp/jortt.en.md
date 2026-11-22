# Moving from Jortt

Are your books in Jortt? Then you get your data out, have an AI
assistant convert it to the Huismus template, and import it. Huismus does a
trial run first and only saves something when you choose to.

## Getting your data out of Jortt

Jortt has no export with everything in it. You download a file per part:

1. **Customers:** open **<span lang="nl">Klanten</span>** and click **<span lang="nl">Download CSV</span>**. [This is how
   Jortt describes it in its help](https://www.jortt.nl/factuur-maken/factuur-maken-uitleg/klanten-aanmaken-en-beheren/).
2. **Invoices:** open **<span lang="nl">Facturen en offertes</span>**, **<span lang="nl">Facturen</span>**. Choose a
   period, for example a year, and click the download icon. You get a zip
   with a PDF per invoice. Do this for every year. [This is how Jortt
   describes it in its help](https://www.jortt.nl/uitleg/faq/exportmogelijkheden-in-jortt/).
3. **Quotes, purchase invoices and receipts:** Jortt only exports these
   through its Dropbox connection. [This is how Jortt describes it in its
   help](https://www.jortt.nl/uitleg/faq/exportmogelijkheden-in-jortt/).
4. **Audit file:** open **<span lang="nl">Boekhoudbot</span>** and choose **<span lang="nl">Maak voor mij een
   auditfile</span>**, for every year. The assistant uses it to check whether an
   invoice is missing. [This is how Jortt describes it in its
   help](https://www.jortt.nl/boekhouder/boekhouder-uitleg/auditfile/).

You only get your invoices as PDFs. The assistant reads every line from the
PDF. That's a lot of work, so do it per year if you have many invoices. The
trial run then checks every total. The PDFs come along: in Huismus, every
invoice keeps the PDF your customer received.

## Converting with an AI assistant

1. In Huismus, open **Import**, choose **From another package or Excel** and
   click **Download template**.
2. Open an AI assistant, such as ChatGPT or Claude. This is an ordinary chat
   you add files to, not the connection under
   [AI assistants](ai-assistenten.en.md).
3. Add the template and all your files from Jortt to the chat. Copy the
   instructions below and paste them in.

You do let that service read your books.

```text
I'm moving from Jortt to Huismus. Convert my data to the Huismus import template.

What I'm giving you:
- the Huismus import template (a zip);
- my export from Jortt: the customer file (CSV), a zip with the PDFs of my invoices per year, and the audit file. Maybe quotes, purchase invoices and receipts from Dropbox too.

Where it goes:
- Jortt's customer file → customers.csv.
- Every PDF of an invoice or credit note → a row in invoices.csv and the lines in lines.csv, as they are on the PDF. The PDF itself → the folder for PDFs of invoices or credit notes.
- Quotes → quotes.csv and lines.csv; purchase invoices and receipts → expenses.csv, expense-lines.csv and the receipts folder.
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
year under **Reports › Year overview** with the one in Jortt.

## When you cancel

According to Jortt, you keep your data if you go back to jortt Starter.
The bookkeeping, the audit file and the Dropbox connection then stop
working, so export those first. [This is how Jortt describes it in its
help](https://www.jortt.nl/boekhouder/boekhouder-uitleg/weggaan-bij-jortt/).
