# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Case, Q, When
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from huismus.business import smtp
from huismus.business.kor_limit import kor_limit_crossed_by
from huismus.business.models import Settings
from huismus.contacts.models import Contact
from huismus.core.templatetags.money import euros

from .detail import contact_changed_since_issue, timeline_events
from .drafts import (
    create_credit_note,
    document_form,
    line_formset,
    peek_number_for,
    recompute_stored_totals,
    save_draft,
)
from .editing import preview_totals
from .forms import (
    MailForm,
    PaymentForm,
    attention_options,
    default_attention,
)
from .issuing import IssueError, issue
from .listing import (
    INVOICE_TABS,
    QUOTE_TABS,
    expiry_hint,
    in_quote_tab,
    in_tab,
    matches_search,
)
from .mailing import MAILABLE_STATUSES, default_message, default_recipients, send_document
from .models import Document, DocumentLine
from .pdf import render_pdf
from .preview import render_preview_pdf
from .quoting import (
    QuoteError,
    accept_quote,
    convert_to_invoice,
    decline_quote,
    expire_quote,
    send_quote,
)
from .reopening import ReopenError, reopen, undo_reopen
from .totals import tax_rows
from .vat import vat_for_copy

# How many rows the invoice list shows at first, and how many more each
# "Meer laden" adds.
LIST_PAGE_SIZE = 50


def _int_param(request, name, default):
    try:
        return int(request.GET[name])
    except (KeyError, ValueError):
        return default


@login_required
def document_list(request):
    """Invoices and credit notes, with tabs, search and a year filter.

    Query parameters (all optional): tab (a slug from INVOICE_TABS), q
    (search), jaar (a year; default and "alle": every year, so an imported
    history is all there) and toon (how many rows to show). Drafts have no
    issue date yet and show in every year.
    """
    this_year = timezone.localdate().year
    year_param = request.GET.get("jaar", "alle")
    year = None if year_param == "alle" else _int_param(request, "jaar", this_year)
    tab_slugs = [slug for slug, _label in INVOICE_TABS]
    tab = request.GET.get("tab") if request.GET.get("tab") in tab_slugs else tab_slugs[0]
    query = request.GET.get("q", "").strip()
    shown = max(_int_param(request, "toon", LIST_PAGE_SIZE), LIST_PAGE_SIZE)

    invoices = Document.objects.filter(kind__in=["invoice", "credit_note"])
    years_with_invoices = {d.year for d in invoices.dates("issue_date", "year")}
    years = sorted(years_with_invoices | {this_year}, reverse=True)
    if year is not None:
        invoices = invoices.filter(Q(issue_date__year=year) | Q(issue_date__isnull=True))
    invoices = (
        invoices.with_payment_totals()
        .select_related("contact")
        # Drafts first, then newest first.
        .order_by(Case(When(status="draft", then=0), default=1), "-issue_date", "-number")
    )

    found = [d for d in invoices if matches_search(d, query)]
    rows = [d for d in found if in_tab(d, tab)]

    def list_url(**changes):
        params = {"tab": tab, "q": query, "jaar": year or "alle", **changes}
        return "?" + urlencode({k: v for k, v in params.items() if v})

    tabs = [
        {
            "slug": slug,
            "label": label,
            "count": sum(1 for d in found if in_tab(d, slug)),
            "url": list_url(tab=slug),
        }
        for slug, label in INVOICE_TABS
    ]
    return render(
        request,
        "documents/list.html",
        {
            "documents": rows[:shown],
            "total": len(rows),
            "more_url": list_url(toon=shown + LIST_PAGE_SIZE) if len(rows) > shown else None,
            "tabs": tabs,
            "tab": tab,
            "query": query,
            "year": year,
            "years": years,
            "has_any": Document.objects.filter(kind__in=["invoice", "credit_note"]).exists(),
        },
    )


