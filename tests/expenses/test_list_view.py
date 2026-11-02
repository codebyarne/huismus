# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The expense list (M8): year, category, search, total, receipts, "Meer laden"."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone

from huismus.core.models import Attachment
from huismus.expenses import views
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory

pytestmark = pytest.mark.django_db

THIS_YEAR = timezone.localdate().year


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


def _expense(supplier, cents, year=THIS_YEAR, category=None, description=""):
    return create_expense(
        [ExpenseLineInput("", cents, None, category)],
        date=date(year, 3, 1),
        supplier=supplier,
        description=description,
    )


def _get(client, **params):
    response = client.get(reverse("expenses:list"), params)
    assert response.status_code == 200
    return response


def test_empty_state_when_there_are_no_expenses(client_in):
    assert "Nog geen uitgaven" in _get(client_in).content.decode()


def test_defaults_to_this_year_and_totals_what_matches(client_in):
    _expense("NS", 3840)
    _expense("Adobe", 2419)
    _expense("Vorig jaar", 10000, year=THIS_YEAR - 1)

    response = _get(client_in)
    assert response.context["total"] == 2
    assert response.context["total_cents"] == 3840 + 2419
    assert _get(client_in, jaar="alle").context["total_cents"] == 3840 + 2419 + 10000


def test_category_and_search_filters(client_in):
    travel = ExpenseCategory.objects.create(name="Reiskosten")
    _expense("NS", 3840, category=travel)
    _expense("Adobe", 2419, description="Creative Cloud")

    assert [e.supplier for e in _get(client_in, categorie=travel.pk).context["expenses"]] == ["NS"]
    assert [e.supplier for e in _get(client_in, q="creative").context["expenses"]] == ["Adobe"]


def test_receipt_is_marked_with_a_paperclip(client_in):
    expense = _expense("Kamera Express", 18900)
    Attachment.objects.create(
        expense=expense, kind="receipt", file=ContentFile(b"x", name="bon.pdf")
    )
    _expense("PostNL", 1562)

    rows = {e.supplier: e.has_receipt for e in _get(client_in).context["expenses"]}
    assert rows == {"Kamera Express": True, "PostNL": False}


def test_more_button_shows_more_rows_but_the_total_covers_everything(client_in, monkeypatch):
    monkeypatch.setattr(views, "LIST_PAGE_SIZE", 2)
    for cents in (100, 200, 300):
        _expense("Leverancier", cents)

    first = _get(client_in)
    assert len(first.context["expenses"]) == 2
    assert first.context["total_cents"] == 600
    second = client_in.get(reverse("expenses:list") + first.context["more_url"])
    assert len(second.context["expenses"]) == 3
    assert second.context["more_url"] is None


def test_with_a_category_the_total_counts_only_its_lines(client_in):
    # As the year overview does (huismus-intern/besluiten.md, 2026-11-02).
    software = ExpenseCategory.objects.create(name="Software")
    travel = ExpenseCategory.objects.create(name="Reiskosten")
    create_expense(
        [
            ExpenseLineInput("Hosting", 1000, None, software),
            ExpenseLineInput("Trein", 800, None, travel),
        ],
        date=date(THIS_YEAR, 3, 1),
        supplier="Gemengd",
    )

    response = _get(client_in, categorie=travel.pk)

    assert [e.supplier for e in response.context["expenses"]] == ["Gemengd"]
    assert response.context["total_cents"] == 800
    # The row shows the same part, so the rows add up to the total.
    assert [e.shown_cents for e in response.context["expenses"]] == [800]
    assert [e.shown_cents for e in _get(client_in).context["expenses"]] == [1800]


def test_search_finds_a_line_description(client_in):
    create_expense(
        [ExpenseLineInput("Visitekaartjes", 1000, None, None)],
        date=date(THIS_YEAR, 3, 1),
        supplier="Drukkerij",
    )

    assert [e.supplier for e in _get(client_in, q="visitek").context["expenses"]] == ["Drukkerij"]
