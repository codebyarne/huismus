# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Input VAT on the year overview (SPEC.md M21, part 3; issue #99;
product-owner agent 2026-11-07, huismus-intern/besluiten.md, "Voorbelasting
op uitgaven"). With the KOR off, per expense line: at 21, 9 or 0% the
costs are gross minus VAT and the VAT is input VAT; reverse charged or
without a rate, the costs are gross. With the KOR on everything stays
gross. Stored amounts never change (CLAUDE.md, hard rule 7)."""

from datetime import date

import pytest

from huismus.business.models import Settings
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory, VatRate
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


def _kor(on: bool):
    settings = Settings.load()
    settings.kor_enabled = on
    settings.save()


def _expense(day, *lines):
    """lines: (gross, vat, rate, category)."""
    return create_expense(
        [ExpenseLineInput("", gross, vat, category, rate) for gross, vat, rate, category in lines],
        date=day,
    )


@pytest.fixture
def year():
    office = ExpenseCategory.objects.create(name="Kantoor")
    travel = ExpenseCategory.objects.create(name="Reizen")
    _expense(
        date(2026, 1, 10), (12100, 2100, VatRate.HIGH, office), (1090, 90, VatRate.LOW, travel)
    )
    _expense(date(2026, 2, 1), (5000, 0, VatRate.ZERO, office))
    _expense(date(2026, 4, 2), (20000, 4200, VatRate.REVERSE_EU, office))
    _expense(date(2026, 7, 3), (3000, 500, "", travel))  # no rate: never input VAT
    _expense(date(2026, 10, 4), (2420, None, "", None))
    return office, travel


def test_without_the_kor_costs_are_without_vat_and_input_vat_is_apart(year):
    _kor(False)

    overview = compute_year_overview(2026)

    gross = 12100 + 1090 + 5000 + 20000 + 3000 + 2420
    assert overview.input_vat_cents == 2100 + 90
    assert overview.expenses_cents == gross - 2190
    assert [q.input_vat_cents for q in overview.quarters] == [2190, 0, 0, 0]
    assert [q.expenses_cents for q in overview.quarters] == [16000, 20000, 3000, 2420]
    assert sum(q.expenses_cents for q in overview.quarters) == overview.expenses_cents
    assert overview.shows_input_vat


def test_without_the_kor_categories_are_without_vat_and_add_up(year):
    _kor(False)

    overview = compute_year_overview(2026)

    by_name = {c.name: c.amount_cents for c in overview.by_category}
    assert by_name == {
        "Kantoor": 10000 + 5000 + 20000,
        "Reizen": 1000 + 3000,
        "Zonder categorie": 2420,
    }
    assert sum(by_name.values()) == overview.expenses_cents


def test_profit_is_revenue_minus_costs_without_vat(year):
    _kor(False)

    overview = compute_year_overview(2026)

    assert overview.profit_cents == overview.revenue_cents - overview.expenses_cents


def test_with_the_kor_everything_stays_gross(year):
    _kor(True)

    overview = compute_year_overview(2026)

    assert overview.input_vat_cents == 0
    assert overview.expenses_cents == 12100 + 1090 + 5000 + 20000 + 3000 + 2420
    assert not overview.shows_input_vat


def test_stored_amounts_do_not_change(year):
    from huismus.expenses.models import Expense, ExpenseLine

    before = list(ExpenseLine.objects.values_list("amount_cents", "vat_info_cents"))
    totals = list(Expense.objects.values_list("amount_cents", "vat_info_cents"))
    _kor(False)

    compute_year_overview(2026)

    assert list(ExpenseLine.objects.values_list("amount_cents", "vat_info_cents")) == before
    assert list(Expense.objects.values_list("amount_cents", "vat_info_cents")) == totals


def _login(client):
    from django.contrib.auth import get_user_model

    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def test_the_page_shows_costs_without_vat_and_input_vat(client, year):
    from django.urls import reverse

    _kor(False)
    _login(client)

    content = client.get(reverse("reports:year_overview"), {"jaar": "2026"}).content.decode()

    assert "Kosten zonder btw" in content
    assert "Voorbelasting €\u00a021,90" in content
    assert "Kosten zonder btw per categorie" in content
    assert "Kosten zijn bruto" not in content


def test_with_the_kor_the_page_is_as_before(client, year):
    from django.urls import reverse

    _kor(True)
    _login(client)

    content = client.get(reverse("reports:year_overview"), {"jaar": "2026"}).content.decode()

    assert "Kosten zonder btw" not in content
    assert "Voorbelasting" not in content


def test_the_csv_has_input_vat_only_without_the_kor(client, year):
    from django.urls import reverse

    _login(client)
    _kor(False)
    lines = (
        client.get(reverse("reports:year_overview_csv"), {"jaar": "2026"})
        .content.decode("utf-8-sig")
        .splitlines()
    )
    assert lines[0] == "kwartaal;omzet;kosten zonder btw;voorbelasting;winst"
    assert lines[1] == "Q1;0,00;160,00;21,90;-160,00"
    _kor(True)
    lines = (
        client.get(reverse("reports:year_overview_csv"), {"jaar": "2026"})
        .content.decode("utf-8-sig")
        .splitlines()
    )
    assert lines[0] == "kwartaal;omzet;kosten;winst"
    assert lines[1] == "Q1;0,00;181,90;-181,90"


def test_the_overview_card_follows(client, year):
    from django.urls import reverse
    from django.utils import timezone

    if timezone.localdate().year != 2026:
        pytest.skip("the overview shows this year")
    from huismus.contacts.models import Contact

    Contact.objects.create(company_name="Klant BV")  # past the welcome
    _kor(False)
    _login(client)
    assert "Kosten zonder btw" in client.get(reverse("home")).content.decode()


def test_the_ai_connection_follows(year):
    from huismus.assistants.tools import list_expenses

    _kor(False)
    data = list_expenses({"year": 2026})
    assert (data["total"], data["total_without_vat"], data["input_vat"]) == (
        "€ 414,20",
        True,
        "€ 21,90",
    )
    _kor(True)
    data = list_expenses({"year": 2026})
    assert (data["total"], data["total_without_vat"]) == ("€ 436,10", False)
    assert "input_vat" not in data
