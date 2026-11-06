# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT of an issued document per rate, stored once (decided by the
owner on 2026-11-06, huismus-intern/besluiten.md, "Btw vastleggen: factuur
per tarief"): on issuing, each invoice and credit note keeps its revenue
and VAT per rate, reverse charge apart, exactly as on the PDF, and that
never changes afterwards. The VAT return reads these rows."""

import pytest
from django.db import IntegrityError, connection, transaction

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import issue
from huismus.documents.models import (
    Document,
    DocumentLine,
    DocumentVatRow,
    ImmutableDocumentError,
)
from huismus.documents.reopening import reopen, undo_reopen
from huismus.documents.totals import compute_totals, vat_rows

pytestmark = pytest.mark.django_db


def _settings(*, kor=False):
    settings = Settings.load()
    for key, value in {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "vat_number": "NL000099998B57",
        "kor_enabled": kor,
        "kor_text": "Vrijgesteld van btw (voorbeeldtekst).",
        "reverse_charge_text": "Btw verlegd (voorbeeldtekst).",
    }.items():
        setattr(settings, key, value)
    settings.save()
    return settings


def _draft(*lines, kind="invoice", related=None):
    """lines: (unit_price_cents, rate_bp, reverse_charge) per line."""
    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=Contact.objects.create(company_name="Klant BV"),
        related_document=related,
    )
    for position, (price, rate, reverse_charge) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position}",
            quantity="1",
            unit_price_cents=price,
            tax_rate_bp=rate,
            reverse_charge=reverse_charge,
        )
    return document


def _rows(document):
    return [
        (row.rate_bp, row.reverse_charge, row.revenue_cents, row.tax_cents)
        for row in document.vat_rows.all()
    ]


def test_issuing_stores_revenue_and_vat_per_rate_with_reverse_charge_apart():
    _settings()
    document = _draft(
        (1005, 2100, False),
        (1005, 2100, False),
        (1005, 2100, False),
        (5000, 900, False),
        (2000, 0, False),
        (7000, 0, True),
    )

    issue(document)

    assert _rows(document) == [
        (0, False, 2000, 0),
        (0, True, 7000, 0),
        (900, False, 5000, 450),
        # 21% of € 30,15 is € 6,3315: per rate, not per line (invariant 3).
        (2100, False, 3015, 633),
    ]
    assert sum(row[2] for row in _rows(document)) == document.subtotal_cents
    assert sum(row[3] for row in _rows(document)) == document.tax_cents


def test_a_kor_invoice_has_one_row_at_zero_percent():
    _settings(kor=True)
    document = _draft((12500, 0, False))

    issue(document)

    assert _rows(document) == [(0, False, 12500, 0)]


def test_a_credit_note_has_rows_like_its_own_totals():
    """A credit note stores its amounts positive, like its totals; the
    export and the VAT return count it negative by its kind."""
    _settings()
    invoice = issue(_draft((10000, 2100, False)))
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))

    issue(credit_note)

    assert _rows(credit_note) == [(2100, False, 10000, 2100)]


def test_the_rows_of_an_issued_document_cannot_change_in_the_model():
    _settings()
    document = issue(_draft((10000, 2100, False)))
    row = document.vat_rows.get()

    row.tax_cents = 0
    with pytest.raises(ImmutableDocumentError):
        row.save()
    with pytest.raises(ImmutableDocumentError):
        row.delete()
    with pytest.raises(ImmutableDocumentError):
        DocumentVatRow.objects.create(
            document=document, rate_bp=900, reverse_charge=False, revenue_cents=1, tax_cents=0
        )


@pytest.mark.parametrize(
    "sql",
    [
        "UPDATE documents_documentvatrow SET tax_cents = 0",
        "DELETE FROM documents_documentvatrow",
        "INSERT INTO documents_documentvatrow "
        "(created_at, updated_at, document_id, rate_bp, reverse_charge, revenue_cents, tax_cents)"
        " VALUES (datetime(), datetime(), {pk}, 900, 0, 1, 0)",
    ],
)
def test_the_rows_of_an_issued_document_cannot_change_in_the_database(sql):
    _settings()
    document = issue(_draft((10000, 2100, False)))

    with pytest.raises(IntegrityError), transaction.atomic(), connection.cursor() as cursor:
        cursor.execute(sql.format(pk=document.pk))

    assert _rows(document) == [(2100, False, 10000, 2100)]


def test_toch_bewerken_and_issuing_again_replaces_the_rows():
    _settings()
    document = issue(_draft((10000, 2100, False)))
    reopen(document)
    DocumentLine.objects.filter(document=document).update(tax_rate_bp=900)

    issue(document)

    assert _rows(document) == [(900, False, 10000, 900)]


def test_annuleren_after_toch_bewerken_keeps_the_rows_it_was_issued_with():
    """The stored rows themselves, not a new sum: even when Huismus would
    compute them differently by now (here: a row changed while a draft)."""
    _settings()
    document = issue(_draft((10000, 2100, False)))
    reopen(document)
    DocumentLine.objects.filter(document=document).update(tax_rate_bp=900)
    DocumentVatRow.objects.filter(document=document).update(revenue_cents=9999)

    undo_reopen(document)

    assert _rows(document) == [(2100, False, 9999, 2100)]


def test_annuleren_stores_the_rows_of_a_document_reopened_before_they_existed():
    """A document reopened before this was built has no rows; when it is
    issued again by "Annuleren" it gets the rows of what it was issued as."""
    _settings()
    document = issue(_draft((10000, 2100, False)))
    reopen(document)
    DocumentVatRow.objects.filter(document=document).delete()  # a draft now
    DocumentLine.objects.filter(document=document).update(tax_rate_bp=900)

    undo_reopen(document)

    assert _rows(document) == [(2100, False, 10000, 2100)]


def test_vat_rows_are_none_when_the_stored_totals_are_not_those_of_the_lines():
    """An import with Moneybird's own totals (a discount, a rounding cent):
    Huismus doesn't guess a split (hard rule 6)."""
    lines = list(_draft((10000, 2100, False)).lines.all())

    assert vat_rows(lines, subtotal_cents=9000, tax_cents=1890) is None


def test_vat_rows_come_from_the_one_totals_function():
    document = _draft((1005, 2100, False), (999, 900, False), (500, 0, True))
    lines = list(document.lines.all())
    totals = compute_totals(lines)

    rows = vat_rows(lines, subtotal_cents=totals.subtotal_cents, tax_cents=totals.tax_cents)

    assert [(r.rate_bp, r.reverse_charge, r.revenue_cents, r.tax_cents) for r in rows] == [
        (0, True, 500, 0),
        (900, False, 999, 90),
        (2100, False, 1005, 211),
    ]
