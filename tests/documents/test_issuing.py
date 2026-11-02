# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import base64
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

import pytest
from django.db import connections

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import IssueError, issue
from huismus.documents.models import Document, DocumentLine
from tests.support import clean_up_issued_documents_for_flush

pytestmark = pytest.mark.django_db


def _settings(**overrides):
    fields = {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "default_payment_terms_days": 14,
    }
    fields.update(overrides)
    settings = Settings.load()
    for key, value in fields.items():
        setattr(settings, key, value)
    settings.save()
    return settings


_UNSET = object()  # distinguishes "no contact passed" (auto-create one) from contact=None


def _draft_invoice(*, contact=_UNSET, kind="invoice", **overrides):
    if contact is _UNSET:
        contact = Contact.objects.create(company_name="Klant BV")
    fields = {"kind": kind, "status": "draft", "contact": contact}
    fields.update(overrides)
    return Document.objects.create(**fields)


def _line(document, **overrides):
    fields = {
        "document": document,
        "description": "Consult",
        "quantity": "2",
        "unit_price_cents": 10000,
        "tax_rate_bp": 0,
    }
    fields.update(overrides)
    return DocumentLine.objects.create(**fields)


def test_issue_sets_number_status_and_totals():
    _settings()
    document = _draft_invoice()
    _line(document, quantity="2", unit_price_cents=10000, tax_rate_bp=2100)

    issued = issue(document)

    assert issued.status == "issued"
    assert issued.number
    assert issued.subtotal_cents == 20000
    assert issued.tax_cents == 4200
    assert issued.total_cents == 24200
    assert issued.issue_date == date.today()


def test_default_settings_produce_a_year_prefixed_number_not_the_word_none():
    # Regression test: invoice_number_format defaults to "{year}-{seq:04d}"
    # and number_reset_yearly now defaults to True so they agree; with the
    # old False default this rendered the literal word "None" in every
    # invoice number on a fresh install.
    _settings()
    document = _draft_invoice()
    _line(document)

    issued = issue(document)

    assert issued.number == f"{date.today().year}-0001"


def test_issue_numbers_sequentially_using_the_invoice_format():
    # number_reset_yearly=False -> year is None throughout the format.
    _settings(invoice_number_format="{year}-{seq:04d}", number_reset_yearly=False)
    first_doc = _draft_invoice()
    _line(first_doc)
    first = issue(first_doc)

    second_doc = _draft_invoice()
    _line(second_doc)
    second = issue(second_doc)

    assert first.number == "None-0001"
    assert second.number == "None-0002"


def test_issue_requires_draft_status():
    document = _draft_invoice()
    _line(document)
    issue(document)

    with pytest.raises(IssueError):
        issue(document)


def test_issue_rejects_a_quote():
    _settings()
    document = _draft_invoice(kind="quote", status="draft")
    _line(document)
    with pytest.raises(IssueError):
        issue(document)


def test_issue_requires_at_least_one_line():
    _settings()
    document = _draft_invoice()
    with pytest.raises(IssueError):
        issue(document)


def test_issue_requires_kor_text_when_kor_enabled():
    _settings(kor_enabled=True, kor_text="")
    document = _draft_invoice()
    _line(document, tax_rate_bp=0)
    with pytest.raises(IssueError):
        issue(document)


def test_issue_rejects_nonzero_tax_when_kor_enabled():
    _settings(kor_enabled=True, kor_text="Vrijgesteld van btw i.v.m. KOR.")
    document = _draft_invoice()
    _line(document, tax_rate_bp=2100)
    with pytest.raises(IssueError):
        issue(document)


def test_issue_succeeds_with_kor_enabled_and_zero_tax():
    _settings(kor_enabled=True, kor_text="Vrijgesteld van btw i.v.m. KOR.")
    document = _draft_invoice()
    _line(document, tax_rate_bp=0)

    issued = issue(document)

    assert issued.kor_text_snapshot == "Vrijgesteld van btw i.v.m. KOR."
    assert issued.tax_cents == 0


