# Moving from Excel

Do you keep your invoices and expenses in Excel or Numbers? Then you
have an AI assistant convert your spreadsheets to the Huismus template, and
import them. Huismus does a trial run first and only saves something when
you choose to.

## Getting your files ready

Gather what you have: your spreadsheets with invoices, customers and
expenses, the PDFs of your invoices and your receipts. What your
spreadsheets look like doesn't matter. But every invoice needs a number, a
date, a customer and an amount.

Rather fill it in yourself? You can: see [Importing from another package or
Excel](importeren.en.md#filling-in-the-template).

## Converting with an AI assistant

1. In Huismus, open **Import**, choose **From another package or Excel** and
   click **Download template**.
2. Open an AI assistant, such as ChatGPT or Claude. This is an ordinary chat
   you add files to, not the connection under
   [AI assistants](ai-assistenten.en.md).
3. Add the template and all your files from Excel to the chat. Copy the
   instructions below and paste them in.

You do let that service read your books.

```text
I'm moving from Excel to Huismus. Convert my data to the Huismus import template.

What I'm giving you:
- the Huismus import template (a zip);
- my own spreadsheets from Excel or Numbers, and maybe the PDFs of my invoices and my receipts.

Where it goes:
- First look at which sheets and columns I have, and tell me how you want to map them to the template. Only start when I agree.
- If my invoices are only a total in a sheet, without lines, make one line per invoice with the amount per VAT rate.
- A PDF of an invoice → the folder for PDFs of invoices.

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
year under **Reports › Year overview** with your own spreadsheets.
