# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The step-by-step start (/welkom/, SPEC.md M13): the settings needed to
send a first invoice, a few at a time. Each step is a part of the settings
page (business.forms.SettingsPartForm), with its validation; nothing here
is stored apart from Settings itself.

The step Je werk (issue #259) asks three questions and decides which steps
come after it: KOR only under the KOR, Btw verlegd only without it and with
a "ja". What no setting holds ("Weet ik nog niet", a "ja" for btw verlegd)
travels in the address for this round only (Round), never in the database."""

from dataclasses import dataclass
from urllib.parse import urlencode

from django import forms
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from huismus.business.forms import DEFAULT_KOR_TEXT
from huismus.business.models import Settings


@dataclass(frozen=True)
class Step:
    slug: str
    title: str
    intro: str
    fields: tuple[str, ...]
    # The name in the step bar, where the title doesn't fit.
    short: str = ""

    @property
    def label(self):
        return self.short or self.title


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
    # Its own form (WorkForm), not a part of the settings form.
    Step(
        "werk",
        _("Je werk"),
        _(
            "Een paar vragen, zodat je alleen ziet wat bij jou hoort. "
            "Je past het later aan in Instellingen."
        ),
        ("kor_enabled", "default_language"),
    ),
    Step(
        "kor",
        _("Kleineondernemersregeling (KOR)"),
        _("Jouw KOR-tekst komt onder elke factuur."),
        ("kor_text", "kor_limit_cents", "kor_warning_percent"),
        short=_("KOR"),
    ),
    Step(
        "verlegd",
        _("Btw verlegd"),
        _(
            "Deze tekst komt onder elke factuur met een regel “verlegd”. "
            "Je kunt hem ook leeg laten."
        ),
        ("reverse_charge_text",),
    ),
    Step(
        "facturen",
        _("Facturen"),
        _(
            "Je betalingstermijn en hoe Huismus je facturen en offertes nummert. "
            "Meestal is de standaard goed."
        ),
        (
            "default_payment_terms_days",
            "invoice_number_format",
            "quote_number_format",
            "next_invoice_number",
            "next_quote_number",
        ),
    ),
    Step(
        "logo",
        _("Logo"),
        _("Je logo komt bovenaan je facturen en offertes. Je kunt het ook later toevoegen."),
        ("logo",),
    ),
)

BY_SLUG = {step.slug: step for step in STEPS}

VAT_YES, VAT_KOR, VAT_LATER = "ja", "kor", "later"
REVERSE_NO = "nee"
REVERSE_PLACES = ("nl", "eu", "buiten-eu")


@dataclass(frozen=True)
class Round:
    """The answers of Je werk that no setting holds, for this round of the
    wizard only: they go along in the address (?kor=later&verlegd=nl)."""

    kor_later: bool = False
    # Where the btw is reverse-charged ("nl", "eu", "buiten-eu"), or "".
    reverse_charge: str = ""

    @classmethod
    def from_query(cls, query) -> "Round":
        reverse_charge = query.get("verlegd", "")
        if reverse_charge not in REVERSE_PLACES:
            reverse_charge = ""
        return cls(query.get("kor") == "later", reverse_charge)

    def query(self) -> str:
        params = {}
        if self.kor_later:
            params["kor"] = "later"
        if self.reverse_charge:
            params["verlegd"] = self.reverse_charge
        return f"?{urlencode(params)}" if params else ""

    def url(self, slug: str) -> str:
        if slug == "klaar":
            return reverse("onboarding_done") + self.query()
        return reverse("onboarding", args=[slug]) + self.query()


def steps_for(settings: Settings, current: Round) -> list[Step]:
    """The steps this user gets: KOR only under the KOR; Btw verlegd only
    without it and after a "ja" (a text already there stays, but doesn't
    bring the step: huismus-intern/besluiten.md, 2026-11-21).

    The round's answers live only in the address, on purpose (nothing about
    them is stored): open a step without them, from the address bar or an
    old link, and Btw verlegd and the KOR line on the done page are gone,
    while everything already saved stays."""

    def shown(step: Step) -> bool:
        if step.slug == "kor":
            return settings.kor_enabled
        if step.slug == "verlegd":
            return not settings.kor_enabled and bool(current.reverse_charge)
        return True

    return [step for step in STEPS if shown(step)]


class WorkForm(forms.Form):
    """Je werk: three choices, no free fields. Only kor_enabled (with the
    settings page's suggestion for the KOR text) and default_language are
    saved; the answer about btw verlegd only decides the next step."""

    vat = forms.ChoiceField(
        label=_("Reken je btw op je facturen?"),
        choices=[
            (VAT_YES, _("Ja")),
            (VAT_KOR, _("Nee, ik gebruik de KOR")),
            (VAT_LATER, _("Weet ik nog niet")),
        ],
        widget=forms.RadioSelect,
    )
    reverse_charge = forms.ChoiceField(
        label=_("Heb je klanten waarbij de btw verlegd wordt?"),
        choices=[
            (REVERSE_NO, _("Nee")),
            (REVERSE_PLACES[0], _("Ja, in Nederland")),
            (REVERSE_PLACES[1], _("Ja, in een ander EU-land")),
            (REVERSE_PLACES[2], _("Ja, buiten de EU")),
        ],
        widget=forms.RadioSelect,
        # Required unless the KOR is chosen (clean).
        required=False,
    )
    default_language = forms.ChoiceField(
        label=_("In welke taal maak je je facturen meestal?"),
        # In the app's language, unlike the settings page's fixed names.
        choices=[("nl", _("Nederlands")), ("en", _("Engels"))],
        widget=forms.RadioSelect,
    )

    @classmethod
    def from_settings(cls, settings: Settings, current: Round) -> "WorkForm":
        """The current state as the answer: nothing else is stored."""
        if settings.kor_enabled:
            vat = VAT_KOR
        else:
            vat = VAT_LATER if current.kor_later else VAT_YES
        if current.reverse_charge:
            reverse_charge = current.reverse_charge
        elif settings.reverse_charge_text.strip():
            # There is a text, but nothing says where: no guess. Nothing is
            # ticked, and clean() asks for an answer.
            reverse_charge = None
        else:
            reverse_charge = REVERSE_NO
        return cls(
            initial={
                "vat": vat,
                "reverse_charge": reverse_charge,
                "default_language": settings.default_language,
            }
        )

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("vat") not in (None, VAT_KOR) and not cleaned.get("reverse_charge"):
            self.add_error("reverse_charge", _("Kies een antwoord."))
        return cleaned

    def save(self, settings: Settings) -> Round:
        """Save the settings; return what the rest of this round needs."""
        vat = self.cleaned_data["vat"]
        settings.kor_enabled = vat == VAT_KOR
        if settings.kor_enabled and not settings.kor_text.strip():
            # The model wants a text while the KOR is on: the same
            # suggestion as the settings page, to change in the KOR step.
            settings.kor_text = str(DEFAULT_KOR_TEXT)
        settings.default_language = self.cleaned_data["default_language"]
        settings.save()
        # Under the KOR, and with "Nee", there is no step Btw verlegd.
        place = ""
        reverse_charge = self.cleaned_data.get("reverse_charge")
        if vat != VAT_KOR and reverse_charge in REVERSE_PLACES:
            place = reverse_charge
        return Round(kor_later=vat == VAT_LATER, reverse_charge=place)
