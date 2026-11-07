# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Opening a request that carries a secret (a key, a password, a token)
without following a redirect.

urllib.request.urlopen follows 301, 302, 303 (and 307/308 for GET) and
copies every header but the body's to whatever the Location says: the
Authorization header goes along to another host, or to plain http://.
Here a redirect stays an HTTPError with its 3xx status, which the caller
treats as an address that doesn't answer."""

import urllib.request


class _Refuse(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # None: urllib then raises HTTPError for the 3xx itself.
        return None


_opener = urllib.request.build_opener(_Refuse)


def urlopen(request: urllib.request.Request, timeout: float):
    """As urllib.request.urlopen, but a redirect raises HTTPError."""
    return _opener.open(request, timeout=timeout)


def is_redirect(status: int) -> bool:
    return 300 <= status < 400
