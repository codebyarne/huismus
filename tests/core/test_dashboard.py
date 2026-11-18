# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Overzicht page (M8): core.dashboard and the home view."""

from datetime import timedelta

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone, translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.dashboard import month_bars, onboarding_steps, outstanding_invoices
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment

pytestmark = pytest.mark.django_db

TODAY = timezone.localdate()


@pytest.fixture
def settings_filled():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.save()
    return settings


def _issued(cents, due_date=None, paid=0, kind="invoice", related=None):
    contact = Contact.objects.create(company_name="Klant BV")
    document = Document.objects.create(
        kind=kind, status="draft", contact=contact, due_date=due_date, related_document=related
    )
    DocumentLine.objects.create(
        document=document, description="Werk", quantity="1", unit_price_cents=cents
    )
    document = issue(document)
    if paid:
        Payment.objects.create(document=document, paid_on=TODAY, amount_cents=paid)
    return document


def test_outstanding_sums_what_is_still_owed_and_counts_overdue(settings_filled):
    _issued(100000)
    _issued(50000, paid=20000)
    _issued(30000, due_date=TODAY - timedelta(days=3))
    _issued(40000, paid=40000)  # paid: not outstanding
    credited = _issued(25000)
    _issued(25000, kind="credit_note", related=credited)  # fully credited

    summary = outstanding_invoices()

    assert summary["total_cents"] == 100000 + 30000 + 30000
    assert summary["count"] == 3
    assert summary["overdue_count"] == 1


def test_outstanding_says_how_much_of_it_is_overdue(settings_filled):
    _issued(100000)
    _issued(30000, due_date=TODAY - timedelta(days=3))
    _issued(50000, due_date=TODAY - timedelta(days=1), paid=20000)  # partly paid, overdue
    _issued(80000, due_date=TODAY - timedelta(days=9), paid=80000)  # paid: not overdue

    summary = outstanding_invoices()

    assert summary["overdue_cents"] == 30000 + 30000
    assert summary["total_cents"] == 100000 + 30000 + 30000
    assert summary["has_issued"] is True
    # The invoices themselves, the one that fell due last first.
    assert [d.days_overdue for d in summary["overdue"]] == [1, 3]


def test_outstanding_before_the_first_invoice_is_empty(settings_filled):
    summary = outstanding_invoices()
    assert summary == {
        "count": 0,
        "total_cents": 0,
        "overdue_count": 0,
        "overdue_cents": 0,
        "overdue": [],
        "has_issued": False,
    }


def test_onboarding_steps_follow_what_exists(settings_filled):
    steps = {step["key"]: step["done"] for step in onboarding_steps()}
    assert steps == {
        "business": True,
        "logo": False,
        "kor": False,
        "contact": False,
        "invoice": False,
    }

    Contact.objects.create(company_name="Klant BV")
    assert {s["key"]: s["done"] for s in onboarding_steps()}["contact"] is True


def test_home_shows_the_welcome_until_there_is_anything(client, settings_filled):
    user = get_user_model().objects.create_user(
        username="lotte", password="s3cret-pass", first_name="Lotte"
    )
    client.force_login(user)

    first = client.get(reverse("home"))
    assert first.context["first_time"] is True
    assert "Welkom bij Huismus" in first.content.decode()

    _issued(12100)
    later = client.get(reverse("home"))
    assert later.context["first_time"] is False
    assert later.context["outstanding"]["total_cents"] == 12100
    # The page is called Overzicht; no greeting (besluiten.md, 2026-11-18).
    assert "<h1>Overzicht</h1>" in later.content.decode()


def _kor_on(settings, *, limit_cents=1_000_000, warning_percent=80):
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld van btw (KOR)."
    settings.kor_limit_cents = limit_cents
    settings.kor_warning_percent = warning_percent
    settings.save()


@pytest.fixture
def logged_in(client):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


def test_without_the_kor_the_overview_says_nothing_about_a_limit(logged_in, settings_filled):
    _issued(5_000_000)
    page = logged_in.get(reverse("home")).content.decode()
    assert "KOR-grens" not in page


