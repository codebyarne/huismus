# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""How the desktop app names the moment of a backup: "vandaag 09:12",
"gisteren 09:05", "27 okt 08:58", and with the year when it isn't this
year (as the timeline does)."""

from django import template
from django.utils import timezone
from django.utils.dateformat import format as date_format
from django.utils.translation import gettext as _

from huismus.core import auto_backups

register = template.Library()


@register.filter
def moment(value, today=None):
    if value is None:
        return ""
    if timezone.is_aware(value):
        value = timezone.localtime(value)
    today = today or timezone.localdate()
    time = date_format(value, "H:i")
    days = (today - value.date()).days
    if days == 0:
        return _("vandaag %(time)s") % {"time": time}
    if days == 1:
        return _("gisteren %(time)s") % {"time": time}
    day = date_format(
        value, "MONTH_DAY_FORMAT" if value.year == today.year else "SHORT_DATE_FORMAT"
    )
    return f"{day} {time}"


@register.filter(name="folder_label")
def folder_label_filter(folder):
    return auto_backups.folder_label(folder)
