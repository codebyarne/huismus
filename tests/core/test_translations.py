# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The English catalog is complete: every UI string has a translation.

A missing or "fuzzy" entry falls back to Dutch in an otherwise English UI —
easy to miss by looking, so it's checked here. (CLAUDE.md: Dutch and
English strings for every milestone.)
"""

import re
from pathlib import Path

from django.conf import settings

CATALOG = Path(settings.CODE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"


def _entries():
    """The catalog's entries as text blocks, without the header (msgid "")
    and without obsolete ones (#~)."""
    blocks = CATALOG.read_text().split("\n\n")
    for block in blocks:
        lines = [line for line in block.splitlines() if not line.startswith("#~")]
        text = "\n".join(lines)
        if 'msgid ""\nmsgstr ""\n"Project-Id-Version' in text or "msgid " not in text:
            continue
        yield text


def _is_empty(block: str, field: str) -> bool:
    """True when `field` (msgstr or msgstr[n]) is "" with no continuation lines."""
    match = re.search(rf'^{re.escape(field)} ""\n(?!")', block + "\n", re.M)
    return match is not None


def test_no_fuzzy_entries():
    fuzzy = [block for block in _entries() if "#, fuzzy" in block or ", fuzzy" in block]
    assert fuzzy == [], "fuzzy in huismus/locale/en: " + "; ".join(
        b.splitlines()[-2] for b in fuzzy
    )


def test_every_entry_is_translated():
    untranslated = []
    for block in _entries():
        fields = re.findall(r"^(msgstr(?:\[\d+\])?) ", block, re.M)
        if any(_is_empty(block, field) for field in fields):
            untranslated.append(re.search(r'^msgid "(.*)"', block, re.M).group(1) or block)
    assert untranslated == [], f"untranslated in huismus/locale/en: {untranslated[:10]}"


def test_every_template_string_finds_its_english_translation():
    """Every {% translate "…" %} in a template is found in the English
    catalog the way Django looks it up at runtime, so also on a screen
    test_every_page doesn't see (a form with the KOR off). Found by hand
    (BUGS-BY-HAND.md, 2026-11-06): a "%" in a template string is "%%" in
    the catalog, and an entry added without it was never found."""
    from django.utils import translation

    pattern = re.compile(r'{%\s*translate\s+"((?:[^"\\]|\\.)*)"(?:\s+as\s+\w+)?\s*%}')
    missing = []
    for template in (Path(settings.CODE_DIR) / "templates").rglob("*.html"):
        for text in pattern.findall(template.read_text()):
            # As Django's translate tag asks the catalog for it.
            msgid = text.replace("%", "%%")
            with translation.override("en"):
                found = translation.gettext(msgid)
            if found == msgid and not re.fullmatch(r"[\W\d]*|[A-Z][\w-]*|\w+@\S+", text):
                missing.append(f"{template.name}: {text}")
    assert missing == [], "not found in huismus/locale/en: " + "; ".join(missing[:10])
