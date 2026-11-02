# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def test_year_overview_requires_login(client):
    response = client.get(reverse("reports:year_overview"))
    assert response.status_code == 302


def test_year_overview_defaults_to_the_current_year(client):
    _login(client)
    response = client.get(reverse("reports:year_overview"))
    assert response.status_code == 200
    assert str(timezone.localdate().year) in response.content.decode()


def test_year_overview_accepts_a_year_query_param(client):
    _login(client)
    Expense.objects.create(date="2020-01-15", amount_cents=1000)

    response = client.get(reverse("reports:year_overview"), {"jaar": "2020"})

    assert response.status_code == 200
    assert response.context["year"] == 2020
    assert response.context["overview"].expenses_cents == 1000
    assert "10,00" in response.content.decode()


def test_year_overview_ignores_a_garbage_year_param(client):
    _login(client)
    response = client.get(reverse("reports:year_overview"), {"jaar": "not-a-year"})
    assert response.status_code == 200


def test_year_overview_csv_download(client):
    _login(client)
    Expense.objects.create(date="2026-01-15", amount_cents=1000)

    response = client.get(reverse("reports:year_overview_csv"), {"jaar": "2026"})

    assert response.status_code == 200
    assert response["Content-Type"] == "text/csv; charset=utf-8"
    # The CSV form of every CSV in Huismus (SPEC.md M19): a BOM, semicolons
    # and a decimal comma, so Dutch Excel opens it.
    assert response.content.startswith("\ufeff".encode())
    lines = response.content.decode("utf-8-sig").splitlines()
    assert lines[0] == "kwartaal;omzet;kosten;winst"
    assert lines[1] == "Q1;0,00;10,00;-10,00"
    assert lines[-1] == "totaal;0,00;10,00;-10,00"


def _kor_on(*, limit_cents=1_000_000, warning_percent=80):
    settings = Settings.load()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.kor_limit_cents = limit_cents
    settings.kor_warning_percent = warning_percent
    settings.save()


def _issued_invoice(issue_date, total_cents):
    Document.objects.create(
        kind="invoice",
        status="issued",
        number=f"F-{issue_date}",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date=issue_date,
        subtotal_cents=total_cents,  # 0% VAT: under the KOR
        total_cents=total_cents,
    )


def test_year_overview_without_the_kor_says_nothing_about_a_limit(client):
    _login(client)
    response = client.get(reverse("reports:year_overview"))
    assert response.context["kor_limit"] is None
    assert "KOR-grens" not in response.content.decode()


def test_year_overview_shows_that_years_revenue_against_the_kor_limit(client):
    _login(client)
    _kor_on()
    _issued_invoice("2021-03-01", 850_000)
    _issued_invoice("2022-03-01", 999_999)  # another year: doesn't count

    response = client.get(reverse("reports:year_overview"), {"jaar": "2021"})

    kor_limit = response.context["kor_limit"]
    assert kor_limit.revenue_cents == 850_000
    assert kor_limit.level == "near"
    page = response.content.decode()
    assert 'id="kor-grens"' in page
    assert "85% van je KOR-grens" in page
    assert "€ 8.500,00 van € 10.000,00" in page
    assert "progress is-warn" in page


def test_an_earlier_year_says_it_is_measured_with_the_current_limit(client):
    _login(client)
    _kor_on()
    last_year = timezone.localdate().year - 1

    earlier = client.get(reverse("reports:year_overview"), {"jaar": last_year})
    this_year = client.get(reverse("reports:year_overview"))

    note = "Gemeten met je huidige KOR-grens van € 10.000,00."
    assert note in earlier.content.decode()
    assert note not in this_year.content.decode()


def test_a_year_without_revenue_shows_an_empty_bar(client):
    _login(client)
    _kor_on()
    response = client.get(reverse("reports:year_overview"), {"jaar": "2019"})
    assert response.context["kor_limit"].percent == 0
    assert "0% van je KOR-grens" in response.content.decode()


def test_a_year_over_the_limit_shows_a_red_bar(client):
    _login(client)
    _kor_on()
    _issued_invoice("2020-05-01", 1_000_001)
    response = client.get(reverse("reports:year_overview"), {"jaar": "2020"})
    assert response.context["kor_limit"].level == "over"
    assert "progress is-bad" in response.content.decode()


def test_the_csv_counts_revenue_without_vat(client):
    _login(client)
    Document.objects.create(
        kind="invoice",
        status="issued",
        number="F-btw",
        contact=Contact.objects.create(company_name="Klant BV"),
        issue_date="2026-02-01",
        subtotal_cents=100000,
        tax_cents=21000,
        total_cents=121000,
    )
    content = client.get(reverse("reports:year_overview_csv"), {"jaar": "2026"}).content.decode()
    assert "1000,00" in content
    assert "1210,00" not in content


def test_rapporten_opens_the_year_overview(client):
    _login(client)
    response = client.get(reverse("reports:index"))
    assert response.url == reverse("reports:year_overview")


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("/uitgaven/jaaroverzicht/?jaar=2021", "/rapporten/jaaroverzicht/?jaar=2021"),
        ("/uitgaven/jaaroverzicht/csv/?jaar=2021", "/rapporten/jaaroverzicht/csv/?jaar=2021"),
    ],
)
def test_the_old_year_overview_address_still_arrives(client, old, new):
    # Bookmarks and the installed app may still have the address from
    # before "Rapporten".
    response = client.get(old)
    assert response.status_code == 301
    assert response.url == new
