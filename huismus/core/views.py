# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
import posixpath

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.templatetags.static import static
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from django.views.static import serve as static_serve

from huismus.business.forms import SettingsPartForm
from huismus.business.kor_limit import kor_limit_status
from huismus.business.models import Settings
from huismus.documents.listing import expiry_hint
from huismus.documents.models import Document
from huismus.documents.numbering import next_numbers_if_issued_today
from huismus.reports.year_overview import compute_year_overview

from . import (
    auto_backups,
    desktop,
    feedback_views,
    login_throttle,
    maintenance,
    sample_data,
    updates,
)
from .backup_views import sign_in_again
from .dashboard import onboarding_steps, outstanding_invoices
from .onboarding import STEPS


class LoginView(auth_views.LoginView):
    """Django's login, plus the "Ingelogd blijven op dit apparaat" checkbox.

    Unchecked, the session ends when the browser closes (set_expiry(0));
    checked, Django's default SESSION_COOKIE_AGE applies.

    In the desktop app (SPEC.md M11, design D6) only the password: the one
    user with a password is filled in hidden, and the session always ends
    when the app closes, so the app asks it at every start.
    """

    template_name = "registration/login.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        # After a POST, so the attempt that reached the limit already
        # explains why, rather than "wrong password" once more.
        context["locked"] = login_throttle.is_locked()
        if settings.DESKTOP:
            # Never None here in practice: without a password the window is
            # signed in by itself and never sees this page.
            user = desktop.user_with_password()
            context["desktop_username"] = user.get_username() if user else ""
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        # In the desktop app always: it asks the password at every start.
        if settings.DESKTOP or not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)
        return response


def _greeting(now):
    if now.hour < 12:
        return _("Goedemorgen")
    if now.hour < 18:
        return _("Goedemiddag")
    return _("Goedenavond")


@login_required
def home(request):
    """Overzicht: what's outstanding, this year's figures, the latest
    invoices and quotes waiting for an answer. Until there are contacts or
    documents, a welcome with the Moneybird import and a checklist."""
    first_time = sample_data.is_empty()
    if first_time:
        steps = onboarding_steps()
        return render(
            request,
            "core/home.html",
            {
                "first_time": True,
                "steps": steps,
                "steps_done": sum(1 for step in steps if step["done"]),
            },
        )

    now = timezone.localtime()
    today = now.date()
    sent_quotes = Document.objects.filter(kind="quote", status="sent").select_related("contact")
    return render(
        request,
        "core/home.html",
        {
            "first_time": False,
            "greeting": _greeting(now),
            "today": today,
            "outstanding": outstanding_invoices(),
            "year": today.year,
            "overview": compute_year_overview(today.year),
            "kor_limit": kor_limit_status(today.year),
            "drafts": Document.objects.filter(kind="invoice", status="draft").select_related(
                "contact"
            ),
            "latest_invoices": Document.objects.filter(kind="invoice", status="issued")
            .with_payment_totals()
            .order_by("-issue_date", "-pk")[:5],
            "waiting_quotes": [
                (quote, expiry_hint(quote, today=today))
                for quote in sent_quotes.order_by("expiry_date", "pk")
            ],
            **_backup_context(now),
            **_update_notices(request),
        },
    )


def _update_notices(request) -> dict:
    """The new-version banner (M11, huismus/core/updates.py), also in Docker.
    In the desktop app also, once, the toast after an update's first start:
    shown now, so cleared now (desktop/app.py sets it)."""
    status = updates.load_status()
    if status.just_updated:
        messages.success(
            request, _("Bijgewerkt naar %(version)s.") % {"version": status.just_updated}
        )
    if status.not_installed:
        messages.error(
            request,
            _("Bijwerken naar %(version)s is niet gelukt. Je gebruikt nog versie %(current)s.")
            % {"version": status.not_installed, "current": updates.current_version()},
        )
    if status.just_updated or status.not_installed:
        updates.update_status(just_updated="", not_installed="")
    return {
        "new_release": updates.available(),
        "release_waiting": updates.waiting(),
        "release_downloading": updates.downloading(),
    }


def _backup_context(now) -> dict:
    """The backup banner and "Laatste back-up" line (M11, M15)."""
    return {
        "backup_warning": auto_backups.warning(now),
        "last_backup": auto_backups.last_success(),
    }


@login_required
@require_POST
def sample_data_fill(request):
    """ "Probeer met nepdata" on the welcome card (huismus/core/sample_data.py)."""
    try:
        sample_data.fill()
    except sample_data.NotEmpty:
        pass  # A second click, or another tab: the overview shows what there is.
    except maintenance.Busy:
        messages.error(request, _("Huismus is even bezig. Probeer het zo nog eens."))
    return redirect("home")


CLEARED = _("De nepdata is weg. Je begint met een lege administratie.")


