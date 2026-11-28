# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers (#125): what you type and how it is shown. Decided by the
product-owner agent on 2026-11-28 (huismus-intern/besluiten.md,
"Kilometerregistratie (#125)"): one decimal at most, never rounded
silently; "12 km", "12,5 km", "1.842 km" from one function."""

from decimal import Decimal

import pytest
from django.utils import translation
from hypothesis import given
from hypothesis import strategies as st

from huismus.mileage.trips import (
    TooPrecise,
    UnclearDistance,
    distance_text,
    km_text,
    parse_distance,
)


@pytest.mark.parametrize(
    ("text", "km"),
    [
        ("12", Decimal("12.0")),
        ("12,5", Decimal("12.5")),
        ("12.5", Decimal("12.5")),
        (" 7,0 ", Decimal("7.0")),
        (",5", Decimal("0.5")),
        ("2000", Decimal("2000.0")),
        ("0", Decimal("0.0")),  # a number: the form says it must be more than 0
    ],
)
def test_parse_distance(text, km):
    assert parse_distance(text) == km


@pytest.mark.parametrize("text", ["", " ", "km", "12 km", "1.234,5", "1,2,3", "-4", "1:30", "."])
def test_what_is_no_distance(text):
    with pytest.raises(UnclearDistance):
        parse_distance(text)


@pytest.mark.parametrize("text", ["12,55", "0.05", "3,000"])
def test_more_than_one_decimal_is_refused_not_rounded(text):
    with pytest.raises(TooPrecise):
        parse_distance(text)


@given(st.decimals(min_value=0, max_value=2000, places=1))
def test_what_is_shown_reads_back_as_the_same_distance(km):
    with translation.override("nl"):
        shown = km_text(km)
    shown = shown.removesuffix(" km").replace(".", "")
    assert parse_distance(shown) == km


@pytest.mark.parametrize(
    ("km", "nl", "en"),
    [
        (Decimal("12.0"), "12 km", "12 km"),
        (Decimal("12.5"), "12,5 km", "12.5 km"),
        (Decimal("1842.0"), "1.842 km", "1,842 km"),
        (Decimal("123456.7"), "123.456,7 km", "123,456.7 km"),
        (Decimal("0.1"), "0,1 km", "0.1 km"),
        (Decimal("0"), "0 km", "0 km"),
    ],
)
def test_km_text(km, nl, en):
    with translation.override("nl"):
        assert km_text(km) == nl
    with translation.override("en"):
        assert km_text(km) == en


def test_a_form_field_has_no_thousands_so_it_reads_back():
    with translation.override("nl"):
        assert distance_text(Decimal("1842.5"), grouping=False) == "1842,5"
    with translation.override("en"):
        assert parse_distance(distance_text(Decimal("1842.5"), grouping=False)) == Decimal("1842.5")
