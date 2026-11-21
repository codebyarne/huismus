# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Money going out on Bank (#257): proposals under Te doen, Niet herkend
with Uitgave maken and its tabs, the expense made from a line, and undo
from both sides. Every action a plain POST."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from huismus.bank import views
from huismus.bank.models import BankTransaction
from huismus.business.models import Settings
from huismus.expenses.models import Expense

from .test_reading import _camt as _camt_in
from .test_reading import _invoice
from .test_reading_going_out import _camt, _expense

pytestmark = pytest.mark.django_db

State = BankTransaction.State
PAGE = "/bank/"


@pytest.fixture
def client(client):
    from .test_reading import _settings as settings_fixture

    settings_fixture.__wrapped__()
    user = get_user_model().objects.create_user("demo", password="pw-123456789")
    client.force_login(user)
    return client


def _upload(client, data):
    return client.post(PAGE, {"bestand": SimpleUploadedFile("sep.xml", data)}, follow=True)


def _text(page):
    return page.text.replace("\xa0", " ")


def test_a_proposal_for_an_expense_is_under_te_doen_and_confirms(client):
    hosting = _expense(2420, day=date(2026, 9, 1))
    page = _upload(client, _camt(("24.20", "Hosting Noord B.V.", "2026-09-26")))
    text = _text(page)
    assert "Af · uitgave" in text
    assert " · Hosting Noord · € 24,20" in text
    assert "Bij deze uitgave mist het bonnetje." in text
    assert views.to_do_count() == 1
    line = BankTransaction.objects.get()
    page = client.post(reverse("bank:confirm", args=[line.pk]), {"terug": PAGE}, follow=True)
    line.refresh_from_db()
    assert (line.state, line.expense) == (State.CONFIRMED, hosting)
    assert "Afschrijving geboekt bij de uitgave." in page.text
    assert views.to_do_count() == 0


def test_an_expense_with_the_amount_is_under_te_doen_first_in_the_list(client):
    ns = _expense(6130, supplier="NS", day=date(2026, 9, 1))
    page = _upload(client, _camt(("61.30", "NS Reizigers", "2026-09-23")))
    text = _text(page)
    assert "Er is al een uitgave met dit bedrag. Is het die? Kies hem dan en boek." in text
    assert f'<option value="{ns.pk}" selected>' in text
    assert views.to_do_count() == 1
    line = BankTransaction.objects.get()
    client.post(reverse("bank:book", args=[line.pk]), {"uitgave": ns.pk, "terug": PAGE})
    line.refresh_from_db()
    assert (line.state, line.expense) == (State.CONFIRMED, ns)


def test_a_line_that_fits_nothing_asks_nothing(client):
    page = _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    text = _text(page)
    assert views.to_do_count() == 0
    assert 'id="niet-herkend"' in text
    line = BankTransaction.objects.get()
    assert f"/uitgaven/nieuw/?afschrijving={line.pk}" in text
    assert "Maak er dan een uitgave van." in text


def test_the_af_tile_has_the_euros_that_went_out(client):
    _invoice(1000, company="Klant Een")
    data = _camt(("412.00", "Bol.com", "2026-09-25"), ("24.20", "Hosting", "2026-09-26"))
    text = _text(_upload(client, data))
    assert "€ 436,20" in text
    assert "die koppel je later" not in text


def _both_sides(client, outgoing=1):
    lines = [(f"{10 + i}.00", f"Winkel {i}", "2026-09-25") for i in range(outgoing)]
    _upload(client, _camt(*lines))
    _upload(client, _camt_in(("12.34", "Iemand", "iets")))


def test_niet_herkend_has_tabs_when_both_sides_are_there(client):
    _both_sides(client)
    text = _text(client.get(PAGE))
    assert "Alles (2)" in text and "Bij (1)" in text and "Af (1)" in text
    only_out = _text(client.get(PAGE + "?kant=af"))
    assert "Winkel 0" in only_out and "Iemand" not in only_out
    # A tab opens the section.
    assert '<details class="fold" id="niet-herkend" open>' in only_out