@login_required
def document_delete(request, pk, kind="invoice"):
    """Deletes a draft: an invoice or credit note that was never issued, or
    a quote that was never sent. Both are numberless, so no gap appears in
    a number sequence (invariant 3). Anything else is a 404: an issued
    document is never deleted (invariant 2; Document.delete() and the
    triggers refuse as well) — corrections are a credit note. So is a
    draft that already has a number (reopened, or imported as scheduled)."""
    kinds = ["quote"] if kind == "quote" else ["invoice", "credit_note"]
    document = get_object_or_404(Document, pk=pk, kind__in=kinds, status="draft", number="")
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    credited_invoice = document.related_document if document.kind == "credit_note" else None
    document.delete()
    messages.success(request, _("Concept verwijderd."))
    if credited_invoice is not None:
        return redirect("documents:edit", pk=credited_invoice.pk)
    return redirect("quotes:list" if kind == "quote" else "documents:list")


def _editor_context(document, form, formset):
    """Everything the draft editor shows besides the form itself: the live
    totals (documents.editing.preview_totals), the customer's address, and
    the issue dialog's summary with the number the document would get."""
    settings = Settings.load()
    totals, line_totals = preview_totals(formset)
    if form.is_bound:
        # cleaned_data also holds the valid fields of a form with errors
        # elsewhere, so the address stays right while one field is wrong.
        form.is_valid()
        contact = form.cleaned_data.get("contact")
        issue_date = form.cleaned_data.get("issue_date")
    else:
        contact = document.contact if document.pk else form.initial.get("contact")
        issue_date = document.issue_date or form.initial.get("issue_date")
    # The T.a.v. line: as typed, as saved, or the new customer's own.
    if form.is_bound:
        attention = form.cleaned_data.get("attention", "")
    elif document.pk:
        attention = document.attention
    else:
        attention = default_attention(contact)
    options = attention_options(contact)
    if attention and attention not in options:
        options.insert(0, attention)
    attention_context = {"attention": attention, "options": options, "contact": contact}
    if document.reopened_at is not None and document.contact_snapshot:
        # A reopened document keeps the customer as it was on the invoice
        # (documents.issuing): show that, not the contact as it is now.
        contact = document.contact_snapshot
    issue_date = issue_date or timezone.localdate()
    year = issue_date.year if settings.number_reset_yearly else None
    counted_lines = sum(1 for cents in line_totals.values() if cents is not None)

    # A credit note may take the invoice down to zero, not below (SPEC.md
    # invariant 5; issue() enforces it). The editor shows the room left and
    # refuses to offer "Uitgeven" above it.
    credited_invoice = credit_remaining = None
    credit_over = False
    if document.kind == "credit_note" and document.related_document_id:
        credited_invoice = Document.objects.with_payment_totals().get(
            pk=document.related_document_id
        )
        credit_remaining = credited_invoice.total_cents - credited_invoice.credited_cents
        credit_over = totals.total_cents > credit_remaining
    is_quote = document.kind == "quote"
    prefix = "quotes" if is_quote else "documents"
    if document.pk:
        form_action = _edit_url(document)
        preview_url = reverse(f"{prefix}:preview", args=[document.pk])
        pdf_preview_url = reverse(f"{prefix}:pdf_preview", args=[document.pk])
    else:
        form_action = reverse(f"{prefix}:create")
        preview_url = reverse(f"{prefix}:preview_new")
        pdf_preview_url = reverse(f"{prefix}:pdf_preview_new")
    # Whether issuing this invoice, on the issue date shown, takes that
    # year's revenue past the KOR warning or the limit (business.kor_limit).
    # Informs, never blocks.
    kor_crossed = None
    if document.kind == "invoice":
        kor_crossed = kor_limit_crossed_by(issue_date.year, totals.subtotal_cents)
    return {
        "document": document,
        "is_quote": is_quote,
        "form_action": form_action,
        "preview_url": preview_url,
        "pdf_preview_url": pdf_preview_url,
        "list_url": reverse(f"{prefix}:list"),
        # A quote that was converted: the invoice made from it.
        "converted_invoice": Document.objects.filter(kind="invoice", related_document=document)
        .order_by("pk")
        .first()
        if is_quote and document.pk
        else None,
        "form": form,
        "formset": formset,
        "totals": totals,
        "line_totals": line_totals,
        "contact": contact,
        "attention": attention_context,
        "settings": settings,
        "has_contacts": Contact.objects.filter(archived=False).exists(),
        "can_issue": contact is not None and counted_lines > 0 and not credit_over,
        "credited_invoice": credited_invoice,
        "credit_remaining_cents": credit_remaining,
        "credit_over": credit_over,
        "next_number": peek_number_for(document, settings, year),
        "kor_crossed": kor_crossed,
        # A sent quote's history, mails included (SPEC.md M10).
        "timeline": timeline_events(document) if is_quote and document.number else None,
    }


