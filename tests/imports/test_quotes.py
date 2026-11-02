# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from pathlib import Path

import openpyxl
import pytest

from huismus.imports.quotes import QuoteParseError, parse_quotes
from huismus.imports.sources import read_files

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _quote_files(year):
    files = read_files(FIXTURES / f"lindeboom_communicatie_{year}")
    header = next(c for n, c in files.items() if n.endswith("estimates/offertes_export.xlsx"))
    lines = next(
        c for n, c in files.items() if n.endswith("estimates_details/offertes_regels_export.xlsx")
    )
    return header, lines


def test_parses_all_real_quotes_and_a_known_one_exactly():
    header, lines = _quote_files(2019)

    quotes = parse_quotes(header, lines)

    assert len(quotes) == 7
    quote = next(q for q in quotes if q.number == "480006")
    assert quote.external_id == "244320874481583895"
    assert quote.customer_number == "48"
    assert quote.status == "declined"  # Moneybird's "rejected"
    assert quote.issue_date == date(2019, 1, 11)
    assert quote.expiry_date == date(2019, 1, 25)
    assert quote.stated_subtotal_cents == 158671
    assert quote.stated_tax_cents == 0
    assert quote.stated_total_cents == 158671


def test_quote_lines_match_the_real_export():
    header, lines = _quote_files(2019)
    quotes = parse_quotes(header, lines)

    quote = next(q for q in quotes if q.number == "480006")

    assert len(quote.lines) >= 1
    first = quote.lines[0]
    assert first.description == "Logo- en huisstijlontwikkeling"
    assert first.quantity == Decimal("1")
    assert first.unit_price_cents == 36616
    assert first.tax_rate_bp == 0


def test_every_moneybird_status_in_the_2019_fixture_maps_cleanly():
    # Real statuses observed: accepted, rejected, late (huismus-intern/STATUS.md's M5
    # notes) — a still-open/not-yet-responded status is not exercised by
    # any real fixture row and is deliberately left unmapped (see
    # quotes.py's QUOTE_STATUS_MAP comment) rather than guessed at.
    header, lines = _quote_files(2019)
    quotes = parse_quotes(header, lines)
    assert {q.status for q in quotes} == {"accepted", "declined", "expired"}


def test_2021_export_has_no_quote_files_at_all():
    # Confirmed already in test_detect.py; not re-parsing here, just
    # documenting that _quote_files(2021) has nothing to find — the
    # pipeline (huismus/imports/pipeline.py) has to tolerate this the same way
    # it already tolerates a missing sales-invoice file.
    files = read_files(FIXTURES / "lindeboom_communicatie_2021")
    assert not any("estimates" in name for name in files)


def _minimal_workbook(sheet_name, header_row, data_row):
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.title = sheet_name
    sheet.append(header_row)
    sheet.append(data_row)
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


def test_an_unrecognised_status_raises_a_clear_error():
    header_content = _minimal_workbook(
        "offertes_export",
        ["id", "offertenummer", "klantnummer", "status", "offerte datum", "vervaldatum"],
        ["1", "1000", "1", "open", None, None],
    )
    lines_content = _minimal_workbook(
        "offertes_regels_export",
        ["id", "offertenummer", "omschrijving", "aantal (decimaal)", "prijs", "btw"],
        ["1", "1000", "iets", 1, 10.0, "0% btw"],
    )

    with pytest.raises(QuoteParseError):
        parse_quotes(header_content, lines_content)


def test_an_unrecognised_vat_rate_raises_a_clear_error():
    header_content = _minimal_workbook(
        "offertes_export",
        ["id", "offertenummer", "klantnummer", "status", "offerte datum", "vervaldatum"],
        ["1", "1000", "1", "accepted", None, None],
    )
    lines_content = _minimal_workbook(
        "offertes_regels_export",
        ["id", "offertenummer", "omschrijving", "aantal (decimaal)", "prijs", "btw"],
        ["1", "1000", "iets", 1, 10.0, "hoog"],
    )

    with pytest.raises(QuoteParseError):
        parse_quotes(header_content, lines_content)


def _quote_with(columns: dict):
    header = _minimal_workbook(
        "offertes_export",
        ["id", "offertenummer", "klantnummer", "status", "offerte datum", *columns],
        ["1", "1000", "1", "accepted", None, *columns.values()],
    )
    lines = _minimal_workbook(
        "offertes_regels_export",
        ["id", "offertenummer", "omschrijving", "aantal (decimaal)", "prijs", "btw"],
        ["1", "1000", "iets", 1, 10.0, "0% btw"],
    )
    return parse_quotes(header, lines)[0]


def test_a_quote_keeps_its_reference():
    assert _quote_with({"referentie": "Project X"}).reference == "Project X"


def test_a_quote_keeps_the_day_it_was_accepted_or_declined():
    from datetime import datetime

    accepted = _quote_with({"geaccepteerd op": datetime(2019, 3, 2), "afgewezen op": None})
    assert (accepted.accepted_on, accepted.declined_on) == (date(2019, 3, 2), None)


def _quote_with_status(status, accepted=None, declined=None):
    header = _minimal_workbook(
        "offertes_export",
        ["id", "offertenummer", "klantnummer", "status", "offerte datum", "vervaldatum"]
        + ["geaccepteerd op", "afgewezen op"],
        ["1", "1000", "1", status, None, None, accepted, declined],
    )
    lines = _minimal_workbook(
        "offertes_regels_export",
        ["id", "offertenummer", "omschrijving", "aantal (decimaal)", "prijs", "btw"],
        ["1", "1000", "Werk", 1, 10, "21% btw"],
    )
    (quote,) = parse_quotes(header, lines)
    return quote


def test_billed_is_accepted_without_taking_the_invoice_date_as_acceptance():
    # huismus-intern/besluiten.md, 2026-11-01: an invoice was made from it.
    quote = _quote_with_status("billed")

    assert (quote.status, quote.accepted_on) == ("accepted", None)


def test_billed_keeps_its_acceptance_date_when_moneybird_has_one():
    quote = _quote_with_status("billed", accepted=datetime(2014, 3, 1))

    assert (quote.status, quote.accepted_on) == ("accepted", date(2014, 3, 1))


@pytest.mark.parametrize(
    ("accepted", "declined", "status"),
    [
        (datetime(2014, 3, 1), None, "accepted"),
        (None, datetime(2014, 3, 2), "declined"),
        (None, None, "expired"),
    ],
)
def test_archived_follows_its_answer_and_expires_without_one(accepted, declined, status):
    assert _quote_with_status("archived", accepted, declined).status == status


@pytest.mark.parametrize("year", [2013, 2014])
def test_every_quote_status_in_the_2013_and_2014_exports_maps(year):
    header, lines = _quote_files(year)

    assert {q.status for q in parse_quotes(header, lines)} <= {"accepted", "declined", "expired"}
