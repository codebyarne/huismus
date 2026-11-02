# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Instellingen → Exporteren (SPEC.md M19): a choice of everything or one
year, and the ZIP (core.export) as a plain GET that works without JS."""

import re
import tempfile

from django.contrib.auth.decorators import login_required
from django.http import FileResponse
from django.shortcuts import render

from . import export, help

# Read by app.js, so not HttpOnly; it holds only the page's own token.
DOWNLOAD_COOKIE = "huismus_download"


def _year(request) -> int | None:
    """?jaar=2025, or None for everything (also for anything else)."""
    try:
        year = int(request.GET.get("jaar", ""))
    except ValueError:
        return None
    return year if year > 0 else None


@login_required
def page(request):
    return render(
        request,
        "business/export.html",
        {"years": export.years(), "chosen": _year(request), "help_url": help.url("exporteren")},
    )


@login_required
def download(request):
    """Made in this request, in a temporary file rather than in memory; no
    background task (SPEC.md M19). FileResponse closes the file, which
    removes it, once it has been sent."""
    year = _year(request)
    file = tempfile.TemporaryFile()
    export.write_zip(file, year)
    file.seek(0)
    response = FileResponse(
        file, as_attachment=True, filename=export.filename(year), content_type="application/zip"
    )
    # The page's busy button waits for this cookie (app.js, data-download).
    token = request.GET.get("klaar", "")
    if re.fullmatch(r"[0-9]{1,32}", token):
        response.set_cookie(
            DOWNLOAD_COOKIE, token, max_age=60, samesite="Lax", secure=request.is_secure()
        )
    return response
