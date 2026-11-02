# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus?: what kind of organisation someone has, what
they miss and how to reach them, sent to the app's maker only if they
choose to (huismus-intern/besluiten.md, 2026-11-01 and 2026-11-02).

Huismus sends it itself, to the Contact Form 7 form on arnekrijnsen.com,
but only when the user presses Versturen after seeing everything that goes
along: the third kind of outgoing request of SPEC.md principle 6. Where
Huismus runs, its version and its language Huismus fills in itself; they
are in that overview too.

The choices are those of the issue form (.github/ISSUE_TEMPLATE/idee.yml).
The form on the site takes a choice only when the value is exactly its
option text, so each choice has that text here, the same in every language
of the app; `taal` says which language the app speaks.
"""

import json
import logging
import secrets
import sys
import urllib.request

from django.conf import settings
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .updates import current_version

logger = logging.getLogger("huismus.feedback")

# The form "Huismus: vertel wie je bent" on the maker's site: Contact Form 7,
# form 2943 on the page /huismus-vertel/ (2939). Its REST endpoint wants the
# form's unit tag on that page. A new form on the site means new numbers here.
# The site lets this form skip reCAPTCHA for a User-Agent "Huismus/…" (plugin
# Huismus-formulier, huismus-intern/wordpress/).
FORM_ID = 2943
PAGE_ID = 2939
SEND_URL = (
    f"https://www.arnekrijnsen.com/wp-json/contact-form-7/v1/contact-forms/{FORM_ID}/feedback"
)
UNIT_TAG = f"wpcf7-f{FORM_ID}-p{PAGE_ID}-o1"
TIMEOUT_SECONDS = 15
# The form's own limits (maxlength on the site).
MAX_WISH = 2000
MAX_EMAIL = 400

# (key stored in Settings, option text on the form, label in the app)
ORGANISATIONS = (
    ("kor", "Eenmanszaak of vof met KOR", _("Eenmanszaak of vof met KOR")),
    ("btw", "Eenmanszaak of vof met btw", _("Eenmanszaak of vof met btw")),
    ("bv", "Bv of holding", _("Bv of holding")),
    ("stichting", "Stichting", _("Stichting")),
    ("vereniging", "Vereniging", _("Vereniging")),
    ("anders", "Anders", _("Anders")),
)
# Where Huismus runs: not asked, Huismus knows (runs_on()).
PLATFORMS = (
    ("mac", "Desktop-app op een Mac", _("Desktop-app op een Mac")),
    ("windows", "Desktop-app op Windows", _("Desktop-app op Windows")),
    ("docker", "Docker, op een server of NAS", _("Docker, op een server of NAS")),
)

# Settings.feedback_status. Not asked yet: the done page of the step-by-step
# start asks; skipped or sent: it doesn't ask again.
NOT_ASKED = ""
SKIPPED = "skipped"
SENT = "sent"
STATUS_CHOICES = [(NOT_ASKED, "not asked"), (SKIPPED, "skipped"), (SENT, "sent")]

ORGANISATION_CHOICES = [(key, label) for key, _text, label in ORGANISATIONS]


class SendError(Exception):
    """The form didn't take it. str(error) is what the site said, for the log."""


def _form_text(choices, key: str) -> str:
    return next((text for k, text, _label in choices if k == key), "")


def _label(choices, key: str) -> str:
    return next((str(label) for k, _text, label in choices if k == key), "")


def runs_on() -> str:
    """Desktop app on a Mac or Windows; anything else is Docker (SPEC.md
    principle 6: one container, or one desktop app), a development server
    included."""
    if settings.DESKTOP and sys.platform == "darwin":
        return "mac"
    if settings.DESKTOP and sys.platform == "win32":
        return "windows"
    return "docker"


def form_language(language: str | None = None) -> str:
    """The language the form is told about: the app's, nl or en."""
    language = (language or get_language() or "nl")[:2]
    return language if language in ("nl", "en") else "nl"


def outgoing(organisation: str, wish: str, email: str, language: str | None = None) -> list:
    """Everything that goes, as (label, value) for the overview. send()
    sends exactly these fields and nothing more."""
    language = form_language(language)
    return [
        (_("Organisatie"), _label(ORGANISATIONS, organisation)),
        (_("Wat je mist"), wish),
        (_("E-mailadres"), email),
        (_("Draait op"), _label(PLATFORMS, runs_on())),
        (_("Versie"), current_version()),
        (_("Taal"), "English" if language == "en" else "Nederlands"),
    ]


def form_data(organisation: str, wish: str, email: str, language: str | None = None) -> dict:
    """The fields of the form on the site, plus the hidden ones its REST
    endpoint needs. An unknown organisation stays empty: the site refuses it."""
    return {
        "_wpcf7_unit_tag": UNIT_TAG,
        "_wpcf7_container_post": str(PAGE_ID),
        "organisatie": _form_text(ORGANISATIONS, organisation),
        "gebruik": _form_text(PLATFORMS, runs_on()),
        "wens": wish,
        "email": email,
        "versie": current_version(),
        "taal": form_language(language),
    }


def multipart(fields: dict) -> tuple[bytes, str]:
    """The body and Content-Type of a multipart/form-data POST: the only
    kind the endpoint of Contact Form 7 accepts. A few lines instead of a
    dependency: the names are fixed (form_data), and a value can't end a
    part early, because the boundary is random."""
    boundary = f"huismus-{secrets.token_hex(16)}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
        for name, value in fields.items()
    ]
    body = "".join(parts) + f"--{boundary}--\r\n"
    return body.encode(), f"multipart/form-data; boundary={boundary}"


def send(organisation: str, wish: str, email: str, language: str | None = None) -> None:
    """Post the answers to the form. Raises SendError unless the site says
    it mailed them."""
    data, content_type = multipart(form_data(organisation, wish, email, language))
    request = urllib.request.Request(
        SEND_URL,
        data=data,
        headers={
            "User-Agent": f"Huismus/{current_version()}",
            "Accept": "application/json",
            "Content-Type": content_type,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read(100_000))
    except (OSError, ValueError) as error:
        # OSError: no connection, a timeout, or an HTTP error page;
        # ValueError: an answer that isn't JSON.
        logger.warning("Feedback not sent: %s", error)
        raise SendError(str(error)) from error
    if not isinstance(answer, dict) or answer.get("status") != "mail_sent":
        answer = answer if isinstance(answer, dict) else {}
        logger.warning("Feedback not taken: %s %s", answer.get("status"), answer.get("message"))
        raise SendError(str(answer.get("status")))
