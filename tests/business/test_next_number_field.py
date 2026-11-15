# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The next number by hand on Facturen en nummering and in the start's
Facturen step (issue #141). The rules themselves: tests/documents/test_next_number.py."""

from datetime import date

import pytest
from django.urls import reverse
from django.utils import timezone

from huismus.documents.issuing import issue
from huismus.documents.numbering import next_sequence_number
from tests.business.test_views import _login, _valid_form_data
from tests.documents.test_issuing import _settings
from tests.documents.test_next_number import _draft, _imported

pytestmark = pytest.mark.django_db

PAGE = reverse("business:topic", args=["facturen"])
YEAR = timezone.localdate().year


def _facturen(**overrides):
    names = (
        "default_payment_terms_days",
        "invoice_number_format",
        "quote_number_format",
        "number_reset_yearly",
        "default_language",
        "currency",
    )
    data = {name: value for name, value in _valid_form_data().items() if name in names}
    data.update({"next_invoice_number": "1", "next_quote_number": "1"})
    data.update(overrides)
    return data


def test_the_page_shows_the_next_sequence_numbers(client):
    _login(client)
    page = client.get(PAGE).content.decode()

    assert 'name="next_invoice_number"' in page
    assert 'name="next_quote_number"' in page
    assert "Volgnummer van je volgende factuur" in page


def test_saving_sets_the_next_invoice_number(client):
    _login(client)
    response = client.post(PAGE, _facturen(next_invoice_number="43", next_quote_number="12"))

    assert response.status_code == 302
    assert next_sequence_number("invoice", year=YEAR) == 43
    assert next_sequence_number("quote", year=YEAR) == 12
    page = client.get(PAGE).content.decode()
    assert f"Volgende als je vandaag uitgeeft: {YEAR}-0043" in page
    assert 'value="43"' in page


def test_the_new_format_counts_in_the_same_save(client):
    # Format and number in one save: the existing-number check uses the
    # format being saved.
    _login(client)
    _imported(f"F-{YEAR}-0043", issue_date=date(YEAR, 1, 2))

    response = client.post(
        PAGE, _facturen(invoice_number_format="F-{year}-{seq:04d}", next_invoice_number="40")
    )

    assert "Kies 44 of hoger" in response.content.decode()
    assert next_sequence_number("invoice", year=YEAR) == 1


def test_a_refused_number_saves_nothing_else(client):
    _login(client)
    _imported(f"{YEAR}-0050", issue_date=date(YEAR, 1, 2))

    response = client.post(
        PAGE, _facturen(next_invoice_number="50", default_payment_terms_days="30")
    )

    assert response.status_code == 200
    assert response.context["form"].errors["next_invoice_number"]
    assert client.get(PAGE).context["form"]["default_payment_terms_days"].value() != 30


def test_once_an_invoice_is_issued_the_field_is_gone(client):
    _login(client)
    _settings()
    issue(_draft(issue_date=timezone.localdate()))

    page = client.get(PAGE).content.decode()

    assert 'name="next_invoice_number"' not in page
    assert "Het nummer loopt vanzelf door sinds je eerste factuur in Huismus." in page
    assert 'name="next_quote_number"' in page
    # Saving the rest still works, and a sent field is ignored.
    response = client.post(PAGE, _facturen(next_invoice_number="99"))
    assert response.status_code == 302
    assert next_sequence_number("invoice", year=YEAR) == 2


def test_the_start_has_the_field_too(client):
    _login(client)
    step = reverse("onboarding", args=["facturen"])
    assert 'name="next_invoice_number"' in client.get(step).content.decode()

    response = client.post(
        step,
        {
            "default_payment_terms_days": "14",
            "invoice_number_format": "{year}-{seq:04d}",
            "quote_number_format": "OFF-{year}-{seq:04d}",
            "next_invoice_number": "128",
            "next_quote_number": "1",
        },
    )

    assert response.status_code == 302
    assert next_sequence_number("invoice", year=YEAR) == 128


def test_in_english(client):
    _login(client)
    page = client.get(PAGE, headers={"accept-language": "en"}).content.decode()

    assert "Sequence number of your next invoice" in page
