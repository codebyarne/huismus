# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date
from decimal import Decimal

import pytest
from django import forms

from huismus.core.forms import EuroCentsField, HTML5DateInput


@pytest.mark.parametrize(
    ("euros", "expected_cents"),
    [
        # Dutch notation, as the field shows it (huismus-intern/besluiten.md 2026-10-29).
        ("20.000,00", 2_000_000),
        ("1.234.567,89", 123_456_789),
        ("12,50", 1250),
        ("12,5", 1250),
        ("1234,56", 123456),
        ("1.500", 150_000),
        # A decimal point still works, as in the old number field.
        ("10.50", 1050),
        ("10.5", 1050),
        ("10", 1000),
        ("0.01", 1),
        ("0", 0),
        ("1234.56", 123456),
        (" 12,50 ", 1250),
        ("-12,50", -1250),
    ],
)
def test_clean_converts_euros_to_cents(euros, expected_cents):
    field = EuroCentsField()
    assert field.clean(euros) == expected_cents


@pytest.mark.parametrize(
    "text",
    [
        "1.50.0",
        "1,2,3",
        "12,505",
        "0.500",
        "0.001",
        "0.500,00",
        "12.50,00",
        "1.5000",
        ",50",
        "12,",
        "€ 12",
        "twaalf",
    ],
)
def test_rejects_an_unclear_amount(text):
    from django.core.exceptions import ValidationError

    field = EuroCentsField()
    with pytest.raises(ValidationError) as error:
        field.clean(text)
    assert error.value.messages == ["Vul een bedrag in, zoals 1.250,00."]


def test_the_unclear_message_is_translated():
    from django.core.exceptions import ValidationError
    from django.utils import translation

    with translation.override("en"):
        with pytest.raises(ValidationError) as error:
            EuroCentsField().clean("1,2,3")
        assert error.value.messages == ["Enter an amount, such as 1.250,00."]


def test_clean_handles_a_blank_optional_field():
    field = EuroCentsField(required=False)
    assert field.clean("") is None


@pytest.mark.parametrize(
    ("cents", "shown"),
    [(2_000_000, "20.000,00"), (1250, "12,50"), (1, "0,01"), (0, "0,00"), (-1250, "-12,50")],
)
def test_shows_stored_cents_in_dutch_notation(cents, shown):
    # Like every amount elsewhere in the app, also in English.
    class _Form(forms.Form):
        amount = EuroCentsField()

    html = str(_Form(initial={"amount": cents})["amount"])
    assert f'value="{shown}"' in html
    assert 'type="text"' in html
    assert 'inputmode="decimal"' in html


@pytest.mark.parametrize("cents", [0, 1, 1250, 123456, 2_000_000, 123_456_789])
def test_round_trips_through_display_and_back(cents):
    field = EuroCentsField()
    assert field.clean(field.prepare_value(cents)) == cents


def test_still_checks_min_and_max():
    from django.core.exceptions import ValidationError

    field = EuroCentsField(min_value=Decimal("0.01"), max_value=Decimal("10000000"))
    with pytest.raises(ValidationError):
        field.clean("0,00")
    with pytest.raises(ValidationError):
        field.clean("10.000.000,01")


def test_html5_date_input_renders_existing_value_in_iso_format():
    # Regression: forms.DateInput(attrs={"type": "date"}) renders a bound
    # value using the active locale's DATE_INPUT_FORMATS (nl: d-m-Y) —
    # an <input type="date"> requires yyyy-mm-dd and silently discards
    # anything else, rendering blank. Found by editing a real record
    # with a date already set in a real browser: every date field in
    # this app (invoices, quotes, payments) had this bug.
    field = forms.DateField(widget=HTML5DateInput())
    rendered = field.widget.render("date", date(2026, 1, 15))
    assert 'value="2026-01-15"' in rendered
    assert 'value="15-01-2026"' not in rendered


def test_html5_date_input_still_sets_the_type_attribute():
    field = forms.DateField(widget=HTML5DateInput())
    assert field.widget.input_type == "date"
