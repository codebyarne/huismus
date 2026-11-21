# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The window's own two screens, shown before Django runs: "Huismus
start…" and "Huismus kon niet starten" (design round 3, D3:
docs/design/ronde-3/Desktop-opstarten.dc.html).

While Huismus starts or updates, the sparrow of the logo hops and pecks
instead of a spinner (_BIRD); with reduced motion it sits still.

Django's gettext is not available yet here, so the two languages are
written out; the language follows the system's, like the app's pages do
(Accept-Language). A moment the app also shows, such as updating, uses
the app's own words (tests/desktop/test_desktop_shell.py checks it), and
every text follows docs/schrijfwijzer.md (tests/core/test_schrijfwijzer.py).
"""

from html import escape
from string import Template

from desktop.paths import bundle_dir

TEXTS = {
    "nl": {
        "starting": "Huismus start…",
        "opening": "Je administratie gaat zo open.",
        "failed": "Huismus kon niet starten",
        "advice": (
            "Probeer het opnieuw. Lukt het weer niet? Bewaar het logbestand en stuur "
            "het mee als je om hulp vraagt."
        ),
        "retry": "Opnieuw proberen",
        "save_log": "Logbestand bewaren",
        "code": "Foutcode",
        "save_file": "Bewaar",
        "updating": "Huismus werkt zichzelf bij…",
        "updating_to": "Versie $version wordt geïnstalleerd. Dit duurt ongeveer een minuut.",
        "update_failed": "Bijwerken is niet gelukt",
        "update_failed_text": (
            "Huismus $to kon je administratie niet overnemen. De back-up van vlak "
            "voor het bijwerken ($moment) staat klaar."
        ),
        "restore": "Back-up terugzetten",
        "after_restore": (
            "Na terugzetten is alles weer zoals vlak voor het bijwerken. Installeer "
            "daarna weer versie $previous."
        ),
        "download": "Versie $previous downloaden",
        "restored": "Teruggezet naar $moment",
        "restored_text": "Installeer versie $previous om verder te werken.",
        "restore_failed": "Terugzetten is niet gelukt",
        "restore_failed_text": "De back-up staat in $backup.",
    },
    "en": {
        "starting": "Huismus is starting…",
        "opening": "Your records will open in a moment.",
        "failed": "Huismus could not start",
        "advice": (
            "Try again. Still not working? Save the log file and send it along when "
            "you ask for help."
        ),
        "retry": "Try again",
        "save_log": "Save log file",
        "code": "Error code",
        "save_file": "Save",
        "updating": "Huismus is updating…",
        "updating_to": "Installing version $version. This takes about a minute.",
        "update_failed": "Updating didn't work",
        "update_failed_text": (
            "Huismus $to could not take over your records. The backup from just "
            "before updating ($moment) is ready."
        ),
        "restore": "Restore backup",
        "after_restore": (
            "After restoring, everything is as it was just before updating. Then "
            "install version $previous again."
        ),
        "download": "Download version $previous",
        "restored": "Restored to $moment",
        "restored_text": "Install version $previous to carry on.",
        "restore_failed": "Restoring didn't work",
        "restore_failed_text": "The backup is in $backup.",
    },
}

_PAGE = Template("""<!doctype html>
<html lang="$lang">
<head>
<meta charset="utf-8">
<title>Huismus</title>
<style>$css
.desktop-screen { min-height: 100vh; display: grid; place-content: center; justify-items: center;
  gap: var(--s-4); padding: var(--s-6); text-align: center; background: var(--bg); }
.desktop-screen .mark { width: 56px; height: 56px; }
.desktop-screen h1 { font-size: var(--fs-xl); margin: 0; }
.desktop-screen p { margin: 0; max-width: 34em; color: var(--text-muted); }
$bird_css
.desktop-screen .row { display: flex; gap: var(--s-3); flex-wrap: wrap; justify-content: center; }
</style>
</head>
<body>
<main class="desktop-screen">
$mark
$body
</main>
</body>
</html>
""")


# The sparrow of favicon.svg without its tile, in parts that move: the
# tail, the head (beak and eye) and the whole bird with its shadow.
_BIRD = """<svg class="bird" viewBox="0 0 56 52" xmlns="http://www.w3.org/2000/svg">
<ellipse class="bird-shadow" cx="23" cy="49" rx="12" ry="2"/>
<g class="bird-hop"><g transform="translate(0 4)">
<path class="bird-tail" d="M11 30 3.6 17.4c-.8-1.4.2-2.4 1.6-2L18 19Z"/>
<circle cx="22" cy="28" r="13"/>
<path class="bird-wing" d="M13 26c5-5 13-5 17 1-5 6-13 5-17-1Z"/>
<g class="bird-head">
<circle cx="31" cy="17" r="8.5"/>
<path class="bird-beak" d="M38 12.5 46.5 17 38 21.5Z"/>
<circle class="bird-eye" cx="33" cy="15.5" r="2.6"/>
</g></g></g>
</svg>"""

# Two hops, a look around and two pecks at the ground, every 2.4 s.
_BIRD_CSS = """
.desktop-screen .bird { width: 96px; height: 89px; overflow: visible; fill: var(--primary); }
.bird * { transform-box: fill-box; }
.bird .bird-wing { fill: var(--primary-hover); }
.bird .bird-beak { fill: var(--accent); }
.bird .bird-eye { fill: var(--bg); transform-origin: center; animation: bird-blink 3.1s infinite; }
.bird .bird-shadow { fill: var(--text-muted); opacity: .25; transform-origin: center;
  animation: bird-shadow 2.4s infinite; }
