# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Write the files of the Huismus Design System in Claude (docs/design/README.md).

Everything comes from the repo: tokens from huismus/core/static/core/huismus.css,
icons from huismus/templates/icons.svg, component previews from the sections of
docs/design/componenten.html. Nothing here is designed by hand, so the
Design System in Claude stays a copy of the component page (huismus-intern/besluiten.md,
2026-10-30). Run it again after huismus.css changes, then publish the folder
as docs/design/README.md describes.

    uv run python scripts/design_system_export.py <folder> [commit]

The folder gets project/... (the files the Design System type reads) and
upload/... (logo and icons as standalone SVG files, to upload as assets).
"""

import json
import re
import shutil
import sys
from pathlib import Path
from typing import NamedTuple

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "huismus" / "core" / "static" / "core" / "huismus.css"
ICONS = ROOT / "huismus" / "templates" / "icons.svg"
PAGE = ROOT / "docs" / "design" / "componenten.html"
DOMAIN_RULES = ROOT / "docs" / "design" / "README.md"

# Section id on the component page -> component name, group and what it is for.
COMPONENTS = {
    "knoppen": (
        "Button",
        "Acties",
        "Knoppen: primair (blauw) voor de ene hoofdactie, secundair (wit) en ghost "
        "(kaal) voor de rest, danger (rood) alleen voor verwijderen.\n\n"
        "- Eén primaire knop per scherm of dialoog.\n"
        "- Abrikoos is nooit een knop.\n"
        "- Laadtoestand: HTMX zet `.htmx-request` op de knop; het label verdwijnt "
        "en de spinner verschijnt, de breedte blijft gelijk.\n"
        "- Klassen: `.btn` plus `.btn-primary`, `.btn-secondary`, `.btn-ghost`, "
        "`.btn-danger`, `.btn-danger-quiet`; maten `.btn-sm`, `.btn-lg`, "
        "`.btn-icon`, `.btn-block`.",
    ),
    "labels": (
        "StatusLabel",
        "Status",
        "Statuslabels (`.pill`): een vlak alleen als er iets moet gebeuren.\n\n"
        "- Vol vlak: Vervallen (rood), Onbetaald en Deels betaald (amber), "
        "Verzonden (blauw), Concept (grijs), Geïmporteerd (abrikoos).\n"
        "- Rustig, zonder vlak: Definitief (slotje), Betaald en Geaccepteerd "
        "(groene stip), Afgewezen (rode stip), Verlopen (open stip).\n"
        "- Rand zonder kleur: Creditnota, Gecrediteerd.\n"
        "- De tabel in de preview zegt per label wanneer je hem gebruikt.",
    ),
    "meldingen": (
        "Notice",
        "Status",
        "Meldingen. Op het overzicht een rustige kaart (`.hint-banner`) met een "
        "gekleurde streep en een gekleurd icoon; alleen de link rechts in de "
        "statuskleur.\n\n"
        "- `.is-bad` (rood): over de KOR-grens, iets is mislukt.\n"
        "- `.is-warn` (amber): let op.\n"
        "- `.is-info` (blauw): informatie, zoals een nieuwe versie.\n"
        "- Zonder klasse (abrikoos): een herinnering, zoals een open concept.\n"
        "- Na een actie: `.flash` bovenaan de pagina of `.toast` rechtsboven; "
        "foutmeldingen blijven staan.",
    ),
    "velden": (
        "FormField",
        "Formulieren",
        "Formuliervelden. Elk veld heeft een `<label>`; een fout staat onder het "
        "veld met `aria-invalid` en `aria-describedby`.\n\n"
        "- Bedragen in `.money` (euroteken links, cijfers rechts uitgelijnd).\n"
        "- Btw-tarieven als `.seg`, aan/uit als `.switch`.\n"
        "- Elk formulier werkt ook zonder JavaScript.",
    ),
    "tabellen": (
        "Table",
        "Inhoud",
        "Lijsten en cijfers. Tabellen met `.stackable` worden op een telefoon "
        "kaarten; elke cel krijgt `data-cell`.\n\n"
        "- Concepten tonen `Concept` in plaats van een nummer.\n"
        "- Bedragen rechts, met tabulaire cijfers.\n"
        "- De blauwe KPI-kaart (`.kpi-hero`) is er één per scherm: openstaand.",
    ),
    "leeg": (
        "EmptyState",
        "Inhoud",
        "Lege toestand: de mus, één zin wat hier komt, en de actie om te beginnen.",
    ),
    "dialoog": (
        "Dialog",
        "Acties",
        "Dialoog voor iets wat niet terug kan. De titel is de vraag, de knop "
        'zegt wat er gebeurt ("Verwijderen", niet "OK"). Annuleren links.',
    ),
    "voortgang": (
        "Progress",
        "Status",
        "Stappen (`.steps`), voortgangsbalken (`.progress`), vervalhints "
        "(`.due-hint`), verwijzingen tussen documenten (`.doc-ref`) en tellers "
        "(`.stat-chip`).",
    ),
    "document": (
        "Paper",
        "Inhoud",
        "Het document als vel papier. Uitgegeven: `.paper-final` met het stempel "
        "en het slotje, zonder invoervelden. De KOR-tekst onder de factuur is de "
        "tekst die de gebruiker in Instellingen zet.",
    ),
}

# The cover above the brand book (the Design System type wants one): the palette as
# blocks and one pattern, the name on the ground. 960 x 288, no responsive layout.
# The comment above the SVG is the "derivation" the type asks every cover to keep:
# which tokens the blocks, the pattern and the sizes come from.
COVER = """<!-- @dsCard height=288 -->
<style>
  .cover { position: relative; width: 960px; height: 288px; overflow: hidden;
    background: var(--bg); }
  .cover svg { position: absolute; inset: 0; }
  .sky { fill: var(--primary); } .apricot { fill: var(--accent); }
  .ink { fill: var(--text); } .soft { fill: var(--primary-soft); }
  .seed { fill: var(--accent-soft); }
  .name { position: absolute; left: 40px; bottom: 64px; margin: 0; max-width: 440px;
    font: 700 104px/.92 var(--font-sans); letter-spacing: -.035em; color: var(--text); }
  .tag { position: absolute; left: 42px; bottom: 36px; margin: 0; max-width: 440px;
    font: 14px/1.4 var(--font-sans); color: var(--text-muted); }
