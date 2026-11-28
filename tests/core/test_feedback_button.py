# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The feedback button on every page (huismus/core/feedback_views.py, quick;
huismus-intern/besluiten.md, 2026-11-21): what goes, how you work, the
picture of the screen, and the three steps with and without HTMX. The site
is never reached."""

import base64
import email
import email.policy
import io
import json
import re
import zlib

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import translation

from huismus.business.models import Settings
from huismus.core import feedback
from huismus.core.updates import current_version


def _png(size=1):
    """A real, tiny PNG of size × size grey pixels."""

    def chunk(kind, data):
        body = kind + data
        return len(data).to_bytes(4, "big") + body + zlib.crc32(body).to_bytes(4, "big")

    header = size.to_bytes(4, "big") * 2 + bytes([8, 0, 0, 0, 0])
    rows = b"".join(b"\x00" + b"\x80" * size for _ in range(size))
    return (
        feedback.PNG_SIGNATURE
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(rows))
        + chunk(b"IEND", b"")
    )


def _data_url(content):
    return feedback.IMAGE_PREFIX + base64.b64encode(content).decode()


# ---------- What goes ----------


def test_how_you_work_says_what_the_settings_say():
    instance = Settings(legal_entity="bv", kor_enabled=True, default_language="nl")
    with translation.override("nl"):
        assert feedback.how_you_work(instance) == (
            "Bv · met KOR · btw verlegd: nee · facturen in het Nederlands"
        )


def test_how_you_work_names_the_legal_form_not_the_old_card_answer():
    instance = Settings(feedback_organisation="bv", kor_enabled=True, default_language="nl")
    with translation.override("nl"):
        assert feedback.how_you_work(instance).startswith("met KOR · ")


def test_how_you_work_without_the_kor_or_a_legal_form():
    """The start keeps no answers: KOR off may be VAT or "don't know yet"."""
    instance = Settings(kor_enabled=False, reverse_charge_text="Btw verlegd", default_language="en")
    with translation.override("nl"):
        assert feedback.how_you_work(instance) == (
            "btw op facturen, of nog niet gekozen · btw verlegd: ja · facturen in het Engels"
        )


def test_how_you_work_with_no_vat_for_another_reason():
    instance = Settings(vat_exempt=True, default_language="nl")
    with translation.override("nl"):
        assert feedback.how_you_work(instance) == (
            "geen btw om een andere reden · btw verlegd: nee · facturen in het Nederlands"
        )


def test_the_button_sends_the_kind_page_and_how_you_work_in_dutch(settings):
    settings.DESKTOP = False
    instance = Settings(legal_entity="stichting", kor_enabled=True)
    with translation.override("en"):
        data = feedback.quick_form_data(
            instance, "probleem", "Knop doet niets", "", "/facturen/", "en"
        )
    assert data == {
        "_wpcf7_unit_tag": feedback.UNIT_TAG,
        "_wpcf7_container_post": str(feedback.PAGE_ID),
        "rechtsvorm": "stichting",
        "btw": "kor",
        "gebruik": "Docker, op een server of NAS",
        "soort": "Iets werkt niet",
        "wens": "Knop doet niets",
        "pagina": "/facturen/",
        "werkwijze": "Stichting · met KOR · btw verlegd: nee · facturen in het Nederlands",
        "email": "",
        "versie": current_version(),
        "taal": "en",
    }


def test_without_a_legal_form_it_goes_empty():
    data = feedback.quick_form_data(Settings(), "idee", "x", "", "", "nl")
    assert data["rechtsvorm"] == ""
    assert "organisatie" not in data


def test_the_overview_shows_every_field_that_goes():
    """Nothing goes that the user didn't see: a line per field, and one for the picture."""
    instance = Settings()
    with translation.override("nl"):
        shown = dict(
            (str(label), value)
            for label, value in feedback.quick_outgoing(instance, "vraag", "Hoe?", "", "/", True)
        )
    sent = feedback.quick_form_data(instance, "vraag", "Hoe?", "", "/", "nl")
    # The picture has its own line.
    fields = [key for key in sent if not key.startswith("_wpcf7")]
    assert len(shown) == len(fields) + 1
    assert str(shown["Soort"]) == "Vraag"
    assert str(shown["Afbeelding"]) == "ja, hierboven"
    assert shown["Hoe je werkt"] == feedback.how_you_work(instance)
    assert (str(shown["Rechtsvorm"]), str(shown["Btw"])) == (
        "niet ingevuld",
        "btw op facturen, of nog niet gekozen",
    )


