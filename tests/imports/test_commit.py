# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from dataclasses import replace
from pathlib import Path

import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact, ContactPerson
from huismus.core.models import Attachment
from huismus.documents.models import Document, NumberSequence, Payment
from huismus.imports.commit import import_contacts, import_quotes, import_sales_invoices
from huismus.imports.contacts import parse_contacts
from huismus.imports.invoices import parse_sales_invoices, pdfs_by_external_id, pdfs_by_number
from huismus.imports.quotes import parse_quotes
from huismus.imports.sources import read_files

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _parsed_2019_contacts():
    files = read_files(FIXTURES / "lindeboom_communicatie_2019")
    content = next(c for n, c in files.items() if n.endswith("_contacts.xlsx"))
    return parse_contacts(content)


def _2019_files():
    return read_files(FIXTURES / "lindeboom_communicatie_2019")


def _parsed_2019_invoices():
    files = _2019_files()
    header = next(
        c for n, c in files.items() if n.endswith("sales_invoices/verkoopfacturen_export.xlsx")
    )
    lines = next(
        c
        for n, c in files.items()
        if n.endswith("sales_invoices_details/verkoopfacturen_regels_export.xlsx")
    )
    return parse_sales_invoices(header, lines)


def _parsed_2019_quotes():
    files = _2019_files()
    header = next(c for n, c in files.items() if n.endswith("estimates/offertes_export.xlsx"))
    lines = next(
        c for n, c in files.items() if n.endswith("estimates_details/offertes_regels_export.xlsx")
    )
    return parse_quotes(header, lines)


def test_dry_run_reports_new_contacts_but_writes_nothing():
    parsed = _parsed_2019_contacts()

    report = import_contacts(parsed, commit=False)

    assert report.new == len(parsed)
    assert report.updated == 0
    assert Contact.objects.count() == 0
    assert ContactPerson.objects.count() == 0


def test_commit_persists_contacts_and_persons():
    parsed = _parsed_2019_contacts()

    report = import_contacts(parsed, commit=True)

    assert report.new == len(parsed)
    assert Contact.objects.count() == len(parsed)
    hoge_wissel = Contact.objects.get(source="moneybird", external_id="184512349371107181")
    assert hoge_wissel.company_name == "Hoge Wissel Advies"
    assert hoge_wissel.customer_number == "44"
    assert hoge_wissel.persons.count() == 1
    assert hoge_wissel.persons.get().name == "Pim van Rijn"


def test_commit_keeps_a_contact_s_attention_line():
    import_contacts(_parsed_2019_contacts(), commit=True)

    assert Contact.objects.get(customer_number="13").attention == "Karin Groen"


def test_reimporting_unchanged_data_reports_zero_changes():
    parsed = _parsed_2019_contacts()
    import_contacts(parsed, commit=True)
    contact_count_after_first = Contact.objects.count()

    report = import_contacts(parsed, commit=True)

    assert report.new == 0
    assert report.updated == 0
    assert report.unchanged == len(parsed)
    assert Contact.objects.count() == contact_count_after_first


def test_a_changed_field_is_reported_and_applied_as_an_update():
    parsed = _parsed_2019_contacts()
    import_contacts(parsed, commit=True)
    contact = Contact.objects.get(source="moneybird", external_id="184512349371107181")
    contact.city = "Een andere stad"
    contact.save()

    report = import_contacts(parsed, commit=True)

    assert report.updated == 1
    assert report.new == 0
    contact.refresh_from_db()
    assert contact.city == "Gouda"  # re-imported from the source file


def test_dry_run_after_a_real_commit_still_changes_nothing():
    parsed = _parsed_2019_contacts()
    import_contacts(parsed, commit=True)
    count_before = Contact.objects.count()

    report = import_contacts(parsed, commit=False)

    assert report.unchanged == len(parsed)
    assert Contact.objects.count() == count_before


def test_dry_run_sales_invoices_reports_new_but_writes_nothing():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=False)

    assert report.new == len(parsed)
    assert Document.objects.count() == 0
    assert Payment.objects.count() == 0
    assert Attachment.objects.count() == 0


def test_commit_true_with_write_attachments_false_never_touches_storage():
    # Regression: huismus/imports/pipeline.py calls this with commit=True
    # unconditionally (so its own nested transaction never self-
    # rollbacks — see the pipeline's module docstring) and passes the
    # *real* dry-run/commit intent separately as write_attachments.
    # Before this parameter existed, commit=True on its own always wrote
    # every original PDF to disk regardless of the real intent, because
    # FileField writes to storage immediately (outside any DB
    # transaction) — a dry run through the pipeline silently left real
    # files behind that no rollback could undo.
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    import_sales_invoices(parsed, pdfs, commit=True, write_attachments=False)

    assert Document.objects.count() == len(parsed)  # the DB write still happens
    assert Attachment.objects.count() == 0  # but no file/Attachment row