</style>
<div class="cover">
  <!-- blocks: --primary 216x288 slab bleeding off the top, --accent 144x120, --text 96x96,
       --primary-soft 168x144; arrangement: one tall slab with satellites, right of x=480;
       pattern: pills and discs (soft, friendly, large radii: --r-xl, --r-pill) like the
       labels and the sparrow's round body, on a 24px pitch (--s-6);
       steps --s-6 24px, --s-8 32px; radii --r-xl 20px, pills half the short side. -->
  <svg width="960" height="288" viewBox="0 0 960 288" aria-hidden="true">
    <rect class="soft" x="504" y="120" width="168" height="144" rx="20"/>
    <rect class="sky" x="696" y="-20" width="216" height="308" rx="20"/>
    <rect class="apricot" x="552" y="24" width="120" height="72" rx="36"/>
    <rect class="ink" x="840" y="168" width="96" height="96" rx="48"/>
    <circle class="seed" cx="744" cy="48" r="12"/><circle class="seed" cx="792" cy="48" r="12"/>
    <circle class="seed" cx="744" cy="96" r="12"/><circle class="seed" cx="792" cy="96" r="12"/>
    <rect class="apricot" x="720" y="216" width="96" height="24" rx="12"/>
    <rect class="sky" x="528" y="216" width="72" height="24" rx="12"/>
  </svg>
  <p class="name">Huismus</p>
  <p class="tag">Facturen voor zzp'ers onder de KOR. Zomerochtend: hemelsblauw en
    abrikoos op warme neutralen.</p>
