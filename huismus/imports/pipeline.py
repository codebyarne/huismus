# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Ties detect/parse/commit together into one Moneybird import run — the
shared logic behind `manage.py import_moneybird` and, later (M5 step 7),
the web upload page. SPEC.md section 7's pipeline: parse, link, validate,
dry-run report by default, commit.
"""

import hashlib
from dataclasses import asdict, dataclass, field
from io import BytesIO
from pathlib import Path, PurePosixPath

import openpyxl
from django.db import transaction
from django.utils.translation import gettext as _
from django.utils.translation import gettext_noop, ngettext

from huismus.business.models import Settings

from .archive import keep_originals, keep_rows
from .columns import COLUMNS, check_columns
from .commit import import_contacts, import_expenses, import_quotes, import_sales_invoices
from .contacts import parse_contacts
from .detect import FileKind, detect_workbook, unknown_sheets
from .expenses import parse_expenses, receipts_by_external_id
from .invoices import parse_sales_invoices, pdfs_by_external_id
from .models import ImportRun
from .quotes import parse_quotes
from .report_check import check_reports
from .settings_proposal import propose_settings
from .sources import Export, ImportSourceError, read_exports, read_uploaded_exports
from .ubl import UblCheck, apply_ubl
from .xlsx_utils import to_str

SOURCE = "moneybird"

# The second sentence of both "no file" notes: what to do instead.
CHOOSE_THE_YEAR_EXPORT = gettext_noop(
    "Kies de jaarexport-zip zoals Moneybird hem geeft, zonder er iets uit te halen."
)


def _files_of_kind(files: dict[str, bytes], kind: FileKind) -> list[str]:
    matches = []
    for name, content in files.items():
        if not name.lower().endswith(".xlsx"):
            continue
        if any(detected.kind == kind for detected in detect_workbook(content)):
            matches.append(name)
    return sorted(matches)


def _pick_primary(candidates: list[str]) -> str | None:
    # Moneybird exports the same sales-invoice/quote header sheet twice —
    # once under sales_invoices/ (or estimates/), once again alongside
    # its PDF archive under sales_invoices_archive/ (or
    # estimates_archive/) — identical row data, different file bytes
    # (verified against the real fixtures). Prefer the non-archive copy
    # deterministically; either is correct, this just avoids depending on
    # dict/filesystem ordering. Matched on the parent folder's own name,
    # not membership in `.parts` — "sales_invoices_archive" is one path
    # component, not "archive" as a separate one, so a plain `in .parts`
    # check never actually matches anything.
    if not candidates:
        return None
    non_archive = [c for c in candidates if not _in_archive(c)]
    return non_archive[0] if non_archive else candidates[0]


def _in_archive(name: str) -> bool:
    """In one of Moneybird's *_archive folders, at any depth: the incoming
    documents' copy is at documents_archive/<year>/inkoop/inkoop.xlsx."""
    return any(part.endswith("_archive") for part in PurePosixPath(name).parent.parts)


# settings_values=PROPOSED: save the settings proposed from the export
# itself (imports.settings_proposal) — for the dry run, whose rollback
# undoes it, so its report shows what the import does with them.
PROPOSED = "proposed"


def run_moneybird_import(source: Path, *, commit: bool, settings_values=None) -> ImportRun:
    """`source`: a path on disk, per manage.py import_moneybird's CLI
    contract. `settings_values`: see _run_import()."""
    return _run_import(read_exports(source), commit=commit, settings_values=settings_values)


def run_moneybird_import_from_uploads(uploads, *, commit: bool) -> ImportRun:
    """`uploads`: files already in memory (the web upload page's
    request.FILES.getlist(...)) rather than a path on disk — see
    imports.sources.read_uploaded_exports()."""
    return _run_import(read_uploaded_exports(uploads), commit=commit)