def _edit_url(document):
    name = "quotes:edit" if document.kind == "quote" else "documents:edit"
    return reverse(name, args=[document.pk])


def _after_save(request, document):
    """The editor's submit buttons: save, or — from the dialog — save first
    and then issue (invoice, credit note) or send (quote). The dialog never
    throws away what was typed."""
    action = request.POST.get("actie")
    if action == "uitgeven":
        _issue_with_messages(request, document)
    elif action == "verzenden":
        try:
            send_quote(document)
        except QuoteError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, _("Offerte verzonden."))
    elif document.kind == "quote":
        messages.success(request, _("Offerte opgeslagen."))
    else:
        messages.success(request, _("Concept opgeslagen."))
    return redirect(_edit_url(document))


def _new_document(request, kind):
    """A new invoice or quote. Nothing is stored until the user saves:
    opening "Nieuwe factuur" and walking away leaves no empty draft behind."""
    settings = Settings.load()
    document = Document(kind=kind, status="draft")
    if request.method == "POST":
        form = document_form(document, request.POST)
        formset = line_formset(document, request.POST)
        if form.is_valid() and formset.is_valid():
            return _after_save(request, save_draft(document, form, formset))
    else:
        form = document_form(
            document,
            initial={
                "issue_date": timezone.localdate(),
                "language": settings.default_language,
                "footer_text": settings.default_footer_text,
                # ?contact=<pk>: back from "Nieuw contact" (contacts.views
                # ._back_to_invoice) with the new customer chosen.
                "contact": Contact.objects.filter(pk=_int_param(request, "contact", None)).first(),
            },
        )
        formset = line_formset(document)
    return render(request, "documents/edit.html", _editor_context(document, form, formset))


@login_required
def document_create(request):
    return _new_document(request, "invoice")


@login_required
def document_preview(request, pk=None, kind="invoice"):
    """The editor's live parts for the unsaved form: line totals, totals,
    address and issue summary, as out-of-band HTMX swaps. Saves nothing.
    Quotes stay editable after sending, so only issued documents are out."""
    if pk is None:
        document = Document(kind=kind, status="draft")
    elif kind == "quote":
        document = get_object_or_404(Document, pk=pk, kind="quote")
    else:
        document = get_object_or_404(
            Document, pk=pk, kind__in=["invoice", "credit_note"], status="draft"
        )
    form = document_form(document, request.POST)
    formset = line_formset(document, request.POST)
    return render(request, "documents/_editor_live.html", _editor_context(document, form, formset))


@login_required
def document_pdf_preview(request, pk=None, kind="invoice"):
    """The PDF of the draft as it is typed in the editor: in a new tab, or in
    the installed app in a dialog over the editor (app.js). The editor posts
    its whole, unsaved form here (documents.preview). Nothing is saved and
    no number is taken."""
    if request.method != "POST":
        return HttpResponseNotAllowed(["POST"])
    if pk is None:
        document = Document(kind=kind, status="draft")
    elif kind == "quote":
        # Only a quote that was never sent: a sent one has snapshots of what
        # the customer received, and its own PDF (document_pdf).
        document = get_object_or_404(Document, pk=pk, kind="quote", status="draft")
    else:
        document = get_object_or_404(
            Document, pk=pk, kind__in=["invoice", "credit_note"], status="draft"
        )
    form = document_form(document, request.POST)
    formset = line_formset(document, request.POST)
    response = HttpResponse(render_preview_pdf(form, formset), content_type="application/pdf")
    response["Content-Disposition"] = 'inline; filename="voorbeeld.pdf"'
    # In the installed app it opens in a frame over the editor (app.js),
    # only on Huismus's own pages.
    response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@login_required