def test_commit_persists_a_known_invoice_faithfully():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert report.new == len(parsed)
    assert Document.objects.count() == len(parsed)
    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    assert invoice.kind == "invoice"
    assert invoice.status == "issued"
    assert invoice.number == "430033"
    # Moneybird's own stated total, not Huismus's recomputation from
    # lines — the two differ by a cent for this invoice, faithfully
    # preserved as a reported discrepancy instead (see the test below).
    assert invoice.subtotal_cents == 13426
    assert invoice.total_cents == 13426
    assert invoice.contact.customer_number == "43"
    assert invoice.contact_snapshot["customer_number"] == "43"
    assert invoice.lines.count() == 4


def test_an_imported_invoice_shows_the_customer_and_units_as_on_the_invoice():
    # Re-rendered, an old invoice must not take the customer's new name or
    # address, nor lose "uur" after "2,5".
    files = read_files(FIXTURES / "lindeboom_communicatie_2021")
    contacts = next(c for n, c in files.items() if n.endswith("_contacts.xlsx"))
    import_contacts(parse_contacts(contacts), commit=True)
    header = next(
        c for n, c in files.items() if n.endswith("sales_invoices/verkoopfacturen_export.xlsx")
    )
    lines = next(
        c
        for n, c in files.items()
        if n.endswith("sales_invoices_details/verkoopfacturen_regels_export.xlsx")
    )
    import_sales_invoices(parse_sales_invoices(header, lines), {}, commit=True)

    invoice = Document.objects.get(number="430057")
    assert invoice.contact.company_name == "Stille Vallei Studio"
    assert invoice.contact_snapshot["display_name"] == "Vrije Brug Projecten"
    assert invoice.contact_snapshot["company_name"] == "Vrije Brug Projecten"
    assert invoice.contact_snapshot["city"] == "Gouda"
    assert invoice.contact_snapshot["customer_number"] == "43"
    assert Document.objects.get(number="440056").lines.filter(unit="uur").exists()


def test_a_stated_vs_recomputed_mismatch_is_reported_not_silently_fixed():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert any("430033" in d for d in report.discrepancies)
    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    assert invoice.total_cents == 13426  # stated total, unchanged by the mismatch


def test_a_fully_paid_invoice_gets_a_matching_payment():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    import_sales_invoices(parsed, pdfs, commit=True)

    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    payment = invoice.payments.get()
    assert payment.amount_cents == 13426
    assert str(payment.paid_on) == "2019-03-06"


def test_the_original_pdf_is_attached_by_invoice_number():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    import_sales_invoices(parsed, pdfs, commit=True)

    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    attachment = invoice.attachments.get()
    assert attachment.kind == "original_pdf"
    assert attachment.source == "moneybird"
    assert attachment.sha256


def test_reimporting_invoices_changes_nothing_issued_documents_are_immutable():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())
    import_sales_invoices(parsed, pdfs, commit=True)
    count_before = Document.objects.count()

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert report.new == 0
    assert report.unchanged == len(parsed)
    assert Document.objects.count() == count_before


def test_real_moneybird_numbers_do_not_fit_the_default_format():
    # Documents this fixture's real property rather than assuming it:
    # Moneybird's own numbers ("430033") don't fit Huismus's default
    # "{year}-{seq:04d}" invoice_number_format at all, so numbering
    # cannot continue automatically — SPEC.md's documented fallback ("the
    # user sets the next number manually"), reported rather than guessed.
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert report.numbering_note != ""
    assert NumberSequence.objects.count() == 0


def test_an_apparent_payment_with_no_paid_on_date_is_reported_not_dropped():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    invoice_430033 = next(i for i in parsed if i.number == "430033")
    parsed[parsed.index(invoice_430033)] = replace(invoice_430033, paid_on=None)
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert any("430033" in issue for issue in report.payment_issues)
    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    assert invoice.payments.count() == 0


def test_dry_run_quotes_reports_new_but_writes_nothing():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_quotes()

    report = import_quotes(parsed, commit=False)

    assert report.new == len(parsed)
    assert Document.objects.filter(kind="quote").count() == 0


def test_commit_persists_a_known_quote_faithfully():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_quotes()

    report = import_quotes(parsed, commit=True)

    assert report.new == len(parsed)
    assert Document.objects.filter(kind="quote").count() == len(parsed)
    quote = Document.objects.get(source="moneybird", external_id="244320874481583895")
    assert quote.kind == "quote"
    assert quote.status == "declined"  # Moneybird's "rejected"
    assert quote.number == "480006"
    assert quote.subtotal_cents == 158671
    assert quote.total_cents == 158671
    assert quote.contact.customer_number == "48"
    assert quote.contact_snapshot["customer_number"] == "48"
    assert quote.lines.count() >= 1


