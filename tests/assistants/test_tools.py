# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What an assistant can do (SPEC.md M16), through the same code as the app:
the editor's forms, compute_totals(), issue(), send_quote(), send_document()."""

import pytest
from django.core import mail
from django.utils import timezone

from huismus.business import smtp
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, EmailLog
from huismus.documents.totals import compute_totals
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db

YEAR = timezone.localdate().year


def _draft(customer, lines=((6, 8500),), kind="invoice"):
    document = Document.objects.create(kind=kind, status="draft", contact=customer)
    for position, (quantity, cents) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description="Fotografie",
            quantity=quantity,
            unit="uur",
            unit_price_cents=cents,
        )
    return document


def _issued(customer, **kwargs):
    return issue(_draft(customer, **kwargs))


@pytest.fixture
def mail_set_up(business):
    smtp.set_password("app-password-for-tests")
    business.smtp_provider = "gmail"
    business.smtp_host = "smtp.gmail.com"
    business.smtp_port = 587
    business.smtp_security = "starttls"
    business.save()


LINES = [{"description": "Fotografie", "quantity": 6, "unit": "uur", "unit_price": "85"}]


# --- Drafts ---


def test_a_draft_invoice_from_the_assistant(tool, business, customer):
    data, _text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=LINES
    )
    assert not is_error
    document = Document.objects.get(pk=data["id"])
    assert (document.kind, document.status, document.number) == ("invoice", "draft", "")
    assert document.contact == customer
    assert document.issue_date == timezone.localdate()
    # The one totals function (invariant 3), stored as the editor stores it.
    assert document.total_cents == compute_totals(document.lines.all()).total_cents == 51000
    assert data["total"] == "€ 510,00"
    assert data["lines"][0]["quantity"] == "6"


def test_amounts_in_dutch_notation_and_a_fixed_price(tool, business, customer):
    lines = [{"description": "Ontwerp", "unit_price": "1.250,50"}]
    data, _text, _error = tool("create_draft", kind="quote", contact_id=customer.pk, lines=lines)
    line = Document.objects.get(pk=data["id"]).lines.get()
    assert (line.quantity, line.unit_price_cents, line.line_total_cents) == (None, 125050, 125050)


def test_under_the_kor_only_zero_percent(tool, business, customer):
    lines = [{**LINES[0], "vat_percent": 21}]
    _data, text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=lines
    )
    assert is_error
    assert Document.objects.count() == 0
    assert "btw" in text.lower()


def test_an_unknown_customer_is_made_in_huismus_first(tool, business):
    _data, text, is_error = tool("create_draft", kind="invoice", contact_id=999, lines=LINES)
    assert is_error
    assert "Klanten" in text
    assert Document.objects.count() == 0


def test_a_credit_note_is_not_a_new_draft(tool, business, customer):
    _data, _text, is_error = tool(
        "create_draft", kind="credit_note", contact_id=customer.pk, lines=LINES
    )
    assert is_error


def test_changing_a_draft_keeps_what_is_left_out(tool, business, customer):
    data, _text, _error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=LINES, reference="PO-12"
    )
    data, _text, is_error = tool("update_draft", id=data["id"], notes="Bellen voor vrijdag")
    assert not is_error
    document = Document.objects.get(pk=data["id"])
    assert (document.reference, document.notes) == ("PO-12", "Bellen voor vrijdag")
    assert document.lines.count() == 1
    assert document.total_cents == 51000


def test_new_lines_replace_the_old_ones(tool, business, customer):
    document = _draft(customer, lines=((1, 1000), (2, 2000)))
    lines = [{"description": "Montage", "quantity": "2,5", "unit_price": 100}]
    data, _text, is_error = tool("update_draft", id=document.pk, lines=lines)
    assert not is_error
    assert [line.description for line in document.lines.all()] == ["Montage"]
    document.refresh_from_db()
    assert document.total_cents == 25000
    assert data["total"] == "€ 250,00"


def test_an_issued_invoice_cannot_be_changed(tool, business, customer):
    invoice = _issued(customer)
    _data, _text, is_error = tool("update_draft", id=invoice.pk, notes="anders")
    assert is_error
    invoice.refresh_from_db()
    assert invoice.notes == ""


def test_a_draft_with_a_number_is_left_to_the_user(tool, business, customer):
    document = _draft(customer)
    document.number = "2026-0003"
    document.save()
    _data, _text, is_error = tool("update_draft", id=document.pk, notes="anders")
    assert is_error


def test_a_credit_note_draft_from_an_issued_invoice(tool, business, customer):
    invoice = _issued(customer)
    data, _text, is_error = tool("create_credit_note_draft", id=invoice.pk)
    assert not is_error
    credit_note = Document.objects.get(pk=data["id"])
    assert (credit_note.kind, credit_note.status) == ("credit_note", "draft")
    assert credit_note.related_document == invoice
    assert credit_note.total_cents == invoice.total_cents


