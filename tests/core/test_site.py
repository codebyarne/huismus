# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site: huismus/core/site.py, built by manage.py build_site."""

import re
from html.parser import HTMLParser

import pytest
from django.core.management import CommandError, call_command

from huismus.core import help, site


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.ids: set[str] = set()

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.ids.add(attrs["id"])
        if tag == "a" and "href" in attrs:
            self.links.append(attrs["href"])


def _read(out, address):
    page = _Page()
    page.feed((out / address.strip("/") / "index.html").read_text(encoding="utf-8"))
    return page


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    call_command("build_site", str(out))
    return out


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_every_topic_but_feedback_has_a_page_in_both_languages(out, language):
    for slug in help.TOPICS:
        path = out / site.help_url(language, slug).strip("/") / "index.html"
        assert path.exists() == (slug != help.FEEDBACK), slug
    assert (out / site.help_url(language).strip("/") / "index.html").exists()
    assert (out / site.home_url(language).strip("/") / "index.html").exists()


def test_every_link_inside_the_site_lands_on_a_page_and_heading(out):
    """Also the links between help files (`back-ups.nl.md#…` in docs/hulp/)."""
    addresses = [site.home_url(lang) for lang in help.LANGUAGES]
    addresses += [site.install_url(lang) for lang in help.LANGUAGES]
    addresses += [site.contribute_url(lang) for lang in help.LANGUAGES]
    addresses += [site.help_url(lang) for lang in help.LANGUAGES]
    addresses += [site.help_url(lang, slug) for lang in help.LANGUAGES for slug in site.TOPICS]
    for address in addresses:
        page = _read(out, address)
        for link in page.links:
            if link.startswith("#"):
                assert link[1:] in page.ids, (address, link)
                continue
            if not link.startswith("/"):
                # Another site, or a help file that core.help didn't turn into a page.
                # Meebouwen links to the developer docs in the repository on purpose.
                in_repository = link.startswith(f"{site.REPOSITORY}/blob/")
                assert link.startswith("https://"), (address, link)
                assert ".md" not in link or in_repository, (address, link)
                continue
            path, _hash, anchor = link.partition("#")
            assert (out / path.strip("/") / "index.html").exists(), (address, link)
            if anchor:
                assert anchor in _read(out, path).ids, (address, link)


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_download_buttons_always_get_the_newest_release(out, language):
    """No version in the address: a button never points at an old release."""
    for address in (site.home_url(language), site.install_url(language)):
        links = _read(out, address).links
        for name in site.LATEST_ASSETS.values():
            assert f"{site.REPOSITORY}/releases/latest/download/{name}" in links


def test_every_release_carries_the_files_the_buttons_point_at():
    release = (site.MEDIA_DIR.parent.parent / ".github" / "workflows" / "release.yml").read_text()
    for name in site.LATEST_ASSETS.values():
        assert f"dist/{name}" in release


def test_every_picture_of_the_app_is_there_in_both_languages_and_themes(out):
    """scripts/site-beelden.sh makes them; a missing one is a broken image."""
    for path in site.media_files():
        assert path.exists(), f"{path.name}: draai ./scripts/site-beelden.sh"
        assert (out / "beelden" / path.name).exists()
    for language in help.LANGUAGES:
        html = (out / site.home_url(language).strip("/") / "index.html").read_text()
        assert f"/beelden/factuur-maken.{language}.light.webp" in html
        assert f"https://{site.DOMAIN}/delen.{language}.png" in html
        assert (out / f"delen.{language}.png").exists()


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_install_and_contribute_have_a_page_in_both_languages(out, language):
    for address in (site.install_url(language), site.contribute_url(language)):
        assert (out / address.strip("/") / "index.html").exists()


def test_the_english_pages_are_in_english(out):
    html = (out / "en" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en">' in html and "Download for Mac" in html
    assert "Download voor Mac" not in html
    help_page = (out / "en" / "help" / "back-ups" / "index.html").read_text(encoding="utf-8")
    assert "<h1>Backups</h1>" in help_page


def test_it_looks_like_the_app_and_has_its_own_domain(out):
    assert (out / "huismus.css").read_bytes() == (site._STATIC / "huismus.css").read_bytes()
    assert (out / "CNAME").read_text().strip() == site.DOMAIN
    assert (out / ".nojekyll").exists() and (out / "404.html").exists()


def test_building_again_leaves_nothing_old_behind(tmp_path):
    call_command("build_site", str(tmp_path))
    (tmp_path / "oud.html").write_text("weg")
    call_command("build_site", str(tmp_path))
    assert not (tmp_path / "oud.html").exists()
    assert not re.search(r"\{[{%]", (tmp_path / "index.html").read_text(encoding="utf-8"))


def test_a_folder_that_is_not_a_site_is_never_emptied(tmp_path):
    (tmp_path / "pyproject.toml").write_text("van iemand anders")
    with pytest.raises(CommandError):
        call_command("build_site", str(tmp_path))
    assert (tmp_path / "pyproject.toml").exists()
