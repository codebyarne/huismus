# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Migrations that rebuild a table must not lose the immutability triggers
(SPEC.md invariant 1) or the issued data."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

TRIGGERS = {
    "documents_document_immutable_update",
    "documents_document_immutable_delete",
    "documents_documentline_immutable_update",
    "documents_documentline_immutable_delete",
    "documents_documentline_immutable_insert",
}


def _triggers():
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        return {name for (name,) in cursor.fetchall() if name.startswith("documents_")}


def test_making_quantity_optional_keeps_the_triggers_and_issued_lines():
    executor = MigrationExecutor(connection)
    executor.migrate([("documents", "0006_document_documents_unique_source_external_id")])
    old_apps = executor.loader.project_state(
        [("documents", "0006_document_documents_unique_source_external_id")]
    ).apps
    Document = old_apps.get_model("documents", "Document")
    Line = old_apps.get_model("documents", "DocumentLine")
    document = Document.objects.create(kind="invoice", status="draft")
    Line.objects.create(
        document=document,
        description="Oud",
        quantity=2,
        unit_price_cents=500,
        line_total_cents=1000,
    )
    Document.objects.filter(pk=document.pk).update(status="issued")

    executor = MigrationExecutor(connection)
    executor.migrate([("documents", "0007_line_quantity_optional")])

    assert _triggers() == TRIGGERS
    new_apps = executor.loader.project_state([("documents", "0007_line_quantity_optional")]).apps
    kept = new_apps.get_model("documents", "DocumentLine").objects.get()
    assert (kept.description, kept.line_total_cents) == ("Oud", 1000)

    # And the triggers still bite: the issued line cannot be changed.
    with pytest.raises(Exception, match="immutable"):
        new_apps.get_model("documents", "DocumentLine").objects.update(description="Nieuw")

    # Leave the database as the other tests expect it (their flush deletes
    # issued rows, which the triggers refuse; see tests/support.py), and at
    # the latest migration, whose tables that clean-up empties too.
    from tests.support import clean_up_issued_documents_for_flush

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    clean_up_issued_documents_for_flush()


def test_adding_reverse_charge_keeps_the_triggers_and_issued_documents():
    """0015 adds two columns without rebuilding a table (SPEC.md M18)."""
    before = ("documents", "0014_quote_answer_dates")
    after = ("documents", "0015_reverse_charge")
    executor = MigrationExecutor(connection)
    executor.migrate([before])
    old_apps = executor.loader.project_state([before]).apps
    Document = old_apps.get_model("documents", "Document")
    Line = old_apps.get_model("documents", "DocumentLine")
    document = Document.objects.create(kind="invoice", status="draft", number="2026-0001")
    Line.objects.create(
        document=document, description="Oud", unit_price_cents=500, line_total_cents=500
    )
    Document.objects.filter(pk=document.pk).update(status="issued", kor_text_snapshot="KOR")

    executor = MigrationExecutor(connection)
    executor.migrate([after])

    # Including the mail log's own (0010), which exist by then.
    assert _triggers() == TRIGGERS | {
        "documents_emaillog_append_only_update",
        "documents_emaillog_append_only_delete",
    }
    new_apps = executor.loader.project_state([after]).apps
    kept = new_apps.get_model("documents", "DocumentLine").objects.get()
    assert (kept.description, kept.reverse_charge) == ("Oud", False)
    issued = new_apps.get_model("documents", "Document").objects.get()
    assert (issued.number, issued.reverse_charge_text_snapshot) == ("2026-0001", "")

    with pytest.raises(Exception, match="immutable"):
        new_apps.get_model("documents", "DocumentLine").objects.update(reverse_charge=True)
    # "Toch bewerken" may not change the new snapshot in the same statement.
    with pytest.raises(Exception, match="immutable"):
        new_apps.get_model("documents", "Document").objects.update(
            status="draft",
            reopened_at="2026-11-02T10:00:00Z",
            reverse_charge_text_snapshot="anders",
        )

    from tests.support import clean_up_issued_documents_for_flush

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    clean_up_issued_documents_for_flush()
