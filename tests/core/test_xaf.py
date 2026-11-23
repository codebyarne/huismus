# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The auditfile in the export (issue #123, SPEC.md M26, docs/auditfile.md):
valid against the Belastingdienst's own XSD, every transaction closes, and
its accounts add up to the cent to the year overview and the VAT return."""

import io
import zipfile
from collections import defaultdict
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from lxml import etree

from huismus.business.models import Settings
from huismus.core import export, xaf
from huismus.core.demo_history import FIRST_YEAR, LAST_YEAR, create_history
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.reopening import reopen
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory
from huismus.reports.periods import YEAR, Period
from huismus.reports.vat_return import compute_vat_return
from huismus.reports.year_overview import compute_year_overview

from .test_export import _business, _contact, _credit_note, _draft, _invoice  # noqa: F401

pytestmark = pytest.mark.django_db

XSD = Path(__file__).parents[1] / "fixtures" / "xaf" / "XmlAuditfileFinancieel4.0.xsd"
NS = {"x": xaf.NAMESPACE}


@pytest.fixture(scope="module")
def schema():
    return etree.XMLSchema(etree.parse(str(XSD)))


def _parse(year: int):
    return etree.fromstring(xaf.auditfile(year))


def _cents(text: str) -> int:
    return int(Decimal(text) * 100)


def _signed(line) -> int:
    """Debit positive, credit negative."""
    amount = _cents(line.findtext("x:amnt", namespaces=NS))
    return amount if line.findtext("x:amntTp", namespaces=NS) == "D" else -amount


def _balances(root) -> dict[str, int]:
    """The year's movement per account, debit positive."""
    totals = defaultdict(int)
    for line in root.iterfind(".//x:trLine", NS):
        totals[line.findtext("x:accID", namespaces=NS)] += _signed(line)
    return totals


def _opening(root) -> dict[str, int]:
    return {
        line.findtext("x:accID", namespaces=NS): _signed(line)
        for line in root.iterfind(".//x:obLine", NS)
    }


def _cost_accounts(root) -> list[str]:
    return [
        account.findtext("x:accID", namespaces=NS)
        for account in root.iterfind(".//x:ledgerAccount", NS)
        if account.findtext("x:accID", namespaces=NS).startswith("4")
    ]


def _set_no_vat(kor: bool):
    settings = Settings.load()
    settings.kor_enabled = kor
    settings.kor_text = "Vrijgesteld van btw (KOR)." if kor else ""
    settings.save()


def _a_year_of_everything():
    """2025: invoices at 21% and 9%, reverse charge to the Netherlands and
    to Germany, a credit note, a payment, and expenses at 21%, without a
    rate, and reverse charged from outside the EU."""
    customer = _contact(company_name="Klant BV", customer_number="K001", vat_number="NL1")
    german = _contact(company_name="Kunde GmbH", country="DE")
    first = _invoice(contact=customer, lines=((1, 100000, 2100), (2, 5000, 900)))
    _invoice(contact=customer, issue_date="2025-06-01", lines=((1, 30000, 0, True),))
    _invoice(contact=german, issue_date="2025-07-01", lines=((1, 40000, 0, True),))
    _credit_note(first, issue_date="2025-08-01")
    second = _invoice(contact=customer, issue_date="2025-09-01", lines=((3, 2500, 2100),))
    Payment.objects.create(document=second, paid_on=date(2025, 9, 20), amount_cents=5000)
    office = ExpenseCategory.objects.create(name="Kantoor")
    travel = ExpenseCategory.objects.create(name="Reizen")
    create_expense(
        [
            ExpenseLineInput("Papier", 1210, 210, office, "21"),
            ExpenseLineInput("Trein", 2000, None, travel),
            ExpenseLineInput("Software", 5000, 1050, office, "reverse_non_eu"),
        ],
        date="2025-02-03",
        supplier="Winkel",
    )
    create_expense([ExpenseLineInput("Zonder categorie", 999, 0, None, "0")], date="2025-11-11")


def test_the_auditfile_is_valid_against_the_official_xsd(schema):
    _a_year_of_everything()

    root = _parse(2025)

    assert schema.validate(root), schema.error_log


