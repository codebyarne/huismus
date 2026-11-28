# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The desktop app's second listener, for linked phones on the same Wi-Fi
(issue #143, SPEC.md M11).

The window keeps its own server on 127.0.0.1 (desktop/server.py). This one
listens on the laptop's address on the home or office network, and only
while linking is on (core.phones.is_on). Never on 0.0.0.0 and never on
IPv6, so nothing outside that network reaches it (SPEC.md 9).

Before Django sees a request, _Guard checks what a network can fake or
reach: the caller must be on a home network, the Host must be exactly this
address (no DNS rebinding), X-Forwarded-* headers are dropped (Huismus sits
behind no proxy here), and a body may not be larger than an upload Huismus
takes anyway. It then marks the request with PHONE_ENVIRON, a key no client
can set (headers arrive as HTTP_*), and huismus/core/desktop.py does the rest:
the phone's cookie and the pages a phone may open.
"""

import errno
import logging
import socket
import threading
import time
from socketserver import ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from django.conf import settings

from . import phones

logger = logging.getLogger("huismus.desktop")

PHONE_ENVIRON = "huismus.phone"
# A bookmark on the phone keeps working as long as the address stays.
PREFERRED_PORT = 8766
# Receipts are the largest thing a phone sends (expenses: 10 MB).
MAX_BODY = 25 * 1024 * 1024
# One person's phones: a few requests at once is plenty, and a device on the
# Wi-Fi that opens many connections can't tie up the laptop.
MAX_CONNECTIONS = 16
SOCKET_TIMEOUT = 30
WATCH_SECONDS = 60

# desktop/server.py sets the WSGI application it serves the window with.
application = None
_server = None
_lock = threading.Lock()


def lan_address() -> str | None:
    """The laptop's IPv4 address towards the network, or None when that is
    not a home network. A UDP socket's connect sends nothing; it only picks
    the interface the system would use."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 9))
            address = probe.getsockname()[0]
    except OSError:
        return None
    return address if phones.is_home_network(address) else None


def address() -> str | None:
    """http://<ip>:<port> while listening, else None."""
    server = _server
    if server is None:
        return None
    return f"http://{server.host}:{server.server_port}"


def is_wifi_host(host: str) -> bool:
    """The Host of this listener: the window's requests may not carry it."""
    server = _server
    return server is not None and host.rsplit(":", 1)[0] == server.host


def start() -> str | None:
    """Listens when not yet listening; the address, or None when the laptop
    is on no home network (or the app serves no window, as on Docker)."""
    global _server
    with _lock:
        if _server is not None:
            return address()
        host = lan_address()
        if host is None or application is None:
            return None
        port = phones.saved_port() or PREFERRED_PORT
        try:
            _server = _serve(host, port)
        except OSError as error:
            if error.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            _server = _serve(host, 0)
        phones.save_port(_server.server_port)
        _allow_host(host)
        threading.Thread(target=_server.serve_forever, daemon=True).start()
        logger.info("Huismus luistert op het wifi-netwerk: %s", address())
        return address()


def stop() -> None:
    global _server
    with _lock:
        server, _server = _server, None
    if server is not None:
        server.shutdown()
        server.server_close()
        _forbid_host(server.host)


def start_if_on() -> None:
    """At the app's start: listens again when a phone is linked."""
    if phones.is_on():
        start()


def follow_the_network() -> None:
    """Once a minute (watch_thread): after the laptop woke up on another
    network, listen on the new address, or stop on none (PO, 2026-11-28)."""
    server = _server
    if server is None:
        start_if_on()
        return
    if lan_address() != server.host:
        stop()
        start_if_on()


def watch_thread() -> None:
    """Started by desktop/app.py next to the server; ends with the app."""

    def watch():
        while True:
            time.sleep(WATCH_SECONDS)
            try:
                follow_the_network()
            except Exception:
                logger.exception("Wifi-adres nakijken mislukte")

    threading.Thread(target=watch, daemon=True).start()


def _serve(host, port):
    server = make_server(
        host,
        port,
        _Guard(application),
        server_class=_PhoneServer,
        handler_class=_PhoneHandler,
    )
    server.host = host
    server.wsgi_app.host = f"{host}:{server.server_port}"
    return server


def _allow_host(host):
    # Django's own Host check, besides _Guard's: the window's requests are
    # held to 127.0.0.1 in huismus/core/desktop.py, so this address only
    # counts on this listener.
    if host not in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.append(host)


def _forbid_host(host):
    if host in settings.ALLOWED_HOSTS:
        settings.ALLOWED_HOSTS.remove(host)


class _Guard:
    def __init__(self, app):
        self.app = app
        self.host = ""

    def __call__(self, environ, start_response):
        if not phones.is_home_network(environ.get("REMOTE_ADDR", "")):
            return _refuse(start_response, "403 Forbidden")
        if environ.get("HTTP_HOST") != self.host:
            return _refuse(start_response, "400 Bad Request")
        try:
            length = int(environ.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return _refuse(start_response, "400 Bad Request")
        if length > MAX_BODY:
            return _refuse(start_response, "413 Content Too Large")
        for name in [k for k in environ if k.startswith("HTTP_X_FORWARDED_")]:
            del environ[name]
        environ.pop("HTTP_FORWARDED", None)
        environ[PHONE_ENVIRON] = True
        return self.app(environ, start_response)


def _refuse(start_response, status):
    start_response(status, [("Content-Type", "text/plain; charset=utf-8")])
    return [b""]


class _PhoneServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, *args, **kwargs):
        self._slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kwargs)

    def server_bind(self):
        # As desktop/server.py: no socket.getfqdn() for a name nobody uses.
        from socketserver import TCPServer

        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
        self.setup_environ()

    def process_request(self, request, client_address):
        if not self._slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        super().process_request(request, client_address)

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self._slots.release()


class _PhoneHandler(WSGIRequestHandler):
    timeout = SOCKET_TIMEOUT

    def log_message(self, format, *args):
        # Never the query: the link code is in it (review-veiligheid).
        logger.debug("%s %s", self.address_string(), self.path.split("?", 1)[0])
