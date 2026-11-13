# SPDX-FileCopyrightText: 2026 Huismus contributors
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A stand-in for an AI service with the OpenAI-compatible chat API
(huismus/expenses/ai_service.py), so no test ever pays a real one.

FakeAIService is a small HTTP server on this computer. Since it is on
127.0.0.1, Huismus takes its http:// address without a key, as it would
Ollama's; tests that need a key set one anyway."""

import http.server
import json
import threading

KEY = "sk-nep-sleutel"


class FakeAIService:
    def __init__(self):
        # What the next answers say: a list of (status, body) or a text,
        # used in order; the last one stays.
        self.answers: list = ["OK"]
        self.key = KEY
        self.models = {"nep-model"}
        self.requests: list[dict] = []  # the JSON bodies received
        self.authorizations: list[str] = []
        self.delay = 0.0  # seconds before answering
        handler = self._handler()
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()

    def answer(self, *answers) -> None:
        """The next answers: a text (the model's reply), a dict (its JSON
        reply, as text), or (status, body)."""
        self.answers = list(answers)

    def _next(self):
        return self.answers.pop(0) if len(self.answers) > 1 else self.answers[0]

    def _handler(self):
        fake = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _send(self, status, data):
                body = json.dumps(data).encode() if not isinstance(data, bytes) else data
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                if self.path != "/v1/chat/completions":
                    return self._send(404, {"error": {"message": "Not found"}})
                request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                fake.requests.append(request)
                authorization = self.headers.get("Authorization", "")
                fake.authorizations.append(authorization)
                if fake.delay:
                    threading.Event().wait(fake.delay)
                if fake.key and authorization != f"Bearer {fake.key}":
                    return self._send(401, {"error": {"message": "Invalid API key"}})
                # As newer models do (Anthropic's Claude Haiku 5.5 among
                # them): sampling settings are refused.
                if {"temperature", "top_p", "top_k"} & request.keys():
                    message = "temperature, top_p and top_k are not supported for this model"
                    return self._send(400, {"error": {"message": message}})
                if request.get("model") not in fake.models:
                    message = f"The model {request.get('model')} does not exist"
                    return self._send(404, {"error": {"message": message}})
                answer = fake._next()
                if isinstance(answer, tuple):
                    return self._send(*answer)
                text = json.dumps(answer) if isinstance(answer, dict) else answer
                self._send(
                    200,
                    {"choices": [{"message": {"role": "assistant", "content": text}}]},
                )

        return Handler
