# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Turns parsed Moneybird data into Huismus rows — idempotent, keyed on
(source, external_id) (SPEC.md section 7), dry-run by default.

Dry-run and commit share one code path: every import function here always
performs the actual writes inside transaction.atomic(), and only rolls
back at the very end when commit=False. A dry-run that instead computed
its report by reading the database without writing would risk silently
diverging from what a real commit does — SPEC.md's "a dry-run leaves the
database byte-identical" is much more trustworthy when the two share
every line of logic and differ only in whether the transaction commits.
"""

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Max
from django.utils.translation import gettext as _

from huismus.business.models import Settings
from huismus.contacts.models import Contact, ContactPerson
from huismus.core.models import Attachment
from huismus.core.templatetags.money import euros
from huismus.documents.models import Document, DocumentLine, NumberSequence, Payment
from huismus.documents.numbering import ensure_sequence_row, parse_number
from huismus.documents.snapshots import business_snapshot, contact_snapshot
from huismus.documents.totals import LineInput, compute_totals, line_total_cents
from huismus.documents.vat_snapshot import store_vat_rows
from huismus.expenses.lines import ExpenseLineInput, create_expense, split_gross
from huismus.expenses.models import Expense, ExpenseCategory
from huismus.imports.expenses import ParsedExpenseLine
from huismus.imports.ubl import UblCheck, invoice_label, line_differences

SOURCE = "moneybird"


@dataclass
class ImportReport:
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    discrepancies: list[str] = field(default_factory=list)


@dataclass
class InvoiceImportReport:
    new: int = 0
    unchanged: int = 0
    skipped_missing_contact: list[str] = field(default_factory=list)
    skipped_no_lines: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    missing_pdfs: list[str] = field(default_factory=list)
    payment_issues: list[str] = field(default_factory=list)
    # Draft or scheduled in Moneybird: imported as a draft (see below).
    drafts: list[str] = field(default_factory=list)
    # A discount in Moneybird (PO-besluit 2026-11-02, Q2), named here and
    # not also as a discrepancy.
    discounts: list[str] = field(default_factory=list)
    numbering_note: str = ""


@dataclass
class QuoteImportReport:
    new: int = 0
    unchanged: int = 0
    skipped_missing_contact: list[str] = field(default_factory=list)
    skipped_no_lines: list[str] = field(default_factory=list)
    discrepancies: list[str] = field(default_factory=list)
    discounts: list[str] = field(default_factory=list)
    numbering_note: str = ""


@dataclass
class ExpenseImportReport:
    new: int = 0
    unchanged: int = 0
    discrepancies: list[str] = field(default_factory=list)
    missing_receipts: list[str] = field(default_factory=list)
    # Moneybird categories that weren't in Huismus yet: made by the import.
    new_categories: list[str] = field(default_factory=list)
    # Lines whose VAT rate Huismus doesn't know, "<document>: <Moneybird's
    # name>": imported without a rate (SPEC.md M21, part 2).
    unknown_vat_rates: list[str] = field(default_factory=list)


def _mismatch_text(document_label, number, mismatches) -> str:
    """One line for the report: which of Moneybird's own totals differ from
    the recomputed ones, in euros. `document_label` is e.g. "factuur
    %(number)s"; `mismatches` holds (label, stated_cents, recomputed_cents)."""
    details = ", ".join(
        _("%(label)s Moneybird € %(stated)s, Huismus € %(recomputed)s")
        % {"label": label, "stated": euros(stated), "recomputed": euros(recomputed)}
        for label, stated, recomputed in mismatches
    )
    return f"{document_label % {'number': number}}: {details}"


