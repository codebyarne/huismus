# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Bank statements read in, and their lines (SPEC.md section 4): money
that came in, matched to invoices (#77), and money that went out, matched
to expenses (#257). The bank balance is #159.

A payment booked from a line coming in is an ordinary `Payment` on the
invoice; the line points to it, so Huismus knows which payments it booked
and can undo exactly those. A line going out points to its expense; the
expense itself never changes for it (CLAUDE.md rule 7), and undoing only
takes the link away.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel
from huismus.documents.models import Document, Payment
from huismus.expenses.models import Expense


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
    """One line of a statement, and what became of it. `amount_cents` > 0:
    money in, for an invoice; < 0: money out, for an expense."""

    objects = BankTransactionQuerySet.as_manager()

    class State(models.TextChoices):
        # Huismus booked it itself: number and open amount fit, or (money
        # out) amount, name and date of one expense (expense_matching.py).
        BOOKED = "booked", _("geboekt door Huismus")
        # The user confirmed Huismus's proposal, or chose the invoice or
        # expense, or made the expense from the line (Uitgave maken).
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
    # Only for a line that waits: Huismus's proposal (PROPOSED), or the
    # invoice a payment was undone from (OPEN). A booked line has its
    # invoice through `payment`.
    proposed_document = models.ForeignKey(
        Document,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("voorgestelde factuur"),
    )
    # Money out: the same, for an expense. `proposed_expense` while it
    # waits, `expense` once it is linked.
    proposed_expense = models.ForeignKey(
        Expense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name=_("voorgestelde uitgave"),
    )
    # Deleting the expense makes the line wait again (signals.py).
    expense = models.OneToOneField(
        Expense,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="bank_transaction",
        verbose_name=_("uitgave"),
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
        verbose_name = _("bankregel")
        verbose_name_plural = _("bankregels")
        ordering = ["booked_on", "pk"]

    def __str__(self):
        return f"{self.booked_on} {self.amount_cents} {self.counterparty_name}"

    @property
    def is_outgoing(self) -> bool:
        return self.amount_cents < 0

    @property
    def gross_cents(self) -> int:
        """The amount without its sign: what an expense for it is."""
        return abs(self.amount_cents)

    @property
    def can_undo(self) -> bool:
        """Booked from this line, by Huismus or by the user: a payment that
        was there before the statement is never taken back."""
        linked = self.payment_id is not None or self.expense_id is not None
        return linked and self.state in (self.State.BOOKED, self.State.CONFIRMED)


class BankBalance(TimestampedModel):
    """The opening and closing balance one statement states (#159), as the
    bank gives them: Huismus never adds lines up to get a balance. The
    same statement from another or an overlapping file is one row. What
    Huismus does with them is in balances.py."""

    account_iban = models.CharField(_("rekening"), max_length=34)
    opening_on = models.DateField(_("datum beginsaldo"))
    opening_cents = models.BigIntegerField(_("beginsaldo (cent)"))
    closing_on = models.DateField(_("datum eindsaldo"))
    closing_cents = models.BigIntegerField(_("eindsaldo (cent)"))

    class Meta:
        verbose_name = _("banksaldo")
        verbose_name_plural = _("banksaldi")
        ordering = ["account_iban", "closing_on", "pk"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "account_iban",
                    "opening_on",
                    "opening_cents",
                    "closing_on",
                    "closing_cents",
                ],
                name="bank_balance_once",
            )
        ]

    def __str__(self):
        return f"{self.account_iban} {self.closing_on} {self.closing_cents}"
