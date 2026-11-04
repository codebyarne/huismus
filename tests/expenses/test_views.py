# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import BytesIO

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from huismus.core.models import Attachment
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _receipt_png():
    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    return SimpleUploadedFile("bon.png", buffer.getvalue(), content_type="image/png")


def test_list_requires_login(client):
    response = client.get(reverse("expenses:list"))
    assert response.status_code == 302


def test_list_shows_expenses(client):
    _login(client)
    # Today: the list shows the current year by default.
    Expense.objects.create(date=timezone.localdate(), supplier="Acme BV", amount_cents=1234)

    response = client.get(reverse("expenses:list"))

    assert b"Acme BV" in response.content


def _lines(*lines, ids=()):
    """The line formset's POST data: (description, amount, vat, category pk)
    per line; a line with DELETE as fifth item is removed. `ids`: the pks of
    the lines already saved, the first lines."""
    data = {
        "lines-TOTAL_FORMS": str(len(lines)),
        "lines-INITIAL_FORMS": str(len(ids)),
        "lines-MIN_NUM_FORMS": "0",
        "lines-MAX_NUM_FORMS": "1000",
    }
    for i, line in enumerate(lines):
        description, amount, vat, category, *delete = (*line, "", "", "")[:5]
        data |= {
            f"lines-{i}-description": description,
            f"lines-{i}-amount_cents": amount,
            f"lines-{i}-vat_info_cents": vat,
            f"lines-{i}-category": category,
        }
        if delete and delete[0]:
            data[f"lines-{i}-DELETE"] = "on"
        if i < len(ids):
            data[f"lines-{i}-id"] = str(ids[i])
    return data


def _header(**fields):
    return {"date": "2026-01-15", "supplier": "Acme BV", "description": "", **fields}


def test_create_saves_a_gross_amount_in_cents(client):
    _login(client)
    response = client.post(reverse("expenses:create"), _header() | _lines(("", "12.34", "")))

    assert response.status_code == 302
    expense = Expense.objects.get()
    assert expense.amount_cents == 1234
    assert expense.vat_info_cents is None
    assert expense.lines.get().amount_cents == 1234


def test_create_with_two_lines_in_their_own_category(client):
    _login(client)
    software = ExpenseCategory.objects.create(name="Software")
    travel = ExpenseCategory.objects.create(name="Reiskosten")

    client.post(
        reverse("expenses:create"),
        _header()
        | _lines(
            ("Hosting", "12,10", "2,10", software.pk),
            ("Trein", "8,00", "", travel.pk),
        ),
    )

    expense = Expense.objects.get()
    assert expense.amount_cents == 2010
    assert expense.vat_info_cents == 210
    assert [(line.description, line.category) for line in expense.lines.all()] == [
        ("Hosting", software),
        ("Trein", travel),
    ]


def test_a_new_expense_starts_with_one_line_that_needs_an_amount(client):
    _login(client)
    assert client.get(reverse("expenses:create")).context["formset"].total_form_count() == 1

    response = client.post(reverse("expenses:create"), _header() | _lines(("", "", "")))

    assert response.status_code == 200
    assert Expense.objects.count() == 0
    assert response.context["formset"].forms[0].errors["amount_cents"]


def test_deleting_every_line_is_refused(client):
    _login(client)
    expense = create_expense([ExpenseLineInput("Hosting", 1000, None, None)], date="2026-01-15")

    response = client.post(
        reverse("expenses:edit", kwargs={"pk": expense.pk}),
        _header() | _lines(("Hosting", "10,00", "", "", "x"), ids=[expense.lines.get().pk]),
    )

    assert response.status_code == 200
    assert "Vul minstens één regel in met een bedrag." in response.content.decode()
    assert expense.lines.count() == 1


def test_add_a_line_without_js_saves_and_comes_back_with_an_empty_line(client):
    _login(client)

    response = client.post(
        reverse("expenses:create"),
        _header() | _lines(("Hosting", "10,00", "")) | {"regel_toevoegen": "1"},
    )

    expense = Expense.objects.get()
    assert response.url == reverse("expenses:edit", kwargs={"pk": expense.pk}) + "?regel=1"
    page = client.get(response.url)
    assert page.context["formset"].total_form_count() == 2


def test_edit_updates_the_expense_and_removes_a_deleted_line(client):
    _login(client)
    expense = create_expense(
        [ExpenseLineInput("Oud", 1000, None, None), ExpenseLineInput("Weg", 500, None, None)],
        date="2026-01-15",
    )

    response = client.post(
        reverse("expenses:edit", kwargs={"pk": expense.pk}),
        _header(supplier="Nieuwe leverancier", date="2026-01-16")
        | _lines(
            ("Oud", "20,00", ""),
            ("Weg", "5,00", "", "", "x"),
            ids=list(expense.lines.values_list("pk", flat=True)),
        ),
    )

    assert response.status_code == 302
    expense.refresh_from_db()
    assert expense.supplier == "Nieuwe leverancier"
    assert expense.amount_cents == 2000
    assert list(expense.lines.values_list("description", "amount_cents")) == [("Oud", 2000)]


