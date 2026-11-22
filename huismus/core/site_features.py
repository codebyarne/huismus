# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Everything a bookkeeping for a freelancer needs, and whether Huismus does it
now or later: the one list behind the overview on the site's home page and the
page Functies (huismus/core/site.py), so both always say the same.

The point is to show how complete Huismus is: every feature you would expect
of a full bookkeeping package is here, with a check when it works today and
"Binnenkort verwacht" when it is on the list (the owner, 2026-11-19; it
replaced "Later" of 2026-11-18, which replaced the months of 2026-11-17). It is
not a date. The release PR gives what is finished
its check (CLAUDE.md, Releases).
"""

from dataclasses import dataclass

from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Feature:
    name: str
    text: str = ""
    # The help topic that explains it (docs/hulp/<slug>.*.md).
    help: str = ""
    # On the list, not in Huismus yet.
    later: bool = False


def _later(name, text=""):
    return Feature(name, text, later=True)


FEATURES = (
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
            _later(_("Periodieke facturen"), _("Zoals elke maand dezelfde.")),
            _later(_("Uren bijhouden"), _("En daar een factuur van maken.")),
            _later(_("Artikelen"), _("Vaste regels met prijs en btw-tarief.")),
            _later(
                _("E-factuur als bijlage"),
                _("Een factuur die het boekhoudpakket van je klant kan inlezen."),
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
            _later(_("Kilometers"), _("Je ritten bij je administratie.")),
            _later(_("Investeringen en afschrijving")),
        ),
    ),
    (
        _("Btw en jaar"),
        (
            Feature(
                _("Kleineondernemersregeling (KOR), met je grens in beeld"),
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
            Feature(
                _("Je bankafschrift inlezen"),
                _("Zodat je ziet welke factuur betaald is."),
                "bankafschrift",
            ),
            _later(_("Winst-en-verliesrekening"), _("Per jaar.")),
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
            Feature(
                _("Importeren uit andere pakketten en uit Excel"),
                _("Met één importbestand, ook als je niet van Moneybird komt."),
                "importeren",
            ),
            _later(
                _("Auditfile voor je boekhouder"),
                _("Het bestand dat boekhoudpakketten van boekhouders inlezen."),
            ),
            _later(
                _(
                    "Back-ups rechtstreeks naar Google Drive en OneDrive, ook zonder hun app "
                    "op je computer"
                )
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
            _later(
                _("Huismus op je telefoon via je eigen wifi"),
                _("Ook als Huismus op je Mac of pc staat."),
            ),
            _later(_("Huismus in de Microsoft Store")),
        ),
    ),
)

# Nothing is decided about these (SPEC.md section 1), so they are not "Later".
MAYBE = (
    Feature(_("Een betaallink op je factuur")),
    Feature(_("Een koppeling met je bank")),
)

NEVER = (
    Feature(_("Salarissen")),
    Feature(_("Een webshop")),
    Feature(_("Belastingadvies")),
)


def counts() -> tuple[int, int]:
    """(how many work today, how many come later)."""
    every = [feature for _group, items in FEATURES for feature in items]
    later = sum(feature.later for feature in every)
    return len(every) - later, later
