# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Where every column of a Moneybird sheet goes (besluit 2026-11-02,
"Moneybird-import verliest nooit stil gegevens"; CLAUDE.md rule 6).

Each column of a sheet the import reads is one of three things:

- **read**: a parser in this package uses it. `required` ones must be there,
  or the import stops and names the column;
- **left out**: Huismus knows it and deliberately doesn't take it over; the
  reason is next to it. Its values stay in the stored raw rows
  (imports.models.ImportedRow);
- **unknown**: anything else. The report names it instead of dropping it
  silently.

Column names come from the sample exports in
tests/fixtures/moneybird-example-data, never from guesses; the test
tests/imports/test_columns.py checks that every column there has a place.
"""

from dataclasses import dataclass, field

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .detect import FileKind
from .expenses import HEADER_REQUIRED as EXPENSE_REQUIRED
from .expenses import LINES_REQUIRED as EXPENSE_LINES_REQUIRED
from .invoices import CUSTOMER_COLUMNS as INVOICE_CUSTOMER_COLUMNS
from .quotes import CUSTOMER_COLUMNS as QUOTE_CUSTOMER_COLUMNS
from .sources import ImportSourceError


@dataclass(frozen=True)
class SheetColumns:
    read: frozenset[str]
    required: frozenset[str] = frozenset()
    # Column -> why Huismus doesn't take it over (for the reader of this
    # code; the user sees only that it is kept).
    left_out: dict[str, str] = field(default_factory=dict)


# Repeated on every line of Moneybird's per-line sheets: the document's own
# details, which Huismus reads from the per-document sheet.
_REPEATS_THE_DOCUMENT = "repeats the document's own row, read from the per-document sheet"
_LINE_TOTALS = (
    "a line total: Huismus computes it with the one totals function "
    "(CLAUDE.md rule 4); the document's totals are checked to the cent"
)
_PROJECT = "projects are not in scope (besluit 2026-11-01)"
_CATEGORY = "a revenue category (ledger account): Huismus has none for sales"
_EUR_COPY = "the amount in euros; the same as the column without (EUR) for a euro document"

_INVOICE_HEADER_REPEATS = (
    "status",
    "factuurdatum",
    "vervaldatum",
    "contact",
    "klantnummer",
    "btw-identificatienummer",
    "KVK-nummer",
    "referentie",
    "valuta",
    "totale korting",
    "Adres",
    "2e Adresregel",
    "Postcode",
    "Plaats",
    "Land",
    "Telefoonnummer",
    "e-mailadres",
    "betaald op",
)
_QUOTE_HEADER_REPEATS = (
    "referentie",
    "status",
    "offerte datum",
    "vervaldatum",
    "geaccepteerd op",
    "gefactureerd op",
    "afgewezen op",
    "contact",
    "klantnummer",
    "btw-identificatienummer",
    "KVK-nummer",
    "email",
    "valuta",
    "totale korting",
)
_EXPENSE_HEADER_REPEATS = (
    "referentie",
    "status",
    "datum",
    "vervaldatum",
    "contact",
    "contactnummer",
    "valuta",
    "betaald op",
)


COLUMNS: dict[FileKind, SheetColumns] = {
    FileKind.CONTACTS: SheetColumns(
        read=frozenset(
            {
                "id",
                "customer_id",
                "company_name",
                "firstname",
                "lastname",
                "email",
                "send_estimates_to_email",
                "phone",
                "address1",
                "address2",
                "zipcode",
                "city",
                "country",
                "delivery_method",
                "tax_number",
                "chamber_of_commerce",
                "attention",
                "sepa_iban",
                "archived",
            }
        ),
        required=frozenset({"id", "customer_id"}),
        left_out={
            "tax_number_valid": "Moneybird's own check of the VAT number at the time",
            "bank_account": "free text next to sepa_iban, which Huismus reads as the IBAN",
            "sepa_iban_account_name": "direct debit: Huismus doesn't collect payments",
            "sepa_bic": "direct debit: Huismus doesn't collect payments",
            "sepa_sequence_type": "direct debit: Huismus doesn't collect payments",
            "invoice_workflow": "Moneybird's own workflow settings",
            "estimate_workflow": "Moneybird's own workflow settings",
        },
    ),
    FileKind.CONTACT_PERSONS: SheetColumns(
        read=frozenset({"customer_id", "firstname", "lastname", "department", "email", "phone"}),
        required=frozenset({"customer_id", "firstname", "lastname"}),
    ),
    FileKind.SALES_INVOICES: SheetColumns(
        read=frozenset(
            {
                "id",
                "factuurnummer",
                "status",
                "factuurdatum",
                "vervaldatum",
                "klantnummer",
                "referentie",
                "totaalprijs exclusief btw",
                "btw",
                "totaalprijs inclusief btw",
                "totaal onbetaald",
                "betaald op",
                "valuta",  # checked: euros only
                "totale korting",  # named in the report
                *INVOICE_CUSTOMER_COLUMNS,
            }
        ),
        # Not "status": invoices.py has its own message that says why it
        # can't do without it.
        required=frozenset(
            {
                "id",
                "factuurnummer",
                "factuurdatum",
                "klantnummer",
                "totaalprijs exclusief btw",
                "btw",
                "totaalprijs inclusief btw",
                "totaal onbetaald",
            }
        ),
        left_out={
            "totaalprijs exclusief btw (EUR)": _EUR_COPY,
            "totaalprijs inclusief btw (EUR)": _EUR_COPY,
        },
    ),
    FileKind.SALES_INVOICE_LINES: SheetColumns(
        read=frozenset(
            {"id", "factuurnummer", "omschrijving", "aantal", "aantal (decimaal)", "prijs"}
            | {"Btw-tarief"}
        ),
        required=frozenset({"id", "aantal (decimaal)", "prijs", "Btw-tarief"}),
        left_out={
            **dict.fromkeys(_INVOICE_HEADER_REPEATS, _REPEATS_THE_DOCUMENT),
            "periode van": "Huismus has no period per line",
            "periode tot": "Huismus has no period per line",
            "categorie": _CATEGORY,
            "categorie id": _CATEGORY,
            "Project": _PROJECT,
            "totaalprijs exclusief btw": _LINE_TOTALS,
            "btw": _LINE_TOTALS,
            "totaalprijs inclusief btw": _LINE_TOTALS,
            "totaalprijs exclusief btw (EUR)": _LINE_TOTALS,
            "totaalprijs inclusief btw (EUR)": _LINE_TOTALS,
        },
    ),
    FileKind.QUOTES: SheetColumns(
        read=frozenset(
            {
                "id",
                "offertenummer",
                "referentie",
                "status",
                "offerte datum",
                "vervaldatum",
                "geaccepteerd op",
                "afgewezen op",
                "klantnummer",
                "totaalprijs exclusief btw",
                "totaalprijs inclusief btw",
                "valuta",  # checked: euros only
                "totale korting",  # named in the report
                *QUOTE_CUSTOMER_COLUMNS,
            }
        ),
        required=frozenset(
            {
                "id",
                "offertenummer",
                "status",
                "offerte datum",
                "klantnummer",
                "totaalprijs exclusief btw",
                "totaalprijs inclusief btw",
            }
        ),
        left_out={
            "gefactureerd op": "the invoice made from it; not linked yet (besluit 2026-11-01)",
            "totaalprijs exclusief btw (EUR)": _EUR_COPY,
            "totaalprijs inclusief btw (EUR)": _EUR_COPY,
        },
    ),
    FileKind.QUOTE_LINES: SheetColumns(
        read=frozenset(
            {"id", "offertenummer", "omschrijving", "aantal", "aantal (decimaal)", "prijs", "btw"}
        ),
        required=frozenset({"id", "aantal (decimaal)", "prijs", "btw"}),
        left_out={
            **dict.fromkeys(_QUOTE_HEADER_REPEATS, _REPEATS_THE_DOCUMENT),
            "categorie": _CATEGORY,
            "categorie id": _CATEGORY,
            "Project": _PROJECT,
            "totaalprijs exclusief btw inclusief korting": _LINE_TOTALS,
        },
    ),
    FileKind.EXPENSES: SheetColumns(
        read=frozenset(
            {"id", "referentie", "status", "datum", "contact", "valuta", "btw"}
            | set(EXPENSE_REQUIRED)
        ),
        required=frozenset(EXPENSE_REQUIRED),
        left_out={
            "vervaldatum": "an expense in Huismus has no due date",
            "contactnummer": "a supplier is a name on the expense, not a contact",
            "betaald op": "an expense in Huismus has no payment state",
            "totaalprijs exclusief btw": "in the document's own currency; read in euros (EUR)",
            "totaalprijs inclusief btw": "in the document's own currency; read in euros (EUR)",
        },
    ),
    FileKind.EXPENSE_LINES: SheetColumns(
        # "categorie": each line's own category (besluit 2026-11-02,
        # "Uitgaven krijgen regels, net als Moneybird").
        read=frozenset(EXPENSE_LINES_REQUIRED) | {"categorie"},
        required=frozenset(EXPENSE_LINES_REQUIRED),
        left_out={
            **dict.fromkeys(_EXPENSE_HEADER_REPEATS, _REPEATS_THE_DOCUMENT),
            "aantal": "the expense's lines are amounts, not quantities",
            "aantal (decimaal)": "the expense's lines are amounts, not quantities",
            "categorienummer": "Moneybird's number for the category; its name is read",
            "btw-tarief": "VAT is information only on an expense (CLAUDE.md rule 7)",
            "btw-tarief naam": "VAT is information only on an expense (CLAUDE.md rule 7)",
            "btw": "VAT is information only on an expense (CLAUDE.md rule 7)",
            "totaalprijs exclusief btw": "in the document's own currency; read in euros (EUR)",
            "totaalprijs inclusief btw": "in the document's own currency; read in euros (EUR)",
            "totaalprijs inclusief btw (EUR)": _LINE_TOTALS,
            "begin periode": "Huismus has no period per line",
            "eind periode": "Huismus has no period per line",
            "project": _PROJECT,
        },
    ),
}


# How a missing-column message names the sheet; the expense ones are the
# labels huismus/imports/expenses.py uses for the same message.
FILE_LABELS = {
    FileKind.CONTACTS: gettext_lazy("de klanten"),
    FileKind.CONTACT_PERSONS: gettext_lazy("de contactpersonen"),
    FileKind.SALES_INVOICES: gettext_lazy("de facturen"),
    FileKind.SALES_INVOICE_LINES: gettext_lazy("de factuurregels"),
    FileKind.QUOTES: gettext_lazy("de offertes"),
    FileKind.QUOTE_LINES: gettext_lazy("de offerteregels"),
    FileKind.EXPENSES: gettext_lazy("de uitgaven"),
    FileKind.EXPENSE_LINES: gettext_lazy("de uitgaveregels"),
}


def check_columns(kind: FileKind, headers: list[str]) -> list[str]:
    """The unknown columns of a sheet of `kind`, in the sheet's order.
    Stops the import (ImportSourceError) when a required column is missing."""
    columns = COLUMNS[kind]
    for column in sorted(columns.required):
        if column not in headers:
            raise ImportSourceError(
                _(
                    "In %(file)s ontbreekt de kolom ‘%(column)s’. Exporteer je jaar opnieuw "
                    "uit Moneybird en kies de zip zoals hij is."
                )
                % {"file": FILE_LABELS[kind], "column": column}
            )
    known = set(columns.read) | set(columns.left_out)
    unknown = []
    for header in headers:
        if header not in known and header not in unknown:
            unknown.append(header)
    return unknown