def _contact_fields(parsed) -> dict:
    return {
        "customer_number": parsed.customer_number,
        "company_name": parsed.company_name,
        "first_name": parsed.first_name,
        "last_name": parsed.last_name,
        "email": parsed.email,
        "phone": parsed.phone,
        "address_line1": parsed.address_line1,
        "address_line2": parsed.address_line2,
        "postal_code": parsed.postal_code,
        "city": parsed.city,
        "country": parsed.country or "NL",
        "vat_number": parsed.vat_number,
        "kvk_number": parsed.kvk_number,
        "iban": parsed.iban,
        "attention": parsed.attention,
        "quote_email": parsed.quote_email,
        "delivery_method": parsed.delivery_method,
        "archived": parsed.archived,
    }


def _sync_persons(contact: Contact, parsed_persons) -> None:
    # Moneybird's Contactpersonen sheet has no stable per-person ID (only
    # the parent's customer_id) to key idempotency on the way Contact
    # itself does — replacing the full set on every import is simple and
    # correct-enough here, since nothing else in this app references a
    # ContactPerson by its own identity.
    contact.persons.all().delete()
    ContactPerson.objects.bulk_create(
        ContactPerson(
            contact=contact,
            name=p.name,
            email=p.email,
            phone=p.phone,
            department=p.department,
        )
        for p in parsed_persons
    )


def _snapshot_as_stated(contact: Contact, stated: dict[str, str]) -> dict:
    """The contact snapshot of an imported document: the contact as it is
    now, with what the document itself states about the customer (name,
    address, numbers as they were then) on top. A company's name is its
    display name; a document without a country stays in the contact's."""
    snapshot = contact_snapshot(contact)
    stated = {key: value for key, value in stated.items() if value or key != "country"}
    if not stated.get("display_name"):
        stated.pop("display_name", None)
    snapshot.update(stated)
    if contact.company_name and "display_name" in stated:
        snapshot["company_name"] = stated["display_name"]
    return snapshot


def import_contacts(parsed_contacts, *, commit: bool) -> ImportReport:
    report = ImportReport()
    with transaction.atomic():
        for parsed in parsed_contacts:
            fields = _contact_fields(parsed)
            existing = Contact.objects.filter(source=SOURCE, external_id=parsed.external_id).first()
            if existing is None:
                report.new += 1
                contact = Contact.objects.create(
                    source=SOURCE, external_id=parsed.external_id, **fields
                )
                _sync_persons(contact, parsed.persons)
            else:
                changed = any(getattr(existing, key) != value for key, value in fields.items())
                if changed:
                    report.updated += 1
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    existing.save()
                else:
                    report.unchanged += 1
                _sync_persons(existing, parsed.persons)

        if not commit:
            transaction.set_rollback(True)
    return report


