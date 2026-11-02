# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Moneybird's UBL files: the digital copy of every invoice it sent, in
`sales_invoices_ubl_archive/<number>.xml` (UBL 2.1). Reading one, and
checking it against the invoice from the Excel export (SPEC.md section 7,
"UBL as a cross-check"; besluit 2026-11-02, "Moneybird-import: de UBL als
tweede bron voor de regels").

The rule, which always applies: when the UBL *fits* the invoice (same
number, date, subtotal, VAT and total as the invoice export, as many lines
as the line export, no discount per line), Huismus takes the lines from the
UBL: description, quantity, price without VAT and VAT rate. The unit comes
from the line export, in the same order. When it doesn't fit, or can't be
read, the lines stay as the Excel export has them, and the report says so.
The totals always stay Moneybird's own from the invoice export.

Why the UBL: where prices included VAT in Moneybird, the Excel line export
gives the price with VAT, the UBL the price without. And UBL is a standard,
so the meaning of each field is defined, not guessed (CLAUDE.md rule 6).
"""

from dataclasses import dataclass, field, replace
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import PurePosixPath

import defusedxml.ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from django.utils.text import get_text_list
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from huismus.documents.totals import round_half_up_cents

from .invoices import ParsedInvoice, ParsedInvoiceLine
from .xlsx_utils import euros_to_cents


class UblReadError(Exception):
    """Not an invoice Huismus can read: broken XML, one defusedxml refuses
    (XML bombs, XXE), another root element than Invoice (a CreditNote),
    or a missing or broken required field."""


@dataclass(frozen=True)
class UblLine:
    description: str
    quantity: Decimal
    unit_price_cents: int
    tax_rate_bp: int
    # An AllowanceCharge inside the line. Huismus has no discount per
    # line, so a UBL with one doesn't fit.
    has_discount: bool = False


@dataclass(frozen=True)
class UblInvoice:
    number: str
    issue_date: date
    subtotal_cents: int
    tax_cents: int
    total_cents: int
    lines: list[UblLine]
    # A discount on the whole invoice: an AllowanceCharge on the invoice
    # itself, or an AllowanceTotalAmount that isn't 0.
    has_discount: bool = False


# --- Reading ---------------------------------------------------------------


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def child(element, name):
    """The first direct child called `name`, whatever its namespace."""
    if element is None:
        return None
    return next((c for c in element if _local(c.tag) == name), None)


def children(element, name) -> list:
    if element is None:
        return []
    return [c for c in element if _local(c.tag) == name]


def text(element, *path) -> str:
    for name in path:
        element = child(element, name)
    return (element.text or "").strip() if element is not None else ""


def is_ubl_file(name: str) -> bool:
    """An .xml file in Moneybird's folder of sales invoice UBL files."""
    path = PurePosixPath(name)
    return path.suffix.lower() == ".xml" and path.parent.name.startswith("sales_invoices_ubl")


def parse_root(content: bytes):
    try:
        return SafeET.fromstring(content)
    except (SafeET.ParseError, DefusedXmlException) as error:
        raise UblReadError from error


def _required(element, *path) -> str:
    value = text(element, *path)
    if not value:
        raise UblReadError("/".join(path))
    return value


def _cents(element, *path) -> int:
    try:
        return euros_to_cents(_required(element, *path))
    except InvalidOperation as error:
        raise UblReadError("/".join(path)) from error


def _decimal(element, *path) -> Decimal:
    try:
        return Decimal(_required(element, *path))
    except InvalidOperation as error:
        raise UblReadError("/".join(path)) from error


def _basis_points(percent: Decimal) -> int:
    """21.0 (percent, as in the UBL) -> 2100, as Huismus stores a rate."""
    return int((percent * 100).to_integral_value())


def _is_allowance(allowance_charge) -> bool:
    """ChargeIndicator false is a discount; true is a surcharge."""
    return text(allowance_charge, "ChargeIndicator").lower() == "false"


def _read_line(line) -> UblLine:
    item = child(line, "Item")
    return UblLine(
        description=text(item, "Description") or text(item, "Name"),
        quantity=_decimal(line, "InvoicedQuantity"),
        unit_price_cents=_cents(line, "Price", "PriceAmount"),
        tax_rate_bp=_basis_points(_decimal(item, "ClassifiedTaxCategory", "Percent")),
        has_discount=any(_is_allowance(a) for a in children(line, "AllowanceCharge")),
    )


def read_ubl(content: bytes) -> UblInvoice:
    """Raises UblReadError for anything that isn't a UBL invoice with the
    fields Huismus compares."""
    root = parse_root(content)
    if _local(root.tag) != "Invoice":
        raise UblReadError(_local(root.tag))
    try:
        issue_date = date.fromisoformat(_required(root, "IssueDate"))
    except ValueError as error:
        raise UblReadError("IssueDate") from error
    totals = child(root, "LegalMonetaryTotal")
    allowance_total = (
        _cents(totals, "AllowanceTotalAmount") if text(totals, "AllowanceTotalAmount") else 0
    )
    return UblInvoice(
        number=_required(root, "ID"),
        issue_date=issue_date,
        subtotal_cents=_cents(totals, "TaxExclusiveAmount"),
        tax_cents=_cents(root, "TaxTotal", "TaxAmount"),
        total_cents=_cents(totals, "TaxInclusiveAmount"),
        lines=[_read_line(line) for line in children(root, "InvoiceLine")],
        has_discount=any(_is_allowance(a) for a in children(root, "AllowanceCharge"))
        or allowance_total != 0,
    )


# --- Comparing -------------------------------------------------------------


def _excel_text(description: str) -> str:
    """Moneybird's Excel export writes a carriage return as `_x000D_`:
    that's a line break, not a difference with the UBL."""
    return description.replace("_x000D_\n", "\n").replace("_x000D_", "\n")


def _includes_vat(excel_price_cents: int, ubl: UblLine) -> bool:
    """The Excel price is the UBL price plus VAT at the line's rate, give
    or take a cent: the price included VAT in Moneybird. A cent, because
    Moneybird works back from the price with VAT to one without, rounded
    to the cent (2014-0001: € 81,37 in Excel, € 67,24 in the UBL, and
    € 67,24 + 21% is € 81,36)."""
    if excel_price_cents == ubl.unit_price_cents:
        return False
    with_vat = round_half_up_cents(
        Decimal(ubl.unit_price_cents) * (10000 + ubl.tax_rate_bp) / 10000
    )
    return ubl.tax_rate_bp > 0 and abs(excel_price_cents - with_vat) <= 1


def _misfit_fields(invoice: ParsedInvoice, ubl: UblInvoice) -> list[str]:
    """What keeps the UBL from fitting the invoice, in the report's words."""
    checks = (
        (_("nummer"), ubl.number == invoice.number),
        (_("datum"), ubl.issue_date == invoice.issue_date),
        (_("subtotaal"), ubl.subtotal_cents == invoice.stated_subtotal_cents),
        (_("btw"), ubl.tax_cents == invoice.stated_tax_cents),
        (_("totaal"), ubl.total_cents == invoice.stated_total_cents),
        (_("aantal regels"), len(ubl.lines) == len(invoice.lines)),
        (_("korting per regel"), not any(line.has_discount for line in ubl.lines)),
    )
    return [name for name, fits in checks if not fits]


def line_differences(excel, ubl: UblLine, *, allow_vat_included: bool) -> list[str]:
    """The fields in which a line differs from its UBL line. `excel` has
    description, quantity, unit_price_cents and tax_rate_bp: a parsed line
    or a DocumentLine. A price that is the UBL price plus VAT isn't one
    when `allow_vat_included`: that's what the UBL is for."""
    # No quantity is a fixed price: one, as documents.totals counts it.
    quantity = excel.quantity if excel.quantity is not None else Decimal(1)
    price_differs = excel.unit_price_cents != ubl.unit_price_cents and not (
        allow_vat_included and _includes_vat(excel.unit_price_cents, ubl)
    )
    checks = (
        (_("omschrijving"), _excel_text(excel.description) != _excel_text(ubl.description)),
        (_("aantal"), quantity != ubl.quantity),
        (_("prijs"), price_differs),
        (_("btw-tarief"), excel.tax_rate_bp != ubl.tax_rate_bp),
    )
    return [name for name, differs in checks if differs]


def _fields(names: list[str]) -> str:
    return get_text_list(names, _("en"))


def invoice_label(number: str) -> str:
    """How a message names the invoice: "Factuur 2013-0003:"."""
    return _("Factuur %(number)s") % {"number": number} + ":"


@dataclass
class UblCheck:
    """What the report says about the UBL files of all exports together."""

    found: bool = False
    # Per invoice, as points to check: a UBL that doesn't fit, a line that
    # differs, an invoice already in Huismus with other lines.
    messages: list[str] = field(default_factory=list)
    # Invoices whose prices included VAT in Moneybird.
    vat_included: int = 0
    # Notes under "Let op": a UBL that can't be read, or without invoice.
    notes: list[str] = field(default_factory=list)

    def as_report(self) -> dict | None:
        """JSON-safe for ImportRun.report; None without UBL files, so the
        report shows nothing about them."""
        if not self.found:
            return None
        return {
            "messages": self.messages,
            "vat_included": self.vat_included,
            "vat_included_text": self._vat_included_text(),
            "all_match": not self.messages and not self.notes,
        }

    def _vat_included_text(self) -> str:
        if not self.vat_included:
            return ""
        return ngettext(
            "Bij %(count)s factuur stonden de prijzen in Moneybird inclusief btw. "
            "Huismus nam daar de prijzen zonder btw uit de UBL.",
            "Bij %(count)s facturen stonden de prijzen in Moneybird inclusief btw. "
            "Huismus nam daar de prijzen zonder btw uit de UBL.",
            self.vat_included,
        ) % {"count": self.vat_included}


def apply_ubl(invoices: list[ParsedInvoice], files: dict[str, bytes], check: UblCheck):
    """The invoices of one export, each with its lines from its UBL where
    that fits. A UBL belongs to the invoice of the same export whose number
    is its file name. What there is to report goes into `check`, which
    collects it for all exports of the import."""
    ubl_files = {PurePosixPath(name).stem: name for name in sorted(files) if is_ubl_file(name)}
    if not ubl_files:
        return invoices
    check.found = True
    numbers = {invoice.number for invoice in invoices}
    for stem, name in ubl_files.items():
        if stem not in numbers:
            check.notes.append(
                _(
                    "%(file)s hoort bij geen enkele factuur in de export. Huismus neemt het "
                    "niet over, maar bewaart het wel."
                )
                % {"file": name}
            )
    return [_with_ubl(invoice, ubl_files, files, check) for invoice in invoices]


def _with_ubl(invoice: ParsedInvoice, ubl_files, files, check: UblCheck) -> ParsedInvoice:
    name = ubl_files.get(invoice.number)
    if not invoice.number or name is None:
        return invoice
    try:
        ubl = read_ubl(files[name])
    except UblReadError:
        check.notes.append(
            _(
                "Huismus kan %(file)s niet lezen en vergelijkt die factuur er niet mee. "
                "De import gaat gewoon door."
            )
            % {"file": name}
        )
        return invoice

    misfit = _misfit_fields(invoice, ubl)
    if misfit:
        check.messages.append(
            _(
                "%(label)s de UBL wijkt af in %(fields)s. Huismus neemt hier de regels uit "
                "de Excel-export."
            )
            % {"label": invoice_label(invoice.number), "fields": _fields(misfit)}
        )
        return invoice

    vat_included = False
    for position, (excel, line) in enumerate(zip(invoice.lines, ubl.lines, strict=True), 1):
        differences = line_differences(excel, line, allow_vat_included=True)
        if differences:
            check.messages.append(
                _(
                    "%(label)s regel %(line)s wijkt af in %(fields)s. Huismus neemt hier de "
                    "regels uit de UBL."
                )
                % {
                    "label": invoice_label(invoice.number),
                    "line": position,
                    "fields": _fields(differences),
                }
            )
        if _includes_vat(excel.unit_price_cents, line):
            vat_included = True
    if vat_included:
        check.vat_included += 1

    lines = [
        ParsedInvoiceLine(
            description=line.description,
            quantity=line.quantity,
            unit_price_cents=line.unit_price_cents,
            tax_rate_bp=line.tax_rate_bp,
            unit=excel.unit,
        )
        for excel, line in zip(invoice.lines, ubl.lines, strict=True)
    ]
    return replace(
        invoice,
        lines=lines,
        lines_from_ubl=True,
        has_discount=invoice.has_discount or ubl.has_discount,
    )
