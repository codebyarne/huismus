# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The pages of Uren (#80): the list per week with the quick form, the
filters, changing and deleting (product-owner agent 2026-11-27,
huismus-intern/besluiten.md, "Urenregistratie (#80)" and "Designkeuring
Uren (#80)")."""

import re
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.hours.models import TimeEntry
from tests.business.test_parts import client_in

pytestmark = pytest.mark.django_db

__all__ = ["client_in"]

LIST = reverse("hours:list")
TODAY = date(2026, 11, 27)


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


def _page(client, url=LIST):
    response = client.get(url)
    assert response.status_code == 200
    # Amounts keep a non-breaking space ("€ 90,00", core.templatetags.money).
    return response.content.decode().replace("\u00a0", " ")


def _add(client, contact, url=LIST, **fields):
    data = {
        "date": "2026-11-27",
        "contact": contact.pk if contact else "",
        "description": "Huisstijl",
        "hours": "1,5",
        "rate_cents": "90,00",
        **fields,
    }
    return client.post(url, data)


# ---------- Toevoegen ----------


def test_adding_stores_the_hours_and_says_so(client_in, studio):
    response = _add(client_in, studio, hours="1:20")
    assert response.status_code == 302
    entry = TimeEntry.objects.get()
    assert (entry.date, entry.contact, entry.hours, entry.rate_cents) == (
        TODAY,
        studio,
        Decimal("1.33"),
        9000,
    )
    assert entry.amount_cents == 11970
    assert "Uren toegevoegd." in _page(client_in, response.url)


def test_an_empty_rate_is_hours_you_dont_bill(client_in, studio):
    _add(client_in, studio, rate_cents="")
    assert TimeEntry.objects.get().rate_cents is None
    assert "Geen tarief" in _page(client_in)


@pytest.mark.parametrize(
    ("hours", "message"),
    [
        ("", "Vul je uren in, bijvoorbeeld 1,5 of 1:30."),
        ("anderhalf", "Vul je uren in, bijvoorbeeld 1,5 of 1:30."),
        ("0", "Vul meer dan 0 uur in."),
        ("24,5", "Eén regel kan hoogstens 24 uur zijn."),
    ],
)
def test_unclear_hours_stay_on_the_page_with_the_reason(client_in, studio, hours, message):
    response = _add(client_in, studio, hours=hours)
    assert response.status_code == 200
    html = response.content.decode()
    assert message in html
    assert re.search(r'<input[^>]*name="hours"[^>]*aria-invalid="true"', html)
    assert 'value="Huisstijl"' in html  # what was typed stays
    assert not TimeEntry.objects.exists()


def test_a_negative_rate_is_refused(client_in, studio):
    response = _add(client_in, studio, rate_cents="-5,00")
    assert "Een tarief kan niet negatief zijn." in response.content.decode()
    assert not TimeEntry.objects.exists()


def test_no_customer_is_refused(client_in, studio):
    response = _add(client_in, None)
    assert "Kies een klant." in response.content.decode()


def test_an_archived_customer_cant_get_new_hours(client_in, studio, bakery):
    bakery.archived = True
    bakery.save()
    html = _page(client_in)
    assert "Bakkerij De Korenaar" not in html
    response = _add(client_in, bakery)
    assert "Kies een klant." in response.content.decode()


def test_adding_goes_to_the_month_of_the_hours(client_in, studio):
    response = _add(client_in, studio, date="2026-10-05")
    assert response.url == f"{LIST}?maand=2026-10"


def test_adding_keeps_the_customer_filter_when_it_fits(client_in, studio):
    response = _add(client_in, studio, url=f"{LIST}?klant={studio.pk}")
    assert response.url == f"{LIST}?klant={studio.pk}"


# ---------- Het snelle formulier ----------


def test_the_form_starts_with_today_the_last_customer_and_his_rate(client_in, studio, bakery):
    _entry(bakery, date(2026, 11, 2), "1", rate=8500)
    _entry(studio, date(2026, 11, 3), "1", rate=9000)
    html = _page(client_in)
    assert 'value="2026-11-27"' in html
    assert re.search(rf'<option value="{studio.pk}" selected>', html)
    assert re.search(r'name="rate_cents" value="90,00"', html)
    # With JS a change of customer fills in his rate, from the server.
    rates = re.search(r"data-rates=\"([^\"]*)\"", html).group(1)
    assert "85,00" in rates.replace("&quot;", '"')


def test_without_earlier_hours_the_rate_is_empty(client_in, studio):
    html = _page(client_in)
    assert not re.search(r'name="rate_cents" value="', html)


@pytest.mark.parametrize(("kor", "text"), [(False, "Zonder btw."), (True, None)])
def test_the_rate_help_follows_the_vat_choice(client_in, studio, kor, text):
    settings = Settings.load()
    settings.kor_enabled = kor
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.save()
    _entry(studio, date(2026, 11, 3), "1")
    html = _page(client_in)
    assert "Laat leeg voor uren die je niet factureert." in html
    assert ("Zonder btw." in html) is (text is not None)
    assert ("Bedragen zonder btw." in html) is (text is not None)


def test_without_customers_the_form_makes_way_for_add_a_customer(client_in):
    html = _page(client_in)
    assert "Voeg eerst een klant toe." in html
    assert reverse("contacts:create") in html
    assert 'name="hours"' not in html
    assert "Nog geen uren" not in html


def test_with_only_archived_customers_their_hours_stay_in_view(client_in, studio):
    _entry(studio, date(2026, 11, 3), "2")
    studio.archived = True
    studio.save()
    html = _page(client_in)
    assert "Voeg eerst een klant toe." in html
    assert "Studio Noordlicht" in html
    assert "2 uur" in html


# ---------- De lijst ----------


def test_the_list_shows_weeks_newest_first_with_their_totals(client_in, studio, bakery):
    _entry(studio, date(2026, 11, 24), "2.5")
    _entry(bakery, date(2026, 11, 26), "2.25", rate=8500)
    _entry(studio, date(2026, 11, 26), "0.75", rate=None)
    _entry(studio, date(2026, 11, 18), "6")
    html = _page(client_in)
    assert html.index("Week 48 · 23 t/m 29 november") < html.index("Week 47 · 16 t/m 22 november")
    assert "5,5 uur · € 416,25" in html  # 2,5 × 90 + 2,25 × 85; 0,75 without a rate
    assert "6 uur · € 540,00" in html
    assert "Totaal: <strong>11,5 uur · € 956,25</strong>" in html


def test_the_list_opens_on_this_month(client_in, studio):
    _entry(studio, date(2026, 11, 3), "1")
    _entry(studio, date(2026, 10, 30), "4")
    html = _page(client_in)
    assert "Totaal: <strong>1 uur · € 90,00</strong>" in html
    assert "Filters wissen" not in html


def test_all_months(client_in, studio):
    _entry(studio, date(2026, 11, 3), "1")
    _entry(studio, date(2025, 10, 30), "4")
    html = _page(client_in, f"{LIST}?maand=alle")
    assert "Totaal: <strong>5 uur · € 450,00</strong>" in html
    assert "Filters wissen" in html
    assert "Week 44 · 27 oktober t/m 2 november 2025" not in html
    assert "Week 44 · 27 oktober t/m 2 november" in html


def test_a_week_across_months_counts_only_the_month_shown(client_in, studio):
    _entry(studio, date(2026, 11, 1), "2")  # Sunday of week 44
    _entry(studio, date(2026, 10, 28), "3")
    html = _page(client_in)
    assert "Week 44 · 26 oktober t/m 1 november" in html
    assert "2 uur · € 180,00" in html
    assert "5 uur" not in html


def test_a_week_across_years_names_the_years(client_in, studio):
    _entry(studio, date(2026, 1, 1), "1")
    html = _page(client_in, f"{LIST}?maand=2026-01")
    assert "Week 1 · 29 december 2025 t/m 4 januari 2026" in html


def test_the_customer_filter(client_in, studio, bakery):
    _entry(studio, date(2026, 11, 3), "1")
    _entry(bakery, date(2026, 11, 4), "2")
    html = _page(client_in, f"{LIST}?klant={bakery.pk}")
    assert "Totaal: <strong>2 uur · € 180,00</strong>" in html
    assert "Filters wissen" in html


def test_a_month_without_hours_offers_all_months(client_in, studio):
    _entry(studio, date(2026, 9, 3), "1")
    html = _page(client_in)
    assert "Geen uren in november 2026" in html
    assert 'href="?maand=alle"' in html
    assert "Nog geen uren" not in html


def test_no_hours_at_all(client_in, studio):
    html = _page(client_in)
    assert "Nog geen uren" in html
    assert "Vul ze hierboven in." in html


def test_months_with_hours_and_this_one_are_in_the_filter(client_in, studio):
    _entry(studio, date(2025, 3, 3), "1")
    html = _page(client_in)
    options = re.findall(r'<option value="(\d{4}-\d{2}|alle)"', html)
    assert options == ["2026-11", "2025-03", "alle"]


def test_meer_laden_keeps_one_head_per_week_with_the_whole_weeks_total(
    client_in, studio, monkeypatch
):
    from huismus.hours import views

    monkeypatch.setattr(views, "LIST_PAGE_SIZE", 2)
    for day in (25, 24, 23):
        _entry(studio, date(2026, 11, day), "1")
    html = _page(client_in)
    assert html.count("Week 48 ·") == 1
    assert "3 uur · € 270,00" in html  # the whole week, though two rows show
    assert "toon=4" in html
    html = _page(client_in, f"{LIST}?toon=4")
    assert html.count("Week 48 ·") == 1
    assert "Meer laden" not in html


def test_english(client_in, studio):
    _entry(studio, date(2026, 11, 24), "1")
    _entry(studio, date(2026, 11, 25), "0.5")
    client_in.cookies["django_language"] = "en"
    html = client_in.get(LIST, HTTP_ACCEPT_LANGUAGE="en").content.decode().replace("\u00a0", " ")
    assert "Week 48 · 23–29 November" in html
    assert "1.5 hours · € 135,00" in html
    assert "1 hour" in html


# ---------- Wijzigen en verwijderen ----------


def test_a_row_opens_its_page(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "1.5")
    assert reverse("hours:edit", args=[entry.pk]) in _page(client_in)
    html = _page(client_in, reverse("hours:edit", args=[entry.pk]))
    assert "Uren wijzigen" in html
    assert 'value="1,5"' in html
    assert "Deze uren verwijderen?" in html


def test_changing_saves_and_goes_to_its_month(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "1.5")
    response = client_in.post(
        reverse("hours:edit", args=[entry.pk]),
        {"date": "2026-10-01", "contact": studio.pk, "hours": "3", "rate_cents": "100,00"},
    )
    assert response.url == f"{LIST}?maand=2026-10"
    entry.refresh_from_db()
    assert (entry.date, entry.hours, entry.rate_cents, entry.description) == (
        date(2026, 10, 1),
        Decimal("3.00"),
        10000,
        "",
    )
    assert "Uren opgeslagen." in _page(client_in, response.url)


def test_an_archived_customer_stays_on_his_entry(client_in, studio, bakery):
    entry = _entry(studio, date(2026, 11, 3), "1")
    studio.archived = True
    studio.save()
    html = _page(client_in, reverse("hours:edit", args=[entry.pk]))
    assert re.search(rf'<option value="{studio.pk}" selected>', html)
    response = client_in.post(
        reverse("hours:edit", args=[entry.pk]),
        {"date": "2026-11-03", "contact": studio.pk, "hours": "2"},
    )
    assert response.status_code == 302


def test_deleting(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "1")
    response = client_in.post(reverse("hours:delete", args=[entry.pk]))
    assert response.url == LIST
    assert not TimeEntry.objects.exists()
    assert "Uren verwijderd." in _page(client_in)


def test_deleting_needs_a_post(client_in, studio):
    entry = _entry(studio, date(2026, 11, 3), "1")
    assert client_in.get(reverse("hours:delete", args=[entry.pk])).status_code == 405
    assert TimeEntry.objects.exists()


def test_the_pages_need_a_login(client, studio):
    entry = _entry(studio, date(2026, 11, 3), "1")
    for url in (LIST, reverse("hours:edit", args=[entry.pk])):
        assert client.get(url).status_code == 302
    client.post(reverse("hours:delete", args=[entry.pk]))
    assert TimeEntry.objects.exists()
