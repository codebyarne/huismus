# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The help pages: the user documentation in docs/hulp/, shown in the app.

The same Markdown files are read on GitHub and on the Huismus site (core.site,
huismus-intern/besluiten.md, 2026-10-30), so the explanation always belongs to the
version someone runs. One file per topic per language:
docs/hulp/<slug>.<nl|en>.md: a "# " title on the first line, an empty
line, and a plain paragraph that sums the topic up (the list on /hulp/).
tests/core/test_help.py checks that.

A help file links to another one by its file name (`back-ups.nl.md#…`), so
the link works on GitHub too; here it becomes the help page's address.
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from xml.etree.ElementTree import Element

import markdown
from django.conf import settings
from django.urls import reverse
from django.utils.translation import get_language

HELP_DIR = settings.BASE_DIR / "docs" / "hulp"
LANGUAGES = ("nl", "en")
# The order of the list on /hulp/.
# "Feedback geven" also shows the card Hoe gebruik je Huismus? (core.feedback_views).
FEEDBACK = "feedback"
TOPICS = (
    "beginnen",
    "facturen",
    "offertes",
    "uitgaven",
    "kor-en-btw",
    "moneybird",
    "back-ups",
    "exporteren",
    "mailen",
    "ai-assistenten",
    "desktop-app",
    "docker",
    "vps",
    "telefoon",
    # What each weekly release brings; written on release day (CLAUDE.md, Releases).
    "nieuw",
    FEEDBACK,
)

_HELP_LINK = re.compile(r"^(?P<slug>[a-z0-9-]+)\.(?:nl|en)\.md(?P<anchor>#.*)?$")


@dataclass(frozen=True)
class HelpPage:
    slug: str
    title: str
    html: str


def _language(language: str | None) -> str:
    language = (language or get_language() or "nl")[:2]
    return language if language in LANGUAGES else "nl"


def source(slug: str, language: str | None = None) -> str:
    if slug not in TOPICS:
        raise KeyError(slug)
    return (HELP_DIR / f"{slug}.{_language(language)}.md").read_text(encoding="utf-8")


def _split(slug: str, language: str | None) -> tuple[str, str]:
    """(title, the rest) of a help file."""
    heading, _newline, body = source(slug, language).partition("\n")
    return heading.removeprefix("# ").strip(), body


def title(slug: str, language: str | None = None) -> str:
    return _split(slug, language)[0]


def summary(slug: str, language: str | None = None) -> str:
    """The first paragraph under the title, for the list on /hulp/."""
    first_paragraph = _split(slug, language)[1].strip().split("\n\n")[0]
    return " ".join(first_paragraph.split())


def url(slug: str, anchor: str = "") -> str:
    """The address of a help page, with an optional "#heading-id"."""
    return reverse("help:page", args=[slug]) + anchor


class _HelpLinks(markdown.treeprocessors.Treeprocessor):
    def __init__(self, md, link: Callable[[str, str], str]):
        super().__init__(md)
        self.link = link

    def run(self, root: Element) -> None:
        for a in root.iter("a"):
            match = _HELP_LINK.match(a.get("href", ""))
            if match:
                a.set("href", self.link(match["slug"], match["anchor"] or ""))


class _HelpLinksExtension(markdown.extensions.Extension):
    def __init__(self, link: Callable[[str, str], str]):
        super().__init__()
        self.link = link

    def extendMarkdown(self, md):  # noqa: N802 (the name Markdown calls)
        # After "inline" (priority 20), which makes the <a> elements.
        md.treeprocessors.register(_HelpLinks(md, self.link), "help_links", 5)


def render(
    slug: str, language: str | None = None, link: Callable[[str, str], str] = url
) -> HelpPage:
    """The help page as HTML. `link` turns a link to another help file into
    an address: the app's by default, the Huismus site's (core.site) there."""
    heading, body = _split(slug, language)
    # "toc" gives every heading an id ("een-map-koppelen"), so a link from
    # a screen lands on the right heading; the table of contents is unused.
    html = markdown.markdown(
        body, extensions=["fenced_code", "tables", "toc", _HelpLinksExtension(link)]
    )
    return HelpPage(slug, heading, html)
