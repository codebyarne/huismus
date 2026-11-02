# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen as an overview with a page per topic (SPEC.md M14)."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business import smtp
from huismus.business.models import Settings
from huismus.business.topics import TOPICS, cards

pytestmark = pytest.mark.django_db


@pytest.fixture
def client_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _complete_business():
    settings = Settings.load()
    settings.business_name = "Atelier Zonnig"
    settings.address_line1 = "Lindenlaan 3"
    settings.postal_code = "3511 AB"
    settings.city = "Utrecht"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "hallo@example.invalid"
    settings.save()
    return settings


def _card(settings, slug):
    return next(card for card in cards(settings) if card["slug"] == slug)


def test_the_overview_links_to_every_topic(client_in):
    page = client_in.get(reverse("business:overview")).content.decode()

    for topic in TOPICS:
        assert reverse("business:topic", args=[topic.slug]) in page
        assert str(topic.title) in page


@pytest.mark.parametrize("slug", [topic.slug for topic in TOPICS])
def test_every_topic_page_opens_on_a_fresh_installation(client_in, slug):
    response = client_in.get(reverse("business:topic", args=[slug]))

    assert response.status_code == 200
    assert reverse("business:overview") in response.content.decode()


@pytest.mark.parametrize("topic", TOPICS, ids=lambda topic: topic.slug)
def test_every_field_of_a_topic_is_on_its_page(client_in, topic):
    # A field in the form but not on the page would fail invisibly.
    page = client_in.get(reverse("business:topic", args=[topic.slug])).content.decode()

    for name in topic.fields:
        assert f'name="{name}"' in page, name


def test_an_unknown_topic_is_not_found(client_in):
    assert client_in.get(reverse("business:topic", args=["onbekend"])).status_code == 404


def test_a_topic_saves_only_its_own_fields(client_in):
    _complete_business()

    response = client_in.post(
        reverse("business:topic", args=["kor"]),
        {
            "kor_enabled": "on",
            "kor_text": "Eigen tekst",
            "kor_limit_cents": "20000.00",
            "kor_warning_percent": "75",
            "business_name": "Iets anders",
        },
    )

    assert response.status_code == 302
    assert response.url == reverse("business:topic", args=["kor"])
    settings = Settings.load()
    assert (settings.kor_text, settings.kor_warning_percent) == ("Eigen tekst", 75)
    assert settings.business_name == "Atelier Zonnig"


def test_bedrijf_says_whether_every_required_field_is_filled_in():
    settings = Settings.load()
    assert _card(settings, "bedrijf")["pill"][0] == "Niet compleet"

    settings = _complete_business()
    card = _card(settings, "bedrijf")
    assert card["pill"][0] == "Compleet"
    assert card["line"] == "Atelier Zonnig · Utrecht"


def test_kor_shows_the_limit_and_percentage_the_user_set():
    settings = Settings.load()
    settings.kor_limit_cents = 2_500_050
    settings.kor_warning_percent = 90
    settings.save()

    card = _card(settings, "kor")

    assert card["line"] == "Grens €\u00a025.000,50 · waarschuwen vanaf 90%"
    assert card["pill"][0] == "Uit"
    settings.kor_enabled = True
    assert _card(settings, "kor")["pill"][0] == "Aan"


def test_mailen_says_through_what_it_mails_once_set_up():
    settings = _complete_business()
    assert _card(settings, "mailen")["pill"][0] == "Uit"

    settings.smtp_provider = "gmail"
    settings.smtp_host = "smtp.gmail.com"
    smtp.set_password("geheim")
    card = _card(settings, "mailen")

    assert card["pill"][0] == "Gmail"
    assert card["line"] == "via hallo@example.invalid"


def test_huisstijl_shows_the_logo_only_when_there_is_one():
    card = _card(Settings.load(), "huisstijl")

    assert (card["line"], card["pill"]) == ("Nog geen logo", None)


def test_the_test_mail_comes_back_to_the_mail_page(client_in):
    response = client_in.post(reverse("business:test_mail"))

    assert response.url == reverse("business:topic", args=["mailen"])


def test_the_pills_say_on_and_off_in_english():
    # "Aan" is also a mail's "To": the pills have a context of their own.
    from django.utils import translation

    settings = Settings.load()
    with translation.override("en"):
        assert str(_card(settings, "kor")["pill"][0]) == "Off"
        settings.kor_enabled = True
        assert str(_card(settings, "kor")["pill"][0]) == "On"
