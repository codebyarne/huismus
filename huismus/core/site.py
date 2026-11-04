# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The Huismus site (huismus.arnekrijnsen.com): static pages on GitHub Pages.

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
    /hulp/              /en/help/
    /hulp/<onderwerp>/  /en/help/<topic>/
    /meebouwen/         /en/contribute/
    /download/<mac|windows>/  /en/download/<mac|windows>/

Visits are counted only when COUNTER_VARIABLE holds a GoatCounter code: a
1×1 image per page, no cookies and no JS.
"""

import os
import shutil
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from django.utils import translation
from PIL import Image

from . import help, updates

DOMAIN = "huismus.arnekrijnsen.com"
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
MEDIA = (
    "overzicht",
    "factuur-maken",
    "offerte-omzetten",
    "facturen",
    "offertes",
    "uitgaven",
    "jaaroverzicht",
    "ai",
    "instellingen",
    "importeren",
    "welkom",
)
MEDIA_DIR = Path(settings.BASE_DIR) / "docs" / "site"

_STATIC = Path(settings.BASE_DIR) / "huismus" / "core" / "static" / "core"
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


def install_url(language: str) -> str:
    return "/installeren/" if language == "nl" else "/en/install/"


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
    return [
        MEDIA_DIR / f"{name}.{language}.{scheme}.webp"
        for name in MEDIA
        for language in help.LANGUAGES
        for scheme in ("light", "dark")
    ]


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
                "topics": [
                    (help_url(language, s), help.title(s, language), help.summary(s, language))
                    for s in TOPICS
                ],
            },
        ),
    }
    for slug in TOPICS:
        page = help.render(slug, language, link=lambda s, a: help_url(language, s, a))
        pages[help_url(language, slug)] = (
            "site/help_page.html",
            {"nav": "help", "switch_url": help_url(other, slug), "page": page},
        )
    return pages


def build(out: Path) -> list[str]:
    """Write the whole site into `out` (emptied first); returns the addresses.

    Only an empty folder or an earlier site (it has a CNAME) is emptied, so a
    wrong folder, like the repository itself, is refused rather than wiped."""
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
                        "language": language,
                        "address": address,
                        "mac_url": download_page_url(language, "mac"),
                        "windows_url": download_page_url(language, "windows"),
                        "home_url": home_url(language),
                        "help_index_url": help_url(language),
                        "install_url": install_url(language),
                        "contribute_url": contribute_url(language),
                    },
                )
                target = out / address.strip("/") / "index.html"
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(html, encoding="utf-8")
                addresses.append(address)
    with translation.override("nl"):
        (out / "404.html").write_text(
            render_to_string(
                "site/404.html",
                shared
                | {
                    "language": "nl",
                    "address": "/404/",
                    "mac_url": download_page_url("nl", "mac"),
                    "windows_url": download_page_url("nl", "windows"),
                    "home_url": "/",
                    "help_index_url": "/hulp/",
                    "install_url": install_url("nl"),
                    "contribute_url": contribute_url("nl"),
                },
            ),
            encoding="utf-8",
        )
    (out / "beelden").mkdir()
    for path in media_files():
        shutil.copy(path, out / "beelden" / path.name)
    for language in help.LANGUAGES:
        _social_image(language, out / f"delen.{language}.png")
    shutil.copy(_STATIC / "huismus.css", out / "huismus.css")
    shutil.copy(_SITE_CSS, out / "site.css")
    shutil.copy(_STATIC / "favicon.svg", out / "favicon.svg")
    shutil.copy(_STATIC / "icons" / "apple-touch-icon.png", out / "apple-touch-icon.png")
    # GitHub Pages: the custom domain, and serve the files as they are (no Jekyll).
    (out / "CNAME").write_text(DOMAIN + "\n", encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    return addresses


def _social_image(language: str, target: Path) -> None:
    """The picture a link to the site shows on LinkedIn and in chat apps:
    the overview, 1200 × 630, PNG because not every app reads WebP."""
    with Image.open(MEDIA_DIR / f"overzicht.{language}.light.webp") as shot:
        width = shot.width
        height = round(width * 630 / 1200)
        shot.crop((0, 0, width, height)).resize((1200, 630), Image.LANCZOS).save(target)
