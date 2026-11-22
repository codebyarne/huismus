# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The situation someone is in, along a few axes (#284;
huismus-intern/product/profiel-en-functies.md, section 2). Menu, wizard and
feedback ask profile() instead of each reading the settings themselves, so
they always say the same.

Never stored: profile() derives it every time from the settings and the
data, so it can't get out of step with them. The axes that look at data
query only when asked; the feedback only reads what the settings say.

The values are those of the model (kor, btw, nl, eu, offertes, ...): they
go to the feedback form as they are (#285).
"""

from dataclasses import dataclass
from functools import cached_property

# Btw
KOR = "kor"
VAT = "btw"
NO_VAT = "geen_btw"

# Klanten
NL = "nl"
EU = "eu"
OUTSIDE_EU = "buiten_eu"

# Werk: the parts with a place of their own in the menu.
QUOTES = "offertes"
EXPENSES = "uitgaven"
BANK = "bank"

# Herkomst (rompslomp comes with #119)
NEW = "nieuw"
MONEYBIRD = "moneybird"
OTHER = "ander"


@dataclass(frozen=True)
class Profile:
    settings: object  # huismus.business.models.Settings

    @property
    def vat(self) -> str:
        """kor, btw or geen_btw (#53). The step-by-step start keeps no
        answers, so btw is also "not chosen yet"."""
        if self.settings.kor_enabled:
            return KOR
        if self.settings.vat_exempt:
            return NO_VAT
        return VAT

    @property
    def reverse_charge_text(self) -> bool:
        """Whether there is a text for reverse-charge invoices (never the text)."""
        return bool(self.settings.reverse_charge_text.strip())

    @property
    def invoice_language(self) -> str:
        return "en" if self.settings.default_language == "en" else "nl"

    @cached_property
    def customers(self) -> frozenset[str]:
        """Where your customers are: nl, eu, buiten_eu, more at once. From
        the country of each customer, archived ones too, and the country on
        every issued invoice or credit note with a reverse-charged line
        (a draft has no country of its own yet). A customer without a
        country, or no customers at all: nl."""
        from huismus.contacts.models import Contact
        from huismus.documents.models import DocumentLine
        from huismus.reports.vat_return import EU_COUNTRIES

        countries = set(Contact.objects.values_list("country", flat=True).distinct())
        for snapshot in (
            DocumentLine.objects.filter(reverse_charge=True, document__status="issued")
            .values_list("document__contact_snapshot", flat=True)
            .distinct()
        ):
            countries.add((snapshot or {}).get("country") or "")

        def where(country: str) -> str:
            country = country.strip().upper()
            if country in ("", "NL"):
                return NL
            return EU if country in EU_COUNTRIES else OUTSIDE_EU

        return frozenset(map(where, countries)) or frozenset({NL})

    @cached_property
    def parts_in_use(self) -> frozenset[str]:
        """The parts with data in them. Until the choice per part (#260)
        exists, every part stays in the menu whatever this says."""
        from huismus.bank.models import BankStatement
        from huismus.documents.models import Document
        from huismus.expenses.models import Expense

        found = {
            QUOTES: Document.objects.filter(kind="quote").exists(),
            EXPENSES: Expense.objects.exists(),
            BANK: BankStatement.objects.exists(),
        }
        return frozenset(part for part, has_data in found.items() if has_data)

    @cached_property
    def origin(self) -> str:
        """Where the data came from: moneybird once a Moneybird import went
        through, ander after any other import (CSV), else nieuw. A dry run
        doesn't count."""
        from huismus.imports.models import ImportRun

        sources = set(ImportRun.objects.filter(committed=True).values_list("source", flat=True))
        if MONEYBIRD in sources:
            return MONEYBIRD
        return OTHER if sources else NEW


def profile(settings=None) -> Profile:
    """The profile of this installation. `settings`: a Settings to read
    instead of the stored one (an unsaved one in a test, or the one a view
    already loaded)."""
    if settings is None:
        # Here, not at the top: business.models imports core.feedback, which imports this.
        from huismus.business.models import Settings

        settings = Settings.load()
    return Profile(settings)
