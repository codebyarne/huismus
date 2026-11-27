# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The balance on the Bank page (#159, part 1; product-owner agent
2026-11-27): a tile per account after Ingelezen · Bij · Af, and a warning
per account where a statement is missing."""

from datetime import date
from pathlib import Path

import pytest
from django.utils.formats import date_format

from huismus.bank.models import BankBalance

# client and _settings are fixtures: the logged-in client of the bank page.
from .test_views import _settings, _upload, client  # noqa: F401

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bank"
PAGE = "/bank/"


def _short(day):
    return date_format(day, "SHORT_DATE_FORMAT")


def _balance(opening_on, opening, closing_on, closing, account="NL91ABNA0417164300"):
    BankBalance.objects.create(
        account_iban=account,
        opening_on=opening_on,
        opening_cents=opening,
        closing_on=closing_on,
        closing_cents=closing,
    )


def test_reading_a_statement_shows_its_balance(client):  # noqa: F811
    page = _upload(client, (FIXTURES / "camt053-001-02.xml").read_bytes())
    assert f"Saldo op {_short(date(2026, 11, 15))}" in page.text
    assert "€ 2.524,01" in page.text
    assert "volgens je afschrift" in page.text
    assert 'id="saldo-gaten"' not in page.text


def test_more_accounts_each_get_a_tile_with_the_iban(client):  # noqa: F811
    _upload(client, (FIXTURES / "camt053-001-02.xml").read_bytes())
    _balance(date(2026, 11, 1), 0, date(2026, 11, 10), -1250, account="NL20TEST0001234567")
    page = client.get(PAGE)
    assert page.text.count("data-saldo") == 2
    assert "NL20 TEST 0001 2345 67" in page.text
    assert "− € 12,50" in page.text
    assert "volgens je afschrift" not in page.text


def test_no_balance_no_tile(client):  # noqa: F811
    data = (FIXTURES / "camt053-001-02.xml").read_bytes()
    _upload(client, data)
    BankBalance.objects.all().delete()
    assert "data-saldo" not in client.get(PAGE).text


def test_a_missing_statement_is_said(client):  # noqa: F811
    _upload(client, (FIXTURES / "camt053-001-02.xml").read_bytes())
    _balance(date(2026, 3, 1), 0, date(2026, 3, 31), 100000)
    # May ends where the statement of November starts: one gap only.
    _balance(date(2026, 5, 1), 125000, date(2026, 10, 31), 100000)
    page = client.get(PAGE)
    assert (
        "Er mist een afschrift van NL91 ABNA 0417 1643 00 tussen "
        f"{_short(date(2026, 3, 31))} en {_short(date(2026, 5, 1))}. "
        "Het saldo was € 1.000,00 en begint daarna op € 1.250,00. "
        "Lees dat afschrift ook in."
    ) in page.text


def test_more_missing_statements_are_one_warning_with_the_count(client):  # noqa: F811
    _upload(client, (FIXTURES / "camt053-001-02.xml").read_bytes())
    _balance(date(2026, 3, 1), 0, date(2026, 3, 31), 100000)
    _balance(date(2026, 5, 1), 125000, date(2026, 5, 31), 130000)
    _balance(date(2026, 7, 1), 140000, date(2026, 7, 31), 150000)
    page = client.get(PAGE)
    assert page.text.count("hint-banner is-warn") == 1
    assert "het saldo sluit 3 keer niet aan" in page.text


def test_reading_a_file_again_that_only_adds_a_balance_says_so(client):  # noqa: F811
    data = (FIXTURES / "camt053-001-02.xml").read_bytes()
    _upload(client, data)
    BankBalance.objects.all().delete()
    page = _upload(client, data)
    assert (
        "Niets nieuws: alle betalingen in dit bestand waren al ingelezen. Het saldo is bijgewerkt."
    ) in page.text
    page = _upload(client, data)
    assert "Het saldo is bijgewerkt." not in page.text


def test_the_balance_in_english(client):  # noqa: F811
    _upload(client, (FIXTURES / "camt053-001-02.xml").read_bytes())
    client.cookies["django_language"] = "en"
    page = client.get(PAGE)
    assert "Balance on" in page.text
    assert "from your bank statement" in page.text
