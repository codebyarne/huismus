# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The pages of Kilometers (#125): the list per month with the quick form,
the filter per year, changing and deleting (product-owner agent 2026-11-28,
huismus-intern/besluiten.md, "Kilometerregistratie (#125)")."""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from huismus.mileage import views
from huismus.mileage.models import Trip
from tests.business.test_parts import client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]

LIST = reverse("mileage:list")
TODAY = date(2026, 11, 28)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args: TODAY)


def _trip(day, km="12.5", origin="Utrecht", destination="Zwolle", purpose="Klant"):
    return Trip.objects.create(
        date=day, origin=origin, destination=destination, purpose=purpose, distance_km=Decimal(km)
    )


def _page(client, url=LIST):
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode()


def _add(client, url=LIST, **fields):
    data = {
        "date": "2026-11-28",
        "origin": "Utrecht",
        "destination": "Amersfoort",
        "purpose": "Workshop bij Studio Noordlicht",
        "distance_km": "24,5",
        **fields,
    }
    return client.post(url, data)


# ---------- Toevoegen ----------


def test_adding_stores_the_trip_and_says_so(client_in):
    response = _add(client_in, origin=" Utrecht ")
    assert response.status_code == 302
    assert response.url == LIST
    trip = Trip.objects.get()
    assert (trip.date, trip.origin, trip.destination, trip.distance_km) == (
        TODAY,
        "Utrecht",
        "Amersfoort",
        Decimal("24.5"),
    )
    assert "Rit toegevoegd." in _page(client_in)


def test_a_trip_in_another_year_goes_back_to_that_year(client_in):
    response = _add(client_in, date="2025-03-04")
    assert response.url == f"{LIST}?jaar=2025"


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("origin", "", "Vul in waar de rit begon."),
        ("origin", "   ", "Vul in waar de rit begon."),
        ("destination", "", "Vul in waar de rit naartoe ging."),
        ("purpose", "", "Vul het doel van de rit in."),
        ("distance_km", "", "Vul de kilometers in, bijvoorbeeld 12,5."),
        ("distance_km", "twaalf", "Vul de kilometers in, bijvoorbeeld 12,5."),
        ("distance_km", "0", "Vul meer dan 0 km in."),
        ("distance_km", "2000,1", "Eén rit kan hoogstens 2.000 km zijn."),
        ("distance_km", "12,55", "Hoogstens één cijfer achter de komma."),
    ],
)
def test_errors_say_what_to_do_and_keep_what_was_typed(client_in, field, value, error):
    response = _add(client_in, **{field: value})
    assert response.status_code == 200
    html = response.content.decode()
    assert error in html
    assert "Workshop bij Studio Noordlicht" in html or field == "purpose"
    assert not Trip.objects.exists()


def test_the_quick_form_starts_today_with_the_last_origin(client_in):
    _trip(date(2026, 1, 2), origin="Arnhem")
    _trip(date(2025, 1, 2), origin="Delft")  # entered last, an older date
    html = _page(client_in)
    assert re.search(r'name="date"[^>]*value="2026-11-28"', html)
    assert re.search(r'name="origin"[^>]*value="Delft"', html)
    assert not re.search(r'name="destination"[^>]*value=', html)


def test_van_and_naar_offer_earlier_places_newest_first_each_once(client_in):
    _trip(date(2026, 1, 2), origin="Arnhem", destination="Utrecht")
    _trip(date(2026, 2, 2), origin="Utrecht", destination="Zwolle")
    html = _page(client_in)
    places = re.search(r'<datalist id="plaatsen">(.*?)</datalist>', html).group(1)
    assert re.findall(r'value="([^"]+)"', places) == ["Utrecht", "Zwolle", "Arnhem"]
    assert re.search(r'name="origin"[^>]*list="plaatsen"', html)


def test_at_most_thirty_places_are_offered(client_in):
    for n in range(40):
        _trip(date(2026, 1, 2), origin=f"Van {n}", destination=f"Naar {n}")
    html = _page(client_in)
    places = re.search(r'<datalist id="plaatsen">(.*?)</datalist>', html).group(1)
    assert places.count("<option") == 30


# ---------- De lijst ----------


def test_nothing_yet(client_in):
    html = _page(client_in)
    assert "Nog geen ritten" in html
    assert "Alle jaren" not in html  # no filter without trips


def test_this_year_per_month_with_totals(client_in):
    _trip(date(2026, 11, 3), "12.5")
    _trip(date(2026, 11, 20), "100", destination="Groningen")
    _trip(date(2026, 10, 1), "1000")
    _trip(date(2025, 6, 1), "7")
    html = _page(client_in)
    assert "Totaal: <strong>1.112,5 km</strong>" in html
    assert "November 2026 · 112,5 km" in html
    assert "Oktober 2026 · 1.000 km" in html
    assert "Juni 2025" not in html
    assert html.index("Groningen") < html.index("Oktober 2026")


def test_an_empty_year_says_so_and_offers_all_years(client_in):
    _trip(date(2024, 6, 1))
    html = _page(client_in)
    assert "Geen ritten in 2026" in html
    assert 'href="?jaar=alle"' in html
    assert '<option value="2024"' in html


def test_all_years_and_another_year(client_in):
    _trip(date(2024, 6, 1), "7")
    _trip(date(2026, 6, 1), "8")
    html = _page(client_in, f"{LIST}?jaar=alle")
    assert "Totaal: <strong>15 km</strong>" in html
    assert "Filters wissen" in html
    html = _page(client_in, f"{LIST}?jaar=2024")
    assert "Totaal: <strong>7 km</strong>" in html
    assert re.search(r'<option value="2024" selected', html)


def test_a_wrong_year_shows_this_year(client_in):
    _trip(date(2026, 6, 1), "8")
    assert "Totaal: <strong>8 km</strong>" in _page(client_in, f"{LIST}?jaar=tja")


def test_meer_laden_never_repeats_a_month_and_totals_the_whole_month(client_in, monkeypatch):
    monkeypatch.setattr(views, "LIST_PAGE_SIZE", 2)
    for day in (1, 2, 3):
        _trip(date(2026, 11, day), "10")
    _trip(date(2026, 10, 1), "5")
    html = _page(client_in)
    assert "November 2026 · 30 km" in html
    assert html.count('<tr class="is-link">') == 2
    more = re.search(r'href="(\?toon=4)"', html).group(1)
    html = _page(client_in, LIST + more)
    assert html.count("November 2026") == 1
    assert "Oktober 2026 · 5 km" in html
    assert "Meer laden" not in html


# ---------- Wijzigen en verwijderen ----------


def test_changing_a_trip(client_in):
    trip = _trip(date(2025, 3, 1))
    url = reverse("mileage:edit", args=[trip.pk])
    html = _page(client_in, url)
    assert "Rit wijzigen" in html
    assert re.search(r'name="distance_km"[^>]*value="12,5"', html)
    response = _add(client_in, url, date="2025-03-02", distance_km="30")
    assert response.url == f"{LIST}?jaar=2025"
    trip.refresh_from_db()
    assert trip.distance_km == Decimal("30.0")
    assert "Rit opgeslagen." in _page(client_in, response.url)


def test_a_whole_number_is_shown_without_decimal(client_in):
    trip = _trip(date(2026, 3, 1), "30")
    html = _page(client_in, reverse("mileage:edit", args=[trip.pk]))
    assert re.search(r'name="distance_km"[^>]*value="30"', html)


def test_deleting_a_trip(client_in):
    trip = _trip(date(2026, 3, 1))
    html = _page(client_in, reverse("mileage:edit", args=[trip.pk]))
    assert "Deze rit verwijderen?" in html
    assert client_in.get(reverse("mileage:delete", args=[trip.pk])).status_code == 405
    response = client_in.post(reverse("mileage:delete", args=[trip.pk]))
    assert response.url == LIST
    assert not Trip.objects.exists()
    assert "Rit verwijderd." in _page(client_in)


def test_an_unknown_trip_is_not_found(client_in):
    assert client_in.get(reverse("mileage:edit", args=[99])).status_code == 404


def test_html_in_a_trip_is_shown_as_text(client_in):
    _trip(date(2026, 3, 1), purpose="<b>vet</b>")
    html = _page(client_in)
    assert "&lt;b&gt;vet&lt;/b&gt;" in html


def test_english(client_in):
    _trip(date(2026, 3, 1), "1842")
    client_in.cookies["django_language"] = "en"
    html = _page(client_in, f"{LIST}?jaar=alle")
    assert "Total: <strong>1,842 km</strong>" in html
    assert "March 2026 · 1,842 km" in html