def test_business_snapshot_is_copied_and_survives_later_settings_changes():
    _settings(business_name="Origineel BV")
    document = _draft_invoice()
    _line(document)
    issued = issue(document)
    assert issued.business_snapshot["business_name"] == "Origineel BV"

    _settings(business_name="Gewijzigd BV")

    issued.refresh_from_db()
    assert issued.business_snapshot["business_name"] == "Origineel BV"


def test_contact_snapshot_is_copied_and_survives_later_contact_changes():
    _settings()
    contact = Contact.objects.create(company_name="Klant BV", city="Utrecht")
    document = _draft_invoice(contact=contact)
    _line(document)
    issued = issue(document)
    assert issued.contact_snapshot["company_name"] == "Klant BV"

    contact.company_name = "Andere naam"
    contact.save()

    issued.refresh_from_db()
    assert issued.contact_snapshot["company_name"] == "Klant BV"


def test_issuing_without_a_contact_is_rejected():
    # docs/invoice-requirements.md: the customer's full name and address
    # are legally mandatory on an invoice. Without a contact there's
    # nothing to put there — see huismus/documents/issuing.py's comment.
    _settings()
    document = _draft_invoice(contact=None)
    _line(document)
    with pytest.raises(IssueError):
        issue(document)


def test_due_date_uses_contact_override_over_business_default():
    _settings(default_payment_terms_days=14)
    contact = Contact.objects.create(company_name="Klant BV", payment_terms_days=30)
    document = _draft_invoice(contact=contact)
    _line(document)

    issued = issue(document)

    assert issued.due_date == issued.issue_date + timedelta(days=30)


def test_due_date_falls_back_to_business_default_without_contact_override():
    _settings(default_payment_terms_days=14)
    contact = Contact.objects.create(company_name="Klant BV", payment_terms_days=None)
    document = _draft_invoice(contact=contact)
    _line(document)

    issued = issue(document)

    assert issued.due_date == issued.issue_date + timedelta(days=14)


def test_logo_bytes_are_embedded_in_the_business_snapshot():
    from django.core.files.uploadedfile import SimpleUploadedFile

    settings = _settings()
    png_bytes = b"\x89PNG\r\n\x1a\nfake-but-fine-for-this-test"
    settings.logo.save("logo.png", SimpleUploadedFile("logo.png", png_bytes), save=True)

    document = _draft_invoice()
    _line(document)
    issued = issue(document)

    assert issued.business_snapshot["logo_content_type"] == "image/png"
    assert base64.b64decode(issued.business_snapshot["logo_base64"]) == png_bytes


def test_line_totals_are_persisted_on_issue():
    _settings()
    document = _draft_invoice()
    line = _line(document, quantity="3", unit_price_cents=500, tax_rate_bp=0)

    issue(document)

    line.refresh_from_db()
    assert line.line_total_cents == 1500


# --- Credit notes (invariant 5) ------------------------------------------


def _issued_invoice(total_line_cents=10000):
    _settings()
    invoice = _draft_invoice()
    _line(invoice, quantity="1", unit_price_cents=total_line_cents, tax_rate_bp=0)
    return issue(invoice)


def test_credit_note_within_invoice_total_succeeds():
    invoice = _issued_invoice(10000)
    credit_note = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(credit_note, quantity="1", unit_price_cents=4000, tax_rate_bp=0)

    issued = issue(credit_note)

    assert issued.status == "issued"
    assert issued.total_cents == 4000


def test_credit_note_exceeding_invoice_total_is_rejected():
    invoice = _issued_invoice(10000)
    credit_note = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(credit_note, quantity="1", unit_price_cents=10001, tax_rate_bp=0)

    with pytest.raises(IssueError):
        issue(credit_note)


def test_credit_notes_cannot_cumulatively_exceed_invoice_total():
    invoice = _issued_invoice(10000)
    first = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(first, quantity="1", unit_price_cents=6000, tax_rate_bp=0)
    issue(first)

    second = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(second, quantity="1", unit_price_cents=5000, tax_rate_bp=0)

    with pytest.raises(IssueError):
        issue(second)


