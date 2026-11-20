# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The import pages for Huismus's own format (SPEC.md M22): the second tab,
the template, and the dry run and commit of a filled-in template."""

import io
import zipfile

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.imports import csv_template, staging
from huismus.imports.pipeline import run_import

pytestmark = pytest.mark.django_db


@pytest.fixture
def user_client(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")
    return client


def _filled_template() -> bytes:
    """The Dutch template with the examples replaced by own data."""
    buffer = io.BytesIO()
    with (
        zipfile.ZipFile(io.BytesIO(csv_template.template_zip())) as template,
        zipfile.ZipFile(buffer, "w") as filled,
    ):
        for name in template.namelist():
            text = template.read(name).decode("utf-8-sig")
            for example, own in (
                ("Voorbeeld BV", "Echte Klant BV"),
                ("Voorbeeldwinkel", "Echte Winkel"),
                ("Sam Voorbeeld", "Sam Jansen"),
            ):
                text = text.replace(example, own)
            filled.writestr(name, text)
    return buffer.getvalue()


def _upload(content=None, name="ingevuld.zip"):
    return SimpleUploadedFile(name, content or _filled_template(), "application/zip")


def test_the_page_has_a_tab_for_each_source(user_client):
    moneybird = user_client.get(reverse("imports:upload"))
    own = user_client.get(reverse("imports:upload_other"))

    for response in (moneybird, own):
        assert reverse("imports:upload") in response.content.decode()
        assert reverse("imports:upload_other") in response.content.decode()
    assert "Importeren uit Moneybird" in moneybird.content.decode()
    assert "Sjabloon downloaden" not in moneybird.content.decode()
    assert "Importeren uit een ander pakket of Excel" in own.content.decode()
    assert reverse("imports:template") in own.content.decode()


def test_the_template_needs_a_login(client):
    assert client.get(reverse("imports:template")).status_code == 302


@pytest.mark.parametrize(
    ("language", "filename", "files"),
    [
        (
            "nl",
            "huismus-importsjabloon.zip",
            {
                "LEESMIJ.txt",
                "facturen.csv",
                "offertes.csv",
                "regels.csv",
                "klanten.csv",
                "contactpersonen.csv",
                "uitgaven.csv",
                "uitgaveregels.csv",
            },
        ),
        (
            "en",
            "huismus-import-template.zip",
            {
                "README.txt",
                "invoices.csv",
                "quotes.csv",
                "lines.csv",
                "customers.csv",
                "contact-persons.csv",
                "expenses.csv",
                "expense-lines.csv",
            },
        ),
    ],
)
def test_the_template_is_a_zip_in_the_language_of_the_screen(
    user_client, language, filename, files
):
    with translation.override(language):
        response = user_client.get(reverse("imports:template"), HTTP_ACCEPT_LANGUAGE=language)

    assert response["Content-Disposition"] == f'attachment; filename="{filename}"'
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == files


def test_the_template_itself_passes_the_dry_run(tmp_path):
    # What the template gives is what the import reads: no missing column,
    # no unknown one, in either language.
    for language in ("nl", "en"):
        with translation.override(language):
            path = tmp_path / f"{language}.zip"
            path.write_bytes(csv_template.template_zip())
        run = run_import(path, commit=False)
        assert all("voorbeeld" in note.lower() for note in run.report["notes"]), language


def test_the_dry_run_shows_the_report_without_a_settings_block(user_client):
    response = user_client.post(reverse("imports:upload_other"), {"files": _upload()})

    page = response.content.decode()
    assert response.context["source"] == "csv"
    assert "Importeren uit een ander pakket of Excel" in page
    assert "Proefdraai: er is nog niets opgeslagen" in page
    assert "Je bedrijfsgegevens zijn nog leeg" in page
    assert "settings-business_name" not in page
    for label in ("Klanten", "Contactpersonen", "Facturen", "Offertes", "Regels", "Uitgaven"):
        assert label in page
    assert not Document.objects.exists()
    assert not Settings.objects.exists()


def test_the_notice_about_business_details_goes_once_they_are_filled_in(user_client):
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.save()

    response = user_client.post(reverse("imports:upload_other"), {"files": _upload()})

    assert "Je bedrijfsgegevens zijn nog leeg" not in response.content.decode()


def test_commit_imports_the_staged_files_and_shows_the_done_page(user_client):
    token = user_client.post(reverse("imports:upload_other"), {"files": _upload()}).context["token"]

    response = user_client.post(reverse("imports:commit"), {"token": token})

    page = response.content.decode()
    assert "Je administratie is verhuisd" in page
    assert "1 nieuwe klant, 1 factuur, 1 offerte en 1 uitgave" in page
    assert Contact.objects.get().company_name == "Echte Klant BV"
    assert Document.objects.filter(kind="invoice", status="issued").count() == 1
    assert staging.staged_path(token) is None


def test_the_files_decide_which_import_runs_not_the_tab(user_client):
    response = user_client.post(reverse("imports:upload"), {"files": _upload()})

    assert response.context["source"] == "csv"


def test_a_missing_column_shows_the_error_on_the_same_tab(user_client):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("klanten.csv", "klantnummer;bedrijfsnaam;plaats;land\n1;Klant BV;Ede;NL\n")

    response = user_client.post(
        reverse("imports:upload_other"), {"files": _upload(content.getvalue())}
    )

    page = response.content.decode()
    assert "ontbreekt de kolom ‘achternaam’" in page
    assert "Sjabloon downloaden" in page
    assert not Contact.objects.exists()


def test_refused_and_skipped_documents_are_points_to_check(user_client):
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("klanten.csv", "klantnummer;bedrijfsnaam;achternaam\n7;Klant BV;\n")
        archive.writestr(
            "facturen.csv",
            "soort;nummer;factuurdatum;klantnummer;bedrag excl. btw;btw;totaal incl. btw;btw 21%\n"
            "factuur;2025-0001;2025-03-10;7;100,00;21,00;121,00;20,00\n",
        )
        archive.writestr(
            "regels.csv",
            "soort;nummer;omschrijving;prijs per eenheid;btw-tarief (%)\n"
            "factuur;2025-0001;Werk;100,00;21\n",
        )

    response = user_client.post(
        reverse("imports:upload_other"), {"files": _upload(content.getvalue())}
    )

    page = response.content.decode()
    assert response.context["invoices"]["issue_count"] == 1
    assert "Geweigerd" in page
    assert "btw 21% in het bestand € 20,00, volgens de regels € 21,00" in page


def _refusing_zip() -> bytes:
    """One good invoice, one whose VAT per rate is wrong, no PDFs."""
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("klanten.csv", "klantnummer;bedrijfsnaam;achternaam\n7;Klant BV;\n")
        archive.writestr(
            "facturen.csv",
            "soort;nummer;factuurdatum;klantnummer;bedrag excl. btw;btw;totaal incl. btw;btw 21%\n"
            "factuur;2025-0001;2025-03-10;7;100,00;21,00;121,00;21,00\n"
            "factuur;2025-0002;2025-03-10;7;100,00;21,00;121,00;20,00\n",
        )
        archive.writestr(
            "regels.csv",
            "soort;nummer;omschrijving;prijs per eenheid;btw-tarief (%)\n"
            "factuur;2025-0001;Werk;100,00;21\nfactuur;2025-0002;Werk;100,00;21\n",
        )
    return content.getvalue()


def test_the_done_page_still_names_what_was_refused(user_client):
    token = user_client.post(
        reverse("imports:upload_other"), {"files": _upload(_refusing_zip())}
    ).context["token"]

    page = user_client.post(reverse("imports:commit"), {"token": token}).content.decode()

    assert "1 geweigerde factuur verbeteren en opnieuw importeren" in page
    assert "Factuur 2025-0002: btw 21% in het bestand € 20,00" in page
    assert "Je bestanden staan bewaard in Huismus" in page
    assert Document.objects.get().number == "2025-0001"


def test_a_missing_pdf_alone_is_no_warning_for_this_format(user_client):
    response = user_client.post(reverse("imports:upload_other"), {"files": _upload()})

    invoices = response.context["invoices"]
    assert invoices["missing_pdfs"] == ["2026-0001"]
    assert (invoices["issue_count"], invoices["warn"]) == (0, False)
    assert "Alle totalen kloppen tot op de cent. 1 zonder pdf." in response.content.decode()


def test_without_the_kor_lines_without_a_vat_rate_are_points_to_check(user_client):
    settings = Settings.load()
    settings.business_name = "Voorbeeld BV"
    settings.kor_enabled = False
    settings.save()
    content = io.BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr("uitgaven.csv", "uitgavenummer;datum;bedrag (bruto)\n1;2025-02-02;12,10\n")

    response = user_client.post(
        reverse("imports:upload_other"), {"files": _upload(content.getvalue())}
    )

    assert response.context["expenses"]["issue_count"] == 1
    assert "1 uitgaveregel heeft geen btw-tarief" in response.content.decode()


def test_the_template_link_carries_the_language_of_the_page(user_client):
    # Safari fetches a download apart from the page, in the browser's own
    # language (found by the WebKit run on main).
    page = user_client.get(reverse("imports:upload_other")).content.decode()
    assert reverse("imports:template") + "?taal=nl" in page

    response = user_client.get(
        reverse("imports:template"), {"taal": "nl"}, HTTP_ACCEPT_LANGUAGE="en"
    )
    assert "huismus-importsjabloon.zip" in response["Content-Disposition"]
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        assert "klanten.csv" in archive.namelist()

    unknown = user_client.get(reverse("imports:template"), {"taal": "xx"})
    assert unknown.status_code == 200
