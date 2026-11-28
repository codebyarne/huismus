# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.db import models
from django.utils.translation import gettext_lazy as _

from huismus.core.models import TimestampedModel

MAX_KM = 2000


class Trip(TimestampedModel):
    """A business trip (#125, SPEC.md section 4): where from, where to, why
    and how far. Not a document: it can be changed and deleted freely.
    No money: Huismus works out no allowance."""

    date = models.DateField(_("datum"))
    origin = models.CharField(_("van"), max_length=200)
    destination = models.CharField(_("naar"), max_length=200)
    purpose = models.CharField(_("doel"), max_length=500)
    # The whole trip, one decimal. More than 0 and at most MAX_KM: the
    # constraint guards the table, DistanceField says it in words.
    distance_km = models.DecimalField(_("kilometers"), max_digits=5, decimal_places=1)

    class Meta:
        verbose_name = _("rit")
        verbose_name_plural = _("ritten")
        # Within a day the trip entered last first (product-owner agent 2026-11-28).
        ordering = ["-date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(distance_km__gt=0) & models.Q(distance_km__lte=MAX_KM),
                name="trip_more_than_0_at_most_2000_km",
            ),
        ]

    def __str__(self):
        return f"{self.date} {self.origin} → {self.destination}"
