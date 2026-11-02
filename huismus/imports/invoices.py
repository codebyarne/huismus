# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Parses Moneybird's per-invoice and per-line sales invoice sheets into
normalised dataclasses (SPEC.md section 7). The per-invoice sheet is the
totals source of truth (SPEC.md: "per-line exports do not always show
VAT per line"); the per-line sheet supplies the lines. Committing these
to Document/DocumentLine, and validating recomputed totals against the
stated ones, is huismus/imports/commit.py's job — parsing stays pure here.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import PurePosixPath

import openpyxl
from django.utils.translation import gettext as _

from .sources import ImportSourceError
from .xlsx_utils import (
    VatRateParseError,
    customer_on_document,
    euros_to_cents,
    has_discount,
    is_euro,
    parse_vat_rate_bp,
    to_date,
    to_str,
    unit_of_quantity,
)

# Moneybird's sales invoice states, as its API documentation lists them
# (developer.moneybird.com, sales invoices, "state"). Only "paid" occurs in
# the fixture exports; "scheduled" was seen in a real export. A draft or
# scheduled invoice was never sent, so it becomes a draft here too (it
# keeps its number, if it has one: documents.issuing). Anything else was
# sent. An unknown state fails clearly instead of being guessed (SPEC.md
# section 7), as huismus/imports/quotes.py does for quotes.
INVOICE_STATUS_MAP = {
    "draft": "draft",
    "scheduled": "draft",
    "open": "issued",
    "pending_payment": "issued",
    "reminded": "issued",
    "late": "issued",
    "paid": "issued",
    "uncollectible": "issued",
}


# The customer per invoice, as on the invoice then (the contact may have
# moved or been renamed since): Moneybird column -> contact-snapshot key.
CUSTOMER_COLUMNS = {
    "contact": "display_name",
    "Adres": "address_line1",
    "2e Adresregel": "address_line2",
    "Postcode": "postal_code",
    "Plaats": "city",
    "Land": "country",
    "e-mailadres": "email",
    "Telefoonnummer": "phone",
    "btw-identificatienummer": "vat_number",
    "KVK-nummer": "kvk_number",
}


class InvoiceParseError(ImportSourceError):
    # An ImportSourceError, so the upload page and import_moneybird show the
    # message like an unreadable file's, and the import stops before saving.
    """A row doesn't fit any known Moneybird export shape (SPEC.md: "fail
    clearly on missing required columns" — extended here to a malformed
    value in a required one, e.g. a Btw-tarief we can't parse)."""


@dataclass(frozen=True)
class ParsedInvoiceLine:
    description: str
    quantity: Decimal
    unit_price_cents: int
    tax_rate_bp: int
    unit: str = ""


@dataclass(frozen=True)
class ParsedInvoice:
    external_id: str
    number: str
    customer_number: str
    status: str  # already mapped: "draft" or "issued"
    issue_date: date
    due_date: date | None
    paid_on: date | None
    stated_subtotal_cents: int
    stated_tax_cents: int
    stated_total_cents: int
    stated_unpaid_cents: int
    lines: list[ParsedInvoiceLine] = field(default_factory=list)
    # Contact-snapshot keys as the invoice states them (CUSTOMER_COLUMNS).
    customer: dict[str, str] = field(default_factory=dict)
    reference: str = ""  # "Kenmerk"
    # Moneybird's "totale korting" is not 0: Huismus has no discount, so
    # the report names the document (PO-besluit 2026-11-02, Q2).
    has_discount: bool = False
    # The lines come from the invoice's UBL file (huismus/imports/ubl.py).
    lines_from_ubl: bool = False


def _parse_tax_rate_bp(raw, *, number: str) -> int:
    try:
        return parse_vat_rate_bp(raw)
    except VatRateParseError as error:
        raise InvoiceParseError(
            _(
                "Factuur %(number)s heeft een btw-tarief dat Huismus niet herkent: ‘%(rate)s’. "
                "Kijk de factuur na in Moneybird en exporteer opnieuw."
            )
            % {"number": number, "rate": to_str(error.raw)}
        ) from error


def _check_currency(raw, *, number: str) -> None:
    """Amounts are stored as euros: a document in another currency would
    come in with the wrong amounts, so the import stops (PO-besluit
    2026-11-02, Q1)."""
    if not is_euro(raw):
        raise InvoiceParseError(
            _(
                "Factuur %(number)s staat in %(currency)s, niet in euro's. Huismus importeert nog "
                "alleen euro's, dus er is niets opgeslagen."
            )
            % {"number": number, "currency": to_str(raw)}
        )


def _map_status(raw: str, *, number: str) -> str:
    mapped = INVOICE_STATUS_MAP.get(raw)
    if mapped is None:
        raise InvoiceParseError(
            _(
                "Factuur %(number)s heeft een status die Huismus niet kent: ‘%(status)s’. "
                "Kijk de factuur na in Moneybird en exporteer opnieuw."
            )
            % {"number": number, "status": raw}
        )
    return mapped


def _parse_lines(content: bytes) -> dict[str, list[ParsedInvoiceLine]]:
    lines_by_external_id: dict[str, list[ParsedInvoiceLine]] = {}
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows)
    for raw_row in rows:
        row = dict(zip(header, raw_row, strict=True))
        external_id = to_str(row["id"])
        lines_by_external_id.setdefault(external_id, []).append(
            ParsedInvoiceLine(
                description=to_str(row.get("omschrijving")),
                quantity=Decimal(str(row["aantal (decimaal)"])),
                unit_price_cents=euros_to_cents(row.get("prijs")),
                tax_rate_bp=_parse_tax_rate_bp(
                    row.get("Btw-tarief"),
                    number=to_str(row.get("factuurnummer")),
                ),
                unit=unit_of_quantity(row.get("aantal")),
            )
        )
    return lines_by_external_id


