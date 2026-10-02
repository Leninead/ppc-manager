"""The chat's internal HTTP door: one POST per Slack batch, answered as a stream of JSON lines, behind a bearer token.

Nothing publishes its port: only the bot shares its network. The token is a second lock on the same door.
"""
from __future__ import annotations

import hmac
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from services.chat_api.account_scope import AccountScopes
from services.chat_api.turns import TurnRequest, answer_turn

log = logging.getLogger(__name__)

TURN_PATH = "/v1/slack/turns"
HEALTH_PATH = "/health"
MAX_BODY_BYTES = 1_000_000


class ChatApiServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, scopes: AccountScopes | None = None, answer=answer_turn):
        super().__init__(address, ChatApiHandler)
        self.token = token
        self.scopes = scopes or AccountScopes()
        self.answer = answer


class ChatApiHandler(BaseHTTPRequestHandler):
    server: ChatApiServer
    server_version = "ppc-manager-chat"

    def do_GET(self) -> None:
        if self.path == HEALTH_PATH:
            self._json(200, {"ok": True})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != TURN_PATH:
            self._json(404, {"error": "not found"})
            return
        if not self._authorized():
            self._json(401, {"error": "unauthorized"})
            return
        length = _content_length(self.headers.get("Content-Length"))
        if length <= 0 or length > MAX_BODY_BYTES:
            self._json(413 if length > MAX_BODY_BYTES else 400, {"error": "body size"})
            return
        try:
            request = TurnRequest.from_json(json.loads(self.rfile.read(length)))
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"error": str(exc)})
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        try:
            self.server.answer(request, self._emit, scopes=self.server.scopes)
        except BrokenPipeError:
            log.warning("the bot hung up before %s was answered", request.conversation)
        except Exception as exc:  # whatever breaks, the bot must get an answer it can act on
            log.exception("turn for %s failed", request.conversation)
            self._emit({"type": "error", "kind": "failed", "message": type(exc).__name__})

    def log_message(self, format: str, *args) -> None:
        log.debug("%s %s", self.address_string(), format % args)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization") or ""
        token = header.removeprefix("Bearer ").strip() if header.startswith("Bearer ") else ""
        return bool(self.server.token) and hmac.compare_digest(token.encode(), self.server.token.encode())

    def _emit(self, event: dict) -> None:
        self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
        self.wfile.flush()

    def _json(self, status: int, body: dict) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _content_length(header: str | None) -> int:
    try:
        return int(header or 0)
    except ValueError:
        return 0


def serve(token: str, port: int) -> None:
    server = ChatApiServer(("0.0.0.0", port), token)
    log.info("chat API listening on port %d", port)
    server.serve_forever()
