# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document, DocumentLine

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _draft_quote_with_contact():
    return Document.objects.create(
        kind="quote", status="draft", contact=Contact.objects.create(company_name="Klant BV")
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


def _quote_form_data(**overrides):
    data = {
        "contact": "",
        "issue_date": "",
        "due_date": "",
        "delivery_date": "",
        "expiry_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
    }
    data.update(overrides)
    return data


def test_list_requires_login(client):
    response = client.get(reverse("quotes:list"))
    assert response.status_code == 302


def test_opening_a_new_quote_stores_nothing(client):
    _login(client)
    assert client.get(reverse("quotes:create")).status_code == 200
    assert Document.objects.count() == 0


def test_saving_a_new_quote_creates_the_draft_and_redirects_to_edit(client):
    _login(client)
    contact = Contact.objects.create(company_name="Klant BV")
    data = {
        **_quote_form_data(contact=contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "1",
                "unit_price_cents": "50.00",
                "tax_rate_bp": "0",
            }
        ),
    }

    response = client.post(reverse("quotes:create"), data)

    quote = Document.objects.get()
    assert (quote.kind, quote.status, quote.total_cents) == ("quote", "draft", 5000)
    assert response.url == reverse("quotes:edit", kwargs={"pk": quote.pk})


def test_edit_get_shows_the_form_with_expiry_date_field(client):
    _login(client)
    quote = _draft_quote_with_contact()
    response = client.get(reverse("quotes:edit", kwargs={"pk": quote.pk}))
    assert response.status_code == 200
    assert b"expiry_date" in response.content


def test_edit_post_saves_quote_fields_and_a_line(client):
    _login(client)
    quote = _draft_quote_with_contact()

    data = _quote_form_data(expiry_date="2026-12-31")
    data.update(
        _line_formset_data(
            one={
                "description": "Website",
                "quantity": "1",
                "unit": "",
                "unit_price_cents": "500.00",
                "tax_rate_bp": "2100",
            }
        )
    )

    response = client.post(reverse("quotes:edit", kwargs={"pk": quote.pk}), data=data)

    assert response.status_code == 302
    quote.refresh_from_db()
    assert str(quote.expiry_date) == "2026-12-31"
    line = DocumentLine.objects.get(document=quote)
    assert line.description == "Website"
    assert line.line_total_cents == 50000
    assert quote.total_cents == 60500  # EUR500 at 21% = EUR605.00


def test_editing_a_sent_quotes_line_recomputes_its_stored_total(client):
    # Regression test: a sent quote stays editable (unlike an issued
    # invoice), and quote_list.html displays total_cents — editing a
    # line used to save the new line but never recompute the document's
    # stored total, leaving it silently wrong after a normal UI action.
    # Found by review, not caught by a test at the time (the only
    # existing line-edit test only touched a draft quote).
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000, tax_rate_bp=0
    )
    client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))
    quote.refresh_from_db()
    assert quote.total_cents == 50000

    data = _quote_form_data(expiry_date="")
    data.update(
        _line_formset_data(
            one={
                "description": "Website (uitgebreid)",
                "quantity": "1",
                "unit": "",
                "unit_price_cents": "800.00",
                "tax_rate_bp": "0",
            }
        )
    )
    line_id = quote.lines.get().pk
    data["lines-0-id"] = str(line_id)
    data["lines-INITIAL_FORMS"] = "1"

    client.post(reverse("quotes:edit", kwargs={"pk": quote.pk}), data=data)

    quote.refresh_from_db()
    assert quote.total_cents == 80000
    assert quote.lines.get().line_total_cents == 80000


def test_send_action_sends_a_valid_draft(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000
    )

    response = client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))

    assert response.status_code == 302
    quote.refresh_from_db()
    assert quote.status == "sent"
    assert quote.number


def test_send_action_on_an_empty_draft_shows_an_error(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()

    response = client.post(reverse("quotes:send", kwargs={"pk": quote.pk}), follow=True)

    quote.refresh_from_db()
    assert quote.status == "draft"
    messages = list(response.context["messages"])
    assert any("Voeg eerst een regel toe" in str(m) for m in messages)


def test_accept_action_transitions_a_sent_quote(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000
    )
    client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))

    response = client.post(reverse("quotes:accept", kwargs={"pk": quote.pk}))

    assert response.status_code == 302
    quote.refresh_from_db()
    assert quote.status == "accepted"


