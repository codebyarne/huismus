# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""profile(): the situation someone is in, derived from settings and data
and never stored (#284, huismus-intern/product/profiel-en-functies.md).
One test group per axis."""

import pytest

from huismus.bank.models import BankStatement
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.profile import profile
from huismus.documents.models import Document, DocumentLine
from huismus.expenses.models import Expense
from huismus.imports.models import ImportRun

# ---------- Btw ----------


@pytest.mark.parametrize(
    ("kor", "exempt", "expected"),
    [(True, False, "kor"), (False, False, "btw"), (False, True, "geen_btw")],
)
def test_vat_follows_the_settings(kor, exempt, expected):
    assert profile(Settings(kor_enabled=kor, vat_exempt=exempt)).vat == expected


def test_vat_reads_the_stored_settings_without_an_instance(db):
    Settings.objects.filter(pk=Settings.load().pk).update(kor_enabled=True)
    assert profile().vat == "kor"


def test_reverse_charge_text_and_invoice_language():
    with_text = profile(Settings(reverse_charge_text=" Btw verlegd ", default_language="en"))
    assert with_text.reverse_charge_text is True
    assert with_text.invoice_language == "en"
    without = profile(Settings(reverse_charge_text="  ", default_language="nl"))
    assert without.reverse_charge_text is False
    assert without.invoice_language == "nl"


# ---------- Klanten ----------


def test_without_customers_the_customers_are_in_the_netherlands(db):
    assert profile().customers == frozenset({"nl"})


@pytest.mark.parametrize(
    ("countries", "expected"),
    [
        (["NL"], {"nl"}),
        ([""], {"nl"}),
        (["NL", "DE"], {"nl", "eu"}),
        (["be", "US"], {"eu", "buiten_eu"}),
        (["GB"], {"buiten_eu"}),
    ],
)
def test_customers_follow_the_countries_of_your_customers(db, countries, expected):
    for country in countries:
        Contact.objects.create(company_name=f"Klant {country}", country=country)
    assert profile().customers == frozenset(expected)


def test_an_archived_customer_still_counts(db):
    Contact.objects.create(company_name="Oud", country="FR", archived=True)
    assert profile().customers == frozenset({"eu"})


def _invoice_with_reverse_charge(contact, snapshot_country, status="issued"):
    document = Document.objects.create(
        kind="invoice",
        contact=contact,
        issue_date="2026-01-01",
        contact_snapshot={"country": snapshot_country},
    )
    DocumentLine.objects.create(
        document=document, description="Werk", unit_price_cents=100, reverse_charge=True
    )
    # Straight to issued: only the country on it matters here, not how it got issued.
    Document.objects.filter(pk=document.pk).update(status=status)


def test_a_reverse_charged_line_counts_the_country_on_the_invoice(db):
    """The customer moved to the Netherlands since; the invoice says Germany."""
    contact = Contact.objects.create(company_name="Verhuisd", country="NL")
    _invoice_with_reverse_charge(contact, "DE")
    assert profile().customers == frozenset({"nl", "eu"})


def test_a_draft_with_a_reverse_charged_line_adds_no_country(db):
    contact = Contact.objects.create(company_name="Duits", country="DE")
    _invoice_with_reverse_charge(contact, "", status="draft")
    assert profile().customers == frozenset({"eu"})


# ---------- Werk ----------


def test_without_data_no_part_is_in_use(db):
    assert profile().parts_in_use == frozenset()


def test_a_quote_puts_quotes_in_use(db):
    contact = Contact.objects.create(company_name="Klant")
    Document.objects.create(kind="quote", contact=contact, issue_date="2026-01-01")
    assert profile().parts_in_use == frozenset({"offertes"})


def test_an_invoice_puts_no_part_in_use(db):
    contact = Contact.objects.create(company_name="Klant")
    Document.objects.create(kind="invoice", contact=contact, issue_date="2026-01-01")
    assert profile().parts_in_use == frozenset()


def test_an_expense_puts_expenses_in_use(db):
    Expense.objects.create(date="2026-01-01", amount_cents=1000)
    assert profile().parts_in_use == frozenset({"uitgaven"})


def test_a_bank_statement_puts_bank_in_use(db):
    BankStatement.objects.create(filename="afschrift.csv", sha256="0" * 64, format="csv")
    assert profile().parts_in_use == frozenset({"bank"})


# ---------- Herkomst ----------


def test_without_an_import_you_started_here(db):
    assert profile().origin == "nieuw"


def test_a_dry_run_is_no_origin(db):
    ImportRun.objects.create(source="moneybird", dry_run=True, committed=False)
    assert profile().origin == "nieuw"


@pytest.mark.parametrize(
    ("sources", "expected"),
    [
        (["moneybird"], "moneybird"),
        (["csv"], "ander"),
        (["csv", "moneybird"], "moneybird"),
        (["csv", "csv"], "ander"),
    ],
)
def test_origin_follows_the_imports_that_went_through(db, sources, expected):
    for source in sources:
        ImportRun.objects.create(source=source, dry_run=False, committed=True)
    assert profile().origin == expected


# ---------- Lazy ----------


def test_the_vat_axis_needs_no_database():
    """Feedback asks only what the settings say; the other axes query when asked."""
    assert profile(Settings(kor_enabled=True)).vat == "kor"
