# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus? (huismus.core.feedback): the card on the done
page of the step-by-step start and on the help page "Feedback geven"
(huismus-intern/besluiten.md, 2026-11-02).

Three steps in the page, each a plain POST: fill in, "Controleer gegevens"
shows every field that goes, "Versturen" sends. Between the steps the
answers travel in the page (hidden fields), not on the server: until
Versturen nothing is stored, and what someone misses and their e-mail
address never are, only sent. The overview is a step for the user, not a
check on the server: a POST with "versturen" sends a valid form."""

from django import forms
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from huismus.business.models import Settings

from . import feedback, help
from .onboarding import STEPS

# Where the card is, as the form's hidden "plek".
DONE_PAGE = "welkom"
HELP_PAGE = "hulp"
# In the address after sending, for the thank-you line.
SENT_PARAM = "verstuurd"


class FeedbackForm(forms.Form):
    """Only the organisation is needed; skipping is its own button."""

    organisation = forms.ChoiceField(
        label=_("Wat voor organisatie heb je?"),
        choices=[("", _("Kies…")), *feedback.ORGANISATION_CHOICES],
    )
    wish = forms.CharField(
        label=_("Wat mis je, of wat wil je met Huismus doen?"),
        help_text=_("Komt als idee op GitHub, waar anderen het kunnen lezen. Je e-mailadres niet."),
        max_length=feedback.MAX_WISH,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    email = forms.EmailField(
        label=_("E-mailadres"),
        help_text=_("Alleen als de appbouwer je er iets over mag vragen."),
        max_length=feedback.MAX_EMAIL,
        required=False,
    )

    def clean_wish(self):
        # A browser sends a textarea's line breaks as \r\n, the hidden copy
        # in the overview as \n: one form, so the same text goes either way.
        return self.cleaned_data["wish"].replace("\r\n", "\n")


def card_context(
    request, instance: Settings, form: FeedbackForm | None = None, preview=False, failed=False
) -> dict:
    """What _feedback.html shows. preview needs a valid form: the overview
    is made from its cleaned data."""
    form = form or FeedbackForm(initial={"organisation": instance.feedback_organisation})
    context = {
        "show_feedback_card": True,
        "feedback_form": form,
        "feedback_preview": preview,
        "feedback_failed": failed,
        "feedback_skipped": instance.feedback_status == feedback.SKIPPED,
        "feedback_sent": instance.feedback_status == feedback.SENT,
        "feedback_just_sent": SENT_PARAM in request.GET,
    }
    if preview:
        data = form.cleaned_data
        context["feedback_outgoing"] = feedback.outgoing(
            data["organisation"], data["wish"], data["email"]
        )
    return context


def render_done_page(request, **card):
    context = {"steps": STEPS, **card_context(request, Settings.load(), **card)}
    return render(request, "core/onboarding_done.html", context)


def render_help_page(request, **card):
    # After a POST the address is /vertel/, outside help's namespace: Hulp
    # stays marked in the menu anyway.
    context = {
        "page": help.render(help.FEEDBACK),
        "nav_section": "help",
        **card_context(request, Settings.load(), **card),
    }
    return render(request, "core/help_page.html", context)


@login_required
@require_POST
def save(request):
    """Overslaan, Controleer gegevens, Aanpassen or Versturen."""
    place = request.POST.get("plek")
    if place not in (DONE_PAGE, HELP_PAGE):
        raise Http404
    instance = Settings.load()
    back = reverse("onboarding_done") if place == DONE_PAGE else help.url(help.FEEDBACK)
    render_page = render_done_page if place == DONE_PAGE else render_help_page

    if "overslaan" in request.POST and place == DONE_PAGE:
        # Overslaan is only on the done page, and only while it asks (a
        # second tab could still show the question after sending).
        if instance.feedback_status == feedback.NOT_ASKED:
            instance.feedback_status = feedback.SKIPPED
            instance.save(update_fields=["feedback_status", "updated_at"])
        return redirect(back)

    form = FeedbackForm(request.POST)
    if not form.is_valid() or "aanpassen" in request.POST:
        return render_page(request, form=form)
    if "versturen" not in request.POST:
        return render_page(request, form=form, preview=True)

    data = form.cleaned_data
    try:
        feedback.send(data["organisation"], data["wish"], data["email"])
    except feedback.SendError:
        return render_page(request, form=form, preview=True, failed=True)
    instance.feedback_organisation = data["organisation"]
    instance.feedback_status = feedback.SENT
    instance.save(update_fields=["feedback_organisation", "feedback_status", "updated_at"])
    return redirect(f"{back}?{SENT_PARAM}#vertel")
