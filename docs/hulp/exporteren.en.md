# Exporting

Want to use your administration outside Huismus, for your accountant or in
a spreadsheet? Download an export: one ZIP with your invoices, quotes,
customers and expenses as CSV, with the PDFs and receipts. You can open it
without Huismus.

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
- **expenses.csv** and **expense-lines.csv**: your expenses, and the
  category per line.
- **pdf/invoices**, **pdf/credit-notes** and **pdf/quotes**: every PDF,
  named after its number. It's the same PDF **Download** gives you. For an
  invoice from Moneybird, that's the original PDF.
- **receipts**: every receipt, with the expense's number in front.

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

## Opening it in a spreadsheet

The CSVs use a semicolon between columns and a comma in amounts
("1234,56"), without a separator for thousands. Dates look like 2026-11-02.
Excel and Numbers in Dutch open them right away. A spreadsheet in English
may ask which separator to use: choose the semicolon.

If a text starts with `=`, `+`, `-` or `@`, Huismus puts a `'` in front.
Otherwise a spreadsheet takes it for a formula and runs it.

An export isn't a backup. You restore a backup into Huismus; an export is
for using your data somewhere else. How backups work is explained in
[Backups](back-ups.en.md).
