# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Content-Security-Policy for every HTML page.

Should an escaping mistake ever let markup from user data through, the
browser still runs no script and loads nothing from elsewhere: only
Huismus's own files. Django 5.2 has no CSP setting of its own yet (6.0
does); this is the whole of it.

Only for text/html: a PDF opened in the browser's own viewer, or a logo or
receipt from data/, has no HTML to protect, and a page policy can stop the
PDF viewer.
"""

CONTENT_SECURITY_POLICY = "; ".join(
    [
        "default-src 'self'",
        "script-src 'self'",
        # style="" attributes in templates, and the <style> htmx adds for
        # its loading indicators.
        "style-src 'self' 'unsafe-inline'",
        # data: for the logo snapshot of an issued document (and the
        # select chevron in huismus.css).
        "img-src 'self' data:",
        "object-src 'none'",
        "base-uri 'none'",
        "form-action 'self'",
        "frame-ancestors 'none'",
    ]
)


class ContentSecurityPolicyMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.get("Content-Type", "").startswith("text/html"):
            response.setdefault("Content-Security-Policy", CONTENT_SECURITY_POLICY)
        return response
