# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel
from huismus.core.validators import validate_dutch_postal_code, validate_iban, validate_kvk_number


class Contact(TimestampedModel):
    """A customer (SPEC.md section 4). Either a company, a person, or both."""

    customer_number = models.CharField(_("klantnummer"), max_length=50, blank=True)
    company_name = models.CharField(_("bedrijfsnaam"), max_length=200, blank=True)
    first_name = models.CharField(_("voornaam"), max_length=100, blank=True)
    last_name = models.CharField(_("achternaam"), max_length=100, blank=True)

    address_line1 = models.CharField(_("adresregel 1"), max_length=200, blank=True)
    address_line2 = models.CharField(_("adresregel 2"), max_length=200, blank=True)
    postal_code = models.CharField(_("postcode"), max_length=10, blank=True)
    city = models.CharField(_("plaats"), max_length=100, blank=True)
    country = models.CharField(_("land"), max_length=2, default="NL", blank=True)

    email = models.EmailField(_("e-mail"), blank=True)
    # Quotes go here instead, when set (Moneybird's "send_estimates_to_email").
    quote_email = models.EmailField(_("e-mail voor offertes"), blank=True)
    phone = models.CharField(_("telefoon"), max_length=30, blank=True)
    # How the customer wants their documents; "" is no preference.
    delivery_method = models.CharField(
        _("verzendwijze"),
        max_length=10,
        blank=True,
        choices=[("email", _("E-mail")), ("post", _("Post"))],
    )

    kvk_number = models.CharField(
        _("KvK-nummer"), max_length=8, blank=True, validators=[validate_kvk_number]
    )
    vat_number = models.CharField(_("btw-nummer"), max_length=20, blank=True)
    # "T.a.v." on its documents unless one names another contact person
    # (Document.attention); Moneybird's "attention".
    attention = models.CharField(_("t.a.v."), max_length=200, blank=True)
    iban = models.CharField(_("IBAN"), max_length=34, blank=True, validators=[validate_iban])

    payment_terms_days = models.PositiveSmallIntegerField(
        _("betalingstermijn (dagen)"),
        null=True,
        blank=True,
        help_text=_("Leeg = gebruik de standaardtermijn uit Instellingen."),
    )

    notes = models.TextField(_("notities"), blank=True)
    archived = models.BooleanField(_("gearchiveerd"), default=False)

    # Set only for contacts that came in through an import (SPEC.md
    # section 7); blank for anything created by hand in this UI.
    source = models.CharField(_("bron"), max_length=50, blank=True)
    external_id = models.CharField(_("extern ID"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("contact")
        verbose_name_plural = _("contacten")
        ordering = ["company_name", "last_name", "first_name"]
        constraints = [
            # "Unique on (source, external_id) when set" (SPEC.md section
            # 4) — most contacts made through the UI have neither field, so
            # a plain unique_together would wrongly forbid more than one
            # blank/blank row.
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(source="") & ~Q(external_id=""),
                name="contacts_unique_source_external_id",
            )
        ]

    def __str__(self):
        return self.display_name

    @property
    def display_name(self):
        if self.company_name:
            return self.company_name
        full_name = f"{self.first_name} {self.last_name}".strip()
        return full_name or str(_("Klant zonder naam"))

    def clean(self):
        super().clean()
        if not self.company_name and not self.first_name and not self.last_name:
            raise ValidationError(_("Vul een bedrijfsnaam of een voor- en achternaam in."))
        if self.country == "NL" and self.postal_code:
            validate_dutch_postal_code(self.postal_code)


class ContactPerson(TimestampedModel):
    """A person at a Contact (SPEC.md section 4). No lifecycle of its own."""

    contact = models.ForeignKey(
        Contact, on_delete=models.CASCADE, related_name="persons", verbose_name=_("contact")
    )
    name = models.CharField(_("naam"), max_length=200)
    email = models.EmailField(_("e-mail"), blank=True)
    phone = models.CharField(_("telefoon"), max_length=30, blank=True)
    department = models.CharField(_("afdeling"), max_length=100, blank=True)

    class Meta:
        verbose_name = _("contactpersoon")
        verbose_name_plural = _("contactpersonen")
        ordering = ["name"]

    def __str__(self):
        return self.name
