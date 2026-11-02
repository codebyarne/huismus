# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The mail server Huismus mails documents through (SPEC.md M10).

Everything but the password is in Settings. The password is typed in the
same screen but kept in a file of its own in DATA_DIR, readable only by
Huismus: not in the database, so not in a backup (core.backup skips the
file). It is read at the moment of sending, and kept out of every error
message.
"""

from pathlib import Path

from django.conf import settings as django_settings
from django.core import mail
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from huismus.core.private_files import write_owner_only

# What the "Gmail" choice fills in (business.forms.SettingsForm._clean_smtp).
GMAIL = {"smtp_host": "smtp.gmail.com", "smtp_port": 587, "smtp_security": "starttls"}


def password_path() -> Path:
    return Path(django_settings.DATA_DIR) / "smtp-password"


def password() -> str:
    try:
        return password_path().read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""


def set_password(value: str) -> None:
    """Saves the password, or removes it when value is empty."""
    path = password_path()
    if not value:
        path.unlink(missing_ok=True)
        return
    write_owner_only(path, value)


def is_configured(business) -> bool:
    return bool(business.smtp_provider and business.smtp_host and password())


def sender(business) -> str:
    return business.smtp_from_email or business.email


def connection_kwargs(business) -> dict:
    return {
        "host": business.smtp_host,
        "port": business.smtp_port,
        "username": business.smtp_username,
        "password": password(),
        "use_tls": business.smtp_security == "starttls",
        "use_ssl": business.smtp_security == "ssl",
        "timeout": django_settings.SMTP_TIMEOUT,
    }


def connection(business):
    """A connection with settings.EMAIL_BACKEND: SMTP in production, the
    locmem backend in tests (which ignores these arguments)."""
    return mail.get_connection(**connection_kwargs(business))


def describe_error(error: Exception) -> str:
    """The error as the user sees it and the log keeps it, as "<exception
    name>: <text>" (plain_error() reads the name back), with the
    password blanked out wherever it appears literally (a server could
    echo it back). An encoded form of it is not recognised."""
    text = f"{type(error).__name__}: {error}"
    secret = password()
    return text.replace(secret, "••••") if secret else text


# A plain sentence above the technical text of a mail error (designronde 3,
# D8), recognised by the exception's name at the start of describe_error()'s
# text, so a stored EmailLog.error gets one too.
_UNREACHABLE = gettext_lazy(
    "Huismus kan de mailserver niet bereiken. Kijk of de SMTP-server en de poort kloppen."
)
_FAILED = gettext_lazy("Mailen is niet gelukt. Kijk bij Instellingen → Mailen of alles klopt.")
_PLAIN_ERRORS = {
    "SMTPAuthenticationError": gettext_lazy(
        "De mailserver weigert je gebruikersnaam of wachtwoord. "
        "Kijk of ze kloppen; bij Gmail gebruik je een app-wachtwoord."
    ),
    "SMTPConnectError": _UNREACHABLE,
    "ConnectionRefusedError": _UNREACHABLE,
    "gaierror": _UNREACHABLE,
    "TimeoutError": gettext_lazy("De mailserver reageerde niet op tijd. Probeer het zo nog eens."),
}


def plain_error(text: str) -> str:
    """The sentence for an error text from describe_error(); any other
    error gets the general sentence, and no error none."""
    if not text:
        return ""
    name = text.split(":", 1)[0]
    return str(_PLAIN_ERRORS.get(name, _FAILED))


# What sending can raise: smtplib's SMTPException is an OSError, like a
# server that cannot be reached (refused, timeout, TLS); BadHeaderError is a
# subject with a line break in it.
SEND_ERRORS = (mail.BadHeaderError, OSError)


def send_test_mail(business) -> None:
    """A short mail to the sender itself; raises like sending does."""
    address = sender(business)
    mail.EmailMessage(
        subject=_("Testmail van Huismus"),
        body=_("Als je dit leest, kan Huismus mailen."),
        from_email=address,
        to=[address],
        connection=connection(business),
    ).send()
