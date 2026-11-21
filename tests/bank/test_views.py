# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank → Bankafschrift inlezen (#77): the page, its blocks and every
action as a plain POST."""

from datetime import date

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from huismus.bank.models import BankTransaction
from huismus.bank.views import summary_text
from huismus.documents.models import Document, Payment

from .test_reading import _camt, _invoice

pytestmark = pytest.mark.django_db

State = BankTransaction.State
PAGE = "/bank/"


@pytest.fixture
def client(client, _settings):
    user = get_user_model().objects.create_user("demo", password="pw-123456789")
    client.force_login(user)
    return client


@pytest.fixture
def _settings():
    from .test_reading import _settings as settings_fixture

    settings_fixture.__wrapped__()


def _upload(client, data, name="nov.xml"):
    return client.post(PAGE, {"bestand": SimpleUploadedFile(name, data)}, follow=True)


def test_bank_is_its_own_menu_item_not_a_button_on_facturen(client):
    # Owner 2026-11-21: one statement holds both sides, so one place.
    _invoice(1000)
    assert reverse("bank:statement") == PAGE
    page = client.get(PAGE)
    assert page.status_code == 200
    assert "<h1>Bank</h1>" in page.text
    assert f'href="{PAGE}" aria-current="page"' in page.text
    assert "bankafschrift-knop" not in client.get("/facturen/").text


def test_reading_shows_the_summary_and_the_blocks(client):
    sure = _invoice(121000, company="Bakkerij De Korst")
    likely = _invoice(60500, company="Studio Noord")
    page = _upload(
        client,
        _camt(
            ("1210.00", "Bakkerij De Korst", f"Factuur {sure.number}"),
            ("700.00", "Studio Noord", f"Factuur {likely.number}"),
            ("12.34", "Iemand", "iets"),
        ),
    )
    text = page.text.replace("\xa0", " ")
    assert "3 bijschrijvingen gelezen. 1 geboekt, 1 om te bevestigen, 1 om zelf te kiezen." in text
    assert 'id="geboekt"' in text and 'id="te-doen"' in text and 'id="niet-herkend"' in text
    assert "data-voorstel" in text
    assert "€ 95,00 meer dan er open staat." in text


def test_the_same_file_again_says_nothing_new(client):
    data = _camt(("12.34", "Iemand", "iets"))
    _upload(client, data)
    page = _upload(client, data)
    assert "Niets nieuws: alle bijschrijvingen in dit bestand waren al ingelezen." in page.text


def test_a_wrong_file_says_so(client):
    page = client.post(PAGE, {"bestand": SimpleUploadedFile("foto.jpg", b"\xff\xd8\xff")})
    assert page.status_code == 200
    assert "Huismus herkent dit bestand niet als bankafschrift." in page.text


def test_confirm_books_the_proposal(client):
    invoice = _invoice(60500, company="Studio Noord")
    _upload(client, _camt(("605.00", "Studio Noord", "bedankt")))
    line = BankTransaction.objects.get()
    client.post(reverse("bank:confirm", args=[line.pk]), {"terug": PAGE})
    line.refresh_from_db()
    assert line.state == State.CONFIRMED
    assert line.payment.document == invoice


def test_book_on_a_chosen_invoice_and_undo_from_the_invoice(client):
    invoice = _invoice(121000)
    _upload(client, _camt(("12.34", "Iemand", "iets")))
    line = BankTransaction.objects.get()
    client.post(reverse("bank:book", args=[line.pk]), {"factuur": invoice.pk})
    detail = client.get(reverse("documents:edit", args=[invoice.pk])).text
    assert "uit bankafschrift: Iemand" in detail
    assert reverse("bank:undo", args=[line.pk]) in detail

    back = reverse("documents:edit", args=[invoice.pk])
    page = client.post(reverse("bank:undo", args=[line.pk]), {"terug": back}, follow=True)
    assert page.redirect_chain[-1][0] == back
    assert "Betaling teruggedraaid. Hij staat weer bij Te doen." in page.text
    assert not Payment.objects.exists()


def test_book_without_an_invoice_books_nothing(client):
    _upload(client, _camt(("12.34", "Iemand", "iets")))
    line = BankTransaction.objects.get()
    page = client.post(reverse("bank:book", args=[line.pk]), {"factuur": ""}, follow=True)
    assert "Kies een factuur." in page.text
    assert not Payment.objects.exists()


def test_a_payment_by_hand_has_no_undo_on_the_invoice(client):
    invoice = _invoice(1000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 11, 1), amount_cents=1000)
    detail = client.get(reverse("documents:edit", args=[invoice.pk])).text
    assert "Terugdraaien" not in detail


def test_skip_and_restore(client):
    _upload(client, _camt(("1.00", "A", "een"), ("2.00", "B", "twee")))
    first, second = BankTransaction.objects.all()
    client.post(reverse("bank:skip", args=[first.pk]))
    client.post(reverse("bank:skip", args=[second.pk]))
    assert not BankTransaction.objects.waiting().exists()
    skipped = client.get(reverse("bank:skipped"))
    assert skipped.text.count("Terugzetten") == 2
    assert "Overgeslagen (2)" in client.get(PAGE).text
    client.post(reverse("bank:restore", args=[first.pk]))
    assert BankTransaction.objects.waiting().count() == 1


def test_a_line_that_fits_no_invoice_waits_folded_and_asks_nothing(client):
    """Direction D (owner 2026-11-21): a line that fits no invoice is often
    private money. It goes to Niet herkend, folded, and the overview doesn't
    count it as something to do."""
    _invoice(121000, company="Bakkerij De Korst")
    _upload(client, _camt(("63.18", "Supermarkt De Hoek", "pinbetaling")))
    text = client.get(PAGE).text
    assert '<details class="fold" id="niet-herkend">' in text
    assert "Als factuurbetaling markeren" in text
    assert "betaling uit je bankafschrift" not in client.get("/").text


def test_a_hint_when_the_text_names_more_than_one_invoice(client):
    a, b = _invoice(1000), _invoice(2000)
    page = _upload(client, _camt(("30.00", "Klant BV", f"{a.number} en {b.number}")))
    assert "Deze betaling noemt meer dan één factuur." in page.text


def test_back_never_leaves_huismus(client):
    _upload(client, _camt(("1.00", "A", "een")))
    line = BankTransaction.objects.get()
    response = client.post(
        reverse("bank:skip", args=[line.pk]), {"terug": "https://example.invalid/"}
    )
    assert response.url == PAGE


def test_te_doen_counts_what_waits_first(client):
    # Each line fits an invoice by its amount: something to do.
    _invoice(100)
    _invoice(200)
    _upload(client, _camt(("1.00", "A", "een"), ("2.00", "B", "twee")))
    home = client.get("/").text
    assert "2 betalingen uit je bankafschrift wachten op je" in home
    assert home.index('data-todo="bank"') < home.find('data-todo="te-laat"') or (
        'data-todo="te-laat"' not in home
    )


def test_too_much_paid_is_never_shown_as_negative_open(client):
    invoice = _invoice(1000)
    Payment.objects.create(document=invoice, paid_on=date(2026, 11, 1), amount_cents=1500)
    detail = client.get(reverse("documents:edit", args=[invoice.pk])).text
    assert "Te veel betaald" in detail
    assert Document.objects.get(pk=invoice.pk).payment_state == "paid"
    # Nowhere a negative open amount: the invoice, the list, the overview
    # with Te doen (product-owner agent 2026-11-20).
    for path in (reverse("documents:edit", args=[invoice.pk]), "/facturen/", "/"):
        text = client.get(path).text.replace("\xa0", " ")
        assert "-5,00" not in text and "−5,00" not in text and "-€" not in text, path


def test_summary_text_counts_what_went_out():
    assert summary_text({"read": 2, "booked": 2, "outgoing": 4}) == (
        "2 bijschrijvingen gelezen. 2 geboekt. "
        "4 afschrijvingen: die koppel je later aan je uitgaven."
    )


def test_summary_text_leaves_out_what_is_zero():
    assert summary_text(
        {"read": 1, "booked": 1, "seen_before": 2, "accounts": ["NL91ABNA0417164300"]}
    ) == (
        "1 bijschrijving gelezen. 1 geboekt. 2 waren al ingelezen. "
        "Van rekening NL91 ABNA 0417 1643 00."
    )


def test_the_pages_need_a_login():
    from django.test import Client

    assert Client().get(PAGE).status_code == 302