</div>
"""

LOGO = "mus"  # the one symbol in icons.svg that is the mark, not an icon
# A standalone SVG knows neither currentColor nor the page's tokens: the sparrow's
# parts and the icons' ink get the light value of these tokens instead.
MARK_TOKENS = {"mark-body": "primary", "mark-accent": "accent", "mark-eye": "surface"}
ICON_INK_TOKEN = "text"


def _css():
    return re.sub(r"/\*.*?\*/", "", CSS.read_text(encoding="utf-8"), flags=re.S)


def _root_tokens():
    """The tokens of huismus.css: its first :root block, closed by a "}" on its own line."""
    root = re.search(r":root\s*\{(.*?)\n\}", _css(), flags=re.S)
    if not root:
        sys.exit(f"No :root block with the tokens found in {CSS}.")
    return dict(re.findall(r"--([\w-]+)\s*:\s*([^;]+);", root.group(1)))


def _light(token):
    value = _color(_root_tokens()[token])
    return value["light"] if isinstance(value, dict) else value


def _rgba(value):
    """rgb(1 2 3 / .5) -> rgba(1, 2, 3, 0.5): the form the Design System reads."""

    def one(m):
        r, g, b, a = m.groups()
        return f"rgba({r}, {g}, {b}, {float(a):g})"

    return re.sub(r"rgb\((\d+) (\d+) (\d+) / ([\d.]+)\)", one, value)


def _color(value):
    m = re.fullmatch(r"light-dark\((.+?),\s*(.+)\)", value.strip())
    if m:
        return {"light": _rgba(m.group(1)).lower(), "dark": _rgba(m.group(2)).lower()}
    return _rgba(value.strip()).lower()


COLOR_USAGE = {
    "bg": "Achtergrond van de pagina.",
    "surface": "Kaarten, dialogen.",
    "surface-2": "Hover, verzonken vlak, tellers.",
    "surface-3": "Nog dieper: voortgangsbalk.",
    "border": "Randen van kaarten en tabellen.",
    "border-strong": "Randen van invoervelden, totaalregel.",
    "text": "Tekst.",
    "text-muted": "Bijtekst, labels, rustige statussen (AA op --surface).",
    "paper": "Het vel papier van een document.",
    "primary": "Primaire knop, actieve navigatie, focus. Ochtendlucht.",
    "primary-hover": "Hover van de primaire knop.",
    "on-primary": "Tekst op --primary.",
    "primary-soft": "Zacht blauw vlak (Verzonden, informatie), met --primary-ink.",
    "primary-ink": "Tekst en links op --primary-soft en op de pagina.",
    "ring": "Focusring.",
    "accent": "Abrikoos: streep van een herinnering, kosten in grafieken. Nooit een knop.",
    "accent-soft": "Zacht abrikoos vlak: KOR-hint, Geïmporteerd.",
    "accent-ink": "Tekst op --accent-soft.",
    "ok": "Betaald, gelukt (stip of icoon).",
    "ok-bg": "Vlak bij een geslaagde melding.",
    "warn": "Let op: onbetaald, deels betaald.",
    "warn-bg": "Vlak bij --warn.",
    "bad": "Vervallen, over de KOR-grens, fout.",
    "bad-bg": "Vlak bij --bad.",
    "draft": "Concept.",
    "draft-bg": "Vlak van Concept.",
    "danger": "Verwijderknop.",
    "danger-hover": "Hover van de verwijderknop.",
    "on-danger": "Tekst op --danger.",
    "danger-ring": "Focusring van de verwijderknop.",
    "overlay": "Achter een dialoog.",
}


class TextStyle(NamedTuple):
    name: str
    size: str  # tokens in huismus.css, without "--"
    weight: str | None  # None: the normal weight of body text
    line_height: str
    sample: str
    usage: str


TEXT_STYLES = [
    TextStyle("display", "fs-3xl", "fw-bold", "lh-tight", "Factuur", "Groot op een document."),
    TextStyle("page-title", "fs-2xl", "fw-semibold", "lh-tight", "Facturen", "Paginatitel."),
    TextStyle("dialog-title", "fs-xl", "fw-semibold", "lh-tight", "Factuur uitgeven?", "Dialoog."),
    TextStyle("section-title", "fs-lg", "fw-semibold", "lh-tight", "Betalingen", "Sectietitel."),
    TextStyle(
        "body", "fs-md", None, "lh", "Ook lange woorden als kleineondernemersregeling.", "Basis."
    ),
    TextStyle("label", "fs-sm", "fw-semibold", "lh", "Vervaldatum", "Labels, tabelkoppen."),
    TextStyle("small", "fs-sm", None, "lh", "Helptekst onder het veld.", "Bijtekst."),
    TextStyle("tiny", "fs-xs", "fw-semibold", "lh", "Verloopt over 3 dagen", "Vervalhint."),
]


def tokens(commit):
    t = _root_tokens()
    colors = [
        {"name": name, "value": _color(t[name]), "usage": usage}
        for name, usage in COLOR_USAGE.items()
    ]
    styles = [
        {
            "name": style.name,
            "fontSize": t[style.size].split("/")[0].strip(),
            "lineHeight": t[style.line_height].strip(),
            "fontWeight": int(t[style.weight]) if style.weight else 400,
            "sample": style.sample,
            "usage": f"{style.usage} --{style.size}"
            + (f", --{style.weight}" if style.weight else "")
            + f", --{style.line_height}.",
        }
        for style in TEXT_STYLES
    ]

    def plain(pattern):
        return [{"name": n, "value": v.strip()} for n, v in t.items() if re.fullmatch(pattern, n)]

    return {
        "name": "Huismus",
        "version": 1,
        "meta": {
            "source": "github",
            "repo": "codebyarne/huismus",
            "ref": commit,
            "paths": {
                "tokens": ["huismus/core/static/core/huismus.css"],
                "assets": ["huismus/templates/icons.svg"],
                "docs": ["docs/design/componenten.html", "docs/design/README.md"],
            },
        },
        "color": {
            "themes": [{"id": "light", "name": "Licht"}, {"id": "dark", "name": "Donker"}],
            "tokens": colors,
        },
        "type": {
            "fonts": [],
            "families": {"sans": t["font-sans"].strip(), "mono": t["font-mono"].strip()},
            "groups": [{"name": "Tekst", "family": "sans", "styles": styles}],
        },
        "spacing": {
            "note": "Raster van 4 px.",
            "tokens": [dict(x, usage="Afstand.") for x in plain(r"s-\d+")],
        },
        "radius": {"tokens": plain(r"r-[a-z]+")},
        "shadow": {
            "tokens": [
                {"name": n, "value": _rgba(t[n].strip()), "usage": u}
                for n, u in [
                    ("sh-1", "Kaart."),
                    ("sh-2", "Zwevend, hover."),
                    ("sh-paper", "Het vel papier."),
                    ("sh-pop", "Dialoog, menu, toast."),
                ]
            ]
        },
        "size": {
            "tokens": [
                {"name": "sidebar-w", "value": t["sidebar-w"].strip(), "usage": "Zijbalk."},
                {
                    "name": "content-max",
                    "value": t["content-max"].strip(),
                    "usage": "Breedte van de inhoud.",
                },
                {
                    "name": "control-h",
                    "value": t["control-h"].strip(),
                    "usage": "Hoogte van velden en knoppen.",
                },
            ]
        },
    }


def _symbols():
    text = ICONS.read_text(encoding="utf-8")
    return {
        m.group(2): m.group(1)
        for m in re.finditer(r'(<symbol id="([\w-]+)".*?</symbol>)', text, flags=re.S)
    }


def standalone_svg(name, symbol):
    body = re.sub(r"^<symbol[^>]*>|</symbol>$", "", symbol)
    attrs = re.search(r"<symbol([^>]*)>", symbol).group(1).replace(f' id="{name}"', "")
    attrs = attrs.replace('stroke="currentColor"', f'stroke="{_light(ICON_INK_TOKEN)}"')
    for var, token in MARK_TOKENS.items():
        body = re.sub(rf"var\(--{var},var\(--[\w-]+\)\)", _light(token), body)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg"{attrs}>{body}</svg>\n'
    if "var(" in svg or "currentColor" in svg:
        sys.exit(f"icons.svg#{name} uses a colour this script can't fill in; extend MARK_TOKENS.")
    return svg


def _sections():
    """The page's sections by id. They don't nest: the first </section> ends one."""
    page = PAGE.read_text(encoding="utf-8")
    sections = dict(re.findall(r'<section id="([\w-]+)"[^>]*>(.*?)</section>', page, flags=re.S))
    for section_id, html in sections.items():
        if "<section" in html:
            sys.exit(f"Section #{section_id} on {PAGE} holds another section.")
    return sections


def preview(section_id, html, symbols):
    used = sorted(set(re.findall(r"icons\.svg#([\w-]+)", html)))
    html = html.replace("../../templates/icons.svg#", "#")
    html = re.sub(r'<h2 class="section-title">.*?</h2>', "", html, count=1)
    sprite = "".join(symbols[name] for name in used)
    _, group, _ = COMPONENTS[section_id]
    source = f"docs/design/componenten.html#{section_id}"
    return (
        f'<!-- @dsCard group="{group}" height=320 subtitle="{source}" -->\n'
        f'<div class="content" style="padding:16px;max-width:none">\n'
        f'<svg xmlns="http://www.w3.org/2000/svg" style="display:none">{sprite}</svg>\n'
        f'<div class="stack">{html}</div>\n</div>\n'
    )


def readme(commit):
    rules = DOMAIN_RULES.read_text(encoding="utf-8")
    domain = re.search(r"## Domeinregels in de UI\n(.*?)(?=\n## |\Z)", rules, flags=re.S).group(1)
    return f"""# Huismus

