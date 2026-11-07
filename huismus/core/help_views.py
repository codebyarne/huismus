# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hulp: the user documentation from docs/hulp/ (huismus/core/help.py)."""

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from . import feedback_views, help


@login_required
def index(request):
    groups = [
        (group.title, [(slug, help.title(slug), help.summary(slug)) for slug in group.topics])
        for group in help.groups()
    ]
    return render(request, "core/help_index.html", {"groups": groups})


@login_required
def page(request, slug):
    if slug not in help.TOPICS:
        raise Http404
    if slug == help.FEEDBACK:
        return feedback_views.render_help_page(request)
    return render(request, "core/help_page.html", {"page": help.render(slug)})
