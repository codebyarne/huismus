# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A sent quote after its expiry date (SPEC.md M8, #204): it reads as
"Verlopen" on every screen, while the stored status stays "sent" so a late
answer can still be recorded. Huismus stores nothing for it by itself."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.contacts.models import Contact
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_client(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _quote(days_left, *, status="sent", name="Klant BV"):
    """A quote whose expiry date is `days_left` days from today (None: no date)."""
    expiry = None if days_left is None else timezone.localdate() + timedelta(days=days_left)
    contact = Contact.objects.create(company_name=name)
    return Document.objects.create(
        kind="quote",
        status=status,
        number=f"OFF-{contact.pk}",
        contact=contact,
        issue_date=timezone.localdate() - timedelta(days=40),
        expiry_date=expiry,
    )


@pytest.mark.parametrize(
    ("status", "days_left", "shown"),
    [
        ("sent", 30, "sent"),
        ("sent", 0, "sent"),  # the last day it is valid
        ("sent", -1, "expired"),
        ("sent", None, "sent"),  # without a date a quote never expires
        ("draft", -1, "draft"),
        ("accepted", -1, "accepted"),
        ("declined", -1, "declined"),
        ("expired", 30, "expired"),
    ],
)
def test_the_status_a_quote_shows(status, days_left, shown):
    quote = _quote(days_left, status=status)

    assert quote.shown_status == shown
    assert Document.objects.get(pk=quote.pk).status == status


def test_past_its_date_a_quote_is_under_declined_or_expired_not_waiting(user_client):
    _quote(-1, name="Datum Voorbij")
    _quote(0, name="Vandaag Nog")

    response = user_client.get(reverse("quotes:list"))
    counts = {t["slug"]: t["count"] for t in response.context["tabs"]}

    assert counts["wachten"] == 1
    assert counts["afgewezen"] == 1
    waiting = user_client.get(reverse("quotes:list"), {"tab": "wachten"}).content.decode()
    gone = user_client.get(reverse("quotes:list"), {"tab": "afgewezen"}).content.decode()
    assert "Vandaag Nog" in waiting and "Datum Voorbij" not in waiting
    assert "verloopt vandaag" in waiting
    assert "Datum Voorbij" in gone and "pill-quote-expired" in gone


def test_its_own_page_says_expired_and_still_takes_the_answer(user_client):
    quote = _quote(-1)

    page = user_client.get(reverse("quotes:edit", args=[quote.pk])).content.decode()

    assert "pill-quote-expired" in page
    assert "Was geldig tot" in page
    assert "Wacht op antwoord van de klant" not in page
    assert reverse("quotes:accept", args=[quote.pk]) in page
    assert reverse("quotes:decline", args=[quote.pk]) in page
    # "Markeer als verlopen" is for before the date; now it already reads so.
    assert reverse("quotes:expire", args=[quote.pk]) not in page

    user_client.post(reverse("quotes:accept", args=[quote.pk]))

    quote.refresh_from_db()
    assert quote.status == "accepted"
    assert quote.shown_status == "accepted"


def test_before_its_date_the_page_waits_and_offers_to_mark_it_expired(user_client):
    quote = _quote(3)

    page = user_client.get(reverse("quotes:edit", args=[quote.pk])).content.decode()

    assert "Wacht op antwoord van de klant" in page
    assert reverse("quotes:expire", args=[quote.pk]) in page


def test_a_later_expiry_date_makes_it_wait_again(user_client):
    quote = _quote(-1)

    Document.objects.filter(pk=quote.pk).update(
        expiry_date=timezone.localdate() + timedelta(days=14)
    )

    counts = {
        t["slug"]: t["count"] for t in user_client.get(reverse("quotes:list")).context["tabs"]
    }
    assert counts["wachten"] == 1
    assert counts["afgewezen"] == 0


def test_the_customers_page_says_expired_too(user_client):
    quote = _quote(-1)

    page = user_client.get(reverse("contacts:edit", args=[quote.contact.pk])).content.decode()

    assert quote.number in page
    assert "pill-quote-expired" in page


def test_the_overview_only_lists_quotes_that_still_wait(user_client):
    _quote(-1, name="Datum Voorbij")
    _quote(5, name="Wacht Nog")

    page = user_client.get(reverse("home")).content.decode()

    assert "Wacht Nog" in page
    assert "Datum Voorbij" not in page


@pytest.mark.parametrize(
    ("status", "shown"),
    [("sent", True), ("accepted", False), ("declined", False), ("expired", False)],
)
def test_only_a_quote_that_still_runs_says_to_send_the_new_pdf_again(user_client, status, shown):
    quote = _quote(30, status=status)

    page = user_client.get(reverse("quotes:edit", args=[quote.pk])).content.decode()

    assert ("is al verzonden. Pas je iets aan" in page) is shown
