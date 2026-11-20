# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The template of Huismus's own import format (SPEC.md M22): a ZIP with
the seven CSV files of the export (M19), each with one made-up example, and
a note on how to fill them. In the language of the screen, like the
export. The columns come from core.export_format and the cells are written
by core.csv_files, so the template is always what the import reads.

The import never takes an example that is still exactly as it is here
(imports.csv_pipeline): an issued example invoice could not be removed.
"""

import io
import zipfile
from datetime import date
from decimal import Decimal

from django.utils.translation import gettext as _
from django.utils.translation import pgettext

from huismus.core import export_format
from huismus.core.csv_files import Amount, csv_bytes
from huismus.core.export import payment_state_name, percent
from huismus.core.export_format import expense_labels, labels
from huismus.documents.models import DOCUMENT_KIND_CHOICES, STATUS_CHOICES
from huismus.expenses.models import VatRate

RATE_BP = 2100


def filename() -> str:
    return pgettext("import template", "huismus-importsjabloon") + ".zip"


def readme_name() -> str:
    return pgettext("import template", "LEESMIJ") + ".txt"


def _readme() -> str:
    return "\r\n".join(
        [
            _("Sjabloon voor het importeren in Huismus"),
            "",
            _(
                "In elk bestand staat één voorbeeld. Vervang het door je eigen gegevens: "
                "een voorbeeld dat je laat staan, slaat Huismus over."
            ),
            _(
                "Laat de eerste rij met de kolomnamen staan. Een bestand of een kolom die "
                "je niet nodig hebt, mag je weghalen."
            ),
            _(
                "Bedragen schrijf je als 1234,56 en datums als 2026-03-14 of 14-03-2026. "
                "Tussen de kolommen staat een puntkomma."
            ),
            _(
                "Pdf's van facturen zet je in pdf/facturen, van creditnota's in "
                "pdf/creditnotas en van offertes in pdf/offertes, met het nummer als naam. "
                "Bonnetjes zet je in bonnetjes, met hun naam in de kolom bonnetjes."
            ),
            _(
                "Maak er weer één zip van en kies die in Huismus bij Importeren. Huismus "
                "doet eerst een proefdraai en slaat pas iets op als jij dat kiest."
            ),
            "",
        ]
    )


def _row(columns, cells: dict) -> list:
    """A row in the order of `columns`, from cells by column key; a
    column without a cell stays empty."""
    unknown = set(cells) - {column.key for column in columns}
    assert not unknown, unknown
    return [cells.get(column.key) for column in columns]


def _files() -> list[tuple[str, list[str], list[list]]]:
    """(file name without .csv, header row, the example rows)."""
    kinds, statuses = dict(DOCUMENT_KIND_CHOICES), dict(STATUS_CHOICES)
    customer_number, customer = "1", _("Voorbeeld BV")
    invoice_number, quote_number = "2026-0001", "2026-001"
    amounts = {"subtotal": Amount(15000), "tax": Amount(3150), "total": Amount(18150)}
    rate = percent(RATE_BP)

    invoice_header = labels(export_format.INVOICE_COLUMNS)
    invoice_header += [
        _(export_format.RATE_REVENUE) % {"rate": rate},
        _(export_format.RATE_TAX) % {"rate": rate},
    ]
    invoice_header += labels(export_format.INVOICE_COLUMNS_AFTER_RATES)
    invoice = (
        _row(
            export_format.INVOICE_COLUMNS,
            {
                "kind": str(kinds["invoice"]),
                "number": invoice_number,
                "issue_date": date(2026, 1, 15),
                "due_date": date(2026, 1, 29),
                "customer_number": customer_number,
                "customer": customer,
                "customer_country": "NL",
                "currency": "EUR",
                **amounts,
            },
        )
        # "omzet 21%" and "btw 21%".
        + [Amount(15000), Amount(3150)]
        + _row(
            export_format.INVOICE_COLUMNS_AFTER_RATES,
            {
                "payment_state": payment_state_name("paid"),
                "paid": Amount(18150),
                "outstanding": Amount(0),
                "paid_on": date(2026, 1, 20),
            },
        )
    )
    quote = _row(
        export_format.QUOTE_COLUMNS,
        {
            "number": quote_number,
            "issue_date": date(2026, 1, 5),
            "expiry_date": date(2026, 1, 19),
            "customer_number": customer_number,
            "customer": customer,
            "status": str(statuses["accepted"]),
            "accepted_on": date(2026, 1, 10),
            "invoice": invoice_number,
            **amounts,
        },
    )
    lines = [
        _row(
            export_format.LINE_COLUMNS,
            {
                "kind": str(kinds[kind]),
                "number": number,
                "position": 1,
                "description": _("Advies"),
                "quantity": Decimal(2),
                "unit": _("uur"),
                "unit_price": Amount(7500),
                "tax_rate": rate,
                "reverse_charge": _("nee"),
                "line_total": Amount(15000),
            },
        )
        for kind, number in (("invoice", invoice_number), ("quote", quote_number))
    ]
    contact = _row(
        export_format.CONTACT_COLUMNS,
        {
            "customer_number": customer_number,
            "company_name": customer,
            "address_line1": _("Voorbeeldweg 1"),
            "postal_code": "1234 AB",
            "city": _("Voorbeeldstad"),
            "country": "NL",
            "email": "administratie@voorbeeld.example",
            "payment_terms_days": 14,
            "archived": _("nee"),
        },
    )
    person = _row(
        export_format.CONTACT_PERSON_COLUMNS,
        {
            "customer_number": customer_number,
            "name": _("Sam Voorbeeld"),
            "email": "sam@voorbeeld.example",
        },
    )
    paper = _("Printerpapier")
    expense = _row(
        export_format.EXPENSE_COLUMNS,
        {
            "expense_id": "1",
            "date": date(2026, 1, 8),
            "supplier": _("Voorbeeldwinkel"),
            "description": paper,
            "amount": Amount(1210),
            "vat": Amount(210),
        },
    )
    expense_line = _row(
        export_format.EXPENSE_LINE_COLUMNS,
        {
            "expense_id": "1",
            "position": 1,
            "description": paper,
            "amount": Amount(1210),
            "vat": Amount(210),
            "vat_rate": str(VatRate.HIGH.label),
            "category": _("Kantoor"),
        },
    )
    return [
        (pgettext("export file", "facturen"), invoice_header, [invoice]),
        (pgettext("export file", "offertes"), labels(export_format.QUOTE_COLUMNS), [quote]),
        (pgettext("export file", "regels"), labels(export_format.LINE_COLUMNS), lines),
        (pgettext("export file", "klanten"), labels(export_format.CONTACT_COLUMNS), [contact]),
        (
            pgettext("export file", "contactpersonen"),
            labels(export_format.CONTACT_PERSON_COLUMNS),
            [person],
        ),
        (
            pgettext("export file", "uitgaven"),
            expense_labels(export_format.EXPENSE_COLUMNS, kor_enabled=False),
            [expense],
        ),
        (
            pgettext("export file", "uitgaveregels"),
            expense_labels(export_format.EXPENSE_LINE_COLUMNS, kor_enabled=False),
            [expense_line],
        ),
    ]


def template_zip() -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(readme_name(), _readme().encode("utf-8-sig"))
        for stem, header, rows in _files():
            archive.writestr(f"{stem}.csv", csv_bytes(header, rows))
    return buffer.getvalue()
