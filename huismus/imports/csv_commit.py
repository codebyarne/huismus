# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Saves what imports.csv_parse read from Huismus's own CSV format
(SPEC.md M22), in the way of the Moneybird import (imports.commit): always
writing, inside the transaction of imports.csv_pipeline, whose rollback
makes it a dry run. Files (PDFs, receipts) are only written on a real
import: a rollback can't take a file back.

What is already in Huismus is never changed: a document by its number, an
expense by (source, external_id). Every total is checked to the cent
against the one totals function (CLAUDE.md, hard rules 4 and 6).
"""

import hashlib
from dataclasses import dataclass, field

from django.core.files.base import ContentFile
from django.db.models import Sum
from django.utils.translation import gettext as _

from huismus.business.models import Settings
from huismus.contacts.models import Contact, ContactPerson
from huismus.core.export import percent
from huismus.core.models import Attachment
from huismus.core.templatetags.money import euros
from huismus.documents.issuing import no_vat_text_for, reverse_charge_text_for
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.snapshots import business_snapshot
from huismus.documents.totals import compute_totals, line_total_cents, vat_rows
from huismus.documents.vat_snapshot import store_vat_rows
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

from .commit import category_named, continue_numbering, snapshot_as_stated
from .csv_parse import SOURCE, CsvDocument, CsvExpense


@dataclass
class ContactReport:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    # Rows Huismus didn't take, each with the reason.
    refused: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    persons_new: int = 0
    # Contact persons whose customer number is no contact's: "<name> (<number>)".
    persons_without_contact: list[str] = field(default_factory=list)


@dataclass
class DocumentReport:
    new: int = 0
    unchanged: int = 0
    skipped_missing_contact: list[str] = field(default_factory=list)
    skipped_no_lines: list[str] = field(default_factory=list)
    refused: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    missing_pdfs: list[str] = field(default_factory=list)
    payment_issues: list[str] = field(default_factory=list)
    # Credit notes that name no invoice Huismus has: imported without one.
    unlinked_credit_notes: list[str] = field(default_factory=list)
    numbering_note: str = ""


@dataclass
class ExpenseReport:
    new: int = 0
    unchanged: int = 0
    refused: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    missing_receipts: list[str] = field(default_factory=list)
    new_categories: list[str] = field(default_factory=list)
    unknown_vat_rates: list[str] = field(default_factory=list)
    # Expenses that were in Huismus before this import and aren't from it.
    other_expenses: int = 0
    # New expenses with the date and amount of one of those.
    possible_duplicates: list[str] = field(default_factory=list)
    # Imported before, but with another date or amount in this file.
    changed_in_file: list[str] = field(default_factory=list)
    # Without the KOR: new lines without a VAT rate (SPEC.md M21).
    lines_without_rate: int = 0


def import_contacts(contacts) -> ContactReport:
    report = ContactReport()
    for parsed in contacts:
        if not parsed.has_name:
            report.refused.append(
                _("%(file)s, rij %(row)s: klant %(number)s heeft geen bedrijfsnaam en geen naam.")
                % {"file": parsed.file, "row": parsed.row, "number": parsed.customer_number}
            )
            continue
        existing = _contact(parsed.customer_number)
        if existing is None:
            Contact.objects.create(
                source=SOURCE,
                external_id=parsed.external_id,
                customer_number=parsed.customer_number,
                **parsed.fields,
            )
            report.new += 1
        elif existing.source != SOURCE:
            # Made here or imported another way: left as it is.
            report.unchanged += 1
        elif any(getattr(existing, name) != value for name, value in parsed.fields.items()):
            for name, value in parsed.fields.items():
                setattr(existing, name, value)
            existing.save()
            report.updated += 1
        else:
            report.unchanged += 1
    return report


def import_contact_persons(persons, report: ContactReport) -> None:
    """Adds the persons a contact of this import doesn't have yet. A
    contact made here or imported another way is left as it is, persons
    included."""
    for parsed in persons:
        contact = _contact(parsed.customer_number)
        if contact is None:
            report.persons_without_contact.append(f"{parsed.name} ({parsed.customer_number})")
            continue
        if contact.source != SOURCE:
            continue
        person = {
            "name": parsed.name,
            "email": parsed.email,
            "phone": parsed.phone,
            "department": parsed.department,
        }
        if not contact.persons.filter(**person).exists():
            ContactPerson.objects.create(contact=contact, **person)
            report.persons_new += 1


def _contact(customer_number: str) -> Contact | None:
    """The contact with this customer number: the one this import made
    before, else the oldest other one. Customer numbers aren't unique in
    Huismus; with two contacts made by hand under one number, documents go
    to the first, as the number is all the file says."""
    contacts = Contact.objects.filter(customer_number=customer_number)
    return contacts.filter(source=SOURCE).first() or contacts.order_by("pk").first()


def _label(document: CsvDocument) -> str:
    names = {
        "invoice": _("Factuur %(number)s"),
        "credit_note": _("Creditnota %(number)s"),
        "quote": _("Offerte %(number)s"),
    }
    return names[document.kind] % {"number": document.number}


def _existing(document: CsvDocument) -> bool:
    """A document with this number is already in Huismus, wherever it came
    from. Invoices and credit notes share their numbers; quotes have their
    own."""
    kinds = ["quote"] if document.kind == "quote" else ["invoice", "credit_note"]
    return Document.objects.filter(kind__in=kinds, number=document.number).exists()


def _total_mismatches(parsed: CsvDocument, totals) -> list[str]:
    """Where the file's own amounts differ from what its lines add up to."""
    found = [
        _("%(label)s in het bestand € %(stated)s, volgens de regels € %(computed)s")
        % {"label": label, "stated": euros(stated), "computed": euros(computed)}
        for label, stated, computed in (
            (_("subtotaal"), parsed.stated_subtotal_cents, totals.subtotal_cents),
            (_("btw"), parsed.stated_tax_cents, totals.tax_cents),
            (_("totaal"), parsed.stated_total_cents, totals.total_cents),
        )
        if stated != computed
    ]
    for position, (line, computed) in enumerate(
        zip(parsed.lines, totals.line_totals_cents, strict=True), start=1
    ):
        if line.stated_total_cents is not None and line.stated_total_cents != computed:
            found.append(
                _("regel %(position)s in het bestand € %(stated)s, uitgerekend € %(computed)s")
                % {
                    "position": position,
                    "stated": euros(line.stated_total_cents),
                    "computed": euros(computed),
                }
            )
    return found