@login_required
def sample_data_clear(request):
    """ "Weer leegmaken": a page to confirm, then back to how it was."""
    if not sample_data.in_use():
        if request.method == "POST":
            # Meant for the second request of a double click without
            # JavaScript: the first one cleared it, and the browser dropped
            # its answer (huismus-intern/besluiten.md, 2026-10-31). From an old tab
            # the toast is just as true: there is no sample data.
            messages.success(request, CLEARED)
        return redirect("home")
    if request.method == "POST":
        username = request.user.get_username()
        try:
            sample_data.clear()
        except maintenance.Busy:
            messages.error(request, _("Huismus is even bezig. Probeer het zo nog eens."))
            return redirect("sample_data_clear")
        sign_in_again(request, username)
        messages.success(request, CLEARED)
        return redirect("home")
    return render(request, "core/sample_data_clear.html")


@login_required
def onboarding_start(request):
    return redirect("onboarding", STEPS[0].slug)


@login_required
def onboarding(request, slug):
    """One step of the step-by-step start: a part of the settings page.
    Saving goes on to the next step; the last one to the done page."""
    slugs = [step.slug for step in STEPS]
    if slug not in slugs:
        raise Http404
    index = slugs.index(slug)
    step = STEPS[index]
    instance = Settings.load()
    if request.method == "POST":
        form = SettingsPartForm(request.POST, request.FILES, instance=instance, fields=step.fields)
        if form.is_valid():
            form.save()
            if index + 1 < len(STEPS):
                return redirect("onboarding", STEPS[index + 1].slug)
            return redirect("onboarding_done")
    else:
        form = SettingsPartForm(instance=instance, fields=step.fields)

    return render(
        request,
        "core/onboarding.html",
        {
            "form": form,
            "step": step,
            "steps": STEPS,
            "step_number": index + 1,
            "previous": STEPS[index - 1] if index else None,
            "is_last": index + 1 == len(STEPS),
            "settings": instance,
            # From the saved settings: a rejected form has changed instance.
            "next_numbers": next_numbers_if_issued_today(Settings.load()),
        },
    )


@login_required
def onboarding_done(request):
    return feedback_views.render_done_page(request)


# The only directories under data/ that pages link to (the logo, receipts,
# imported PDFs). The rest of data/ — the database itself, backups, import
# staging — is never served, not even after login.
SERVED_MEDIA_DIRS = ("logo/", "attachments/")


@login_required
def media(request, path):
    """Serve the logo and attachments from data/.

    WhiteNoise only serves STATIC_URL; nothing else serves MEDIA_URL out of
    the box, in DEBUG or otherwise. django.views.static.serve isn't hardened
    for high-traffic production use, but this app is single-user and
    low-traffic, and — unlike Django's own DEBUG-only `static()` helper —
    gating it behind login matters here, since data/ holds private
    business documents, not just the logo.
    """
    # Normalised the same way static_serve does, so "logo/../db.sqlite3"
    # is checked as the "db.sqlite3" it would actually serve.
    normalized = posixpath.normpath(path).lstrip("/")
    if not normalized.startswith(SERVED_MEDIA_DIRS):
        raise Http404
    return static_serve(request, normalized, document_root=settings.MEDIA_ROOT)


def favicon(request):
    """Pages without an icon link of their own (the Django admin) make the
    browser ask for /favicon.ico; send it to the icon base.html links to."""
    return redirect(static("core/favicon.svg"))


# Error pages (M8). One template; the view only chooses the texts. No
# error code on the page (docs/schrijfwijzer.md): the status is for the browser.
def _error(request, status, title, text):
    return render(request, "errors/error.html", {"title": title, "text": text}, status=status)


def page_not_found(request, exception=None):
    return _error(
        request,
        404,
        _("Deze pagina bestaat niet"),
        _(
            "Misschien is de link oud of zit er een typefout in. "
            "Je gegevens zijn gewoon waar ze waren."
        ),
    )


def permission_denied(request, exception=None):
    return _error(
        request,
        403,
        _("Hier heb je geen toegang toe"),
        _(
            "Je account mag deze pagina niet openen. "
            "Ga terug naar het overzicht, of log in met een ander account."
        ),
    )


def server_error(request):
    # Not "nothing was saved": after a crash Huismus can't know that.
    return _error(
        request,
        500,
        _("Huismus kon deze pagina niet laden"),
        _(
            "Er ging iets mis in Huismus, niet bij jou. Probeer het over een minuut "
            "nog eens. Gaat het weer mis, start Huismus dan opnieuw."
        ),
    )


def csrf_failure(request, reason=""):
    """settings.CSRF_FAILURE_VIEW: a form sent after its page stood open
    too long (or from another tab after logging out). Django rejects it
    before any view runs, so nothing was saved. Reloading this page would
    send the same form again, hence "go back"."""
    return _error(
        request,
        403,
        _("Dit formulier is verlopen"),
        _(
            "De pagina stond te lang open, of je logde in een ander tabblad uit. "
            "Er is niets opgeslagen. Ga terug, laad het formulier opnieuw en vul "
            "het nog een keer in."
        ),
    )
