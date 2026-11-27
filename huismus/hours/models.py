# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel

from .entries import amount_cents

MAX_HOURS = 24


class TimeEntry(TimestampedModel):
    """Hours worked for a customer on a day (#80, SPEC.md section 4). Not a
    document: it can be changed and deleted freely. The amount is never
    stored (hours.entries.amount_cents); without a rate these are hours
    you don't bill."""

    date = models.DateField(_("datum"))
    # PROTECT: a customer is archived, never deleted, and keeps his hours.
    contact = models.ForeignKey(
        "contacts.Contact",
        on_delete=models.PROTECT,
        related_name="time_entries",
        verbose_name=_("klant"),
    )
    description = models.CharField(_("omschrijving"), max_length=500, blank=True)
    # Hours with two decimals: "1:20" is stored, shown and billed as 1,33.
    hours = models.DecimalField(
        _("uren"),
        max_digits=4,
        decimal_places=2,
        validators=[MinValueValidator(0), MaxValueValidator(MAX_HOURS)],
    )
    # Cents per hour, excluding VAT when you charge VAT. Empty: not billed.
    rate_cents = models.BigIntegerField(
        _("tarief per uur"), null=True, blank=True, validators=[MinValueValidator(0)]
    )
    # For an import later (Moneybird, Huismus's own format); empty when
    # entered here.
    source = models.CharField(max_length=20, blank=True)
    external_id = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = _("uren")
        verbose_name_plural = _("uren")
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hours__gt=0) & models.Q(hours__lte=MAX_HOURS),
                name="hours_more_than_0_at_most_24",
            ),
            models.CheckConstraint(
                condition=models.Q(rate_cents__isnull=True) | models.Q(rate_cents__gte=0),
                name="hours_rate_not_negative",
            ),
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~models.Q(external_id=""),
                name="hours_unique_source_external_id",
            ),
        ]

    def __str__(self):
        return f"{self.date} {self.contact} {self.hours}"

    @property
    def amount_cents(self) -> int | None:
        return amount_cents(self.hours, self.rate_cents)
