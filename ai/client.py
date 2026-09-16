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
    headers = {"X-Provider-Token": config.PROVIDER_SECRET} if config.PROVIDER_SECRET else {}

    t0 = time.time()
    base = {"ts": t0, "tag": tag, "model": model,
            "context_chars": sum(len(d.get("content", "")) for d in context),
            "resumed": bool(session_id),
            "ads_account_id": (ads_scope or {}).get("account_id")}
    try:
        r = requests.post(f"{config.PROVIDER_URL}/v1/answer", json=payload,
                          headers=headers, timeout=timeout_s)
    except requests.exceptions.ReadTimeout as e:
        # Reached but silent: pointing at a stopped container would send someone to the wrong place.
        _log({**base, "status": "timeout", "error": str(e)})
        raise ProviderDown(
            f"El AI provider no respondió en {timeout_s} s y el pedido se cortó.") from e
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
        # 503 covers everything the provider could not reach, and the message
        # has to name which one. Blaming the Claude credential for a failed
        # Amazon session sent an operator to check the wrong subsystem, while
        # the real cause stayed buried in the detail — seen on 2026-09-10 with
        # "no está autenticado con Claude: could not open the Amazon Ads MCP
        # session". The detail is what identifies the subsystem, so read it.
        raise ProviderDown(_unreachable_message(str(detail)))
    if r.status_code == 401:
        raise ProviderDown("El AI provider rechazó la credencial de la app: "
                           "CLAUDE_PROVIDER_SECRET no coincide con su PROVIDER_SHARED_SECRET.")
    if ads_scope and r.status_code in (404, 409):
        # The account the AM picked is gone or its authorization died: the
        # fix is in Cuentas conectadas, not in the provider.
        raise UpstreamError(f"Cuenta de Amazon Ads: {detail}")
    raise UpstreamError(f"El AI provider respondió {r.status_code}: {detail}")