def import_sales_invoices(
    parsed_invoices,
    pdfs_by_external_id: dict[str, bytes],
    *,
    commit: bool,
    write_attachments: bool | None = None,
    ubl_check: UblCheck | None = None,
) -> InvoiceImportReport:
    # write_attachments defaults to `commit` for a standalone call (every
    # existing caller before huismus/imports/pipeline.py existed), but the
    # pipeline needs to tell these apart: it always passes commit=True so
    # this function's own nested transaction never self-rollbacks before
    # import_quotes() can see the same contacts (huismus/imports/pipeline.py's
    # module docstring) — but a real PDF file write happens immediately,
    # outside any transaction (FileField.pre_save()), so *that* decision
    # must still reflect the caller's real dry-run/commit intent, not the
    # transaction-nesting workaround. Found by review: before this fix,
    # every dry run through the pipeline (CLI or web) silently wrote
    # every original invoice PDF to disk and never cleaned it up, because
    # `commit` was always True by the time it reached the file-write
    # check below.
    if write_attachments is None:
        write_attachments = commit
    # `ubl_check` (imports.ubl) hears of an invoice already in Huismus with
    # other lines than its UBL: a point of the UBL check, which the pipeline
    # collects for the whole import.
    if ubl_check is None:
        ubl_check = UblCheck()

    report = InvoiceImportReport()
    settings = Settings.load()
    imported_numbers: list[tuple] = []  # (issue_date, number, customer number): numbering

    with transaction.atomic():
        for parsed in parsed_invoices:
            existing = Document.objects.filter(
                source=SOURCE, external_id=parsed.external_id
            ).first()
            if existing is not None:
                # Issued documents are immutable (invariant 1/7) — a
                # re-import can only skip an already-imported invoice,
                # never update it in place. SPEC.md's "re-importing
                # changes nothing" is literal here, unlike contacts.py's
                # upsert-to-same-values idempotency.
                report.unchanged += 1
                if parsed.lines_from_ubl and _differs_from_ubl(existing, parsed.lines):
                    ubl_check.messages.append(
                        _(
                            "%(label)s deze factuur staat al in Huismus, met andere regels dan "
                            "de UBL. Huismus past een factuur die er al staat niet aan. Je kunt "
                            'hem zelf verbeteren met "Toch bewerken".'
                        )
                        % {"label": invoice_label(parsed.number)}
                    )
                continue

            if not parsed.lines:
                report.skipped_no_lines.append(parsed.number)
                continue

            contact = Contact.objects.filter(
                source=SOURCE, customer_number=parsed.customer_number
            ).first()
            if contact is None:
                report.skipped_missing_contact.append(parsed.number)
                continue

            recomputed = compute_totals(parsed.lines)
            mismatches = [
                (label, stated, recomputed_value)
                for label, stated, recomputed_value in (
                    (_("subtotaal"), parsed.stated_subtotal_cents, recomputed.subtotal_cents),
                    (_("btw"), parsed.stated_tax_cents, recomputed.tax_cents),
                    (_("totaal"), parsed.stated_total_cents, recomputed.total_cents),
                )
                if stated != recomputed_value
            ]
            if parsed.has_discount:
                # Under "Korting", not also as a discrepancy, but with the
                # difference to the cent (CLAUDE.md rule 6).
                label = _("Factuur %(number)s")
                report.discounts.append(
                    _mismatch_text(label, parsed.number, mismatches)
                    if mismatches
                    else label % {"number": parsed.number}
                )
            elif mismatches:
                report.discrepancies.append(
                    _mismatch_text(_("Factuur %(number)s"), parsed.number, mismatches)
                )

            report.new += 1
            if parsed.number:
                imported_numbers.append((parsed.issue_date, parsed.number, parsed.customer_number))

            if parsed.status == "draft":
                _import_draft_invoice(parsed, contact, settings, recomputed)
                report.drafts.append(parsed.number or parsed.external_id)
                continue

            # Created as "draft" and only flipped to "issued" at the very
            # end, mirroring documents.issuing.issue(): DocumentLine.save()
            # refuses to write once its Document is already "issued"
            # (invariant 1), so the lines below would be rejected if the
            # document already carried its final status.
            document = Document.objects.create(
                kind="invoice",
                status="draft",
                contact=contact,
                language=settings.default_language,
                currency="EUR",
                source=SOURCE,
                external_id=parsed.external_id,
                reference=parsed.reference,
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
                    line_total_cents=line_total_cents(line.quantity, line.unit_price_cents),
                )

            document.number = parsed.number
            document.issue_date = parsed.issue_date
            document.due_date = parsed.due_date
            document.business_snapshot = business_snapshot(settings)
            document.contact_snapshot = _snapshot_as_stated(contact, parsed.customer)
            document.kor_text_snapshot = settings.kor_text if settings.kor_enabled else ""
            # Faithful (SPEC.md section 7): Moneybird's own stated totals,
            # never the recomputed ones — see the discrepancy check
            # above, and huismus-intern/STATUS.md's M5 notes on why the two can
            # legitimately differ by a cent even when nothing is wrong.
            document.subtotal_cents = parsed.stated_subtotal_cents
            document.tax_cents = parsed.stated_tax_cents
            document.total_cents = parsed.stated_total_cents
            # Its VAT per rate, only when Moneybird's totals are those of
            # its lines (huismus-intern/besluiten.md, 2026-11-06). Before
            # the status below: once issued, the triggers refuse new rows.
            store_vat_rows(
                document,
                document.lines.order_by("position"),
                subtotal_cents=document.subtotal_cents,
                tax_cents=document.tax_cents,
            )
            document.status = "issued"
            document.save()

            # One Payment per invoice, dated on Moneybird's own "betaald
            # op" — Moneybird's export has no per-installment payment
            # history to reconstruct, so a partially paid invoice still
            # becomes exactly one Payment for the amount paid so far.
            paid_cents = parsed.stated_total_cents - parsed.stated_unpaid_cents
            if paid_cents > 0 and parsed.paid_on:
                Payment.objects.create(
                    document=document, paid_on=parsed.paid_on, amount_cents=paid_cents
                )
            elif paid_cents > 0:
                # Moneybird says money came in ("totaal onbetaald" <
                # total) but gives no date for it — recorded as a review
                # item instead of silently dropping the payment.
                report.payment_issues.append(
                    _(
                        "Factuur %(number)s: € %(paid)s is betaald volgens Moneybird, "
                        "maar zonder datum. Voeg de betaling zelf toe."
                    )
                    % {"number": parsed.number, "paid": euros(paid_cents)}
                )
            elif paid_cents < 0:
                report.payment_issues.append(
                    _(
                        "Factuur %(number)s: volgens Moneybird staat er € %(unpaid)s open, "
                        "meer dan het totaal van € %(total)s. Kijk de betalingen na in Moneybird."
                    )
                    % {
                        "number": parsed.number,
                        "unpaid": euros(parsed.stated_unpaid_cents),
                        "total": euros(parsed.stated_total_cents),
                    }
                )

            # By external_id, not number: see invoices.pdfs_by_external_id().
            pdf_content = pdfs_by_external_id.get(parsed.external_id)
            if pdf_content is None:
                report.missing_pdfs.append(parsed.number)
            elif write_attachments:
                # Only on a real commit: FileField writes to storage
                # immediately on save (Django's FileField.pre_save()),
                # outside the DB transaction — a dry-run's rollback below
                # would not undo a file already written to disk.
                Attachment.objects.create(
                    document=document,
                    file=ContentFile(pdf_content, name=f"{parsed.number}.pdf"),
                    kind="original_pdf",
                    sha256=hashlib.sha256(pdf_content).hexdigest(),
                    source=SOURCE,
                )

        report.numbering_note = _continue_numbering(
            "invoice",
            settings.invoice_number_format,
            imported_numbers,
            settings,
            label=_("factuurnummers"),
        )

        if not commit:
            transaction.set_rollback(True)
    return report


