# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Huismus reads receipts itself with the user's AI service (SPEC.md M20,
part 3; huismus/expenses/reading.py), against the fake service of
tests/ai_fakes.py: never a real one. The model only reads; Huismus checks
the answer, and never sends one receipt twice."""

from io import BytesIO

import pytest
from django.core.files.base import ContentFile
from PIL import Image

from huismus.business.models import Settings
from huismus.core.backup import BEFORE_SAMPLE_DATA_FILE_NAME
from huismus.core.models import Attachment
from huismus.expenses import ai_service, inbox, reading
from huismus.expenses.ai_service import Config, ServiceError
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, ExpenseCategory
from tests.ai_fakes import KEY

pytestmark = pytest.mark.django_db

ANSWER = {
    "kind": "receipt",
    "date": "2026-11-04",
    "supplier": "Bouwmarkt De Spijker",
    "description": "Schroeven en verf",
    "total": "42.35",
    "lines": [
        {
            "description": "Verf",
            "amount": "30.25",
            "vat": "5.25",
            "vat_rate": "21",
            "category": "Kantoor",
        },
        {
            "description": "Schroeven",
            "amount": "12.10",
            "vat": "2.10",
            "vat_rate": "21",
            "category": None,
        },
    ],
}


def _png() -> bytes:
    out = BytesIO()
    Image.new("RGB", (40, 60), "white").save(out, "PNG")
    return out.getvalue()


def _receipt(name="bon.png", content=None) -> Attachment:
    return Attachment.objects.create(
        file=ContentFile(content or _png(), name=name),
        kind="receipt",
        source=inbox.SOURCE,
    )


@pytest.fixture
def service(ai_fake):
    ai_service.save(Config("other", ai_fake.url, "nep-model", KEY))
    return ai_fake


@pytest.fixture
def kor(db):
    def set_kor(on: bool):
        settings = Settings.load()
        settings.kor_enabled = on
        settings.save()

    return set_kor


def test_a_receipt_becomes_an_expense_to_check(service, kor):
    kor(False)
    ExpenseCategory.objects.create(name="Kantoor")
    receipt = _receipt()
    service.answer(ANSWER)

    assert reading.read_waiting() == 1

    expense = Expense.objects.get()
    assert expense.needs_review
    assert expense.source == reading.SOURCE
    assert expense.supplier == "Bouwmarkt De Spijker"
    assert str(expense.date) == "2026-11-04"
    # Totals through save_lines (invariant 7: gross amounts).
    assert expense.amount_cents == 4235
    assert expense.vat_info_cents == 735
    lines = list(expense.lines.order_by("position"))
    assert [line.amount_cents for line in lines] == [3025, 1210]
    assert lines[0].category.name == "Kantoor"
    assert lines[1].category is None
    receipt.refresh_from_db()
    assert receipt.expense == expense
    assert receipt.read_at is not None
    assert receipt.read_by == "127.0.0.1"
    assert receipt.read_reason == ""
    assert reading.read_by(expense) == "127.0.0.1"


def test_what_is_sent_is_the_receipt_as_the_assistant_reads_it(service):
    ExpenseCategory.objects.create(name="Kantoor")
    _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    content = service.requests[-1]["messages"][0]["content"]
    assert "Categories: Kantoor" in content[0]["text"]
    assert [part["type"] for part in content] == ["text", "image_url"]
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_a_pdf_with_nothing_to_read_is_never_sent(service):
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    out = BytesIO()
    writer.write(out)
    # A blank PDF has neither text nor images: nothing to send.
    receipt = _receipt("leeg.pdf", out.getvalue())
    reading.read_waiting()
    assert service.requests == []
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.UNREADABLE
    assert receipt.read_at is not None


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"kind": "unreadable"}, reading.UNREADABLE),
        ({"kind": "not_a_receipt"}, reading.NOT_A_RECEIPT),
        ({"kind": "more_than_one"}, reading.MORE_THAN_ONE),
        ({"kind": "iets anders"}, reading.UNREADABLE),
        ({"total": None}, reading.NO_TOTAL),
        ({"total": "ongeveer 40"}, reading.NO_TOTAL),
        ({"total": "50.00"}, reading.NOT_ADDING_UP),
        ({"lines": []}, reading.NOT_ADDING_UP),
        ({"lines": [{"description": "x", "amount": None, "vat": "1.00"}]}, reading.NOT_ADDING_UP),
        ({"date": None}, reading.UNREADABLE),
        ({"date": "gisteren"}, reading.UNREADABLE),
    ],
)
def test_huismus_checks_the_answer_and_leaves_the_receipt(service, changes, reason):
    receipt = _receipt()
    service.answer({**ANSWER, **changes})
    reading.read_waiting()
    assert not Expense.objects.exists()
    receipt.refresh_from_db()
    assert receipt.expense is None
    assert receipt.read_reason == reason
    assert reading.reason_sentence(receipt).startswith("Niet gelezen:")


def test_an_answer_that_is_no_json_leaves_the_receipt(service):
    receipt = _receipt()
    service.answer("Ik zie een bonnetje van de bouwmarkt.")
    reading.read_waiting()
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.UNREADABLE


def test_json_in_fences_is_read(service):
    _receipt()
    service.answer("```json\n" + __import__("json").dumps(ANSWER) + "\n```")
    reading.read_waiting()
    assert Expense.objects.count() == 1


def test_without_the_kor_vat_is_needed_and_never_filled_in(service, kor):
    kor(False)
    receipt = _receipt()
    lines = [{"description": "Verf", "amount": "42.35", "vat": None}]
    service.answer({**ANSWER, "lines": lines})
    reading.read_waiting()
    assert not Expense.objects.exists()
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.NO_VAT
    assert reading.reason_sentence(receipt) == "Niet gelezen: de btw staat er niet bij."


def test_under_the_kor_vat_is_only_for_information(service, kor):
    kor(True)
    lines = [{"description": "Verf", "amount": "42.35", "vat": None}]
    _receipt()
    service.answer({**ANSWER, "lines": lines})
    reading.read_waiting()
    expense = Expense.objects.get()
    assert expense.amount_cents == 4235
    assert expense.vat_info_cents is None


def test_a_vat_that_is_no_amount_leaves_the_receipt(service, kor):
    kor(True)
    receipt = _receipt()
    lines = [{"description": "Verf", "amount": "42.35", "vat": "21%"}]
    service.answer({**ANSWER, "lines": lines})
    reading.read_waiting()
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.NO_VAT


def test_without_the_kor_the_rate_is_stored_as_read(service, kor):
    """SPEC.md M21, part 2: the rate as on the receipt."""
    kor(False)
    _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    expense = Expense.objects.get()
    assert [line.vat_rate for line in expense.lines.all()] == ["21", "21"]


@pytest.mark.parametrize("rate", [None, "21%", "6"])
def test_without_the_kor_a_missing_or_unknown_rate_leaves_the_receipt(service, kor, rate):
    """Never guessed: the receipt stays in the tray, as without VAT."""
    kor(False)
    receipt = _receipt()
    lines = [{"description": "Verf", "amount": "42.35", "vat": "7.35", "vat_rate": rate}]
    service.answer({**ANSWER, "lines": lines})
    reading.read_waiting()
    assert not Expense.objects.exists()
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.NO_VAT_RATE
    assert reading.reason_sentence(receipt) == "Niet gelezen: het btw-tarief staat er niet bij."


def test_under_the_kor_the_rate_is_not_needed(service, kor):
    kor(True)
    _receipt()
    lines = [{"description": "Verf", "amount": "42.35", "vat": None}]
    service.answer({**ANSWER, "lines": lines})
    reading.read_waiting()
    assert Expense.objects.get().lines.get().vat_rate == ""


def test_an_expense_like_it_already_there_leaves_the_receipt(service):
    similar = create_expense(
        [ExpenseLineInput("Verf", 4235, None, None)],
        date="2026-11-04",
        supplier="Bouwmarkt",
    )
    receipt = _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    assert Expense.objects.count() == 1
    receipt.refresh_from_db()
    assert receipt.read_reason == reading.SIMILAR
    assert receipt.read_similar == similar
    assert reading.reason_sentence(receipt) == (
        "Niet gelezen: lijkt op je uitgave van 4 nov 2026 (€\xa042,35)."
    )


def test_a_receipt_is_never_sent_twice(service):
    _receipt()
    service.answer({"kind": "unreadable"})
    reading.read_waiting()
    reading.read_waiting()
    assert len(service.requests) == 1


def test_a_refused_key_sends_the_receipt_again_next_time(service):
    receipt = _receipt()
    service.key = "een-andere"
    assert reading.read_waiting() == 0
    receipt.refresh_from_db()
    assert receipt.read_at is None
    assert reading.load().failed
    assert reading.failure_sentence() == (
        "127.0.0.1 weigert je sleutel. Kijk of je hem goed hebt overgenomen."
    )
    assert not reading.active()

    service.key = KEY
    service.answer(ANSWER)
    assert reading.read_waiting() == 1
    assert not reading.load().failed
    assert reading.failure_sentence() == ""


@pytest.mark.parametrize("status", [429, 500])
def test_busy_or_broken_waits_too(service, status):
    receipt = _receipt()
    service.answer((status, {"error": {"message": "even niet"}}))
    reading.read_waiting()
    receipt.refresh_from_db()
    assert receipt.read_at is None


def test_a_failure_stops_the_round(service):
    _receipt("a.png")
    _receipt("b.png")
    service.key = "een-andere"
    reading.read_waiting()
    assert len(service.requests) == 1


def test_a_timeout_counts_as_read_and_is_not_sent_again(service, monkeypatch):
    receipt = _receipt()

    def slow(config, content, timeout=None):
        raise ServiceError(ai_service.TIMEOUT_REASON, "timed out")

    monkeypatch.setattr(ai_service, "chat", slow)
    reading.read_waiting()
    receipt.refresh_from_db()
    assert receipt.read_at is not None
    assert receipt.read_reason == reading.TIMEOUT
    assert reading.reason_sentence(receipt) == "Niet gelezen: 127.0.0.1 gaf te laat antwoord."
    assert not reading.load().failed
    calls = []
    monkeypatch.setattr(ai_service, "chat", lambda *args, **kwargs: calls.append(1))
    reading.read_waiting()
    assert calls == []


def test_a_receipt_the_user_made_an_expense_of_meanwhile(service, monkeypatch):
    receipt = _receipt()
    by_hand = create_expense([ExpenseLineInput("Verf", 999, None, None)], date="2026-11-01")
    real_chat = ai_service.chat

    def chat_while_the_user_saves(config, content, timeout=ai_service.TIMEOUT):
        Attachment.objects.filter(pk=receipt.pk).update(expense=by_hand)
        return real_chat(config, content, timeout)

    monkeypatch.setattr(ai_service, "chat", chat_while_the_user_saves)
    service.answer(ANSWER)
    reading.read_waiting()
    # Huismus's answer goes away; the user's expense stays as it was.
    assert list(Expense.objects.all()) == [by_hand]
    receipt.refresh_from_db()
    assert receipt.expense == by_hand
    assert receipt.read_at is None
    assert receipt.read_reason == ""


def test_nothing_while_a_backup_is_restored(service):
    from huismus.core import maintenance

    _receipt()
    with maintenance.gate.exclusive(timeout=0):
        assert reading.read_when_open() == 0
    assert service.requests == []


def test_a_receipt_taken_before_its_turn_is_skipped(service):
    receipt = _receipt()
    receipt.delete()
    assert reading.read_waiting() == 0
    assert service.requests == []


def test_nothing_without_a_service(ai_fake):
    _receipt()
    assert reading.read_waiting() == 0
    assert ai_fake.requests == []


def test_nothing_with_the_sample_data(service, settings):
    (settings.DATA_DIR / BEFORE_SAMPLE_DATA_FILE_NAME).write_bytes(b"x")
    try:
        _receipt()
        assert reading.read_waiting() == 0
        assert service.requests == []
    finally:
        (settings.DATA_DIR / BEFORE_SAMPLE_DATA_FILE_NAME).unlink()


def test_new_expenses_to_check_until_the_list_is_opened(service):
    _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    assert reading.new_expenses() == 1
    reading.seen()
    assert reading.new_expenses() == 0


def test_an_expense_of_the_assistant_is_not_one_huismus_read(service):
    expense = create_expense([ExpenseLineInput("x", 100, None, None)], date="2026-11-01")
    assert reading.read_by(expense) == ""


def test_the_status_file_is_left_out_of_backups():
    assert reading.STATUS_FILE_NAME.startswith(ai_service.FILE_PREFIX)


# -- With the receipts folder --------------------------------------------------------


@pytest.fixture
def folder(settings, tmp_path, monkeypatch):
    monkeypatch.setattr(inbox, "SETTLE_SECONDS", 0)
    folder = tmp_path / "Huismus bonnetjes"
    folder.mkdir()
    inbox.choose_folder(folder)
    return folder


def test_a_look_reads_what_it_brought_in(service, folder):
    (folder / "bon.png").write_bytes(_png())
    service.answer(ANSWER)
    inbox.fetch_if_due(at_start=True)
    expense = Expense.objects.get()
    assert expense.attachments.get().filename == "bon.png"
    # Read and made: not "1 nieuw bonnetje", but an expense to check.
    assert inbox.new_receipts() == 0
    assert reading.new_expenses() == 1


def test_nothing_new_in_the_tray_while_huismus_reads_it(service, folder):
    receipt = _receipt()
    inbox._update(seen_until="2000-01-01T00:00:00+00:00")
    assert inbox.new_receipts() == 0
    # Left with a reason: it is new in the tray after all.
    receipt.read_at = receipt.created_at
    receipt.read_reason = reading.NO_TOTAL
    receipt.save()
    assert inbox.new_receipts() == 1


def test_while_the_service_fails_waiting_receipts_count_as_new(service, folder):
    _receipt()
    inbox._update(seen_until="2000-01-01T00:00:00+00:00")
    service.key = "een-andere"
    reading.read_waiting()
    assert inbox.new_receipts() == 1


def test_a_look_tries_a_failed_receipt_again(service, folder):
    _receipt()
    service.key = "een-andere"
    reading.read_waiting()
    service.key = KEY
    service.answer(ANSWER)
    inbox.fetch_if_due(at_start=True)
    assert Expense.objects.count() == 1


def test_now_in_the_background_reads_too(service, folder, monkeypatch):
    monkeypatch.setattr(inbox, "_start", lambda work: work())
    (folder / "bon.png").write_bytes(_png())
    service.answer(ANSWER)
    inbox.fetch_in_background()
    assert Expense.objects.count() == 1


def test_now_tries_a_failed_receipt_again_without_a_new_file(service, folder, monkeypatch):
    """Found by verify-e2e: after the key works again, "Nu ophalen" with
    nothing new in the folder has to read the receipt that waited."""
    monkeypatch.setattr(inbox, "_start", lambda work: work())
    (folder / "bon.png").write_bytes(_png())
    service.key = "een-andere"
    inbox.fetch_in_background()
    assert Attachment.objects.in_tray().count() == 1
    assert reading.failure_sentence()
    service.key = KEY
    service.answer(ANSWER)
    inbox.fetch_in_background()
    assert Expense.objects.count() == 1
    assert reading.failure_sentence() == ""


def test_a_similar_expense_deleted_since_keeps_the_reason(service):
    """Found by verify-e2e: the line said "niet goed leesbaar" once the
    expense it looked like was gone."""
    similar = create_expense([ExpenseLineInput("Verf", 4235, None, None)], date="2026-11-04")
    receipt = _receipt()
    service.answer(ANSWER)
    reading.read_waiting()
    similar.delete()
    receipt.refresh_from_db()
    assert reading.reason_sentence(receipt) == "Niet gelezen: lijkt op een uitgave die er al was."
