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
from django.urls import Resolver404, resolve, reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from huismus.business.models import Settings

from . import feedback, help
from .onboarding import Round

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
    settings = Settings.load()
    context = {
        # "Weet ik nog niet" at Je werk: say where the KOR is switched on.
        "kor_later": Round.from_query(request.GET).kor_later and not settings.kor_enabled,
        **card_context(request, settings, **card),
    }
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


# The feedback button on every page (huismus-intern/besluiten.md,
# 2026-11-21): a panel in a popover, the same three steps as the card. With
# HTMX the steps swap inside the panel (HX-Target below); without JS the form
# posts as a plain page.
PANEL_TARGET = "feedback-inhoud"


class QuickFeedbackForm(forms.Form):
    """What the feedback button asks. The page and the picture of the screen
    are filled in by the page and feedback.js; both may stay empty."""

    prefix = "fb"

    kind = forms.ChoiceField(
        label=_("Soort"),
        choices=feedback.KIND_CHOICES,
        initial="probleem",
        widget=forms.RadioSelect,
    )
    message = forms.CharField(
        label=_("Vertel het in je eigen woorden"),
        max_length=feedback.MAX_WISH,
        widget=forms.Textarea(attrs={"rows": 4}),
    )
    email = forms.EmailField(
        label=_("E-mailadres"),
        help_text=_("Alleen als de appbouwer je iets mag terugvragen."),
        max_length=feedback.MAX_EMAIL,
        required=False,
    )
    page = forms.CharField(required=False, widget=forms.HiddenInput)
    image = forms.CharField(required=False, widget=forms.HiddenInput)

    def clean_message(self):
        return self.cleaned_data["message"].replace("\r\n", "\n")

    def picture(self):
        """The picture to show in the form again: only a real PNG, never a
        posted value that clean_image would refuse (no other address in <img>)."""
        value = self["image"].value() or ""
        return value if feedback.image_bytes(value) else ""

    def clean_page(self):
        """A path of this app, or nothing: it goes to the site as it is."""
        page = self.cleaned_data["page"]
        if len(page) > feedback.MAX_PAGE or not page.startswith("/") or page.startswith("//"):
            return ""
        try:
            resolve(page)
        except Resolver404:
            return ""
        return page

    def clean_image(self):
        image = self.cleaned_data["image"]
        if image and feedback.image_bytes(image) is None:
            raise forms.ValidationError(_("Deze afbeelding kan niet mee. Maak hem opnieuw."))
        return image


def _panel(request, form, state, failed=False):
    instance = Settings.load()
    context = {"fb_form": form, "fb_state": state, "fb_failed": failed}
    if state == "preview":
        data = form.cleaned_data
        context["fb_image"] = data["image"]
        context["fb_outgoing"] = feedback.quick_outgoing(
            instance,
            data["kind"],
            data["message"],
            data["email"],
            data["page"],
            bool(data["image"]),
        )
    if request.headers.get("HX-Target") == PANEL_TARGET:
        return render(request, "core/_feedback_panel.html", context)
    return render(request, "core/feedback_page.html", {**context, "fb_in_page": True})


@login_required
@require_POST
def quick(request):
    """Controleer wat er meegaat, Aanpassen or Versturen, from the panel.
    Invalid or Aanpassen: the form again. No button (Controleer): the
    overview. Versturen with a valid form: send. clean_image already checked
    the picture, so image_bytes gives its bytes here."""
    form = QuickFeedbackForm(request.POST)
    if not form.is_valid() or "aanpassen" in request.POST:
        return _panel(request, form, "form")
    if "versturen" not in request.POST:
        return _panel(request, form, "preview")
    data = form.cleaned_data
    try:
        feedback.send_quick(
            Settings.load(),
            data["kind"],
            data["message"],
            data["email"],
            data["page"],
            feedback.image_bytes(data["image"]) if data["image"] else None,
        )
    except feedback.SendError:
        return _panel(request, form, "preview", failed=True)
    return _panel(request, QuickFeedbackForm(), "sent")
