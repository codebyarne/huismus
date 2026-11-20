# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading MT940 (#77) in the dialects of the Dutch banks
(docs/bankafschriften.md): the fixtures follow each bank's own format
description, with made-up accounts and names."""

from datetime import date
from pathlib import Path

import pytest

from huismus.bank import mt940
from huismus.bank.lines import StatementReadError

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bank"


def _read(name):
    data = (FIXTURES / name).read_bytes()
    assert mt940.is_mt940(data)
    return mt940.read(data)


def test_ing_structured():
    statement = _read("mt940-ing.sta")
    assert statement.accounts == {"NL91INGB0001234567"}
    first, second = statement.lines
    assert first.booked_on == date(2026, 11, 14)
    assert first.amount_cents == 121000
    assert first.counterparty_iban == "NL02RABO0123456789"
    # A word broken over two lines of 65 is whole again.
    assert first.counterparty_name == "Bakkerij De Korst B.V."
    assert first.description == "Factuur 2026-015 dank je wel"
    assert first.bank_reference == "00000000001005"
    assert second.counterparty_name == "J. de Vries"
    assert second.reference == "9001123412341234"
    assert statement.not_incoming == 1


def test_rabobank_structured():
    statement = _read("mt940-rabobank.swi")
    assert statement.accounts == {"NL91RABO0123456789"}
    first, second = statement.lines
    assert first.amount_cents == 121000
    # The payer's IBAN is on the line under :61:.
    assert first.counterparty_iban == "NL02INGB0123456789"
    assert first.counterparty_name == "Studio Noord"
    assert first.description == "Factuur 2026-016"
    assert second.counterparty_name == "Studio Zuid"
    assert second.reference == "1234567890123456"
    assert second.description == ""
    # RD: a reversal, no customer paying.
    assert statement.not_incoming == 1


def test_abn_amro_structured_and_the_older_free_text():
    statement = _read("mt940-abnamro.sta")
    structured, free = statement.lines
    assert structured.amount_cents == 121000  # "1210" without decimals
    assert structured.counterparty_iban == "NL02RABO0123456789"
    assert structured.counterparty_name == "Bakkerij De Korst"
    assert structured.description == "Factuur 2026-015"
    assert free.amount_cents == 60550  # "605,5"
    assert free.counterparty_iban == "NL20INGB0001234567"
    assert free.counterparty_name == "J DE VRIES"
    assert free.description == "FACTUUR 2026-016"


def test_triodos_subfields():
    (line,) = _read("mt940-triodos.sta").lines
    assert line.counterparty_iban == "NL02RABO0123456789"
    # Name and description come as one text: the number is in it.
    assert "Factuur 2026-015" in line.description
    assert "Bakkerij De Korst" in line.description


def test_cp1252_is_read_too():
    data = (FIXTURES / "mt940-ing.sta").read_bytes().replace(b"Vries", "Vri\xebs".encode("cp1252"))
    (_, second) = mt940.read(data).lines
    assert second.counterparty_name == "J. de Vriës"


def test_booking_date_in_january_for_a_december_value_date():
    data = (
        b":20:X\r\n:25:NL91INGB0001234567EUR\r\n:28C:1\r\n:60F:C261231EUR0,00\r\n"
        b":61:2612310102C10,00NTRFNONREF\r\n:86:/REMI/USTD//x/\r\n:62F:C270102EUR10,00\r\n"
    )
    (line,) = mt940.read(data).lines
    assert line.booked_on == date(2027, 1, 2)


@pytest.mark.parametrize(
    "data",
    [
        b":20:X\r\n:25:NL\r\n:61:2613991114C1,00NTRFNONREF\r\n",  # day 99
        b":20:X\r\n:25:NL\r\n:61:261114C1,00,00NTRFNONREF\r\n",  # two commas
    ],
)
def test_a_broken_line_is_refused(data):
    with pytest.raises(StatementReadError):
        mt940.read(data)


def test_not_mt940():
    assert not mt940.is_mt940(b"<?xml version='1.0'?><Document/>")
    assert not mt940.is_mt940(b"Datum;Naam;Bedrag\n")


@pytest.mark.parametrize(
    "value, mmdd, booked",
    [
        (date(2026, 12, 31), "0102", date(2027, 1, 2)),
        (date(2027, 1, 2), "1231", date(2026, 12, 31)),
        (date(2026, 11, 14), "1115", date(2026, 11, 15)),
    ],
)
def test_the_booking_date_gets_the_right_year(value, mmdd, booked):
    assert mt940.booking_date(value, mmdd) == booked
