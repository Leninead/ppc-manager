"""HTTP receiver for the integrations portal — closes OAuth grants and takes
Mercado Libre webhooks. Runs as its own container on the VPS, behind Caddy.

Three endpoints under `app.capybaras.agency`:

  GET  /oauth/callback   **Provider-agnostic.** Whatever integration started
                         a grant in `integration_pending_grants` (Mercado Libre
                         today; Amazon Ads and Walmart when they light up in
                         the catalog) lands here with `?code=…&state=…`. The
                         receiver seals the code with the portal's public key
                         and stashes it on the pending row. **The receiver
                         never opens anything sealed** — the private key lives
                         only in the worker container. Compromising this
                         service yields sealed blobs and nothing else. The
                         state → integration lookup + provider-specific token
                         exchange stay in the worker (`worker.py::_exchange_grant`
                         reads `integration.token_url` from the catalog).

  POST /notifications    Mercado Libre webhook. Provider-specific because
                         each vendor's push mechanism differs (Amazon uses SNS,
                         Walmart uses periodic pull). The receiver does the
                         shortest possible thing: dedup on (external_id, topic)
                         and insert into `meli_notifications`. Must return 200
                         in under 500 ms or MELI retries and eventually shuts
                         the app off. When Amazon lights up, its notifications
                         will land on a separate handler (`/notifications/amazon`
                         or an SNS endpoint), not here.

  GET  /health           Cheap health check — never touches the database, so
                         Caddy/Docker healthchecks don't flap on a slow PostgREST.

Env vars (see deploy/integrations/env.example):

  SUPABASE_URL                  PostgREST base URL, reachable from this container.
  INTEGRATIONS_RECEIVER_JWT     JWT with role=web_user. INSERT/UPDATE on
                                integration_pending_grants and INSERT on
                                meli_notifications is enough — the receiver
                                never reads sealed columns.
  INTEGRATIONS_PUBLIC_KEY       PEM of the sealing public key. The worker
                                publishes it on first boot via
                                `integration_settings.sealing_public_key`; the
                                receiver takes it from the env for zero db
                                round-trips on the hot path.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI, HTTPException, Request, Response

from core.integrations import crypto
from core.integrations.store import (
    PENDING_GRANTS_TABLE,
    _Rest,
)

log = logging.getLogger("integrations.receiver")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

# Notifications table lives in the meli_api migration (003_meli_api.sql).
NOTIFICATIONS_TABLE = "meli_notifications"

app = FastAPI(title="Integrations receiver", docs_url=None, redoc_url=None)


def _rest() -> _Rest:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("INTEGRATIONS_RECEIVER_JWT", "").strip()
    if not (url and key):
        raise HTTPException(
            status_code=503,
            detail="Receiver missing SUPABASE_URL or INTEGRATIONS_RECEIVER_JWT",
        )
    return _Rest(url, key)


def _public_key() -> str:
    key = os.environ.get("INTEGRATIONS_PUBLIC_KEY", "").strip()
    if not key:
        raise HTTPException(
            status_code=503,
            detail="Receiver missing INTEGRATIONS_PUBLIC_KEY",
        )
    return key.replace("\\n", "\n")


@app.get("/health")
def health(response: Response) -> dict[str, str]:
    """Configuration only — never touches the database, so the healthcheck does
    not flap when PostgREST is slow.

    It does check the sealing key, because without it every seller consent
    fails and nothing else notices: the callback would 500 one visitor at a
    time while the container reported healthy. Failing here instead makes the
    deploy's health gate catch it.
    """
    missing = [name for name in ("SUPABASE_URL", "INTEGRATIONS_RECEIVER_JWT",
                                 "INTEGRATIONS_PUBLIC_KEY")
               if not os.environ.get(name, "").strip()]
    if missing:
        response.status_code = 503
        log.error("unconfigured: missing %s", ", ".join(missing))
        return {"status": "unconfigured", "missing": ", ".join(missing)}
    return {"status": "ok"}


@app.get("/oauth/callback", response_class=Response)
def oauth_callback(request: Request, code: str = "", state: str = "",
                   error: str = "", error_description: str = "") -> Response:
    """Any provider lands here after the person consents — Mercado Libre and
    Login with Amazon today (Amazon also appends a `scope` query param, which
    is ignored).

    Success path: look up the pending grant by `state`, seal the `code` with
    the portal's public key, mark the row as received. The worker picks it up
    on its next `grants` run.

    Never leaks whether the `state` existed: an attacker who guesses states
    should not learn which ones are in flight.
    """
    if error:
        # A denial (access_denied) or a misconfigured app (invalid_scope,
        # unauthorized_client) comes back here with the state. Record it on
        # the pending row so the failure is visible to the team, not only on
        # the tab the person just closed; then show it plainly, don't 500.
        _record_provider_error(state, error, error_description, request)
        return _render(
            "Autorización cancelada",
            f"El proveedor devolvió: {error}. {error_description}".strip(),
            status=400,
        )
    if not (code and state):
        raise HTTPException(status_code=400, detail="callback missing code or state")

    try:
        code_sealed = crypto.seal(code, _public_key())
    except crypto.SealError as exc:
        log.error("could not seal the code: %s", exc)
        raise HTTPException(status_code=500, detail="could not seal the code")

    rest = _rest()
    try:
        rows = rest.select(
            PENDING_GRANTS_TABLE,
            {"select": "id",
             "state": f"eq.{state}",
             "estado": "eq.pendiente",
             "limit": "1"},
        )
    except Exception as exc:
        log.error("could not look up the pending grant: %s", exc)
        raise HTTPException(status_code=502, detail="database unreachable")

    if not rows:
        # Same message shape as the happy path so a scanner can't tell them
        # apart. The worker will simply not have anything to exchange.
        log.warning("callback with unknown or already-used state (ip=%s)",
                    _client_ip(request))
        return _render(
            "Autorización recibida",
            "Podés cerrar esta pestaña. Si algo falla, el equipo lo va a ver "
            "en el próximo pase del worker.",
        )

    try:
        rest.update(
            PENDING_GRANTS_TABLE,
            {"state": f"eq.{state}"},
            {"code_sealed": code_sealed, "estado": "recibido"},
        )
    except Exception as exc:
        log.error("could not stash the sealed code: %s", exc)
        raise HTTPException(status_code=502, detail="could not persist the code")

    log.info("oauth code sealed and stashed for state %s (ip=%s)",
             state[:8], _client_ip(request))
    return _render(
        "Autorización recibida",
        "Podés cerrar esta pestaña. En pocos minutos el módulo va a mostrar "
        "la cuenta como conectada.",
    )


@app.post("/notifications")
async def notifications(request: Request) -> Response:
    """Mercado Libre webhook endpoint. Must return 200 in under 500 ms."""
    try:
        body = await request.json()
    except Exception:
        # A malformed body from MELI is still a 200 for MELI (any 4xx/5xx
        # triggers a retry storm). We drop it, log the miss.
        log.warning("notification with non-JSON body (ip=%s)", _client_ip(request))
        return Response(status_code=200)

    external_id = str(body.get("_id") or body.get("id") or "").strip()
    topic = str(body.get("topic") or "").strip()
    user_id = str(body.get("user_id") or "").strip()
    if not (external_id and topic and user_id):
        log.warning("notification missing required fields (topic=%r, id=%r)",
                    topic, external_id)
        return Response(status_code=200)

    resource = body.get("resource")
    application_id = str(body.get("application_id") or "").strip() or None
    sent_at = _parse_iso(body.get("sent") or body.get("received")
                         or body.get("recieved"))

    row = {
        "external_id": external_id,
        "topic": topic,
        "user_id": user_id,
        "resource": resource,
        "application_id": application_id,
        "sent_at": sent_at.isoformat() if sent_at else None,
        "body": body,
    }

    rest = _rest()
    try:
        rest.insert(NOTIFICATIONS_TABLE, row)
    except Exception as exc:
        # Duplicate (external_id, topic) triggers a 409 by design — dedup at
        # the DB level. Treat as success so MELI doesn't retry. The status
        # code is what identifies it: PostgREST's `Prefer: return=minimal`
        # answers with an empty body, so the pg error text never reaches here.
        status = getattr(getattr(exc, "response", None), "status_code", None)
        if status == 409:
            log.info("notification duplicate ignored (topic=%s id=%s)",
                     topic, external_id)
        else:
            log.error("could not persist notification: %s", exc)

    return Response(status_code=200)


def _record_provider_error(state: str, error: str, description: str,
                           request: Request) -> None:
    """Mark the pending grant `fallido` with what the provider said. Best
    effort: the person still gets the page whether or not the write lands."""
    if not state:
        return
    try:
        rest = _rest()
        rest.update(
            PENDING_GRANTS_TABLE,
            {"state": f"eq.{state}", "estado": "eq.pendiente"},
            {"estado": "fallido", "error": f"{error}: {description}".strip(": ")[:500]},
        )
        log.info("provider error %s recorded for state %s (ip=%s)",
                 error, state[:8], _client_ip(request))
    except Exception as exc:
        log.warning("could not record provider error for state %s: %s", state[:8], exc)


# ── plumbing ──────────────────────────────────────────────────────────────


def _client_ip(request: Request) -> str:
    """Trust the last proxy header only. Caddy sets X-Forwarded-For; anything
    upstream of Caddy would already be logged there."""
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ"):
        try:
            parsed = datetime.strptime(text, fmt)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except ValueError:
            continue
    return None


def _render(title: str, message: str, status: int = 200) -> Response:
    """Sober success/failure page. No script, no external assets — this page
    ships from the receiver container and has to work with the strictest CSP.

    The page body is Spanish because it faces Capybaras vendors after an OAuth
    handshake; the `lang="es"` attribute matches that copy.
    """
    html = f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ margin: 0; background: #FFFFFF; color: #1A1A1A;
          font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
                       "Helvetica Neue", Arial, sans-serif;
          display: flex; align-items: center; justify-content: center;
          min-height: 100vh; padding: 24px; }}
  main {{ max-width: 520px; }}
  h1 {{ font-size: 22px; font-weight: 700; margin: 0 0 12px;
       color: {'#1B6B2F' if status == 200 else '#B02A00'}; }}
  p {{ font-size: 15px; line-height: 1.55; color: #6B7280; margin: 0; }}
</style>
</head>
<body><main><h1>{title}</h1><p>{message}</p></main></body>
</html>"""
    return Response(content=html, media_type="text/html; charset=utf-8", status_code=status)
