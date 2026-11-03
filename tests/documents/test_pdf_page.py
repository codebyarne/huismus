# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The page the PDF button opens (documents.views.document_pdf_page): the
PDF in a frame, Download, and a way back to the document. On an iPhone, in
the app on the home screen, a bare PDF filled the screen with no way back
(huismus-intern/besluiten.md, 2026-11-01)."""

import re
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import send_quote
from huismus.documents.reopening import reopen

pytestmark = pytest.mark.django_db

TEMPLATES = Path(__file__).resolve().parents[2] / "huismus" / "templates"


@pytest.fixture
def logged_in(client):
    user = get_user_model().objects.create_user(username="eigenaar", password="x")
    client.force_login(user)
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return client


def _document(kind="invoice"):
    contact = Contact.objects.create(company_name="Klant BV", city="Utrecht")
    document = Document.objects.create(kind=kind, status="draft", contact=contact)
    DocumentLine.objects.create(
        document=document, description="Consult", quantity="1", unit_price_cents=10000
    )
    return send_quote(document) if kind == "quote" else issue(document)


def _with_original(document):
    Attachment.objects.create(
        document=document,
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )
    return document


def _page(client, document, query=""):
    name = "quotes:pdf_page" if document.kind == "quote" else "documents:pdf_page"
    response = client.get(reverse(name, args=[document.pk]) + query)
    assert response.status_code == 200
    return response.content.decode()


def test_the_pdf_button_opens_the_pdf_page(logged_in):
    invoice = _document()

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    header = content[: content.index('class="split-rev"')]
    assert f'href="{reverse("documents:pdf_page", args=[invoice.pk])}"' in header


def test_the_pdf_page_shows_the_pdf_with_a_way_back_and_download(logged_in):
    invoice = _document()

    content = _page(logged_in, invoice)

    assert f'class="back" href="{reverse("documents:edit", args=[invoice.pk])}"' in content
    assert f"Factuur {invoice.number}</a>" in content
    assert f"<h1>{invoice.number}.pdf</h1>" in content
    assert f'href="{reverse("documents:pdf", args=[invoice.pk])}"' in content
    assert (
        f'<iframe class="pdf-frame" src="{reverse("documents:pdf_embed", args=[invoice.pk])}"'
        in (content)
    )
    assert "Origineel uit Moneybird" not in content


def test_a_quote_s_pdf_page_leads_back_to_the_quote(logged_in):
    quote = _document("quote")

    content = _page(logged_in, quote)

    assert f'class="back" href="{reverse("quotes:edit", args=[quote.pk])}"' in content
    assert f"Offerte {quote.number}</a>" in content


def test_a_draft_has_no_pdf_page(logged_in):
    contact = Contact.objects.create(company_name="Klant BV")
    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)

    response = logged_in.get(reverse("documents:pdf_page", args=[draft.pk]))

    assert response.status_code == 404


def test_the_pdf_page_requires_login(client):
    invoice = _document()

    response = client.get(reverse("documents:pdf_page", args=[invoice.pk]))

    assert response.status_code == 302


def test_download_is_still_named_after_the_number_and_never_in_a_frame(logged_in):
    invoice = _document()

    response = logged_in.get(reverse("documents:pdf", args=[invoice.pk]))

    assert response["Content-Disposition"] == f'attachment; filename="{invoice.number}.pdf"'
    assert response["X-Frame-Options"] == "DENY"


def test_the_frame_shows_the_pdf_only_on_huismus_s_own_pages(logged_in):
    invoice = _with_original(_document())

    for name in ("documents:pdf_embed", "documents:original_pdf_embed"):
        response = logged_in.get(reverse(name, args=[invoice.pk]))

        assert response["Content-Type"] == "application/pdf"
        assert response["Content-Disposition"] == f'inline; filename="{invoice.number}.pdf"'
        assert response["X-Frame-Options"] == "SAMEORIGIN"


def test_an_imported_invoice_opens_on_the_original(logged_in):
    invoice = _with_original(_document())

    content = _page(logged_in, invoice)

    assert 'href="?versie=origineel" aria-current="page"' in content
    assert f'href="{reverse("documents:original_pdf", args=[invoice.pk])}"' in content
    assert f'src="{reverse("documents:original_pdf_embed", args=[invoice.pk])}"' in content


def test_an_imported_invoice_switches_to_the_regenerated_pdf(logged_in):
    invoice = _with_original(_document())

    content = _page(logged_in, invoice, "?versie=opnieuw")

    assert 'href="?versie=opnieuw" aria-current="page"' in content
    assert f'href="{reverse("documents:pdf", args=[invoice.pk])}"' in content
    assert f'src="{reverse("documents:pdf_embed", args=[invoice.pk])}"' in content


def test_after_editing_an_imported_invoice_its_pdf_page_opens_on_the_new_one(logged_in):
    invoice = issue(reopen(_with_original(_document())))

    content = _page(logged_in, invoice)

    assert 'href="?versie=opnieuw" aria-current="page"' in content


def test_an_unknown_version_falls_back_and_without_an_original_there_is_no_choice(logged_in):
    imported = _with_original(_document())
    plain = _document()

    assert 'href="?versie=origineel" aria-current="page"' in _page(
        logged_in, imported, "?versie=iets"
    )
    content = _page(logged_in, plain, "?versie=origineel")
    assert f'src="{reverse("documents:pdf_embed", args=[plain.pk])}"' in content
    assert "?versie=" not in content


def test_the_documents_links_open_the_pdf_page_with_their_own_choice(logged_in):
    invoice = _with_original(_document())

    content = logged_in.get(reverse("documents:edit", args=[invoice.pk])).content.decode()

    page = reverse("documents:pdf_page", args=[invoice.pk])
    assert f'href="{page}?versie=origineel"' in content
    assert f'href="{page}?versie=opnieuw"' in content


def test_no_template_links_to_a_bare_pdf_except_the_pdf_page():
    # The whole kind of bug: a link that opens the PDF itself leaves no way
    # back in the app on an iPhone. Only the PDF page's Download does, and
    # the editor's preview (a form, huismus-intern/backlog.md).
    bare = re.compile(r"\{% url '(?:documents|quotes):(?:pdf|original_pdf)(?:_embed)?'")
    offenders = [
        str(path.relative_to(TEMPLATES))
        for path in TEMPLATES.rglob("*.html")
        if bare.search(path.read_text(encoding="utf-8"))
    ]
    assert not offenders, f"link to the PDF page instead: {offenders}"


def test_a_credit_note_s_pdf_page_leads_back_to_the_credit_note(logged_in):
    from huismus.documents.drafts import create_credit_note

    invoice = Document.objects.with_payment_totals().get(pk=_document().pk)
    credit_note = issue(create_credit_note(invoice))

    content = _page(logged_in, credit_note)

    assert f'class="back" href="{reverse("documents:edit", args=[credit_note.pk])}"' in content
    assert f"Creditnota {credit_note.number}</a>" in content


def test_a_quote_s_pdf_page_sits_under_quotes_and_marks_quotes_in_the_menu(logged_in):
    quote = _document("quote")
    invoice = _document()

    content = logged_in.get(reverse("quotes:edit", args=[quote.pk])).content.decode()
    assert f'href="{reverse("quotes:pdf_page", args=[quote.pk])}"' in content
    page = logged_in.get(reverse("quotes:pdf_page", args=[quote.pk]))
    assert page.context["nav_section"] == "quotes"
    # Each kind at its own address only.
    assert logged_in.get(reverse("documents:pdf_page", args=[quote.pk])).status_code == 404
    assert logged_in.get(reverse("quotes:pdf_page", args=[invoice.pk])).status_code == 404
