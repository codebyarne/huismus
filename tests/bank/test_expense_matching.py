# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laying money going out next to the expenses without a bank line (#257;
product-owner agent 2026-11-21, huismus-intern/besluiten.md, "Bank (#257,
ronde 9)" point 3 and "afschrijvingen in richting D" points 1 and 2)."""

from datetime import date, timedelta

from huismus.bank.expense_matching import CHOOSE, LIKELY, NONE, SURE, OpenExpense, match
from huismus.bank.lines import StatementLine

BANK_DAY = date(2026, 9, 26)


def _line(cents, name="Hosting Noord B.V.", day=BANK_DAY):
    return StatementLine(
        account_iban="NL91ABNA0417164300",
        booked_on=day,
        amount_cents=-cents,
        counterparty_name=name,
        description="Abonnement september",
    )


def _expense(pk, cents, supplier="Hosting Noord", days_before=0):
    return OpenExpense(
        pk=pk, date=BANK_DAY - timedelta(days=days_before), supplier=supplier, gross_cents=cents
    )


def test_one_expense_same_amount_name_and_date_is_sure():
    hosting = _expense(1, 2420, days_before=3)
    result = match(_line(2420), [hosting, _expense(2, 8995, "Kantoorhuis")])
    assert (result.kind, result.expense) == (SURE, hosting)


def test_the_amount_is_to_the_cent():
    assert match(_line(2421), [_expense(1, 2420)]).kind == NONE


def test_seven_days_either_way_is_still_sure():
    assert match(_line(2420), [_expense(1, 2420, days_before=7)]).kind == SURE
    assert match(_line(2420), [_expense(1, 2420, days_before=-7)]).kind == SURE


def test_a_bill_paid_later_with_the_name_is_a_proposal():
    hosting = _expense(1, 2420, days_before=25)
    result = match(_line(2420), [hosting])
    assert (result.kind, result.expense) == (LIKELY, hosting)


def test_up_to_45_days_before_is_a_proposal_not_longer():
    assert match(_line(2420), [_expense(1, 2420, days_before=45)]).kind == LIKELY
    assert match(_line(2420), [_expense(1, 2420, days_before=46)]).kind == NONE


def test_amount_and_date_without_the_name_is_a_proposal():
    # A card payment: the bank gives the shop's terminal, not its name.
    supermarket = _expense(1, 6318, "Supermarkt De Hoek", days_before=1)
    result = match(_line(6318, name="CCV*HOEK 1234"), [supermarket])
    assert (result.kind, result.expense) == (LIKELY, supermarket)


def test_amount_alone_is_never_enough():
    # The right amount, another name, three weeks before: the user chooses.
    other = _expense(1, 6130, "NS", days_before=23)
    result = match(_line(6130, name="NS Reizigers"), [other])
    assert result.kind == CHOOSE
    assert result.candidates == (other,)


def test_two_expenses_with_the_amount_are_never_sure():
    first = _expense(1, 999, "Pluim Opslag", days_before=2)
    second = _expense(2, 999, "Andere winkel", days_before=30)
    result = match(_line(999, name="Pluim Opslag"), [first, second])
    # Not booked, but the one with the name and the date is proposed.
    assert (result.kind, result.expense) == (LIKELY, first)


def test_two_expenses_that_both_fit_go_to_the_user():
    first = _expense(1, 999, "Pluim Opslag", days_before=2)
    second = _expense(2, 999, "Pluim Opslag", days_before=30)
    result = match(_line(999, name="Pluim Opslag"), [first, second])
    assert result.kind == CHOOSE
    # The closest date first.
    assert result.candidates == (first, second)


def test_another_waiting_line_that_fits_the_same_expense_makes_it_a_proposal():
    hosting = _expense(1, 2420, days_before=2)
    other = _line(2420, day=BANK_DAY - timedelta(days=1))
    result = match(_line(2420), [hosting], other_lines=[other])
    assert (result.kind, result.expense) == (LIKELY, hosting)


def test_a_waiting_line_with_another_amount_does_not_count():
    hosting = _expense(1, 2420, days_before=2)
    result = match(_line(2420), [hosting], other_lines=[_line(5000)])
    assert result.kind == SURE


def test_outside_the_window_nothing_fits():
    # An old expense with the same amount: Niet herkend, not Te doen.
    assert match(_line(2420), [_expense(1, 2420, days_before=200)]).kind == NONE
    assert match(_line(2420), [_expense(1, 2420, days_before=-8)]).kind == NONE


def test_money_coming_in_is_never_an_expense():
    line = StatementLine(account_iban="NL91ABNA0417164300", booked_on=BANK_DAY, amount_cents=2420)
    assert match(line, [_expense(1, 2420)]).kind == NONE


def test_legal_forms_and_capitals_dont_matter_for_the_name():
    hosting = _expense(1, 2420, "Hosting Noord B.V.", days_before=20)
    assert match(_line(2420, name="HOSTING NOORD"), [hosting]).kind == LIKELY


def test_an_old_expense_with_the_amount_does_not_stop_this_one():
    # Last year's subscription, never linked to a bank line.
    hosting = _expense(1, 2420, days_before=2)
    result = match(_line(2420), [hosting, _expense(2, 2420, days_before=365)])
    assert (result.kind, result.expense) == (SURE, hosting)