def test_the_edit_page_shows_the_lines_and_the_total(client):
    _login(client)
    expense = create_expense(
        [
            ExpenseLineInput("Hosting", 1210, None, None),
            ExpenseLineInput("Domein", 1500, None, None),
        ],
        date="2026-01-15",
    )

    response = client.get(reverse("expenses:edit", kwargs={"pk": expense.pk}))

    html = " ".join(response.content.decode().split())
    assert response.context["formset"].total_form_count() == 2
    assert "Hosting" in html and "Domein" in html
    assert "€ 27,10" in html
    assert 'data-formset-add="lines"' in html


def test_edit_page_does_not_leak_a_template_comment_as_visible_text(client):
    # Regression: a multi-line {# ... #} comment in form.html rendered
    # as literal page text — Django's {# #} syntax only ever comments
    # out a single line; anything after the first newline is treated as
    # ordinary template text instead of being swallowed. Found by
    # actually looking at a rendered edit page in a browser, not by any
    # test before this one. {% comment %}...{% endcomment %} is the tag
    # that actually supports multiple lines.
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)

    response = client.get(reverse("expenses:edit", kwargs={"pk": expense.pk}))

    assert b"NoReverseMatch" not in response.content
    assert b"expense_create()" not in response.content


def test_delete_removes_the_expense(client):
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)

    response = client.post(reverse("expenses:delete", kwargs={"pk": expense.pk}))

    assert response.status_code == 302
    assert Expense.objects.count() == 0


def test_delete_also_removes_its_receipt_files_from_disk(client, settings, tmp_path):
    # Regression: Attachment.expense is on_delete=CASCADE, so the row
    # disappeared on its own even before this fix — but nothing removed
    # the file it pointed at, leaving a permanent orphan on disk with no
    # database row left to explain it.
    settings.MEDIA_ROOT = tmp_path
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)
    Attachment.objects.create(expense=expense, file=_receipt_png(), kind="receipt")
    assert any(tmp_path.rglob("*.png"))

    client.post(reverse("expenses:delete", kwargs={"pk": expense.pk}))

    assert Attachment.objects.count() == 0
    assert not any(tmp_path.rglob("*.png"))


def test_receipt_upload_attaches_a_file_to_the_expense(client):
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)

    response = client.post(
        reverse("expenses:receipt_upload", kwargs={"pk": expense.pk}),
        {"file": _receipt_png()},
    )

    assert response.status_code == 302
    attachment = Attachment.objects.get()
    assert attachment.expense_id == expense.pk
    assert attachment.kind == "receipt"
    assert attachment.sha256


def test_receipt_upload_rejects_an_invalid_file(client):
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)

    response = client.post(
        reverse("expenses:receipt_upload", kwargs={"pk": expense.pk}),
        {"file": SimpleUploadedFile("bon.png", b"not an image", content_type="image/png")},
        follow=True,
    )

    assert Attachment.objects.count() == 0
    # The real reason, not "Controleer het bestand." (besluiten 2026-11-01, deel 3).
    messages = [str(m) for m in response.context["messages"]]
    assert messages == ["Huismus kan deze afbeelding niet openen. Kies een ander bestand."]


def test_create_with_a_receipt_attaches_it_to_the_new_expense(client):
    _login(client)

    response = client.post(
        reverse("expenses:create"),
        _header() | _lines(("", "12.34", "")) | {"receipt-file": _receipt_png()},
    )

    assert response.status_code == 302
    expense = Expense.objects.get()
    attachment = Attachment.objects.get()
    assert attachment.expense_id == expense.pk
    assert attachment.kind == "receipt"
    assert attachment.sha256


def test_create_with_an_invalid_receipt_saves_nothing_and_says_why(client):
    _login(client)
    bad = SimpleUploadedFile("bon.png", b"not an image", content_type="image/png")

    response = client.post(
        reverse("expenses:create"),
        _header() | _lines(("", "12.34", "")) | {"receipt-file": bad},
    )

    assert response.status_code == 200
    assert Expense.objects.count() == 0
    assert Attachment.objects.count() == 0
    assert "Huismus kan deze afbeelding niet openen." in response.content.decode()


def test_create_with_a_receipt_but_another_error_asks_to_choose_it_again(client):
    """A browser doesn't keep a chosen file when the page comes back with
    an error, so the page says so instead of silently losing it."""
    _login(client)

    response = client.post(
        reverse("expenses:create"),
        _header() | _lines(("", "", "")) | {"receipt-file": _receipt_png()},
    )

    assert response.status_code == 200
    assert Expense.objects.count() == 0
    assert Attachment.objects.count() == 0
    assert "Kies het bonnetje opnieuw" in response.content.decode()


