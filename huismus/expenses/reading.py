# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Huismus reads the receipts in the tray with the user's own AI service
(SPEC.md M20, part 3; huismus-intern/besluiten.md, 2026-11-06).

After every look of the receipts folder (expenses.inbox) and after the
service is saved, each receipt without an expense that Huismus hasn't read
yet goes to the service, one at a time, in the background. What it sends
is what the AI assistant gets from read_receipt (assistants.receipts): a
photo made smaller, a PDF's text and scans.

The model only reads; Huismus decides. It leaves a receipt in the tray,
with a reason, when the answer has no total, when the lines don't add up
to it, when a line lacks its VAT while the KOR is off (never 0 filled in),
or when an expense with the same date and amount is already there. Else it
makes the expense through expenses.adding, as the assistant's add_expense
does, marked "Nakijken".

Never paying twice for one receipt: it counts as read (Attachment.read_at)
once the service answered, whatever it said, and after a timeout, since
the service may have done the work. Every other failure (unreachable, key
refused, unknown model, busy, a server error) means the service did no
work: the receipt waits for the next look, and the page shows the failure.
"""

import datetime
import json
import logging
import re
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

from django.conf import settings
from django.db import connections
from django.template.defaultfilters import date as date_filter
from django.utils import timezone
from django.utils.translation import gettext as _

from huismus.assistants import receipts
from huismus.business.models import Settings
from huismus.core import maintenance
from huismus.core.backup import sample_data_in_use
from huismus.core.models import Attachment
from huismus.core.templatetags.money import money

from . import adding, ai_service
from .ai_service import Config, ServiceError
from .models import Expense, ExpenseCategory

# Expense.source of an expense Huismus made from a receipt it read.
SOURCE = "bonnetjes-lezen"

# Why a receipt stayed in the tray (Attachment.read_reason): stored, never
# rename these values. The first three are also the model's "kind".
UNREADABLE, NOT_A_RECEIPT, MORE_THAN_ONE = "unreadable", "not_a_receipt", "more_than_one"
NO_TOTAL, NOT_ADDING_UP, NO_VAT = "no_total", "not_adding_up", "no_vat"
SIMILAR, TIMEOUT = "similar", "timeout"

# Left out of backups, as the settings (core.backup skips ai_service.FILE_PREFIX).
STATUS_FILE_NAME = f"{ai_service.FILE_PREFIX}-status.json"

_status_lock = threading.Lock()
# One reading at a time.
_read_lock = threading.Lock()
logger = logging.getLogger("huismus.receipts")


# -- Status -----------------------------------------------------------------------


@dataclass
class Status:
    last_success: str = ""  # ISO timestamps
    last_failure: str = ""
    failure_reason: str = ""  # an ai_service reason
    # Expenses made since this moment are "n nieuwe uitgaven om na te
    # kijken" on the overview; set when the Nakijken list is opened.
    seen_until: str = ""

    @property
    def failed(self) -> bool:
        """The last request failed (after the last one that worked)."""
        return bool(self.last_failure) and self.last_failure > self.last_success


def _status_path() -> Path:
    return Path(settings.DATA_DIR) / STATUS_FILE_NAME


def load() -> Status:
    try:
        data = json.loads(_status_path().read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return Status()
    return Status(**{key: str(data.get(key, "")) for key in Status.__dataclass_fields__})


def _update(**changes) -> Status:
    with _status_lock:
        status = load()
        for key, value in changes.items():
            setattr(status, key, value)
        path = _status_path()
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text(json.dumps(asdict(status), indent=2), encoding="utf-8")
        temporary.replace(path)
        return status


def forget_failure() -> None:
    """A newly saved service starts without the old one's red line."""
    _update(last_failure="", failure_reason="")


def failure_sentence() -> str:
    """Why the last request failed, or "" when it didn't (or it's off)."""
    status = load()
    config = ai_service.load()
    if not ai_service.is_on(config) or not status.failed:
        return ""
    return ai_service.failure_sentence(status.failure_reason, config)