def _differs_from_ubl(document: Document, ubl_lines) -> bool:
    """An invoice imported before Huismus read the UBL (or edited since)
    whose lines aren't the UBL's: description, quantity, price and VAT
    rate, as imports.ubl compares them."""
    lines = list(document.lines.order_by("position"))
    if len(lines) != len(ubl_lines):
        return True
    return any(
        line_differences(line, ubl, allow_vat_included=False)
        for line, ubl in zip(lines, ubl_lines, strict=True)
    )


def _import_draft_invoice(parsed, contact, settings, totals) -> None:
    """A Moneybird invoice that was never sent (draft or scheduled) becomes
    a draft: the user finishes and issues it here. It keeps its Moneybird
    number, if it has one (documents.issuing), so the numbering above
    continues after it. No snapshots, payments or original PDF: those
    belong to an issued invoice, and issuing takes the snapshots. `totals`:
    compute_totals() of its lines, as a draft stores them (invariant 3)."""
    document = Document.objects.create(
        kind="invoice",
        status="draft",
        contact=contact,
        number=parsed.number,
        issue_date=parsed.issue_date,
        due_date=parsed.due_date,
        language=settings.default_language,
        currency="EUR",
        source=SOURCE,
        external_id=parsed.external_id,
        reference=parsed.reference,
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
            line_total_cents=line_total_cents(line.quantity, line.unit_price_cents),
        )
    document.subtotal_cents = totals.subtotal_cents
    document.tax_cents = totals.tax_cents
    document.total_cents = totals.total_cents
    document.save()


