# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The main paths through the app, in a real browser."""

import re
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest
from PIL import Image
from playwright.sync_api import expect

from huismus.business.models import Settings
from huismus.documents.models import Document

pytestmark = pytest.mark.django_db(transaction=True)

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "moneybird-example-data"
# A click that sends an import form waits until the next page has loaded.
# The dry run and "doorvoeren" read a whole export, and Firefox and WebKit on
# CI sometimes need more than the default 5 s for that (as with uitgeven).
IMPORT_CLICK_TIMEOUT = 30000

SIDEBAR = [
    ("Overzicht", "/"),
    ("Facturen", "/facturen/"),
    ("Offertes", "/offertes/"),
    ("Klanten", "/contacten/"),
    ("Uitgaven", "/uitgaven/"),
    ("Importeren", "/importeren/"),
    ("Instellingen", "/instellingen/"),
]


def test_sidebar_navigation_reaches_every_section_and_marks_it(app):
    for label, path in SIDEBAR:
        app.locator(".sidebar .nav > a", has_text=label).click()
        expect(app).to_have_url(app.base + path)
        expect(app.locator(".sidebar .nav > a[aria-current=page]")).to_have_text(label)


def test_clicking_the_current_section_again_stays_there(app):
    link = app.locator(".sidebar .nav a", has_text="Overzicht").first
    app.goto(app.base + "/facturen/")
    link.click()
    expect(app).to_have_url(app.base + "/")
    link.click()
    expect(app).to_have_url(app.base + "/")
    link.dblclick()
    expect(app).to_have_url(app.base + "/")


def test_a_list_row_is_clickable_and_never_covers_the_menu(app, contact):
    app.goto(app.base + "/contacten/")
    app.locator("tr.is-link td[data-cell=secondary]").click()
    expect(app).to_have_url(re.compile(r"/contacten/\d+/"))
    # Safari used to stretch the row link over the whole screen, so a second
    # click on the menu opened the first row instead.
    app.goto(app.base + "/")
    link = app.locator(".sidebar .nav a", has_text="Klanten")
    link.click()
    link.dblclick()
    expect(app).to_have_url(app.base + "/contacten/")


def test_create_and_issue_an_invoice_with_live_totals(app, contact):
    app.goto(app.base + "/facturen/nieuw/")

    # Customer picker: type to filter, Enter to choose; the address follows.
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    expect(app.locator("#aan-adres")).to_contain_text("Utrecht")

    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Uren")
    line.locator("input[name$=-quantity]").fill("2,5")
    line.locator("input[name$=-unit_price_cents]").fill("85")
    # Computed by the server while typing (documents:preview), nothing saved.
    expect(app.locator("#lines-0-totaal")).to_have_text("€ 212,50")
    # The KOR is off here: a new line starts at 21% (SPEC.md M18).
    expect(app.locator("#totalen")).to_contain_text("21% btw")
    expect(app.locator("#totalen")).to_contain_text("257,13")
    assert Document.objects.count() == 0

    app.click("#uitgeven-knop")
    expect(app.locator("#uitgeven")).to_contain_text("257,13")
    # The click waits until the issued invoice's page has loaded; WebKit on
    # CI sometimes needs more than the default 5 s for that.
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)

    expect(app.locator("h1")).to_contain_text("Factuur")
    expect(app.locator(".pill-final").first).to_be_visible()
    invoice = Document.objects.get()
    assert (invoice.status, invoice.total_cents) == ("issued", 25713)
    expect(app.locator("h1")).to_contain_text(invoice.number)

    # The PDF button opens the PDF page; Downloaden there names the file
    # after the invoice number.
    app.locator(".page-head a.btn", has_text="PDF").click()
    expect(app.locator("h1")).to_have_text(f"{invoice.number}.pdf")
    with app.expect_download() as download:
        app.get_by_role("link", name="Downloaden").click()
    assert download.value.suggested_filename == f"{invoice.number}.pdf"


def test_an_invoice_with_21_and_9_percent_shows_the_vat_per_rate(app, contact):
    """For a business that charges VAT (SPEC.md M18): a rate per line, the
    VAT per rate under the subtotal, worked out by the server."""
    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")

    first = app.locator("[data-formset-forms=lines] .line").first
    expect(first.locator("select[name$=-tax_rate_bp]")).to_have_value("2100")
    first.locator("textarea[name$=-description]").fill("Ontwerp")
    first.locator("input[name$=-unit_price_cents]").fill("1000")
    app.click("[data-formset-add=lines]")
    second = app.locator("[data-formset-forms=lines] .line").nth(1)
    second.locator("textarea[name$=-description]").fill("Boek")
    second.locator("input[name$=-unit_price_cents]").fill("100")
    second.locator("select[name$=-tax_rate_bp]").select_option("900")

    totals = app.locator("#totalen")
    expect(totals).to_contain_text("9% btw")
    expect(totals).to_contain_text("9,00")
    expect(totals).to_contain_text("21% btw")
    expect(totals).to_contain_text("210,00")
    expect(totals).to_contain_text("1.319,00")

    app.click("#uitgeven-knop")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator(".pill-final").first).to_be_visible()
    invoice = Document.objects.get()
    totals_stored = (invoice.subtotal_cents, invoice.tax_cents, invoice.total_cents)
    assert totals_stored == (110000, 21900, 131900)
    expect(app.locator("dl.totals")).to_contain_text("9% btw")
    expect(app.locator("dl.totals")).to_contain_text("21% btw")


def test_a_verlegd_line_is_issued_with_the_text_from_the_settings(app, contact):
    """Btw verlegd (SPEC.md M18): a choice per line; issuing without the
    text says where to fill it in."""
    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Advies")
    line.locator("input[name$=-unit_price_cents]").fill("500")
    line.locator("select[name$=-tax_rate_bp]").select_option("verlegd")
    expect(app.locator("#totalen")).to_contain_text("500,00")

    app.click("#uitgeven-knop")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator("body")).to_contain_text("Vul eerst de tekst bij btw verlegd in")
    assert Document.objects.get().status == "draft"

    business = Settings.load()
    business.reverse_charge_text = "Btw verlegd (voorbeeldtekst)."
    business.save()
    app.click("#uitgeven-knop")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator(".pill-final").first).to_be_visible()
    expect(app.locator("table")).to_contain_text("verlegd")
    invoice = Document.objects.get()
    assert invoice.reverse_charge_text_snapshot == "Btw verlegd (voorbeeldtekst)."
    assert (invoice.tax_cents, invoice.total_cents) == (0, 50000)


def test_the_t_a_v_line_follows_the_customer_and_lands_on_the_pdf(app, contact):
    # As in Moneybird: a contact has persons, a document picks one.
    from huismus.contacts.models import Contact, ContactPerson

    contact.attention = "Joke Jansen"
    contact.save()
    ContactPerson.objects.create(contact=contact, name="Piet de Boer")
    other = Contact.objects.create(company_name="Studio Noordwind", city="Zwolle")
    ContactPerson.objects.create(contact=other, name="Anna Smit")

    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    choice = app.locator("#aan-tav select")
    expect(choice).to_have_value("Joke Jansen")
    choice.select_option("Piet de Boer")

    picker.fill("noordwind")
    picker.press("Enter")
    expect(app.locator("#aan-adres")).to_contain_text("Zwolle")
    expect(choice).to_have_value("")
    expect(choice.locator("option")).to_have_text(["Niemand", "Anna Smit"])
    choice.select_option("Anna Smit")

    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Uren")
    line.locator("input[name$=-unit_price_cents]").fill("85")
    app.click("button[value=opslaan]")
    expect(app).to_have_url(re.compile(r"/facturen/\d+/"))
    expect(app.locator("#aan-tav select")).to_have_value("Anna Smit")
    assert Document.objects.get().attention == "Anna Smit"


