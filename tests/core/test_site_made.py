# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The site's page "Zo wordt Huismus gemaakt" (issue #313).

The page says who decides, who writes and what guards Huismus. Each test below holds one of its
statements against the code as it is, so the page can't keep saying
something the code stopped doing: change the code, and the test names the
sentence to rewrite (huismus/templates/site/made.html).

Where a statement is about how another test, a workflow or a working
agreement in CLAUDE.md is written, the
check here reads that file's text: it is a tripwire for the sentence, not a
second test of the behaviour, which the named test itself covers."""

import re
from pathlib import Path

import pytest
from django.conf import settings
from django.core.management import call_command
from django.db import connection

from huismus.core import demo_history, help, site

ROOT = Path(settings.BASE_DIR)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    call_command("build_site", str(out))
    return out


def _html(out, address: str) -> str:
    return (out / address.strip("/") / "index.html").read_text(encoding="utf-8")


def _menu(html: str) -> str:
    return re.search(r'<nav class="site-nav".*?</nav>', html, re.S).group(0)


def _foot(html: str) -> str:
    return re.search(r'<nav class="foot-nav".*?</nav>', html, re.S).group(0)


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_page_is_reached_from_why_and_every_foot_but_not_from_the_menu(out, language):
    made = site.made_url(language)
    page = _html(out, made)
    link = f'href="{made}"'
    assert link in _html(out, site.why_url(language)).split('<footer class="site-foot')[0]
    assert link in _foot(_html(out, site.help_url(language)))
    assert link not in _menu(page)
    assert f'href="{site.why_url(language)}"' in page.split('<footer class="site-foot')[0]
    assert f"https://{site.DOMAIN}{made}" in (out / "sitemap.xml").read_text()
    assert f"https://{site.DOMAIN}{made}" in (out / "llms.txt").read_text()


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_every_link_to_the_source_is_a_file_that_exists(out, language):
    page = _html(out, site.made_url(language))
    for path in site.MADE_SOURCES.values():
        assert (ROOT / path).exists(), path
        assert f"{site.REPOSITORY}/" in page and f"/main/{path}" in page, path


@pytest.mark.parametrize(("language", "number"), [("nl", "2.500"), ("en", "2,500")])
def test_it_says_how_many_tests_there_are_and_never_more_than_there_are(out, language, number):
    """ "Meer dan 2.500 tests": counted as test functions, which is fewer
    than pytest runs (one function can run for several cases)."""
    functions = sum(
        len(re.findall(r"^\s*def test_\w+", path.read_text(encoding="utf-8"), re.M))
        for path in (ROOT / "tests").rglob("test_*.py")
    )
    assert functions > site.TESTS_AT_LEAST
    assert site._thousands(site.TESTS_AT_LEAST, language) == number
    assert number in _html(out, site.made_url(language))


def test_one_command_runs_every_check_and_github_runs_it_on_every_change():
    """ "Bij elke wijziging draaien ze allemaal, op GitHub: eerst op de
    wijziging zelf, daarna op het geheel. Eén commando zegt ja of nee." And
    the same command looks at the migrations and at real records in git."""
    gate = _text("scripts/verify.sh")
    assert "uv run pytest" in gate
    assert "makemigrations --check" in gate
    # "Geen bestanden van een echte administratie": by their place and kind.
    assert "git ls-files -- 'data-import/*' 'data/*' '*.sqlite3' '.env'" in gate
    ci = _text(".github/workflows/ci.yml")
    assert "run: ./scripts/verify.sh" in ci
    assert re.search(r"^on:\n  push:\n    branches: \[main\]\n  pull_request:\n", ci, re.M)


@pytest.mark.django_db
def test_the_database_itself_refuses_a_change_to_an_issued_document():
    """ "De database weigert hem zelf ook: voor het document, voor de regels
    en voor de btw per tarief." What each trigger refuses is tested in
    tests/documents/test_immutability.py; here, that they are all there."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT name FROM sqlite_master WHERE type = 'trigger'")
        triggers = {name for (name,) in cursor.fetchall()}
    expected = {
        f"documents_{table}_immutable_{change}"
        for table, changes in (
            ("document", ("update", "delete")),
            ("documentline", ("update", "delete", "insert")),
            ("documentvatrow", ("update", "delete", "insert")),
        )
        for change in changes
    }
    assert expected <= triggers


def test_toch_bewerken_is_the_one_way_back_and_stops_at_a_credit_note():
    """ "Met Toch bewerken zet je een factuur terug naar concept, met
    hetzelfde nummer. Dat kan niet meer als er een creditnota voor die
    factuur is uitgegeven." The trigger lets only that change through."""
    trigger = _text("huismus/documents/migrations/0015_reverse_charge.py")
    assert "NEW.status = 'draft'" in trigger and "AND NEW.number = OLD.number" in trigger
    reopening = _text("huismus/documents/reopening.py")
    assert 'kind="credit_note", status="issued", related_document_id=document.pk' in reopening
    assert "Toch bewerken" in _text("huismus/locale/nl/LC_MESSAGES/django.po")


def test_a_number_is_taken_while_issuing_and_twenty_at_once_leave_no_gap():
    """ "Een factuur krijgt zijn nummer pas bij het uitgeven, in dezelfde
    stap", "Mislukt het uitgeven, dan is er ook geen nummer verbruikt" and
    "Een test vraagt twintig nummers tegelijk aan"."""
    assert "def test_issue_refuses_a_number_that_already_exists_and_uses_no_number(" in _text(
        "tests/documents/test_issuing.py"
    )
    assert "allocate_number() must be called inside transaction.atomic()" in _text(
        "huismus/documents/numbering.py"
    )
    test = _text("tests/documents/test_numbering.py")
    assert "thread_count = 20" in test
    assert "assert sorted(numbers) == list(range(1, thread_count + 1))" in test


