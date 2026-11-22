# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Hoe gebruik je Huismus? (huismus/core/feedback.py and feedback_views.py):
what goes, how it is sent, and the card on the done page and on Hulp."""

import email
import email.policy
import io
import json
import re
import urllib.error
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

from huismus.business.models import Settings
from huismus.core import feedback
from huismus.core.updates import current_version

ISSUE_FORMS = Path(__file__).resolve().parents[2] / ".github" / "ISSUE_TEMPLATE"
ISSUE_FORM = ISSUE_FORMS / "idee.yml"


def _issue_options(field, form=ISSUE_FORM):
    block = form.read_text(encoding="utf-8").split(f"id: {field}\n")[1]
    block = block.split("validations:")[0]
    return [option.split(" / ")[0] for option in re.findall(r'^\s+- "(.+)"$', block, re.M)]


# What goes and how (huismus/core/feedback.py).


@pytest.mark.parametrize(
    ("desktop", "platform", "expected"),
    [
        (True, "darwin", "mac"),
        (True, "win32", "windows"),
        (False, "linux", "docker"),
        (False, "darwin", "docker"),  # runserver or Docker Desktop on a Mac
    ],
)
def test_huismus_knows_where_it_runs(settings, monkeypatch, desktop, platform, expected):
    settings.DESKTOP = desktop
    monkeypatch.setattr(feedback.sys, "platform", platform)
    assert feedback.runs_on() == expected


def test_the_form_gets_the_answers_and_what_huismus_fills_in(settings, monkeypatch, db):
    settings.DESKTOP = True
    monkeypatch.setattr(feedback.sys, "platform", "win32")
    Settings.objects.filter(pk=Settings.load().pk).update(legal_entity="stichting")
    data = feedback.form_data("Uren bijhouden", "a@example.com", "en")
    assert data == {
        "_wpcf7_unit_tag": feedback.UNIT_TAG,
        "_wpcf7_container_post": str(feedback.PAGE_ID),
        "rechtsvorm": "stichting",
        "btw": "btw",
        "gebruik": "Desktop-app op Windows",
        "wens": "Uren bijhouden",
        "email": "a@example.com",
        "versie": current_version(),
        "taal": "en",
        "btw_verlegd": "nee",
        "factuurtaal": "nl",
    }


@pytest.mark.parametrize(
    ("text", "language", "reverse_charge", "invoice_language"),
    [
        ("", "nl", "nee", "nl"),
        ("  \n", "nl", "nee", "nl"),  # only spaces: nothing under a verlegd line
        ("Btw verlegd naar de afnemer.", "en", "ja", "en"),
    ],
)
def test_reverse_charge_and_invoice_language_come_from_the_settings(
    db, text, language, reverse_charge, invoice_language
):
    """Only whether there is a text, never the text itself (#268)."""
    instance = Settings.load()
    instance.reverse_charge_text = text
    instance.default_language = language
    instance.save()
    data = feedback.form_data("", "", "nl")
    assert (data["btw_verlegd"], data["factuurtaal"]) == (reverse_charge, invoice_language)
    if text.strip():
        assert not any(text.strip() in value for value in data.values())


def test_the_overview_shows_every_field_that_goes(db):
    """Nothing goes that the user didn't see: one line per form field."""
    with translation.override("nl"):
        shown = {str(label): str(value) for label, value in feedback.outgoing("", "", "nl")}
    sent = feedback.form_data("", "", "nl")
    assert len(shown) == len([key for key in sent if not key.startswith("_wpcf7")])
    assert shown["Rechtsvorm"] == "niet ingevuld"
    assert shown["Btw"] == "btw op facturen, of nog niet gekozen"
    assert shown["Draait op"] == "Docker, op een server of NAS"
    assert shown["Versie"] == sent["versie"]
    assert shown["Taal van de app"] == "Nederlands"
    assert shown["Btw verlegd"] == "Nee"
    assert shown["Taal van je facturen"] == "Nederlands"


def test_the_overview_says_reverse_charge_and_invoice_language_in_english(db):
    instance = Settings.load()
    instance.reverse_charge_text = "VAT reverse charged."
    instance.default_language = "en"
    instance.save()
    with translation.override("en"):
        shown = {str(label): str(value) for label, value in feedback.outgoing("", "", "en")}
    assert shown["Reverse charge"] == "Yes"
    assert shown["Language of your invoices"] == "English"


def test_the_profile_goes_as_it_is_in_every_language(db):
    Settings.objects.filter(pk=Settings.load().pk).update(legal_entity="bv", kor_enabled=True)
    for language in ("nl", "en"):
        data = feedback.form_data("", "", language)
        assert (data["rechtsvorm"], data["btw"]) == ("bv", "kor")
    assert "organisatie" not in data


@pytest.mark.parametrize(
    ("entity", "kor", "exempt", "legal_form", "vat"),
    [
        ("bv", True, False, "Bv", "met KOR"),
        ("vof", False, True, "Vof", "geen btw om een andere reden"),
        ("", False, False, "niet ingevuld", "btw op facturen, of nog niet gekozen"),
    ],
)
def test_the_overview_shows_legal_form_and_vat_from_the_profile(
    db, entity, kor, exempt, legal_form, vat
):
    Settings.objects.filter(pk=Settings.load().pk).update(
        legal_entity=entity, kor_enabled=kor, vat_exempt=exempt
    )
    with translation.override("nl"):
        shown = {str(label): str(value) for label, value in feedback.outgoing("", "", "nl")}
    assert (shown["Rechtsvorm"], shown["Btw"]) == (legal_form, vat)


def test_the_overview_says_not_filled_in_in_english(db):
    with translation.override("en"):
        shown = {str(label): str(value) for label, value in feedback.outgoing("", "", "en")}
    assert shown["Legal form"] == "not filled in"


def test_an_old_card_answer_does_not_go(db):
    # Before #302 the card asked the organisation; it stays only for the
    # suggestion on Instellingen › Bedrijf.
    Settings.objects.filter(pk=Settings.load().pk).update(feedback_organisation="bv")
    assert feedback.form_data("", "", "nl")["rechtsvorm"] == ""


def test_another_language_is_sent_as_dutch(db):
    assert feedback.form_data("", "", "de")["taal"] == "nl"


def test_the_organisations_match_the_issue_form():
    """Same choices as the issue form "Idee of iets wat je mist", whose
    options read "Nederlands / English" (huismus-intern/besluiten.md, 2026-11-01)."""
    assert [text for _key, text, _label in feedback.ORGANISATIONS] == _issue_options("organisatie")


def test_where_it_runs_is_an_option_of_the_issue_form():
    assert {text for _key, text, _label in feedback.PLATFORMS} <= set(_issue_options("gebruik"))


def test_the_bug_form_asks_where_it_runs_with_the_same_choices():
    bug_form = ISSUE_FORMS / "bug.yml"
    assert _issue_options("gebruik", bug_form) == [text for _k, text, _l in feedback.PLATFORMS]


@pytest.mark.parametrize("choices", [feedback.ORGANISATIONS, feedback.PLATFORMS])
def test_the_dutch_label_is_the_text_on_the_form(choices):
    """Two copies of each text: the one for the form and the translatable
    label. Change one, change the other."""
    with translation.override("nl"):
        assert [str(label) for _key, _text, label in choices] == [
            text for _key, text, _label in choices
        ]


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _site_says(monkeypatch, answer):
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        if isinstance(answer, Exception):
            raise answer
        return _Answer(json.dumps(answer).encode())

    monkeypatch.setattr(feedback.urllib.request, "urlopen", urlopen)
    return sent


def test_send_posts_the_form_fields_to_contact_form_7(monkeypatch, db):
    sent = _site_says(monkeypatch, {"status": "mail_sent", "message": "Bedankt"})
    feedback.send("Offertes online", "", "nl")
    (request,) = sent
    assert request.full_url == feedback.SEND_URL
    assert request.get_method() == "POST"
    assert request.get_header("User-agent") == f"Huismus/{current_version()}"
    message = email.message_from_bytes(
        f"Content-Type: {request.get_header('Content-type')}\r\n\r\n".encode() + request.data,
        policy=email.policy.HTTP,
    )
    fields = {
        part.get_param("name", header="content-disposition"): part.get_content().strip()
        for part in message.iter_parts()
    }
    assert fields == feedback.form_data("Offertes online", "", "nl")


def test_send_keeps_line_breaks_and_quotes_in_what_you_miss(monkeypatch, db):
    sent = _site_says(monkeypatch, {"status": "mail_sent"})
    wish = 'Regel 1\r\nRegel "2"\n--huismus-nep--'
    feedback.send(wish, "", "nl")
    message = email.message_from_bytes(
        f"Content-Type: {sent[0].get_header('Content-type')}\r\n\r\n".encode() + sent[0].data,
        policy=email.policy.HTTP,
    )
    parts = {
        part.get_param("name", header="content-disposition"): part.get_payload()
        for part in message.iter_parts()
    }
    assert parts["wens"].removesuffix("\r\n") == wish


def test_an_answer_that_is_not_an_object_is_a_failure(monkeypatch, db):
    _site_says(monkeypatch, ["mail_sent"])
    with pytest.raises(feedback.SendError):
        feedback.send("", "", "nl")


@pytest.mark.parametrize(
    "answer",
    [
        {"status": "spam", "message": "Er is een fout opgetreden"},
        {"status": "validation_failed", "message": "Fouten"},
        urllib.error.URLError("offline"),
        TimeoutError("traag"),
    ],
)
def test_send_fails_unless_the_site_mailed_it(monkeypatch, answer, db):
    _site_says(monkeypatch, answer)
    with pytest.raises(feedback.SendError):
        feedback.send("", "", "nl")


def test_send_fails_on_an_answer_that_is_not_json(monkeypatch, db):
    monkeypatch.setattr(
        feedback.urllib.request, "urlopen", lambda request, timeout: _Answer(b"<html>")
    )
    with pytest.raises(feedback.SendError):
        feedback.send("", "", "nl")


# The card on the done page and on Hulp (huismus/core/feedback_views.py).


@pytest.fixture
def logged_in(client, db):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


@pytest.fixture
def sends(monkeypatch):
    """Records what would be sent; never reaches the site."""
    calls = []
    monkeypatch.setattr(feedback, "send", lambda *args: calls.append(args))
    return calls


def _post(client, button, place="welkom", **answers):
    data = {"plek": place, "wish": "", "email": "", button: ""}
    data.update(answers)
    return client.post(reverse("feedback"), data)


def test_the_done_page_asks_how_you_use_huismus(logged_in):
    page = logged_in.get(reverse("onboarding_done")).content.decode()
    assert 'id="vertel"' in page
    assert "Hoe gebruik je Huismus?" in page
    assert 'name="wish"' in page
    # The profile says the legal form and VAT (#302): the card doesn't ask.
    assert 'name="organisation"' not in page
    assert "Wat voor organisatie heb je?" not in page
    assert 'name="overslaan"' in page
    assert "Krijnsen" not in page


def test_the_card_says_what_you_miss_goes_on_github_and_your_email_not(logged_in):
    # The site turns what you miss into a public issue (plugin
    # Huismus-formulier); the card has to say so before anyone types it.
    page = logged_in.get(reverse("onboarding_done")).content.decode()
    assert "Komt als idee op GitHub, waar anderen het kunnen lezen. Je e-mailadres niet." in page


def test_see_what_goes_shows_everything_and_sends_nothing(logged_in, sends):
    response = _post(logged_in, "bekijk", wish="Uren & <b>projecten</b>", email="a@example.com")
    page = response.content.decode()
    assert response.status_code == 200
    assert 'id="vertel-wat-er-gaat"' in page
    for value in (
        "Rechtsvorm",
        "niet ingevuld",
        "Uren &amp; &lt;b&gt;projecten&lt;/b&gt;",
        "a@example.com",
    ):
        assert value in page
    assert "Docker, op een server of NAS" in page
    assert current_version() in page
    assert 'name="versturen"' in page
    assert "Btw verlegd" in page
    assert "Taal van je facturen" in page
    assert sends == []
    assert Settings.load().feedback_status == ""


def test_send_sends_and_keeps_only_that_it_was_sent(logged_in, sends):
    Settings.objects.filter(pk=Settings.load().pk).update(feedback_organisation="bv")
    response = _post(logged_in, "versturen", wish="Uren", email="a@example.com")
    assert response.status_code == 302
    assert response["Location"] == reverse("onboarding_done") + "?verstuurd#vertel"
    assert sends == [("Uren", "a@example.com")]
    settings = Settings.load()
    # The old answer stays as it was, for the legal form suggestion.
    assert (settings.feedback_organisation, settings.feedback_status) == ("bv", "sent")

    page = logged_in.get(response["Location"]).content.decode()
    assert 'id="vertel-verstuurd"' in page
    # Back on the done page later: it no longer asks.
    assert 'id="vertel"' not in logged_in.get(reverse("onboarding_done")).content.decode()


def test_a_failed_send_says_so_and_keeps_the_overview(logged_in, monkeypatch):
    def fail(*args):
        raise feedback.SendError("spam")

    monkeypatch.setattr(feedback, "send", fail)
    page = _post(logged_in, "versturen", wish="Uren").content.decode()
    assert 'id="vertel-mislukt"' in page
    assert 'id="vertel-wat-er-gaat"' in page
    assert Settings.load().feedback_status == ""


def test_change_goes_back_to_the_form_with_the_answers(logged_in, sends):
    page = _post(logged_in, "aanpassen", wish="Uren bijhouden").content.decode()
    assert 'name="wish"' in page
    assert "Uren bijhouden" in page
    assert 'id="vertel-wat-er-gaat"' not in page


def test_nothing_is_needed(logged_in, sends):
    # Both fields empty: only the profile goes.
    response = _post(logged_in, "versturen")
    assert response.status_code == 302
    assert sends == [("", "")]


def test_an_email_address_must_be_one(logged_in, sends):
    response = _post(logged_in, "bekijk", email="geen-adres")
    assert 'aria-invalid="true"' in response.content.decode()
    assert 'id="vertel-wat-er-gaat"' not in response.content.decode()


def test_after_skipping_the_done_page_no_longer_asks(logged_in):
    response = logged_in.post(reverse("feedback"), {"plek": "welkom", "overslaan": ""})
    assert response["Location"] == reverse("onboarding_done")
    assert Settings.load().feedback_status == "skipped"
    page = logged_in.get(reverse("onboarding_done")).content.decode()
    assert 'id="vertel"' not in page
    assert reverse("contacts:create") in page


def test_skipping_after_sending_keeps_it_sent(logged_in, sends):
    _post(logged_in, "versturen")
    logged_in.post(reverse("feedback"), {"plek": "welkom", "overslaan": ""})
    assert Settings.load().feedback_status == "sent"


def test_the_help_page_always_has_the_form(logged_in, sends):
    logged_in.post(reverse("feedback"), {"plek": "welkom", "overslaan": ""})
    url = reverse("help:page", args=["feedback"])
    page = logged_in.get(url).content.decode()
    assert 'name="wish"' in page
    assert 'name="overslaan"' not in page

    response = _post(logged_in, "versturen", place="hulp")
    assert response["Location"] == url + "?verstuurd#vertel"
    assert 'name="wish"' in logged_in.get(url).content.decode()


def test_hulp_stays_marked_in_the_menu_on_the_overview(logged_in, sends):
    page = _post(logged_in, "bekijk", place="hulp").content.decode()
    assert re.search(r'href="/hulp/" aria-current="page"', page)


def test_the_card_is_in_english_with_the_same_values_on_the_form(logged_in, sends):
    Settings.objects.filter(pk=Settings.load().pk).update(legal_entity="stichting")
    logged_in.cookies["django_language"] = "en"
    page = _post(logged_in, "bekijk").content.decode()
    assert "How do you use Huismus?" in page
    assert "Foundation" in page
    assert "English" in page


def test_an_unknown_place_is_refused(logged_in, sends):
    assert _post(logged_in, "versturen", place="elders").status_code == 404
    assert sends == []


def test_the_card_needs_a_login(client, db, sends):
    response = client.post(reverse("feedback"), {"plek": "welkom", "versturen": ""})
    assert response.status_code == 302
    assert sends == []


def test_on_hulp_the_card_skips_the_intro_the_help_text_already_gives(logged_in):
    intro = "Huismus houdt niet bij wie het gebruikt. Vertel"
    assert intro in logged_in.get(reverse("onboarding_done")).content.decode()
    assert intro not in logged_in.get(reverse("help:page", args=["feedback"])).content.decode()


def test_skipping_from_hulp_does_nothing(logged_in):
    logged_in.post(reverse("feedback"), {"plek": "hulp", "overslaan": ""})
    assert Settings.load().feedback_status == ""
