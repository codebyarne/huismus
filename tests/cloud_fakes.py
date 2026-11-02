# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""Stand-ins for the cloud services of huismus/core/cloud_backups.py, so no test
ever talks to the real Dropbox or a real WebDAV server.

FakeWebDAV is a small WebDAV server on this computer. The app only takes
https:// addresses; install() makes https://dav.test/ go to the fake.
FakeDropbox answers Dropbox's API at the one place the module goes on the
network (core.cloud_backups._open)."""

import base64
import http.server
import json
import threading
import urllib.parse

from huismus.core import cloud_backups

ADDRESS = "https://dav.test/remote.php/dav/files/sanne/"
USERNAME, PASSWORD = "sanne", "app-wachtwoord"


class FakeWebDAV:
    def __init__(self):
        self.files: dict[str, bytes] = {}  # path below the address -> content
        self.folders: set[str] = set()
        self.password = PASSWORD
        self.full = False
        handler = self._handler()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/remote.php/dav/files/sanne/"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def names(self) -> list[str]:
        return sorted(path.removeprefix("Huismus/") for path in self.files)

    def _handler(self):
        fake = self
        root = "/remote.php/dav/files/sanne/"

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _path(self):
                path = urllib.parse.unquote(urllib.parse.urlsplit(self.path).path)
                return path.removeprefix(root).rstrip("/") if path.startswith(root) else None

            def _answer(self, status, body=b"", content_type="application/octet-stream"):
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _allowed(self):
                expected = base64.b64encode(f"{USERNAME}:{fake.password}".encode()).decode()
                if self.headers.get("Authorization") != f"Basic {expected}":
                    self._answer(401)
                    return False
                return True

            def _body(self):
                return self.rfile.read(int(self.headers.get("Content-Length") or 0))

            def do_PROPFIND(self):
                path = self._path()
                if path is None:
                    return self._answer(404)
                if not self._allowed():
                    return
                if path and path not in fake.folders:
                    return self._answer(404)
                entries = [f"<d:response><d:href>{root}{path}/</d:href></d:response>"]
                if self.headers.get("Depth") == "1":
                    for name, content in fake.files.items():
                        folder, _, file_name = name.rpartition("/")
                        if folder == path:
                            href = root + urllib.parse.quote(name)
                            entries.append(
                                f"<d:response><d:href>{href}</d:href><d:propstat><d:prop>"
                                f"<d:getcontentlength>{len(content)}</d:getcontentlength>"
                                "</d:prop></d:propstat></d:response>"
                            )
                body = '<?xml version="1.0"?><d:multistatus xmlns:d="DAV:">'
                body += "".join(entries) + "</d:multistatus>"
                self._answer(207, body.encode(), "application/xml")

            def do_MKCOL(self):
                if self._path() is None:
                    return self._answer(404)
                path = self._path()
                if not self._allowed():
                    return
                if path in fake.folders:
                    return self._answer(405)
                fake.folders.add(path)
                self._answer(201)

            def do_PUT(self):
                if self._path() is None:
                    return self._answer(404)
                path = self._path()
                body = self._body()
                if not self._allowed():
                    return
                if path.rpartition("/")[0] not in fake.folders:
                    return self._answer(409)
                if fake.full:
                    return self._answer(507)
                fake.files[path] = body
                self._answer(201)

            def do_GET(self):
                if self._path() is None:
                    return self._answer(404)
                if not self._allowed():
                    return
                path = self._path()
                if path not in fake.files:
                    return self._answer(404)
                self._answer(200, fake.files[path])

            def do_DELETE(self):
                if self._path() is None:
                    return self._answer(404)
                if not self._allowed():
                    return
                fake.files.pop(self._path(), None)
                self._answer(204)

        return Handler

    def install(self, monkeypatch):
        """Routes https://dav.test/… to this server."""
        real_open = cloud_backups._open

        def routed(request):
            if request.full_url.startswith("https://dav.test/"):
                request.full_url = request.full_url.replace(
                    "https://dav.test/remote.php/dav/files/sanne/", self.url
                )
            return real_open(request)

        monkeypatch.setattr(cloud_backups, "_open", routed)


class FakeDropbox:
    """Dropbox's API for one app folder, at core.cloud_backups._open."""

    CODE = "goede-code"

    def __init__(self):
        self.files: dict[str, bytes] = {}
        self.refresh_tokens = {"refresh-1"}
        self.revoked = False
        self.calls: list[str] = []
        self.full = False
        self.session = b""  # an upload in parts, between start and finish
        self.used_codes: set[str] = set()  # Dropbox takes each code once

    def install(self, monkeypatch):
        monkeypatch.setattr(cloud_backups, "_open", self.open)

    def open(self, request):
        url = request.full_url
        self.calls.append(url)
        body = request.data or b""
        if url == cloud_backups.Dropbox.TOKEN:
            form = dict(urllib.parse.parse_qsl(body.decode()))
            if form["grant_type"] == "authorization_code" and form["code"] == self.CODE:
                if form["code"] in self.used_codes:
                    used = {"error": "invalid_grant", "error_description": "code has expired"}
                    return 400, json.dumps(used).encode()
                self.used_codes.add(form["code"])
                return 200, json.dumps({"refresh_token": "refresh-1", "access_token": "a"}).encode()
            if (
                form["grant_type"] == "refresh_token"
                and form["refresh_token"] in self.refresh_tokens
            ):
                return 200, json.dumps({"access_token": "access-1"}).encode()
            return 400, b'{"error": "invalid_grant"}'
        if request.get_header("Authorization") != "Bearer access-1":
            return 401, b"{}"
        endpoint = url.split("/2/", 1)[1]
        header = request.get_header("Dropbox-api-arg")
        arg = json.loads(header) if header else json.loads(body or b"null")
        if endpoint == "files/upload":
            if self.full:
                return 409, b'{"error_summary": "path/insufficient_space/"}'
            self.files[arg["path"].lstrip("/")] = body
            return 200, b"{}"
        if endpoint == "files/upload_session/start":
            self.session = body
            return 200, b'{"session_id": "s1"}'
        if endpoint == "files/upload_session/append_v2":
            assert arg["cursor"]["offset"] == len(self.session)
            self.session += body
            return 200, b"null"
        if endpoint == "files/upload_session/finish":
            assert arg["cursor"]["offset"] == len(self.session)
            self.files[arg["commit"]["path"].lstrip("/")] = self.session + body
            return 200, b"{}"
        if endpoint == "files/list_folder":
            entries = [
                {".tag": "file", "name": name, "size": len(content)}
                for name, content in self.files.items()
            ]
            return 200, json.dumps({"entries": entries, "has_more": False}).encode()
        if endpoint == "files/download":
            name = arg["path"].lstrip("/")
            if name not in self.files:
                return 409, b'{"error_summary": "path/not_found/"}'
            return 200, self.files[name]
        if endpoint == "files/delete_v2":
            self.files.pop(arg["path"].lstrip("/"), None)
            return 200, b"{}"
        if endpoint == "auth/token/revoke":
            self.revoked = True
            return 200, b"null"
        return 404, b""
