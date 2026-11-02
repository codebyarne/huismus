# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Made-up variants of the 2013 sample export, for the UBL check
(huismus/imports/ubl.py): a copy of the export with one invoice's UBL or
Excel rows changed. The sample data has prices including VAT (2013-0003,
2013-0006) but no discount and no UBL that doesn't fit; those are made
here, following UBL 2.1.

Also usable by hand: `uv run python -m tests.imports.ubl_variants <dir>`
writes each variant as a zip, to upload in the dry run.
"""

import re
import shutil
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import openpyxl

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"
EXPORT_2013 = FIXTURES / "lindeboom_communicatie_2013"
UBL_FOLDER = "sales_invoices_ubl_archive"


def copy_2013(target: Path) -> Path:
    export = target / "lindeboom_communicatie_2013"
    shutil.copytree(EXPORT_2013, export)
    return export


def edit_ubl(export: Path, number: str, old: str, new: str) -> None:
    path = export / UBL_FOLDER / f"{number}.xml"
    content = path.read_text(encoding="utf-8")
    assert old in content, old
    path.write_text(content.replace(old, new, 1), encoding="utf-8")


def set_invoice_cells(export: Path, number: str, values: dict, *, folder="sales_invoices"):
    """Change cells of `number`'s rows in the invoice export (or, with
    folder="sales_invoices_details", the line export)."""
    (path,) = (export / folder).glob("*.xlsx")
    workbook = openpyxl.load_workbook(path)
    sheet = workbook.active
    header = [cell.value for cell in sheet[1]]
    for row in sheet.iter_rows(min_row=2):
        if row[header.index("factuurnummer")].value == number:
            for column, value in values.items():
                row[header.index(column)].value = value
    workbook.save(path)


def discount_on_invoice(export: Path) -> None:
    """2013-0002 (one line of € 412,06 at 21%) with 10% discount on the
    whole invoice, only in the UBL: subtotal € 370,85, VAT € 77,88."""
    edit_ubl(
        export,
        "2013-0002",
        "  <cac:TaxTotal>",
        """  <cac:AllowanceCharge>
    <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
    <cbc:AllowanceChargeReason>Korting</cbc:AllowanceChargeReason>
    <cbc:MultiplierFactorNumeric>10</cbc:MultiplierFactorNumeric>
    <cbc:Amount currencyID="EUR">41.21</cbc:Amount>
    <cbc:BaseAmount currencyID="EUR">412.06</cbc:BaseAmount>
    <cac:TaxCategory>
      <cbc:ID>S</cbc:ID>
      <cbc:Percent>21.0</cbc:Percent>
      <cac:TaxScheme><cbc:ID>VAT</cbc:ID></cac:TaxScheme>
    </cac:TaxCategory>
  </cac:AllowanceCharge>
  <cac:TaxTotal>""",
    )
    for old, new in (
        ('<cbc:TaxAmount currencyID="EUR">86.53</cbc:TaxAmount>\n    <cac:TaxSubtotal>',
         '<cbc:TaxAmount currencyID="EUR">77.88</cbc:TaxAmount>\n    <cac:TaxSubtotal>'),
        ('<cbc:TaxableAmount currencyID="EUR">412.06</cbc:TaxableAmount>\n      '
         '<cbc:TaxAmount currencyID="EUR">86.53</cbc:TaxAmount>',
         '<cbc:TaxableAmount currencyID="EUR">370.85</cbc:TaxableAmount>\n      '
         '<cbc:TaxAmount currencyID="EUR">77.88</cbc:TaxAmount>'),
        ('<cbc:TaxExclusiveAmount currencyID="EUR">412.06',
         '<cbc:TaxExclusiveAmount currencyID="EUR">370.85'),
        ('<cbc:TaxInclusiveAmount currencyID="EUR">498.59',
         '<cbc:TaxInclusiveAmount currencyID="EUR">448.73'),
        ('<cbc:AllowanceTotalAmount currencyID="EUR">0<',
         '<cbc:AllowanceTotalAmount currencyID="EUR">41.21<'),
        ('<cbc:PayableAmount currencyID="EUR">498.59',
         '<cbc:PayableAmount currencyID="EUR">448.73'),
    ):  # fmt: skip
        edit_ubl(export, "2013-0002", old, new)
    set_invoice_cells(
        export,
        "2013-0002",
        {
            "totaalprijs exclusief btw": 370.85,
            "btw": 77.88,
            "totaalprijs inclusief btw": 448.73,
            "totaalprijs exclusief btw (EUR)": 370.85,
            "totaalprijs inclusief btw (EUR)": 448.73,
        },
    )


def discount_per_line(export: Path) -> None:
    """2013-0007's only line with a discount inside the line."""
    edit_ubl(
        export,
        "2013-0007",
        "    <cac:Item>",
        """    <cac:AllowanceCharge>
      <cbc:ChargeIndicator>false</cbc:ChargeIndicator>
      <cbc:AllowanceChargeReason>Korting</cbc:AllowanceChargeReason>
      <cbc:Amount currencyID="EUR">0.00</cbc:Amount>
    </cac:AllowanceCharge>
    <cac:Item>""",
    )


def ubl_that_does_not_fit(export: Path) -> None:
    """2013-0005's UBL with another date and total."""
    path = export / UBL_FOLDER / "2013-0005.xml"
    content = path.read_text(encoding="utf-8")
    content = re.sub(r"<cbc:IssueDate>[^<]*<", "<cbc:IssueDate>2012-01-01<", content, count=1)
    path.write_text(content, encoding="utf-8")
    edit_ubl(
        export,
        "2013-0005",
        '<cbc:TaxInclusiveAmount currencyID="EUR">',
        '<cbc:TaxInclusiveAmount currencyID="EUR">1',
    )


def broken_ubl(export: Path) -> None:
    (export / UBL_FOLDER / "2013-0004.xml").write_bytes(b"<Invoice><cbc:ID>kapot")


def ubl_without_invoice(export: Path) -> None:
    shutil.copy(export / UBL_FOLDER / "2013-0001.xml", export / UBL_FOLDER / "2013-9999.xml")


def other_description(export: Path) -> None:
    """2013-0008's second line has another description in the UBL."""
    edit_ubl(export, "2013-0008", "Inkoop stockfotografie", "Inkoop stockfoto's")


VARIANTS = {
    "korting": (discount_on_invoice,),
    "past-niet": (ubl_that_does_not_fit, broken_ubl, ubl_without_invoice),
}


def write_zips(target: Path) -> None:
    """Each variant as a zip, as Moneybird delivers an export."""
    for name, changes in VARIANTS.items():
        work = target / f"work-{name}"
        export = copy_2013(work)
        for change in changes:
            change(export)
        buffer = BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for path in sorted(export.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(export).as_posix())
        (target / f"ubl-{name}.zip").write_bytes(buffer.getvalue())
        shutil.rmtree(work)


if __name__ == "__main__":
    write_zips(Path(sys.argv[1]))
