# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""#273, part 2: what an assistant changes, through the same functions as
the app's screens (SPEC.md M16). Each action: a test that it does what the
screen does, and one for what it refuses."""

from datetime import timedelta

import pytest
from django.core import mail
from django.core.files.base import ContentFile
from django.utils import timezone

from huismus.bank.models import BankStatement, BankTransaction
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.issuing import issue
from huismus.documents.models import Document, EmailLog, Payment
from huismus.documents.quoting import send_quote
from huismus.documents.reopening import reopen
from huismus.expenses import adding
from huismus.expenses.models import Expense, ExpenseCategory

from .test_tools import _draft, _issued

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


def _overdue(customer):
    """Issued 42 days ago with 30 days to pay: 12 days late."""
    draft = _draft(customer)
    draft.issue_date = TODAY - timedelta(days=42)
    draft.due_date = TODAY - timedelta(days=12)
    draft.save()
    return issue(draft)


# --- Payments ---


def test_the_payment_preview_says_what_stays_open(tool, business, customer):
    invoice = _issued(customer)
    found, _text, error = tool("preview_payment", id=invoice.pk, amount="200,00")
    assert not error
    assert found["action"] == "record_payment"
    assert found["outstanding_now"] == "€ 510,00"
    assert found["outstanding_after"] == "€ 310,00"
    assert not Payment.objects.exists()


def test_the_payment_preview_says_when_it_is_too_much(tool, business, customer):
    invoice = _issued(customer)
    found, _text, _error = tool("preview_payment", id=invoice.pk, amount="600")
    assert found["overpaid"] == "€ 90,00"


def test_a_payment_is_recorded_as_the_button_does(tool, business, customer):
    invoice = _issued(customer)
    found, _text, error = tool(
        "record_payment", id=invoice.pk, amount="510,00", paid_on=TODAY.isoformat()
    )
    assert not error
    payment = Payment.objects.get()
    assert (payment.document, payment.amount_cents, payment.method) == (
        invoice,
        51000,
        "Overboeking",
    )
    assert found["payment_state"] == "paid"
    assert found["path"] == f"/facturen/{invoice.pk}/"


def test_no_payment_on_a_draft_or_with_an_unclear_amount(tool, business, customer):
    _found, _text, error = tool("record_payment", id=_draft(customer).pk, amount="10")
    assert error
    _found, text, error = tool("record_payment", id=_issued(customer).pk, amount="tien")
    assert error and "1.250,00" in text
    assert not Payment.objects.exists()


# --- Reminders ---


def test_a_reminder_goes_to_the_customer_with_the_reminder_text(tool, mail_set_up, customer):
    invoice = _overdue(customer)
    preview, _text, error = tool("preview_reminder", id=invoice.pk)
    assert not error
    assert preview["to"] == "korrel@example.invalid"
    assert preview["days_overdue"] == 12
    assert not mail.outbox
    found, _text, error = tool("send_reminder", id=invoice.pk)
    assert not error and found["sent"]
    assert mail.outbox[0].subject == preview["subject"]
    assert EmailLog.objects.get().reminder is True


def test_no_reminder_for_an_invoice_that_is_not_late(tool, mail_set_up, customer):
    invoice = _issued(customer)
    _found, text, error = tool("send_reminder", id=invoice.pk)
    assert error and "niet te laat" in text
    assert not mail.outbox


def test_no_reminder_without_mail_set_up(tool, business, customer):
    _found, text, error = tool("preview_reminder", id=_overdue(customer).pk)
    assert error and "Instellingen → Mailen" in text


# --- Quotes ---


def test_answering_a_quote_goes_through_quoting(tool, business, customer):
    quote = send_quote(_draft(customer, kind="quote"))
    found, _text, error = tool("answer_quote", id=quote.pk, answer="accepted")
    assert not error
    quote.refresh_from_db()
    assert quote.status == "accepted" and quote.accepted_on == TODAY
    assert found["status"] == "accepted"


def test_only_a_sent_quote_is_answered(tool, business, customer):
    draft = _draft(customer, kind="quote")
    _found, text, error = tool("answer_quote", id=draft.pk, answer="declined")
    assert error and "verzonden offerte" in text
    draft.refresh_from_db()
    assert draft.status == "draft"


def test_a_quote_becomes_a_draft_invoice(tool, business, customer):
    quote = send_quote(_draft(customer, kind="quote"))
    found, _text, error = tool("convert_quote", id=quote.pk)
    assert not error
    invoice = Document.objects.get(pk=found["id"])
    assert (invoice.kind, invoice.status, invoice.related_document) == ("invoice", "draft", quote)
    assert invoice.total_cents == quote.total_cents
    assert found["path"] == f"/facturen/{invoice.pk}/"


def test_an_invoice_is_not_converted(tool, business, customer):
    _found, _text, error = tool("convert_quote", id=_issued(customer).pk)
    assert error


# --- Copies ---


def test_a_copy_is_a_new_draft_without_a_number(tool, business, customer):
    invoice = _issued(customer)
    found, _text, error = tool("copy_document", id=invoice.pk)
    assert not error
    copy = Document.objects.get(pk=found["id"])
    assert (copy.kind, copy.status, copy.number) == ("invoice", "draft", "")
    assert copy.total_cents == invoice.total_cents
    assert copy.related_document is None


def test_a_credit_note_is_not_copied(tool, business, customer):
    credit_note = Document.objects.create(kind="credit_note", status="draft", contact=customer)
    _found, _text, error = tool("copy_document", id=credit_note.pk)
    assert error
    assert Document.objects.count() == 1


# --- Deleting a draft ---


def test_a_draft_is_deleted(tool, business, customer):
    draft = _draft(customer)
    preview, _text, error = tool("preview_delete", what="draft", id=draft.pk)
    assert not error and preview["action"] == "delete_draft"
    assert Document.objects.filter(pk=draft.pk).exists()
    _found, _text, error = tool("delete_draft", id=draft.pk)
    assert not error
    assert not Document.objects.filter(pk=draft.pk).exists()


def test_an_issued_invoice_or_a_draft_with_a_number_is_not_deleted(tool, business, customer):
    invoice = _issued(customer)
    _found, _text, error = tool("delete_draft", id=invoice.pk)
    assert error
    reopen(invoice)
    _found, text, error = tool("delete_draft", id=invoice.pk)
    assert error and "nummer" in text
    assert Document.objects.filter(pk=invoice.pk).exists()


# --- Toch bewerken ---


def test_reopening_goes_through_reopening(tool, business, customer):
    invoice = _issued(customer)
    preview, _text, error = tool("preview_reopen", id=invoice.pk)
    assert not error
    assert preview["action"] == "reopen_document"
    assert "creditnota" in preview["advice"]
    found, _text, error = tool("reopen_document", id=invoice.pk)
    assert not error
    invoice.refresh_from_db()
    assert (invoice.status, found["number"]) == ("draft", invoice.number)
    assert invoice.reopened_at is not None


def test_undoing_puts_it_back_as_issued(tool, business, customer):
    invoice = reopen(_issued(customer))
    preview, _text, error = tool("preview_reopen", id=invoice.pk)
    assert preview["action"] == "undo_reopen"
    _found, _text, error = tool("undo_reopen", id=invoice.pk)
    assert not error
    invoice.refresh_from_db()
    assert invoice.status == "issued"


def test_an_ordinary_draft_has_nothing_to_undo(tool, business, customer):
    draft = _draft(customer)
    _found, text, error = tool("undo_reopen", id=draft.pk)
    assert error and "niets terug te zetten" in text
    _found, _text, error = tool("reopen_document", id=draft.pk)
    assert error


def test_an_invoice_with_a_credit_note_is_not_reopened(tool, business, customer):
    invoice = _issued(customer)
    credit_note = Document.objects.create(
        kind="credit_note", status="draft", contact=customer, related_document=invoice
    )
    credit_note.lines.create(position=0, description="Correctie", unit_price_cents=1000)
    issue(credit_note)
    _found, text, error = tool("reopen_document", id=invoice.pk)
    assert error and "creditnota" in text
    invoice.refresh_from_db()
    assert invoice.status == "issued"


# --- Expenses ---


def _expense():
    return adding.add_expense(
        date=TODAY.isoformat(),
        supplier="Drukkerij",
        description="Visitekaartjes",
        lines=[adding.Line("Kaartjes", "60,50", "10,50", None, "21")],
    )


@pytest.fixture
def no_kor(business):
    business.kor_enabled = False
    business.save()
    return business


def test_changing_an_expense_keeps_what_is_left_out(tool, business):
    expense = _expense()
    Expense.objects.filter(pk=expense.pk).update(needs_review=False)
    found, _text, error = tool("update_expense", id=expense.pk, supplier="Copyshop")
    assert not error
    expense.refresh_from_db()
    assert (expense.supplier, expense.description, expense.amount_cents) == (
        "Copyshop",
        "Visitekaartjes",
        6050,
    )
    # The user sees the change: "Nakijken" again.
    assert expense.needs_review and found["to_check"]


def test_new_lines_replace_the_old_ones_and_may_make_a_category(tool, business):
    expense = _expense()
    found, _text, error = tool(
        "update_expense",
        id=expense.pk,
        lines=[{"amount": "20", "category": "Drukwerk"}, {"amount": "5,25"}],
    )
    assert not error
    assert found["amount"] == "€ 25,25"
    assert found["new_categories"] == ["Drukwerk"]
    assert expense.lines.count() == 2


def test_a_change_of_date_leaves_the_lines_alone(tool, no_kor):
    """Also an old line without its VAT, which the form would refuse now."""
    expense = _expense()
    expense.lines.update(vat_info_cents=None, vat_rate="")
    _found, _text, error = tool("update_expense", id=expense.pk, date="2026-01-02")
    assert not error
    expense.refresh_from_db()
    assert (expense.date.isoformat(), expense.amount_cents) == ("2026-01-02", 6050)


def test_without_the_kor_a_changed_line_needs_its_vat(tool, no_kor):
    expense = _expense()
    _found, text, error = tool("update_expense", id=expense.pk, lines=[{"amount": "20"}])
    assert error and "btw" in text
    expense.refresh_from_db()
    assert expense.amount_cents == 6050


def test_a_receipt_from_the_tray_onto_an_expense(tool, business):
    expense = _expense()
    Expense.objects.filter(pk=expense.pk).update(needs_review=False)
    receipt = Attachment.objects.create(
        file=ContentFile(b"%PDF-1.4", name="bon.pdf"), kind="receipt", sha256="a" * 64
    )
    assert Attachment.objects.in_tray().filter(pk=receipt.pk).exists()
    _found, _text, error = tool("attach_receipt", expense_id=expense.pk, receipt_id=receipt.pk)
    assert not error
    receipt.refresh_from_db()
    assert receipt.expense == expense
    expense.refresh_from_db()
    assert expense.needs_review
    # Not twice.
    other = _expense()
    _found, text, error = tool("attach_receipt", expense_id=other.pk, receipt_id=receipt.pk)
    assert error


def test_deleting_an_expense_says_the_receipt_goes_too(tool, business):
    expense = _expense()
    Attachment.objects.create(
        expense=expense, file=ContentFile(b"%PDF-1.4", name="bon.pdf"), kind="receipt"
    )
    preview, _text, error = tool("preview_delete", what="expense", id=expense.pk)
    assert not error and "bonnetje" in preview["after"]
    _found, _text, error = tool("delete_expense", id=expense.pk)
    assert not error
    assert not Expense.objects.filter(pk=expense.pk).exists()
    assert not Attachment.objects.exists()


def test_an_unknown_expense(tool, business):
    _found, text, error = tool("delete_expense", id=999)
    assert error and "bestaat niet" in text


# --- Categories ---


def test_categories_are_added_renamed_and_deleted(tool, business):
    found, _text, error = tool("add_category", name="Reizen")
    assert not error
    category = ExpenseCategory.objects.get(pk=found["id"])
    _found, _text, error = tool("rename_category", id=category.pk, name="Reiskosten")
    assert not error
    category.refresh_from_db()
    assert category.name == "Reiskosten"
    preview, _text, error = tool("preview_delete", what="category", id=category.pk)
    assert not error and preview["action"] == "delete_category"
    _found, _text, error = tool("delete_category", id=category.pk)
    assert not error
    assert not ExpenseCategory.objects.exists()


def test_a_category_with_expenses_stays(tool, business):
    category = ExpenseCategory.objects.create(name="Kantoor")
    adding.add_expense(
        date=TODAY.isoformat(),
        supplier="",
        description="",
        lines=[adding.Line("Pennen", "4", None, category)],
    )
    _found, text, error = tool("preview_delete", what="category", id=category.pk)
    assert error and "andere categorie" in text
    _found, text, error = tool("delete_category", id=category.pk)
    assert error and "andere categorie" in text
    assert ExpenseCategory.objects.filter(pk=category.pk).exists()


def test_a_category_needs_a_name(tool, business):
    _found, _text, error = tool("add_category", name="")
    assert error
    assert not ExpenseCategory.objects.exists()


# --- Contacts ---


def test_a_customer_is_added_with_the_next_number(tool, business):
    found, _text, error = tool("add_contact", company_name="Studio Noord", city="Groningen")
    assert not error
    contact = Contact.objects.get(pk=found["id"])
    # ContactForm.save() gives the next customer number.
    assert contact.customer_number
    assert found["customer_number"] == contact.customer_number
    assert found["path"] == f"/contacten/{contact.pk}/"


def test_a_customer_needs_a_name(tool, business):
    _found, text, error = tool("add_contact", city="Groningen")
    assert error and "bedrijfsnaam" in text
    assert not Contact.objects.exists()


def test_changing_a_customer_keeps_the_rest_and_its_persons(tool, business, customer):
    customer.persons.create(name="Anna", email="anna@example.invalid")
    _found, _text, error = tool("update_contact", id=customer.pk, city="Zwolle")
    assert not error
    customer.refresh_from_db()
    assert (customer.company_name, customer.city) == ("Bakkerij De Korrel", "Zwolle")
    assert customer.persons.count() == 1


def test_archiving_and_back(tool, business, customer):
    _found, _text, error = tool("archive_contact", id=customer.pk, archived=True)
    assert not error
    customer.refresh_from_db()
    assert customer.archived
    found, _text, _error = tool("search_contacts")
    assert found["contacts"] == []
    tool("archive_contact", id=customer.pk, archived=False)
    customer.refresh_from_db()
    assert not customer.archived


# --- Bank ---


def _bank_line(cents, **fields):
    statement, _made = BankStatement.objects.get_or_create(filename="nov.xml")
    return BankTransaction.objects.create(
        statement=statement,
        booked_on=TODAY,
        amount_cents=cents,
        counterparty_name="Bakkerij De Korrel",
        fingerprint=f"{cents}-{BankTransaction.objects.count()}",
        **{"state": BankTransaction.State.OPEN, **fields},
    )


def test_a_proposal_is_confirmed_as_the_button_does(tool, business, customer):
    invoice = _issued(customer)
    line = _bank_line(51000, state=BankTransaction.State.PROPOSED, proposed_document=invoice)
    preview, _text, error = tool("preview_bank_booking", id=line.pk)
    assert not error
    assert preview["action"] == "confirm_bank_match"
    assert preview["outstanding_after"] == "€ 0,00"
    found, _text, error = tool("confirm_bank_match", id=line.pk)
    assert not error
    line.refresh_from_db()
    assert line.state == BankTransaction.State.CONFIRMED
    assert line.payment.document == invoice
    assert found["invoice"]["number"] == invoice.number


def test_a_line_is_booked_on_a_chosen_invoice_and_undone(tool, business, customer):
    invoice = _issued(customer)
    line = _bank_line(20000)
    preview, _text, _error = tool("preview_bank_booking", id=line.pk, invoice_id=invoice.pk)
    assert preview["action"] == "book_bank_line"
    _found, _text, error = tool("book_bank_line", id=line.pk, invoice_id=invoice.pk)
    assert not error
    assert Payment.objects.get().amount_cents == 20000
    preview, _text, _error = tool("preview_bank_booking", id=line.pk)
    assert preview["action"] == "undo_bank_booking"
    assert preview["payment_removed"] == "€ 200,00"
    assert preview["outstanding_after"] == "€ 510,00"
    _found, _text, error = tool("undo_bank_booking", id=line.pk)
    assert not error
    assert not Payment.objects.exists()
    line.refresh_from_db()
    assert line.state == BankTransaction.State.OPEN


def test_booking_twice_is_refused(tool, business, customer):
    invoice = _issued(customer)
    line = _bank_line(20000)
    tool("book_bank_line", id=line.pk, invoice_id=invoice.pk)
    _found, text, error = tool("book_bank_line", id=line.pk, invoice_id=invoice.pk)
    assert error and "al geboekt" in text
    assert Payment.objects.count() == 1


def test_money_out_is_linked_to_an_expense(tool, business):
    expense = _expense()
    line = _bank_line(-6050)
    _found, text, error = tool("book_bank_line", id=line.pk)
    assert error and "Kies een uitgave" in text
    _found, _text, error = tool("book_bank_line", id=line.pk, expense_id=expense.pk)
    assert not error
    line.refresh_from_db()
    assert line.expense == expense
    preview, _text, _error = tool("preview_bank_booking", id=line.pk)
    assert "uitgave blijft staan" in preview["after"]


def test_without_a_proposal_nothing_is_confirmed(tool, business):
    line = _bank_line(1234)
    _found, text, error = tool("confirm_bank_match", id=line.pk)
    assert error and "geen voorstel" in text


def test_skipping_and_restoring_a_line(tool, business):
    line = _bank_line(1234)
    _found, _text, error = tool("skip_bank_line", id=line.pk)
    assert not error
    line.refresh_from_db()
    assert line.state == BankTransaction.State.SKIPPED
    _found, text, error = tool("skip_bank_line", id=line.pk)
    assert error
    _found, _text, error = tool("restore_bank_line", id=line.pk)
    assert not error
    line.refresh_from_db()
    assert line.state == BankTransaction.State.OPEN
    _found, text, error = tool("restore_bank_line", id=line.pk)
    assert error and "niet overgeslagen" in text