def test_every_transaction_closes_and_the_totals_add_up():
    _a_year_of_everything()

    root = _parse(2025)

    transactions = root.find(".//x:transactions", NS)
    lines = list(root.iterfind(".//x:trLine", NS))
    debit = sum(_signed(line) for line in lines if _signed(line) > 0)
    credit = -sum(_signed(line) for line in lines if _signed(line) < 0)
    assert int(transactions.findtext("x:linesCount", namespaces=NS)) == len(lines)
    assert _cents(transactions.findtext("x:totalDebit", namespaces=NS)) == debit
    assert _cents(transactions.findtext("x:totalCredit", namespaces=NS)) == credit
    for transaction in root.iterfind(".//x:transaction", NS):
        assert sum(_signed(line) for line in transaction.iterfind("x:trLine", NS)) == 0


@pytest.mark.parametrize("kor", [False, True])
def test_revenue_and_costs_are_the_year_overviews(kor):
    _a_year_of_everything()
    _set_no_vat(kor)

    root = _parse(2025)
    balances = _balances(root)
    overview = compute_year_overview(2025)

    revenue = -sum(cents for account, cents in balances.items() if account.startswith("8"))
    costs = sum(balances[account] for account in _cost_accounts(root))
    assert revenue == overview.revenue_cents
    assert costs == overview.expenses_cents
    assert balances.get(xaf.INPUT_VAT, 0) == (
        overview.input_vat_cents + (0 if kor else 1050)  # plus the reverse charged VAT
    )


def test_a_cost_account_per_category_named_after_it():
    _a_year_of_everything()

    root = _parse(2025)
    names = {
        account.findtext("x:accID", namespaces=NS): account.findtext("x:accDesc", namespaces=NS)
        for account in root.iterfind(".//x:ledgerAccount", NS)
    }
    balances = _balances(root)
    by_name = {names[account]: balances[account] for account in _cost_accounts(root)}

    overview = {c.name: c.amount_cents for c in compute_year_overview(2025).by_category}
    assert by_name["Kantoor"] == overview["Kantoor"] == 1000 + 5000
    assert by_name["Reizen"] == overview["Reizen"] == 2000
    assert by_name["Kosten zonder categorie"] == overview["Zonder categorie"] == 999


def test_vat_per_box_is_the_vat_returns():
    _a_year_of_everything()

    balances = _balances(_parse(2025))
    vat_return = compute_vat_return(Period(YEAR, 2025, 0, date(2026, 1, 1)))
    boxes = {box.code: box for box in vat_return.boxes}

    for code, revenue_account, tax_account in [
        ("1a", "8010", "1510"),
        ("1b", "8020", "1520"),
        ("1e", "8050", None),
        ("3b", "8080", None),
    ]:
        assert -balances.get(revenue_account, 0) == boxes[code].revenue_cents, code
        if tax_account:
            assert -balances.get(tax_account, 0) == boxes[code].tax_cents, code
    for code, tax_account in [("2a", "1530"), ("4a", "1540"), ("4b", "1550")]:
        assert -balances.get(tax_account, 0) == boxes[code].tax_cents, code
    assert balances[xaf.INPUT_VAT] == vat_return.input_vat_cents
    owed = -sum(balances.get(account, 0) for account in ("1510", "1520", "1530", "1540", "1550"))
    assert owed - balances[xaf.INPUT_VAT] == vat_return.balance_cents


def test_under_the_kor_no_vat_on_expenses_and_kor_invoices_have_no_box():
    _set_no_vat(True)
    issued = _invoice(lines=((1, 50000, 0),))
    assert issued.kor_text_snapshot
    create_expense([ExpenseLineInput("Papier", 1210, 210, None, "21")], date="2025-02-03")

    balances = _balances(_parse(2025))

    assert balances["8090"] == -50000
    assert balances["4999"] == 1210
    assert xaf.INPUT_VAT not in balances


def test_a_credit_note_turns_the_invoice_around():
    invoice = _invoice(lines=((1, 10000, 2100),))
    _credit_note(invoice)

    balances = _balances(_parse(2025))

    assert balances[xaf.DEBTORS] == 0
    assert balances["8010"] == 0
    assert balances["1510"] == 0


