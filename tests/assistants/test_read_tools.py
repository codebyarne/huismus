# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The read actions of #273, part 1: Te doen, the year overview, the bank,
categories, a document's PDF and the settings. Each reads with the same
function as its page in the app, and changes nothing."""

import base64
import json

import pytest
from django.core.files.base import ContentFile
from django.utils import timezone

from huismus.assistants.tools import BY_NAME
from huismus.bank import reading
from huismus.bank import views as bank_views
from huismus.business import smtp
from huismus.core.dashboard import outstanding_invoices
from huismus.core.models import Attachment
from huismus.core.todo import current_todo
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine
from huismus.expenses.models import ExpenseCategory
from huismus.reports.year_overview import compute_year_overview

from ..bank.test_reading import _camt

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year
NEW_READ_TOOLS = (
    "get_year_overview",
    "list_bank",
    "list_categories",
    "get_document_pdf",
    "get_settings",
)


def _draft(customer, cents=51000, kind="invoice"):
    document = Document.objects.create(kind=kind, status="draft", contact=customer)
    DocumentLine.objects.create(
        document=document, description="Fotografie", quantity=1, unit_price_cents=cents
    )
    return document


@pytest.fixture
def full(mcp):
    """The whole answer of one tool: (result, its content list)."""

    def call(name, **arguments):
        result = mcp("tools/call", {"name": name, "arguments": arguments})["result"]
        return result, result["content"]

    return call


@pytest.mark.parametrize("name", NEW_READ_TOOLS)
def test_the_new_actions_only_read(name):
    """The assistant's app runs them without asking (huismus-intern/besluiten.md,
    2026-11-21): read-only, not destructive."""
    annotations = BY_NAME[name].definition()["annotations"]
    assert annotations["readOnlyHint"] is True
    assert annotations["destructiveHint"] is False


def test_titles_follow_the_default_language(mcp, business):
    titles = {tool["name"]: tool["title"] for tool in mcp("tools/list")["result"]["tools"]}
    assert titles["get_year_overview"] == "Jaaroverzicht bekijken"
    business.default_language = "en"
    business.save()
    titles = {tool["name"]: tool["title"] for tool in mcp("tools/list")["result"]["tools"]}
    assert titles["get_year_overview"] == "View year overview"
    assert titles["get_document_pdf"] == "Document PDF"


# --- Te doen ---


def test_the_overview_says_what_waits_as_te_doen_does(tool, business, customer):
    lines = [{"description": "Fotografie", "unit_price": "510"}]
    tool("create_draft", kind="invoice", contact_id=customer.pk, lines=lines)
    data, _text, _error = tool("get_overview")
    rows = current_todo(timezone.localdate(), outstanding_invoices()).items
    assert [row["title"] for row in data["to_do"]] == [str(row.title) for row in rows]
    [row] = data["to_do"]
    assert row["kind"] == "concept"
    assert row["title"] == "Je concept voor Bakkerij De Korrel staat klaar"
    assert row["detail"] == "€ 510,00 · nog niet verstuurd"
    assert row["path"].startswith("/facturen/")


def test_nothing_waits(tool, business):
    data, _text, _error = tool("get_overview")
    assert data["to_do"] == []


# --- The year overview ---


def test_the_year_overview_under_the_kor_has_gross_costs(tool, business, customer):
    issue(_draft(customer))
    tool("add_expense", date=f"{YEAR}-02-03", lines=[{"amount": "121"}])
    data, _text, is_error = tool("get_year_overview")
    assert not is_error
    overview = compute_year_overview(YEAR)
    assert overview.expenses_cents == 12100
    assert (data["revenue"], data["costs"], data["profit"]) == ("€ 510,00", "€ 121,00", "€ 389,00")
    assert data["costs_label"] == "Kosten"
    assert data["costs_without_vat"] is False
    assert "input_vat" not in data
    assert data["quarters"][0] == {
        "quarter": "Q1",
        "revenue": "€ 510,00" if timezone.localdate().month <= 3 else "€ 0,00",
        "costs": "€ 121,00",
        "profit": data["quarters"][0]["profit"],
    }
    assert data["costs_by_category"] == [{"category": "Zonder categorie", "amount": "€ 121,00"}]


def test_the_year_overview_without_the_kor_has_costs_without_vat(tool, business):
    business.kor_enabled = False
    business.save()
    _data, text, is_error = tool(
        "add_expense",
        date=f"{YEAR}-05-06",
        lines=[{"amount": "121", "vat_info": "21", "vat_rate": "21"}],
    )
    assert not is_error, text
    data, _text, _error = tool("get_year_overview", year=YEAR)
    assert data["costs_label"] == "Kosten zonder btw"
    assert data["costs_without_vat"] is True
    assert (data["costs"], data["input_vat"]) == ("€ 100,00", "€ 21,00")
    assert data["quarters"][1]["input_vat"] == "€ 21,00"


# --- The bank ---


def test_the_bank_as_its_page_shows_it(tool, business, customer):
    sure = issue(_draft(customer, 121000))
    likely = issue(_draft(customer, 60500))
    reading.read_statement(
        "nov.xml",
        _camt(
            ("1210.00", "Bakkerij De Korrel", f"Factuur {sure.number}"),
            ("700.00", "Bakkerij De Korrel", f"Factuur {likely.number}"),
            ("12.34", "Iemand", "iets", "NL02RABO0123456789"),
        ),
    )
    data, _text, is_error = tool("list_bank")
    assert not is_error
    to_do, unknown = bank_views.to_do_and_unknown()
    assert [line["id"] for line in data["to_do"]] == [item.line.pk for item in to_do]
    [waiting] = data["to_do"]
    assert waiting["proposal"]["number"] == likely.number
    assert waiting["difference"] == "€ 95,00"
    [booked] = data["booked"]
    assert booked["invoice"]["number"] == sure.number
    assert booked["state"] == "geboekt door Huismus"
    [other] = data["not_recognised"]
    assert (other["name"], other["amount"], other["direction"]) == ("Iemand", "€ 12,34", "in")
    assert data["not_recognised_total"] == len(unknown) == 1
    # Someone else's account number is not given.
    assert "NL02RABO0123456789" not in json.dumps(data)


def test_without_a_statement_the_bank_is_empty(tool, business):
    data, _text, _error = tool("list_bank")
    assert (data["to_do"], data["booked"], data["latest_statement"]) == ([], [], None)


# --- Categories ---


def test_categories_with_their_count(tool, business):
    travel = ExpenseCategory.objects.create(name="Reizen")
    ExpenseCategory.objects.create(name="Software")
    tool("add_expense", lines=[{"amount": "10", "category": "reizen"}])
    data, _text, _error = tool("list_categories")
    assert data["categories"] == [
        {"id": travel.pk, "name": "Reizen", "expenses": 1},
        {"id": travel.pk + 1, "name": "Software", "expenses": 0},
    ]


# --- A document's PDF ---


def _pdf(content):
    [_text, resource] = content
    assert resource["type"] == "resource"
    assert resource["resource"]["mimeType"] == "application/pdf"
    return base64.b64decode(resource["resource"]["blob"])


def test_the_pdf_of_an_issued_invoice(full, business, customer, monkeypatch):
    invoice = issue(_draft(customer))
    made = []

    def render(document, **kwargs):
        made.append((document.pk, kwargs))
        return b"%PDF-1.7 van Huismus"

    monkeypatch.setattr("huismus.documents.mailing.render_pdf", render)
    result, content = full("get_document_pdf", id=invoice.pk)
    assert _pdf(content) == b"%PDF-1.7 van Huismus"
    assert made == [(invoice.pk, {})]
    data = result["structuredContent"]
    assert (data["number"], data["made_by"], data["preview"]) == (invoice.number, "huismus", False)
    assert data["name"] == f"{invoice.number}.pdf"


def test_the_pdf_of_an_imported_invoice_is_its_original(full, business, customer):
    invoice = issue(_draft(customer))
    Attachment.objects.create(
        document=invoice,
        kind="original_pdf",
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
    )
    result, content = full("get_document_pdf", id=invoice.pk)
    assert _pdf(content) == b"%PDF-1.4 het origineel"
    assert result["structuredContent"]["made_by"] == "original"


def test_a_draft_gives_a_preview(full, business, customer, monkeypatch):
    draft = _draft(customer)
    made = []

    def render(document, **kwargs):
        made.append(kwargs)
        return b"%PDF-1.7 voorbeeld"

    monkeypatch.setattr("huismus.assistants.tools.render_pdf", render)
    result, content = full("get_document_pdf", id=draft.pk)
    assert _pdf(content) == b"%PDF-1.7 voorbeeld"
    assert made == [{"preview": True}]
    data = result["structuredContent"]
    assert data["preview"] is True
    assert "VOORBEELD" in data["note"]
    assert "number" not in data


def test_a_credit_note_names_the_invoice(full, business, customer, monkeypatch):
    monkeypatch.setattr("huismus.documents.mailing.render_pdf", lambda d, **k: b"%PDF")
    invoice = issue(_draft(customer))
    invoice = Document.objects.with_payment_totals().get(pk=invoice.pk)
    credit_note = issue(create_credit_note(invoice))
    result, _content = full("get_document_pdf", id=credit_note.pk)
    assert result["structuredContent"]["corrects_invoice"] == invoice.number


def test_a_real_pdf_renders(full, business, customer):
    """The smoke test: WeasyPrint really makes it."""
    invoice = issue(_draft(customer))
    _result, content = full("get_document_pdf", id=invoice.pk)
    assert _pdf(content).startswith(b"%PDF")


def test_no_pdf_of_a_document_that_isnt_there(tool, business):
    _data, text, is_error = tool("get_document_pdf", id=999)
    assert is_error
    assert "bestaat niet" in text


# --- Settings ---


def test_the_settings_an_assistant_needs(tool, business, customer):
    issue(_draft(customer))
    data, _text, _error = tool("get_settings")
    assert data["kor"] is True
    assert data["no_vat_for_another_reason"] is False
    assert data["default_language"] == "nl"
    assert data["payment_terms_days"] == business.default_payment_terms_days
    numbers = data["next_number_if_issued_now"]
    assert numbers["invoice"] == numbers["credit_note"]
    assert numbers["invoice"].endswith("0002")
    assert data["mail_set_up"] is False


def test_the_settings_never_give_secrets_or_details(tool, business):
    smtp.set_password("app-password-for-tests")
    business.smtp_provider = "gmail"
    business.smtp_host = "smtp.gmail.com"
    business.smtp_port = 587
    business.smtp_security = "starttls"
    business.smtp_username = "ik@example.invalid"
    business.vat_number = "NL000099998B57"
    business.save()
    data, text, _error = tool("get_settings")
    assert data["mail_set_up"] is True
    for kept_out in (
        "app-password-for-tests",
        "smtp.gmail.com",
        "ik@example.invalid",
        business.iban,
        business.kvk_number,
        business.vat_number,
        business.address_line1,
    ):
        assert kept_out not in text
