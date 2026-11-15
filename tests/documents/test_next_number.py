# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Setting the next number by hand (issue #141): for someone who comes from
another package without an import. Invariant 3 decides what may: never a
gap within what Huismus issued, never a number twice."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from django.db import connections

from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, NumberSequence
from huismus.documents.numbering import (
    NumberingError,
    next_sequence_number,
    next_sequence_number_is_fixed,
    set_next_sequence_number,
)
from huismus.documents.quoting import send_quote
from huismus.documents.reopening import reopen
from tests.documents.test_issuing import _settings
from tests.support import clean_up_issued_documents_for_flush

pytestmark = pytest.mark.django_db

FORMAT = "{year}-{seq:04d}"


def _draft(kind="invoice", *, issue_date=date(2026, 3, 1), **fields):
    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=issue_date,
        **fields,
    )
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    return document


def _imported(number, *, kind="invoice", issue_date=date(2026, 2, 1)):
    """An issued document as the Moneybird import leaves it: its own
    number, source set, the sequence moved past it."""
    return Document.objects.create(
        kind=kind,
        status="issued" if kind != "quote" else "sent",
        contact=Contact.objects.create(company_name="Oude klant BV"),
        number=number,
        issue_date=issue_date,
        source="moneybird",
        external_id=number,
        total_cents=100000,
    )


def test_an_empty_sequence_starts_at_one():
    assert next_sequence_number("invoice", year=2026) == 1
    assert not next_sequence_number_is_fixed("invoice")


def test_the_first_invoice_gets_the_number_that_was_set():
    _settings()
    set_next_sequence_number("invoice", FORMAT, year=2026, value=43)

    assert next_sequence_number("invoice", year=2026) == 43
    assert issue(_draft()).number == "2026-0043"
    assert issue(_draft()).number == "2026-0044"


def test_the_same_value_writes_nothing():
    set_next_sequence_number("invoice", FORMAT, year=2026, value=1)

    assert not NumberSequence.objects.exists()


def test_once_huismus_issued_an_invoice_the_number_is_fixed():
    # Raising it now would leave a gap after 2026-0001 (invariant 3).
    _settings()
    issue(_draft())

    assert next_sequence_number_is_fixed("invoice")
    with pytest.raises(NumberingError):
        set_next_sequence_number("invoice", FORMAT, year=2026, value=43)
    assert next_sequence_number("invoice", year=2026) == 2


def test_a_credit_note_fixes_the_invoice_sequence_too():
    _settings()
    invoice = _imported("2026-0042")
    NumberSequence.objects.create(kind="invoice", year=2026, last_value=42)
    issue(_draft("credit_note", related_document=invoice))

    assert next_sequence_number_is_fixed("invoice")


def test_a_reopened_invoice_still_counts():
    # "Toch bewerken" makes it a draft again, with its number kept.
    _settings()
    reopen(issue(_draft()))

    assert next_sequence_number_is_fixed("invoice")


def test_last_year_s_invoice_fixes_the_new_year_s_sequence_too():
    # Else someone who already invoices in Huismus could skip numbers
    # at the start of a new year.
    _settings(number_reset_yearly=True)
    issue(_draft(issue_date=date(2025, 12, 30)))

    with pytest.raises(NumberingError):
        set_next_sequence_number("invoice", FORMAT, year=2026, value=10)
    assert next_sequence_number("invoice", year=2026) == 1


def test_without_a_yearly_reset_any_invoice_fixes_it():
    _settings(number_reset_yearly=False, invoice_number_format="F{seq:05d}")
    issue(_draft(issue_date=date(2024, 5, 1)))

    assert next_sequence_number_is_fixed("invoice")


def test_imported_invoices_do_not_fix_it():
    # After an import whose numbers didn't fit the format, the import
    # message sends the user here.
    _imported("430033")
    NumberSequence.objects.create(kind="invoice", year=2026, last_value=0)

    assert not next_sequence_number_is_fixed("invoice")
    set_next_sequence_number("invoice", FORMAT, year=2026, value=34)
    assert next_sequence_number("invoice", year=2026) == 34