def test_saving_while_the_live_totals_are_on_their_way_waits_for_them(app, contact):
    # The browser sends the form itself (app.js). Leaving the page would cut
    # off the live totals still underway, which htmx reports as an error
    # (the app fixture fails on it); so the form waits for them.
    held = []

    def hold_the_totals(route):
        held.append(route)

    app.route("**/facturen/nieuw/voorbeeld/", hold_the_totals)
    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    line = app.locator("[data-formset-forms=lines] .line").first
    # The first change sends them; the others queue behind it.
    with app.expect_request("**/facturen/nieuw/voorbeeld/"):
        picker.fill("korrel")
        picker.press("Enter")
        line.locator("input[name$=-unit_price_cents]").fill("85")
        line.locator("textarea[name$=-description]").fill("Uren")

    app.get_by_role("button", name="Concept opslaan").click(no_wait_after=True)
    # Without the wait, the save is there within a few milliseconds.
    app.wait_for_timeout(300)
    assert Document.objects.count() == 0
    for route in held:
        route.continue_()

    expect(app.locator(".flash-success").first).to_contain_text("Concept opgeslagen")
    assert Document.objects.get().lines.get().description == "Uren"


def test_a_form_sent_once_ignores_the_next_click_until_back(app):
    # A double click made the browser cut off the first request and send the
    # form again; after "Leegmaken" or "Terugzetten" the second one found the
    # database already replaced (BUGS-BY-HAND.md). Every POST form: the first
    # one goes, the next is stopped, and "back" (pageshow) makes the page
    # usable again. A listener after app.js's sees what it decided.
    app.goto(app.base + "/")
    prevented = app.evaluate(
        """() => {
            const form = [...document.querySelectorAll("form[method=post]")]
                .find((f) => f.textContent.includes("Probeer met nepdata"));
            const seen = [];
            document.addEventListener("submit", (event) => {
                seen.push(event.defaultPrevented);
                event.preventDefault();  // keep this page for the next step
            }, true);
            form.requestSubmit();
            form.requestSubmit();
            window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
            form.requestSubmit();
            // A form whose answer opens in a new tab (the editor's
            // "Voorbeeld-pdf") leaves nothing: it stays clickable.
            window.dispatchEvent(new PageTransitionEvent("pageshow", { persisted: true }));
            const tab = document.createElement("button");
            tab.formTarget = "_blank";
            form.append(tab);
            form.requestSubmit(tab);
            form.requestSubmit(tab);
            form.requestSubmit();
            return seen;
        }"""
    )
    assert prevented == [False, True, False, False, False, False]


def test_tab_in_the_last_cell_adds_a_line(app):
    app.goto(app.base + "/facturen/nieuw/")
    lines = app.locator("[data-formset-forms=lines] .line")
    expect(lines).to_have_count(1)
    lines.first.locator("select").focus()
    app.keyboard.press("Tab")
    expect(lines).to_have_count(2)
    expect(lines.nth(1).locator("textarea[name$=-description]")).to_be_focused()


APPEARANCE = "/instellingen/weergave/"


def _save_appearance(page, *labels):
    """Instellingen → Weergave: click each choice by its visible label (the
    radios themselves are hidden inside .seg), then Opslaan / Save."""
    page.goto(page.base + APPEARANCE)
    for label in labels:
        page.locator("#weergave label", has_text=label).click()
    page.locator("button[type=submit][form=weergave]").click()


def test_switching_language_translates_the_page_and_sets_lang(app):
    _save_appearance(app, "English")
    expect(app.locator("html")).to_have_attribute("lang", "en")
    expect(app.locator("h1")).to_have_text("Appearance")
    expect(app.locator(".toast")).to_be_visible()
    expect(app.locator(".sidebar .nav a").nth(1)).to_have_text("Invoices")

    app.locator(".sidebar .nav a", has_text="Invoices").click()
    expect(app.locator("h1")).to_have_text("Invoices")
    expect(app.locator("html")).to_have_attribute("lang", "en")

    _save_appearance(app, "Nederlands")
    expect(app.locator("html")).to_have_attribute("lang", "nl")
    expect(app.locator("h1")).to_have_text("Weergave")


def _background(page):
    return page.evaluate("getComputedStyle(document.body).backgroundColor")


def test_a_chosen_theme_beats_the_system_and_stays_after_a_reload(app, browser):
    # A tester, 2026-10-31: Huismus only followed the system's light/dark.
    app.emulate_media(color_scheme="light")
    light = _background(app)

    _save_appearance(app, "Donker")
    expect(app.locator("html")).to_have_attribute("data-theme", "dark")
    dark = _background(app)
    assert dark != light
    expect(app.locator("#weergave input[name=theme][value=dark]")).to_be_checked()

    # Through a page swap (hx-boost) and a reload the choice stays.
    app.locator(".sidebar .nav a", has_text="Facturen").click()
    expect(app.locator("h1")).to_have_text("Facturen")
    app.reload()
    expect(app.locator("html")).to_have_attribute("data-theme", "dark")
    assert _background(app) == dark

    # Kept for the user, not the browser: a second browser sees it too.
    other = browser.new_context(locale="nl-NL", color_scheme="light")
    other.add_cookies(app.context.cookies())
    page = other.new_page()
    page.goto(app.base + "/")
    expect(page.locator("html")).to_have_attribute("data-theme", "dark")
    other.close()

    # Light while the system is dark, and back to the system.
    app.emulate_media(color_scheme="dark")
    _save_appearance(app, "Licht")
    expect(app.locator("html")).to_have_attribute("data-theme", "light")
    assert _background(app) == light
    _save_appearance(app, "Systeem")
    expect(app.locator("#weergave input[name=theme][value='']")).to_be_checked()
    expect(app.locator("html")).not_to_have_attribute("data-theme", re.compile(".*"))
    assert _background(app) == dark


def test_the_sidebar_and_more_menu_have_no_switches_left(app):
    # Taal en thema moved to Instellingen → Weergave (huismus-intern/besluiten.md,
    # 2026-10-31): linksonder only Hulp and Uitloggen.
    expect(app.locator(".sidebar-foot form.lang")).to_have_count(0)
    expect(app.locator(".sidebar-foot")).to_contain_text("Hulp")
    expect(app.locator(".sidebar-foot")).to_contain_text("Uitloggen")
    app.set_viewport_size({"width": 360, "height": 740})
    app.click(".tabbar button[popovertarget=meer-menu]")
    expect(app.locator("#meer-menu form.lang")).to_have_count(0)
    expect(app.locator("#meer-menu")).to_contain_text("Uitloggen")


def test_live_search_filters_and_keeps_focus(app, contact):
    from huismus.contacts.models import Contact

    Contact.objects.create(company_name="Studio Noordwind", city="Groningen")
    app.goto(app.base + "/contacten/")
    search = app.locator("input[name=q]")
    search.press_sequentially("noord")
    expect(app.locator("#contacten-tabel")).to_contain_text("Studio Noordwind")
    expect(app.locator("#contacten-tabel")).not_to_contain_text("Bakkerij De Korrel")
    expect(search).to_be_focused()


@pytest.mark.parametrize("path", ["/contacten/", "/facturen/", "/offertes/", "/uitgaven/"])
def test_clearing_a_live_search_leaves_one_q_in_the_address(app, history, path):
    # With hx-get="" htmx built on the current address, so after typing
    # and clearing it read ?q=Bakkerij&q= (found by verify-e2e, 2026-10-30).
    # history: an empty list shows no search field.
    app.goto(app.base + path)
    search = app.locator("input[name=q]")
    search.press_sequentially("ba")
    expect(app).to_have_url(re.compile(r"[?&]q=ba(&|$)"))
    search.fill("")
    expect(app).to_have_url(re.compile(r"[?&]q=(&|$)"))
    assert parse_qs(urlparse(app.url).query, keep_blank_values=True)["q"] == [""], app.url


