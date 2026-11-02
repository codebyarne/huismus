# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _draft_invoice_with_contact():
    return Document.objects.create(
        kind="invoice", status="draft", contact=Contact.objects.create(company_name="Klant BV")
    )


def _configure_settings():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return settings


def _line_formset_data(**lines):
    data = {
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, fields in enumerate(lines.values()):
        for key, value in fields.items():
            data[f"lines-{index}-{key}"] = value
    return data


def _document_form_data(**overrides):
    data = {
        "contact": "",
        "issue_date": "",
        "due_date": "",
        "delivery_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
    }
    data.update(overrides)
    return data


def test_list_requires_login(client):
    response = client.get(reverse("documents:list"))
    assert response.status_code == 302


def test_opening_a_new_invoice_stores_nothing(client):
    # M8: "Nieuwe factuur" used to create an empty draft on every click.
    _login(client)
    response = client.get(reverse("documents:create"))
    assert response.status_code == 200
    assert Document.objects.count() == 0


def test_new_invoice_starts_with_today_and_the_settings_defaults(client):
    _login(client)
    settings = _configure_settings()
    settings.default_footer_text = "Graag binnen de termijn betalen."
    settings.default_language = "en"
    settings.save()

    form = client.get(reverse("documents:create")).context["form"]

    assert form.initial["issue_date"] == timezone.localdate()
    assert form.initial["footer_text"] == "Graag binnen de termijn betalen."
    assert form.initial["language"] == "en"


def test_saving_a_new_invoice_creates_the_draft_and_redirects_to_edit(client):
    _login(client)
    contact = Contact.objects.create(company_name="Klant BV")
    data = {
        **_document_form_data(contact=contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "2",
                "unit_price_cents": "50.00",
                "tax_rate_bp": "0",
            }
        ),
    }

    response = client.post(reverse("documents:create"), data)

    document = Document.objects.get()
    assert (document.kind, document.status, document.total_cents) == ("invoice", "draft", 10000)
    assert response.url == reverse("documents:edit", kwargs={"pk": document.pk})


def test_issue_from_the_dialog_saves_the_edits_first(client):
    _login(client)
    _configure_settings()
    draft = _draft_invoice_with_contact()
    data = {
        **_document_form_data(contact=draft.contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "1",
                "unit_price_cents": "75.00",
                "tax_rate_bp": "0",
            }
        ),
        "actie": "uitgeven",
    }

    client.post(reverse("documents:edit", args=[draft.pk]), data)

    draft.refresh_from_db()
    assert draft.status == "issued"
    assert draft.total_cents == 7500
    assert draft.number


def test_preview_returns_server_computed_totals_and_saves_nothing(client):
    _login(client)
    draft = _draft_invoice_with_contact()
    data = {
        **_document_form_data(contact=draft.contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "2,5",
                "unit_price_cents": "10.00",
                "tax_rate_bp": "0",
            }
        ),
    }

    response = client.post(reverse("documents:preview", args=[draft.pk]), data)

    html = response.content.decode()
    assert 'id="totalen"' in html and 'hx-swap-oob="true"' in html
    assert "25,00" in html
    assert draft.lines.count() == 0


def test_edit_get_shows_the_draft_form(client):
    _login(client)
    document = Document.objects.create(kind="invoice", status="draft")
    response = client.get(reverse("documents:edit", kwargs={"pk": document.pk}))
    assert response.status_code == 200
    assert b"lines-TOTAL_FORMS" in response.content


def test_edit_post_saves_document_fields_and_a_line(client):
    _login(client)
    document = Document.objects.create(kind="invoice", status="draft")

    data = _document_form_data(notes="Testnotitie")
    data.update(
        _line_formset_data(
            one={
                "description": "Consult",
                "quantity": "2",
                "unit": "uur",
                "unit_price_cents": "50.00",
                "tax_rate_bp": "2100",
            }
        )
    )

    response = client.post(reverse("documents:edit", kwargs={"pk": document.pk}), data=data)

    assert response.status_code == 302
    document.refresh_from_db()
    assert document.notes == "Testnotitie"
    line = DocumentLine.objects.get(document=document)
    assert line.description == "Consult"
    assert line.unit_price_cents == 5000
    assert line.position == 0


