# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the user sees of Huismus reading receipts (SPEC.md M20, part 3):
the card on Instellingen, the lines in the tray, the red line, the notice
on the expense and on the overview. Against tests/ai_fakes.py."""

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from PIL import Image

from huismus.contacts.models import Contact
from huismus.core.models import Attachment
from huismus.expenses import ai_service, inbox, reading
from huismus.expenses.ai_service import Config
from tests.ai_fakes import KEY
from tests.expenses.test_reading import ANSWER

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


@pytest.fixture
def service(ai_fake):
    ai_service.save(Config("other", ai_fake.url, "nep-model", KEY))
    return ai_fake


def _receipt(name="bon.png") -> Attachment:
    out = BytesIO()
    Image.new("RGB", (40, 60), "white").save(out, "PNG")
    return Attachment.objects.create(
        file=ContentFile(out.getvalue(), name=name), kind="receipt", source=inbox.SOURCE
    )


def _card(client):
    page = client.get("/instellingen/").content.decode()
    start = page.index('href="/instellingen/bonnetjes-lezen/"')
    return page[start : start + 1500]


def test_the_card_comes_right_after_bonnetjesmap(client_in):
    page = client_in.get("/instellingen/").content.decode()
    assert page.index("/instellingen/bonnetjesmap/") < page.index("/instellingen/bonnetjes-lezen/")
    assert "Nog geen dienst gekozen" in _card(client_in)


def test_the_card_names_the_service(client_in, service):
    assert "Met 127.0.0.1" in _card(client_in)


def test_the_card_says_when_reading_failed(client_in, service):
    _receipt()
    service.key = "een-andere"
    reading.read_waiting()
    assert "Lezen is mislukt" in _card(client_in)


def test_saving_the_service_reads_what_waits(client_in, ai_fake, monkeypatch):
    monkeypatch.setattr(reading, "_start", lambda work: work())
    receipt = _receipt()
    ai_fake.answer("OK", ANSWER)
    client_in.post(
        "/instellingen/bonnetjes-lezen/",
        {"provider": "other", "url": ai_fake.url, "model": "nep-model", "key": KEY},
    )
    receipt.refresh_from_db()
    assert receipt.expense is not None


def test_the_tray_says_why_a_receipt_stayed(client_in, service):
    receipt = _receipt()
    service.answer({**ANSWER, "total": None})
    reading.read_waiting()
    page = client_in.get("/uitgaven/bonnetjes/").content.decode()
    assert "Niet gelezen: er staat geen totaal op." in page
    assert "Uitgave maken" in page
    assert f'id="bonnetje-{receipt.pk}"' in page


def test_the_tray_shows_a_receipt_huismus_will_read(client_in, service):
    _receipt()
    page = client_in.get("/uitgaven/bonnetjes/").content.decode()
    assert "Huismus leest dit bonnetje…" in page


def test_the_tray_is_red_while_the_service_fails(client_in, service):
    _receipt()
    service.key = "een-andere"
    reading.read_waiting()
    page = client_in.get("/uitgaven/bonnetjes/").content.decode()
    assert 'id="lezen-mislukt"' in page
    assert "Huismus kon je bonnetjes niet lezen. 127.0.0.1 weigert je sleutel." in page
    assert "Huismus leest dit bonnetje…" not in page
    page = client_in.get("/instellingen/bonnetjes-lezen/").content.decode()
    assert 'id="lezen-mislukt"' in page


def test_the_expense_says_which_service_read_it(client_in, service):
    _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    expense = Attachment.objects.get().expense
    # The service of that moment, also after it changed.
    ai_service.save(Config("mistral", "https://api.mistral.ai/v1", "m", "k"))
    page = client_in.get(f"/uitgaven/{expense.pk}/").content.decode()
    assert "Huismus las dit bonnetje met 127.0.0.1. Klopt alles?" in page


def test_the_overview_counts_new_expenses_to_check(client_in, service):
    # Not the welcome: an administration with something in it.
    Contact.objects.create(company_name="Klant BV")
    _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    page = client_in.get("/").content.decode()
    assert "1 nieuwe uitgave om na te kijken." in page
    client_in.get("/uitgaven/?nakijken=1")
    page = client_in.get("/").content.decode()
    assert "nieuwe uitgave om na te kijken" not in page


def test_english(client_in, service):
    client_in.cookies["django_language"] = "en"
    _receipt()
    service.answer({**ANSWER, "total": None})
    reading.read_waiting()
    page = client_in.get("/uitgaven/bonnetjes/").content.decode()
    assert "Not read: there&#x27;s no total on it." in page