def test_on_a_phone_the_contact_search_spans_the_card_after_a_tab_switch_and_archiving(
    app, contact
):
    # A hidden "Zoeken…" next to the field took its room (2026-10-30).
    app.set_viewport_size({"width": 390, "height": 800})

    def field_fills_the_toolbar():
        return app.evaluate(
            """() => {
                const toolbar = document.querySelector('.toolbar');
                const style = getComputedStyle(toolbar);
                const room = toolbar.clientWidth
                    - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
                const field = document.querySelector('.toolbar .input-affix');
                return Math.abs(field.getBoundingClientRect().width - room) <= 1;
            }"""
        )

    app.goto(app.base + "/contacten/")
    assert field_fills_the_toolbar()
    app.get_by_role("button", name="Archiveren").click()
    expect(app.locator("#contacten-tabel")).to_contain_text("Al je klanten zijn gearchiveerd")
    assert field_fills_the_toolbar()
    app.locator(".tabs .tab", has_text="Gearchiveerd").click()
    expect(app).to_have_url(re.compile(r"archived=1"))
    assert field_fills_the_toolbar()
    app.get_by_role("button", name="Dearchiveren").click()
    expect(app.locator(".tabs .tab", has_text="Actief")).to_contain_text("1")
    assert field_fills_the_toolbar()


def test_keyboard_shortcut_n_opens_a_new_invoice(app):
    app.goto(app.base + "/facturen/")
    app.keyboard.press("n")
    expect(app).to_have_url(app.base + "/facturen/nieuw/")


def test_moneybird_import_dry_run_then_commit_without_choosing_files_again(app):
    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2019.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)

    expect(app.locator(".mode-banner")).to_contain_text("Proefdraai")
    expect(app.locator(".file-item").first).to_contain_text("Klanten")
    assert Document.objects.count() == 0

    app.click("button[form=doorvoeren]", timeout=IMPORT_CLICK_TIMEOUT)
    expect(app.locator("h1")).to_have_text("Je administratie is verhuisd")
    assert Document.objects.filter(kind="invoice").count() == 13


def test_the_dry_run_file_rows_stay_readable_with_many_tabs(app):
    # Met de hand gevonden (BUGS-BY-HAND.md): een export met veel tabbladen
    # kneep de naam tot "l.." en schoof de grootte over de lijst met tabbladen.
    app.goto(app.base + "/importeren/")
    zips = sorted(FIXTURES.glob("lindeboom_communicatie_*.zip"))
    app.set_input_files("input[name=files]", [str(z) for z in zips])
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)
    expect(app.locator(".mode-banner")).to_contain_text("Proefdraai")

    for width in (390, 900, 1280):
        app.set_viewport_size({"width": width, "height": 900})
        problems = app.locator(".file-list").evaluate(
            """list => [...list.querySelectorAll('.file-item')].flatMap(item => {
                const name = item.querySelector('.f-name');
                const meta = item.querySelector('.f-meta');
                const arrow = item.querySelector('.f-arrow');
                const out = [];
                if (name.scrollWidth > name.clientWidth + 1)
                    out.push('naam afgekapt: ' + name.textContent);
                const lines = meta.getClientRects().length;
                if (lines > 1) out.push('grootte over ' + lines + ' regels: ' + meta.textContent);
                const a = meta.getBoundingClientRect(), b = arrow.getBoundingClientRect();
                const overlaps = a.left < b.right && b.left < a.right
                    && a.top < b.bottom && b.top < a.bottom;
                if (overlaps) out.push('grootte over tabbladen: ' + name.textContent);
                return out;
            })"""
        )
        assert problems == [], f"{width}px: {problems}"


def test_moneybird_import_counts_names_a_discount_and_keeps_the_export(app):
    # Besluit 2026-11-02, "Moneybird-import verliest nooit stil gegevens".
    from huismus.imports.models import ImportedRow

    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2014.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)

    quotes = app.locator("details.report", has_text="Offertes")
    expect(quotes.locator(".stat-chip").first).to_have_text("14in de export")
    expect(quotes).to_have_attribute("open", "")
    expect(quotes.locator("h3", has_text="Korting")).to_be_visible()
    expect(quotes).to_contain_text("Offerte 2013-0011")

    app.click("button[form=doorvoeren]", timeout=IMPORT_CLICK_TIMEOUT)
    expect(app.locator(".celebrate")).to_contain_text(
        "Je originele export staat bewaard in Huismus, ook in je back-ups."
    )
    assert ImportedRow.objects.filter(sheet="offertes_export").count() == 14


def test_moneybird_import_names_a_column_huismus_does_not_know(app, tmp_path):
    import zipfile
    from io import BytesIO

    import openpyxl

    source = FIXTURES / "lindeboom_communicatie_2021.zip"
    export = tmp_path / source.name
    with zipfile.ZipFile(source) as zin, zipfile.ZipFile(export, "w") as zout:
        for item in zin.infolist():
            content = zin.read(item)
            if item.filename.endswith("/verkoopfacturen_export.xlsx"):
                workbook = openpyxl.load_workbook(BytesIO(content))
                workbook.active.cell(
                    row=1, column=workbook.active.max_column + 1, value="kostenplaats"
                )
                buffer = BytesIO()
                workbook.save(buffer)
                content = buffer.getvalue()
            zout.writestr(item, content)

    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(export))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)

    expect(app.locator("details.report", has_text="Let op")).to_contain_text(
        "In verkoopfacturen_export.xlsx staat een kolom die Huismus niet kent: kostenplaats. "
        "Huismus neemt hem niet over, maar bewaart hem wel."
    )


def test_mobile_tab_bar_and_more_menu(app):
    app.set_viewport_size({"width": 360, "height": 740})
    app.goto(app.base + "/")
    expect(app.locator(".sidebar")).to_be_hidden()
    app.click(".tabbar button[popovertarget=meer-menu]")
    app.locator("#meer-menu a", has_text="Klanten").click()
    expect(app).to_have_url(app.base + "/contacten/")
    width = app.evaluate("document.documentElement.scrollWidth")
    assert width <= 360


def test_rapporten_opens_the_year_overview_on_desktop_and_phone(app):
    app.goto(app.base + "/")
    app.locator(".sidebar a", has_text="Rapporten").click()
    expect(app).to_have_url(app.base + "/rapporten/jaaroverzicht/")
    expect(app.locator(".sidebar a[aria-current=page]")).to_have_text("Rapporten")

    app.set_viewport_size({"width": 360, "height": 740})
    app.goto(app.base + "/")
    app.click(".tabbar button[popovertarget=meer-menu]")
    app.locator("#meer-menu a", has_text="Rapporten").click()
    expect(app).to_have_url(app.base + "/rapporten/jaaroverzicht/")
    expect(app.locator(".tabbar button[popovertarget=meer-menu]")).to_have_attribute(
        "aria-current", "page"
    )


def test_on_a_phone_the_language_is_set_under_instellingen(app):
    app.set_viewport_size({"width": 360, "height": 740})
    app.goto(app.base + "/facturen/")
    app.click(".tabbar button[popovertarget=meer-menu]")
    app.locator("#meer-menu a", has_text="Instellingen").click()
    app.locator(".settings-topics a", has_text="Weergave").click()
    expect(app).to_have_url(app.base + APPEARANCE)
    app.locator("#weergave label", has_text="English").click()
    app.locator("button[type=submit][form=weergave]").click()

    expect(app.locator("html")).to_have_attribute("lang", "en")
    expect(app.locator("h1")).to_have_text("Appearance")
    assert app.evaluate("document.documentElement.scrollWidth") <= 360