def parse_sales_invoices(header_content: bytes, lines_content: bytes) -> list[ParsedInvoice]:
    """`header_content`: the per-invoice export (totals source of truth).
    `lines_content`: the per-line export — a genuinely separate file in
    the real Moneybird export, unlike Contacten/Contactpersonen."""
    lines_by_external_id = _parse_lines(lines_content)

    invoices = []
    workbook = openpyxl.load_workbook(BytesIO(header_content), read_only=True, data_only=True)
    rows = workbook.active.iter_rows(values_only=True)
    header = next(rows)
    if "status" not in header:
        raise InvoiceParseError(
            _(
                "In het facturenbestand ontbreekt de kolom ‘status’. Zonder die kolom ziet "
                "Huismus niet welke facturen verstuurd zijn. Exporteer je facturen opnieuw "
                "uit Moneybird."
            )
        )
    for raw_row in rows:
        row = dict(zip(header, raw_row, strict=True))
        external_id = to_str(row["id"])
        number = to_str(row["factuurnummer"])
        _check_currency(row.get("valuta"), number=number or external_id)
        invoices.append(
            ParsedInvoice(
                external_id=external_id,
                number=number,
                customer_number=to_str(row["klantnummer"]),
                status=_map_status(to_str(row["status"]), number=number or external_id),
                issue_date=to_date(row["factuurdatum"]),
                due_date=to_date(row.get("vervaldatum")),
                paid_on=to_date(row.get("betaald op")),
                stated_subtotal_cents=euros_to_cents(row.get("totaalprijs exclusief btw")),
                stated_tax_cents=euros_to_cents(row.get("btw")),
                stated_total_cents=euros_to_cents(row.get("totaalprijs inclusief btw")),
                stated_unpaid_cents=euros_to_cents(row.get("totaal onbetaald")),
                lines=lines_by_external_id.get(external_id, []),
                customer=customer_on_document(row, CUSTOMER_COLUMNS),
                reference=to_str(row.get("referentie")),
                has_discount=has_discount(row.get("totale korting")),
            )
        )
    return invoices


def pdfs_by_number(files: dict[str, bytes]) -> dict[str, bytes]:
    """`files`: the full dict from huismus.imports.sources.read_files(). Keys on
    each PDF's own filename stem, so this naturally only picks up
    "<number>.pdf" directly under sales_invoices_archive/<year>/ — never
    the per-number subfolder some exports also contain (e.g.
    ".../430057/Algemene_Voorwaarden.pdf", stem "Algemene_Voorwaarden"),
    which SPEC.md's "attach the matching PDF as original_pdf" doesn't
    ask for.
    """
    pdfs = {}
    for name, content in files.items():
        path = PurePosixPath(name)
        if path.suffix.lower() == ".pdf" and "sales_invoices_archive" in path.parts:
            pdfs[path.stem] = content
    return pdfs


def pdfs_by_external_id(invoices, files: dict[str, bytes]) -> dict[str, bytes]:
    """Each invoice's original PDF, found by number in `files` (the export
    the invoice itself came from) and keyed by its external_id. Numbers
    can repeat across years, with a yearly reset; an external_id can't.
    So PDFs from several exports can be combined in one mapping without
    one year's PDF ending up on another year's invoice."""
    by_number = pdfs_by_number(files)
    return {
        invoice.external_id: by_number[invoice.number]
        for invoice in invoices
        if invoice.number in by_number
    }
