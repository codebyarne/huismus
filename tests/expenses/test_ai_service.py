# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user's own AI service (SPEC.md M20, part 3; huismus/expenses/
ai_service.py), against the fake in tests/ai_fakes.py: no real service is
ever called."""

import socket

import pytest

from huismus.expenses import ai_service
from huismus.expenses.ai_service import Config, ServiceError
from tests.ai_fakes import KEY
from tests.redirect_fakes import Catcher, Redirector


def _config(fake, **changes) -> Config:
    values = {"provider": "other", "url": fake.url, "model": "nep-model", "key": KEY}
    return Config(**{**values, **changes})


def test_off_without_a_file():
    assert ai_service.load() == Config()
    assert not ai_service.is_on()


def test_saved_owner_only_and_read_back(settings):
    ai_service.save(Config("mistral", "https://api.mistral.ai/v1", "mistral-medium-latest", "k"))
    path = settings.DATA_DIR / ai_service.CONFIG_FILE_NAME
    assert path.stat().st_mode & 0o777 == 0o600
    assert ai_service.load().key == "k"
    assert ai_service.is_on()
    assert ai_service.name() == "Mistral"


def test_turn_off_forgets_the_key():
    ai_service.save(Config("openai", "https://api.openai.com/v1", "gpt-5-mini", "k"))
    ai_service.turn_off()
    assert ai_service.load() == Config()


def test_another_service_is_named_by_its_host():
    assert ai_service.name(Config("other", "https://ai.example.test/v1", "m", "k")) == (
        "ai.example.test"
    )


@pytest.mark.parametrize(
    "url",
    [
        "http://localhost:11434/v1",
        "http://127.0.0.1:11434/v1",
        "http://192.168.1.20:11434/v1",
        "http://10.0.0.5/v1",
        "http://nas.local:11434/v1",
        "http://host.docker.internal:11434/v1",
    ],
)
def test_http_only_nearby(url):
    assert ai_service.is_nearby(url)
    assert ai_service.address_error(url) is None


@pytest.mark.parametrize("url", ["http://api.example.test/v1", "http://8.8.8.8/v1"])
def test_http_over_the_internet_is_refused(url):
    assert not ai_service.is_nearby(url)
    assert "https://" in ai_service.address_error(url)


@pytest.mark.parametrize("url", ["", "ftp://x.test", "api.mistral.ai", "https://"])
def test_not_an_address(url):
    assert ai_service.address_error(url)


def test_chat_sends_model_key_and_content(ai_fake):
    ai_fake.answer("Hallo")
    content = [{"type": "text", "text": "Zeg hallo"}]
    assert ai_service.chat(_config(ai_fake), content) == "Hallo"
    request = ai_fake.requests[-1]
    assert request["model"] == "nep-model"
    assert request["messages"] == [{"role": "user", "content": content}]
    assert ai_fake.authorizations[-1] == f"Bearer {KEY}"


def test_no_key_sends_no_authorization(ai_fake):
    ai_fake.key = ""
    ai_service.chat(_config(ai_fake, key=""), [{"type": "text", "text": "x"}])
    assert ai_fake.authorizations[-1] == ""


def test_a_wrong_key_is_refused(ai_fake):
    with pytest.raises(ServiceError) as error:
        ai_service.chat(_config(ai_fake, key="fout"), [{"type": "text", "text": "x"}])
    assert error.value.reason == ai_service.REFUSED
    assert "fout" not in str(error.value)


def test_an_unknown_model(ai_fake):
    with pytest.raises(ServiceError) as error:
        ai_service.chat(_config(ai_fake, model="bestaat-niet"), [{"type": "text", "text": "x"}])
    assert error.value.reason == ai_service.NO_MODEL


@pytest.mark.parametrize(
    ("status", "reason"),
    [(429, ai_service.BUSY), (500, ai_service.SERVER), (503, ai_service.SERVER)],
)
def test_busy_or_broken(ai_fake, status, reason):
    ai_fake.answer((status, {"error": {"message": "even niet"}}))
    with pytest.raises(ServiceError) as error:
        ai_service.chat(_config(ai_fake), [{"type": "text", "text": "x"}])
    assert error.value.reason == reason


def test_a_model_that_reads_no_images(ai_fake):
    ai_fake.answer((400, {"error": {"message": "This model does not support image input"}}))
    with pytest.raises(ServiceError) as error:
        ai_service.test_connection(_config(ai_fake))
    assert error.value.reason == ai_service.NO_IMAGES


def test_unreachable():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    config = Config("other", f"http://127.0.0.1:{port}/v1", "m", "")
    with pytest.raises(ServiceError) as error:
        ai_service.chat(config, [{"type": "text", "text": "x"}])
    assert error.value.reason == ai_service.UNREACHABLE


def test_no_answer_in_time_may_have_been_paid(ai_fake):
    ai_fake.delay = 1.0
    with pytest.raises(ServiceError) as error:
        ai_service.chat(_config(ai_fake), [{"type": "text", "text": "x"}], timeout=0.2)
    assert error.value.reason == ai_service.TIMEOUT_REASON


def test_a_wrong_path_is_an_address_that_does_not_answer(ai_fake):
    config = _config(ai_fake, url=ai_fake.url.removesuffix("/v1") + "/verkeerd")
    with pytest.raises(ServiceError) as error:
        ai_service.chat(config, [{"type": "text", "text": "x"}])
    assert error.value.reason == ai_service.UNREACHABLE


def test_a_damaged_settings_file_counts_as_off(settings):
    (settings.DATA_DIR / ai_service.CONFIG_FILE_NAME).write_text("{kapot")
    assert ai_service.load() == Config()


def test_an_answer_that_is_not_a_chat_answer(ai_fake):
    ai_fake.answer((200, {"iets": "anders"}))
    with pytest.raises(ServiceError) as error:
        ai_service.chat(_config(ai_fake), [{"type": "text", "text": "x"}])
    assert error.value.reason == ai_service.ANSWER


def test_test_connection_sends_one_image(ai_fake):
    ai_service.test_connection(_config(ai_fake))
    content = ai_fake.requests[-1]["messages"][0]["content"]
    images = [part for part in content if part["type"] == "image_url"]
    assert len(images) == 1
    assert images[0]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_every_reason_has_a_sentence():
    for reason in (
        ai_service.REFUSED,
        ai_service.UNREACHABLE,
        ai_service.BUSY,
        ai_service.SERVER,
        ai_service.NO_MODEL,
        ai_service.NO_IMAGES,
        ai_service.TIMEOUT_REASON,
        ai_service.ANSWER,
    ):
        sentence = ai_service.failure_sentence(reason, Config("mistral", "u", "m-1", "k"))
        assert sentence and "%(" not in sentence


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_a_redirect_is_not_followed_and_takes_no_key_along(status):
    # urllib would follow it and copy "Authorization: Bearer <key>" to
    # whatever the Location says: another host, or plain http://.
    catcher = Catcher()
    redirector = Redirector(status, catcher.url + "v1/chat/completions")
    try:
        config = Config("other", redirector.url + "v1", "nep-model", KEY)
        with pytest.raises(ServiceError) as error:
            ai_service.chat(config, [{"type": "text", "text": "x"}])
        assert error.value.reason == ai_service.UNREACHABLE
        assert catcher.requests == []
        assert KEY not in str(error.value)
    finally:
        redirector.close()
        catcher.close()
