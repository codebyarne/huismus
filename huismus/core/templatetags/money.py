# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template

register = template.Library()


@register.filter
def euros(cents):
    """Integer cents -> "12.345,67"-style display (SPEC.md principle 2:
    money is stored as integer cents; this is display-only, never used to
    feed a calculation back in)."""
    if cents is None:
        return ""
    negative = cents < 0
    whole, remainder = divmod(abs(cents), 100)
    formatted = f"{whole:,}".replace(",", ".")
    return f"{'-' if negative else ''}{formatted},{remainder:02d}"


@register.filter
def money(cents):
    """Integer cents -> "€ 1.815,00" / "− € 93,39", the notation of the M8
    design. Display-only, like euros(): a real minus sign, and non-breaking
    spaces so an amount never wraps."""
    if cents is None:
        return ""
    formatted = f"€\u00a0{euros(abs(cents))}"
    return f"\u2212\u00a0{formatted}" if cents < 0 else formatted


@register.filter
def whole_euros(cents):
    """Integer cents -> "€ 8.000", for chart axes: whole euros, rounded
    down. Display-only."""
    if cents is None:
        return ""
    return f"€ {cents // 100:,}".replace(",", ".")
