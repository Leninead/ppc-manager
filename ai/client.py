"""Single HTTP touchpoint to the ai-provider: transport, typed errors, local log."""
import datetime
import json
import pathlib
import threading
import time
from collections.abc import Iterator

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


def _unreachable_message(detail: str) -> str:
    """Say which subsystem is down, from what the provider reported.

    A 503 can be the Claude credential, the Amazon Ads session or the portal.
    One canned prefix for all three made the message actively misleading: an
    Amazon failure read as a Claude authentication problem, which is a different
    person, a different console and a different fix.
    """
    lowered = detail.lower()
    if "amazon ads mcp" in lowered or "amazon ads session" in lowered:
        # The TaskGroup wrapper hides the sub-exception; say so rather than
        # printing "1 sub-exception" at someone who cannot act on it.
        if "taskgroup" in lowered:
            return ("No se pudo abrir la conexión con Amazon Ads y el provider no "
                    "reportó la causa. Suele ceder al reintentar; si insiste, "
                    "revisá los logs del provider.")
        return f"No se pudo abrir la conexión con Amazon Ads: {detail}"
    if "amazon ads" in lowered or "portal" in lowered:
        return f"El portal de integraciones no respondió: {detail}"
    if "oauth" in lowered or "token" in lowered or "autentic" in lowered:
        return f"El AI provider no está autenticado con Claude: {detail}"
    return f"El AI provider no pudo atender el pedido: {detail}"


class UpstreamError(AIError):
    """Claude itself failed (or the provider rejected the request)."""


# Tool profiles the provider can actually serve, and when we last looked.
# Short TTL: this changes on a provider redeploy, not during a conversation.
_TOOLS_TTL_S = 60
_tools_seen: tuple[float, frozenset[str]] | None = None
_tools_lock = threading.Lock()


def available_tools() -> frozenset[str] | None:
    """Which tool profiles the provider has configured, or None if unknown.

    `/health` already reports this ({"datadive": false, "amazon_ads": true});
    nobody was reading it. Asking for a profile the provider cannot serve is a
    503 for the WHOLE turn, so a missing DataDive key took down a DataDive chat
    that could still have answered about the analysis on screen — the AM got
    "DATADIVE_API_KEY is not configured on the provider", which is neither their
    problem nor their vocabulary.

    None means the question could not be asked. The caller keeps whatever it was
    going to send: if the provider is unreachable the turn fails anyway, and
    silently dropping every tool would be a worse way to find out.
    """
    global _tools_seen
    now = time.time()
    with _tools_lock:
        if _tools_seen and now - _tools_seen[0] < _TOOLS_TTL_S:
            return _tools_seen[1]
    try:
        r = requests.get(f"{config.PROVIDER_URL}/health", timeout=5)
        served = frozenset(k for k, v in (r.json().get("tools") or {}).items() if v)
    except (requests.exceptions.RequestException, ValueError, AttributeError):
        return None
    with _tools_lock:
        _tools_seen = (now, served)
    return served


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


def _payload(*, system: str, input_text: str, context: list, model: str,
             effort: str | None, output_schema: dict | None, session_id: str | None,
             max_turns: int, tools: list | None, ads_scope: dict | None,
             skills: list | None) -> dict:
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
    if ads_scope:
        payload["ads_scope"] = ads_scope
    if skills:
        # Knowledge the agency wrote, uploaded from Sistema. It travels with the
        # turn because the provider cannot reach this app's disk.
        payload["skills"] = skills
    return payload


def _headers() -> dict:
    return {"X-Provider-Token": config.PROVIDER_SECRET} if config.PROVIDER_SECRET else {}


def _log_base(t0: float, tag: str, model: str, context: list, session_id: str | None,
              ads_scope: dict | None) -> dict:
    return {"ts": t0, "tag": tag, "model": model,
            "context_chars": sum(len(d.get("content", "")) for d in context),
            "resumed": bool(session_id),
            "ads_account_id": (ads_scope or {}).get("account_id")}


def _unreached(e: requests.exceptions.RequestException, base: dict, timeout_s: int) -> ProviderDown:
    # Mid-stream, requests reports a read timeout as a ConnectionError that says so.
    if isinstance(e, requests.exceptions.ReadTimeout) or "read timed out" in str(e).lower():
        # Reached but silent: pointing at a stopped container would send someone to the wrong place.
        _log({**base, "status": "timeout", "error": str(e)})
        return ProviderDown(f"El AI provider no respondió en {timeout_s} s y el pedido se cortó.")
    _log({**base, "status": "provider_down", "error": str(e)})
    return ProviderDown(f"No se pudo contactar al AI provider en {config.PROVIDER_URL}. "
                        "¿Está corriendo el contenedor?")


def ask(*, system: str, input_text: str, context: list, model: str,
        effort: str | None = None, output_schema: dict | None = None,
        session_id: str | None = None, timeout_s: int = 3600,
        max_turns: int = 1, tools: list | None = None,
        ads_scope: dict | None = None, skills: list | None = None,
        tag: str = "") -> dict:
    """POST /v1/answer and return the provider's response body.

    `ads_scope` ({account_id, profile_id, requested_by}) names the client's
    Amazon Ads account a chat is about; the provider resolves the credentials
    itself, the app only points at the row. It goes with the shared secret."""
    payload = _payload(system=system, input_text=input_text, context=context, model=model,
                       effort=effort, output_schema=output_schema, session_id=session_id,
                       max_turns=max_turns, tools=tools, ads_scope=ads_scope, skills=skills)
    t0 = time.time()
    base = _log_base(t0, tag, model, context, session_id, ads_scope)
    try:
        r = requests.post(f"{config.PROVIDER_URL}/v1/answer", json=payload,
                          headers=_headers(), timeout=timeout_s)
    except requests.exceptions.RequestException as e:
        raise _unreached(e, base, timeout_s) from e

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
    raise _refused(r.status_code, body, r.text, r.headers, ads_scope)


