# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from huismus.business.forms import SettingsForm, SettingsPartForm

# The settings an export can fill in (imports.settings_proposal), in the
# order the dry run shows them.
PROPOSABLE_FIELDS = [
    "business_name",
    "address_line1",
    "address_line2",
    "postal_code",
    "city",
    "country",
    "email",
    "phone",
    "kvk_number",
    "vat_number",
    "iban",
    "bic",
    "default_payment_terms_days",
    "invoice_number_format",
    "quote_number_format",
    "number_reset_yearly",
]


class ImportSettingsForm(SettingsPartForm):
    """The dry run's settings block. A part of the settings page, with its
    validation (IBAN, KvK, number formats, {year} and the yearly reset) —
    what the user confirms here is what "Nu echt importeren" saves."""

    prefix = "settings"

    class Meta(SettingsForm.Meta):
        fields = PROPOSABLE_FIELDS

    def __init__(self, *args, **kwargs):
        super().__init__(*args, fields=PROPOSABLE_FIELDS, **kwargs)


def settings_form_for(settings, proposal_values: dict, data=None) -> ImportSettingsForm:
    """Current settings with the export's proposal over them."""
    initial = {name: proposal_values[name] for name in PROPOSABLE_FIELDS if name in proposal_values}
    return ImportSettingsForm(data, instance=settings, initial=initial)


def differing_current_values(settings, proposal_values: dict) -> dict:
    """field -> the current value, where there is one and the proposal
    differs: the dry run shows it next to the field."""
    differing = {}
    for name in PROPOSABLE_FIELDS:
        current = getattr(settings, name)
        if isinstance(current, bool):
            continue  # a switch shows its own state
        if (
            name in proposal_values
            and current not in ("", None)
            and current != proposal_values[name]
        ):
            differing[name] = current
    return differing
