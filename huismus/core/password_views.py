# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Wachtwoord, in the desktop app only (SPEC.md M11; design
D6, docs/design/ronde-3/Beveiliging.dc.html; build choices in
huismus-intern/besluiten.md, 2026-10-29).

Without a password the window signs itself in (huismus/core/desktop.py); with
one, the app asks it when it opens. Changing or turning it off needs the
current password first, checked through authenticate() so a wrong guess
counts towards the same limit as on the login page (huismus/core/login_throttle.py).
A correct current password allows one change within VERIFIED_SECONDS.
"""

import time

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import SetPasswordForm
from django.contrib.auth.password_validation import (
    MinimumLengthValidator,
    get_default_password_validators,
    validate_password,
)
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from . import login_throttle

VERIFIED_SECONDS = 10 * 60
_VERIFIED_AT = "password_verified_at"


def minimum_length() -> int:
    """The length the validators in settings ask for (now 8)."""
    for validator in get_default_password_validators():
        if isinstance(validator, MinimumLengthValidator):
            return validator.min_length
    return 0


class NewPasswordForm(SetPasswordForm):
    """Django's own form and validators, with the design's labels."""

    error_messages = {
        **SetPasswordForm.error_messages,
        "password_mismatch": gettext_lazy(
            "De twee wachtwoorden zijn niet gelijk. Vul ze nog een keer in."
        ),
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].label = gettext_lazy("Nieuw wachtwoord")
        length = minimum_length()
        self.fields["new_password1"].help_text = (
            _("Minstens %(count)d tekens.") % {"count": length} if length else ""
        )
        self.fields["new_password2"].label = gettext_lazy("Nieuw wachtwoord, nog een keer")
        self.fields["new_password2"].help_text = ""

    def validate_password_for_user(self, user, password_field_name="new_password2"):
        """Django's validators, with their errors at "Nieuw wachtwoord",
        where the rules are. Django's own Dutch for "too short" doesn't
        match its message and stays English (found by verify-e2e), so
        that one is ours."""
        password = self.cleaned_data.get(password_field_name)
        if not password:
            return
        try:
            validate_password(password, user)
        except ValidationError as errors:
            for error in errors.error_list:
                if error.code == "password_too_short":
                    error = ValidationError(
                        _("Dit wachtwoord is te kort. Kies er een van minstens %(count)d tekens.")
                        % {"count": minimum_length()},
                        code=error.code,
                    )
                self.add_error("new_password1", error)


class CurrentPasswordForm(forms.Form):
    current = forms.CharField(
        label=gettext_lazy("Huidig wachtwoord"),
        help_text=gettext_lazy("Nodig om het te wijzigen of uit te zetten."),
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request

    def clean_current(self):
        password = self.cleaned_data["current"]
        user = authenticate(
            self.request, username=self.request.user.get_username(), password=password
        )
        if user is None:
            if login_throttle.is_locked():
                raise forms.ValidationError(
                    _(
                        "Je hebt te vaak een verkeerd wachtwoord ingevuld. "
                        "Over een kwartier kun je het weer proberen."
                    )
                )
            raise forms.ValidationError(_("Dit wachtwoord klopt niet."))
        return password


def _is_verified(request) -> bool:
    return time.time() - request.session.get(_VERIFIED_AT, 0) < VERIFIED_SECONDS


@login_required
def page(request):
    if not settings.DESKTOP:
        raise Http404
    user = request.user
    has_password = user.has_usable_password()
    # A new password: the first one, or a change after the current one.
    may_set = not has_password or _is_verified(request)
    action = request.POST.get("action") if request.method == "POST" else None
    # The first password only with the switch on: without :has() in the
    # browser the fields show anyway, and then the switch still decides.
    switched_on = has_password or request.POST.get("enabled") == "on"

    new_form = NewPasswordForm(
        user, request.POST if action == "set" and may_set and switched_on else None
    )
    current_form = CurrentPasswordForm(
        request, request.POST if action in ("change", "off") and has_password else None
    )
    if action == "set" and not may_set:
        # The ten minutes after the current password ran out.
        messages.error(request, _("Vul je huidige wachtwoord nog een keer in."))
        return redirect("business:password")

    if new_form.is_bound and new_form.is_valid():
        new_form.save()
        update_session_auth_hash(request, user)
        request.session.pop(_VERIFIED_AT, None)
        messages.success(
            request, _("Wachtwoord gewijzigd.") if has_password else _("Wachtwoord ingesteld.")
        )
        return redirect("business:password")

    if current_form.is_bound and current_form.is_valid():
        if action == "off":
            user.set_unusable_password()
            user.save(update_fields=["password"])
            # Still signed in; from now on the window signs itself in.
            update_session_auth_hash(request, user)
            messages.success(request, _("Wachtwoord uitgezet."))
        else:
            request.session[_VERIFIED_AT] = time.time()
        return redirect("business:password")

    return render(
        request,
        "business/password.html",
        {
            "has_password": has_password,
            "may_set": may_set,
            "new_form": new_form,
            "current_form": current_form,
        },
    )
