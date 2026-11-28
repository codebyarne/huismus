# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The screens of an invoice from the hours (#81): "Factuur maken…" on
Uren, the page "Factuur maken uit uren", and hours that are on an invoice
(product-owner agent 2026-11-28, huismus-intern/besluiten.md, "Maandfactuur
uit uren (#81)")."""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.issuing import issue
from huismus.documents.models import Document
from huismus.hours.invoicing import PER_DAY, create_invoice
from huismus.hours.models import TimeEntry
from tests.business.test_parts import client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]

LIST = reverse("hours:list")
PAGE = reverse("hours:invoice")
TODAY = date(2026, 11, 27)
NOVEMBER = date(2026, 11, 1)


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *args: TODAY)


@pytest.fixture
def studio():
    return Contact.objects.create(company_name="Studio Noordlicht")


@pytest.fixture
def bakery():
    return Contact.objects.create(company_name="Bakkerij De Korenaar")


def _entry(contact, day, hours, rate=9000, description=""):
    return TimeEntry.objects.create(
        date=day, contact=contact, hours=Decimal(hours), rate_cents=rate, description=description
    )


def _page(client, url):
    response = client.get(url)
    assert response.status_code == 200
    return response.content.decode().replace(" ", " ")


# --- "Factuur maken…" on Uren -------------------------------------------------


