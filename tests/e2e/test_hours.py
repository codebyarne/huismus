# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uren (#80) in a real browser: switch it on, add hours with the quick
form (the rate of another customer filled in by JS), filter with HTMX,
change and delete, on a desktop and a phone."""

from datetime import timedelta
from decimal import Decimal

import pytest
from django.utils import timezone
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.hours.models import TimeEntry

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture
def customers(contact):
    return contact, Contact.objects.create(company_name="Studio Noordlicht")


def _worked_yesterday(bakery):
    """The bakery worked at € 85 an hour last time."""
    TimeEntry.objects.create(
        date=timezone.localdate() - timedelta(days=1),
        contact=bakery,
        hours=Decimal("2"),
        rate_cents=8500,
        description="Menukaart",
    )


def _switch_on(app):
    app.goto(app.base + "/instellingen/menu/")
    app.get_by_label("Uren").check()
    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    assert Settings.load().show_hours is True


def test_add_filter_change_and_delete_hours_on_a_desktop(app, customers):
    bakery, studio = customers
    app.set_viewport_size({"width": 1440, "height": 900})
    _switch_on(app)
    _worked_yesterday(bakery)
    app.locator(".sidebar nav.nav").get_by_role("link", name="Uren", exact=True).click()
    expect(app.get_by_role("heading", name="Uren", exact=True)).to_be_visible()

    # The form starts on the bakery, the last customer, at his rate; another
    # customer without hours empties it, back to the bakery fills it again.
    rate = app.get_by_label("Tarief per uur")
    expect(rate).to_have_value("85,00")
    app.locator("#id_contact").select_option(label="Studio Noordlicht")
    expect(rate).to_have_value("")
    app.locator("#id_contact").select_option(label="Bakkerij De Korrel")
    expect(rate).to_have_value("85,00")

    app.get_by_label("Omschrijving").fill("Winterkaart")
    app.get_by_label("Uren", exact=True).fill("1:30")
    app.get_by_role("button", name="Toevoegen").click()
    expect(app.get_by_text("Uren toegevoegd.")).to_be_visible()
    row = app.get_by_role("row").filter(has_text="Winterkaart")
    expect(row).to_contain_text("1,5 uur")
    expect(row).to_contain_text("€ 127,50")
    expect(app.locator(".hours-total")).to_contain_text("3,5 uur · € 297,50")

    # Hours you don't bill: no rate.
    app.locator("#id_contact").select_option(label="Studio Noordlicht")
    app.get_by_label("Uren", exact=True).fill("0,75")
    app.get_by_role("button", name="Toevoegen").click()
    expect(app.get_by_role("row").filter(has_text="Studio Noordlicht")).to_contain_text(
        "Geen tarief"
    )

    # The customer filter, with HTMX.
    app.locator("select[name=klant]").select_option(label="Studio Noordlicht")
    expect(app.locator("#uren-resultaat")).not_to_contain_text("Winterkaart")
    expect(app.get_by_role("link", name="Filters wissen")).to_be_visible()
    app.get_by_role("link", name="Filters wissen").click()
    expect(app.locator("#uren-resultaat")).to_contain_text("Winterkaart")

    # Change.
    app.get_by_role("link", name="Bakkerij De Korrel").first.click()
    expect(app.get_by_role("heading", name="Uren wijzigen")).to_be_visible()
    app.get_by_label("Uren", exact=True).fill("2,5")
    app.get_by_role("button", name="Opslaan").click()
    expect(app.get_by_text("Uren opgeslagen.")).to_be_visible()

    # Delete, after the dialog.
    app.get_by_role("link", name="Studio Noordlicht").first.click()
    app.get_by_role("button", name="Verwijderen…").click()
    dialog = app.get_by_role("dialog")
    expect(dialog).to_contain_text("Deze uren verwijderen?")
    dialog.get_by_role("button", name="Verwijderen").click()
    expect(app.get_by_text("Uren verwijderd.")).to_be_visible()
    assert TimeEntry.objects.filter(contact=studio).count() == 0
    assert TimeEntry.objects.count() == 2


def test_on_a_phone_nieuw_uren_opens_the_form_and_says_what_is_wrong(app, customers):
    Settings.objects.filter(pk=1).update(show_hours=True)
    app.set_viewport_size({"width": 390, "height": 844})
    app.goto(app.base + "/")
    app.locator("nav.tabbar").get_by_role("button", name="Nieuw").click()
    app.locator("#plus-menu").get_by_role("link", name="Uren").click()
    expect(app.get_by_label("Datum")).to_be_focused()
    expect(app.get_by_label("Datum")).to_have_value(timezone.localdate().isoformat())

    hours = app.get_by_label("Uren", exact=True)
    hours.fill("anderhalf")
    app.get_by_role("button", name="Toevoegen").click()
    expect(hours).to_have_attribute("aria-invalid", "true")
    expect(app.locator(".quick-add")).to_contain_text("Vul je uren in, bijvoorbeeld 1,5 of 1:30.")
    hours.fill("8")
    app.get_by_role("button", name="Toevoegen").click()
    expect(app.get_by_text("Uren toegevoegd.")).to_be_visible()
    # Uren lives behind "Meer" on a phone, never in the tab bar.
    expect(app.locator("nav.tabbar").get_by_role("link", name="Uren", exact=True)).to_have_count(0)
    assert TimeEntry.objects.filter(hours=8, date=timezone.localdate()).exists()