Self-hosted facturatie voor Nederlandse zzp'ers onder de KOR. Eén gebruiker, op een
Raspberry Pi, laptop en telefoon. Richting **Zomerochtend**: hemelsblauw en abrikoos op
warme neutralen.

> Dit Design System is een **kopie**. De bron is `huismus/core/static/core/huismus.css` in
> `codebyarne/huismus`, de componenten staan op `docs/design/componenten.html`.
> Gebouwd uit commit `{commit}` met `scripts/design_system_export.py`. Wijzig de app,
> niet dit Design System. Alle voorbeelddata is fictief.

## Principes

1. **Kleur alleen waar je iets moet doen; de rest is rustig.** Vervallen, onbetaald,
   over de KOR-grens: een gekleurd vlak (`--bad-bg`, `--warn-bg`). Betaald, definitief,
   afgerond: alleen een stip of slotje in `--text-muted`. Zo valt het ene belangrijke op.
2. **Zomerochtend.** `--primary` (hemelsblauw) voor acties, `--accent` (abrikoos) voor
   highlights en herinneringen, warme neutralen (`--bg`, `--surface`) voor de rest. Geen
   nieuwe kleuren of lettertypes zonder besluit.
3. **Abrikoos is nooit een knop.**
4. **Uitgegeven is definitief.** Geen invoervelden, een slotje. Concepten hebben geen nummer.
5. **Licht en donker, telefoon en laptop.** Alles werkt op 360 px, in beide thema's, en
   haalt WCAG AA. Elk formulier werkt zonder JavaScript; totalen komen van de server.

