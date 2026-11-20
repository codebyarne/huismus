# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Reading a statement into Huismus (#77): what is sure is booked, what is
likely proposed, the rest waits; the same file again changes nothing;
and what Huismus booked can be undone."""

import io
import zipfile
from datetime import date
from pathlib import Path

import pytest

from huismus.bank import reading
from huismus.bank.lines import StatementReadError
from huismus.bank.models import BankStatement, BankTransaction
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db

State = BankTransaction.State
FIXTURES = Path(__file__).parents[1] / "fixtures" / "bank"


@pytest.fixture(autouse=True)
def _settings():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()


def _invoice(cents, company="Klant BV", iban="", **contact):
    customer = Contact.objects.create(company_name=company, iban=iban, **contact)
    document = Document.objects.create(kind="invoice", status="draft", contact=customer)
    DocumentLine.objects.create(
        document=document, description="Werk", quantity="1", unit_price_cents=cents
    )
    return issue(document)


def _camt(*entries, account="NL91ABNA0417164300"):
    """A fictional CAMT.053 with one credit per (amount, name, text[, iban])."""
    body = ""
    for amount, name, text, *rest in entries:
        iban = rest[0] if rest else ""
        body += f"""<Ntry><Amt Ccy="EUR">{amount}</Amt><CdtDbtInd>CRDT</CdtDbtInd>
        <Sts>BOOK</Sts><BookgDt><Dt>2026-11-14</Dt></BookgDt><NtryDtls><TxDtls>
        <RltdPties><Dbtr><Nm>{name}</Nm></Dbtr>
        <DbtrAcct><Id><IBAN>{iban}</IBAN></Id></DbtrAcct></RltdPties>
        <RmtInf><Ustrd>{text}</Ustrd></RmtInf></TxDtls></NtryDtls></Ntry>"""
    return f"""<?xml version="1.0"?>
