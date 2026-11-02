# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The field messages every form shows, in place of Django's own.

Django says "Dit veld is verplicht." and "Zorg ervoor dat deze waarde
hoogstens 8 karakters bevat (het zijn er nu 9)."; Huismus says what to do,
short (docs/schrijfwijzer.md; huismus-intern/besluiten.md, 2026-11-01,
"Teksten in Arnes stem, deel 3"). A form that sets its own message for a
field (the amount, the quantity of a line) still wins. On purpose this
also reaches Django's own forms (the password form, the admin).

`apply()` changes Django's class-level defaults. Fields copy those messages
when they are created, so it runs when huismus/core/apps.py is imported,
before any form module is imported (tests/core/test_form_messages.py checks forms
from several apps, and one of Django's own).
"""

from django import forms
from django.core import validators
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext_lazy

FILL_THIS_IN = _("Vul dit in.")
ENTER_A_DATE = _("Vul een datum in.")
ENTER_A_NUMBER = _("Vul een getal in.")
# The same sentence as on the mail form; Django fills in %(value)s.
NOT_AN_EMAIL_ADDRESS = _("“%(value)s” is geen e-mailadres. Kijk na of je het goed typte.")


def apply():
    forms.Field.default_error_messages["required"] = FILL_THIS_IN
    forms.DateField.default_error_messages["invalid"] = ENTER_A_DATE
    forms.IntegerField.default_error_messages["invalid"] = ENTER_A_NUMBER
    forms.DecimalField.default_error_messages["invalid"] = ENTER_A_NUMBER
    forms.FloatField.default_error_messages["invalid"] = ENTER_A_NUMBER
    forms.FileField.default_error_messages["empty"] = _(
        "Dit bestand is leeg. Kies een ander bestand."
    )
    # Validators read `message` from the class unless one is passed in, so
    # this also reaches the instances Django made at import time
    # (validate_email) and the ones model fields make (max_length, the 0 of
    # a PositiveIntegerField).
    validators.EmailValidator.message = NOT_AN_EMAIL_ADDRESS
    validators.MinValueValidator.message = _("Vul %(limit_value)s of meer in.")
    validators.MaxValueValidator.message = _("Vul %(limit_value)s of minder in.")
    validators.MaxLengthValidator.message = ngettext_lazy(
        "Dit mag hoogstens %(limit_value)d teken zijn. Nu zijn het er %(show_value)d.",
        "Dit mag hoogstens %(limit_value)d tekens zijn. Nu zijn het er %(show_value)d.",
        "limit_value",
    )
