# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Helpers shared by several test modules."""

import importlib

from django.db import connection

_triggers_migration = importlib.import_module(
    "huismus.documents.migrations.0003_immutability_triggers"
)
_reopen_migration = importlib.import_module(
    "huismus.documents.migrations.0008_document_reopened_at"
)
_reverse_charge_migration = importlib.import_module(
    "huismus.documents.migrations.0015_reverse_charge"
)
_email_triggers_migration = importlib.import_module(
    "huismus.documents.migrations.0010_emaillog_append_only_triggers"
)


def clean_up_issued_documents_for_flush():
    """transaction=True tests reset the database via Django's `flush`
    command (a plain DELETE FROM per table) rather than a rolled-back
    savepoint, since they need real commits (a cross-connection race, or a
    browser talking to the live server). The immutability triggers
    correctly refuse that DELETE for the issued rows the test created — by
    design, nothing should be able to delete them, not even test cleanup.
    Dropping the triggers, deleting the test's own documents (and the rows
    pointing at them), then recreating the triggers (reusing the exact SQL
    from the migrations, not a copy that could drift from it) leaves `flush`
    with nothing left to fail on, without weakening the triggers for any
    other test: they're back in place before this function returns, and
    no other test runs concurrently with this one.
    """
    with connection.cursor() as cursor:
        # executescript(), not execute(): DROP/CREATE_TRIGGERS are each
        # several statements, and the DB-API's execute() only ever runs one.
        cursor.executescript(_triggers_migration.DROP_TRIGGERS)
        cursor.executescript(_email_triggers_migration.DROP_TRIGGERS)
        cursor.execute("DELETE FROM documents_emaillog")
        cursor.execute("DELETE FROM documents_payment")
        cursor.execute("DELETE FROM core_attachment WHERE document_id IS NOT NULL")
        cursor.execute("DELETE FROM documents_documentline")
        cursor.execute("DELETE FROM documents_document")
        cursor.executescript(_triggers_migration.CREATE_TRIGGERS)
        # 0008 replaced two of 0003's triggers; recreate them as they are now.
        cursor.executescript(_reopen_migration.DROP_TRIGGERS + _reopen_migration.CREATE_TRIGGERS)
        # 0015 replaced the update trigger once more.
        cursor.executescript(
            _reverse_charge_migration.DROP_TRIGGERS + _reverse_charge_migration.CREATE_TRIGGERS
        )
        cursor.executescript(_email_triggers_migration.CREATE_TRIGGERS)