def _split_mismatches(parsed: CsvDocument, totals) -> list[str]:
    """Where the file's revenue and VAT per rate differ from the lines',
    through the one totals function. Only the columns the file has, and
    only when the row fills in at least one of them."""
    if parsed.stated_split is None:
        return []
    rows = vat_rows(
        parsed.lines,
        subtotal_cents=totals.subtotal_cents,
        tax_cents=totals.tax_cents,
        prices_include_vat=parsed.prices_include_vat,
    )
    computed: dict = {}
    for row in rows or []:
        if row.reverse_charge:
            computed[(None, "revenue")] = computed.get((None, "revenue"), 0) + row.revenue_cents
        else:
            computed[(row.rate_bp, "revenue")] = row.revenue_cents
            computed[(row.rate_bp, "tax")] = row.tax_cents
    found = []
    for (rate_bp, part), stated in sorted(
        parsed.stated_split.items(), key=lambda item: (item[0][0] is None, item[0])
    ):
        expected = computed.get((rate_bp, part), 0)
        if stated == expected:
            continue
        if rate_bp is None:
            column = _("omzet btw verlegd")
        else:
            template = _("omzet %(rate)s%%") if part == "revenue" else _("btw %(rate)s%%")
            column = template % {"rate": percent(rate_bp)}
        found.append(
            _("%(label)s in het bestand € %(stated)s, volgens de regels € %(computed)s")
            % {"label": column, "stated": euros(stated), "computed": euros(expected)}
        )
    return found


def pdf_key(kind: str, number: str) -> tuple[str, str]:
    """How a document's PDF is found: its kind and its number as the export
    writes it in a file name (core.export.write_zip)."""
    return kind, number.replace("/", "-").replace("\\", "-")


