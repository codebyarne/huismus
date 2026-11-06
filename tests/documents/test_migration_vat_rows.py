# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""0016: every document already issued gets its VAT per rate once, as
issue() would have stored it; the documents and their lines stay as they
were, and an import whose totals are Moneybird's own gets none (approved by
the owner on 2026-11-06, huismus-intern/besluiten.md, "Btw vastleggen:
factuur per tarief")."""

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.usefixtures("newest_migrations_after"),
]

BEFORE = ("documents", "0015_reverse_charge")
AFTER = ("documents", "0016_vat_rows")


def _issued(Document, Line, *, number, lines, subtotal, tax, kind="invoice"):
    document = Document.objects.create(kind=kind, status="draft", number=number)
    for position, (price, rate, reverse_charge) in enumerate(lines):
        Line.objects.create(
            document=document,
            position=position,
            description=f"Regel {position}",
            quantity=1,
            unit_price_cents=price,
            tax_rate_bp=rate,
            reverse_charge=reverse_charge,
            line_total_cents=price,
        )
    Document.objects.filter(pk=document.pk).update(
        status="issued", subtotal_cents=subtotal, tax_cents=tax, total_cents=subtotal + tax
    )
    return document


def test_issued_documents_get_their_vat_per_rate_and_stay_as_they_were():
    executor = MigrationExecutor(connection)
    executor.migrate([BEFORE])
    old = executor.loader.project_state([BEFORE]).apps
    Document = old.get_model("documents", "Document")
    Line = old.get_model("documents", "DocumentLine")
    mixed = _issued(
        Document,
        Line,
        number="2026-0001",
        lines=[(1005, 2100, False), (1005, 2100, False), (5000, 900, False), (7000, 0, True)],
        subtotal=14010,
        tax=872,
    )
    credit_note = _issued(
        Document,
        Line,
        number="2026-0002",
        kind="credit_note",
        lines=[(10000, 2100, False)],
        subtotal=10000,
        tax=2100,
    )
    # Moneybird's own totals, a cent off its lines.
    imported = _issued(
        Document, Line, number="430033", lines=[(10000, 2100, False)], subtotal=10000, tax=2101
    )
    draft = Document.objects.create(kind="invoice", status="draft")
    Line.objects.create(
        document=draft, description="Concept", unit_price_cents=100, tax_rate_bp=2100
    )
    quote = Document.objects.create(kind="quote", status="sent", number="O-1")
    before = list(Document.objects.order_by("pk").values())
    before_lines = list(Line.objects.order_by("pk").values())

    executor = MigrationExecutor(connection)
    executor.migrate([AFTER])

    new = executor.loader.project_state([AFTER]).apps
    Row = new.get_model("documents", "DocumentVatRow")

    def rows(document):
        return list(
            Row.objects.filter(document_id=document.pk)
            .order_by("rate_bp", "reverse_charge")
            .values_list("rate_bp", "reverse_charge", "revenue_cents", "tax_cents")
        )

    assert rows(mixed) == [(0, True, 7000, 0), (900, False, 5000, 450), (2100, False, 2010, 422)]
    assert rows(credit_note) == [(2100, False, 10000, 2100)]
    assert rows(imported) == []
    assert rows(draft) == []
    assert rows(quote) == []
    NewDocument = new.get_model("documents", "Document")
    NewLine = new.get_model("documents", "DocumentLine")
    assert list(NewDocument.objects.order_by("pk").values()) == before
    assert list(NewLine.objects.order_by("pk").values()) == before_lines

    # The triggers bite from now on.
    with pytest.raises(Exception, match="immutable"):
        Row.objects.filter(document_id=mixed.pk).update(tax_cents=0)

    from tests.support import clean_up_issued_documents_for_flush

    executor = MigrationExecutor(connection)
    executor.migrate(executor.loader.graph.leaf_nodes())
    clean_up_issued_documents_for_flush()