def test_with_the_kor_the_revenue_card_shows_the_share_of_the_limit(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(250_000)
    page = logged_in.get(reverse("home")).content.decode()
    page = page.replace("\xa0", " ")
    # Its own tile beside the petrol block: the bar, in petrol, and what is left.
    assert 'id="kor-grens"' in page and 'id="winst"' not in page
    assert "€ 2.500,00 van € 10.000,00" in page
    assert 'class="progress is-kor" role="img" aria-label="25% van je KOR-grens"' in page
    assert "Nog € 7.500,00 tot de grens" in page
    assert 'id="kor-melding"' not in page


def test_from_the_warning_percentage_a_banner_shows(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(850_000)
    page = logged_in.get(reverse("home")).content.decode()
    assert 'id="kor-melding"' in page
    assert "85% van je KOR-grens" in page
    assert f"?jaar={TODAY.year}" in page
    # No amber: the bar stays petrol up to the limit.
    assert 'class="progress is-kor" role="img"' in page


def test_above_the_limit_the_banner_says_so(logged_in, settings_filled):
    _kor_on(settings_filled)
    _issued(1_000_001)
    response = logged_in.get(reverse("home"))
    assert response.context["kor_limit"].level == "over"
    page = response.content.decode()
    assert "hoger dan je KOR-grens" in page
    # Only over the limit the bar is red, and nothing is left to count down.
    assert 'class="progress is-kor is-bad"' in page
    assert "tot de grens" not in page


def test_the_kor_or_vat_step_is_done_with_the_kor_and_its_text(settings_filled):
    settings_filled.kor_enabled = True
    settings_filled.kor_text = "Vrijgesteld van btw (KOR)."
    settings_filled.save()
    step = next(s for s in onboarding_steps() if s["key"] == "kor")
    assert step["done"] is True
    assert str(step["title"]) == "KOR of btw instellen"


def test_the_kor_or_vat_step_is_done_without_the_kor_and_with_a_vat_number(settings_filled):
    settings_filled.kor_enabled = False
    settings_filled.vat_number = ""
    settings_filled.save()
    assert next(s for s in onboarding_steps() if s["key"] == "kor")["done"] is False
    settings_filled.vat_number = "NL000099998B57"
    settings_filled.save()
    assert next(s for s in onboarding_steps() if s["key"] == "kor")["done"] is True


def test_the_query_filter_leaves_out_no_open_invoice(settings_filled):
    """outstanding_invoices() narrows the query for speed; payment_state
    still decides. Every invoice it decides is open must be counted."""
    _issued(100000)
    _issued(50000, paid=20000)
    _issued(40000, paid=40000)
    credited = _issued(25000)
    _issued(25000, kind="credit_note", related=credited)
    _issued(0)  # € 0, nothing paid: "unpaid"

    every = Document.objects.filter(kind="invoice", status="issued").with_payment_totals()
    open_count = sum(1 for d in every if d.payment_state in ("unpaid", "partial"))

    assert outstanding_invoices()["count"] == open_count == 3


def _home(client):
    user = get_user_model().objects.create_user(username="sam", password="s3cret-pass")
    client.force_login(user)
    return client.get(reverse("home")).content.decode().replace("\xa0", " ")


def test_the_menu_panel_shows_no_amount(client, settings_filled):
    """The amount is the overview's; the panel only has the menu
    (huismus-intern/besluiten.md, 2026-11-15)."""
    _issued(100000)

    html = _home(client)

    sidebar = html[html.index('<aside class="sidebar"') : html.index("</aside>")]
    assert "€" not in sidebar
    assert "Je krijgt nog" not in html


def test_an_overview_without_invoices_shows_one_card_to_make_the_first(client, settings_filled):
    Contact.objects.create(company_name="Klant BV")  # past the welcome

    html = _home(client)

    assert 'id="nog-geen-facturen"' in html
    assert "Eerste factuur maken" in html
    assert "Importeren uit Moneybird" in html
    assert "Openstaand" not in html
    assert "Laatste facturen" not in html


def test_home_lists_drafts_and_what_waits_in_verwerken_under_te_doen(client, settings_filled):
    from huismus.expenses.models import Expense

    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    _issued(10000)

    calm = client.get(reverse("home")).content.decode()
    assert 'id="niets-te-doen"' in calm and "Er wacht niets op je." in calm
    assert 'id="te-doen-teller"' not in calm

    contact = Contact.objects.create(company_name="Concept Klant")
    draft = Document.objects.create(
        kind="invoice", status="draft", contact=contact, total_cents=9500
    )
    Expense.objects.create(date=TODAY, supplier="Acme", amount_cents=100, needs_review=True)

    response = client.get(reverse("home"))
    page = response.content.decode()

    assert 'id="niets-te-doen"' not in page
    assert "Je concept voor Concept Klant staat klaar" in page
    assert f'href="{reverse("documents:edit", args=[draft.pk])}"' in page
    assert "1 uitgave om na te kijken" in page
    assert f'href="{reverse("expenses:list")}?nakijken=1"' in page
    assert response.context["todo"].count == 2
    assert '<span class="count-badge" id="te-doen-teller">2</span>' in page
    # Work comes below the figures, above the latest invoices.
    assert page.index("kpi-value") < page.index('id="te-doen"') < page.index("Laatste facturen")


def test_home_shows_the_bars_and_what_is_still_to_come_in(logged_in, settings_filled):
    _issued(12100, due_date=TODAY - timedelta(days=2))

    response = logged_in.get(reverse("home"))
    page = response.content.decode()

    bars = response.context["month_bars"]
    assert sum(bar.revenue_cents for bar in bars) == response.context["overview"].revenue_cents
    assert page.count('<span class="month-bar') == 12
    assert 'class="month-bar is-current" style="--v:100"' in page
    assert f"Omzet per maand in {TODAY.year}" in page
    assert "Nog te ontvangen" in page and "1 factuur, 1 te laat" in page
    assert "?tab=openstaand" in page
    # Without the KOR: the profit, not a limit.
    assert 'id="winst"' in page and 'id="kor-grens"' not in page


def test_with_nothing_open_the_tile_says_so(logged_in, settings_filled):
    _issued(5000, paid=5000)
    assert "Niets openstaand" in logged_in.get(reverse("home")).content.decode()


def test_without_invoices_te_doen_shows_only_when_something_waits(client, settings_filled):
    from huismus.expenses.models import Expense

    Contact.objects.create(company_name="Klant BV")
    client.force_login(get_user_model().objects.create_user(username="sam", password="x"))
    assert 'id="te-doen"' not in client.get(reverse("home")).content.decode()

    Expense.objects.create(date=TODAY, supplier="Acme", amount_cents=100, needs_review=True)
    assert "1 uitgave om na te kijken" in client.get(reverse("home")).content.decode()


# The bars in the petrol block (#215): what the template needs per month.
# The amounts come from the year overview; here only how high and how drawn.


def test_month_bars_scale_to_the_best_month_and_mark_the_current_one():
    bars = month_bars([5000, 10000, 2500, 0, 0, 0, 0, 0, 0, 0, 0, 0], current_month=3)

    assert len(bars) == 12
    assert [bar.height_percent for bar in bars[:4]] == [50, 100, 25, 0]
    assert [bar.revenue_cents for bar in bars[:3]] == [5000, 10000, 2500]
    assert [bar.is_current for bar in bars[:4]] == [False, False, True, False]
    # Still to come and nothing in it yet: a dashed line, not a bar.
    assert [bar.is_ahead for bar in bars] == [False] * 3 + [True] * 9
    assert all(isinstance(bar.height_percent, int) for bar in bars)


def test_month_bars_name_each_month_in_full_short_and_one_letter():
    bars = month_bars([0] * 12, current_month=12)

    with translation.override("nl"):
        assert (str(bars[2].name), str(bars[2].short), bars[2].letter) == ("maart", "mrt", "m")
    with translation.override("en"):
        assert (str(bars[2].name), str(bars[2].short), bars[2].letter) == ("March", "mar", "m")


def test_a_month_below_zero_or_a_year_without_revenue_has_no_height():
    assert [bar.height_percent for bar in month_bars([0] * 12, current_month=6)] == [0] * 12
    bars = month_bars([-300, 600] + [0] * 10, current_month=2)
    assert [bar.height_percent for bar in bars[:2]] == [0, 100]


def test_a_month_ahead_with_revenue_already_is_a_bar():
    """An invoice dated next month counts in the year, so it shows."""
    bars = month_bars([1000, 0, 500] + [0] * 9, current_month=1)
    assert (bars[2].is_ahead, bars[2].height_percent) == (False, 50)
    assert bars[1].is_ahead
