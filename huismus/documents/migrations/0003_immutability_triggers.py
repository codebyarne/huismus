# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# SPEC.md invariant 1: "Once a document is issued, neither the document
# nor its lines can be updated or deleted. Enforced in model save()/
# delete() and by SQLite triggers (RAISE(ABORT)) as defense in depth."
# huismus/documents/models.py's Document/DocumentLine.save()/delete() are the
# primary enforcement; these triggers catch anything that reaches the
# database by another path (a bulk .update()/.delete(), a future
# management command, raw SQL) and fire regardless of which of those.
from django.db import migrations

CREATE_TRIGGERS = """
CREATE TRIGGER documents_document_immutable_update
BEFORE UPDATE ON documents_document
WHEN OLD.status = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Issued documents are immutable.');
END;

CREATE TRIGGER documents_document_immutable_delete
BEFORE DELETE ON documents_document
WHEN OLD.status = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Issued documents are immutable.');
END;

CREATE TRIGGER documents_documentline_immutable_update
BEFORE UPDATE ON documents_documentline
WHEN (SELECT status FROM documents_document WHERE id = OLD.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an issued document are immutable.');
END;

CREATE TRIGGER documents_documentline_immutable_delete
BEFORE DELETE ON documents_documentline
WHEN (SELECT status FROM documents_document WHERE id = OLD.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Lines of an issued document are immutable.');
END;

CREATE TRIGGER documents_documentline_immutable_insert
BEFORE INSERT ON documents_documentline
WHEN (SELECT status FROM documents_document WHERE id = NEW.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Cannot add lines to an issued document.');
END;
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS documents_document_immutable_update;
DROP TRIGGER IF EXISTS documents_document_immutable_delete;
DROP TRIGGER IF EXISTS documents_documentline_immutable_update;
DROP TRIGGER IF EXISTS documents_documentline_immutable_delete;
DROP TRIGGER IF EXISTS documents_documentline_immutable_insert;
"""


class Migration(migrations.Migration):
    dependencies = [("documents", "0002_document_documentline")]

    operations = [migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP_TRIGGERS)]
