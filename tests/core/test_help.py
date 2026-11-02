# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hulp: docs/hulp/ shown in the app.

See huismus/core/help.py and huismus-intern/besluiten.md, 2026-10-31.
"""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from huismus.core import help

pytestmark = pytest.mark.django_db

ROOT = Path(settings.BASE_DIR)


@pytest.mark.parametrize("language", help.LANGUAGES)
@pytest.mark.parametrize("slug", help.TOPICS)
def test_every_topic_exists_in_both_languages_with_a_title(slug, language):
    text = help.source(slug, language)
    assert text.startswith("# ") and help.title(slug, language)


@pytest.mark.parametrize("language", help.LANGUAGES)
@pytest.mark.parametrize("slug", help.TOPICS)
def test_every_topic_starts_with_a_plain_paragraph_for_the_list(slug, language):
    summary = help.summary(slug, language)
    assert summary and not re.search(r"[#*`\[\]<>|]|^- ", summary), summary


def test_every_file_in_docs_hulp_is_a_topic():
    """A file nobody can reach in the app is a forgotten topic."""
    files = {path.name for path in help.HELP_DIR.glob("*.md")}
    expected = {f"{slug}.{language}.md" for slug in help.TOPICS for language in help.LANGUAGES}
    assert files == expected


@pytest.mark.parametrize("language", help.LANGUAGES)
@pytest.mark.parametrize("slug", help.TOPICS)
def test_help_links_only_to_help_pages_and_headings_that_exist(slug, language):
    """No SPEC.md, source code or GitHub: a user can't open those
    (huismus-intern/besluiten.md 2026-10-31), and an anchor must land on a heading."""
    html = help.render(slug, language).html
    for href in re.findall(r'href="([^"]+)"', html):
        if href.startswith("https://") and "github.com" not in href:
            continue
        target, _hash, anchor = href.partition("#")
        assert target in ("", *(help.url(other) for other in help.TOPICS)), href
        if anchor:
            other = target.removeprefix("/hulp/").strip("/") or slug
            assert f'id="{anchor}"' in help.render(other, language).html, href


def test_a_link_to_another_help_file_becomes_its_page():
    html = help.render("desktop-app", "nl").html
    assert 'href="/hulp/back-ups/"' in html
    assert ".md" not in html


def test_the_index_lists_every_topic_in_the_users_language(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("arne", password="x" * 12))

    page = client.get(reverse("help:index")).content.decode()
    for slug in help.TOPICS:
        assert reverse("help:page", args=[slug]) in page
    assert help.summary("back-ups", "nl") in page

    client.cookies["django_language"] = "en"
    page = client.get(reverse("help:index")).content.decode()
    assert "Backups" in page and "Uitleg bij" not in page


def test_a_page_shows_the_markdown_with_ids_on_its_headings(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("arne", password="x" * 12))

    page = client.get(reverse("help:page", args=["back-ups"])).content.decode()
    assert '<h2 id="een-map-koppelen">Een map koppelen</h2>' in page
    assert "<pre><code>docker run" in page

    client.cookies["django_language"] = "en"
    page = client.get(reverse("help:page", args=["back-ups"])).content.decode()
    assert '<h2 id="linking-a-folder">Linking a folder</h2>' in page


def test_an_unknown_topic_is_a_404(client, django_user_model):
    client.force_login(django_user_model.objects.create_user("arne", password="x" * 12))
    assert client.get("/hulp/bestaat-niet/").status_code == 404


@pytest.mark.parametrize("url", ["/hulp/", "/hulp/back-ups/"])
def test_help_needs_a_login(client, url):
    response = client.get(url)
    assert response.status_code == 302 and "/login/" in response["Location"]


def test_no_screen_links_to_github_for_an_explanation():
    """The explanation belongs to the version someone runs, and the repo is
    private (huismus-intern/besluiten.md 2026-10-31). Release pages stay: core.updates."""
    sources = [*ROOT.glob("huismus/templates/**/*.html")]
    sources += ROOT.glob("huismus/**/*.py")
    offenders = [
        str(path.relative_to(ROOT))
        for path in sources
        if re.search(r"github\.com/[^\"' ]+/(blob|tree)/", path.read_text(encoding="utf-8"))
    ]
    assert offenders == []
