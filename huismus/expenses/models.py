# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel
from huismus.core.templatetags.money import euros


class VatRate(models.TextChoices):
    """The VAT rate of an expense line (SPEC.md M21, part 2; product-owner
    agent 2026-11-06, huismus-intern/besluiten.md). Reverse charge three
    times, as the VAT return asks them apart. Empty on a line: entered under
    the KOR or before rates were kept; it never counts as input VAT."""

    HIGH = "21", "21%"
    LOW = "9", "9%"
    ZERO = "0", _("0% of geen btw")
    REVERSE_NL = "reverse_nl", _("Btw verlegd: Nederland")
    REVERSE_EU = "reverse_eu", _("Btw verlegd: ander EU-land")
    REVERSE_NON_EU = "reverse_non_eu", _("Btw verlegd: buiten de EU")


class ExpenseCategory(TimestampedModel):
    """SPEC.md section 4. No `archived` flag: `category` PROTECTs any
    ExpenseLine that references it, so a category actually in use simply
    can't be deleted — nothing to orphan."""

    name = models.CharField(_("naam"), max_length=100)
    sort_order = models.PositiveSmallIntegerField(_("sorteervolgorde"), default=0)

    class Meta:
        verbose_name = _("uitgavecategorie")
        verbose_name_plural = _("uitgavecategorieën")
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Expense(TimestampedModel):
    """SPEC.md section 4. Not immutable the way an issued Document is —
    nothing in SPEC.md or CLAUDE.md's invariants asks for that here."""

    date = models.DateField(_("datum"))
    supplier = models.CharField(_("leverancier"), max_length=200, blank=True)
    description = models.TextField(_("omschrijving"), blank=True)
    # Gross amount actually paid (invariant 7): under the KOR there is no
    # input VAT deduction, so this is the only amount that ever counts
    # toward the year overview's expense total — never reduced by
    # vat_info_cents below. The sum of the lines (ExpenseLine), stored
    # here by huismus/expenses/lines.py, the one place that writes it.
    amount_cents = models.BigIntegerField(_("bedrag (cent)"))
    # Informational only, e.g. copied from a receipt for the user's own
    # records — never subtracted from amount_cents anywhere (invariant 7).
    # The sum of the lines' VAT, or empty when no line has any.
    vat_info_cents = models.BigIntegerField(_("btw ter info (cent)"), null=True, blank=True)

    # Set only for expenses that came in through an import; blank for
    # anything entered by hand in this UI — same pattern as Contact and
    # Document.
    source = models.CharField(_("bron"), max_length=50, blank=True)
    external_id = models.CharField(_("extern ID"), max_length=100, blank=True)
    # "Nakijken": an AI assistant filled it in (add_expense), and the user
    # hasn't said yet that it's right. "Klopt" or saving the expense turns
    # it off (huismus-intern/besluiten.md, 2026-11-05, "Bonnetjes onderweg,
    # deel 2").
    needs_review = models.BooleanField(_("nakijken"), default=False)

    class Meta:
        verbose_name = _("uitgave")
        verbose_name_plural = _("uitgaven")
        ordering = ["-date"]
        constraints = [
            # Same pattern as Contact/Document: unique on (source,
            # external_id) only when both are actually set.
            models.UniqueConstraint(
                fields=["source", "external_id"],
                condition=~Q(source="") & ~Q(external_id=""),
                name="expenses_unique_source_external_id",
            )
        ]

    @property
    def category_names(self) -> str:
        """The categories of its lines, each once, in line order: for the
        list and the AI assistants. Prefetch "lines__category" for a list."""
        names = []
        for line in self.lines.all():
            if line.category and line.category.name not in names:
                names.append(line.category.name)
        return ", ".join(names)

    def __str__(self):
        label = self.supplier or self.description[:30] or str(_("Uitgave"))
        return f"{label} (€ {euros(self.amount_cents)})"


class ExpenseLine(TimestampedModel):
    """One line of an expense, as in Moneybird's incoming documents: its
    own description, gross amount and category (huismus-intern/besluiten.md,
    2026-11-02). Written only through huismus/expenses/lines.py, which keeps
    Expense.amount_cents the sum of these."""

    expense = models.ForeignKey(
        Expense, on_delete=models.CASCADE, related_name="lines", verbose_name=_("uitgave")
    )
    position = models.PositiveIntegerField(_("positie"), default=0)
    description = models.TextField(_("omschrijving"), blank=True)
    # Gross, as on Expense (invariant 7).
    amount_cents = models.BigIntegerField(_("bedrag (cent)"))
    vat_info_cents = models.BigIntegerField(_("btw ter info (cent)"), null=True, blank=True)
    # The rate the VAT above was charged at, as on the receipt. Required
    # without the KOR (huismus/expenses/forms.py); never used to compute
    # the VAT, which is always what the user entered.
    vat_rate = models.CharField(_("btw-tarief"), max_length=20, choices=VatRate, blank=True)
    # PROTECT, as before on Expense: a category in use can't be deleted.
    category = models.ForeignKey(
        ExpenseCategory,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="lines",
        verbose_name=_("categorie"),
    )

    class Meta:
        verbose_name = _("uitgaveregel")
        verbose_name_plural = _("uitgaveregels")
        ordering = ["position", "pk"]

    def __str__(self):
        return f"{self.description[:30]} (€ {euros(self.amount_cents)})"
