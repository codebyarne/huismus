# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The card Zakelijke kilometers on the year overview (#125; product-owner
agent 2026-11-28): the year's kilometres and trips, only when the year has
trips, never an amount. The CSV of the year overview stays in euros."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from huismus.mileage.models import Trip
from tests.business.test_parts import client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]

PAGE = reverse("reports:year_overview")


def _trip(day, km):
    Trip.objects.create(
        date=day, origin="Utrecht", destination="Zwolle", purpose="Klant", distance_km=Decimal(km)
    )


def _html(client, year):
    return client.get(f"{PAGE}?jaar={year}").content.decode()


def test_the_card_has_the_years_kilometres_and_trips(client_in):
    _trip(date(2025, 1, 5), "1000")
    _trip(date(2025, 12, 31), "842")
    _trip(date(2024, 12, 31), "5")
    html = _html(client_in, 2025)
    assert "Zakelijke kilometers" in html
    assert "1.842 km in 2 ritten" in html
    assert f'href="{reverse("mileage:list")}?jaar=2025"' in html
    assert "Bekijk de ritten" in html


def test_one_trip_is_singular(client_in):
    _trip(date(2025, 1, 5), "12.5")
    assert "12,5 km in 1 rit<" in _html(client_in, 2025)


def test_no_trips_no_card(client_in):
    _trip(date(2024, 1, 5), "12")
    assert "Zakelijke kilometers" not in _html(client_in, 2025)


def test_the_csv_stays_in_euros(client_in):
    _trip(date(2025, 1, 5), "12")
    csv = client_in.get(reverse("reports:year_overview_csv") + "?jaar=2025").content.decode()
    assert "km" not in csv


# ---------- Het bedrag per kilometer (eigenaar 2026-11-28) ----------
# docs/belastingregels.md, sectie 8: € 0,25 in 2026, € 0,23 in 2025 en 2024.


@pytest.mark.parametrize(
    ("year", "km", "cents"),
    [
        (2026, "1842", 46050),
        (2025, "1842", 42366),
        (2024, "0.1", 2),  # 2,3 cent, half-up
        (2026, "0.1", 3),  # 2,5 cent, half-up
    ],
)
def test_the_deduction_is_the_years_amount_per_km(year, km, cents):
    from huismus.mileage.trips import deduction_cents

    assert deduction_cents(year, Decimal(km)) == cents


def test_a_year_without_a_source_has_no_amount():
    from huismus.mileage.trips import deduction_cents

    assert deduction_cents(2023, Decimal("100")) is None
    assert deduction_cents(2027, Decimal("100")) is None


def test_the_card_shows_the_amount_as_information_with_its_source(client_in):
    _trip(date(2026, 1, 5), "1842")
    html = _html(client_in, 2026).replace("\xa0", " ")
    assert "€ 0,25 per kilometer" in html
    assert "€ 460,50" in html
    assert "Huismus telt dit niet mee in je winst." in html
    assert "belastingdienst.nl" in html


def test_the_amount_is_not_in_the_profit(client_in):
    from huismus.reports.year_overview import compute_year_overview

    _trip(date(2026, 1, 5), "1842")
    overview = compute_year_overview(2026)
    assert overview.expenses_cents == 0
    assert overview.profit_cents == 0


def test_without_a_source_for_the_year_only_the_kilometres(client_in):
    _trip(date(2023, 1, 5), "100")
    html = _html(client_in, 2023)
    assert "100 km in 1 rit<" in html
    assert "per kilometer" not in html