def test_no_credit_note_from_a_draft(tool, business, customer):
    _data, _text, is_error = tool("create_credit_note_draft", id=_draft(customer).pk)
    assert is_error


# --- Issuing, sending, mailing ---


def test_the_preview_says_what_issuing_will_do(tool, business, customer):
    document = _draft(customer)
    data, _text, is_error = tool("preview_issue", id=document.pk)
    assert not is_error
    assert data["customer"] == "Bakkerij De Korrel"
    assert data["total"] == "€ 510,00"
    assert data["action"] == "issue_document"
    assert data["kor_limit"] is None
    data_after, _text, _error = tool("issue_document", id=document.pk)
    assert data_after["number"] == data["number"]


def test_the_preview_has_the_kor_line_of_the_issue_dialog(tool, business, customer):
    business.kor_limit_cents = 50000
    business.save()
    data, _text, _error = tool("preview_issue", id=_draft(customer).pk)
    assert (
        data["kor_limit"] == "Met deze factuur kom je op € 510,00, boven je KOR-grens van € 500,00."
    )


def test_issuing_goes_through_issue(tool, business, customer):
    document = _draft(customer)
    data, _text, is_error = tool("issue_document", id=document.pk)
    assert not is_error
    document.refresh_from_db()
    assert document.status == "issued"
    assert document.number == data["number"]
    assert document.contact_snapshot["display_name"] == "Bakkerij De Korrel"


def test_issuing_twice_is_refused(tool, business, customer):
    invoice = _issued(customer)
    _data, _text, is_error = tool("issue_document", id=invoice.pk)
    assert is_error


def test_a_refusal_of_issue_comes_back_as_its_message(tool, business, customer):
    business.kor_text = ""
    business.save()
    _data, text, is_error = tool("issue_document", id=_draft(customer).pk)
    assert is_error
    assert "KOR" in text
    assert Document.objects.get().status == "draft"


def test_a_quote_is_sent_not_issued(tool, business, customer):
    quote = _draft(customer, kind="quote")
    _data, _text, is_error = tool("issue_document", id=quote.pk)
    assert is_error
    data, _text, is_error = tool("preview_issue", id=quote.pk)
    assert data["action"] == "send_quote"
    data, _text, is_error = tool("send_quote", id=quote.pk)
    assert not is_error
    quote.refresh_from_db()
    assert quote.status == "sent"
    assert quote.number
    assert len(mail.outbox) == 0


def test_mailing_goes_to_the_customer_and_is_logged(tool, mail_set_up, customer):
    invoice = _issued(customer)
    preview, _text, is_error = tool("preview_mail", id=invoice.pk)
    assert not is_error
    assert preview["to"] == "korrel@example.invalid"
    data, _text, is_error = tool("mail_document", id=invoice.pk)
    assert not is_error
    assert len(mail.outbox) == 1
    assert mail.outbox[0].to == ["korrel@example.invalid"]
    assert mail.outbox[0].subject == preview["subject"]
    log = EmailLog.objects.get()
    assert (log.document, log.succeeded) == (invoice, True)


def test_a_credit_note_is_issued_like_an_invoice(tool, business, customer):
    invoice = _issued(customer)
    data, _text, _error = tool("create_credit_note_draft", id=invoice.pk)
    preview, _text, _error = tool("preview_issue", id=data["id"])
    assert (preview["action"], preview["total"]) == ("issue_document", "€ 510,00")
    assert preview["kor_limit"] is None
    issued, _text, is_error = tool("issue_document", id=data["id"])
    assert not is_error
    assert issued["number"] == preview["number"]
    assert Document.objects.get(pk=data["id"]).status == "issued"


def test_a_sent_quote_is_mailed_to_the_address_for_quotes(tool, mail_set_up, customer):
    customer.quote_email = "offertes@example.invalid"
    customer.save()
    quote = _draft(customer, kind="quote")
    tool("send_quote", id=quote.pk)
    preview, _text, _error = tool("preview_mail", id=quote.pk)
    assert preview["to"] == "offertes@example.invalid"
    tool("mail_document", id=quote.pk)
    assert mail.outbox[0].to == ["offertes@example.invalid"]


def test_a_draft_is_not_mailed(tool, mail_set_up, customer):
    _data, _text, is_error = tool("mail_document", id=_draft(customer).pk)
    assert is_error
    assert len(mail.outbox) == 0


def test_without_mail_set_up_nothing_is_mailed(tool, business, customer):
    _data, text, is_error = tool("preview_mail", id=_issued(customer).pk)
    assert is_error
    assert "Mailen" in text


