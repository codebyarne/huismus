# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site: huismus/core/site.py, built by manage.py build_site."""

import json
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
    addresses += [site.why_url(lang) for lang in help.LANGUAGES]
    addresses += [site.contribute_url(lang) for lang in help.LANGUAGES]
    addresses += [site.made_url(lang) for lang in help.LANGUAGES]
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
            if not link.startswith("/"):
                # Another site, or a help file that core.help didn't turn into a page.
                # Meebouwen links to the developer docs in the repository on purpose.
                in_repository = link.startswith(f"{site.REPOSITORY}/blob/")
                assert link.startswith("https://"), (address, link)
                assert ".md" not in link or in_repository, (address, link)
                continue
            path, _hash, anchor = link.partition("#")
            # "/?naar=downloaden#downloaden": a real navigation, so the menu closes.
            path = path.split("?")[0]
            if path.startswith("/beelden/"):
                # "Download de film", for a browser that can't play it: the file itself.
                assert (out / path.strip("/")).is_file(), (address, link)
                continue
            assert (out / path.strip("/") / "index.html").exists(), (address, link)
            if anchor:
                assert anchor in _read(out, path).ids, (address, link)


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_download_buttons_always_get_the_newest_release(out, language):
    """A button goes to a download page, which starts the newest file: no
    version in the address, so it never points at an old release."""
    for address in (site.home_url(language), site.install_url(language)):
        links = _read(out, address).links
        assert site.download_page_url(language, "mac") in links
        assert site.STORE_URL in links
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
    for path in site.media_files(site.SITE_SCHEMES):
        assert (out / "beelden" / path.name).exists()
    for language in help.LANGUAGES:
        html = (out / site.home_url(language).strip("/") / "index.html").read_text()
        assert f"/beelden/factuur-maken.{language}.light.webp" in html
        assert f"https://{site.DOMAIN}/delen.{language}.png" in html
        assert (out / f"delen.{language}.png").exists()


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_home_page_shows_the_app_without_the_kor_too(out, language):
    """The site says "met of zonder KOR" (issue #130): who charges VAT sees
    the VAT return and a receipt with its VAT, and on a narrow screen each as
    a phone shows it, so the amounts are not cut off."""
    html = (out / site.home_url(language).strip("/") / "index.html").read_text()
    for name in site.PHONE_DETAILS:
        assert f'src="/beelden/{name}.{language}.light.webp"' in html
        assert f'srcset="/beelden/{name}.{language}.light.phone.webp"' in html
    # Every picture reserves its room: a size the template can't find is empty.
    assert 'width=""' not in html
    assert 'height=""' not in html


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_install_and_contribute_have_a_page_in_both_languages(out, language):
    for address in (site.install_url(language), site.contribute_url(language)):
        assert (out / address.strip("/") / "index.html").exists()


def test_the_english_pages_are_in_english(out):
    html = (out / "en" / "index.html").read_text(encoding="utf-8")
    assert '<html lang="en"' in html and "Download for Mac" in html
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
def test_functies_and_the_home_page_show_the_whole_list_with_a_check_or_later(out, language):
    """One list (core/site_features.py), to show how complete Huismus is:
    every feature on both pages, in the language of the page, and as many
    "Binnenkort verwacht" labels as features that come later. No months (the owner,
    2026-11-18)."""
    from django.utils.html import escape

    from huismus.core import site_features

    home = (out / site.home_url(language).strip("/") / "index.html").read_text()
    features = (out / site.features_url(language).strip("/") / "index.html").read_text()
    with translation.override(language):
        names = [str(f.name) for _group, items in site_features.FEATURES for f in items]
        later = str(translation.gettext("Binnenkort verwacht"))
    _now, coming = site_features.counts()
    for page in (home, features):
        for name in names:
            assert escape(name) in page, name
        assert page.count(f'<span class="later">{later}</span>') >= coming
    assert "Verwacht in" not in features and "Expected in" not in features


def test_every_help_link_of_a_feature_is_a_help_page():
    from huismus.core import site_features

    for _group, items in site_features.FEATURES:
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