def import_quotes(parsed_quotes, *, commit: bool) -> QuoteImportReport:
    report = QuoteImportReport()
    settings = Settings.load()
    imported_numbers: list[tuple] = []  # (issue_date, number, customer number): numbering

    with transaction.atomic():
        for parsed in parsed_quotes:
            if Document.objects.filter(source=SOURCE, external_id=parsed.external_id).exists():
                # Same reasoning as invoices: SPEC.md's "re-importing
                # changes nothing" is a skip, never an update — even
                # though a quote (unlike an invoice) isn't immutable,
                # re-writing it would silently clobber any local edit
                # made in this UI since the first import.
                report.unchanged += 1
                continue

            if not parsed.lines:
                report.skipped_no_lines.append(parsed.number)
                continue

            contact = Contact.objects.filter(
                source=SOURCE, customer_number=parsed.customer_number
            ).first()
            if contact is None:
                report.skipped_missing_contact.append(parsed.number)
                continue

            recomputed = compute_totals(parsed.lines)
            mismatches = [
                (label, stated, recomputed_value)
                for label, stated, recomputed_value in (
                    (_("subtotaal"), parsed.stated_subtotal_cents, recomputed.subtotal_cents),
                    (_("btw"), parsed.stated_tax_cents, recomputed.tax_cents),
                    (_("totaal"), parsed.stated_total_cents, recomputed.total_cents),
                )
                if stated != recomputed_value
            ]
            if parsed.has_discount:
                # Under "Korting", not also as a discrepancy, but with the
                # difference to the cent (CLAUDE.md rule 6).
                label = _("Offerte %(number)s")
                report.discounts.append(
                    _mismatch_text(label, parsed.number, mismatches)
                    if mismatches
                    else label % {"number": parsed.number}
                )
            elif mismatches:
                report.discrepancies.append(
                    _mismatch_text(_("Offerte %(number)s"), parsed.number, mismatches)
                )

            report.new += 1
            imported_numbers.append((parsed.issue_date, parsed.number, parsed.customer_number))

            # No draft-then-flip dance here, unlike invoices: a quote's
            # status vocabulary has no "issued" (huismus/documents/models.py's
            # ALLOWED_STATUSES_BY_KIND), so DocumentLine.save()'s
            # immutability check never rejects a quote's lines, whatever
            # status the quote itself already has.
            document = Document.objects.create(
                kind="quote",
                status=parsed.status,
                number=parsed.number,
                issue_date=parsed.issue_date,
                expiry_date=parsed.expiry_date,
                accepted_on=parsed.accepted_on,
                declined_on=parsed.declined_on,
                contact=contact,
                business_snapshot=business_snapshot(settings),
                contact_snapshot=_snapshot_as_stated(contact, parsed.customer),
                kor_text_snapshot=settings.kor_text if settings.kor_enabled else "",
                language=settings.default_language,
                currency="EUR",
                # Faithful (SPEC.md section 7): Moneybird's own stated
                # totals, never the recomputed ones — same reasoning as
                # import_sales_invoices().
                subtotal_cents=parsed.stated_subtotal_cents,
                tax_cents=parsed.stated_tax_cents,
                total_cents=parsed.stated_total_cents,
                source=SOURCE,
                external_id=parsed.external_id,
                reference=parsed.reference,
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
                    line_total_cents=line_total_cents(line.quantity, line.unit_price_cents),
                )

        report.numbering_note = _continue_numbering(
            "quote",
            settings.quote_number_format,
            imported_numbers,
            settings,
            label=_("offertenummers"),
        )

        if not commit:
            transaction.set_rollback(True)
    return report


