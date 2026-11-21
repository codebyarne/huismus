# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The step-by-step start (/welkom/, M13): each step saves its part of
Settings with the settings page's validation."""

from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from huismus.business.models import Settings
from huismus.core.onboarding import STEPS

pytestmark = pytest.mark.django_db

BUSINESS = {
    "business_name": "Voorbeeld BV",
    "address_line1": "Hoofdstraat 1",
    "postal_code": "1234 AB",
    "city": "Amsterdam",
    "country": "NL",
    "kvk_number": "12345678",
    "iban": "NL91ABNA0417164300",
    "email": "info@example.invalid",
}


@pytest.fixture
def logged_in(client):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


def _png_upload():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="green").save(buffer, format="PNG")
    return SimpleUploadedFile("logo.png", buffer.getvalue(), content_type="image/png")


def _url(step):
    return reverse("onboarding", args=[step])


def test_welkom_starts_at_the_first_step(logged_in):
    response = logged_in.get(reverse("onboarding_start"))
    assert response.url == _url("bedrijf")


def test_the_steps_are_business_work_kor_reverse_charge_invoices_and_logo():
    assert [step.slug for step in STEPS] == [
        "bedrijf",
        "werk",
        "kor",
        "verlegd",
        "facturen",
        "logo",
    ]


def _kor_on():
    settings = Settings.load()
    settings.kor_enabled = True
    settings.kor_text = "Vrijgesteld (KOR)."
    settings.save()


def test_the_kor_step_spells_its_name_out_and_the_step_bar_keeps_it_short(logged_in):
    _kor_on()
    page = logged_in.get(_url("kor")).content.decode()

    assert "<h1>Kleineondernemersregeling (KOR)</h1>" in page
    assert "</span>KOR</li>" in page


def test_the_wizard_requires_login(client):
    response = client.get(_url("bedrijf"))
    assert response.status_code == 302
    assert "/login/" in response.url


def test_an_unknown_step_is_not_found(logged_in):
    assert logged_in.get(_url("taart")).status_code == 404


def test_the_business_step_saves_and_goes_to_your_work(logged_in):
    response = logged_in.post(_url("bedrijf"), BUSINESS)

    assert response.url == _url("werk")
    settings = Settings.load()
    assert (settings.business_name, settings.kvk_number) == ("Voorbeeld BV", "12345678")


def test_the_business_step_validates_like_the_settings_page(logged_in):
    response = logged_in.post(_url("bedrijf"), {**BUSINESS, "iban": "NL00INVALID000000"})

    assert response.status_code == 200
    assert response.context["form"].errors["iban"]
    assert Settings.load().business_name == ""


def test_a_step_only_changes_its_own_fields(logged_in):
    settings = Settings.load()
    settings.invoice_number_format = "F{year}-{seq:03d}"
    settings.save()

    logged_in.post(_url("bedrijf"), BUSINESS)

    assert Settings.load().invoice_number_format == "F{year}-{seq:03d}"


def test_the_kor_step_needs_a_text_while_the_kor_is_on(logged_in):
    _kor_on()
    data = {
        "kor_text": "",
        "kor_limit_cents": "20000.00",
        "kor_warning_percent": "80",
    }
    response = logged_in.post(_url("kor"), data)
    assert response.context["form"].errors["kor_text"]

    response = logged_in.post(_url("kor"), {**data, "kor_text": "Vrijgesteld (KOR)."})
    assert response.url == _url("facturen")
    settings = Settings.load()
    assert (settings.kor_enabled, settings.kor_limit_cents) == (True, 2_000_000)


def test_the_invoices_step_keeps_the_yearly_reset_it_does_not_show(logged_in):
    response = logged_in.post(
        _url("facturen"),
        {
            "default_payment_terms_days": "30",
            "invoice_number_format": "{year}-{seq:04d}",
            "quote_number_format": "OFF-{year}-{seq:04d}",
        },
    )

    assert response.url == _url("logo")
    settings = Settings.load()
    assert (settings.default_payment_terms_days, settings.number_reset_yearly) == (30, True)


def test_the_invoices_step_shows_the_next_number(logged_in):
    page = logged_in.get(_url("facturen")).content.decode()
    assert "Volgende als je vandaag uitgeeft: OFF-" in page
    assert page.count("Volgende als je vandaag uitgeeft") == 2


def test_the_logo_step_saves_a_logo_and_finishes(logged_in):
    response = logged_in.post(_url("logo"), {"logo": _png_upload()})

    assert response.url == reverse("onboarding_done")
    assert Settings.load().logo


def test_the_logo_step_can_be_skipped(logged_in):
    page = logged_in.get(_url("logo")).content.decode()
    assert reverse("onboarding_done") in page


def test_each_step_after_the_first_links_back(logged_in):
    assert _url("bedrijf") in logged_in.get(_url("werk")).content.decode()
    assert _url("werk") in logged_in.get(_url("facturen")).content.decode()


def test_the_done_page_offers_a_first_customer_and_the_overview(logged_in):
    page = logged_in.get(reverse("onboarding_done")).content.decode()
    assert reverse("contacts:create") in page
    assert 'href="/"' in page


