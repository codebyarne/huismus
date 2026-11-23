# Exporting

Want to use your administration outside Huismus, for your accountant or in
a spreadsheet? Download an export: one ZIP with your invoices, quotes,
customers and expenses as CSV, the PDFs and receipts, and an audit file per
year. You can open it without Huismus.

## Downloading an export

Open **Settings → Export**. Choose **Everything** or one year and click
**Download ZIP**. On the **Year overview**, **Export →** takes you to the
same page with that year already chosen.

A year counts by invoice date, as on the year overview. An expense counts by
its own date. All customers are always included, archived ones too.

## What's in it

- **invoices.csv**: a row per invoice and credit note, with the customer as
  on the invoice, the amounts, revenue and VAT per rate, and whether it's
  paid.
- **quotes.csv**: a row per quote, with its status and the invoice it
  became.
- **lines.csv**: the lines of every invoice, credit note and quote.
- **customers.csv**: all your customers.
- **contact-persons.csv**: the contact persons at your customers.
- **expenses.csv** and **expense-lines.csv**: your expenses, and the
  category per line.
- **pdf/invoices**, **pdf/credit-notes** and **pdf/quotes**: every PDF,
  named after its number. It's the same PDF **Download** gives you. For an
  invoice from Moneybird, that's the original PDF.
- **receipts**: every receipt, with the expense's number in front.
- **auditfile-2025.xaf**: the year's audit file. Choose **Everything** and
  there's an audit file per year. See [The audit file](#the-audit-file).

Drafts aren't included. Neither is an invoice you turned back into a draft
with **Edit anyway**, until you issue it again.

## The amounts

A credit note is negative in the export. Add up a year's **amount excl.
VAT** column and you get the year overview's revenue.

Each VAT rate gets two columns, for example **revenue 21%** and **VAT 21%**.
Lines with VAT reverse charged go in **revenue reverse charge**. An invoice
from Moneybird with different VAT (from a discount, say) shows one "VAT" row
in Huismus. For such an invoice the columns per rate stay empty and only the
totals are filled in.

## The audit file

An audit file is the file an accounting program reads: your accountant or
another package gets your year in one go. Huismus makes it in version 4.0
(XAF), as the Dutch tax authority describes it on
[odb.belastingdienst.nl](https://odb.belastingdienst.nl/documentatie/xml-auditfile-financieel-xaf-4-0-3/).

It holds your customers, your invoices and credit notes, the payments and
your expenses, booked on a fixed chart of accounts. Revenue and costs are
the same as on the year overview. If you charge VAT, the VAT per box is the
same as on the VAT return report. Each expense category gets an account of
its own, with the category's name.

What isn't in it, because Huismus doesn't keep track of it:

- your bank balance, your equity and what you took out or put in privately;
- investments and depreciation;
- whether you paid an expense privately: every expense is set against the
  bank.

At the start of the year there's only what customers still owed you then.
The amount against it is on **Opening balance, to be allocated**; your
accountant allocates it. Entering a real
opening position comes later.

## Opening it in a spreadsheet

The CSVs use a semicolon between columns and a comma in amounts
("1234,56"), without a separator for thousands. Dates look like 2026-11-02.
Excel and Numbers in Dutch open them right away. A spreadsheet in English
may ask which separator to use: choose the semicolon.

If a text starts with `=`, `+`, `-` or `@`, Huismus puts a `'` in front.
Otherwise a spreadsheet takes it for a formula and runs it.

You can import an export again, into a new Huismus: see
[Importing from another package or Excel](importeren.en.md).

An export isn't a backup. You restore a backup into Huismus; an export is
for using your data somewhere else. How backups work is explained in
[Backups](back-ups.en.md).
