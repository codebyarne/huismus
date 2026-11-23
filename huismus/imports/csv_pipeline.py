# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One import run of Huismus's own format (SPEC.md M22): the ZIP that
Exporteren makes (M19), or the same CSV files filled by hand. The same
steps as the Moneybird import (imports.pipeline): read, link, check, a dry
run by default, and one transaction that saves everything or nothing.

What is in the files and belongs nowhere (a PDF without its document, a
receipt no expense names, a file Huismus doesn't know) is named in the
report; nothing is left out without a word.
"""

import hashlib
import re
from dataclasses import dataclass, field
from functools import cache
from pathlib import PurePosixPath

from django.db import transaction
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from huismus.business.models import Settings
from huismus.core.export import pdf_folder
from huismus.core.export_format import LANGUAGES, normalised

from . import csv_template
from .archive import keep_originals
from .counting import COUNTED_SECTIONS, check_count, section
from .csv_commit import (
    ContactReport,
    import_contact_persons,
    import_contacts,
    import_documents,
    import_expenses,
    pdf_key,
)
from .csv_parse import (
    SOURCE,
    lines_by_document,
    orphan_lines,
    parse_contact_persons,
    parse_contacts,
    parse_expenses,
    parse_invoices,
    parse_quotes,
)
from .csv_tables import CsvKind, Table, read_table
from .expenses import RECEIPT_SUFFIXES
from .models import ImportRun
from .sources import Export, ImportSourceError, files_in_upload

# How many file names one note lists before it says how many more there are.
MAX_NAMED_FILES = 10


@dataclass
class ParsedCsv:
    """What all files of one run hold together."""

    contacts: list = field(default_factory=list)
    persons: list = field(default_factory=list)
    invoices: list = field(default_factory=list)  # with the credit notes
    quotes: list = field(default_factory=list)
    expenses: list = field(default_factory=list)
    # Which parts the files have at all: a part without a file is not in
    # the report, one with an empty file is.
    has: set = field(default_factory=set)
    # (kind, number as in the file name) -> the document's PDF.
    pdfs: dict = field(default_factory=dict)
    # File name without folders -> content, for everything that isn't a
    # table, a document's PDF or the template's note: receipts, or nothing.
    other_files: dict = field(default_factory=dict)
    orphan_lines: dict = field(
        default_factory=lambda: {"sales_invoices": [], "quotes": [], "expenses": []}
    )
    notes: list = field(default_factory=list)


@cache
def _pdf_kinds() -> dict[str, str]:
    """Folder name under pdf/, in Dutch or English -> the document kind."""
    kinds = {}
    for language in LANGUAGES:
        with translation.override(language):
            for kind in ("invoice", "credit_note", "quote"):
                kinds[normalised(pdf_folder(kind))] = kind
    return kinds


# The auditfile the export writes per year (core.export.write_zip).
AUDITFILE_NAME = re.compile(r"auditfile-\d{4}\.xaf")


@cache
def _readme_names() -> set[str]:
    names = set()
    for language in LANGUAGES:
        with translation.override(language):
            names.add(normalised(csv_template.readme_name()))
    return names


def _tables(export: Export, notes: list) -> dict[CsvKind, Table]:
    """The tables in one export's CSV files; a column Huismus doesn't know
    goes into `notes`. Two files of one kind in one export would mean two
    exports in one: lines would end up under the wrong year's documents."""
    tables: dict[CsvKind, Table] = {}
    for name, content in sorted(export.files.items()):
        path = PurePosixPath(name)
        table = read_table(path.name, content) if path.suffix.lower() == ".csv" else None
        if table is None:
            continue
        if table.kind in tables:
            raise ImportSourceError(
                _(
                    "In %(export)s staan twee bestanden met dezelfde soort gegevens "
                    "(%(first)s en %(second)s). Zip elke export apart, of importeer ze "
                    "één voor één."
                )
                % {
                    "export": export.name,
                    "first": tables[table.kind].file_name,
                    "second": table.file_name,
                }
            )
        tables[table.kind] = table
        if table.unknown:
            notes.append(
                ngettext(
                    "In %(file)s staat een kolom die Huismus niet kent: %(columns)s. "
                    "Huismus neemt hem niet over.",
                    "In %(file)s staan kolommen die Huismus niet kent: %(columns)s. "
                    "Huismus neemt ze niet over.",
                    len(table.unknown),
                )
                % {"file": table.file_name, "columns": ", ".join(table.unknown)}
            )
    return tables


def _keep_other_files(export: Export, tables: dict[CsvKind, Table], parsed: ParsedCsv) -> None:
    """What isn't a table: a PDF in a folder of pdf/ is that kind of
    document's, the template's note and the export's auditfiles are
    nothing (an auditfile is made from the files beside it, SPEC.md M26),
    and the rest may be a receipt (_receipts)."""
    table_files = {table.file_name for table in tables.values()}
    for name, content in export.files.items():
        path = PurePosixPath(name)
        folder = normalised(path.parent.name)
        if path.name in table_files or normalised(path.name) in _readme_names():
            continue
        if AUDITFILE_NAME.fullmatch(path.name):
            continue
        if path.suffix.lower() == ".pdf" and folder in _pdf_kinds():
            parsed.pdfs[(_pdf_kinds()[folder], path.stem)] = content
        else:
            parsed.other_files[path.name] = content


def _parse_export(export: Export, parsed: ParsedCsv) -> None:
    """One export on its own: its lines belong to its own documents."""
    tables = _tables(export, parsed.notes)
    _keep_other_files(export, tables, parsed)
    parsed.has |= set(tables)
    documents_without_lines = {CsvKind.INVOICES, CsvKind.QUOTES} & set(tables)
    if documents_without_lines and CsvKind.LINES not in tables:
        raise ImportSourceError(
            _(
                "Bij %(file)s zit geen bestand met de regels. Zonder regels kan Huismus "
                "een factuur of offerte niet importeren. Zet het regelbestand erbij."
            )
            % {
                "file": tables[
                    CsvKind.INVOICES if CsvKind.INVOICES in tables else CsvKind.QUOTES
                ].file_name
            }
        )
    if CsvKind.EXPENSE_LINES in tables and CsvKind.EXPENSES not in tables:
        raise ImportSourceError(
            _("Bij %(file)s zit geen bestand met de uitgaven zelf. Zet het erbij.")
            % {"file": tables[CsvKind.EXPENSE_LINES].file_name}
        )

    if CsvKind.CONTACTS in tables:
        parsed.contacts += parse_contacts(tables[CsvKind.CONTACTS])
    if CsvKind.CONTACT_PERSONS in tables:
        parsed.persons += parse_contact_persons(tables[CsvKind.CONTACT_PERSONS])
    lines = lines_by_document(tables.get(CsvKind.LINES))
    documents = []
    if CsvKind.INVOICES in tables:
        documents += parse_invoices(tables[CsvKind.INVOICES], lines)
    if CsvKind.QUOTES in tables:
        documents += parse_quotes(tables[CsvKind.QUOTES], lines)
    parsed.invoices += [document for document in documents if document.kind != "quote"]
    parsed.quotes += [document for document in documents if document.kind == "quote"]
    for name, orphans in orphan_lines(lines, documents, export.name).items():
        parsed.orphan_lines[name] += orphans
    if CsvKind.EXPENSES in tables:
        expenses, orphans = parse_expenses(
            tables[CsvKind.EXPENSES], tables.get(CsvKind.EXPENSE_LINES), export.name
        )
        parsed.expenses += expenses
        parsed.orphan_lines["expenses"] += orphans


@cache
def _examples() -> ParsedCsv:
    """The template's own examples, in both languages, as the import would
    read them."""
    examples = ParsedCsv()
    for language in LANGUAGES:
        with translation.override(language):
            content = csv_template.template_zip()
        _parse_export(_archive(content), examples)
    return examples


def _archive(content: bytes) -> Export:
    return Export("sjabloon", files_in_upload("sjabloon.zip", content))


def _without_examples(items: list, examples: list, notes: list, text: str) -> list:
    kept = [item for item in items if item not in examples]
    if len(kept) != len(items):
        notes.append(text)
    return kept


def _once(items: list, notes: list, label: str) -> list:
    """One item per external_id. The same one in two files counts once;
    when they differ the last file's is used, and the report says so."""
    chosen: dict = {}
    for item in items:
        earlier = chosen.get(item.external_id)
        if earlier is not None and earlier != item:
            notes.append(
                _(
                    "%(label)s staat twee keer in de bestanden, met verschillen. Huismus "
                    "neemt de laatste."
                )
                % {"label": f"{label} {item.external_id.split(':')[-1]}"}
            )
        chosen[item.external_id] = item
    return list(chosen.values())


def parse_exports(exports: list[Export]) -> ParsedCsv:
    parsed = ParsedCsv()
    for export in exports:
        _parse_export(export, parsed)
    if not parsed.has:
        raise ImportSourceError(
            _(
                "Huismus herkent geen van deze bestanden. Download het sjabloon en kijk of "
                "de kolomnamen in de eerste rij staan."
            )
        )
    examples = _examples()
    notes = parsed.notes
    skipped = _("Het voorbeeld uit het sjabloon staat er nog in. Huismus slaat het over: %(what)s.")
    parsed.contacts = _once(
        _without_examples(
            parsed.contacts, examples.contacts, notes, skipped % {"what": _("de klant")}
        ),
        notes,
        _("Klant"),
    )
    # The same person in two files counts once.
    parsed.persons = [
        person for person in dict.fromkeys(parsed.persons) if person not in examples.persons
    ]
    parsed.invoices = _once(
        _without_examples(
            parsed.invoices, examples.invoices, notes, skipped % {"what": _("de factuur")}
        ),
        notes,
        _("Factuur"),
    )
    parsed.quotes = _once(
        _without_examples(
            parsed.quotes, examples.quotes, notes, skipped % {"what": _("de offerte")}
        ),
        notes,
        _("Offerte"),
    )
    parsed.expenses = _once(
        _without_examples(
            parsed.expenses, examples.expenses, notes, skipped % {"what": _("de uitgave")}
        ),
        notes,
        _("Uitgave"),
    )
    return parsed


def _receipts(parsed: ParsedCsv) -> dict[str, bytes]:
    """The files that an expense names in "bonnetjes", when they are a file a
    receipt can be (RECEIPT_SUFFIXES, as the Moneybird import and the upload
    keep to). Huismus serves a receipt to the browser by its name, so an
    .svg or .html from someone else's zip never becomes one; it is named
    with the files that belong nowhere."""
    wanted = {name for expense in parsed.expenses for name in expense.receipt_names}
    return {
        name: content
        for name, content in parsed.other_files.items()
        if name in wanted and PurePosixPath(name).suffix.lower() in RECEIPT_SUFFIXES
    }


def _note_files_without_a_place(parsed: ParsedCsv, receipts: dict) -> None:
    """PDFs without their document and files that are no receipt of an
    expense in the files: named, never dropped without a word."""
    documents = {
        pdf_key(document.kind, document.number) for document in parsed.invoices + parsed.quotes
    }
    named = {name for expense in parsed.expenses for name in expense.receipt_names}
    names = sorted(
        [f"{number}.pdf" for (kind, number) in parsed.pdfs if (kind, number) not in documents]
        + [name for name in parsed.other_files if name not in receipts and name not in named]
    )
    if refused := sorted(name for name in parsed.other_files if name in named - set(receipts)):
        parsed.notes.append(
            _(
                "Een bonnetje is een pdf, png of jpg. Huismus slaat over wat een uitgave "
                "noemt en iets anders is: %(names)s."
            )
            % {"names": ", ".join(refused[:MAX_NAMED_FILES])}
        )
    if not names:
        return
    shown = ", ".join(names[:MAX_NAMED_FILES])
    if len(names) > MAX_NAMED_FILES:
        shown = _("%(names)s en nog %(count)s") % {
            "names": shown,
            "count": len(names) - MAX_NAMED_FILES,
        }
    parsed.notes.append(
        ngettext(
            "Dit bestand hoort bij geen factuur, offerte of uitgave in de bestanden. "
            "Huismus slaat het over: %(names)s.",
            "Deze bestanden horen bij geen factuur, offerte of uitgave in de bestanden. "
            "Huismus slaat ze over: %(names)s.",
            len(names),
        )
        % {"names": shown}
    )


def run_csv_import(exports: list[Export], *, commit: bool) -> ImportRun:
    parsed = parse_exports(exports)
    receipts = _receipts(parsed)
    _note_files_without_a_place(parsed, receipts)
    # An invoice before the credit notes: a credit note finds its invoice.
    invoices = sorted(parsed.invoices, key=lambda document: document.kind == "credit_note")
    invoice_of_quote = {
        number: quote.number for quote in parsed.quotes for number in quote.invoice_numbers
    }

    with transaction.atomic():
        settings = Settings.load()
        contacts_report = quotes_report = invoices_report = expenses_report = None
        if CsvKind.CONTACTS in parsed.has:
            contacts_report = import_contacts(parsed.contacts)
        if CsvKind.CONTACT_PERSONS in parsed.has:
            # After the contacts: a person is added to its contact.
            contacts_report = contacts_report or ContactReport()
            import_contact_persons(parsed.persons, contacts_report)
        # Quotes first: an invoice made from one points to it.
        if CsvKind.QUOTES in parsed.has:
            quotes_report = import_documents(
                parsed.quotes,
                parsed.pdfs,
                write_attachments=commit,
                sequence="quote",
                number_format=settings.quote_number_format,
                numbers_label=_("offertenummers"),
            )
        if CsvKind.INVOICES in parsed.has:
            invoices_report = import_documents(
                invoices,
                parsed.pdfs,
                write_attachments=commit,
                sequence="invoice",
                number_format=settings.invoice_number_format,
                numbers_label=_("factuurnummers"),
                invoice_of_quote=invoice_of_quote,
            )
        if CsvKind.EXPENSES in parsed.has:
            expenses_report = import_expenses(parsed.expenses, receipts, write_attachments=commit)

        report = {
            "contacts": section(contacts_report, parsed.contacts),
            "sales_invoices": section(
                invoices_report, invoices, parsed.orphan_lines["sales_invoices"]
            ),
            "quotes": section(quotes_report, parsed.quotes, parsed.orphan_lines["quotes"]),
            "expenses": section(expenses_report, parsed.expenses, parsed.orphan_lines["expenses"]),
            "notes": parsed.notes,
        }
        for kind, name in COUNTED_SECTIONS:
            check_count(report[name], _(kind))

        # Inside the transaction: a dry run leaves no row behind at all.
        run = ImportRun.objects.create(
            source=SOURCE,
            dry_run=not commit,
            file_hashes={
                f"{export.name}/{name}": hashlib.sha256(content).hexdigest()
                for export in exports
                for name, content in export.files.items()
            },
            report=report,
            committed=commit,
        )
        if commit:
            # The files as given, in data/import-archief/ (imports.archive).
            keep_originals(exports)
        else:
            transaction.set_rollback(True)
    return run
