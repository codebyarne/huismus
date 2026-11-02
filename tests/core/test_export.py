# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The export (SPEC.md M19): one ZIP with CSVs, PDFs and receipts, readable
without Huismus."""

import csv
import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.urls import reverse
from django.utils import translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core import export
from huismus.core.models import Attachment
from huismus.documents.drafts import create_credit_note
from huismus.documents.issuing import issue
from huismus.documents.models import Document, DocumentLine, Payment
from huismus.documents.quoting import accept_quote, convert_to_invoice, send_quote
from huismus.documents.reopening import reopen
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import ExpenseCategory
from huismus.reports.year_overview import compute_year_overview

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _business():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.address_line1 = "Hoofdstraat 1"
    settings.postal_code = "1234 AB"
    settings.city = "Amsterdam"
    settings.kvk_number = "12345678"
    settings.iban = "NL91ABNA0417164300"
    settings.email = "info@example.invalid"
    settings.reverse_charge_text = "Btw verlegd."
    settings.save()


def _contact(**fields):
    fields.setdefault("company_name", "Klant BV")
    return Contact.objects.create(**fields)


def _draft(kind="invoice", *, contact=None, issue_date="2025-03-10", lines=((1, 10000, 0),)):
    document = Document.objects.create(
        kind=kind,
        status="draft",
        contact=contact or _contact(),
        issue_date=date.fromisoformat(issue_date),
    )
    for position, (quantity, price, rate, *charged) in enumerate(lines):
        DocumentLine.objects.create(
            document=document,
            position=position,
            description=f"Regel {position + 1}",
            quantity=quantity,
            unit_price_cents=price,
            tax_rate_bp=rate,
            reverse_charge=bool(charged and charged[0]),
        )
    return document


def _invoice(**kwargs):
    return issue(_draft(**kwargs))


def _credit_note(invoice, issue_date="2025-04-01"):
    credit_note = create_credit_note(Document.objects.with_payment_totals().get(pk=invoice.pk))
    credit_note.issue_date = date.fromisoformat(issue_date)
    credit_note.save()
    return issue(credit_note)


def _zip(year=None) -> zipfile.ZipFile:
    buffer = io.BytesIO()
    export.write_zip(buffer, year)
    buffer.seek(0)
    return zipfile.ZipFile(buffer)


def _rows(archive, name) -> list[dict]:
    text = archive.read(name).decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _cents(text: str) -> int:
    """ "-93,39" -> -9339."""
    sign = -1 if text.startswith("-") else 1
    whole, _comma, fraction = text.lstrip("-").partition(",")
    return sign * (int(whole) * 100 + int(fraction or 0))


def test_a_years_revenue_excluding_vat_adds_up_to_the_year_overview():
    first = _invoice(lines=((2, 12550, 2100), (1, 999, 900)))
    _invoice(lines=((Decimal("1.5"), 3333, 2100),))
    _credit_note(first)
    _invoice(issue_date="2024-12-31")  # another year

    rows = _rows(_zip(2025), "facturen.csv")

    assert len(rows) == 3
    assert sum(_cents(row["bedrag excl. btw"]) for row in rows) == (
        compute_year_overview(2025).revenue_cents
    )


def test_a_credit_note_is_negative_in_the_invoices_and_the_lines():
    invoice = _invoice(lines=((1, 10000, 2100),))
    credit_note = _credit_note(invoice)

    archive = _zip()
    row = next(r for r in _rows(archive, "facturen.csv") if r["nummer"] == credit_note.number)
    line = next(r for r in _rows(archive, "regels.csv") if r["nummer"] == credit_note.number)

    assert row["soort"] == "creditnota"
    assert row["gecrediteerde factuur"] == invoice.number
    assert (row["bedrag excl. btw"], row["btw"], row["totaal incl. btw"]) == (
        "-100,00",
        "-21,00",
        "-121,00",
    )
    assert row["omzet 21%"] == "-100,00"
    assert row["btw 21%"] == "-21,00"
    assert line["soort"] == "creditnota"
    assert line["bedrag excl. btw"] == "-100,00"


def test_a_credit_note_without_its_invoice_has_an_empty_credited_invoice():
    # An import can have a credit note that names no invoice; issue()
    # refuses that, the import stores it as it is.
    document = _draft(kind="credit_note")
    Document.objects.filter(pk=document.pk).update(
        status="issued", number="CN-1", subtotal_cents=10000, total_cents=10000
    )

    row = _rows(_zip(), "facturen.csv")[0]

    assert (row["soort"], row["gecrediteerde factuur"]) == ("creditnota", "")


def test_every_rate_gets_its_own_columns_and_reverse_charge_its_own():
    invoice = _invoice(lines=((1, 10000, 2100), (1, 4000, 900), (1, 30000, 0, True)))
    _invoice(lines=((1, 5000, 600),))

    archive = _zip()
    rows = _rows(archive, "facturen.csv")
    row = next(r for r in rows if r["nummer"] == invoice.number)
    lines = [r for r in _rows(archive, "regels.csv") if r["nummer"] == invoice.number]

    for column in ("omzet 6%", "btw 6%", "omzet 9%", "btw 9%", "omzet 21%", "btw 21%"):
        assert column in row
    assert (row["omzet 21%"], row["btw 21%"]) == ("100,00", "21,00")
    assert (row["omzet 9%"], row["btw 9%"]) == ("40,00", "3,60")
    assert (row["omzet 6%"], row["btw 6%"]) == ("", "")
    assert row["omzet btw verlegd"] == "300,00"
    assert [line["btw verlegd"] for line in lines] == ["nee", "nee", "ja"]
    assert [line["btw-tarief (%)"] for line in lines] == ["21", "9", "0"]


def test_an_import_that_shows_one_vat_row_leaves_the_rate_columns_empty():
    # Moneybird's own VAT (a rounding cent): the screen shows one "Btw" row.
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
        status="issued",
        subtotal_cents=9000,
        tax_cents=1891,
        total_cents=10891,
        contact_snapshot={"display_name": "Klant BV"},
    )

    row = _rows(_zip(), "facturen.csv")[0]

    assert row["omzet 21%"] == ""
    assert row["btw 21%"] == ""
    assert (row["bedrag excl. btw"], row["btw"], row["totaal incl. btw"]) == (
        "90,00",
        "18,91",
        "108,91",
    )
    assert row["bron"] == "Moneybird"


def test_drafts_and_reopened_documents_are_left_out():
    kept = _invoice()
    reopen(_invoice())
    _draft()
    _draft(kind="quote")
    sent = send_quote(_draft(kind="quote"))

    archive = _zip()

    assert [r["nummer"] for r in _rows(archive, "facturen.csv")] == [kept.number]
    assert [r["nummer"] for r in _rows(archive, "offertes.csv")] == [sent.number]
    assert {r["nummer"] for r in _rows(archive, "regels.csv")} == {kept.number, sent.number}
    assert sorted(n for n in archive.namelist() if n.startswith("pdf/")) == [
        f"pdf/facturen/{kept.number}.pdf",
        f"pdf/offertes/{sent.number}.pdf",
    ]


def test_the_customer_comes_from_the_snapshot_not_the_current_contact():
    contact = _contact(company_name="Oude Naam BV", vat_number="NL000099998B57", country="NL")
    invoice = _invoice(contact=contact)
    contact.company_name = "Nieuwe Naam BV"
    contact.country = "BE"
    contact.save()

    row = _rows(_zip(), "facturen.csv")[0]
    contacts = _rows(_zip(), "klanten.csv")

    assert row["nummer"] == invoice.number
    assert row["klant"] == "Oude Naam BV"
    assert row["land klant"] == "NL"
    assert row["btw-nummer klant"] == "NL000099998B57"
    assert contacts[0]["bedrijfsnaam"] == "Nieuwe Naam BV"


def test_an_import_gets_its_original_pdf_and_others_the_pdf_from_the_snapshot():
    imported = _invoice()
    Attachment.objects.create(
        document=imported,
        file=ContentFile(b"%PDF-1.4 het origineel", name="origineel.pdf"),
        kind="original_pdf",
        source="moneybird",
    )
    made_here = _invoice()

    archive = _zip()

    assert archive.read(f"pdf/facturen/{imported.number}.pdf") == b"%PDF-1.4 het origineel"
    assert archive.read(f"pdf/facturen/{made_here.number}.pdf").startswith(b"%PDF")


def test_the_csv_form_semicolons_decimal_comma_iso_dates_and_a_bom():
    _invoice(lines=((1, 123456, 0),))

    raw = _zip().read("facturen.csv")

    assert raw.startswith("﻿".encode())
    header, first = raw.decode("utf-8-sig").splitlines()[:2]
    assert header.startswith("soort;nummer;factuurdatum;")
    assert ";2025-03-10;" in first
    assert ";1234,56;" in first
    assert "1.234" not in first


def test_file_names_columns_and_values_follow_the_language_of_the_screen():
    credit_note = _credit_note(_invoice())

    with translation.override("en"):
        archive = _zip()

    names = archive.namelist()
    assert "invoices.csv" in names
    assert "quotes.csv" in names
    assert "lines.csv" in names
    assert "customers.csv" in names
    assert "expenses.csv" in names
    assert "expense-lines.csv" in names
    assert f"pdf/credit-notes/{credit_note.number}.pdf" in names
    row = next(r for r in _rows(archive, "invoices.csv") if r["number"] == credit_note.number)
    assert row["kind"] == "credit note"
    assert row["amount excl. VAT"] == "-100,00"


def test_payment_columns():
    invoice = _invoice(lines=((1, 10000, 0),))
    Payment.objects.create(document=invoice, paid_on="2025-03-20", amount_cents=4000)
    Payment.objects.create(document=invoice, paid_on="2025-03-25", amount_cents=1000)

    row = _rows(_zip(), "facturen.csv")[0]

    assert row["betaalstatus"] == "deels betaald"
    assert (row["betaald"], row["openstaand"], row["laatst betaald op"]) == (
        "50,00",
        "50,00",
        "2025-03-25",
    )
    assert row["bron"] == "Huismus"


def test_quotes_with_their_status_and_the_invoice_they_became():
    quote = accept_quote(send_quote(_draft(kind="quote", lines=((1, 20000, 2100),))))
    invoice = issue(convert_to_invoice(quote))

    row = _rows(_zip(), "offertes.csv")[0]

    assert row["nummer"] == quote.number
    assert row["status"] == "geaccepteerd"
    assert row["geaccepteerd op"] == quote.accepted_on.isoformat()
    assert row["totaal incl. btw"] == "242,00"
    assert row["factuur"] == invoice.number


def test_a_year_takes_documents_and_expenses_of_that_year_and_every_contact():
    _invoice(issue_date="2024-06-01")
    this_year = _invoice(issue_date="2025-06-01")
    _contact(company_name="Gearchiveerd BV", archived=True)
    create_expense([ExpenseLineInput("Laptop", 99900, None, None)], date="2024-02-02")
    kept = create_expense([ExpenseLineInput("Telefoon", 50000, None, None)], date="2025-02-02")

    archive = _zip(2025)

    assert [r["nummer"] for r in _rows(archive, "facturen.csv")] == [this_year.number]
    assert [r["uitgavenummer"] for r in _rows(archive, "uitgaven.csv")] == [str(kept.pk)]
    contacts = _rows(archive, "klanten.csv")
    assert len(contacts) == 3
    assert {c["gearchiveerd"] for c in contacts} == {"ja", "nee"}


def test_expenses_their_lines_and_receipts():
    category = ExpenseCategory.objects.create(name="Kantoor")
    expense = create_expense(
        [
            ExpenseLineInput("Papier", 1210, 210, category),
            ExpenseLineInput("Pennen", 500, None, None),
        ],
        date="2025-01-15",
        supplier="Kantoorwinkel",
    )
    Attachment.objects.create(
        expense=expense, file=ContentFile(b"bon", name="bon.png"), kind="receipt"
    )

    archive = _zip()
    row = _rows(archive, "uitgaven.csv")[0]
    lines = _rows(archive, "uitgaveregels.csv")

    assert row["leverancier"] == "Kantoorwinkel"
    assert row["bedrag (bruto)"] == "17,10"
    assert row["btw ter info"] == "2,10"
    assert row["bonnetjes"] == f"{expense.pk}-bon.png"
    assert archive.read(f"bonnetjes/{expense.pk}-bon.png") == b"bon"
    assert [(r["omschrijving"], r["bedrag (bruto)"], r["categorie"]) for r in lines] == [
        ("Papier", "12,10", "Kantoor"),
        ("Pennen", "5,00", ""),
    ]


def test_years_to_choose_are_the_years_with_something_in_them_newest_first():
    _invoice(issue_date="2023-01-01")
    _draft(issue_date="2019-01-01")
    create_expense([ExpenseLineInput("", 100, None, None)], date="2025-01-01")

    assert export.years() == [2025, 2023]


# The page and the download.


@pytest.fixture
def logged_in(client):
    user = get_user_model().objects.create_user(username="arne", password="x")
    client.force_login(user)
    return client


def test_the_page_needs_a_login(client):
    assert client.get(reverse("business:export")).status_code == 302
    assert client.get(reverse("business:export_zip")).status_code == 302


def test_the_page_offers_everything_and_the_years_with_the_year_chosen(logged_in):
    _invoice(issue_date="2024-01-01")
    _invoice(issue_date="2025-01-01")

    html = logged_in.get(reverse("business:export"), {"jaar": "2024"}).content.decode()

    assert '<option value="">Alles</option>' in html
    assert html.index('value="2025"') < html.index('value="2024"')
    assert '<option value="2024" selected>' in html
    assert f'action="{reverse("business:export_zip")}"' in html
    assert 'method="get"' in html


def test_the_download_is_a_zip_named_after_the_choice(logged_in):
    _invoice(issue_date="2025-01-01")

    everything = logged_in.get(reverse("business:export_zip"))
    one_year = logged_in.get(reverse("business:export_zip"), {"jaar": "2025"})

    assert everything["Content-Type"] == "application/zip"
    assert 'filename="huismus-export-alles.zip"' in everything["Content-Disposition"]
    assert 'filename="huismus-export-2025.zip"' in one_year["Content-Disposition"]
    archive = zipfile.ZipFile(io.BytesIO(b"".join(one_year.streaming_content)))
    assert "facturen.csv" in archive.namelist()


def test_the_download_sends_the_pages_token_back_as_a_cookie(logged_in):
    # The busy button on the page waits for it (app.js, data-download).
    response = logged_in.get(reverse("business:export_zip"), {"klaar": "17305551234"})
    assert response.cookies["huismus_download"].value == "17305551234"

    for token in ("", "<script>", "1" * 40):
        response = logged_in.get(reverse("business:export_zip"), {"klaar": token})
        assert "huismus_download" not in response.cookies


def test_a_year_that_is_not_a_number_exports_everything(logged_in):
    response = logged_in.get(reverse("business:export_zip"), {"jaar": "x"})
    assert 'filename="huismus-export-alles.zip"' in response["Content-Disposition"]


def test_the_settings_overview_has_an_export_card_after_backups(logged_in):
    html = logged_in.get(reverse("business:overview")).content.decode()
    assert html.index(reverse("business:backups")) < html.index(reverse("business:export"))


def test_the_year_overview_links_to_the_export_of_that_year(logged_in):
    html = logged_in.get(reverse("reports:year_overview"), {"jaar": "2024"}).content.decode()
    assert f"{reverse('business:export')}?jaar=2024" in html


def test_on_an_empty_administration_the_page_offers_only_everything(logged_in):
    html = logged_in.get(reverse("business:export")).content.decode()
    assert '<option value="" selected>Alles</option>' in html
    assert html.count("<option") == 1
