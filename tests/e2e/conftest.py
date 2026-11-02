# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Browser tests (pytest-playwright + Django's live server).

These cover what the server-side tests can't: HTMX, the JavaScript in
huismus/core/static/core/app.js, page swaps with hx-boost and switching language.
One-time setup: `uv run playwright install chromium`.
"""

import os
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.backup import (
    BEFORE_SAMPLE_DATA_FILE_NAME,
    STATUS_FILE_NAME,
    UPDATE_STATUS_FILE_NAME,
)
from tests.e2e.server_report import describe_server
from tests.support import clean_up_issued_documents_for_flush

# Playwright's sync API runs an event loop in this thread; Django refuses
# ORM calls from inside one unless told it's fine. It is here: the test
# only sets up data, the live server handles the requests.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")

# A skipped or aborted view transition only means no animation (hidden tab,
# a click or resize during a transition); it is not a bug in the page.
# The last one is WebKit's wording for a transition a newer one replaced.
IGNORED = ("ViewTransition", "Transition was aborted", "view transition aborted")

PASSWORD = "e2e-wachtwoord-123"

# How long a click or a page load may take. WebKit gets more: on CI it
# sometimes took longer than 5 s to call a button in a dialog stable, or to
# load the page after the import's commit, but only on runs that were slow
# throughout (about 9 minutes instead of 7.5) and green on a rerun. A busy
# machine, then, not a page that hangs; that cause is read from the logs,
# not seen in WebKit itself.
#
# Both clocks get it: page.set_default_timeout() covers clicks, fills and
# page loads, expect() has a clock of its own (also 5 s). With only the
# first, an expect() right after a slow POST (the import's dry run) still
# gave up after 5 s in WebKit on CI.
TIMEOUT = 5000
WEBKIT_TIMEOUT = 15000


@pytest.fixture(scope="session")
def browser_type_launch_args(browser_type_launch_args, browser_name):
    """An already installed Chromium instead of Playwright's own download,
    when HUISMUS_CHROMIUM_EXECUTABLE points to one. Claude Code's cloud
    containers ship a Chromium that doesn't match Playwright's pinned
    revision (.claude/hooks/session-start.sh sets the variable there)."""
    executable = os.environ.get("HUISMUS_CHROMIUM_EXECUTABLE")
    if executable and browser_name == "chromium":
        return {**browser_type_launch_args, "executable_path": executable}
    return browser_type_launch_args


@pytest.fixture(scope="session")
def browser_context_args(browser_context_args):
    """A Dutch browser, whatever the machine's language: the app follows
    Accept-Language, and these tests read the Dutch UI (the language switch
    test changes it on purpose).

    No service worker (huismus/core/pwa.py): page.route() doesn't see requests from
    a page a worker controls in every engine. The offline test turns it on.

    Reduced motion: huismus.css then shortens every animation to 1 ms, so
    a click in a dialog doesn't wait for it to finish opening (hm-pop). It
    didn't stop WebKit's timeouts on CI; see WEBKIT_TIMEOUT."""
    return {
        **browser_context_args,
        "locale": "nl-NL",
        "service_workers": "block",
        "reduced_motion": "reduce",
    }


def _forget_this_computer(settings):
    for name in (STATUS_FILE_NAME, UPDATE_STATUS_FILE_NAME, BEFORE_SAMPLE_DATA_FILE_NAME):
        (Path(settings.DATA_DIR) / name).unlink(missing_ok=True)


@pytest.fixture
def app(live_server, page, transactional_db, settings, browser_name):
    """A page logged in as a fresh user, with business settings filled in.
    Fails the test on any JavaScript error in the browser console."""
    # The files beside the database that belong to the computer (the backup
    # folder and its status, the update setting) start empty in each test,
    # so one test's failed backup is never the next one's banner.
    _forget_this_computer(settings)
    # Outside DEBUG the cookies are Secure (meant for HTTPS, SPEC.md 9); the
    # live server speaks plain HTTP. Chromium accepts Secure cookies on
    # http://localhost anyway, WebKit and Firefox don't.
    settings.SESSION_COOKIE_SECURE = False
    settings.CSRF_COOKIE_SECURE = False
    settings.LANGUAGE_COOKIE_SECURE = False
    get_user_model().objects.create_user(username="freelancer", password=PASSWORD)
    business = Settings.load()
    business.business_name = "Voorbeeld BV"
    business.address_line1 = "Hoofdstraat 1"
    business.postal_code = "1234 AB"
    business.city = "Amsterdam"
    business.kvk_number = "12345678"
    business.iban = "NL91ABNA0417164300"
    business.email = "info@example.invalid"
    business.save()

    errors = []

    def record(text):
        if not any(note in text for note in IGNORED) and not any(
            part in text for part in page.tolerate
        ):
            errors.append(text)

    # Messages a test accepts on purpose (see test_walkthrough.py).
    page.tolerate = []

    page.on("pageerror", lambda error: record(str(error)))
    page.on("console", lambda message: record(message.text) if message.type == "error" else None)
    timeout = WEBKIT_TIMEOUT if browser_name == "webkit" else TIMEOUT
    page.set_default_timeout(timeout)
    expect.set_options(timeout=timeout)
    # The first page of a fresh browser context: with every core running
    # tests (pytest -n auto), Firefox sometimes needs longer than 5 s just
    # to get going. This load gets more time than the test's own steps.
    # Even 30 s was sometimes not enough on CI, green on a rerun; the error
    # then says what the server was doing (tests/e2e/server_report.py).
    # The listener stays for the rest of the test; only a timeout here reads it.
    answered = []
    page.on("response", lambda response: answered.append(f"{response.status} {response.url}"))
    try:
        page.goto(f"{live_server.url}/login/", timeout=30000)
    except PlaywrightTimeoutError as error:
        raise PlaywrightTimeoutError(f"{error.message}\n{describe_server(answered)}") from error
    page.fill("#id_username", "freelancer")
    page.fill("#id_password", PASSWORD)
    page.click("button[type=submit]")
    page.wait_for_url(f"{live_server.url}/")
    page.base = live_server.url
    yield page
    # The live server's issued documents would make the next flush fail on
    # the immutability triggers; see tests/support.py.
    clean_up_issued_documents_for_flush()
    _forget_this_computer(settings)
    assert errors == [], f"JavaScript errors: {errors}"


@pytest.fixture
def contact(transactional_db):
    return Contact.objects.create(
        company_name="Bakkerij De Korrel",
        address_line1="Hoofdweg 1",
        postal_code="3511 AA",
        city="Utrecht",
    )


@pytest.fixture
def history(transactional_db):
    """A nine-year administration (huismus/core/demo_history.py), the size of a real
    one. Use it for what only shows on long lists: filters, pagination,
    clicking through."""
    from huismus.core.demo_history import create_history

    create_history()
