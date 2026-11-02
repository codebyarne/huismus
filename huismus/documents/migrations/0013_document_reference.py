# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# Document.reference, the "Kenmerk". ALTER TABLE ADD COLUMN for the same
# reason as 0012: Django would rebuild the table under the line triggers.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0012_document_attention"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE documents_document "
                    "ADD COLUMN reference varchar(100) NOT NULL DEFAULT ''",
                    reverse_sql="ALTER TABLE documents_document DROP COLUMN reference",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="document",
                    name="reference",
                    field=models.CharField(blank=True, max_length=100, verbose_name="kenmerk"),
                ),
            ],
        ),
    ]
