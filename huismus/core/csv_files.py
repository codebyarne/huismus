# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The one CSV form of Huismus (SPEC.md M19), for the export and the year
overview: semicolons, a decimal comma without thousands separators
("1234,56", "-93,39"), ISO dates and UTF-8 with a BOM, so Dutch Excel and
Numbers open it as columns. The same in both languages, as amounts in the
app are always written the Dutch way."""

import csv
import io
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from django.http import HttpResponse


@dataclass(frozen=True)
class Amount:
    """Integer cents in a cell, so they aren't mistaken for a plain number."""

    cents: int


def _amount(cents: int) -> str:
    # From the integer: no float on the way out either (invariant 1).
    sign = "-" if cents < 0 else ""
    whole, remainder = divmod(abs(cents), 100)
    return f"{sign}{whole},{remainder:02d}"


def _decimal(value: Decimal) -> str:
    """2.500 -> "2,5", 1.000 -> "1": without the zeros a quantity is stored with."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text.replace(".", ",")


# A cell starting with one of these is a formula to Excel and Numbers.
# Supplier names and descriptions can come from an import, so text that
# starts like this gets a ' in front: the spreadsheet shows it as text.
_FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def _text(value: str) -> str:
    return "'" + value if value.startswith(_FORMULA_START) else value


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, Amount):
        return _amount(value.cents)
    if isinstance(value, Decimal):
        return _decimal(value)
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str):
        return _text(value)
    return str(value)


def csv_bytes(header, rows) -> bytes:
    text = io.StringIO()
    writer = csv.writer(text, delimiter=";", lineterminator="\r\n")
    writer.writerow([str(name) for name in header])
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return text.getvalue().encode("utf-8-sig")


def csv_response(filename: str, header, rows) -> HttpResponse:
    response = HttpResponse(csv_bytes(header, rows), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
