# Import bank statement

Download the statement of your bank account and import it into Huismus.
Huismus looks at which invoices were paid and records the payments that are
certain. Your bank details stay on your own computer: Huismus doesn't
connect to your bank.

## How to import a statement

1. Download a statement from your bank as **CAMT.053** or **MT940**. Below is
   where each bank keeps it.
2. In Huismus, go to **Bank**.
3. Drag the file into the box, or click **Choose file**. A zip with more
   statements works too.
4. Click **Import**.

At your bank, choose the period since last time. If it overlaps with a
statement you already imported, that's fine: importing the same statement
again changes nothing.

## What Huismus does

For now Huismus only looks at money that came in. It counts money going
out, but doesn't link it to your expenses yet. It lays every incoming payment
next to your invoices that are still open.

At the top you see what was in the statement: how many payments, how many of
them belong to your invoices, and what came in. Below that are three
sections, each of which you can fold open and shut.

- **To do.** Does an invoice fit, but not for certain? For example the number
  is right but the amount isn't, or the amount and the name are right but
  there is no number. Then Huismus proposes that invoice. Click **Confirm**,
  or choose an **Other invoice**. Do several invoices fit? Then pick one
  yourself and click **Record**. Or click **Skip**.
- **Recorded.** Is the invoice number in the description and the amount
  exactly what is open? Then Huismus records the payment itself. Had you
  recorded the payment yourself already, it says "was already booked" and
  Huismus doesn't record it again.
- **Not recognised.** Does no invoice fit at all? Then it's often private, or
  money from your savings account. This section stays shut: you don't need to
  do anything with it. Is it a customer's payment after all? Open it, click
  **Mark as invoice payment** and choose the invoice.

Do you use your account privately too? Then most of it is under **Not
recognised**. That's fine.

What is under **To do** stays on the page, also when you come back later.
On the overview it's at the top of **To do**.

Does one transfer mention more than one invoice? Then record the payment on
each invoice yourself, with **Record payment**, and skip the line here.

## Undoing a payment

Is a payment wrong after all? Click **Undo**, on the statement page or on the
invoice itself. The payment goes away and the line is back under **To do**. Huismus never undoes a payment you recorded yourself.

A line you skipped is under **Skipped**. **Restore** puts it back on the
page.

Paid in cash? That's not on your statement. Mark the invoice as paid
yourself.

Huismus keeps every statement you import. It goes into your backups.

## Where to find the statement

This is what the banks call it themselves (checked on 20 November 2026; the
menus are in Dutch). Choose **CAMT.053** if your bank has it, otherwise
**MT940**.

- **ING:** with a business account, in <span lang="nl">Mijn ING Zakelijk</span>. A personal ING
  account only gives CSV and PDF. Huismus doesn't read those; record a payment
  on the invoice instead.
- **Rabobank:** **<span lang="nl">Transacties downloaden</span>** › your account › choose the
  format CAMT.053 and the period › **<span lang="nl">Downloaden</span>**. "<span lang="nl">Vanaf de laatste
  download</span>" works too.
- **ABN AMRO:** **<span lang="nl">Zelf regelen</span>** › **<span lang="nl">Bij- en afschrijvingen
  downloaden</span>** › account › period › CAMT.053. In the app: <span lang="nl">Profiel › Rekeningen en
  betalen › Afschriften en jaaroverzicht</span>.
- **bunq:** Profile › Accounting › **Export Statement**, and choose MT940. bunq
  has no CAMT.053.
- **Knab, Triodos:** download the transactions as CAMT.053.
- **SNS, ASN, RegioBank:** **<span lang="nl">transacties downloaden</span>** (RegioBank: **<span lang="nl">Bij- en
  afschrijvingen downloaden</span>**) › CAMT.053 › **<span lang="nl">Downloaden</span>**. You get a zip;
  no need to unpack it.
- **Revolut Business:** Statements › Account statement › choose your euro
  account, the period and XML (CAMT.053) › **Generate**.

Huismus only reads amounts in euros.
