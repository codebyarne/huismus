# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What an AI assistant can do in Huismus (SPEC.md M16). Since
huismus-intern/besluiten.md, 2026-11-21 "een assistent mag wat jij mag"
(#273): what the user may do in the app, an assistant may do here, and what
can't be undone or goes outside asks the user first.

Five kinds of tool:

- "read": changes nothing. Marked read-only, so the assistant's app may
  run it without asking: the overview with Te doen, documents and their
  PDF, contacts, expenses, categories, the receipts without an expense,
  the bank page, the year overview, the VAT return, and the settings an
  assistant needs (never passwords, keys or backups). The previews before
  a "confirm" are read tools too.
- "draft": makes or changes a draft, through the editor's own forms and
  documents.drafts: a new one, a copy, a quote turned into an invoice, a
  credit note.
- "add": adds an expense, through the expense page's own forms and
  expenses.adding, with a receipt from the tray if given (SPEC.md M20,
  part 2). It gets no number and the user can still change or delete it
  in the app, so it is not marked destructive.
- "change": changes what the user can change back: an expense (marked to
  check again), a receipt from the tray onto an expense, categories,
  customers and archiving them, skipping a bank line. Not destructive
  either; the answer has the path to the place in Huismus.
- "confirm": what can't be undone or goes outside (huismus-intern/
  besluiten.md, 2026-11-22, "AI-koppeling deel 2"): issuing, sending a
  quote, mailing, a reminder, recording a payment, a quote's answer,
  deleting, "Toch bewerken" and undoing it, booking a bank line and
  undoing that. Marked destructive and never read-only, so the
  assistant's app asks the user first; the button is the app's, the
  assistant cannot press it. Each has a preview tool before it that says
  what will happen (a quote's answer: get_document).

Every action goes through the same function as the app's screen (issue(),
send_quote(), send_document(), documents.drafts, documents.payments,
documents.quoting, documents.reopening, expenses.adding, ContactForm,
bank.reading), so numbering, totals and immutability are checked where
they always are. Contact persons stay in the app for now.

