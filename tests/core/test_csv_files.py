# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one CSV form of Huismus (SPEC.md M19): semicolons, a decimal comma,
ISO dates and UTF-8 with a BOM, so Dutch Excel opens it."""

from datetime import date
from decimal import Decimal

import pytest

from huismus.core.csv_files import Amount, csv_bytes, csv_response


@pytest.mark.parametrize(
    ("cents", "text"),
    [
        (1000, "10,00"),
        (5, "0,05"),
        (-9339, "-93,39"),
        (-5, "-0,05"),
        (0, "0,00"),
        (123456789, "1234567,89"),
    ],
)
def test_amounts_have_a_decimal_comma_and_no_thousands_separator(cents, text):
    # Rule 1: money is integer cents, also on its way out.
    assert csv_bytes(["bedrag"], [[Amount(cents)]]).decode("utf-8-sig").splitlines()[1] == text


def test_values_dates_quantities_and_empty_cells():
    rows = [[date(2026, 11, 2), Decimal("2.500"), Decimal("1.000"), None, "a;b", 7]]
    line = csv_bytes(["a", "b", "c", "d", "e", "f"], rows).decode("utf-8-sig").splitlines()[1]
    assert line == '2026-11-02;2,5;1;;"a;b";7'


def test_starts_with_a_bom_and_uses_semicolons():
    raw = csv_bytes(["één", "twee"], [])
    assert raw.startswith("﻿".encode())
    assert raw.decode("utf-8-sig").splitlines() == ["één;twee"]


def test_the_response_is_a_download():
    response = csv_response("jaaroverzicht-2026.csv", ["a"], [[Amount(1)]])
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    assert response["Content-Disposition"] == 'attachment; filename="jaaroverzicht-2026.csv"'
