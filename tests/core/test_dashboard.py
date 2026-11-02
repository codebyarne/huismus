# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Overzicht page (M8): core.dashboard and the home view."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.dashboard import onboarding_steps, outstanding_invoices
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def settings_filled():
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


def _issued(cents, due_date=None, paid=0, kind="invoice", related=None):
    contact = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(
        kind=kind, status="draft", contact=contact, due_date=due_date, related_document=related
    )
    DocumentLine.objects.create(
        document=document, description="Werk", quantity="1", unit_price_cents=cents
    )
    document = issue(document)
    if paid:
        Payment.objects.create(document=document, paid_on=TODAY, amount_cents=paid)
    return document


def test_outstanding_sums_what_is_still_owed_and_counts_overdue(settings_filled):
    _issued(100000)
    _issued(50000, paid=20000)
    _issued(30000, due_date=TODAY - timedelta(days=3))
    _issued(40000, paid=40000)  # paid: not outstanding
    credited = _issued(25000)
    _issued(25000, kind="credit_note", related=credited)  # fully credited

    summary = outstanding_invoices()

    assert summary["total_cents"] == 100000 + 30000 + 30000
    assert summary["count"] == 3
    assert summary["overdue_count"] == 1


def test_onboarding_steps_follow_what_exists(settings_filled):
    steps = {step["key"]: step["done"] for step in onboarding_steps()}
    assert steps == {
        "business": True,
        "logo": False,
        "kor": False,
        "contact": False,
        "invoice": False,
    }

    Contact.objects.create(company_name="Klant BV")
    assert {s["key"]: s["done"] for s in onboarding_steps()}["contact"] is True


def test_home_shows_the_welcome_until_there_is_anything(client, settings_filled):
    user = get_user_model().objects.create_user(
        username="lotte", password="s3cret-pass", first_name="Lotte"
    )
    client.force_login(user)

    first = client.get(reverse("home"))
    assert first.context["first_time"] is True
    assert "Welkom bij Huismus" in first.content.decode()

    _issued(12100)
    later = client.get(reverse("home"))
    assert later.context["first_time"] is False
    assert later.context["outstanding"]["total_cents"] == 12100
    assert "Lotte" in later.content.decode()


def _kor_on(settings, *, limit_cents=1_000_000, warning_percent=80):
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.kor_limit_cents = limit_cents
    settings.kor_warning_percent = warning_percent
    settings.save()


@pytest.fixture
def logged_in(client):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


def test_without_the_kor_the_overview_says_nothing_about_a_limit(logged_in, settings_filled):
    _issued(5_000_000)
    page = logged_in.get(reverse("home")).content.decode()
    assert "KOR-grens" not in page


def test_with_the_kor_the_revenue_card_shows_the_share_of_the_limit(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(250_000)
    page = logged_in.get(reverse("home")).content.decode()
    assert "25% van je KOR-grens" in page
    assert 'id="kor-melding"' not in page


def test_from_the_warning_percentage_a_banner_shows(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(850_000)
    page = logged_in.get(reverse("home")).content.decode()
    assert 'id="kor-melding"' in page
    assert "85% van je KOR-grens" in page
    assert f"?jaar={TODAY.year}" in page


def test_above_the_limit_the_banner_says_so(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(1_000_001)
    response = logged_in.get(reverse("home"))
    assert response.context["kor_limit"].level == "over"
    assert "hoger dan je KOR-grens" in response.content.decode()


def test_the_kor_or_vat_step_is_done_with_the_kor_and_its_text(settings_filled):
    settings_filled.kor_enabled = True
    settings_filled.kor_text = "Vrijgesteld van btw (KOR)."
    settings_filled.save()
    step = next(s for s in onboarding_steps() if s["key"] == "kor")
    assert step["done"] is True
    assert str(step["title"]) == "KOR of btw instellen"


def test_the_kor_or_vat_step_is_done_without_the_kor_and_with_a_vat_number(settings_filled):
    settings_filled.kor_enabled = False
    settings_filled.vat_number = ""
    settings_filled.save()
    assert next(s for s in onboarding_steps() if s["key"] == "kor")["done"] is False
    settings_filled.vat_number = "NL000099998B57"
    settings_filled.save()
    assert next(s for s in onboarding_steps() if s["key"] == "kor")["done"] is True