def test_the_new_page_has_a_receipt_field_in_its_form_and_the_edit_page_not(client):
    """On the edit page receipts have their own section with its own
    upload; a second file field in the expense form would be confusing."""
    _login(client)
    expense = create_expense([ExpenseLineInput("Hosting", 1000, None, None)], date="2026-01-15")

    new_page = client.get(reverse("expenses:create")).content.decode()
    edit_page = client.get(reverse("expenses:edit", kwargs={"pk": expense.pk})).content.decode()

    assert 'name="receipt-file"' in new_page
    assert 'enctype="multipart/form-data"' in new_page
    assert 'name="receipt-file"' not in edit_page


def test_the_receipt_comes_first_on_the_new_and_the_edit_page(client):
    """The receipt is what the rest is typed from, so it sits above the
    date and the lines (Arne, 2026-11-04)."""
    _login(client)
    expense = create_expense([ExpenseLineInput("Hosting", 1000, None, None)], date="2026-01-15")

    new_page = client.get(reverse("expenses:create")).content.decode()
    edit_page = client.get(reverse("expenses:edit", kwargs={"pk": expense.pk})).content.decode()

    assert new_page.index('name="receipt-file"') < new_page.index('name="date"')
    assert edit_page.index(
        reverse("expenses:receipt_upload", kwargs={"pk": expense.pk})
    ) < edit_page.index('name="date"')


def test_receipt_delete_removes_the_attachment(client):
    _login(client)
    expense = Expense.objects.create(date="2026-01-15", amount_cents=1000)
    attachment = Attachment.objects.create(expense=expense, file=_receipt_png(), kind="receipt")

    response = client.post(
        reverse(
            "expenses:receipt_delete", kwargs={"pk": expense.pk, "attachment_pk": attachment.pk}
        )
    )

    assert response.status_code == 302
    assert Attachment.objects.count() == 0


def test_category_list_requires_login(client):
    response = client.get(reverse("expenses:category_list"))
    assert response.status_code == 302


def test_category_create(client):
    _login(client)
    response = client.post(
        reverse("expenses:category_list"), {"name": "Software", "sort_order": "0"}
    )
    assert response.status_code == 302
    assert ExpenseCategory.objects.filter(name="Software").exists()


def test_category_edit_renames_it(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Softwear")

    response = client.post(
        reverse("expenses:category_edit", kwargs={"pk": category.pk}),
        {"name": "Software", "sort_order": "0"},
    )

    assert response.status_code == 302
    category.refresh_from_db()
    assert category.name == "Software"


def test_category_delete_when_unused(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Software")

    response = client.post(reverse("expenses:category_delete", kwargs={"pk": category.pk}))

    assert response.status_code == 302
    assert ExpenseCategory.objects.count() == 0


def test_category_delete_when_in_use_shows_an_error_and_keeps_it(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Software")
    create_expense([ExpenseLineInput("", 1000, None, category)], date="2026-01-15")

    response = client.post(
        reverse("expenses:category_delete", kwargs={"pk": category.pk}), follow=True
    )

    assert ExpenseCategory.objects.count() == 1
    messages = list(response.context["messages"])
    assert any("Er horen nog uitgaven bij deze categorie." in str(m) for m in messages)


def test_new_category_with_only_a_name_goes_to_the_bottom(client):
    _login(client)
    ExpenseCategory.objects.create(name="Software", sort_order=4)

    client.post(reverse("expenses:category_list"), {"name": "Verzekeringen"})

    assert ExpenseCategory.objects.get(name="Verzekeringen").sort_order == 5


def test_category_list_shows_the_edit_row_and_expense_counts(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Software")
    create_expense([ExpenseLineInput("", 1000, None, category)], date="2026-01-15")

    response = client.get(reverse("expenses:category_list"), {"bewerk": category.pk})

    assert response.context["editing_pk"] == category.pk
    assert 'class="is-editing"' in response.content.decode()
    assert response.context["categories"][0].expense_count == 1


def test_category_edit_get_opens_the_inline_edit_row(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Software")

    response = client.get(reverse("expenses:category_edit", kwargs={"pk": category.pk}))

    assert response.status_code == 302
    assert response.url.endswith(f"?bewerk={category.pk}")


def test_category_edit_with_an_empty_name_keeps_the_row_open_with_the_error(client):
    _login(client)
    category = ExpenseCategory.objects.create(name="Software")

    response = client.post(
        reverse("expenses:category_edit", kwargs={"pk": category.pk}),
        {"name": "", "sort_order": "1"},
    )

    assert response.status_code == 200
    assert response.context["editing_pk"] == category.pk
    assert 'aria-invalid="true"' in response.content.decode()