.bird .bird-hop { transform-origin: 50% 100%; animation: bird-hop 2.4s infinite; }
.bird .bird-tail { transform-origin: 100% 85%; animation: bird-tail 2.4s infinite; }
.bird .bird-head { transform-origin: 15% 85%; animation: bird-head 2.4s infinite; }
@keyframes bird-hop {
  0%, 46%, 100% { transform: none; animation-timing-function: ease-out; }
  4%, 26% { transform: scale(1.06, .9); animation-timing-function: ease-out; }
  12%, 32% { transform: translate(5%, -14%) scale(.96, 1.05); animation-timing-function: ease-in; }
  20%, 40% { transform: scale(1.06, .92); }
}
@keyframes bird-shadow {
  0%, 4%, 20%, 26%, 40%, 100% { transform: none; opacity: .25; }
  12%, 32% { transform: scale(.65); opacity: .12; }
}
@keyframes bird-tail {
  0%, 8%, 46%, 100% { transform: none; }
  14%, 34% { transform: rotate(14deg); }
  22%, 42% { transform: rotate(-10deg); }
  80% { transform: none; }
  84% { transform: rotate(8deg); }
  88% { transform: none; }
}
@keyframes bird-head {
  0%, 50%, 100% { transform: none; }
  55%, 60% { transform: rotate(-8deg); }
  64% { transform: none; }
  70%, 82% { transform: rotate(38deg) translate(4%, 6%); }
  76%, 88% { transform: rotate(10deg); }
  92% { transform: none; }
}
@keyframes bird-blink { 0%, 92%, 100% { transform: none; } 95% { transform: scaleY(.1); } }
@media (prefers-reduced-motion: reduce) { .bird, .bird * { animation: none !important; } }
"""


def language(preferred: list[str]) -> str:
    """The first of the system's languages that Huismus has, else Dutch."""
    for code in preferred:
        if code[:2] in TEXTS:
            return code[:2]
    return "nl"


def starting(lang: str) -> str:
    t = TEXTS[lang]
    body = f"<h1>{t['starting']}</h1><p>{t['opening']}</p>"
    return _page(lang, body, waiting=t["starting"])


def failed(lang: str, code: str) -> str:
    """The buttons call desktop.app.Api through pywebview."""
    t = TEXTS[lang]
    body = (
        f"<h1>{t['failed']}</h1><p>{t['advice']}</p>"
        '<div class="row">'
        f'<button class="btn btn-primary" type="button" '
        f'onclick="pywebview.api.retry()">{t["retry"]}</button>'
        f'<button class="btn btn-secondary" type="button" '
        f'onclick="pywebview.api.save_log()">{t["save_log"]}</button>'
        "</div>"
        f'<p class="small">{t["code"]}: <code>{escape(code)}</code></p>'
    )
    return _page(lang, body)


def updating(lang: str, version: str = "") -> str:
    t = _texts(lang, version=version)
    body = f"<h1>{t['updating']}</h1>"
    if version:
        body += f"<p>{t['updating_to']}</p>"
    return _page(lang, body, waiting=t["updating"])


def update_failed(lang: str, to: str, previous: str, moment: str) -> str:
    """After an update whose first start couldn't migrate (design D3,
    docs/design/ronde-3/Desktop-bijwerken.dc.html)."""
    t = _texts(lang, to=to, previous=previous, moment=moment)
    body = (
        f"<h1>{t['update_failed']}</h1><p>{t['update_failed_text']}</p>"
        '<div class="row">'
        f'<button class="btn btn-primary" type="button" '
        f'onclick="pywebview.api.restore_before_update()">{t["restore"]}</button>'
        f'<button class="btn btn-secondary" type="button" '
        f'onclick="pywebview.api.save_log()">{t["save_log"]}</button>'
        "</div>"
        f'<p class="small">{t["after_restore"]}</p>'
        f'<p><a href="#" onclick="pywebview.api.open_previous_release()">{t["download"]}</a></p>'
    )
    return _page(lang, body)


def update_restored(lang: str, previous: str, moment: str) -> str:
    """After "Back-up terugzetten": the server stays off, since this
    version would try the same migration again."""
    t = _texts(lang, previous=previous, moment=moment)
    body = (
        f"<h1>{t['restored']}</h1><p>{t['restored_text']}</p>"
        f'<p><a href="#" onclick="pywebview.api.open_previous_release()">{t["download"]}</a></p>'
    )
    return _page(lang, body)


def restore_failed(lang: str, backup: str) -> str:
    t = _texts(lang, backup=backup)
    body = (
        f"<h1>{t['restore_failed']}</h1><p>{t['restore_failed_text']}</p>"
        '<div class="row">'
        f'<button class="btn btn-secondary" type="button" '
        f'onclick="pywebview.api.save_log()">{t["save_log"]}</button>'
        "</div>"
    )
    return _page(lang, body)


def _texts(lang: str, **values) -> dict:
    """The texts with $names filled in, escaped."""
    safe = {name: escape(value) for name, value in values.items()}
    return {key: Template(text).safe_substitute(safe) for key, text in TEXTS[lang].items()}


def _page(lang: str, body: str, waiting: str = "") -> str:
    """With `waiting` (what Huismus is busy with) the sparrow hops; without,
    the logo stands still above the message."""
    static = bundle_dir() / "huismus" / "core" / "static" / "core"
    if waiting:
        mark = f'<span role="status" aria-label="{waiting}">{_BIRD}</span>'
    else:
        sparrow = (static / "favicon.svg").read_text(encoding="utf-8")
        mark = f'<span class="mark" aria-hidden="true">{sparrow}</span>'
    return _PAGE.substitute(
        lang=lang,
        css=(static / "huismus.css").read_text(encoding="utf-8"),
        bird_css=_BIRD_CSS,
        mark=mark,
        body=body,
    )