@dataclass
class ParsedExports:
    """What all exports of one run hold together: one contact, invoice and
    quote per external_id (see _combine), each invoice's original PDF, and
    the notes for the report."""

    contacts: list = field(default_factory=list)
    invoices: list = field(default_factory=list)
    quotes: list = field(default_factory=list)
    pdfs: dict[str, bytes] = field(default_factory=dict)
    expenses: list = field(default_factory=list)
    receipts: dict[str, list] = field(default_factory=dict)
    has_expenses_file: bool = False
    has_contacts_file: bool = False
    has_invoices_file: bool = False
    has_recurring: bool = False
    # The external ids of each export's invoices, by export name: Moneybird's
    # own reports in an export cover that export's invoices (report_check).
    invoice_ids: dict[str, set[str]] = field(default_factory=dict)
    # What the invoices' UBL files said (imports.ubl).
    ubl: UblCheck = field(default_factory=UblCheck)
    notes: list = field(default_factory=list)
    # Lines whose document isn't in the export, per report section:
    # [{"row": <row in the line sheet>, "export": <export name>}].
    orphan_lines: dict[str, list] = field(
        default_factory=lambda: {"sales_invoices": [], "quotes": [], "expenses": []}
    )


def parse_exports(exports: list[Export]) -> ParsedExports:
    """Every export parsed on its own, then combined."""
    parsed = ParsedExports()
    tagged: dict[str, list] = {"contacts": [], "invoices": [], "quotes": [], "expenses": []}
    for export in exports:
        _parse_export(export, parsed, tagged)
    parsed.contacts = _combine(
        tagged["contacts"], _("Klant"), parsed.notes, key=lambda c: c.customer_number
    )
    parsed.invoices = _combine(
        tagged["invoices"], _("Factuur"), parsed.notes, key=lambda i: i.number or i.external_id
    )
    parsed.quotes = _combine(tagged["quotes"], _("Offerte"), parsed.notes, key=lambda q: q.number)
    parsed.expenses = _combine(
        tagged["expenses"], _("Uitgave"), parsed.notes, key=lambda e: e.reference or e.supplier
    )
    return parsed


def _one_file(export: Export, kind: FileKind) -> str | None:
    """The file of `kind` in this export. Moneybird puts the invoice and
    quote headers in twice (see _pick_primary); anything beyond that means
    the export holds more than one export — e.g. two unzipped years side
    by side — and choosing one would silently drop the others."""
    candidates = _files_of_kind(export.files, kind)
    primary = [c for c in candidates if not _in_archive(c)]
    if len(primary) > 1:
        raise ImportSourceError(
            _(
                "%(export)s bevat meer dan één export (%(files)s). Zip elke export apart, "
                "of importeer ze één voor één."
            )
            % {"export": export.name, "files": ", ".join(primary)}
        )
    return _pick_primary(candidates)