def _continue_numbering(
    kind: str, number_format: str, imported_numbers, settings: Settings, *, label: str
) -> str:
    """SPEC.md section 7: "the sequence continues after the highest
    imported number." Only numbers that parse cleanly against the
    configured format count — anything else is exactly SPEC.md's "if
    existing numbers cannot be parsed against the format, the user sets
    the next number manually," reported rather than guessed at. Writes
    unconditionally like the rest of this transaction — the caller's
    dry-run rollback undoes this the same way it undoes everything else.
    Shared by import_sales_invoices() and import_quotes(); `kind`
    matches documents.models.SEQUENCE_KIND_CHOICES ("invoice"/"quote").
    """
    if not imported_numbers:
        return ""

    highest_seq_by_year: dict[int | None, int] = {}
    unparsed = 0
    for issue_date, number, customer_number in imported_numbers:
        year = issue_date.year if settings.number_reset_yearly else None
        seq = parse_number(number_format, number, year=year, customer=customer_number)
        if seq is None:
            unparsed += 1
            continue
        highest_seq_by_year[year] = max(seq, highest_seq_by_year.get(year, 0))

    for year, seq in highest_seq_by_year.items():
        # ensure_sequence_row(), not get_or_create(): a concurrent first
        # allocate_number() call for this same (kind, year) — e.g. a
        # hand-issued document via the UI while this import runs — could
        # otherwise race get_or_create()'s own SELECT-then-INSERT into a
        # SQLite "database table is locked" error that DATABASES.OPTIONS
        # .timeout never retries. See huismus/documents/numbering.py's docstring.
        ensure_sequence_row(kind, year)
        NumberSequence.objects.filter(kind=kind, year=year, last_value__lt=seq).update(
            last_value=seq
        )

    if unparsed:
        return _(
            "%(unparsed)s van %(total)s geïmporteerde %(label)s passen niet in het ingestelde "
            "nummerformaat. Stel het volgende nummer zelf in bij Instellingen."
        ) % {"unparsed": unparsed, "total": len(imported_numbers), "label": label}
    return ""


def import_expenses(
    parsed_expenses,
    receipts_by_external_id: dict[str, list[tuple[str, bytes]]],
    *,
    commit: bool,
    write_attachments: bool | None = None,
) -> ExpenseImportReport:
    """Moneybird's incoming documents as Expense rows, one per document,
    with their files as receipts (SPEC.md section 7). `write_attachments`:
    as in import_sales_invoices(), the pipeline's real dry-run/commit
    intent for files, which a rollback can't undo. Decisions on category,
    status and description: huismus-intern/besluiten.md, 2026-11-01,
    "Uitgaven uit de Moneybird-import"."""
    if write_attachments is None:
        write_attachments = commit
    report = ExpenseImportReport()
    categories: dict[str, ExpenseCategory] = {}

    with transaction.atomic():
        for parsed in parsed_expenses:
            # parsed.status is not looked at: every status becomes an
            # expense (huismus-intern/besluiten.md).
            if Expense.objects.filter(source=SOURCE, external_id=parsed.external_id).exists():
                # Skipped, never updated: the user may have changed it
                # since (a category, a receipt), as with quotes.
                report.unchanged += 1
                continue

            label = (
                f"{parsed.reference} ({parsed.supplier})" if parsed.reference else parsed.supplier
            )
            mismatches = _expense_mismatches(parsed)
            if mismatches:
                report.discrepancies.append(
                    _mismatch_text(_("Uitgave %(number)s"), label, mismatches)
                )

            for line in parsed.lines:
                # A rate Moneybird gave that Huismus doesn't take over; no
                # rate columns at all is no message.
                given = line.vat_rate_name or (
                    f"{line.vat_rate_number}%" if line.vat_rate_number else ""
                )
                if given and not line.vat_rate:
                    report.unknown_vat_rates.append(f"{label}: {given}")
            expense = create_expense(
                _expense_lines(parsed, categories, report),
                date=parsed.date,
                supplier=parsed.supplier,
                # The lines have their own descriptions; the supplier's
                # reference makes the expense findable by their number.
                description=parsed.reference,
                source=SOURCE,
                external_id=parsed.external_id,
            )
            report.new += 1

            receipts = receipts_by_external_id.get(parsed.external_id, [])
            if not receipts:
                report.missing_receipts.append(label)
            elif write_attachments:
                for filename, content in receipts:
                    Attachment.objects.create(
                        expense=expense,
                        file=ContentFile(content, name=filename),
                        kind="receipt",
                        sha256=hashlib.sha256(content).hexdigest(),
                        source=SOURCE,
                    )

        if not commit:
            transaction.set_rollback(True)
    return report


