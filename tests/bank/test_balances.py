# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bank balance from the statement (#159, part 1): the opening and
closing balance every statement states, per account; the latest one, the
one on a day, and where a statement is missing because the next one
doesn't start where the one before ended."""

from datetime import date
from pathlib import Path

import pytest

from huismus.bank import balances, camt, mt940, reading
from huismus.bank.lines import StatementBalance, StatementReadError
from huismus.bank.models import BankBalance, BankStatement

FIXTURES = Path(__file__).parents[1] / "fixtures" / "bank"
ACCOUNT = "NL91ABNA0417164300"


def _fixture(name):
    return (FIXTURES / name).read_bytes()


# Reading


def test_camt_reads_opening_and_closing_booked_balance():
    statement = camt.read(_fixture("camt053-001-02.xml"))
    # CLAV (available) is no booked balance: left out.
    assert statement.balances == [
        StatementBalance(ACCOUNT, date(2026, 11, 14), 100000, date(2026, 11, 15), 252401)
    ]


def test_camt_001_08_takes_previous_closing_as_opening_and_a_debit_is_negative():
    statement = camt.read(_fixture("camt053-001-08.xml"))
    assert statement.balances == [
        StatementBalance(ACCOUNT, date(2026, 11, 12), -85500, date(2026, 11, 13), -25000)
    ]


def _camt_balances(*balances, account=ACCOUNT, currency="EUR"):
    body = "".join(
        f"""<Bal><Tp><CdOrPrtry><Cd>{code}</Cd></CdOrPrtry></Tp>
        <Amt Ccy="{currency}">{amount}</Amt><CdtDbtInd>{direction}</CdtDbtInd>
        <Dt><Dt>{day}</Dt></Dt></Bal>"""
        for code, amount, direction, day in balances
    )
    return f"""<?xml version="1.0"?>
    <Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>
    <Stmt><Acct><Id><IBAN>{account}</IBAN></Id></Acct>{body}</Stmt>
    </BkToCstmrStmt></Document>""".encode()


def test_camt_opening_booked_wins_over_previous_closing_and_interim_closes_a_page():
    data = _camt_balances(
        ("PRCD", "10.00", "CRDT", "2026-10-31"),
        ("OPBD", "10.00", "CRDT", "2026-11-01"),
        ("ITBD", "25.00", "CRDT", "2026-11-15"),
    )
    assert camt.read(data).balances == [
        StatementBalance(ACCOUNT, date(2026, 11, 1), 1000, date(2026, 11, 15), 2500)
    ]


def test_camt_closing_booked_wins_over_interim():
    data = _camt_balances(
        ("OPBD", "10.00", "CRDT", "2026-11-01"),
        ("ITBD", "25.00", "CRDT", "2026-11-15"),
        ("CLBD", "30.00", "CRDT", "2026-11-30"),
    )
    assert camt.read(data).balances[0].closing_cents == 3000


@pytest.mark.parametrize(
    "balances",
    [
        [("OPBD", "10.00", "CRDT", "2026-11-01")],  # no closing
        [("CLBD", "10.00", "CRDT", "2026-11-30")],  # no opening
        [],
    ],
)
def test_camt_without_both_balances_gives_none(balances):
    assert camt.read(_camt_balances(*balances)).balances == []


def test_camt_balance_of_an_account_in_another_currency_is_left_out():
    data = _camt_balances(
        ("OPBD", "10.00", "CRDT", "2026-11-01"),
        ("CLBD", "30.00", "CRDT", "2026-11-30"),
        currency="USD",
    )
    assert camt.read(data).balances == []


def test_camt_balance_with_a_wrong_direction_is_refused():
    data = _camt_balances(
        ("OPBD", "10.00", "XXXX", "2026-11-01"), ("CLBD", "30.00", "CRDT", "2026-11-30")
    )
    with pytest.raises(StatementReadError):
        camt.read(data)


@pytest.mark.parametrize(
    "name, account, closing",
    [
        ("mt940-ing.sta", "NL91TEST0001234567", 276901),
        ("mt940-rabobank.swi", None, 229750),
        ("mt940-abnamro.sta", "417164300", 281550),
        ("mt940-triodos.sta", None, 221000),
    ],
)
def test_mt940_of_every_bank_reads_its_balances(name, account, closing):
    statement = mt940.read(_fixture(name))
    (balance,) = statement.balances
    assert balance.opening_on == date(2026, 11, 13)
    assert balance.opening_cents == 100000
    assert balance.closing_on == date(2026, 11, 14)
    assert balance.closing_cents == closing
    assert balance.account_iban in statement.accounts
    if account:
        assert balance.account_iban == account


