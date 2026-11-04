# What's new

A new version of Huismus comes out every Wednesday. Here you read, per
version, what you can do with it now. The newest is at the top.

## 0.1.2, 4 November 2026

- **The desktop app updates itself.** When there's a new version, Huismus
  fetches it in the background. The next time you open the app, it makes a
  backup first and then installs the new version. Don't want to wait? Choose
  **Settings → Updates → Update**.
- **Huismus in Docker tells you when there's a new version**, on the overview
  and in **Settings → Updates**. It also shows what to type to update. How it
  works: [Huismus in Docker](docker.en.md#updating).
- **A backup first, then the new version.** Before a new version in Docker
  updates your records, Huismus makes a backup. If something goes wrong, you
  still have it.

## 0.1.1, 4 November 2026

- **Start step by step** is now the main button when you open Huismus for the first
  time. Importing from Moneybird sits next to it.
- **Help for the everyday work.** Under Help you now read how to make
  invoices, quotes and expenses, how mailing works and how to export.
- **Restoring a backup is safer.** Huismus never takes the secret keys from
  the backup file. Those of your own installation stay.
- **Exporting to a spreadsheet is safer.** Text that starts like a formula,
  such as `=SUM(…)`, stays plain text in Excel or Numbers.
- **On the Mac, menus close again** after you pick something.

## 0.1.0, 2 November 2026

The first version. You make quotes, invoices and credit notes as PDFs and
mail them to your client. You keep track of your expenses, with receipts.
Under **Reports** you see your revenue per year and how far you are from the
KOR limit. Coming from Moneybird? Then you bring your whole export along. And
Huismus makes a backup every day: see [Backups](back-ups.en.md).