def test_edit_post_skips_an_empty_extra_line_form(client):
    _login(client)
    document = Document.objects.create(kind="invoice", status="draft")

    data = _document_form_data()
    data.update(
        _line_formset_data(
            one={
                "description": "",
                "quantity": "",
                "unit": "",
                "unit_price_cents": "",
                "tax_rate_bp": "0",
            }
        )
    )

    response = client.post(reverse("documents:edit", kwargs={"pk": document.pk}), data=data)

    assert response.status_code == 302
    assert DocumentLine.objects.filter(document=document).count() == 0


def test_issue_action_issues_a_valid_draft(client):
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )

    response = client.post(reverse("documents:issue", kwargs={"pk": document.pk}))

    assert response.status_code == 302
    document.refresh_from_db()
    assert document.status == "issued"
    assert document.number
    # The message names the document, not just "Document uitgegeven."
    messages = [str(m) for m in response.wsgi_request._messages]
    assert f"Factuur {document.number} is uitgegeven." in messages


def test_issue_action_on_an_empty_draft_shows_an_error_and_stays_draft(client):
    _login(client)
    _configure_settings()
    document = Document.objects.create(kind="invoice", status="draft")

    response = client.post(reverse("documents:issue", kwargs={"pk": document.pk}), follow=True)

    document.refresh_from_db()
    assert document.status == "draft"
    messages = list(response.context["messages"])
    assert any("Voeg eerst een regel toe" in str(m) for m in messages)


def test_issue_action_404s_for_a_quote_pk(client):
    # document_issue filters by kind, matching document_edit — otherwise a
    # quote's pk redirects to document_edit, which 404s there instead
    # (issue() itself already rejects a quote's kind either way).
    _login(client)
    quote = Document.objects.create(kind="quote", status="draft")
    response = client.post(reverse("documents:issue", kwargs={"pk": quote.pk}))
    assert response.status_code == 404


def test_edit_on_an_issued_document_shows_the_detail_view_not_the_form(client):
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))

    response = client.get(reverse("documents:edit", kwargs={"pk": document.pk}))

    assert response.status_code == 200
    assert b"lines-TOTAL_FORMS" not in response.content
    document.refresh_from_db()
    assert document.number.encode() in response.content


def test_issued_document_without_an_attachment_shows_only_the_generated_pdf_link(client):
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))

    response = client.get(reverse("documents:edit", kwargs={"pk": document.pk}))

    html = response.content.decode()
    assert reverse("documents:pdf_page", kwargs={"pk": document.pk}) in html
    assert "Origineel uit Moneybird" not in html


def test_an_imported_invoices_original_pdf_is_shown_as_the_primary_document(client):
    # SPEC.md section 7: "the UI shows [original_pdf] as the primary
    # document for imported invoices. A re-rendered PDF is offered
    # separately and labelled as such."
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))
    document.refresh_from_db()
    Attachment.objects.create(
        document=document,
        file=ContentFile(b"%PDF-1.4 fake", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )

    response = client.get(reverse("documents:edit", kwargs={"pk": document.pk}))
    content = response.content.decode()

    assert "Origineel uit Moneybird" in content
    assert "Opnieuw gegenereerd" in content
    # Primary: the original comes first, the re-rendered one after it.
    assert content.index("Origineel uit Moneybird") < content.index("Opnieuw gegenereerd")
    # The PDF button opens the PDF page, which starts on the original
    # (tests/documents/test_pdf_page.py); the original's own link opens it
    # with the original chosen.
    page_url = reverse("documents:pdf_page", kwargs={"pk": document.pk})
    assert f'href="{page_url}"' in content
    assert f'href="{page_url}?versie=origineel"' in content


def test_the_original_pdf_downloads_named_after_the_number_whatever_its_stored_name(client):
    # Stored as "origineel.pdf" here; in data/ a second file of the same
    # name is stored as "430033_kfWEXfH.pdf". Neither reaches the customer.
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))
    document.refresh_from_db()
    Attachment.objects.create(
        document=document,
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )

    response = client.get(reverse("documents:original_pdf", kwargs={"pk": document.pk}))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"] == f'attachment; filename="{document.number}.pdf"'
    assert b"".join(response.streaming_content) == b"%PDF-1.4 het origineel"


