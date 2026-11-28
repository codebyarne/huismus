# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The columns of the export's CSV files (SPEC.md M19), in one place.

The export (core.export) writes them and the import of the same format
(imports.csv_*, SPEC.md M22) reads them back, so the two can't drift apart.
A label is the Dutch column name; the export translates it to the language
of the screen, the import knows it in both.

`required`: the import stops when the column is missing. Every other
column may be left out of a file. The import knows them all, so none is
reported as unknown, but it doesn't use "openstaand" and "bron": they
follow from the rest.
"""

from dataclasses import dataclass

from django.utils import translation
from django.utils.translation import gettext, gettext_noop

LANGUAGES = ("nl", "en")


@dataclass(frozen=True)
class Column:
    key: str
    label: str
    required: bool = False
    # Other labels the export has written for this column.
    also: tuple[str, ...] = ()


def labels(columns) -> list[str]:
    """The header row, in the language of the screen."""
    return [gettext(column.label) for column in columns]


def in_both_languages(text) -> list[str]:
    """`text` (a msgid, or a lazy string) in Dutch and in English."""
    found = []
    for language in LANGUAGES:
        with translation.override(language):
            found.append(gettext(text) if isinstance(text, str) else str(text))
    return found


def normalised(name: str) -> str:
    """A column name as the import compares it: without the spaces around
    it and whatever its capitals."""
    return " ".join(str(name).split()).casefold()


INVOICE_COLUMNS = (
    Column("kind", gettext_noop("soort"), required=True),
    Column("number", gettext_noop("nummer"), required=True),
    Column("issue_date", gettext_noop("factuurdatum"), required=True),
    Column("due_date", gettext_noop("vervaldatum")),
    Column("delivery_date", gettext_noop("leverdatum")),
    Column("credited_invoice", gettext_noop("gecrediteerde factuur")),
    Column("customer_number", gettext_noop("klantnummer"), required=True),
    Column("customer", gettext_noop("klant")),
    Column("customer_vat_number", gettext_noop("btw-nummer klant")),
    Column("customer_kvk_number", gettext_noop("KvK-nummer klant")),
    Column("customer_country", gettext_noop("land klant")),
    Column("reference", gettext_noop("kenmerk")),
    Column("currency", gettext_noop("valuta")),
    Column("subtotal", gettext_noop("bedrag excl. btw"), required=True),
    Column("tax", gettext_noop("btw"), required=True),
    Column("total", gettext_noop("totaal incl. btw"), required=True),
)
# Between these two groups: "omzet t%" and "btw t%" for every rate in the
# export (RATE_REVENUE, RATE_TAX).
INVOICE_COLUMNS_AFTER_RATES = (
    Column("reverse_charge_revenue", gettext_noop("omzet btw verlegd")),
    Column("payment_state", gettext_noop("betaalstatus")),
    Column("paid", gettext_noop("betaald")),
    Column("outstanding", gettext_noop("openstaand")),
    Column("paid_on", gettext_noop("laatst betaald op")),
    Column("source", gettext_noop("bron")),
    # The line prices include VAT (#362): "prijs per eenheid" and
    # "regelbedrag" in the lines file are then amounts including VAT.
    Column("prices_include_vat", gettext_noop("prijzen incl. btw")),
)
RATE_REVENUE = gettext_noop("omzet %(rate)s%%")
RATE_TAX = gettext_noop("btw %(rate)s%%")

QUOTE_COLUMNS = (
    Column("number", gettext_noop("nummer"), required=True),
    Column("issue_date", gettext_noop("datum"), required=True),
    Column("expiry_date", gettext_noop("geldig tot")),
    Column("customer_number", gettext_noop("klantnummer"), required=True),
    Column("customer", gettext_noop("klant")),
    Column("reference", gettext_noop("kenmerk")),
    Column("status", gettext_noop("status"), required=True),
    Column("accepted_on", gettext_noop("geaccepteerd op")),
    Column("declined_on", gettext_noop("afgewezen op")),
    Column("subtotal", gettext_noop("bedrag excl. btw"), required=True),
    Column("tax", gettext_noop("btw"), required=True),
    Column("total", gettext_noop("totaal incl. btw"), required=True),
    Column("invoice", gettext_noop("factuur")),
    Column("prices_include_vat", gettext_noop("prijzen incl. btw")),
)

LINE_COLUMNS = (
    Column("kind", gettext_noop("soort"), required=True),
    Column("number", gettext_noop("nummer"), required=True),
    Column("position", gettext_noop("positie")),
    Column("description", gettext_noop("omschrijving"), required=True),
    Column("quantity", gettext_noop("aantal")),
    Column("unit", gettext_noop("eenheid")),
    Column("unit_price", gettext_noop("prijs per eenheid"), required=True),
    Column("tax_rate", gettext_noop("btw-tarief (%)"), required=True),
    Column("reverse_charge", gettext_noop("btw verlegd")),
    # Without VAT, or with when the document's prices include VAT (#362).
    # Called "bedrag excl. btw" before #362; files with that name still read.
    Column("line_total", gettext_noop("regelbedrag"), also=(gettext_noop("bedrag excl. btw"),)),
)

CONTACT_COLUMNS = (
    Column("customer_number", gettext_noop("klantnummer"), required=True),
    Column("company_name", gettext_noop("bedrijfsnaam"), required=True),
    Column("first_name", gettext_noop("voornaam")),
    Column("last_name", gettext_noop("achternaam"), required=True),
    Column("attention", gettext_noop("t.a.v.")),
    Column("address_line1", gettext_noop("adresregel 1")),
    Column("address_line2", gettext_noop("adresregel 2")),
    Column("postal_code", gettext_noop("postcode")),
    Column("city", gettext_noop("plaats")),
    Column("country", gettext_noop("land")),
    Column("email", gettext_noop("e-mail")),
    Column("quote_email", gettext_noop("e-mail voor offertes")),
    Column("phone", gettext_noop("telefoon")),
    Column("kvk_number", gettext_noop("KvK-nummer")),
    Column("vat_number", gettext_noop("btw-nummer")),
    Column("iban", gettext_noop("IBAN")),
    Column("payment_terms_days", gettext_noop("betalingstermijn (dagen)")),
    Column("notes", gettext_noop("notities")),
    Column("archived", gettext_noop("gearchiveerd")),
)

CONTACT_PERSON_COLUMNS = (
    Column("customer_number", gettext_noop("klantnummer"), required=True),
    Column("name", gettext_noop("naam"), required=True),
    Column("email", gettext_noop("e-mail")),
    Column("phone", gettext_noop("telefoon")),
    Column("department", gettext_noop("afdeling")),
)

# The VAT of an expense is "btw ter info" under the KOR and "btw" without
# it (SPEC.md M21); the import reads either.
VAT = gettext_noop("btw")
VAT_FOR_INFO = gettext_noop("btw ter info")

EXPENSE_COLUMNS = (
    Column("expense_id", gettext_noop("uitgavenummer"), required=True),
    Column("date", gettext_noop("datum"), required=True),
    Column("supplier", gettext_noop("leverancier")),
    Column("description", gettext_noop("omschrijving")),
    Column("amount", gettext_noop("bedrag (bruto)"), required=True),
    Column("vat", VAT, also=(VAT_FOR_INFO,)),
    Column("receipts", gettext_noop("bonnetjes")),
)

EXPENSE_LINE_COLUMNS = (
    Column("expense_id", gettext_noop("uitgavenummer"), required=True),
    Column("position", gettext_noop("positie")),
    Column("description", gettext_noop("omschrijving")),
    Column("amount", gettext_noop("bedrag (bruto)"), required=True),
    Column("vat", VAT, also=(VAT_FOR_INFO,)),
    Column("vat_rate", gettext_noop("btw-tarief")),
    Column("category", gettext_noop("categorie")),
)

# The names of several receipts in one cell of "bonnetjes".
RECEIPT_SEPARATOR = " | "


def expense_labels(columns, *, kor_enabled: bool) -> list[str]:
    """The header row of an expense file: its VAT column says "ter info"
    under the KOR, as on the expense page."""
    vat_label = VAT_FOR_INFO if kor_enabled else VAT
    names = [vat_label if column.key == "vat" else column.label for column in columns]
    return [gettext(name) for name in names]
