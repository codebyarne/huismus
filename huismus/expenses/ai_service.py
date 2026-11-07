# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The user's own AI service, which reads receipts (SPEC.md M20, part 3;
huismus-intern/besluiten.md, 2026-11-06, "Huismus leest bonnetjes zelf").

One way for every service: the OpenAI-compatible chat API (an address, a
key, a model), which OpenAI, Mistral, Google, Anthropic and Ollama all
speak. A known service only fills in its address and a model to start
with; the user can change both.

The settings live in one file in DATA_DIR, owner-only, because the key is
in it: not in the database, so not in a backup, and never taken from one
(core.backup skips every file whose name starts with FILE_PREFIX), like
the mail password. The key is never shown again after it is saved.
"""

import base64
import ipaddress
import json
import logging
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from PIL import Image, ImageDraw

from huismus.core import no_redirects
from huismus.core.private_files import write_owner_only

logger = logging.getLogger("huismus.receipts")

FILE_PREFIX = "ai-service"
CONFIG_FILE_NAME = f"{FILE_PREFIX}.json"

# Seconds to wait for an answer: reading a photo takes a model a while
# (huismus-intern/besluiten.md, 2026-11-06: three minutes).
TIMEOUT = 180


@dataclass(frozen=True)
class Provider:
    name: str  # in sentences: "Mistral weigert je sleutel."
    label: str  # in the list of services
    url: str
    model: str  # one that reads images


# Stored in data/: never rename the keys. In the order of the list:
# alphabetical, then Ollama and "Andere dienst" (besluit 2026-11-06). The
# models are a start; a service renames its models now and then, so the
# field stays editable.
PROVIDERS = {
    "anthropic": Provider(
        "Anthropic", "Anthropic (Claude)", "https://api.anthropic.com/v1", "claude-haiku-5-5"
    ),
    "gemini": Provider(
        "Google Gemini",
        "Google Gemini",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.5-flash",
    ),
    "mistral": Provider("Mistral", "Mistral", "https://api.mistral.ai/v1", "mistral-medium-latest"),
    "openai": Provider("OpenAI", "OpenAI", "https://api.openai.com/v1", "gpt-5-mini"),
    "ollama": Provider(
        "Ollama",
        gettext_lazy("Ollama (eigen computer of netwerk)"),
        "http://localhost:11434/v1",
        "qwen2.5vl",
    ),
}
OTHER = "other"
OTHER_LABEL = gettext_lazy("Andere dienst")


def choices() -> list[tuple[str, str]]:
    return [(slug, str(p.label)) for slug, p in PROVIDERS.items()] + [(OTHER, str(OTHER_LABEL))]


@dataclass
class Config:
    provider: str = ""  # a key of PROVIDERS, OTHER, or "" when off
    url: str = ""
    model: str = ""
    key: str = ""


def _path() -> Path:
    return Path(settings.DATA_DIR) / CONFIG_FILE_NAME


def load() -> Config:
    """The saved service; off (an empty Config) without the file. A file
    that can't be read counts as off too, with a line in the log: the
    page then offers to set the service up again."""
    try:
        data = json.loads(_path().read_text(encoding="utf-8"))
    except FileNotFoundError:
        return Config()
    except (OSError, ValueError) as error:
        logger.warning("%s niet te lezen: %s", CONFIG_FILE_NAME, error)
        return Config()
    return Config(**{name: str(data.get(name, "")) for name in Config.__dataclass_fields__})


def save(config: Config) -> None:
    write_owner_only(_path(), json.dumps(asdict(config), indent=2))


def turn_off() -> None:
    _path().unlink(missing_ok=True)


def is_on(config: Config | None = None) -> bool:
    config = config or load()
    return bool(config.provider and config.url and config.model)


def name(config: Config | None = None) -> str:
    """The service as the user knows it: "Mistral", or the address's host."""
    config = config or load()
    return provider_name(config.provider, config.url)


def provider_name(provider: str, url: str) -> str:
    if provider in PROVIDERS:
        return PROVIDERS[provider].name
    return urlsplit(url).hostname or url


# -- The address --------------------------------------------------------------


def is_nearby(url: str) -> bool:
    """On this computer or the home network: Ollama on a laptop or a NAS.
    Only there may an address be http, and may the key be left empty."""
    host = (urlsplit(url).hostname or "").lower()
    if host in ("localhost", "host.docker.internal") or host.endswith((".local", ".localhost")):
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return address.is_loopback or address.is_private or address.is_link_local


def address_error(url: str) -> str | None:
    """Why this address can't be used, or None."""
    parts = urlsplit(url)
    # A receipt goes over the internet only encrypted.
    if (
        parts.scheme not in ("https", "http")
        or not parts.hostname
        or (parts.scheme == "http" and not is_nearby(url))
    ):
        return _(
            "Vul een adres in dat met https:// begint. "
            "http:// werkt alleen op je eigen computer of netwerk."
        )
    return None


# -- Talking to the service ---------------------------------------------------

# Why a request failed. Only after TIMEOUT_REASON may the service have
# done the work (and charged for it): with every other reason it did none.
REFUSED, UNREACHABLE, BUSY, SERVER = "refused", "unreachable", "busy", "server"
NO_MODEL, NO_IMAGES, TIMEOUT_REASON, ANSWER = "no_model", "no_images", "timeout", "answer"