def document_edit(request, pk):
    document = get_object_or_404(Document, pk=pk, kind__in=["invoice", "credit_note"])

    if document.status == "issued":
        return render(request, "documents/detail.html", _detail_context(document))

    return _edit_document(request, document)


def _edit_document(request, document):
    if request.method == "POST":
        form = document_form(document, request.POST)
        formset = line_formset(document, request.POST)
        if form.is_valid() and formset.is_valid():
            return _after_save(request, save_draft(document, form, formset))
    else:
        form = document_form(document)
        formset = line_formset(document)
    return render(request, "documents/edit.html", _editor_context(document, form, formset))


@login_required
def document_issue(request, pk):
    # kind__in, matching document_edit: without it, POSTing this URL for a
    # quote's pk 404s only one redirect later, at document_edit itself
    # (issue() rejects the kind internally and this view redirects there
    # regardless) — confusing over a direct 404 here, found by manually
    # exercising a URL no normal click-path in this UI ever produces.
    document = get_object_or_404(Document, pk=pk, kind__in=["invoice", "credit_note"])
    if request.method == "POST":
        _issue_with_messages(request, document)
    return redirect("documents:edit", pk=document.pk)


def _issue_with_messages(request, document):
    try:
        issue(document)
    except IssueError as exc:
        messages.error(request, str(exc))
        return
    messages.success(
        request,
        _("%(kind)s %(number)s is uitgegeven.")
        % {"kind": document.get_kind_display().capitalize(), "number": document.number},
    )
    # A reopened invoice may come out lower than what was already paid.
    if document.kind == "invoice" and document.reopened_at is not None:
        paid = Document.objects.with_payment_totals().get(pk=document.pk).paid_cents
        if paid > document.total_cents:
            messages.warning(
                request,
                _(
                    "Er is al € %(paid)s betaald, meer dan het nieuwe totaal van € %(total)s. "
                    "Controleer de betalingen."
                )
                % {"paid": euros(paid), "total": euros(document.total_cents)},
            )


@login_required
def document_reopen(request, pk):
    """ "Toch bewerken" on an issued invoice or credit note (documents.
    reopening). Only by POST, from the confirmation dialog on its page."""
    document = get_object_or_404(
        Document, pk=pk, kind__in=["invoice", "credit_note"], status="issued"
    )
    if request.method == "POST":
        try:
            reopen(document)
        except ReopenError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                _(
                    "Hij is weer een concept, met hetzelfde nummer. "
                    "Pas aan wat nodig is en geef hem opnieuw uit."
                ),
            )
    return redirect("documents:edit", pk=document.pk)


@login_required
def document_reopen_undo(request, pk):
    """ "Annuleren" in the editor of a reopened invoice or credit note: back
    to exactly how it was issued (documents.reopening.undo_reopen)."""
    document = get_object_or_404(
        Document, pk=pk, kind__in=["invoice", "credit_note"], status="draft"
    )
    if request.method == "POST":
        try:
            undo_reopen(document)
        except ReopenError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(
                request,
                _("%(kind)s %(number)s staat weer zoals je hem uitgaf.")
                % {"kind": document.get_kind_display().capitalize(), "number": document.number},
            )
    return redirect("documents:edit", pk=document.pk)