def test_decline_action_transitions_a_sent_quote(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000
    )
    client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))

    response = client.post(reverse("quotes:decline", kwargs={"pk": quote.pk}))

    assert response.status_code == 302
    quote.refresh_from_db()
    assert quote.status == "declined"


def test_expire_action_transitions_a_sent_quote(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000
    )
    client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))

    response = client.post(reverse("quotes:expire", kwargs={"pk": quote.pk}))

    assert response.status_code == 302
    quote.refresh_from_db()
    assert quote.status == "expired"


def test_accept_action_on_a_draft_quote_shows_an_error(client):
    _login(client)
    quote = _draft_quote_with_contact()

    response = client.post(reverse("quotes:accept", kwargs={"pk": quote.pk}), follow=True)

    quote.refresh_from_db()
    assert quote.status == "draft"
    messages = list(response.context["messages"])
    assert any("verzonden" in str(m).lower() for m in messages)


def test_convert_action_creates_a_draft_invoice_and_redirects_to_it(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Website", quantity="1", unit_price_cents=50000
    )
    client.post(reverse("quotes:send", kwargs={"pk": quote.pk}))

    response = client.post(reverse("quotes:convert", kwargs={"pk": quote.pk}))

    invoice = Document.objects.get(kind="invoice")
    assert response.status_code == 302
    assert response.url == reverse("documents:edit", kwargs={"pk": invoice.pk})
    assert invoice.related_document_id == quote.pk
    assert invoice.lines.count() == 1


# --- M8: send from the dialog, preview, PDF, list tabs ---


def test_send_from_the_dialog_saves_the_edits_first(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    data = {
        **_quote_form_data(contact=quote.contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "2",
                "unit_price_cents": "40.00",
                "tax_rate_bp": "0",
            }
        ),
        "actie": "verzenden",
    }

    client.post(reverse("quotes:edit", args=[quote.pk]), data)

    quote.refresh_from_db()
    assert quote.status == "sent"
    assert quote.number
    assert quote.total_cents == 8000


def test_quote_preview_returns_server_computed_totals(client):
    _login(client)
    quote = _draft_quote_with_contact()
    data = {
        **_quote_form_data(contact=quote.contact.pk),
        **_line_formset_data(
            one={
                "description": "Werk",
                "quantity": "3",
                "unit_price_cents": "10.00",
                "tax_rate_bp": "0",
            }
        ),
    }

    response = client.post(reverse("quotes:preview", args=[quote.pk]), data)

    assert "30,00" in response.content.decode()
    assert quote.lines.count() == 0


def test_a_sent_quote_has_a_pdf_but_a_draft_does_not(client):
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Werk", quantity="1", unit_price_cents=5000
    )

    assert client.get(reverse("documents:pdf", args=[quote.pk])).status_code == 404
    client.post(reverse("quotes:send", args=[quote.pk]))
    response = client.get(reverse("documents:pdf", args=[quote.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"


def test_quote_list_tabs(client):
    _login(client)
    for status in ("draft", "sent", "sent", "accepted", "declined", "expired"):
        Document.objects.create(
            kind="quote", status=status, number="" if status == "draft" else f"OFF-{status}"
        )

    response = client.get(reverse("quotes:list"))

    counts = {t["slug"]: t["count"] for t in response.context["tabs"]}
    assert counts == {"alle": 6, "concepten": 1, "wachten": 2, "geaccepteerd": 1, "afgewezen": 2}
    assert len(client.get(reverse("quotes:list"), {"tab": "wachten"}).context["quotes"]) == 2


def test_the_customer_of_a_sent_quote_can_no_longer_change(client):
    # Its PDF shows the contact snapshot taken at sending; a different live
    # contact would no longer match it (invariant 5).
    _login(client)
    _configure_settings()
    quote = _draft_quote_with_contact()
    DocumentLine.objects.create(
        document=quote, description="Werk", quantity="1", unit_price_cents=5000
    )
    client.post(reverse("quotes:send", args=[quote.pk]))
    other = Contact.objects.create(company_name="Andere Klant BV")
    lines = _line_formset_data()
    lines["lines-INITIAL_FORMS"] = "0"

    client.post(
        reverse("quotes:edit", args=[quote.pk]),
        {**_quote_form_data(contact=other.pk), **lines},
    )

    quote.refresh_from_db()
    assert quote.contact.company_name == "Klant BV"