def test_on_a_phone_the_language_works_by_touch_and_survives_a_restart(app, browser, browser_name):
    # Found by hand, 2026-10-31: on a phone the language didn't stick. A phone
    # 390 px wide with touch, like an iPhone: tap English, tap Opslaan.
    # Firefox has no mobile mode in Playwright; touch it does have.
    phone_args = {
        "viewport": {"width": 390, "height": 844},
        "has_touch": True,
        "locale": "nl-NL",
        "service_workers": "block",
    }
    if browser_name != "firefox":
        phone_args["is_mobile"] = True
    phone = browser.new_context(**phone_args)
    phone.add_cookies(app.context.cookies())
    page = phone.new_page()
    page.goto(app.base + APPEARANCE)
    page.locator("#weergave label", has_text="English").tap()
    page.locator("button[type=submit][form=weergave]").tap()
    expect(page.locator("h1")).to_have_text("Appearance")

    # The phone closes the browser (or the app on the home screen) and
    # forgets every cookie without an expiry, which Playwright reports as
    # expires -1. Huismus sets none: such a cookie is a choice the phone
    # loses (BUGS-BY-HAND.md).
    cookies = phone.cookies()
    assert [cookie["name"] for cookie in cookies if cookie["expires"] <= 0] == []
    phone.close()
    phone = browser.new_context(**phone_args)
    phone.add_cookies(cookies)
    page = phone.new_page()
    page.goto(app.base + "/facturen/")
    expect(page.locator("h1")).to_have_text("Invoices")

    # And back to Dutch the same way.
    page.goto(app.base + APPEARANCE)
    page.locator("#weergave label", has_text="Nederlands").tap()
    page.locator("button[type=submit][form=weergave]").tap()
    expect(page.locator("h1")).to_have_text("Weergave")
    phone.close()


def test_django_admin_works_under_the_page_policy(app):
    # The admin has templates of its own; a script or style they need but
    # the Content-Security-Policy (core.middleware) blocks shows up as a
    # console error, which the `app` fixture fails on.
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(username="freelancer").update(is_staff=True, is_superuser=True)
    app.goto(app.base + "/admin/auth/user/")
    expect(app.locator("#result_list")).to_contain_text("freelancer")


def test_htmx_never_evaluates_code_from_a_page(app):
    # hx-on, js: values and <script> in swapped-in HTML would all run code
    # taken from a page; Huismus uses none of them (base.html).
    app.goto(app.base + "/facturen/")
    app.wait_for_function("window.htmx !== undefined")
    config = app.evaluate("({eval: htmx.config.allowEval, scripts: htmx.config.allowScriptTags})")
    assert config == {"eval": False, "scripts": False}


def test_moneybird_dry_run_can_be_cancelled(app):
    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2019.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)
    expect(app.locator(".mode-banner")).to_contain_text("Proefdraai")

    app.click("form[action$='annuleren/'] button")

    expect(app).to_have_url(app.base + "/importeren/")
    expect(app.locator("body")).to_contain_text("Import geannuleerd")
    assert Document.objects.count() == 0


def test_the_submit_button_shows_a_spinner_while_the_request_runs(app):
    # A dry run of years of exports on a Pi takes a while, and without a
    # spinner the page looked like nothing was happening. The browser sends
    # the form itself (app.js), and while it waits for the next page
    # Playwright can't look at the old one, so a listener that runs after
    # app.js's reports the button's state at the moment the form is sent.
    app.goto(app.base + "/importeren/")
    reports = []
    app.on("console", lambda message: reports.append(message.text))
    app.evaluate(
        """document.addEventListener("submit", (event) => {
            const button = event.submitter;
            const spinner = getComputedStyle(button.querySelector(".spinner")).display;
            console.log(`${button.classList.contains("is-loading")} ${spinner}`);
        }, true)"""
    )
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2019.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)

    expect(app.locator(".mode-banner")).to_contain_text("Proefdraai")
    loading, spinner = reports[0].split()
    assert loading == "true"
    assert spinner != "none"


def test_the_dry_run_proposes_settings_from_the_export_and_saves_what_you_confirm(app):
    from huismus.business.models import Settings

    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2019.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)

    number_format = app.locator("input[name='settings-invoice_number_format']")
    expect(number_format).to_have_value("{customer}{seq:04d}")
    app.fill("input[name='settings-phone']", "020 123 4567")
    app.click("button[form=doorvoeren]", timeout=IMPORT_CLICK_TIMEOUT)

    expect(app.locator("h1")).to_have_text("Je administratie is verhuisd")
    settings = Settings.load()
    assert settings.invoice_number_format == "{customer}{seq:04d}"
    assert settings.phone == "020 123 4567"


@pytest.mark.parametrize("path", ["/facturen/nieuw/", "/offertes/nieuw/"])
def test_new_contact_from_the_editor_returns_with_the_contact_chosen(app, contact, path):
    app.goto(f"{app.base}{path}")
    app.get_by_role("link", name="+ Nieuwe klant").click()
    app.wait_for_url(re.compile("/contacten/nieuw/"))
    app.locator("input[name=company_name]").fill("Studio Noordwind")
    app.get_by_role("button", name=re.compile("Opslaan en terug")).click()
    app.wait_for_url(re.compile(re.escape(path)))
    expect(app.locator("#id_contact option:checked")).to_have_text("Studio Noordwind")


def test_only_the_sidebar_morphs_between_pages(app):
    # A view-transition-name on content that differs in size from page to
    # page makes the browser stretch the old page into the new one: it looked
    # like zooming out and in at every menu click.
    for path in ["/", "/facturen/", "/offertes/"]:
        app.goto(app.base + path)
        names = app.evaluate(
            """() => [...document.querySelectorAll("*")]
                .map(el => getComputedStyle(el).viewTransitionName)
                .filter(name => name && name !== "none" && name !== "root")"""
        )
        assert names == ["sidebar"], f"{path}: {names}"


def test_the_trash_icon_over_the_logo_removes_it(app):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from huismus.business.models import Settings

    buffer = BytesIO()
    Image.new("RGB", (40, 20), "#1B6AC9").save(buffer, "PNG")
    png = buffer.getvalue()
    business = Settings.load()
    business.logo.save("logo.png", SimpleUploadedFile("logo.png", png), save=True)

    app.goto(app.base + "/instellingen/huisstijl/")
    app.locator(".logo-remove").click()
    expect(app.locator(".logo-slot img")).to_have_css("opacity", "0.3")
    app.get_by_role("button", name="Opslaan", exact=True).click()

    expect(app.locator(".logo-slot img")).to_have_count(0)
    expect(app.locator(".logo-slot")).to_contain_text("Nog geen logo")
    assert not Settings.load().logo


@pytest.mark.parametrize("width", [390, 1440])
def test_a_settings_topic_opens_from_the_overview_and_saves_on_its_own_page(app, width):
    app.set_viewport_size({"width": width, "height": 800})
    app.goto(app.base + "/instellingen/")
    card = app.get_by_role("link", name="KOR", exact=True)
    expect(card).to_contain_text("Uit")

    card.click()
    expect(app.locator("h1")).to_have_text("KOR")
    app.get_by_role("switch", name="Ik gebruik de KOR").check()
    app.get_by_role("button", name="Opslaan", exact=True).click()

    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    expect(app).to_have_url(f"{app.base}/instellingen/kor/")
    app.get_by_role("link", name="← Instellingen").click()
    expect(app.get_by_role("link", name="KOR", exact=True)).to_contain_text("Aan")
    assert Settings.load().kor_enabled


def test_the_kor_limit_field_shows_and_takes_a_dutch_amount(app):
    # huismus-intern/besluiten.md 2026-10-29: "20.000,00", not "20000.00", in every
    # browser engine (a number input could not show it at all).
    app.goto(app.base + "/instellingen/kor/")
    limit = app.locator("#id_kor_limit_cents")
    expect(limit).to_have_value("20.000,00")

    limit.fill("25.000,50")
    app.get_by_role("button", name="Opslaan", exact=True).click()

    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    expect(app.locator("#id_kor_limit_cents")).to_have_value("25.000,50")
    assert Settings.load().kor_limit_cents == 2_500_050


def test_an_unclear_amount_gets_an_example(app):
    app.goto(app.base + "/instellingen/kor/")
    app.locator("#id_kor_limit_cents").fill("1,2,3")
    app.get_by_role("button", name="Opslaan", exact=True).click()

    expect(app.locator("main")).to_contain_text("Vul een bedrag in, zoals 1.250,00.")
    expect(app.locator("#id_kor_limit_cents")).to_have_value("1,2,3")
    assert Settings.load().kor_limit_cents == 2_000_000


