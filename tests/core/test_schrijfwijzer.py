# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The measurable part of docs/schrijfwijzer.md, for every UI text, help page and doc.

The Dutch source texts (the msgids) and docs/hulp/*.nl.md say "je", never
"u"; the English translations and docs/hulp/*.en.md follow the same rules.
The lists stay short on purpose: a check that rejects good text gets ignored
(huismus-intern/besluiten.md, 2026-11-01, "Teksten in de Huismus-stem").
"""

import ast
import re
from pathlib import Path

import pytest
from django.conf import settings

ROOT = Path(settings.BASE_DIR)
LOCALE = ROOT / "huismus" / "locale"
HELP = ROOT / "docs" / "hulp"

# The README and docs/*.md hold Dutch and English side by side, so both
# lists apply. Two are left out on purpose: the writing guide quotes the
# words it forbids, and the invoice requirements quote the Belastingdienst
# (text about law or tax is a question for the owner, CLAUDE.md).
DOCS_NOT_CHECKED = {"schrijfwijzer.md", "invoice-requirements.md"}

# A sentence joined with an em dash; the writing guide wants a full stop,
# a colon or a comma. (A title like "Back-ups — Huismus" is not a msgid.)
EM_DASH = ("—", "em-dash in een zin / em dash in a sentence")

# Per language: what the writing guide forbids, as (pattern, why).
FORBIDDEN = {
    "nl": [
        (r"\b[Uu]w?\b", "je/jij, nooit u"),
        (r"\bnaadloo?s|\bnaadloze\b", "corporate taal"),
        (r"\bcruciaa?l(e)?\b", "corporate taal"),
        (r"\bgelieve\b", "corporate taal"),
        (r"\bsuccesvol(le)?\b", "corporate taal"),
        (r"\boptima(al|le)\b", "corporate taal"),
        EM_DASH,
    ],
    "en": [
        (r"\bseamless(ly)?\b", "corporate words"),
        (r"\bleverag(e|es|ing)\b", "corporate words"),
        (r"\bplease note\b", "corporate words"),
        EM_DASH,
    ],
}

# Text a help page or the site's download page quotes from another program,
# word for word. It's not ours to rewrite, so it doesn't count.
QUOTED_FROM_ELSEWHERE = ['"Windows heeft uw pc beschermd"']

# One line of a .po entry: a keyword with a string, e.g. msgid "Opslaan" or
# msgstr[1] "%(count)s invoices". A line with just a string continues it.
PO_KEYWORD = re.compile(r'^(msgctxt|msgid|msgid_plural|msgstr)(?:\[\d+\])? (".*")$')


def _po_strings(text: str) -> list[tuple[str, str]]:
    """Every string in a .po file as (keyword, text), long strings joined.

    Obsolete entries ("#~ msgid …") don't match PO_KEYWORD and are skipped.
    ast.literal_eval turns a quoted .po string into text, escapes and all.
    """
    strings: list[list[str]] = []
    for line in text.splitlines():
        if match := PO_KEYWORD.match(line):
            strings.append([match.group(1), ast.literal_eval(match.group(2))])
        elif line.startswith('"') and strings:
            strings[-1][1] += ast.literal_eval(line)
    return [(keyword, value) for keyword, value in strings if value]


def _po_texts(language: str) -> list[str]:
    """The texts a user reads: the Dutch msgids, or the English msgstrs."""
    path = LOCALE / language / "LC_MESSAGES" / "django.po"
    wanted = ("msgid", "msgid_plural") if language == "nl" else ("msgstr",)
    return [value for keyword, value in _po_strings(path.read_text()) if keyword in wanted]


def _prose(markdown: str) -> str:
    """A help page without what may say anything: code and quoted programs."""
    markdown = re.sub(r"^```.*?^```", "", markdown, flags=re.M | re.S)  # code blocks
    markdown = re.sub(r"`[^`]*`", "", markdown)  # inline code, such as `id -u`
    for quote in QUOTED_FROM_ELSEWHERE:
        markdown = markdown.replace(quote, "")
    return markdown


def _offences(language: str, texts: list[str]) -> list[str]:
    return [
        f"{why}: {text!r}"
        for text in texts
        for pattern, why in FORBIDDEN[language]
        if re.search(pattern, text)
    ]


@pytest.mark.parametrize("language", ["nl", "en"])
def test_ui_texts_follow_the_writing_guide(language):
    texts = _po_texts(language)
    assert ("Opslaan" if language == "nl" else "Save") in texts, "the .po file was not read"
    for quote in QUOTED_FROM_ELSEWHERE:
        texts = [text.replace(quote, "") for text in texts]
    assert _offences(language, texts) == []


@pytest.mark.parametrize("language", ["nl", "en"])
def test_desktop_texts_follow_the_writing_guide(language):
    # The desktop window's own screens run before Django, so their texts
    # live in Python instead of the .po files.
    from desktop import screens, windows

    texts = [*screens.TEXTS[language].values(), windows.TEXTS[language]]
    assert _offences(language, texts) == []


@pytest.mark.parametrize("language", ["nl", "en"])
def test_help_pages_follow_the_writing_guide(language):
    pages = sorted(HELP.glob(f"*.{language}.md"))
    assert pages
    lines = [line for page in pages for line in _prose(page.read_text()).splitlines()]
    assert _offences(language, lines) == []


def _docs() -> list[Path]:
    docs = sorted(p for p in (ROOT / "docs").glob("*.md") if p.name not in DOCS_NOT_CHECKED)
    return [ROOT / "README.md", *docs]


def test_readme_and_docs_follow_the_writing_guide():
    pages = _docs()
    assert ROOT / "docs" / "tailscale.md" in pages
    lines = [line for page in pages for line in _prose(page.read_text()).splitlines()]
    # Both lists on every line: the Dutch patterns (u/uw, Dutch words) don't
    # match normal English, and the English ones don't match Dutch.
    assert [*_offences("nl", lines), *_offences("en", lines)] == []


def test_the_po_reader_joins_long_strings_reads_plurals_and_skips_obsolete_ones():
    sample = "\n".join(
        [
            'msgid ""',
            'msgstr ""',
            '"Project-Id-Version: huismus\\n"',
            "",
            'msgid ""',
            '"Een lange zin die "',
            '"doorloopt."',
            'msgstr "A long sentence that goes on."',
            "",
            'msgid "%(count)s factuur"',
            'msgid_plural "%(count)s facturen"',
            'msgstr[0] "%(count)s invoice"',
            'msgstr[1] "%(count)s invoices"',
            "",
            '#~ msgid "Oud — weg"',
            '#~ msgstr "Old — gone"',
        ]
    )
    assert _po_strings(sample) == [
        ("msgstr", "Project-Id-Version: huismus\n"),
        ("msgid", "Een lange zin die doorloopt."),
        ("msgstr", "A long sentence that goes on."),
        ("msgid", "%(count)s factuur"),
        ("msgid_plural", "%(count)s facturen"),
        ("msgstr", "%(count)s invoice"),
        ("msgstr", "%(count)s invoices"),
    ]


def test_the_check_catches_what_it_should():
    """The patterns themselves: u-form and an em dash caught, normal words left alone."""
    assert len(_offences("nl", ["Wilt u dit opslaan?", "Uw factuur", "Klaar — opgeslagen"])) == 3
    assert not _offences("nl", ["Je factuur staat klaar.", "Gebruik uitgaven", "Huismus"])
    assert not _offences("en", ["Back up now", "Use a seam ripper"])
    assert _prose('Kies "Windows heeft uw pc beschermd" en `id -u`') == "Kies  en "
