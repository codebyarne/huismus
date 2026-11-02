# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from huismus.core.forms import EuroCentsField
from huismus.documents import mail_texts
from huismus.documents.numbering import format_number

from . import smtp
from .logo import validate_and_sanitize_logo
from .models import Settings

DEFAULT_KOR_TEXT = _(
    "Vrijgesteld van btw op grond van de kleineondernemersregeling (KOR). "
    "Er is geen btw in rekening gebracht."
)


# Instellingen → Mailen: a subject and a body per kind and language.
MAIL_TEXT_FIELDS = [
    (kind, part, language, mail_texts.field_name(kind, part, language))
    for kind in mail_texts.KINDS
    for language in mail_texts.LANGUAGES
    for part in ("subject", "body")
]
MAIL_TEXT_TITLES = {"invoice": _("Factuur"), "credit_note": _("Creditnota"), "quote": _("Offerte")}
MAIL_TEXT_PARTS = {
    ("subject", "nl"): _("onderwerp in het Nederlands"),
    ("body", "nl"): _("tekst in het Nederlands"),
    ("subject", "en"): _("onderwerp in het Engels"),
    ("body", "en"): _("tekst in het Engels"),
}


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = [
            "business_name",
            "legal_form",
            "address_line1",
            "address_line2",
            "postal_code",
            "city",
            "country",
            "kvk_number",
            "vat_number",
            "iban",
            "bic",
            "email",
            "phone",
            "website",
            "kor_enabled",
            "kor_text",
            "kor_limit_cents",
            "kor_warning_percent",
            "reverse_charge_text",
            "logo",
            "default_payment_terms_days",
            "invoice_number_format",
            "quote_number_format",
            "number_reset_yearly",
            "default_footer_text",
            "default_language",
            "currency",
            "smtp_provider",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "smtp_from_email",
            *(name for _kind, _part, _language, name in MAIL_TEXT_FIELDS),
        ]
        widgets = {
            "kor_text": forms.Textarea(attrs={"rows": 3}),
            "reverse_charge_text": forms.Textarea(attrs={"rows": 2}),
            "default_footer_text": forms.Textarea(attrs={"rows": 3}),
            # With JS, the mail fields hide while mailing is off (app.js).
            "smtp_provider": forms.Select(attrs={"data-shows-group": "smtp"}),
            **{
                name: forms.Textarea(attrs={"rows": 7})
                for _kind, part, _language, name in MAIL_TEXT_FIELDS
                if part == "body"
            },
        }

    # Not a model field: saved by save() to its own file (business.smtp).
    # Never filled in when the page is shown; empty keeps the saved one.
    smtp_password = forms.CharField(
        label=_("Wachtwoord"),
        required=False,
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    kor_limit_cents = EuroCentsField(
        label=_("KOR-grens"), min_value=Decimal("0.01"), max_value=Decimal("10000000")
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The logo as saved, before this form's data is put on the instance.
        self.old_logo = self.instance.logo
        # A suggestion in the field, not a stored default: nothing is saved
        # until the user saves the form, and they can change it freely.
        if not self.instance.kor_text:
            self.initial["kor_text"] = DEFAULT_KOR_TEXT
        # Likewise the mail texts: the standard text, placeholders and all,
        # to change rather than to write from nothing.
        for kind, part, language, name in MAIL_TEXT_FIELDS:
            if not getattr(self.instance, name):
                self.initial[name] = mail_texts.standard_text(kind, part, language)
            # "Factuur: onderwerp in het Nederlands" in the error summary;
            # on the screen the block already says which kind it is.
            if name in self.fields:
                self.fields[name].label = format_lazy(
                    "{}: {}", MAIL_TEXT_TITLES[kind], MAIL_TEXT_PARTS[part, language]
                )
        # The same words as the switch on the screen.
        if "number_reset_yearly" in self.fields:
            self.fields["number_reset_yearly"].label = _("Nummering elk jaar opnieuw beginnen")

    def _clean_number_format(self, name):
        """A format must fill in with a year and a sequence number, and
        contain the sequence number — caught here instead of at the first
        issue, where format_number() would raise."""
        value = self.cleaned_data[name]
        if "{seq" not in value:
            raise ValidationError(_("Zet {seq} in het formaat, voor het volgnummer."))
        try:
            format_number(value, year=2026, seq=1)
        except (KeyError, IndexError, ValueError):
            raise ValidationError(
                _(
                    "Dit formaat klopt niet. Gebruik {year} voor het jaar "
                    "en {seq:04d} voor het volgnummer."
                )
            ) from None
        return value

    def clean_invoice_number_format(self):
        return self._clean_number_format("invoice_number_format")

    def clean_quote_number_format(self):
        return self._clean_number_format("quote_number_format")

    def clean(self):
        cleaned = super().clean()
        # Without a yearly reset there is no year for {year}: every number
        # would contain the word "None" (see Settings.number_reset_yearly).
        # A part of the form without that switch (SettingsPartForm) checks
        # against the saved one.
        has_switch = "number_reset_yearly" in self.fields
        reset_yearly = (
            cleaned.get("number_reset_yearly") if has_switch else self.instance.number_reset_yearly
        )
        if not reset_yearly:
            # "Zet dat aan" only where the switch is on the screen.
            if has_switch:
                message = _(
                    "Met {year} in het formaat moet de nummering elk jaar opnieuw beginnen. "
                    "Zet dat aan, of haal {year} weg."
                )
            else:
                message = _(
                    "Met {year} in het formaat moet de nummering elk jaar opnieuw beginnen. "
                    "Haal {year} weg."
                )
            for name in ("invoice_number_format", "quote_number_format"):
                if "{year" in cleaned.get(name, ""):
                    self.add_error(name, message)
        self._clean_smtp(cleaned)
        self._clean_mail_texts(cleaned)
        return cleaned

    def _clean_mail_texts(self, cleaned):
        """Only placeholders that exist for that kind of document: a typo
        would otherwise end up in the customer's mail as {klant}."""
        for kind, _part, _language, name in MAIL_TEXT_FIELDS:
            unknown = mail_texts.unknown_placeholders(cleaned.get(name, ""), kind)
            if unknown:
                known = [
                    f"{{{placeholder}}}"
                    for placeholder, kinds in mail_texts.PLACEHOLDERS.items()
                    if kind in kinds
                ]
                self.add_error(
                    name,
                    _("Huismus kent %(unknown)s niet. Je kunt gebruiken: %(known)s.")
                    % {"unknown": ", ".join(unknown), "known": ", ".join(known)},
                )

    def _clean_smtp(self, cleaned):
        """ "Gmail" fills in its own server; "Anders" needs one typed in."""
        provider = cleaned.get("smtp_provider")
        if provider == "gmail":
            cleaned.update(smtp.GMAIL)
            # Google shows an app password in groups of four; the spaces
            # are not part of it.
            cleaned["smtp_password"] = "".join(cleaned.get("smtp_password", "").split())
            if not cleaned.get("smtp_username"):
                self.add_error("smtp_username", _("Vul je Gmail-adres in."))
        elif provider == "other":
            for name in ("smtp_host", "smtp_port"):
                if not cleaned.get(name):
                    self.add_error(name, _("Vul dit in om via je eigen mailserver te mailen."))

    def save(self, commit=True):
        # One logo file at a time: drop the old one when it's replaced (an
        # UploadedFile) or removed (False: "Logo verwijderen" was ticked),
        # so a Pi's SD card doesn't slowly fill up with orphaned logos.
        new_logo = self.cleaned_data.get("logo")
        if (isinstance(new_logo, UploadedFile) or new_logo is False) and self.old_logo:
            self.old_logo.delete(save=False)
        instance = super().save(commit)
        # "Niet ingesteld" switches mailing off and forgets the password.
        # Only where mailing is part of the form (not in SettingsPartForm).
        if "smtp_provider" in self.fields:
            if not instance.smtp_provider:
                smtp.set_password("")
            elif self.cleaned_data["smtp_password"]:
                smtp.set_password(self.cleaned_data["smtp_password"])
        return instance

    def clean_logo(self):
        logo = self.cleaned_data.get("logo")
        # A newly uploaded file arrives here as an UploadedFile; leaving an
        # unchanged field instead returns the existing FieldFile, which has
        # already been validated and has nothing new to sanitize.
        if isinstance(logo, UploadedFile):
            validate_and_sanitize_logo(logo)
        return logo


class SettingsPartForm(SettingsForm):
    """A few fields of the settings page, with its validation: a step of
    the step-by-step start (core.onboarding) or the import's settings block
    (imports.forms). Only the fields named; the ones SettingsForm declares
    itself (mail password, KOR limit) too. The rest keep their saved values."""

    def __init__(self, *args, fields, **kwargs):
        super().__init__(*args, **kwargs)
        for name in list(self.fields):
            if name not in fields:
                del self.fields[name]