def test_a_long_line_description_is_fully_readable(app, contact):
    long_text = (
        "Webdesign en ontwikkeling van de nieuwe website, inclusief ontwerp, bouw en overdracht. "
        * 3
    )
    app.goto(app.base + "/facturen/nieuw/")
    description = app.locator("textarea.line-desc").first
    short_height = description.evaluate("el => el.clientHeight")

    description.fill(long_text)

    # Grown to its text: nothing is cut off, so nothing needs scrolling.
    expect(description).to_have_value(long_text)
    assert description.evaluate("el => el.clientHeight") > short_height * 2
    assert description.evaluate("el => el.scrollHeight <= el.clientHeight + 1")
    for width in (1280, 390):  # the layout switches to stacked fields on a narrow paper
        app.set_viewport_size({"width": width, "height": 900})
        assert description.evaluate("el => el.scrollHeight <= el.clientHeight + 1")


def test_a_draft_invoice_can_be_deleted_from_the_editor(app, contact):
    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    app.goto(f"{app.base}/facturen/{draft.pk}/")

    app.get_by_role("button", name="Verwijderen").first.click()
    expect(app.locator("#verwijderen")).to_be_visible()
    app.locator("#verwijderen").get_by_role("button", name="Verwijderen").click()

    expect(app).to_have_url(app.base + "/facturen/")
    assert not Document.objects.filter(pk=draft.pk).exists()


def test_the_preview_pdf_opens_in_a_new_tab_and_saves_nothing(app, contact):
    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    expect(app.locator("#aan-adres")).to_contain_text("Utrecht")
    app.locator("textarea[name$=-description]").first.fill("Voorbeeldwerk")
    app.locator("input[name$=-unit_price_cents]").first.fill("125.00")

    # Headless browsers have no PDF viewer, so the tab itself stays blank:
    # check that a new tab was opened and what the server answered.
    with (
        app.context.expect_page(),
        app.context.expect_event("response", lambda r: "voorbeeld-pdf" in r.url) as answer,
    ):
        app.get_by_role("button", name="Voorbeeld-pdf").click()

    assert answer.value.status == 200
    assert answer.value.headers["content-type"] == "application/pdf"
    assert app.url == app.base + "/facturen/nieuw/"  # not loaded into the editor's own tab
    # The editor is still there with what was typed, and nothing was stored.
    expect(app.locator("textarea[name$=-description]").first).to_have_value("Voorbeeldwerk")
    assert Document.objects.count() == 0


def test_in_the_installed_app_the_preview_pdf_opens_over_the_editor(app, contact):
    # Playwright can't install the app: matchMedia says it is installed.
    from huismus.documents.models import DocumentLine

    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=draft, description="Uren", unit_price_cents=10000)
    app.add_init_script(
        """const own = window.matchMedia.bind(window);
        window.matchMedia = (query) => query === "(display-mode: standalone)"
            ? { matches: true, media: query, addEventListener() {}, removeEventListener() {} }
            : own(query);"""
    )
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(f"{app.base}/facturen/{draft.pk}/")
    description = app.locator("textarea[name$=-description]").first
    description.fill("Voorbeeldwerk")
    dialog = app.locator("#voorbeeld-pdf")
    # Leaving the field sends the live totals once more (its change event).
    with app.expect_response(lambda r: r.url.endswith("/voorbeeld/")):
        description.blur()
    posts = []
    app.on("request", lambda r: posts.append(r.url) if r.method == "POST" else None)

    for close in ("button", "Escape", "backdrop"):
        app.locator(".actionbar-more-toggle").click()
        with app.expect_response(lambda r: "voorbeeld-pdf" in r.url) as answer:
            app.get_by_role("button", name="Voorbeeld-pdf").click()
        assert answer.value.headers["content-type"] == "application/pdf"
        expect(dialog).to_be_visible()
        frame = dialog.locator("iframe.pdf-frame")
        expect(frame).to_be_visible()
        assert frame.bounding_box()["width"] <= 390
        expect(dialog.get_by_role("button", name="Sluiten")).to_be_in_viewport()
        if close == "button":
            dialog.get_by_role("button", name="Sluiten").click()
        elif close == "Escape":
            app.keyboard.press("Escape")
        else:
            app.mouse.click(2, 2)  # beside the dialog
        expect(dialog).to_be_hidden()
        # Focus back on "Meer", whose menu held the button.
        expect(app.locator(".actionbar-more-toggle")).to_be_focused()
        # Still the editor, with what was typed.
        assert app.url == f"{app.base}/facturen/{draft.pk}/"
        expect(description).to_have_value("Voorbeeldwerk")
        expect(frame).to_have_count(0)

    # Only the preview was posted: no save, no live totals.
    assert posts and all("voorbeeld-pdf" in url for url in posts)
    # Nothing was saved: opened again, the old line is back. (Not reload():
    # Firefox then puts back what was typed in the form itself.)
    app.goto(f"{app.base}/facturen/{draft.pk}/")
    expect(app.locator("textarea[name$=-description]").first).to_have_value("Uren")
    assert DocumentLine.objects.get(document=draft).description == "Uren"


def test_an_issued_invoice_can_be_reopened_after_a_warning(app, contact):
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(
        document=draft, description="Uren", quantity="1", unit_price_cents=10000
    )
    invoice = issue(draft)
    app.goto(f"{app.base}/facturen/{invoice.pk}/")

    app.get_by_role("button", name="Toch bewerken…").click()
    dialog = app.locator("#heropenen")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("creditnota")
    dialog.get_by_role("button", name="Toch bewerken").click()

    expect(app.locator("#factuur")).to_be_visible()
    expect(app.locator(".flash-warning").first).to_contain_text(invoice.number)
    assert Document.objects.get(pk=invoice.pk).status == "draft"


@pytest.mark.parametrize("width", [1440, 390])
def test_annuleren_after_toch_bewerken_puts_the_invoice_back(app, contact, width):
    # Saved changes too: "Annuleren" means never mind, all of it.
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(
        document=draft, description="Uren", quantity="1", unit_price_cents=10000
    )
    invoice = issue(draft)
    app.set_viewport_size({"width": width, "height": 800})
    app.goto(f"{app.base}/facturen/{invoice.pk}/")
    app.get_by_role("button", name="Toch bewerken…").click()
    app.locator("#heropenen").get_by_role("button", name="Toch bewerken").click()
    app.locator("textarea[name$=-description]").first.fill("Uren (aangepast)")
    app.get_by_role("button", name="Concept opslaan").click()
    expect(app.locator(".flash-success").first).to_contain_text("Concept opgeslagen")

    bar = app.locator(".actionbar")
    if width < 760:
        bar.get_by_role("button", name="Meer").click()
    bar.get_by_role("button", name="Annuleren").click()

    expect(app.locator(".flash-success").first).to_contain_text("weer zoals je hem uitgaf")
    expect(app.locator(".doc-table")).to_contain_text("Uren")
    expect(app.locator(".doc-table")).not_to_contain_text("aangepast")
    assert Document.objects.get(pk=invoice.pk).status == "issued"


# Playwright's offline emulation with a service worker is only dependable in
# Chromium.
@pytest.mark.only_browser("chromium")
@pytest.mark.browser_context_args(service_workers="allow")
def test_the_installed_app_shows_its_offline_page_without_a_connection(app):
    # The worker caches the offline page while installing, before it takes
    # control of this page.
    # Not wait_for_function: while it polls, Playwright evaluates its
    # predicate as a string, which the CSP (script-src 'self') refuses.
    # Never without a limit: a controllerchange missed under load hung the
    # whole test run. After 10 s a reload hands the page to the worker that
    # is active by then.
    controlled = app.evaluate(
        """() => navigator.serviceWorker.ready.then(() =>
            navigator.serviceWorker.controller ? true : new Promise((resolve) => {
                navigator.serviceWorker.addEventListener("controllerchange", () => resolve(true));
                setTimeout(() => resolve(false), 10000);
            }))"""
    )
    if not controlled:
        app.reload()
        assert app.evaluate("() => Boolean(navigator.serviceWorker.controller)")

    # Offline on purpose: Chromium logs the failed request as a console error
    # (the version in Claude Code's cloud containers does, at least).
    app.tolerate.append("ERR_INTERNET_DISCONNECTED")
    app.context.set_offline(True)
    app.goto(app.base + "/facturen/")
    expect(app.get_by_role("heading", name="Huismus is niet bereikbaar")).to_be_visible()

    app.context.set_offline(False)
    app.get_by_role("link", name="Opnieuw proberen").click()
    expect(app).to_have_url(app.base + "/")
    expect(app.locator(".sidebar")).to_be_visible()


