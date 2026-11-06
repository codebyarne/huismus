# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stores the VAT per rate of a document that is being issued
(DocumentVatRow; decided by the owner on 2026-11-06,
huismus-intern/besluiten.md, "Btw vastleggen: factuur per tarief").

Called by everything that turns a document into an issued one: issue(),
"Annuleren" after "Toch bewerken" and the Moneybird import. Always while
the document is still a draft in the database, in the same transaction as
the change to issued: an issued document's rows can't change any more.
The amounts come from documents.totals.vat_rows() (invariant 3).
"""

from .models import DocumentVatRow
from .totals import vat_rows


def store_vat_rows(document, lines, *, subtotal_cents: int, tax_cents: int) -> None:
    """Replaces the document's rows with those of `lines` and the totals it
    is issued with. The document must still be a draft in the database:
    the triggers refuse rows of an issued one."""
    DocumentVatRow.objects.filter(document=document).delete()
    rows = vat_rows(lines, subtotal_cents=subtotal_cents, tax_cents=tax_cents)
    if rows is None:
        # Totals that are not the lines' (an import with Moneybird's own
        # totals): no rows rather than a guessed split. Having none is how
        # such a document can be told apart later (SPEC.md M21).
        return
    DocumentVatRow.objects.bulk_create(
        DocumentVatRow(
            document=document,
            rate_bp=row.rate_bp,
            reverse_charge=row.reverse_charge,
            revenue_cents=row.revenue_cents,
            tax_cents=row.tax_cents,
        )
        for row in rows
    )
