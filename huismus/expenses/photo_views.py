# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A new expense on a phone, the photo first (#188; huismus-intern/besluiten.md,
2026-11-15, "Nieuwe huisstijl", and the plan of #188).

On a phone app.js turns "Uitgave" into the camera. The photo is sent to
photo_upload(), which puts it in the tray at once, as a receipt from the
receipts folder would be: walking away never loses it. photo_expense()
then shows it above the few fields of one line, the amount first. "Uitgave
opslaan" makes the expense with the receipt on it, as Verwerken does;
"Alleen de foto bewaren" leaves it in the tray, where Verwerken has it.

Without JS, or on a wide screen, "Uitgave" is the ordinary form
(views._expense_form); nothing here is needed for that.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from huismus.core.models import Attachment

from . import batch, reading
from .adding import RECEIPT_GONE
from .forms import ExpenseForm, ExpenseLineFormSet, ReceiptUploadForm
from .models import Expense
from .receipts import sha256_of
from .views import TrayReceiptGone, all_valid, save_expense

# Attachment.source of a photo taken here.
SOURCE = "telefoon"
# The request header app.js sends the photo with, and the response header
# with the page to open (_go).
CAMERA, GO = "X-Huismus-Camera", "X-Huismus-Go"


@login_required
def photo_upload(request):
    """The photo from the camera, into the tray. With `vervangt`
    ("Opnieuw"), the photo it replaces goes, if it still waits."""
    if request.method != "POST":
        return redirect("expenses:create")
    form = ReceiptUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        # The form's own reason: "Dit bonnetje is groter dan 10 MB. …". The
        # ordinary form can take a photo from the library or a PDF.
        messages.error(request, form.errors["file"][0])
        return _go(request, reverse("expenses:create"))
    uploaded = form.cleaned_data["file"]
    receipt = Attachment.objects.create(
        file=uploaded, kind="receipt", sha256=sha256_of(uploaded), source=SOURCE
    )
    # The old one goes only now the new one is in. Only a photo taken here
    # that still waits in the tray: one on an expense meanwhile (another
    # tab) or one from the receipts folder stays. Anything else than a
    # number replaces nothing.
    replaces = request.POST.get("vervangt", "")
    if replaces.isdigit():
        replaced = Attachment.objects.in_tray().filter(source=SOURCE, pk=int(replaces))
        for old in replaced:
            old.file.delete(save=False)
            old.delete()
    return _go(request, reverse("expenses:photo", kwargs={"pk": receipt.pk}))


def _go(request, url):
    """Where the page goes next. To app.js's upload (the header CAMERA) a
    204 with the address: had fetch() followed a redirect, it would have
    shown the next page's message to nobody, and the page that opens after
    it wouldn't have it any more. To a plain form, a redirect."""
    if CAMERA not in request.headers:
        return redirect(url)
    response = HttpResponse(status=204)
    response[GO] = url
    return response


@login_required
def photo_expense(request, pk):
    """The photo above the amount, where, date and category of one line."""
    receipt = Attachment.objects.in_tray().filter(pk=pk).first()
    if receipt is None:
        # Made into an expense or removed meanwhile, in another tab.
        messages.error(request, str(RECEIPT_GONE))
        return redirect("expenses:list")
    if request.method == "POST" and "alleen_foto" in request.POST:
        # It is in the tray already. Read now, if the AI service is on.
        reading.read_in_background()
        messages.success(request, _("Bonnetje bewaard. Je vindt het bij Verwerken."))
        return redirect("expenses:list")

    # A new expense's amount 0 lasts only until save_lines() sets it.
    instance = Expense(amount_cents=0)
    if request.method == "POST":
        form = ExpenseForm(request.POST, instance=instance)
        formset = ExpenseLineFormSet(request.POST, instance=instance, prefix="lines")
        if all_valid(form, formset):
            try:
                save_expense(form, formset, tray_receipt=receipt)
            except TrayReceiptGone:
                messages.error(request, str(RECEIPT_GONE))
                return redirect("expenses:list")
            messages.success(request, _("Uitgave opgeslagen."))
            return redirect("expenses:list")
    else:
        form = ExpenseForm(instance=instance, initial={"date": timezone.localdate()})
        formset = ExpenseLineFormSet(instance=instance, prefix="lines")
    return render(
        request,
        "expenses/photo.html",
        {
            "receipt": receipt,
            "form": form,
            "formset": formset,
            "line_form": formset.forms[0],
            # More lines or a description: the whole form, in Verwerken.
            "full_form_url": batch.Item(batch.RECEIPT, receipt.pk).url(),
            "upload_url": reverse("expenses:photo_upload"),
        },
    )