def ask_stream(*, system: str, input_text: str, context: list, model: str,
               effort: str | None = None, output_schema: dict | None = None,
               session_id: str | None = None, timeout_s: int = 3600,
               max_turns: int = 1, tools: list | None = None,
               ads_scope: dict | None = None, skills: list | None = None,
               tag: str = "") -> Iterator[dict]:
    """POST /v1/answer/stream and yield the provider's events as they arrive.

    A `tool` event names a tool the model just asked for, while it works. The last
    event is the `result`, with the same fields `ask` returns. Every failure raises
    the error `ask` would raise for it, whether it is known before the first event
    (the HTTP status) or only at the end (a result that reports an error)."""
    payload = _payload(system=system, input_text=input_text, context=context, model=model,
                       effort=effort, output_schema=output_schema, session_id=session_id,
                       max_turns=max_turns, tools=tools, ads_scope=ads_scope, skills=skills)
    t0 = time.time()
    base = {**_log_base(t0, tag, model, context, session_id, ads_scope), "stream": True}
    try:
        r = requests.post(f"{config.PROVIDER_URL}/v1/answer/stream", json=payload,
                          headers=_headers(), timeout=timeout_s, stream=True)
    except requests.exceptions.RequestException as e:
        raise _unreached(e, base, timeout_s) from e

    with r:
        if r.status_code != 200:
            try:
                body = r.json()
            except ValueError:
                body = {"error": r.text[:500]}
            _log({**base, "status": r.status_code,
                  "duration_ms": int((time.time() - t0) * 1000),
                  "request_id": body.get("request_id"), "error": body.get("error")})
            raise _refused(r.status_code, body, r.text, r.headers, ads_scope)
        result = None
        try:
            for line in r.iter_lines():
                # Bytes, decoded here: an event stream without a charset would
                # otherwise be read as Latin-1 and garble every accent.
                if not line.startswith(b"data: "):
                    continue
                try:
                    event = json.loads(line[len(b"data: "):].decode("utf-8"))
                except ValueError as e:
                    _log({**base, "status": "stream_error", "duration_ms": int((time.time() - t0) * 1000),
                          "error": f"unreadable event: {e}"})
                    raise UpstreamError("El AI provider devolvió una respuesta ilegible.") from e
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "result":
                    result = event
                    break
                if event.get("type") == "tool":
                    yield event
        except requests.exceptions.RequestException as e:
            raise _unreached(e, base, timeout_s) from e

    _log({**base, "status": 200 if result and not result.get("is_error") else "stream_error",
          "duration_ms": int((time.time() - t0) * 1000),
          "request_id": (result or {}).get("request_id"), "usage": (result or {}).get("usage"),
          "error": (result or {}).get("error"), "response": result})
    if result is None:
        raise UpstreamError("El AI provider cortó la respuesta antes de terminarla.")
    if result.get("is_error"):
        raise _failed(result)
    yield result


def _failed(result: dict) -> AIError:
    """The error a streamed result reports, named the way `ask` names its status."""
    detail = str(result.get("error") or "error desconocido")
    kind = result.get("error_kind")
    if kind == "quota":
        return QuotaExceeded("Cuota de IA agotada — reintentar en ~300s.", 300)
    if kind == "auth":
        return ProviderDown(f"El AI provider no está autenticado con Claude: {detail}")
    if kind == "ads_unavailable":
        return ProviderDown(_unreachable_message(f"Amazon Ads MCP is unavailable: {detail}"))
    return UpstreamError(f"El AI provider no pudo terminar la respuesta: {detail}")


def _refused(status: int, body: dict, text: str, headers, ads_scope: dict | None) -> AIError:
    detail = body.get("detail") or body.get("error") or text[:300]
    if status == 429:
        retry_after = int(headers.get("Retry-After", "60"))
        return QuotaExceeded(
            f"Cuota de IA agotada — reintentar en ~{retry_after}s.", retry_after)
    if status == 503:
        # 503 covers everything the provider could not reach, and the message
        # has to name which one. Blaming the Claude credential for a failed
        # Amazon session sent an operator to check the wrong subsystem, while
        # the real cause stayed buried in the detail — seen on 2026-09-10 with
        # "no está autenticado con Claude: could not open the Amazon Ads MCP
        # session". The detail is what identifies the subsystem, so read it.
        return ProviderDown(_unreachable_message(str(detail)))
    if status == 401:
        return ProviderDown("El AI provider rechazó la credencial de la app: "
                            "CLAUDE_PROVIDER_SECRET no coincide con su PROVIDER_SHARED_SECRET.")
    if ads_scope and status in (404, 409):
        # The account the AM picked is gone or its authorization died: the
        # fix is in Cuentas conectadas, not in the provider.
        return UpstreamError(f"Cuenta de Amazon Ads: {detail}")
    return UpstreamError(f"El AI provider respondió {status}: {detail}")