<Document xmlns="urn:iso:std:iso:20022:tech:xsd:camt.053.001.02"><BkToCstmrStmt>
<Stmt><Acct><Id><IBAN>{account}</IBAN></Id></Acct>{body}</Stmt>
</BkToCstmrStmt></Document>""".encode()


def _read(data, name="afschrift.xml"):
    return reading.read_statement(name, data)


def test_number_and_open_amount_is_booked_as_a_payment():
    invoice = _invoice(121000)
    result = _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))

    payment = Payment.objects.get(document=invoice)
    assert payment.amount_cents == 121000
    assert payment.paid_on == date(2026, 11, 14)
    assert payment.method == "Overboeking"
    line = BankTransaction.objects.get()
    assert (line.state, line.payment) == (State.BOOKED, payment)
    assert Document.objects.get(pk=invoice.pk).payment_state == "paid"
    assert result.booked == [line]


def test_number_with_another_amount_is_proposed_and_books_nothing():
    invoice = _invoice(121000)
    result = _read(_camt(("500.00", "Klant BV", f"Factuur {invoice.number}")))

    assert not Payment.objects.exists()
    line = BankTransaction.objects.get()
    assert (line.state, line.proposed_document) == (State.PROPOSED, invoice)
    assert result.proposed == [line]


def test_amount_and_name_is_proposed():
    invoice = _invoice(60500, company="Studio Noord")
    _read(_camt(("605.00", "STUDIO NOORD", "bedankt")))
    line = BankTransaction.objects.get()
    assert (line.state, line.proposed_document) == (State.PROPOSED, invoice)


def test_the_customers_iban_from_the_contact_counts():
    invoice = _invoice(60500, company="Studio Noord", iban="NL02 TEST 0123 4567 88")
    _read(_camt(("605.00", "S. Noordhuis", "bedankt", "NL02TEST0123456788")))
    assert BankTransaction.objects.get().proposed_document == invoice


def test_the_name_on_the_invoice_counts_after_the_contact_was_renamed():
    invoice = _invoice(60500, company="Studio Noord")
    Contact.objects.filter(pk=invoice.contact_id).update(company_name="Noord Media")
    _read(_camt(("605.00", "Studio Noord", "bedankt")))
    assert BankTransaction.objects.get().proposed_document == invoice


def test_nothing_that_fits_waits_for_the_user():
    _invoice(121000)
    result = _read(_camt(("12.34", "Iemand", "terugbetaling")))
    line = BankTransaction.objects.get()
    assert (line.state, line.proposed_document) == (State.OPEN, None)
    assert result.open == [line]


def test_a_paid_invoice_is_not_open_any_more():
    invoice = _invoice(121000)
    first = _camt(("1210.00", "Klant BV", f"Factuur {invoice.number}"))
    _read(first)
    # The customer pays twice: the second time there is nothing open.
    _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number} nogmaals")))
    assert Payment.objects.count() == 1
    assert BankTransaction.objects.last().state == State.OPEN


def test_two_payments_for_one_invoice_in_one_file_book_only_the_first():
    invoice = _invoice(121000)
    _read(
        _camt(
            ("1210.00", "Klant BV", f"Factuur {invoice.number}"),
            ("1210.00", "Klant BV", f"Factuur {invoice.number} dubbel"),
        )
    )
    assert Payment.objects.count() == 1
    assert [t.state for t in BankTransaction.objects.all()] == [State.BOOKED, State.OPEN]


def test_a_payment_already_booked_by_hand_is_linked_not_booked_again():
    invoice = _invoice(121000)
    by_hand = Payment.objects.create(
        document=invoice, paid_on=date(2026, 11, 15), amount_cents=121000, method="Overboeking"
    )
    result = _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))
    line = BankTransaction.objects.get()
    assert (line.state, line.payment) == (State.ALREADY_BOOKED, by_hand)
    assert Payment.objects.count() == 1
    assert result.already_booked == [line]


def test_a_payment_by_hand_long_before_is_not_this_one():
    invoice = _invoice(121000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 9, 1), amount_cents=121000)
    _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))
    assert BankTransaction.objects.get().state == State.OPEN


def test_reading_the_same_file_again_changes_nothing():
    invoice = _invoice(121000)
    data = _camt(("1210.00", "Klant BV", f"Factuur {invoice.number}"), ("12.34", "Iemand", "iets"))
    _read(data)
    result = _read(data)
    assert result.seen_before == 2
    assert result.new == 0
    assert BankTransaction.objects.count() == 2
    assert Payment.objects.count() == 1


def test_an_overlapping_statement_adds_only_the_new_lines():
    _read(_camt(("10.00", "A", "een"), ("20.00", "B", "twee")))
    result = _read(_camt(("20.00", "B", "twee"), ("30.00", "C", "drie")))
    assert (result.seen_before, result.new) == (1, 1)
    assert BankTransaction.objects.count() == 3


def test_two_equal_payments_on_one_day_are_both_kept():
    _read(_camt(("10.00", "A", "huur"), ("10.00", "A", "huur")))
    assert BankTransaction.objects.count() == 2
    # And the same file again still adds none.
    _read(_camt(("10.00", "A", "huur"), ("10.00", "A", "huur")))
    assert BankTransaction.objects.count() == 2


def test_a_statement_without_new_lines_is_not_kept():
    data = _camt(("10.00", "A", "een"))
    _read(data)
    _read(data)
    assert BankStatement.objects.count() == 1


def test_the_bank_files_in_a_zip_are_read_all():
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("nov/a.xml", _camt(("10.00", "A", "een")))
        archive.writestr("nov/b.xml", _camt(("20.00", "B", "twee")))
        archive.writestr("LEESMIJ.txt", "geen afschrift")
    result = _read(buffer.getvalue(), name="afschriften.zip")
    assert result.new == 2


def test_mt940_and_camt_from_the_fixtures_read():
    result = _read((FIXTURES / "camt053-001-02.xml").read_bytes())
    assert result.new == 3
    assert result.not_incoming == 2
    assert result.other_currency == 1
    assert result.accounts == {"NL91ABNA0417164300"}


def test_a_file_that_is_no_statement_is_refused_and_keeps_nothing():
    with pytest.raises(StatementReadError):
        _read(b"%PDF-1.4 not a statement", name="afschrift.pdf")
    assert not BankStatement.objects.exists()


def test_undo_removes_the_payment_and_the_line_waits_again():
    invoice = _invoice(121000)
    _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))
    line = BankTransaction.objects.get()

    reading.undo(line)

    line.refresh_from_db()
    assert not Payment.objects.exists()
    assert (line.state, line.payment, line.proposed_document) == (State.OPEN, None, invoice)


def test_undo_leaves_a_payment_booked_by_hand_alone():
    invoice = _invoice(121000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 11, 14), amount_cents=121000)
    _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))
    line = BankTransaction.objects.get()
    with pytest.raises(ValueError):
        reading.undo(line)
    assert Payment.objects.count() == 1


def test_booking_a_line_on_an_invoice_the_user_chose():
    invoice = _invoice(121000)
    _read(_camt(("500.00", "Iemand", "deel")))
    line = BankTransaction.objects.get()

    reading.book(line, invoice)

    line.refresh_from_db()
    assert line.state == State.CONFIRMED
    assert line.payment.document == invoice
    assert line.payment.amount_cents == 50000
    assert Document.objects.get(pk=invoice.pk).payment_state == "partial"


def test_booking_twice_is_refused():
    invoice = _invoice(121000)
    _read(_camt(("500.00", "Iemand", "deel")))
    line = BankTransaction.objects.get()
    reading.book(line, invoice)
    with pytest.raises(ValueError):
        reading.book(line, invoice)
    assert Payment.objects.count() == 1


def test_booking_on_a_draft_or_quote_is_refused():
    draft = Document.objects.create(kind="invoice", status="draft")
    _read(_camt(("5.00", "Iemand", "deel")))
    with pytest.raises(ValueError):
        reading.book(BankTransaction.objects.get(), draft)


def test_skip_and_back():
    _read(_camt(("5.00", "Iemand", "iets")))
    line = BankTransaction.objects.get()
    assert reading.skip(line).state == State.SKIPPED
    assert reading.unskip(line).state == State.OPEN


def test_the_file_is_kept_once_in_the_data_folder(django_capture_on_commit_callbacks):
    data = _camt(("10.00", "A", "een"))
    with django_capture_on_commit_callbacks(execute=True):
        _read(data, name="../nov.xml")
    stored = BankStatement.objects.get()
    path = reading.archived_path(stored)
    assert path.parent == reading.archive_dir()
    assert path.read_bytes() == data
    with django_capture_on_commit_callbacks(execute=True):
        _read(data, name="../nov.xml")
    assert len(list(reading.archive_dir().iterdir())) == 1


@pytest.mark.parametrize(
    "name", ["mt940-ing.sta", "mt940-rabobank.swi", "mt940-abnamro.sta", "mt940-triodos.sta"]
)
def test_mt940_of_every_bank_reads(name):
    result = _read((FIXTURES / name).read_bytes(), name=name)
    assert result.new >= 1
    assert all(t.amount_cents > 0 for t in BankTransaction.objects.all())


def test_an_mt940_line_books_like_a_camt_one():
    customer = Contact.objects.create(company_name="Bakkerij De Korst")
    document = Document.objects.create(kind="invoice", status="draft", contact=customer)
    DocumentLine.objects.create(
        document=document, description="Brood", quantity="1", unit_price_cents=121000
    )
    invoice = issue(document)
    data = (
        (FIXTURES / "mt940-abnamro.sta").read_bytes().replace(b"2026-015", invoice.number.encode())
    )
    _read(data, name="abn.sta")
    assert Payment.objects.get().document == invoice


def test_a_rolled_back_read_keeps_no_file():
    with pytest.raises(StatementReadError):
        _read(b"<Document><BkToCstmrStmt>broken", name="kapot.xml")
    assert not reading.archive_dir().exists() or not list(reading.archive_dir().iterdir())


def test_a_zip_with_a_file_bigger_than_its_header_says_is_refused(monkeypatch):
    monkeypatch.setattr(reading, "_MAX_FILE_SIZE", 100)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("a.xml", _camt(("10.00", "A", "een")))
    with pytest.raises(StatementReadError):
        _read(buffer.getvalue(), name="a.zip")


def test_an_invoice_with_vat_is_booked_on_its_total_with_vat():
    settings = Settings.load()
    settings.kor_enabled = False
    settings.save()
    customer = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(kind="invoice", status="draft", contact=customer)
    DocumentLine.objects.create(
        document=document,
        description="Werk",
        quantity="1",
        unit_price_cents=100000,
        tax_rate_bp=2100,
    )
    invoice = issue(document)
    assert invoice.total_cents == 121000
    _read(_camt(("1210.00", "Klant BV", f"Factuur {invoice.number}")))
    assert BankTransaction.objects.get().state == State.BOOKED
