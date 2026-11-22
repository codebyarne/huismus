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

# Rechtsvorm: the one axis that is stored (Settings.legal_entity, #302),
# because no setting or data says it. Empty: not chosen.
SOLE_PROPRIETOR = "eenmanszaak"
PARTNERSHIP = "vof"
PRIVATE_COMPANY = "bv"
FOUNDATION = "stichting"
ASSOCIATION = "vereniging"
OTHER_FORM = "anders"
LEGAL_FORMS = (SOLE_PROPRIETOR, PARTNERSHIP, PRIVATE_COMPANY, FOUNDATION, ASSOCIATION, OTHER_FORM)

# Herkomst (rompslomp comes with #119): ImportRun.source → origin. A new
# import source gets its own line here.
NEW = "nieuw"
MONEYBIRD = "moneybird"
OTHER = "ander"
ORIGIN_BY_SOURCE = {"moneybird": MONEYBIRD, "csv": OTHER}


class Profile:
    """Read it, don't keep it: the axes that look at data are worked out
    once per Profile, on first use."""

    def __init__(self, settings):
        self.settings = settings  # huismus.business.models.Settings

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
    def legal_form(self) -> str:
        """eenmanszaak, vof, bv, stichting, vereniging, anders, or "" when
        not chosen. Only the saved choice: never the suggestion
        (business.legal_entity), which counts only once someone saves it."""
        return self.settings.legal_entity

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

        # The country on the invoice too: a customer who moved since was
        # invoiced, reverse charged, where the invoice says.
        countries = list(Contact.objects.values_list("country", flat=True).distinct())
        snapshots = (
            DocumentLine.objects.filter(reverse_charge=True, document__status="issued")
            .values_list("document__contact_snapshot", flat=True)
            .distinct()
        )
        for snapshot in snapshots:
            countries.append((snapshot or {}).get("country") or "")

        found = set()
        for country in countries:
            country = country.strip().upper()
            if country in ("", "NL"):
                found.add(NL)
            elif country in EU_COUNTRIES:
                found.add(EU)
            else:
                found.add(OUTSIDE_EU)
        return frozenset(found or {NL})

    @cached_property
    def parts_in_use(self) -> frozenset[str]:
        """The parts with data in them. Until the choice per part (#260)
        exists, every part stays in the menu whatever this says."""
        from huismus.bank.models import BankStatement
        from huismus.documents.models import Document
        from huismus.expenses.models import Expense

        found = set()
        if Document.objects.filter(kind="quote").exists():
            found.add(QUOTES)
        if Expense.objects.exists():
            found.add(EXPENSES)
        if BankStatement.objects.exists():
            found.add(BANK)
        return frozenset(found)

    @cached_property
    def origin(self) -> str:
        """Where the data came from: moneybird once a Moneybird import went
        through, else ander after a CSV import, else nieuw. A dry run
        doesn't count."""
        from huismus.imports.models import ImportRun

        sources = ImportRun.objects.filter(committed=True).values_list("source", flat=True)
        origins = {ORIGIN_BY_SOURCE.get(source) for source in sources}
        for origin in (MONEYBIRD, OTHER):
            if origin in origins:
                return origin
        return NEW


def profile(settings=None) -> Profile:
    """The profile of this installation. `settings`: a Settings to read
    instead of the stored one (an unsaved one in a test, or the one a view
    already loaded)."""
    if settings is None:
        # Here, not at the top: business.models imports core.feedback, which imports this.
        from huismus.business.models import Settings

        settings = Settings.load()
    return Profile(settings)
