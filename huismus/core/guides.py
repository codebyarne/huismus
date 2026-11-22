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
from xml.etree.ElementTree import Element

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


def _split(slug: str, language: str) -> tuple[str, str]:
    """(title, the rest) of a file."""
    heading, _newline, body = source(slug, language).partition("\n")
    return heading.removeprefix("# ").strip(), body


def title(slug: str, language: str) -> str:
    return _split(slug, language)[0]


def summary(slug: str, language: str) -> str:
    """The first paragraph under the title: the list on /uitleg/, the line
    under the title and what a search result shows."""
    return " ".join(_split(slug, language)[1].strip().split("\n\n")[0].split())


def parts(slug: str, language: str) -> tuple[str, str, str]:
    """The Markdown of (the explanation, in Huismus, the sources), each
    without its heading and the explanation without the summary. A file
    that misses a part raises ValueError."""
    body = _split(slug, language)[1].strip()
    _summary, _blank, rest = body.partition("\n\n")
    explanation, found, rest = rest.partition(f"\n## {IN_HUISMUS[language]}\n")
    in_huismus, found_sources, sources = rest.partition(f"\n## {SOURCES[language]}\n")
    if not (found and found_sources):
        raise ValueError(f"{slug}.{language}.md mist een deel.")
    return explanation.strip(), in_huismus.strip(), sources.strip()


class _Links(markdown.treeprocessors.Treeprocessor):
    def __init__(self, md, help_link: Callable[[str, str], str], link: Callable[[str], str]):
        super().__init__(md)
        self.help_link, self.link = help_link, link

    def run(self, root: Element) -> None:
        for a in root.iter("a"):
            match = _LINK.match(a.get("href", ""))
            if not match:
                continue
            anchor = match["anchor"] or ""
            if match["help"]:
                a.set("href", self.help_link(match["slug"], anchor))
            else:
                a.set("href", self.link(match["slug"]) + anchor)


class _LinksExtension(markdown.extensions.Extension):
    def __init__(self, help_link: Callable[[str, str], str], link: Callable[[str], str]):
        super().__init__()
        self.help_link, self.link = help_link, link

    def extendMarkdown(self, md):  # noqa: N802 (the name Markdown calls)
        # After "inline" (priority 20), which makes the <a> elements.
        md.treeprocessors.register(_Links(md, self.help_link, self.link), "guide_links", 5)


def render(
    slug: str,
    language: str,
    help_link: Callable[[str, str], str],
    link: Callable[[str], str],
) -> GuidePage:
    """The page as HTML. `help_link(slug, anchor)` gives the address of a
    help page and `link(slug)` that of another page here."""
    extensions = ["tables", "toc", _LinksExtension(help_link, link)]
    explanation, in_huismus, sources = (
        markdown.markdown(part, extensions=extensions) for part in parts(slug, language)
    )
    return GuidePage(
        slug, title(slug, language), summary(slug, language), explanation, in_huismus, sources
    )


def help_topics() -> tuple[str, ...]:
    """The help pages a page here may link to: the ones the site has."""
    return tuple(slug for slug in help.TOPICS if slug != help.FEEDBACK)
