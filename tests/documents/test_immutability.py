# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.db import IntegrityError, connection

from huismus.documents.models import Document, DocumentLine, ImmutableDocumentError

pytestmark = pytest.mark.django_db


def _draft_invoice(**overrides):
    fields = {"kind": "invoice", "status": "draft"}
    fields.update(overrides)
    return Document.objects.create(**fields)


def _issue(document):
    # Mimics the one legitimate mutation without going through the full
    # documents.issuing flow (not built yet) — just the status flip that
    # immutability cares about.
    document.status = "issued"
    document.number = "2026-0001"
    document.save()
    return document


# --- Model-level enforcement (Document) ---------------------------------


def test_draft_document_can_be_saved_repeatedly():
    document = _draft_invoice()
    document.notes = "eerste concept"
    document.save()
    document.notes = "tweede concept"
    document.save()  # must not raise


def test_the_draft_to_issued_transition_itself_is_allowed():
    document = _draft_invoice()
    _issue(document)  # must not raise
    document.refresh_from_db()
    assert document.status == "issued"


def test_saving_an_already_issued_document_is_blocked():
    document = _issue(_draft_invoice())
    document.notes = "poging tot wijziging"
    with pytest.raises(ImmutableDocumentError):
        document.save()


def test_deleting_an_issued_document_is_blocked():
    document = _issue(_draft_invoice())
    with pytest.raises(ImmutableDocumentError):
        document.delete()


def test_deleting_a_draft_document_is_allowed():
    document = _draft_invoice()
    document.delete()  # must not raise
    assert not Document.objects.filter(pk=document.pk).exists()


# --- Model-level enforcement (DocumentLine) ------------------------------


def test_lines_can_be_added_edited_and_removed_while_draft():
    document = _draft_invoice()
    line = DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    line.description = "Consult (aangepast)"
    line.save()  # must not raise
    line.delete()  # must not raise


def test_adding_a_line_to_an_issued_document_is_blocked():
    document = _issue(_draft_invoice())
    with pytest.raises(ImmutableDocumentError):
        DocumentLine.objects.create(
            document=document, description="Te laat", quantity="1", unit_price_cents=100
        )


def test_editing_a_line_of_an_issued_document_is_blocked():
    document = _draft_invoice()
    line = DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    _issue(document)
    line.description = "Stiekem gewijzigd"
    with pytest.raises(ImmutableDocumentError):
        line.save()


def test_deleting_a_line_of_an_issued_document_is_blocked():
    document = _draft_invoice()
    line = DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    _issue(document)
    with pytest.raises(ImmutableDocumentError):
        line.delete()


# --- SQLite trigger enforcement (defense in depth, bypassing the model) -


def _raw_sql(sql, params=()):
    with connection.cursor() as cursor:
        cursor.execute(sql, params)


def test_trigger_blocks_raw_update_of_an_issued_document():
    document = _issue(_draft_invoice())
    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("UPDATE documents_document SET notes = %s WHERE id = %s", ["hack", document.pk])


def test_trigger_blocks_raw_delete_of_an_issued_document():
    document = _issue(_draft_invoice())
    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("DELETE FROM documents_document WHERE id = %s", [document.pk])


def test_trigger_allows_raw_update_of_a_draft_document():
    document = _draft_invoice()
    _raw_sql("UPDATE documents_document SET notes = %s WHERE id = %s", ["ok", document.pk])
    document.refresh_from_db()
    assert document.notes == "ok"


def test_trigger_blocks_raw_update_of_a_line_on_an_issued_document():
    document = _draft_invoice()
    line = DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    _issue(document)
    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql(
            "UPDATE documents_documentline SET description = %s WHERE id = %s",
            ["hack", line.pk],
        )


def test_trigger_blocks_raw_delete_of_a_line_on_an_issued_document():
    document = _draft_invoice()
    line = DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    _issue(document)
    with pytest.raises(IntegrityError, match="immutable"):
        _raw_sql("DELETE FROM documents_documentline WHERE id = %s", [line.pk])


def test_trigger_blocks_raw_insert_of_a_line_on_an_issued_document():
    document = _issue(_draft_invoice())
    with pytest.raises(IntegrityError, match="Cannot add"):
        _raw_sql(
            """
            INSERT INTO documents_documentline
                (document_id, position, description, quantity, unit, unit_price_cents,
                 tax_rate_bp, line_total_cents, created_at, updated_at)
            VALUES (%s, 0, 'stiekem', 1, '', 100, 0, 100, datetime('now'), datetime('now'))
            """,
            [document.pk],
        )