def test_no_tabs_with_one_side(client):
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    assert "Alles (" not in _text(client.get(PAGE))


def test_twenty_lines_then_toon_meer(client):
    _both_sides(client, outgoing=25)
    text = _text(client.get(PAGE + "?kant=af"))
    assert text.count("?afschrijving=") == 20
    assert "Toon meer (5 nog)" in text
    more = _text(client.get(PAGE + "?kant=af&toon=40"))
    assert more.count("?afschrijving=") == 25
    assert "Toon meer" not in more


def test_after_an_action_back_on_the_same_tab(client):
    _both_sides(client)
    line = BankTransaction.objects.get(amount_cents__lt=0)
    back = PAGE + "?kant=af"
    response = client.post(reverse("bank:skip", args=[line.pk]), {"terug": back})
    assert response.url == back


# Uitgave maken


def _new_expense_url(line):
    return reverse("expenses:create") + f"?afschrijving={line.pk}&terug=/bank/%3Fkant%3Daf"


def _form(line, **fields):
    data = {
        "date": "2026-09-25",
        "supplier": "Bol.com",
        "description": "Bestelling 4021-3381",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "1",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "",
        "lines-0-amount_cents": "412,00",
        "lines-0-vat_info_cents": "71,50",
        "lines-0-vat_rate": "21",
        "lines-0-category": "",
    }
    return data | fields


def test_uitgave_maken_fills_in_what_the_bank_knows(client):
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    text = _text(client.get(_new_expense_url(line)))
    assert 'value="2026-09-25"' in text
    assert 'value="Bol.com"' in text
    assert 'value="412,00"' in text
    assert "Uit je bankafschrift: − € 412,00 aan Bol.com op" in text
    # The VAT stays empty: the bank doesn't know it.
    assert 'name="lines-0-vat_info_cents" value' not in text
    assert 'href="/bank/?kant=af"' in text


def test_saving_it_links_the_line_and_goes_back_to_bank(client):
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    response = client.post(_new_expense_url(line), _form(line))
    assert response.url == "/bank/?kant=af"
    expense = Expense.objects.get()
    line.refresh_from_db()
    assert (line.state, line.expense) == (State.CONFIRMED, expense)
    assert expense.amount_cents == 41200  # gross (CLAUDE.md rule 7)
    page = _text(client.get(response.url))
    assert "Uitgave bewaard. De afschrijving staat nu bij Geboekt." in page
    assert "Uitgave · Bestelling 4021-3381" in page


def test_without_the_kor_the_vat_is_asked_and_nothing_is_linked_yet(client):
    assert not Settings.load().kor_enabled
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    page = client.post(_new_expense_url(line), _form(line, **{"lines-0-vat_info_cents": ""}))
    assert page.status_code == 200
    assert "Vul het btw-bedrag in." in page.text
    line.refresh_from_db()
    assert line.state == State.OPEN and not Expense.objects.exists()


def test_a_line_booked_meanwhile_saves_no_second_expense(client):
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    url = _new_expense_url(line)
    client.post(url, _form(line))
    response = client.post(url, _form(line), follow=True)
    assert Expense.objects.count() == 1
    assert "Deze afschrijving is al geboekt." in response.text


def test_the_expense_shows_its_bank_line_and_undo_keeps_it(client):
    _upload(client, _camt(("412.00", "Bol.com", "2026-09-25")))
    line = BankTransaction.objects.get()
    client.post(_new_expense_url(line), _form(line))
    expense = Expense.objects.get()
    page_url = reverse("expenses:edit", args=[expense.pk])
    text = _text(client.get(page_url))
    assert "Afgeschreven op" in text
    assert "uit bankafschrift: Bol.com" in text
    response = client.post(reverse("bank:undo", args=[line.pk]), {"terug": page_url}, follow=True)
    assert "Koppeling teruggedraaid. De uitgave blijft staan" in response.text
    assert Expense.objects.filter(pk=expense.pk).exists()
    line.refresh_from_db()
    assert line.state == State.OPEN
    assert "Afgeschreven op" not in _text(client.get(page_url))
    # The expense is the first choice again, under Te doen.
    assert views.to_do_count() == 1
