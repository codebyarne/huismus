# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import of Huismus's own CSV format (SPEC.md M22), file by file:
what it reads, what it refuses and what it says about it. The round trip
with the export is in test_csv_roundtrip.py."""

import io
import zipfile
from datetime import date

import pytest
from django.utils import translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact, ContactPerson
from huismus.documents.models import Document, Payment
from huismus.expenses.lines import ExpenseLineInput, create_expense
from huismus.expenses.models import Expense
from huismus.imports import csv_template
from huismus.imports.pipeline import run_import
from huismus.imports.sources import ImportSourceError

pytestmark = pytest.mark.django_db

CONTACTS = "klantnummer;bedrijfsnaam;achternaam\n7;Klant BV;\n"
INVOICE_HEADER = (
    "soort;nummer;factuurdatum;klantnummer;bedrag excl. btw;btw;totaal incl. btw;"
    "omzet 21%;btw 21%;betaalstatus;betaald;laatst betaald op;gecrediteerde factuur"
)
LINE_HEADER = "soort;nummer;omschrijving;aantal;prijs per eenheid;btw-tarief (%)"
INVOICE = "factuur;2025-0001;2025-03-10;7;100,00;21,00;121,00;100,00;21,00;;;;\n"
LINE = "factuur;2025-0001;Werk;1;100,00;21\n"


@pytest.fixture(autouse=True)
def _business():
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.kor_enabled = False
    settings.save()


def _zip(files: dict) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content if isinstance(content, bytes) else content.encode())
    return buffer.getvalue()


def _run(tmp_path, files: dict, *, commit=True):
    path = tmp_path / "import.zip"
    path.write_bytes(_zip(files))
    return run_import(path, commit=commit)


def _invoice_files(invoice=INVOICE, line=LINE, **more) -> dict:
    return {
        "klanten.csv": CONTACTS,
        "facturen.csv": f"{INVOICE_HEADER}\n{invoice}",
        "regels.csv": f"{LINE_HEADER}\n{line}",
        **more,
    }


def test_the_template_as_it_is_brings_nothing_in(tmp_path):
    for language in ("nl", "en"):
        with translation.override(language):
            content = csv_template.template_zip()
        path = tmp_path / f"{language}.zip"
        path.write_bytes(content)

        run = run_import(path, commit=True)

        assert not Document.objects.exists()
        assert not Contact.objects.exists()
        assert not ContactPerson.objects.exists()
        assert not Expense.objects.exists()
        assert len([note for note in run.report["notes"] if "voorbeeld" in note.lower()]) == 4


def test_the_template_with_your_own_data_comes_in(tmp_path):
    with translation.override("en"):
        content = csv_template.template_zip()
    files = {}
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        for name in archive.namelist():
            text = archive.read(name).decode("utf-8-sig")
            for example, own in (
                ("Example Ltd", "Real Ltd"),
                ("Example shop", "Real shop"),
                ("Sam Example", "Sam Real"),
            ):
                text = text.replace(example, own)
            files[name] = text

    run = _run(tmp_path, files)

    assert run.report["notes"] == []
    assert Contact.objects.get().company_name == "Real Ltd"
    assert ContactPerson.objects.get().contact.customer_number == "1"
    invoice = Document.objects.get(kind="invoice")
    assert (invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents) == (15000, 3150, 18150)
    assert invoice.related_document == Document.objects.get(kind="quote")
    assert Payment.objects.get().amount_cents == 18150
    expense = Expense.objects.get()
    assert (expense.amount_cents, expense.vat_info_cents) == (1210, 210)
    assert expense.lines.get().vat_rate == "21"
    assert run.report["sales_invoices"]["missing_pdfs"] == ["2026-0001"]


def test_a_missing_required_column_stops_the_import_with_its_name(tmp_path):
    files = _invoice_files()
    files["facturen.csv"] = files["facturen.csv"].replace("factuurdatum", "dag")

    with pytest.raises(ImportSourceError, match="facturen.csv.*‘factuurdatum’"):
        _run(tmp_path, files)
    assert not Contact.objects.exists()


def test_an_unknown_column_is_named_and_left_out(tmp_path):
    files = _invoice_files()
    files["klanten.csv"] = "klantnummer;bedrijfsnaam;achternaam;Fax\n7;Klant BV;;010\n"

    run = _run(tmp_path, files)

    assert any("klanten.csv" in note and "Fax" in note for note in run.report["notes"])
    assert Contact.objects.get().company_name == "Klant BV"


def test_commas_between_the_columns_are_not_guessed(tmp_path):
    with pytest.raises(ImportSourceError, match="puntkomma"):
        _run(tmp_path, {"klanten.csv": "klantnummer,bedrijfsnaam,achternaam\n7,Klant BV,\n"})


@pytest.mark.parametrize(
    ("invoice", "column"),
    [
        (INVOICE.replace("2025-03-10", "10/03/25"), "factuurdatum"),
        (INVOICE.replace("121,00", "honderd"), "totaal incl. btw"),
    ],
)
def test_a_cell_that_cannot_be_read_stops_the_import(tmp_path, invoice, column):
    with pytest.raises(ImportSourceError, match=f"facturen.csv, rij 2, kolom ‘{column}’"):
        _run(tmp_path, _invoice_files(invoice=invoice))
    assert not Document.objects.exists()


def test_day_month_year_dates_and_windows_encoding_are_read(tmp_path):
    files = _invoice_files(invoice=INVOICE.replace("2025-03-10", "10-3-2025"))
    files["klanten.csv"] = "klantnummer;bedrijfsnaam;achternaam\n7;Café Zoë;\n".encode("cp1252")

    _run(tmp_path, files)

    assert Document.objects.get().issue_date == date(2025, 3, 10)
    assert Contact.objects.get().company_name == "Café Zoë"


def test_vat_per_rate_that_differs_from_the_lines_refuses_the_invoice(tmp_path):
    invoice = INVOICE.replace("100,00;21,00;;", "100,00;20,00;;")

    run = _run(tmp_path, _invoice_files(invoice=invoice))

    assert not Document.objects.exists()
    (refused,) = run.report["sales_invoices"]["refused"]
    assert "2025-0001" in refused and "btw 21%" in refused
    assert "20,00" in refused and "21,00" in refused


def test_empty_rate_cells_are_not_checked(tmp_path):
    invoice = "factuur;2025-0001;2025-03-10;7;100,00;21,00;121,00;;;;;;\n"

    run = _run(tmp_path, _invoice_files(invoice=invoice))

    assert run.report["sales_invoices"]["refused"] == []
    assert Document.objects.get().vat_rows.get().tax_cents == 2100


def test_totals_that_differ_from_the_lines_come_in_as_the_file_has_them(tmp_path):
    invoice = "factuur;2025-0001;2025-03-10;7;100,00;21,01;121,01;;;;;;\n"

    run = _run(tmp_path, _invoice_files(invoice=invoice))

    document = Document.objects.get()
    assert (document.tax_cents, document.total_cents) == (2101, 12101)
    assert not document.vat_rows.exists()
    (discrepancy,) = run.report["sales_invoices"]["discrepancies"]
    assert "21,01" in discrepancy and "21,00" in discrepancy


def test_an_invoice_without_its_customer_or_lines_is_skipped(tmp_path):
    invoices = INVOICE + "factuur;2025-0002;2025-03-11;99;100,00;21,00;121,00;;;;;;\n"
    invoices += "factuur;2025-0003;2025-03-12;7;100,00;21,00;121,00;;;;;;\n"
    lines = LINE + "factuur;2025-0002;Werk;1;100,00;21\n"

    run = _run(tmp_path, _invoice_files(invoice=invoices, line=lines))

    report = run.report["sales_invoices"]
    assert report["skipped_missing_contact"] == ["2025-0002"]
    assert report["skipped_no_lines"] == ["2025-0003"]
    assert (report["in_export"], report["new"]) == (3, 1)


def test_another_currency_stops_the_import_and_no_column_is_euros(tmp_path):
    files = _invoice_files()
    files["facturen.csv"] = (
        "soort;nummer;factuurdatum;klantnummer;valuta;bedrag excl. btw;btw;totaal incl. btw\n"
        "factuur;2025-0001;2025-03-10;7;USD;100,00;21,00;121,00\n"
    )
    with pytest.raises(ImportSourceError, match="USD"):
        _run(tmp_path, files)

    _run(tmp_path, _invoice_files())
    assert Document.objects.get().currency == "EUR"


def test_a_credit_note_finds_its_invoice_or_is_named(tmp_path):
    invoices = (
        INVOICE
        + "creditnota;2025-0002;2025-04-01;7;-100,00;-21,00;-121,00;;;;;;2025-0001\n"
        + "creditnota;2025-0003;2025-04-02;7;-10,00;-2,10;-12,10;;;;;;2025-0001\n"
        + "creditnota;2025-0004;2025-04-03;7;-10,00;-2,10;-12,10;;;;;;1999-0001\n"
    )
    lines = (
        LINE
        + "creditnota;2025-0002;Werk;1;-100,00;21\n"
        + "creditnota;2025-0003;Werk;1;-10,00;21\n"
        + "creditnota;2025-0004;Werk;1;-10,00;21\n"
    )

    run = _run(tmp_path, _invoice_files(invoice=invoices, line=lines))

    report = run.report["sales_invoices"]
    first = Document.objects.get(number="2025-0002")
    assert first.related_document.number == "2025-0001"
    assert first.total_cents == 12100
    # More than the invoice together (SPEC.md invariant 5).
    assert not Document.objects.filter(number="2025-0003").exists()
    assert "2025-0003" in report["refused"][0]
    assert report["unlinked_credit_notes"] == ["2025-0004"]
    assert Document.objects.get(number="2025-0004").related_document is None


def test_a_payment_without_a_date_or_an_amount_is_a_point_to_check(tmp_path):
    invoices = (
        "factuur;2025-0001;2025-03-10;7;100,00;21,00;121,00;;;betaald;121,00;2025-03-20;\n"
        "factuur;2025-0002;2025-03-10;7;100,00;21,00;121,00;;;betaald;121,00;;\n"
        "factuur;2025-0003;2025-03-10;7;100,00;21,00;121,00;;;deels betaald;;;\n"
    )
    lines = "".join(f"factuur;2025-000{n};Werk;1;100,00;21\n" for n in (1, 2, 3))

    run = _run(tmp_path, _invoice_files(invoice=invoices, line=lines))

    payment = Payment.objects.get()
    assert (payment.document.number, payment.amount_cents) == ("2025-0001", 12100)
    assert payment.paid_on == date(2025, 3, 20)
    issues = run.report["sales_invoices"]["payment_issues"]
    assert len(issues) == 2
    assert "2025-0002" in issues[0] and "2025-0003" in issues[1]


def test_an_expense_that_is_not_the_sum_of_its_lines_is_refused(tmp_path):
    files = {
        "uitgaven.csv": (
            "uitgavenummer;datum;leverancier;bedrag (bruto);btw\n"
            "1;2025-02-02;Hosting BV;100,00;\n"
            "2;2025-02-03;Kiosk;5,00;\n"
            "3;2025-02-04;Drukker;12,10;2,10\n"
        ),
        "uitgaveregels.csv": (
            "uitgavenummer;bedrag (bruto);btw;btw-tarief;categorie\n"
            "1;60,00;;;\n1;30,00;;;\n"
            "3;12,10;2,10;hoog;Drukwerk\n"
        ),
    }

    run = _run(tmp_path, files)

    report = run.report["expenses"]
    assert [expense.supplier for expense in Expense.objects.order_by("date")] == [
        "Kiosk",
        "Drukker",
    ]
    assert "Hosting BV" in report["refused"][0] and "90,00" in report["refused"][0]
    assert report["unknown_vat_rates"] == ["Drukker: hoog"]
    assert report["new_categories"] == ["Drukwerk"]
    # Without the KOR: both new lines have no rate Huismus knows.
    assert report["lines_without_rate"] == 2
    assert (report["in_export"], report["new"]) == (3, 2)


def test_expenses_already_in_huismus_are_named_not_skipped(tmp_path):
    create_expense([ExpenseLineInput("", 500, None, None)], date=date(2025, 2, 3), supplier="Kiosk")
    files = {
        "uitgaven.csv": "uitgavenummer;datum;leverancier;bedrag (bruto)\n2;2025-02-03;Kiosk;5,00\n"
    }

    run = _run(tmp_path, files)
    again = _run(tmp_path, files)

    assert Expense.objects.count() == 2
    assert run.report["expenses"]["other_expenses"] == 1
    assert len(run.report["expenses"]["possible_duplicates"]) == 1
    assert again.report["expenses"]["unchanged"] == 1

    files["uitgaven.csv"] = files["uitgaven.csv"].replace("5,00", "6,00")
    changed = _run(tmp_path, files)
    assert changed.report["expenses"]["changed_in_file"] == ["Kiosk"]
    assert Expense.objects.get(source="csv").amount_cents == 500


def test_only_a_pdf_or_a_photo_becomes_a_receipt(tmp_path):
    """What an expense names in "bonnetjes" is only kept when it is a file a
    receipt can be, as the upload and the Moneybird import do. Anything else
    (an .svg or .html can carry a script) is named and left out."""
    files = {
        "uitgaven.csv": (
            "uitgavenummer;datum;leverancier;bedrag (bruto);bonnetjes\n"
            "2;2025-02-03;Kiosk;5,00;bon.jpg | plaatje.svg | pagina.html\n"
        ),
        "bonnetjes/bon.jpg": b"jpg",
        "bonnetjes/plaatje.svg": b"<svg xmlns='http://www.w3.org/2000/svg'><script/></svg>",
        "bonnetjes/pagina.html": b"<script></script>",
    }

    run = _run(tmp_path, files)

    names = [a.file.name.rsplit("/", 1)[-1] for a in Expense.objects.get().attachments.all()]
    assert len(names) == 1 and names[0].endswith(".jpg")
    (note,) = run.report["notes"]
    assert "plaatje.svg" in note and "pagina.html" in note and "bon.jpg" not in note


def test_files_that_belong_nowhere_are_named(tmp_path):
    files = _invoice_files(
        **{
            "pdf/facturen/2025-0001.pdf": b"%PDF-een",
            "pdf/facturen/1999-0001.pdf": b"%PDF-niets",
            "bonnetjes/los.jpg": b"jpg",
            "LEESMIJ.txt": "uitleg",
        }
    )

    run = _run(tmp_path, files)

    (note,) = run.report["notes"]
    assert "1999-0001.pdf" in note and "los.jpg" in note
    assert "2025-0001.pdf" not in note and "LEESMIJ" not in note
    assert Document.objects.get().primary_original_pdf().file.read() == b"%PDF-een"


def test_a_contact_made_here_is_left_as_it_is(tmp_path):
    own = Contact.objects.create(company_name="Eigen naam", customer_number="7")
    files = _invoice_files(
        **{"contactpersonen.csv": "klantnummer;naam\n7;Sam Jansen\n12;Kim de Boer\n"}
    )

    run = _run(tmp_path, files)

    own.refresh_from_db()
    assert own.company_name == "Eigen naam"
    assert not own.persons.exists()
    assert Document.objects.get().contact == own
    report = run.report["contacts"]
    assert (report["new"], report["unchanged"]) == (0, 1)
    assert report["persons_without_contact"] == ["Kim de Boer (12)"]


def test_contact_persons_come_in_once(tmp_path):
    files = {
        "klanten.csv": CONTACTS,
        "contactpersonen.csv": (
            "klantnummer;naam;e-mail;afdeling\n7;Sam Jansen;sam@voorbeeld.example;Inkoop\n"
        ),
    }

    first = _run(tmp_path, files)
    again = _run(tmp_path, files)

    person = ContactPerson.objects.get()
    assert (person.contact.customer_number, person.name, person.department) == (
        "7",
        "Sam Jansen",
        "Inkoop",
    )
    assert first.report["contacts"]["persons_new"] == 1
    assert again.report["contacts"]["persons_new"] == 0


def test_a_contact_without_a_name_is_refused(tmp_path):
    run = _run(tmp_path, {"klanten.csv": CONTACTS + "8;;\n"})

    assert Contact.objects.count() == 1
    assert "rij 3" in run.report["contacts"]["refused"][0]


def test_documents_without_a_lines_file_stop_the_import(tmp_path):
    files = _invoice_files()
    del files["regels.csv"]

    with pytest.raises(ImportSourceError, match="regels"):
        _run(tmp_path, files)


def test_files_huismus_does_not_know_stop_the_import(tmp_path):
    with pytest.raises(ImportSourceError, match="herkent geen"):
        _run(tmp_path, {"iets.csv": "a;b;c\n1;2;3\n"})


def test_moneybird_files_and_csv_files_together_are_refused(tmp_path):
    from pathlib import Path

    fixtures = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"
    with zipfile.ZipFile(fixtures / "lindeboom_communicatie_2019.zip") as moneybird:
        files = {name: moneybird.read(name) for name in moneybird.namelist()}
    files["klanten.csv"] = CONTACTS

    with pytest.raises(ImportSourceError, match="door elkaar"):
        _run(tmp_path, files)
    assert not Contact.objects.exists()


def test_a_quote_with_a_status_huismus_does_not_know_stops_the_import(tmp_path):
    files = {
        "klanten.csv": CONTACTS,
        "offertes.csv": (
            "nummer;datum;klantnummer;status;bedrag excl. btw;btw;totaal incl. btw\n"
            "2025-001;2025-03-01;7;misschien;100,00;21,00;121,00\n"
        ),
        "regels.csv": f"{LINE_HEADER}\nofferte;2025-001;Werk;1;100,00;21\n",
    }

    with pytest.raises(ImportSourceError, match="offertes.csv, rij 2, kolom ‘status’"):
        _run(tmp_path, files)


def test_an_empty_vat_cell_and_an_empty_rate_are_zero(tmp_path):
    invoice = "factuur;2025-0001;2025-03-10;7;100,00;;100,00;;;;;;\n"

    run = _run(tmp_path, _invoice_files(invoice=invoice, line="factuur;2025-0001;Werk;1;100,00;\n"))

    document = Document.objects.get()
    assert (document.tax_cents, document.lines.get().tax_rate_bp) == (0, 0)
    assert run.report["sales_invoices"]["discrepancies"] == []


@pytest.mark.parametrize("quantity", ["NaN", "1e999", "1,23456", "12345678"])
def test_a_quantity_huismus_cannot_keep_stops_the_import(tmp_path, quantity):
    line = f"factuur;2025-0001;Werk;{quantity};100,00;21\n"

    with pytest.raises(ImportSourceError, match="regels.csv, rij 2, kolom ‘aantal’"):
        _run(tmp_path, _invoice_files(line=line))


def test_a_row_is_named_by_its_number_in_the_file_empty_rows_counted(tmp_path):
    files = _invoice_files()
    files["klanten.csv"] = "klantnummer;bedrijfsnaam;achternaam\n\n7;Klant BV;\n;Zonder nummer;\n"

    with pytest.raises(ImportSourceError, match="klanten.csv, rij 4, kolom ‘klantnummer’"):
        _run(tmp_path, files)


def test_only_the_apostrophe_the_export_put_in_front_is_taken_off(tmp_path):
    files = {
        "klanten.csv": "klantnummer;bedrijfsnaam;achternaam\n7;'=Som BV;\n8;'t Hoekje '-korting;\n"
    }

    _run(tmp_path, files)

    assert list(Contact.objects.order_by("customer_number").values_list("company_name", flat=True))
    names = Contact.objects.order_by("customer_number").values_list("company_name", flat=True)
    assert list(names) == ["=Som BV", "'t Hoekje '-korting"]


def test_letters_huismus_cannot_read_stop_the_import(tmp_path):
    # 0x81 is no letter in UTF-8 nor in Windows's own encoding.
    files = {"klanten.csv": b"klantnummer;bedrijfsnaam;achternaam\n7;Klant \x81;\n"}

    with pytest.raises(ImportSourceError, match="klanten.csv"):
        _run(tmp_path, files)


def test_a_real_import_keeps_the_files_as_given_once(tmp_path, settings):
    archive = settings.DATA_DIR / "import-archief"

    def kept():
        return {path for path in archive.rglob("*") if path.is_file()}

    path = tmp_path / "bewaren.zip"
    path.write_bytes(_zip(_invoice_files()))
    before = kept()

    run_import(path, commit=False)
    assert kept() == before

    run_import(path, commit=True)
    run_import(path, commit=True)
    (new,) = kept() - before
    assert new.read_bytes() == path.read_bytes()


def test_the_command_reads_this_format_too(tmp_path):
    from django.core.management import call_command

    path = tmp_path / "import.zip"
    path.write_bytes(_zip(_invoice_files()))

    call_command("import_moneybird", str(path), "--commit")

    assert Document.objects.get().number == "2025-0001"