def test_reimporting_quotes_is_a_pure_skip():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_quotes()
    import_quotes(parsed, commit=True)
    count_before = Document.objects.filter(kind="quote").count()

    report = import_quotes(parsed, commit=True)

    assert report.new == 0
    assert report.unchanged == len(parsed)
    assert Document.objects.filter(kind="quote").count() == count_before


def test_quotes_do_not_block_on_immutability_unlike_invoices():
    # Unlike an invoice, a quote's status vocabulary has no "issued", so
    # import_quotes() writes the final status directly (no draft-then-
    # flip dance) — this would raise ImmutableDocumentError if that
    # assumption were ever wrong.
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_quotes()

    import_quotes(parsed, commit=True)  # must not raise

    assert Document.objects.filter(kind="quote").exists()


def test_real_moneybird_quote_numbers_do_not_fit_the_default_format():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_quotes()

    report = import_quotes(parsed, commit=True)

    assert report.numbering_note != ""
    assert NumberSequence.objects.filter(kind="quote").count() == 0


def test_quote_missing_a_contact_is_skipped_and_reported():
    parsed = _parsed_2019_quotes()  # no contacts imported first

    report = import_quotes(parsed, commit=True)

    assert report.new == 0
    assert len(report.skipped_missing_contact) == len(parsed)
    assert Document.objects.filter(kind="quote").count() == 0


def test_unpaid_exceeding_total_is_reported_not_a_negative_payment():
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    invoice_430033 = next(i for i in parsed if i.number == "430033")
    parsed[parsed.index(invoice_430033)] = replace(
        invoice_430033, stated_unpaid_cents=invoice_430033.stated_total_cents + 100
    )
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert any("430033" in issue for issue in report.payment_issues)
    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    assert invoice.payments.count() == 0


def test_two_invoices_with_the_same_number_each_get_their_own_pdf():
    # Numbers can repeat across years (a yearly reset without the year in
    # the format); the external_id can't. A PDF keyed by number alone would
    # attach one year's PDF to both invoices, and an issued document can't
    # be corrected afterwards.
    import_contacts(_parsed_2019_contacts(), commit=True)
    original = _parsed_2019_invoices()[0]
    twin = replace(original, external_id=original.external_id + "9")
    pdfs = {original.external_id: b"%PDF- van 2019", twin.external_id: b"%PDF- van 2020"}

    import_sales_invoices([original, twin], pdfs, commit=True)

    for invoice, content in ((original, b"%PDF- van 2019"), (twin, b"%PDF- van 2020")):
        document = Document.objects.get(source="moneybird", external_id=invoice.external_id)
        attachment = Attachment.objects.get(document=document, kind="original_pdf")
        assert attachment.file.read() == content


def test_pdfs_by_external_id_takes_each_invoice_s_pdf_from_its_own_files():
    invoice = _parsed_2019_invoices()[0]
    pdfs = pdfs_by_external_id([invoice], _2019_files())

    assert pdfs == {invoice.external_id: pdfs_by_number(_2019_files())[invoice.number]}


def test_numbering_continues_after_moneybird_s_customer_number_format():
    # Moneybird's default: customer number, then one running sequence for
    # all customers. With that format in Settings, the next invoice
    # continues after the highest imported sequence number (44 in 2019).
    settings = Settings.load()
    settings.invoice_number_format = "{customer}{seq:04d}"
    settings.quote_number_format = "{customer}{seq:04d}"
    settings.number_reset_yearly = False
    settings.save()
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()

    report = import_sales_invoices(parsed, pdfs_by_external_id(parsed, _2019_files()), commit=True)

    assert report.numbering_note == ""
    highest = max(int(invoice.number[-4:]) for invoice in parsed)
    assert NumberSequence.objects.get(kind="invoice", year=None).last_value == highest


def test_a_scheduled_moneybird_invoice_becomes_a_draft_that_keeps_its_number():
    # Moneybird "scheduled" (ingepland) and "draft": never sent, so not
    # issued here either. The user finishes and issues it in Huismus.
    import_contacts(_parsed_2019_contacts(), commit=True)
    parsed = _parsed_2019_invoices()
    invoice_430033 = next(i for i in parsed if i.number == "430033")
    parsed[parsed.index(invoice_430033)] = replace(
        invoice_430033, status="draft", stated_unpaid_cents=invoice_430033.stated_total_cents
    )
    pdfs = pdfs_by_external_id(parsed, _2019_files())

    report = import_sales_invoices(parsed, pdfs, commit=True)

    assert report.drafts == ["430033"]
    invoice = Document.objects.get(source="moneybird", external_id="238804323181528959")
    assert (invoice.status, invoice.number) == ("draft", "430033")
    assert invoice.lines.count() == 4
    assert invoice.payments.count() == 0
    assert not invoice.attachments.exists()
    assert invoice.business_snapshot is None
    # Re-import: still nothing to change.
    assert import_sales_invoices(parsed, pdfs, commit=True).new == 0
