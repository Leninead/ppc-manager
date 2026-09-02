"""Single HTTP touchpoint to the ai-provider: transport, typed errors, local log."""
import datetime
import json
import pathlib
import threading
import time

import requests

from ai import config


class AIError(Exception):
    """Base for every provider-related failure."""


class ProviderDown(AIError):
    """The provider is unreachable or not authenticated upstream."""


class QuotaExceeded(AIError):
    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


class UpstreamError(AIError):
    """Claude itself failed (or the provider rejected the request)."""


_log_lock = threading.Lock()


def _log(record: dict) -> None:
    # Observability must never take the app down.
    try:
        log_dir = pathlib.Path(config.LOG_DIR)
        log_dir.mkdir(parents=True, exist_ok=True)
        path = log_dir / f"{datetime.date.today().isoformat()}.jsonl"
        with _log_lock, open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
    except OSError:
        pass


def ask(*, system: str, input_text: str, context: list, model: str,
        effort: str | None = None, output_schema: dict | None = None,
        session_id: str | None = None, timeout_s: int = 900,
        max_turns: int = 1, tools: list | None = None, tag: str = "") -> dict:
    """POST /v1/answer and return the provider's response body."""
    payload: dict = {"system": system, "input": input_text, "model": model,
                     "max_turns": max_turns, "context": context}
    if effort:
        payload["effort"] = effort
    if output_schema:
        payload["output_schema"] = output_schema
    if session_id:
        payload["session_id"] = session_id
    if tools:
        payload["tools"] = tools

    t0 = time.time()
    base = {"ts": t0, "tag": tag, "model": model,
            "context_chars": sum(len(d.get("content", "")) for d in context),
            "resumed": bool(session_id)}
    try:
        r = requests.post(f"{config.PROVIDER_URL}/v1/answer", json=payload,
                          timeout=timeout_s)
    except requests.exceptions.RequestException as e:
        _log({**base, "status": "provider_down", "error": str(e)})
        raise ProviderDown(
            f"No se pudo contactar al AI provider en {config.PROVIDER_URL}. "
            "¿Está corriendo el contenedor?") from e

    try:
        body = r.json()
    except ValueError:
        body = {"error": r.text[:500]}

    _log({**base, "status": r.status_code,
          "duration_ms": int((time.time() - t0) * 1000),
          "request_id": body.get("request_id"), "usage": body.get("usage"),
          "error": body.get("error"), "response": body if r.ok else None})

    if r.status_code == 200:
        return body
    detail = body.get("detail") or body.get("error") or r.text[:300]
    if r.status_code == 429:
        retry_after = int(r.headers.get("Retry-After", "60"))
        raise QuotaExceeded(
            f"Cuota de IA agotada — reintentar en ~{retry_after}s.", retry_after)
    if r.status_code == 503:
        raise ProviderDown(f"El AI provider no está autenticado con Claude: {detail}")
    raise UpstreamError(f"El AI provider respondió {r.status_code}: {detail}")
