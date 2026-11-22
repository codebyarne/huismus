# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A suggestion for the legal form choice (Settings.legal_entity, #302) on
an installation that has none yet: from the free text typed before, when it
can mean only one thing, else from the old answer in "Hoe gebruik je
Huismus?". Only shown as preselected in the form; nothing is stored until
the user saves (huismus-intern/product/profiel-en-functies.md, section 2a)."""

from huismus.core.profile import (
    ASSOCIATION,
    FOUNDATION,
    PARTNERSHIP,
    PRIVATE_COMPANY,
    SOLE_PROPRIETOR,
)

# The free text in lower case, without dots and spaces.
FROM_TEXT = {
    "eenmanszaak": SOLE_PROPRIETOR,
    "vof": PARTNERSHIP,
    "vennootschaponderfirma": PARTNERSHIP,
    "bv": PRIVATE_COMPANY,
    "beslotenvennootschap": PRIVATE_COMPANY,
    "stichting": FOUNDATION,
    "vereniging": ASSOCIATION,
}
# Settings.feedback_organisation. "kor" and "btw" were "Eenmanszaak of vof":
# which of the two, Huismus doesn't guess.
FROM_CARD = {"bv": PRIVATE_COMPANY, "stichting": FOUNDATION, "vereniging": ASSOCIATION}


def suggestion(settings) -> str:
    """The choice to preselect, or "" for none (also once one is chosen)."""
    if settings.legal_entity:
        return ""
    text = "".join(settings.legal_form.lower().replace(".", "").split())
    return FROM_TEXT.get(text) or FROM_CARD.get(settings.feedback_organisation, "")
