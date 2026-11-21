# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus?: what kind of organisation someone has, what
they miss and how to reach them, sent to the app's maker only if they
choose to (huismus-intern/besluiten.md, 2026-11-01 and 2026-11-02).

Huismus sends it itself, to the Contact Form 7 form on arnekrijnsen.com,
but only when the user presses Versturen after seeing everything that goes
along: the third kind of outgoing request of SPEC.md principle 6. Where
Huismus runs, its version and its language Huismus fills in itself, and
from the settings whether there is a text for reverse-charge invoices and
the language invoices are in (#268); they are in that overview too.

The choices are those of the issue form (.github/ISSUE_TEMPLATE/idee.yml).
The form on the site takes a choice only when the value is exactly its
option text, so each choice has that text here, the same in every language
of the app; `taal` says which language the app speaks.
"""

import base64
import binascii
import json
import logging
import secrets
import sys
import urllib.request

from django.conf import settings
from django.utils import translation
from django.utils.translation import get_language
from django.utils.translation import gettext_lazy as _

from .updates import current_version

logger = logging.getLogger("huismus.feedback")

# The form "Huismus: vertel wie je bent" on the maker's site: Contact Form 7,
# form 2943 on the page /huismus-vertel/ (2939). Its REST endpoint wants the
# form's unit tag on that page. A new form on the site means new numbers here.
# The site lets this form skip reCAPTCHA for a User-Agent "Huismus/<version>"
# (plugin Huismus-formulier, huismus-intern/wordpress/), but only when the
# request looks exactly like this one (the same version in "versie", a known
# "taal" and "gebruik", and "btw_verlegd" and "factuurtaal" either missing,
# as from Huismus before #268, or a value of invoice_setup()) and only a
# few times an hour: the User-Agent is public,
# so anyone could copy it. Change those fields here, change the plugin too.
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

# The feedback button (huismus-intern/besluiten.md, 2026-11-21): what kind
# of message it is, as (key, option text on the form, label in the app).
KINDS = (
    ("probleem", "Iets werkt niet", _("Iets werkt niet")),
    ("idee", "Idee", _("Idee")),
    ("vraag", "Vraag", _("Vraag")),
)
KIND_CHOICES = [(key, label) for key, _text, label in KINDS]
MAX_PAGE = 200
# The picture of the screen, as the browser made it (feedback.js): a PNG,
# at most this many bytes. The form on the site takes up to 2 MB.
MAX_IMAGE_BYTES = 1_500_000
IMAGE_PREFIX = "data:image/png;base64,"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


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


def invoice_setup() -> tuple[str, str]:
    """From the settings, as sent to the form: "ja" when there is a text
    for reverse-charge invoices, else "nee" (never the text itself), and the
    invoice language, nl or en. Where the reverse charge applies (NL, EU or
    outside the EU) is in no setting, so it doesn't go."""
    # Here, not at the top: business.models imports this module's choices.
    from huismus.business.models import Settings

    instance = Settings.load()
    reverse_charge = "ja" if instance.reverse_charge_text.strip() else "nee"
    return reverse_charge, "en" if instance.default_language == "en" else "nl"


def outgoing(organisation: str, wish: str, email: str, language: str | None = None) -> list:
    """Everything that goes, as (label, value) for the overview. send()
    sends exactly these fields and nothing more. What Huismus fills in
    itself is read again at Versturen, like the version: a setting changed
    in between goes as it is then."""
    language = form_language(language)
    reverse_charge, invoice_language = invoice_setup()
    return [
        (_("Organisatie"), _label(ORGANISATIONS, organisation)),
        (_("Wat je mist"), wish),
        (_("E-mailadres"), email),
        (_("Draait op"), _label(PLATFORMS, runs_on())),
        (_("Versie"), current_version()),
        (_("Taal van de app"), "English" if language == "en" else "Nederlands"),
        (_("Btw verlegd"), _("Ja") if reverse_charge == "ja" else _("Nee")),
        (_("Taal van je facturen"), "English" if invoice_language == "en" else "Nederlands"),
    ]


def form_data(organisation: str, wish: str, email: str, language: str | None = None) -> dict:
    """The fields of the form on the site, plus the hidden ones its REST
    endpoint needs. An unknown organisation stays empty: the site refuses it."""
    reverse_charge, invoice_language = invoice_setup()
    return {
        "_wpcf7_unit_tag": UNIT_TAG,
        "_wpcf7_container_post": str(PAGE_ID),
        "organisatie": _form_text(ORGANISATIONS, organisation),
        "gebruik": _form_text(PLATFORMS, runs_on()),
        "wens": wish,
        "email": email,
        "versie": current_version(),
        "taal": form_language(language),
        "btw_verlegd": reverse_charge,
        "factuurtaal": invoice_language,
    }


def how_you_work(instance) -> str:
    """Hoe je werkt, in the language that is active: the organisation last
    sent from "Hoe gebruik je Huismus?" and what the step-by-step start set
    (huismus-intern/besluiten.md, 2026-11-21). The start keeps no answers,
    only settings, so KOR off says "with VAT, or not chosen yet"."""
    parts = []
    organisation = _label(ORGANISATIONS, instance.feedback_organisation)
    if organisation:
        parts.append(organisation)
    parts.append(
        _("met KOR") if instance.kor_enabled else _("btw op facturen, of nog niet gekozen")
    )
    if instance.reverse_charge_text.strip():
        parts.append(_("btw verlegd: ja"))
    else:
        parts.append(_("btw verlegd: nee"))
    if instance.default_language == "en":
        parts.append(_("facturen in het Engels"))
    else:
        parts.append(_("facturen in het Nederlands"))
    return " · ".join(str(part) for part in parts)


def image_bytes(data_url: str) -> bytes | None:
    """The PNG in a data: URL from the browser, or None when it is not one
    (not base64, not a PNG, too big)."""
    if not data_url.startswith(IMAGE_PREFIX):
        return None
    try:
        image = base64.b64decode(data_url[len(IMAGE_PREFIX) :], validate=True)
    except (binascii.Error, ValueError):
        return None
    if not image.startswith(PNG_SIGNATURE) or len(image) > MAX_IMAGE_BYTES:
        return None
    return image


def quick_outgoing(instance, kind, message, email, page, has_image, language=None) -> list:
    """Everything the feedback button sends, as (label, value) for the
    overview. send_quick() sends these fields and the picture; like the
    choices, the kind and Hoe je werkt go in Dutch, whatever the app's language."""
    language = form_language(language)
    return [
        (_("Soort"), _label(KINDS, kind)),
        (_("Bericht"), message),
        (_("Pagina"), page),
        (_("Afbeelding"), _("ja, hierboven") if has_image else _("nee")),
        (_("E-mailadres"), email),
        (_("Hoe je werkt"), how_you_work(instance)),
        (_("Draait op"), _label(PLATFORMS, runs_on())),
        (_("Versie"), current_version()),
        (_("Taal"), "English" if language == "en" else "Nederlands"),
    ]


def quick_form_data(instance, kind, message, email, page, language=None) -> dict:
    """The fields of the form on the site for the feedback button: the same
    form as form_data(), with soort, pagina and werkwijze besides. The
    organisation goes only when it was sent before; the site does not need
    it from the button. Hoe je werkt goes in Dutch, like the choices."""
    with translation.override("nl"):
        work = how_you_work(instance)
    return {
        "_wpcf7_unit_tag": UNIT_TAG,
        "_wpcf7_container_post": str(PAGE_ID),
        "organisatie": _form_text(ORGANISATIONS, instance.feedback_organisation),
        "gebruik": _form_text(PLATFORMS, runs_on()),
        "soort": _form_text(KINDS, kind),
        "wens": message,
        "pagina": page,
        "werkwijze": work,
        "email": email,
        "versie": current_version(),
        "taal": form_language(language),
    }


def multipart(fields: dict, files: dict | None = None) -> tuple[bytes, str]:
    """The body and Content-Type of a multipart/form-data POST: the only
    kind the endpoint of Contact Form 7 accepts. A few lines instead of a
    dependency: the names are fixed (form_data), and a value can't end a
    part early, because the boundary is random. files: name → (file name,
    media type, bytes)."""
    boundary = f"huismus-{secrets.token_hex(16)}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode()
        for name, value in fields.items()
    ]
    for name, (filename, media_type, content) in (files or {}).items():
        head = (
            f"--{boundary}\r\nContent-Disposition: form-data; "
            f'name="{name}"; filename="{filename}"\r\nContent-Type: {media_type}\r\n\r\n'
        )
        parts.append(head.encode() + content + b"\r\n")
    body = b"".join(parts) + f"--{boundary}--\r\n".encode()
    return body, f"multipart/form-data; boundary={boundary}"


def send(organisation: str, wish: str, email: str, language: str | None = None) -> None:
    """Post the answers to the form. Raises SendError unless the site says
    it mailed them."""
    _post(*multipart(form_data(organisation, wish, email, language)))


def send_quick(instance, kind, message, email, page, image=None, language=None) -> None:
    """Post what the feedback button collected, with the picture of the
    screen as a file when there is one. Raises SendError like send()."""
    files = {"afbeelding": ("huismus.png", "image/png", image)} if image else None
    _post(*multipart(quick_form_data(instance, kind, message, email, page, language), files))


def _post(data: bytes, content_type: str) -> None:
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
