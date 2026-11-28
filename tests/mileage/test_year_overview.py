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
