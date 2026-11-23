# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Rapporten → Winst en verlies: the page, its PDF and its CSV (issue #109,
SPEC.md M28)."""

import io
from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from pypdf import PdfReader

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.business_name = "Studio Voorbeeld"
    settings.kvk_number = "12345678"
    settings.save()


@pytest.fixture
def year():
    Document.objects.create(
        kind="invoice",
        status="issued",
        number="2026-001",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=date(2026, 3, 1),
        subtotal_cents=100000,
        total_cents=121000,
    )
    software = ExpenseCategory.objects.create(name="Software")
    create_expense(
        [
            ExpenseLineInput("", 12100, 2100, software, VatRate.HIGH),
            ExpenseLineInput("", 500, None, None, ""),
        ],
        date=date(2026, 2, 1),
    )


def _text(response) -> str:
    return "".join(page.extract_text() for page in PdfReader(io.BytesIO(response.content)).pages)


def test_the_page_needs_a_login(client):
    assert client.get(reverse("reports:profit_and_loss")).status_code == 302


def test_the_page_shows_revenue_costs_per_category_and_profit(logged_in, year):
    _kor(False)

    response = logged_in.get(reverse("reports:profit_and_loss"), {"jaar": "2026"})

    page = response.content.decode()
    assert response.status_code == 200
    assert "Winst-en-verliesrekening 2026" in page
    assert "Opbrengsten" in page
    assert "Bedrijfskosten" in page
    assert "zonder btw" in page
    assert "Software" in page
    assert "Zonder categorie" in page
    assert "1.000,00" in page  # revenue without VAT
    assert "105,00" in page  # 100 + 5 costs without VAT
    assert "895,00" in page  # profit


def test_with_the_kor_costs_are_what_was_paid(logged_in, year):
    _kor(True)

    page = logged_in.get(reverse("reports:profit_and_loss"), {"jaar": "2026"}).content.decode()

    assert "zonder btw" not in page
    assert "126,00" in page  # 121 + 5


def test_a_year_without_expenses_says_so(logged_in):
    page = logged_in.get(reverse("reports:profit_and_loss"), {"jaar": "2020"}).content.decode()

    assert "Je hebt dit jaar geen uitgaven." in page


def test_the_page_defaults_to_this_year_and_ignores_a_garbage_year(logged_in):
    response = logged_in.get(reverse("reports:profit_and_loss"), {"jaar": "nope"})

    assert response.status_code == 200
    assert response.context["year"] == timezone.localdate().year


def test_the_tabs_lead_to_the_statement(logged_in):
    page = logged_in.get(reverse("reports:year_overview")).content.decode()

    assert reverse("reports:profit_and_loss") in page


def test_the_csv_has_a_row_per_heading_and_category(logged_in, year):
    _kor(False)

    response = logged_in.get(reverse("reports:profit_and_loss_csv"), {"jaar": "2026"})

    assert response.status_code == 200
    assert response["Content-Disposition"].endswith('winst-en-verlies-2026.csv"')
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines == [
        "rubriek;regel;bedrag",
        "Opbrengsten;Omzet;1000,00",
        "Bedrijfskosten;Software;100,00",
        "Bedrijfskosten;Zonder categorie;5,00",
        "Bedrijfskosten;Kosten zonder btw;105,00",
        "Winst;;895,00",
    ]


def test_the_pdf_has_the_business_the_year_and_the_profit(logged_in, year):
    _kor(False)

    response = logged_in.get(reverse("reports:profit_and_loss_pdf"), {"jaar": "2026"})

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].endswith('winst-en-verlies-2026.pdf"')
    text = _text(response)
    assert "Studio Voorbeeld" in text
    assert "Winst-en-verliesrekening 2026" in text
    assert "895,00" in text
    assert "Software" in text


def test_the_pdf_is_in_the_language_of_the_user(logged_in, year):
    _kor(False)
    logged_in.cookies["django_language"] = "en"

    response = logged_in.get(reverse("reports:profit_and_loss_pdf"), {"jaar": "2026"})

    text = _text(response)
    assert "Profit and loss statement 2026" in text
