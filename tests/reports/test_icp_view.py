# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The ICP page and its CSV (issue #168), and when Rapporten shows its tab
(huismus-intern/product/profiel-en-functies.md, row Opgaaf ICP: only with
VAT and customers in another EU country)."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.contacts.models import Contact
from huismus.core.csv_files import Amount

from .test_icp import _invoice
from .test_vat_return import _settings

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    _settings(kor=False)
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _page(client, period="2026-Q3"):
    return client.get(reverse("reports:icp"), {"periode": period}).content.decode()


def test_it_requires_login(client):
    assert client.get(reverse("reports:icp")).status_code == 302
    assert client.get(reverse("reports:icp_csv")).status_code == 302


def test_it_shows_a_line_per_vat_number_and_the_total(logged_in):
    _invoice(date(2026, 7, 1), 100_00)
    _invoice(date(2026, 8, 1), 25_00, country="BE", vat_number="BE0123456789", name="Klant BV")

    html = _page(logged_in)
    assert "DE123456789" in html and "BE0123456789" in html
    assert "125,00" in html
    assert "3b" in html
    assert 'id="leeg"' not in html


def test_invoices_without_a_vat_number_are_named(logged_in):
    invoice = _invoice(date(2026, 7, 1), 10_00, vat_number="")

    html = _page(logged_in)
    assert 'id="btw-nummer-ontbreekt"' in html
    assert invoice.number in html


def test_an_empty_period_says_so(logged_in):
    assert 'id="leeg"' in _page(logged_in)


def test_a_year_becomes_a_quarter(logged_in):
    """A yearly return needs a licence: Huismus offers a quarter or a month."""
    html = _page(logged_in, "2025")
    assert "4e kwartaal 2025" in html


def test_with_the_kor_on_it_shows_no_figures_and_makes_no_claim(logged_in):
    _invoice(date(2026, 7, 1), 100_00)
    _settings(kor=True)

    html = _page(logged_in)
    assert 'id="kor-aan"' in html
    assert "100,00" not in html
    assert "belastingdienst.nl" in html
    response = logged_in.get(reverse("reports:icp_csv"), {"periode": "2026-Q3"})
    assert response.status_code == 302


def test_the_csv_has_a_row_per_vat_number_and_the_total(logged_in):
    from huismus.reports.icp import compute_icp
    from huismus.reports.icp_csv import rows
    from huismus.reports.periods import Period

    _invoice(date(2026, 7, 1), 100_00)
    missing = _invoice(date(2026, 7, 2), 5_00, vat_number="")
    report = compute_icp(Period.parse("2026-Q3", today=date(2026, 11, 7)))

    assert rows(report) == [
        ["2026-Q3", "DE123456789", "DE", "Kunde GmbH", "", Amount(100_00)],
        ["2026-Q3", "btw-nummer ontbreekt", "DE", "Kunde GmbH", missing.number, Amount(5_00)],
        ["2026-Q3", "totaal", "", "", "", Amount(105_00)],
    ]
    response = logged_in.get(reverse("reports:icp_csv"), {"periode": "2026-Q3"})
    assert response.status_code == 200
    assert "opgaaf-icp-2026-Q3.csv" in response["Content-Disposition"]


def test_the_tab_shows_only_with_vat_and_a_customer_in_the_eu(logged_in):
    tab = reverse("reports:icp")
    year = reverse("reports:year_overview")
    assert tab not in logged_in.get(year).content.decode()

    Contact.objects.create(company_name="Kunde GmbH", country="DE")
    assert tab in logged_in.get(year).content.decode()
    assert tab in logged_in.get(reverse("reports:vat_return")).content.decode()

    _settings(kor=True)
    assert tab not in logged_in.get(year).content.decode()
