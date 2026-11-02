# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from huismus.business.models import Settings
from huismus.documents.models import Document

from .forms import ContactForm, ContactPersonFormSet
from .models import Contact


@login_required
def contact_list(request):
    """Active or archived contacts, with search.

    Always the full page, also for HTMX requests: with hx-boost every link
    click is one. The live search takes just #contacten-tabel from it with
    hx-select.
    """
    show_archived = request.GET.get("archived") == "1"
    query = request.GET.get("q", "").strip()
    contacts = Contact.objects.filter(archived=show_archived)
    if query:
        contacts = contacts.filter(
            Q(company_name__icontains=query)
            | Q(first_name__icontains=query)
            | Q(last_name__icontains=query)
            | Q(customer_number__icontains=query)
            | Q(email__icontains=query)
            | Q(city__icontains=query)
        )
    return render(
        request,
        "contacts/list.html",
        {
            "contacts": contacts,
            "query": query,
            "show_archived": show_archived,
            "active_count": Contact.objects.filter(archived=False).count(),
            "archived_count": Contact.objects.filter(archived=True).count(),
            "has_any": Contact.objects.exists(),
        },
    )


def _back_to_invoice(back_to, contact):
    """Where "Nieuw contact" from the invoice or quote editor returns to, with
    the new contact chosen: ?terug=factuur / ?terug=offerte is a new document,
    ?terug=<pk> an existing draft invoice or quote. None when the contact
    wasn't made from the editor."""
    if back_to == "factuur":
        return f"{reverse('documents:create')}?contact={contact.pk}"
    if back_to == "offerte":
        return f"{reverse('quotes:create')}?contact={contact.pk}"
    if back_to.isdigit():
        document = (
            Document.objects.filter(pk=int(back_to))
            .filter(Q(kind="invoice", status="draft") | Q(kind="quote"))
            .first()
        )
        if document is not None:
            document.contact = contact
            document.save(update_fields=["contact", "updated_at"])
            if document.kind == "quote":
                return reverse("quotes:edit", args=[document.pk])
            return reverse("documents:edit", args=[document.pk])
    return None


@login_required
def contact_create(request):
    back_to = request.GET.get("terug", "")
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            contact = form.save()
            messages.success(request, _("Klant toegevoegd."))
            return redirect(
                _back_to_invoice(back_to, contact) or reverse("contacts:edit", args=[contact.pk])
            )
    else:
        form = ContactForm()
    return render(
        request,
        "contacts/form.html",
        {
            "form": form,
            "formset": None,
            "contact": None,
            "back_to": back_to,
            "default_terms": Settings.load().default_payment_terms_days,
        },
    )


@login_required
def contact_edit(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == "POST":
        form = ContactForm(request.POST, instance=contact)
        formset = ContactPersonFormSet(request.POST, instance=contact, prefix="persons")
        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()
            messages.success(request, _("Klant opgeslagen."))
            return redirect("contacts:edit", pk=contact.pk)
    else:
        form = ContactForm(instance=contact)
        formset = ContactPersonFormSet(instance=contact, prefix="persons")

    # Side panel: this contact's invoices, credit notes and quotes, newest
    # first, and the net amount invoiced — issued invoices minus issued
    # credit notes, from their stored totals.
    documents = list(
        Document.objects.filter(contact=contact)
        .with_payment_totals()
        .order_by("-issue_date", "-created_at")
    )
    issued = [d for d in documents if d.status == "issued"]
    invoiced_cents = sum(d.total_cents for d in issued if d.kind == "invoice") - sum(
        d.total_cents for d in issued if d.kind == "credit_note"
    )
    return render(
        request,
        "contacts/form.html",
        {
            "form": form,
            "formset": formset,
            "contact": contact,
            "documents": documents,
            "invoiced_cents": invoiced_cents,
            "default_terms": Settings.load().default_payment_terms_days,
        },
    )


@login_required
def contact_archive_toggle(request, pk):
    contact = get_object_or_404(Contact, pk=pk)
    if request.method == "POST":
        contact.archived = not contact.archived
        contact.save()
        messages.success(
            request,
            _("Klant gearchiveerd.") if contact.archived else _("Klant gedearchiveerd."),
        )
    return redirect("contacts:list")
