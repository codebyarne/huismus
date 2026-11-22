# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Which navigation item is active, decided once for sidebar and tab bar;
and whether the desktop app signed the window in without a password."""

from django.conf import settings

from huismus.core import auto_backups
from huismus.core.appearance import theme_of
from huismus.core.desktop import has_no_password
from huismus.core.feedback_views import QuickFeedbackForm
from huismus.core.profile import BANK, EXPENSES, QUOTES, profile

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


def parts(request):
    """show_quotes, show_expenses, show_bank: whether a part is in the
    sidebar and under "Nieuw" (#260, core.profile.parts_shown).
    menu_tab: what the tab bar's fourth place holds, "expenses", else "quotes",
    else "contacts" (huismus-intern/besluiten.md, 2026-11-22); the values
    are URL namespaces, like nav_section. menu_more: the sections behind "Meer",
    everything the tab bar has no place for; it lists their links and is
    marked on their pages. Uitgaven's Categorieën is in it as "categories",
    no section: its page marks the Uitgaven tab, like every expenses page."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    from huismus.business.models import Settings

    # Read, never write: a page (the import's dry run) may leave the
    # settings row unmade. Not there yet: the defaults.
    stored = Settings.objects.filter(pk=1).first() or Settings()
    shown = profile(stored).parts_shown
    if EXPENSES in shown:
        tab = "expenses"
    elif QUOTES in shown:
        tab = "quotes"
    else:
        tab = "contacts"
    # Named menu_*: a view's own "tab" (the tabs of Facturen) would win.
    meer = {"reports", "imports", "business", "help"}
    if QUOTES in shown:
        meer.add("quotes")
    if EXPENSES in shown:
        meer.add("categories")
    if BANK in shown:
        meer.add("bank")
    meer.add("contacts")
    meer.discard(tab)
    return {
        "show_quotes": QUOTES in shown,
        "show_expenses": EXPENSES in shown,
        "show_bank": BANK in shown,
        "menu_tab": tab,
        "menu_more": meer,
    }


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


def feedback_panel(request):
    """The empty form of the feedback button, for base.html, with the page
    it is on (huismus/core/feedback_views.py)."""
    if not getattr(request, "user", None) or not request.user.is_authenticated:
        return {}
    return {"quick_feedback_form": QuickFeedbackForm(initial={"page": request.path})}
