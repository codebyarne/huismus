# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The step-by-step start (/welkom/, SPEC.md M13): the settings needed to
send a first invoice, a few at a time. Each step is a part of the settings
page (business.forms.SettingsPartForm), with its validation; nothing here
is stored apart from Settings itself."""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Step:
    slug: str
    title: str
    intro: str
    fields: tuple[str, ...]


STEPS = (
    Step(
        "bedrijf",
        _("Bedrijf"),
        _("Dit komt op elke factuur en offerte."),
        (
            "business_name",
            "legal_form",
            "address_line1",
            "postal_code",
            "city",
            "country",
            "kvk_number",
            "vat_number",
            "iban",
            "email",
            "phone",
            "website",
        ),
    ),
    Step(
        "kor",
        _("KOR"),
        _("Gebruik je de kleineondernemersregeling? Dan komt jouw KOR-tekst onder elke factuur."),
        ("kor_enabled", "kor_text", "kor_limit_cents", "kor_warning_percent"),
    ),
    Step(
        "facturen",
        _("Facturen"),
        _(
            "Je betalingstermijn en hoe Huismus je facturen en offertes nummert. "
            "Meestal is de standaard goed."
        ),
        ("default_payment_terms_days", "invoice_number_format", "quote_number_format"),
    ),
    Step(
        "logo",
        _("Logo"),
        _("Je logo komt bovenaan je facturen en offertes. Je kunt het ook later toevoegen."),
        ("logo",),
    ),
)
