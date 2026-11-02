# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# "Toch bewerken" (documents.reopening): an issued invoice or credit note
# may go back to draft, keeping its number, when the user explicitly
# chooses so. The update trigger from 0003 lets exactly that one change
# through: status issued -> draft with a new reopened_at, everything that
# was issued (number, dates, customer, snapshots, totals) unchanged in the
# same statement. Any other change to an issued row is still refused.
#
# The delete trigger also refuses a numbered draft invoice or credit note
# (a reopened one, or one imported from Moneybird as scheduled): deleting
# it would leave a gap in the numbering (invariant 2).
#
# Both triggers keep their names from 0003; tests/support.py recreates
# them from CREATE_TRIGGERS here after 0003's own.
from django.db import migrations, models

CREATE_TRIGGERS = """
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

CREATE TRIGGER documents_document_immutable_delete
BEFORE DELETE ON documents_document
WHEN OLD.status = 'issued'
    OR (OLD.kind IN ('invoice', 'credit_note') AND OLD.number != '')
BEGIN
    SELECT RAISE(ABORT, 'Issued documents are immutable.');
END;
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS documents_document_immutable_update;
DROP TRIGGER IF EXISTS documents_document_immutable_delete;
"""

# 0003's versions of the same two triggers.
OLD_TRIGGERS = """
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
"""


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0007_line_quantity_optional"),
    ]

    operations = [
        migrations.AddField(
            model_name="document",
            name="reopened_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="heropend op"),
        ),
        migrations.RunSQL(
            sql=DROP_TRIGGERS + CREATE_TRIGGERS,
            reverse_sql=DROP_TRIGGERS + OLD_TRIGGERS,
        ),
    ]
