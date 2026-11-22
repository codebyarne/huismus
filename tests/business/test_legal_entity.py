# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The legal form as a choice (#302, huismus-intern/product/profiel-en-functies.md
section 2a): stored in Settings.legal_entity, next to the free text
legal_form, which stays as it is. A suggestion only from unambiguous text,
or from an old answer in "Hoe gebruik je Huismus?"; it counts only once saved."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from huismus.business.legal_entity import suggestion
from huismus.business.models import Settings
from huismus.core.profile import profile


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Eenmanszaak", "eenmanszaak"),
        ("eenmanszaak ", "eenmanszaak"),
        ("vof", "vof"),
        ("V.O.F.", "vof"),
        ("v.o.f", "vof"),
        ("Vennootschap onder firma", "vof"),
        ("B.V.", "bv"),
        ("bv", "bv"),
        ("BV", "bv"),
        ("Besloten vennootschap", "bv"),
        ("Stichting", "stichting"),
        ("vereniging", "vereniging"),
    ],
)
def test_unambiguous_text_gives_a_suggestion(text, expected):
    assert suggestion(Settings(legal_form=text)) == expected


@pytest.mark.parametrize(
    "text",
    [
        "zzp",
        "ZZP'er",
        "eenmanszaak/vof",
        "holding",
        "cv",
        "Bv i.o.",
        "nv",
        "Anders",
        "B.V. holding",
    ],
)
def test_other_text_gives_none(text):
    assert suggestion(Settings(legal_form=text)) == ""


@pytest.mark.parametrize(
    ("answer", "expected"),
    [
        ("bv", "bv"),
        ("stichting", "stichting"),
        ("vereniging", "vereniging"),
        # "Eenmanszaak of vof": which of the two, Huismus doesn't guess.
        ("kor", ""),
        ("btw", ""),
        ("anders", ""),
        ("", ""),
    ],
)
def test_without_text_the_old_card_answer(answer, expected):
    assert suggestion(Settings(feedback_organisation=answer)) == expected


def test_the_text_goes_before_the_card_answer():
    instance = Settings(legal_form="Stichting", feedback_organisation="bv")
    assert suggestion(instance) == "stichting"


def test_text_without_a_suggestion_falls_back_to_the_card_answer():
    assert suggestion(Settings(legal_form="holding", feedback_organisation="bv")) == "bv"


def test_a_choice_made_gives_no_suggestion():
    assert suggestion(Settings(legal_entity="anders", legal_form="B.V.")) == ""


def test_the_profile_counts_only_the_stored_choice():
    assert profile(Settings(legal_form="B.V.", feedback_organisation="bv")).legal_entity == ""
    assert profile(Settings(legal_entity="vof")).legal_entity == "vof"


def test_the_six_choices():
    assert [key for key, _label in Settings._meta.get_field("legal_entity").choices] == [
        "eenmanszaak",
        "vof",
        "bv",
        "stichting",
        "vereniging",
        "anders",
    ]


def test_new_settings_have_no_choice(db):
    assert Settings.load().legal_entity == ""


# ---------- On the screen ----------

BUSINESS = {
    "business_name": "Voorbeeld",
    "address_line1": "Hoofdstraat 1",
    "postal_code": "1234 AB",
    "city": "Amsterdam",
    "country": "NL",
    "kvk_number": "12345678",
    "iban": "NL91ABNA0417164300",
    "email": "info@example.invalid",
}
SUGGESTED = "Voorstel op basis van wat je eerder invulde. Klopt het, sla dan op."


@pytest.fixture
def logged_in(client, db):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


def _settings_page(client):
    return client.get(reverse("business:topic", args=["bedrijf"])).content.decode()


def _set(**fields):
    Settings.objects.filter(pk=Settings.load().pk).update(**fields)


def test_the_wizard_asks_only_the_choice_and_it_may_stay_empty(logged_in):
    url = reverse("onboarding", args=["bedrijf"])
    page = logged_in.get(url).content.decode()
    assert 'name="legal_entity"' in page
    assert 'name="legal_form"' not in page
    assert SUGGESTED not in page

    assert logged_in.post(url, BUSINESS).status_code == 302
    assert Settings.load().legal_entity == ""
    logged_in.post(url, {**BUSINESS, "legal_entity": "vof"})
    assert Settings.load().legal_entity == "vof"


def test_the_wizard_suggests_from_old_text_too(logged_in):
    _set(legal_form="Stichting")
    page = logged_in.get(reverse("onboarding", args=["bedrijf"])).content.decode()
    assert SUGGESTED in page
    assert '<option value="stichting" selected>' in page
    assert Settings.load().legal_entity == ""


def test_the_wizard_keeps_the_old_text(logged_in):
    _set(legal_form="Holding")
    logged_in.post(reverse("onboarding", args=["bedrijf"]), {**BUSINESS, "legal_entity": "bv"})
    assert (Settings.load().legal_form, Settings.load().legal_entity) == ("Holding", "bv")


def test_a_new_installation_sees_only_the_choice(logged_in):
    page = _settings_page(logged_in)
    assert 'name="legal_entity"' in page
    assert 'name="legal_form"' not in page
    assert SUGGESTED not in page


def test_the_old_text_shows_while_it_holds_text_and_goes_once_emptied(logged_in):
    _set(legal_form="zzp", **{k: v for k, v in BUSINESS.items()})
    page = _settings_page(logged_in)
    assert 'name="legal_form"' in page
    assert 'value="zzp"' in page
    assert "Rechtsvorm, zoals je hem eerder typte" in page
    # Unclear text: no suggestion.
    assert SUGGESTED not in page

    url = reverse("business:topic", args=["bedrijf"])
    logged_in.post(url, {**BUSINESS, "legal_entity": "eenmanszaak", "legal_form": ""})
    assert (Settings.load().legal_entity, Settings.load().legal_form) == ("eenmanszaak", "")
    assert 'name="legal_form"' not in _settings_page(logged_in)


def test_the_suggestion_is_preselected_but_not_saved(logged_in):
    _set(legal_form="B.V.")
    page = _settings_page(logged_in)
    assert SUGGESTED in page
    assert '<option value="bv" selected>' in page
    assert Settings.load().legal_entity == ""


def test_the_suggestion_counts_once_saved(logged_in):
    _set(legal_form="B.V.")
    url = reverse("business:topic", args=["bedrijf"])
    logged_in.post(url, {**BUSINESS, "legal_entity": "bv", "legal_form": "B.V."})
    assert Settings.load().legal_entity == "bv"
    page = _settings_page(logged_in)
    assert SUGGESTED not in page
    assert '<option value="bv" selected>' in page


def test_the_old_card_answer_gives_a_suggestion_too(logged_in):
    _set(feedback_organisation="stichting")
    page = _settings_page(logged_in)
    assert SUGGESTED in page
    assert '<option value="stichting" selected>' in page


def test_anders_or_no_choice_asks_nothing_more(logged_in):
    # No notice on the overview, no extra question (principle 7).
    for entity in ("", "anders"):
        _set(legal_entity=entity, **BUSINESS)
        page = logged_in.get("/", follow=True).content.decode()
        assert "echtsvorm" not in page
