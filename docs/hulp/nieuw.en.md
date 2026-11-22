# What's new

A new version of Huismus comes out about every two weeks. Here you read, per
version, what you can do with it now. The newest is at the top.

After a new version, a notice on the overview points you here.

## 0.1.7, 22 November 2026

- **Import your bank statement.** Under **Bank** you import a statement as
  CAMT.053 or MT940. Huismus puts each payment in next to your open invoices,
  and each payment out next to your expenses. What is certain, Huismus books
  itself. When Huismus isn't sure, it's under **To do**. Is an expense not in
  Huismus yet? Click **Create expense** on the line. Huismus doesn't connect
  to your bank. How it works:
  [Import bank statement](bankafschrift.en.md).
- **No VAT for another reason.** Is your work exempt from VAT? Under
  **Settings → VAT**, choose **No, for another reason** and fill in the text
  that goes under your invoices. See
  [Small business scheme (KOR) and VAT](kor-en-btw.en.md#no-vat-for-another-reason).
- **Getting started asks about your work first.** Under **Start step by
  step** you answer three questions: do you charge VAT, do you have customers
  where VAT is reverse charged, and in which language you make your invoices.
  After that, only the steps that fit you come.
- **Give feedback from every page.** At the bottom right is the **Feedback**
  button. With **Point at the screen** you show where it is. Names and
  amounts become grey bars, and before you send you see everything that goes
  along.
- **Switching from another package or Excel.** Under **Import → From another
  package or Excel** you download a template, fill it in and import
  everything at once, with a trial run first. How to get your data out of
  Rompslomp, Tellow, e-Boekhouden.nl, Jortt or Excel is in
  [Moving to Huismus](overstappen.en.md), and that tab links to it. An export
  from Huismus imports this way too.
- **A new category on your expense.** Type its name in the **Category**
  field. Huismus makes it when you save. If you have your receipts read,
  Huismus chooses the category too.
- **On your phone** you choose first for a new expense: **Take a photo**,
  **Choose a photo or file** or **Without a receipt**. Huismus makes a photo
  smaller first, so it's sent quickly.
- **Moving to a new computer.** A new help page says what you take along and
  what you set up again: [Moving to a new computer](nieuwe-computer.en.md).
- **The sparrow hops** while Huismus is busy: when receipts come in, a backup
  runs, or the app starts or updates.
- **Your mail password is missing.** When you restore a backup on another
  computer, your mail password doesn't come along. The mail screen now says
  so, with a link to **Settings → Mail**. Before, it said mailing wasn't set
  up yet.
- **Choose your legal form.** Under **Settings → Business** and in **Start
  step by step** you choose your legal form: sole proprietorship,
  partnership, bv and so on. It doesn't go on your invoices.
- **Safer importing.** In an import with the template, only a PDF or a photo
  becomes a receipt. A zip of bank statements that is larger than 200 MB
  unpacked, Huismus refuses with a message.

## 0.1.5, 18 November 2026

- **A new, clear look.** Huismus is lighter and calmer: the menu stands on its
  own, your work is on one white sheet, and on each screen one thing stands out.
  With a new logo: a white sparrow on a petrol tile.
- **The overview says what to do.** At the top is **To do**: an invoice that is
  overdue, a quote waiting for an answer, a draft that is ready. Below it your
  revenue per month, what you still have to receive, and with the small business scheme (KOR) how much
  still fits under your limit.
- **Send a payment reminder.** For an overdue invoice, choose **Send reminder**.
  It goes through your own email, with the invoice attached. The invoice also
  says how many days overdue it is.
- **Sort your lists.** Sort Invoices, Quotes, Expenses and Customers by any
  column.
- **Expired quotes.** A sent quote past its date reads **Expired** everywhere.
- **Photo first.** When you use Huismus on your phone, a new expense starts with
  the camera.
- **Choose your next number.** Under **Settings → Invoices and numbering** you
  set the next invoice and quote number yourself, as long as Huismus hasn't
  issued one yet. Handy when you come from somewhere else.
- **Everything Huismus does** is now on the site, with what comes later. You
  find the link at the bottom of **Help**.

## 0.1.4, 13 November 2026

- **Receipts on the road.** Save a photo of a receipt on your phone in your
  receipts folder. Huismus fetches it, and the overview shows, for example,
  **2 new receipts**. Choose the folder under **Settings → Receipts folder**:
  a folder in iCloud Drive, Google Drive, OneDrive or Dropbox, or in Docker
  Dropbox or WebDAV. Photos from an iPhone (HEIC) work too. How it works:
  [Receipts on the road](bonnetjes.en.md).
- **Process them all in one go.** With **Process** you go through the receipts
  without an expense one by one, with the receipt large beside the fields.
  After **Save** or **Looks right**, the next receipt comes up.
- **Huismus reads your receipts itself**, if you want. Under **Settings →
  Reading receipts with AI**, choose an AI service with your own key, or Ollama
  on your own computer. Each new receipt then becomes an expense marked
  **To check**. What an AI assistant fills in is marked **To check** too.
- **The VAT return.** Under **Reports → VAT return** you see, per quarter,
  month or year, what goes in each box, and what you pay or get back. **Download
  CSV** gives you the same as a file. You copy the amounts over yourself;
  Huismus sends nothing. How it works: [Small business scheme (KOR) and VAT](kor-en-btw.en.md#vat-return).
- **VAT per expense line.** With the KOR off, you choose the VAT rate for each
  expense line. The year overview then shows your costs without VAT and the
  input VAT apart. When importing from Moneybird, Huismus takes the rate along
  when its name says it plainly.
- **Help in groups**, so you find what you need faster.
- **After a new version** the overview says once that Huismus was updated,
  with a link to this page. **Check now** under **Settings → Updates** looks
  for a new version right away.
- **The Mac app now needs macOS 15 (Sequoia) or newer.** Still on macOS 14?
  Update your Mac in **System Settings → General → Software Update**. Your
  records stay where they are.
- **Smaller improvements.** An invoice line sits on one row. A wide table
  scrolls inside its card instead of being cut off. An error page says in
  plain words what went wrong, without an error code.

## 0.1.3, 4 November 2026

- **Choose the receipt right away for a new expense.** You no longer have to
  save the expense first. The receipt is now at the top of the form, since you
  usually type the rest from it. On an existing expense, the receipts are above
  the form.
- **The + on your phone** now lets you choose: Invoice, Quote, Customer or
  Expense, just like **New** on a computer. It used to make only an invoice.
- **What's new** is under **Help**: per version, what you can do with it, like
  this page. The notice about a new version links to it too.
- **No more lost backups in the cloud.** When two backups were sent to Dropbox or
  WebDAV in the same second, for example when you linked it again quickly, the
  second one overwrote the first. Now both stay.

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
