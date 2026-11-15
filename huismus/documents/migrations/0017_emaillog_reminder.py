# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# A mail can be a payment reminder (#114). Every mail sent before was not.
#
# The column is added with ALTER TABLE instead of Django's AddField, as in
# 0015: for a NOT NULL column SQLite's schema editor rebuilds the table, and
# dropping it would take the mail log's append-only triggers (0010) along.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0016_vat_rows"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE documents_emaillog "
                    "ADD COLUMN reminder bool NOT NULL DEFAULT 0",
                    reverse_sql="ALTER TABLE documents_emaillog DROP COLUMN reminder",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="emaillog",
                    name="reminder",
                    field=models.BooleanField(default=False, verbose_name="herinnering"),
                ),
            ],
        ),
    ]
