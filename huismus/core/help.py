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
from django.utils.translation import gettext_lazy as _

HELP_DIR = settings.BASE_DIR / "docs" / "hulp"
LANGUAGES = ("nl", "en")
# "Feedback geven" also shows the card Hoe gebruik je Huismus? (core.feedback_views).
FEEDBACK = "feedback"
# Opening it counts as having seen the overview's "Huismus is bijgewerkt"
# (core.help_views.page).
WHATS_NEW = "nieuw"


@dataclass(frozen=True)
class Group:
    """A heading on /hulp/ with its topics, in the app and on the site
    (issue #130; huismus-intern/besluiten.md, 2026-11-07)."""

    title: str
    topics: tuple[str, ...]


# The order of the list on /hulp/. A group without topics (on the site: with
# only Feedback geven) isn't shown, so a group can wait here for its pages.
GROUPS = (
    Group(
        _("Beginnen"),
        # What each release brings; written on release day (CLAUDE.md, Releases).
        ("beginnen", WHATS_NEW, FEEDBACK),
    ),
    Group(_("Overstappen"), ("moneybird",)),
    Group(
        _("Het hele jaar"),
        (
            "facturen",
            "offertes",
            "mailen",
            "uitgaven",
            "bonnetjes",
            "kor-en-btw",
            "back-ups",
            "ai-assistenten",
        ),
    ),
    Group(_("Voor je boekhouder"), ("exporteren",)),
    Group(_("Installeren en bijwerken"), ("desktop-app", "docker", "vps", "telefoon")),
    Group(_("Wat Huismus (nog) niet doet"), ()),
)
TOPICS = tuple(slug for group in GROUPS for slug in group.topics)


def groups(shown: tuple[str, ...] = TOPICS) -> list[Group]:
    """The groups with only the `shown` topics; a group left without any is
    dropped. The app shows every topic; the site passes core.site.TOPICS,
    which leaves out Feedback geven."""
    kept = (Group(g.title, tuple(s for s in g.topics if s in shown)) for g in GROUPS)
    return [group for group in kept if group.topics]


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