def test_the_top_of_the_home_page_is_a_person(out):
    """The owner, 2026-11-25 (docs/design/ronde-9/kop.md): the furniture
    maker in a card at the top, with the words and the download buttons on it,
    loaded first, and one made-up card from the app that a screen reader skips.
    The line about trying first comes right under the card. She is in the card
    only: Voor wie shows the four others."""
    for language in help.LANGUAGES:
        home = (out / site.home_url(language).strip("/") / "index.html").read_text()
        card = home[home.index('<div class="hero-card">') : home.index('class="hero-chip"')]
        assert re.search(
            rf'<img [^>]*src="/beelden/fotos/werkplaats\.{language}\.1600\.webp"'
            r'[^>]*fetchpriority="high"',
            card,
        )
        assert "<h1>" in card and 'class="downloads"' in card
        assert 'loading="lazy"' not in card
        assert re.search(r'<p class="hero-chip" aria-hidden="true">', home)
        after_card = home[home.index('class="hero-chip"') :]
        assert re.match(
            r'class="hero-chip".*?</p>\s*</div>\s*<p class="downloads-note small">',
            after_card,
            re.S,
        )
        people = home[home.index('<div class="people">') :]
        people = people[: people.index('<div class="kor-lines">')]
        assert people.count('<figure class="person">') == 4
        assert "werkplaats" not in people


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


def test_every_picture_that_comes_with_the_site_is_on_a_page(out):
    """No megabytes nobody sees."""
    pages = " ".join(path.read_text() for path in out.rglob("index.html"))
    for path in (out / "beelden").rglob("*.webp"):
        assert f"/beelden/{path.relative_to(out / 'beelden')}" in pages, path.name


def test_on_the_home_page_the_jump_in_the_menu_has_its_own_address(out):
    """A popover stays open on a jump within the same page, and the site has no
    JS: on the home page the menu's link to a block (Download) is a navigation
    of its own, so choosing it closes the menu. Overstappen is a page since #122."""
    page = _read(out, "/")
    assert [link for link in page.links if link.startswith("/?")] == [
        "/?naar=downloaden#downloaden"
    ]


def test_a_help_page_is_described_in_whole_words():
    assert site._short("Kort.") == "Kort."
    text = "Eerste zin is kort. " + "Tweede zin is veel te lang " * 10 + "."
    assert site._short(text) == "Eerste zin is kort."
    assert site._short("woord " * 60).endswith("woord…")
    assert len(site._short("woord " * 60)) <= 160


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_why_huismus_exists_has_a_page_the_home_page_and_every_foot_link_to(out, language):
    """Who makes Huismus and why (the owner, 2026-11-18)."""
    why = site.why_url(language)
    page = (out / why.strip("/") / "index.html").read_text()
    assert "https://www.arnekrijnsen.com" in page
    home = _read(out, site.home_url(language))
    assert why in home.links
    assert why in _read(out, site.help_url(language)).links


def test_the_films_are_on_the_dutch_home_page_and_the_receipts_help(out):
    """A film and its still come with the site, and nothing of it loads or
    plays until the visitor presses play."""
    for path in site.film_files():
        assert path.exists(), f"{path.name}: zie docs/README.md, Films"
        assert (out / "beelden" / path.name).exists()
    home = (out / "index.html").read_text()
    receipts = (out / site.help_url("nl", "bonnetjes").strip("/") / "index.html").read_text()
    for page, name in ((home, "rondleiding"), (receipts, "bonnetjes")):
        (video,) = re.findall(r"<video [^>]*>", page)
        assert f'poster="/beelden/film-{name}.nl.webp"' in video
        assert "controls" in video and 'preload="none"' in video
        assert "autoplay" not in video
        assert re.search(r'aria-label="[^"]{20,}"', video)
        assert f'<source src="/beelden/film-{name}.nl.mp4" type="video/mp4">' in page
    # Any other help page has no film.
    assert (
        "<video"
        not in (out / site.help_url("nl", "facturen").strip("/") / "index.html").read_text()
    )