# --- Reading ---


def test_the_overview(tool, business, customer):
    _issued(customer)
    _draft(customer)
    data, _text, _error = tool("get_overview")
    assert data["revenue"] == "€ 510,00"
    assert data["open_invoices"] == 1
    assert data["kor_limit"]["level"] == "ok"


def test_searching_documents(tool, business, customer):
    invoice = _issued(customer)
    _draft(customer, kind="quote")
    data, _text, _error = tool("search_documents", kind="invoice", status="open")
    assert [d["id"] for d in data["documents"]] == [invoice.pk]
    data, _text, _error = tool("search_documents", query="korrel")
    assert len(data["documents"]) == 2
    data, _text, _error = tool("search_documents", query=invoice.number)
    assert [d["number"] for d in data["documents"]] == [invoice.number]


def test_an_issued_document_shows_its_snapshot(tool, business, customer):
    invoice = _issued(customer)
    customer.company_name = "Bakkerij De Nieuwe Korrel"
    customer.save()
    data, _text, _error = tool("get_document", id=invoice.pk)
    assert data["customer"] == "Bakkerij De Korrel"
    assert data["payment_state"] == "unpaid"
    assert data["lines"][0]["line_total"] == "€ 510,00"


def test_an_unknown_document(tool, business):
    _data, _text, is_error = tool("get_document", id=12345)
    assert is_error


def test_searching_contacts_leaves_archived_ones_out(tool, business, customer):
    from huismus.contacts.models import Contact

    Contact.objects.create(company_name="Oude Korrel", archived=True)
    data, _text, _error = tool("search_contacts", query="korrel")
    assert [c["id"] for c in data["contacts"]] == [customer.pk]


def test_expenses_of_a_year(tool, business):
    Expense.objects.create(date=timezone.localdate(), supplier="Drukkerij", amount_cents=12100)
    data, _text, _error = tool("list_expenses", year=YEAR)
    assert data["total"] == "€ 121,00"
    assert data["expenses"][0]["supplier"] == "Drukkerij"


def test_the_expenses_of_a_year_name_the_categories(tool, business):
    ExpenseCategory.objects.create(name="Kantoor", sort_order=0)
    ExpenseCategory.objects.create(name="Reizen", sort_order=1)
    data, _text, _error = tool("list_expenses", year=YEAR)
    assert data["categories"] == ["Kantoor", "Reizen"]


# --- Expenses (huismus-intern/besluiten.md, 2026-11-02) ---


def test_an_expense_from_the_assistant(tool, business):
    category = ExpenseCategory.objects.create(name="Gereedschap")
    data, text, is_error = tool(
        "add_expense",
        date="2026-10-30",
        supplier="Gamma",
        description="Boormachine",
        lines=[{"description": "Accuboor", "amount": "42,35", "category": "gereedschap"}],
    )
    assert not is_error, text
    expense = Expense.objects.get(pk=data["id"])
    assert (expense.supplier, expense.description) == ("Gamma", "Boormachine")
    assert expense.date.isoformat() == "2026-10-30"
    # Gross (invariant 7), the sum of its lines, stored by expenses.lines.
    assert expense.amount_cents == 4235
    assert expense.vat_info_cents is None
    line = expense.lines.get()
    assert (line.description, line.amount_cents, line.category) == ("Accuboor", 4235, category)
    assert expense.source == ""
    assert data["amount"] == "€ 42,35"
    assert data["lines"][0]["category"] == "Gereedschap"
    assert data["path"] == f"/uitgaven/{expense.pk}/"
    assert data["receipt"]


def test_without_categories_the_category_is_left_out(tool, business):
    _data, text, is_error = tool("add_expense", lines=[{"amount": "10", "category": "Lunch"}])
    assert is_error
    assert "Laat de categorie weg" in text
    data, _text, is_error = tool("add_expense", lines=[{"amount": "10"}])
    assert not is_error
    assert data["lines"][0]["category"] is None


def test_without_the_kor_an_expense_needs_its_vat(tool, business):
    """The same rule as the form (decision of the owner, 2026-11-05)."""
    business.kor_enabled = False
    business.save()
    _data, text, is_error = tool("add_expense", lines=[{"amount": "12,10"}])
    assert is_error
    assert "Vul het btw-bedrag in." in text
    data, _text, is_error = tool("add_expense", lines=[{"amount": "12,10", "vat_info": 0}])
    assert not is_error
    assert Expense.objects.get(pk=data["id"]).amount_cents == 1210


