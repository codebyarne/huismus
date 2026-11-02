# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What a user sees Huismus in: the language (a cookie per device) and the
theme (per user, core.models.UserPreferences). Used by the page
Instellingen → Weergave, its card on the overview and the theme on <html>."""

from .models import UserPreferences

LANGUAGE_CHOICES = [("nl", "Nederlands"), ("en", "English")]


def theme_of(user) -> str:
    """ "light", "dark", or "" to follow the system (also for a user who
    never chose)."""
    chosen = UserPreferences.objects.filter(user=user).values_list("theme", flat=True).first()
    return chosen or ""


def language_name(code: str) -> str:
    return dict(LANGUAGE_CHOICES).get(code, code)
