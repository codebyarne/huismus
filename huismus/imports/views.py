# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.utils import translation
from django.utils.translation import get_language, ngettext
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.core import help
from huismus.core.export_format import LANGUAGES

from . import csv_template, staging
from .csv_parse import SOURCE as CSV
from .forms import (
    PROPOSABLE_FIELDS,
    ImportSettingsForm,
    differing_current_values,
    settings_form_for,
)
from .pipeline import PROPOSED, run_import, run_import_of, source_of
from .recognition import describe_uploads
from .sources import ImportSourceError, read_exports

# The two tabs of the upload page. Which import runs follows from the
# files themselves (pipeline.source_of), not from the tab.
MONEYBIRD_TAB = "moneybird"
CSV_TAB = "csv"
UPLOAD_URLS = {MONEYBIRD_TAB: "imports:upload", CSV_TAB: "imports:upload_other"}


def _with_counts(section, source=""):
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
        + len(section.get("refused", []))
        + len(section.get("unlinked_credit_notes", []))
        + len(section.get("possible_duplicates", []))
        + len(section.get("changed_in_file", []))
        + len((section.get("moneybird_reports") or {}).get("differences", []))
        + len((section.get("ubl") or {}).get("messages", []))
    )
    if section.get("lines_without_rate"):
        # Only counted without the KOR (csv_commit): VAT that stays out of
        # the VAT return report until the rate is chosen.
        issues += section["lines_without_rate"] + len(section.get("unknown_vat_rates", []))
    # A missing PDF or receipt is a warning for Moneybird, whose export has
    # them all. In Huismus's own format a file without them is normal: the
    # block keeps its check mark, and its title line says how many.
    missing_files = section.get("missing_pdfs") or section.get("missing_receipts")
    warn = bool(issues or (missing_files and source != CSV))
    return {**section, "skipped_count": skipped, "issue_count": issues, "warn": warn}


def _report_context(run):
    return {
        "invoices": _with_counts(run.report.get("sales_invoices"), run.source),
        "quotes": _with_counts(run.report.get("quotes"), run.source),
        "expenses": _with_counts(run.report.get("expenses"), run.source),
        "contacts": run.report.get("contacts"),
        "source": run.source,
        "back_url": UPLOAD_URLS[CSV_TAB if run.source == CSV else MONEYBIRD_TAB],
        "notes": run.report.get("notes", []),
    }


def _upload_page(request, tab):
    return render(
        request,
        "imports/upload.html",
        {"tab": tab, "upload_url": UPLOAD_URLS[tab], "help_url": help.url("importeren")},
    )


@login_required
def template(request):
    """The template of Huismus's own format (imports.csv_template). Small
    and made at once: a plain download. In the language of the page it was
    asked from, which the link carries (?taal=): Safari fetches a download
    apart from the page, and then the request's own language can be
    another one."""
    language = request.GET.get("taal")
    if language not in LANGUAGES:
        language = get_language()
    with translation.override(language):
        response = HttpResponse(csv_template.template_zip(), content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{csv_template.filename()}"'
    return response


@login_required
def upload(request, tab=MONEYBIRD_TAB):
    """SPEC.md section 7's web entry point, in two steps (M8). `tab`: which
    explanation the page shows, for Moneybird or for Huismus's own format
    (M22); the files decide which import runs.

    1. Upload: the files are kept in a staging (imports.staging) and a dry
       run reports what would happen. Nothing is written to the database.
    2. Commit (see commit() below): imports exactly those staged files, so
       the user doesn't choose them again.
    """
    if request.method != "POST":
        return _upload_page(request, tab)
    uploads = request.FILES.getlist("files")
    if not uploads:
        messages.error(request, _("Kies eerst een of meer bestanden."))
        return _upload_page(request, tab)

    token = staging.stage(uploads)
    directory = staging.staged_path(token)
    try:
        return _dry_run(request, token, directory)
    except ImportSourceError as exc:
        staging.discard(token)
        messages.error(request, str(exc))
        return _upload_page(request, tab)


def _dry_run(request, token, directory, settings_form=None):
    """The dry-run page. The export's proposed settings are applied inside
    the dry run's rolled-back transaction, so the report shows what the
    import does with them (numbering continuing, for one). `settings_form`:
    the user's own, with errors, when "Nu echt importeren" refused it."""
    run = run_import(directory, commit=False, settings_values=PROPOSED)
    if run.source == CSV:
        return _csv_dry_run(request, run, token, directory)
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


def _csv_dry_run(request, run, token, directory):
    """The dry run of Huismus's own format: the same page without the
    settings block, since these files hold no business details. An
    imported document takes the business details of that moment, so the
    page says so while the business name is still empty."""
    settings = Settings.objects.filter(pk=1).first()
    return render(
        request,
        "imports/dry_run.html",
        {
            "run": run,
            "token": token,
            "uploads": describe_uploads(directory),
            "business_name_missing": settings is None or not settings.business_name,
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
    # Read once: what the files are decides whether settings come along.
    exports = read_exports(directory)
    settings_values = None
    if source_of(exports) != CSV:
        settings_form = ImportSettingsForm(request.POST, instance=Settings.load())
        if not settings_form.is_valid():
            return _dry_run(request, token, directory, settings_form=settings_form)
        settings_values = {name: settings_form.cleaned_data[name] for name in PROPOSABLE_FIELDS}
    run = run_import_of(exports, commit=True, settings_values=settings_values)
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
