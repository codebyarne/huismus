# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Linking a phone to the desktop app over the user's own Wi-Fi (issue #143,
huismus/core/phones.py): the one-time code in the QR code, the phone's own
cookie, unlinking and turning it all off."""

import json
import os
import stat
from datetime import UTC, datetime, timedelta

import pytest

from huismus.core import phones

NOW = datetime(2026, 11, 28, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def data_dir(settings, tmp_path):
    settings.DATA_DIR = tmp_path
    return tmp_path


def _paired(name="iPhone", now=NOW):
    code = phones.new_code(now=now)
    return phones.pair(code, name, now=now)


def test_nothing_is_on_at_first():
    assert not phones.is_on()
    assert phones.devices() == []


def test_a_code_links_one_phone():
    code = phones.new_code(now=NOW)
    assert phones.is_on()

    token = phones.pair(code, "iPhone", now=NOW)

    assert token
    assert phones.device_for(token, now=NOW)["name"] == "iPhone"
    assert [d["name"] for d in phones.devices()] == ["iPhone"]


def test_a_code_works_once():
    code = phones.new_code(now=NOW)
    assert phones.pair(code, "iPhone", now=NOW)

    assert phones.pair(code, "Android-telefoon", now=NOW) is None
    assert len(phones.devices()) == 1


def test_a_code_expires_after_ten_minutes():
    code = phones.new_code(now=NOW)

    assert phones.pair(code, "iPhone", now=NOW + timedelta(minutes=10, seconds=1)) is None


def test_a_new_code_replaces_the_old_one():
    old = phones.new_code(now=NOW)
    new = phones.new_code(now=NOW)

    assert phones.pair(old, "iPhone", now=NOW) is None
    assert phones.pair(new, "iPhone", now=NOW)


@pytest.mark.parametrize("guess", ["", "wrong", "tökén", None])
def test_a_wrong_code_or_cookie_links_nothing(guess):
    phones.new_code(now=NOW)
    token = _paired()

    assert phones.pair(guess, "iPhone", now=NOW) is None
    assert phones.device_for(guess, now=NOW) is None
    assert phones.device_for(token + "x", now=NOW) is None


def test_the_file_holds_no_code_or_cookie_only_their_hashes(data_dir):
    code = phones.new_code(now=NOW)
    token = phones.pair(code, "iPhone", now=NOW)
    phones.new_code(now=NOW)

    text = (data_dir / phones.FILE_NAME).read_text()
    assert token not in text
    assert code not in text
    json.loads(text)


def test_the_file_is_readable_only_by_huismus(data_dir):
    _paired()

    mode = stat.S_IMODE(os.stat(data_dir / phones.FILE_NAME).st_mode)
    assert mode == 0o600


def test_unlinking_one_phone_keeps_the_others():
    first = _paired("iPhone")
    second = _paired("Android-telefoon")
    first_id = phones.device_for(first, now=NOW)["id"]

    phones.unpair(first_id)

    assert phones.device_for(first, now=NOW) is None
    assert phones.device_for(second, now=NOW)["name"] == "Android-telefoon"


def test_turning_off_removes_every_link_and_the_code():
    token = _paired()
    code = phones.new_code(now=NOW)

    phones.turn_off()

    assert not phones.is_on()
    assert phones.device_for(token, now=NOW) is None
    assert phones.pair(code, "iPhone", now=NOW) is None


def test_last_used_is_written_at_most_once_an_hour(data_dir):
    token = _paired()
    phones.device_for(token, now=NOW + timedelta(minutes=30))
    assert phones.devices()[0]["last_seen"] == NOW.isoformat()

    phones.device_for(token, now=NOW + timedelta(hours=2))

    assert phones.devices()[0]["last_seen"] == (NOW + timedelta(hours=2)).isoformat()


def test_a_phone_unused_for_ninety_days_must_link_again():
    token = _paired()

    assert phones.device_for(token, now=NOW + timedelta(days=89)) is not None
    assert phones.device_for(token, now=NOW + timedelta(days=89 + 91)) is None
    assert phones.devices() == []


def test_a_damaged_file_counts_as_nothing_linked(data_dir):
    (data_dir / phones.FILE_NAME).write_text("{not json")

    assert phones.devices() == []
    assert phones.device_for("anything", now=NOW) is None


@pytest.mark.parametrize(
    ("agent", "name"),
    [
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) Safari", "iPhone"),
        ("Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X)", "iPad"),
        ("Mozilla/5.0 (Linux; Android 15; Pixel 9) Chrome/131 Mobile", "Android-telefoon"),
        ("Mozilla/5.0 (Linux; Android 15; SM-X710) Chrome/131", "Android-tablet"),
        ("", "Telefoon"),
    ],
)
def test_a_phone_is_named_by_its_kind_only(agent, name):
    assert str(phones.phone_name(agent)) == name


@pytest.mark.parametrize(
    ("address", "private"),
    [
        ("192.168.1.23", True),
        ("10.0.0.5", True),
        ("172.16.0.1", True),
        ("172.31.255.254", True),
        ("172.32.0.1", False),
        ("127.0.0.1", False),
        ("100.64.0.1", False),  # carrier-grade NAT, also Tailscale
        ("169.254.10.1", False),
        ("8.8.8.8", False),
        ("::1", False),
        ("fe80::1", False),
        ("not an address", False),
        ("", False),
    ],
)
def test_only_a_home_or_office_network_counts(address, private):
    assert phones.is_home_network(address) is private
