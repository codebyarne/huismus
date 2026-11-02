# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Settings proposed from a Moneybird export, to check in the dry run.

The fixtures: 2019 and 2021 of one fictional business that moved (and
changed KvK number and bank account) in between; the newest invoice has
the current details.
"""

from dataclasses import replace
from pathlib import Path

from huismus.imports.pipeline import parse_exports
from huismus.imports.settings_proposal import propose_settings
from huismus.imports.sources import read_exports

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _proposal(*years):
    exports = [
        e for year in years for e in read_exports(FIXTURES / f"lindeboom_communicatie_{year}.zip")
    ]
    parsed = parse_exports(exports)
    return propose_settings(exports, parsed.invoices, parsed.quotes)


def test_business_details_come_from_the_newest_invoice():
    proposal = _proposal("2019", "2021")

    assert proposal.values["business_name"] == "Lindeboom Communicatie"
    assert proposal.values["address_line1"] == "Celebesstraat 40 bis"
    assert proposal.values["postal_code"] == "3531 KD"
    assert proposal.values["city"] == "Zeist"
    assert proposal.values["country"] == "NL"
    assert proposal.values["kvk_number"] == "35536519"
    assert proposal.values["email"] == "info@lindeboomcommunicatie.nl"
    assert proposal.values["iban"] == "NL87TEST7728849485"
    assert proposal.values["bic"] == "TESTNL2A"
    assert proposal.source_invoice_date.isoformat() == "2021-12-30"


def test_the_order_of_the_exports_does_not_matter():
    assert _proposal("2021", "2019").values == _proposal("2019", "2021").values


def test_moneybird_s_customer_number_format_is_recognised():
    proposal = _proposal("2019", "2021")

    assert proposal.values["invoice_number_format"] == "{customer}{seq:04d}"
    assert proposal.values["quote_number_format"] == "{customer}{seq:04d}"
    assert proposal.values["number_reset_yearly"] is False


def test_numbers_in_another_shape_get_no_format_proposed():
    # Not for quotes either: both formats share the yearly-reset setting.
    exports = read_exports(FIXTURES / "lindeboom_communicatie_2019.zip")
    parsed = parse_exports(exports)
    invoices = [replace(i, number=f"2019-{n:04d}") for n, i in enumerate(parsed.invoices, 1)]

    proposal = propose_settings(exports, invoices, parsed.quotes)

    assert "invoice_number_format" not in proposal.values
    assert "quote_number_format" not in proposal.values
    assert "number_reset_yearly" not in proposal.values


def test_the_most_common_payment_term_is_proposed():
    exports = read_exports(FIXTURES / "lindeboom_communicatie_2019.zip")
    parsed = parse_exports(exports)
    invoices = parsed.invoices
    terms = [(i.due_date - i.issue_date).days for i in invoices if i.due_date]
    expected = max(set(terms), key=terms.count)

    assert propose_settings(exports, invoices, []).values["default_payment_terms_days"] == expected


def test_without_ubl_files_there_are_no_business_details():
    exports = read_exports(FIXTURES / "lindeboom_communicatie_2019.zip")
    for export in exports:
        export.files = {n: c for n, c in export.files.items() if "ubl" not in n}
    parsed = parse_exports(exports)

    proposal = propose_settings(exports, parsed.invoices, parsed.quotes)

    assert "business_name" not in proposal.values
    assert proposal.source_invoice_date is None


def _with_extra_ubl(content: bytes):
    exports = read_exports(FIXTURES / "lindeboom_communicatie_2019.zip")
    exports[0].files["x/sales_invoices_ubl_archive/999999.xml"] = content
    parsed = parse_exports(exports)
    return propose_settings(exports, parsed.invoices, parsed.quotes)


def test_a_hostile_ubl_file_is_skipped_not_fatal():
    # defusedxml refuses entity declarations (XML bombs, XXE) with its own
    # exception, not a ParseError.
    bomb = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><Invoice>&a;</Invoice>'

    assert _with_extra_ubl(bomb).values["business_name"] == "Lindeboom Communicatie"


def test_a_ubl_file_with_a_broken_date_is_skipped_not_fatal():
    broken = b"<Invoice><IssueDate>gisteren</IssueDate></Invoice>"

    assert _with_extra_ubl(broken).values["business_name"] == "Lindeboom Communicatie"