def test_the_english_home_page_has_the_english_tour_and_no_other_film(out):
    """The tour exists in English too (2026-11-25); the receipts film is
    Dutch only, so no other English page shows a film."""
    home = (out / "en" / "index.html").read_text()
    (video,) = re.findall(r"<video [^>]*>", home)
    assert 'poster="/beelden/film-rondleiding.en.webp"' in video
    assert '<source src="/beelden/film-rondleiding.en.mp4" type="video/mp4">' in home
    assert 'srclang="en" label="English" src="/beelden/film-rondleiding.en.vtt"' in home
    assert ".nl." not in home[home.index("<video") : home.index("</video>")]
    for page in (out / "en").rglob("index.html"):
        if page != out / "en" / "index.html":
            assert "<video" not in page.read_text(), page


def test_a_film_is_small_enough_for_a_phone_on_the_road():
    """The sharp film, which only a wide screen takes, may be larger."""
    for path in site.film_files():
        if path.name.endswith(".hd.mp4"):
            limit = 8_000_000
        else:
            limit = 3_000_000 if path.suffix == ".mp4" else 100_000
        assert path.stat().st_size < limit, path.name


def test_a_wide_screen_gets_the_sharp_film_and_a_phone_the_small_one(out):
    """The browser takes the first source that fits: the sharp one only from
    a wide window, the small one otherwise. No script chooses."""
    home = (out / "index.html").read_text()
    for name in site.FILMS_SHARP:
        assert (out / "beelden" / f"film-{name}.nl.hd.mp4").exists()
        sharp = (
            f'<source src="/beelden/film-{name}.nl.hd.mp4" type="video/mp4" '
            f'media="(min-width: {site.FILM_SHARP_FROM}px)">'
        )
        small = f'<source src="/beelden/film-{name}.nl.mp4" type="video/mp4">'
        assert sharp in home and small in home
        assert home.index(sharp) < home.index(small)
    receipts = (out / site.help_url("nl", "bonnetjes").strip("/") / "index.html").read_text()
    assert ".hd.mp4" not in receipts


def test_a_film_on_the_site_has_sound_only_once_the_owner_has_heard_it():
    """Owner, 2026-11-19: ./scripts/promo-film.sh site leaves the sound track
    out; an mp4 with one has an AAC track ("mp4a"). The tour has a voice the
    owner has heard (site.FILMS_WITH_VOICE)."""
    for path in site.film_files():
        if path.suffix == ".mp4":
            voiced = any(f"film-{name}." in path.name for name in site.FILMS_WITH_VOICE)
            assert (b"mp4a" in path.read_bytes()) == voiced, path.name


def test_a_film_with_a_voice_has_its_words_as_captions(out):
    """Who can't hear the voice, or has the sound off, reads along: a text
    track in Dutch, shown from the start. A film without a voice has none."""
    home = (out / "index.html").read_text()
    receipts = (out / site.help_url("nl", "bonnetjes").strip("/") / "index.html").read_text()
    for name in site.FILMS_WITH_VOICE:
        captions = (out / "beelden" / f"film-{name}.nl.vtt").read_text(encoding="utf-8")
        assert captions.startswith("WEBVTT\n")
        cues = re.findall(r"^(\d\d:\d\d\.\d{3}) --> (\d\d:\d\d\.\d{3})$", captions, re.M)
        assert len(cues) > 10
        # In order, and never two at once.
        times = [time for cue in cues for time in cue]
        assert times == sorted(times)
        assert (
            f'<track kind="captions" srclang="nl" label="Nederlands" '
            f'src="/beelden/film-{name}.nl.vtt" default>'
        ) in home
    assert "<track" not in receipts


