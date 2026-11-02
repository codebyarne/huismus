# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# Document.attention, the "T.a.v." line. A plain ALTER TABLE ADD COLUMN
# instead of Django's AddField: for a NOT NULL column SQLite's schema editor
# rebuilds the table (copy, drop, rename), and dropping documents_document
# breaks the immutability triggers on documents_documentline that refer to
# it (0003). Adding a column leaves every row and trigger as it was; the
# triggers from 0008 refuse any change to an issued row, this column too.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0011_document_before_reopening"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE documents_document "
                    "ADD COLUMN attention varchar(200) NOT NULL DEFAULT ''",
                    reverse_sql="ALTER TABLE documents_document DROP COLUMN attention",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="document",
                    name="attention",
                    field=models.CharField(blank=True, max_length=200, verbose_name="t.a.v."),
                ),
            ],
        ),
    ]
