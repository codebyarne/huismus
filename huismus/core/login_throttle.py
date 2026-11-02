# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A cap on failed logins, against guessing the password.

After MAX_FAILURES failed attempts within WINDOW_SECONDS of the first one,
every login is refused until that window has passed — also with the right
password, or the guessing would simply go on. A successful login before
that starts the count over.

Huismus has one account, so all failures count together, not per username
or IP address: behind `tailscale serve` or a reverse proxy every request
comes from the same address anyway.

The check sits in authenticate() itself (ThrottledModelBackend, the one
entry in AUTHENTICATION_BACKENDS), so it covers /admin/login/ as well as
Huismus's own login page. The count lives in Django's default cache: in
memory, per process. The container runs one gunicorn worker; a restart
clears it.
"""

from django.contrib.auth.backends import ModelBackend
from django.core.cache import cache
from django.core.exceptions import PermissionDenied

MAX_FAILURES = 10
WINDOW_SECONDS = 15 * 60
_KEY = "login-throttle-failures"


def is_locked() -> bool:
    return cache.get(_KEY, 0) >= MAX_FAILURES


def record_failure(**kwargs) -> None:
    """user_login_failed receiver."""
    # add() starts the window at the first failure; incr() keeps its expiry.
    cache.add(_KEY, 0, WINDOW_SECONDS)
    try:
        cache.incr(_KEY)
    except ValueError:  # the window expired between add() and incr()
        cache.add(_KEY, 1, WINDOW_SECONDS)


def reset(**kwargs) -> None:
    """user_logged_in receiver."""
    cache.delete(_KEY)


class ThrottledModelBackend(ModelBackend):
    """Django's own backend, refusing while locked.

    PermissionDenied makes authenticate() stop without checking the
    password at all, and fire user_login_failed.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if is_locked():
            raise PermissionDenied
        return super().authenticate(request, username=username, password=password, **kwargs)
