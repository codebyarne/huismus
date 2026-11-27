# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.forms import EuroCentsField, HTML5DateInput
from huismus.core.templatetags.money import euros

from .entries import UnclearHours, parse_hours
from .models import MAX_HOURS, TimeEntry


class HoursField(forms.CharField):
    """Hours as "1,5", "1.5" or "1:30" (hours.entries.parse_hours),
    returned as a Decimal with two decimals."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal"}))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        # A stored Decimal ("1.50") shown in Dutch notation, without
        # trailing zeros: "1,5", "2".
        if hasattr(value, "normalize"):
            text = format(value.normalize(), "f")
            return text.replace(".", ",")
        return value

    def to_python(self, value):
        text = super().to_python(value)
        if not text:
            return None
        try:
            hours = parse_hours(text)
        except UnclearHours:
            raise ValidationError(
                _("Vul je uren in, bijvoorbeeld 1,5 of 1:30."), code="unclear"
            ) from None
        if hours <= 0:
            raise ValidationError(_("Vul meer dan 0 uur in."), code="zero")
        if hours > MAX_HOURS:
            raise ValidationError(_("Eén regel kan hoogstens 24 uur zijn."), code="too_many")
        return hours


class TimeEntryForm(forms.ModelForm):
    """The quick form on Uren and the page Uren wijzigen. A new entry picks
    from the customers that aren't archived; an existing one keeps its own
    customer, archived or not (product-owner agent 2026-11-27)."""

    hours = HoursField(
        label=_("Uren"),
        help_text=_("Bijvoorbeeld 1,5 of 1:30."),
        error_messages={"required": _("Vul je uren in, bijvoorbeeld 1,5 of 1:30.")},
    )
    rate_cents = EuroCentsField(label=_("Tarief per uur"), required=False)

    class Meta:
        model = TimeEntry
        fields = ["date", "contact", "description", "hours", "rate_cents"]
        widgets = {"date": HTML5DateInput(), "description": forms.TextInput()}
        labels = {
            "date": _("Datum"),
            "contact": _("Klant"),
            "description": _("Omschrijving"),
        }
        error_messages = {"contact": {"required": _("Kies een klant.")}}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        contact = self.fields["contact"]
        contact.queryset = Contact.objects.filter(
            Q(archived=False) | Q(pk=self.instance.contact_id)
        )
        contact.empty_label = None
        contact.error_messages["invalid_choice"] = _("Kies een klant.")
        rate_help = _("Laat leeg voor uren die je niet factureert.")
        if not Settings.load().no_vat:
            rate_help = _("Zonder btw. Laat leeg voor uren die je niet factureert.")
        self.fields["rate_cents"].help_text = rate_help

    def clean_rate_cents(self):
        rate = self.cleaned_data.get("rate_cents")
        if rate is not None and rate < 0:
            raise ValidationError(_("Een tarief kan niet negatief zijn."), code="negative")
        return rate


def last_rates() -> dict[int, str]:
    """Per customer the rate of his newest entry, as the field shows it
    ("90,00"); a customer whose newest entry has no rate isn't in it. The
    quick form starts with it, and with JS a change of customer fills it
    in (app.js), so the browser never works out a rate itself."""
    # Newest first per customer, so the first rate seen of each is his
    # last one, also when that is None: hours without a rate then count as
    # his last, and the field starts empty.
    newest: dict[int, int | None] = {}
    newest_first = TimeEntry.objects.order_by("contact_id", "-date", "-id")
    for contact_id, rate in newest_first.values_list("contact_id", "rate_cents"):
        newest.setdefault(contact_id, rate)
    return {pk: euros(rate) for pk, rate in newest.items() if rate is not None}