def _mt940(*blocks):
    text = ""
    for account, opening, closing in blocks:
        text += f":20:TEST\n:25:{account}EUR\n:28C:1\n:{opening}\n:{closing}\n-\n"
    return text.encode()


def test_mt940_a_statement_per_day_gives_a_balance_per_day():
    data = _mt940(
        (ACCOUNT, "60F:C261113EUR10,00", "62F:C261113EUR20,00"),
        (ACCOUNT, "60F:C261113EUR20,00", "62F:D261114EUR5,50"),
    )
    assert mt940.read(data).balances == [
        StatementBalance(ACCOUNT, date(2026, 11, 13), 1000, date(2026, 11, 13), 2000),
        StatementBalance(ACCOUNT, date(2026, 11, 13), 2000, date(2026, 11, 14), -550),
    ]


def test_mt940_intermediate_balances_close_and_open_a_page():
    data = _mt940((ACCOUNT, "60M:C261113EUR10,00", "62M:C261113EUR15,00"))
    assert mt940.read(data).balances == [
        StatementBalance(ACCOUNT, date(2026, 11, 13), 1000, date(2026, 11, 13), 1500)
    ]


def test_mt940_balance_in_another_currency_is_left_out():
    data = b":20:TEST\n:25:NL91ABNA0417164300USD\n:60F:C261113USD10,00\n:62F:C261113USD20,00\n-\n"
    assert mt940.read(data).balances == []


def test_mt940_a_balance_that_cant_be_read_is_refused():
    data = _mt940((ACCOUNT, "60F:X261113EUR10,00", "62F:C261113EUR20,00"))
    with pytest.raises(StatementReadError):
        mt940.read(data)


# Storing


db = pytest.mark.django_db


@db
def test_reading_a_statement_keeps_its_balance():
    reading.read_statement("a.xml", _fixture("camt053-001-02.xml"))
    (balance,) = BankBalance.objects.all()
    assert (balance.account_iban, balance.closing_on, balance.closing_cents) == (
        ACCOUNT,
        date(2026, 11, 15),
        252401,
    )


@db
def test_the_same_balance_from_another_file_counts_once():
    reading.read_statement("a.xml", _fixture("camt053-001-02.xml"))
    result = reading.read_statement("a.xml", _fixture("camt053-001-02.xml"))
    assert BankBalance.objects.count() == 1
    assert result.balances_added == 0


@db
def test_a_file_with_only_known_lines_still_adds_its_balance():
    """A statement read before Huismus kept balances: reading it again
    adds the balance and leaves its lines as they are."""
    data = _fixture("camt053-001-02.xml")
    reading.read_statement("a.xml", data)
    BankBalance.objects.all().delete()
    result = reading.read_statement("a.xml", data)
    assert result.statement is None
    assert result.balances_added == 1
    assert BankBalance.objects.count() == 1


@db
def test_a_file_that_only_adds_a_balance_is_kept_as_evidence(
    settings, tmp_path, django_capture_on_commit_callbacks
):
    """The file is the evidence of the balance, as of a payment (product-
    owner agent 2026-11-27); no statement row, so the page doesn't show an
    empty statement."""
    settings.DATA_DIR = tmp_path
    data = _fixture("camt053-001-02.xml")
    reading.read_statement("a.xml", data)
    BankBalance.objects.all().delete()
    # The first read kept no file: its on_commit never ran in this test.
    assert not reading.archive_dir().exists()
    with django_capture_on_commit_callbacks(execute=True):
        reading.read_statement("b.xml", data)
    assert len(list(reading.archive_dir().iterdir())) == 1
    assert BankStatement.objects.count() == 1


# The balance per account, and gaps


def _balance(opening_on, opening, closing_on, closing, account=ACCOUNT):
    return BankBalance.objects.create(
        account_iban=account,
        opening_on=opening_on,
        opening_cents=opening,
        closing_on=closing_on,
        closing_cents=closing,
    )


@db
def test_latest_is_the_last_closing_balance_per_account():
    _balance(date(2026, 9, 1), 0, date(2026, 9, 30), 1000)
    _balance(date(2026, 10, 1), 1000, date(2026, 10, 31), 2500)
    _balance(date(2026, 10, 1), 500, date(2026, 10, 15), -300, account="NL20TEST0001234567")
    assert balances.latest() == [
        balances.AccountBalance("NL20TEST0001234567", date(2026, 10, 15), -300),
        balances.AccountBalance(ACCOUNT, date(2026, 10, 31), 2500),
    ]


