# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen as an overview with a page per topic (SPEC.md M14). Each
topic is a part of the settings form (business.forms.SettingsPartForm),
with its validation; the overview card shows a line and a pill from the
saved settings."""

from dataclasses import dataclass

from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import get_language, pgettext_lazy
from django.utils.translation import gettext_lazy as _

from huismus.assistants import key as assistant_key
from huismus.core import auto_backups, cloud_backups, desktop, updates
from huismus.core.appearance import language_name
from huismus.core.models import THEME_CHOICES
from huismus.core.templatetags.backups import moment
from huismus.core.templatetags.money import money
from huismus.documents.numbering import next_numbers_if_issued_today
from huismus.expenses import inbox

from . import smtp
from .forms import MAIL_TEXT_FIELDS
from .models import Settings


@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    intro: str
    fields: tuple[str, ...]


TOPICS = (
    Topic(
        "bedrijf",
        _("Bedrijf"),
        _("Staat op elke factuur: naam, adres, KvK, btw-nummer, bank en e-mail."),
        (
            "business_name",
            "legal_form",
            "address_line1",
            "address_line2",
            "postal_code",
            "city",
            "country",
            "email",
            "phone",
            "website",
            "kvk_number",
            "vat_number",
            "iban",
            "bic",
        ),
    ),
    Topic(
        "kor",
        _("KOR"),
        _("De KOR-tekst onder je facturen, en wanneer je hoort dat je omzet de grens nadert."),
        (
            "kor_enabled",
            "kor_text",
            "kor_limit_cents",
            "kor_warning_percent",
            "reverse_charge_text",
        ),
    ),
    Topic(
        "facturen",
        _("Facturen en nummering"),
        _("Betalingstermijn, nummerformaten en standaardtaal."),
        (
            "default_payment_terms_days",
            "invoice_number_format",
            "quote_number_format",
            "number_reset_yearly",
            "default_language",
            "currency",
        ),
    ),
    Topic(
        "huisstijl",
        _("Huisstijl"),
        _("Je logo bovenaan en de voettekst onderaan je facturen."),
        ("logo", "default_footer_text"),
    ),
    Topic(
        "mailen",
        _("Mailen"),
        _("Hoe Huismus je facturen en offertes mailt, en met welke tekst."),
        (
            "smtp_provider",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "smtp_password",
            "smtp_from_email",
            *(name for _kind, _part, _language, name in MAIL_TEXT_FIELDS),
        ),
    ),
)

BY_SLUG = {topic.slug: topic for topic in TOPICS}


def business_is_complete(settings: Settings) -> bool:
    """Every field of Bedrijf that the settings require is filled in."""
    return all(
        getattr(settings, name)
        for name in BY_SLUG["bedrijf"].fields
        if not Settings._meta.get_field(name).blank
    )


def cards(settings: Settings, theme: str = "") -> list[dict]:
    """The overview: per topic its line and, where it says something, a pill
    (its text and huismus.css class). theme: the signed-in user's, for the
    card Weergave."""
    ok, warn, off = "pill-accepted", "pill-unpaid", "pill-expired"
    # A context of their own: "Aan" is also "To" (a mail's recipient).
    on_text, off_text = pgettext_lazy("setting", "Aan"), pgettext_lazy("setting", "Uit")
    summary = {}

    place = " · ".join(part for part in (settings.business_name, settings.city) if part)
    summary["bedrijf"] = (
        place or _("Nog niet ingevuld"),
        (_("Compleet"), ok) if business_is_complete(settings) else (_("Niet compleet"), warn),
    )

    # The limit and percentage the user set, never a rule of our own (M12).
    summary["kor"] = (
        _("Grens %(limit)s · waarschuwen vanaf %(percent)s%%")
        % {"limit": money(settings.kor_limit_cents), "percent": settings.kor_warning_percent},
        (on_text, ok) if settings.kor_enabled else (off_text, off),
    )

    next_invoice = next_numbers_if_issued_today(settings)["invoice"]
    summary["facturen"] = (
        _("Volgende factuur: %(number)s") % {"number": next_invoice} if next_invoice else "",
        None,
    )

    if settings.logo:
        summary["huisstijl"] = (settings.logo.name.rsplit("/", 1)[-1], (_("Logo"), ok))
    else:
        summary["huisstijl"] = (_("Nog geen logo"), None)

    if smtp.is_configured(settings):
        provider = "Gmail" if settings.smtp_provider == "gmail" else _("Eigen server")
        summary["mailen"] = (
            _("via %(address)s") % {"address": smtp.sender(settings)},
            (provider, ok),
        )
    else:
        summary["mailen"] = (_("Nog niet ingesteld"), (off_text, off))

    result = [
        {
            "title": topic.title,
            "intro": topic.intro,
            "slug": topic.slug,
            "url": reverse("business:topic", args=[topic.slug]),
            "line": summary[topic.slug][0],
            "pill": summary[topic.slug][1],
        }
        for topic in TOPICS
    ]
    result.append(_backups_card(ok, off))
    result.append(_receipts_folder_card(ok, off))
    result.append(_export_card())
    result.append(_assistants_card(ok, off))
    result.append(_updates_card(ok, off))
    if django_settings.DESKTOP:
        result.append(_password_card(ok, off))
    result.append(_appearance_card(theme))
    return result


def _backups_card(ok, off) -> dict:
    """Back-ups (SPEC.md M11, M15) is not a part of the settings form, but
    its own page (core.backup_views)."""
    status = auto_backups.load_status()
    cloud = cloud_backups.load()
    last = auto_backups.last_success()
    if not status.folder and not cloud.service:
        line, pill = _("Nog geen map gekozen"), (pgettext_lazy("setting", "Uit"), off)
    elif status.failed or (cloud.service and cloud.failed):
        line, pill = _("De laatste back-up is mislukt"), (_("Mislukt"), "pill-overdue")
    else:
        line = _("Laatste back-up: %(moment)s") % {"moment": moment(last)} if last else ""
        pill = (pgettext_lazy("setting", "Aan"), ok)
    return {
        "title": _("Back-ups"),
        "intro": _("Elke dag een kopie van je administratie in een map die jij kiest."),
        "slug": "back-ups",
        "url": reverse("business:backups"),
        "line": line,
        "pill": pill,
    }


def _receipts_folder_card(ok, off) -> dict:
    """Bonnetjesmap (SPEC.md M20, expenses.inbox_views): where Huismus picks
    up receipts saved on the road."""
    status = inbox.load()
    if not inbox.is_on(status):
        line, pill = _("Nog geen map gekozen"), (pgettext_lazy("setting", "Uit"), off)
    elif status.failed:
        line, pill = _("Ophalen is mislukt"), (_("Mislukt"), "pill-overdue")
    else:
        line, pill = inbox.place(status), (pgettext_lazy("setting", "Aan"), ok)
    return {
        "title": _("Bonnetjesmap"),
        "intro": _("Bonnetjes van onderweg, vanzelf in Huismus."),
        "slug": "bonnetjesmap",
        "url": reverse("business:receipts_folder"),
        "line": line,
        "pill": pill,
    }


def _export_card() -> dict:
    """Exporteren (SPEC.md M19, core.export_views), next to Back-ups. No
    pill: nothing to switch on."""
    return {
        "title": _("Exporteren"),
        "intro": _("Al je facturen, offertes, klanten en uitgaven in één ZIP."),
        "slug": "exporteren",
        "url": reverse("business:export"),
        "line": "",
        "pill": None,
    }


def _assistants_card(ok, off) -> dict:
    """AI-assistenten (SPEC.md M16, assistants.views), everywhere."""
    if not assistant_key.current():
        line, pill = _("Nog niet gekoppeld"), (pgettext_lazy("setting", "Uit"), off)
    elif assistant_key.is_used():
        line, pill = "", (_("Gekoppeld"), ok)
    else:
        line, pill = "", (_("Wacht op verbinding"), "pill-sent")
    return {
        "title": _("AI-assistenten"),
        "intro": _("Laat een AI-assistent met je administratie werken."),
        "slug": "ai-assistenten",
        "url": reverse("business:assistants"),
        "line": line,
        "pill": pill,
    }


def _updates_card(ok, off) -> dict:
    """SPEC.md M11, core.update_views. In Docker it only says so."""
    status = updates.load_status()
    release = updates.available()
    if release is not None:
        line = _("Huismus %(version)s is er") % {"version": release.version}
    else:
        line = _("Versie %(version)s") % {"version": updates.current_version()}
    on, off_text = pgettext_lazy("setting", "Aan"), pgettext_lazy("setting", "Uit")
    return {
        "title": _("Updates"),
        "intro": _("Huismus werkt zichzelf bij.")
        if django_settings.DESKTOP
        else _("Huismus zegt het als er een nieuwe versie is."),
        "slug": "updates",
        "url": reverse("business:updates"),
        "line": line,
        "pill": (on, ok) if status.enabled else (off_text, off),
    }


def _password_card(ok, off) -> dict:
    """Only in the desktop app (SPEC.md M11, core.password_views)."""
    on = desktop.user_with_password() is not None
    return {
        "title": _("Wachtwoord"),
        "intro": _("Een wachtwoord vragen als Huismus opent. Standaard uit."),
        "slug": "wachtwoord",
        "url": reverse("business:password"),
        "line": _("Huismus vraagt een wachtwoord") if on else _("Huismus opent zonder wachtwoord"),
        "pill": (pgettext_lazy("setting", "Aan"), ok)
        if on
        else (pgettext_lazy("setting", "Uit"), off),
    }


def _appearance_card(theme) -> dict:
    """Taal en thema, last (huismus-intern/besluiten.md, 2026-10-31): the language
    of this device and the user's theme. No pill: nothing to switch on."""
    return {
        "title": _("Weergave"),
        "intro": _("Taal en thema van Huismus. Je facturen veranderen niet."),
        "slug": "weergave",
        "url": reverse("business:appearance"),
        "line": f"{language_name(get_language())} · {dict(THEME_CHOICES)[theme]}",
        "pill": None,
    }
