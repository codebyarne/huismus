# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The M8 app shell in huismus/templates/base.html: navigation, logout, language."""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.messages import constants as message_levels
from django.urls import reverse
from django.utils import translation

pytestmark = pytest.mark.django_db


@pytest.fixture
def logged_in(client):
    user = get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.force_login(user)
    return client


def test_current_section_is_marked_in_the_navigation(logged_in):
    html = logged_in.get(reverse("contacts:list")).content.decode()
    assert f'href="{reverse("contacts:list")}" aria-current="page"' in html
    assert f'href="{reverse("documents:list")}" aria-current="page"' not in html


def test_expenses_subnavigation_only_shows_inside_expenses(logged_in):
    categories = reverse("expenses:category_list")
    assert '<div class="sub">' not in logged_in.get(reverse("contacts:list")).content.decode()
    html = logged_in.get(categories).content.decode()
    assert '<div class="sub">' in html
    assert f'href="{categories}" aria-current="page"' in html


def test_the_year_overview_is_under_rapporten_not_under_uitgaven(logged_in):
    html = logged_in.get(reverse("reports:year_overview")).content.decode()
    sidebar = html.split('class="sidebar"', 1)[1].split("</aside>", 1)[0]
    assert f'href="{reverse("reports:index")}" aria-current="page"' in sidebar
    assert '<div class="sub">' not in sidebar
    assert reverse("reports:year_overview") not in sidebar


def test_logout_is_a_post_form(logged_in):
    html = logged_in.get(reverse("home")).content.decode()
    assert f'method="post" action="{reverse("logout")}"' in html
    response = logged_in.post(reverse("logout"))
    assert response.status_code == 302
    assert logged_in.get(reverse("home")).status_code == 302


@pytest.fixture
def restore_language():
    # LocaleMiddleware activates the chosen language for this thread and
    # doesn't reset it, so without this later tests would run in English.
    yield
    translation.activate("nl")


def test_language_switch_changes_the_ui_language(logged_in, restore_language):
    response = logged_in.post(reverse("set_language"), {"language": "en", "next": reverse("home")})
    assert response.status_code == 302
    html = logged_in.get(reverse("home")).content.decode()
    # Only the active language, not a translated string: CI doesn't run
    # compilemessages, so the .mo catalogs don't exist there.
    assert '<html lang="en">' in html


def test_messages_render_as_toasts_with_their_level(logged_in, settings):
    # The settings screen adds a success message on save; any level works the
    # same way, so check the mapping with the message framework directly.
    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.template.loader import render_to_string
    from django.test import RequestFactory

    request = RequestFactory().get("/")
    request.session = logged_in.session
    storage = FallbackStorage(request)
    storage.add(message_levels.ERROR, "Iets ging mis")
    html = render_to_string("core/_toasts.html", {"messages": storage})
    assert 'class="toast flash-error"' in html
    assert 'role="alert"' in html


def test_login_language_switch_is_not_nested_in_the_login_form(client):
    # A <form> inside a <form> is dropped by the HTML parser: NL/EN would
    # then submit the login form instead of switching the language.
    html = client.get(reverse("login")).content.decode()
    login_form_end = html.index("</form>")
    assert html.index('class="lang"') > login_form_end


def test_file_downloads_are_not_boosted(logged_in):
    # hx-boost would swap a CSV or PDF response into the page instead of
    # downloading it.
    html = logged_in.get(reverse("reports:year_overview")).content.decode()
    assert f"{reverse('reports:year_overview_csv')}?jaar=" in html
    csv_link = html.split(reverse("reports:year_overview_csv"), 1)[1].split(">", 1)[0]
    assert 'hx-boost="false"' in csv_link


@pytest.mark.parametrize(
    ("url_name", "kwargs", "section", "subsection"),
    [
        ("home", {}, "home", None),
        ("documents:list", {}, "documents", None),
        ("expenses:list", {}, "expenses", None),
        ("expenses:receipt_upload", {"pk": 1}, "expenses", None),
        ("reports:year_overview_csv", {}, "reports", None),
        ("expenses:category_delete", {"pk": 1}, "expenses", "categories"),
    ],
)
def test_navigation_marks_one_section_and_at_most_one_subsection(
    rf, url_name, kwargs, section, subsection
):
    from django.urls import resolve

    from huismus.core.context_processors import navigation

    request = rf.get(reverse(url_name, kwargs=kwargs))
    request.resolver_match = resolve(request.path)
    assert navigation(request) == {"nav_section": section, "nav_subsection": subsection}


def test_sidebar_has_one_item_called_importeren(logged_in):
    # Importeren is the Moneybird import; two identical labels were easy to
    # mix up.
    html = logged_in.get(reverse("expenses:list")).content.decode()
    sidebar = html.split('class="sidebar"', 1)[1].split("</aside>", 1)[0]
    assert sidebar.count(">Importeren<") == 1