def test_an_imported_invoice_s_pdf_page_switches_and_leads_back(app):
    # The original from Moneybird is a file from data/, not a generated
    # PDF. The PDF page opens on it, switches to the regenerated one, and
    # downloads either named after the number. 390 px: on a phone.
    from huismus.core.models import Attachment

    app.goto(app.base + "/importeren/")
    app.set_input_files("input[name=files]", str(FIXTURES / "lindeboom_communicatie_2019.zip"))
    app.click("button.btn-lg[type=submit]", timeout=IMPORT_CLICK_TIMEOUT)
    app.click("button[form=doorvoeren]", timeout=IMPORT_CLICK_TIMEOUT)
    expect(app.locator("h1")).to_have_text("Je administratie is verhuisd")

    invoice = Attachment.objects.filter(kind="original_pdf").first().document
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + f"/facturen/{invoice.pk}/")
    app.locator(".page-head a.btn", has_text="PDF").click()
    original = app.get_by_role("link", name="Origineel uit Moneybird")
    expect(original).to_have_attribute("aria-current", "page")
    expect(app.locator("iframe.pdf-frame")).to_have_attribute(
        "src", f"/facturen/{invoice.pk}/origineel/ingebed/"
    )
    with app.expect_download() as download:
        app.get_by_role("link", name="Downloaden").click()
    assert download.value.suggested_filename == f"{invoice.number}.pdf"

    app.get_by_role("link", name="Opnieuw gegenereerd").click()
    expect(app.locator("iframe.pdf-frame")).to_have_attribute(
        "src", f"/facturen/{invoice.pk}/pdf/ingebed/"
    )
    with app.expect_download() as download:
        app.get_by_role("link", name="Downloaden").click()
    assert download.value.suggested_filename == f"{invoice.number}.pdf"

    app.get_by_role("link", name=f"Factuur {invoice.number}").click()
    expect(app).to_have_url(app.base + f"/facturen/{invoice.pk}/")


def _issued_invoice(contact):
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=invoice, description="Brood", unit_price_cents=1250)
    return issue(invoice)


def test_on_a_phone_the_pdf_has_a_way_back_to_the_invoice(app, contact):
    # In the app on an iPhone's home screen there is no back button of the
    # browser: a bare PDF filled the screen and there was no way back (found
    # by hand, twice). Now the PDF sits on a page of Huismus.
    invoice = _issued_invoice(contact)
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + f"/facturen/{invoice.pk}/")

    app.locator(".page-head a.btn", has_text="PDF").click()

    expect(app).to_have_url(app.base + f"/facturen/{invoice.pk}/pdf/bekijken/")
    frame = app.locator("iframe.pdf-frame")
    expect(frame).to_be_visible()
    assert frame.bounding_box()["width"] <= 390
    back = app.get_by_role("link", name=f"Factuur {invoice.number}")
    expect(back).to_be_in_viewport()
    expect(app.get_by_role("link", name="Downloaden")).to_be_in_viewport()
    back.click()
    expect(app).to_have_url(app.base + f"/facturen/{invoice.pk}/")
    expect(app.locator("h1")).to_contain_text(invoice.number)


def test_in_the_installed_app_the_pdf_page_shares_instead_of_downloading(app, contact):
    # Playwright can't install the app nor open a share sheet: matchMedia
    # says it is installed, and navigator.share records what it was given.
    invoice = _issued_invoice(contact)
    app.add_init_script(
        """const own = window.matchMedia.bind(window);
        window.matchMedia = (query) => query === "(display-mode: standalone)"
            ? { matches: true, media: query, addEventListener() {}, removeEventListener() {} }
            : own(query);
        navigator.canShare = (data) => Boolean(data.files?.length);
        navigator.share = async (data) => { window.shared = data.files.map((f) => f.name); };"""
    )
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(app.base + f"/facturen/{invoice.pk}/pdf/bekijken/")

    share = app.get_by_role("button", name="Delen")
    expect(share).to_be_visible()
    expect(app.get_by_role("link", name="Downloaden")).to_be_hidden()
    share.click()
    app.wait_for_function("window.shared")
    assert app.evaluate("window.shared") == [f"{invoice.number}.pdf"]


def test_without_sharing_the_pdf_page_keeps_download(app, contact):
    invoice = _issued_invoice(contact)
    app.add_init_script("delete Navigator.prototype.canShare; delete navigator.canShare;")
    app.goto(app.base + f"/facturen/{invoice.pk}/pdf/bekijken/")

    expect(app.get_by_role("link", name="Downloaden")).to_be_visible()
    expect(app.get_by_role("button", name="Delen")).to_be_hidden()


def test_an_issued_invoice_can_be_copied_into_a_new_draft(app, contact):
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=invoice, description="Brood", unit_price_cents=1250)
    issue(invoice)
    app.goto(f"{app.base}/facturen/{invoice.pk}/")

    app.locator(".page-head").get_by_role("button", name="Kopiëren").click()

    expect(app.locator("h1")).to_have_text("Factuur voor Bakkerij De Korrel")
    copy = Document.objects.exclude(pk=invoice.pk).get()
    expect(app).to_have_url(f"{app.base}/facturen/{copy.pk}/")
    expect(app.locator("textarea[name$=-description]").first).to_have_value("Brood")
    expect(app.locator("#aan-adres")).to_contain_text("Utrecht")


def test_a_sent_quote_can_be_copied_into_a_new_draft(app, contact):
    from huismus.documents.models import DocumentLine
    from huismus.documents.quoting import send_quote

    quote = Document.objects.create(kind="quote", status="draft", contact=contact)
    DocumentLine.objects.create(document=quote, description="Taarten", unit_price_cents=3000)
    send_quote(quote)
    app.goto(f"{app.base}/offertes/{quote.pk}/")

    app.get_by_role("button", name="Kopiëren").click()

    expect(app.locator("h1")).to_have_text("Offerte voor Bakkerij De Korrel")
    copy = Document.objects.exclude(pk=quote.pk).get()
    expect(app).to_have_url(f"{app.base}/offertes/{copy.pk}/")
    expect(app.locator("textarea[name$=-description]").first).to_have_value("Taarten")


def test_on_a_phone_the_editor_s_extra_actions_sit_behind_meer(app, contact):
    draft = Document.objects.create(kind="invoice", status="draft", contact=contact)
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(f"{app.base}/facturen/{draft.pk}/")
    bar = app.locator(".actionbar")
    expect(bar.get_by_role("button", name="Verwijderen")).to_be_hidden()

    bar.get_by_role("button", name="Meer").click()
    bar.get_by_role("button", name="Verwijderen").click()

    # The dialog opens over the menu, and the menu is gone.
    expect(app.locator("#verwijderen")).to_be_visible()
    expect(app.locator("#actiebalk-meer")).to_be_hidden()


def _mail_set_up(settings):
    from huismus.business import smtp
    from huismus.business.models import Settings

    smtp.set_password("e2e-niet-echt")
    business = Settings.load()
    business.smtp_provider = "gmail"
    business.smtp_host = "smtp.gmail.com"
    business.smtp_port = 587
    business.smtp_username = "voorbeeld@example.invalid"
    business.save()


