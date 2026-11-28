# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reads the CSV files of Huismus's own format (SPEC.md M22): the files the
export writes (M19), filled by Huismus itself or by hand from another
package or a spreadsheet.

A file is recognised by its column names, never by its file name, and a
column by its name in Dutch or English (core.export_format), never by its
place (CLAUDE.md, hard rule 6). A required column that is missing stops
the import with its name; a column Huismus doesn't know is named in the
report and left out. A cell that can't be read (a date, an amount) stops
the import too, with the file, row and column.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from functools import cache

from django.utils.translation import gettext as _

from huismus.core import export_format
from huismus.core.export_format import Column, in_both_languages, normalised
from huismus.core.forms import amount_with_decimal_point

from .sources import ImportSourceError


class CsvKind(Enum):
    CONTACTS = "contacts"
    CONTACT_PERSONS = "contact_persons"
    INVOICES = "invoices"
    QUOTES = "quotes"
    LINES = "lines"
    EXPENSES = "expenses"
    EXPENSE_LINES = "expense_lines"


COLUMNS: dict[CsvKind, tuple[Column, ...]] = {
    CsvKind.CONTACTS: export_format.CONTACT_COLUMNS,
    CsvKind.CONTACT_PERSONS: export_format.CONTACT_PERSON_COLUMNS,
    CsvKind.INVOICES: export_format.INVOICE_COLUMNS + export_format.INVOICE_COLUMNS_AFTER_RATES,
    CsvKind.QUOTES: export_format.QUOTE_COLUMNS,
    CsvKind.LINES: export_format.LINE_COLUMNS,
    CsvKind.EXPENSES: export_format.EXPENSE_COLUMNS,
    CsvKind.EXPENSE_LINES: export_format.EXPENSE_LINE_COLUMNS,
}

# A file is one of ours from this many known column names on: one name
# ("nummer", "datum") says too little.
MIN_KNOWN_COLUMNS = 2
# A file that misses a required column still counts as ours from this many
# on, so the message can name the column; fewer is more likely another
# file with a "datum" and an "omschrijving" in it.
MIN_KNOWN_COLUMNS_INCOMPLETE = 3

# A quantity: at most seven digits before and three after the comma.
_QUANTITY = re.compile(r"-?\d{1,7}(?:[.,]\d{1,3})?")

# What csv_files._text() puts in front of text a spreadsheet would run as
# a formula; the import takes it off again.
_FORMULA_GUARD = re.compile(r"^'(?=[=+\-@\t\r])")


@cache
def _keys_by_name(kind: CsvKind) -> dict[str, str]:
    """Column name, in either language -> the column's key."""
    names = {}
    for column in COLUMNS[kind]:
        for label in (column.label, *column.also):
            for name in in_both_languages(label):
                names[normalised(name)] = column.key
    return names


@cache
def _rate_patterns() -> list[tuple[str, re.Pattern]]:
    """("revenue" or "tax", what "omzet 21%" or "btw 21%" looks like) in
    either language. The rate itself is read by _rate_bp()."""
    patterns = []
    for part, template in (
        ("revenue", export_format.RATE_REVENUE),
        ("tax", export_format.RATE_TAX),
    ):
        for text in in_both_languages(template):
            before, after = (re.escape(normalised(piece)) for piece in text.split("%(rate)s"))
            # "%%" in the template is one "%" once filled in.
            after = after.replace("%%", "%")
            patterns.append((part, re.compile(rf"{before}\s?(\d{{1,3}}(?:,\d{{1,2}})?){after}")))
    return patterns


def _rate_bp(percent: str) -> int:
    """ "21" -> 2100, "5,5" -> 550: as core.export._percent() writes it."""
    return int(Decimal(percent.replace(",", ".")) * 100)


def _rate_column(name: str) -> tuple[int, str] | None:
    for part, pattern in _rate_patterns():
        match = pattern.fullmatch(name)
        if match:
            return _rate_bp(match.group(1)), part
    return None


