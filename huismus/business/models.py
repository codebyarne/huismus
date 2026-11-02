# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core import feedback
from huismus.core.models import TimestampedModel
from huismus.core.validators import validate_dutch_postal_code, validate_iban, validate_kvk_number


def logo_upload_to(instance, filename):
    # Deliberately always the same path per extension: business/views.edit
    # deletes the old logo file before saving a new one, so there is always
    # exactly one current logo, not an accumulating pile of them.
    #
    # M3 warning: this means the logo is a live, mutable reference, not a
    # versioned one. When Document.business_snapshot is built at issue time
    # (SPEC.md invariant 4), it must copy the logo's bytes into the
    # snapshot/Attachment — never store this path or URL — or replacing the
    # logo later would silently change how already-issued PDFs render.
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "bin"
    return f"logo/logo.{extension}"


class Settings(TimestampedModel):
    """The one business-profile row (SPEC.md section 4: "Settings (singleton)").

    Always has pk=1 — see save()/load(). Changing a field here never touches
    already-issued documents: those store their own business/contact/KOR-text
    snapshot at issue time (SPEC.md invariant 4), not a live reference to
    this row.
    """

    business_name = models.CharField(_("bedrijfsnaam"), max_length=200)
    legal_form = models.CharField(_("rechtsvorm"), max_length=100, blank=True)
    address_line1 = models.CharField(_("adresregel 1"), max_length=200)
    address_line2 = models.CharField(_("adresregel 2"), max_length=200, blank=True)
    postal_code = models.CharField(_("postcode"), max_length=10)
    city = models.CharField(_("plaats"), max_length=100)
    country = models.CharField(_("land"), max_length=2, default="NL")

    kvk_number = models.CharField(_("KvK-nummer"), max_length=8, validators=[validate_kvk_number])
    vat_number = models.CharField(_("btw-nummer"), max_length=20, blank=True)
    iban = models.CharField(_("IBAN"), max_length=34, validators=[validate_iban])
    bic = models.CharField(_("BIC"), max_length=11, blank=True)

    email = models.EmailField(_("e-mail"))
    phone = models.CharField(_("telefoon"), max_length=30, blank=True)
    website = models.URLField(_("website"), blank=True)

    kor_enabled = models.BooleanField(_("KOR van toepassing"), default=False)
    kor_text = models.TextField(
        _("KOR-vermeldingstekst"),
        blank=True,
        help_text=_("Wordt getoond op elke factuur zolang “KOR van toepassing” aan staat."),
    )
    # Under every document with a "verlegd" line (SPEC.md M18). The user's
    # own words: Huismus suggests no legal text.
    reverse_charge_text = models.TextField(_("tekst bij btw verlegd"), blank=True)

    # The revenue at which Huismus warns (business.kor_limit). A setting, not
    # a rule this app knows: the user sets the amount that applies to them.
    kor_limit_cents = models.PositiveIntegerField(
        _("KOR-grens"), default=2_000_000, validators=[MinValueValidator(1)]
    )
    kor_warning_percent = models.PositiveSmallIntegerField(
        _("waarschuw vanaf (%)"),
        default=80,
        validators=[MinValueValidator(1), MaxValueValidator(100)],
    )

    logo = models.FileField(_("logo"), upload_to=logo_upload_to, blank=True)

    default_payment_terms_days = models.PositiveSmallIntegerField(
        _("standaard betalingstermijn (dagen)"), default=14, validators=[MinValueValidator(1)]
    )
    invoice_number_format = models.CharField(
        _("factuurnummerformaat"), max_length=50, default="{year}-{seq:04d}"
    )
    quote_number_format = models.CharField(
        _("offertenummerformaat"), max_length=50, default="OFF-{year}-{seq:04d}"
    )
    # True to match invoice_number_format's own default, which includes
    # {year} — number_reset_yearly=False with a {year} placeholder in the
    # format renders the literal word "None" in every number (found by
    # M3's issuing tests, which use both defaults together for the first
    # time; M1 never exercised the two settings against each other).
    number_reset_yearly = models.BooleanField(_("nummering elk jaar resetten"), default=True)

    default_footer_text = models.TextField(_("standaard voettekst"), blank=True)
    default_language = models.CharField(
        _("standaardtaal"),
        max_length=2,
        choices=[("nl", "Nederlands"), ("en", "English")],
        default="nl",
    )
    currency = models.CharField(_("valuta"), max_length=3, default="EUR")

    # Mailing documents (SPEC.md M10). No password field: the password is
    # kept in a file of its own (business.smtp), never in the database.
    smtp_provider = models.CharField(
        _("mailen via"),
        max_length=10,
        choices=[("", _("Niet ingesteld")), ("gmail", "Gmail"), ("other", _("Anders"))],
        blank=True,
    )
    smtp_host = models.CharField(_("SMTP-server"), max_length=200, blank=True)
    smtp_port = models.PositiveIntegerField(_("poort"), null=True, blank=True)
    smtp_security = models.CharField(
        _("beveiliging"),
        max_length=10,
        choices=[("starttls", "STARTTLS"), ("ssl", "SSL/TLS")],
        default="starttls",
    )
    smtp_username = models.CharField(_("gebruikersnaam"), max_length=200, blank=True)
    smtp_from_email = models.EmailField(
        _("afzender"),
        blank=True,
        help_text=_("Leeg: het e-mailadres van je bedrijf."),
    )

    # The text a mail starts from, per kind and language (documents.mail_texts).
    # Empty: the standard text.
    mail_invoice_subject_nl = models.CharField(
        _("onderwerp factuur (nederlands)"), max_length=300, blank=True
    )
    mail_invoice_body_nl = models.TextField(_("tekst factuur (nederlands)"), blank=True)
    mail_invoice_subject_en = models.CharField(
        _("onderwerp factuur (engels)"), max_length=300, blank=True
    )
    mail_invoice_body_en = models.TextField(_("tekst factuur (engels)"), blank=True)
    mail_credit_note_subject_nl = models.CharField(
        _("onderwerp creditnota (nederlands)"), max_length=300, blank=True
    )
    mail_credit_note_body_nl = models.TextField(_("tekst creditnota (nederlands)"), blank=True)
    mail_credit_note_subject_en = models.CharField(
        _("onderwerp creditnota (engels)"), max_length=300, blank=True
    )
    mail_credit_note_body_en = models.TextField(_("tekst creditnota (engels)"), blank=True)
    mail_quote_subject_nl = models.CharField(
        _("onderwerp offerte (nederlands)"), max_length=300, blank=True
    )
    mail_quote_body_nl = models.TextField(_("tekst offerte (nederlands)"), blank=True)
    mail_quote_subject_en = models.CharField(
        _("onderwerp offerte (engels)"), max_length=300, blank=True
    )
    mail_quote_body_en = models.TextField(_("tekst offerte (engels)"), blank=True)

    # Hoe gebruik je Huismus? (huismus.core.feedback): the organisation last
    # sent, to fill in next time, and whether the done page still asks.
    feedback_organisation = models.CharField(
        _("organisatie"), max_length=20, choices=feedback.ORGANISATION_CHOICES, blank=True
    )
    feedback_status = models.CharField(max_length=10, choices=feedback.STATUS_CHOICES, blank=True)

    class Meta:
        verbose_name = _("instellingen")
        verbose_name_plural = _("instellingen")

    def __str__(self):
        return self.business_name or _("Bedrijfsinstellingen")

    def clean(self):
        super().clean()
        if self.kor_enabled and not self.kor_text.strip():
            raise ValidationError(
                {
                    "kor_text": _(
                        "KOR-vermeldingstekst is verplicht zolang “KOR van toepassing” aan staat."
                    )
                }
            )
        if self.country == "NL" and self.postal_code:
            validate_dutch_postal_code(self.postal_code)

    def save(self, *args, **kwargs):
        self.pk = 1
        if self.created_at is None:
            # This instance was never loaded from the DB (e.g. a fresh
            # Settings() built directly rather than via load()), but forcing
            # pk=1 above turns this into an UPDATE if a row already exists —
            # auto_now_add then never fires, and created_at would be
            # written as NULL. Backfill it from the existing row instead.
            existing_created_at = (
                Settings.objects.filter(pk=1).values_list("created_at", flat=True).first()
            )
            if existing_created_at is not None:
                self.created_at = existing_created_at
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _created = cls.objects.get_or_create(pk=1)
        return obj
