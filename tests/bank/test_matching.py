# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Laying an incoming payment next to the open invoices (#77; the owner's
decision 2026-11-13): sure, likely, or the user chooses."""

from datetime import date

import pytest

from huismus.bank.lines import StatementLine
from huismus.bank.matching import CHOOSE, LIKELY, SURE, OpenInvoice, match


def _line(amount_cents, description="", name="", iban="", reference=""):
    return StatementLine(
        account_iban="NL91ABNA0417164300",
        booked_on=date(2026, 11, 14),
        amount_cents=amount_cents,
        counterparty_name=name,
        counterparty_iban=iban,
        description=description,
        reference=reference,
    )


KORST = OpenInvoice(
    pk=1, number="2026-015", outstanding_cents=121000, names=("Bakkerij De Korst B.V.",), ibans=()
)
NOORD = OpenInvoice(
    pk=2,
    number="2026-016",
    outstanding_cents=60500,
    names=("Studio Noord", "Anna Jansen"),
    ibans=("NL02RABO0123456789",),
)
ZUID = OpenInvoice(
    pk=3, number="2026-017", outstanding_cents=60500, names=("Studio Zuid",), ibans=()
)
OPEN = [KORST, NOORD, ZUID]


def test_number_in_the_text_and_the_open_amount_is_sure():
    result = match(_line(121000, "Factuur 2026-015"), OPEN)
    assert (result.kind, result.invoice) == (SURE, KORST)


@pytest.mark.parametrize(
    "description",
    ["factuur 2026015", "FACTUUR 2026 015", "fact.2026.015 bedankt", "2026-015", "inv/2026-015/"],
)
def test_the_number_is_found_with_other_separators_or_none(description):
    assert match(_line(121000, description), OPEN).kind == SURE


@pytest.mark.parametrize("description", ["12026-015", "2026-0150", "2026-015A", "A2026-015"])
def test_the_number_inside_a_longer_one_is_not_it(description):
    assert match(_line(121000, description), OPEN).kind != SURE


def test_the_number_in_a_structured_reference_counts_too():
    assert match(_line(121000, reference="2026-015"), OPEN).kind == SURE


def test_the_number_with_another_amount_is_likely():
    # Partly paid, or too much: the user confirms.
    result = match(_line(50000, "Factuur 2026-015"), OPEN)
    assert (result.kind, result.invoice) == (LIKELY, KORST)


def test_amount_and_name_of_exactly_one_invoice_is_likely():
    result = match(_line(60500, "bedankt!", name="STUDIO NOORD"), OPEN)
    assert (result.kind, result.invoice) == (LIKELY, NOORD)


def test_the_name_may_be_part_of_the_bank_name_and_legal_forms_dont_count():
    assert match(_line(121000, name="Bakkerij de Korst"), OPEN).invoice == KORST
    assert match(_line(60500, name="Hr A Jansen"), OPEN).kind == CHOOSE  # initial, not the name
    assert match(_line(60500, name="Anna Jansen eo"), OPEN).invoice == NOORD


def test_the_customers_iban_counts_as_the_name():
    result = match(_line(60500, name="A. JANSEN", iban="NL02RABO0123456789"), OPEN)
    assert (result.kind, result.invoice) == (LIKELY, NOORD)


def test_amount_without_name_is_for_the_user_with_the_amount_first():
    result = match(_line(60500, "bedankt"), OPEN)
    assert result.kind == CHOOSE
    assert result.invoice is None
    assert result.candidates == (NOORD, ZUID)


def test_two_invoices_with_the_number_are_for_the_user():
    result = match(_line(181500, "Facturen 2026-015 en 2026-016"), OPEN)
    assert result.kind == CHOOSE
    assert set(result.candidates) == {KORST, NOORD}


def test_name_with_another_amount_is_for_the_user_with_that_invoice_as_candidate():
    result = match(_line(100, name="Studio Zuid"), OPEN)
    assert result.kind == CHOOSE
    assert result.candidates == (ZUID,)


def test_nothing_that_fits():
    result = match(_line(999, "salaris"), OPEN)
    assert (result.kind, result.invoice, result.candidates) == (CHOOSE, None, ())


def test_no_open_invoices():
    assert match(_line(121000, "Factuur 2026-015"), []).kind == CHOOSE


def test_a_short_name_never_matches_by_accident():
    tiny = OpenInvoice(pk=9, number="2026-099", outstanding_cents=500, names=("AB",), ibans=())
    assert match(_line(500, name="ABN AMRO Bank"), [tiny]).kind == CHOOSE
