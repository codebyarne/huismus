# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stel een vraag: the form on the site (mijnhuismus.nl) that sends a
question to the maker of Huismus, who answers by mail
(huismus-intern/besluiten.md, 2026-11-25).

The site is static HTML without JavaScript (core.site), so the form posts
as a plain HTML form to a page on arnekrijnsen.com that holds a Contact
Form 7 form. Contact Form 7 handles a POST with `_wpcf7` on any page of the
site (its non-Ajax mode) and mails the question to the maker. The plugin
Huismus-formulier (huismus-intern/wordpress/) skips reCAPTCHA for this one
form, which needs JavaScript, but only for a POST from this site and a few
times an hour; the honeypot and Akismet stay on. Then it sends the visitor
back here: to the page Verstuurd or, when the form didn't take it, Mislukt.

The names of the fields are those of the form on arnekrijnsen.com. Change
one here, change it there and in the plugin too. The page says the question
doesn't go to GitHub: the plugin makes an issue only for the form of
Hoe gebruik je Huismus? (core.feedback), never for this one.
"""

from django.utils.translation import gettext_lazy as _

# What the maker promises (huismus-intern/besluiten.md, 2026-11-25): "meestal",
# because one person can't keep a hard deadline.
PROMISE = _(
    "Je krijgt een persoonlijk antwoord van de maker, per mail. Meestal binnen twee werkdagen."
)

# The form "Huismus: stel een vraag" on the maker's site and the page it is
# on. Contact Form 7 finds the form by `_wpcf7`; the page is where the POST
# goes and where Contact Form 7 would show its answer if the plugin didn't
# send the visitor back.
FORM_ID = 0
PAGE_ID = 0
ACTION_URL = "https://www.arnekrijnsen.com/huismus-vraag/"

# The form's own limits (maxlength on arnekrijnsen.com).
MAX_QUESTION = 2000
MAX_EMAIL = 400

# The honeypot field: hidden from people, a bot fills it in, and then
# Contact Form 7 (plugin Honeypot for Contact Form 7) calls it spam. A name
# without a meaning for autofill, so a browser never fills it in for a person.
HONEYPOT = "hm_leeg"

# Where someone uses Huismus, as (value sent, label on the page). The values
# are the options of the select on arnekrijnsen.com, the same in both
# languages; Contact Form 7 refuses any other value.
PLATFORMS = (
    ("Mac", _("Mac-app")),
    ("Windows", _("Windows-app")),
    ("Docker", _("Docker (in de browser)")),
    ("Nog niet", _("Nog niet")),
)


def hidden_fields(language: str) -> list[tuple[str, str]]:
    """The hidden fields of the form: what Contact Form 7 needs to find it,
    and the language of the page, so the plugin sends the visitor back to a
    page in the same language."""
    return [
        ("_wpcf7", str(FORM_ID)),
        ("_wpcf7_unit_tag", f"wpcf7-f{FORM_ID}-p{PAGE_ID}-o1"),
        ("_wpcf7_container_post", str(PAGE_ID)),
        ("taal", language),
    ]
