# Importing from another package or Excel

Are your books in another package than Moneybird, or in Excel? Then you put
your customers, invoices, quotes and expenses into Huismus's template and
import them in one go. Huismus does a trial run first and only saves something
when you choose to.

The import is meant for a Huismus that is still empty, or new. It doesn't
change what is already there.

## Filling in the template

1. Open **Import** and choose **From another package or Excel**.
2. Click **Download template**. You get a zip with seven CSV files and a
   README.
3. Open the files in Excel or Numbers. Each file holds one example. Replace
   it with your own data and keep the first row with the column names.
4. Remove a file you don't need. A column you don't need can go too, except
   the required ones below.
5. Make one zip of it again and drag it to the box. Click **Start trial run**.

Huismus skips an example you leave in.

## What the trial run shows

The trial run saves nothing. Per file you see what Huismus recognises, how many
customers, invoices, quotes and expenses are new, and what is wrong:

- **Refused**: an invoice whose revenue or VAT per rate differs from its
  lines, or an expense that isn't the sum of its lines. It doesn't come into
  Huismus. Correct the file and try again.
- **Skipped**: an invoice without lines, or for a customer number that is
  not in the customer file and not in Huismus.
- **Amounts differ from the lines**: the total in the file differs from what
  the lines add up to. Huismus takes the total from the file and names the
  difference.
- **Maybe double**: if there are expenses in Huismus already, the ones from
  the file are added. When a new expense has the same date and amount as an
  existing one, the trial run names it. Huismus does import it; if it is
  double, delete it afterwards.
- **Without a VAT rate**: if you don't use the
  small business scheme (KOR), Huismus only counts the
  VAT of an expense line in the VAT return report when the line has a VAT
  rate. The trial run says how many lines have none. You choose the rate on
  the expense afterwards.
- **Note**: a column Huismus doesn't know, or a PDF or receipt that belongs
  nowhere.

Fill in your business details under **Settings** first. An imported invoice
takes the business details of that moment.

If it looks good, click **Import now**. Import the same zip again later
and nothing changes.

## The files and their columns

Huismus recognises a file by its column names, not by its file name. The
names can be in Dutch or in English, as the template gives them. When a
required column is missing, the import stops and says which one.

- **customers.csv**: required are **customer number**, **company name** and
  **last name**. Every customer has a company name or a name.
- **contact-persons.csv**: the persons at a customer. Required: **customer
  number** and **name**.
- **invoices.csv**: one row per invoice and credit note. Required: **kind**
  (invoice or credit note), **number**, **invoice date**, **customer
  number**, **amount excl. VAT**, **VAT** and **total incl. VAT**. Write a
  credit note with negative amounts, with the number of the invoice it
  belongs to in **credited invoice**.
- **lines.csv**: the lines of your invoices, credit notes and quotes.
  Required: **kind**, **number**, **description**, **unit price** and **VAT
  rate (%)**. An empty **quantity** is a fixed price.
- **quotes.csv**: required are **number**, **date**, **customer number**,
  **status** (sent, accepted, declined or expired) and the three amounts.
- **expenses.csv**: required are **expense number**, **date** and **amount
  (gross)**. You choose the expense number yourself, for example 1, 2, 3.
- **expense-lines.csv**: only needed when an expense has more lines, or a
  category or VAT rate. Required: **expense number** and **amount (gross)**.

If you fill in **paid** and **last paid on** for an invoice, Huismus makes
one payment of it. Without a date Huismus makes no payment: the invoice is
then open, and the trial run names it.

## Amounts, dates and characters

- A semicolon separates the columns. Dutch Excel and Numbers do that by
  themselves when you save as CSV; in an English spreadsheet, choose the
  semicolon.
- Write an amount as 1234,56. Huismus also reads 1.234,56 and 1234.56.
- Write a date as 2026-03-14 or 14-03-2026. 14-3-2026 works too. Huismus
  doesn't read slashes or a two-digit year.
- Huismus imports euros only.

When Huismus can't read an amount or a date, the import stops and says in
which file, which row and which column.

## PDFs and receipts

Do you have the PDFs of your invoices? Put them in the zip in
**pdf/invoices**, **pdf/credit-notes** and **pdf/quotes**, with the number
as the name, for example `2025-0012.pdf`. Huismus keeps such a PDF as the
original with the invoice. Without a PDF Huismus makes it itself.

Put receipts in the folder **receipts**. In **expenses.csv**, put the file
name in the column **receipts**. Separate several receipts for one expense
with ` | `.

## Help from an AI assistant

An AI assistant can convert the export of your old package into the
template. Give it the template and your export, and ask it to fill the
files. You then let that service read your books. The trial run shows whether
the result is right: every total is checked to the cent.

For each package there's a guide with instructions you can copy as they are:
[Rompslomp](rompslomp.en.md), [Tellow](tellow.en.md),
[e-Boekhouden.nl](e-boekhouden.en.md), [Jortt](jortt.en.md) and
[Excel](excel.en.md).

## Importing an export from Huismus

The zip from **Settings → Export** has the same form as the template. That
is how you take your books to a new Huismus. What the export holds is under
[Export](exporteren.en.md).

Don't import an export into the Huismus it came from. Huismus recognises
invoices by their number, but your expenses would come in twice. To go back
to an earlier state, restore a backup: see [Backups](back-ups.en.md).

## What doesn't come along

- Drafts.
- Separate part payments: each invoice gets one payment.
- The customer's address at the time of the invoice. The invoice gets the
  customer's address of now. The original PDF still shows the old address.
- An invoice's language: every invoice gets the language from your
  settings.

Coming from Moneybird? There is an import of its own that reads Moneybird's
export as it is: see [Switching from Moneybird](moneybird.en.md).
