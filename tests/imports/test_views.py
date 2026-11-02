# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import translation

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.imports import staging
from huismus.imports.models import ImportRun
from huismus.imports.views import _new_counts_text, _with_counts

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def _login(client):
    get_user_model().objects.create_user(username="freelancer", password="s3cret-pass")
    client.login(username="freelancer", password="s3cret-pass")


def _uploaded_zip():
    content = (FIXTURES / "lindeboom_communicatie_2019.zip").read_bytes()
    return SimpleUploadedFile("lindeboom_communicatie_2019.zip", content, "application/zip")


def _dry_run(client):
    """Upload the fixture and return what "Nu echt importeren" posts: the
    token and the settings block as the page filled it in."""
    response = client.post(reverse("imports:upload"), {"files": _uploaded_zip()})
    data = {"token": response.context["token"]}
    for bound_field in response.context["settings_form"]:
        value = bound_field.value()
        if value is True:
            data[bound_field.html_name] = "on"
        elif value not in (None, False):
            data[bound_field.html_name] = value
    return data


def test_upload_page_requires_login(client):
    response = client.get(reverse("imports:upload"))
    assert response.status_code == 302


def test_get_shows_the_upload_form(client):
    _login(client)
    response = client.get(reverse("imports:upload"))
    assert response.status_code == 200
    assert b'name="files"' in response.content


def test_upload_is_always_a_dry_run_and_keeps_the_files_for_the_commit(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {"files": _uploaded_zip()})

    assert response.status_code == 200
    assert Contact.objects.count() == 0
    assert Document.objects.count() == 0
    assert "Proefdraai" in response.content.decode()
    token = response.context["token"]
    assert staging.staged_path(token) is not None
    assert response.context["uploads"][0]["recognized"] is True


def test_commit_imports_the_files_of_the_dry_run_without_choosing_them_again(client):
    _login(client)
    confirmed = _dry_run(client)
    token = confirmed["token"]

    response = client.post(reverse("imports:commit"), confirmed)

    assert response.status_code == 200
    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7
    assert (
        "58 nieuwe klanten, 13 facturen, 7 offertes en 0 uitgaven staan nu in Huismus."
        in " ".join(response.content.decode().split())
    )
    assert staging.staged_path(token) is None  # cleaned up after the commit


def test_commit_with_an_unknown_token_imports_nothing(client):
    _login(client)

    response = client.post(reverse("imports:commit"), {"token": "0" * 32}, follow=True)

    assert Contact.objects.count() == 0
    assert any("opnieuw" in str(m) for m in response.context["messages"])


def test_committing_twice_imports_once(client):
    _login(client)
    confirmed = _dry_run(client)
    client.post(reverse("imports:commit"), confirmed)

    client.post(reverse("imports:commit"), confirmed, follow=True)

    assert Document.objects.filter(kind="invoice").count() == 13


def test_post_without_any_files_shows_an_error_and_imports_nothing(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {})

    assert response.status_code == 200
    assert Contact.objects.count() == 0


def test_an_unreadable_zip_shows_an_error_and_keeps_nothing(client):
    _login(client)
    upload = SimpleUploadedFile("kapot.zip", b"PK\x03\x04 not really a zip", "application/zip")
    staged_before = _staged()

    response = client.post(reverse("imports:upload"), {"files": [upload]}, follow=True)

    assert response.status_code == 200
    assert "kapot.zip" in response.content.decode()
    assert _staged() == staged_before


def _staged():
    root = staging._root()
    return set(root.iterdir()) if root.is_dir() else set()


def test_cancel_after_the_dry_run_removes_the_files_and_imports_nothing(client):
    _login(client)
    token = client.post(reverse("imports:upload"), {"files": _uploaded_zip()}).context["token"]

    response = client.post(reverse("imports:cancel"), {"token": token}, follow=True)

    assert response.redirect_chain[-1][0] == reverse("imports:upload")
    assert "geannuleerd" in response.content.decode()
    assert staging.staged_path(token) is None
    assert Contact.objects.count() == 0
    assert Document.objects.count() == 0


def test_the_dry_run_page_offers_to_cancel(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {"files": _uploaded_zip()})

    assert f'action="{reverse("imports:cancel")}"' in response.content.decode()


