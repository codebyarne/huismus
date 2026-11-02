# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _

from huismus.documents import listing

register = template.Library()

PAYMENT_STATE_LABELS = {
    "unpaid": _("onbetaald"),
    "partial": _("deels betaald"),
    "paid": _("betaald"),
    "credited": _("gecrediteerd"),
}


@register.filter
def payment_state_label(state):
    return PAYMENT_STATE_LABELS.get(state, "")


@register.filter
def contact_name(document):
    return listing.contact_name(document)


# Quote status -> pill class in huismus.css (§7).
QUOTE_PILLS = {
    "draft": "concept",
    "sent": "sent",
    "accepted": "accepted",
    "declined": "rejected",
    "expired": "expired",
}


@register.filter
def quote_pill(status):
    return QUOTE_PILLS.get(status, "concept")


@register.filter
def money_for(cents, document):
    """money(), with a minus sign for a credit note: its amounts are stored
    as positive cents (SPEC.md M8) but shown as money going back."""
    from huismus.core.templatetags.money import money

    if cents is None:
        return ""
    return money(-cents if document.kind == "credit_note" else cents)


@register.filter
def get(mapping, key):
    """mapping[key] in a template, None when missing."""
    return mapping.get(key)


@register.filter
def plain_quantity(value):
    """A stored quantity for reading: Decimal("4.000") -> "4",
    Decimal("2.500") -> "2,5" (in Dutch)."""
    from django.utils.formats import number_format

    from huismus.documents.forms import _plain_quantity

    if value is None:
        return ""
    return number_format(_plain_quantity(value))


@register.filter
def line_quantity(line):
    """A line's quantity as the PDF's first column shows it: "2,5 uur", or
    "3 x" without a unit. Empty for a line that counts once (no quantity,
    or 1 without a unit), as in Moneybird, whose import stores 1 for those."""
    if line.quantity is None or (line.quantity == 1 and not line.unit):
        return ""
    return f"{plain_quantity(line.quantity)} {line.unit or 'x'}"


@register.filter
def has_quantities(lines):
    """Whether any line shows a quantity, so the PDF makes room for them."""
    return any(line_quantity(line) for line in lines)


@register.filter
def iban(value):
    """ "NL91ABNA0417164300" -> "NL91 ABNA 0417 1643 00", for reading."""
    compact = (value or "").replace(" ", "")
    return " ".join(compact[i : i + 4] for i in range(0, len(compact), 4))


@register.filter
def tax_percent(basis_points):
    """VAT in basis points -> "21%" or "5,5%" (in Dutch); see documents.vat."""
    from huismus.documents.vat import rate_label

    return rate_label(basis_points)


@register.filter
def line_vat(line):
    """A line's VAT column: "21%", or "verlegd" for reverse charge (M18)."""
    if line.reverse_charge:
        return gettext("verlegd")
    return tax_percent(line.tax_rate_bp)


@register.filter
def subtract(cents, other_cents):
    """cents − other_cents, for amounts that are a plain difference of two
    stored values ("Nog te crediteren" = invoice total − credited)."""
    return (cents or 0) - (other_cents or 0)
