# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# "Btw verlegd" (SPEC.md M18): a line may be reverse charged, and a document
# keeps the reverse charge text it was issued with.
#
# Columns are added with ALTER TABLE instead of Django's AddField, as in
# 0012: for a NOT NULL column SQLite's schema editor rebuilds the table, and
# dropping a table takes the immutability triggers (0003, 0008) with it.
# Adding a column leaves every row and trigger as it was.
#
# The document's update trigger from 0008 is replaced by the same trigger
# with one more condition: "Toch bewerken" keeps the new snapshot too, like
# the KOR text. Its other conditions are copied unchanged.
from django.db import migrations, models

UPDATE_TRIGGER = """
CREATE TRIGGER documents_document_immutable_update
BEFORE UPDATE ON documents_document
WHEN OLD.status = 'issued' AND NOT (
    NEW.status = 'draft'
    AND NEW.reopened_at IS NOT NULL
    AND NEW.reopened_at IS NOT OLD.reopened_at
    AND NEW.kind = OLD.kind
    AND NEW.number = OLD.number
    AND NEW.issue_date IS OLD.issue_date
    AND NEW.contact_id IS OLD.contact_id
    AND NEW.contact_snapshot IS OLD.contact_snapshot
    AND NEW.business_snapshot IS OLD.business_snapshot
    AND NEW.kor_text_snapshot = OLD.kor_text_snapshot
    AND NEW.reverse_charge_text_snapshot = OLD.reverse_charge_text_snapshot
    AND NEW.subtotal_cents = OLD.subtotal_cents
    AND NEW.tax_cents = OLD.tax_cents
    AND NEW.total_cents = OLD.total_cents
    AND NEW.related_document_id IS OLD.related_document_id
    AND NEW.source = OLD.source
    AND NEW.external_id = OLD.external_id
)
BEGIN
    SELECT RAISE(ABORT, 'Issued documents are immutable.');
END;
"""

# 0008's version, for going back.
OLD_UPDATE_TRIGGER = """
CREATE TRIGGER documents_document_immutable_update
BEFORE UPDATE ON documents_document
WHEN OLD.status = 'issued' AND NOT (
    NEW.status = 'draft'
    AND NEW.reopened_at IS NOT NULL
    AND NEW.reopened_at IS NOT OLD.reopened_at
    AND NEW.kind = OLD.kind
    AND NEW.number = OLD.number
    AND NEW.issue_date IS OLD.issue_date
    AND NEW.contact_id IS OLD.contact_id
    AND NEW.contact_snapshot IS OLD.contact_snapshot
    AND NEW.business_snapshot IS OLD.business_snapshot
    AND NEW.kor_text_snapshot = OLD.kor_text_snapshot
    AND NEW.subtotal_cents = OLD.subtotal_cents
    AND NEW.tax_cents = OLD.tax_cents
    AND NEW.total_cents = OLD.total_cents
    AND NEW.related_document_id IS OLD.related_document_id
    AND NEW.source = OLD.source
    AND NEW.external_id = OLD.external_id
)
BEGIN
    SELECT RAISE(ABORT, 'Issued documents are immutable.');
END;
"""

DROP_UPDATE_TRIGGER = "DROP TRIGGER IF EXISTS documents_document_immutable_update;"

# For tests/support.py: the triggers as they are after this migration.
DROP_TRIGGERS = DROP_UPDATE_TRIGGER
CREATE_TRIGGERS = UPDATE_TRIGGER


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0014_quote_answer_dates"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE documents_document "
                    "ADD COLUMN reverse_charge_text_snapshot text NOT NULL DEFAULT ''",
                    reverse_sql="ALTER TABLE documents_document "
                    "DROP COLUMN reverse_charge_text_snapshot",
                ),
                migrations.RunSQL(
                    sql="ALTER TABLE documents_documentline "
                    "ADD COLUMN reverse_charge bool NOT NULL DEFAULT 0",
                    reverse_sql="ALTER TABLE documents_documentline DROP COLUMN reverse_charge",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="document",
                    name="reverse_charge_text_snapshot",
                    field=models.TextField(blank=True, verbose_name="tekst-snapshot btw verlegd"),
                ),
                migrations.AddField(
                    model_name="documentline",
                    name="reverse_charge",
                    field=models.BooleanField(default=False, verbose_name="btw verlegd"),
                ),
            ],
        ),
        migrations.RunSQL(
            sql=DROP_UPDATE_TRIGGER + UPDATE_TRIGGER,
            reverse_sql=DROP_UPDATE_TRIGGER + OLD_UPDATE_TRIGGER,
        ),
    ]
