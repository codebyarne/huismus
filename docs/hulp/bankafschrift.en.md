# Import bank statement

Download the statement of your bank account and import it into Huismus.
Huismus looks at which invoices were paid and records the payments that are
certain. Your bank details stay on your own computer: Huismus doesn't
connect to your bank.

## How to import a statement

1. Download a statement from your bank as **CAMT.053** or **MT940**. Below is
   where each bank keeps it.
2. In Huismus, go to **Invoices** and click **Import bank statement**.
3. Drag the file into the box, or click **Choose file**. A zip with more
   statements works too.
4. Click **Import**.

At your bank, choose the period since last time. If it overlaps with a
statement you already imported, that's fine: importing the same statement
again changes nothing.

## What Huismus does

Huismus only looks at money that came in. It lays every incoming payment
next to your invoices that are still open.

- **Recorded.** Is the invoice number in the description and the amount
  exactly what is open? Then Huismus records the payment itself.
- **Is this right?** Does exactly one invoice fit, but not for certain? For
  example the number is right but the amount isn't, or the amount and the
  name are right but there is no number. Then Huismus proposes that invoice.
  Click **Confirm**, or choose an **Other invoice**.
- **Pick an invoice.** Does no invoice fit, or more than one? Then pick the
  invoice yourself and click **Record**, or click **Skip**. **Skip all** skips
  them in one go.
- **Already recorded.** Had you recorded the payment yourself already? Then
  Huismus doesn't record it again.

What still waits for you stays on the page, also when you come back later.
On the overview it's at the top of **To do**.

Does one transfer mention more than one invoice? Then record the payment on
each invoice yourself, with **Record payment**, and skip the line here.

## Undoing a payment

Is a payment wrong after all? Click **Undo**, on the statement page or on the
invoice itself. The payment goes away and the line is back under **Pick an
invoice**. Huismus never undoes a payment you recorded yourself.

A line you skipped is under **Skipped**. **Restore** puts it back under
**Pick an invoice**.

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
