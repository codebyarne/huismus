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


def test_the_steps_are_business_kor_invoices_and_logo():
    assert [step.slug for step in STEPS] == ["bedrijf", "kor", "facturen", "logo"]


def test_the_wizard_requires_login(client):
    response = client.get(_url("bedrijf"))
    assert response.status_code == 302
    assert "/login/" in response.url


def test_an_unknown_step_is_not_found(logged_in):
    assert logged_in.get(_url("taart")).status_code == 404


def test_the_business_step_saves_and_goes_to_the_kor_step(logged_in):
    response = logged_in.post(_url("bedrijf"), BUSINESS)

    assert response.url == _url("kor")
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
    data = {
        "kor_enabled": "on",
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
    assert _url("bedrijf") in logged_in.get(_url("kor")).content.decode()


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


@pytest.mark.parametrize("step", STEPS, ids=lambda step: step.slug)
def test_a_step_shows_only_its_own_fields(step):
    # The same kind of bug as the import's stray "Wachtwoord" field: a part
    # of the settings form showing a field SettingsForm declares itself.
    from huismus.business.forms import SettingsPartForm

    form = SettingsPartForm(instance=Settings.load(), fields=step.fields)

    assert set(form.fields) == set(step.fields)


def test_the_kor_step_says_what_off_means(logged_in):
    page = logged_in.get(_url("kor")).content.decode()
    assert "Staat de KOR uit, dan kies je per regel 0, 9 of 21% btw." in page
