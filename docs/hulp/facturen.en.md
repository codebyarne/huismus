# Invoices

You make an invoice as a draft first. Only when you issue it does it get a
number and become fixed. After that you keep track of what's been paid, and
you correct with a credit note.

## Making an invoice

Click **New invoice**. Choose a customer, or add one right there with
**+ New customer**. Then fill in the lines: a description, the quantity, the
unit and the price. Huismus works out the total as you type.

**Save draft** keeps it so you can carry on later. You can change a draft as
often as you like, or delete it. **Preview PDF** shows what the invoice will
look like.

If you leave the due date empty, Huismus uses the customer's payment term, or
otherwise the one from your settings.

### Prices including VAT

Do you give your customer a price with VAT in it? Then turn on **Prices
include VAT** above the lines. The total is then exactly what you enter, and
Huismus works out the VAT per rate inside it. The PDF then shows the prices
with VAT, and below them the amount without VAT, the VAT and the total.

Want this for every new invoice and quote? Turn on **Prices include VAT by
default** under **Settings → VAT**. You can still change it per invoice. You
only see this choice if you charge VAT.

## Products

Do you use the same line often, like an hour of advice or a workshop? Save it
as a product: on **Invoices**, click **Products**. You fill in a description,
unit, price and VAT rate. The price is without VAT.

In an invoice or quote you then pick a product under **Add product**, and the
line is there, with quantity 1. After that it's an ordinary line: you change
it like any other. If you later change or delete a product, your invoices and
quotes stay as they are.

Under the small business scheme (KOR), or without VAT, Huismus doesn't ask
for a VAT rate for a product.

## Issuing

Ready? Click **Issue…**. You first see a summary: the customer, the amount and
the number the invoice will get. With **Issue for good**:

- the invoice gets the next number, with no gaps in the series;
- Huismus records your business details and the customer's as they are now.
  If you change an address later, the invoice stays as you sent it;
- the invoice is fixed. You can't change or delete it anymore.

Then download the PDF with **PDF**, or mail it with **Mail**. See
[Mail](mailen.en.md).

## Carrying on from another bookkeeping app

Coming from another bookkeeping app? Then you want your numbers to carry on.
Go to **Settings → Invoices and numbering** and under **Sequence number of
your next invoice** enter the number that follows your last invoice. If your
last invoice was 2026-0042, enter 43. Quotes work the same way.

You can do this until your first invoice in Huismus. After that the number
counts up by itself, so your series has no gap.

## Payments

The invoice shows its payment status: unpaid, partly paid, paid or overdue.
When a payment comes in, click **Record payment**. The amount is already
filled in with what's still open. A partial payment works too.

Many payments at once? Import your bank statement and Huismus records them
itself. See [Import bank statement](bankafschrift.en.md).

The overview shows how much is open in total and which invoices are late.

## Sending a reminder

When an invoice is late, the invoice shows by how many days, and **Send
reminder** is at the top. You get a mail with the invoice attached and a
text that says what's still open. Change what you like and click **Send**.
After that, the invoice shows when you sent the last reminder. Huismus never
sends a reminder by itself. You set the text under [Mail](mailen.en.md).

## Correcting something

You don't change an issued invoice anymore. If something's wrong, make a
credit note with **Create credit note…**. That's an invoice with negative
amounts that undoes the old one, in full or in part. Huismus starts with the
same lines as the invoice, or with an empty credit note if you're crediting
only part of it. Then make a new invoice if you need one.

Did you just make a mistake and haven't sent the invoice yet? **Edit anyway…**
turns it back into a draft, with the same number. Huismus asks you to confirm
first. **Cancel** in the draft takes you back to the invoice as it was.

## Copying

Sending the same invoice once more? Open the last one and click **Copy**. You
get a new draft with the same customer and lines.

## Recurring

Do you send the same invoice every month, quarter or year? Open an issued
invoice and click **Make recurring…**. Choose how often, and on which day the
next one should be ready.

On that day a draft is ready for you, with the same customer and lines. It
appears when you open Huismus on or after that day, and you see it under **To
do** on the Overview. Huismus never issues it by itself: you check it and click
**Issue…**. Only then does it get a number and that day's date. If Huismus was
closed for a while, there is a draft for every time you missed.

Each new draft is a copy of the previous invoice in the series. Raise the
price in a draft, and the next one has it too.

Under **Invoices** › **Recurring** you see everything that comes back. There
you change how often and the next date, or click **Stop…**. What is already
there stays.

## Searching and sorting

At the top of the list you search by number or customer and pick a year. The
list starts with what is overdue and ends with what is paid. Click a column,
such as **Customer** or **Amount**, to sort by it; click again to turn the
order round, and a third time for the usual order. The usual order is the one
by **Status**; click it to turn the list round. On a phone, use **Sort**.
Quotes and Customers work the same way.
