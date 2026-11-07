# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VAT return page (SPEC.md M21, part 4): the boxes of a period, the
period choice, and "Niet meegeteld" only when there is something in it."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.models import Settings
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import VatRate

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _kor(on):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def test_it_requires_login(client):
    assert client.get(reverse("reports:vat_return")).status_code == 302


def test_it_shows_a_period_and_its_boxes(logged_in):
    _kor(False)
    create_expense(
        [ExpenseLineInput("Laptop", 121000, 21000, None, VatRate.HIGH)], date=date(2025, 5, 2)
    )

    response = logged_in.get(reverse("reports:vat_return"), {"periode": "2025-Q2"})

    html = response.content.decode()
    assert response.status_code == 200
    assert "2e kwartaal 2025" in html
    assert "1a" in html and "4b" in html
    assert "210,00" in html  # 5b
    assert "Terug te krijgen" in html
    assert 'id="niet-meegeteld"' not in html
    assert 'id="kor-aan"' not in html
    # Both reports have the tabs.
    assert reverse("reports:year_overview") in html


def test_lines_without_a_rate_are_listed_with_a_link(logged_in):
    _kor(False)
    expense = create_expense(
        [ExpenseLineInput("Treinkaartje", 1500, 0, None, "")],
        date=date(2025, 5, 2),
        supplier="NS",
    )

    html = logged_in.get(reverse("reports:vat_return"), {"periode": "2025-05"}).content.decode()

    assert "Niet meegeteld: 1." in html
    assert 'id="regels-zonder-tarief"' in html
    assert reverse("expenses:edit", args=[expense.pk]) in html


def test_with_the_kor_on_it_says_so_and_shows_no_figures(logged_in):
    _kor(True)
    create_expense([ExpenseLineInput("Pen", 1210, 210, None, VatRate.HIGH)], date=date(2025, 5, 2))

    html = logged_in.get(reverse("reports:vat_return"), {"periode": "2025"}).content.decode()

    assert 'id="kor-aan"' in html
    assert reverse("business:topic", args=["kor"]) in html
    assert 'id="rubrieken"' not in html
    assert 'id="niet-meegeteld"' not in html
    # Every period would show the same notice: no period choice.
    assert "Vorige periode" not in html
    assert "<h1>Btw-aangifte</h1>" in html


def test_an_empty_period_says_so_above_the_zeros(logged_in):
    _kor(False)

    html = logged_in.get(reverse("reports:vat_return"), {"periode": "2016-Q1"}).content.decode()

    assert "Geen facturen of uitgaven in deze periode." in html
    assert 'id="rubrieken"' in html


def test_the_period_kinds_link_to_each_other(logged_in):
    html = logged_in.get(reverse("reports:vat_return"), {"periode": "2025-Q2"}).content.decode()

    assert "?periode=2025-06" in html
    assert "?periode=2025" in html
    assert "?periode=2025-Q1" in html and "?periode=2025-Q3" in html
