# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers (#125): reading what someone types, and showing it.

A trip's distance has one decimal at most: "12", "12,5" or "12.5", in both
languages. More decimals are an error, never rounded away (product-owner
agent 2026-11-28, huismus-intern/besluiten.md, "Kilometerregistratie
(#125)"). Huismus works out no allowance: kilometers are no money, so none
of the money rules apply here.

distance_text is the one way a distance is shown: in the list, its
totals, the year overview and the form field.
"""

import re
from decimal import Decimal

from django.utils import formats

# "12", "12,5", ",5": one separator at most, no thousands, no sign.
_DECIMAL = re.compile(r"^(\d*)(?:[.,](\d+))?$")


class UnclearDistance(ValueError):
    """What was typed is no number of kilometers."""


class TooPrecise(ValueError):
    """More than one decimal."""


def parse_distance(text: str) -> Decimal:
    """The kilometers in `text`, with one decimal. Whether the number is
    allowed (more than 0, at most 2.000) is the form's to say."""
    match = _DECIMAL.match((text or "").strip())
    if not match or not (match.group(1) or match.group(2)):
        raise UnclearDistance(text)
    whole, fraction = match.groups()
    if fraction and len(fraction) > 1:
        raise TooPrecise(text)
    return Decimal(f"{whole or 0}.{fraction or 0}")


def distance_text(km: Decimal, *, grouping: bool = True) -> str:
    """ "12", "12,5", "1.842"; in English "1,842". No ",0" behind a whole
    number. Without grouping for a form field ("1842"), which
    parse_distance reads back."""
    km = Decimal(km)
    places = 0 if km == km.to_integral_value() else 1
    return formats.number_format(km, decimal_pos=places, use_l10n=True, force_grouping=grouping)


def km_text(km: Decimal) -> str:
    """ "12 km", "12,5 km", "1.842 km"; in English "1,842 km"."""
    return f"{distance_text(km)} km"
