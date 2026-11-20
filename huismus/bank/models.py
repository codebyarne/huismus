# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank statements read in, and their incoming payments (#77, SPEC.md
section 4). Only money that came in is stored: #77 is about invoices that
were paid; the bank balance and other lines are #159.

A payment booked from a bank line is an ordinary `Payment` on the invoice;
the line points to it, so Huismus knows which payments it booked and can
undo exactly those.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel
from huismus.documents.models import Document, Payment


class BankStatement(TimestampedModel):
    """One file the user read in."""

    filename = models.CharField(_("bestandsnaam"), max_length=255)
    sha256 = models.CharField(_("sha256"), max_length=64)
    format = models.CharField(_("formaat"), max_length=20)
    # What reading it found, for the summary on the page (reading.ReadResult).
    summary = models.JSONField(_("samenvatting"), default=dict)

    class Meta:
        verbose_name = _("bankafschrift")
        verbose_name_plural = _("bankafschriften")
        ordering = ["-created_at"]

    def __str__(self):
        return self.filename


class BankTransactionQuerySet(models.QuerySet):
    def waiting(self):
        """What waits for the user: proposals and lines to choose for."""
        return self.filter(state__in=[BankTransaction.State.PROPOSED, BankTransaction.State.OPEN])


class BankTransaction(TimestampedModel):
    """One incoming payment from a statement, and what became of it."""

    objects = BankTransactionQuerySet.as_manager()

    class State(models.TextChoices):
        # Huismus booked it itself: number and open amount fit.
        BOOKED = "booked", _("geboekt door Huismus")
        # The user confirmed Huismus's proposal, or chose the invoice.
        CONFIRMED = "confirmed", _("geboekt door jou")
        # Already booked before the statement came in (by hand, or an
        # import): linked to that payment, nothing new booked.
        ALREADY_BOOKED = "already_booked", _("stond al geboekt")
        PROPOSED = "proposed", _("voorstel")
        OPEN = "open", _("open")
        SKIPPED = "skipped", _("overgeslagen")

    statement = models.ForeignKey(
        BankStatement,
        on_delete=models.CASCADE,
        related_name="transactions",
        verbose_name=_("bankafschrift"),
    )
    account_iban = models.CharField(_("rekening"), max_length=34, blank=True)
    booked_on = models.DateField(_("datum"))
    amount_cents = models.BigIntegerField(_("bedrag (cent)"))
    counterparty_name = models.CharField(_("naam"), max_length=255, blank=True)
    counterparty_iban = models.CharField(_("tegenrekening"), max_length=34, blank=True)
    description = models.TextField(_("omschrijving"), blank=True)
    reference = models.CharField(_("betalingskenmerk"), max_length=140, blank=True)
    bank_reference = models.CharField(_("referentie van de bank"), max_length=140, blank=True)
    # Recognises the same line in the same or an overlapping statement
    # (reading.fingerprint): reading it again changes nothing.
    fingerprint = models.CharField(_("vingerafdruk"), max_length=64, unique=True)
    state = models.CharField(_("status"), max_length=20, choices=State.choices)
    proposed_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("voorgestelde factuur"),
    )
    payment = models.OneToOneField(
        Payment,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_transaction",
        verbose_name=_("betaling"),
    )

    class Meta:
        verbose_name = _("bijschrijving")
        verbose_name_plural = _("bijschrijvingen")
        ordering = ["booked_on", "pk"]

    def __str__(self):
        return f"{self.booked_on} {self.amount_cents} {self.counterparty_name}"

    @property
    def can_undo(self) -> bool:
        """Booked from this line, by Huismus or by the user: a payment that
        was there before the statement is never taken back."""
        return self.payment_id is not None and self.state in (
            self.State.BOOKED,
            self.State.CONFIRMED,
        )
