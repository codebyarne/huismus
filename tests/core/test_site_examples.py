# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Voorbeelden on the site (issue #309): docs/site/voorbeelden/, made by
scripts/site_voorbeelden.py, and the page huismus/core/site.py builds.

The page says the invoice with VAT has every detail the Belastingdienst
asks for; test_the_invoice_with_vat_has_every_required_detail keeps that
true against the list in docs/invoice-requirements.md.
"""

import io
import re
import zipfile
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import openpyxl
import pypdf
import pytest
from django.conf import settings
from django.core.management import call_command
from PIL import Image

from huismus.core import help, site
from huismus.core import site_examples as names
from huismus.documents.totals import LineInput, compute_totals
from scripts import site_voorbeelden

FOLDER = names.EXAMPLES_DIR
DOCUMENTS = (names.INVOICE_WITH_VAT, names.INVOICE_WITHOUT_VAT, names.QUOTE)
EVERY = [(example, language) for language in names.LANGUAGES for example in names.EXAMPLES]
EVERY_DOCUMENT = [(example, language) for example, language in EVERY if example in DOCUMENTS]


def _path(example, language, format, folder=FOLDER) -> Path:
    return folder / names.file_name(example, language, format)


def _pdf_text(path: Path) -> str:
    """Without the spaces and line breaks a PDF puts where it likes."""
    text = "".join(page.extract_text() for page in pypdf.PdfReader(path).pages)
    return re.sub(r"\s+", "", text)


def _docx_xml(path: Path, part: str = "word/document.xml") -> str:
    with zipfile.ZipFile(path) as file:
        return file.read(part).decode("utf-8")


def _docx_text(path: Path) -> str:
    """Everything a reader sees: the page and its footer."""
    with zipfile.ZipFile(path) as file:
        parts = [n for n in file.namelist() if re.fullmatch(r"word/(document|footer\d*)\.xml", n)]
        xml = "".join(file.read(part).decode("utf-8") for part in sorted(parts))
    return re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", xml))


def _cells(path: Path, calculated: bool) -> dict[str, object]:
    """{"F19": …}: the formulas, or (`calculated`) the amounts they carry."""
    sheet = openpyxl.load_workbook(path, data_only=calculated).active
    return {
        cell.coordinate: cell.value
        for row in sheet.iter_rows()
        for cell in row
        if cell.value is not None
    }


def _cents(euros) -> int:
    return int((Decimal(str(euros)) * 100).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def _money(cents: int) -> str:
    """ "€ 1.790,80" as the PDF and Word write it, without the space."""
    from huismus.core.templatetags.money import money

    return re.sub(r"\s+", "", money(cents))


def _lines(path: Path) -> list[tuple[str, LineInput]]:
    """(row, the line) for every line of a document's spreadsheet: a row with
    a quantity in A and a price in D."""
    cells = _cells(path, calculated=False)
    lines = []
    for coordinate, value in cells.items():
        row = coordinate[1:]
        if coordinate[0] == "A" and isinstance(value, int | float) and f"D{row}" in cells:
            rate_bp = int(round(Decimal(str(cells.get(f"E{row}", 0))) * 10000))
            line = LineInput(Decimal(str(value)), _cents(cells[f"D{row}"]), rate_bp)
            lines.append((row, line))
    return lines


def test_every_example_is_there_in_every_format_and_both_languages():
    assert {path.name for path in FOLDER.iterdir()} == {path.name for path in names.files()}
    assert len(names.files()) == 2 * 4 * 4
    for example, language in EVERY:
        assert _path(example, language, "pdf").read_bytes().startswith(b"%PDF")
        for format in ("docx", "xlsx"):
            assert zipfile.is_zipfile(_path(example, language, format))


@pytest.mark.parametrize("example,language", EVERY)
def test_the_picture_is_the_first_page_twice_as_wide_as_shown(example, language):
    with Image.open(_path(example, language, names.PREVIEW_FORMAT)) as picture:
        assert picture.width == 2 * names.PREVIEW_WIDTH
        assert picture.height == pytest.approx(picture.width * 297 / 210, abs=2)


@pytest.mark.django_db
@pytest.mark.parametrize("language", names.LANGUAGES)
def test_the_files_are_what_the_script_makes(language, tmp_path):
    """Changed the script, the PDF template or a translation? Then run
    scripts/site-voorbeelden.sh and commit the files."""
    site_voorbeelden.make(tmp_path, language)
    for example in names.EXAMPLES:
        made, kept = (_path(example, language, "pdf", f) for f in (tmp_path, FOLDER))
        assert _pdf_text(made) == _pdf_text(kept), kept.name
        made, kept = (_path(example, language, "docx", f) for f in (tmp_path, FOLDER))
        assert _docx_xml(made) == _docx_xml(kept), kept.name
        made, kept = (_path(example, language, "xlsx", f) for f in (tmp_path, FOLDER))
        for calculated in (False, True):
            assert _cells(made, calculated) == _cells(kept, calculated), kept.name


@pytest.mark.parametrize("language", names.LANGUAGES)
def test_the_invoice_with_vat_has_every_required_detail(language):
    """The list "Verplichte gegevens op een factuur" of
    docs/invoice-requirements.md, in its order."""
    text = _pdf_text(_path(names.INVOICE_WITH_VAT, language, "pdf"))
    business, customer = site_voorbeelden.BUSINESS, site_voorbeelden.CUSTOMER
    quantity, _unit, description, price = site_voorbeelden.LINES[language][0]
    required = {
        "your name": business["business_name"],
        "the customer's name": customer["company_name"],
        "your address": business["address_line1"],
        "your postal code and city": f"{business['postal_code']} {business['city']}",
        "the customer's address": customer["address_line1"],
        "the customer's postal code and city": f"{customer['postal_code']} {customer['city']}",
        "your VAT identification number": business["vat_number"],
        "your KVK number": business["kvk_number"],
        "the date of issue": site_voorbeelden.INVOICE_DATE.strftime("%d-%m-%Y"),
        "an invoice number": "2026-0001",
        "what was supplied": description,
        "how much": str(quantity),
        "the date of supply": site_voorbeelden.DELIVERY_DATE.strftime("%d-%m-%Y"),
        "the amount without VAT": _money(148000),
        "the VAT rate": "21%",
        "the VAT amount": _money(31080),
    }
    for detail, value in required.items():
        assert re.sub(r"\s+", "", value) in text, detail
    assert business["vat_number"].startswith("NL")


@pytest.mark.parametrize("language", names.LANGUAGES)
def test_the_invoice_without_vat_charges_none_and_says_its_text_is_an_example(language):
    text = _pdf_text(_path(names.INVOICE_WITHOUT_VAT, language, "pdf"))
    assert "21%" not in text and _money(148000) in text and _money(179080) not in text
    assert re.sub(r"\s+", "", site_voorbeelden.KOR_TEXT[language]) in text
    assert re.search(r"voorbeeldtekst|sample text", site_voorbeelden.KOR_TEXT[language])


@pytest.mark.parametrize("language", names.LANGUAGES)
def test_the_quote_says_until_when_it_is_valid(language):
    text = _pdf_text(_path(names.QUOTE, language, "pdf"))
    assert site_voorbeelden.QUOTE_VALID_UNTIL.strftime("%d-%m-%Y") in text


@pytest.mark.parametrize("example,language", EVERY_DOCUMENT)
def test_word_and_excel_show_the_amounts_of_the_pdf(example, language):
    """The amounts are the app's own (rule 4): what the spreadsheet carries
    is what documents.totals makes of its lines, and the PDF and Word say it."""
    spreadsheet = _path(example, language, "xlsx")
    totals = compute_totals([line for _row, line in _lines(spreadsheet)])
    amounts = {_cents(v) for v in _cells(spreadsheet, calculated=True).values() if _is_amount(v)}
    pdf, word = (
        _pdf_text(_path(example, language, "pdf")),
        _docx_text(_path(example, language, "docx")),
    )
    for cents in (*totals.line_totals_cents, totals.subtotal_cents, totals.total_cents):
        assert cents in amounts
        assert _money(cents) in pdf and _money(cents) in word
    for _rate_bp, cents in totals.tax_per_rate:
        assert cents in amounts
        assert _money(cents) in pdf and _money(cents) in word


def _is_amount(value) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


@pytest.mark.parametrize("example,language", EVERY_DOCUMENT)
def test_the_formulas_count_like_the_app(example, language):
    """A line is quantity × price rounded to cents; VAT is rounded per rate
    over the whole document, not per line (documents.totals). Each formula
    is of that shape, and worked out it gives the amount the cell carries."""
    path = _path(example, language, "xlsx")
    formulas, shown = _cells(path, calculated=False), _cells(path, calculated=True)
    lines = _lines(path)
    first, last = lines[0][0], lines[-1][0]
    totals = compute_totals([line for _row, line in lines])

    for (row, _line), cents in zip(lines, totals.line_totals_cents, strict=True):
        assert formulas[f"F{row}"] == f"=ROUND(A{row}*D{row},2)"
        assert _cents(shown[f"F{row}"]) == cents

    by_formula = {v: k for k, v in formulas.items() if isinstance(v, str) and v.startswith("=")}
    subtotal = by_formula[f"=SUM(F{first}:F{last})"]
    assert _cents(shown.get(subtotal, 0)) == totals.subtotal_cents
    taxes = []
    for rate_bp, cents in totals.tax_per_rate:
        rate = Decimal(rate_bp) / 10000
        cell = by_formula[f"=ROUND(SUMIF(E{first}:E{last},{rate},F{first}:F{last})*{rate},2)"]
        assert _cents(shown.get(cell, 0)) == cents
        taxes.append(cell)
    total = by_formula["=" + "+".join([subtotal, *taxes])]
    assert _cents(shown[total]) == totals.total_cents
    # Nothing else counts: every formula is one of these.
    assert len(by_formula) == len(lines) + 2 + len(taxes)


@pytest.mark.parametrize("language", names.LANGUAGES)
def test_the_timesheet_adds_up_its_hours_in_every_format(language):
    hours = sum(Decimal(h) for _day, _what, h in site_voorbeelden.TIMESHEET_ROWS)
    assert hours == site_voorbeelden.LINES[language][0][0], "the hours on the invoice"
    path = _path(names.TIMESHEET, language, "xlsx")
    formulas, shown = _cells(path, calculated=False), _cells(path, calculated=True)
    (cell,) = [k for k, v in formulas.items() if isinstance(v, str) and v.startswith("=SUM(C")]
    assert Decimal(str(shown[cell])) == hours
    total = site_voorbeelden.WORDS[language]["total"] + f"{hours.normalize():f}"
    assert total in _pdf_text(_path(names.TIMESHEET, language, "pdf"))
    assert total in _docx_text(_path(names.TIMESHEET, language, "docx"))


@pytest.mark.parametrize("example,language", EVERY)
def test_a_file_names_no_person_and_no_real_address(example, language):
    """Its properties say Huismus made it, and every mail address in it ends
    in .example."""
    word = _path(example, language, "docx")
    properties = _docx_xml(word, "docProps/core.xml")
    assert "<dc:creator>Huismus</dc:creator>" in properties
    assert "<cp:lastModifiedBy>Huismus</cp:lastModifiedBy>" in properties
    book = openpyxl.load_workbook(_path(example, language, "xlsx"))
    assert book.properties.creator == "Huismus"
    assert book.properties.lastModifiedBy in (None, "", "Huismus")
    pdf = pypdf.PdfReader(_path(example, language, "pdf"))
    assert not pdf.metadata.author
    everything = (
        _pdf_text(_path(example, language, "pdf"))
        + _docx_text(word)
        + " ".join(str(v) for v in _cells(_path(example, language, "xlsx"), False).values())
    )
    assert everything.count("@") == len(re.findall(r"@[\w-]+\.example", everything)) > 0


def test_excel_has_no_macros_and_no_locked_sheet():
    for example, language in EVERY:
        path = _path(example, language, "xlsx")
        with zipfile.ZipFile(path) as file:
            assert not [name for name in file.namelist() if "vba" in name.lower()]
        assert not openpyxl.load_workbook(path).active.protection.sheet


# --- The page on the site.


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    out = tmp_path_factory.mktemp("site")
    call_command("build_site", str(out))
    return out


def _page(out, language) -> str:
    return (out / site.examples_url(language).strip("/") / "index.html").read_text()


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_page_offers_every_example_in_its_own_language(out, language):
    html = _page(out, language)
    for example in names.EXAMPLES:
        for format in (*names.FORMATS, names.PREVIEW_FORMAT):
            address = site.EXAMPLE_FILES_URL + names.file_name(example, language, format)
            assert f'"{address}"' in html
            assert (out / address.strip("/")).is_file()
    other = "en" if language == "nl" else "nl"
    assert names.file_name(names.QUOTE, other, "pdf") not in html
    assert f'href="{site.examples_url(other)}" hreflang="{other}"' in html


def test_the_site_carries_one_copy_of_every_file_and_nothing_else(out):
    folder = out / site.EXAMPLE_FILES_URL.strip("/")
    assert {path.name for path in folder.iterdir()} == {path.name for path in names.files()}


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_every_download_and_picture_says_what_it_is(out, language):
    html = _page(out, language)
    buttons = re.findall(r'<a class="btn" href="[^"]+" download aria-label="([^"]+)"', html)
    assert len(buttons) == len(set(buttons)) == 12
    pictures = re.findall(r'<img class="example-picture"[^>]*>', html)
    assert len(pictures) == 4
    for picture in pictures:
        assert re.search(r'alt="[^"]{12,}"', picture) and 'loading="lazy"' in picture
        assert re.search(r'width="\d+" height="\d+"', picture)


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_every_link_on_the_page_lands_on_a_page(out, language):
    html = _page(out, language)
    links = [link for link in re.findall(r'href="(/[^"#?]*)', html) if link.endswith("/")]
    assert site.guides_url(language, "factuureisen") in links
    assert site.guides_url(language, "kor") in links
    assert site.help_url(language, "facturen") in links
    assert site.help_url(language, "offertes") in links
    for link in links:
        assert (out / link.strip("/") / "index.html").exists(), link


def test_the_english_page_is_in_english(out):
    html = _page(out, "en")
    assert "<h1>Examples to download</h1>" in html
    assert "Invoice without VAT" in html and "Timesheet" in html
    for dutch in ("Voorbeeld", "Factuur", "Urenstaat", "Offerte"):
        assert dutch not in re.sub(r'href="[^"]*"', "", html), dutch


@pytest.mark.parametrize("language", help.LANGUAGES)
def test_the_foot_uitleg_and_the_invoice_page_link_to_it_but_the_menu_does_not(out, language):
    address = site.examples_url(language)
    home = (out / site.home_url(language).strip("/") / "index.html").read_text()
    menu = home[home.index('<nav class="site-nav"') : home.index("</nav>")]
    foot = home[home.index('<nav class="foot-nav"') :]
    assert f'href="{address}"' in foot and f'href="{address}"' not in menu
    for page in (site.guides_url(language), site.guides_url(language, "factuureisen")):
        assert f'href="{address}"' in (out / page.strip("/") / "index.html").read_text(), page


def test_a_search_engine_and_an_ai_assistant_find_the_page(out):
    sitemap, llms = (out / "sitemap.xml").read_text(), (out / "llms.txt").read_text()
    for language in help.LANGUAGES:
        address = f"https://{site.DOMAIN}{site.examples_url(language)}"
        assert f"<loc>{address}</loc>" in sitemap
        assert f"]({address}): " in llms
    assert "[Examples to download]" in llms and "[Voorbeelden om te downloaden]" in llms


def test_the_site_is_built_without_the_packages_that_make_the_examples():
    """.github/workflows/pages.yml installs no dev packages."""
    for module in ("site.py", "site_examples.py", "guides.py"):
        source = (Path(settings.BASE_DIR) / "huismus" / "core" / module).read_text()
        imported = re.findall(r"^\s*(?:from|import) ([\w.]+)", source, re.M)
        assert not {"docx", "xlsxwriter", "pypdfium2", "scripts"} & set(imported), module


def test_made_in_memory_a_pdf_is_a_pdf():
    """_preview() reads the bytes of a PDF, not a path."""
    pdf = _path(names.TIMESHEET, "nl", "pdf").read_bytes()
    with Image.open(io.BytesIO(site_voorbeelden._preview(pdf))) as picture:
        assert picture.format == "WEBP"