class Row:
    """One row of a table: its cells by column key, as text, and readers
    for a date, an amount and so on that stop the import on a cell they
    can't read."""

    def __init__(self, table: "Table", number: int, cells: dict[str, str], rates: dict):
        self.table = table
        self.number = number  # as a spreadsheet counts: the header is row 1
        self._cells = cells
        # (rate in basis points, "revenue" or "tax") -> the cell's text.
        self.rates: dict[tuple[int, str], str] = rates

    def text(self, key: str) -> str:
        return self._cells.get(key, "")

    def _fail(self, key: str, reason: str):
        raise ImportSourceError(
            _("In %(file)s, rij %(row)s, kolom ‘%(column)s’: %(reason)s")
            % {
                "file": self.table.file_name,
                "row": self.number,
                "column": self.table.header_of.get(key, key),
                "reason": reason,
            }
        )

    def required(self, key: str) -> str:
        value = self.text(key)
        if not value:
            self._fail(key, _("dit vak is leeg, maar moet gevuld zijn."))
        return value

    def required_date(self, key: str) -> date:
        self.required(key)
        return self.date(key)

    def required_amount(self, key: str) -> int:
        self.required(key)
        return self.amount(key)

    def required_choice(self, key: str, choices: dict[str, object], *, examples: str):
        self.required(key)
        return self.choice(key, choices, examples=examples)

    def date(self, key: str) -> date | None:
        value = self.text(key)
        if not value:
            return None
        for date_format in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(value, date_format).date()
            except ValueError:
                continue
        self._fail(
            key,
            _("‘%(value)s’ is geen datum die Huismus leest. Schrijf 2026-03-14 of 14-03-2026.")
            % {"value": value},
        )

    def amount(self, key: str) -> int | None:
        """Cents, or None for an empty cell."""
        return self.amount_of(key, self.text(key))

    def amount_of(self, key: str, value: str) -> int | None:
        if not value:
            return None
        plain = amount_with_decimal_point(value.replace("€", "").strip())
        if plain is None:
            self._fail(
                key,
                _("‘%(value)s’ is geen bedrag dat Huismus leest. Schrijf 1234,56.")
                % {"value": value},
            )
        # From the text, never through a float (CLAUDE.md, hard rule 1).
        return int((Decimal(plain) * 100).to_integral_value())

    def decimal(self, key: str) -> Decimal | None:
        value = self.text(key)
        if not value:
            return None
        # What a line's quantity can hold (DocumentLine.quantity): more
        # digits would be rounded when saved, after the totals were made.
        if not _QUANTITY.fullmatch(value):
            self._fail(key, _("‘%(value)s’ is geen getal. Schrijf 2 of 2,5.") % {"value": value})
        return Decimal(value.replace(",", "."))

    def whole_number(self, key: str) -> int | None:
        value = self.text(key)
        if not value:
            return None
        if not value.isdecimal():
            self._fail(key, _("‘%(value)s’ is geen heel getal.") % {"value": value})
        return int(value)

    def choice(self, key: str, choices: dict[str, object], *, examples: str):
        """The value of a cell with a fixed set of words ("ja", "factuur"),
        in either language; None for an empty cell. `choices`: normalised
        word -> value. `examples`: the words to name when it is none."""
        value = self.text(key)
        if not value:
            return None
        found = choices.get(normalised(value))
        if found is None:
            self._fail(
                key,
                _("‘%(value)s’ kent Huismus hier niet. Kies uit: %(examples)s.")
                % {"value": value, "examples": examples},
            )
        return found

    def fail(self, key: str, reason: str):
        """For a parser's own check on a cell."""
        self._fail(key, reason)


@dataclass
class Table:
    kind: CsvKind
    file_name: str
    # Column key -> the name the file itself uses, for messages.
    header_of: dict[str, str] = field(default_factory=dict)
    # Column names Huismus doesn't know, as written.
    unknown: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)

    def has(self, key: str) -> bool:
        return key in self.header_of


def _decode(file_name: str, content: bytes) -> str:
    """UTF-8 (with or without a BOM), as the export writes; else Windows's
    own encoding, which Excel saves a CSV in. Anything else stops the
    import: a name with a wrong letter in it would come in unnoticed."""
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ImportSourceError(
        _("Huismus kan de letters in %(file)s niet lezen. Sla het bestand op als CSV (UTF-8).")
        % {"file": file_name}
    )


def _numbered_lines(file_name: str, content: bytes) -> list[tuple[int, list[str]]]:
    """The lines of a CSV file that have something in them, each with its
    row number as a spreadsheet shows it: empty rows count too."""
    reader = csv.reader(io.StringIO(_decode(file_name, content), newline=""), delimiter=";")
    return [
        (number, line)
        for number, line in enumerate(reader, start=1)
        if any(cell.strip() for cell in line)
    ]


def _clean(cell: str) -> str:
    return _FORMULA_GUARD.sub("", cell.strip())


def _known(kind: CsvKind, name: str) -> bool:
    if name in _keys_by_name(kind):
        return True
    return kind is CsvKind.INVOICES and _rate_column(name) is not None


