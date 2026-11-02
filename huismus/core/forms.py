# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import re

from django import forms
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

from huismus.core.templatetags.money import euros


class HTML5DateInput(forms.DateInput):
    """An `<input type="date">` needs its `value` attribute in ISO format
    (yyyy-mm-dd) to pre-populate — Django's plain DateInput instead
    formats a bound value using the active locale's DATE_INPUT_FORMATS
    (nl: d-m-Y), which the date input silently fails to parse, rendering
    empty rather than raising an error. Found by testing an actual edit
    of an existing record in a real browser, not by any test: every
    `forms.DateInput(attrs={"type": "date"})` in this codebase had this
    bug — editing a record with a date already set showed a blank date
    picker, even though the stored value was correct all along.
    """

    def __init__(self, attrs=None):
        super().__init__(attrs={"type": "date", **(attrs or {})}, format="%Y-%m-%d")


# The amounts EuroCentsField accepts (huismus-intern/besluiten.md, 2026-10-29). With a
# comma, the comma is the decimal separator and dots group thousands
# ("20.000,00"). Without one, a dot before 1 or 2 digits is a decimal point
# ("12.50", as the old number field took it) and dots before groups of 3
# are thousands ("1.500", but never "0.500": that is no way to write 500).
# Anything else is unclear and refused. No text fits two of the patterns,
# so the order they are tried in doesn't matter.
_DUTCH_AMOUNT = re.compile(r"-?(\d+|[1-9]\d{0,2}(\.\d{3})+),\d{1,2}")
_POINT_AMOUNT = re.compile(r"-?\d+(\.\d{1,2})?")
_THOUSANDS_AMOUNT = re.compile(r"-?[1-9]\d{0,2}(\.\d{3})+")


class EuroCentsField(forms.DecimalField):
    """A euro amount in a form, shown in Dutch notation ("20.000,00", like
    every amount elsewhere in the app) and returned as integer cents
    (SPEC.md principle 2: money is integer cents).

    Showing a raw cents integer in a form field would be a genuine
    correctness hazard, not just an ugly UI: a user typing "50" meaning
    fifty euros would silently create a 50-cent line instead. A text input,
    not type="number": a number input can't show "20.000,00".
    """

    default_error_messages = {"unclear": _("Vul een bedrag in, zoals 1.250,00.")}

    def __init__(self, **kwargs):
        kwargs.setdefault("decimal_places", 2)
        kwargs.setdefault("max_digits", 12)
        kwargs.setdefault("widget", forms.TextInput(attrs={"inputmode": "decimal"}))
        super().__init__(**kwargs)

    def prepare_value(self, value):
        if isinstance(value, int):
            return euros(value)
        return super().prepare_value(value)

    def clean(self, value):
        # Rewrite the amount as "1234.56" and let DecimalField's own pipeline
        # (required, max_digits, min/max) check that. Not in to_python():
        # that has to return a Decimal for DecimalField.validate(), which runs
        # after it; only clean()'s already-valid result becomes cents.
        euro_amount = super().clean(self._with_decimal_point(value))
        if euro_amount is None:
            return None
        return int((euro_amount * 100).to_integral_value())

    def _with_decimal_point(self, value):
        text = (value or "").strip()
        if not text:
            return text
        if _DUTCH_AMOUNT.fullmatch(text):
            return text.replace(".", "").replace(",", ".")
        if _POINT_AMOUNT.fullmatch(text):
            return text
        if _THOUSANDS_AMOUNT.fullmatch(text):
            return text.replace(".", "")
        raise ValidationError(self.error_messages["unclear"], code="unclear")
