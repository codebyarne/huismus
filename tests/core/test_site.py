# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site: huismus/core/site.py, built by manage.py build_site."""

import re
from html.parser import HTMLParser

import pytest
from django.core.management import CommandError, call_command
from django.utils import translation

from huismus.core import help, site


class _Page(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        # A list, not a set: an id twice is a link that jumps to the wrong one.
        self.id_list: list[str] = []
        self.h1s = 0
        self.sources: list[str] = []

    @property
    def ids(self) -> set[str]:
        return set(self.id_list)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if "id" in attrs:
            self.id_list.append(attrs["id"])
        if tag == "h1":
            self.h1s += 1
        for name in ("src", "srcset"):
            if attrs.get(name):
                self.sources += [part.split()[0] for part in attrs[name].split(",")]
        if tag == "link" and attrs.get("rel") in ("stylesheet", "preload", "icon"):
            self.sources.append(attrs["href"])
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
    addresses += [site.features_url(lang) for lang in help.LANGUAGES]
    addresses += [site.contribute_url(lang) for lang in help.LANGUAGES]
    addresses += [
        site.download_page_url(lang, n) for lang in help.LANGUAGES for n in site.PLATFORMS
    ]
    addresses += [site.help_url(lang) for lang in help.LANGUAGES]
    addresses += [site.help_url(lang, slug) for lang in help.LANGUAGES for slug in site.TOPICS]
    for address in addresses:
        page = _read(out, address)
        for link in page.links:
            if link.startswith("#"):
                assert link[1:] in page.ids, (address, link)
                continue
            if link == site.MAC_PRIVACY_SETTINGS:
                continue
            if link.startswith("mailto:"):
                # "Mail jezelf de link": no address, only this site's own address.
                assert link.startswith("mailto:?") and site.DOMAIN in link, (address, link)
                continue
            if not link.startswith("/"):
                # Another site, or a help file that core.help didn't turn into a page.
                # Meebouwen links to the developer docs in the repository on purpose.
                in_repository = link.startswith(f"{site.REPOSITORY}/blob/")
                assert link.startswith("https://"), (address, link)
                assert ".md" not in link or in_repository, (address, link)
                continue
            path, _hash, anchor = link.partition("#")
            # "/?#overstappen": on the home page a real navigation, so the menu closes.
            path = path.split("?")[0]
            assert (out / path.strip("/") / "index.html").exists(), (address, link)
            if anchor:
                assert anchor in _read(out, path).ids, (address, link)


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_download_buttons_always_get_the_newest_release(out, language):
    """A button goes to a download page, which starts the newest file: no
    version in the address, so it never points at an old release."""
    for address in (site.home_url(language), site.install_url(language)):
        links = _read(out, address).links
        for name in site.PLATFORMS:
            assert site.download_page_url(language, name) in links
    for name, platform in site.PLATFORMS.items():
        page = out / site.download_page_url(language, name).strip("/") / "index.html"
        html = page.read_text(encoding="utf-8")
        latest = f"{site.REPOSITORY}/releases/latest/download/{site.LATEST_ASSETS[platform]}"
        assert f'<meta http-equiv="refresh" content="0; url={latest}">' in html
        assert f'href="{latest}"' in html


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


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_help_index_has_the_same_groups_as_the_app_without_feedback(out, language):
    html = (out / site.help_url(language).strip("/") / "index.html").read_text(encoding="utf-8")
    with translation.override(language):
        titles = [str(group.title) for group in help.groups(site.TOPICS)]
    assert re.findall(r'<h2 id="help-group-\d+">([^<]+)</h2>', html) == titles
    assert site.help_url(language, help.FEEDBACK) not in html
    sections = html.split('<section class="help-group"')[1:]
    for section, group in zip(sections, help.groups(site.TOPICS), strict=True):
        for slug in group.topics:
            assert f'href="{site.help_url(language, slug)}"' in section


def test_without_a_counter_code_the_site_counts_nothing(out):
    for page in out.rglob("*.html"):
        assert "goatcounter" not in page.read_text(encoding="utf-8"), page


def test_with_a_counter_code_every_page_counts_its_own_address(tmp_path, monkeypatch):
    monkeypatch.setenv(site.COUNTER_VARIABLE, "huismus")
    call_command("build_site", str(tmp_path))
    page = (tmp_path / "en" / "download" / "mac" / "index.html").read_text(encoding="utf-8")
    assert 'src="https://huismus.goatcounter.com/count?p=%2Fen%2Fdownload%2Fmac%2F"' in page
    assert "GoatCounter, without cookies" in page


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


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_mac_steps_link_to_privacy_and_security(out, language):
    for address in (site.install_url(language), site.download_page_url(language, "mac")):
        assert site.MAC_PRIVACY_SETTINGS in _read(out, address).links, address


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_functies_shows_the_whole_list_and_the_home_page_what_comes_first(out, language):
    """One list (core/site_features.py): every feature and every month on
    Functies, in the language of the page; the home page points at it with
    what comes first and its month."""
    from django.utils.formats import date_format
    from django.utils.html import escape

    from huismus.core import site_features

    home = (out / site.home_url(language).strip("/") / "index.html").read_text()
    features = (out / site.features_url(language).strip("/") / "index.html").read_text()
    with translation.override(language):
        names = [str(f.name) for _group, items in site_features.NOW for f in items]
        names += [str(f.name) for _month, items in site_features.COMING for f in items]
        months = [date_format(month, "F Y") for month, _items in site_features.COMING]
        first_month, first_items = site_features.COMING[0]
        first = str(first_items[0].name)
        first_month = date_format(first_month, "F Y")
    for text in names + months:
        assert escape(text) in features, text
    assert escape(first[:1].lower() + first[1:]) in home
    assert first_month in home
    assert f'href="{site.features_url(language)}"' in home


def test_the_months_of_what_is_coming_follow_each_other():
    from huismus.core import site_features

    months = [month for month, _items in site_features.COMING]
    assert months == sorted(set(months)) and all(month.day == 1 for month in months)


def test_every_help_link_of_a_feature_is_a_help_page():
    from huismus.core import site_features

    for _group, items in site_features.NOW:
        for feature in items:
            assert not feature.help or feature.help in site.TOPICS, feature.name


def test_nothing_is_loaded_from_another_site(out):
    """Letters, pictures and styles come with the site: no CDN, no web fonts
    from elsewhere, no script."""
    for name in site._FONTS:
        assert (out / "fonts" / name).exists()
    for language in help.LANGUAGES:
        for address in (site.home_url(language), site.features_url(language)):
            html = (out / address.strip("/") / "index.html").read_text()
            sources = re.findall(r'(?:src|srcset)="([^"]+)"', html)
            sources += re.findall(
                r'<link rel="(?:stylesheet|preload|icon)[^>]*href="([^"]+)"', html
            )
            assert sources and all(source.startswith("/") for source in sources), sources
            assert "<script src" not in html


def test_every_photo_is_there_in_both_widths(out):
    """scripts/site-beelden.sh makes them (scripts/site_fotos.py); a photo
    with the app on the laptop shows it in the language of the page."""
    homes = " ".join(
        (out / site.home_url(lang).strip("/") / "index.html").read_text() for lang in help.LANGUAGES
    )
    for path in site.photo_files():
        assert path.exists(), f"{path.name}: draai ./scripts/site-beelden.sh"
        assert (out / "beelden" / "fotos" / path.name).exists()
        assert f"/beelden/fotos/{path.name}" in homes
    for language in help.LANGUAGES:
        home = (out / site.home_url(language).strip("/") / "index.html").read_text()
        for name in site.PHOTOS_WITH_SCREEN:
            assert f"/beelden/fotos/{name}.{language}." in home


def test_every_picture_on_a_page_has_a_description(out):
    for language in help.LANGUAGES:
        html = (out / site.home_url(language).strip("/") / "index.html").read_text()
        images = re.findall(r"<img [^>]*>", html)
        assert len(images) >= 10
        for image in images:
            assert re.search(r'alt="[^"]{20,}"', image), image


def test_a_search_engine_finds_every_page_but_the_downloads(out):
    sitemap = (out / "sitemap.xml").read_text()
    assert f"https://{site.DOMAIN}/functies/" in sitemap and "/download/" not in sitemap
    assert "sitemap.xml" in (out / "robots.txt").read_text()
    download = (out / "download" / "mac" / "index.html").read_text()
    assert '<meta name="robots" content="noindex">' in download
    home = (out / "index.html").read_text()
    assert f'<link rel="canonical" href="https://{site.DOMAIN}/">' in home
    assert f'hreflang="en" href="https://{site.DOMAIN}/en/"' in home


def _every_address(out):
    """Every page the build wrote, by its address."""
    addresses = []
    for path in out.rglob("index.html"):
        folder = path.parent.relative_to(out).as_posix()
        addresses.append("/" if folder == "." else f"/{folder}/")
    return sorted(addresses)


def test_no_page_has_an_id_twice_or_more_than_one_main_heading(out):
    """The icons (icons.svg) are on every page with ids like download and
    menu: a heading or a section with the same id is never jumped to."""
    for address in _every_address(out):
        page = _read(out, address)
        twice = {i for i in page.id_list if page.id_list.count(i) > 1}
        assert not twice, (address, twice)
        assert page.h1s == 1, address


def test_no_page_loads_anything_from_another_site(out):
    for address in _every_address(out):
        page = _read(out, address)
        outside = [s for s in page.sources if not s.startswith("/")]
        assert outside == [], (address, outside)


def test_a_description_fits_in_a_search_result(out):
    for address in _every_address(out):
        html = (out / address.strip("/") / "index.html").read_text()
        description = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
        assert 50 <= len(description) <= 160, (address, len(description))


def test_with_less_motion_an_animation_stands_still(out):
    for language in help.LANGUAGES:
        html = (out / site.home_url(language).strip("/") / "index.html").read_text()
        for name in ("factuur-maken", "importeren"):
            still = f"/beelden/{name}.{language}.light.still.webp"
            assert still in html
            assert (out / still.lstrip("/")).exists()


def test_a_month_in_the_past_stops_the_build(tmp_path, monkeypatch):
    from datetime import date

    from huismus.core import site_features

    monkeypatch.setattr(site_features, "COMING", ((date(2020, 1, 1), ()),))
    with pytest.raises(CommandError, match="2020-01"):
        call_command("build_site", str(tmp_path / "site"))


def test_every_picture_that_comes_with_the_site_is_on_a_page(out):
    """No megabytes nobody sees."""
    pages = " ".join(path.read_text() for path in out.rglob("index.html"))
    for path in (out / "beelden").rglob("*.webp"):
        assert f"/beelden/{path.relative_to(out / 'beelden')}" in pages, path.name