def test_cancel_with_an_unknown_token_just_returns_to_the_upload_page(client):
    _login(client)

    response = client.post(reverse("imports:cancel"), {"token": "../../etc"})

    assert response.status_code == 302
    assert response.url == reverse("imports:upload")


# The settings block (imports.settings_proposal): filled in from the
# export, checked by the user, saved with the import.


def test_the_dry_run_fills_in_the_business_details_from_the_export(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {"files": _uploaded_zip()})

    form = response.context["settings_form"]
    assert form["business_name"].value() == "Lindeboom Communicatie"
    assert form["invoice_number_format"].value() == "{customer}{seq:04d}"
    assert 'name="settings-business_name"' in response.content.decode()


def test_the_dry_run_shows_the_current_value_where_the_proposal_differs(client):
    _login(client)
    settings = Settings.load()
    settings.city = "Oudplaats"
    settings.save()

    response = client.post(reverse("imports:upload"), {"files": _uploaded_zip()})

    assert "Oudplaats" in response.content.decode()


def test_commit_saves_the_confirmed_settings(client):
    _login(client)
    confirmed = _dry_run(client)
    confirmed["settings-city"] = "Nieuwplaats"

    client.post(reverse("imports:commit"), confirmed)

    settings = Settings.load()
    assert settings.city == "Nieuwplaats"
    assert settings.business_name == "Lindeboom Communicatie"
    assert settings.invoice_number_format == "{customer}{seq:04d}"


def test_commit_with_an_invalid_setting_imports_nothing_and_shows_the_error(client):
    _login(client)
    confirmed = _dry_run(client)
    confirmed["settings-iban"] = "NL00 GEEN IBAN"

    response = client.post(reverse("imports:commit"), confirmed)

    assert response.status_code == 200
    assert response.context["settings_form"].errors["iban"]
    assert Document.objects.count() == 0
    assert Settings.load().iban == ""
    assert staging.staged_path(confirmed["token"]) is not None  # try again without re-uploading


def test_the_dry_run_page_writes_no_settings_row(client):
    # A dry run leaves the database as it was — also on a fresh install,
    # where there is no Settings row yet.
    _login(client)

    client.post(reverse("imports:upload"), {"files": _uploaded_zip()})

    assert not Settings.objects.exists()


# Singular and plural on the done page and in the report (besluit "Teksten in
# Arnes stem, deel 4": "1 facturen" and "2 afwijking" were wrong).
@pytest.mark.parametrize(
    ("language", "count", "expected"),
    [
        ("nl", 1, "1 nieuwe klant, 1 factuur, 1 offerte en 1 uitgave staan nu in Huismus."),
        ("nl", 2, "2 nieuwe klanten, 2 facturen, 2 offertes en 2 uitgaven staan nu in Huismus."),
        ("en", 1, "1 new customer, 1 invoice, 1 quote and 1 expense are now in Huismus."),
        ("en", 2, "2 new customers, 2 invoices, 2 quotes and 2 expenses are now in Huismus."),
    ],
)
def test_the_done_page_counts_in_singular_and_plural(language, count, expected):
    report = {s: {"new": count} for s in ("contacts", "sales_invoices", "quotes", "expenses")}
    with translation.override(language):
        html = render_to_string(
            "imports/committed.html",
            {"run": ImportRun(report=report), **_new_counts_text(report)},
        )
    assert expected in " ".join(html.split())


@pytest.mark.parametrize(
    ("language", "count", "expected"),
    [
        ("nl", 1, "afwijking<"),
        ("nl", 2, "afwijkingen<"),
        ("en", 1, "difference<"),
        ("en", 2, "differences<"),
    ],
)
def test_the_differences_chip_counts_in_singular_and_plural(language, count, expected):
    section = {
        "new": 0,
        "unchanged": 0,
        "skipped_count": 0,
        "issue_count": count,
        "skipped_missing_contact": [],
        "skipped_no_lines": [],
        "discrepancies": ["Factuur 1: …"] * count,
    }
    with translation.override(language):
        html = render_to_string("imports/_report_section.html", {"r": section, "title": "x"})
    assert f"<b>{count}</b>{expected}" in html