## Teksten

Gewoon Nederlands, kort, de gebruiker spreekt met "je". Domeintermen in het Nederlands:
factuur, offerte, creditnota, klant. Een knop zegt wat er gebeurt ("Uitgeven",
"Verwijderen"). Geen beweringen over wet of belasting in de interface; de KOR-tekst
onder een factuur is de tekst van de gebruiker zelf. Engels komt via vertalingen.

## Letters

De systeemletter (`--font-sans`): geen webfonts, werkt offline. Cijfers in bedragen
tabulair. Nummerformaten en code in `--font-mono`.

## Iconen

Lijniconen op een raster van 24, lijndikte 1,8, ronde uiteinden, in `currentColor`.
In de app komen ze uit één sprite (`huismus/templates/icons.svg`). De bestanden hier hebben
een vaste inkt (`--text` licht, {_light(ICON_INK_TOKEN)}) omdat een losse afbeelding geen
`currentColor` kent. De mus is het merkteken: lijf `--primary`, vleugel en snavel
`--accent`.

## Domeinregels in de UI
{domain}
## Niet overgenomen

- `--ease` (één beweging voor alle overgangen): het Design System kent geen beweging.
- `--lh`, `--lh-tight` en de gewichten `--fw-*` staan in de tekststijlen, niet als losse
  tokens.
- Componenten zijn statische voorbeelden met de echte `huismus.css` (`components/bundle.css`);
  er is geen componentenbibliotheek, de app is Django-templates.
"""


def export(out, commit):
    """Write the files to out, which must not exist yet or be an earlier export."""
    project = out / "project"
    if out.exists():
        if {path.name for path in out.iterdir()} - {"project", "upload"}:
            sys.exit(f"{out} holds other files; give an empty or new folder.")
        shutil.rmtree(out)
    (project / "components").mkdir(parents=True)
    symbols = _symbols()

    (project / "tokens.json").write_text(
        json.dumps(tokens(commit), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (project / "README.md").write_text(readme(commit), encoding="utf-8")
    shutil.copy(CSS, project / "components" / "bundle.css")
    sections = _sections()
    for section_id, (name, _, guide) in COMPONENTS.items():
        folder = project / "components" / name
        folder.mkdir()
        (folder / "README.md").write_text(f"# {name}\n\n{guide}\n", encoding="utf-8")
        (folder / "preview.html").write_text(
            preview(section_id, sections[section_id], symbols), encoding="utf-8"
        )
    (project / "components" / "Cover").mkdir()
    (project / "components" / "Cover" / "preview.html").write_text(COVER, encoding="utf-8")
    (project / "assets" / "Icons").mkdir(parents=True)
    (project / "assets" / "Icons" / "README.md").write_text(
        f"# Iconen\n\nLijniconen uit `huismus/templates/icons.svg`, inkt {_light(ICON_INK_TOKEN)}. "
        "In de app in `currentColor`.\n",
        encoding="utf-8",
    )
    (project / "assets" / "Logos").mkdir(parents=True)
    (project / "assets" / "Logos" / "README.md").write_text(
        "# Logo\n\nDe mus: lijf `--primary`, vleugel en snavel `--accent`, oog `--surface`.\n",
        encoding="utf-8",
    )
    for group, names in (("Logos", [LOGO]), ("Icons", [n for n in symbols if n != LOGO])):
        folder = out / "upload" / group
        folder.mkdir(parents=True, exist_ok=True)
        for name in names:
            (folder / f"{name}.svg").write_text(
                standalone_svg(name, symbols[name]), encoding="utf-8"
            )


if __name__ == "__main__":
    export(Path(sys.argv[1]), sys.argv[2] if len(sys.argv) > 2 else "onbekend")
