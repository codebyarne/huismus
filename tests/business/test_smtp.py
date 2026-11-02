# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The SMTP settings for mailing documents (SPEC.md M10). The password is
typed in the settings screen and kept in its own file in DATA_DIR
(business.smtp), never in the database, a backup or the page."""

import smtplib
import socket

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.urls import reverse

from huismus.business import smtp
from huismus.business.forms import SettingsForm
from huismus.business.models import Settings

pytestmark = pytest.mark.django_db

PASSWORD = "test-app-password-not-real"


@pytest.fixture
def client_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


def _form_data(**changes):
    data = {
        "business_name": "Voorbeeld BV",
        "address_line1": "Hoofdstraat 1",
        "postal_code": "1234 AB",
        "city": "Amsterdam",
        "country": "NL",
        "kvk_number": "12345678",
        "iban": "NL91ABNA0417164300",
        "email": "info@example.invalid",
        "kor_limit_cents": "20000.00",
        "kor_warning_percent": "80",
        "default_payment_terms_days": "14",
        "invoice_number_format": "{year}-{seq:04d}",
        "quote_number_format": "OFF-{year}-{seq:04d}",
        "number_reset_yearly": "on",
        "default_language": "nl",
        "currency": "EUR",
        "smtp_provider": "",
        "smtp_host": "",
        "smtp_port": "",
        "smtp_security": "starttls",
        "smtp_username": "",
        "smtp_from_email": "",
    }
    data.update(changes)
    return data


def _saved(**changes):
    form = SettingsForm(_form_data(**changes), instance=Settings.load())
    assert form.is_valid(), form.errors
    return form.save()


def test_mailing_is_off_until_a_provider_is_chosen():
    assert _saved().smtp_provider == ""


def test_the_gmail_preset_fills_in_server_port_and_security():
    business = _saved(
        smtp_provider="gmail",
        smtp_host="iets anders",
        smtp_port="25",
        smtp_security="ssl",
        smtp_username="voorbeeld@example.invalid",
    )

    assert (business.smtp_host, business.smtp_port, business.smtp_security) == (
        "smtp.gmail.com",
        587,
        "starttls",
    )


def test_gmail_needs_the_gmail_address_as_username():
    form = SettingsForm(_form_data(smtp_provider="gmail"), instance=Settings.load())

    assert "smtp_username" in form.errors


def test_another_server_needs_a_host_and_a_port():
    form = SettingsForm(_form_data(smtp_provider="other"), instance=Settings.load())

    assert {"smtp_host", "smtp_port"} <= set(form.errors)


def test_another_server_keeps_what_was_typed():
    business = _saved(
        smtp_provider="other",
        smtp_host="mail.example.invalid",
        smtp_port="465",
        smtp_security="ssl",
        smtp_username="info@example.invalid",
    )

    assert (business.smtp_host, business.smtp_port, business.smtp_security) == (
        "mail.example.invalid",
        465,
        "ssl",
    )


def test_a_typed_password_is_kept_in_its_own_file_not_in_the_database():
    business = _saved(
        smtp_provider="gmail", smtp_username="voorbeeld@example.invalid", smtp_password=PASSWORD
    )

    assert smtp.password() == PASSWORD
    assert smtp.password_path().stat().st_mode & 0o777 == 0o600
    assert PASSWORD not in str(Settings.objects.filter(pk=business.pk).values().get())


def test_an_empty_password_field_keeps_the_saved_password():
    smtp.set_password(PASSWORD)

    _saved(smtp_provider="gmail", smtp_username="voorbeeld@example.invalid", smtp_password="")

    assert smtp.password() == PASSWORD


def test_a_gmail_app_password_is_kept_without_the_spaces_google_shows():
    _saved(
        smtp_provider="gmail",
        smtp_username="voorbeeld@example.invalid",
        smtp_password="abcd efgh ijkl mnop",
    )

    assert smtp.password() == "abcdefghijklmnop"


def test_another_server_keeps_the_password_as_typed():
    _saved(
        smtp_provider="other",
        smtp_host="mail.example.invalid",
        smtp_port="587",
        smtp_password=" met spaties ",
    )

    assert smtp.password() == " met spaties "


def test_turning_mailing_off_removes_the_password():
    smtp.set_password(PASSWORD)

    _saved(smtp_provider="", smtp_password="")

    assert smtp.password() == ""
    assert not smtp.password_path().exists()


def test_the_password_field_never_shows_the_saved_password():
    smtp.set_password(PASSWORD)

    assert PASSWORD not in str(SettingsForm(instance=Settings.load())["smtp_password"])


@pytest.mark.parametrize(
    ("security", "use_tls", "use_ssl"), [("starttls", True, False), ("ssl", False, True)]
)
def test_the_connection_uses_the_settings_and_the_saved_password(
    settings, security, use_tls, use_ssl
):
    smtp.set_password(PASSWORD)
    business = _saved(
        smtp_provider="other",
        smtp_host="mail.example.invalid",
        smtp_port="465",
        smtp_security=security,
        smtp_username="info@example.invalid",
    )

    assert smtp.connection_kwargs(business) == {
        "host": "mail.example.invalid",
        "port": 465,
        "username": "info@example.invalid",
        "password": PASSWORD,
        "use_tls": use_tls,
        "use_ssl": use_ssl,
        "timeout": settings.SMTP_TIMEOUT,
    }


def test_mailing_is_configured_only_with_a_provider_and_a_password():
    business = _saved(smtp_provider="gmail", smtp_username="voorbeeld@example.invalid")

    smtp.set_password("")
    assert smtp.is_configured(business) is False
    smtp.set_password(PASSWORD)
    assert smtp.is_configured(business) is True
    business.smtp_provider = ""
    assert smtp.is_configured(business) is False


def test_the_sender_is_the_business_address_unless_another_is_set():
    business = _saved()
    assert smtp.sender(business) == "info@example.invalid"

    business.smtp_from_email = "facturen@example.invalid"
    assert smtp.sender(business) == "facturen@example.invalid"


def test_an_error_never_contains_the_password():
    smtp.set_password(PASSWORD)

    error = smtp.describe_error(smtplib.SMTPAuthenticationError(535, f"nope {PASSWORD}".encode()))

    assert "535" in error
    assert PASSWORD not in error


# --- The settings page ---


def test_the_page_says_whether_the_password_is_set_but_never_shows_it(client_in):
    smtp.set_password(PASSWORD)
    page = client_in.get(reverse("business:topic", args=["mailen"])).content.decode()
    assert PASSWORD not in page
    assert "Wachtwoord ingesteld" in page

    smtp.set_password("")
    page = client_in.get(reverse("business:topic", args=["mailen"])).content.decode()
    assert "Geen wachtwoord ingesteld" in page


def test_without_js_the_mail_fields_are_always_on_the_page(client_in):
    # app.js hides them while mailing is off; the page itself never does.
    page = client_in.get(reverse("business:topic", args=["mailen"])).content.decode()

    assert 'data-group="smtp"' in page
    assert 'name="smtp_password"' in page
    assert " hidden" not in page.split('id="instellingen"')[1].split("</form>")[0]


def test_the_test_mail_goes_to_the_sender(client_in):
    smtp.set_password(PASSWORD)
    _saved(smtp_provider="gmail", smtp_username="voorbeeld@example.invalid")

    response = client_in.post(reverse("business:test_mail"))

    assert response.status_code == 302
    [message] = mail.outbox
    assert message.to == ["info@example.invalid"]
    assert message.from_email == "info@example.invalid"


def test_a_failed_test_mail_says_why(client_in, monkeypatch):
    def refuse(self, messages):
        raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr("django.core.mail.backends.locmem.EmailBackend.send_messages", refuse)
    smtp.set_password(PASSWORD)
    _saved(smtp_provider="gmail", smtp_username="voorbeeld@example.invalid")

    response = client_in.post(reverse("business:test_mail"), follow=True)

    page = response.content.decode()
    assert "De mailserver weigert je gebruikersnaam of wachtwoord." in page
    assert '<span class="small">SMTPAuthenticationError: (535' in page


def test_no_test_mail_without_a_password(client_in):
    smtp.set_password("")
    _saved(smtp_provider="gmail", smtp_username="voorbeeld@example.invalid")

    client_in.post(reverse("business:test_mail"))

    assert mail.outbox == []


def test_the_test_mail_only_answers_a_post(client_in):
    assert client_in.get(reverse("business:test_mail")).status_code == 405


# --- Mail texts ---


def test_the_mail_texts_start_from_the_standard_text_with_placeholders():
    form = SettingsForm(instance=Settings.load())

    assert form.initial["mail_invoice_subject_nl"] == "Factuur {nummer} van {bedrijf}"
    assert form.initial["mail_invoice_subject_en"] == "Invoice {nummer} from {bedrijf}"
    assert "{vervaldatum}" in form.initial["mail_invoice_body_nl"]
    assert "{geldig_tot}" in form.initial["mail_quote_body_nl"]


def test_a_saved_mail_text_is_shown_as_saved():
    _saved(mail_quote_body_nl="Tot ziens, {bedrijf}")

    form = SettingsForm(instance=Settings.load())

    assert form.initial["mail_quote_body_nl"] == "Tot ziens, {bedrijf}"


def test_an_unknown_placeholder_in_a_mail_text_is_refused():
    form = SettingsForm(
        _form_data(mail_invoice_body_nl="Beste {klant}, {bedrag}"), instance=Settings.load()
    )

    assert "mail_invoice_body_nl" in form.errors
    assert "{klant}" in str(form.errors["mail_invoice_body_nl"])


def test_a_date_placeholder_only_fits_its_own_kind_of_document():
    form = SettingsForm(
        _form_data(mail_credit_note_body_nl="Geldig tot {geldig_tot}"), instance=Settings.load()
    )

    assert "mail_credit_note_body_nl" in form.errors


# --- The plain sentence above a mail error (designronde 3, D8) ---


@pytest.mark.parametrize(
    ("error", "sentence"),
    [
        (smtplib.SMTPAuthenticationError(535, b"5.7.8 rejected"), "wachtwoord"),
        (ConnectionRefusedError(111, "Connection refused"), "niet bereiken"),
        (socket.gaierror(-2, "Name or service not known"), "niet bereiken"),
        (smtplib.SMTPConnectError(421, b"busy"), "niet bereiken"),
        (TimeoutError("timed out"), "niet op tijd"),
        (
            smtplib.SMTPRecipientsRefused({}),
            "Mailen is niet gelukt. Kijk bij Instellingen → Mailen",
        ),
    ],
)
def test_a_known_mail_error_gets_a_plain_sentence(error, sentence):
    # From the stored text (EmailLog.error), so old failures get one too.
    assert sentence in smtp.plain_error(smtp.describe_error(error))


def test_no_error_has_no_sentence():
    assert smtp.plain_error("") == ""