def _detail_context(document):
    """The read-only page of an issued invoice or credit note."""
    # Only a mail that went out counts.
    last_mail = document.emails.filter(succeeded=True).order_by("-sent_at").first()
    context = {
        "document": document,
        # The VAT per rate, as on the PDF (documents.totals.tax_rows).
        "tax_per_rate": tax_rows(document, document.lines.all()),
        "contact_changed": contact_changed_since_issue(document),
        # SPEC.md section 7: "the UI shows [original_pdf] as the primary
        # document for imported invoices. A re-rendered PDF is offered
        # separately and labelled as such." None for a hand-created
        # invoice/credit note — huismus/imports/commit.py is the only thing that
        # ever creates one.
        "original_pdf": document.attachments.filter(kind="original_pdf").first(),
        # The file the PDF button downloads, the same one Mailen sends.
        "primary_pdf": document.primary_original_pdf(),
        "payment_form": None,
        "is_credit": document.kind == "credit_note",
        # documents.reopening refuses an invoice with an issued credit note;
        # the dialog says so instead of offering a button that fails.
        "can_reopen": not Document.objects.filter(
            kind="credit_note", status="issued", related_document=document
        ).exists(),
        # The "Toch bewerken" dialog says whether the customer already has it.
        "last_mail": last_mail,
        # Issued again after "Toch bewerken" (reopened_at stays set then, see
        # Document.reopened_at), but the customer's last mail is older: they
        # still have the version from before.
        "customer_has_old_version": bool(
            last_mail and document.reopened_at and last_mail.sent_at < document.reopened_at
        ),
    }
    if document.kind == "credit_note":
        invoice = document.related_document
        if invoice is not None:
            invoice = Document.objects.with_payment_totals().get(pk=invoice.pk)
        context["invoice"] = invoice
        context["timeline"] = timeline_events(document)
        return context

    invoice = Document.objects.with_payment_totals().get(pk=document.pk)
    outstanding = invoice.outstanding_cents
    # Share of the invoice that is settled, for the progress bar.
    settled_cents = invoice.paid_cents + invoice.credited_cents
    if invoice.total_cents > 0:
        settled_percent = min(100, settled_cents * 100 // invoice.total_cents)
    else:
        settled_percent = 100
    context.update(
        {
            "document": invoice,
            "paid_cents": invoice.paid_cents,
            "credited_cents": invoice.credited_cents,
            "outstanding_cents": outstanding,
            "settled_percent": settled_percent,
            "payments": invoice.payments.all(),
            "credit_notes": Document.objects.filter(
                kind="credit_note", related_document=invoice
            ).order_by("issue_date", "pk"),
            "timeline": timeline_events(invoice),
            "payment_form": PaymentForm(
                initial={
                    "paid_on": timezone.localdate(),
                    "amount_cents": max(outstanding, 0),
                }
            ),
        }
    )
    return context


@login_required
def document_credit_note_create(request, pk):
    """A draft credit note for an issued invoice (documents.drafts)."""
    invoice = get_object_or_404(
        Document.objects.with_payment_totals(), pk=pk, kind="invoice", status="issued"
    )
    if request.method == "POST":
        credit_note = create_credit_note(invoice)
        return redirect("documents:edit", pk=credit_note.pk)
    return redirect("documents:edit", pk=invoice.pk)


@login_required
def document_copy(request, pk, kind="invoice"):
    """A new draft of the same kind with the customer, lines and texts of an
    invoice or quote, in any status. It gets no number, dates or snapshots
    until it is issued or sent itself (the due date then follows from the
    payment term, like any new invoice), and is no correction of the
    original (that is a credit note), so it carries no related_document.
    The notes are about the original, not about the copy."""
    document = get_object_or_404(Document, pk=pk, kind=kind)
    if request.method != "POST":
        return redirect(_edit_url(document))
    lines = list(document.lines.all())
    settings = Settings.load()
    # One transaction: a copy that fails halfway leaves no half draft.
    with transaction.atomic():
        copy = Document.objects.create(
            kind=kind,
            status="draft",
            contact=document.contact,
            language=document.language,
            currency=document.currency,
            intro_text=document.intro_text,
            footer_text=document.footer_text,
            attention=document.attention,
            reference=document.reference,
        )
        for line in lines:
            DocumentLine.objects.create(
                document=copy,
                position=line.position,
                description=line.description,
                quantity=line.quantity,
                unit=line.unit,
                unit_price_cents=line.unit_price_cents,
                **vat_for_copy(line, settings),
            )
        recompute_stored_totals(copy)
    messages.success(request, _("Kopie gemaakt. Dit is een nieuw concept."))
    return redirect(_edit_url(copy))


@login_required
def payment_create(request, pk):
    document = get_object_or_404(Document, pk=pk, kind="invoice", status="issued")
    if request.method == "POST":
        form = PaymentForm(request.POST)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.document = document
            payment.full_clean()
            payment.save()
            messages.success(request, _("Betaling geregistreerd."))
        else:
            # The detail template always builds a fresh, unbound
            # PaymentForm() (see document_edit), so there's no bound form
            # to re-render with field errors after this redirect — a
            # message is the only way the user finds out anything failed,
            # rather than the page silently looking like nothing happened.
            messages.error(
                request, _("De betaling is niet opgeslagen. Kijk het bedrag en de datum na.")
            )
    return redirect("documents:edit", pk=document.pk)


# A PDF is rendered from the snapshots (invariant 5): issued invoices and
# credit notes, and quotes once sent (send_quote() takes the snapshots).
PDF_STATUSES = ["issued", "sent", "accepted", "declined", "expired"]


# The two PDFs the PDF page (document_pdf_page) can show: ?versie=…
ORIGINAL, REGENERATED = "origineel", "opnieuw"


@login_required
def document_pdf_page(request, pk, kind="invoice"):
    """The page the PDF button opens: the PDF in a frame, Download (and
    Share, app.js), and a link back to the document. The bare PDF never
    fills the window on its own: in the installed app on an iPhone there
    was no way back from it (huismus-intern/besluiten.md, 2026-11-01). For an
    imported invoice it switches between the Moneybird original and the
    PDF Huismus makes from the snapshots. A quote's page sits under
    offertes/, so the menu marks Offertes, as on the quote itself."""
    kinds = ["quote"] if kind == "quote" else ["invoice", "credit_note"]
    document = get_object_or_404(Document, pk=pk, kind__in=kinds, status__in=PDF_STATUSES)
    has_original = document.attachments.filter(kind="original_pdf").exists()
    # Three cases: no original (only the PDF from the snapshots); an original
    # and a choice in the address; or an original and no choice, then the
    # one the PDF button used to download: the original, unless the invoice
    # was edited after the import ("Toch bewerken").
    version = request.GET.get("versie")
    if not has_original:
        version = REGENERATED
    elif version not in (ORIGINAL, REGENERATED):
        version = ORIGINAL if document.primary_original_pdf() else REGENERATED
    url_name = "original_pdf" if version == ORIGINAL else "pdf"
    return render(
        request,
        "documents/pdf_page.html",
        {
            "document": document,
            "back_url": _edit_url(document),
            "has_original": has_original,
            "version": version,
            "download_url": reverse(f"documents:{url_name}", args=[document.pk]),
            "embed_url": reverse(f"documents:{url_name}_embed", args=[document.pk]),
            "filename": f"{document.number}.pdf",
        },
    )


def _pdf_response(response, document, embed):
    """A download named after the number, ready to attach to an e-mail; or,
    for the frame on the PDF page, shown in the browser. Only that one may
    sit in a frame, and only on Huismus's own pages (XFrameOptionsMiddleware
    leaves a header that is already there alone)."""
    kind = "inline" if embed else "attachment"
    response["Content-Disposition"] = f'{kind}; filename="{document.number}.pdf"'
    if embed:
        response["X-Frame-Options"] = "SAMEORIGIN"
    return response


@login_required
def document_pdf(request, pk, embed=False):
    document = get_object_or_404(Document, pk=pk, status__in=PDF_STATUSES)
    response = HttpResponse(render_pdf(document), content_type="application/pdf")
    return _pdf_response(response, document, embed)


@login_required
def document_mail(request, pk, kind="invoice"):
    """The mail form for an issued invoice or credit note, or a sent quote
    (SPEC.md M10). Sending logs an EmailLog and leaves the document alone."""
    kinds = ["quote"] if kind == "quote" else ["invoice", "credit_note"]
    document = get_object_or_404(Document, pk=pk, kind__in=kinds)
    if document.status not in MAILABLE_STATUSES[document.kind]:
        raise Http404
    configured = smtp.is_configured(Settings.load())
    failed = None
    if request.method == "POST":
        form = MailForm(request.POST)
        if not configured:
            messages.error(request, _("Mailen is nog niet ingesteld."))
        elif form.is_valid():
            log = send_document(
                document,
                to=form.cleaned_data["to"],
                subject=form.cleaned_data["subject"],
                body=form.cleaned_data["body"],
                bcc_self=form.cleaned_data["bcc_self"],
            )
            if log.succeeded:
                messages.success(request, _("Gemaild naar %(to)s.") % {"to": log.to})
                return redirect(_edit_url(document))
            failed = log
    else:
        subject, body = default_message(document)
        form = MailForm(
            initial={"to": default_recipients(document), "subject": subject, "body": body}
        )
    return render(
        request,
        "documents/mail.html",
        {
            "document": document,
            "form": form,
            "mail_configured": configured,
            "failed": failed,
            "back_url": _edit_url(document),
            "attachment_name": f"{document.number}.pdf",
        },
    )


@login_required
def document_original_pdf(request, pk, embed=False):
    """The original PDF of an imported invoice, named after its number. Not
    a plain link into data/: there the file keeps the name it was stored
    under ("430033_kfWEXfH.pdf" when the name was taken), and the browser
    takes that name over the link's own."""
    document = get_object_or_404(Document, pk=pk)
    original = get_object_or_404(document.attachments, kind="original_pdf")
    response = FileResponse(original.file.open("rb"), content_type="application/pdf")
    return _pdf_response(response, document, embed)


@login_required
def quote_list(request):
    """Quotes with tabs and search, newest first; drafts first."""
    tab_slugs = [slug for slug, _label in QUOTE_TABS]
    tab = request.GET.get("tab") if request.GET.get("tab") in tab_slugs else tab_slugs[0]
    query = request.GET.get("q", "").strip()
    quotes = Document.objects.filter(kind="quote").select_related("contact")
    quotes = quotes.order_by(Case(When(status="draft", then=0), default=1), "-issue_date", "-pk")
    found = [q for q in quotes if matches_search(q, query)]
    today = timezone.localdate()
    rows = [(q, expiry_hint(q, today=today)) for q in found if in_quote_tab(q, tab)]

    def list_url(**changes):
        params = {"tab": tab, "q": query, **changes}
        return "?" + urlencode({k: v for k, v in params.items() if v})

    tabs = [
        {
            "slug": slug,
            "label": label,
            "count": sum(1 for q in found if in_quote_tab(q, slug)),
            "url": list_url(tab=slug),
        }
        for slug, label in QUOTE_TABS
    ]
    return render(
        request,
        "documents/quote_list.html",
        {
            "quotes": rows,
            "tabs": tabs,
            "tab": tab,
            "query": query,
            "has_any": Document.objects.filter(kind="quote").exists(),
        },
    )


@login_required
def quote_create(request):
    return _new_document(request, "quote")


@login_required
def quote_edit(request, pk):
    # A sent quote stays editable (see huismus/documents/quoting.py's module
    # docstring), so every status uses the editor.
    return _edit_document(request, get_object_or_404(Document, pk=pk, kind="quote"))


def _quote_action(request, pk, action, success_message):
    quote = get_object_or_404(Document, pk=pk, kind="quote")
    if request.method == "POST":
        try:
            action(quote)
            messages.success(request, success_message)
        except QuoteError as exc:
            messages.error(request, str(exc))
    return redirect("quotes:edit", pk=quote.pk)


@login_required
def quote_send(request, pk):
    return _quote_action(request, pk, send_quote, _("Offerte verzonden."))


@login_required
def quote_accept(request, pk):
    return _quote_action(request, pk, accept_quote, _("Offerte geaccepteerd."))


@login_required
def quote_decline(request, pk):
    return _quote_action(request, pk, decline_quote, _("Offerte afgewezen."))


@login_required
def quote_expire(request, pk):
    return _quote_action(request, pk, expire_quote, _("Offerte gemarkeerd als verlopen."))


@login_required
def quote_convert(request, pk):
    quote = get_object_or_404(Document, pk=pk, kind="quote")
    if request.method == "POST":
        try:
            invoice = convert_to_invoice(quote)
            messages.success(request, _("Conceptfactuur gemaakt van de offerte."))
            return redirect("documents:edit", pk=invoice.pk)
        except QuoteError as exc:
            messages.error(request, str(exc))
    return redirect("quotes:edit", pk=quote.pk)