def _parse_export(export: Export, parsed: ParsedExports, tagged: dict[str, list]) -> None:
    """One export on its own: its invoice lines belong to its own invoice
    headers, never to another year's. Items are tagged with the export's
    name, for _combine's note on a conflict."""
    files = export.files
    _check_sheets(files, parsed.notes)
    contacts_file = _one_file(export, FileKind.CONTACTS)
    if contacts_file:
        parsed.has_contacts_file = True
        tagged["contacts"] += [(export.name, c) for c in parse_contacts(files[contacts_file])]

    header_file = _one_file(export, FileKind.SALES_INVOICES)
    lines_file = _one_file(export, FileKind.SALES_INVOICE_LINES)
    if header_file and lines_file:
        parsed.has_invoices_file = True
        parsed.orphan_lines["sales_invoices"] += _orphan_lines(
            "sales_invoices", export.name, files[header_file], files[lines_file]
        )
        invoices = parse_sales_invoices(files[header_file], files[lines_file])
        invoices = apply_ubl(invoices, files, parsed.ubl)
        tagged["invoices"] += [(export.name, invoice) for invoice in invoices]
        parsed.invoice_ids[export.name] = {invoice.external_id for invoice in invoices}
        parsed.pdfs.update(pdfs_by_external_id(invoices, files))

    # No "not found" note when quote files are absent, unlike sales
    # invoices: a business can legitimately have never made a quote in a
    # given export period — confirmed for real in the 2021 fixture year,
    # which has zero estimates/ files at all (Moneybird omits the section
    # rather than exporting it empty).
    quotes_header_file = _one_file(export, FileKind.QUOTES)
    quotes_lines_file = _one_file(export, FileKind.QUOTE_LINES)
    if quotes_header_file and quotes_lines_file:
        parsed.orphan_lines["quotes"] += _orphan_lines(
            "quotes", export.name, files[quotes_header_file], files[quotes_lines_file]
        )
        quotes = parse_quotes(files[quotes_header_file], files[quotes_lines_file])
        tagged["quotes"] += [(export.name, quote) for quote in quotes]

    # Like quotes: no note when there are none. Moneybird leaves the
    # documents/ folders out of a year without incoming documents (the
    # 2019 and 2021 fixtures).
    expenses_file = _one_file(export, FileKind.EXPENSES)
    expense_lines_file = _one_file(export, FileKind.EXPENSE_LINES)
    if bool(expenses_file) != bool(expense_lines_file):
        # Half of them would import expenses without description, or
        # nothing at all, without saying so.
        raise ImportSourceError(
            _("In %(export)s staan wel uitgaven, maar geen uitgaveregels, of andersom.")
            % {"export": export.name}
            + " "
            + _(CHOOSE_THE_YEAR_EXPORT)
        )
    if expenses_file and expense_lines_file:
        parsed.has_expenses_file = True
        parsed.orphan_lines["expenses"] += _orphan_lines(
            "expenses", export.name, files[expenses_file], files[expense_lines_file]
        )
        expenses = parse_expenses(files[expenses_file], files[expense_lines_file])
        tagged["expenses"] += [(export.name, expense) for expense in expenses]
        # Exports come in by name, so for a document in more than one
        # export the newest one's receipts win, as _combine() takes the
        # newest one's expense.
        parsed.receipts.update(receipts_by_external_id(expenses, files))

    if _files_of_kind(files, FileKind.RECURRING_INVOICES):
        parsed.has_recurring = True


def _check_sheets(files: dict[str, bytes], notes: list) -> None:
    """Every sheet and column has a destination (huismus/imports/columns.py):
    a missing required column stops the import; an unknown column or sheet
    is named once per file. Moneybird's *_archive copies have the same
    name and columns, so they add no second note."""
    for name, content in sorted(files.items()):
        if not name.lower().endswith(".xlsx"):
            continue
        file_name = PurePosixPath(name).name
        for detected in detect_workbook(content):
            if detected.kind not in COLUMNS:
                continue
            unknown = check_columns(detected.kind, detected.headers)
            if unknown:
                _note_once(
                    notes,
                    ngettext(
                        "In %(file)s staat een kolom die Huismus niet kent: %(columns)s. "
                        "Huismus neemt hem niet over, maar bewaart hem wel.",
                        "In %(file)s staan kolommen die Huismus niet kent: %(columns)s. "
                        "Huismus neemt ze niet over, maar bewaart ze wel.",
                        len(unknown),
                    )
                    % {"file": file_name, "columns": ", ".join(unknown)},
                )
        for detected in unknown_sheets(content):
            _note_once(
                notes,
                _(
                    "In %(file)s staat een tabblad dat Huismus niet kent: %(sheet)s. "
                    "Huismus neemt het niet over, maar bewaart het wel."
                )
                % {"file": file_name, "sheet": detected.sheet_name},
            )


def _ids(content: bytes, kind: FileKind) -> list:
    """The "id" column of the sheet of `kind`, recognised by its headers
    like everywhere else, one per row (None for an empty row)."""
    sheet_name = next(s.sheet_name for s in detect_workbook(content) if s.kind is kind)
    workbook = openpyxl.load_workbook(BytesIO(content), read_only=True, data_only=True)
    rows = workbook[sheet_name].iter_rows(values_only=True)
    header = list(next(rows, ()))
    column = header.index("id")  # a required column: checked in _check_sheets
    return [None if all(cell is None for cell in row) else to_str(row[column]) for row in rows]


# The header sheet and line sheet of each kind of document.
_LINE_SHEETS = {
    "sales_invoices": (FileKind.SALES_INVOICES, FileKind.SALES_INVOICE_LINES),
    "quotes": (FileKind.QUOTES, FileKind.QUOTE_LINES),
    "expenses": (FileKind.EXPENSES, FileKind.EXPENSE_LINES),
}


