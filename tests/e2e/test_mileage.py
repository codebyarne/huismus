# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Kilometers (#125) in a real browser: switch it on, add trips with the
quick form (Van filled in, earlier places offered), filter on the year with
HTMX, change and delete, on a desktop and a phone."""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.mileage.models import Trip

pytestmark = pytest.mark.django_db(transaction=True)


def _drove_last_year():
    Trip.objects.create(
        date=date(timezone.localdate().year - 1, 6, 1),
        origin="Utrecht",
        destination="Zwolle",
        purpose="Overleg",
        distance_km=Decimal("178"),
    )


def _switch_on(app):
    app.goto(app.base + "/instellingen/menu/")
    app.get_by_label("Kilometers").check()
    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    assert Settings.load().show_mileage is True


def test_add_filter_change_and_delete_trips_on_a_desktop(app):
    app.set_viewport_size({"width": 1440, "height": 900})
    _switch_on(app)
    _drove_last_year()
    app.locator(".sidebar nav.nav").get_by_role("link", name="Kilometers", exact=True).click()
    expect(app.get_by_role("heading", name="Kilometers", exact=True)).to_be_visible()
    expect(
        app.get_by_role("heading", name=f"Geen ritten in {timezone.localdate().year}")
    ).to_be_visible()

    # Van starts where the last trip started; Naar offers earlier places.
    expect(app.get_by_label("Van")).to_have_value("Utrecht")
    expect(app.locator("#plaatsen option[value=Zwolle]")).to_have_count(1)
    app.get_by_label("Naar").fill("Amersfoort")
    app.get_by_label("Doel").fill("Workshop")
    app.get_by_label("Kilometers", exact=True).fill("24,5")
    app.get_by_role("button", name="Toevoegen").click()
    expect(app.get_by_text("Rit toegevoegd.")).to_be_visible()
    row = app.get_by_role("row").filter(has_text="Workshop")
    expect(row).to_contain_text("Amersfoort")
    expect(row).to_contain_text("24,5 km")
    expect(app.locator(".hours-total")).to_contain_text("24,5 km")

    # The year filter, with HTMX.
    app.locator("select[name=jaar]").select_option(label="Alle jaren")
    expect(app.locator(".hours-total")).to_contain_text("202,5 km")
    expect(app.get_by_role("link", name="Filters wissen")).to_be_visible()
    app.get_by_role("link", name="Filters wissen").click()
    expect(app.locator("#ritten-resultaat")).not_to_contain_text("Overleg")

    # Change.
    app.get_by_role("link", name="Utrecht").first.click()
    expect(app.get_by_role("heading", name="Rit wijzigen")).to_be_visible()
    app.get_by_label("Kilometers", exact=True).fill("49")
    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Rit opgeslagen.")).to_be_visible()
    expect(app.get_by_role("row").filter(has_text="Workshop")).to_contain_text("49 km")

    # Delete, after the dialog.
    app.get_by_role("link", name="Utrecht").first.click()
    app.get_by_role("button", name="Verwijderen…").click()
    dialog = app.get_by_role("dialog")
    expect(dialog).to_contain_text("Deze rit verwijderen?")
    dialog.get_by_role("button", name="Verwijderen").click()
    expect(app.get_by_text("Rit verwijderd.")).to_be_visible()
    assert list(Trip.objects.values_list("purpose", flat=True)) == ["Overleg"]


def test_on_a_phone_nieuw_rit_opens_the_form_and_says_what_is_wrong(app):
    Settings.objects.filter(pk=1).update(show_mileage=True)
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/")
    app.locator("nav.tabbar").get_by_role("button", name="Nieuw").click()
    app.locator("#plus-menu").get_by_role("link", name="Rit").click()
    expect(app.get_by_label("Datum")).to_be_focused()

    app.get_by_label("Van").fill("Utrecht")
    app.get_by_label("Naar").fill("Zwolle")
    app.get_by_label("Doel").fill("Overleg")
    km = app.get_by_label("Kilometers", exact=True)
    km.fill("12,55")
    app.get_by_role("button", name="Toevoegen").click()
    expect(km).to_have_attribute("aria-invalid", "true")
    expect(app.locator(".quick-add")).to_contain_text("Hoogstens één cijfer achter de komma.")
    km.fill("89")
    app.get_by_role("button", name="Toevoegen").click()
    expect(app.get_by_text("Rit toegevoegd.")).to_be_visible()
    # Stacked, the trip reads "Utrecht → Zwolle" on one line.
    expect(app.get_by_role("link", name="Utrecht → Zwolle")).to_be_visible()
    expect(
        app.locator("nav.tabbar").get_by_role("link", name="Kilometers", exact=True)
    ).to_have_count(0)
    assert Trip.objects.filter(distance_km=89, date=timezone.localdate()).exists()


def test_the_year_overview_shows_the_years_mileage(app):
    _drove_last_year()
    last_year = timezone.localdate().year - 1
    app.goto(f"{app.base}/rapporten/jaaroverzicht/?jaar={last_year}")
    card = app.locator("#kilometers")
    expect(card).to_contain_text("Zakelijke kilometers")
    expect(card).to_contain_text("178 km in 1 rit")
    # What you may deduct, as information (owner 2026-11-28), with its source.
    if last_year in (2024, 2025, 2026):
        expect(card).to_contain_text("Huismus telt dit niet mee in je winst.")
        expect(card.get_by_role("link", name="Bron: Belastingdienst")).to_have_attribute(
            "href", re.compile("belastingdienst.nl")
        )
    card.get_by_role("link", name="Bekijk de ritten").click()
    expect(app.locator(".hours-total")).to_contain_text("178 km")


def test_a_place_without_spaces_wraps_instead_of_stretching_the_list(app):
    """Found by hand (verify-e2e, 2026-11-28): a long Van and Doel without
    spaces squeezed the other columns and pushed Km out of view."""
    Settings.objects.filter(pk=1).update(show_mileage=True)
    Trip.objects.create(
        date=timezone.localdate(),
        origin="A" * 200,
        destination="Zwolle",
        purpose="B" * 500,
        distance_km=Decimal("12"),
    )
    for width in (1440, 1024):
        app.set_viewport_size({"width": width, "height": 900})
        app.goto(app.base + "/kilometers/")
        km = app.get_by_role("cell", name="12 km", exact=True)
        expect(km).to_be_in_viewport()
        wrap = app.locator("#ritten-resultaat .table-wrap")
        assert wrap.evaluate("el => el.scrollWidth <= el.clientWidth")
        # Van keeps a column of its own instead of one letter per line.
        origin = app.locator("tr.is-link td").nth(1)
        assert origin.evaluate("el => el.getBoundingClientRect().width") > 120
        # Van and Naar weigh the same (product-owner agent 2026-11-28).
        weights = [
            app.locator("tr.is-link .row-link").first.evaluate(
                "el => getComputedStyle(el).fontWeight"
            ),
            app.locator("tr.is-link .trip-place").first.evaluate(
                "el => getComputedStyle(el).fontWeight"
            ),
        ]
        assert weights[0] == weights[1]
    # The month's head stays on one line on a phone, beside a long place too.
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/kilometers/")
    head = app.locator("tr.week-head th").first
    line = head.evaluate("el => parseFloat(getComputedStyle(el).lineHeight)")
    assert head.evaluate("el => el.getBoundingClientRect().height") < line * 1.5