def test_it_never_goes_onto_or_below_an_existing_number():
    # The import already continued after 2026-0042; 40 would give
    # 2026-0042 a second time two invoices later.
    _imported("2026-0042")
    NumberSequence.objects.create(kind="invoice", year=2026, last_value=42)

    with pytest.raises(NumberingError, match="43"):
        set_next_sequence_number("invoice", FORMAT, year=2026, value=40)
    assert next_sequence_number("invoice", year=2026) == 43


def test_a_typo_can_be_set_back_lower():
    # 430 instead of 43: nothing was issued from it, so lower is no gap.
    set_next_sequence_number("invoice", FORMAT, year=2026, value=430)
    set_next_sequence_number("invoice", FORMAT, year=2026, value=43)

    assert next_sequence_number("invoice", year=2026) == 43


def test_last_year_s_imported_numbers_do_not_limit_this_year():
    _imported("2025-0042", issue_date=date(2025, 6, 1))

    set_next_sequence_number("invoice", FORMAT, year=2026, value=5)
    assert next_sequence_number("invoice", year=2026) == 5


def test_an_imported_customer_number_limits_the_sequence():
    _settings(invoice_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    document = _imported("580097")
    Contact.objects.filter(pk=document.contact_id).update(customer_number="58")

    with pytest.raises(NumberingError, match="98"):
        set_next_sequence_number("invoice", "{customer}{seq:04d}", year=None, value=90)


def test_a_number_that_already_exists_is_refused():
    _imported("2026-0050")

    with pytest.raises(NumberingError):
        set_next_sequence_number("invoice", FORMAT, year=2026, value=50)
    assert next_sequence_number("invoice", year=2026) == 1


def test_an_existing_quote_number_does_not_block_an_invoice_number():
    _imported("2026-0050", kind="quote")

    set_next_sequence_number("invoice", FORMAT, year=2026, value=50)
    assert next_sequence_number("invoice", year=2026) == 50


def test_zero_is_refused():
    with pytest.raises(NumberingError):
        set_next_sequence_number("invoice", FORMAT, year=2026, value=0)


def test_quotes_have_their_own_sequence():
    _settings()
    issue(_draft())

    set_next_sequence_number("quote", FORMAT, year=2026, value=7)
    assert next_sequence_number("quote", year=2026) == 7
    assert send_quote(_draft("quote")).number.endswith("2026-0007")
    assert next_sequence_number_is_fixed("quote")


def test_with_a_customer_number_the_sequence_still_counts():
    # Moneybird's own numbering: customer 58, sequence 97 is "580097".
    _settings(invoice_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    set_next_sequence_number("invoice", "{customer}{seq:04d}", year=None, value=97)

    draft = _draft()
    Contact.objects.filter(pk=draft.contact_id).update(customer_number="58")
    draft.refresh_from_db()
    assert issue(draft).number == "580097"


@pytest.mark.django_db(transaction=True)
def test_setting_it_while_invoices_are_issued_leaves_no_gap():
    # Either the number is set before the first invoice, or it is refused:
    # never set halfway, which would leave a gap after what was issued.
    _settings()
    drafts = [_draft() for _ in range(8)]

    def issue_one(document):
        try:
            return issue(document).number
        finally:
            connections.close_all()

    def set_it():
        try:
            set_next_sequence_number("invoice", FORMAT, year=2026, value=100)
            return True
        except NumberingError:
            return False
        finally:
            connections.close_all()

    try:
        with ThreadPoolExecutor(max_workers=9) as pool:
            setting = pool.submit(set_it)
            numbers = list(pool.map(issue_one, drafts))
            was_set = setting.result()

        sequence = sorted(int(number.split("-")[1]) for number in numbers)
        first = 100 if was_set else 1
        assert sequence == list(range(first, first + len(drafts)))
    finally:
        clean_up_issued_documents_for_flush()
