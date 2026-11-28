# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template

from huismus.mileage.trips import km_text

register = template.Library()

register.filter("km", km_text)