def import_documents(
    documents: list[CsvDocument],
    pdfs: dict[tuple[str, str], bytes],
    *,
    sequence: str,
    write_attachments: bool,
    number_format: str,
    numbers_label: str,
    invoice_of_quote: dict[str, str] | None = None,
) -> DocumentReport:
    """Quotes (`sequence` "quote"), or invoices and credit notes
    ("invoice", the number sequence they share): `documents` in the order
    to save them in (a credit note after its invoice). `invoice_of_quote`:
    invoice number -> the number of the quote it was made from."""
    report = DocumentReport()
    settings = Settings.load()
    imported_numbers = []
    for parsed in documents:
        if _existing(parsed):
            report.unchanged += 1
            continue
        if not parsed.lines:
            report.skipped_no_lines.append(parsed.number)
            continue
        contact = _contact(parsed.customer_number)
        if contact is None:
            report.skipped_missing_contact.append(parsed.number)
            continue

        totals = compute_totals(parsed.lines, prices_include_vat=parsed.prices_include_vat)
        wrong_split = _split_mismatches(parsed, totals)
        if wrong_split:
            report.refused.append(f"{_label(parsed)}: {', '.join(wrong_split)}")
            continue
        credited = None
        if parsed.kind == "credit_note":
            credited = Document.objects.filter(
                kind="invoice", status="issued", number=parsed.credited_number
            ).first()
            if credited is None:
                report.unlinked_credit_notes.append(parsed.number)
            elif _credited_cents(credited) + parsed.stated_total_cents > credited.total_cents:
                # SPEC.md invariant 5.
                report.refused.append(
                    _(
                        "%(label)s: samen met de andere creditnota's is dit meer dan het "
                        "bedrag van factuur %(invoice)s."
                    )
                    % {"label": _label(parsed), "invoice": credited.number}
                )
                continue
        mismatches = _total_mismatches(parsed, totals)
        if mismatches:
            report.discrepancies.append(f"{_label(parsed)}: {', '.join(mismatches)}")

        quote_number = (invoice_of_quote or {}).get(parsed.number)
        related = credited or (
            Document.objects.filter(kind="quote", number=quote_number).first()
            if quote_number and parsed.kind == "invoice"
            else None
        )
        document = _create(parsed, contact, settings, related)
        report.new += 1
        imported_numbers.append((parsed.issue_date, parsed.number, parsed.customer_number))
        if parsed.kind == "invoice":
            _import_payment(parsed, document, report)

        pdf = pdfs.get(pdf_key(parsed.kind, parsed.number))
        if pdf is None:
            report.missing_pdfs.append(parsed.number)
        elif write_attachments:
            Attachment.objects.create(
                document=document,
                file=ContentFile(pdf, name=f"{pdf_key(parsed.kind, parsed.number)[1]}.pdf"),
                kind="original_pdf",
                sha256=hashlib.sha256(pdf).hexdigest(),
                source=SOURCE,
            )

    report.numbering_note = continue_numbering(
        sequence,
        number_format,
        imported_numbers,
        settings,
        label=numbers_label,
    )
    return report


def _credited_cents(invoice: Document) -> int:
    credited = Document.objects.filter(
        kind="credit_note", status="issued", related_document=invoice
    ).aggregate(total=Sum("total_cents"))
    return credited["total"] or 0


def _create(parsed: CsvDocument, contact, settings, related) -> Document:
    """The document as the file has it, with the file's own totals. Saved
    as a draft first: a line can't be added to an issued document
    (invariant 1); the status it ends in is set last."""
    document = Document.objects.create(
        kind=parsed.kind,
        status="draft",
        contact=contact,
        related_document=related,
        language=settings.default_language,
        currency="EUR",
        source=SOURCE,
        external_id=parsed.external_id,
        reference=parsed.reference,
        prices_include_vat=parsed.prices_include_vat,
    )
    for position, line in enumerate(parsed.lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=line.description,
            quantity=line.quantity,
            unit=line.unit,
            unit_price_cents=line.unit_price_cents,
            tax_rate_bp=line.tax_rate_bp,
            reverse_charge=line.reverse_charge,
            line_total_cents=line_total_cents(line.quantity, line.unit_price_cents),
        )
    lines = list(document.lines.order_by("position"))
    document.number = parsed.number
    document.issue_date = parsed.issue_date
    document.due_date = parsed.due_date
    document.delivery_date = parsed.delivery_date
    document.expiry_date = parsed.expiry_date
    document.accepted_on = parsed.accepted_on
    document.declined_on = parsed.declined_on
    document.business_snapshot = business_snapshot(settings)
    document.contact_snapshot = snapshot_as_stated(contact, parsed.customer)
    # No KOR text beside VAT or a "verlegd" line: that document was not
    # made under the KOR, whatever the settings say now.
    under_kor = parsed.stated_tax_cents == 0 and not any(line.reverse_charge for line in lines)
    document.kor_text_snapshot = no_vat_text_for(document, settings) if under_kor else ""
    document.reverse_charge_text_snapshot = reverse_charge_text_for(document, lines, settings)
    document.subtotal_cents = parsed.stated_subtotal_cents
    document.tax_cents = parsed.stated_tax_cents
    document.total_cents = parsed.stated_total_cents
    if parsed.kind != "quote":
        # Its VAT per rate, only when the file's totals are those of its
        # lines; while it is still a draft (documents.vat_snapshot).
        store_vat_rows(
            document,
            lines,
            subtotal_cents=document.subtotal_cents,
            tax_cents=document.tax_cents,
            prices_include_vat=document.prices_include_vat,
        )
    document.status = parsed.status
    document.save()
    return document


