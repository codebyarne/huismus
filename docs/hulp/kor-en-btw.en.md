# Small business scheme (KOR) and VAT

Huismus works with and without the small business scheme (KOR). If you use the
KOR, your invoices carry no VAT. If you do charge VAT, you choose the rate per
line.

You set it up under **Settings → VAT**. There you answer **Do you charge
VAT on your invoices?** with **Yes**, **No, I use the KOR** or **No, for
another reason**.

## With the KOR

You can use the KOR if you're based in the Netherlands, your revenue in a
calendar year stays at or below € 20,000 and your work is subject to VAT. For
the exact conditions, see the [Belastingdienst](https://www.belastingdienst.nl/wps/wcm/connect/nl/btw/content/kor-voorwaarden) (in Dutch).

Choose **No, I use the KOR** and fill in your **KOR text**. That text goes under
every new invoice. Huismus doesn't suggest a text: you write it yourself.
While the KOR is on, Huismus won't issue an invoice without it.

Every line then has 0% VAT.

### The KOR limit

Under **KOR limit**, fill in the revenue amount you want to keep an eye on.
The overview shows how much of it you've used this year. From the percentage
you choose, you get a warning there. If a new invoice takes you past that
percentage, Huismus already tells you when you issue it.

## No VAT for another reason

Do you charge no VAT, but not because of the KOR? That's mostly when your
work is exempt from VAT. The Belastingdienst lists, among others, healthcare,
education, childcare, sports clubs, social and cultural institutions,
financial services and insurance, and composers, writers, cartoonists and
journalists. Each exemption has its own conditions: look up your work in the
[Belastingdienst's list](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/tarieven_en_vrijstellingen/vrijstellingen/) (in Dutch). Do you have several clients? Then
check per assignment whether the exemption applies.

If your work is exempt:

- you charge your customers no VAT;
- you file no VAT return on that revenue, with a few exceptions;
- you don't deduct the VAT on your costs.

Source: [Exempt goods or services](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/tarieven_en_vrijstellingen/vrijstellingen/wat_moet_u_doen_als_u_vrijgestelde_goederen_of_diensten_levert)
(Belastingdienst, in Dutch).

Someone who isn't an entrepreneur for VAT charges no VAT either. You're an
entrepreneur if you work independently and earn income from it. The
Belastingdienst tells you whether you're an entrepreneur for VAT after you
register with the KVK. See
[Ondernemer voor de btw](https://www.belastingdienst.nl/wps/wcm/connect/bldcontentnl/belastingdienst/zakelijk/btw/hoe_werkt_de_btw/voor_wie_geldt_de_btw/ondernemer) (in Dutch).

Under **Settings → VAT**, choose **No, for another reason** and fill in the
**No-VAT text**. It goes under every new invoice. For exempt work, say that an
exemption applies, for example "Vrijgesteld van btw." (exempt from VAT). The
Belastingdienst prescribes no fixed wording. Without that text, Huismus won't
issue an invoice.

Every line then has 0% VAT. As with the KOR, the VAT return report has no
amounts, the VAT on your expenses counts nowhere and you see your costs with
VAT. There is no KOR limit.

Do you have work with and without VAT side by side? Then you keep VAT
records and file VAT returns. Huismus can't do that yet.

## With VAT

Choose **Yes**. You then choose 0, 9 or 21% VAT per line. A new line starts
at 21%. Fill in your VAT number under **Settings → Business**, and it goes on
your invoices.

Under the invoice you see the VAT per rate, for example "21% VAT € 210.00",
on screen and in the PDF.

### Reverse charge

For a line where the VAT is reverse charged, choose **reverse charge** instead
of a rate. The line counts as 0%, and the invoice says "reverse charge". Also
fill in the **Reverse charge text** under **Settings → VAT**. It goes at the
bottom of the invoice. Without that text, Huismus won't issue such an
invoice.

If the customer has a VAT number in Huismus, it goes under their address on
the invoice.

## Revenue

Revenue in Huismus is always without VAT: on the overview, on the year
overview and for the KOR limit. What's open and what's been paid includes
VAT, because that's what your customer pays.

## Costs and input VAT

Huismus always keeps an expense with the amount you paid.

With the KOR off, the year overview shows your costs excluding VAT, and the
VAT on your expenses apart, as **Input VAT**. It goes per line: at 21%, 9% or
0% the VAT you filled in counts as input VAT and the rest as costs. With
reverse charge, and on a line without a rate, the whole amount counts as
costs. With the KOR on, you see the costs including VAT, as always.

## VAT return

Under **Reports → VAT return** you see, per quarter, month or year, the
revenue and VAT from your invoices and expenses, per box, and what you pay or
get back. You copy the amounts into your return yourself; Huismus sends
nothing.

Huismus counts issued invoices and credit notes on their invoice date, and
expense lines with a VAT rate on the date of the receipt. A service to a
business in another EU country (box 3b) counts on the delivery date, if you
filled one in on the invoice. What it can't count is listed at the bottom under **Not counted**, with a
link. There you fill it in or take it along yourself.

With **Download CSV** you get the same as a file for Excel or Numbers: the
boxes, what you pay or get back, and what isn't counted. An
[AI assistant](ai-assistenten.en.md) can read the report too. With the KOR
on, the report has no amounts and there is no CSV.

You can also download an export for your accountant. See
[Exporting](exporteren.en.md).

## A credit note and a copy

A credit note keeps the rates of the invoice it credits. If you copy an
invoice or convert a quote while the KOR is on, the new invoice starts at 0%.
