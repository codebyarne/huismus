# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Voorbeelden on the Huismus site (issue #309): an invoice with and without
VAT, a quote and a timesheet, each to download as Word, Excel and PDF, in
Dutch and English.

The files are in docs/site/voorbeelden/, made by scripts/site-voorbeelden.sh
on made-up data and committed, like the pictures of the app; core.site copies
them. This module only knows their names, so the site is built without the
packages that write Word files.
"""

from pathlib import Path

from django.conf import settings
from django.utils.translation import gettext_lazy as _

from . import help

EXAMPLES_DIR = Path(settings.BASE_DIR) / "docs" / "site" / "voorbeelden"

INVOICE_WITH_VAT = "factuur-met-btw"
INVOICE_WITHOUT_VAT = "factuur-zonder-btw"
QUOTE = "offerte"
TIMESHEET = "urenstaat"
# The order on the page.
EXAMPLES = (INVOICE_WITH_VAT, INVOICE_WITHOUT_VAT, QUOTE, TIMESHEET)
TITLES = {
    INVOICE_WITH_VAT: _("Factuur met btw"),
    INVOICE_WITHOUT_VAT: _("Factuur zonder btw"),
    QUOTE: _("Offerte"),
    TIMESHEET: _("Urenstaat"),
}
FORMATS = ("docx", "xlsx", "pdf")
# What a download button says.
FORMAT_LABELS = {"docx": "Word", "xlsx": "Excel", "pdf": _("Pdf")}
# The page's title and its line in a search result and in llms.txt.
PAGE_TITLE = _("Voorbeelden om te downloaden")
PAGE_SUMMARY = _(
    "Voorbeeld van een factuur met en zonder btw, een offerte en een urenstaat. "
    "Gratis te downloaden als Word, Excel en pdf."
)

# What a visitor's download is called: the language is in the name itself.
FILE_NAMES = {
    "nl": {
        INVOICE_WITH_VAT: "voorbeeld-factuur-met-btw",
        INVOICE_WITHOUT_VAT: "voorbeeld-factuur-zonder-btw",
        QUOTE: "voorbeeld-offerte",
        TIMESHEET: "voorbeeld-urenstaat",
    },
    "en": {
        INVOICE_WITH_VAT: "example-invoice-with-vat",
        INVOICE_WITHOUT_VAT: "example-invoice-without-vat",
        QUOTE: "example-quote",
        TIMESHEET: "example-timesheet",
    },
}
# The first page of the PDF as a picture, for the card on the page.
PREVIEW_FORMAT = "webp"
# The width of that picture in CSS pixels; the file is twice as wide.
PREVIEW_WIDTH = 420


def file_name(example: str, language: str, format: str) -> str:
    return f"{FILE_NAMES[language][example]}.{format}"


def files(folder: Path = EXAMPLES_DIR) -> list[Path]:
    """Every download and every picture, in both languages."""
    return [
        folder / file_name(example, language, format)
        for language in help.LANGUAGES
        for example in EXAMPLES
        for format in (*FORMATS, PREVIEW_FORMAT)
    ]