def is_on() -> bool:
    return ai_service.is_on() and not sample_data_in_use()


def waiting():
    """The receipts Huismus will still read: in the tray, not read yet."""
    return Attachment.objects.in_tray().filter(read_at__isnull=True)


def is_reading() -> bool:
    return _read_lock.locked()


def active() -> bool:
    """Huismus reads what waits: a service is on and not failing. Then a
    receipt in the tray that it hasn't read yet will be read soon."""
    return is_on() and not load().failed


def still_new(receipts):
    """Of these receipts in the tray, those that count as new on the
    overview ("n nieuwe bonnetjes"): while Huismus reads, only the ones it
    left with a reason; the others become expenses to check."""
    return receipts.filter(read_at__isnull=False) if active() else receipts


# -- "n nieuwe uitgaven om na te kijken" -------------------------------------------


def new_expenses() -> int:
    """Expenses Huismus made from receipts since the Nakijken list was last
    opened, still to check. Only reads: the overview asks every 30 seconds."""
    if sample_data_in_use():
        return 0
    expenses = Expense.objects.filter(needs_review=True, source=SOURCE)
    seen_until = load().seen_until
    if seen_until:
        expenses = expenses.filter(created_at__gt=datetime.datetime.fromisoformat(seen_until))
    return expenses.count()


def seen() -> None:
    """The Nakijken list was opened. Written only when something was new."""
    if new_expenses():
        _update(seen_until=timezone.now().isoformat())


# -- Reading ------------------------------------------------------------------------

PROMPT = """You read one receipt for a Dutch freelancer's expense administration.
Answer with one JSON object and nothing else:

{
  "kind": "receipt" | "unreadable" | "not_a_receipt" | "more_than_one",
  "date": "YYYY-MM-DD",
  "supplier": "the shop or company",
  "description": "what was bought, in a few words, in the receipt's language",
  "total": "the total paid, including VAT, e.g. 42.35",
  "lines": [
    {"description": "...", "amount": "gross, including VAT, e.g. 34.99",
     "vat": "the VAT on this line as the receipt shows it, e.g. 6.07, or null",
     "category": "one of the categories below, or null"}
  ]
}

Rules:
- Never guess. Copy amounts as the receipt shows them; use null for what isn't there.
- One line per VAT rate is enough. The lines' amounts add up to the total.
- "vat": the VAT amount the receipt states for that line or rate. null when the
  receipt shows no VAT; 0 only when the receipt says 0.
- Amounts with a dot for decimals and no thousands separator.
- kind "unreadable" when you can't read the total or the date; "more_than_one" when
  it holds more than one receipt; "not_a_receipt" when it is something else.
"""


def _content(receipt: Attachment, categories: list[ExpenseCategory]) -> list[dict]:
    """What goes to the service. receipts.Unreadable for a file with
    nothing in it to read: then nothing is sent."""
    found = receipts.read(receipt)
    names = ", ".join(category.name for category in categories) or "(none)"
    text = f"{PROMPT}\nCategories: {names}\nFile name: {receipt.filename}"
    if found.text:
        text += f"\n\nText of the PDF:\n{found.text}"
    return [
        {"type": "text", "text": text},
        *(ai_service.image_part(image["data"]) for image in found.images),
    ]