def _import_payment(parsed: CsvDocument, document: Document, report: DocumentReport) -> None:
    """One payment for what the file says was paid, on "laatst betaald
    op". Without that date no payment is made up: the invoice stays open
    and the report names it."""
    if parsed.paid_cents > 0 and parsed.paid_on:
        Payment.objects.create(
            document=document, paid_on=parsed.paid_on, amount_cents=parsed.paid_cents
        )
    elif parsed.paid_cents > 0:
        report.payment_issues.append(
            _(
                "Factuur %(number)s: er is € %(paid)s betaald volgens het bestand, maar "
                "zonder datum. Voeg de betaling zelf toe."
            )
            % {"number": parsed.number, "paid": euros(parsed.paid_cents)}
        )
    elif parsed.payment_state in ("paid", "partial"):
        report.payment_issues.append(
            _(
                "Factuur %(number)s: volgens het bestand is hij betaald, maar er staat "
                "geen bedrag bij. Voeg de betaling zelf toe."
            )
            % {"number": parsed.number}
        )


def import_expenses(
    expenses: list[CsvExpense],
    receipts: dict[str, bytes],
    *,
    write_attachments: bool,
) -> ExpenseReport:
    """`receipts`: file name (as in the column "bonnetjes") -> content."""
    report = ExpenseReport()
    no_vat = Settings.load().no_vat
    categories: dict = {}
    others = list(Expense.objects.exclude(source=SOURCE).values_list("date", "amount_cents"))
    report.other_expenses = len(others)

    for parsed in expenses:
        existing = Expense.objects.filter(source=SOURCE, external_id=parsed.external_id).first()
        if existing is not None:
            report.unchanged += 1
            if (existing.date, existing.amount_cents) != (parsed.date, parsed.stated_amount_cents):
                report.changed_in_file.append(parsed.label)
            continue
        reason = _expense_refusal(parsed)
        if reason:
            report.refused.append(f"{parsed.label}: {reason}")
            continue

        lines = []
        if not parsed.lines:
            # No lines in the file: one line with the whole amount.
            lines.append(
                ExpenseLineInput("", parsed.stated_amount_cents, parsed.stated_vat_cents, None)
            )
        for line in parsed.lines:
            if line.vat_rate_given and not line.vat_rate:
                report.unknown_vat_rates.append(f"{parsed.label}: {line.vat_rate_given}")
            lines.append(
                ExpenseLineInput(
                    description=line.description,
                    amount_cents=line.amount_cents,
                    vat_info_cents=line.vat_cents,
                    category=category_named(line.category, categories, report),
                    vat_rate=line.vat_rate,
                )
            )
        if not no_vat:
            report.lines_without_rate += sum(1 for line in lines if not line.vat_rate)
        expense = create_expense(
            lines,
            date=parsed.date,
            supplier=parsed.supplier,
            description=parsed.description,
            source=SOURCE,
            external_id=parsed.external_id,
        )
        report.new += 1
        if (parsed.date, parsed.stated_amount_cents) in others:
            report.possible_duplicates.append(
                f"{parsed.label}, {parsed.date.isoformat()}, € {euros(parsed.stated_amount_cents)}"
            )

        found = [(name, receipts[name]) for name in parsed.receipt_names if name in receipts]
        if not found:
            report.missing_receipts.append(parsed.label)
        elif write_attachments:
            for name, content in found:
                Attachment.objects.create(
                    expense=expense,
                    # The export puts the expense's number in front.
                    file=ContentFile(content, name=name.removeprefix(f"{parsed.external_id}-")),
                    kind="receipt",
                    sha256=hashlib.sha256(content).hexdigest(),
                    source=SOURCE,
                )
    return report


def _expense_refusal(parsed: CsvExpense) -> str:
    """Why this expense can't come in, or "". Huismus keeps an expense as
    the sum of its lines (expenses.lines), so a file that says otherwise
    can't be stored as it is."""
    if not parsed.lines:
        return ""
    lines_amount = sum(line.amount_cents for line in parsed.lines)
    if lines_amount != parsed.stated_amount_cents:
        return _("het bedrag is € %(stated)s, maar de regels tellen op tot € %(lines)s.") % {
            "stated": euros(parsed.stated_amount_cents),
            "lines": euros(lines_amount),
        }
    lines_vat = sum(line.vat_cents or 0 for line in parsed.lines)
    if parsed.stated_vat_cents is not None and lines_vat != parsed.stated_vat_cents:
        return _("de btw is € %(stated)s, maar de regels tellen op tot € %(lines)s.") % {
            "stated": euros(parsed.stated_vat_cents),
            "lines": euros(lines_vat),
        }
    return ""
