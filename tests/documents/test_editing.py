# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""documents.editing.preview_totals: the editor's live totals (M8).

They must come from the one totals function (invariant 3) and match what
saving the same form stores.
"""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.documents.drafts import line_formset
from huismus.documents.editing import preview_totals
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db


def _lines(*lines, deleted=()):
    data = {
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, (description, quantity, price, tax) in enumerate(lines):
        data[f"lines-{index}-description"] = description
        data[f"lines-{index}-quantity"] = quantity
        data[f"lines-{index}-unit"] = ""
        data[f"lines-{index}-unit_price_cents"] = price
        data[f"lines-{index}-tax_rate_bp"] = tax
        if index in deleted:
            data[f"lines-{index}-DELETE"] = "on"
    return data


def _formset(data, document=None):
    return line_formset(document or Document(kind="invoice"), data)


def test_preview_totals_counts_valid_lines_per_rate_group():
    data = _lines(("Sessie", "1", "450.00", "0"), ("Portretten", "10", "19.00", "2100"))
    totals, line_totals = preview_totals(_formset(data))

    assert line_totals == {"lines-0": 45000, "lines-1": 19000}
    assert totals.subtotal_cents == 64000
    assert totals.tax_cents == 3990  # 21% of 190,00, per rate group
    assert totals.total_cents == 67990


def test_invalid_empty_and_deleted_lines_are_left_out():
    data = _lines(
        ("Sessie", "1", "450.00", "0"),
        ("Tikfout", "2,5x", "85.00", "0"),  # not a number
        ("Weg", "1", "100.00", "0"),
        ("", "", "", "0"),  # the blank extra line
        deleted={2},
    )
    totals, line_totals = preview_totals(_formset(data))

    assert totals.total_cents == 45000
    assert line_totals == {"lines-0": 45000, "lines-1": None, "lines-2": None, "lines-3": None}


def test_preview_matches_what_saving_the_same_form_stores(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    contact = Contact.objects.create(company_name="Studio Noordwind")
    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    lines = _lines(("Uren", "2.5", "85.00", "900"), ("Reis", "1", "12.34", "0"))
    form = {
        "contact": contact.pk,
        "issue_date": "",
        "due_date": "",
        "delivery_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
    }

    preview, _ = preview_totals(_formset(lines, draft))
    client.post(reverse("documents:edit", args=[draft.pk]), {**form, **lines})
    draft.refresh_from_db()

    assert (draft.subtotal_cents, draft.tax_cents, draft.total_cents) == (
        preview.subtotal_cents,
        preview.tax_cents,
        preview.total_cents,
    )


def test_unbound_formset_uses_the_saved_lines():
    from huismus.documents.models import DocumentLine

    draft = Document.objects.create(kind="invoice", status="draft")
    first = DocumentLine.objects.create(
        document=draft, position=0, description="Uren", quantity="2", unit_price_cents=8500
    )
    DocumentLine.objects.create(
        document=draft, position=1, description="Reis", quantity="1", unit_price_cents=1234
    )

    formset = line_formset(draft)
    totals, line_totals = preview_totals(formset)

    assert totals.total_cents == 17000 + 1234
    assert line_totals["lines-0"] == 17000
    assert formset.forms[0].instance == first
    assert line_totals["lines-2"] is None  # the blank extra form


@pytest.mark.parametrize(("typed", "stored"), [("2,5", "2.5"), ("2.5", "2.5"), ("1", "1")])
def test_quantity_accepts_a_dutch_decimal_comma(typed, stored):
    from decimal import Decimal

    data = _lines(("Uren", typed, "85.00", "0"))
    formset = _formset(data)
    assert formset.is_valid(), formset.errors
    assert formset.forms[0].cleaned_data["quantity"] == Decimal(stored)


def test_saved_quantity_is_shown_without_trailing_zeros():
    from huismus.documents.models import DocumentLine

    draft = Document.objects.create(kind="invoice", status="draft")
    DocumentLine.objects.create(
        document=draft, position=0, description="Uren", quantity="10.000", unit_price_cents=100
    )
    DocumentLine.objects.create(
        document=draft, position=1, description="Uren", quantity="2.500", unit_price_cents=100
    )
    formset = line_formset(draft)
    assert 'value="10"' in str(formset.forms[0]["quantity"])
    assert 'value="2,5"' in str(formset.forms[1]["quantity"])


def test_saved_price_is_rendered_in_dutch_notation(client):
    # Regression (M8): the template localized Decimal("85.00") to "85,00",
    # which the <input type="number"> of that time rejected: the field showed
    # up empty and the next save failed with "Prijs per eenheid: verplicht".
    # Since 2026-10-29 the field is a text input in Dutch notation.
    from huismus.documents.models import DocumentLine

    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    draft = Document.objects.create(kind="invoice", status="draft")
    DocumentLine.objects.create(
        document=draft, position=0, description="Uren", quantity="2.5", unit_price_cents=128500
    )

    html = client.get(reverse("documents:edit", args=[draft.pk])).content.decode()

    assert 'value="1.285,00" type="text"' in html


def test_credit_note_editor_blocks_issuing_above_what_is_left_to_credit(client):
    from huismus.business.models import Settings
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
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
    contact = Contact.objects.create(company_name="Kiezel")
    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(
        document=invoice, description="Werk", quantity="1", unit_price_cents=181500
    )
    issue(invoice)
    credit = Document.objects.create(
        kind="credit_note", status="draft", contact=contact, related_document=invoice
    )
    form = {
        "contact": contact.pk,
        "issue_date": "",
        "due_date": "",
        "delivery_date": "",
        "language": "nl",
        "currency": "EUR",
        "intro_text": "",
        "footer_text": "",
        "notes": "",
    }
    url = reverse("documents:preview", args=[credit.pk])

    within = client.post(url, {**form, **_lines(("Correctie", "1", "135.00", "0"))})
    over = client.post(url, {**form, **_lines(("Correctie", "1", "1950.00", "0"))})

    assert within.context["credit_remaining_cents"] == 181500
    assert within.context["can_issue"] is True
    assert over.context["can_issue"] is False
    assert "is-over" in over.content.decode()


def test_a_line_without_quantity_or_unit_is_a_fixed_price():
    from huismus.documents.forms import DocumentLineForm

    form = DocumentLineForm(
        {
            "description": "Vast bedrag",
            "quantity": "",
            "unit": "",
            "unit_price_cents": "250.00",
            "tax_rate_bp": "0",
        },
        choices=["0", "900", "2100"],
        default_rate=2100,
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["quantity"] is None
    assert form.cleaned_data["unit"] == ""
    assert form.cleaned_data["unit_price_cents"] == 25000