class ServiceError(Exception):
    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail


def _open(request: urllib.request.Request, timeout: float) -> tuple[int, bytes]:
    """One HTTP request; the status and body, also for an error status.
    The one place this module goes on the network. A redirect counts as
    an address that doesn't answer: following it would send the key along
    (core.no_redirects)."""
    try:
        with no_redirects.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        if no_redirects.is_redirect(error.code):
            raise ServiceError(UNREACHABLE, f"redirect {error.code}") from error
        return error.code, error.read()
    except TimeoutError as error:
        # Sent, and no answer in time: the service may have done the work.
        raise ServiceError(TIMEOUT_REASON, str(error)) from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, TimeoutError):
            raise ServiceError(TIMEOUT_REASON, str(error)) from error
        raise ServiceError(UNREACHABLE, str(error)) from error
    except (OSError, ValueError, UnicodeError) as error:
        raise ServiceError(UNREACHABLE, str(error)) from error


def _message_of(body: bytes) -> str:
    """The service's own error message, short, for the log and the page's
    detail line. Never the request: that holds the key."""
    try:
        data = json.loads(body)
    except ValueError:
        return body[:200].decode("utf-8", "replace")
    error = data.get("error") if isinstance(data, dict) else None
    if isinstance(error, dict):
        return str(error.get("message", ""))[:200]
    if isinstance(error, str):
        return error[:200]
    if isinstance(data, dict) and "message" in data:
        return str(data["message"])[:200]
    return body[:200].decode("utf-8", "replace")


def chat(config: Config, content: list[dict], timeout: float = TIMEOUT) -> str:
    """Sends one user message (OpenAI's content parts: text and image_url)
    and returns the answer's text. ServiceError when it fails."""
    body = json.dumps(
        {
            "model": config.model,
            "messages": [{"role": "user", "content": content}],
            "temperature": 0,
        }
    ).encode()
    headers = {"Content-Type": "application/json", "User-Agent": "Huismus"}
    if config.key:
        headers["Authorization"] = f"Bearer {config.key}"
    request = urllib.request.Request(
        config.url.rstrip("/") + "/chat/completions", data=body, headers=headers, method="POST"
    )
    status, answer = _open(request, timeout)
    if status != 200:
        raise ServiceError(_reason(status, answer), f"{status}: {_message_of(answer)}")
    try:
        text = json.loads(answer)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise ServiceError(ANSWER, answer[:200].decode("utf-8", "replace")) from error
    if isinstance(text, list):
        # Some services give the answer as content parts too.
        text = "".join(part.get("text", "") for part in text if isinstance(part, dict))
    return str(text or "")


def _reason(status: int, body: bytes) -> str:
    message = _message_of(body).lower()
    if status in (401, 403):
        return REFUSED
    if status == 429:
        return BUSY
    if status >= 500:
        return SERVER
    if "model" in message and ("not found" in message or "exist" in message):
        return NO_MODEL
    if status == 404:
        # Nothing at this address: a typing error in it, most likely.
        return UNREACHABLE
    if "image" in message or "vision" in message or "multimodal" in message:
        return NO_IMAGES
    return ANSWER


def image_part(jpeg_base64: str) -> dict:
    return {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{jpeg_base64}"}}


def _test_image() -> str:
    """A small white card with "OK" on it, as a base64 JPEG."""
    image = Image.new("RGB", (160, 80), "white")
    ImageDraw.Draw(image).text((60, 30), "OK", fill="black", font_size=28)
    buffer = BytesIO()
    image.save(buffer, "JPEG", quality=85)
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def test_connection(config: Config) -> None:
    """One small request with an image, so a model that can't read images
    shows up now and not at the first receipt. ServiceError when it fails."""
    chat(
        config,
        [
            {"type": "text", "text": "What word is in this image? Answer with that word only."},
            image_part(_test_image()),
        ],
        timeout=60,
    )


def failure_sentence(reason: str, config: Config) -> str:
    """Why a request to the service failed, in plain words."""
    values = {"service": name(config), "model": config.model}
    if reason == REFUSED:
        return _("%(service)s weigert je sleutel. Kijk of je hem goed hebt overgenomen.") % values
    if reason == UNREACHABLE:
        return (
            _(
                "Huismus kan %(service)s niet bereiken. "
                "Kijk of het adres klopt en of je internet hebt."
            )
            % values
        )
    if reason == BUSY:
        return (
            _("%(service)s is te druk of je tegoed is op. Huismus probeert het later opnieuw.")
            % values
        )
    if reason == SERVER:
        return _("%(service)s gaf een fout. Huismus probeert het later opnieuw.") % values
    if reason == NO_MODEL:
        return (
            _("%(service)s kent het model %(model)s niet. Kijk hoe het model precies heet.")
            % values
        )
    if reason == NO_IMAGES:
        return (
            _("Het model %(model)s kan geen plaatjes lezen. Kies een model dat dat wel kan.")
            % values
        )
    if reason == TIMEOUT_REASON:
        return _("%(service)s gaf te laat antwoord.") % values
    return _("%(service)s gaf een antwoord dat Huismus niet begrijpt.") % values
