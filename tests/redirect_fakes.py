# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Two small HTTP servers on this computer for the redirect tests: one
that sends every request elsewhere, and one that only writes down what
reached it. A key sent along with a redirect would show up in the
second's list."""

import http.server
import threading


class _Server:
    def __init__(self):
        self.requests: list[tuple[str, str]] = []  # (method, Authorization)
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_port}/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def _answer(self, handler) -> None:
        raise NotImplementedError

    def _handler(self):
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def __getattr__(self, name):
                # Every method: GET, POST, PUT, PROPFIND, MKCOL and so on.
                if not name.startswith("do_"):
                    raise AttributeError(name)

                def answer():
                    length = int(self.headers.get("Content-Length") or 0)
                    self.rfile.read(length)
                    fake.requests.append((self.command, self.headers.get("Authorization", "")))
                    fake._answer(self)

                return answer

        return Handler


class Catcher(_Server):
    """Answers 200 to everything and keeps what came in."""

    def _answer(self, handler) -> None:
        handler.send_response(200)
        handler.send_header("Content-Length", "2")
        handler.end_headers()
        handler.wfile.write(b"{}")


class Redirector(_Server):
    """Sends every request on to location with status."""

    def __init__(self, status: int, location: str):
        self.status = status
        self.location = location
        super().__init__()

    def _answer(self, handler) -> None:
        handler.send_response(self.status)
        handler.send_header("Location", self.location)
        handler.send_header("Content-Length", "0")
        handler.end_headers()