def recognise(header: list[str]) -> CsvKind | None:
    """Which of our files has this header row. The one whose required
    columns are all there, with the most columns known; when none is
    complete, the one with the most known columns, so the message can
    name what is missing. None for a file that isn't one of ours."""
    names = [normalised(name) for name in header]

    def known_count(kind):
        return sum(1 for name in names if _known(kind, name))

    best = max(CsvKind, key=lambda kind: (_has_required(kind, names), known_count(kind)))
    enough = MIN_KNOWN_COLUMNS if _has_required(best, names) else MIN_KNOWN_COLUMNS_INCOMPLETE
    return best if known_count(best) >= enough else None


def _has_required(kind: CsvKind, names: list[str]) -> bool:
    """`names` (normalised) hold every required column of `kind`."""
    present = {_keys_by_name(kind).get(name) for name in names}
    return all(column.key in present for column in COLUMNS[kind] if column.required)


def is_complete(file_name: str, content: bytes) -> bool:
    """A CSV file with every required column of one of our files: surely
    meant as one, whatever else was uploaded with it."""
    header = _header(file_name, content)
    kind = recognise(header) if header else None
    return kind is not None and _has_required(kind, [normalised(name) for name in header])


@cache
def _hours_names() -> tuple[frozenset[str], ...]:
    """The header row of uren.csv, per language, without the invoice
    column (#81), so an export from before it is still recognised."""
    labels = [
        export_format.in_both_languages(column.label)
        for column in export_format.HOURS_COLUMNS
        if column.key != "invoice"
    ]
    return tuple(frozenset(normalised(label[i]) for label in labels) for i in range(len(labels[0])))


def is_hours_csv(file_name: str, content: bytes) -> bool:
    """uren.csv from Huismus's own export (#80). Not read in yet (#358):
    the import names it and goes on, instead of taking it for another file
    because it has a "datum" and an "omschrijving"."""
    header = {normalised(name) for name in _header(file_name, content)}
    return any(names <= header for names in _hours_names())


def kind_of(file_name: str, content: bytes) -> CsvKind | None:
    """Which of our files this CSV is, by its header row alone."""
    if is_hours_csv(file_name, content):
        return None
    header = _header(file_name, content)
    return recognise(header) if header else None


def _header(file_name: str, content: bytes) -> list[str]:
    lines = _numbered_lines(file_name, content)
    return lines[0][1] if lines else []


def read_table(file_name: str, content: bytes) -> Table | None:
    """The table in a CSV file, or None when it isn't one of ours."""
    lines = _numbered_lines(file_name, content)
    if not lines or is_hours_csv(file_name, content):
        return None
    header = [cell.strip() for cell in lines[0][1]]
    if len(header) == 1 and ("," in header[0] or "\t" in header[0]):
        # Never guessed (hard rule 6): commas can be inside a description.
        raise ImportSourceError(
            _(
                "%(file)s heeft geen puntkomma's tussen de kolommen. Sla het bestand op als "
                "CSV met puntkomma's (;) en probeer het opnieuw."
            )
            % {"file": file_name}
        )
    kind = recognise(header)
    if kind is None:
        return None

    table = Table(kind, file_name)
    keys = _keys_by_name(kind)
    key_at: dict[int, str] = {}
    rate_at: dict[int, tuple[int, str]] = {}
    for index, name in enumerate(header):
        key = keys.get(normalised(name))
        rate = _rate_column(normalised(name)) if kind is CsvKind.INVOICES else None
        if key is not None and key not in table.header_of:
            key_at[index] = key
            table.header_of[key] = name
        elif key is None and rate is not None and rate not in rate_at.values():
            rate_at[index] = rate
        elif name:
            table.unknown.append(name)  # also a column that is there twice

    missing = [
        _(column.label)
        for column in COLUMNS[kind]
        if column.required and column.key not in table.header_of
    ]
    if missing:
        raise ImportSourceError(
            _(
                "In %(file)s ontbreekt de kolom ‘%(column)s’. Zet hem erbij, met precies "
                "deze naam, en probeer het opnieuw."
            )
            % {"file": file_name, "column": missing[0]}
        )

    for number, line in lines[1:]:
        cells = {key: _clean(line[index]) for index, key in key_at.items() if index < len(line)}
        rates = {rate: _clean(line[index]) for index, rate in rate_at.items() if index < len(line)}
        table.rows.append(Row(table, number, cells, rates))
    return table