def test_an_issued_invoice_is_mailed_from_its_page_and_lands_on_the_timeline(
    app, contact, settings
):
    # The live server runs in this process with the locmem backend
    # (huismus/config/settings_test.py): mail.outbox, never a real server.
    from django.core import mail

    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    _mail_set_up(settings)
    contact.email = "bakker@example.invalid"
    contact.save()
    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=invoice, description="Brood", unit_price_cents=1250)
    issue(invoice)
    app.goto(f"{app.base}/facturen/{invoice.pk}/")

    app.locator(".page-head").get_by_role("link", name="Mailen").click()

    expect(app.locator("h1")).to_have_text(f"Factuur {invoice.number} mailen")
    expect(app.get_by_label("Aan")).to_have_value("bakker@example.invalid")
    expect(app.get_by_label("Onderwerp")).to_have_value(
        f"Factuur {invoice.number} van Voorbeeld BV"
    )
    app.get_by_label("Stuur mij een kopie (BCC)").check()
    app.locator(".actionbar").get_by_role("button", name="Versturen").click()

    expect(app).to_have_url(f"{app.base}/facturen/{invoice.pk}/")
    expect(app.locator(".timeline")).to_contain_text("Gemaild naar bakker@example.invalid")
    [message] = mail.outbox
    assert message.to == ["bakker@example.invalid"]
    assert message.bcc == ["info@example.invalid"]
    assert message.attachments[0][0] == f"{invoice.number}.pdf"


def test_on_a_phone_a_sent_quote_is_mailed_from_behind_meer(app, contact, settings):
    from django.core import mail

    from huismus.documents.models import DocumentLine
    from huismus.documents.quoting import send_quote

    _mail_set_up(settings)
    contact.email = "bakker@example.invalid"
    contact.save()
    quote = Document.objects.create(kind="quote", status="draft", contact=contact)
    DocumentLine.objects.create(document=quote, description="Taarten", unit_price_cents=3000)
    send_quote(quote)
    app.set_viewport_size({"width": 390, "height": 800})
    app.goto(f"{app.base}/offertes/{quote.pk}/")

    bar = app.locator(".actionbar")
    bar.get_by_role("button", name="Meer").click()
    bar.get_by_role("link", name="Mailen").click()
    app.locator(".actionbar").get_by_role("button", name="Versturen").click()

    expect(app).to_have_url(f"{app.base}/offertes/{quote.pk}/")
    expect(app.locator(".timeline")).to_contain_text("Gemaild naar bakker@example.invalid")
    assert len(mail.outbox) == 1
    assert app.evaluate("document.documentElement.scrollWidth") <= 390


def test_without_a_password_the_mail_page_says_where_to_set_it_up(app, contact):
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=invoice, description="Brood", unit_price_cents=1250)
    issue(invoice)
    app.goto(f"{app.base}/facturen/{invoice.pk}/mailen/")

    expect(app.get_by_text("Mailen is nog niet ingesteld.")).to_be_visible()
    expect(app.locator(".actionbar").get_by_role("button", name="Versturen")).to_be_disabled()
    app.get_by_role("link", name="Instellingen").last.click()
    expect(app).to_have_url(re.compile(r"/instellingen/mailen/$"))


def test_mailing_is_set_up_in_the_settings_screen_password_included(app):
    from huismus.business import smtp

    app.goto(f"{app.base}/instellingen/mailen/")
    # While mailing is off, only "Mailen via" shows (without JS: everything).
    expect(app.get_by_label("Gebruikersnaam")).to_be_hidden()
    expect(app.get_by_text("Geen wachtwoord ingesteld.")).to_be_hidden()

    app.get_by_label("Mailen via").select_option(label="Gmail")
    expect(app.get_by_text("Geen wachtwoord ingesteld.")).to_be_visible()
    app.get_by_label("Gebruikersnaam").fill("voorbeeld@example.invalid")
    app.get_by_label("Wachtwoord", exact=True).fill("abcd efgh ijkl mnop")
    app.get_by_role("button", name="Opslaan", exact=True).click()

    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()
    expect(app.get_by_text("Wachtwoord ingesteld", exact=True)).to_be_visible()
    expect(app.get_by_label("Wachtwoord", exact=True)).to_have_value("")
    expect(app.get_by_role("button", name="Testmail sturen")).to_be_visible()
    assert smtp.password() == "abcdefghijklmnop"


def test_the_mail_fields_hide_again_when_mailing_is_switched_off(app, settings):
    _mail_set_up(settings)
    app.goto(f"{app.base}/instellingen/mailen/")
    expect(app.get_by_label("SMTP-server")).to_be_visible()
    expect(app.get_by_role("button", name="Testmail sturen")).to_be_visible()

    app.get_by_label("Mailen via").select_option(label="Niet ingesteld")

    expect(app.get_by_label("SMTP-server")).to_be_hidden()
    expect(app.get_by_label("Wachtwoord", exact=True)).to_be_hidden()
    expect(app.get_by_text("Wachtwoord ingesteld", exact=True)).to_be_hidden()
    expect(app.get_by_role("button", name="Testmail sturen")).to_be_hidden()

    app.get_by_label("Mailen via").select_option(label="Anders")
    expect(app.get_by_label("SMTP-server")).to_be_visible()


def test_a_mail_text_changed_in_the_settings_is_where_the_mail_starts(app, contact, settings):
    from huismus.documents.issuing import issue
    from huismus.documents.models import DocumentLine

    _mail_set_up(settings)
    app.goto(f"{app.base}/instellingen/mailen/")
    app.locator("details", has_text="Factuur").locator("summary").click()
    subject = app.get_by_label("Onderwerp in het Nederlands").first
    expect(subject).to_have_value("Factuur {nummer} van {bedrijf}")
    subject.fill("Rekening {nummer}")
    app.get_by_role("button", name="Opslaan", exact=True).click()
    expect(app.get_by_text("Instellingen opgeslagen.")).to_be_visible()

    invoice = Document.objects.create(kind="invoice", status="draft", contact=contact)
    DocumentLine.objects.create(document=invoice, description="Brood", unit_price_cents=1250)
    issue(invoice)
    app.goto(f"{app.base}/facturen/{invoice.pk}/mailen/")

    expect(app.get_by_label("Onderwerp")).to_have_value(f"Rekening {invoice.number}")


def test_the_kor_limit_shows_in_the_issue_dialog_and_on_the_overview(app, contact):
    business = Settings.load()
    business.kor_enabled = True
    business.kor_text = "Vrijgesteld van btw (KOR)."
    business.kor_limit_cents = 100_000
    business.save()

    app.goto(app.base + "/facturen/nieuw/")
    picker = app.locator("input[role=combobox]")
    picker.fill("korrel")
    picker.press("Enter")
    line = app.locator("[data-formset-forms=lines] .line").first
    line.locator("textarea[name$=-description]").fill("Uren")
    line.locator("input[name$=-unit_price_cents]").fill("850")
    expect(app.locator("#totalen")).to_contain_text("850,00")

    # The dialog warns before the number is taken; it doesn't block.
    app.click("#uitgeven-knop")
    expect(app.locator("#uitgeven")).to_contain_text("85% van je KOR-grens van € 1.000,00")
    app.click("#uitgeven button[value=uitgeven]", timeout=30000)
    expect(app.locator(".pill-final").first).to_be_visible()

    app.goto(app.base + "/")
    banner = app.locator("#kor-melding")
    expect(banner).to_contain_text("85% van je KOR-grens")
    banner.click()
    expect(app).to_have_url(re.compile(r"/rapporten/jaaroverzicht/\?jaar=\d{4}$"))

    # The year overview shows the same share of the limit as a bar.
    card = app.locator("#kor-grens")
    expect(card).to_contain_text("85% van je KOR-grens")
    expect(card).to_contain_text("€ 850,00 van € 1.000,00")
    expect(card.locator(".progress.is-warn")).to_be_visible()
    expect(card).not_to_contain_text("Gemeten met je huidige KOR-grens")

    # An earlier year, measured with the limit set now.
    app.get_by_role("link", name="Vorig jaar").click()
    expect(app.locator("#kor-grens")).to_contain_text("0% van je KOR-grens")
    expect(app.locator("#kor-grens")).to_contain_text(
        "Gemeten met je huidige KOR-grens van € 1.000,00."
    )


