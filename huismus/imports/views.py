# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from huismus.business.models import Settings

from . import staging
from .forms import (
    PROPOSABLE_FIELDS,
    ImportSettingsForm,
    differing_current_values,
    settings_form_for,
)
from .pipeline import PROPOSED, run_moneybird_import
from .recognition import describe_uploads
from .sources import ImportSourceError


def _with_counts(section):
    """A report section (dict of an InvoiceImportReport, QuoteImportReport
    or ExpenseImportReport) plus the counts the page shows: skipped, and
    issues to check. Quotes have no payments, expenses skip nothing,
    hence .get()."""
    if not section:
        return section
    skipped = len(section.get("skipped_missing_contact", [])) + len(
        section.get("skipped_no_lines", [])
    )
    issues = (
        skipped
        + len(section["discrepancies"])
        + len(section.get("payment_issues", []))
        + len(section.get("discounts", []))
        + len(section.get("orphan_lines", []))
        + len((section.get("moneybird_reports") or {}).get("differences", []))
        + len((section.get("ubl") or {}).get("messages", []))
    )
    return {**section, "skipped_count": skipped, "issue_count": issues}


def _report_context(run):
    return {
        "invoices": _with_counts(run.report.get("sales_invoices")),
        "quotes": _with_counts(run.report.get("quotes")),
        "expenses": _with_counts(run.report.get("expenses")),
        "contacts": run.report.get("contacts"),
        "notes": run.report.get("notes", []),
    }


@login_required
def upload(request):
    """SPEC.md section 7's web entry point, in two steps (M8).

    1. Upload: the files are kept in a staging (imports.staging) and a dry
       run reports what would happen. Nothing is written to the database.
    2. Commit (see commit() below): imports exactly those staged files, so
       the user doesn't choose them again.
    """
    if request.method != "POST":
        return render(request, "imports/upload.html")
    uploads = request.FILES.getlist("files")
    if not uploads:
        messages.error(request, _("Kies eerst een of meer bestanden."))
        return render(request, "imports/upload.html")

    token = staging.stage(uploads)
    directory = staging.staged_path(token)
    try:
        return _dry_run(request, token, directory)
    except ImportSourceError as exc:
        staging.discard(token)
        messages.error(request, str(exc))
        return render(request, "imports/upload.html")


def _dry_run(request, token, directory, settings_form=None):
    """The dry-run page. The export's proposed settings are applied inside
    the dry run's rolled-back transaction, so the report shows what the
    import does with them (numbering continuing, for one). `settings_form`:
    the user's own, with errors, when "Nu echt importeren" refused it."""
    run = run_moneybird_import(directory, commit=False, settings_values=PROPOSED)
    proposal = run.report["settings_proposal"]
    # Not Settings.load(): that creates the row on a fresh install, and a
    # dry run writes nothing. Unsaved defaults show the same.
    settings = Settings.objects.filter(pk=1).first() or Settings(pk=1)
    if settings_form is None:
        settings_form = settings_form_for(settings, proposal["values"])
    current = differing_current_values(settings, proposal["values"])
    return render(
        request,
        "imports/dry_run.html",
        {
            "run": run,
            "token": token,
            "uploads": describe_uploads(directory),
            "settings_form": settings_form,
            "settings_fields": [(field, current.get(field.name)) for field in settings_form],
            "settings_source_date": (
                date.fromisoformat(proposal["source_invoice_date"])
                if proposal["source_invoice_date"]
                else None
            ),
            **_report_context(run),
        },
    )


@login_required
def commit(request):
    """Imports the files of a dry run, by its staging token, then removes
    them. An unknown or expired token imports nothing."""
    if request.method != "POST":
        return redirect("imports:upload")
    token = request.POST.get("token")
    directory = staging.staged_path(token)
    if directory is None:
        messages.error(
            request,
            _("Deze proefdraai is verlopen of al geïmporteerd. Kies de bestanden opnieuw."),
        )
        return redirect("imports:upload")
    settings_form = ImportSettingsForm(request.POST, instance=Settings.load())
    if not settings_form.is_valid():
        return _dry_run(request, token, directory, settings_form=settings_form)
    run = run_moneybird_import(
        directory,
        commit=True,
        settings_values={name: settings_form.cleaned_data[name] for name in PROPOSABLE_FIELDS},
    )
    staging.discard(token)
    return render(
        request,
        "imports/committed.html",
        {"run": run, **_report_context(run), **_new_counts_text(run.report)},
    )


def _new_counts_text(report):
    """The four parts of the sentence on the done page, as text: each
    count needs its own singular and plural ("1 factuur", "80 facturen"),
    which one blocktranslate around the whole sentence can't do."""

    def new(section):
        return (report.get(section) or {}).get("new", 0)

    customers, invoices, quotes = new("contacts"), new("sales_invoices"), new("quotes")
    expenses = new("expenses")
    return {
        "customers_text": ngettext("%(count)s nieuwe klant", "%(count)s nieuwe klanten", customers)
        % {"count": customers},
        "invoices_text": ngettext("%(count)s factuur", "%(count)s facturen", invoices)
        % {"count": invoices},
        "quotes_text": ngettext("%(count)s offerte", "%(count)s offertes", quotes)
        % {"count": quotes},
        "expenses_text": ngettext("%(count)s uitgave", "%(count)s uitgaven", expenses)
        % {"count": expenses},
    }


@login_required
def cancel(request):
    """ "Annuleren" on the dry run: removes the staged files, imports
    nothing. Like commit(), only by POST and only for a real token
    (staging.staged_path checks it)."""
    if request.method == "POST":
        staging.discard(request.POST.get("token"))
        messages.success(request, _("Import geannuleerd. Er is niets opgeslagen."))
    return redirect("imports:upload")