@db
def test_balance_on_a_day_is_the_last_closing_on_or_before_it():
    _balance(date(2026, 12, 1), 1000, date(2026, 12, 31), 4000)
    _balance(date(2027, 1, 1), 4000, date(2027, 1, 31), 6000)
    assert balances.balance_on(date(2026, 12, 31)) == [
        balances.AccountBalance(ACCOUNT, date(2026, 12, 31), 4000)
    ]
    assert balances.balance_on(date(2027, 1, 15)) == [
        balances.AccountBalance(ACCOUNT, date(2026, 12, 31), 4000)
    ]
    assert balances.balance_on(date(2026, 11, 30)) == []


@db
def test_statements_that_connect_have_no_gap():
    _balance(date(2026, 9, 1), 0, date(2026, 9, 30), 1000)
    _balance(date(2026, 10, 1), 1000, date(2026, 10, 31), 2500)
    # A year statement over both, read as well: no gap either.
    _balance(date(2026, 9, 1), 0, date(2026, 12, 31), 2500)
    assert balances.gaps() == []


@db
def test_a_statement_that_starts_elsewhere_than_the_one_before_ended_is_a_gap():
    _balance(date(2026, 3, 1), 0, date(2026, 3, 31), 100000)
    _balance(date(2026, 5, 1), 125000, date(2026, 5, 31), 130000)
    assert balances.gaps() == [
        balances.Gap(ACCOUNT, date(2026, 3, 31), 100000, date(2026, 5, 1), 125000)
    ]
    # The balance stays the bank's; balance_on says a statement is missing.
    assert balances.balance_on(date(2026, 4, 30)) == [
        balances.AccountBalance(ACCOUNT, date(2026, 3, 31), 100000, gap_before=False)
    ]
    assert balances.balance_on(date(2026, 5, 31)) == [
        balances.AccountBalance(ACCOUNT, date(2026, 5, 31), 130000, gap_before=True)
    ]


@db
def test_the_first_statement_is_no_gap_whatever_it_starts_with():
    _balance(date(2026, 3, 1), 99999, date(2026, 3, 31), 100000)
    assert balances.gaps() == []


@db
def test_daily_mt940_where_opening_and_closing_share_the_date_has_no_gap():
    _balance(date(2026, 11, 13), 1000, date(2026, 11, 13), 2000)
    _balance(date(2026, 11, 14), 2000, date(2026, 11, 14), 1500)
    # Two pages of one day (:62M, then :60M).
    _balance(date(2026, 11, 15), 1500, date(2026, 11, 15), 1800)
    _balance(date(2026, 11, 15), 1800, date(2026, 11, 15), 1900)
    assert balances.gaps() == []
    assert balances.latest() == [balances.AccountBalance(ACCOUNT, date(2026, 11, 15), 1900)]


@db
def test_a_gap_is_per_account():
    _balance(date(2026, 3, 1), 0, date(2026, 3, 31), 1000)
    _balance(date(2026, 4, 1), 5000, date(2026, 4, 30), 6000, account="NL20TEST0001234567")
    assert balances.gaps() == []


# Statements read in before #159


@db
def test_the_update_takes_the_balances_from_the_kept_files(settings, tmp_path):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("huismus.bank.migrations.0004_balances_from_kept_files")
    settings.DATA_DIR = tmp_path
    folder = tmp_path / reading.ARCHIVE_DIR_NAME
    folder.mkdir()
    (folder / "1-camt.xml").write_bytes(_fixture("camt053-001-02.xml"))
    (folder / "2-ing.sta").write_bytes(_fixture("mt940-ing.sta"))
    # Neither of these stops the update.
    (folder / "3-kapot.xml").write_bytes(b"<Document><BkToCstmrStmt><Stmt>")
    (folder / "4-half.sta.deel").write_bytes(_fixture("mt940-ing.sta")[:40])
    migration.balances_from_kept_files(apps, None)
    migration.balances_from_kept_files(apps, None)  # twice: still once each
    assert sorted(BankBalance.objects.values_list("closing_cents", flat=True)) == [252401, 276901]


@db
def test_the_update_without_kept_files_does_nothing(settings, tmp_path):
    import importlib

    from django.apps import apps

    migration = importlib.import_module("huismus.bank.migrations.0004_balances_from_kept_files")
    settings.DATA_DIR = tmp_path
    migration.balances_from_kept_files(apps, None)
    assert BankBalance.objects.count() == 0


@db
def test_an_older_statement_with_the_same_balance_doesnt_hide_a_gap():
    # A savings account at zero: March and July end at 0, May starts at 0
    # after a missing April that brought it to 500.
    _balance(date(2026, 3, 1), 0, date(2026, 3, 31), 0)
    _balance(date(2026, 4, 1), 0, date(2026, 4, 30), 500)
    _balance(date(2026, 6, 1), 0, date(2026, 6, 30), 0)
    assert balances.gaps() == [balances.Gap(ACCOUNT, date(2026, 4, 30), 500, date(2026, 6, 1), 0)]
