# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile
from django.db import transaction
from django.utils.text import format_lazy
from django.utils.translation import gettext_lazy as _

from huismus.core import profile as profile_axes
from huismus.core.forms import EuroCentsField
from huismus.core.profile import LEGAL_ENTITY_CHOICES
from huismus.documents import mail_texts
from huismus.documents.numbering import (
    NumberingError,
    check_next_sequence_number,
    format_number,
    next_sequence_number,
    next_sequence_number_is_fixed,
    set_next_sequence_number,
    year_if_issued_today,
)

from . import smtp
from .legal_entity import suggestion
from .logo import validate_and_sanitize_logo
from .models import Settings

CHARGES_VAT, USES_KOR, NO_VAT_OTHER = "ja", "kor", "anders"
VAT_CHOICES = [
    (CHARGES_VAT, _("Ja")),
    (USES_KOR, _("Nee, ik gebruik de KOR")),
    (NO_VAT_OTHER, _("Nee, om een andere reden")),
]


def vat_choice_of(settings) -> str:
    if settings.kor_enabled:
        return USES_KOR
    return NO_VAT_OTHER if settings.vat_exempt else CHARGES_VAT


DEFAULT_KOR_TEXT = _(
    "Vrijgesteld van btw op grond van de kleineondernemersregeling (KOR). "
    "Er is geen btw in rekening gebracht."
)


# Not settings fields: they set the sequence (documents.numbering). Per
# field the kind of sequence, label and help.
NEXT_NUMBER_FIELDS = {
    "next_invoice_number": (
        "invoice",
        _("Volgnummer van je volgende factuur"),
        _("Kom je uit een ander pakket? Vul het volgnummer in dat na je laatste factuur komt."),
    ),
    "next_quote_number": (
        "quote",
        _("Volgnummer van je volgende offerte"),
        _("Kom je uit een ander pakket? Vul het volgnummer in dat na je laatste offerte komt."),
    ),
}


# Instellingen → Mailen: a subject and a body per kind and language.
MAIL_TEXT_FIELDS = [
    (kind, part, language, mail_texts.field_name(kind, part, language))
    for kind in mail_texts.KINDS
    for language in mail_texts.LANGUAGES
    for part in ("subject", "body")
]
MAIL_TEXT_TITLES = {
    "invoice": _("Factuur"),
    "credit_note": _("Creditnota"),
    "quote": _("Offerte"),
    "reminder": _("Herinnering"),
}
MAIL_TEXT_PARTS = {
    ("subject", "nl"): _("onderwerp in het Nederlands"),
    ("body", "nl"): _("tekst in het Nederlands"),
    ("subject", "en"): _("onderwerp in het Engels"),
    ("body", "en"): _("tekst in het Engels"),
}


# Instellingen › Menu (#260): the checkbox per part, and why it stays
# on while the part has something in it (huismus-intern/besluiten.md,
# 2026-11-22, "Onderdelen verbergen").
PART_FIELDS = {
    "show_quotes": (profile_axes.QUOTES, _("Je hebt offertes, dus Offertes blijft in het menu.")),
    "show_expenses": (
        profile_axes.EXPENSES,
        _("Je hebt uitgaven of bonnetjes, dus Uitgaven blijft in het menu."),
    ),
    "show_bank": (
        profile_axes.BANK,
        _("Je hebt een bankafschrift ingelezen, dus Bank blijft in het menu."),
    ),
}


