# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# "Aantal" may be left empty (a fixed price). On SQLite, making a column
# nullable rebuilds the table, and DROP TABLE takes the immutability
# triggers of 0003 with it. They are removed first and created again after,
# from the very SQL of 0003 (an applied migration, which is never edited),
# so the immutability rule is never left unprotected.
import importlib

from django.db import migrations, models

_triggers = importlib.import_module("huismus.documents.migrations.0003_immutability_triggers")


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0006_document_documents_unique_source_external_id"),
    ]

    operations = [
        migrations.RunSQL(sql=_triggers.DROP_TRIGGERS, reverse_sql=_triggers.CREATE_TRIGGERS),
        migrations.AlterField(
            model_name="documentline",
            name="quantity",
            field=models.DecimalField(
                blank=True, decimal_places=3, max_digits=10, null=True, verbose_name="aantal"
            ),
        ),
        migrations.RunSQL(sql=_triggers.CREATE_TRIGGERS, reverse_sql=_triggers.DROP_TRIGGERS),
    ]