def test_amounts_are_whole_cents_and_random_invoices_check_the_totals():
    """ "Huismus slaat elk bedrag op in hele centen" and "Tests met
    willekeurige facturen kijken of het subtotaal altijd de som van de
    regels is, en het totaal altijd het subtotaal plus de btw"."""
    from huismus.documents.models import Document, DocumentLine

    for model, field in (
        (Document, "subtotal_cents"),
        (Document, "tax_cents"),
        (Document, "total_cents"),
        (DocumentLine, "unit_price_cents"),
        (DocumentLine, "line_total_cents"),
    ):
        assert model._meta.get_field(field).get_internal_type() == "BigIntegerField"
    test = _text("tests/documents/test_totals.py")
    assert "from hypothesis import given" in test
    assert "def test_subtotal_always_equals_sum_of_line_totals(" in test
    assert "def test_total_is_always_subtotal_plus_tax_and_non_negative(" in test


def test_the_import_checks_each_total_and_a_second_import_changes_nothing():
    """ "Huismus rekent van elke factuur het totaal opnieuw uit en
    vergelijkt het […] tot op de cent" and "Lees je dezelfde export twee
    keer in, dan verandert er de tweede keer niets. Ook dat kijkt een test na." """
    for path in ("huismus/imports/commit.py", "huismus/imports/csv_commit.py"):
        assert "parsed.stated_total_cents" in _text(path), path
    assert "recomputed = compute_totals(parsed.lines)" in _text("huismus/imports/commit.py")
    assert "def test_importing_several_exports_twice_changes_nothing(" in _text(
        "tests/imports/test_pipeline.py"
    )
    assert "def test_a_second_import_changes_nothing(" in _text(
        "tests/imports/test_csv_roundtrip.py"
    )


def test_browser_tests_open_every_page_in_three_widths_and_three_engines():
    """ "Op drie schermbreedtes", "met negen jaar verzonnen administratie",
    and Chromium for every change, Safari's and Firefox's engines as well
    when something you see changes."""
    assert "WIDTHS = [390, 1024, 1440]" in _text("tests/e2e/test_every_page.py")
    # "Een factuur uitgeven", in a browser.
    assert 'app.click("#uitgeven-knop")' in _text("tests/e2e/test_browser.py")
    assert "WIDTHS = [390, 1024, 1440]" in _text("tests/e2e/test_walkthrough.py")
    assert demo_history.LAST_YEAR - demo_history.FIRST_YEAR + 1 == 9
    ci = _text(".github/workflows/ci.yml")
    assert """all='["chromium", "webkit", "firefox"]'""" in ci
    assert """echo 'list=["chromium"]'""" in ci


def test_a_release_waits_for_the_security_checks():
    """ "Een nieuwe versie komt pas online als twee controles slagen", and
    the reviewer that reads everything since the last release."""
    release = _text(".github/workflows/release.yml")
    assert "pip-audit" in release and "check --deploy --fail-level WARNING" in release
    assert "  build-and-push:\n    needs: security\n" in release
    assert re.search(r"^    needs: \[security, .*\]$", release, re.M)
    # The reviewer is an agreement in CLAUDE.md, as the page says; no job runs it.
    assert "een bevinding met ernst\nhoog of middel houdt de release tegen" in _text("CLAUDE.md")
    assert "een lage wordt een\nissue" in _text("CLAUDE.md")
    reviewer = _text(".claude/agents/review-veiligheid.md")
    for subject in (
        "Geheimen",
        "Verbindingen naar buiten",
        "Ingangen zonder sessie",
        "Wat de gebruiker inleest",
    ):
        assert f"**{subject}**" in reviewer, subject


def test_the_maker_decides_and_the_agreements_say_so():
    """ "De maker bepaalt wat er gebouwd wordt en in welke volgorde", the
    public list of work, what the maker sees and decides, "leest de maker
    niet regel voor regel na" and trying a new version on the maker's own
    records: all agreements in CLAUDE.md, which the page links to."""
    rules = _text(site.MADE_SOURCES["rules"])
    for agreement in (
        "De backlog staat openbaar in de issues",
        "eigenaar sleept wat eerst moet naar boven",
        "Een grote wijziging met UI gaat pas naar `main` als de eigenaar de flow heeft\ngezien",
        "een nieuw scherm, of een taak waarvan de stappen veranderen",
        "tekst over wet of belasting zonder bron",
        "alles wat geld kost",
        "een migratie die bestaande gegevens wijzigt of verwijdert",
        "De eigenaar is product owner en leest geen code.",
        "eigenaar draait de voorproef op de echte administratie",
    ):
        assert agreement in rules, agreement


def test_the_rules_the_small_steps_and_the_sources_are_agreements_too():
    """ "De regels […] staan in gewone tekst bij de code", reviewers with one
    task each, small steps with a plan, tests before the code for invoicing,
    and tax statements only from an official source."""
    rules = _text(site.MADE_SOURCES["rules"])
    for agreement in (
        "## Hard rules (invariants)",
        "write a short plan",
        "**write the tests first**",
        "One concern per commit.",
        "never from memory",
    ):
        assert agreement in rules, agreement
    for reviewer in ("review-invarianten", "review-uitlegbaarheid", "review-spec"):
        assert (ROOT / ".claude" / "agents" / f"{reviewer}.md").exists(), reviewer
    assert (ROOT / "docs" / "belastingregels.md").exists()


def test_the_bugs_found_by_hand_are_where_the_page_says():
    """The list of bugs found by hand names the kinds without a check yet
    as "nog geen"."""
    assert "nog geen" in _text(site.MADE_SOURCES["bugs"])
