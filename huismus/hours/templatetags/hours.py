# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django import template

from huismus.hours.listing import hours_text

register = template.Library()

register.filter("hours", hours_text)