def test_the_empty_overview_offers_both_ways_to_start(logged_in):
    page = logged_in.get(reverse("home")).content.decode()
    assert reverse("imports:upload") in page
    assert reverse("onboarding_start") in page


def test_the_invoices_step_refuses_a_format_without_a_sequence_number(logged_in):
    response = logged_in.post(
        _url("facturen"),
        {
            "default_payment_terms_days": "14",
            "invoice_number_format": "{year}",
            "quote_number_format": "OFF-{year}-{seq:04d}",
        },
    )

    assert response.context["form"].errors["invoice_number_format"]
    assert Settings.load().invoice_number_format == "{year}-{seq:04d}"


def test_the_invoices_step_checks_year_against_the_saved_yearly_reset(logged_in):
    settings = Settings.load()
    settings.number_reset_yearly = False
    settings.invoice_number_format = "F{seq:04d}"
    settings.quote_number_format = "O{seq:04d}"
    settings.save()

    response = logged_in.post(
        _url("facturen"),
        {
            "default_payment_terms_days": "14",
            "invoice_number_format": "{year}-{seq:04d}",
            "quote_number_format": "O{seq:04d}",
        },
    )

    assert response.context["form"].errors["invoice_number_format"]


def test_the_logo_step_refuses_a_file_that_is_not_an_image(logged_in):
    not_an_image = SimpleUploadedFile("logo.png", b"no image", content_type="image/png")

    response = logged_in.post(_url("logo"), {"logo": not_an_image})

    assert response.context["form"].errors["logo"]
    assert not Settings.load().logo


@pytest.mark.parametrize(
    "step", [step for step in STEPS if step.slug != "werk"], ids=lambda step: step.slug
)
def test_a_step_shows_only_its_own_fields(step):
    # The same kind of bug as the import's stray "Wachtwoord" field: a part
    # of the settings form showing a field SettingsForm declares itself.
    from huismus.business.forms import SettingsPartForm

    form = SettingsPartForm(instance=Settings.load(), fields=step.fields)

    assert set(form.fields) == set(step.fields)


def test_your_work_says_what_charging_vat_means(logged_in):
    page = logged_in.get(_url("werk")).content.decode()
    assert "Je kiest dan per regel het btw-tarief." in page


# Je werk (issue #259): three choices that set existing settings only, and
# decide which steps follow. Nothing about the answers is stored.

WORK = {"vat": "ja", "reverse_charge": "nee", "default_language": "nl"}


def _steps(response):
    return [step.slug for step in response.context["steps"]]


def test_charging_vat_turns_the_kor_off_and_skips_its_step(logged_in):
    _kor_on()

    response = logged_in.post(_url("werk"), WORK)

    assert response.url == _url("facturen")
    assert not Settings.load().kor_enabled
    assert _steps(logged_in.get(response.url)) == ["bedrijf", "werk", "facturen", "logo"]


def test_the_kor_turns_it_on_with_the_suggested_text_and_brings_its_step(logged_in):
    from huismus.business.forms import DEFAULT_KOR_TEXT

    response = logged_in.post(_url("werk"), {**WORK, "vat": "kor", "reverse_charge": ""})

    assert response.url == _url("kor")
    settings = Settings.load()
    assert settings.kor_enabled
    assert settings.kor_text == str(DEFAULT_KOR_TEXT)
    steps = _steps(logged_in.get(response.url))
    assert steps == ["bedrijf", "werk", "kor", "facturen", "logo"]


def test_the_kor_keeps_a_text_of_your_own(logged_in):
    settings = Settings.load()
    settings.kor_text = "Mijn eigen KOR-tekst."
    settings.save()

    logged_in.post(_url("werk"), {**WORK, "vat": "kor"})

    assert Settings.load().kor_text == "Mijn eigen KOR-tekst."


def test_the_kor_ignores_the_question_about_reverse_charge(logged_in):
    response = logged_in.post(_url("werk"), {**WORK, "vat": "kor", "reverse_charge": "eu"})

    assert response.url == _url("kor")


def test_not_knowing_yet_leaves_the_kor_off_and_the_done_page_says_where_it_goes(logged_in):
    _kor_on()

    response = logged_in.post(_url("werk"), {**WORK, "vat": "later"})

    assert response.url == _url("facturen") + "?kor=later"
    assert not Settings.load().kor_enabled
    # The answer travels along to the end of this round, Terug included.
    page = logged_in.get(response.url).content.decode()
    assert f'href="{_url("werk")}?kor=later"' in page
    response = logged_in.post(
        response.url,
        {
            "default_payment_terms_days": "14",
            "invoice_number_format": "{year}-{seq:04d}",
            "quote_number_format": "OFF-{year}-{seq:04d}",
        },
    )
    assert response.url == _url("logo") + "?kor=later"
    assert (
        f'href="{reverse("onboarding_done")}?kor=later"'
        in logged_in.get(response.url).content.decode()
    )
    done = logged_in.get(reverse("onboarding_done") + "?kor=later").content.decode()
    assert 'id="kor-later"' in done
    assert reverse("business:topic", args=["kor"]) in done


