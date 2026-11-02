# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two things pywebview's macOS window does differently from a browser,
and that Huismus needs:

- A PDF to download (Content-Disposition: attachment) would be shown in
  the window itself, with no back button to leave it. Here it goes to a
  save dialog, downloaded by WebKit itself so the window's cookie
  (huismus/core/desktop.py) goes along.
- A link or form with target="_blank" (the draft's "Voorbeeld-pdf") would
  open in the browser, where the window's cookie is missing, or not at
  all. Here Huismus's own pages open in a second window of the app.
  Other sites still open in the browser.

pywebview creates its delegate as BrowserView.BrowserDelegate, so a
subclass in that place is all it takes. macOS only; Windows (WebView2)
comes later in M11.
"""

import AppKit
import Foundation
import objc
import WebKit
from webview.platforms import cocoa

_HOSTS = {"127.0.0.1", "localhost"}
# Second windows, kept here so they are not released while open. Closed
# ones stay too: a handful per session, gone when the app quits.
_windows = []


class _Delegate(cocoa.BrowserView.BrowserDelegate):
    def webView_decidePolicyForNavigationResponse_decisionHandler_(
        self, webview, navigation_response, decision_handler
    ):
        response = navigation_response.response()
        disposition = ""
        if isinstance(response, Foundation.NSHTTPURLResponse):
            disposition = response.valueForHTTPHeaderField_("Content-Disposition") or ""
        if disposition.lower().startswith("attachment"):
            decision_handler(WebKit.WKNavigationResponsePolicyDownload)
            return
        objc.super(_Delegate, self).webView_decidePolicyForNavigationResponse_decisionHandler_(
            webview, navigation_response, decision_handler
        )

    def webView_navigationResponse_didBecomeDownload_(self, webview, navigation_response, download):
        # WKDownload holds its delegate weakly; retain() keeps it alive for
        # the download, as pywebview does for its own downloads.
        download.setDelegate_(cocoa.BrowserView.DownloadDelegate.alloc().init().retain())

    def webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
        self, webview, configuration, action, features
    ):
        if action.request().URL().host() not in _HOSTS:
            return objc.super(
                _Delegate, self
            ).webView_createWebViewWithConfiguration_forNavigationAction_windowFeatures_(
                webview, configuration, action, features
            )
        return _second_window(configuration)


def _second_window(configuration):
    """WebKit loads the request (a POST too) in the view returned here,
    with the same cookies as the main window."""
    frame = Foundation.NSMakeRect(0, 0, 900, 1000)
    style = (
        AppKit.NSWindowStyleMaskTitled
        | AppKit.NSWindowStyleMaskClosable
        | AppKit.NSWindowStyleMaskMiniaturizable
        | AppKit.NSWindowStyleMaskResizable
    )
    window = AppKit.NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
        frame, style, AppKit.NSBackingStoreBuffered, False
    )
    window.setReleasedWhenClosed_(False)
    window.setTitle_("Huismus")
    view = WebKit.WKWebView.alloc().initWithFrame_configuration_(frame, configuration)
    window.setContentView_(view)
    window.center()
    window.makeKeyAndOrderFront_(None)
    _windows.append(window)
    return view


def install():
    cocoa.BrowserView.BrowserDelegate = _Delegate
