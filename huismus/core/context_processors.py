# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which navigation item is active, decided once for sidebar and tab bar;
and whether the desktop app signed the window in without a password."""

from django.conf import settings

from huismus.core import auto_backups
from huismus.core.appearance import theme_of
from huismus.core.desktop import has_no_password

# Expense routes that have their own item in the sidebar's sub-navigation.
# Every other expenses route (list, form, receipts, delete) belongs to the
# "Uitgaven" item itself.
EXPENSES_SUBSECTIONS = {
    "category_list": "categories",
    "category_edit": "categories",
    "category_delete": "categories",
}


def navigation(request):
    """nav_section: the URL namespace ("documents", "expenses", ...), or
    "home". nav_subsection: set only for EXPENSES_SUBSECTIONS, so the
    sidebar marks either "Uitgaven" or one of its sub-items as the current
    page, never both."""
    match = request.resolver_match
    if match is None:
        return {"nav_section": None, "nav_subsection": None}
    section = match.namespace or match.url_name
    subsection = None
    if section == "expenses":
        subsection = EXPENSES_SUBSECTIONS.get(match.url_name)
    return {"nav_section": section, "nav_subsection": subsection}


def desktop(request):
    """desktop: running as the desktop app (SPEC.md M11).
    desktop_without_password: the logout button is left out, since the
    window would only be signed in again (huismus/core/desktop.py)."""
    return {
        "desktop": settings.DESKTOP,
        "desktop_without_password": has_no_password(request.user),
    }


def sample_data(request):
    """sample_data_in_use: the banner with "Weer leegmaken" on every page
    (huismus/core/sample_data.py)."""
    return {"sample_data_in_use": auto_backups.sample_data_in_use()}


def theme(request):
    """theme: what the signed-in user chose on Instellingen → Weergave
    ("light" or "dark"), or "" to follow the system, as before anyone is
    signed in (core.appearance_views)."""
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {"theme": ""}
    return {"theme": theme_of(user)}
