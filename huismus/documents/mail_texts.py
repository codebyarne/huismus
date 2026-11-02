# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The text a mail starts from (SPEC.md M10): per kind of document and per
language, set in Instellingen → Mailen, or the standard text below when
that setting is empty. Placeholders like {nummer} are filled in per
document; the user can still change everything per mail.
"""

import re

from django.utils import translation
from django.utils.translation import gettext as _

KINDS = ["invoice", "credit_note", "quote"]
LANGUAGES = ["nl", "en"]

# Every placeholder, and the kinds it belongs to. The names are Dutch in
# both languages: they are what the user types in the settings screen.
PLACEHOLDERS = {
    "nummer": KINDS,
    "bedrag": KINDS,
    "naam": KINDS,
    "bedrijf": KINDS,
    "vervaldatum": ["invoice"],
    "geldig_tot": ["quote"],
}
DATE_PLACEHOLDERS = {"vervaldatum", "geldig_tot"}
_PLACEHOLDER = re.compile(r"\{(\w+)\}")


def field_name(kind: str, part: str, language: str) -> str:
    """The Settings field for e.g. ("invoice", "subject", "nl")."""
    return f"mail_{kind}_{part}_{language}"


def standard_text(kind: str, part: str, language: str) -> str:
    with translation.override(language):
        if part == "subject":
            return {
                "invoice": _("Factuur {nummer} van {bedrijf}"),
                "credit_note": _("Creditnota {nummer} van {bedrijf}"),
                "quote": _("Offerte {nummer} van {bedrijf}"),
            }[kind]
        attached = {
            "invoice": _("In de bijlage vind je factuur {nummer} van {bedrag}."),
            "credit_note": _("In de bijlage vind je creditnota {nummer} van {bedrag}."),
            "quote": _("In de bijlage vind je offerte {nummer} van {bedrag}."),
        }[kind]
        # A line of its own, so it can be left out when there is no date.
        date_line = {
            "invoice": "\n" + _("Wil je hem uiterlijk {vervaldatum} betalen?"),
            "credit_note": "",
            "quote": "\n" + _("De offerte is geldig tot {geldig_tot}."),
        }[kind]
        return (
            _("Beste {naam},")
            + f"\n\n{attached}{date_line}\n\n"
            + _("Met vriendelijke groet,")
            + "\n{bedrijf}\n"
        )


def unknown_placeholders(text: str, kind: str) -> list[str]:
    """The {…} in text that are not a placeholder for this kind."""
    return [
        f"{{{name}}}"
        for name in _PLACEHOLDER.findall(text)
        if kind not in PLACEHOLDERS.get(name, [])
    ]


def fill(text: str, values: dict[str, str]) -> str:
    """The text with its placeholders filled in. A line with a date
    placeholder whose date is missing (a quote without an end date) is left
    out as a whole; anything else in braces stays as it is."""
    lines = [
        line
        for line in text.split("\n")
        if not any(f"{{{name}}}" in line and not values.get(name) for name in DATE_PLACEHOLDERS)
    ]
    return _PLACEHOLDER.sub(
        lambda match: values.get(match.group(1), match.group(0)), "\n".join(lines)
    )
