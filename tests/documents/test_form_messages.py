# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The field messages on the payment and mail forms say what to do, instead of
Django's "Dit veld is verplicht." (huismus-intern/besluiten.md, 2026-11-01,
"Teksten in Arnes stem, deel 2")."""

import pytest
from django.utils import translation

from huismus.documents.forms import MailForm, PaymentForm


@pytest.mark.parametrize(
    ("language", "fill_in", "date"),
    [("nl", "Vul dit in.", "Vul een datum in."), ("en", "Fill this in.", "Enter a date.")],
)
def test_the_payment_form_says_what_to_fill_in(language, fill_in, date):
    with translation.override(language):
        form = PaymentForm(data={"amount_cents": "", "paid_on": "gisteren", "method": "Contant"})
        assert not form.is_valid()
        assert form.errors["amount_cents"] == [fill_in]
        assert form.errors["paid_on"] == [date]


@pytest.mark.parametrize(
    ("language", "fill_in", "address", "no_address"),
    [
        (
            "nl",
            "Vul dit in.",
            "“a@b” is geen e-mailadres. Kijk na of je het goed typte.",
            "Vul een e-mailadres in.",
        ),
        (
            "en",
            "Fill this in.",
            "“a@b” isn't an e-mail address. Check how you typed it.",
            "Enter an e-mail address.",
        ),
    ],
)
def test_the_mail_form_says_what_to_fill_in(language, fill_in, address, no_address):
    with translation.override(language):
        form = MailForm(data={"to": "a@b", "subject": "", "body": ""})
        assert not form.is_valid()
        assert form.errors["to"] == [address]
        assert form.errors["subject"] == [fill_in]
        assert form.errors["body"] == [fill_in]
        assert MailForm(data={"to": "", "subject": "x", "body": "x"}).errors["to"] == [no_address]
