# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Nakijken": an expense an AI assistant filled in (add_expense) is marked
until the user says it's right, with "Klopt" or by saving it
(huismus-intern/besluiten.md, 2026-11-05/06, "Bonnetjes onderweg, deel 2b")."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def kor_on():
    from huismus.business.models import Settings

    settings = Settings.load()
    settings.kor_enabled = True
    settings.save()


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _expense(supplier, date=None, needs_review=False):
    expense = create_expense(
        [ExpenseLineInput(description="", amount_cents=1210, vat_info_cents=None, category=None)],
        date=date or datetime.date.today(),
        supplier=supplier,
    )
    if needs_review:
        Expense.objects.filter(pk=expense.pk).update(needs_review=True)
        expense.refresh_from_db()
    return expense


def _form(expense, **extra):
    line = expense.lines.get()
    return {
        "date": expense.date.isoformat(),
        "supplier": expense.supplier,
        "description": expense.description,
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": line.description,
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": "",
        "lines-0-category": "",
        **extra,
    }


def test_the_list_shows_the_pill_and_the_button_with_the_count_of_every_year(logged_in):
    _expense("Gamma", needs_review=True)
    _expense("Oud", date=datetime.date(2019, 3, 1), needs_review=True)
    _expense("Praxis")

    page = logged_in.get(reverse("expenses:list")).content.decode()

    assert "Nakijken (2)" in page
    assert page.count('class="pill pill-check"') == 1  # 2019 isn't shown


def test_no_button_when_nothing_is_to_check(logged_in):
    _expense("Praxis")
    assert "naar-nakijken" not in logged_in.get(reverse("expenses:list")).content.decode()


def test_the_filter_shows_only_what_to_check_of_every_year(logged_in):
    _expense("Gamma", needs_review=True)
    _expense("Oud", date=datetime.date(2019, 3, 1), needs_review=True)
    _expense("Praxis")

    page = logged_in.get(reverse("expenses:list") + "?nakijken=1").content.decode()

    assert "Gamma" in page and "Oud" in page and "Praxis" not in page
    assert "Alleen uitgaven om na te kijken." in page
    # Searching stays within the filter, also without JS.
    assert '<input type="hidden" name="nakijken" value="1">' in page
    searched = logged_in.get(reverse("expenses:list") + "?nakijken=1&q=gam&jaar=alle")
    assert "Oud" not in searched.content.decode()


def test_the_expense_shows_the_notice(logged_in):
    expense = _expense("Gamma", needs_review=True)
    page = logged_in.get(reverse("expenses:edit", args=[expense.pk])).content.decode()
    assert "Je AI-assistent vulde deze uitgave in. Klopt alles?" in page
    plain = logged_in.get(reverse("expenses:edit", args=[_expense("Praxis").pk]))
    assert "Klopt alles?" not in plain.content.decode()


def test_klopt_saves_and_goes_on_to_the_next_one(logged_in):
    first = _expense("Gamma", needs_review=True)
    second = _expense("Praxis", needs_review=True)

    response = logged_in.post(
        reverse("expenses:edit", args=[first.pk]), _form(first, supplier="Gamma BV", klopt="1")
    )

    # The order and "Overslaan": tests/expenses/test_batch.py.
    assert response.url == reverse("expenses:edit", args=[second.pk])
    first.refresh_from_db()
    assert (first.needs_review, first.supplier) == (False, "Gamma BV")


def test_klopt_on_the_last_one_goes_to_the_list(logged_in):
    expense = _expense("Gamma", needs_review=True)
    response = logged_in.post(
        reverse("expenses:edit", args=[expense.pk]), _form(expense, klopt="1"), follow=True
    )
    assert response.redirect_chain[-1][0] == reverse("expenses:list")
    assert "Uitgave nagekeken." in response.content.decode()
    # Twice (a second tab): saved again, same way, no error.
    again = logged_in.post(reverse("expenses:edit", args=[expense.pk]), _form(expense, klopt="1"))
    assert again.url == reverse("expenses:list")


def test_klopt_with_an_error_keeps_the_mark(logged_in):
    expense = _expense("Gamma", needs_review=True)
    response = logged_in.post(
        reverse("expenses:edit", args=[expense.pk]), _form(expense, date="", klopt="1")
    )
    assert response.status_code == 200
    expense.refresh_from_db()
    assert expense.needs_review


def test_saving_takes_the_mark_away_too(logged_in):
    expense = _expense("Gamma", needs_review=True)
    response = logged_in.post(reverse("expenses:edit", args=[expense.pk]), _form(expense))
    assert response.url == reverse("expenses:edit", args=[expense.pk])
    expense.refresh_from_db()
    assert not expense.needs_review


def test_an_empty_filter_says_nothing_was_found(logged_in):
    _expense("Gamma", needs_review=True)
    page = logged_in.get(reverse("expenses:list") + "?nakijken=1&q=praxis").content.decode()
    assert "Niets gevonden" in page and "Filters wissen" in page


def test_without_the_kor_klopt_still_needs_the_vat(logged_in):
    from huismus.business.models import Settings

    settings = Settings.load()
    settings.kor_enabled = False
    settings.save()
    expense = _expense("Gamma", needs_review=True)

    response = logged_in.post(
        reverse("expenses:edit", args=[expense.pk]), _form(expense, klopt="1")
    )

    assert response.status_code == 200
    assert "Vul het btw-bedrag in." in response.content.decode()
    expense.refresh_from_db()
    assert expense.needs_review
