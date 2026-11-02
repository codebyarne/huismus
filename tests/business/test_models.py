# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import ValidationError

from huismus.business.models import Settings

pytestmark = pytest.mark.django_db


def _minimal_settings(**overrides):
    fields = {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
    }
    fields.update(overrides)
    return Settings(**fields)


def test_save_always_uses_pk_one():
    settings_a = _minimal_settings()
    settings_a.save()
    settings_b = _minimal_settings(business_name="Andere naam")
    settings_b.save()

    assert Settings.objects.count() == 1
    assert Settings.objects.get().business_name == "Andere naam"


def test_load_creates_a_blank_row_on_first_call():
    assert Settings.objects.count() == 0

    loaded = Settings.load()

    assert loaded.pk == 1
    assert Settings.objects.count() == 1


def test_load_returns_the_existing_row_on_later_calls():
    _minimal_settings().save()

    loaded = Settings.load()

    assert loaded.business_name == "Voorbeeld BV"
    assert Settings.objects.count() == 1


def test_clean_requires_kor_text_when_kor_enabled():
    settings = _minimal_settings(kor_enabled=True, kor_text="")

    with pytest.raises(ValidationError):
        settings.clean()


def test_clean_allows_kor_enabled_with_text():
    settings = _minimal_settings(kor_enabled=True, kor_text="Factuur is vrijgesteld van btw.")

    settings.clean()  # must not raise


def test_clean_validates_dutch_postal_code_for_nl_country():
    settings = _minimal_settings(country="NL", postal_code="not a postcode")

    with pytest.raises(ValidationError):
        settings.clean()


def test_clean_skips_postal_code_format_for_non_nl_country():
    settings = _minimal_settings(country="BE", postal_code="1000")

    settings.clean()  # must not raise: Dutch format isn't enforced abroad
