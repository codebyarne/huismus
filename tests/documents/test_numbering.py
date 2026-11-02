# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from concurrent.futures import ThreadPoolExecutor

import pytest
from django.db import connections, transaction

from huismus.documents.models import NumberSequence
from huismus.documents.numbering import (
    allocate_number,
    ensure_sequence_row,
    format_number,
    parse_number,
    peek_next_number,
)

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_allocate_number_requires_an_atomic_block():
    # plain @pytest.mark.django_db already wraps every test in an implicit
    # atomic block for rollback purposes, so this needs transaction=True to
    # actually observe "not in an atomic block" at all.
    with pytest.raises(RuntimeError):
        allocate_number("invoice", year=None)


def test_allocate_number_starts_at_one_and_increments():
    with transaction.atomic():
        assert allocate_number("invoice", year=None) == 1
        assert allocate_number("invoice", year=None) == 2
        assert allocate_number("invoice", year=None) == 3


def test_allocate_number_keeps_separate_sequences_per_kind():
    with transaction.atomic():
        assert allocate_number("invoice", year=None) == 1
        assert allocate_number("quote", year=None) == 1
        assert allocate_number("invoice", year=None) == 2


def test_allocate_number_keeps_separate_sequences_per_year():
    with transaction.atomic():
        assert allocate_number("invoice", year=2025) == 1
        assert allocate_number("invoice", year=2026) == 1
        assert allocate_number("invoice", year=2025) == 2


def test_format_number_fills_in_year_and_sequence():
    assert format_number("{year}-{seq:04d}", year=2026, seq=7) == "2026-0007"


def test_parse_number_inverts_format_number():
    formatted = format_number("{year}-{seq:04d}", year=2026, seq=7)
    assert parse_number("{year}-{seq:04d}", formatted, year=2026) == 7


def test_parse_number_rejects_a_number_that_does_not_fit_the_template():
    # Real Moneybird numbers ("430033") don't fit Huismus's default
    # "{year}-{seq:04d}" shape at all — SPEC.md's documented case where
    # the user sets the next number manually, not a bug.
    assert parse_number("{year}-{seq:04d}", "430033", year=2019) is None


def test_parse_number_rejects_a_number_from_the_wrong_year():
    formatted = format_number("{year}-{seq:04d}", year=2025, seq=7)
    assert parse_number("{year}-{seq:04d}", formatted, year=2026) is None


@pytest.mark.django_db(transaction=True)
def test_allocate_number_is_gap_free_and_duplicate_free_under_concurrency():
    # transaction=True: a real TransactionTestCase-style test, with actual
    # committed transactions on the real SQLite file — a plain
    # django_db()-wrapped test runs everything inside one rolled-back
    # savepoint, which can't exercise a genuine cross-thread/cross-
    # connection race at all.
    thread_count = 20

    def issue_one():
        try:
            with transaction.atomic():
                return allocate_number("invoice", year=None)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        numbers = list(pool.map(lambda _: issue_one(), range(thread_count)))

    assert sorted(numbers) == list(range(1, thread_count + 1))
    assert NumberSequence.objects.get(kind="invoice", year=None).last_value == thread_count


@pytest.mark.django_db(transaction=True)
def test_ensure_sequence_row_is_race_safe_for_concurrent_first_creation():
    # huismus/imports/commit.py's numbering continuation shares ensure_sequence_row
    # with allocate_number() specifically to avoid a second, independent
    # SELECT-then-INSERT (get_or_create()) on this table racing a real
    # allocate_number() call — found by review once the import started
    # writing to NumberSequence too. This exercises that directly, not
    # just through allocate_number()'s own callers.
    thread_count = 20

    def ensure_one():
        try:
            with transaction.atomic():
                ensure_sequence_row("invoice", 2030)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        list(pool.map(lambda _: ensure_one(), range(thread_count)))

    assert NumberSequence.objects.filter(kind="invoice", year=2030).count() == 1


# --- peek_next_number(): a read-only preview for the settings page (M8). ---


def test_peek_next_number_on_an_empty_sequence_is_one_and_creates_nothing():
    assert peek_next_number("invoice", "{year}-{seq:04d}", year=2026) == "2026-0001"
    assert NumberSequence.objects.count() == 0


def test_peek_next_number_predicts_what_allocate_number_returns():
    with transaction.atomic():
        allocate_number("invoice", 2026)
        allocate_number("invoice", 2026)

    peeked = peek_next_number("invoice", "{year}-{seq:04d}", year=2026)
    with transaction.atomic():
        allocated = format_number(
            "{year}-{seq:04d}", year=2026, seq=allocate_number("invoice", 2026)
        )

    assert peeked == allocated == "2026-0003"


def test_peek_next_number_does_not_change_the_sequence():
    with transaction.atomic():
        allocate_number("quote", None)
    peek_next_number("quote", "OFF-{seq:04d}", year=None)
    peek_next_number("quote", "OFF-{seq:04d}", year=None)
    assert NumberSequence.objects.get(kind="quote", year=None).last_value == 1


def test_peek_next_number_returns_none_for_a_broken_format():
    assert peek_next_number("invoice", "{jaar}-{seq}", year=2026) is None


# {customer}: Moneybird's default numbering is the contact's customer
# number followed by one running sequence for all customers ("580097" is
# customer 58, sequence 97), and Huismus continues it after an import.


def test_format_number_fills_in_the_customer_number():
    assert format_number("{customer}{seq:04d}", year=None, seq=99, customer="58") == "580099"


def test_parse_number_with_a_customer_number():
    assert parse_number("{customer}{seq:04d}", "580097", year=None, customer="58") == 97


def test_parse_number_with_another_customer_s_number_does_not_fit():
    assert parse_number("{customer}{seq:04d}", "580097", year=None, customer="43") is None


def test_peek_next_number_shows_where_the_customer_number_goes():
    assert peek_next_number("invoice", "{customer}{seq:04d}", year=None) == "[klantnummer]0001"


def test_peek_next_number_for_a_known_customer():
    number = peek_next_number("invoice", "{customer}{seq:04d}", year=None, customer="58")
    assert number == "580001"


def test_no_preview_number_says_none_for_a_missing_year():
    # Every caller of the preview (settings, onboarding): {year} without a
    # year gives no number rather than "None-0001".
    assert peek_next_number("invoice", "{year}-{seq:04d}", year=None) is None
    assert peek_next_number("invoice", "F{seq:04d}", year=None) == "F0001"