def test_the_site_is_always_light(out):
    """Whatever the visitor's system is (the owner, 2026-11-19): no page and no
    picture follows a dark system."""
    for address in _every_address(out):
        html = (out / address.strip("/") / "index.html").read_text()
        assert 'data-theme="light"' in html, address
        assert "prefers-color-scheme: dark" not in html, address
        assert ".dark." not in html, address


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_kor_is_written_out_before_it_is_called_kor(out, language):
    """Not everyone knows the KOR (the owner, 2026-11-19): on every page of the
    site, the help included, the first KOR a visitor meets is the whole name,
    with KOR after it."""
    whole = {"nl": "kleineondernemersregeling (KOR)", "en": "small business scheme (KOR)"}
    for address in _every_address(out):
        if address.startswith("/en/") != (language == "en"):
            continue
        html = (out / address.strip("/") / "index.html").read_text()
        body = html[html.index("<body") :]
        if "KOR" in body:
            first = body.index("KOR")
            assert body[: first + 4].lower().endswith(whole[language].lower()), (
                address,
                body[first - 80 : first + 10],
            )


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_overstappen_in_the_menu_is_a_page_and_what_to_do_next_links_to_it(out, language):
    """Issue #122: someone coming from another package finds the page with the
    steps from the menu on every page, from the block on the home page, and
    from what to do after installing."""
    switching = site.switching_url(language)
    assert switching == site.help_url(language, help.SWITCHING)
    for address in (
        site.home_url(language),
        site.help_url(language),
        site.install_url(language),
        *(site.download_page_url(language, name) for name in site.PLATFORMS),
    ):
        assert _read(out, address).links.count(switching) >= 1, address
    # The menu, and "Zo stap je over" in the block Overstappen.
    assert _read(out, site.home_url(language)).links.count(switching) == 2
    # Under "Daarna": the menu's link and one in the text.
    assert _read(out, site.install_url(language)).links.count(switching) == 2
    html = (out / switching.strip("/") / "index.html").read_text(encoding="utf-8")
    assert f'<a href="{switching}" aria-current="page">' in html


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_overstappen_links_to_every_package_and_aan_de_slag_links_to_it(out, language):
    switching = site.switching_url(language)
    links = _read(out, switching).links
    for slug in ("moneybird", "importeren", *help.PACKAGES):
        assert site.help_url(language, slug) in links, slug
    # Aan de slag: the menu and the text.
    assert _read(out, site.help_url(language, "beginnen")).links.count(switching) == 2


def test_an_ai_assistant_finds_what_huismus_is_and_every_help_page(out):
    """llms.txt (issue #295): one file with what Huismus is and a line per page,
    and every address in it is a page of the site."""
    text = (out / "llms.txt").read_text(encoding="utf-8")
    assert text.startswith("# Huismus\n\n> ")
    addresses = re.findall(rf"https://{re.escape(site.DOMAIN)}(/[^\s)]*)", text)
    for language in help.LANGUAGES:
        for slug in site.TOPICS:
            assert site.help_url(language, slug) in addresses, slug
    for address in addresses:
        assert (out / address.strip("/") / "index.html").exists(), address


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_home_page_tells_a_search_engine_what_the_app_is(out, language):
    html = (out / site.home_url(language).strip("/") / "index.html").read_text(encoding="utf-8")
    data = json.loads(
        re.search(r'<script type="application/ld\+json">(.*?)</script>', html).group(1)
    )
    assert data["@type"] == "SoftwareApplication" and data["isAccessibleForFree"] is True
    assert data["description"] and data["sameAs"] == site.REPOSITORY
    assert data["downloadUrl"].endswith("#downloaden")


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_windows_goes_to_the_store_and_the_installer_stays_reachable(out, language):
    """The Windows button leads to the Microsoft Store; Installeren keeps the
    unsigned installer behind a details element, and the installer's own
    page points back to the Store (huismus-intern/besluiten.md, 2026-11-25)."""
    install = (out / site.install_url(language).strip("/") / "index.html").read_text(
        encoding="utf-8"
    )
    windows = install.split('id="windows"', 1)[1].split("</section>", 1)[0]
    assert site.STORE_URL in windows
    details = windows.split("<details", 1)[1].split("</details>", 1)[0]
    assert site.download_page_url(language, "windows") in details
    assert "how-to" in details
    page = out / site.download_page_url(language, "windows").strip("/") / "index.html"
    html = page.read_text(encoding="utf-8")
    assert site.STORE_URL in html and "<details" not in html
