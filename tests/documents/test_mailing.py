# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Mailing an issued invoice, credit note or sent quote (SPEC.md M10).

Django's test runner swaps in the locmem mail backend: every "sent" mail
lands in mail.outbox, nothing leaves the machine."""

import datetime
import hashlib
import smtplib

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.base import ContentFile
from django.forms.models import model_to_dict
from django.urls import reverse

from huismus.business import smtp
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.detail import timeline_events
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, EmailLog, ImmutableDocumentError
from huismus.documents.quoting import send_quote

pytestmark = pytest.mark.django_db

PASSWORD = "test-app-password-not-real"


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


@pytest.fixture(autouse=True)
def business_settings(settings):
    smtp.set_password(PASSWORD)
    business = Settings.load()
    business.business_name = "Voorbeeld BV"
    business.address_line1 = "Hoofdstraat 1"
    business.postal_code = "1234 AB"
    business.city = "Amsterdam"
    business.kvk_number = "12345678"
    business.iban = "NL91ABNA0417164300"
    business.email = "info@example.invalid"
    business.smtp_provider = "gmail"
    business.smtp_host = "smtp.gmail.com"
    business.smtp_port = 587
    business.smtp_security = "starttls"
    business.smtp_username = "voorbeeld@example.invalid"
    business.save()
    return business


def _contact(**fields):
    return Contact.objects.create(
        company_name="Uitgeverij Kiezel",
        first_name="Sanne",
        email="sanne@example.invalid",
        **fields,
    )


def _draft(kind="invoice", language="nl", contact=None, **fields):
    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=contact or _contact(),
        language=language,
        **{
            "issue_date": datetime.date(2026, 3, 1),
            "due_date": datetime.date(2026, 3, 15),
            **fields,
        },
    )
    DocumentLine.objects.create(
        document=document, position=0, description="Uren", quantity="10", unit_price_cents=8500
    )
    return document


def _invoice(**fields):
    return issue(_draft(**fields))


def _quote(**fields):
    return send_quote(_draft(kind="quote", **fields))


def _mail_url(document):
    namespace = "quotes" if document.kind == "quote" else "documents"
    return reverse(f"{namespace}:mail", args=[document.pk])


def _post(client, document, **data):
    fields = {
        "to": "sanne@example.invalid",
        "subject": "Factuur",
        "body": "Zie bijlage.",
        **data,
    }
    return client.post(_mail_url(document), fields)


def _as_stored(document):
    """Everything about a document and its lines, as in the database."""
    document = Document.objects.get(pk=document.pk)
    lines = [model_to_dict(line) for line in document.lines.all()]
    return model_to_dict(document), document.updated_at, lines


# --- The mail itself ---


def test_mailing_an_issued_invoice_sends_one_mail_with_its_pdf(client_in):
    invoice = _invoice()

    response = _post(client_in, invoice, subject="Factuur 1", body="Hallo Sanne")

    assert response.status_code == 302
    assert response.url == reverse("documents:edit", args=[invoice.pk])
    [message] = mail.outbox
    assert message.to == ["sanne@example.invalid"]
    assert (message.subject, message.body) == ("Factuur 1", "Hallo Sanne")
    assert message.from_email == "info@example.invalid"
    assert message.bcc == []
    [(name, content, mimetype)] = message.attachments
    assert name == f"{invoice.number}.pdf"
    assert mimetype == "application/pdf"
    assert content.startswith(b"%PDF")


def test_a_credit_note_and_a_sent_quote_can_be_mailed_too(client_in):
    invoice = _invoice()
    credit_note = issue(_draft(kind="credit_note", related_document=invoice))
    quote = _quote()

    _post(client_in, credit_note)
    response = _post(client_in, quote)

    assert response.url == reverse("quotes:edit", args=[quote.pk])
    assert [m.attachments[0][0] for m in mail.outbox] == [
        f"{credit_note.number}.pdf",
        f"{quote.number}.pdf",
    ]


def test_an_accepted_quote_can_still_be_mailed(client_in):
    quote = _quote()
    quote.status = "accepted"
    quote.save()

    _post(client_in, quote)

    assert len(mail.outbox) == 1


def test_an_imported_invoice_goes_out_with_its_original_pdf(client_in):
    # SPEC.md section 7: the original PDF is the legal record.
    invoice = _invoice()
    Attachment.objects.create(
        document=invoice,
        kind="original_pdf",
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
    )

    _post(client_in, invoice)

    [(name, content, _mimetype)] = mail.outbox[0].attachments
    assert (name, content) == (f"{invoice.number}.pdf", b"%PDF-1.4 het origineel")


def test_an_imported_invoice_edited_in_huismus_goes_out_as_it_is_now(client_in):
    # After "Toch bewerken" the original no longer matches the invoice; the
    # detail page then offers the PDF from the snapshots too.
    from huismus.documents.reopening import reopen

    invoice = _invoice()
    Attachment.objects.create(
        document=invoice,
        kind="original_pdf",
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
    )
    invoice = issue(reopen(invoice))

    _post(client_in, invoice)

    [(name, content, _mimetype)] = mail.outbox[0].attachments
    assert name == f"{invoice.number}.pdf"
    assert content.startswith(b"%PDF") and b"het origineel" not in content


def test_bcc_to_myself_goes_to_the_sender(client_in):
    _post(client_in, _invoice(), bcc_self="on")

    assert mail.outbox[0].bcc == ["info@example.invalid"]


def test_the_sender_can_differ_from_the_business_address(client_in, business_settings):
    business_settings.smtp_from_email = "facturen@example.invalid"
    business_settings.save()

    _post(client_in, _invoice(), bcc_self="on")

    assert mail.outbox[0].from_email == "facturen@example.invalid"
    assert mail.outbox[0].bcc == ["facturen@example.invalid"]


def test_several_recipients_separated_by_commas(client_in):
    _post(client_in, _invoice(), to="sanne@example.invalid, boekhouding@example.invalid")

    assert mail.outbox[0].to == ["sanne@example.invalid", "boekhouding@example.invalid"]


@pytest.mark.parametrize("to", ["", "geen-adres", "sanne@example.invalid, ook geen"])
def test_an_invalid_recipient_sends_nothing_and_logs_nothing(client_in, to):
    response = _post(client_in, _invoice(), to=to)

    assert response.status_code == 200
    assert mail.outbox == []
    assert EmailLog.objects.count() == 0


# --- What the form starts with ---


def test_the_form_starts_with_the_contacts_current_address(client_in):
    invoice = _invoice()
    invoice.contact.email = "nieuw@example.invalid"
    invoice.contact.save()

    response = client_in.get(_mail_url(invoice))

    assert response.context["form"].initial["to"] == "nieuw@example.invalid"


def test_without_a_contact_the_form_starts_with_the_address_on_the_document():
    from huismus.documents.mailing import default_recipients

    invoice = _invoice()
    invoice.contact = None  # as for an invoice whose contact is gone; not saved

    assert default_recipients(invoice) == "sanne@example.invalid"


def test_the_default_text_is_dutch_for_a_dutch_invoice(client_in):
    invoice = _invoice(language="nl")

    initial = client_in.get(_mail_url(invoice)).context["form"].initial

    assert initial["subject"] == f"Factuur {invoice.number} van Voorbeeld BV"
    assert initial["body"].startswith("Beste Sanne,")
    assert f"factuur {invoice.number}" in initial["body"]
    assert "€ 850,00" in initial["body"]
    assert "15 maart 2026" in initial["body"]
    assert initial["body"].rstrip().endswith("Voorbeeld BV")


def test_the_default_text_is_english_for_an_english_invoice(client_in):
    invoice = _invoice(language="en")

    initial = client_in.get(_mail_url(invoice)).context["form"].initial

    assert initial["subject"] == f"Invoice {invoice.number} from Voorbeeld BV"
    assert initial["body"].startswith("Dear Sanne,")
    assert "15 March 2026" in initial["body"]


def test_the_default_text_names_the_kind_of_document(client_in):
    invoice = _invoice()
    credit_note = issue(_draft(kind="credit_note", related_document=invoice))
    quote = _quote(expiry_date=datetime.date(2026, 4, 1))

    credit_subject = client_in.get(_mail_url(credit_note)).context["form"].initial["subject"]
    quote_initial = client_in.get(_mail_url(quote)).context["form"].initial

    assert credit_subject == f"Creditnota {credit_note.number} van Voorbeeld BV"
    assert quote_initial["subject"] == f"Offerte {quote.number} van Voorbeeld BV"
    assert "1 april 2026" in quote_initial["body"]


def test_a_quote_without_an_end_date_leaves_out_the_line_about_it(client_in):
    quote = _quote(expiry_date=None)

    body = client_in.get(_mail_url(quote)).context["form"].initial["body"]

    assert "geldig tot" not in body
    assert "{geldig_tot}" not in body


# --- Mail texts from the settings ---


def test_the_mail_text_from_the_settings_is_filled_in(client_in, business_settings):
    business_settings.mail_invoice_subject_nl = "Rekening {nummer}"
    business_settings.mail_invoice_body_nl = (
        "Hoi {naam},\n\n{bedrag} voor {vervaldatum}, graag.\n\nGroet,\n{bedrijf}"
    )
    business_settings.save()
    invoice = _invoice(language="nl")

    initial = client_in.get(_mail_url(invoice)).context["form"].initial

    assert initial["subject"] == f"Rekening {invoice.number}"
    assert initial["body"] == (
        "Hoi Sanne,\n\n€ 850,00 voor 15 maart 2026, graag.\n\nGroet,\nVoorbeeld BV"
    )


def test_an_english_document_gets_the_english_mail_text(client_in, business_settings):
    business_settings.mail_invoice_subject_nl = "Rekening {nummer}"
    business_settings.mail_invoice_subject_en = "Bill {nummer}"
    business_settings.save()
    invoice = _invoice(language="en")

    subject = client_in.get(_mail_url(invoice)).context["form"].initial["subject"]

    assert subject == f"Bill {invoice.number}"


def test_each_kind_of_document_has_its_own_mail_text(client_in, business_settings):
    business_settings.mail_invoice_subject_nl = "Factuur!"
    business_settings.mail_credit_note_subject_nl = "Creditnota!"
    business_settings.mail_quote_subject_nl = "Offerte! Geldig tot {geldig_tot}"
    business_settings.save()
    invoice = _invoice()
    credit_note = issue(_draft(kind="credit_note", related_document=invoice))
    quote = _quote(expiry_date=datetime.date(2026, 4, 1))

    def subject(document):
        return client_in.get(_mail_url(document)).context["form"].initial["subject"]

    assert subject(invoice) == "Factuur!"
    assert subject(credit_note) == "Creditnota!"
    assert subject(quote) == "Offerte! Geldig tot 1 april 2026"


def test_an_empty_mail_text_in_the_settings_means_the_standard_text(client_in, business_settings):
    business_settings.mail_invoice_subject_nl = ""
    business_settings.mail_invoice_body_nl = ""
    business_settings.save()
    invoice = _invoice()

    initial = client_in.get(_mail_url(invoice)).context["form"].initial

    assert initial["subject"] == f"Factuur {invoice.number} van Voorbeeld BV"
    assert initial["body"].startswith("Beste Sanne,")


def test_the_mail_text_is_a_start_and_can_still_be_changed_per_mail(client_in, business_settings):
    business_settings.mail_invoice_subject_nl = "Rekening {nummer}"
    business_settings.save()
    invoice = _invoice()

    _post(client_in, invoice, subject="Iets anders")

    [message] = mail.outbox
    assert message.subject == "Iets anders"


# --- What can be mailed, and by whom ---


@pytest.mark.parametrize("kind", ["invoice", "credit_note", "quote"])
def test_a_draft_cannot_be_mailed(client_in, kind):
    draft = _draft(kind=kind)

    assert client_in.get(_mail_url(draft)).status_code == 404
    assert _post(client_in, draft).status_code == 404
    assert mail.outbox == []


def test_the_mail_page_needs_a_login(client):
    invoice = _invoice()

    response = client.get(_mail_url(invoice))

    assert response.status_code == 302
    assert reverse("login") in response.url


def test_without_a_password_nothing_is_sent_and_the_page_says_how(client_in, settings):
    smtp.set_password("")
    invoice = _invoice()

    page = client_in.get(_mail_url(invoice))
    _post(client_in, invoice)

    assert page.context["mail_configured"] is False
    assert reverse("business:topic", args=["mailen"]) in page.content.decode()
    assert mail.outbox == []
    assert EmailLog.objects.count() == 0


def test_without_a_provider_nothing_is_sent(client_in, business_settings):
    business_settings.smtp_provider = ""
    business_settings.save()

    _post(client_in, _invoice())

    assert mail.outbox == []


# --- The log ---


def test_every_sent_mail_is_logged(client_in):
    invoice = _invoice()

    _post(client_in, invoice, to="a@example.invalid, b@example.invalid", bcc_self="on")

    log = EmailLog.objects.get()
    attachment = mail.outbox[0].attachments[0]
    assert log.document == invoice
    assert log.succeeded is True
    assert log.error == ""
    assert (log.to, log.bcc) == ("a@example.invalid, b@example.invalid", "info@example.invalid")
    assert (log.subject, log.body) == ("Factuur", "Zie bijlage.")
    assert log.attachment_name == f"{invoice.number}.pdf"
    assert log.attachment_sha256 == hashlib.sha256(attachment[1]).hexdigest()


def test_a_failed_send_is_logged_and_shown_without_the_password(client_in, monkeypatch):
    def refuse(self, messages):
        raise smtplib.SMTPAuthenticationError(535, f"bad credentials {PASSWORD}".encode())

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", refuse)
    invoice = _invoice()

    response = _post(client_in, invoice)

    log = EmailLog.objects.get()
    assert log.succeeded is False
    assert "535" in log.error
    assert PASSWORD not in log.error
    assert response.status_code == 200
    page = response.content.decode()
    assert "535" in page
    assert "De mailserver weigert je gebruikersnaam of wachtwoord." in page
    assert PASSWORD not in page


def test_a_missing_original_pdf_is_logged_as_a_failure_and_sends_nothing(client_in):
    # data/ restored without the attachments, say: no error page, a log row.
    invoice = _invoice()
    original = Attachment.objects.create(
        document=invoice,
        kind="original_pdf",
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
    )
    original.file.storage.delete(original.file.name)

    response = _post(client_in, invoice)

    assert response.status_code == 200
    assert mail.outbox == []
    log = EmailLog.objects.get()
    assert log.succeeded is False
    assert log.error
    assert log.attachment_sha256 == ""


def test_a_server_that_cannot_be_reached_is_logged_as_a_failure(client_in, monkeypatch):
    def unreachable(self, messages):
        raise TimeoutError("timed out")

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", unreachable)

    _post(client_in, _invoice())

    assert EmailLog.objects.get().succeeded is False


def test_the_log_is_append_only():
    invoice = _invoice()
    log = EmailLog.objects.create(
        document=invoice,
        to="sanne@example.invalid",
        subject="Factuur",
        body="Zie bijlage.",
        attachment_name="x.pdf",
        attachment_sha256="0" * 64,
        succeeded=True,
    )

    log.subject = "Anders"
    with pytest.raises(ImmutableDocumentError):
        log.save()
    with pytest.raises(ImmutableDocumentError):
        log.delete()
    assert EmailLog.objects.get().subject == "Factuur"


def test_the_database_refuses_to_change_or_remove_a_log_too():
    # The triggers of migration 0009, for paths that skip EmailLog.save().
    from django.db import DatabaseError, transaction

    log = _log(_invoice())

    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        EmailLog.objects.filter(pk=log.pk).update(subject="Anders")
    with pytest.raises(DatabaseError, match="immutable"), transaction.atomic():
        EmailLog.objects.filter(pk=log.pk).delete()
    assert EmailLog.objects.get().subject == "Factuur"


def test_every_status_with_a_pdf_can_be_mailed():
    # The mail button follows the PDF: both lists must name the same statuses.
    from huismus.documents.mailing import MAILABLE_STATUSES
    from huismus.documents.views import PDF_STATUSES

    assert {s for statuses in MAILABLE_STATUSES.values() for s in statuses} == set(PDF_STATUSES)


# --- Mailing changes nothing about the document (invariants 1 and 4) ---


@pytest.mark.parametrize("kind", ["invoice", "credit_note", "quote"])
def test_mailing_leaves_the_document_as_it_was(client_in, kind):
    if kind == "quote":
        document = _quote()
    elif kind == "credit_note":
        document = issue(_draft(kind="credit_note", related_document=_invoice()))
    else:
        document = _invoice()
    before = _as_stored(document)

    _post(client_in, document, bcc_self="on")

    assert _as_stored(document) == before


def test_a_failed_send_leaves_the_document_as_it_was_too(client_in, monkeypatch):
    def refuse(self, messages):
        raise smtplib.SMTPException("nee")

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", refuse)
    quote = _quote()
    before = _as_stored(quote)

    _post(client_in, quote)

    assert _as_stored(quote) == before


# --- On the timeline ---


def _log(document, succeeded=True):
    return EmailLog.objects.create(
        document=document,
        to="sanne@example.invalid",
        subject="Factuur",
        body="",
        attachment_name="x.pdf",
        attachment_sha256="0" * 64,
        succeeded=succeeded,
        error="" if succeeded else "SMTPAuthenticationError: (535, b'bad credentials')",
    )


def test_mails_are_on_the_invoice_timeline_after_issuing():
    invoice = _invoice(issue_date=None)
    sent = _log(invoice)
    failed = _log(invoice, succeeded=False)

    events = timeline_events(invoice)

    assert [event["kind"] for event in events] == ["created", "issued", "email", "email"]
    assert [event["email"] for event in events[2:]] == [sent, failed]


def test_a_credit_note_and_a_quote_have_a_timeline_with_their_mails():
    credit_note = issue(_draft(kind="credit_note", related_document=_invoice(), issue_date=None))
    quote = _quote(issue_date=None)
    _log(credit_note)
    _log(quote)

    assert [e["kind"] for e in timeline_events(credit_note)] == ["created", "issued", "email"]
    assert [e["kind"] for e in timeline_events(quote)] == ["created", "sent", "email"]


def test_the_pages_show_the_mails_on_the_timeline(client_in):
    invoice = _invoice()
    quote = _quote()
    _log(invoice, succeeded=False)
    _log(quote)

    invoice_page = client_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()
    quote_page = client_in.get(reverse("quotes:edit", args=[quote.pk])).content.decode()

    assert "Mailen mislukt" in invoice_page
    assert "De mailserver weigert je gebruikersnaam of wachtwoord." in invoice_page
    assert "Gemaild naar sanne@example.invalid" in quote_page


def test_the_mail_button_is_on_every_mailable_page_and_not_on_drafts(client_in):
    invoice = _invoice()
    quote = _quote()
    draft = _draft()

    for document, page in [
        (invoice, reverse("documents:edit", args=[invoice.pk])),
        (quote, reverse("quotes:edit", args=[quote.pk])),
    ]:
        assert _mail_url(document) in client_in.get(page).content.decode()
    draft_page = client_in.get(reverse("documents:edit", args=[draft.pk])).content.decode()
    assert "/mailen/" not in draft_page


def test_a_quote_goes_to_the_contact_s_address_for_quotes():
    # Moneybird's "send_estimates_to_email": quotes to someone else.
    from huismus.documents.mailing import default_recipients

    contact = _contact(quote_email="inkoop@example.invalid")

    assert default_recipients(_quote(contact=contact)) == "inkoop@example.invalid"
    assert default_recipients(_invoice(contact=contact)) == "sanne@example.invalid"


def test_the_mail_page_says_when_the_customer_wants_post(client_in):
    invoice = _invoice(contact=_contact(delivery_method="post"))

    response = client_in.get(_mail_url(invoice))

    assert "per post" in response.content.decode()
