# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""GitHub webhook on the Pi: deploys main once CI has passed on it.

Listens on 127.0.0.1 only; a Tailscale Funnel path forwards GitHub's
requests to it (docs/deploy.md). Every request must carry GitHub's
HMAC-SHA256 signature made with WEBHOOK_SECRET. Only a completed, green
run of the CI workflow for a push to main starts a deploy, and it deploys
exactly the commit that run tested — not whatever main is by then.

Standard library only, so it runs on the Pi's own python3, outside the
container it replaces: `python3 deploy/webhook.py`, kept running by PM2.
"""

import hashlib
import hmac
import json
import os
import re
import subprocess
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SECRET_FILE = REPO / ".env.webhook"
DEPLOY_SCRIPT = REPO / "deploy" / "deploy.sh"
CI_WORKFLOW = "CI"  # `name:` in .github/workflows/ci.yml
_SHA = re.compile(r"[0-9a-f]{40}")


def signature_is_valid(secret: bytes, body: bytes, header: str) -> bool:
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, header)


def commit_to_deploy(event: str, payload: dict) -> str | None:
    """The commit to deploy for this GitHub event, or None."""
    if event != "workflow_run" or payload.get("action") != "completed":
        return None
    run = payload.get("workflow_run") or {}
    if not (
        run.get("name") == CI_WORKFLOW
        and run.get("event") == "push"
        and run.get("head_branch") == "main"
        and run.get("conclusion") == "success"
    ):
        return None
    sha = run.get("head_sha", "")
    return sha if _SHA.fullmatch(sha) else None


def _read_secret() -> bytes:
    """WEBHOOK_SECRET=... from .env.webhook (gitignored, made on the Pi)."""
    for line in SECRET_FILE.read_text().splitlines():
        key, _, value = line.partition("=")
        if key.strip() == "WEBHOOK_SECRET" and value.strip():
            return value.strip().encode()
    raise SystemExit(f"WEBHOOK_SECRET ontbreekt in {SECRET_FILE}")


class Handler(BaseHTTPRequestHandler):
    secret = b""

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(min(length, 5 * 1024 * 1024))
        if not signature_is_valid(self.secret, body, self.headers.get("X-Hub-Signature-256", "")):
            self.log_message("ongeldige handtekening, geweigerd")
            return self._reply(403, "Forbidden")
        try:
            payload = json.loads(body)
        except ValueError:
            return self._reply(400, "Bad Request")

        sha = commit_to_deploy(self.headers.get("X-GitHub-Event", ""), payload)
        if sha is None:
            return self._reply(200, "Niets te doen")
        self.log_message("CI groen op main, deploy van %s gestart", sha[:12])
        # Not waited for: building on the Pi takes minutes, GitHub gives up
        # after ten seconds. deploy.sh logs to PM2's log for this process.
        subprocess.Popen([str(DEPLOY_SCRIPT), sha], cwd=REPO)
        return self._reply(202, "Deploy gestart")

    def do_GET(self):
        self._reply(404, "Not Found")

    def _reply(self, status: int, text: str):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(text.encode())


def main():
    Handler.secret = _read_secret()
    port = int(os.environ.get("WEBHOOK_PORT", "9002"))
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Huismus-webhook luistert op 127.0.0.1:{port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
