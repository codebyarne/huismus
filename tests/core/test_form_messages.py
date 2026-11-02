# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Every form says what to fill in, instead of Django's "Dit veld is
verplicht." (huismus/core/form_messages.py; huismus-intern/besluiten.md,
2026-11-01, "Teksten in Arnes stem, deel 3"). Forms from several apps and
one of Django's own, so a form module imported before the messages were
set would show up here."""

import pytest
from django import forms
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import ValidationError
from django.utils import translation

from huismus.contacts.forms import ContactForm
from huismus.expenses.forms import ExpenseCategoryForm, ExpenseForm, ExpenseLineForm

MESSAGES = {
    "nl": {
        "fill_in": "Vul dit in.",
        "date": "Vul een datum in.",
        "number": "Vul een getal in.",
        "minimum": "Vul 0 of meer in.",
        "too_long": "Dit mag hoogstens 8 tekens zijn. Nu zijn het er 9.",
        "email": "“a@b” is geen e-mailadres. Kijk na of je het goed typte.",
    },
    "en": {
        "fill_in": "Fill this in.",
        "date": "Enter a date.",
        "number": "Enter a number.",
        "minimum": "Enter 0 or more.",
        "too_long": "This can be at most 8 characters. It's 9 now.",
        "email": "“a@b” isn't an e-mail address. Check how you typed it.",
    },
}


@pytest.mark.parametrize("language", ["nl", "en"])
def test_an_expense_says_what_to_fill_in(language, db):
    expected = MESSAGES[language]
    with translation.override(language):
        assert ExpenseForm(data={"date": ""}).errors["date"] == [expected["fill_in"]]
        line = ExpenseLineForm(data={"amount_cents": ""})
        assert line.errors["amount_cents"] == [expected["fill_in"]]
        assert ExpenseForm(data={"date": "gisteren"}).errors["date"] == [expected["date"]]
        assert ExpenseCategoryForm(data={"name": ""}).errors["name"] == [expected["fill_in"]]


@pytest.mark.parametrize("language", ["nl", "en"])
def test_a_customer_says_what_is_wrong(language, db):
    expected = MESSAGES[language]
    with translation.override(language):
        form = ContactForm(
            data={
                "company_name": "Voorbeeld BV",
                "email": "a@b",
                "kvk_number": "123456789",
                "payment_terms_days": "-1",
            }
        )
        assert form.errors["email"] == [expected["email"]]
        assert expected["too_long"] in form.errors["kvk_number"]
        assert form.errors["payment_terms_days"] == [expected["minimum"]]
        form = ContactForm(data={"company_name": "Voorbeeld BV", "payment_terms_days": "veel"})
        assert form.errors["payment_terms_days"] == [expected["number"]]


@pytest.mark.parametrize("language", ["nl", "en"])
def test_djangos_own_forms_say_it_too(language, django_user_model, db):
    user = django_user_model(username="demo")
    with translation.override(language):
        form = SetPasswordForm(user, data={"new_password1": "", "new_password2": ""})
        assert form.errors["new_password1"] == [MESSAGES[language]["fill_in"]]


@pytest.mark.parametrize(
    ("language", "expected"), [("nl", "Vul 10 of minder in."), ("en", "Enter 10 or less.")]
)
def test_a_maximum_says_what_to_fill_in(language, expected):
    field = forms.IntegerField(max_value=10)
    with translation.override(language):
        with pytest.raises(ValidationError) as raised:
            field.clean("11")
        assert raised.value.messages == [expected]
