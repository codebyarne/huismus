# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Copying an invoice or quote into a new draft (SPEC.md section 6, M8: "added after
first real use")."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.documents.quoting import send_quote

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


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


def _invoice(kind="invoice", **fields):
    invoice = Document.objects.create(
        kind=kind,
        status="draft",
        contact=Contact.objects.create(company_name="Klant BV"),
        language="en",
        intro_text="Werk in maart",
        footer_text="Dank je wel",
        notes="Alleen voor mij",
        issue_date=datetime.date(2026, 3, 1),
        delivery_date=datetime.date(2026, 2, 28),
        **{"due_date": datetime.date(2026, 3, 15), **fields},
    )
    DocumentLine.objects.create(
        document=invoice,
        position=0,
        description="Uren",
        quantity="12.5",
        unit="uur",
        unit_price_cents=8500,
        tax_rate_bp=0,
    )
    DocumentLine.objects.create(
        document=invoice,
        position=1,
        description="Reiskosten",
        unit_price_cents=4200,
        tax_rate_bp=900,
    )
    return invoice


def _copy(client, document):
    return client.post(reverse("documents:copy", kwargs={"pk": document.pk}))


def test_copying_an_issued_invoice_makes_a_new_draft_and_opens_it(logged_in):
    _configure_settings()
    invoice = issue(_invoice())

    response = _copy(logged_in, invoice)

    copy = Document.objects.exclude(pk=invoice.pk).get()
    assert response.status_code == 302
    assert response.url == reverse("documents:edit", kwargs={"pk": copy.pk})
    assert (copy.kind, copy.status, copy.number) == ("invoice", "draft", "")


def test_the_copy_keeps_customer_lines_and_texts(logged_in):
    invoice = _invoice()

    _copy(logged_in, invoice)

    copy = Document.objects.exclude(pk=invoice.pk).get()
    assert copy.contact_id == invoice.contact_id
    assert (copy.language, copy.currency) == ("en", "EUR")
    assert (copy.intro_text, copy.footer_text) == ("Werk in maart", "Dank je wel")
    assert [
        (line.position, line.description, line.quantity, line.unit, line.unit_price_cents)
        for line in copy.lines.order_by("position")
    ] == [
        (0, "Uren", invoice.lines.get(position=0).quantity, "uur", 8500),
        (1, "Reiskosten", None, "", 4200),
    ]
    assert [line.tax_rate_bp for line in copy.lines.order_by("position")] == [0, 900]


def test_the_copy_starts_without_dates_notes_snapshots_or_a_link(logged_in):
    # Dates are filled in at issue (issuing.issue), like any new invoice;
    # notes belong to the original; a copy is no correction of it.
    _configure_settings()
    invoice = issue(_invoice())

    _copy(logged_in, invoice)

    copy = Document.objects.exclude(pk=invoice.pk).get()
    assert (copy.issue_date, copy.due_date, copy.delivery_date) == (None, None, None)
    assert copy.notes == ""
    assert copy.related_document is None
    assert (copy.contact_snapshot, copy.business_snapshot, copy.kor_text_snapshot) == (
        None,
        None,
        "",
    )
    assert (copy.source, copy.external_id) == ("", "")


def test_the_copy_has_the_same_totals_as_the_original(logged_in):
    _configure_settings()
    invoice = issue(_invoice())

    _copy(logged_in, invoice)

    copy = Document.objects.exclude(pk=invoice.pk).get()
    assert [line.line_total_cents for line in copy.lines.order_by("position")] == [
        line.line_total_cents for line in invoice.lines.order_by("position")
    ]
    assert (copy.subtotal_cents, copy.tax_cents, copy.total_cents) == (
        invoice.subtotal_cents,
        invoice.tax_cents,
        invoice.total_cents,
    )


def test_the_original_stays_as_it_was(logged_in):
    _configure_settings()
    invoice = issue(_invoice())
    before = (invoice.number, invoice.total_cents, invoice.lines.count())

    _copy(logged_in, invoice)

    invoice.refresh_from_db()
    assert (invoice.number, invoice.total_cents, invoice.lines.count()) == before


def test_issuing_the_copy_takes_the_next_number(logged_in):
    _configure_settings()
    invoice = issue(_invoice())
    _copy(logged_in, invoice)
    copy = Document.objects.exclude(pk=invoice.pk).get()

    issue(copy)

    assert copy.number != invoice.number
    assert copy.issue_date is not None