def test_a_document_without_an_original_has_no_original_download(client):
    _login(client)
    document = _draft_invoice_with_contact()

    response = client.get(reverse("documents:original_pdf", kwargs={"pk": document.pk}))

    assert response.status_code == 404


def test_payment_create_records_a_payment(client):
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))
    document.refresh_from_db()

    response = client.post(
        reverse("documents:payment_create", kwargs={"pk": document.pk}),
        data={
            "paid_on": "2026-01-01",
            "amount_cents": "100.00",
            "method": "Overboeking",
            "note": "",
        },
    )

    assert response.status_code == 302
    payment = Payment.objects.get(document=document)
    assert payment.amount_cents == 10000


def test_payment_create_with_invalid_data_shows_an_error_and_saves_nothing(client):
    _login(client)
    _configure_settings()
    document = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": document.pk}))
    document.refresh_from_db()

    response = client.post(
        reverse("documents:payment_create", kwargs={"pk": document.pk}),
        data={"paid_on": "", "amount_cents": "", "method": "Overboeking", "note": ""},
        follow=True,
    )

    assert not Payment.objects.filter(document=document).exists()
    messages = list(response.context["messages"])
    assert any("De betaling is niet opgeslagen" in str(m) for m in messages)


def test_credit_note_create_makes_a_draft_linked_to_the_invoice(client):
    _login(client)
    _configure_settings()
    invoice = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=invoice, description="Consult", quantity="1", unit_price_cents=10000
    )
    client.post(reverse("documents:issue", kwargs={"pk": invoice.pk}))
    invoice.refresh_from_db()

    response = client.post(reverse("documents:credit_note_create", kwargs={"pk": invoice.pk}))

    assert response.status_code == 302
    credit_note = Document.objects.get(kind="credit_note")
    assert credit_note.related_document_id == invoice.pk
    assert response.url == reverse("documents:edit", kwargs={"pk": credit_note.pk})


# --- Deleting a draft ---


def _draft_with_line(kind="invoice", **fields):
    document = Document.objects.create(
        kind=kind, status="draft", contact=Contact.objects.create(company_name="Klant BV"), **fields
    )
    DocumentLine.objects.create(
        document=document, description="Uren", quantity="1", unit_price_cents=1000
    )
    return document


def test_a_draft_invoice_can_be_deleted_with_its_lines(client):
    _login(client)
    draft = _draft_with_line()

    response = client.post(reverse("documents:delete", args=[draft.pk]))

    assert response.status_code == 302
    assert response.url == reverse("documents:list")
    assert not Document.objects.filter(pk=draft.pk).exists()
    assert not DocumentLine.objects.exists()


def test_a_draft_quote_can_be_deleted(client):
    _login(client)
    draft = _draft_with_line(kind="quote")

    response = client.post(reverse("quotes:delete", args=[draft.pk]))

    assert response.url == reverse("quotes:list")
    assert not Document.objects.filter(pk=draft.pk).exists()


def test_a_draft_credit_note_goes_back_to_its_invoice(client):
    _login(client)
    invoice = _draft_with_line()
    Document.objects.filter(pk=invoice.pk).update(status="issued", number="2026-0001")
    credit_note = _draft_with_line(kind="credit_note", related_document=invoice)

    response = client.post(reverse("documents:delete", args=[credit_note.pk]))

    assert response.url == reverse("documents:edit", args=[invoice.pk])
    assert not Document.objects.filter(pk=credit_note.pk).exists()


