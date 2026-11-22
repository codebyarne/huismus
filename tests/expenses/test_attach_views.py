# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
""" "Bij bestaande uitgave" in the tray and "Hoort bij een uitgave die er al
is?" in Verwerken: "Bij welke uitgave hoort dit bonnetje?" (#127)."""

import datetime

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.core.models import Attachment
from huismus.expenses import batch
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def user(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _expense(supplier="Drukkerij", cents=1250, day=3, needs_review=False):
    category, _made = ExpenseCategory.objects.get_or_create(name="Kantoor")
    expense = Expense.objects.create(
        date=datetime.date(2026, 3, day),
        supplier=supplier,
        amount_cents=cents,
        needs_review=needs_review,
    )
    expense.lines.create(category=category, amount_cents=cents)
    return expense


def _receipt(name="bon.pdf", **extra):
    return Attachment.objects.create(
        file=ContentFile(b"%PDF-1.4", name=name), kind="receipt", sha256=name * 4, **extra
    )


def _page(receipt, **params):
    return reverse("expenses:tray_attach", args=[receipt.pk]), params


def _get(client, receipt, **params):
    url, params = _page(receipt, **params)
    return client.get(url, params)


def test_the_page_needs_a_login(client):
    receipt = _receipt()
    assert client.get(reverse("expenses:tray_attach", args=[receipt.pk])).status_code == 302


def test_the_tray_offers_it_for_every_receipt(client, user):
    receipt = _receipt()
    response = client.get(reverse("expenses:tray"))
    assert reverse("expenses:tray_attach", args=[receipt.pk]).encode() in response.content
    assert "Bij bestaande uitgave" in response.text


def test_without_a_search_it_lists_the_expenses_without_a_receipt(client, user):
    without = _expense("Zonder")
    with_receipt = _expense("Met")
    Attachment.objects.create(
        expense=with_receipt, file=ContentFile(b"x", name="a.pdf"), kind="receipt"
    )
    response = _get(client, _receipt())
    assert response.status_code == 200
    assert f'id="kies-{without.pk}"' in response.text
    assert f'id="kies-{with_receipt.pk}"' not in response.text
    assert "Uitgaven zonder bonnetje" in response.text


def test_newest_first(client, user):
    old, new = _expense("Oud", day=1), _expense("Nieuw", day=20)
    text = _get(client, _receipt()).text
    assert text.index(f'id="kies-{new.pk}"') < text.index(f'id="kies-{old.pk}"')


def test_searching_finds_every_expense_also_one_with_a_receipt(client, user):
    with_receipt = _expense("Koffiebar")
    Attachment.objects.create(
        expense=with_receipt, file=ContentFile(b"x", name="a.pdf"), kind="receipt"
    )
    other = _expense("Drukkerij")
    text = _get(client, _receipt(), q="koffie").text
    assert f'id="kies-{with_receipt.pk}"' in text
    assert f'id="kies-{other.pk}"' not in text
    assert "Met bonnetje" in text


def test_searching_on_the_amount(client, user):
    hit, miss = _expense("A", cents=1250), _expense("B", cents=999)
    for query in ("12,50", "€ 12,50", "12.50"):
        text = _get(client, _receipt(name=f"{query}.pdf"), q=query).text
        assert f'id="kies-{hit.pk}"' in text, query
        assert f'id="kies-{miss.pk}"' not in text, query


def test_what_it_looks_like_comes_first_and_only_once(client, user):
    similar = _expense("Lijkt erop")
    receipt = _receipt(read_similar=similar)
    text = _get(client, receipt).text
    assert 'id="lijkt-op"' in text
    assert "Lijkt op dit bonnetje" in text
    assert text.count(f'id="kies-{similar.pk}"') == 1
    assert text.index('id="lijkt-op"') < text.index(f'id="kies-{similar.pk}"')


def test_no_expenses_yet(client, user):
    receipt = _receipt()
    text = _get(client, receipt).text
    assert 'id="geen-uitgaven"' in text
    assert batch.Item(batch.RECEIPT, receipt.pk).url() in text


def test_every_expense_has_a_receipt(client, user):
    expense = _expense()
    Attachment.objects.create(expense=expense, file=ContentFile(b"x", name="a.pdf"), kind="receipt")
    assert 'id="alles-met-bonnetje"' in _get(client, _receipt()).text


def test_nothing_found(client, user):
    _expense()
    assert 'id="niets-gevonden"' in _get(client, _receipt(), q="bestaat niet").text


def test_more_expenses_load_twenty_at_a_time(client, user):
    for day in range(1, 26):
        _expense(f"Winkel {day}", day=day)
    text = _get(client, _receipt()).text
    assert text.count('id="kies-') == 20
    assert "toon=40" in text
    assert _get(client, _receipt(name="b.pdf"), toon=40).text.count('id="kies-') == 25


def test_choosing_puts_it_on_the_expense_and_goes_back_to_the_tray(client, user):
    expense, receipt = _expense(), _receipt()
    url, _params = _page(receipt)

    response = client.post(url, {"uitgave": expense.pk})

    assert response.status_code == 302
    assert response.url == f"{reverse('expenses:tray')}?gekoppeld={receipt.pk}"
    receipt.refresh_from_db()
    assert receipt.expense == expense
    expense.refresh_from_db()
    assert not expense.needs_review


def test_an_expense_on_nakijken_stays_there(client, user):
    expense, receipt = _expense(needs_review=True), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})
    expense.refresh_from_db()
    assert expense.needs_review


