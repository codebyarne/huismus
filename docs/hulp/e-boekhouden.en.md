# Moving from e-Boekhouden.nl

Are your books in e-Boekhouden.nl? Then you get your data out, have an
AI assistant convert it to the Huismus template, and import it. Huismus
does a trial run first and only saves something when you choose to.

## Getting your data out of e-Boekhouden.nl

e-Boekhouden.nl has no export with everything in it. This is what it
describes in its help:

1. **Customers:** open **<span lang="nl">Relaties</span>**, choose **<span lang="nl">Zoeken</span>**, click **<span lang="nl">zoeken</span>** and
   then the Excel icon. [This is how e-Boekhouden.nl describes it in its
   help](https://cdn.e-boekhouden.nl/handleiding/Handleiding_Relaties.pdf).
2. **Invoices:** open **<span lang="nl">Factureren</span>**, **<span lang="nl">Facturen</span>**, **<span lang="nl">Overzicht</span>**. For each
   invoice, save the PDF with the printer icon. [This is how e-Boekhouden.nl
   describes it in its help](https://cdn.e-boekhouden.nl/handleiding/Handleiding_Factureren.pdf).
3. **Audit file:** open **<span lang="nl">Beheer</span>**, **<span lang="nl">Exporteren</span>**, **<span lang="nl">XML-Auditfile</span>**. The
   assistant uses it to check whether an invoice is missing. [This is how
   e-Boekhouden.nl describes it in its help](https://www.e-boekhouden.nl/veelgestelde-vragen).

An export of invoice lines, quotes, expenses or your attachments isn't in
e-Boekhouden.nl's public help. Then you only have your invoices as PDFs. The
assistant reads every line from the PDF. That's a lot of work, so do it per
year if you have many invoices. The trial run then checks every total.

If you don't save the PDFs, Huismus makes them itself, with your business
details of today. So keep the PDFs your customers received yourself as
well.

## Converting with an AI assistant

1. In Huismus, open **Import**, choose **From another package or Excel** and
   click **Download template**.
2. Open an AI assistant, such as ChatGPT or Claude. This is an ordinary chat
   you add files to, not the connection under
   [AI assistants](ai-assistenten.en.md).
3. Add the template and all your files from e-Boekhouden.nl to the chat. Copy the
   instructions below and paste them in.

You do let that service read your books.

```text
I'm moving from e-Boekhouden.nl to Huismus. Convert my data to the Huismus import template.

What I'm giving you:
- the Huismus import template (a zip);
- my export from e-Boekhouden.nl: the relations as Excel, the PDFs of my invoices, and the XML audit file.

Where it goes:
- Relations I invoice → customers.csv.
- Every PDF of an invoice or credit note → a row in invoices.csv and the lines in lines.csv, as they are on the PDF. The PDF itself → the folder for PDFs of invoices or credit notes.
- Only add expenses if I give them to you separately.
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
year under **Reports › Year overview** with the one in e-Boekhouden.nl.

## Cancelling afterwards

Cancel e-Boekhouden.nl only when everything is in Huismus, you've checked it and you
have a [backup](back-ups.en.md). Also keep what you got out of e-Boekhouden.nl with
your own files.

According to e-Boekhouden.nl, you cancel under **<span lang="nl">Beheer</span>**. After that
your data is deleted, unless you take an Online Archief. [This is how e-Boekhouden.nl describes it
in its help](https://www.e-boekhouden.nl/veelgestelde-vragen).
