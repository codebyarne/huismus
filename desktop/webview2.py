# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""One thing pywebview's Windows window (WebView2) does differently from
a browser, and that Huismus needs, as desktop/webkit.py does on macOS:

- A link or form with target="_blank" (the draft's "Voorbeeld-pdf") would
  open in the browser, where the window's cookie (huismus/core/desktop.py) is
  missing. Here Huismus's own pages are left to WebView2, which opens them
  in a second window of its own, with the same cookies, the request as it
  was (a POST too) and its PDF viewer. Other sites still open in the
  browser.

A PDF to download already goes to a save dialog in pywebview, and WebView2
downloads it with the window's cookie.

Only Huismus's own address (serve, from desktop/app.py): a cookie for
127.0.0.1 goes along to every port there, so a second window to another
program on this computer would hand it the window's cookie.
"""

import logging
import webbrowser
from urllib.parse import urlsplit

logger = logging.getLogger("huismus.desktop")
_origin = None  # ("http", "127.0.0.1", 52817) once the server runs


def serve(url: str) -> None:
    global _origin
    _origin = _origin_of(url)


def _origin_of(url: str):
    parts = urlsplit(url)
    return parts.scheme, parts.hostname, parts.port


def opens_in_the_app(url: str) -> bool:
    return _origin is not None and _origin_of(url) == _origin


def _on_new_window_request(self, sender, args):
    url = str(args.get_Uri())
    if opens_in_the_app(url):
        return  # not handled: WebView2 opens its own window
    args.set_Handled(True)
    webbrowser.open(url)


def install():
    """pywebview's own handler (6.2) is replaced by name. Should a later
    pywebview rename it, the log says so instead of the preview silently
    going to the browser."""
    from webview.platforms import edgechromium

    if not hasattr(edgechromium.EdgeChrome, "on_new_window_request"):
        logger.warning(
            "pywebview heeft geen on_new_window_request meer; Voorbeeld-pdf opent in de browser"
        )
    edgechromium.EdgeChrome.on_new_window_request = _on_new_window_request
