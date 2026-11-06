# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjes lezen (SPEC.md M20, part 3; expenses.reading_views),
against the fake service of tests/ai_fakes.py."""

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse

from huismus.core.models import Attachment
from huismus.expenses import ai_service
from huismus.expenses.ai_service import Config
from tests.ai_fakes import KEY

pytestmark = pytest.mark.django_db

URL = "/instellingen/bonnetjes-lezen/"


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


def _post(client, fake, **changes):
    data = {"provider": "other", "url": fake.url, "model": "nep-model", "key": KEY, **changes}
    return client.post(URL, data)


def test_the_address():
    assert reverse("business:receipt_reading") == URL


def test_login_required(client):
    assert client.get(URL).status_code == 302


def test_off_shows_the_choice_without_the_on_card(client_in):
    page = client_in.get(URL).content.decode()
    assert 'id="lezen-kiezen"' in page
    assert 'id="lezen-aan"' not in page
    assert "Kies een dienst" in page
    # No receipts folder yet: the page says to set one up first.
    assert 'id="eerst-bonnetjesmap"' in page


def test_known_services_carry_address_and_model(client_in):
    page = client_in.get(URL).content.decode()
    mistral = ai_service.PROVIDERS["mistral"]
    assert f'data-url="{mistral.url}"' in page
    assert f'data-model="{mistral.model}"' in page
    assert "Andere dienst" in page


def test_saving_tests_first_then_saves(client_in, ai_fake):
    response = _post(client_in, ai_fake)
    assert response.status_code == 302
    # The test image went out before anything was saved.
    assert len(ai_fake.requests) == 1
    assert ai_service.load() == Config("other", ai_fake.url, "nep-model", KEY)
    page = client_in.get(URL).content.decode()
    assert "Opgeslagen. 127.0.0.1 kan je bonnetjes lezen." in page
    assert 'id="lezen-aan"' in page


def test_the_key_is_never_shown_again(client_in, ai_fake):
    _post(client_in, ai_fake)
    page = client_in.get(URL).content.decode()
    assert KEY not in page
    assert "Leeg laten houdt de bewaarde sleutel." not in page  # a nearby address
    assert "Niet nodig voor een adres op je eigen computer of netwerk." in page


def test_empty_key_keeps_the_saved_one(client_in, ai_fake):
    _post(client_in, ai_fake)
    response = _post(client_in, ai_fake, key="")
    assert response.status_code == 302
    assert ai_service.load().key == KEY
    assert ai_fake.authorizations[-1] == f"Bearer {KEY}"


def test_a_refused_key_saves_nothing(client_in, ai_fake):
    response = _post(client_in, ai_fake, key="fout")
    assert response.status_code == 200
    page = response.content.decode()
    assert "Nog niet opgeslagen" in page
    assert "127.0.0.1 weigert je sleutel." in page
    assert not ai_service.is_on()
    assert "fout" not in page.split('name="key"')[1].split(">")[0]


def test_an_unknown_model_saves_nothing(client_in, ai_fake):
    response = _post(client_in, ai_fake, model="bestaat-niet")
    assert "kent het model bestaat-niet niet" in response.content.decode()
    assert not ai_service.is_on()


def test_a_known_service_fills_in_what_was_left_empty(client_in, monkeypatch):
    sent = []
    monkeypatch.setattr(ai_service, "test_connection", sent.append)
    response = client_in.post(URL, {"provider": "mistral", "url": "", "model": "", "key": "k"})
    assert response.status_code == 302
    mistral = ai_service.PROVIDERS["mistral"]
    assert ai_service.load() == Config("mistral", mistral.url, mistral.model, "k")
    assert sent == [ai_service.load()]


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://192.168.1.20:11434/v1",
        "http://nas.local:11434/v1",
        "http://172.20.0.1:11434/v1",
    ],
)
def test_nearby_saves_without_a_key(client_in, monkeypatch, url):
    monkeypatch.setattr(ai_service, "test_connection", lambda config: None)
    response = client_in.post(URL, {"provider": "ollama", "url": url, "model": "m", "key": ""})
    assert response.status_code == 302
    assert ai_service.load() == Config("ollama", url, "m", "")


def test_the_saved_key_never_goes_to_another_address(client_in, monkeypatch):
    monkeypatch.setattr(ai_service, "test_connection", lambda config: None)
    ai_service.save(Config("openai", "https://api.openai.com/v1", "gpt-5-mini", "sk-openai"))
    response = client_in.post(URL, {"provider": "mistral", "url": "", "model": "", "key": ""})
    assert "Vul je API-sleutel in." in response.content.decode()
    assert ai_service.load().key == "sk-openai"
    assert ai_service.load().provider == "openai"


def test_https_needs_a_key(client_in, monkeypatch):
    monkeypatch.setattr(ai_service, "test_connection", lambda config: None)
    response = client_in.post(URL, {"provider": "openai", "url": "", "model": "", "key": ""})
    assert "Vul je API-sleutel in." in response.content.decode()
    assert not ai_service.is_on()


def test_http_over_the_internet_is_refused(client_in, monkeypatch):
    monkeypatch.setattr(ai_service, "test_connection", lambda config: None)
    response = client_in.post(
        URL, {"provider": "other", "url": "http://ai.example.test/v1", "model": "m", "key": "k"}
    )
    assert "http:// werkt alleen op je eigen computer of netwerk" in response.content.decode()
    assert not ai_service.is_on()


def test_no_service_chosen(client_in):
    response = client_in.post(URL, {"provider": "", "url": "", "model": "", "key": ""})
    assert response.status_code == 200
    assert not ai_service.is_on()


def test_the_sentence_names_the_service(client_in, ai_fake, monkeypatch):
    monkeypatch.setattr(ai_service, "test_connection", lambda config: None)
    ai_service.save(Config("mistral", "https://api.mistral.ai/v1", "m", "k"))
    page = client_in.get(URL).content.decode()
    assert "naar Mistral. Mistral rekent de kosten met jou af." in page
    assert "Opslaan stuurt eerst één klein plaatje om te testen." in page


def test_the_sentence_counts_receipts_already_waiting(client_in):
    for name in ("a.pdf", "b.pdf"):
        Attachment.objects.create(file=ContentFile(b"%PDF-1.4", name=name), kind="receipt")
    page = client_in.get(URL).content.decode()
    assert "Ook de 2 bonnetjes zonder uitgave die er nu zijn." in page
    # One Huismus already read doesn't go again.
    Attachment.objects.filter(file__endswith="a.pdf").update(read_at="2026-11-06T10:00:00Z")
    page = client_in.get(URL).content.decode()
    assert "Ook het bonnetje zonder uitgave dat er nu is." in page


def test_test_connection_with_the_saved_settings(client_in, ai_fake):
    _post(client_in, ai_fake)
    response = client_in.post(URL, {"action": "test"}, follow=True)
    assert "Het werkt. 127.0.0.1 kan je bonnetjes lezen." in response.content.decode()
    ai_fake.key = "een-andere"
    response = client_in.post(URL, {"action": "test"}, follow=True)
    assert "127.0.0.1 weigert je sleutel." in response.content.decode()


def test_turn_off_forgets_service_and_key(client_in, ai_fake):
    _post(client_in, ai_fake)
    response = client_in.post(URL, {"action": "off"}, follow=True)
    assert "Bonnetjes lezen staat uit. Huismus is de sleutel vergeten." in response.content.decode()
    assert ai_service.load() == Config()


def test_english(client_in, ai_fake):
    client_in.cookies["django_language"] = "en"
    page = client_in.get(URL).content.decode()
    assert "Receipt reading" in page
    assert "Choose a service" in page