def _expense_lines(parsed, categories: dict, report) -> list[ExpenseLineInput]:
    """The lines of an expense as Moneybird has them, each with its own
    category (huismus-intern/besluiten.md, 2026-11-02). Gross, what was paid
    (invariant 7): Moneybird's own total, never a recomputed one, split over
    the lines by their subtotal (Moneybird gives a line no gross amount),
    so the lines add up to exactly that total. Moneybird's own VAT is split
    the same way, so the expense's VAT stays exactly Moneybird's (never
    recomputed); none for a foreign currency. A document without lines
    gets one with the whole total."""
    lines = parsed.lines or [ParsedExpenseLine("", parsed.stated_subtotal_cents)]
    subtotals = [line.subtotal_cents for line in lines]
    gross = split_gross(parsed.stated_total_cents, subtotals)
    if parsed.stated_tax_cents is None:  # a foreign currency
        vat = [None] * len(lines)
    else:
        vat = split_gross(parsed.stated_tax_cents, subtotals)
    return [
        ExpenseLineInput(
            description=line.description,
            amount_cents=amount,
            vat_info_cents=line_vat,
            category=_category(line.category, categories, report),
            vat_rate=line.vat_rate,
        )
        for line, amount, line_vat in zip(lines, gross, vat, strict=True)
    ]


def _category(name: str, categories: dict, report):
    """Moneybird's category by name: the one with that name, or a new one
    at the bottom of the list, named in the report. `categories`: the ones
    this import used. A dry run creates it too, inside the pipeline's
    transaction, whose rollback removes it again."""
    if not name:
        return None
    if name not in categories:
        category = ExpenseCategory.objects.filter(name=name).first()
        if category is None:
            last = ExpenseCategory.objects.aggregate(Max("sort_order"))["sort_order__max"]
            category = ExpenseCategory.objects.create(
                name=name, sort_order=0 if last is None else last + 1
            )
            report.new_categories.append(name)
        categories[name] = category
    return categories[name]


def _expense_mismatches(parsed) -> list[tuple]:
    """Moneybird's own totals checked to the cent: the lines add up to the
    subtotal (summed by the one totals function, invariant 4), and the
    subtotal plus VAT is the total. The VAT itself is not recomputed: it
    is typed over from the receipt, often a cent off 21% of the subtotal,
    and only for information under the KOR (invariant 7)."""
    # Each line as one unit at its subtotal, without VAT: compute_totals()
    # then adds up the lines' subtotals, and only that is used.
    lines = [
        LineInput(quantity=Decimal(1), unit_price_cents=line.subtotal_cents, tax_rate_bp=0)
        for line in parsed.lines
    ]
    mismatches = []
    lines_subtotal = compute_totals(lines).subtotal_cents
    if lines and lines_subtotal != parsed.stated_subtotal_cents:
        mismatches.append((_("subtotaal"), parsed.stated_subtotal_cents, lines_subtotal))
    if parsed.stated_tax_cents is not None:
        subtotal_plus_tax = parsed.stated_subtotal_cents + parsed.stated_tax_cents
        if subtotal_plus_tax != parsed.stated_total_cents:
            mismatches.append((_("totaal"), parsed.stated_total_cents, subtotal_plus_tax))
    return mismatches