def test_the_notice_after_choosing(client, user):
    expense, receipt = _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})

    text = client.get(reverse("expenses:tray"), {"gekoppeld": receipt.pk}).text

    assert 'id="bonnetje-gekoppeld"' in text
    assert "Bonnetje hangt nu aan je uitgave van" in text
    assert reverse("expenses:edit", args=[expense.pk]) in text
    assert reverse("expenses:tray_attach_undo", args=[receipt.pk]) in text


def test_no_notice_for_a_receipt_still_in_the_tray(client, user):
    receipt = _receipt()
    text = client.get(reverse("expenses:tray"), {"gekoppeld": receipt.pk}).text
    assert 'id="bonnetje-gekoppeld"' not in text


def test_undo_puts_it_back_and_returns_to_the_same_page(client, user):
    expense, receipt = _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})
    place = f"{reverse('expenses:tray')}?gekoppeld={receipt.pk}"

    response = client.post(
        reverse("expenses:tray_attach_undo", args=[receipt.pk]),
        {"uitgave": expense.pk, "plek": place},
        follow=True,
    )

    # The same page, without the notice that has nothing to say any more.
    assert response.redirect_chain[-1][0] == reverse("expenses:tray")
    assert Attachment.objects.in_tray().filter(pk=receipt.pk).exists()
    assert "Het bonnetje staat weer bij de bonnetjes zonder uitgave." in response.text
    assert 'id="bonnetje-gekoppeld"' not in response.text


def test_undo_goes_nowhere_else(client, user):
    expense, receipt = _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})
    response = client.post(
        reverse("expenses:tray_attach_undo", args=[receipt.pk]),
        {"uitgave": expense.pk, "plek": "https://elders.example/"},
    )
    assert response.url == reverse("expenses:tray")


def test_undo_once_it_no_longer_hangs_there(client, user):
    first, second, receipt = _expense(), _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": first.pk})

    response = client.post(
        reverse("expenses:tray_attach_undo", args=[receipt.pk]),
        {"uitgave": second.pk, "plek": reverse("expenses:tray")},
        follow=True,
    )

    assert "Dit bonnetje hangt niet meer aan die uitgave." in response.text
    receipt.refresh_from_db()
    assert receipt.expense == first


def test_a_receipt_taken_meanwhile(client, user):
    expense, receipt = _expense(), _receipt()
    url = _page(receipt)[0]
    client.post(url, {"uitgave": expense.pk})

    response = client.post(url, {"uitgave": _expense().pk}, follow=True)

    assert "Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave." in response.text
    receipt.refresh_from_db()
    assert receipt.expense == expense


def test_an_unknown_expense(client, user):
    receipt = _receipt()
    assert client.post(_page(receipt)[0], {"uitgave": 999}).status_code == 404
    assert Attachment.objects.in_tray().filter(pk=receipt.pk).exists()


# -- From Verwerken -------------------------------------------------------------------


def test_verwerken_links_to_it_for_a_receipt(client, user):
    receipt = _receipt()
    text = client.get(batch.Item(batch.RECEIPT, receipt.pk).url(2)).text
    assert 'id="bij-bestaande"' in text
    assert f"{reverse('expenses:tray_attach', args=[receipt.pk])}?terug=verwerken&amp;klaar=2" in (
        text
    )


def test_verwerken_has_no_link_for_an_expense_to_check(client, user):
    expense = _expense(needs_review=True)
    text = client.get(batch.Item(batch.EXPENSE, expense.pk).url()).text
    assert 'id="bij-bestaande"' not in text


def test_from_verwerken_the_back_link_and_the_fields_go_along(client, user):
    _expense()
    text = _get(client, _receipt(), terug="verwerken", klaar=2).text
    assert f'href="{reverse("expenses:process")}?klaar=2"' in text
    assert 'name="terug" value="verwerken"' in text


def test_choosing_from_verwerken_goes_on_to_the_next_one(client, user):
    expense = _expense()
    older = _receipt("oud.pdf")
    receipt = _receipt("nieuw.pdf")

    response = client.post(
        _page(receipt)[0], {"uitgave": expense.pk, "terug": "verwerken", "klaar": "2"}
    )

    next_url = batch.Item(batch.RECEIPT, older.pk).url(3)
    assert response.url == f"{next_url}&gekoppeld={receipt.pk}"
    text = client.get(response.url).text
    assert 'id="bonnetje-gekoppeld"' in text


def test_choosing_the_last_one_from_verwerken(client, user):
    expense, receipt = _expense(), _receipt()
    response = client.post(
        _page(receipt)[0], {"uitgave": expense.pk, "terug": "verwerken"}, follow=True
    )
    assert 'id="niets-te-verwerken"' in response.text
    assert 'id="bonnetje-gekoppeld"' in response.text


def test_undo_goes_back_only_to_the_tray_or_verwerken(client, user):
    expense, receipt = _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})
    response = client.post(
        reverse("expenses:tray_attach_undo", args=[receipt.pk]),
        {"uitgave": expense.pk, "plek": reverse("expenses:tray_delete", args=[receipt.pk])},
    )
    assert response.url == reverse("expenses:tray")


def test_undo_in_verwerken_goes_back_to_that_receipt_not_done(client, user):
    expense, receipt = _expense(), _receipt()
    client.post(_page(receipt)[0], {"uitgave": expense.pk})
    place = (
        f"{reverse('expenses:process_item', args=['bonnetje', 7])}?klaar=3&gekoppeld={receipt.pk}"
    )

    response = client.post(
        reverse("expenses:tray_attach_undo", args=[receipt.pk]),
        {"uitgave": expense.pk, "plek": place},
    )

    assert response.url == batch.Item(batch.RECEIPT, receipt.pk).url(2)
