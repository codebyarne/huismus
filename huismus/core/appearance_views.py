# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Weergave: the language and theme of Huismus in one form
(huismus-intern/besluiten.md, 2026-10-31, "Taal en thema naar Instellingen").

The two are kept differently on purpose. The language is a cookie per
device, the same one the NL/EN switch on the login page sets, so a
language chosen there is not overwritten after signing in. The theme is
per user (core.models.UserPreferences), on every device they use.
"""

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from .appearance import LANGUAGE_CHOICES, theme_of
from .models import THEME_CHOICES, UserPreferences


class AppearanceForm(forms.Form):
    # Each language in its own words, so it can be found in either one.
    language = forms.ChoiceField(label=gettext_lazy("Taal"), choices=LANGUAGE_CHOICES)
    # Empty is the choice "Systeem" (THEME_CHOICES), so not required.
    theme = forms.ChoiceField(label=gettext_lazy("Thema"), choices=THEME_CHOICES, required=False)


@login_required
def page(request):
    if request.method == "POST":
        form = AppearanceForm(request.POST)
        if form.is_valid():
            language = form.cleaned_data["language"]
            UserPreferences.objects.update_or_create(
                user=request.user, defaults={"theme": form.cleaned_data["theme"]}
            )
            # The confirmation in the language just chosen.
            translation.activate(language)
            messages.success(request, _("Instellingen opgeslagen."))
            response = redirect("business:appearance")
            # The cookie Django's set_language sets; not that view itself,
            # because this one form also saves the theme.
            response.set_cookie(
                settings.LANGUAGE_COOKIE_NAME,
                language,
                max_age=settings.LANGUAGE_COOKIE_AGE,
                path=settings.LANGUAGE_COOKIE_PATH,
                domain=settings.LANGUAGE_COOKIE_DOMAIN,
                secure=settings.LANGUAGE_COOKIE_SECURE,
                httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
                samesite=settings.LANGUAGE_COOKIE_SAMESITE,
            )
            return response
    else:
        form = AppearanceForm(
            initial={"language": translation.get_language(), "theme": theme_of(request.user)}
        )
    return render(request, "business/appearance.html", {"form": form})