def _answer(text: str) -> dict | None:
    """The JSON object in a model's answer, also inside ``` fences."""
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        return None
    try:
        data = json.loads(text[start : end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


_AMOUNT = re.compile(r"^(-?)(\d+)(?:[.,](\d{1,2}))?$")


def _cents(value) -> int | None:
    """ "42.35", "42,35", 42.35 or 42 as cents; None for anything else. A
    number from JSON is read through its text, never computed as a float."""
    if value is None or isinstance(value, bool):
        return None
    match = _AMOUNT.match(str(value).replace("€", "").strip())
    if not match:
        return None
    sign, euros, decimals = match.groups()
    cents = int(euros) * 100 + int((decimals or "0").ljust(2, "0"))
    return -cents if sign else cents


def _euros(cents: int) -> str:
    """As the expense form takes an amount: "42,35"."""
    sign = "-" if cents < 0 else ""
    euros, rest = divmod(abs(cents), 100)
    return f"{sign}{euros},{rest:02d}"


def _category(name, categories: list[ExpenseCategory]) -> ExpenseCategory | None:
    """An existing category by its name; any other name is none."""
    for category in categories:
        if name and category.name.casefold() == str(name).casefold():
            return category
    return None


@dataclass(frozen=True)
class Outcome:
    expense: Expense | None = None
    reason: str = ""  # why it stayed in the tray
    similar: Expense | None = None


def _expense_from(data: dict, receipt: Attachment, categories, vat_required: bool) -> Outcome:
    """Huismus's own checks on what the model read, then the expense."""
    kind = data.get("kind")
    if kind in (UNREADABLE, NOT_A_RECEIPT, MORE_THAN_ONE):
        return Outcome(reason=kind)
    if kind != "receipt":
        return Outcome(reason=UNREADABLE)
    total = _cents(data.get("total"))
    if total is None:
        return Outcome(reason=NO_TOTAL)
    raw_lines = data.get("lines")
    if not isinstance(raw_lines, list) or not raw_lines:
        return Outcome(reason=NOT_ADDING_UP)
    lines, amounts = [], []
    for raw in raw_lines:
        amount = _cents(raw.get("amount")) if isinstance(raw, dict) else None
        if amount is None:
            return Outcome(reason=NOT_ADDING_UP)
        vat = _cents(raw.get("vat"))
        if vat is None and (vat_required or raw.get("vat") is not None):
            # Not on the receipt while it must be, or not an amount.
            return Outcome(reason=NO_VAT)
        amounts.append(amount)
        lines.append(
            adding.Line(
                description=str(raw.get("description") or "")[:200],
                amount=_euros(amount),
                vat_info=None if vat is None else _euros(vat),
                category=_category(raw.get("category"), categories),
            )
        )
    # A check of the model's answer against the total it read, not a total
    # that is stored: save_lines() computes that (expense_totals).
    if sum(amounts) != total:
        return Outcome(reason=NOT_ADDING_UP)
    try:
        date = datetime.date.fromisoformat(str(data.get("date") or ""))
    except ValueError:
        return Outcome(reason=UNREADABLE)
    similar = Expense.objects.filter(date=date, amount_cents=total).first()
    if similar is not None:
        return Outcome(reason=SIMILAR, similar=similar)
    try:
        expense = adding.add_expense(
            date=date.isoformat(),
            supplier=str(data.get("supplier") or "")[:200],
            description=str(data.get("description") or "")[:200],
            lines=lines,
            receipt=receipt,
            source=SOURCE,
        )
    except adding.NotAdded:
        # The form refused it, or the user made an expense of the receipt
        # meanwhile: then Huismus's answer goes away.
        return Outcome(reason=UNREADABLE)
    return Outcome(expense=expense)


def read_one(receipt: Attachment, config: Config) -> Outcome | None:
    """Reads one receipt and records the outcome on it. None when the
    service did no work (recorded in the status): the receipt waits."""
    categories = list(ExpenseCategory.objects.all())
    vat_required = not Settings.load().kor_enabled
    try:
        content = _content(receipt, categories)
    except receipts.Unreadable:
        outcome = Outcome(reason=UNREADABLE)
    else:
        try:
            text = ai_service.chat(config, content)
        except ServiceError as error:
            if error.reason != ai_service.TIMEOUT_REASON:
                logger.warning("Bonnetje lezen mislukt: %s", error)
                _update(last_failure=timezone.now().isoformat(), failure_reason=error.reason)
                return None
            outcome = Outcome(reason=TIMEOUT)
        else:
            _update(last_success=timezone.now().isoformat())
            data = _answer(text)
            if data is None:
                outcome = Outcome(reason=UNREADABLE)
            else:
                outcome = _expense_from(data, receipt, categories, vat_required)
    # Marks the receipt: on the expense just made, or still in the tray.
    # One the user put on an expense of their own meanwhile stays as it is.
    Attachment.objects.filter(pk=receipt.pk, expense=outcome.expense).update(
        read_at=timezone.now(),
        read_by=ai_service.name(config),
        read_reason="" if outcome.expense else outcome.reason,
        read_similar=outcome.similar,
    )
    return outcome


def read_waiting() -> int:
    """Reads the receipts that wait, oldest first, and stops at the first
    failure of the service: the rest would fail the same way. The number
    read; 0 when off, with the sample data, or while another reading runs."""
    if not is_on() or not _read_lock.acquire(blocking=False):
        return 0
    try:
        config = ai_service.load()
        count = 0
        for pk in list(waiting().order_by("created_at", "pk").values_list("pk", flat=True)):
            # Taken meanwhile (made by hand, deleted): the next one.
            receipt = waiting().filter(pk=pk).first()
            if receipt is None:
                continue
            if read_one(receipt, config) is None:
                break
            count += 1
        return count
    finally:
        _read_lock.release()


def read_when_open() -> int:
    """read_waiting(), unless a backup is being restored."""
    with maintenance.gate.request() as open_:
        return read_waiting() if open_ else 0


def _start(work) -> None:
    """Runs work in its own thread; tests replace this to run it at once."""

    def run():
        try:
            work()
        except Exception:
            logger.exception("Bonnetjes lezen mislukt")
        finally:
            connections.close_all()

    threading.Thread(target=run, name="huismus-reading", daemon=True).start()


def read_in_background() -> None:
    """After the service is saved: the receipts that wait, without making
    the page wait for the service."""
    if is_on() and waiting().exists():
        _start(read_when_open)


# -- Sentences ------------------------------------------------------------------------


def read_by(expense: Expense) -> str:
    """The service Huismus read this expense's receipt with, or "" when
    Huismus didn't make it from a receipt."""
    if expense.source != SOURCE:
        return ""
    receipt = expense.attachments.filter(kind="receipt").exclude(read_by="").first()
    return receipt.read_by if receipt else ""


def reason_sentence(receipt: Attachment) -> str:
    """Why Huismus left this receipt in the tray, for the line under it;
    "" when it didn't read it."""
    if receipt.read_at is None:
        return ""
    reason = receipt.read_reason
    if reason == NOT_A_RECEIPT:
        return _("Niet gelezen: dit lijkt geen bonnetje.")
    if reason == MORE_THAN_ONE:
        return _("Niet gelezen: hier staan meer bonnetjes op.")
    if reason == NO_TOTAL:
        return _("Niet gelezen: er staat geen totaal op.")
    if reason == NOT_ADDING_UP:
        return _("Niet gelezen: de bedragen tellen niet op tot het totaal.")
    if reason == NO_VAT:
        return _("Niet gelezen: de btw staat er niet bij.")
    if reason == SIMILAR and receipt.read_similar is None:
        # That expense was deleted since.
        return _("Niet gelezen: lijkt op een uitgave die er al was.")
    if reason == SIMILAR:
        similar = receipt.read_similar
        return _("Niet gelezen: lijkt op je uitgave van %(date)s (%(amount)s).") % {
            "date": date_filter(similar.date, "j b Y"),
            "amount": money(similar.amount_cents),
        }
    if reason == TIMEOUT:
        return _("Niet gelezen: %(service)s gaf te laat antwoord.") % {"service": receipt.read_by}
    return _("Niet gelezen: dit bonnetje is niet goed leesbaar.")