@pytest.mark.parametrize(
    ("kind", "url_name"),
    [
        ("quote", "documents:copy"),
        ("invoice", "quotes:copy"),
        ("credit_note", "documents:copy"),
        ("credit_note", "quotes:copy"),
    ],
)
def test_each_url_copies_only_its_own_kind(logged_in, kind, url_name):
    document = Document.objects.create(kind=kind, status="draft")

    response = logged_in.post(reverse(url_name, kwargs={"pk": document.pk}))

    assert response.status_code == 404
    assert Document.objects.count() == 1


def test_a_get_copies_nothing(logged_in):
    invoice = _invoice()

    response = logged_in.get(reverse("documents:copy", kwargs={"pk": invoice.pk}))

    assert response.status_code == 302
    assert Document.objects.count() == 1


def test_copying_requires_login(client):
    invoice = _invoice()

    response = _copy(client, invoice)

    assert response.status_code == 302
    assert "/login/" in response.url
    assert Document.objects.count() == 1


def test_both_the_editor_and_the_detail_page_offer_the_copy(logged_in):
    _configure_settings()
    draft = _invoice()
    issued = issue(_invoice())
    for document in (draft, issued):
        response = logged_in.get(reverse("documents:edit", kwargs={"pk": document.pk}))
        assert reverse("documents:copy", kwargs={"pk": document.pk}) in response.text


def test_a_credit_note_offers_no_copy(logged_in):
    credit_note = Document.objects.create(kind="credit_note", status="draft")

    response = logged_in.get(reverse("documents:edit", kwargs={"pk": credit_note.pk}))

    assert reverse("documents:copy", kwargs={"pk": credit_note.pk}) not in response.text


# --- Quotes ---


def _quote():
    return _invoice(kind="quote", due_date=None, expiry_date=datetime.date(2026, 3, 31))


def _copy_quote(client, quote):
    return client.post(reverse("quotes:copy", kwargs={"pk": quote.pk}))


def test_copying_a_sent_quote_makes_a_new_draft_quote_and_opens_it(logged_in):
    _configure_settings()
    quote = send_quote(_quote())

    response = _copy_quote(logged_in, quote)

    copy = Document.objects.exclude(pk=quote.pk).get()
    assert response.status_code == 302
    assert response.url == reverse("quotes:edit", kwargs={"pk": copy.pk})
    assert (copy.kind, copy.status, copy.number) == ("quote", "draft", "")
    assert copy.contact_id == quote.contact_id
    assert (copy.language, copy.intro_text, copy.footer_text) == (
        "en",
        "Werk in maart",
        "Dank je wel",
    )
    assert [line.description for line in copy.lines.order_by("position")] == ["Uren", "Reiskosten"]


def test_the_quote_copy_starts_without_dates_notes_snapshots_or_a_link(logged_in):
    _configure_settings()
    quote = send_quote(_quote())

    _copy_quote(logged_in, quote)

    copy = Document.objects.exclude(pk=quote.pk).get()
    assert (copy.issue_date, copy.expiry_date, copy.delivery_date) == (None, None, None)
    assert copy.notes == ""
    assert copy.related_document is None
    assert (copy.contact_snapshot, copy.business_snapshot) == (None, None)


def test_copying_a_quote_leaves_the_original_as_it_was(logged_in):
    _configure_settings()
    quote = send_quote(_quote())
    before = (quote.status, quote.number, quote.total_cents, quote.lines.count())

    _copy_quote(logged_in, quote)

    quote.refresh_from_db()
    assert (quote.status, quote.number, quote.total_cents, quote.lines.count()) == before


def test_the_quote_editor_offers_the_copy_in_every_status(logged_in):
    _configure_settings()
    draft = _quote()
    sent = send_quote(_quote())
    for quote in (draft, sent):
        response = logged_in.get(reverse("quotes:edit", kwargs={"pk": quote.pk}))
        assert reverse("quotes:copy", kwargs={"pk": quote.pk}) in response.text


def test_a_copy_that_fails_halfway_leaves_nothing_behind(logged_in, monkeypatch):
    invoice = _invoice()
    create = DocumentLine.objects.create
    calls = []

    def fail_on_the_second_line(**fields):
        calls.append(fields)
        if len(calls) == 2:
            raise RuntimeError("disk full")
        return create(**fields)

    monkeypatch.setattr(DocumentLine.objects, "create", fail_on_the_second_line)

    with pytest.raises(RuntimeError):
        _copy(logged_in, invoice)

    assert Document.objects.count() == 1
