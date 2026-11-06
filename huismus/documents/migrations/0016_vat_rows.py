# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
# The VAT per rate of an issued invoice or credit note, kept as on its PDF
# (DocumentVatRow; decided by the owner on 2026-11-06,
# huismus-intern/besluiten.md, "Btw vastleggen: factuur per tarief").
#
# Every document already issued gets its rows once, from the one totals
# function, as issue() would have stored them; the documents themselves
# and their lines are not touched (approved by the owner the same day,
# escalation point 3). An import whose stated totals are not those of its
# lines gets none: Huismus doesn't guess a split (hard rule 6).
#
# The sum is a frozen copy of documents.totals.vat_rows() as it is today,
# not an import of it: a later change there must not change what this
# migration does. tests/documents/test_migration_vat_rows.py pins it.
#
# The rows are added before the triggers exist; afterwards the rows of an
# issued document can't be added, changed or removed, like its lines (0003).
from decimal import ROUND_HALF_UP, Decimal

import django.db.models.deletion
from django.db import migrations, models

CREATE_TRIGGERS = """
CREATE TRIGGER documents_documentvatrow_immutable_update
BEFORE UPDATE ON documents_documentvatrow
WHEN (SELECT status FROM documents_document WHERE id = OLD.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'The VAT of an issued document is immutable.');
END;

CREATE TRIGGER documents_documentvatrow_immutable_delete
BEFORE DELETE ON documents_documentvatrow
WHEN (SELECT status FROM documents_document WHERE id = OLD.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'The VAT of an issued document is immutable.');
END;

CREATE TRIGGER documents_documentvatrow_immutable_insert
BEFORE INSERT ON documents_documentvatrow
WHEN (SELECT status FROM documents_document WHERE id = NEW.document_id) = 'issued'
BEGIN
    SELECT RAISE(ABORT, 'Cannot add VAT to an issued document.');
END;
"""

DROP_TRIGGERS = """
DROP TRIGGER IF EXISTS documents_documentvatrow_immutable_update;
DROP TRIGGER IF EXISTS documents_documentvatrow_immutable_delete;
DROP TRIGGER IF EXISTS documents_documentvatrow_immutable_insert;
"""


def _cents(value: Decimal) -> int:
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _rows(document, lines):
    """(rate, reverse charge, revenue, VAT) per rate, VAT per rate group
    half-up (invariant 3); None when the stored totals are not the lines'."""
    revenue = {}
    by_rate = {}
    for line in lines:
        quantity = Decimal(1) if line.quantity is None else Decimal(line.quantity)
        cents = _cents(quantity * Decimal(line.unit_price_cents))
        key = (line.tax_rate_bp, bool(line.reverse_charge))
        revenue[key] = revenue.get(key, 0) + cents
        by_rate[line.tax_rate_bp] = by_rate.get(line.tax_rate_bp, 0) + cents
    tax = {rate: _cents(Decimal(cents) * rate / 10000) for rate, cents in by_rate.items()}
    if (sum(by_rate.values()), sum(tax.values())) != (document.subtotal_cents, document.tax_cents):
        return None
    return [
        (rate, reverse_charge, cents, 0 if reverse_charge else tax[rate])
        for (rate, reverse_charge), cents in sorted(revenue.items())
    ]


def add_rows_to_issued_documents(apps, schema_editor):
    Document = apps.get_model("documents", "Document")
    DocumentVatRow = apps.get_model("documents", "DocumentVatRow")
    issued = Document.objects.filter(kind__in=["invoice", "credit_note"], status="issued")
    for document in issued.iterator():
        rows = _rows(document, document.lines.all())
        DocumentVatRow.objects.bulk_create(
            DocumentVatRow(
                document=document,
                rate_bp=rate,
                reverse_charge=reverse_charge,
                revenue_cents=revenue,
                tax_cents=tax,
            )
            for rate, reverse_charge, revenue, tax in rows or []
        )


class Migration(migrations.Migration):
    dependencies = [
        ("documents", "0015_reverse_charge"),
    ]

    operations = [
        migrations.CreateModel(
            name="DocumentVatRow",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("rate_bp", models.PositiveIntegerField(verbose_name="btw-tarief (basispunten)")),
                ("reverse_charge", models.BooleanField(default=False, verbose_name="btw verlegd")),
                ("revenue_cents", models.BigIntegerField(verbose_name="omzet (cent)")),
                ("tax_cents", models.BigIntegerField(verbose_name="btw (cent)")),
                (
                    "document",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vat_rows",
                        to="documents.document",
                    ),
                ),
            ],
            options={
                "verbose_name": "btw per tarief",
                "verbose_name_plural": "btw per tarief",
                "ordering": ["document", "rate_bp", "reverse_charge"],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("document", "rate_bp", "reverse_charge"),
                        name="documents_vat_row_unique_rate",
                    )
                ],
            },
        ),
        migrations.RunPython(add_rows_to_issued_documents, migrations.RunPython.noop),
        migrations.RunSQL(sql=CREATE_TRIGGERS, reverse_sql=DROP_TRIGGERS),
    ]
