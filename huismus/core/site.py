# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site (mijnhuismus.nl): static pages on GitHub Pages.

Built at every release from the files of that release (huismus-intern/besluiten.md,
2026-10-30), so the site always belongs to the version you download: a tour of
the app with the download buttons, how to open it the first time, the help from
docs/hulp/ and a page for developers, in Dutch and English. It is written for
people who are not technical: the desktop app comes first, running it yourself
on a server is the second route. It uses the app's own stylesheet and
components, so it looks like Huismus. `manage.py build_site <map>` writes it;
.github/workflows/pages.yml publishes it.

The pictures of the app come from docs/site/, made by scripts/site-beelden.sh
on a made-up administration (core/site_data.py).

Addresses: Dutch at the root, English under /en/.

    /                   /en/
    /installeren/       /en/install/
    /functies/          /en/features/
    /hulp/              /en/help/
    /hulp/<onderwerp>/  /en/help/<topic>/
    /meebouwen/         /en/contribute/
    /download/<mac|windows>/  /en/download/<mac|windows>/

Visits are counted only when COUNTER_VARIABLE holds a GoatCounter code: a
1×1 image per page, no cookies and no JS.
"""

import os
import shutil
from datetime import date
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation
from PIL import Image

from . import help, site_features, updates

DOMAIN = "mijnhuismus.nl"
REPOSITORY = "https://github.com/codebyarne/huismus"
# "Feedback geven" asks you to fill in the form below it, which only the app has.
TOPICS = tuple(slug for slug in help.TOPICS if slug != help.FEEDBACK)

# The file the download buttons point at, the same name in every release
# (release.yml uploads a copy under it), so "latest" always has it.
LATEST_ASSETS = {"darwin": "Huismus-macos.dmg", "win32": "Huismus-windows.exe"}
# The platforms of the download pages, by their address.
PLATFORMS = {"mac": "darwin", "windows": "win32"}
# Opens System Settings › Privacy & Security on a Mac, where "Toch openen" is
# the first time you open the unsigned app. Elsewhere the link does nothing.
MAC_PRIVACY_SETTINGS = "x-apple.systempreferences:com.apple.settings.PrivacySecurity.extension"
# GoatCounter, a visitor counter without cookies: the code of the account
# (<code>.goatcounter.com), set by pages.yml from a repository variable.
# Empty: the site counts nothing (besluit 2026-11-03).
COUNTER_VARIABLE = "HUISMUS_SITE_COUNTER"
# The pictures in docs/site/, each as <name>.<nl|en>.<light|dark>.webp.
STILLS = ("overzicht",)
# Only as a phone shows them.
PHONE_STILLS = ("uitgaven",)
ANIMATIONS = ("factuur-maken", "importeren")
# Parts of a screen, shown large (Camera.detail in scripts/site_beelden.py).
DETAILS = ("kor", "jaar")
MEDIA = STILLS + PHONE_STILLS + ANIMATIONS + DETAILS
MEDIA_DIR = Path(settings.BASE_DIR) / "docs" / "site"
# A still is 2560 px wide, for a sharp screen; a phone gets this width.
SMALL_WIDTH = 1280
# The photos of people at work (scripts/site_fotos.py), each in two widths.
PHOTOS = {
    "werkplaats": (800, 1600),
    "keukentafel": (600, 1200),
    "fotograaf": (360, 720),
    "hovenier": (360, 720),
    "schrijver": (360, 720),
}

_STATIC = Path(settings.BASE_DIR) / "huismus" / "core" / "static" / "core"
_FONTS = ("inter-latin-wght-normal.woff2", "bricolage-grotesque-latin-opsz-normal.woff2")
_SITE_CSS = Path(settings.BASE_DIR) / "huismus" / "templates" / "site" / "site.css"


def home_url(language: str) -> str:
    return "/" if language == "nl" else "/en/"


def help_url(language: str, slug: str = "", anchor: str = "") -> str:
    base = "/hulp/" if language == "nl" else "/en/help/"
    return base + (f"{slug}/" if slug else "") + anchor


def whats_new_url(language: str) -> str:
    """Wat is er nieuw on the site: rebuilt with every release, so it already
    has the version an installed Huismus is about to get."""
    return f"https://{DOMAIN}{help_url(language, 'nieuw')}"


def features_overview_url(language: str | None) -> str:
    """The page Functies on the site, for the app's Hulp: what Huismus can do
    and what is coming, with the months, is only there."""
    language = "en" if (language or "")[:2] == "en" else "nl"
    return f"https://{DOMAIN}{features_url(language)}"


def install_url(language: str) -> str:
    return "/installeren/" if language == "nl" else "/en/install/"


def features_url(language: str) -> str:
    return "/functies/" if language == "nl" else "/en/features/"


def switching_url(language: str) -> str:
    """Overstappen in the menu: the block on the home page, until the page
    Overstappen exists (huismus-intern/besluiten.md, 2026-11-13)."""
    return home_url(language) + "#overstappen"


def contribute_url(language: str) -> str:
    return "/meebouwen/" if language == "nl" else "/en/contribute/"


def download_page_url(language: str, platform: str) -> str:
    """The page a button goes to: it starts the download and shows how to
    open the app the first time. A visit to it is a download, for the counter."""
    return ("/download/" if language == "nl" else "/en/download/") + f"{platform}/"


def download_url(platform: str) -> str:
    """Always the newest release, so a button never points at an old version."""
    return f"{REPOSITORY}/releases/latest/download/{LATEST_ASSETS[platform]}"


def media_files() -> list[Path]:
    """Every picture of the app; a still also as the app shows it on a phone
    (….phone.webp), for a narrow screen."""
    return [
        MEDIA_DIR / f"{name}.{language}.{scheme}{kind}.webp"
        for name in MEDIA
        for language in help.LANGUAGES
        for scheme in ("light", "dark")
        for kind in (
            ("", ".phone") if name in STILLS else (".phone",) if name in PHONE_STILLS else ("",)
        )
    ]


# The photos with the app on the laptop: one per language (scripts/site_fotos.py).
PHOTOS_WITH_SCREEN = ("werkplaats", "keukentafel")


def photo_files() -> list[Path]:
    files = []
    for name, widths in PHOTOS.items():
        languages = help.LANGUAGES if name in PHOTOS_WITH_SCREEN else ("",)
        for language in languages:
            for width in widths:
                parts = (name, language, str(width), "webp")
                files.append(MEDIA_DIR / "fotos" / ".".join(p for p in parts if p))
    return files


def social_image(language: str) -> Path:
    """The picture a link to the site shows on LinkedIn and in chat apps:
    1200 × 630, PNG because not every app reads WebP (scripts/site_beelden.py)."""
    return MEDIA_DIR / f"delen.{language}.png"


def _features() -> dict:
    other = site_features.OTHER_PACKAGES
    month = site_features.expected(other)
    next_up = None
    if site_features.COMING:
        first_month, items = site_features.COMING[0]
        name = str(items[0].name)
        # In the middle of a sentence: "Komt eraan: importeren uit …".
        next_up = (first_month, name[:1].lower() + name[1:])
    return {
        "next_up": next_up,
        "switching": (month, other) if month else None,
        "now": site_features.NOW,
        "coming": site_features.COMING,
        "later": site_features.LATER,
        "maybe": site_features.MAYBE,
        "never": site_features.NEVER,
    }


def _help_links(language: str) -> dict[str, str]:
    """{slug: address}, with _ for - so a template can read help.back_ups."""
    return {slug.replace("-", "_"): help_url(language, slug) for slug in TOPICS}


def _pages(language: str, version: str) -> dict[str, tuple[str, dict]]:
    """{address: (template, context)} for one language."""
    other = "en" if language == "nl" else "nl"
    pages = {
        home_url(language): (
            "site/index.html",
            {
                "nav": "home",
                "switch_url": home_url(other),
                "help": _help_links(language),
                "features": _features(),
            },
        ),
        features_url(language): (
            "site/features.html",
            {
                "nav": "features",
                "switch_url": features_url(other),
                "help": _help_links(language),
                "features": _features(),
            },
        ),
        install_url(language): (
            "site/install.html",
            {
                "nav": "install",
                "switch_url": install_url(other),
                "help": _help_links(language),
            },
        ),
        **{
            download_page_url(language, name): (
                "site/download.html",
                {
                    "nav": "download",
                    "switch_url": download_page_url(other, name),
                    "platform": name,
                    "file_url": download_url(platform),
                    "help": _help_links(language),
                },
            )
            for name, platform in PLATFORMS.items()
        },
        contribute_url(language): (
            "site/contribute.html",
            {"nav": "contribute", "switch_url": contribute_url(other)},
        ),
        help_url(language): (
            "site/help_index.html",
            {
                "nav": "help",
                "switch_url": help_url(other),
                "groups": [
                    (
                        group.title,
                        [
                            (
                                help_url(language, s),
                                help.title(s, language),
                                help.summary(s, language),
                            )
                            for s in group.topics
                        ],
                    )
                    for group in help.groups(shown=TOPICS)
                ],
            },
        ),
    }
    for slug in TOPICS:
        page = help.render(slug, language, link=lambda s, a: help_url(language, s, a))
        pages[help_url(language, slug)] = (
            "site/help_page.html",
            {
                "nav": "help",
                "switch_url": help_url(other, slug),
                "page": page,
                "summary": help.summary(slug, language),
            },
        )
    return pages


def _links(language: str) -> dict[str, str]:
    """The addresses every page of one language links to."""
    return {
        "language": language,
        "mac_url": download_page_url(language, "mac"),
        "windows_url": download_page_url(language, "windows"),
        "home_url": home_url(language),
        "switching_url": switching_url(language),
        "features_url": features_url(language),
        "help_index_url": help_url(language),
        "install_url": install_url(language),
        "contribute_url": contribute_url(language),
    }


def build(out: Path) -> list[str]:
    """Write the whole site into `out` (emptied first); returns the addresses.

    Only an empty folder or an earlier site (it has a CNAME) is emptied, so a
    wrong folder, like the repository itself, is refused rather than wiped."""
    past = site_features.months_in_the_past(date.today())
    if past:
        months = ", ".join(month.strftime("%Y-%m") for month in past)
        raise ValueError(
            f"Komt eraan noemt een maand die voorbij is ({months}): "
            "werk huismus/core/site_features.py bij."
        )
    if out.exists() and any(out.iterdir()):
        if not (out / "CNAME").exists():
            raise ValueError(f"{out} is niet leeg en geen eerdere site.")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    version = updates.current_version()
    shared = {
        "repository": REPOSITORY,
        "version": version,
        "domain": DOMAIN,
        "mac_privacy_settings": MAC_PRIVACY_SETTINGS,
        "counter": os.environ.get(COUNTER_VARIABLE, "").strip(),
        "fonts": _FONTS,
    }
    addresses = []
    for language in help.LANGUAGES:
        with translation.override(language):
            for address, (template, context) in _pages(language, version).items():
                html = render_to_string(
                    template,
                    shared
                    | context
                    | {
                        "address": address,
                        "other_language": "en" if language == "nl" else "nl",
                    }
                    | _links(language),
                )
                target = out / address.strip("/") / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")
                addresses.append(address)
    with translation.override("nl"):
        (out / "404.html").write_text(
            render_to_string(
                "site/404.html",
                shared | {"address": "/404/", "nav": "404"} | _links("nl"),
            ),
            encoding="utf-8",
        )
    (out / "beelden" / "fotos").mkdir(parents=True)
    for path in media_files():
        shutil.copy(path, out / "beelden" / path.name)
    for name in STILLS:
        for path in MEDIA_DIR.glob(f"{name}.*.webp"):
            if not path.stem.endswith(".phone"):
                _small(path, out / "beelden" / f"{path.stem}.{SMALL_WIDTH}.webp")
    for name in ANIMATIONS:
        for path in MEDIA_DIR.glob(f"{name}.*.webp"):
            _last_frame(path, out / "beelden" / f"{path.stem}.still.webp")
    for path in photo_files():
        shutil.copy(path, out / "beelden" / "fotos" / path.name)
    for language in help.LANGUAGES:
        shutil.copy(social_image(language), out / f"delen.{language}.png")
    shutil.copy(_STATIC / "huismus.css", out / "huismus.css")
    shutil.copy(_SITE_CSS, out / "site.css")
    # huismus.css loads its letters from fonts/, next to itself.
    shutil.copytree(_STATIC / "fonts", out / "fonts")
    shutil.copy(_STATIC / "favicon.svg", out / "favicon.svg")
    shutil.copy(_STATIC / "icons" / "apple-touch-icon.png", out / "apple-touch-icon.png")
    _for_search_engines(out, addresses)
    # GitHub Pages: the custom domain, and serve the files as they are (no Jekyll).
    (out / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return addresses


def _small(still: Path, target: Path) -> None:
    with Image.open(still) as picture:
        height = round(picture.height * SMALL_WIDTH / picture.width)
        picture.resize((SMALL_WIDTH, height), Image.LANCZOS).save(target, quality=80, method=6)


def _last_frame(animation: Path, target: Path) -> None:
    """With "minder beweging" a visitor gets the end of an animation as a
    still: the paid invoice, the finished import (WCAG 2.2.2)."""
    with Image.open(animation) as picture:
        picture.seek(picture.n_frames - 1)
        picture.convert("RGB").save(target, quality=80, method=6)


def _for_search_engines(out: Path, addresses: list[str]) -> None:
    """robots.txt and a sitemap. The download pages only start a download, so
    they stay out (they also say noindex)."""
    downloads = {download_page_url(lang, name) for lang in help.LANGUAGES for name in PLATFORMS}
    urls = "".join(
        f"<url><loc>https://{DOMAIN}{address}</loc></url>\n"
        for address in addresses
        if address not in downloads
    )
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n{urls}</urlset>\n',
        encoding="utf-8",
    )
    (out / "robots.txt").write_text(
        f"User-agent: *\nAllow: /\n\nSitemap: https://{DOMAIN}/sitemap.xml\n", encoding="utf-8"
    )
