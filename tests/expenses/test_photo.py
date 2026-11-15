# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A new expense on a phone, the photo first (#188,
huismus/expenses/photo_views.py): the photo goes into the tray at once,
then the amount, where, date and category of one line. The camera itself
(app.js) is tests/e2e/test_photo_first.py."""

import datetime
import io

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from huismus.business.models import Settings
from huismus.core.models import Attachment
from huismus.expenses import photo_views, reading
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db


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


def _photo(name="IMG_0001.jpg", color="red"):
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), color=color).save(buffer, format="JPEG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/jpeg")


def _take(client, color="red", **extra):
    """The photo from the camera, as app.js sends it."""
    return client.post(reverse("expenses:photo_upload"), {"file": _photo(color=color), **extra})


def _form(**extra):
    return {
        "date": "2026-11-07",
        "supplier": "Kantoorcentrum Zuid",
        "description": "",
        "lines-TOTAL_FORMS": "1",
        "lines-INITIAL_FORMS": "0",
        "lines-MIN_NUM_FORMS": "1",
        "lines-MAX_NUM_FORMS": "1000",
        "lines-0-description": "",
        "lines-0-amount_cents": "48,95",
        "lines-0-vat_info_cents": "",
        "lines-0-category": "",
        **extra,
    }


# --- The photo -----------------------------------------------------------


def test_the_photo_goes_into_the_tray_at_once(logged_in):
    response = _take(logged_in)
    receipt = Attachment.objects.in_tray().get()
    assert receipt.source == photo_views.SOURCE and receipt.sha256
    assert response.url == reverse("expenses:photo", args=[receipt.pk])


def test_a_receipt_that_is_too_big_goes_to_the_ordinary_form_with_the_reason(
    logged_in, monkeypatch
):
    monkeypatch.setattr("huismus.expenses.receipts.MAX_RECEIPT_BYTES", 10)
    response = _take(logged_in)
    assert response.url == reverse("expenses:create")
    assert not Attachment.objects.exists()
    page = logged_in.get(response.url).content.decode()
    assert "groter dan" in page


def test_without_a_post_it_is_the_ordinary_form(logged_in):
    assert logged_in.get(reverse("expenses:photo_upload")).url == reverse("expenses:create")


def test_opnieuw_replaces_the_photo(logged_in):
    _take(logged_in)
    first = Attachment.objects.get()
    response = _take(logged_in, color="blue", vervangt=str(first.pk))
    second = Attachment.objects.get()
    assert second.pk != first.pk
    assert response.url == reverse("expenses:photo", args=[second.pk])
    assert not first.file.storage.exists(first.file.name)


def test_opnieuw_never_removes_a_receipt_that_is_on_an_expense(logged_in):
    _take(logged_in)
    receipt = Attachment.objects.get()
    logged_in.post(reverse("expenses:photo", args=[receipt.pk]), _form())
    _take(logged_in, vervangt=str(receipt.pk))
    receipt.refresh_from_db()
    assert receipt.expense is not None
    assert Attachment.objects.count() == 2


# --- The page ------------------------------------------------------------


def test_the_page_shows_the_photo_the_amount_first_and_today(logged_in):
    _take(logged_in)
    receipt = Attachment.objects.get()
    page = logged_in.get(reverse("expenses:photo", args=[receipt.pk])).content.decode()
    assert f'src="{receipt.file.url}"' in page
    assert "Opnieuw" in page
    assert page.index('name="lines-0-amount_cents"') < page.index('name="supplier"')
    assert page.index('name="supplier"') < page.index('name="date"')
    assert f'value="{timezone.localdate().isoformat()}"' in page
    assert "Bedrag, zoals je het betaalde" in page
    # The app's own labels, not "Waar" and "Soort" of the design (PO, #188).
    assert "Leverancier" in page and "Categorie" in page
    assert "Uitgave opslaan" in page and "Alleen de foto bewaren" in page
    assert page.index("Uitgave opslaan") < page.index("Alleen de foto bewaren")


def test_meer_regels_opens_verwerken_with_what_was_typed_and_saves_nothing(logged_in):
    _take(logged_in)
    receipt = Attachment.objects.get()
    page = logged_in.get(reverse("expenses:photo", args=[receipt.pk])).content.decode()
    process_url = reverse("expenses:process_item", args=["bonnetje", receipt.pk])
    assert f'formaction="{process_url}"' in page

    # The button posts the form there, as its "Regel toevoegen" without JS.
    response = logged_in.post(process_url, _form(regel_toevoegen="1"))

    page = response.content.decode()
    assert response.status_code == 200
    assert 'value="Kantoorcentrum Zuid"' in page and 'value="48,95"' in page
    assert 'name="lines-1-amount_cents"' in page
    assert not Expense.objects.exists()
    assert Attachment.objects.in_tray().get() == receipt


def test_without_the_kor_it_asks_the_vat_and_the_rate(logged_in):
    _kor(False)
    _take(logged_in)
    receipt = Attachment.objects.get()
    page = logged_in.get(reverse("expenses:photo", args=[receipt.pk])).content.decode()
    assert 'name="lines-0-vat_info_cents"' in page and 'name="lines-0-vat_rate"' in page
    # Right under the amount.
    assert page.index('name="lines-0-vat_rate"') < page.index('name="supplier"')

    response = logged_in.post(reverse("expenses:photo", args=[receipt.pk]), _form())
    assert response.status_code == 200
    assert "Vul het btw-bedrag in." in response.content.decode()
    assert not Expense.objects.exists()


def test_a_receipt_gone_meanwhile_goes_to_uitgaven_with_the_reason(logged_in):
    _take(logged_in)
    receipt = Attachment.objects.get()
    url = reverse("expenses:photo", args=[receipt.pk])
    receipt.delete()
    response = logged_in.get(url)
    assert response.url == reverse("expenses:list")
    page = logged_in.get(response.url).content.decode()
    assert "Dit bonnetje staat niet meer bij de bonnetjes zonder uitgave." in page


# --- Saving --------------------------------------------------------------


def test_uitgave_opslaan_makes_the_expense_with_the_photo_on_it(logged_in):
    office = ExpenseCategory.objects.create(name="Kantoor", sort_order=1)
    _take(logged_in)
    receipt = Attachment.objects.get()

    response = logged_in.post(
        reverse("expenses:photo", args=[receipt.pk]), _form(**{"lines-0-category": office.pk})
    )

    assert response.url == reverse("expenses:list")
    expense = Expense.objects.get()
    assert expense.amount_cents == 4895
    assert expense.supplier == "Kantoorcentrum Zuid"
    assert expense.date == datetime.date(2026, 11, 7)
    assert expense.lines.get().category == office
    assert not expense.needs_review
    receipt.refresh_from_db()
    assert receipt.expense == expense
    assert not Attachment.objects.in_tray().exists()
    assert "Uitgave opgeslagen." in logged_in.get(response.url).content.decode()


def test_without_an_amount_nothing_is_saved_and_the_photo_stays(logged_in):
    _take(logged_in)
    receipt = Attachment.objects.get()
    response = logged_in.post(
        reverse("expenses:photo", args=[receipt.pk]), _form(**{"lines-0-amount_cents": ""})
    )
    assert response.status_code == 200
    assert not Expense.objects.exists()
    assert Attachment.objects.in_tray().get() == receipt


def test_alleen_de_foto_bewaren_leaves_it_in_the_tray_and_reads_it(logged_in, monkeypatch):
    started = []
    monkeypatch.setattr(reading, "read_in_background", lambda: started.append(True))
    _take(logged_in)
    receipt = Attachment.objects.get()

    response = logged_in.post(
        reverse("expenses:photo", args=[receipt.pk]),
        _form(**{"lines-0-amount_cents": "", "alleen_foto": "1"}),
    )

    assert response.url == reverse("expenses:list")
    assert Attachment.objects.in_tray().get() == receipt
    assert not Expense.objects.exists()
    assert started == [True]
    page = logged_in.get(response.url).content.decode()
    assert "Bonnetje bewaard. Je vindt het bij Verwerken." in page
    assert "Verwerken (1)" in page


def test_both_need_a_login(client):
    assert client.post(reverse("expenses:photo_upload")).status_code == 302
    assert "/login/" in client.get(reverse("expenses:photo", args=[1])).url


def test_a_vervangt_that_is_no_number_replaces_nothing(logged_in):
    _take(logged_in)
    _take(logged_in, color="blue", vervangt="nee")
    assert Attachment.objects.in_tray().count() == 2


def test_opnieuw_never_removes_a_receipt_from_the_receipts_folder(logged_in):
    _take(logged_in)
    folder = Attachment.objects.get()
    Attachment.objects.filter(pk=folder.pk).update(source="bonnetjesmap")
    _take(logged_in, color="blue", vervangt=str(folder.pk))
    assert Attachment.objects.in_tray().count() == 2


def test_the_desktop_app_has_no_camera(logged_in, settings):
    assert 'id="camera"' in logged_in.get(reverse("expenses:list")).content.decode()
    settings.DESKTOP = True
    assert 'id="camera"' not in logged_in.get(reverse("expenses:list")).content.decode()