def test_uren_offers_an_invoice_when_the_filter_shows_hours_to_invoice(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2")

    page = _page(client_in, LIST)

    assert "Factuur maken…" in page
    assert f'href="{PAGE}?maand=2026-11"' in page


def test_the_button_carries_the_filter(client_in, studio):
    _entry(studio, date(2026, 10, 3), "2")

    page = _page(client_in, f"{LIST}?klant={studio.pk}&maand=alle")

    assert f'href="{PAGE}?klant={studio.pk}&amp;maand=alle"' in page


def test_no_button_without_hours_to_invoice(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2", rate=None)
    invoiced = _entry(studio, date(2026, 11, 4), "1")
    invoiced.invoice = Document.objects.create(kind="invoice", status="draft", contact=studio)
    invoiced.save()

    assert "Factuur maken…" not in _page(client_in, LIST)


# --- the page -------------------------------------------------------------------


def test_the_page_opens_on_the_oldest_hours_to_invoice(client_in, studio, bakery):
    _entry(studio, date(2026, 11, 3), "2", description="Ontwerp")
    _entry(bakery, date(2026, 10, 7), "1.5", description="Website")
    _entry(bakery, date(2026, 9, 7), "1", rate=None)

    page = _page(client_in, PAGE)

    assert f'<option value="{bakery.pk}" selected>' in page
    assert '<option value="2026-10" selected>oktober 2026</option>' in page
    assert "Website" in page
    assert "Ontwerp" not in page
    assert "1,5 uur · € 135,00" in page
    assert "Bedragen zonder btw." in page


def test_with_a_customer_from_the_filter_his_oldest_month(client_in, studio, bakery):
    _entry(studio, date(2026, 11, 3), "2")
    _entry(studio, date(2026, 9, 3), "3")
    _entry(bakery, date(2026, 8, 7), "1")

    page = _page(client_in, f"{PAGE}?klant={studio.pk}&maand=alle")

    assert f'<option value="{studio.pk}" selected>' in page
    assert '<option value="2026-09" selected>' in page
    # Only months with hours to invoice to choose from.
    assert '<option value="2026-08"' not in page


def test_lines_per_day_and_what_stays_off(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2", description="Ontwerp")
    _entry(studio, date(2026, 11, 3), "1", description="Overleg")
    _entry(studio, date(2026, 11, 4), "1.5", rate=None, description="Bellen")

    page = _page(client_in, f"{PAGE}?klant={studio.pk}&maand=2026-11&per=dag")

    assert "3 november: Ontwerp; Overleg" in page
    assert "1,5 uur zonder tarief komt niet op de factuur." in page
    assert "Op Uren is dit" not in page


def test_the_page_names_a_difference_with_uren(client_in, studio):
    for day in (3, 4, 5):
        _entry(studio, date(2026, 11, day), "0.5", rate=3333)

    page = _page(client_in, f"{PAGE}?klant={studio.pk}&maand=2026-11")

    assert (
        "Op Uren is dit € 50,01. Het verschil komt doordat de factuur de uren per regel optelt."
        in page
    )


def test_a_month_without_hours_to_invoice_says_so(client_in, studio):
    _entry(studio, date(2026, 10, 3), "2")
    create_invoice(studio, date(2026, 10, 1), PER_DAY)
    _entry(studio, date(2026, 11, 3), "2", rate=None)

    page = _page(client_in, f"{PAGE}?klant={studio.pk}&maand=2026-11")

    assert "Geen uren om te factureren voor Studio Noordlicht in november 2026." in page
    assert "Uren zonder tarief en uren die al op een factuur staan, tellen niet mee." in page
    assert "Conceptfactuur maken" not in page


def test_under_the_kor_nothing_about_vat(client_in, studio):
    settings = Settings.load()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.save()
    _entry(studio, date(2026, 11, 3), "2")

    assert "btw" not in _page(client_in, PAGE).split("<main", 1)[1].split("</main>")[0].lower()


def test_making_the_draft_opens_it(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2", description="Ontwerp")
    _entry(studio, date(2026, 11, 4), "1.5", description="Ontwerp")

    response = client_in.post(PAGE, {"klant": studio.pk, "maand": "2026-11", "per": "omschrijving"})

    invoice = Document.objects.get()
    assert response.status_code == 302
    assert response.url == reverse("documents:edit", args=[invoice.pk])
    assert invoice.time_entries.count() == 2
    page = _page(client_in, response.url)
    assert "Conceptfactuur gemaakt met 3,5 uur." in page
    assert "Ontwerp" in page


def test_a_second_click_makes_nothing(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2")
    data = {"klant": studio.pk, "maand": "2026-11", "per": "dag"}
    client_in.post(PAGE, data)

    response = client_in.post(PAGE, data, follow=True)

    # Afterwards (not at the same moment, see test_invoicing) the page says
    # there are none left.
    assert Document.objects.count() == 1
    assert "Geen uren om te factureren voor Studio Noordlicht" in response.content.decode()


def test_a_click_at_the_same_moment_says_the_hours_are_taken(client_in, studio, monkeypatch):
    from huismus.hours import invoicing

    _entry(studio, date(2026, 11, 3), "2")

    def taken(*args):
        raise invoicing.AlreadyInvoiced

    monkeypatch.setattr(invoicing, "create_invoice", taken)
    data = {"klant": studio.pk, "maand": "2026-11", "per": "dag"}
    response = client_in.post(PAGE, data, follow=True)

    assert "Deze uren staan al op een factuur." in response.content.decode()


def test_the_page_in_english(client_in, studio):
    client_in.cookies["django_language"] = "en"
    _entry(studio, date(2026, 11, 3), "2", rate=None)

    page = _page(client_in, f"{PAGE}?klant={studio.pk}&maand=2026-11")

    assert "Invoice from hours" in page
    assert "No hours to invoice for Studio Noordlicht in November 2026." in page


# --- hours on an invoice --------------------------------------------------------


def test_uren_names_the_invoice_an_entry_is_on(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2")
    draft = create_invoice(studio, NOVEMBER, PER_DAY)
    _entry(studio, date(2026, 11, 10), "2")
    issued = issue(create_invoice(studio, NOVEMBER, PER_DAY))

    page = _page(client_in, LIST)

    assert f'href="{reverse("documents:edit", args=[draft.pk])}">Conceptfactuur</a>' in page
    assert f">Factuur {issued.number}</a>" in page


def test_hours_on_an_invoice_cant_be_changed_or_deleted(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "2")
    invoice = issue(create_invoice(studio, NOVEMBER, PER_DAY))
    edit = reverse("hours:edit", args=[entry.pk])

    page = _page(client_in, edit)
    client_in.post(edit, {"date": "2026-11-03", "contact": studio.pk, "hours": "9"})
    client_in.post(reverse("hours:delete", args=[entry.pk]))

    assert f"Deze uren staan op factuur {invoice.number}." in page
    assert "Verwijderen…" not in page
    assert 'name="hours"' not in page
    entry.refresh_from_db()
    assert entry.hours == Decimal("2")


def test_hours_on_a_draft_say_how_to_free_them(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "2")
    draft = create_invoice(studio, NOVEMBER, PER_DAY)

    page = _page(client_in, reverse("hours:edit", args=[entry.pk]))
    editor = _page(client_in, reverse("documents:edit", args=[draft.pk]))

    assert "Deze uren staan op een conceptfactuur. Verwijder het concept om ze te wijzigen." in page
    assert f'href="{reverse("documents:edit", args=[draft.pk])}">Open het concept' in page
    assert "De uren komen weer vrij op Uren." in editor


def test_deleting_the_draft_frees_them_on_uren(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "2")
    draft = create_invoice(studio, NOVEMBER, PER_DAY)

    client_in.post(reverse("documents:delete", args=[draft.pk]))

    entry.refresh_from_db()
    assert entry.invoice is None
    assert "Factuur maken…" in _page(client_in, LIST)


def test_a_draft_for_an_archived_customer_keeps_him_in_the_editor(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2")
    studio.archived = True
    studio.save()
    client_in.post(PAGE, {"klant": studio.pk, "maand": "2026-11", "per": "dag"})
    draft = Document.objects.get()

    page = _page(client_in, reverse("documents:edit", args=[draft.pk]))

    assert "Studio Noordlicht" in page