def test_credit_note_without_a_related_document_is_rejected():
    _settings()
    credit_note = _draft_invoice(kind="credit_note", related_document=None)
    _line(credit_note)
    with pytest.raises(IssueError):
        issue(credit_note)


def test_credit_note_against_a_draft_invoice_is_rejected():
    _settings()
    draft_invoice = _draft_invoice()
    _line(draft_invoice)
    credit_note = _draft_invoice(kind="credit_note", related_document=draft_invoice)
    _line(credit_note)
    with pytest.raises(IssueError):
        issue(credit_note)


@pytest.mark.django_db(transaction=True)
def test_concurrent_credit_notes_cannot_cumulatively_exceed_invoice_total():
    # Regression test for a real race found by review: the cumulative-
    # credit check originally ran on an unlocked SELECT *before*
    # transaction.atomic() opened, so two credit notes issued at the same
    # time could both read the same (too-low) already-credited total and
    # both pass, even though issuing both would exceed the invoice. Fixed
    # by moving the check to after allocate_number()'s UPDATE, which is
    # what actually holds SQLite's write lock for the rest of the
    # transaction — see huismus/documents/issuing.py. This needs
    # transaction=True and a real ThreadPoolExecutor for the same reason
    # tests/documents/test_numbering.py's concurrency test does: a plain
    # @pytest.mark.django_db test runs everything inside one rolled-back
    # savepoint and can't exercise a genuine cross-connection race.
    _settings()
    invoice = _draft_invoice()
    _line(invoice, quantity="1", unit_price_cents=10000, tax_rate_bp=0)
    issue(invoice)

    credit_note_a = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(credit_note_a, quantity="1", unit_price_cents=6000, tax_rate_bp=0)
    credit_note_b = _draft_invoice(kind="credit_note", related_document=invoice)
    _line(credit_note_b, quantity="1", unit_price_cents=6000, tax_rate_bp=0)

    def issue_one(document):
        try:
            issue(document)
            return "issued"
        except IssueError:
            return "rejected"
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(issue_one, [credit_note_a, credit_note_b]))

    assert sorted(results) == ["issued", "rejected"]
    total_issued_credits = sum(
        Document.objects.filter(
            kind="credit_note", status="issued", related_document=invoice
        ).values_list("total_cents", flat=True)
    )
    assert total_issued_credits <= 10000

    clean_up_issued_documents_for_flush()


def test_issue_puts_the_contact_s_customer_number_in_the_number():
    _settings(invoice_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    document = _draft_invoice(
        contact=Contact.objects.create(company_name="Klant BV", customer_number="58")
    )
    _line(document)

    assert issue(document).number == "580001"


def test_issue_hands_out_a_customer_number_when_the_contact_has_none():
    _settings(invoice_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    Contact.objects.create(company_name="Bestaande klant", customer_number="41")
    without = _draft_invoice(contact=Contact.objects.create(company_name="Zonder nummer"))
    _line(without)

    issued = issue(without)

    assert issued.number == "420001"
    without.contact.refresh_from_db()
    assert without.contact.customer_number == "42"
    # The snapshot has the number the invoice was issued with.
    assert issued.contact_snapshot["customer_number"] == "42"


def test_issue_refuses_a_number_that_already_exists_and_uses_no_number():
    # With {customer} two numbers can in theory coincide (customer 1 at
    # sequence 10012 and customer 11 at 0012 are both "110012"), and an
    # imported invoice may already hold a number. Never issue a duplicate.
    _settings(invoice_number_format="{customer}{seq:04d}", number_reset_yearly=False)
    contact = Contact.objects.create(company_name="Klant BV", customer_number="58")
    Document.objects.create(kind="invoice", status="issued", contact=contact, number="580001")
    document = _draft_invoice(contact=contact)
    _line(document)

    with pytest.raises(IssueError, match="580001"):
        issue(document)
    assert document.status == "draft"