def test_deleting_needs_a_post(client):
    _login(client)
    draft = _draft_with_line()

    response = client.get(reverse("documents:delete", args=[draft.pk]))

    assert response.status_code == 405
    assert Document.objects.filter(pk=draft.pk).exists()


def test_an_issued_invoice_cannot_be_deleted(client):
    _login(client)
    invoice = _draft_with_line()
    Document.objects.filter(pk=invoice.pk).update(status="issued", number="2026-0001")

    response = client.post(reverse("documents:delete", args=[invoice.pk]))

    assert response.status_code == 404
    assert Document.objects.filter(pk=invoice.pk).exists()


def test_a_sent_quote_cannot_be_deleted(client):
    _login(client)
    quote = _draft_with_line(kind="quote")
    Document.objects.filter(pk=quote.pk).update(status="sent", number="OFF-0001")

    response = client.post(reverse("quotes:delete", args=[quote.pk]))

    assert response.status_code == 404
    assert Document.objects.filter(pk=quote.pk).exists()


def test_deleting_a_draft_leaves_the_number_sequence_alone(client):
    from huismus.documents.models import NumberSequence

    _login(client)
    draft = _draft_with_line()

    client.post(reverse("documents:delete", args=[draft.pk]))

    # A draft has no number: nothing was allocated, so no gap can appear.
    assert not NumberSequence.objects.exists()


# --- PDF preview from the editor ---


def _preview_post(client, url, contact, **line):
    from io import BytesIO

    from pypdf import PdfReader

    data = {
        **_document_form_data(contact=contact.pk if contact else ""),
        **_line_formset_data(
            one={
                "description": "Webdesign",
                "quantity": "3",
                "unit_price_cents": "100.00",
                "tax_rate_bp": "0",
                **line,
            }
        ),
    }
    response = client.post(url, data)
    text = ""
    if response.status_code == 200 and response["Content-Type"] == "application/pdf":
        text = "\n".join(page.extract_text() for page in PdfReader(BytesIO(response.content)).pages)
    return response, text


def test_pdf_preview_of_an_unsaved_invoice_shows_the_typed_lines_and_saves_nothing(client):
    _login(client)
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV", city="Utrecht")

    response, text = _preview_post(client, reverse("documents:pdf_preview_new"), contact)

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert "Webdesign" in text
    assert "300,00" in text  # 3 × 100, from the one totals function
    assert "Klant BV" in text
    assert "VOORBEELD" in text.upper()
    assert Document.objects.count() == 0
    # A preview takes no number from the sequence (invariant 3).
    from huismus.documents.models import NumberSequence

    assert not NumberSequence.objects.exists()


def test_pdf_preview_may_sit_in_a_frame_on_huismus_only(client):
    # The installed app shows it in a dialog over the editor (app.js).
    _login(client)
    _configure_settings()

    response, _ = _preview_post(client, reverse("documents:pdf_preview_new"), None)

    assert response["X-Frame-Options"] == "SAMEORIGIN"


def test_pdf_preview_of_a_saved_draft_leaves_it_untouched(client):
    _login(client)
    _configure_settings()
    draft = _draft_with_line()
    before = (draft.status, draft.number, draft.total_cents)

    response, text = _preview_post(
        client, reverse("documents:pdf_preview", args=[draft.pk]), draft.contact
    )

    assert response.status_code == 200
    assert "Webdesign" in text  # the typed form, not the stored line "Uren"
    draft.refresh_from_db()
    assert (draft.status, draft.number, draft.total_cents) == before
    assert draft.lines.get().description == "Uren"


def test_pdf_preview_works_with_a_fixed_price_and_no_contact_yet(client):
    _login(client)
    _configure_settings()

    response, text = _preview_post(
        client, reverse("documents:pdf_preview_new"), None, quantity="", unit_price_cents="250.00"
    )

    assert response.status_code == 200
    assert "250,00" in text


