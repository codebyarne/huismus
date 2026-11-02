# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from io import StringIO
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from huismus.contacts.models import Contact
from huismus.documents.models import Document
from huismus.imports.models import ImportRun

pytestmark = pytest.mark.django_db

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"


def test_defaults_to_a_dry_run():
    out = StringIO()

    call_command("import_moneybird", str(FIXTURES / "lindeboom_communicatie_2019"), stdout=out)

    assert "proefdraai" in out.getvalue()
    assert Contact.objects.count() == 0
    # SPEC.md section 7: a dry-run writes nothing, including the
    # ImportRun audit row itself.
    assert ImportRun.objects.count() == 0


def test_commit_flag_actually_imports():
    out = StringIO()

    call_command(
        "import_moneybird",
        str(FIXTURES / "lindeboom_communicatie_2019"),
        "--commit",
        stdout=out,
    )

    assert "geïmporteerd" in out.getvalue()
    assert Contact.objects.count() == 58
    assert Document.objects.filter(kind="invoice").count() == 13
    assert Document.objects.filter(kind="quote").count() == 7


def test_a_missing_path_is_a_clear_error():
    with pytest.raises(CommandError):
        call_command("import_moneybird", "/nonexistent/path/xyz", stdout=StringIO())


def test_the_report_names_the_expenses():
    out = StringIO()

    call_command("import_moneybird", str(FIXTURES / "lindeboom_communicatie_2014.zip"), stdout=out)

    assert "Uitgaven: 32 nieuw, 0 al aanwezig (32 in de export)" in out.getvalue()
