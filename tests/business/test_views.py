# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from huismus.business.models import Settings

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _valid_form_data(**overrides):
    data = {
        "business_name": "Voorbeeld BV",
        "legal_form": "",
        "address_line1": "Hoofdstraat 1",
        "address_line2": "",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "country": "NL",
        "kvk_number": "12345678",
        "vat_number": "",
        "iban": "NL91ABNA0417164300",
        "bic": "",
        "email": "info@example.invalid",
        "phone": "",
        "website": "",
        "kor_enabled": "",
        "kor_text": "",
        "kor_limit_cents": "20000.00",
        "kor_warning_percent": "80",
        "default_payment_terms_days": "14",
        "invoice_number_format": "{year}-{seq:04d}",
        "quote_number_format": "OFF-{year}-{seq:04d}",
        # On, like the model default: {year} in the formats needs it.
        "number_reset_yearly": "on",
        "default_footer_text": "",
        "default_language": "nl",
        "currency": "EUR",
        # A select: the page always sends one of its options.
        "smtp_security": "starttls",
    }
    data.update(overrides)
    return data


def _png_upload(name="logo.png"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="green").save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


def test_settings_page_requires_login(client):
    response = client.get(reverse("business:overview"))
    assert response.status_code == 302
    assert response.url.startswith(reverse("login"))


def test_get_shows_form_with_a_blank_settings_row(client):
    _login(client)

    response = client.get(reverse("business:overview"))

    assert response.status_code == 200
    assert Settings.objects.count() == 1


def test_post_saves_valid_settings(client):
    _login(client)

    response = client.post(
        reverse("business:topic", args=["bedrijf"]), data=_valid_form_data(), follow=True
    )

    assert response.status_code == 200
    assert Settings.objects.get().business_name == "Voorbeeld BV"


def test_post_rejects_invalid_iban_and_does_not_save(client):
    _login(client)

    response = client.post(
        reverse("business:topic", args=["bedrijf"]), data=_valid_form_data(iban="NL00INVALID000000")
    )

    assert response.status_code == 200
    assert not Settings.objects.filter(business_name="Voorbeeld BV").exists()


def test_post_with_logo_saves_it_and_shows_preview(client):
    _login(client)

    response = client.post(
        reverse("business:topic", args=["huisstijl"]),
        data=_valid_form_data(logo=_png_upload()),
        follow=True,
    )

    assert response.status_code == 200
    settings = Settings.objects.get()
    assert settings.logo.name.endswith(".png")
    assert settings.logo.storage.exists(settings.logo.name)


def test_uploading_a_new_logo_deletes_the_old_one(client):
    _login(client)
    client.post(
        reverse("business:topic", args=["huisstijl"]), data=_valid_form_data(logo=_png_upload())
    )
    first_logo_name = Settings.objects.get().logo.name
    storage = Settings.objects.get().logo.storage

    client.post(
        reverse("business:topic", args=["huisstijl"]),
        data=_valid_form_data(logo=_png_upload("second.png")),
    )

    assert not storage.exists(first_logo_name)


def test_ticking_remove_logo_deletes_the_file_and_clears_the_field(client):
    _login(client)
    client.post(
        reverse("business:topic", args=["huisstijl"]), data=_valid_form_data(logo=_png_upload())
    )
    logo_name = Settings.objects.get().logo.name
    storage = Settings.objects.get().logo.storage

    client.post(
        reverse("business:topic", args=["huisstijl"]), data=_valid_form_data(**{"logo-clear": "on"})
    )

    assert not Settings.objects.get().logo
    assert not storage.exists(logo_name)


def test_saving_without_touching_the_logo_keeps_it(client):
    _login(client)
    client.post(
        reverse("business:topic", args=["huisstijl"]), data=_valid_form_data(logo=_png_upload())
    )
    logo_name = Settings.objects.get().logo.name

    client.post(reverse("business:topic", args=["huisstijl"]), data=_valid_form_data())

    assert Settings.objects.get().logo.name == logo_name


# --- KOR text suggestion ---


def test_empty_kor_text_is_prefilled_with_a_suggestion(client):
    _login(client)

    response = client.get(reverse("business:topic", args=["kor"]))

    assert "kleineondernemersregeling" in response.context["form"]["kor_text"].value()