def test_the_done_page_says_nothing_about_the_kor_otherwise(logged_in):
    assert 'id="kor-later"' not in logged_in.get(reverse("onboarding_done")).content.decode()


def test_going_back_to_your_work_shows_not_knowing_yet(logged_in):
    response = logged_in.get(_url("werk") + "?kor=later")
    assert response.context["form"].initial["vat"] == "later"


@pytest.mark.parametrize("place", ["nl", "eu", "buiten-eu"])
def test_a_yes_for_reverse_charge_brings_its_step_with_an_empty_field(logged_in, place):
    response = logged_in.post(_url("werk"), {**WORK, "reverse_charge": place})

    assert response.url == _url("verlegd") + f"?verlegd={place}"
    page = logged_in.get(response.url)
    assert _steps(page) == ["bedrijf", "werk", "verlegd", "facturen", "logo"]
    assert page.context["form"]["reverse_charge_text"].value() in (None, "")
    # Back to Je werk shows the same answer.
    back = logged_in.get(_url("werk") + f"?verlegd={place}")
    assert back.context["form"].initial["reverse_charge"] == place


def test_the_reverse_charge_step_saves_its_text_and_goes_on(logged_in):
    response = logged_in.post(
        _url("verlegd") + "?verlegd=nl", {"reverse_charge_text": "Btw verlegd."}
    )

    assert response.url == _url("facturen") + "?verlegd=nl"
    assert Settings.load().reverse_charge_text == "Btw verlegd."


def test_no_reverse_charge_skips_its_step_and_keeps_a_text_already_there(logged_in):
    settings = Settings.load()
    settings.reverse_charge_text = "Btw verlegd."
    settings.save()

    response = logged_in.post(_url("werk"), {**WORK, "reverse_charge": "nee"})

    assert response.url == _url("facturen")
    assert Settings.load().reverse_charge_text == "Btw verlegd."


def test_the_question_about_reverse_charge_needs_an_answer_without_the_kor(logged_in):
    response = logged_in.post(_url("werk"), {**WORK, "reverse_charge": ""})

    assert response.status_code == 200
    assert response.context["form"].errors["reverse_charge"]
    # The error summary links to the question.
    assert 'href="#id_reverse_charge"' in response.content.decode()


def test_with_a_text_but_no_place_nothing_is_ticked(logged_in):
    # Huismus doesn't guess a country (huismus-intern/besluiten.md, 2026-11-21).
    settings = Settings.load()
    settings.reverse_charge_text = "Btw verlegd."
    settings.save()

    form = logged_in.get(_url("werk")).context["form"]

    assert form.initial["reverse_charge"] is None


def test_your_work_shows_the_current_state(logged_in):
    _kor_on()
    settings = Settings.load()
    settings.default_language = "en"
    settings.save()

    initial = logged_in.get(_url("werk")).context["form"].initial

    assert (initial["vat"], initial["reverse_charge"], initial["default_language"]) == (
        "kor",
        "nee",
        "en",
    )


def test_your_work_sets_the_invoice_language(logged_in):
    logged_in.post(_url("werk"), {**WORK, "default_language": "en"})
    assert Settings.load().default_language == "en"


def test_your_work_leaves_other_settings_alone(logged_in):
    settings = Settings.load()
    settings.kor_limit_cents = 1_234_500
    settings.business_name = "Voorbeeld BV"
    settings.save()

    logged_in.post(_url("werk"), {**WORK, "vat": "kor"})

    settings = Settings.load()
    assert (settings.kor_limit_cents, settings.business_name) == (1_234_500, "Voorbeeld BV")


def test_your_work_needs_an_answer_to_each_question(logged_in):
    response = logged_in.post(_url("werk"), {})

    assert set(response.context["form"].errors) == {"vat", "default_language"}


def test_your_work_links_to_the_help_page_about_the_kor(logged_in):
    page = logged_in.get(_url("werk")).content.decode()
    assert reverse("help:page", args=["kor-en-btw"]) in page


def test_a_step_you_dont_get_goes_on_to_the_next_one(logged_in):
    assert logged_in.get(_url("kor")).url == _url("facturen")
    assert logged_in.get(_url("verlegd")).url == _url("facturen")


def test_an_unknown_place_in_the_address_is_ignored(logged_in):
    assert logged_in.get(_url("verlegd") + "?verlegd=mars").url == _url("facturen")


def test_a_step_opened_without_the_answers_of_this_round_forgets_them(logged_in):
    # On purpose: the answers live only in the address (Round).
    response = logged_in.post(_url("werk"), {**WORK, "reverse_charge": "nl"})
    assert response.url == _url("verlegd") + "?verlegd=nl"

    page = logged_in.get(_url("facturen"))

    assert _steps(page) == ["bedrijf", "werk", "facturen", "logo"]


def test_saving_a_step_keeps_the_answers_of_this_round(logged_in):
    page = logged_in.get(_url("verlegd") + "?verlegd=nl").content.decode()
    assert 'action="/welkom/verlegd/?verlegd=nl"' in page
