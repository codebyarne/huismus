# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import pytest
from django.core.exceptions import ValidationError
from hypothesis import given
from hypothesis import strategies as st

from huismus.core.validators import validate_dutch_postal_code, validate_iban, validate_kvk_number

VALID_IBANS = [
    "NL91ABNA0417164300",
    "nl91 abna 0417 1643 00",
    "GB29NWBK60161331926819",
    "DE89370400440532013000",
]


@pytest.mark.parametrize("iban", VALID_IBANS)
def test_validate_iban_accepts_known_valid_ibans(iban):
    validate_iban(iban)  # must not raise


@pytest.mark.parametrize(
    "iban",
    [
        "NL91ABNA0417164301",  # wrong checksum
        "NOTANIBAN",
        "NL12",  # too short
        "1234ABNA0417164300",  # doesn't start with two letters
    ],
)
def test_validate_iban_rejects_invalid_ibans(iban):
    with pytest.raises(ValidationError):
        validate_iban(iban)


@given(st.text(alphabet="0123456789", min_size=1, max_size=40))
def test_validate_iban_never_crashes_on_digit_strings(digits):
    try:
        validate_iban(digits)
    except ValidationError:
        pass


@pytest.mark.parametrize("kvk", ["12345678", "00000000"])
def test_validate_kvk_number_accepts_eight_digits(kvk):
    validate_kvk_number(kvk)


@pytest.mark.parametrize("kvk", ["1234567", "123456789", "abcdefgh", "1234 567"])
def test_validate_kvk_number_rejects_anything_else(kvk):
    with pytest.raises(ValidationError):
        validate_kvk_number(kvk)


@pytest.mark.parametrize("postal_code", ["1234 AB", "1234AB", "1017 ZD"])
def test_validate_dutch_postal_code_accepts_valid_format(postal_code):
    validate_dutch_postal_code(postal_code)


@pytest.mark.parametrize("postal_code", ["0123 AB", "1234 A", "1234 ABC", "AB 1234", ""])
def test_validate_dutch_postal_code_rejects_invalid_format(postal_code):
    with pytest.raises(ValidationError):
        validate_dutch_postal_code(postal_code)
