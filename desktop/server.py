# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Django on 127.0.0.1 inside the desktop app, without gunicorn.

The standard library's WSGI server, one thread per request: the window is
the only client (huismus/core/desktop.py turns everyone else away), so nothing
more is needed. Static files come from WhiteNoise, as on Docker.
"""

import errno
import logging
import sys
import threading
from socketserver import TCPServer, ThreadingMixIn
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

logger = logging.getLogger("huismus.desktop")


# The AI connection's address should stay the same (SPEC.md M16), so the
# app asks for this port first and takes a free one only when it is taken.
PREFERRED_PORT = 8765


class _ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second program take a port another one
    # is listening on; elsewhere it only allows a restart right after a stop.
    allow_reuse_address = sys.platform != "win32"

    def server_bind(self):
        """WSGIServer's own, without looking up the host's name
        (socket.getfqdn): inside the packaged app that took half a minute
        at every start, for a name nobody uses."""
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]
        self.setup_environ()


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, format, *args):
        logger.debug("%s %s", self.address_string(), format % args)


class MigrationFailed(Exception):
    """The migrations failed: after an update, the app offers the backup it
    made before (desktop/app.py)."""


class Server:
    """Settings must be in the environment before start() (desktop/app.py)."""

    def __init__(self):
        self._httpd = None

    def start(self) -> str:
        """Migrates, then serves on PREFERRED_PORT, or a free port when that is
        taken. Returns the base URL."""
        import django
        from django.core.management import call_command
        from django.core.wsgi import get_wsgi_application

        django.setup()
        try:
            call_command("migrate", interactive=False, verbosity=0)
        except Exception as error:
            raise MigrationFailed() from error
        application = get_wsgi_application()
        try:
            self._httpd = self._serve(application, PREFERRED_PORT)
        except OSError as error:
            if error.errno not in (errno.EADDRINUSE, errno.EACCES):
                raise
            logger.warning("Poort %s is bezet; Huismus kiest een andere.", PREFERRED_PORT)
            self._httpd = self._serve(application, 0)
        threading.Thread(target=self._httpd.serve_forever, daemon=True).start()
        url = f"http://127.0.0.1:{self._httpd.server_port}"
        logger.info("Huismus draait op %s", url)
        return url

    @staticmethod
    def _serve(application, port):
        return make_server(
            "127.0.0.1",
            port,
            application,
            server_class=_ThreadingServer,
            handler_class=_QuietHandler,
        )

    def stop(self):
        if self._httpd is not None:
            self._httpd.shutdown()
            self._httpd.server_close()
            self._httpd = None