def test_pdf_preview_of_a_quote(client):
    _login(client)
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV")

    response, text = _preview_post(client, reverse("quotes:pdf_preview_new"), contact)

    assert response.status_code == 200
    assert "Offerte" in text


def test_pdf_preview_is_post_only_and_needs_login(client):
    assert client.post(reverse("documents:pdf_preview_new")).status_code == 302
    _login(client)
    assert client.get(reverse("documents:pdf_preview_new")).status_code == 405


def test_pdf_preview_refuses_an_issued_invoice(client):
    _login(client)
    invoice = _draft_with_line()
    Document.objects.filter(pk=invoice.pk).update(status="issued", number="2026-0001")

    response = client.post(reverse("documents:pdf_preview", args=[invoice.pk]))

    assert response.status_code == 404


def test_pdf_preview_says_the_number_follows_instead_of_leaving_it_blank(client):
    _login(client)
    _configure_settings()
    contact = Contact.objects.create(company_name="Klant BV")

    _response, text = _preview_post(client, reverse("documents:pdf_preview_new"), contact)

    assert "[nummer volgt]" in text


def test_pdf_preview_refuses_a_sent_quote(client):
    # A sent quote has its own snapshots and PDF; a preview would show
    # today's settings instead of what the customer received.
    _login(client)
    quote = _draft_with_line(kind="quote")
    Document.objects.filter(pk=quote.pk).update(status="sent", number="OFF-0001")

    response = client.post(reverse("quotes:pdf_preview", args=[quote.pk]))

    assert response.status_code == 404


def _kor_limit_of_ten_thousand_euro():
    settings = _configure_settings()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.kor_limit_cents = 1_000_000
    settings.save()


def _draft_invoice_of(cents):
    draft = _draft_invoice_with_contact()
    DocumentLine.objects.create(
        document=draft, description="Werk", quantity="1", unit_price_cents=cents
    )
    return draft


def test_the_issue_dialog_says_when_this_invoice_goes_over_the_kor_limit(client):
    _login(client)
    _kor_limit_of_ten_thousand_euro()
    draft = _draft_invoice_of(1_200_000)

    page = client.get(reverse("documents:edit", args=[draft.pk])).content.decode()

    assert "boven je KOR-grens van" in page


def test_the_issue_dialog_says_nothing_about_the_kor_limit_far_below_it(client):
    _login(client)
    _kor_limit_of_ten_thousand_euro()
    draft = _draft_invoice_of(100_000)

    page = client.get(reverse("documents:edit", args=[draft.pk])).content.decode()

    assert "KOR-grens" not in page


@pytest.mark.parametrize(
    ("language", "fill_in", "number"),
    [
        ("nl", "Omschrijving: vul dit in.", "Aantal: vul een getal in, zoals 2 of 1,5."),
        ("en", "Description: fill this in.", "Quantity: enter a number, like 2 or 1.5."),
    ],
)
def test_a_line_with_errors_says_what_to_fill_in(client, language, fill_in, number):
    """Not Django's "Dit veld is verplicht." (huismus-intern/besluiten.md, 2026-11-01, "Teksten
    in Arnes stem, deel 2"): each line error says what to do, in both languages,
    with a small letter after the colon (deel 3)."""
    _login(client)
    document = _draft_invoice_with_contact()
    client.cookies["django_language"] = language
    data = _document_form_data(contact=str(document.contact.pk), language="nl")
    data.update(
        _line_formset_data(
            a={"description": "", "quantity": "1", "unit_price_cents": "10,00", "tax_rate_bp": "0"},
            b={
                "description": "Consult",
                "quantity": "abc",
                "unit_price_cents": "10,00",
                "tax_rate_bp": "0",
            },
        )
    )

    response = client.post(reverse("documents:edit", kwargs={"pk": document.pk}), data)

    content = response.content.decode()
    assert fill_in in content
    assert number in content
    assert not document.lines.exists()
