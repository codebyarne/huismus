# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
from django.urls import path

from . import views

app_name = "documents"

# Invoices/credit notes, mounted at facturen/ in huismus/config/urls.py.
urlpatterns = [
    path("", views.document_list, name="list"),
    path("nieuw/", views.document_create, name="create"),
    path("nieuw/voorbeeld/", views.document_preview, name="preview_new"),
    path("<int:pk>/", views.document_edit, name="edit"),
    path("<int:pk>/voorbeeld/", views.document_preview, name="preview"),
    path("nieuw/voorbeeld-pdf/", views.document_pdf_preview, name="pdf_preview_new"),
    path("<int:pk>/voorbeeld-pdf/", views.document_pdf_preview, name="pdf_preview"),
    path("<int:pk>/uitgeven/", views.document_issue, name="issue"),
    path("<int:pk>/verwijderen/", views.document_delete, name="delete"),
    path("<int:pk>/heropenen/", views.document_reopen, name="reopen"),
    path("<int:pk>/heropenen/ongedaan/", views.document_reopen_undo, name="reopen_undo"),
    path("<int:pk>/kopieren/", views.document_copy, name="copy"),
    path("<int:pk>/creditnota/", views.document_credit_note_create, name="credit_note_create"),
    path("<int:pk>/betaling/", views.payment_create, name="payment_create"),
    path("<int:pk>/pdf/", views.document_pdf, name="pdf"),
    path("<int:pk>/origineel/", views.document_original_pdf, name="original_pdf"),
    # The PDF page and, for its frame, the same two PDFs shown in the browser.
    path("<int:pk>/pdf/bekijken/", views.document_pdf_page, name="pdf_page"),
    path("<int:pk>/pdf/ingebed/", views.document_pdf, {"embed": True}, name="pdf_embed"),
    path(
        "<int:pk>/origineel/ingebed/",
        views.document_original_pdf,
        {"embed": True},
        name="original_pdf_embed",
    ),
    path("<int:pk>/mailen/", views.document_mail, name="mail"),
]

# Quotes, mounted at offertes/ in huismus/config/urls.py under its own "quotes"
# namespace — a sibling resource, not nested under facturen/, even though
# both share this app's models/views. A second include() of "documents"
# under the *same* namespace turned out not to work: Django's reverse()
# doesn't merge two include()s of one namespace into one search space, so
# {% url 'documents:quote_list' %} (this list's old name) failed with
# NoReverseMatch even though the URL matched fine on the way in. A
# separate namespace sidesteps that rather than relying on undocumented
# namespace-merging behaviour.
quote_app_name = "quotes"
quote_patterns = [
    path("", views.quote_list, name="list"),
    path("nieuw/", views.quote_create, name="create"),
    path("nieuw/voorbeeld/", views.document_preview, {"kind": "quote"}, name="preview_new"),
    path("<int:pk>/", views.quote_edit, name="edit"),
    path("<int:pk>/voorbeeld/", views.document_preview, {"kind": "quote"}, name="preview"),
    path(
        "nieuw/voorbeeld-pdf/",
        views.document_pdf_preview,
        {"kind": "quote"},
        name="pdf_preview_new",
    ),
    path(
        "<int:pk>/voorbeeld-pdf/", views.document_pdf_preview, {"kind": "quote"}, name="pdf_preview"
    ),
    path("<int:pk>/verzenden/", views.quote_send, name="send"),
    path("<int:pk>/verwijderen/", views.document_delete, {"kind": "quote"}, name="delete"),
    path("<int:pk>/kopieren/", views.document_copy, {"kind": "quote"}, name="copy"),
    path("<int:pk>/mailen/", views.document_mail, {"kind": "quote"}, name="mail"),
    path("<int:pk>/pdf/bekijken/", views.document_pdf_page, {"kind": "quote"}, name="pdf_page"),
    path("<int:pk>/accepteren/", views.quote_accept, name="accept"),
    path("<int:pk>/afwijzen/", views.quote_decline, name="decline"),
    path("<int:pk>/verlopen/", views.quote_expire, name="expire"),
    path("<int:pk>/omzetten/", views.quote_convert, name="convert"),
]
