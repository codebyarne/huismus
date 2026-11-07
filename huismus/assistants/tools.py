# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What an AI assistant can do in Huismus (SPEC.md M16; huismus-intern/besluiten.md,
2026-10-28 "Wat een AI-assistent mag" and 2026-10-30 "bouwkeuzes").

Three kinds of tool:

- "read": changes nothing. Marked read-only, so the assistant's app may
  run it without asking.
- "draft": makes or changes a draft, through the editor's own forms and
  documents.drafts.
- "add": adds an expense, through the expense page's own forms and
  expenses.lines, with a receipt from the tray if given (SPEC.md M20,
  part 2). It gets no number and the user can still change or delete it
  in the app, so it is not marked destructive.
- "confirm": issuing, sending a quote, mailing. Marked destructive and never
  read-only, so the assistant's app asks the user first; the button is the
  app's, the assistant cannot press it. Each has a preview tool before it
  that says what will happen.

Never here: contacts, changing an expense, attachments other than the
receipts without an expense, payments, a quote's answer, deleting,
"Toch bewerken". Every action goes through the same function as in the
app (issue(), send_quote(), send_document()), so numbering, totals and
immutability are checked where they always are.

Titles are gettext, shown in the default language from the settings
(assistants.views); descriptions are English, for the assistant.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Literal

from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from huismus.business import smtp
from huismus.business.kor_limit import kor_limit_crossed_by, kor_limit_status
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core import form_messages
from huismus.core.dashboard import outstanding_invoices
from huismus.core.models import Attachment
from huismus.core.templatetags.money import euros, money
from huismus.documents.drafts import (
    create_credit_note,
    document_form,
    line_formset,
    peek_number_for,
    save_draft,
)
from huismus.documents.issuing import IssueError, issue
from huismus.documents.listing import contact_name
from huismus.documents.mailing import (
    MAILABLE_STATUSES,
    default_message,
    default_recipients,
    send_document,
)
from huismus.documents.models import Document
from huismus.documents.quoting import QuoteError, send_quote
from huismus.documents.totals import compute_totals
from huismus.documents.vat import default_rate, editor_value
from huismus.expenses import adding
from huismus.expenses.models import Expense, ExpenseCategory, VatRate
from huismus.reports.year_overview import compute_year_overview

from . import receipts


class ToolError(Exception):
    """A refusal the assistant passes on to the user, not a bug."""


@dataclass(frozen=True)
class WithImages:
    """A handler's answer with images after its data: a receipt."""

    data: dict
    images: list[dict]