def test_an_expense_with_lines_adds_them_up(tool, business):
    data, _text, is_error = tool(
        "add_expense",
        supplier="Drukkerij",
        lines=[
            {"description": "Visitekaartjes", "amount": 60.5, "vat_info": "10,50"},
            {"description": "Flyers", "amount": "1.210,00"},
        ],
    )
    assert not is_error
    expense = Expense.objects.get(pk=data["id"])
    assert expense.date == timezone.localdate()
    assert (expense.amount_cents, expense.vat_info_cents) == (127050, 1050)
    assert [line.position for line in expense.lines.all()] == [0, 1]


def test_an_unknown_category_names_the_ones_there_are(tool, business):
    ExpenseCategory.objects.create(name="Kantoor", sort_order=0)
    ExpenseCategory.objects.create(name="Reizen", sort_order=1)
    _data, text, is_error = tool("add_expense", lines=[{"amount": "10", "category": "Lunch"}])
    assert is_error
    assert "Kantoor, Reizen" in text
    assert not Expense.objects.exists()
    assert not ExpenseCategory.objects.filter(name="Lunch").exists()


def test_an_expense_needs_a_line_with_an_amount(tool, business):
    _data, _text, is_error = tool("add_expense", supplier="Gamma", lines=[])
    assert is_error
    _data, text, is_error = tool("add_expense", lines=[{"amount": "veel"}])
    assert is_error
    assert text
    assert not Expense.objects.exists()


def test_a_wrong_date_is_a_refusal(tool, business):
    _data, text, is_error = tool("add_expense", date="gisteren", lines=[{"amount": "10"}])
    assert is_error
    assert not Expense.objects.exists()


def test_an_unknown_vat_rate_is_a_refusal_not_an_error(tool, business, customer):
    lines = [{**LINES[0], "vat_percent": "veel"}]
    _data, text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=lines
    )
    assert is_error
    assert "21" in text


# --- VAT without the KOR (SPEC.md M18) ---


def test_without_the_kor_a_line_starts_at_21_percent(tool, business, customer):
    business.kor_enabled = False
    business.save()
    data, _text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=LINES
    )
    assert not is_error
    line = Document.objects.get(pk=data["id"]).lines.get()
    assert line.tax_rate_bp == 2100
    assert data["total"] == "€ 617,10"


def test_without_the_kor_9_percent_and_0_percent_can_be_chosen(tool, business, customer):
    business.kor_enabled = False
    business.save()
    lines = [{**LINES[0], "vat_percent": 9}, {**LINES[0], "vat_percent": 0}]
    data, _text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=lines
    )
    assert not is_error
    rates = [line.tax_rate_bp for line in Document.objects.get(pk=data["id"]).lines.all()]
    assert rates == [900, 0]


def test_under_the_kor_a_line_without_a_rate_is_0_percent(tool, business, customer):
    data, _text, is_error = tool(
        "create_draft", kind="invoice", contact_id=customer.pk, lines=LINES
    )
    assert not is_error
    assert Document.objects.get(pk=data["id"]).lines.get().tax_rate_bp == 0


def test_the_overview_and_the_kor_line_count_revenue_without_vat(tool, business, customer):
    """An invoice from before the KOR with 21% VAT, then the KOR on."""
    business.kor_enabled = False
    business.save()
    before = _draft(customer, lines=((1, 1_000_000),))
    before.lines.update(tax_rate_bp=2100)
    assert issue(before).total_cents == 1_210_000
    business.kor_enabled = True
    business.kor_limit_cents = 2_000_000
    business.save()

    data, _text, _error = tool("get_overview")
    assert data["revenue"] == "€ 10.000,00"

    # Another € 10.000,00 takes the revenue to exactly the limit, not over.
    draft = _draft(customer, lines=((1, 1_000_000),))
    data, _text, _error = tool("preview_issue", id=draft.pk)
    assert "€ 20.000,00" in data["kor_limit"]
    assert "100%" in data["kor_limit"]


# --- "Verlegd" (SPEC.md M18) ---


def test_the_assistant_sees_a_verlegd_line_and_keeps_it(tool, business, customer):
    business.kor_enabled = False
    business.save()
    document = _draft(customer)
    document.lines.update(reverse_charge=True)

    data, _text, _error = tool("get_document", id=document.pk)
    assert data["lines"][0]["reverse_charge"] is True

    _data, _text, is_error = tool("update_draft", id=document.pk, notes="Bellen")
    assert not is_error
    assert document.lines.get().reverse_charge is True


def test_an_expense_from_the_assistant_is_to_check(tool, business):
    """ "Nakijken" in Huismus until the user says it's right
    (huismus-intern/besluiten.md, 2026-11-05, "Bonnetjes onderweg, deel 2")."""
    data, _text, is_error = tool("add_expense", lines=[{"amount": "10"}])
    assert not is_error
    assert Expense.objects.get(pk=data["id"]).needs_review
