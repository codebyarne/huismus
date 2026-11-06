# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Bonnetjes lezen (SPEC.md M20, part 3; huismus/expenses/
ai_service.py; choices in huismus-intern/besluiten.md, 2026-11-06).

One form, a plain POST. Saving first sends one small test image
(_works): when that fails nothing is saved and the form says why. The key
is never put back in the field.
"""

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext

from huismus.core.models import Attachment

from . import ai_service, inbox
from .ai_service import Config, ServiceError


class ServiceSelect(forms.Select):
    """Each known service carries its address and model, which app.js puts
    in the fields when it is chosen. Without JS, saving fills in what was
    left empty (ReadingForm.clean)."""

    def create_option(self, name, value, *args, **kwargs):
        option = super().create_option(name, value, *args, **kwargs)
        provider = ai_service.PROVIDERS.get(str(value))
        if provider is not None:
            option["attrs"]["data-url"] = provider.url
            option["attrs"]["data-model"] = provider.model
        return option


class ReadingForm(forms.Form):
    provider = forms.ChoiceField(label=gettext_lazy("Dienst"), widget=ServiceSelect)
    url = forms.CharField(
        label=gettext_lazy("Adres"),
        required=False,
        help_text=gettext_lazy(
            "Vult Huismus in bij een bekende dienst. Bij een andere dienst: het adres dat "
            "die geeft voor OpenAI-compatibele apps."
        ),
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )
    model = forms.CharField(
        label=gettext_lazy("Model"),
        required=False,
        help_text=gettext_lazy("Een model dat foto's kan lezen. Huismus stelt er een voor."),
        widget=forms.TextInput(attrs={"autocomplete": "off", "spellcheck": "false"}),
    )
    # Never filled in when the page is shown; empty keeps the saved one.
    key = forms.CharField(
        label=gettext_lazy("API-sleutel"),
        required=False,
        strip=True,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args, saved: Config, **kwargs):
        super().__init__(*args, **kwargs)
        self.saved = saved
        self.fields["provider"].choices = [("", _("Kies een dienst")), *ai_service.choices()]
        # What clean() made of the fields; the view tests it before saving.
        self.config: Config | None = None

    def clean(self):
        cleaned = super().clean()
        provider = cleaned.get("provider")
        if not provider:
            return cleaned
        known = ai_service.PROVIDERS.get(provider)
        url = cleaned.get("url", "").strip() or (known.url if known else "")
        model = cleaned.get("model", "").strip() or (known.model if known else "")
        # Shown back filled in, also when something else is wrong.
        self.data = self.data.copy()
        self.data.update({"url": url, "model": model})
        if not url:
            self.add_error("url", _("Vul dit in."))
        elif error := ai_service.address_error(url):
            self.add_error("url", error)
        if not model:
            self.add_error("model", _("Vul dit in."))
        # The saved key only goes along to the same address: never one
        # service's key to another.
        key = cleaned.get("key") or (self.saved.key if url == self.saved.url else "")
        if not key and url and not ai_service.is_nearby(url):
            self.add_error("key", _("Vul je API-sleutel in."))
        if not self.errors:
            self.config = Config(provider=provider, url=url, model=model, key=key)
        return cleaned


def _sentence(form: ReadingForm) -> str:
    """What happens after saving, for the service now in the form."""
    provider = form["provider"].value() or ""
    url = form["url"].value() or ""
    if provider and url and ai_service.is_nearby(url):
        return _(
            "Na het opslaan stuurt Huismus elk nieuw bonnetje uit je bonnetjesmap naar het "
            "adres hierboven, in je eigen netwerk."
        )
    if provider:
        service = ai_service.provider_name(provider, url)
        return _(
            "Na het opslaan stuurt Huismus elk nieuw bonnetje uit je bonnetjesmap naar "
            "%(service)s. %(service)s rekent de kosten met jou af."
        ) % {"service": service}
    return _(
        "Na het opslaan stuurt Huismus elk nieuw bonnetje uit je bonnetjesmap naar de dienst "
        "die je kiest. Die rekent de kosten met jou af."
    )


def _waiting_sentence() -> str:
    count = Attachment.objects.in_tray().count()
    if not count:
        return ""
    return ngettext(
        "Ook het bonnetje zonder uitgave dat er nu is.",
        "Ook de %(count)s bonnetjes zonder uitgave die er nu zijn.",
        count,
    ) % {"count": count}


def _works(form: ReadingForm) -> bool:
    """Saving first sends one small test image, as setting up WebDAV first
    tries the address. When it fails, the reason goes under "Nog niet
    opgeslagen" of the form's error summary."""
    try:
        ai_service.test_connection(form.config)
    except ServiceError as error:
        form.add_error(None, ai_service.failure_sentence(error.reason, form.config))
        return False
    return True


@login_required
def settings_page(request):
    saved = ai_service.load()
    on = ai_service.is_on(saved)
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "off":
            ai_service.turn_off()
            messages.success(
                request, _("Bonnetjes lezen staat uit. Huismus is de sleutel vergeten.")
            )
            return redirect("business:receipt_reading")
        if action == "test" and on:
            try:
                ai_service.test_connection(saved)
            except ServiceError as error:
                messages.error(request, ai_service.failure_sentence(error.reason, saved))
            else:
                messages.success(
                    request,
                    _("Het werkt. %(service)s kan je bonnetjes lezen.")
                    % {"service": ai_service.name(saved)},
                )
            return redirect("business:receipt_reading")
        form = ReadingForm(request.POST, saved=saved)
        if form.is_valid() and _works(form):
            ai_service.save(form.config)
            messages.success(
                request,
                _("Opgeslagen. %(service)s kan je bonnetjes lezen.")
                % {"service": ai_service.name(form.config)},
            )
            return redirect("business:receipt_reading")
    else:
        initial = {"provider": saved.provider, "url": saved.url, "model": saved.model}
        form = ReadingForm(initial=initial, saved=saved)

    url = form["url"].value() or ""
    if url and ai_service.is_nearby(url):
        key_help = _("Niet nodig voor een adres op je eigen computer of netwerk.")
    elif saved.key:
        key_help = _("Leeg laten houdt de bewaarde sleutel.")
    else:
        key_help = _(
            "Maak je aan op de site van de dienst. Huismus laat hem daarna nooit meer zien."
        )
    return render(
        request,
        "expenses/receipt_reading.html",
        {
            "form": form,
            "on": on,
            "saved": saved,
            "service": ai_service.name(saved) if on else "",
            "folder_on": inbox.is_on(),
            "sentence": _sentence(form),
            "waiting": _waiting_sentence(),
            "key_help": key_help,
            # The help heading comes with reading itself (part 3, step 2).
            "help_url": "",
        },
    )