def test_an_import_without_vat_per_rate_goes_on_the_accounts_without_a_box():
    document = Document.objects.create(
        kind="invoice",
        status="draft",
        number="2025-0042",
        contact=_contact(),
        issue_date="2025-05-01",
        source="moneybird",
        external_id="42",
    )
    DocumentLine.objects.create(
        document=document, description="Werk", quantity=1, unit_price_cents=9000, tax_rate_bp=2100
    )
    Document.objects.filter(pk=document.pk).update(
        status="issued", subtotal_cents=9000, tax_cents=1891, total_cents=10891
    )

    balances = _balances(_parse(2025))

    assert balances[xaf.DEBTORS] == 10891
    assert balances["8090"] == -9000
    assert balances["1590"] == -1891


def test_payments_go_from_debtors_to_the_bank():
    invoice = _invoice(lines=((1, 10000, 2100),))
    Payment.objects.create(document=invoice, paid_on=date(2025, 4, 1), amount_cents=12100)

    balances = _balances(_parse(2025))

    assert balances[xaf.BANK] == 12100
    assert balances[xaf.DEBTORS] == 0


def test_the_opening_balance_is_what_was_open_on_january_first():
    customer = _contact()
    old = _invoice(contact=customer, issue_date="2024-11-01", lines=((1, 10000, 2100),))
    Payment.objects.create(document=old, paid_on=date(2024, 12, 1), amount_cents=2100)
    Payment.objects.create(document=old, paid_on=date(2025, 1, 15), amount_cents=10000)

    previous, current = _parse(2024), _parse(2025)

    assert _opening(current) == {xaf.DEBTORS: 10000, xaf.OPENING_SUSPENSE: -10000}
    assert _opening(previous) == {}
    # The opening is the end of the year before.
    assert _balances(previous)[xaf.DEBTORS] == 10000
    opening = current.find(".//x:openingBalance", NS)
    assert opening.findtext("x:totalDebit", namespaces=NS) == "100.00"
    assert opening.findtext("x:totalCredit", namespaces=NS) == "100.00"
    relation = current.find(".//x:customerSupplier", NS)
    assert relation.findtext("x:opBalDesc", namespaces=NS) == "100.00"
    assert relation.findtext("x:clBalDesc", namespaces=NS) == "0.00"


def test_drafts_and_reopened_documents_are_left_out():
    _draft(lines=((1, 99900, 2100),))
    reopen(_invoice(lines=((1, 77700, 2100),)))
    _invoice(lines=((1, 10000, 2100),))

    assert _balances(_parse(2025))[xaf.DEBTORS] == 12100


def test_customers_are_relations_and_the_supplier_is_in_the_description():
    _a_year_of_everything()

    root = _parse(2025)

    relations = {
        relation.findtext("x:custSupID", namespaces=NS): relation.findtext(
            "x:custSupName", namespaces=NS
        )
        for relation in root.iterfind(".//x:customerSupplier", NS)
    }
    assert "Klant BV" in relations.values()
    assert relations["K001"] == "Klant BV"
    descriptions = [
        transaction.findtext("x:desc", namespaces=NS)
        for transaction in root.iterfind(".//x:transaction", NS)
    ]
    assert any("Winkel" in text for text in descriptions)


def test_the_export_has_an_auditfile_per_year():
    _invoice(issue_date="2024-03-01")
    _invoice(issue_date="2025-03-01")

    def names(year):
        buffer = io.BytesIO()
        export.write_zip(buffer, year)
        return {n for n in zipfile.ZipFile(buffer).namelist() if n.endswith(".xaf")}

    assert names(2025) == {"auditfile-2025.xaf"}
    assert names(None) == {"auditfile-2024.xaf", "auditfile-2025.xaf"}


def test_nine_years_of_demo_data_are_valid_and_close(schema):
    create_history()

    for year in range(FIRST_YEAR, LAST_YEAR + 1):
        root = _parse(year)
        assert schema.validate(root), (year, schema.error_log)
        assert sum(_balances(root).values()) == 0
        assert sum(_opening(root).values()) == 0
        overview = compute_year_overview(year)
        revenue = -sum(c for a, c in _balances(root).items() if a.startswith("8"))
        assert revenue == overview.revenue_cents, year