class SettingsForm(forms.ModelForm):
    class Meta:
        model = Settings
        fields = [
            "business_name",
            "legal_entity",
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
            "vat_exempt",
            "kor_text",
            "exempt_text",
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
            *PART_FIELDS,
        ]
        widgets = {
            "kor_text": forms.Textarea(attrs={"rows": 3}),
            "exempt_text": forms.Textarea(attrs={"rows": 3}),
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

    # Instellingen → Btw: one choice for the two switches kor_enabled and
    # vat_exempt (issue #53). Not a model field; clean() sets the two.
    vat_choice = forms.ChoiceField(
        label=_("Reken je btw op je facturen?"),
        choices=VAT_CHOICES,
        widget=forms.RadioSelect,
        required=False,
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
        self.initial["vat_choice"] = vat_choice_of(self.instance)
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
        # The legal form (#302): the choice, and the free text from before it.
        if "legal_entity" in self.fields:
            self.fields["legal_entity"].label = _("Rechtsvorm")
            self.fields["legal_entity"].choices = [("", _("Kies…")), *LEGAL_ENTITY_CHOICES]
        if "legal_form" in self.fields:
            self.fields["legal_form"].label = _("Rechtsvorm, zoals je hem eerder typte")
            self.fields["legal_form"].help_text = _(
                "Staat niet op je facturen. Maak het leeg als je het niet meer nodig hebt."
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
        self._clean_vat_choice(cleaned)
        self._clean_smtp(cleaned)
        self._clean_mail_texts(cleaned)
        return cleaned

    def _clean_vat_choice(self, cleaned):
        if "vat_choice" not in self.fields:
            return
        # On the instance, not in cleaned: the two switches are not fields of
        # the page (Instellingen → Btw names vat_choice, not them, and
        # SettingsPartForm drops every field a page doesn't name), so the
        # ModelForm would not set them. The model's own clean() then checks
        # the result. Without an answer (an old form) the choice stays.
        choice = cleaned.get("vat_choice") or vat_choice_of(self.instance)
        self.instance.kor_enabled = choice == USES_KOR
        self.instance.vat_exempt = choice == NO_VAT_OTHER

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
        # The free text from before the choice (#302): only while it holds
        # text, so that nobody loses what they typed. Emptied and saved, it
        # goes.
        if "legal_form" in self.fields and not self.instance.legal_form:
            del self.fields["legal_form"]
        # No choice yet: preselect what the old text or card answer
        # suggests. A suggestion, not a saved value.
        self.legal_entity_suggested = ""
        if "legal_entity" in self.fields and not self.is_bound:
            self.legal_entity_suggested = suggestion(self.instance)
            if self.legal_entity_suggested:
                self.initial["legal_entity"] = self.legal_entity_suggested
                self.fields["legal_entity"].help_text = _(
                    "Voorstel op basis van wat je eerder invulde. Klopt het, sla dan op."
                )
        # A part with something in it stays in the menu: its checkbox shows
        # on and can't be changed, with the reason under it. parts_kept holds
        # what was saved, which may be off: clean() saves that again instead
        # of the "on" on the screen, so the part goes once it is empty.
        self.parts_kept = {}
        in_use = None
        for name, (part, reason) in PART_FIELDS.items():
            if name not in self.fields:
                continue
            if in_use is None:
                in_use = profile_axes.profile(self.instance).parts_in_use
            if part in in_use:
                self.parts_kept[name] = getattr(self.instance, name)
                self.fields[name].disabled = True
                self.fields[name].help_text = reason
                self.initial[name] = True
        if "show_expenses" in self.fields and "show_expenses" not in self.parts_kept:
            self.fields["show_expenses"].help_text = _("Met je bonnetjes en categorieën.")
        # The next number by hand (issue #141), where the fields name it
        # (Facturen en nummering, the start's Facturen step), and only for a
        # kind Huismus never gave a number yet (invariant 3).
        year = year_if_issued_today(self.instance.number_reset_yearly)
        self.fixed_sequences = {}
        for name, (kind, label, help_text) in NEXT_NUMBER_FIELDS.items():
            if name not in fields:
                continue
            self.fixed_sequences[kind] = next_sequence_number_is_fixed(kind)
            if not self.fixed_sequences[kind]:
                self.fields[name] = forms.IntegerField(
                    label=label,
                    help_text=help_text,
                    min_value=1,
                    # Empty keeps the number as it is.
                    required=False,
                    initial=next_sequence_number(kind, year=year),
                )

    def _next_numbers(self):
        """(kind, format, year, value) per next-number field in the form,
        from what the form saves: the number format and yearly reset may
        change in the same save."""
        reset_yearly = self.cleaned_data.get(
            "number_reset_yearly", self.instance.number_reset_yearly
        )
        year = year_if_issued_today(reset_yearly)
        for name, (kind, _label, _help) in NEXT_NUMBER_FIELDS.items():
            value = self.cleaned_data.get(name)
            template = self.cleaned_data.get(f"{kind}_number_format") or getattr(
                self.instance, f"{kind}_number_format"
            )
            if name in self.fields and value is not None:
                yield name, kind, template, year, value

    def clean(self):
        cleaned = super().clean()
        # A kept part saves what was saved, never the "on" it shows.
        cleaned.update(self.parts_kept)
        if not self.errors:
            for name, kind, template, year, value in self._next_numbers():
                # Unchanged is not a change: no checks, so it never stops
                # the rest of the form from saving.
                if value == next_sequence_number(kind, year=year):
                    continue
                try:
                    check_next_sequence_number(kind, template, year=year, value=value)
                except NumberingError as error:
                    self.add_error(name, str(error))
        return cleaned

    def save(self, commit=True):
        """With the next numbers, in one transaction: a refusal (an invoice
        issued since the check in clean()) leaves the settings unsaved too.
        Raises NumberingError then; the view shows it."""
        with transaction.atomic():
            instance = super().save(commit)
            for _name, kind, template, year, value in self._next_numbers():
                set_next_sequence_number(kind, template, year=year, value=value)
        return instance