@pytest.mark.parametrize("choices", [feedback.KINDS])
def test_the_dutch_label_is_the_text_on_the_form(choices):
    with translation.override("nl"):
        assert [str(label) for _key, _text, label in choices] == [
            text for _key, text, _label in choices
        ]


def test_a_png_data_url_gives_its_bytes():
    png = _png()
    assert feedback.image_bytes(_data_url(png)) == png


@pytest.mark.parametrize(
    "value",
    [
        "data:image/jpeg;base64," + base64.b64encode(b"x").decode(),
        feedback.IMAGE_PREFIX + "niet base64!",
        _data_url(b"GIF89a niet een png"),
        _data_url(feedback.PNG_SIGNATURE + b"\0" * feedback.MAX_IMAGE_BYTES),
    ],
)
def test_anything_else_is_not_a_picture(value):
    assert feedback.image_bytes(value) is None


class _Answer(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _site_says(monkeypatch, answer):
    sent = []

    def urlopen(request, timeout):
        sent.append(request)
        return _Answer(json.dumps(answer).encode())

    monkeypatch.setattr(feedback.urllib.request, "urlopen", urlopen)
    return sent


def _parts(request):
    message = email.message_from_bytes(
        f"Content-Type: {request.get_header('Content-type')}\r\n\r\n".encode() + request.data,
        policy=email.policy.HTTP,
    )
    return {
        part.get_param("name", header="content-disposition"): part for part in message.iter_parts()
    }


def test_send_quick_posts_the_fields_and_the_picture_as_a_file(monkeypatch):
    sent = _site_says(monkeypatch, {"status": "mail_sent"})
    png = _png(3)
    feedback.send_quick(Settings(), "idee", "Uren", "", "/", png, "nl")
    (request,) = sent
    assert request.get_header("User-agent") == f"Huismus/{current_version()}"
    parts = _parts(request)
    picture = parts.pop("afbeelding")
    assert picture.get_filename() == "huismus.png"
    assert picture.get_content_type() == "image/png"
    assert picture.get_payload(decode=True) == png
    fields = {name: part.get_payload(decode=True).decode().strip() for name, part in parts.items()}
    assert fields == feedback.quick_form_data(Settings(), "idee", "Uren", "", "/", "nl")


def test_send_quick_without_a_picture_sends_no_file(monkeypatch):
    sent = _site_says(monkeypatch, {"status": "mail_sent"})
    feedback.send_quick(Settings(), "vraag", "Hoe?", "", "", None, "nl")
    assert "afbeelding" not in _parts(sent[0])


def test_send_quick_fails_unless_the_site_mailed_it(monkeypatch):
    _site_says(monkeypatch, {"status": "validation_failed"})
    with pytest.raises(feedback.SendError):
        feedback.send_quick(Settings(), "vraag", "Hoe?", "", "", None, "nl")


# ---------- The button and its panel ----------


@pytest.fixture
def logged_in(client, db):
    client.force_login(get_user_model().objects.create_user(username="lotte", password="x"))
    return client


@pytest.fixture
def sends(monkeypatch):
    calls = []
    monkeypatch.setattr(feedback, "send_quick", lambda *args: calls.append(args))
    return calls


def _post(client, button=None, htmx=True, **answers):
    data = {
        "fb-kind": "probleem",
        "fb-message": "Knop doet niets",
        "fb-email": "lotte@example.com",
        "fb-page": "/facturen/",
    }
    data.update({f"fb-{key}": value for key, value in answers.items()})
    if button:
        data[button] = ""
    headers = {"HX-Request": "true", "HX-Target": "feedback-inhoud"} if htmx else {}
    return client.post(reverse("feedback_quick"), data, headers=headers)


def test_every_page_has_the_button_with_the_page_it_is_on(logged_in):
    page = logged_in.get(reverse("documents:list")).content.decode()
    assert 'id="feedback-knop"' in page
    assert 'popovertarget="feedback-paneel"' in page
    assert 'name="fb-page" value="/facturen/"' in page


def test_the_login_page_has_no_button(client, db):
    assert 'id="feedback-knop"' not in client.get(reverse("login")).content.decode()


def test_check_shows_everything_and_sends_nothing(logged_in, sends):
    Settings.load()
    response = _post(logged_in, image=_data_url(_png()))
    text = response.content.decode()
    assert "<html" not in text  # only the panel, for HTMX
    assert "Dit gaat naar de appbouwer" in text
    assert 'id="fb-wat-er-gaat"' in text
    assert "Knop doet niets" in text
    assert "/facturen/" in text
    assert "btw op facturen, of nog niet gekozen" in text
    # Owner, 2026-11-28: it goes to the maker only, not to GitHub.
    assert "GitHub" not in text
    assert 'src="data:image/png;base64,' in text
    assert sends == []


def test_send_sends_the_picture_as_bytes(logged_in, sends):
    png = _png(2)
    response = _post(logged_in, "versturen", image=_data_url(png))
    assert 'id="fb-verstuurd"' in response.content.decode()
    assert "Alleen de appbouwer leest het." in response.content.decode()
    ((instance, kind, message, mail, page, image),) = sends
    assert (kind, message, mail, page, image) == (
        "probleem",
        "Knop doet niets",
        "lotte@example.com",
        "/facturen/",
        png,
    )
    assert isinstance(instance, Settings)


def test_without_a_picture_none_goes(logged_in, sends):
    _post(logged_in, "versturen")
    assert sends[0][-1] is None


def test_a_page_that_is_not_ours_goes_as_nothing(logged_in, sends):
    _post(logged_in, "versturen", page="https://example.com/")
    _post(logged_in, "versturen", page="/bestaat-niet/")
    assert [call[4] for call in sends] == ["", ""]


def test_a_broken_picture_is_refused_and_nothing_goes(logged_in, sends):
    response = _post(logged_in, "versturen", image="data:image/png;base64,AAAA")
    assert "Deze afbeelding kan niet mee" in response.content.decode()
    assert sends == []


def test_a_message_is_needed(logged_in, sends):
    response = _post(logged_in, "versturen", message="")
    assert 'class="error"' in response.content.decode()
    assert sends == []


def test_an_email_address_is_needed(logged_in, sends):
    # Owner, 2026-11-28 (#368): the maker must be able to answer.
    response = _post(logged_in, "versturen", email="")
    assert 'class="error"' in response.content.decode()
    assert sends == []


def test_the_button_fills_in_the_address_of_your_business(logged_in):
    Settings.objects.filter(pk=Settings.load().pk).update(email="info@voorbeeld.nl")
    page = logged_in.get(reverse("documents:list")).content.decode()
    assert re.search(r'name="fb-email" value="info@voorbeeld.nl"[^>]*required', page)


def test_change_goes_back_to_the_form_with_the_picture(logged_in, sends):
    response = _post(logged_in, "aanpassen", image=_data_url(_png()), email="lotte@example.com")
    text = response.content.decode()
    assert "Wat wil je kwijt?" in text
    assert 'value="lotte@example.com"' in text
    assert (
        'data-fb-voorbeeld alt="Je afbeelding van het scherm" src="data:image/png;base64,' in text
    )
    assert sends == []


def test_a_failed_send_keeps_the_overview(logged_in, monkeypatch):
    def fail(*args):
        raise feedback.SendError("offline")

    monkeypatch.setattr(feedback, "send_quick", fail)
    text = _post(logged_in, "versturen").content.decode()
    assert 'id="fb-mislukt"' in text
    assert 'name="versturen"' in text


def test_without_htmx_it_is_a_page_of_its_own(logged_in, sends):
    text = _post(logged_in, htmx=False).content.decode()
    assert "<html" in text
    assert 'class="card card-pad fb-pagina"' in text
    # No second button and panel on the page that is the panel.
    assert 'id="feedback-knop"' not in text


def test_the_panel_needs_a_login(client, db, sends):
    response = _post(client, "versturen")
    assert response.status_code == 302
    assert sends == []


def test_the_panel_is_in_english(logged_in, sends):
    logged_in.cookies["django_language"] = "en"
    with translation.override("en"):
        text = _post(logged_in).content.decode()
    assert "Knop doet niets" in text
    assert "Dit gaat naar de appbouwer" not in text


def test_a_refused_value_is_never_shown_as_a_picture(logged_in, sends):
    text = _post(logged_in, image="https://example.com/x.png").content.decode()
    assert 'src="https://example.com' not in text


def test_without_an_address_it_says_so_in_english(logged_in, sends):
    logged_in.cookies["django_language"] = "en"
    text = _post(logged_in, "versturen", email="", htmx=False).content.decode()
    assert "Enter your email address." in text
    assert sends == []


def test_without_a_business_address_the_field_starts_empty(logged_in):
    # A fresh install: no settings row yet, and showing the button makes none.
    Settings.objects.all().delete()
    page = logged_in.get(reverse("documents:list")).content.decode()
    assert re.search(r'name="fb-email"(?! value=)[^>]*required', page)
    assert not Settings.objects.exists()
