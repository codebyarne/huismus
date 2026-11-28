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
    assert "met btw" in page
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
        "Totaal bedrijfskosten;Kosten zonder btw;105,00",
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


FIGURES = "ondernemer-bekijk-welke-cijfers-u-nodig-hebt-voor-uw-aangifte-inkomstenbelasting"
COSTS = "zakelijke_kosten/zakelijke_kosten"
KOR = "kleineondernemersregeling"
PROFIT = "winst_uit_onderneming"


def _notes(client) -> str:
    page = client.get(reverse("reports:profit_and_loss"), {"jaar": "2026"}).content.decode()
    return page.split('id="zo-telt-huismus"')[1].split("</ul>")[0]


def test_with_vat_the_notes_say_without_vat_and_link_their_sources(logged_in):
    _kor(False)

    notes = _notes(logged_in)

    assert "Omzet is zonder btw" in notes
    assert FIGURES in notes and COSTS in notes and PROFIT in notes
    assert KOR not in notes


def test_with_the_kor_the_notes_say_with_vat_and_link_the_kor(logged_in):
    _kor(True)

    notes = _notes(logged_in)

    assert "Je rekent geen btw, dus omzet is je totale omzet" in notes
    assert FIGURES in notes and KOR in notes


def test_without_vat_for_another_reason_there_is_no_kor_link(logged_in):
    settings = Settings.load()
    settings.vat_exempt = True
    settings.save()

    notes = _notes(logged_in)

    assert "Je rekent geen btw" in notes
    assert KOR not in notes


def test_the_notes_say_what_is_not_in_it_and_nothing_without_a_source(logged_in):
    notes = _notes(logged_in)

    assert "Alle uitgaven staan onder bedrijfskosten" in notes
    assert "Afschrijvingen houdt Huismus nog niet bij." in notes
    assert "fiscale regels" in notes
    # docs/belastingregels.md, section 7: not asked, or no source.
    for unsourced in ("450", "5.700", "baten en lasten", "vrijstelling"):
        assert unsourced not in notes


def test_the_pdf_has_the_notes(logged_in, year):
    _kor(False)

    text = _text(logged_in.get(reverse("reports:profit_and_loss_pdf"), {"jaar": "2026"}))

    assert "Afschrijvingen houdt Huismus nog niet bij." in text
    assert "zonder btw" in text


def test_with_the_kor_the_csv_total_is_called_costs(logged_in, year):
    _kor(True)

    response = logged_in.get(reverse("reports:profit_and_loss_csv"), {"jaar": "2026"})

    assert "Totaal bedrijfskosten;Kosten;126,00" in response.content.decode("utf-8-sig")
