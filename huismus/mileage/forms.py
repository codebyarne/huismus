# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from huismus.core.forms import HTML5DateInput

from .models import MAX_KM, Trip
from .trips import TooPrecise, UnclearDistance, parse_distance

# How many places the fields Van and Naar offer from earlier trips.
PLACES_OFFERED = 30


class DistanceField(forms.CharField):
    """Kilometers as "12", "12,5" or "12.5" (mileage.trips.parse_distance),
    returned as a Decimal with one decimal."""

    def __init__(self, **kwargs):
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal"}))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        # A stored Decimal ("12.0") in Dutch notation, without ",0": "12", "12,5".
        if hasattr(value, "to_integral_value"):
            if value == value.to_integral_value():
                return str(int(value))
            return format(value, "f").replace(".", ",")
        return value

    def to_python(self, value):
        text = super().to_python(value)
        if not text:
            return None
        try:
            km = parse_distance(text)
        except TooPrecise:
            raise ValidationError(
                _("Hoogstens één cijfer achter de komma."), code="precise"
            ) from None
        except UnclearDistance:
            raise ValidationError(
                _("Vul de kilometers in, bijvoorbeeld 12,5."), code="unclear"
            ) from None
        if km <= 0:
            raise ValidationError(_("Vul meer dan 0 km in."), code="zero")
        if km > MAX_KM:
            raise ValidationError(_("Eén rit kan hoogstens 2.000 km zijn."), code="too_far")
        return km


class TripForm(forms.ModelForm):
    """The quick form on Kilometers and the page Rit wijzigen. All five
    fields are required: a trip with only kilometers says nothing later
    (product-owner agent 2026-11-28)."""

    distance_km = DistanceField(
        label=_("Kilometers"),
        help_text=_("Voor de hele rit, bijvoorbeeld 12,5."),
        error_messages={"required": _("Vul de kilometers in, bijvoorbeeld 12,5.")},
    )

    class Meta:
        model = Trip
        fields = ["date", "origin", "destination", "purpose", "distance_km"]
        widgets = {
            "date": HTML5DateInput(),
            "origin": forms.TextInput(attrs={"list": "plaatsen", "autocomplete": "off"}),
            "destination": forms.TextInput(attrs={"list": "plaatsen", "autocomplete": "off"}),
        }
        labels = {
            "date": _("Datum"),
            "origin": _("Van"),
            "destination": _("Naar"),
            "purpose": _("Doel"),
        }
        error_messages = {
            "date": {"required": _("Vul een datum in.")},
            "origin": {"required": _("Vul in waar de rit begon.")},
            "destination": {"required": _("Vul in waar de rit naartoe ging.")},
            "purpose": {"required": _("Vul het doel van de rit in.")},
        }

    def clean_origin(self):
        return self.cleaned_data["origin"].strip()

    def clean_destination(self):
        return self.cleaned_data["destination"].strip()

    def clean_purpose(self):
        return self.cleaned_data["purpose"].strip()


def earlier_places() -> list[str]:
    """The places of Van and Naar of earlier trips, newest first, each once,
    at most PLACES_OFFERED: what the fields offer (a datalist; without JS a
    plain text field)."""
    places: dict[str, None] = {}
    for origin, destination in Trip.objects.values_list("origin", "destination")[:200]:
        for place in (origin, destination):
            places.setdefault(place, None)
            if len(places) == PLACES_OFFERED:
                return list(places)
    return list(places)