def test_saved_kor_text_is_not_overwritten_by_the_suggestion(client):
    _login(client)
    client.post(reverse("business:topic", args=["kor"]), _valid_form_data(kor_text="Eigen tekst"))

    response = client.get(reverse("business:topic", args=["kor"]))

    assert response.context["form"]["kor_text"].value() == "Eigen tekst"


# --- Number formats (M8): caught on the settings page, not at the first issue. ---


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("invoice_number_format", "{jaar}-{seq:04d}"),  # unknown placeholder
        ("invoice_number_format", "{year}-"),  # no sequence number at all
        ("quote_number_format", "OFF-{seq:04"),  # broken brace
    ],
)
def test_broken_number_format_is_rejected(client, field, value):
    _login(client)
    response = client.post(
        reverse("business:topic", args=["facturen"]), _valid_form_data(**{field: value})
    )
    assert response.status_code == 200
    assert response.context["form"].errors[field]


def test_year_in_format_requires_yearly_reset(client):
    _login(client)
    data = _valid_form_data(invoice_number_format="{year}-{seq:04d}")
    data.pop("number_reset_yearly", None)  # unchecked checkbox
    response = client.post(reverse("business:topic", args=["facturen"]), data)
    assert response.status_code == 200
    assert response.context["form"].errors["invoice_number_format"]


def test_settings_page_previews_the_next_numbers(client):
    _login(client)
    client.post(reverse("business:topic", args=["facturen"]), _valid_form_data())
    response = client.get(reverse("business:topic", args=["facturen"]))
    year = timezone.localdate().year
    assert response.context["next_invoice_number"] == f"{year}-0001"


def test_a_format_with_the_customer_number_is_accepted_and_previewed(client):
    _login(client)
    data = _valid_form_data(
        invoice_number_format="{customer}{seq:04d}", quote_number_format="{customer}{seq:04d}"
    )

    client.post(reverse("business:topic", args=["facturen"]), data)
    response = client.get(reverse("business:topic", args=["facturen"]))

    assert response.context["next_invoice_number"] == "[klantnummer]0001"


def test_kor_limit_is_typed_in_euros_and_stored_in_cents(client):
    _login(client)

    client.post(
        reverse("business:topic", args=["kor"]),
        data=_valid_form_data(kor_limit_cents="25000.50", kor_warning_percent="90"),
    )

    settings = Settings.objects.get()
    assert (settings.kor_limit_cents, settings.kor_warning_percent) == (2_500_050, 90)


@pytest.mark.parametrize(
    "overrides",
    [
        {"kor_limit_cents": "0"},
        {"kor_limit_cents": ""},
        {"kor_warning_percent": "0"},
        {"kor_warning_percent": "101"},
        {"kor_warning_percent": ""},
    ],
)
def test_kor_limit_and_percentage_are_required_and_in_range(client, overrides):
    _login(client)

    response = client.post(
        reverse("business:topic", args=["kor"]), data=_valid_form_data(**overrides)
    )

    assert response.status_code == 200
    assert response.context["form"].errors
    settings = Settings.load()
    assert (settings.kor_limit_cents, settings.kor_warning_percent) == (2_000_000, 80)


def test_a_rejected_number_format_never_previews_a_number_with_none(client):
    # Found by hand (BUGS-BY-HAND.md, 2026-11-01): the preview came from the
    # settings the rejected form had already changed, "None-0001".
    _login(client)
    client.post(reverse("business:topic", args=["facturen"]), _valid_form_data())
    data = _valid_form_data()
    data.pop("number_reset_yearly")  # unchecked, with {year} still in the formats
    response = client.post(reverse("business:topic", args=["facturen"]), data)
    page = response.content.decode()
    assert response.context["form"].errors["invoice_number_format"]
    assert "None" not in page
    # The preview is that of the saved settings.
    assert f"{timezone.localdate().year}-0001" in page


def test_the_kor_page_says_what_off_means(client):
    _login(client)
    page = client.get(reverse("business:topic", args=["kor"])).content.decode()
    assert "Staat de KOR uit, dan kies je per regel 0, 9 of 21% btw." in page
