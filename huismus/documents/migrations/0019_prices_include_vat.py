# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# "Prijzen inclusief btw" (#362): a document's line prices may include VAT.
#
# The column is added with ALTER TABLE instead of Django's AddField, as in
# 0012 and 0015: for a NOT NULL column SQLite's schema editor rebuilds the
# table, and dropping a table takes the immutability triggers (0003, 0008)
# with it. Adding a column leaves every row and trigger as it was; every
# existing document gets 0 (prices without VAT, as they were).
#
# The update trigger needs no new condition: on an issued document it lets
# only "Toch bewerken" through, which doesn't change this column.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0018_recurring_invoices"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql="ALTER TABLE documents_document "
                    "ADD COLUMN prices_include_vat bool NOT NULL DEFAULT 0",
                    reverse_sql="ALTER TABLE documents_document DROP COLUMN prices_include_vat",
                ),
            ],
            state_operations=[
                migrations.AddField(
                    model_name="document",
                    name="prices_include_vat",
                    field=models.BooleanField(default=False, verbose_name="prijzen inclusief btw"),
                ),
            ],
        ),
    ]