def _orphan_lines(
    section: str, export_name: str, header_content: bytes, lines_content: bytes
) -> list[dict]:
    """The rows of a line sheet whose document isn't in the header sheet.
    The parsers only look up lines per document, so these would otherwise
    disappear without a word (PO-besluit 2026-11-02, Q5)."""
    header_kind, lines_kind = _LINE_SHEETS[section]
    documents = set(_ids(header_content, header_kind))
    return [
        {"row": number, "export": export_name}
        for number, external_id in enumerate(_ids(lines_content, lines_kind), start=2)
        if external_id is not None and external_id not in documents
    ]


def _note_once(notes: list, note: str) -> None:
    if note not in notes:
        notes.append(note)


def _combine(tagged_items, label: str, notes: list, *, key) -> list:
    """One item per external_id. Every export lists all contacts, so the
    same one turns up once per year: identical copies count once. When
    copies differ, the one from the last export by name (Moneybird's
    <administratie>_<jaar>: the newest) is used, and the report says so
    rather than choosing silently. `key`: how the note names an item."""
    chosen: dict[str, tuple[str, object]] = {}
    for export_name, item in tagged_items:
        earlier = chosen.get(item.external_id)
        if earlier is not None and earlier[1] != item:
            notes.append(
                _(
                    "%(label)s %(key)s verschilt tussen %(old)s en %(new)s. "
                    "Huismus neemt die uit %(new)s, de nieuwste."
                )
                % {
                    "label": label,
                    "key": key(item),
                    "old": earlier[0],
                    "new": export_name,
                }
            )
        chosen[item.external_id] = (export_name, item)
    return [item for _export_name, item in chosen.values()]


