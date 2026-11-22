# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uitleg: pages on the Huismus site about how something works for a
freelancer (what goes on an invoice, the KOR limit), apart from Huismus
(issue #308). Only the site shows them (core.site); the app doesn't.

One Markdown file per page per language, docs/uitleg/<slug>.<nl|en>.md, in
three parts:

    # Title
    <a plain paragraph that sums the page up>
    <the explanation>
    ## Zo doe je dit in Huismus     (IN_HUISMUS)
    <what Huismus does, with a link to a help page>
    ## Bronnen                      (SOURCES)
    <the official pages, and the day they were checked>

Every statement comes from docs/belastingregels.md or
docs/invoice-requirements.md, and every link to another site is a source
page listed there: without a source there is no page (CLAUDE.md, "Privacy
and safety"). tests/core/test_guides.py checks the parts and the links.

A link to a help page is written as `../hulp/facturen.nl.md#uitgeven` and one
to another page here as `kor.nl.md`, so both also work on GitHub.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

import markdown
from django.conf import settings

from . import help

GUIDES_DIR = settings.BASE_DIR / "docs" / "uitleg"
# The order of the list on /uitleg/.
GUIDES = ("factuureisen", "kor", "kor-grens", "btw-aangifte", "bewaarplicht")
# The headings that start the second and third part of a file.
IN_HUISMUS = {"nl": "Zo doe je dit in Huismus", "en": "How to do this in Huismus"}
SOURCES = {"nl": "Bronnen", "en": "Sources"}

_LINK = re.compile(r"^(?P<help>\.\./hulp/)?(?P<slug>[a-z0-9-]+)\.(?:nl|en)\.md(?P<anchor>#.*)?$")


@dataclass(frozen=True)
class GuidePage:
    slug: str
    title: str
    summary: str
    html: str
    in_huismus_html: str
    sources_html: str


def source(slug: str, language: str) -> str:
    if slug not in GUIDES:
        raise KeyError(slug)
    return (GUIDES_DIR / f"{slug}.{language}.md").read_text(encoding="utf-8")


def title(slug: str, language: str) -> str:
    return help.split_title(source(slug, language))[0]


def summary(slug: str, language: str) -> str:
    """The first paragraph under the title: the list on /uitleg/, the line
    under the title and what a search result shows."""
    return help.first_paragraph(help.split_title(source(slug, language))[1])


def parts(slug: str, language: str) -> tuple[str, str, str]:
    """The Markdown of (the explanation, in Huismus, the sources), each
    without its heading and the explanation without the summary. A file
    that misses a part raises ValueError."""
    body = help.split_title(source(slug, language))[1].strip()
    _summary, _blank, rest = body.partition("\n\n")
    pieces = []
    for heading in (IN_HUISMUS[language], SOURCES[language]):
        piece, found, rest = rest.partition(f"\n## {heading}\n")
        if not found:
            raise ValueError(f'{slug}.{language}.md mist de kop "## {heading}".')
        pieces.append(piece.strip())
    return pieces[0], pieces[1], rest.strip()


def render(
    slug: str,
    language: str,
    help_link: Callable[[str, str], str],
    link: Callable[[str], str],
) -> GuidePage:
    """The page as HTML. `help_link(slug, anchor)` gives the address of a
    help page and `link(slug)` that of another page here: the addresses are
    the site's (core.site), which builds on this module and not the other
    way round."""

    def rewrite(href: str) -> str | None:
        match = _LINK.match(href)
        if not match:
            return None
        anchor = match["anchor"] or ""
        if match["help"]:
            return help_link(match["slug"], anchor)
        return link(match["slug"]) + anchor

    extensions = ["tables", "toc", help.LinksExtension(rewrite)]
    explanation, in_huismus, sources = (
        markdown.markdown(part, extensions=extensions) for part in parts(slug, language)
    )
    return GuidePage(
        slug, title(slug, language), summary(slug, language), explanation, in_huismus, sources
    )