def test_starting_step_by_step_without_moneybird(app, live_server):
    # A fresh installation: nothing filled in yet.
    Settings.objects.all().delete()
    app.goto(app.base + "/")
    app.get_by_role("link", name="Stap voor stap beginnen").click()

    expect(app.locator("h1")).to_have_text("Bedrijf")
    app.fill("#id_business_name", "Atelier Zonnig")
    app.fill("#id_address_line1", "Lindelaan 4")
    app.fill("#id_postal_code", "3512 AB")
    app.fill("#id_city", "Utrecht")
    app.fill("#id_kvk_number", "87654321")
    app.fill("#id_iban", "NL91ABNA0417164300")
    app.fill("#id_email", "hallo@example.invalid")
    app.get_by_role("button", name="Opslaan en verder").click()

    expect(app.locator("h1")).to_have_text("KOR")
    app.get_by_role("switch").check()
    app.fill("#id_kor_text", "Vrijgesteld van btw (KOR).")
    app.get_by_role("button", name="Opslaan en verder").click()

    expect(app.locator("h1")).to_have_text("Facturen")
    expect(app.locator("main")).to_contain_text("Volgende als je vandaag uitgeeft")
    # Back keeps what was saved.
    app.get_by_role("link", name="Terug").click()
    expect(app.locator("#id_kor_text")).to_have_value("Vrijgesteld van btw (KOR).")
    app.get_by_role("button", name="Opslaan en verder").click()
    expect(app.locator("h1")).to_have_text("Facturen")
    app.get_by_role("button", name="Opslaan en verder").click()

    expect(app.locator("h1")).to_have_text("Logo")
    app.get_by_role("link", name="Overslaan").click()

    expect(app.locator("h1")).to_have_text("Je kunt factureren")
    app.get_by_role("link", name="Eerste klant toevoegen").click()
    expect(app).to_have_url(re.compile(r"/contacten/nieuw/$"))
    settings = Settings.load()
    assert (settings.business_name, settings.kor_enabled) == ("Atelier Zonnig", True)


def test_connecting_an_ai_assistant_and_copying_the_key(app, browser_name):
    # SPEC.md M16: Koppelen makes the key; Kopiëren puts it on the clipboard;
    # the first request with it makes the card say "Gekoppeld".
    from huismus.assistants import key

    app.goto(f"{app.base}/instellingen/")
    app.get_by_role("link", name="AI-assistenten").click()
    expect(app.locator("#adres-en-sleutel .pill")).to_have_text("Niet gekoppeld")
    app.get_by_role("button", name="Koppelen").click()

    expect(app.locator("#adres-en-sleutel .pill")).to_have_text("Wacht op verbinding")
    secret = key.current()
    # Hidden until "Toon" (besluit 2026-11-02); Kopiëren works without it.
    field = app.get_by_label("Sleutel", exact=True)
    expect(field).to_have_value(secret)
    expect(field).to_have_attribute("type", "password")
    app.get_by_role("button", name="Toon").click()
    expect(field).to_have_attribute("type", "text")
    app.get_by_role("button", name="Verberg").click()
    expect(field).to_have_attribute("type", "password")
    expect(app.get_by_label("Adres", exact=True)).to_have_value(f"{app.base}/mcp")
    if browser_name == "chromium":
        app.context.grant_permissions(["clipboard-read", "clipboard-write"])
        app.locator("[data-copy=sleutel]").click()
        expect(app.locator("[data-copy=sleutel]")).to_have_text("Gekopieerd")
        assert app.evaluate("navigator.clipboard.readText()") == secret

    answer = app.request.post(
        f"{app.base}/mcp",
        data={"jsonrpc": "2.0", "id": 1, "method": "ping"},
        headers={"Authorization": f"Bearer {secret}"},
    )
    assert answer.json() == {"jsonrpc": "2.0", "id": 1, "result": {}}
    app.reload()
    expect(app.locator("#adres-en-sleutel .pill")).to_have_text("Gekoppeld")

    # A new key asks first, then locks the old one out.
    app.get_by_role("button", name="Nieuwe sleutel").click()
    app.get_by_role("dialog").get_by_role("button", name="Nieuwe sleutel").click()
    expect(app.get_by_text("Nieuwe sleutel gemaakt. De oude werkt niet meer.")).to_be_visible()
    assert key.current() not in ("", secret)
    expect(app.locator("#adres-en-sleutel .pill")).to_have_text("Wacht op verbinding")

    app.get_by_role("button", name="Ontkoppelen").click()
    app.get_by_role("dialog").get_by_role("button", name="Ontkoppelen").click()
    expect(app.locator("#adres-en-sleutel .pill")).to_have_text("Niet gekoppeld")
    assert key.current() == ""


def test_on_a_phone_the_order_field_of_a_category_is_labelled_in_english(app):
    """The label used to come from huismus.css, which gettext never sees
    (BUGS-BY-HAND.md, 2026-10-30)."""
    from huismus.expenses.models import ExpenseCategory

    category = ExpenseCategory.objects.create(name="Reiskosten", sort_order=3)
    app.set_viewport_size({"width": 390, "height": 844})
    app.context.add_cookies([{"name": "django_language", "value": "en", "url": app.base}])
    app.goto(app.base + f"/uitgaven/categorieen/?bewerk={category.pk}")
    cell = app.locator("tr.is-editing td[data-cell=order]")
    label = cell.get_by_text("Order", exact=True)
    expect(label).to_be_visible()
    # An sr-only label is 1px wide; text from ::before is not in the DOM.
    assert label.bounding_box()["width"] > 20
    assert cell.evaluate("td => getComputedStyle(td, '::before').content") in ("none", "normal")


def test_an_expense_gets_a_second_line_in_another_category(app):
    """Regel toevoegen adds a line on the spot, each line has its own
    category, and the expense's total is the sum (huismus-intern/besluiten.md,
    2026-11-02)."""
    from huismus.expenses.models import Expense, ExpenseCategory

    ExpenseCategory.objects.create(name="Software", sort_order=0)
    ExpenseCategory.objects.create(name="Reiskosten", sort_order=1)
    app.goto(app.base + "/uitgaven/nieuw/")
    app.get_by_label("Datum").fill("2026-03-01")
    app.get_by_label("Leverancier").fill("Hosting BV")
    app.locator("[name=lines-0-amount_cents]").fill("12,10")
    app.locator("[name=lines-0-category]").select_option(label="Software")

    app.get_by_role("button", name="Regel toevoegen").click()
    app.locator("[name=lines-1-description]").fill("Trein naar klant")
    app.locator("[name=lines-1-amount_cents]").fill("8,00")
    app.locator("[name=lines-1-category]").select_option(label="Reiskosten")
    app.get_by_role("button", name="Opslaan").click()

    expect(app.get_by_text("Uitgave opgeslagen.")).to_be_visible()
    expect(app.get_by_text("€ 20,10")).to_be_visible()
    expense = Expense.objects.get()
    assert expense.amount_cents == 2010
    assert sorted(line.category.name for line in expense.lines.all()) == ["Reiskosten", "Software"]


def test_a_new_expense_gets_its_receipt_in_one_go(app, tmp_path):
    """The receipt is chosen in the form for a new expense, not only after
    saving it: the page shows the file's name, and Opslaan saves both."""
    from io import BytesIO

    from PIL import Image

    from huismus.expenses.models import Expense

    buffer = BytesIO()
    Image.new("RGB", (4, 4), color="red").save(buffer, format="PNG")
    receipt = tmp_path / "bon-hosting.png"
    receipt.write_bytes(buffer.getvalue())

    app.goto(app.base + "/uitgaven/nieuw/")
    app.get_by_label("Datum").fill("2026-03-01")
    app.get_by_label("Leverancier").fill("Hosting BV")
    app.locator("[name=lines-0-amount_cents]").fill("12,10")
    app.set_input_files("input[name=receipt-file]", str(receipt))
    expect(app.get_by_text("bon-hosting.png")).to_be_visible()
    app.get_by_role("button", name="Opslaan").click()

    expect(app.get_by_text("Uitgave opgeslagen.")).to_be_visible()
    expect(app.locator(".receipt .r-name")).to_have_text("bon-hosting.png")
    assert Expense.objects.get().attachments.count() == 1