def _run_import(exports: list[Export], *, commit: bool, settings_values=None) -> ImportRun:
    """`settings_values`: Settings fields to save before importing, in the
    same transaction — so numbering continues in the format they set, and
    a dry run rolls them back like everything else. PROPOSED for the
    export's own proposal, None to leave Settings alone (the CLI)."""
    parsed = parse_exports(exports)
    proposal = propose_settings(exports, parsed.invoices, parsed.quotes)
    notes = parsed.notes

    # One shared transaction for the whole run, not one per sub-importer:
    # import_contacts() and import_sales_invoices() each manage their own
    # nested transaction.atomic(), but always called here with commit=True
    # so neither one rolls back on its own — the contacts a dry run
    # "imports" must still be visible (uncommitted, same transaction) to
    # the invoice import's contact lookup right after, exactly as they
    # would be on a real commit. Only this outer block's own rollback
    # decision, made once at the end from the real `commit` flag, differs
    # between a dry run and a commit.
    with transaction.atomic():
        if settings_values is not None:
            _save_settings(proposal.values if settings_values == PROPOSED else settings_values)

        contacts_report = None
        if parsed.has_contacts_file:
            contacts_report = import_contacts(parsed.contacts, commit=True)
        else:
            notes.append(
                _("Er zat geen klantenbestand bij, dus Huismus importeert geen klanten.")
                + " "
                + _(CHOOSE_THE_YEAR_EXPORT)
            )

        invoices_report = None
        if parsed.has_invoices_file:
            # commit=True (never self-rollback, see the block comment
            # above) but write_attachments=commit (the *real* intent):
            # unlike a DB write, a PDF Attachment's file is written to
            # storage immediately, outside this transaction, and this
            # outer block's rollback below can't undo that — found by
            # review after the commit=True-everywhere change above made
            # every dry run silently write real files to disk.
            invoices_report = import_sales_invoices(
                parsed.invoices,
                parsed.pdfs,
                commit=True,
                write_attachments=commit,
                ubl_check=parsed.ubl,
            )
        else:
            notes.append(
                _("Er zat geen facturenbestand bij, dus Huismus importeert geen facturen.")
                + " "
                + _(CHOOSE_THE_YEAR_EXPORT)
            )

        quotes_report = None
        if parsed.quotes:
            quotes_report = import_quotes(parsed.quotes, commit=True)

        expenses_report = None
        if parsed.has_expenses_file:
            # write_attachments=commit: same reason as the invoice PDFs.
            expenses_report = import_expenses(
                parsed.expenses, parsed.receipts, commit=True, write_attachments=commit
            )
        if parsed.has_recurring:
            # SPEC.md section 7: "Not exportable: periodic (recurring)
            # invoices. The import report must say so."
            notes.append(
                _(
                    "Huismus neemt je periodieke facturen niet mee: Moneybird exporteert "
                    "alleen de planning, niet de facturen zelf. Wat al gefactureerd is, "
                    "staat gewoon bij je facturen."
                )
            )

        # After the invoices are in, inside this transaction: it compares
        # Moneybird's reports with the invoices as Huismus has them.
        moneybird_reports = check_reports(exports, parsed.invoice_ids, SOURCE, notes)
        notes += parsed.ubl.notes

        report = {
            "contacts": _section(contacts_report, parsed.contacts),
            "sales_invoices": _section(
                invoices_report, parsed.invoices, parsed.orphan_lines["sales_invoices"]
            ),
            "quotes": _section(quotes_report, parsed.quotes, parsed.orphan_lines["quotes"]),
            "expenses": _section(expenses_report, parsed.expenses, parsed.orphan_lines["expenses"]),
            "notes": notes,
            "settings_proposal": proposal.as_report(),
        }
        if report["sales_invoices"] is not None:
            report["sales_invoices"]["moneybird_reports"] = moneybird_reports
            report["sales_invoices"]["ubl"] = parsed.ubl.as_report()

        for kind, name in COUNTED_SECTIONS:
            _check_count(report[name], _(kind))
        # Keyed by export too: two exports can hold a file of the same name.
        file_hashes = {
            f"{export.name}/{name}": hashlib.sha256(content).hexdigest()
            for export in exports
            for name, content in export.files.items()
        }

        # Written unconditionally here, inside the same block: SPEC.md
        # section 7 is explicit that a dry-run "leaves the database
        # byte-identical" and writes "nothing" — that includes this audit
        # row too, not just the imported Contact/Document rows, so the
        # rollback below (when not committing) must undo it the same way.
        run = ImportRun.objects.create(
            source=SOURCE,
            dry_run=not commit,
            file_hashes=file_hashes,
            report=report,
            committed=commit,
        )

        if commit:
            keep_rows(run, exports)
            # Files, inside the transaction on purpose: if writing them
            # fails, the import stops and nothing is saved, so the done
            # page never says the export is kept when it isn't. Each file
            # is named after its content, so one left behind by a later
            # failure is the same file the next import keeps.
            keep_originals(exports)
        else:
            transaction.set_rollback(True)

    return run


# A report section and how the count's error message names it.
COUNTED_SECTIONS = (
    (gettext_noop("klanten"), "contacts"),
    (gettext_noop("facturen"), "sales_invoices"),
    (gettext_noop("offertes"), "quotes"),
    (gettext_noop("uitgaven"), "expenses"),
)


def _section(report, parsed_items, orphan_lines=None) -> dict | None:
    """A report section as stored, with how many documents the export had
    (`in_export`, PO-besluit 2026-11-02, Q5) and the lines without one."""
    if report is None:
        return None
    section = asdict(report)
    section["in_export"] = len(parsed_items)
    if orphan_lines is not None:
        section["orphan_lines"] = orphan_lines
    return section


def _check_count(section: dict | None, kind: str) -> None:
    """Every document of the export is new, already there, or skipped with
    a reason. If not, Huismus itself went wrong and saves nothing."""
    if section is None:
        return
    counted = (
        section["new"]
        + section.get("updated", 0)
        + section["unchanged"]
        + len(section.get("skipped_missing_contact", []))
        + len(section.get("skipped_no_lines", []))
    )
    if counted != section["in_export"]:
        raise ImportSourceError(
            _(
                "Er gaat iets mis in Huismus: bij %(kind)s klopt de telling niet "
                "(%(total)s in de export, %(counted)s verwerkt). Er is niets opgeslagen."
            )
            % {"kind": kind, "total": section["in_export"], "counted": counted}
        )


def _save_settings(values: dict) -> None:
    settings = Settings.load()
    for name, value in values.items():
        setattr(settings, name, value)
    settings.save()
