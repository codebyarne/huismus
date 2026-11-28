# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers (#125): reading what someone types, and showing it.

A trip's distance has one decimal at most: "12", "12,5" or "12.5", in both
languages. More decimals are an error, never rounded away (product-owner
agent 2026-11-28, huismus-intern/besluiten.md, "Kilometerregistratie
(#125)"). Huismus works out no allowance: kilometers are no money, so none
of the money rules apply here.

km_text is the one way a distance is shown: in the list, its totals and
on the year overview.
"""

import re
from collections.abc import Iterable
from decimal import Decimal

from django.utils import formats

ONE_PLACE = Decimal("0.1")

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


def km_text(km: Decimal) -> str:
    """ "12 km", "12,5 km", "1.842 km"; in English "1,842 km". No ",0"
    behind a whole number."""
    km = Decimal(km)
    places = 0 if km == km.to_integral_value() else 1
    number = formats.number_format(km, decimal_pos=places, use_l10n=True, force_grouping=True)
    return f"{number} km"


def total_km(distances: Iterable[Decimal]) -> Decimal:
    return sum(distances, Decimal(0))
