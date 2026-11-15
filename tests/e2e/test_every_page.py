# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Visit every page on a real-size administration, in both languages and at
three widths, and fail on whole classes of UI bugs at once.

Many bugs found by clicking around were not about one page but a kind of
mistake that can happen on any page: template syntax on screen, Dutch left
in the English UI, a page that scrolls sideways on a phone, a menu item
shown twice, a button that a phone hides without another way to reach it, a tab cut off,
a JavaScript error. A check per class keeps catching them on
every page, including pages added later: add new pages to `_pages()`.
See BUGS-BY-HAND.md.

JavaScript errors are caught by the `app` fixture (conftest.py).
"""

import re
from collections import Counter
from pathlib import Path

import pytest

from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core import help
from huismus.core.models import Attachment
from huismus.documents.models import Document
from huismus.expenses.models import Expense, ExpenseCategory

pytestmark = pytest.mark.django_db(transaction=True)

WIDTHS = [390, 1024, 1440]

# Text that never belongs on screen: template syntax and leaked values.
NEVER_VISIBLE = ["{{", "}}", "{%", "%}", "{#", "#}", "None", "undefined", "NaN", "[object Object]"]

ENGLISH_CATALOG = (
    Path(__file__).resolve().parents[2] / "huismus" / "locale" / "en" / "LC_MESSAGES" / "django.po"
)


def _first(queryset, what):
    """The first object, or a clear failure if the demo history has none."""
    found = queryset.order_by("pk").first()
    assert found is not None, f"huismus/core/demo_history.py has no {what}; this test needs one"
    return found


def _pages():
    """Every HTML page, with real objects from the history fixture."""
    documents = Document.objects.all()
    issued = _first(documents.filter(kind="invoice", status="issued"), "invoice")
    sent_quote = _first(documents.filter(kind="quote", status="sent"), "quote")
    pages = [
        "/",
        "/facturen/",
        "/facturen/nieuw/",
        f"/facturen/{_first(documents.filter(kind='invoice', status='draft'), 'draft').pk}/",
        f"/facturen/{issued.pk}/",
        f"/facturen/{issued.pk}/mailen/",
        f"/facturen/{issued.pk}/pdf/bekijken/",
        f"/offertes/{_first(documents.filter(kind='quote', status='sent'), 'quote').pk}/mailen/",
        f"/offertes/{sent_quote.pk}/pdf/bekijken/",
        "/offertes/",
        "/offertes/nieuw/",
        "/contacten/",
        "/contacten/nieuw/",
        f"/contacten/{_first(Contact.objects, 'contact').pk}/",
        "/uitgaven/",
        "/uitgaven/nieuw/",
        # Receipts without an expense (SPEC.md M20); with receipts and
        # "Uitgave maken": tests/e2e/test_receipts_folder.py.
        "/uitgaven/bonnetjes/",
        f"/uitgaven/{_first(Expense.objects, 'expense').pk}/",
        # "Nakijken" (SPEC.md M20 part 2b): the filter, and an expense with
        # the notice and "Klopt"; the flow: tests/e2e/test_to_check.py.
        "/uitgaven/?nakijken=1",
        f"/uitgaven/{_first(Expense.objects.filter(needs_review=True), 'expense to check').pk}/",
        # Verwerken (huismus/expenses/process_views.py): an expense with a
        # photo, one with a PDF, and a receipt from the tray with a reason
        # (huismus/core/demo_receipts.py); the flow: tests/e2e/test_process.py.
        *(
            f"/uitgaven/verwerken/uitgave/{expense.pk}/"
            for expense in Expense.objects.filter(needs_review=True)
        ),
        *(
            f"/uitgaven/verwerken/bonnetje/{receipt.pk}/"
            for receipt in Attachment.objects.in_tray()
        ),
        "/rapporten/jaaroverzicht/",
        # The VAT return (SPEC.md M21, part 4): a year of the history, with
        # imports and lines without a rate under "Niet meegeteld".
        "/rapporten/btw-aangifte/",
        "/rapporten/btw-aangifte/?periode=2025",
        "/uitgaven/categorieen/",
        f"/uitgaven/categorieen/?bewerk={_first(ExpenseCategory.objects, 'category').pk}",
        f"/uitgaven/categorieen/{_first(ExpenseCategory.objects, 'category').pk}/",
        "/importeren/",
        "/instellingen/",
        "/instellingen/bedrijf/",
        "/instellingen/kor/",
        "/instellingen/facturen/",
        "/instellingen/huisstijl/",
        "/instellingen/mailen/",
        # On Docker too (SPEC.md M15); with a linked folder and a backup:
        # test_the_backup_and_update_pages_on_docker_have_no_known_kind_of_ui_bug.
        "/instellingen/back-ups/",
        "/instellingen/back-ups/map/",
        "/instellingen/back-ups/terugzetten/",
        "/instellingen/back-ups/dropbox/",
        "/instellingen/back-ups/webdav/",
        "/instellingen/exporteren/",
        "/instellingen/bonnetjesmap/",
        "/instellingen/bonnetjes-lezen/",
        # Not connected here; connected, with the key: the desktop test below.
        "/instellingen/ai-assistenten/",
        # Docker's, without a new version; with one: the Docker test below.
        "/instellingen/updates/",
        "/instellingen/weergave/",
        "/welkom/bedrijf/",
        "/welkom/kor/",
        "/welkom/facturen/",
        "/welkom/logo/",
        "/welkom/klaar/",
        # Only with the sample data; with it (and the welcome card without
        # it): tests/e2e/test_sample_data.py.
        "/nepdata/leegmaken/",
        "/hulp/",
        *(f"/hulp/{slug}/" for slug in help.TOPICS),
    ]
    # A quote in every status: each one shows different actions.
    quotes = documents.filter(kind="quote")
    # order_by(): without it the default ordering joins the DISTINCT and
    # every quote's status comes back once per quote.
    for status in quotes.order_by().values_list("status", flat=True).distinct():
        pages.append(f"/offertes/{_first(quotes.filter(status=status), 'quote').pk}/")
    return pages


def _dutch_ui_texts():
    """The Dutch source texts that have a different English translation.
    On an English page none of them may be visible.

    Read line by line, so only texts on one line count: a multi-line msgid
    (`msgid ""` followed by continuation lines) and texts with placeholders
    or HTML are skipped. That covers the short UI texts this is about
    (labels, buttons, headings) without a .po parser as a dependency.
    Single words shorter than 8 letters are skipped too: words like "Datum"
    also occur in the Dutch demo data."""
    texts = []
    msgid = None
    fuzzy = False
    for line in ENGLISH_CATALOG.read_text(encoding="utf-8").splitlines():
        # A fuzzy translation isn't compiled: that Dutch rightly shows.
        if line.startswith("#,"):
            fuzzy = "fuzzy" in line
        elif line.startswith('msgid "'):
            msgid = None if fuzzy else line[7:-1]
            fuzzy = False
        elif line.startswith('msgstr "') and msgid:
            msgstr = line[8:-1]
            usable = msgstr and msgstr != msgid and not re.search(r"[%{<\\]", msgid)
            if usable and (" " in msgid or len(msgid) >= 8):
                texts.append(msgid)
            msgid = None
    return texts


def _data_texts():
    """Dutch text that comes from the administration itself, not the UI."""
    business = Settings.load()
    texts = [business.business_name, business.kor_text, business.default_footer_text]
    texts += Contact.objects.values_list("company_name", flat=True)
    texts += ExpenseCategory.objects.values_list("name", flat=True)
    texts += Expense.objects.values_list("description", flat=True)
    texts += Document.objects.values_list("lines__description", flat=True)
    # Never a snippet the page must not show: a description "None" would
    # otherwise hide a leaked None everywhere.
    return [text for text in texts if text and text not in NEVER_VISIBLE]


# A placeholder wider than its field is cut off without anything
# scrolling: the search field on Contacten on a phone, 2026-10-30. The
# text is measured in a hidden span beside the field, in the field's font.
# The room is the field's outer width less its borders and padding:
# clientWidth of an input already leaves out the padding in Firefox, not in
# Chromium and WebKit (CI, 2026-10-30: 274 px in Firefox, 322 px in both).
CUT_OFF_PLACEHOLDERS = """() => [...document.querySelectorAll('input[placeholder]')]
    .filter(el => {
        if (!el.placeholder || el.value || !el.checkVisibility()) return false;
        // A placeholder made transparent (next to a column head) can't be cut off.
        if (getComputedStyle(el, '::placeholder').color === 'rgba(0, 0, 0, 0)') return false;
        const style = getComputedStyle(el);
        const text = document.createElement('span');
        text.textContent = el.placeholder;
        for (const name of ['fontStyle', 'fontWeight', 'fontSize', 'fontFamily',
                            'letterSpacing']) {
            text.style[name] = style[name];
        }
        text.style.cssText += 'position:absolute;visibility:hidden;white-space:pre';
        el.after(text);
        const width = text.getBoundingClientRect().width;
        text.remove();
        const room = el.getBoundingClientRect().width
            - parseFloat(style.borderLeftWidth) - parseFloat(style.borderRightWidth)
            - parseFloat(style.paddingLeft) - parseFloat(style.paddingRight);
        return width > room + 1;
    })
    .map(el => el.placeholder)"""


# An empty field with no border, no background of its own and no placeholder
# is invisible: you can't see where to click (the quantity and unit of an
# invoice line, feedback 2026-11-06). Every field you can type in shows itself.
INVISIBLE_FIELDS = """() => [...document.querySelectorAll(
        'main :is(textarea, select, '
        + 'input:not([type=hidden], [type=checkbox], [type=radio], [type=file]))'
    )].filter(el => {
        if (el.value || el.placeholder || el.readOnly || el.disabled) return false;
        if (!el.checkVisibility() || el.closest('.sr-only')) return false;
        const style = getComputedStyle(el);
        const none = color => color === 'transparent' || color === 'rgba(0, 0, 0, 0)';
        const border = ['Top', 'Right', 'Bottom', 'Left'].some(side =>
            parseFloat(style[`border${side}Width`]) > 0 && !none(style[`border${side}Color`]));
        return !border && none(style.backgroundColor);
    })
    .map(el => el.name || el.outerHTML.slice(0, 60))"""


# A tab row that scrolls sideways with a hidden scrollbar cuts the last tab
# off ("Cr…" on Facturen at a medium width) without anything showing that
# there is more: nothing scrolls the page, so the check on that sees nothing
# (feedback 2026-10-31). Every tab must be wholly inside its row, and the row
# inside the window: the row breaks onto a next line instead.
CUT_OFF_TABS = """() => [...document.querySelectorAll('.tab')]
    .filter(el => {
        if (!el.checkVisibility()) return false;
        const box = el.getBoundingClientRect();
        const row = (el.closest('.tabs') || document.documentElement).getBoundingClientRect();
        const right = Math.min(row.right, document.documentElement.clientWidth);
        // 1px slack: positions are fractions and round differently.
        return box.left < Math.max(row.left, 0) - 1 || box.right > right + 1;
    })
    .map(el => el.innerText.trim())"""


def _problems_on(page, path, language, dutch, data):
    problems = []
    response = page.goto(page.base + path)
    if response.status != 200:
        problems.append(f"HTTP {response.status}")
    page.wait_for_load_state("networkidle")
    lang = page.locator("html").get_attribute("lang")
    if lang != language:
        problems.append(f"lang={lang!r}, verwacht {language!r}")
    # Text from the administration itself (names, descriptions) may contain
    # anything; only what the templates add is checked.
    text = page.locator("body").inner_text()
    for snippet in data:
        text = text.replace(snippet, "")
    # Code in the help pages is typed as is ({vervaldatum} in an English
    # mail text too), not a UI text.
    for snippet in page.locator(".help-text code").all_inner_texts():
        text = text.replace(snippet, "")
    for snippet in NEVER_VISIBLE:
        if re.search(rf"(?<!\w){re.escape(snippet)}(?!\w)", text):
            problems.append(f"zichtbaar: {snippet!r}")
    if dutch:
        for snippet in dutch:
            if re.search(rf"(?<!\w){re.escape(snippet)}(?!\w)", text):
                problems.append(f"Nederlands op de Engelse pagina: {snippet!r}")
    menu = Counter(label.strip() for label in page.locator(".sidebar .nav > a").all_inner_texts())
    doubles = sorted(label for label, times in menu.items() if times > 1)
    if doubles:
        problems.append(f"dubbel in het menu: {doubles}")
    overflow = page.evaluate(
        "document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    if overflow > 1:
        problems.append(f"scrolt {overflow}px opzij")
    # A button wider than its cell doesn't scroll the page: it sticks into the
    # next cell, or only shows by luck in the row's padding (w-min in the
    # stacked view, 2026-10-30).
    sticking_out = page.evaluate(
        """() => [...document.querySelectorAll(
            '.table td :is(.btn, .input, .pill, select, textarea)'
        )].filter(el => {
            const cell = el.closest('td').getBoundingClientRect();
            const box = el.getBoundingClientRect();
            // 1px slack: positions are fractions and round differently.
            return box.width > 0 && (box.left < cell.left - 1 || box.right > cell.right + 1);
        }).map(el => el.outerHTML.slice(0, 60))"""
    )
    if sticking_out:
        problems.append(f"steekt buiten de tabelcel: {sorted(set(sticking_out))}")
    # A table wider than its card was cut off by overflow: hidden: on the year
    # overview "Winst" and "Voorbelasting" were gone at 390px (2026-11-07).
    # It must be in a .table-wrap that scrolls.
    clipped = page.evaluate(
        """() => [...document.querySelectorAll('.table-wrap')].filter(wrap => {
            const table = wrap.querySelector('.table');
            return table && getComputedStyle(wrap).overflowX === 'hidden'
                && table.scrollWidth > wrap.clientWidth + 1;
        }).map(wrap => wrap.textContent.trim().slice(0, 40))"""
    )
    if clipped:
        problems.append(f"tabel rechts afgeknipt: {clipped}")
    # The footer promised "/ zoeken" on every page, where "/" did nothing
    # (feedback 2026-10-31): a shortcut hint only where the shortcut works.
    hints_search = page.locator(".shortcut-hint .kbd", has_text="/").count() > 0
    has_search = page.locator("main input[type=search]").count() > 0
    if hints_search != has_search:
        problems.append(f"sneltoets-hint '/' {hints_search}, zoekveld {has_search}")
    cut_off = page.evaluate(CUT_OFF_PLACEHOLDERS)
    if cut_off:
        problems.append(f"placeholder afgeknipt: {sorted(set(cut_off))}")
    invisible = page.evaluate(INVISIBLE_FIELDS)
    if invisible:
        problems.append(
            f"leeg veld zonder rand, achtergrond of placeholder: {sorted(set(invisible))}"
        )
    cut_off_tabs = page.evaluate(CUT_OFF_TABS)
    if cut_off_tabs:
        problems.append(f"tab afgeknipt: {sorted(set(cut_off_tabs))}")
    return problems


def test_the_placeholder_check_reports_a_cut_off_text_and_only_that(page):
    text = "Zoek op naam, klantnummer of plaats"
    font = "font: 13px sans-serif"
    page.set_content(f'<span style="{font}; white-space: pre">{text}</span>')
    width = page.locator("span").bounding_box()["width"]
    # Padding and a border as on .input-sm, and just enough room for the
    # text: Firefox leaves the padding out of an input's clientWidth, which
    # once made the check count it twice (2026-10-30).
    field = f"{font}; box-sizing: border-box; padding: 0 10px 0 38px; border: 1px solid"
    outside = 38 + 10 + 2  # padding left and right, two borders
    page.set_content(
        # Fits with 2 px to spare, and 10 px too narrow.
        f'<input style="{field}; width: {width + outside + 2}px" placeholder="{text}">'
        # A space more, to tell the two apart in the result.
        f'<input style="{field}; width: {width + outside - 10}px" placeholder="{text} ">'
    )
    assert page.evaluate(CUT_OFF_PLACEHOLDERS) == [f"{text} "]


def test_the_field_check_reports_an_empty_field_you_cannot_see_and_only_that(page):
    quiet = "border: 1px solid transparent; background: transparent"
    page.set_content(
        "<main>"
        f'<input name="invisible" style="{quiet}">'
        f'<input name="placeholder" style="{quiet}" placeholder="Aantal">'
        f'<input name="filled" style="{quiet}" value="2">'
        '<input name="border" style="border: 1px solid #ccc; background: transparent">'
        f'<textarea name="quiet-textarea" style="{quiet}"></textarea>'
        "</main>"
    )
    assert sorted(page.evaluate(INVISIBLE_FIELDS)) == ["invisible", "quiet-textarea"]


def test_the_tab_check_reports_a_row_that_cuts_tabs_off_and_not_one_that_breaks(page):
    tabs = '<a class="tab">Alle</a><a class="tab">Concepten</a><a class="tab">Creditnota\'s</a>'
    style = "<style>.tab { white-space: nowrap; padding: 0 20px; font: 16px sans-serif }</style>"
    row = "display: flex; width: 200px"
    # Scrolling sideways with a hidden scrollbar, as .tabs once did.
    page.set_content(f'{style}<nav class="tabs" style="{row}; overflow-x: auto">{tabs}</nav>')
    assert page.evaluate(CUT_OFF_TABS) != []
    # The same tabs breaking onto a next line, as .tabs does now.
    page.set_content(f'{style}<nav class="tabs" style="{row}; flex-wrap: wrap">{tabs}</nav>')
    assert page.evaluate(CUT_OFF_TABS) == []


@pytest.mark.parametrize("width", WIDTHS)
def test_every_page_in_both_languages_has_no_known_kind_of_ui_bug(app, history, width):
    app.set_viewport_size({"width": width, "height": 800})
    pages = _pages()
    dutch = _dutch_ui_texts()
    data = sorted(_data_texts(), key=len, reverse=True)
    found = []
    for language in ["nl", "en"]:
        app.context.add_cookies([{"name": "django_language", "value": language, "url": app.base}])
        for path in pages:
            check = dutch if language == "en" else []
            for problem in _problems_on(app, path, language, check, data):
                found.append(f"{language} {path} @ {width}px — {problem}")
    assert found == [], "\n".join(found)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_backup_and_update_pages_on_docker_have_no_known_kind_of_ui_bug(
    app, history, width, settings, tmp_path, monkeypatch
):
    from huismus.core import auto_backups, updates

    # A folder linked in and a backup in it (SPEC.md M15), so all shows.
    settings.DESKTOP = False
    linked = tmp_path / "backups"
    linked.mkdir()
    monkeypatch.setattr(auto_backups, "LINKED_FOLDER", linked)
    monkeypatch.setattr(auto_backups, "MOUNTINFO", tmp_path / "geen-proc")
    auto_backups.choose_folder(linked)
    auto_backups.make_backup()
    # A newer version with another X.Y, so the notice and the longest
    # instructions on Updates show (core.update_views._docker).
    updates.update_status(
        available={
            "version": "99.0.0",
            "page_url": "https://github.com/codebyarne/huismus/releases/tag/v99.0.0",
            "asset_url": "",
            "asset_name": "",
            "sha256": "",
        }
    )
    app.set_viewport_size({"width": width, "height": 800})
    dutch = _dutch_ui_texts()
    data = sorted([*_data_texts(), str(tmp_path)], key=len, reverse=True)
    found = []
    for language in ["nl", "en"]:
        app.context.add_cookies([{"name": "django_language", "value": language, "url": app.base}])
        for path in [
            "/",
            "/instellingen/",
            "/instellingen/back-ups/",
            "/instellingen/back-ups/map/",
            "/instellingen/back-ups/terugzetten/",
            "/instellingen/updates/",
        ]:
            check = dutch if language == "en" else []
            for problem in _problems_on(app, path, language, check, data):
                found.append(f"{language} {path} @ {width}px — {problem}")
    assert found == [], "\n".join(found)


@pytest.mark.parametrize("width", WIDTHS)
def test_the_backup_pages_with_a_cloud_have_no_known_kind_of_ui_bug(
    app, history, width, monkeypatch
):
    from huismus.core import cloud_backups
    from tests.cloud_fakes import ADDRESS, PASSWORD, USERNAME, FakeWebDAV

    # WebDAV linked, the code saved and a backup there (SPEC.md M15 step 2).
    dav = FakeWebDAV()
    dav.install(monkeypatch)
    cloud_backups.link_webdav(ADDRESS, USERNAME, PASSWORD)
    cloud_backups.new_code()
    cloud_backups.confirm_code()
    cloud_backups.upload_backup()
    app.set_viewport_size({"width": width, "height": 800})
    dutch = _dutch_ui_texts()
    data = sorted([*_data_texts(), ADDRESS.rstrip("/")], key=len, reverse=True)
    found = []
    try:
        for language in ["nl", "en"]:
            app.context.add_cookies(
                [{"name": "django_language", "value": language, "url": app.base}]
            )
            for path in [
                "/instellingen/back-ups/",
                "/instellingen/back-ups/herstelcode/",
                "/instellingen/back-ups/terugzetten/",
                "/instellingen/back-ups/webdav/",
                "/instellingen/back-ups/webdav/?opnieuw",
            ]:
                check = dutch if language == "en" else []
                for problem in _problems_on(app, path, language, check, data):
                    found.append(f"{language} {path} @ {width}px — {problem}")
    finally:
        dav.close()
    assert found == [], "\n".join(found)


# Pages only the desktop app has (SPEC.md M11), and the ones that change
# there. With a backup folder, one backup and a newer version, so all show.
DESKTOP_PAGES = [
    "/",
    "/instellingen/",
    "/instellingen/back-ups/",
    "/instellingen/back-ups/map/",
    "/instellingen/back-ups/terugzetten/",
    "/instellingen/updates/",
    "/instellingen/updates/bijwerken/",
    "/instellingen/wachtwoord/",
    "/instellingen/ai-assistenten/",
]


@pytest.mark.parametrize("width", WIDTHS)
def test_the_desktop_app_s_pages_have_no_known_kind_of_ui_bug(
    app, history, width, settings, tmp_path, monkeypatch
):
    from huismus.assistants import key
    from huismus.core import auto_backups, updates

    # Connected, so the address and the full key show (SPEC.md M16).
    key.create()
    settings.DESKTOP = True
    settings.WINDOW_TOKEN = "window-token"
    app.context.add_cookies([{"name": "huismus_window", "value": "window-token", "url": app.base}])
    # Sync folders with paths as long as real ones: a long path must wrap,
    # not push the page sideways on a phone (found by verify-e2e).
    home = tmp_path / "Users" / "janedoewithaverylongname"
    icloud = home / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    icloud.mkdir(parents=True)
    (
        home
        / "Library"
        / "CloudStorage"
        / "GoogleDrive-jane.doe.with.a.long.name@example.org"
        / "My Drive"
    ).mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    auto_backups.choose_folder(icloud)
    auto_backups.make_backup()
    # A newer version found, so the update pages show it.
    updates.update_status(
        available={
            "version": "99.0.0",
            "page_url": "https://github.com/codebyarne/huismus/releases/tag/v99.0.0",
            "asset_url": "https://example.invalid/Huismus-99.0.0-macos.dmg",
            "asset_name": "Huismus-99.0.0-macos.dmg",
            "sha256": "ab" * 32,
        }
    )
    app.set_viewport_size({"width": width, "height": 800})
    dutch = _dutch_ui_texts()
    # The paths are this computer's, not text of the app.
    data = sorted([*_data_texts(), str(tmp_path)], key=len, reverse=True)
    found = []
    for language in ["nl", "en"]:
        app.context.add_cookies([{"name": "django_language", "value": language, "url": app.base}])
        for path in DESKTOP_PAGES:
            check = dutch if language == "en" else []
            for problem in _problems_on(app, path, language, check, data):
                found.append(f"{language} {path} @ {width}px — {problem}")
    assert found == [], "\n".join(found)


# The actions on a page (buttons and links) outside the navigation, which
# differs per width on purpose (sidebar vs. tab bar) and has its own test in
# test_walkthrough.py. An action counts as reachable when it is visible, or
# sits in a closed popover menu whose opening button is visible; that the
# menu then shows it is test_browser.py's job (test_on_a_phone_...).
ACTIONS_JS = """
() => {
  const nav = ".sidebar, .tabbar, .mtop, #plus-menu, #meer-menu";
  const visible = (el) => el.checkVisibility();
  const reachable = (el) => {
    if (visible(el)) return true;
    const menu = el.closest("[popover]");
    if (!menu || menu.matches(":popover-open")) return false;
    return [...document.querySelectorAll(`[popovertarget="${menu.id}"]`)].some(visible);
  };
  const out = [];
  for (const el of document.querySelectorAll("a[href], button")) {
    if (el.closest(nav) || el.closest("dialog") || el.hasAttribute("popovertarget")) continue;
    const name = (el.getAttribute("aria-label") || el.innerText || "").trim();
    const where = el.getAttribute("href") || el.getAttribute("formaction") || "";
    out.push({key: `${name} ${where}`.trim(), visible: visible(el), reachable: reachable(el)});
  }
  return out;
}
"""


def test_every_action_on_a_wide_screen_can_be_reached_on_a_narrow_one(app, history):
    """A narrow screen may move an action into a menu, never drop it."""
    found = []
    for path in _pages():
        app.set_viewport_size({"width": WIDTHS[-1], "height": 800})
        app.goto(app.base + path)
        wide = {a["key"] for a in app.evaluate(ACTIONS_JS) if a["visible"]}
        for width in WIDTHS[:-1]:
            app.set_viewport_size({"width": width, "height": 800})
            reachable = {a["key"] for a in app.evaluate(ACTIONS_JS) if a["reachable"]}
            for key in sorted(wide - reachable):
                found.append(f"{path} @ {width}px — onbereikbaar: {key!r}")
    assert found == [], "\n".join(found)


# Everything in the sidebar (its links, the "Nieuw" menu, the language
# switch, logging out), keyed by where it goes; and whether the same key is
# reachable in the phone's navigation (top bar, tab bar, its + and "Meer" menus).
NAVIGATION_JS = """
() => {
  const visible = (el) => el.checkVisibility();
  const reachable = (el) => {
    if (visible(el)) return true;
    const menu = el.closest("[popover]");
    if (!menu || menu.matches(":popover-open")) return false;
    return [...document.querySelectorAll(`[popovertarget="${menu.id}"]`)].some(visible);
  };
  // Where it goes: a link's href, a button's form action (plus its
  // name=value). Two nameless buttons posting to one URL would look alike.
  const key = (el) => {
    if (el.matches("a")) return el.getAttribute("href");
    const form = el.closest("form");
    const value = el.name ? ` ${el.name}=${el.value}` : "";
    return `${form ? form.getAttribute("action") : ""}${value}`;
  };
  const actions = (scope) => [...document.querySelectorAll(scope)].flatMap((root) =>
    [...root.querySelectorAll("a[href], button")].filter((el) => !el.hasAttribute("popovertarget"))
  );
  const phoneNav = ".mtop, .tabbar, #plus-menu, #meer-menu";
  const phone = new Set(actions(phoneNav).filter(reachable).map(key));
  return actions(".sidebar")
    .filter((el) => !phone.has(key(el)))
    .map((el) => `${(el.innerText || "").trim()} ${key(el)}`);
}
"""


def test_everything_in_the_sidebar_can_be_reached_on_a_phone(app, history):
    """The phone has no sidebar: its top bar, tab bar and its + and "Meer"
    menus must offer everything the sidebar does."""
    app.set_viewport_size({"width": WIDTHS[0], "height": 800})
    found = []
    for path in _pages():
        app.goto(app.base + path)
        for missing in app.evaluate(NAVIGATION_JS):
            found.append(f"{path} @ {WIDTHS[0]}px — niet op de telefoon: {missing!r}")
    assert found == [], "\n".join(found)
