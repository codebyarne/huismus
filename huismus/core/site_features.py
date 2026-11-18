# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""What Huismus can do and what is coming: the one list behind the block on
the site's home page and the page Functies (huismus/core/site.py), so both
always say the same (huismus-intern/besluiten.md, 2026-11-17).

A month is an expectation the owner made public, so it is a promise: only
what waits for nothing outside the code gets one. The release PR moves what
is finished to NOW and shifts a month that will not be made (CLAUDE.md,
Releases), so no month in the past is ever shown.
"""

from dataclasses import dataclass
from datetime import date

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Feature:
    name: str
    text: str = ""
    # The help topic that explains it (docs/hulp/<slug>.*.md).
    help: str = ""


NOW = (
    (
        _("Factureren"),
        (
            Feature(_("Klanten"), _("Elk met een eigen betalingstermijn, als je dat wilt.")),
            Feature(
                _("Facturen en creditnota’s als pdf met je logo"),
                _(
                    "Een factuur krijgt een nummer als je hem uitgeeft. "
                    "Corrigeren doe je met een creditnota."
                ),
                "facturen",
            ),
            Feature(
                _("Offertes, met één klik naar een factuur"),
                _("Verzend een offerte en zet hem om als je klant ja zegt."),
                "offertes",
            ),
            Feature(
                _("Betalingen, ook in delen"),
                _("Op het overzicht zie je wat openstaat en wat te laat is."),
            ),
            Feature(
                _("Mailen via je eigen mail"),
                _("Vanuit Huismus, via je eigen Gmail of de mailserver van je domein."),
                "mailen",
            ),
            Feature(
                _("Betaalherinnering"),
                _("Bij een factuur die te laat is, met de factuur als bijlage."),
            ),
        ),
    ),
    (
        _("Uitgaven"),
        (
            Feature(
                _("Bonnetjes als foto of pdf"),
                _("Bij elke uitgave bewaar je het bonnetje."),
                "uitgaven",
            ),
            Feature(
                _("Bonnetjesmap, ook vanaf je telefoon"),
                _("Zet een foto in een map die meesynchroniseert. Huismus haalt hem op."),
                "bonnetjes",
            ),
            Feature(
                _("Bonnetjes laten lezen"),
                _("Een AI-dienst die jij kiest vult de uitgave alvast in. Jij kijkt na."),
                "bonnetjes",
            ),
            Feature(_("Categorieën"), _("Je deelt je kosten in zoals jij dat wilt.")),
        ),
    ),
    (
        _("Btw en jaar"),
        (
            Feature(
                _("KOR met je grens in beeld"),
                _(
                    "Jouw KOR-tekst op elke factuur, en op het overzicht hoe ver je "
                    "van je grens bent."
                ),
                "kor-en-btw",
            ),
            Feature(
                _("Btw per regel, ook verlegd"),
                _(
                    "Op je facturen kies je per regel het tarief. "
                    "Van elk bonnetje leg je de btw vast."
                ),
                "kor-en-btw",
            ),
            Feature(
                _("Btw-aangifterapport per kwartaal"),
                _("De bedragen per rubriek, klaar om over te nemen. Huismus verstuurt zelf niets."),
                "kor-en-btw",
            ),
            Feature(
                _("Jaaroverzicht"),
                _("Je omzet, je kosten en wat je overhoudt, ook per kwartaal."),
            ),
        ),
    ),
    (
        _("Overstappen en bewaren"),
        (
            Feature(
                _("Import uit Moneybird met proefdraai"),
                _(
                    "Je klanten, facturen, offertes en uitgaven, met de pdf’s en de "
                    "bonnetjes. Tot op de cent nagerekend."
                ),
                "moneybird",
            ),
            Feature(
                _("Elke dag een back-up, naar een map, Dropbox of WebDAV"),
                _("Zolang Huismus open staat."),
                "back-ups",
            ),
            Feature(
                _("Export als CSV met pdf’s en bonnetjes"),
                _("Eén ZIP-bestand dat ook zonder Huismus opent."),
                "exporteren",
            ),
        ),
    ),
    (
        _("De app"),
        (
            Feature(
                _("Mac en Windows, werkt zichzelf bij"),
                _("Downloaden, installeren, beginnen."),
                "desktop-app",
            ),
            Feature(
                _("Ook op een eigen server, en dan ook op je telefoon"),
                _("Met Docker, op een Raspberry Pi, een NAS of een VPS."),
                "docker",
            ),
            Feature(
                _("Proberen met nepdata"),
                _("Een verzonnen administratie van negen jaar. Met één knop is hij weer leeg."),
                "beginnen",
            ),
            Feature(_("Nederlands en Engels"), _("De app en je facturen.")),
            Feature(
                _("AI-assistent koppelen"),
                _(
                    "ChatGPT, Claude of Gemini werkt met je administratie. Uitgeven of "
                    "mailen gebeurt pas als jij het goedkeurt."
                ),
                "ai-assistenten",
            ),
        ),
    ),
)

# (the first day of the month it is expected in, what).
COMING = (
    (
        date(2026, 12, 1),
        (
            Feature(
                _("Importeren uit andere pakketten en uit Excel"),
                _("Met één importbestand, ook als je niet van Moneybird komt."),
            ),
            Feature(
                _("Uitleg per pakket om over te stappen"),
                _("Stap voor stap, van exporteren tot nakijken."),
            ),
        ),
    ),
    (
        date(2027, 1, 1),
        (
            Feature(_("Je bankafschrift inlezen"), _("Zodat je ziet welke factuur betaald is.")),
            Feature(_("Winst-en-verliesrekening"), _("Per jaar.")),
            Feature(
                _("Auditfile voor je boekhouder"),
                _("Het bestand dat boekhoudpakketten van boekhouders inlezen."),
            ),
            Feature(_("Periodieke facturen"), _("Zoals elke maand dezelfde.")),
        ),
    ),
    (
        date(2027, 2, 1),
        (
            Feature(
                _("Huismus op je telefoon via je eigen wifi"),
                _("Ook als Huismus op je Mac of pc staat."),
            ),
            Feature(
                _("E-factuur als bijlage"),
                _("Een factuur die het boekhoudpakket van je klant kan inlezen."),
            ),
            Feature(_("Uren bijhouden"), _("En daar een factuur van maken.")),
        ),
    ),
    (
        date(2027, 3, 1),
        (
            Feature(_("Kilometers"), _("Je ritten bij je administratie.")),
            Feature(_("Artikelen"), _("Vaste regels met prijs en btw-tarief.")),
        ),
    ),
)

# Coming, but no month hangs on it yet.
LATER = (
    Feature(_("Rechtstreeks importeren uit meer pakketten")),
    Feature(_("Huismus in de Microsoft Store")),
    Feature(_("Investeringen en afschrijving")),
    Feature(
        _("Back-ups rechtstreeks naar Google Drive en OneDrive, ook zonder hun app op je computer")
    ),
)

# Nothing is decided about these (SPEC.md section 1).
MAYBE = (
    Feature(_("Een betaallink op je factuur")),
    Feature(_("Een koppeling met je bank")),
)


def _months_in_the_past(today: date) -> list[date]:
    """The months of COMING before this month. The site says "Verwacht in
    november" in December otherwise; build_site refuses (CLAUDE.md, Releases)."""
    return [month for month, _items in COMING if month < today.replace(day=1)]


months_in_the_past = _months_in_the_past


NEVER = (
    Feature(_("Salarissen")),
    Feature(_("Een webshop")),
    Feature(_("Belastingadvies")),
)