Titles are gettext, shown in the default language from the settings
(assistants.views); descriptions are English, for the assistant.
"""

import base64
import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from huismus.bank import reading as bank_reading
from huismus.bank import views as bank
from huismus.bank.models import BankStatement, BankTransaction
from huismus.business import smtp
from huismus.business.kor_limit import kor_limit_crossed_by, kor_limit_status
from huismus.business.models import Settings
from huismus.contacts.forms import ContactForm
from huismus.contacts.models import Contact
from huismus.core import form_messages
from huismus.core.dashboard import outstanding_invoices
from huismus.core.models import Attachment
from huismus.core.profile import EXPENSES, QUOTES, profile
from huismus.core.templatetags.money import euros, money
from huismus.core.todo import current_todo
from huismus.documents.drafts import (
    copy_document,
    create_credit_note,
    deletable_drafts,
    delete_draft,
    document_form,
    line_formset,
    peek_number_for,
    save_draft,
)
from huismus.documents.forms import PAYMENT_METHOD_CHOICES, PaymentForm
from huismus.documents.issuing import IssueError, issue
from huismus.documents.listing import contact_name
from huismus.documents.mailing import (
    MAILABLE_STATUSES,
    attachment,
    default_message,
    default_recipients,
    send_document,
)
from huismus.documents.models import Document
from huismus.documents.numbering import NumberingError, next_numbers_if_issued_today
from huismus.documents.payments import record_payment
from huismus.documents.pdf import render_pdf
from huismus.documents.quoting import (
    QuoteError,
    accept_quote,
    convert_to_invoice,
    decline_quote,
    expire_quote,
    send_quote,
)
from huismus.documents.reopening import NOTHING_TO_UNDO, ReopenError, reopen, undo_reopen
from huismus.documents.totals import compute_totals
from huismus.documents.vat import default_rate, editor_value, rate_label
from huismus.expenses import adding
from huismus.expenses.forms import ExpenseCategoryForm
from huismus.expenses.models import Expense, ExpenseCategory, VatRate
from huismus.reports.periods import Period
from huismus.reports.vat_return import EXEMPT_NOTE, KOR_NOTE, NOT_COUNTED_TITLES, compute_vat_return
from huismus.reports.year_overview import compute_year_overview

from . import receipts


class ToolError(Exception):
    """A refusal the assistant passes on to the user, not a bug."""


@dataclass(frozen=True)
class WithContent:
    """A handler's answer with more after its data: the images of a
    receipt, or a document's PDF."""

    data: dict
    content: list[dict]


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    # Decides what the assistant's app asks first (see the module docstring).
    kind: Literal["read", "draft", "add", "change", "confirm"]
    description: str
    properties: dict
    required: tuple[str, ...]
    handler: Callable[[dict], dict]
    # Reaches outside Huismus: mailing.
    open_world: bool = False

    def definition(self) -> dict:
        title = str(self.title)
        return {
            "name": self.name,
            "title": title,
            "description": self.description,
            "inputSchema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
                "additionalProperties": False,
            },
            "annotations": {
                "title": title,
                "readOnlyHint": self.kind == "read",
                "destructiveHint": self.kind == "confirm",
                "idempotentHint": self.kind == "read",
                "openWorldHint": self.open_world,
            },
        }

    def call(self, arguments: dict) -> dict:
        try:
            data = self.handler(arguments)
        except ToolError as refusal:
            return {"content": [{"type": "text", "text": str(refusal)}], "isError": True}
        more = []
        if isinstance(data, WithContent):
            data, more = data.data, data.content
        text = json.dumps(data, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": text}, *more], "structuredContent": data}


# --- What the assistant gets back ---


def _plain_text(text) -> str:
    """Without the non-breaking spaces the pages use."""
    return str(text).replace("\u00a0", " ")


def _amount(cents) -> str:
    """ "€ 1.815,00"."""
    return _plain_text(money(cents))


def _date(value) -> str | None:
    return value.isoformat() if value else None


def _payment_fields(document) -> dict:
    if document.kind != "invoice" or document.status != "issued":
        return {}
    return {
        "payment_state": document.payment_state,
        "outstanding": _amount(document.outstanding_cents),
        "overdue": document.is_overdue,
    }


def _summary(document) -> dict:
    """A document in a list. The customer as the list in the app shows it:
    from the snapshot once issued (invariant 5)."""
    return {
        "id": document.pk,
        "kind": document.kind,
        "status": document.shown_status,
        "number": document.number or None,
        "customer": contact_name(document),
        "issue_date": _date(document.issue_date),
        "total": _amount(document.total_cents),
        **_payment_fields(document),
    }


def _vat_percent(basis_points: int) -> str:
    return f"{_plain(Decimal(basis_points) / 100)}%"


def _plain(value: Decimal) -> str:
    """Decimal("2.500") -> "2.5", Decimal("10.000") -> "10"."""
    return format(value.normalize(), "f")


def _detail(document) -> dict:
    lines = [
        {
            "description": line.description,
            "quantity": None if line.quantity is None else _plain(line.quantity),
            "unit": line.unit,
            "unit_price": _amount(line.unit_price_cents),
            "vat": _vat_percent(line.tax_rate_bp),
            # A "verlegd" line is 0%, but not an ordinary one (SPEC.md M18).
            "reverse_charge": line.reverse_charge,
            "line_total": _amount(line.line_total_cents),
        }
        for line in document.lines.all()
    ]
    related = document.related_document
    return {
        **_summary(document),
        "contact_id": document.contact_id,
        # The line prices include VAT (#362): the total is their sum.
        "prices_include_vat": document.prices_include_vat,
        "attention": document.attention,
        "reference": document.reference,
        "due_date": _date(document.due_date),
        "expiry_date": _date(document.expiry_date),
        "language": document.language,
        "currency": document.currency,
        "intro_text": document.intro_text,
        "footer_text": document.footer_text,
        "notes": document.notes,
        "lines": lines,
        "subtotal": _amount(document.subtotal_cents),
        "vat_total": _amount(document.tax_cents),
        "related_document": None
        if related is None
        else {"id": related.pk, "kind": related.kind, "number": related.number},
        "reopened": document.reopened_at is not None,
    }


def _document(arguments, **filters) -> Document:
    document_id = arguments.get("id")
    document = (
        Document.objects.with_payment_totals().filter(pk=document_id, **filters).first()
        if isinstance(document_id, int)
        else None
    )
    if document is None:
        raise ToolError(_("Dit document bestaat niet in Huismus, of past niet bij deze actie."))
    return document


# --- Read ---


def get_overview(arguments):
    year = arguments.get("year") or timezone.localdate().year
    overview = compute_year_overview(year)
    outstanding = outstanding_invoices()
    data = {
        "year": year,
        "revenue": _amount(overview.revenue_cents),
        "open_invoices": outstanding["count"],
        "outstanding": _amount(outstanding["total_cents"]),
        "overdue_invoices": outstanding["overdue_count"],
        # Te doen on the Overzicht, the same rows (core.todo).
        "to_do": [
            {
                "kind": item.kind,
                "title": _plain_text(item.title),
                "detail": _plain_text(item.detail),
                "path": item.url or item.action_url,
            }
            for item in current_todo(timezone.localdate(), outstanding).items
        ],
    }
    kor = kor_limit_status(year)
    if kor is not None:
        data["kor_limit"] = {
            "limit": _amount(kor.limit_cents),
            "percent_of_limit": kor.percent,
            "warning_from_percent": kor.warning_percent,
            "level": kor.level,
        }
    return data


STATUS_FILTERS = {
    "draft": lambda d: d.status == "draft",
    "issued": lambda d: d.status == "issued",
    # As the screens show it: a sent quote past its date is expired.
    "sent": lambda d: d.shown_status == "sent",
    "accepted": lambda d: d.status == "accepted",
    "declined": lambda d: d.status == "declined",
    "expired": lambda d: d.shown_status == "expired",
    "open": lambda d: d.payment_state in ("unpaid", "partial"),
    "overdue": lambda d: d.is_overdue,
    "paid": lambda d: d.payment_state in ("paid", "credited"),
}


def search_documents(arguments):
    """Filtered in Python, like the invoice list (documents.listing):
    payment_state is a property, not a column."""
    documents = Document.objects.with_payment_totals().select_related("contact")
    if arguments.get("kind"):
        documents = documents.filter(kind=arguments["kind"])
    if arguments.get("year"):
        documents = documents.filter(issue_date__year=arguments["year"])
    if arguments.get("contact_id"):
        documents = documents.filter(contact_id=arguments["contact_id"])
    documents = documents.order_by("-issue_date", "-pk")
    keep = STATUS_FILTERS.get(arguments.get("status"), lambda d: True)
    query = (arguments.get("query") or "").lower()
    limit = min(arguments.get("limit") or 20, 100)
    found = []
    for document in documents:
        if not keep(document):
            continue
        if query and query not in f"{document.number} {contact_name(document)}".lower():
            continue
        found.append(_summary(document))
        if len(found) == limit:
            break
    return {"documents": found}


def get_document(arguments):
    return _detail(_document(arguments))


def search_contacts(arguments):
    contacts = Contact.objects.filter(archived=False).order_by("company_name", "last_name")
    query = (arguments.get("query") or "").lower()
    limit = min(arguments.get("limit") or 20, 100)
    found = []
    for contact in contacts:
        haystack = f"{contact.display_name} {contact.first_name} {contact.last_name}"
        if query and query not in f"{haystack} {contact.email} {contact.city}".lower():
            continue
        found.append(
            {
                "id": contact.pk,
                "name": contact.display_name,
                "customer_number": contact.customer_number,
                "city": contact.city,
                "email": contact.email,
            }
        )
        if len(found) == limit:
            break
    return {"contacts": found}


def list_expenses(arguments):
    year = arguments.get("year") or timezone.localdate().year
    expenses = Expense.objects.filter(date__year=year).prefetch_related("lines__category")
    overview = compute_year_overview(year)
    result = {
        "year": year,
        # The year overview's own total: gross under the KOR, without VAT
        # and with the input VAT apart without it (SPEC.md M21, part 3).
        "total": _amount(overview.expenses_cents),
        "total_without_vat": overview.shows_input_vat,
        "expenses": [
            {
                "date": _date(expense.date),
                "supplier": expense.supplier,
                "description": expense.description,
                "category": expense.category_names or None,
                "amount": _amount(expense.amount_cents),
            }
            for expense in expenses.order_by("date", "pk")
        ],
        # The names add_expense accepts.
        "categories": [category.name for category in ExpenseCategory.objects.all()],
    }
    if overview.shows_input_vat:
        result["input_vat"] = _amount(overview.input_vat_cents)
    return result


def get_vat_return(arguments):
    """The VAT return page (SPEC.md M21, part 5): the same boxes and the
    same "Niet meegeteld", from compute_vat_return(). Under the KOR only
    the page's notice, as the page has no figures then."""
    period = Period.parse(arguments.get("period"), today=timezone.localdate())
    report = compute_vat_return(period)
    if report.kor_on:
        note = EXEMPT_NOTE if Settings.load().vat_exempt else KOR_NOTE
        return {"kor": True, "note": str(note)}

    def document(item, *, vat=True, **extra):
        found = {
            "id": item.document.pk,
            "number": item.number,
            "date": _date(item.issue_date),
            "revenue": _amount(item.revenue_cents),
        }
        if vat:
            found["vat"] = _amount(item.tax_cents)
        return {**found, **extra}

    items = {
        "without_rows": [document(item) for item in report.without_rows],
        "other_rates": [
            document(item, rate=rate_label(item.rate_bp)) for item in report.other_rates
        ],
        "reverse_charge_elsewhere": [
            document(item, country=item.country or None) for item in report.reverse_charge_elsewhere
        ],
        # As on the page: no VAT, under the KOR it is always 0.
        "kor_documents": [document(item, vat=False) for item in report.kor_documents],
        "back_in_draft": [
            {"id": draft.pk, "number": draft.number, "date": _date(draft.issue_date)}
            for draft in report.back_in_draft
        ],
        "lines_missing": [
            {
                "expense_id": line.expense_id,
                # As named on the page.
                "supplier": line.expense.supplier or line.expense.description or _("Uitgave"),
                "date": _date(line.expense.date),
                "description": line.description,
                "amount": _amount(line.amount_cents),
            }
            for line in report.lines_missing
        ],
    }
    data = {
        "period": str(period),
        "first_day": _date(period.first_day),
        "last_day": _date(period.last_day),
        "boxes": [
            {
                "box": box.code,
                "title": box.title,
                "revenue": _amount(box.revenue_cents),
                "vat": _amount(box.tax_cents),
            }
            for box in report.boxes
        ],
        "5a": _amount(report.owed_cents),
        "5b": _amount(report.input_vat_cents),
    }
    if report.reverse_charged_input_vat_cents:
        data["5b_reverse_charged"] = _amount(report.reverse_charged_input_vat_cents)
    data["to_get_back" if report.balance_cents < 0 else "to_pay"] = _amount(
        report.balance_abs_cents
    )
    # In the order of the page, which is that of NOT_COUNTED_TITLES; items
    # has a key for each of its kinds.
    data["not_counted"] = [
        {"kind": kind, "title": str(title), "items": items[kind]}
        for kind, title in NOT_COUNTED_TITLES.items()
        if items[kind]
    ]
    return data


def get_year_overview(arguments):
    """Rapporten → Jaaroverzicht: compute_year_overview() as it is, nothing
    counted anew."""
    year = arguments.get("year") or timezone.localdate().year
    overview = compute_year_overview(year)

    def costs(cents_without, input_vat_cents) -> dict:
        found = {"costs": _amount(cents_without)}
        if overview.shows_input_vat:
            found["input_vat"] = _amount(input_vat_cents)
        return found

    return {
        "year": year,
        # "Kosten" (gross) or "Kosten zonder btw", as the page says.
        "costs_label": str(overview.costs_label),
        "costs_without_vat": overview.shows_input_vat,
        "revenue": _amount(overview.revenue_cents),
        **costs(overview.expenses_cents, overview.input_vat_cents),
        "profit": _amount(overview.profit_cents),
        "quarters": [
            {
                "quarter": f"Q{quarter.quarter}",
                "revenue": _amount(quarter.revenue_cents),
                **costs(quarter.expenses_cents, quarter.input_vat_cents),
                "profit": _amount(quarter.profit_cents),
            }
            for quarter in overview.quarters
        ],
        "costs_by_category": [
            {"category": category.name, "amount": _amount(category.amount_cents)}
            for category in overview.by_category
        ],
    }


# How many invoices or expenses to choose from a line under Te doen
# gives: the ones that fit first (bank.views).
BANK_CHOICES = 5


def _bank_line(line) -> dict:
    return {
        "id": line.pk,
        "date": _date(line.booked_on),
        # Positive: money in, for an invoice; negative: out, for an expense.
        "amount": _amount(line.amount_cents),
        "direction": "out" if line.is_outgoing else "in",
        "name": line.counterparty_name,
        "description": line.description,
        "reference": line.reference,
    }


def _bank_choice(choice, *, outgoing: bool) -> dict:
    """An open invoice (money in) or an expense without a bank line (out)."""
    if not outgoing:
        return {
            "invoice_id": choice.pk,
            "number": choice.number,
            "customer": choice.customer,
            "outstanding": _amount(choice.outstanding_cents),
        }
    return {
        "expense_id": choice.pk,
        "date": _date(choice.date),
        "supplier": choice.supplier,
        "description": choice.description,
        "amount": _amount(choice.gross_cents),
    }


def _waiting_line(item) -> dict:
    found = _bank_line(item.line)
    if item.proposal is not None:
        found["proposal"] = _bank_choice(item.proposal, outgoing=item.line.is_outgoing)
        if not item.line.is_outgoing and item.difference_cents:
            # More (positive) or less (negative) than what is open on it.
            found["difference"] = _amount(item.difference_cents)
    else:
        found["choices"] = [
            _bank_choice(choice, outgoing=item.line.is_outgoing)
            for choice in item.choices[:BANK_CHOICES]
        ]
    return found


def _booked_line(line) -> dict:
    found = {**_bank_line(line), "state": str(line.get_state_display())}
    if line.payment_id:
        document = line.payment.document
        found["invoice"] = {"id": document.pk, "number": document.number}
    elif line.expense_id:
        found["expense_id"] = line.expense_id
    return found


def list_bank(arguments):
    """Bank: the page's three sections, from the page's own functions."""
    to_do, unknown = bank.to_do_and_unknown()
    statement = BankStatement.objects.first()
    limit = min(arguments.get("limit") or 20, 100)
    return {
        "to_do": [_waiting_line(item) for item in to_do],
        # As the page: the booked lines of the latest statement.
        "latest_statement": None
        if statement is None
        else {"name": statement.filename, "read": _date(timezone.localdate(statement.created_at))},
        "booked": [_booked_line(line) for line in bank.booked_lines(statement)],
        "not_recognised": [_bank_line(item.line) for item in unknown[:limit]],
        "not_recognised_total": len(unknown),
        "path": reverse("bank:statement"),
    }


def list_categories(arguments):
    """Uitgaven → Categorieën, with the same count per category."""
    categories = ExpenseCategory.objects.annotate(
        expense_count=Count("lines__expense", distinct=True)
    )
    return {
        "categories": [
            {"id": category.pk, "name": category.name, "expenses": category.expense_count}
            for category in categories
        ],
        "path": reverse("expenses:category_list"),
    }


def get_document_pdf(arguments):
    """The PDF the app gives: for an issued invoice, credit note or a sent
    quote the one of the PDF button, which is the imported original while
    it is still the document (mailing.attachment, Document.primary_original_pdf);
    for a draft the editor's preview, marked VOORBEELD."""
    document = _document(arguments)
    data = {"id": document.pk, "kind": document.kind, "status": document.shown_status}
    if document.status == "draft":
        content = render_pdf(document, preview=True)
        data["preview"] = True
        # None until it is issued; a draft reopened with "Toch bewerken" keeps its own.
        data["number"] = document.number or None
        data["note"] = _(
            "Dit is een concept: de PDF heeft VOORBEELD op elke pagina. "
            "Stuur hem niet als factuur naar je klant."
        )
        name = f"concept-{document.pk}.pdf"
    else:
        name, content = attachment(document)
        data["number"] = document.number
        data["preview"] = False
        data["made_by"] = "original" if document.primary_original_pdf() else "huismus"
    related = document.related_document
    if document.kind == "credit_note" and related is not None:
        data["corrects_invoice"] = related.number
    data["name"] = name
    return WithContent(
        data,
        [
            {
                "type": "resource",
                "resource": {
                    "uri": f"huismus://documents/{document.pk}/{name}",
                    "mimeType": "application/pdf",
                    "blob": base64.b64encode(content).decode("ascii"),
                },
            }
        ],
    )


def get_settings(arguments):
    """What an assistant needs to work well, and nothing more: no address,
    registration numbers, bank account, mail server, passwords, keys or
    backups (huismus-intern/besluiten.md, 2026-11-22)."""
    settings = Settings.load()
    try:
        numbers = next_numbers_if_issued_today(settings)
    except NumberingError as error:
        # The number format can't make a number: say why, don't hide it.
        raise ToolError(str(error)) from error
    return {
        "business_name": settings.business_name,
        "kor": settings.kor_enabled,
        "no_vat_for_another_reason": settings.vat_exempt,
        "default_language": settings.default_language,
        "currency": settings.currency,
        "payment_terms_days": settings.default_payment_terms_days,
        "numbering_restarts_yearly": settings.number_reset_yearly,
        # Nothing is reserved: issuing today would give these. Credit
        # notes share the invoices' sequence (NumberSequence, and
        # documents.drafts.peek_number_for).
        "next_number_if_issued_now": {
            "invoice": numbers["invoice"],
            "credit_note": numbers["invoice"],
            "quote": numbers["quote"],
        },
        "mail_set_up": smtp.is_configured(settings) and not smtp.password_is_missing(settings),
    }


# --- Receipts without an expense (SPEC.md M20, part 2) ---

RECEIPT_GONE = adding.RECEIPT_GONE


def _tray_receipt(pk) -> Attachment:
    """Only a receipt that waits for an expense: every other attachment
    stays closed to the assistant (SPEC.md M16)."""
    try:
        return Attachment.objects.in_tray().get(pk=int(pk))
    except (TypeError, ValueError, Attachment.DoesNotExist) as error:
        raise ToolError(str(RECEIPT_GONE)) from error


def list_receipts(arguments):
    return {
        # The same rule as the expense form (decision of the owner, 2026-11-05).
        "vat_required": not Settings.load().no_vat,
        "receipts": [
            {
                "id": receipt.pk,
                "name": receipt.filename,
                "received": _date(timezone.localdate(receipt.created_at)),
                "type": "pdf" if receipt.is_pdf else "image",
            }
            for receipt in Attachment.objects.in_tray().order_by("created_at", "pk")
        ],
    }


def read_receipt(arguments):
    receipt = _tray_receipt(arguments.get("id"))
    try:
        reading = receipts.read(receipt)
    except receipts.Unreadable as error:
        raise ToolError(
            _("Huismus kan dit bonnetje niet lezen. Maak de uitgave in Huismus.")
        ) from error
    data = {"id": receipt.pk, "name": receipt.filename, "text": reading.text}
    if reading.pages is not None:
        data["pages"] = reading.pages
    return WithContent(data, reading.images)


# --- Drafts ---

DOCUMENT_FIELDS = (
    "reference",
    "issue_date",
    "due_date",
    "expiry_date",
    "language",
    "intro_text",
    "footer_text",
    "notes",
)


# The line formset's POST data is built here, not saved directly, so the
# lines get the editor's own validation (DocumentLineForm: the KOR's 0 %,
# the amount notation) and its saving (documents.drafts). The field
# unit_price_cents takes euros as typed, "85,00": EuroCentsField makes cents.


def _line_data(lines, existing) -> dict:
    """The line formset's POST data: the new lines as extra forms, and
    every existing line marked for deletion, as the editor would post
    after the user replaced them all."""
    data = {
        "lines-TOTAL_FORMS": str(len(existing) + len(lines)),
        "lines-INITIAL_FORMS": str(len(existing)),
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, line in enumerate(existing):
        data[f"lines-{index}-id"] = str(line.pk)
        data[f"lines-{index}-description"] = line.description
        data[f"lines-{index}-unit_price_cents"] = euros(line.unit_price_cents)
        data[f"lines-{index}-tax_rate_bp"] = editor_value(line)
        data[f"lines-{index}-DELETE"] = "on"
    new_line_rate = default_rate(Settings.load())
    for index, line in enumerate(lines, start=len(existing)):
        if not isinstance(line, dict):
            raise ToolError(_("Elke regel heeft een omschrijving en een prijs."))
        quantity = line.get("quantity")
        data[f"lines-{index}-description"] = str(line.get("description") or "")
        data[f"lines-{index}-quantity"] = "" if quantity is None else str(quantity)
        data[f"lines-{index}-unit"] = str(line.get("unit") or "")
        data[f"lines-{index}-unit_price_cents"] = str(line.get("unit_price", ""))
        # Left out: the editor's default for a new line. Whether the rate
        # is allowed (under the KOR only 0%) the editor's form checks below,
        # with documents.vat.allowed_rates.
        vat_percent = line.get("vat_percent")
        if vat_percent is None:
            rate_bp = new_line_rate
        elif vat_percent in (0, 9, 21):
            rate_bp = vat_percent * 100
        else:
            raise ToolError(_("Het btw-tarief is 0, 9 of 21 procent."))
        data[f"lines-{index}-tax_rate_bp"] = str(rate_bp)
    return data


def _keep_lines_data(existing) -> dict:
    """The formset's data with the saved lines as they are."""
    data = {
        "lines-TOTAL_FORMS": str(len(existing)),
        "lines-INITIAL_FORMS": str(len(existing)),
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for index, line in enumerate(existing):
        data[f"lines-{index}-id"] = str(line.pk)
        data[f"lines-{index}-description"] = line.description
        data[f"lines-{index}-quantity"] = "" if line.quantity is None else _plain(line.quantity)
        data[f"lines-{index}-unit"] = line.unit
        data[f"lines-{index}-unit_price_cents"] = euros(line.unit_price_cents)
        data[f"lines-{index}-tax_rate_bp"] = editor_value(line)
    return data


def _contact(contact_id) -> Contact:
    contact = (
        Contact.objects.filter(pk=contact_id, archived=False).first()
        if isinstance(contact_id, int)
        else None
    )
    if contact is None:
        raise ToolError(
            _(
                "Deze klant staat niet in Huismus. Maak de klant eerst aan in Huismus, "
                "onder Klanten."
            )
        )
    return contact


def _save(document, data: dict):
    """Validates and saves like the editor's "Opslaan" (documents.views)."""
    form = document_form(document, data)
    formset = line_formset(document, data)
    if not (form.is_valid() and formset.is_valid()):
        raise ToolError(
            form_messages.as_text(form, *formset.forms) or str(formset.non_form_errors())
        )
    saved = save_draft(document, form, formset)
    return _detail(Document.objects.with_payment_totals().get(pk=saved.pk))


def _part_shown(part, refusal):
    """What "Nieuw" doesn't offer, an assistant doesn't make either: a part
    out of the menu (#260, Instellingen › Menu; huismus-intern/besluiten.md,
    2026-11-22, #273 Q7). A part with something in it is shown."""
    if part not in profile().parts_shown:
        raise ToolError(refusal)


def create_draft(arguments):
    settings = Settings.load()
    if arguments.get("kind") == "quote":
        _part_shown(
            QUOTES,
            _(
                "Offertes staat uit bij Instellingen › Menu. "
                "Zet het daar aan om een offerte te maken."
            ),
        )
    contact = _contact(arguments.get("contact_id"))
    if not arguments.get("lines"):
        raise ToolError(_("Een concept heeft minstens één regel nodig."))
    if arguments.get("kind") not in ("invoice", "quote"):
        raise ToolError(_("Een nieuw concept is een factuur of een offerte."))
    document = Document(kind=arguments["kind"], status="draft")
    # What a new document in the editor starts with (documents.views).
    data = {
        "contact": str(contact.pk),
        "issue_date": timezone.localdate().isoformat(),
        "language": settings.default_language,
        "currency": settings.currency,
        "footer_text": settings.default_footer_text,
    }
    if settings.default_prices_include_vat:
        data["prices_include_vat"] = "on"
    data.update({name: arguments[name] for name in DOCUMENT_FIELDS if name in arguments})
    data.update(_line_data(arguments["lines"], []))
    return _save(document, data)


def update_draft(arguments):
    document = _document(arguments, status="draft")
    # A draft with a number was issued before (reopened by the user) or
    # imported: only the user changes it, in the app.
    if document.number:
        raise ToolError(_("Dit concept heeft al een nummer. Wijzig het in Huismus zelf."))
    # The form as the editor shows it, posted back with the changes: what
    # the assistant leaves out stays as it is.
    form = document_form(document)
    data = {name: form[name].value() for name in form.fields}
    data = {name: "" if value is None else value for name, value in data.items()}
    # The T.a.v. line belongs to this customer: DocumentForm.clean() keeps
    # it, and only picks the default for another customer.
    data["attention_contact"] = str(document.contact_id or "")
    if "contact_id" in arguments:
        data["contact"] = str(_contact(arguments["contact_id"]).pk)
    data.update({name: arguments[name] for name in DOCUMENT_FIELDS if name in arguments})
    existing = list(document.lines.all())
    if "lines" in arguments:
        if not arguments["lines"]:
            raise ToolError(_("Een concept heeft minstens één regel nodig."))
        data.update(_line_data(arguments["lines"], existing))
    else:
        data.update(_keep_lines_data(existing))
    return _save(document, data)


def create_credit_note_draft(arguments):
    invoice = _document(arguments, kind="invoice", status="issued")
    credit_note = create_credit_note(invoice)
    return _detail(Document.objects.with_payment_totals().get(pk=credit_note.pk))


# --- Expenses ---


def _expense_line(line: dict) -> adding.Line:
    """A line as the expense page takes it. The category by its name, in
    any case: a name that isn't there yet makes a new category when the
    expense is saved, as typing one on the expense page does."""
    return adding.Line(
        description=str(line.get("description") or ""),
        amount=str(line.get("amount", "")),
        vat_info=None if line.get("vat_info") is None else str(line["vat_info"]),
        category=None,
        vat_rate=None if line.get("vat_rate") is None else str(line["vat_rate"]),
        new_category=str(line.get("category") or ""),
    )


def _expense_lines(arguments, *, required: bool) -> list[adding.Line] | None:
    lines = arguments.get("lines")
    if lines is None and not required:
        return None
    if not lines or not all(isinstance(line, dict) for line in lines):
        raise ToolError(_("Vul minstens één regel in met een bedrag."))
    return [_expense_line(line) for line in lines]


def _expense_answer(expense: Expense, categories_before: set[int]) -> dict:
    lines = list(expense.lines.select_related("category"))
    new = sorted(
        {line.category.name for line in lines if line.category_id not in (None, *categories_before)}
    )
    return {
        "id": expense.pk,
        "date": _date(expense.date),
        "supplier": expense.supplier,
        "description": expense.description,
        "lines": [
            {
                "description": line.description,
                "amount": _amount(line.amount_cents),
                "vat_info": None if line.vat_info_cents is None else _amount(line.vat_info_cents),
                "vat_rate": line.vat_rate or None,
                "category": line.category.name if line.category else None,
            }
            for line in lines
        ],
        "amount": _amount(expense.amount_cents),
        # Made for this expense: the user may want to know.
        "new_categories": new,
        "to_check": expense.needs_review,
        # The page to change it or add the receipt, after Huismus's address.
        "path": reverse("expenses:edit", kwargs={"pk": expense.pk}),
    }


def _category_ids() -> set[int]:
    return set(ExpenseCategory.objects.values_list("pk", flat=True))


def add_expense(arguments):
    """Validates and saves like "Opslaan" on the expense page, through
    expenses.adding, as Huismus does with a receipt it read itself."""
    _part_shown(
        EXPENSES,
        _(
            "Uitgaven staat uit bij Instellingen › Menu. "
            "Zet het daar aan om een uitgave of categorie toe te voegen."
        ),
    )
    lines = _expense_lines(arguments, required=True)
    receipt = None
    if arguments.get("receipt_id") is not None:
        receipt = _tray_receipt(arguments["receipt_id"])
    before = _category_ids()
    try:
        saved = adding.add_expense(
            date=arguments.get("date") or timezone.localdate().isoformat(),
            supplier=arguments.get("supplier") or "",
            description=arguments.get("description") or "",
            lines=lines,
            receipt=receipt,
        )
    except adding.NotAdded as error:
        raise ToolError(str(error)) from error
    return {
        **_expense_answer(saved, before),
        "receipt": _("Het bonnetje zit eraan vast.")
        if receipt
        else _("Een bonnetje voeg je toe in Huismus, bij de uitgave."),
    }


def _expense(arguments, name="id") -> Expense:
    expense_id = arguments.get(name)
    expense = Expense.objects.filter(pk=expense_id).first() if isinstance(expense_id, int) else None
    if expense is None:
        raise ToolError(_("Deze uitgave bestaat niet in Huismus."))
    return expense


def update_expense(arguments):
    expense = _expense(arguments)
    lines = _expense_lines(arguments, required=False)
    before = _category_ids()
    try:
        saved = adding.change_expense(
            expense,
            date=arguments.get("date"),
            supplier=arguments.get("supplier"),
            description=arguments.get("description"),
            lines=lines,
        )
    except adding.NotAdded as error:
        raise ToolError(str(error)) from error
    return _expense_answer(saved, before)


def attach_receipt(arguments):
    expense = _expense(arguments, "expense_id")
    receipt = _tray_receipt(arguments.get("receipt_id"))
    try:
        adding.attach_receipt(expense, receipt)
    except adding.NotAdded as error:
        raise ToolError(str(error)) from error
    expense.refresh_from_db()
    # Attaching makes no category: every one of its lines was there before.
    answer = _expense_answer(expense, _category_ids())
    del answer["new_categories"]
    return {**answer, "receipt": receipt.filename}


def delete_expense_tool(arguments):
    expense = _expense(arguments)
    # Read before deleting: afterwards the expense has no id.
    answer = {"id": expense.pk, "deleted": True}
    adding.delete_expense(expense)
    return answer


# --- Categories (Uitgaven → Categorieën) ---


def _category(arguments) -> ExpenseCategory:
    category_id = arguments.get("id")
    category = (
        ExpenseCategory.objects.filter(pk=category_id).first()
        if isinstance(category_id, int)
        else None
    )
    if category is None:
        raise ToolError(_("Deze categorie bestaat niet in Huismus."))
    return category


def _save_category(form) -> dict:
    """As the row on Categorieën: ExpenseCategoryForm, an empty sort order
    puts it at the bottom."""
    if not form.is_valid():
        raise ToolError(form_messages.as_text(form))
    category = form.save()
    return {
        "id": category.pk,
        "name": category.name,
        "path": reverse("expenses:category_list"),
    }


def add_category(arguments):
    _part_shown(
        EXPENSES,
        _(
            "Uitgaven staat uit bij Instellingen › Menu. "
            "Zet het daar aan om een uitgave of categorie toe te voegen."
        ),
    )
    return _save_category(ExpenseCategoryForm({"name": arguments.get("name") or ""}))


def rename_category(arguments):
    category = _category(arguments)
    form = ExpenseCategoryForm(
        {"name": arguments.get("name") or "", "sort_order": category.sort_order},
        instance=category,
    )
    return _save_category(form)


def delete_category_tool(arguments):
    category = _category(arguments)
    answer = {"id": category.pk, "name": category.name, "deleted": True}
    try:
        adding.delete_category(category)
    except adding.CategoryInUse as refusal:
        raise ToolError(str(refusal)) from refusal
    return answer


# --- Deleting: what goes ---


def preview_delete(arguments):
    """What delete_draft, delete_expense or delete_category will remove."""
    what = arguments.get("what")
    if what == "draft":
        document = _deletable_draft(arguments)
        return {
            "action": "delete_draft",
            "id": document.pk,
            "kind": document.kind,
            "customer": contact_name(document),
            "total": _amount(document.total_cents),
            "after": _("Het concept heeft nog geen nummer. Het gaat weg en komt niet terug."),
        }
    if what == "expense":
        expense = _expense(arguments)
        receipts_with_it = expense.attachments.count()
        found = {
            "action": "delete_expense",
            "id": expense.pk,
            "date": _date(expense.date),
            "supplier": expense.supplier,
            "amount": _amount(expense.amount_cents),
            "attachments": receipts_with_it,
        }
        notes = []
        if receipts_with_it:
            notes.append(_("Het bonnetje gaat mee weg. Dat is je bewijs van de uitgave."))
        if hasattr(expense, "bank_transaction"):
            notes.append(_("De afschrijving op de bank staat daarna weer bij Te doen."))
        found["after"] = " ".join(str(note) for note in notes) or _(
            "De uitgave gaat weg en komt niet terug."
        )
        return found
    if what == "category":
        category = _category(arguments)
        used = Expense.objects.filter(lines__category=category).distinct().count()
        if used:
            raise ToolError(str(adding.CATEGORY_IN_USE))
        return {"action": "delete_category", "id": category.pk, "name": category.name}
    raise ToolError(_("Verwijderen kan bij een concept, een uitgave of een categorie."))


# --- Contacts ---

CONTACT_FIELDS = tuple(ContactForm._meta.fields)


def _any_contact(arguments) -> Contact:
    """A contact, archived or not: for changing or archiving it."""
    contact_id = arguments.get("id")
    contact = Contact.objects.filter(pk=contact_id).first() if isinstance(contact_id, int) else None
    if contact is None:
        raise ToolError(_("Deze klant staat niet in Huismus."))
    return contact


def _contact_answer(contact: Contact) -> dict:
    return {
        "id": contact.pk,
        "name": contact.display_name,
        "customer_number": contact.customer_number,
        "archived": contact.archived,
        **{name: getattr(contact, name) for name in CONTACT_FIELDS},
        "path": reverse("contacts:edit", kwargs={"pk": contact.pk}),
    }


def _save_contact(form) -> dict:
    """As Opslaan on the customer page: ContactForm, which gives a new
    customer the next customer number. Contact persons stay as they are."""
    if not form.is_valid():
        raise ToolError(form_messages.as_text(form))
    return _contact_answer(form.save())


def add_contact(arguments):
    data = {name: arguments[name] for name in CONTACT_FIELDS if name in arguments}
    return _save_contact(ContactForm({name: str(value) for name, value in data.items()}))


def update_contact(arguments):
    contact = _any_contact(arguments)
    # The form as the page shows it, posted back with the changes: what
    # the assistant leaves out stays as it is.
    form = ContactForm(instance=contact)
    data = {name: form[name].value() for name in form.fields}
    data = {name: "" if value is None else value for name, value in data.items()}
    data.update({name: str(arguments[name]) for name in CONTACT_FIELDS if name in arguments})
    return _save_contact(ContactForm(data, instance=contact))


def archive_contact(arguments):
    """As Archiveren and Dearchiveren on the customer page
    (contacts.views.contact_archive_toggle), with the wanted state."""
    contact = _any_contact(arguments)
    contact.archived = bool(arguments.get("archived", True))
    contact.save()
    return _contact_answer(contact)


# --- Bank: the buttons of the bank page (bank.views, bank.reading) ---


def _bank_transaction(arguments) -> BankTransaction:
    line_id = arguments.get("id")
    line = BankTransaction.objects.filter(pk=line_id).first() if isinstance(line_id, int) else None
    if line is None:
        raise ToolError(_("Deze bankregel staat niet in Huismus."))
    return line


def _chosen(line, arguments):
    """The invoice (money in) or expense (money out) the assistant chose,
    as the page's choice; None when it chose nothing."""
    if line.is_outgoing:
        if arguments.get("expense_id") is None:
            return None
        return _expense(arguments, "expense_id")
    if arguments.get("invoice_id") is None:
        return None
    return _document({"id": arguments["invoice_id"]}, kind="invoice", status="issued")


def _proposal(line):
    if line.state != BankTransaction.State.PROPOSED:
        return None
    return line.proposed_expense if line.is_outgoing else line.proposed_document


def preview_bank_booking(arguments):
    """What confirm_bank_match, book_bank_line or undo_bank_booking will do
    with this line, decided in this order: a booked line can only be
    undone; a waiting line is booked on the invoice or expense given, or
    else on Huismus's proposal; anything else (skipped) is refused."""
    line = _bank_transaction(arguments)
    found = {"line": _bank_line(line)}
    if line.can_undo:
        if line.is_outgoing:
            return {
                **found,
                "action": "undo_bank_booking",
                "expense_id": line.expense_id,
                "after": _(
                    "Alleen de koppeling gaat weg. De uitgave blijft staan en de "
                    "afschrijving staat weer bij Te doen."
                ),
            }
        invoice = Document.objects.with_payment_totals().get(pk=line.payment.document_id)
        return {
            **found,
            "action": "undo_bank_booking",
            "invoice": {"id": invoice.pk, "number": invoice.number},
            "payment_removed": _amount(line.payment.amount_cents),
            "outstanding_after": _amount(invoice.outstanding_cents + line.payment.amount_cents),
            "after": _("De betaling gaat van de factuur af. De regel staat weer bij Te doen."),
        }
    if not BankTransaction.objects.waiting().filter(pk=line.pk).exists():
        raise ToolError(_("Deze bankregel staat niet bij Te doen."))
    target = _chosen(line, arguments)
    action = "book_bank_line"
    if target is None:
        target = _proposal(line)
        action = "confirm_bank_match"
    if target is None:
        raise ToolError(_NO_CHOICE[line.is_outgoing])
    if line.is_outgoing:
        return {
            **found,
            "action": action,
            "expense": {
                "id": target.pk,
                "date": _date(target.date),
                "supplier": target.supplier,
                "amount": _amount(target.amount_cents),
            },
        }
    invoice = Document.objects.with_payment_totals().get(pk=target.pk)
    return {
        **found,
        "action": action,
        "invoice": {
            "id": invoice.pk,
            "number": invoice.number,
            "customer": contact_name(invoice),
            "outstanding_now": _amount(invoice.outstanding_cents),
        },
        **_after_payment(invoice, line.amount_cents),
    }


# The page's own words when nothing is chosen (bank.views.book).
_NO_CHOICE = {True: gettext_lazy("Kies een uitgave."), False: gettext_lazy("Kies een factuur.")}
_ALREADY = {
    True: gettext_lazy("Deze afschrijving of uitgave is al geboekt."),
    False: gettext_lazy("Deze bijschrijving is al geboekt."),
}


def _book_to(line, target) -> dict:
    """As the page's _book and _link, with the page's words for a refusal.
    bank.reading refuses with ValueError: a line that is booked already, or
    an expense with a bank line already. Its other refusals (a line in the
    wrong direction, an invoice not issued) can't happen here: _chosen and
    _proposal pick by direction, and _chosen only takes an issued invoice."""
    try:
        if line.is_outgoing:
            bank_reading.link_expense(line, target)
        else:
            bank_reading.book(line, target)
    except ValueError as refusal:
        raise ToolError(str(_ALREADY[line.is_outgoing])) from refusal
    line.refresh_from_db()
    return {**_booked_line(line), "path": reverse("bank:statement")}


def confirm_bank_match(arguments):
    line = _bank_transaction(arguments)
    target = _proposal(line)
    if target is None:
        raise ToolError(
            _("Huismus heeft voor deze regel geen voorstel. Kies een factuur of uitgave.")
        )
    return _book_to(line, target)


def book_bank_line(arguments):
    line = _bank_transaction(arguments)
    target = _chosen(line, arguments)
    if target is None:
        raise ToolError(str(_NO_CHOICE[line.is_outgoing]))
    return _book_to(line, target)


def skip_bank_line(arguments):
    line = _bank_transaction(arguments)
    try:
        bank_reading.skip(line)
    except ValueError as refusal:
        raise ToolError(_("Deze bankregel staat niet bij Te doen.")) from refusal
    line.refresh_from_db()
    return {**_bank_line(line), "state": str(line.get_state_display())}


def restore_bank_line(arguments):
    line = _bank_transaction(arguments)
    try:
        bank_reading.unskip(line)
    except ValueError as refusal:
        raise ToolError(_("Deze bankregel is niet overgeslagen.")) from refusal
    line.refresh_from_db()
    return {**_bank_line(line), "state": str(line.get_state_display())}


def undo_bank_booking(arguments):
    line = _bank_transaction(arguments)
    try:
        bank_reading.undo(line)
    except ValueError as refusal:
        raise ToolError(_("Deze betaling was al teruggedraaid.")) from refusal
    line.refresh_from_db()
    return {**_bank_line(line), "state": str(line.get_state_display())}


# --- Confirm ---


def _kor_line(document, subtotal_cents) -> str | None:
    """The issue dialog's KOR-limit line (huismus/templates/documents/
    _issue_summary.html), with the same texts."""
    if document.kind != "invoice":
        return None
    issue_date = document.issue_date or timezone.localdate()
    crossed = kor_limit_crossed_by(issue_date.year, subtotal_cents)
    if crossed is None:
        return None
    values = {
        "revenue": _amount(crossed.revenue_cents),
        "limit": _amount(crossed.limit_cents),
        "percent": crossed.percent,
    }
    if crossed.level == "over":
        return (
            _("Met deze factuur kom je op %(revenue)s, boven je KOR-grens van %(limit)s.") % values
        )
    return (
        _("Met deze factuur kom je op %(revenue)s: %(percent)s%% van je KOR-grens van %(limit)s.")
        % values
    )


def preview_issue(arguments):
    document = _document(arguments, status="draft")
    settings = Settings.load()
    # As issue() will compute them, like the issue dialog in the editor.
    totals = compute_totals(document.lines.all(), prices_include_vat=document.prices_include_vat)
    issue_date = document.issue_date or timezone.localdate()
    year = issue_date.year if settings.number_reset_yearly else None
    if document.kind == "quote":
        after = _(
            "Daarna kun je hem mailen of de PDF downloaden. De offerte kun je daarna nog aanpassen."
        )
        action = "send_quote"
    else:
        after = _(
            "Daarna ligt het document vast en kun je het niet meer verwijderen. "
            "Corrigeren doe je met een creditnota."
        )
        action = "issue_document"
    return {
        "action": action,
        "id": document.pk,
        "kind": document.kind,
        "customer": contact_name(document),
        "total": _amount(totals.total_cents),
        "number": peek_number_for(document, settings, year),
        "issue_date": _date(issue_date),
        "after": after,
        "kor_limit": _kor_line(document, totals.subtotal_cents),
    }


def issue_document(arguments):
    document = _document(arguments, kind__in=["invoice", "credit_note"], status="draft")
    try:
        issue(document)
    except IssueError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _detail(Document.objects.with_payment_totals().get(pk=document.pk))


def send_quote_tool(arguments):
    document = _document(arguments, kind="quote", status="draft")
    try:
        send_quote(document)
    except QuoteError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _detail(Document.objects.with_payment_totals().get(pk=document.pk))


def _mailable(arguments) -> tuple[Document, str, str, str]:
    document = _document(arguments)
    if document.status not in MAILABLE_STATUSES[document.kind]:
        raise ToolError(
            _(
                "Alleen een uitgegeven factuur of creditnota, of een verzonden offerte, "
                "kun je mailen."
            )
        )
    _mail_ready(document)
    to = default_recipients(document)
    if not to:
        raise ToolError(_("Deze klant heeft geen e-mailadres in Huismus."))
    subject, body = default_message(document)
    return document, to, subject, body


def _mail_ready(document):
    """Mailing is set up, and the customer has an address."""
    business = Settings.load()
    if smtp.password_is_missing(business):
        raise ToolError(
            _(
                "Je mailwachtwoord ontbreekt in Huismus. Vul het in bij Instellingen → Mailen. "
                "Een back-up neemt het niet mee."
            )
        )
    if not smtp.is_configured(business):
        raise ToolError(
            _("Mailen is nog niet ingesteld. Dat doe je in Huismus, onder Instellingen → Mailen.")
        )
    if not default_recipients(document):
        raise ToolError(_("Deze klant heeft geen e-mailadres in Huismus."))


def preview_mail(arguments):
    document, to, subject, _body = _mailable(arguments)
    return {
        "action": "mail_document",
        "id": document.pk,
        "number": document.number,
        "to": to,
        "subject": subject,
        "attachment": f"{document.number}.pdf",
    }


def mail_document(arguments):
    document, to, subject, body = _mailable(arguments)
    log = send_document(document, to=[to], subject=subject, body=body, bcc_self=False)
    if not log.succeeded:
        raise ToolError(f"{log.plain_error} {log.error}")
    return {"id": document.pk, "number": document.number, "to": to, "sent": True}


# --- Documents: payments, reminders, quotes, copies, deleting, reopening ---


def _invoice_for_payment(arguments) -> Document:
    return _document(arguments, kind="invoice", status="issued")


def _payment_form(arguments) -> PaymentForm:
    """The form of "Betaling registreren", as the user fills it in."""
    form = PaymentForm(
        {
            "paid_on": arguments.get("paid_on") or timezone.localdate().isoformat(),
            "amount_cents": str(arguments.get("amount", "")),
            "method": arguments.get("method") or PAYMENT_METHOD_CHOICES[0][0],
            "note": arguments.get("note") or "",
        }
    )
    if not form.is_valid():
        raise ToolError(form_messages.as_text(form))
    return form


def _after_payment(invoice, cents) -> dict:
    left = invoice.outstanding_cents - cents
    if left < 0:
        return {"overpaid": _amount(-left)}
    return {"outstanding_after": _amount(left)}


def preview_payment(arguments):
    invoice = _invoice_for_payment(arguments)
    form = _payment_form(arguments)
    cents = form.cleaned_data["amount_cents"]
    return {
        "action": "record_payment",
        "id": invoice.pk,
        "number": invoice.number,
        "customer": contact_name(invoice),
        "amount": _amount(cents),
        "paid_on": _date(form.cleaned_data["paid_on"]),
        "method": form.cleaned_data["method"],
        "outstanding_now": _amount(invoice.outstanding_cents),
        **_after_payment(invoice, cents),
    }


def record_payment_tool(arguments):
    invoice = _invoice_for_payment(arguments)
    record_payment(invoice, _payment_form(arguments))
    return {
        **_detail(Document.objects.with_payment_totals().get(pk=invoice.pk)),
        "path": reverse("documents:edit", kwargs={"pk": invoice.pk}),
    }


def _reminder(arguments) -> tuple[Document, str, str, str]:
    """As the button Herinnering sturen: only an invoice that is overdue
    (documents.views.document_reminder), then the same checks as mailing."""
    invoice = _document(arguments, kind="invoice", status="issued")
    if invoice.days_overdue is None:
        raise ToolError(
            _("Factuur %(number)s is niet te laat. Er is geen herinnering gestuurd.")
            % {"number": invoice.number}
        )
    _mail_ready(invoice)
    subject, body = default_message(invoice, reminder=True)
    return invoice, default_recipients(invoice), subject, body


def preview_reminder(arguments):
    invoice, to, subject, _body = _reminder(arguments)
    return {
        "action": "send_reminder",
        "id": invoice.pk,
        "number": invoice.number,
        "to": to,
        "subject": subject,
        "outstanding": _amount(invoice.outstanding_cents),
        "days_overdue": invoice.days_overdue,
        "attachment": f"{invoice.number}.pdf",
    }


def send_reminder(arguments):
    invoice, to, subject, body = _reminder(arguments)
    log = send_document(invoice, to=[to], subject=subject, body=body, bcc_self=False, reminder=True)
    if not log.succeeded:
        raise ToolError(f"{log.plain_error} {log.error}")
    return {"id": invoice.pk, "number": invoice.number, "to": to, "sent": True}


QUOTE_ANSWERS = {"accepted": accept_quote, "declined": decline_quote, "expired": expire_quote}


def answer_quote(arguments):
    quote = _document(arguments, kind="quote")
    answer = QUOTE_ANSWERS.get(arguments.get("answer"))
    if answer is None:
        raise ToolError(_("Een offerte is geaccepteerd, afgewezen of verlopen."))
    try:
        answer(quote)
    except QuoteError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _detail(Document.objects.with_payment_totals().get(pk=quote.pk))


def _with_path(document) -> dict:
    url = "quotes:edit" if document.kind == "quote" else "documents:edit"
    return {
        **_detail(Document.objects.with_payment_totals().get(pk=document.pk)),
        "path": reverse(url, kwargs={"pk": document.pk}),
    }


def convert_quote(arguments):
    try:
        invoice = convert_to_invoice(_document(arguments, kind="quote"))
    except QuoteError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _with_path(invoice)


def copy_document_tool(arguments):
    return _with_path(copy_document(_document(arguments, kind__in=["invoice", "quote"])))


def _deletable_draft(arguments) -> Document:
    document = _document(arguments, status="draft")
    if not deletable_drafts().filter(pk=document.pk).exists():
        raise ToolError(
            _(
                "Dit concept heeft al een nummer, dus het kan niet weg. "
                "Zet het terug of geef het opnieuw uit."
            )
        )
    return document


def delete_draft_tool(arguments):
    document = _deletable_draft(arguments)
    answer = {"id": document.pk, "kind": document.kind, "deleted": True}
    delete_draft(document)
    return answer


def _reopenable(arguments) -> Document:
    return _document(arguments, kind__in=["invoice", "credit_note"])


def preview_reopen(arguments):
    """What Toch bewerken, or undoing it, will do, in the words of the
    detail page's dialog."""
    document = _reopenable(arguments)
    found = {"id": document.pk, "kind": document.kind, "number": document.number or None}
    if document.status == "issued":
        if document.kind == "credit_note":
            advice = _(
                "%(number)s is uitgegeven. Een uitgegeven creditnota corrigeer je meestal "
                "met een nieuw document: dan blijft wat je klant kreeg zoals het was, en "
                "staat de correctie er apart naast."
            )
        else:
            advice = _(
                "%(number)s is uitgegeven. Een uitgegeven factuur corrigeer je meestal "
                "met een creditnota: dan blijft wat je klant kreeg zoals het was, en "
                "staat de correctie er apart naast."
            )
        return {
            **found,
            "action": "reopen_document",
            "advice": advice % {"number": document.number},
            "after": _(
                "Hij is weer een concept, met hetzelfde nummer. Pas aan wat nodig is "
                "en geef hem opnieuw uit."
            ),
        }
    if document.before_reopening is None:
        raise ToolError(str(NOTHING_TO_UNDO))
    return {
        **found,
        "action": "undo_reopen",
        "after": _(
            "Wat je sinds Toch bewerken veranderde, gaat weg. Het document staat weer "
            "zoals je klant het kreeg."
        ),
    }


def reopen_document(arguments):
    document = _reopenable(arguments)
    try:
        reopen(document)
    except ReopenError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _with_path(document)


def undo_reopen_tool(arguments):
    document = _reopenable(arguments)
    if document.status != "draft":
        raise ToolError(str(NOTHING_TO_UNDO))
    try:
        undo_reopen(document)
    except ReopenError as refusal:
        raise ToolError(str(refusal)) from refusal
    return _with_path(document)


# --- The list ---

_ID = {"id": {"type": "integer", "description": "The document's id in Huismus."}}


def _id_of(what: str) -> dict:
    return {"id": {"type": "integer", "description": f"The {what}'s id in Huismus."}}


_YEAR = {"year": {"type": "integer", "description": "Calendar year; default: this year."}}
_LIMIT = {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Default 20."}}
_DATE = {"type": "string", "format": "date", "description": "YYYY-MM-DD"}
_PAYMENT = {
    "id": {"type": "integer", "description": "The issued invoice's id."},
    "amount": {"type": ["string", "number"], "description": 'In euros, for example "1.250,00".'},
    "paid_on": {**_DATE, "description": "YYYY-MM-DD; default: today."},
    "method": {"type": "string", "enum": [value for value, _label in PAYMENT_METHOD_CHOICES]},
    "note": {"type": "string"},
}
_LINES = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "quantity": {
                "type": ["number", "string", "null"],
                "description": "Leave out for a fixed price: the unit price is the line total.",
            },
            "unit": {"type": "string", "description": "For example uur, stuk."},
            "unit_price": {
                "type": ["string", "number"],
                "description": (
                    'In euros, for example "85" or "1.250,00". Without VAT, unless the '
                    "document has prices_include_vat: then including VAT."
                ),
            },
            "vat_percent": {
                "type": "integer",
                "enum": [0, 9, 21],
                "description": (
                    "Omit to use the default: 21 when the KOR is off, 0 when it is on. "
                    "With the KOR on, only 0 is allowed."
                ),
            },
        },
        "required": ["description", "unit_price"],
        "additionalProperties": False,
    },
}
_EXPENSE_LINES = {
    "type": "array",
    "minItems": 1,
    "items": {
        "type": "object",
        "properties": {
            "description": {"type": "string"},
            "amount": {
                "type": ["string", "number"],
                "description": 'Gross, in euros, for example "42,35".',
            },
            "vat_info": {
                "type": ["string", "number", "null"],
                "description": "The VAT on the receipt, for information "
                "only. Required when the user doesn't use the KOR; 0 when "
                "the receipt shows no VAT.",
            },
            "vat_rate": {
                "type": ["string", "null"],
                "enum": [*VatRate.values, None],
                "description": "The VAT rate on the receipt: 21, 9, 0 (0% or "
                "no VAT), or reverse charged by a supplier in the Netherlands "
                "(reverse_nl), another EU country (reverse_eu) or outside the "
                "EU (reverse_non_eu). Required when the user doesn't use the "
                "KOR; never guess it.",
            },
            "category": {
                "type": "string",
                "description": "A category by its name (list_categories); a "
                "new name makes a new category. Omit for none.",
            },
        },
        "required": ["amount"],
        "additionalProperties": False,
    },
}
_EXPENSE_FIELDS = {
    "date": {**_DATE, "description": "YYYY-MM-DD; default: today."},
    "supplier": {"type": "string"},
    "description": {"type": "string"},
}
_CONTACT_FIELDS = {
    name: {"type": "integer"} if name == "payment_terms_days" else {"type": "string"}
    for name in CONTACT_FIELDS
}
_CONTACT_FIELDS["delivery_method"] = {
    "type": "string",
    "enum": [value for value, _label in Contact._meta.get_field("delivery_method").choices] + [""],
}
_BANK_LINE = {"id": {"type": "integer", "description": "The bank line's id, from list_bank."}}
_BANK_TARGET = {
    "invoice_id": {"type": "integer", "description": "Money in: an issued invoice's id."},
    "expense_id": {"type": "integer", "description": "Money out: an expense's id."},
}
_DRAFT_FIELDS = {
    "reference": {"type": "string", "description": "The customer's own reference (kenmerk)."},
    "issue_date": _DATE,
    "due_date": {**_DATE, "description": "YYYY-MM-DD; default: from the payment terms."},
    "expiry_date": {**_DATE, "description": "Quotes only: valid until, YYYY-MM-DD."},
    "language": {"type": "string", "enum": ["nl", "en"]},
    "intro_text": {"type": "string"},
    "footer_text": {"type": "string"},
    "notes": {"type": "string", "description": "Internal notes, not on the PDF."},
}

TOOLS = (
    Tool(
        "get_overview",
        gettext_lazy("Overzicht bekijken"),
        "read",
        "Revenue for a year, open and overdue invoices, how revenue compares with the "
        "KOR limit the user set (when the KOR is on), and to_do: what waits for the user "
        "now, as the list Te doen on Huismus's Overzicht shows it (bank lines, overdue "
        "invoices, quotes waiting for an answer, drafts, receipts and expenses to check). "
        "path is the place in Huismus, after Huismus's address.",
        _YEAR,
        (),
        get_overview,
    ),
    Tool(
        "search_documents",
        gettext_lazy("Documenten zoeken"),
        "read",
        "Find invoices, credit notes and quotes, newest first. query matches the number "
        "or the customer's name.",
        {
            "kind": {"type": "string", "enum": ["invoice", "credit_note", "quote"]},
            "status": {"type": "string", "enum": list(STATUS_FILTERS)},
            "query": {"type": "string"},
            "contact_id": {"type": "integer"},
            **_YEAR,
            **_LIMIT,
        },
        (),
        search_documents,
    ),
    Tool(
        "get_document",
        gettext_lazy("Document openen"),
        "read",
        "One invoice, credit note or quote with its lines, totals and payment state.",
        _ID,
        ("id",),
        get_document,
    ),
    Tool(
        "search_contacts",
        gettext_lazy("Klanten zoeken"),
        "read",
        "Find customers by name, e-mail or city, archived ones left out. Their id is what "
        "create_draft needs. A new customer is made with add_contact.",
        {"query": {"type": "string"}, **_LIMIT},
        (),
        search_contacts,
    ),
    Tool(
        "list_expenses",
        gettext_lazy("Uitgaven bekijken"),
        "read",
        "The expenses of a year (gross amounts) and the year's costs in total: gross, "
        "or without VAT when total_without_vat is true, with input_vat apart.",
        _YEAR,
        (),
        list_expenses,
    ),
    Tool(
        "get_vat_return",
        gettext_lazy("Btw-aangifte bekijken"),
        "read",
        "The VAT return report of a period, as on Huismus's page Rapporten > Btw-aangifte: "
        "revenue and VAT per box, 5a, 5b (with the reverse charged part apart), and to_pay "
        "or to_get_back. period is a quarter (2026-Q3), a month (2026-07) or a year (2026); "
        "default, and for a period that hasn't begun, the last finished quarter: check "
        "period in the answer. Pass the boxes on as they are: don't move amounts between "
        "boxes or fill in boxes Huismus doesn't give. not_counted lists what Huismus could "
        "not put in a box; always tell the user when it isn't empty (documents open with "
        "get_document, expenses are in list_expenses). Huismus files nothing: the user "
        "copies the amounts into their return. With the KOR on there are no figures, only "
        "note.",
        {
            "period": {
                "type": "string",
                "description": "2026-Q3, 2026-07 or 2026; default: the last finished quarter.",
            }
        },
        (),
        get_vat_return,
    ),
    Tool(
        "get_year_overview",
        gettext_lazy("Jaaroverzicht bekijken"),
        "read",
        "The year overview, as on Huismus's page Rapporten > Jaaroverzicht: revenue (without "
        "VAT), costs, profit, per quarter and costs per category. costs_label says what the "
        "costs are: gross, or without VAT when costs_without_vat is true, with input_vat "
        "apart. Pass the amounts on as they are.",
        _YEAR,
        (),
        get_year_overview,
    ),
    Tool(
        "list_bank",
        gettext_lazy("Bank bekijken"),
        "read",
        "The bank page: the lines of the bank statements the user read in. to_do: lines that "
        "fit an invoice (money in) or an expense (money out), with Huismus's proposal, or "
        "choices when the user must pick. booked: the latest statement's booked lines. "
        "not_recognised: lines that fit nothing, often private money; nothing to do. "
        "Huismus reads statements only when the user reads one in, on that page. "
        "limit applies to not_recognised only.",
        {**_LIMIT},
        (),
        list_bank,
    ),
    Tool(
        "list_categories",
        gettext_lazy("Categorieën bekijken"),
        "read",
        "The expense categories, with how many expenses each has. add_expense takes a "
        "category by its name.",
        {},
        (),
        list_categories,
    ),
    Tool(
        "get_document_pdf",
        gettext_lazy("PDF van een document"),
        "read",
        "The PDF of an invoice, credit note or quote, as an attachment you can show the "
        "user. For an issued or sent document it is the PDF the customer gets: made_by "
        "says whether it is the original from the import or made by Huismus. A draft "
        "gives a preview marked VOORBEELD (preview is true): never present it as the "
        "invoice.",
        _ID,
        ("id",),
        get_document_pdf,
    ),
    Tool(
        "get_settings",
        gettext_lazy("Instellingen bekijken"),
        "read",
        "The settings an assistant needs: whether the KOR is on, or no VAT for another "
        "reason, the default language, currency, payment terms, the next numbers if "
        "issued now (nothing is reserved) and whether mailing is set up. Addresses, "
        "registration numbers, the bank account, passwords and keys are not given.",
        {},
        (),
        get_settings,
    ),
    Tool(
        "list_receipts",
        gettext_lazy("Bonnetjes zonder uitgave bekijken"),
        "read",
        "The receipts that wait for an expense: Huismus fetched them from the user's "
        "receipts folder. To process them: read each with read_receipt, then add_expense "
        "with its receipt_id. One receipt is one expense. vat_required is true when the "
        "user doesn't use the KOR: each line then needs the VAT and its rate from the "
        "receipt.",
        {},
        (),
        list_receipts,
    ),
    Tool(
        "read_receipt",
        gettext_lazy("Bonnetje lezen"),
        "read",
        "One receipt without an expense: a photo or a scanned page as an image, and the "
        f"text of a PDF's first {receipts.MAX_PAGES} pages. Read date, supplier, what was "
        "bought, the total paid (gross) and the VAT as the receipt shows it. "
        "Never guess an amount or VAT. "
        "When vat_required is true and the VAT or its rate isn't on the receipt or can't "
        "be read, "
        "don't fill in 0: skip the receipt. Otherwise leave vat_info out when the receipt "
        "shows none. Skip it too when it isn't a receipt or holds more than one. Tell "
        "the user which you skipped and why; they stay in Huismus. Before adding, check "
        "list_expenses for one with the same date and amount, and ask the user when "
        "there is.",
        _ID,
        ("id",),
        read_receipt,
    ),
    Tool(
        "add_expense",
        gettext_lazy("Uitgave toevoegen"),
        "add",
        "Add an expense: what the user paid, as gross amounts (including any VAT). "
        "With receipt_id, the receipt from list_receipts goes onto the expense; other "
        "receipts the user adds in Huismus, at path. "
        "Huismus marks it 'to check' until the user says it's right there. "
        "A category name that isn't there yet makes a new category: new_categories in the "
        "answer names them, tell the user.",
        {
            **_EXPENSE_FIELDS,
            "lines": _EXPENSE_LINES,
            "receipt_id": {
                "type": "integer",
                "description": "A receipt from list_receipts that this expense is for.",
            },
        },
        ("lines",),
        add_expense,
    ),
    Tool(
        "update_expense",
        gettext_lazy("Uitgave wijzigen"),
        "change",
        "Change an expense through the expense page's forms. Fields left out stay as they "
        "are; lines, when given, replace all lines (same rules as add_expense). Huismus "
        "marks it 'to check' again, so the user sees the change.",
        {**_id_of("expense"), **_EXPENSE_FIELDS, "lines": _EXPENSE_LINES},
        ("id",),
        update_expense,
    ),
    Tool(
        "attach_receipt",
        gettext_lazy("Bonnetje aan uitgave hangen"),
        "change",
        "Put a receipt from list_receipts onto an expense there is. Huismus marks the "
        "expense 'to check' again. Other files the user adds in Huismus.",
        {
            "expense_id": {"type": "integer"},
            "receipt_id": {"type": "integer", "description": "A receipt from list_receipts."},
        },
        ("expense_id", "receipt_id"),
        attach_receipt,
    ),
    Tool(
        "preview_delete",
        gettext_lazy("Verwijderen voorbereiden"),
        "read",
        "What delete_draft, delete_expense or delete_category will remove, and what follows "
        "from it (a receipt goes with an expense). Show this to the user first.",
        {
            "what": {"type": "string", "enum": ["draft", "expense", "category"]},
            "id": {"type": "integer"},
        },
        ("what", "id"),
        preview_delete,
    ),
    Tool(
        "delete_expense",
        gettext_lazy("Uitgave verwijderen"),
        "confirm",
        "Delete an expense with its receipts and other attachments. Call preview_delete first.",
        _id_of("expense"),
        ("id",),
        delete_expense_tool,
    ),
    Tool(
        "add_category",
        gettext_lazy("Categorie toevoegen"),
        "change",
        "Add an expense category, at the bottom of the list.",
        {"name": {"type": "string"}},
        ("name",),
        add_category,
    ),
    Tool(
        "rename_category",
        gettext_lazy("Categorie hernoemen"),
        "change",
        "Give a category another name. Its expenses keep it.",
        {**_id_of("category"), "name": {"type": "string"}},
        ("id", "name"),
        rename_category,
    ),
    Tool(
        "delete_category",
        gettext_lazy("Categorie verwijderen"),
        "confirm",
        "Delete a category without expenses. One with expenses is refused: give them "
        "another category first. Call preview_delete first.",
        _id_of("category"),
        ("id",),
        delete_category_tool,
    ),
    Tool(
        "add_contact",
        gettext_lazy("Klant toevoegen"),
        "change",
        "Add a customer: a company name, or a first and last name. Without "
        "customer_number Huismus gives the next one.",
        _CONTACT_FIELDS,
        (),
        add_contact,
    ),
    Tool(
        "update_contact",
        gettext_lazy("Klant wijzigen"),
        "change",
        "Change a customer, archived or not. Fields left out stay as they are. Issued "
        "documents keep the details they were issued with. Contact persons the user "
        "manages in Huismus.",
        {**_id_of("customer"), **_CONTACT_FIELDS},
        ("id",),
        update_contact,
    ),
    Tool(
        "archive_contact",
        gettext_lazy("Klant archiveren"),
        "change",
        "Archive a customer (archived true) or bring one back (false). An archived "
        "customer is left out of search_contacts and of new documents; nothing is deleted.",
        {**_id_of("customer"), "archived": {"type": "boolean"}},
        ("id", "archived"),
        archive_contact,
    ),
    Tool(
        "preview_bank_booking",
        gettext_lazy("Boeking voorbereiden"),
        "read",
        "What a bank line's booking will do. For a line under to_do: with invoice_id "
        "(money in) or expense_id (money out) what book_bank_line does, without them "
        "what confirm_bank_match does with Huismus's proposal. For a booked line: what "
        "undo_bank_booking takes away. Show this to the user first.",
        {**_BANK_LINE, **_BANK_TARGET},
        ("id",),
        preview_bank_booking,
    ),
    Tool(
        "confirm_bank_match",
        gettext_lazy("Voorstel bevestigen"),
        "confirm",
        "Book a bank line under to_do as Huismus proposed: a payment on the invoice, or "
        "the link to the expense. Call preview_bank_booking first.",
        _BANK_LINE,
        ("id",),
        confirm_bank_match,
    ),
    Tool(
        "book_bank_line",
        gettext_lazy("Bankregel boeken"),
        "confirm",
        "Book a bank line under to_do on an invoice the user chose (money in: a payment) "
        "or link it to an expense (money out). Call preview_bank_booking first.",
        {**_BANK_LINE, **_BANK_TARGET},
        ("id",),
        book_bank_line,
    ),
    Tool(
        "skip_bank_line",
        gettext_lazy("Bankregel overslaan"),
        "change",
        "Move a bank line from to_do to Overgeslagen: nothing to book, for example "
        "private money. restore_bank_line brings it back.",
        _BANK_LINE,
        ("id",),
        skip_bank_line,
    ),
    Tool(
        "restore_bank_line",
        gettext_lazy("Bankregel terugzetten"),
        "change",
        "Bring a skipped bank line back to to_do.",
        _BANK_LINE,
        ("id",),
        restore_bank_line,
    ),
    Tool(
        "undo_bank_booking",
        gettext_lazy("Boeking terugdraaien"),
        "confirm",
        "Undo a booked bank line: money in loses its payment on the invoice, money out "
        "only its link (the expense stays). The line goes back to to_do. Call "
        "preview_bank_booking first.",
        _BANK_LINE,
        ("id",),
        undo_bank_booking,
    ),
    Tool(
        "create_draft",
        gettext_lazy("Concept maken"),
        "draft",
        "Make a draft invoice or quote for an existing contact. It gets no number until it "
        "is issued (invoice) or sent (quote).",
        {
            "kind": {"type": "string", "enum": ["invoice", "quote"]},
            "contact_id": {"type": "integer"},
            "lines": _LINES,
            **_DRAFT_FIELDS,
        },
        ("kind", "contact_id", "lines"),
        create_draft,
    ),
    Tool(
        "update_draft",
        gettext_lazy("Concept wijzigen"),
        "draft",
        "Change a draft invoice, quote or credit note that has no number yet. Fields left "
        "out stay as they are; lines, when given, replace all lines.",
        {**_ID, "contact_id": {"type": "integer"}, "lines": _LINES, **_DRAFT_FIELDS},
        ("id",),
        update_draft,
    ),
    Tool(
        "create_credit_note_draft",
        gettext_lazy("Creditnota-concept maken"),
        "draft",
        "Start a draft credit note for an issued invoice, with the invoice's lines (or "
        "none when it was already partly credited). Adjust it with update_draft.",
        {"id": {"type": "integer", "description": "The issued invoice's id."}},
        ("id",),
        create_credit_note_draft,
    ),
    Tool(
        "preview_issue",
        gettext_lazy("Uitgeven voorbereiden"),
        "read",
        "What issuing a draft invoice or credit note, or sending a draft quote, will do: "
        "customer, total, the number it will get, and a KOR-limit line when it applies. "
        "Show this to the user before calling issue_document or send_quote.",
        _ID,
        ("id",),
        preview_issue,
    ),
    Tool(
        "issue_document",
        gettext_lazy("Factuur uitgeven"),
        "confirm",
        "Issue a draft invoice or credit note: it gets its number and can no longer be "
        "changed or deleted. Call preview_issue first.",
        _ID,
        ("id",),
        issue_document,
    ),
    Tool(
        "send_quote",
        gettext_lazy("Offerte verzenden"),
        "confirm",
        "Mark a draft quote as sent: it gets its number. This does not mail it; use "
        "mail_document for that. Call preview_issue first.",
        _ID,
        ("id",),
        send_quote_tool,
    ),
    Tool(
        "convert_quote",
        gettext_lazy("Offerte omzetten naar factuur"),
        "draft",
        "Make a draft invoice from a quote, with its customer, lines and texts, as the "
        "button in Huismus does. The quote stays as it is.",
        _ID,
        ("id",),
        convert_quote,
    ),
    Tool(
        "copy_document",
        gettext_lazy("Kopie als concept"),
        "draft",
        "A new draft of the same kind with the customer, lines and texts of an invoice or "
        "quote, in any status. It has no number, dates or notes yet. Credit notes are not "
        "copied.",
        _ID,
        ("id",),
        copy_document_tool,
    ),
    Tool(
        "preview_payment",
        gettext_lazy("Betaling voorbereiden"),
        "read",
        "What record_payment will do with these values: the invoice, the amount, and what "
        "is outstanding after it (or overpaid). Show this to the user first.",
        _PAYMENT,
        ("id", "amount"),
        preview_payment,
    ),
    Tool(
        "record_payment",
        gettext_lazy("Betaling registreren"),
        "confirm",
        "Record a payment by hand on an issued invoice, as Betaling registreren in Huismus. "
        "Left out: paid_on is today, method is Overboeking (bank transfer); ask the user "
        "when you don't know them. "
        "A payment from the bank is booked with book_bank_line instead. Call "
        "preview_payment first.",
        _PAYMENT,
        ("id", "amount"),
        record_payment_tool,
    ),
    Tool(
        "preview_reminder",
        gettext_lazy("Herinnering voorbereiden"),
        "read",
        "Who send_reminder will mail, with what subject, for an overdue invoice. Show this "
        "to the user first.",
        _ID,
        ("id",),
        preview_reminder,
    ),
    Tool(
        "send_reminder",
        gettext_lazy("Herinnering sturen"),
        "confirm",
        "Mail a payment reminder for an overdue invoice to the customer's e-mail address, "
        "with the standard reminder text and the invoice as PDF. Call preview_reminder "
        "first.",
        _ID,
        ("id",),
        send_reminder,
        open_world=True,
    ),
    Tool(
        "answer_quote",
        gettext_lazy("Offerte beantwoorden"),
        "confirm",
        "Mark a sent quote as accepted, declined or expired. Huismus can't undo this. Show "
        "the quote with get_document first.",
        {
            **_ID,
            "answer": {"type": "string", "enum": list(QUOTE_ANSWERS)},
        },
        ("id", "answer"),
        answer_quote,
    ),
    Tool(
        "delete_draft",
        gettext_lazy("Concept verwijderen"),
        "confirm",
        "Delete a draft invoice, credit note or quote that has no number. Issued "
        "documents are never deleted. Call preview_delete first.",
        _ID,
        ("id",),
        delete_draft_tool,
    ),
    Tool(
        "preview_reopen",
        gettext_lazy("Toch bewerken voorbereiden"),
        "read",
        "What reopen_document (for an issued invoice or credit note) or undo_reopen (for "
        "one reopened before) will do, with Huismus's advice. Show this to the user first.",
        _ID,
        ("id",),
        preview_reopen,
    ),
    Tool(
        "reopen_document",
        gettext_lazy("Toch bewerken"),
        "confirm",
        "Turn an issued invoice or credit note back into a draft with the same number. "
        "The user then changes it in Huismus and issues it again; update_draft leaves a "
        "draft with a number alone. Usually a credit note is the better correction. Call "
        "preview_reopen first.",
        _ID,
        ("id",),
        reopen_document,
    ),
    Tool(
        "undo_reopen",
        gettext_lazy("Toch bewerken ongedaan maken"),
        "confirm",
        "Put a reopened invoice or credit note back exactly as it was issued. Call "
        "preview_reopen first.",
        _ID,
        ("id",),
        undo_reopen_tool,
    ),
    Tool(
        "preview_mail",
        gettext_lazy("Mailen voorbereiden"),
        "read",
        "Who mail_document will mail and with what subject. Show this to the user first.",
        _ID,
        ("id",),
        preview_mail,
    ),
    Tool(
        "mail_document",
        gettext_lazy("Document mailen"),
        "confirm",
        "Mail an issued invoice or credit note, or a sent quote, as PDF to the customer's "
        "e-mail address, with the standard text. Call preview_mail first.",
        _ID,
        ("id",),
        mail_document,
        open_world=True,
    ),
)

BY_NAME = {tool.name: tool for tool in TOOLS}