def _uploaded(year):
    content = (FIXTURES / f"lindeboom_communicatie_{year}.zip").read_bytes()
    return SimpleUploadedFile(f"lindeboom_communicatie_{year}.zip", content, "application/zip")


def test_the_dry_run_shows_the_expenses_and_recognises_their_files(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {"files": _uploaded(2014)})

    html = " ".join(response.content.decode().split())
    assert "<strong>Uitgaven</strong>" in html
    assert "<b>32</b>nieuw" in html
    assert {"Uitgaven", "Uitgaveregels"} <= set(response.context["uploads"][0]["labels"])


def test_the_done_page_counts_the_imported_expenses(client):
    _login(client)
    response = client.post(reverse("imports:upload"), {"files": _uploaded(2014)})
    data = {"token": response.context["token"]}
    for bound_field in response.context["settings_form"]:
        value = bound_field.value()
        if value is True:
            data[bound_field.html_name] = "on"
        elif value not in (None, False):
            data[bound_field.html_name] = value

    response = client.post(reverse("imports:commit"), data)

    assert "en 32 uitgaven staan nu in Huismus." in " ".join(response.content.decode().split())


@pytest.mark.parametrize(
    ("language", "heading", "explanation"),
    [
        ("nl", "Geen bonnetje gevonden", "Huismus importeert ze wel, zonder bonnetje."),
        ("en", "No receipt found", "Huismus imports them anyway, without a receipt."),
    ],
)
def test_the_expenses_section_lists_documents_without_a_receipt(language, heading, explanation):
    section = _with_counts(
        {"new": 1, "unchanged": 0, "discrepancies": [], "missing_receipts": ["F-1 (Drukkerij)"]}
    )
    with translation.override(language):
        html = render_to_string("imports/_report_section.html", {"r": section, "title": "x"})
    assert heading in html
    assert "F-1 (Drukkerij)" in html
    assert explanation in html
    assert "is-warn" in html


def test_an_expense_discrepancy_counts_as_a_point_to_check():
    section = _with_counts(
        {"new": 1, "unchanged": 0, "discrepancies": ["Uitgave F-1: …"], "missing_receipts": []}
    )

    assert (section["issue_count"], section["skipped_count"]) == (1, 0)


def test_the_upload_page_says_where_the_receipts_go(client):
    _login(client)

    response = client.get(reverse("imports:upload"))

    assert "De bonnetjes komen bij je uitgaven." in response.content.decode()


def test_the_upload_page_names_the_expenses_in_what_comes_along(client):
    _login(client)

    response = client.get(reverse("imports:upload"))

    assert "Neem je klanten, facturen, offertes en uitgaven één op één mee." in (
        response.content.decode()
    )


def test_the_expenses_section_names_the_new_categories():
    section = _with_counts(
        {
            "new": 1,
            "unchanged": 0,
            "discrepancies": [],
            "missing_receipts": [],
            "new_categories": ["Software"],
        }
    )
    with translation.override("nl"):
        html = render_to_string("imports/_report_section.html", {"r": section, "title": "x"})
    assert "Nieuwe categorieën" in html and "Software" in html


def test_the_dry_run_says_the_invoices_match_moneybirds_own_reports(client):
    _login(client)

    response = client.post(reverse("imports:upload"), {"files": _uploaded(2014)})

    html = " ".join(response.content.decode().split())
    assert "<h3>Moneybirds eigen rapporten</h3>" in html
    assert "Je facturen kloppen met de omzet en btw in Moneybirds eigen rapporten." in html


@pytest.mark.parametrize("language", ["nl", "en"])
def test_a_difference_with_moneybirds_own_reports_is_a_point_to_check(language):
    difference = "Omzet december 2014, Gouden Golf Advies: Moneybird € 179,01, Huismus € 0,00"
    section = _with_counts(
        {
            "new": 16,
            "unchanged": 0,
            "discrepancies": [],
            "moneybird_reports": {"differences": [difference]},
        }
    )

    with translation.override(language):
        html = render_to_string("imports/_report_section.html", {"r": section, "title": "x"})

    assert section["issue_count"] == 1
    assert difference in html
    assert {
        "nl": "Kijk na of er een factuur ontbreekt.",
        "en": "Check whether an invoice is missing.",
    }[language] in html
