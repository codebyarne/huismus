# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The texts of Instellingen and the mail texts Huismus suggests, in nl and en
(docs/schrijfwijzer.md; huismus-intern/besluiten.md, 2026-11-01, "Teksten in
Arnes stem, deel 5")."""

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

from huismus.business.forms import SettingsPartForm
from huismus.business.models import Settings
from huismus.core.password_views import NewPasswordForm
from huismus.documents import mail_texts

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


@pytest.mark.parametrize(
    ("language", "date_line"),
    [("nl", "Wil je hem uiterlijk {vervaldatum} betalen?"), ("en", "Please pay by {vervaldatum}.")],
)
def test_the_suggested_invoice_mail_asks_to_pay_by_the_due_date(language, date_line):
    body = mail_texts.standard_text("invoice", "body", language)
    assert f"\n{date_line}\n" in body
    # A line of its own: without a due date it drops out as a whole.
    assert date_line not in mail_texts.fill(body, {"vervaldatum": ""})


def test_the_suggested_english_mail_says_attached_is():
    body = mail_texts.standard_text("quote", "body", "en")
    assert "Attached is quote {nummer} for {bedrag}." in body
    assert "Please find" not in body


@pytest.mark.parametrize(
    ("language", "with_switch", "without_switch"),
    [
        ("nl", "Zet dat aan, of haal {year} weg.", "opnieuw beginnen. Haal {year} weg."),
        ("en", "Switch that on, or remove {year}.", "restart every year. Remove {year}."),
    ],
)
def test_year_without_yearly_reset_says_what_to_do_where_you_are(
    language, with_switch, without_switch
):
    settings = Settings.load()
    settings.number_reset_yearly = False
    data = {"invoice_number_format": "{year}-{seq:04d}", "quote_number_format": "{seq:04d}"}
    with translation.override(language):
        # The switch is on this screen (Facturen en nummering): switch it on.
        here = SettingsPartForm(
            {**data, "default_payment_terms_days": "14", "default_language": "nl"},
            instance=settings,
            fields=["invoice_number_format", "quote_number_format", "number_reset_yearly"],
        )
        assert with_switch in here.errors["invoice_number_format"][0]
        # Without the switch on the screen, only what can be done there.
        elsewhere = SettingsPartForm(
            data, instance=settings, fields=["invoice_number_format", "quote_number_format"]
        )
        error = elsewhere.errors["invoice_number_format"][0]
        assert without_switch in error and "Zet dat aan" not in error


@pytest.mark.parametrize(
    ("language", "label"),
    [("nl", "Factuur: onderwerp in het Nederlands"), ("en", "Invoice: subject in Dutch")],
)
def test_a_mail_text_error_names_the_document_and_the_field(logged_in, language, label):
    with translation.override(language):
        form = SettingsPartForm(
            {"mail_invoice_subject_nl": "Factuur {klant}"},
            instance=Settings.load(),
            fields=["mail_invoice_subject_nl"],
        )
        assert str(form["mail_invoice_subject_nl"].label) == label
        assert "{klant}" in form.errors["mail_invoice_subject_nl"][0]


def test_the_mail_page_links_to_the_help_and_shows_the_fields_by_their_part(logged_in):
    page = logged_in.get(reverse("business:topic", args=["mailen"])).content.decode()
    assert 'href="/hulp/mailen/' in page and "Zo werkt het →" in page
    assert "Onderwerp in het Nederlands" in page


def test_the_settings_overview_says_drafts_follow_the_settings(logged_in):
    page = logged_in.get(reverse("business:overview")).content.decode()
    assert "Wijzigingen gelden voor concepten en nieuwe documenten." in page


@pytest.mark.parametrize(
    ("language", "mismatch", "again"),
    [
        ("nl", "De twee wachtwoorden zijn niet gelijk.", "Nieuw wachtwoord, nog een keer"),
        ("en", "The two passwords don't match.", "New password again"),
    ],
)
def test_two_different_new_passwords_say_so(language, mismatch, again):
    user = get_user_model().objects.create_user(username="freelancer")
    with translation.override(language):
        form = NewPasswordForm(
            user, {"new_password1": "lange-zomeravond", "new_password2": "lange-winteravond"}
        )
        assert mismatch in form.errors["new_password2"][0]
        assert str(form.fields["new_password2"].label) == again


def test_disconnecting_an_assistant_says_the_key_stops_working(logged_in):
    logged_in.post(reverse("business:assistants"), {"action": "connect"})
    response = logged_in.post(reverse("business:assistants"), {"action": "disconnect"}, follow=True)
    assert "Ontkoppeld. De sleutel werkt niet meer." in response.content.decode()