@dataclass(frozen=True)
class Tool:
    name: str
    title: str
    # Decides what the assistant's app asks first (see the module docstring).
    kind: Literal["read", "draft", "add", "confirm"]
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
        images = []
        if isinstance(data, WithImages):
            data, images = data.data, data.images
        text = json.dumps(data, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": text}, *images], "structuredContent": data}


# --- What the assistant gets back ---


def _amount(cents) -> str:
    """ "€ 1.815,00", without the non-breaking spaces the pages use."""
    return money(cents).replace("\u00a0", " ")


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
        "status": document.status,
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
    "sent": lambda d: d.status == "sent",
    "accepted": lambda d: d.status == "accepted",
    "declined": lambda d: d.status == "declined",
    "expired": lambda d: d.status == "expired",
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
        "vat_required": not Settings.load().kor_enabled,
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
    return WithImages(data, reading.images)


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


def create_draft(arguments):
    settings = Settings.load()
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


def _category(name, categories: list[ExpenseCategory]) -> ExpenseCategory | None:
    """An existing category by its name, in any case. No name is "Geen
    categorie", as in the app. The assistant makes no categories: the user
    keeps the list (Uitgaven → Categorieën)."""
    if not name:
        return None
    for category in categories:
        if category.name.casefold() == str(name).casefold():
            return category
    if not categories:
        raise ToolError(
            _(
                "Er zijn nog geen categorieën in Huismus. Laat de categorie weg, "
                "of maak er een onder Uitgaven → Categorieën."
            )
        )
    names = ", ".join(category.name for category in categories)
    raise ToolError(
        _("Deze categorie staat niet in Huismus. Kies een van deze: %(names)s.") % {"names": names}
    )


def add_expense(arguments):
    """Validates and saves like "Opslaan" on the expense page, through
    expenses.adding, as Huismus does with a receipt it read itself."""
    lines = arguments.get("lines")
    if not lines or not all(isinstance(line, dict) for line in lines):
        raise ToolError(_("Vul minstens één regel in met een bedrag."))
    categories = list(ExpenseCategory.objects.all())
    inputs = [
        adding.Line(
            description=str(line.get("description") or ""),
            amount=str(line.get("amount", "")),
            vat_info=None if line.get("vat_info") is None else str(line["vat_info"]),
            category=_category(line.get("category"), categories),
            vat_rate=None if line.get("vat_rate") is None else str(line["vat_rate"]),
        )
        for line in lines
    ]
    receipt = None
    if arguments.get("receipt_id") is not None:
        receipt = _tray_receipt(arguments["receipt_id"])
    try:
        saved = adding.add_expense(
            date=arguments.get("date") or timezone.localdate().isoformat(),
            supplier=arguments.get("supplier") or "",
            description=arguments.get("description") or "",
            lines=inputs,
            receipt=receipt,
        )
    except adding.NotAdded as error:
        raise ToolError(str(error)) from error
    return {
        "id": saved.pk,
        "date": _date(saved.date),
        "supplier": saved.supplier,
        "description": saved.description,
        "lines": [
            {
                "description": line.description,
                "amount": _amount(line.amount_cents),
                "vat_info": None if line.vat_info_cents is None else _amount(line.vat_info_cents),
                "vat_rate": line.vat_rate or None,
                "category": line.category.name if line.category else None,
            }
            for line in saved.lines.select_related("category")
        ],
        "amount": _amount(saved.amount_cents),
        # The page to change it or add the receipt, after Huismus's address.
        "path": reverse("expenses:edit", kwargs={"pk": saved.pk}),
        "receipt": _("Het bonnetje zit eraan vast.")
        if receipt
        else _("Een bonnetje voeg je toe in Huismus, bij de uitgave."),
    }


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
    totals = compute_totals(document.lines.all())
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
    if not smtp.is_configured(Settings.load()):
        raise ToolError(
            _("Mailen is nog niet ingesteld. Dat doe je in Huismus, onder Instellingen → Mailen.")
        )
    to = default_recipients(document)
    if not to:
        raise ToolError(_("Deze klant heeft geen e-mailadres in Huismus."))
    subject, body = default_message(document)
    return document, to, subject, body


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


# --- The list ---

_ID = {"id": {"type": "integer", "description": "The document's id in Huismus."}}
_YEAR = {"year": {"type": "integer", "description": "Calendar year; default: this year."}}
_LIMIT = {"limit": {"type": "integer", "minimum": 1, "maximum": 100, "description": "Default 20."}}
_DATE = {"type": "string", "format": "date", "description": "YYYY-MM-DD"}
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
                "description": 'In euros, for example "85" or "1.250,00".',
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
        "Revenue for a year, open and overdue invoices, and how revenue compares with the "
        "KOR limit the user set (when the KOR is on).",
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
        "Find customers by name, e-mail or city. Their id is what create_draft needs. "
        "Contacts cannot be added or changed here: the user does that in Huismus.",
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
        "Changing or deleting an expense is done in Huismus too.",
        {
            "date": {**_DATE, "description": "YYYY-MM-DD; default: today."},
            "supplier": {"type": "string"},
            "description": {"type": "string"},
            "lines": {
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
                            "description": "One of list_expenses' categories; omit for none.",
                        },
                    },
                    "required": ["amount"],
                    "additionalProperties": False,
                },
            },
            "receipt_id": {
                "type": "integer",
                "description": "A receipt from list_receipts that this expense is for.",
            },
        },
        ("lines",),
        add_expense,
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
