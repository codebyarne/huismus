# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Uitleg on the site: docs/uitleg/, huismus/core/guides.py (issue #308).

Without a source there is no page: every link to another site is a source
page from docs/belastingregels.md or docs/invoice-requirements.md.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command

from huismus.core import guides, help, site

ROOT = Path(settings.BASE_DIR)
SOURCE_FILES = ("belastingregels.md", "invoice-requirements.md")
# The line under the sources: the day they were checked, and where to look.
CHECKED = {
    "nl": r"Nagekeken op \d{1,2} [a-z]+ 20\d\d\. Voor je eigen geval kijk je op de bronpagina\.",
    "en": r"Checked on \d{1,2} [A-Z][a-z]+ 20\d\d\. For your own case, see the source page\.",
}
PAGES = [(slug, language) for slug in guides.GUIDES for language in help.LANGUAGES]


def _source_pages() -> set[str]:
    text = "".join((ROOT / "docs" / name).read_text(encoding="utf-8") for name in SOURCE_FILES)
    return set(re.findall(r"\]\((https://[^)\s]+)\)", text))


def _render(slug, language):
    return guides.render(
        slug,
        language,
        help_link=lambda s, a: site.help_url(language, s, a),
        link=lambda s: site.guides_url(language, s),
        examples_link=site.examples_url(language),
    )


def _links(html: str) -> list[str]:
    return re.findall(r'href="([^"]+)"', html)


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    call_command("build_site", str(out))
    return out


def test_every_file_in_docs_uitleg_is_a_page_in_both_languages():
    files = {path.name for path in guides.GUIDES_DIR.glob("*.md")}
    assert files == {f"{slug}.{language}.md" for slug, language in PAGES}


@pytest.mark.parametrize("slug,language", PAGES)
def test_a_page_has_a_title_and_a_plain_summary(slug, language):
    assert guides.source(slug, language).startswith("# ") and guides.title(slug, language)
    summary = guides.summary(slug, language)
    assert summary and not re.search(r"[#*`\[\]<>|]|^- ", summary), summary


@pytest.mark.parametrize("slug,language", PAGES)
def test_every_link_to_another_site_is_a_source_page(slug, language):
    """Also in the explanation itself: a page never sends you to a site that
    isn't in the source files."""
    page = _render(slug, language)
    known = _source_pages()
    for href in _links(page.html + page.in_huismus_html + page.sources_html):
        if href.startswith("http"):
            assert href in known, href


@pytest.mark.parametrize("slug,language", PAGES)
def test_a_page_names_its_sources_and_the_day_they_were_checked(slug, language):
    sources = _render(slug, language).sources_html
    assert [href for href in _links(sources) if href.startswith("https://")]
    assert re.search(CHECKED[language], re.sub(r"\s+", " ", sources)), sources
    if language == "en":
        # The source pages are Dutch; an English reader is told so.
        assert sources.count("in Dutch") == sources.count("<li>")


@pytest.mark.parametrize("slug,language", PAGES)
def test_a_page_ends_with_how_to_do_it_in_huismus_and_a_help_page(slug, language):
    in_huismus = _render(slug, language).in_huismus_html
    help_pages = {site.help_url(language, topic): topic for topic in site.TOPICS}
    targets = [href.partition("#") for href in _links(in_huismus)]
    assert targets and all(target in help_pages for target, _hash, _anchor in targets)
    for target, _hash, anchor in targets:
        if anchor:
            assert f'id="{anchor}"' in help.render(help_pages[target], language).html, anchor


def test_a_file_without_its_sources_is_refused(monkeypatch, tmp_path):
    (tmp_path / "kor.nl.md").write_text(
        "# Titel\n\nSamenvatting.\n\nUitleg.\n\n## Zo doe je dit in Huismus\n\nZo.\n"
    )
    monkeypatch.setattr(guides, "GUIDES_DIR", tmp_path)
    with pytest.raises(ValueError, match="## Bronnen"):
        guides.parts("kor", "nl")


def test_both_languages_have_the_same_sources():
    for slug in guides.GUIDES:
        nl, en = (
            sorted(h for h in _links(_render(slug, language).sources_html))
            for language in help.LANGUAGES
        )
        assert nl == en, slug


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_site_has_every_page_in_the_menu_the_list_the_sitemap_and_llms_txt(out, language):
    index = site.guides_url(language)
    home = (out / site.home_url(language).strip("/") / "index.html").read_text(encoding="utf-8")
    # The menu and the foot.
    assert home.count(f'href="{index}"') == 2
    listed = _links((out / index.strip("/") / "index.html").read_text(encoding="utf-8"))
    sitemap = (out / "sitemap.xml").read_text(encoding="utf-8")
    llms = (out / "llms.txt").read_text(encoding="utf-8")
    assert f"https://{site.DOMAIN}{index}</loc>" in sitemap
    for slug in guides.GUIDES:
        address = site.guides_url(language, slug)
        html = (out / address.strip("/") / "index.html").read_text(encoding="utf-8")
        assert f"<h1>{guides.title(slug, language)}</h1>" in html.replace("&#x27;", "'")
        assert 'id="in-huismus"' in html and 'id="bronnen"' in html
        assert address in listed
        assert f"https://{site.DOMAIN}{address}</loc>" in sitemap
        assert f"(https://{site.DOMAIN}{address}): " in llms


def test_a_page_links_to_itself_in_the_other_language(out):
    html = (out / "uitleg" / "kor" / "index.html").read_text(encoding="utf-8")
    assert f'hreflang="en" href="https://{site.DOMAIN}/en/guides/kor/"' in html
