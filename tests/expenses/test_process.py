# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verwerken (huismus/expenses/process_views.py; huismus-intern/besluiten.md,
2026-11-06): the stack one at a time, the receipt large beside the fields,
"3 van 24" at the top. "Klopt" (an expense) and "Opslaan" (a receipt) save
and go on; "Overslaan" goes on without saving. The order of the stack:
tests/expenses/test_batch.py."""

import datetime
import hashlib
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from huismus.business.models import Settings
from huismus.core.models import Attachment
from huismus.expenses import inbox, reading
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense

pytestmark = pytest.mark.django_db

PDF = b"%PDF-1.4\n% een bonnetje\n"


def _kor(on):
    business = Settings.load()
    business.kor_enabled = on
    business.save()


@pytest.fixture(autouse=True)
def kor_on(settings, tmp_path):
    settings.DATA_DIR = tmp_path / "data"
    settings.MEDIA_ROOT = settings.DATA_DIR
    settings.DATA_DIR.mkdir()
    _kor(True)


@pytest.fixture
def logged_in(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _png():
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return buffer.getvalue()


def _to_check(supplier, day, receipt=None, source=""):
    expense = create_expense(
        [ExpenseLineInput(description="", amount_cents=1210, vat_info_cents=None, category=None)],
        date=datetime.date(2026, 11, day),
        supplier=supplier,
        needs_review=True,
    )
    if source:
        Expense.objects.filter(pk=expense.pk).update(source=source)
    if receipt:
        name, content = receipt
        Attachment.objects.create(
            expense=expense, file=ContentFile(content, name=name), kind="receipt"
        )
    return expense


def _in_tray(name="bon.pdf", **fields):
    content = PDF + name.encode()
    return Attachment.objects.create(
        file=ContentFile(content, name=name),
        kind="receipt",
        sha256=hashlib.sha256(content).hexdigest(),
        source=inbox.SOURCE,
        **fields,
    )


def _url(kind, pk, done=0):
    url = reverse("expenses:process_item", args=[kind, pk])
    return f"{url}?klaar={done}" if done else url


def _expense_form(expense, **extra):
    line = expense.lines.get()
    return {
        "date": expense.date.isoformat(),
        "supplier": expense.supplier,
        "description": expense.description,
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "1",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-id": str(line.pk),
        "lines-0-description": line.description,
        "lines-0-amount_cents": "12,10",
        "lines-0-vat_info_cents": "",
        "lines-0-category": "",
        **extra,
    }


def _new_form(**extra):
    return {
        "date": "2026-11-05",
        "supplier": "Tankstation",
        "description": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "Benzine",
        "lines-0-amount_cents": "45,10",
        "lines-0-vat_info_cents": "7,83",
        "lines-0-vat_rate": "21",
        **extra,
    }


# --- Coming in -----------------------------------------------------------


def test_an_empty_stack_says_so(logged_in):
    page = logged_in.get(reverse("expenses:process")).content.decode()
    assert "Niets meer te verwerken." in page
    assert f'href="{reverse("expenses:list")}"' in page and "Naar Uitgaven" in page
    assert "verwerken-teller" not in page


def test_verwerken_opens_the_top_of_the_stack(logged_in):
    _in_tray()
    expense = _to_check("Gamma", 5)
    response = logged_in.get(reverse("expenses:process"))
    assert response.url == _url("uitgave", expense.pk)


def test_the_expenses_page_has_the_button_with_the_whole_stack(logged_in):
    _to_check("Gamma", 5)
    _in_tray()
    page = logged_in.get(reverse("expenses:list")).content.decode()
    assert "Verwerken (2)" in page
    assert f'href="{reverse("expenses:process")}"' in page


def test_opening_it_makes_the_new_expenses_on_the_overview_seen(logged_in):
    expense = _to_check("Gamma", 5, source=reading.SOURCE)
    assert reading.new_expenses() == 1
    logged_in.get(_url("uitgave", expense.pk))
    assert reading.new_expenses() == 0


def test_an_unknown_kind_is_not_found(logged_in):
    assert logged_in.get("/uitgaven/verwerken/factuur/1/").status_code == 404


def test_an_expense_checked_meanwhile_goes_on_from_the_top(logged_in):
    checked = _to_check("Gamma", 5)
    Expense.objects.filter(pk=checked.pk).update(needs_review=False)
    response = logged_in.get(_url("uitgave", checked.pk, done=2))
    assert response.url == reverse("expenses:process") + "?klaar=2"


# --- An expense to check -------------------------------------------------


def test_an_expense_shows_its_photo_large_the_count_and_klopt(logged_in):
    expense = _to_check("Gamma", 5, receipt=("kassabon.png", _png()))
    _to_check("Praxis", 4)
    _in_tray()

    page = logged_in.get(_url("uitgave", expense.pk)).content.decode()

    assert "1 van 3" in page
    assert 'class="process-img"' in page and 'alt="Bonnetje kassabon.png"' in page
    assert "Bonnetje openen" in page
    assert "Je AI-assistent vulde deze uitgave in. Klopt alles?" in page
    assert 'name="klopt"' in page and ">Overslaan<" in page
    assert 'value="Gamma"' in page


def test_a_pdf_is_shown_in_a_frame_on_a_wide_screen(logged_in):
    expense = _to_check("Gamma", 5, receipt=("factuur.pdf", PDF))
    page = logged_in.get(_url("uitgave", expense.pk)).content.decode()
    receipt = expense.attachments.get()
    # app.js gives the frame its src on a wide screen only.
    assert f'data-wide-src="{receipt.file.url}"' in page
    assert "data-pdf-file" in page and "factuur.pdf" in page


def test_a_pdf_receipt_may_be_framed_by_huismus_itself_other_files_not(logged_in):
    pdf = _to_check("Gamma", 5, receipt=("factuur.pdf", PDF)).attachments.get()
    png = _to_check("Praxis", 4, receipt=("bon.png", _png())).attachments.get()
    assert logged_in.get(pdf.file.url)["X-Frame-Options"] == "SAMEORIGIN"
    assert logged_in.get(png.file.url)["X-Frame-Options"] == "DENY"
    # The page itself still can't be framed anywhere.
    assert logged_in.get(_url("uitgave", pdf.expense_id))["X-Frame-Options"] == "DENY"


def test_the_service_it_was_read_with(logged_in):
    expense = _to_check("Gamma", 5, source=reading.SOURCE)
    Attachment.objects.create(
        expense=expense, file=ContentFile(PDF, name="b.pdf"), kind="receipt", read_by="Mistral"
    )
    page = logged_in.get(_url("uitgave", expense.pk)).content.decode()
    assert "Huismus las dit bonnetje met Mistral. Klopt alles?" in page


def test_an_expense_without_a_receipt_can_get_one_here(logged_in):
    expense = _to_check("Gamma", 5)
    page = logged_in.get(_url("uitgave", expense.pk, done=3)).content.decode()
    assert "Geen bonnetje bij deze uitgave." in page
    assert reverse("expenses:receipt_upload", args=[expense.pk]) in page

    upload = ContentFile(PDF, name="later.pdf")
    response = logged_in.post(
        reverse("expenses:receipt_upload", args=[expense.pk]),
        {"file": upload, "verwerken": "1", "klaar": "3"},
    )

    assert response.url == _url("uitgave", expense.pk, done=3)
    assert expense.attachments.count() == 1


def test_klopt_saves_and_goes_on_with_one_more_done(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)

    response = logged_in.post(
        _url("uitgave", first.pk), _expense_form(first, supplier="Gamma BV", klopt="1"), follow=True
    )

    assert response.redirect_chain[-1][0] == _url("uitgave", second.pk, done=1)
    page = response.content.decode()
    assert "Uitgave nagekeken." in page and "2 van 2" in page
    first.refresh_from_db()
    assert (first.needs_review, first.supplier) == (False, "Gamma BV")


def test_klopt_on_the_last_one_says_nothing_is_left(logged_in):
    only = _to_check("Gamma", 5)
    response = logged_in.post(
        _url("uitgave", only.pk, done=4), _expense_form(only, klopt="1", klaar="4"), follow=True
    )
    assert response.redirect_chain[-1][0] == reverse("expenses:process")
    page = response.content.decode()
    assert "Uitgave nagekeken." in page and "Niets meer te verwerken." in page


def test_overslaan_goes_on_without_saving_and_counts_nothing_done(logged_in):
    first = _to_check("Gamma", 5)
    second = _to_check("Praxis", 4)

    page = logged_in.get(_url("uitgave", first.pk, done=2)).content.decode()

    assert f'id="overslaan" href="{_url("uitgave", second.pk, done=2)}"' in page
    first.refresh_from_db()
    assert first.needs_review
    # Round again: the top one that is left.
    again = logged_in.get(_url("uitgave", second.pk, done=2)).content.decode()
    assert f'href="{_url("uitgave", first.pk, done=2)}"' in again
    assert "4 van 4" in again


def test_the_only_one_has_no_overslaan(logged_in):
    only = _to_check("Gamma", 5)
    page = logged_in.get(_url("uitgave", only.pk)).content.decode()
    assert "1 van 1" in page and "overslaan" not in page


def test_an_error_stays_with_the_same_count_and_keeps_the_mark(logged_in):
    first = _to_check("Gamma", 5)
    _to_check("Praxis", 4)

    response = logged_in.post(
        _url("uitgave", first.pk), _expense_form(first, date="", klopt="1", klaar="1")
    )

    assert response.status_code == 200
    assert "2 van 3" in response.content.decode()
    first.refresh_from_db()
    assert first.needs_review


def test_regel_toevoegen_without_js_adds_a_line_and_saves_nothing(logged_in):
    expense = _to_check("Gamma", 5)

    response = logged_in.post(
        _url("uitgave", expense.pk),
        _expense_form(expense, supplier="Nieuw", regel_toevoegen="1", klaar="2"),
    )

    page = response.content.decode()
    assert response.status_code == 200
    assert 'name="lines-TOTAL_FORMS" value="2"' in page
    assert 'value="Nieuw"' in page and 'name="klaar" value="2"' in page
    expense.refresh_from_db()
    assert (expense.supplier, expense.needs_review) == ("Gamma", True)


# --- A receipt from the tray ---------------------------------------------


def test_a_receipt_has_empty_fields_and_opslaan(logged_in):
    receipt = _in_tray("tankstation.pdf")
    page = logged_in.get(_url("bonnetje", receipt.pk)).content.decode()
    assert "1 van 1" in page and "tankstation.pdf" in page
    assert 'name="klopt"' not in page and "Opslaan" in page
    assert "Klopt alles?" not in page and 'id="nakijken"' not in page


def test_a_receipt_shows_why_huismus_left_it(logged_in):
    receipt = _in_tray(read_at=timezone.now(), read_reason=reading.NOT_A_RECEIPT)
    page = logged_in.get(_url("bonnetje", receipt.pk)).content.decode()
    assert "Niet gelezen: dit lijkt geen bonnetje." in page
    # In the notice, as an expense's "Klopt alles?".
    assert 'class="flash flash-info" id="nakijken"' in page


def test_opslaan_puts_the_receipt_on_a_new_expense_and_goes_on(logged_in):
    expense = _to_check("Gamma", 5)
    receipt = _in_tray()

    response = logged_in.post(_url("bonnetje", receipt.pk), _new_form(klaar="1"), follow=True)

    assert response.redirect_chain[-1][0] == _url("uitgave", expense.pk, done=2)
    assert "Uitgave opgeslagen." in response.content.decode()
    receipt.refresh_from_db()
    made = receipt.expense
    assert (made.supplier, made.amount_cents, made.needs_review) == ("Tankstation", 4510, False)


def test_without_the_kor_an_empty_vat_is_an_error_and_nothing_is_saved(logged_in):
    _kor(False)
    receipt = _in_tray()

    response = logged_in.post(
        _url("bonnetje", receipt.pk), _new_form(**{"lines-0-vat_info_cents": ""})
    )

    assert response.status_code == 200
    assert not Expense.objects.exists()
    assert Attachment.objects.in_tray().count() == 1


def test_in_english(logged_in):
    first = _to_check("Gamma", 5, receipt=("bon.png", _png()))
    _in_tray()
    logged_in.cookies["django_language"] = "en"
    page = logged_in.get(_url("uitgave", first.pk)).content.decode()
    assert "1 of 2" in page and ">Process<" in page and "Open receipt" in page
    empty = logged_in.get(reverse("expenses:process") + "?klaar=1")
    assert empty.status_code == 302  # still something there
