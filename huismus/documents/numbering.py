# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Gap-free document numbering (SPEC.md invariant 2).

The tricky part is concurrency on SQLite specifically: Django's sqlite3
backend does not support SELECT ... FOR UPDATE at all (it silently drops
it), so a Python-side read-increment-write would race under concurrent
issuance. Instead, the increment happens as a single database-side UPDATE
expression (last_value = last_value + 1), which SQLite serializes via its
normal write lock regardless of FOR UPDATE support — the second of two
concurrent writers blocks on that UPDATE (up to DATABASES.OPTIONS.timeout,
set in huismus/config/settings.py) rather than racing to read a stale value.
"""

import re

from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from huismus.contacts.numbering import ensure_customer_number

from .models import Document, NumberSequence


def ensure_sequence_row(kind: str, year: int | None) -> None:
    # Not NumberSequence.objects.get_or_create(): its SELECT-then-INSERT
    # runs inside its own nested savepoint, which under concurrent first-
    # ever-allocation for a (kind, year) raises SQLite's "database table is
    # locked" (SQLITE_LOCKED) — unlike "database is locked" (SQLITE_BUSY),
    # that error is not retried via DATABASES.OPTIONS.timeout at all.
    # INSERT OR IGNORE is a single atomic statement with no such race.
    # Shared by allocate_number() and the Moneybird import's numbering
    # continuation (huismus/imports/commit.py) — both write this table and both
    # need the same protection, found the hard way once already.
    table = NumberSequence._meta.db_table
    now = timezone.now()
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT OR IGNORE INTO {table} "  # noqa: S608 — table name from Django's own metadata, not input
            "(kind, year, last_value, created_at, updated_at) VALUES (%s, %s, 0, %s, %s)",
            [kind, year, now, now],
        )


def allocate_number(kind: str, year: int | None) -> int:
    """Must be called inside the same transaction that issues the document."""
    if not transaction.get_connection().in_atomic_block:
        # A plain exception, not an assert: this is a programmer error in
        # a caller (missing transaction.atomic()), not a condition that
        # should ever depend on -O/PYTHONOPTIMIZE being off to be caught —
        # asserts are stripped entirely under those, silently reopening
        # the exact race this function exists to close.
        raise RuntimeError("allocate_number() must be called inside transaction.atomic()")

    ensure_sequence_row(kind, year)
    NumberSequence.objects.filter(kind=kind, year=year).update(last_value=F("last_value") + 1)
    return (
        NumberSequence.objects.filter(kind=kind, year=year)
        .values_list("last_value", flat=True)
        .get()
    )


# Where the customer number goes when it isn't known yet: the settings
# page shows the next number without a document or contact to take it from.
CUSTOMER_PLACEHOLDER = gettext_lazy("[klantnummer]")


def format_number(
    template: str, *, year: int | None, seq: int, customer: str = CUSTOMER_PLACEHOLDER
) -> str:
    """{year}, {seq} and {customer}: the contact's customer number, for
    Moneybird's own default numbering ("580097" is customer 58 with
    sequence number 97; the sequence runs across all customers)."""
    return template.format(year=year, seq=seq, customer=customer)


def uses_customer_number(template: str) -> bool:
    return "{customer" in template


def number_for(kind: str, template: str, *, year: int | None, contact) -> str:
    """Allocate and format the number of a document being issued or sent.
    Inside the caller's transaction, like allocate_number(): raising here
    rolls the allocation back with everything else, so a refused document
    leaves no gap (invariant 3)."""
    # A contact without a customer number gets the next one here, inside the
    # caller's transaction: if this document is refused, the contact is not
    # left with a number it never used.
    customer = ensure_customer_number(contact) if uses_customer_number(template) else ""
    number = format_number(template, year=year, seq=allocate_number(kind, year), customer=customer)
    # Numbers are unique per series. With {customer} two could coincide
    # (customer 1 at sequence 10012 and customer 11 at 0012 are both
    # "110012"), and an imported document may already hold a number.
    kinds = ["quote"] if kind == "quote" else ["invoice", "credit_note"]
    if Document.objects.filter(kind__in=kinds, number=number).exists():
        raise NumberingError(
            _("Nummer %(number)s bestaat al. Pas het nummerformaat aan in Instellingen.")
            % {"number": number}
        )
    return number


class NumberingError(Exception):
    pass


def peek_next_number(
    kind: str, template: str, *, year: int | None, customer: str = CUSTOMER_PLACEHOLDER
) -> str | None:
    """The number the next issued document of this kind would get, for
    display only (the settings page's "Volgende: ..."). Reads the sequence,
    never creates or changes it — allocate_number() is still the only way
    to get a number (invariant 2). None if the template can't be filled in,
    also for {year} without a year, which format_number() would fill in
    as "None".
    """
    if year is None and "{year" in template:
        return None
    last_value = (
        NumberSequence.objects.filter(kind=kind, year=year)
        .values_list("last_value", flat=True)
        .first()
    )
    try:
        return format_number(template, year=year, seq=(last_value or 0) + 1, customer=customer)
    except (KeyError, IndexError, ValueError):
        return None


def next_numbers_if_issued_today(settings) -> dict[str, str | None]:
    """The settings page's "Volgende als je vandaag uitgeeft: ...", per kind
    ("invoice", "quote"). issue() takes the year of the document's issue
    date; this assumes today. Without a yearly reset the sequence has no
    year (Settings.number_reset_yearly)."""
    year = year_if_issued_today(settings.number_reset_yearly)
    return {
        "invoice": peek_next_number("invoice", settings.invoice_number_format, year=year),
        "quote": peek_next_number("quote", settings.quote_number_format, year=year),
    }


# Which document kinds take their numbers from a sequence: credit notes
# share the invoice sequence (models.SEQUENCE_KIND_CHOICES).
_SEQUENCE_DOCUMENT_KINDS = {"invoice": ["invoice", "credit_note"], "quote": ["quote"]}


def next_sequence_number(kind: str, *, year: int | None) -> int:
    """The {seq} the next document of this sequence gets. Reads only."""
    last_value = (
        NumberSequence.objects.filter(kind=kind, year=year)
        .values_list("last_value", flat=True)
        .first()
    )
    return (last_value or 0) + 1


def next_sequence_number_is_fixed(kind: str) -> bool:
    """True once Huismus itself gave a document of this kind a number, in
    any year. From then on numbers only move by issuing: setting the next
    one by hand could leave a gap after a number Huismus gave, also in a
    new year's sequence (invariant 3). Imported documents don't count:
    their numbers come from the package the user left, which is what the
    user continues by hand. A reopened document ("Toch bewerken") keeps its
    number, so it still counts."""
    return Document.objects.filter(
        kind__in=_SEQUENCE_DOCUMENT_KINDS[kind], number__isnull=False, source=""
    ).exists()


def lowest_next_sequence_number(kind: str, template: str, *, year: int | None) -> int:
    """Just above the highest {seq} already in this sequence: the numbers
    that fit the format, of this year when it resets yearly. Below that the
    sequence would reach a number that exists."""
    highest = 0
    documents = Document.objects.filter(
        kind__in=_SEQUENCE_DOCUMENT_KINDS[kind], number__isnull=False
    ).select_related("contact")
    for document in documents:
        if year is not None and (document.issue_date is None or document.issue_date.year != year):
            continue
        customer = (document.contact.customer_number if document.contact else "") or ""
        seq = parse_number(template, document.number, year=year, customer=customer)
        if seq is not None:
            highest = max(highest, seq)
    return highest + 1


def check_next_sequence_number(kind: str, template: str, *, year: int | None, value: int) -> None:
    """Raise NumberingError if the next {seq} can't be set to `value`
    without a gap or a number twice (invariant 3): not once Huismus issued
    a document of this kind, not onto or below a number that already
    exists. Up and down are both fine before that: nothing was issued from
    the sequence yet, so nothing is skipped. Changes nothing; the settings
    form shows its errors with it, set_next_sequence_number() checks
    again under the write lock."""
    if value < 1:
        raise NumberingError(_("Het volgnummer is minstens 1."))
    if next_sequence_number_is_fixed(kind):
        raise NumberingError(
            _("Je hebt in Huismus al een nummer uitgegeven. Het nummer loopt nu vanzelf door.")
        )
    lowest = lowest_next_sequence_number(kind, template, year=year)
    if value < lowest:
        raise NumberingError(
            _("Kies %(lowest)s of hoger. Een lager nummer bestaat al.") % {"lowest": lowest}
        )
    if not uses_customer_number(template):
        # An existing number that doesn't fit the format (an import) can
        # still be hit exactly. With {customer} the number isn't known
        # until the customer is; number_for() refuses it then.
        number = format_number(template, year=year, seq=value)
        if Document.objects.filter(kind__in=_SEQUENCE_DOCUMENT_KINDS[kind], number=number).exists():
            raise NumberingError(
                _("Nummer %(number)s bestaat al. Kies een hoger volgnummer.") % {"number": number}
            )


def set_next_sequence_number(kind: str, template: str, *, year: int | None, value: int) -> None:
    """Set the {seq} of the next document of this sequence by hand (SPEC.md
    section 7, "the user sets the next number manually"; issue #141), for
    someone continuing the numbers of another package. Raises
    NumberingError where check_next_sequence_number() does. Only the
    sequence row changes; a number is still given only by
    allocate_number(), when issuing."""
    if value == next_sequence_number(kind, year=year):
        return
    with transaction.atomic():
        # A write first, as in allocate_number(): from here SQLite holds the
        # write lock, so no document can be issued between the check and
        # the update. Reading first and writing after could instead
        # deadlock with a concurrent issue().
        ensure_sequence_row(kind, year)
        check_next_sequence_number(kind, template, year=year, value=value)
        NumberSequence.objects.filter(kind=kind, year=year).update(last_value=value - 1)


def year_if_issued_today(reset_yearly: bool) -> int | None:
    """The year of the sequence a document issued today takes; without a
    yearly reset the sequence has no year (Settings.number_reset_yearly)."""
    return timezone.localdate().year if reset_yearly else None


_SEQ_PLACEHOLDER = re.compile(r"\{seq(:[^}]*)?\}")


def parse_number(template: str, number: str, *, year: int | None, customer: str = "") -> int | None:
    """The inverse of format_number() for a known `year` — used by the
    Moneybird import to continue numbering after imported numbers
    (SPEC.md section 7: "the sequence continues after the highest
    imported number"). Returns None if `number` doesn't fit the
    template's shape at all; SPEC.md's fallback for that case is "the
    user sets the next number manually," not a guess.
    """
    match = _SEQ_PLACEHOLDER.search(template)
    if not match:
        return None
    prefix = re.escape(template[: match.start()].format(year=year, customer=customer))
    suffix = re.escape(template[match.end() :].format(year=year, customer=customer))
    parsed = re.match(f"^{prefix}(\\d+){suffix}$", number)
    return int(parsed.group(1)) if parsed else None
