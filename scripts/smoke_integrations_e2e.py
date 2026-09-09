"""End-to-end local smoke: portal → receiver → worker, against the real
PostgREST + the real DB. MELI is stubbed with `responses` — everything else
is the actual production code path.

What it exercises:

  1. Portal saves a system credential (client_id + client_secret sealed).
  2. Portal opens a pending grant for a client (verifier sealed, state).
  3. Simulate MELI redirect: HTTP GET to the receiver's `/oauth/callback`
     with `?code=&state=`.
  4. Verify the receiver sealed the code and marked the row `recibido`.
  5. Worker `grants` picks the pending row, unseals verifier + code + secret,
     hits (stubbed) MELI /oauth/token, receives tokens.
  6. Verify the connection row is `activo` with `refresh_token_sealed`,
     `access_expires_at`, `consent_date`, and no `last_error`.
  7. Worker `refresh` rotates the refresh token; verify the rotation kept
     the previous generation and cleared last_error.

Prereqs (all local):

  docker exec agency-db psql -U postgres -d agency_os               # DB up
  http://127.0.0.1:3002/rest/v1/                                    # gateway up
  sh deploy/db/migrate.sh                                           # portal tables exist
  data/integrations/sealing_private.pem                             # worker key generated
  .env with PGRST_JWT_SECRET, SUPABASE_KEY (web_user JWT)

Run:  .venv/Scripts/python.exe scripts/smoke_integrations_e2e.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import subprocess
import sys
import threading
import time
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

import requests
import responses

# Load .env values so this script matches what the docker-compose overlay sees.
for line in (REPO / ".env").read_text(encoding="utf-8").splitlines():
    if "=" in line and not line.strip().startswith("#"):
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())

# Local rest-gateway — same URL shape production uses (`http://rest-gateway`
# from inside the docker network, `http://127.0.0.1:3002` from the host). The
# gateway strips `/rest/v1` before proxying to postgrest. Talking to postgrest
# directly (`:3001`) hides a URL-prefix bug caught here on 2026-09-03.
os.environ["SUPABASE_URL"] = "http://127.0.0.1:3002"

from core.integrations import catalog, crypto, oauth
from core.integrations.store import (
    CONNECTIONS_TABLE,
    CREDENTIALS_TABLE,
    PENDING_GRANTS_TABLE,
    ConnectionStore,
    CredentialStore,
    _Rest,
    fingerprint,
    open_stores,
)


# ── Utilities ────────────────────────────────────────────────────────────

GREEN, RED, RESET, DIM = "\033[32m", "\033[31m", "\033[0m", "\033[2m"


def ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")
    raise SystemExit(1)


def step(n: int, title: str) -> None:
    print(f"\n{DIM}── step {n} ────────────────────────────────────────{RESET}")
    print(f"  {title}")


def mint_jwt(role: str, secret: str, minutes: int = 60) -> str:
    def b64u(v: bytes) -> str:
        return base64.urlsafe_b64encode(v).rstrip(b"=").decode()
    header = b64u(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = b64u(json.dumps({"role": role, "exp": int(time.time()) + minutes * 60}).encode())
    sig = b64u(hmac.new(secret.encode(), f"{header}.{payload}".encode(), hashlib.sha256).digest())
    return f"{header}.{payload}.{sig}"


# ── Fixture: fresh state ────────────────────────────────────────────────


def clean(rest: _Rest) -> None:
    """Wipe MELI rows across the three tables. The app JWT can't DELETE from
    integration_pending_grants (correct: the app is not supposed to). Use the
    worker JWT for the cleanup."""
    worker_rest = _Rest(rest._url, os.environ["INTEGRATIONS_WORKER_JWT"])
    for table in (CONNECTIONS_TABLE, PENDING_GRANTS_TABLE, CREDENTIALS_TABLE):
        resp = worker_rest._session.delete(
            f"{worker_rest._url}/{table}",
            params={"integration_slug": "eq.mercado_libre"},
            headers=worker_rest._headers(minimal=True),
        )
        resp.raise_for_status()


# ── Steps ────────────────────────────────────────────────────────────────


def step_1_portal_saves_credential(stores) -> None:
    """As the portal would do when Lenin loads the app on MELI."""
    creds, _, settings = stores
    public_key = settings.get("sealing_public_key")
    assert public_key, "the DB has no public key — run `worker keys` first"
    ok(f"portal reads sealing public key from DB ({len(public_key)} bytes)")

    sealed_secret = crypto.seal("FAKE_CLIENT_SECRET_test123", public_key)
    creds.save(
        slug="mercado_libre",
        secret=sealed_secret,
        sealed=True,
        public_fields={"client_id": "FAKE_CLIENT_ID_42"},
        user="smoke",
    )
    status = creds.list_states()["mercado_libre"]
    assert status.public_fields["client_id"] == "FAKE_CLIENT_ID_42"
    assert status.fingerprint == fingerprint(sealed_secret)
    ok(f"credential saved: fingerprint {status.fingerprint} · client_id {status.public_fields['client_id']}")


def step_2_portal_opens_a_pending_grant(stores, public_key: str) -> str:
    """As `_dialogo_conectar` would when the AM clicks 'Preparar autorización'."""
    _, connections, _ = stores
    grant = oauth.start_grant()
    connections.open_grant(
        slug="mercado_libre",
        client="dermaglos-smoke",
        marketplace="MLA",
        state=grant.state,
        verifier_sealed=crypto.seal(grant.verifier, public_key),
        user="smoke",
    )
    ok(f"pending grant opened for dermaglos-smoke · state {grant.state[:10]}…")
    return grant.state


def step_3_meli_redirects_to_receiver(receiver_url: str, state: str) -> None:
    """MELI would redirect the vendor's browser here after consent. We just
    curl it — the response is the sober HTML page the vendor would see."""
    fake_code = "TG-abc123def456"
    resp = requests.get(
        f"{receiver_url}/oauth/callback",
        params={"code": fake_code, "state": state},
        allow_redirects=False,
        timeout=5,
    )
    assert resp.status_code == 200, f"receiver responded {resp.status_code}: {resp.text[:200]}"
    assert "Autorización recibida" in resp.text
    ok(f"receiver returned 200 with the success page")


def step_4_check_code_was_sealed(rest: _Rest, state: str) -> None:
    """The receiver should have sealed the code and marked the row `recibido`.
    Read with the WORKER JWT — the app JWT can't SELECT sealed columns."""
    worker_rest = _Rest(rest._url, os.environ["INTEGRATIONS_WORKER_JWT"])
    rows = worker_rest.select(
        PENDING_GRANTS_TABLE,
        {"select": "estado,code_sealed,verifier_sealed",
         "state": f"eq.{state}"},
    )
    assert len(rows) == 1, f"expected 1 pending row, got {len(rows)}"
    row = rows[0]
    assert row["estado"] == "recibido", f"expected 'recibido', got {row['estado']!r}"
    assert row["code_sealed"] and row["code_sealed"].startswith("v1:"), (
        f"code_sealed missing or not sealed: {row['code_sealed']!r}"
    )
    ok(f"pending row: estado={row['estado']} · code_sealed prefix={row['code_sealed'][:6]}…")


def step_5_worker_exchanges_the_code(stores, state: str, mock_meli):
    """Real worker code path: reads the pending row, unseals verifier+code+secret,
    calls MELI /oauth/token (stubbed), writes the connection."""
    integracion = catalog.by_slug("mercado_libre")
    assert integracion.token_url == "https://api.mercadolibre.com/oauth/token"

    mock_meli.add(
        responses.POST,
        integracion.token_url,
        json={
            "access_token": "ACCESS_abc",
            "refresh_token": "REFRESH_xyz_v1",
            "expires_in": 21600,
            "scope": "offline_access read write",
            "user_id": 999999999,
        },
        status=200,
    )

    # Import worker only now — it reads env at import time in some paths.
    from core.integrations import worker
    os.environ["INTEGRATIONS_REDIRECT_URI"] = "https://app.capybaras.agency/oauth/callback"
    exit_code = worker.command_grants()
    assert exit_code == 0, f"worker grants exited {exit_code}"
    ok("worker exchanged the code with MELI (mocked) and returned 0")


def step_6_check_connection_is_active(stores) -> int:
    _, connections, _ = stores
    all_conn = connections.by_integration_slug().get("mercado_libre", [])
    assert len(all_conn) == 1, f"expected 1 connection, got {len(all_conn)}"
    conn = all_conn[0]
    assert conn.status == "activo", f"expected 'activo', got {conn.status!r}"
    assert conn.external_account_id == "999999999", (
        f"user_id mismatch: {conn.external_account_id!r}"
    )
    assert conn.consent_date == date.today().isoformat(), (
        f"consent_date is {conn.consent_date!r}, expected today"
    )
    assert conn.last_error == ""
    ok(f"connection {conn.id}: cliente={conn.client} · user_id={conn.external_account_id} · estado={conn.status}")
    return conn.id


def step_7_worker_refreshes_the_token(rest: _Rest, mock_meli) -> None:
    """Simulate the refresh cron: push token_rotated_at back so `refresh`
    picks it up, then let the worker call MELI again."""
    integracion = catalog.by_slug("mercado_libre")
    from datetime import datetime, timedelta, timezone
    ancient = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
    # The app JWT can't touch `token_rotated_at` (that's what forces the
    # rotation to go through the worker path). Use the worker JWT here.
    worker_rest = _Rest(rest._url, os.environ["INTEGRATIONS_WORKER_JWT"])
    worker_rest.update(
        CONNECTIONS_TABLE,
        {"integration_slug": "eq.mercado_libre"},
        {"token_rotated_at": ancient},
    )

    mock_meli.add(
        responses.POST,
        integracion.token_url,
        json={
            "access_token": "ACCESS_new",
            "refresh_token": "REFRESH_xyz_v2",
            "expires_in": 21600,
            "scope": "offline_access read write",
            "user_id": 999999999,
        },
        status=200,
    )
    from core.integrations import worker
    exit_code = worker.command_refresh()
    assert exit_code == 0, f"worker refresh exited {exit_code}"

    worker_rest = _Rest(rest._url, os.environ["INTEGRATIONS_WORKER_JWT"])
    rows = worker_rest.select(
        CONNECTIONS_TABLE,
        {"select": "estado,refresh_token_sealed,refresh_token_prev_sealed,last_error",
         "integration_slug": "eq.mercado_libre"},
    )
    row = rows[0]
    assert row["estado"] == "activo"
    assert row["refresh_token_sealed"], "refresh_token_sealed missing after rotate"
    assert row["refresh_token_prev_sealed"], (
        "refresh_token_prev_sealed missing — a crash mid-rotate would orphan the account"
    )
    assert row["refresh_token_sealed"] != row["refresh_token_prev_sealed"], (
        "the two generations are identical — nothing was rotated"
    )
    assert row["last_error"] == ""
    ok(f"token rotated: current + prev generations both sealed, distinct")


# ── Receiver in a thread ─────────────────────────────────────────────────


def start_receiver_in_background() -> tuple[str, threading.Thread]:
    """Boot the FastAPI receiver on a random local port using the SAME env
    the docker-compose overlay would give it."""
    import socket
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]

    os.environ["INTEGRATIONS_PUBLIC_KEY"] = _pub_key_from_disk()
    os.environ["INTEGRATIONS_RECEIVER_JWT"] = os.environ["SUPABASE_KEY"]

    import uvicorn
    from services.integrations_receiver.app import app as receiver_app

    config = uvicorn.Config(receiver_app, host="127.0.0.1", port=port,
                            log_level="warning", access_log=False)
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    # Wait for /health.
    url = f"http://127.0.0.1:{port}"
    for _ in range(50):
        try:
            if requests.get(f"{url}/health", timeout=0.2).status_code == 200:
                return url, thread
        except requests.RequestException:
            time.sleep(0.1)
    fail(f"receiver never came up on {url}")
    raise SystemExit(1)


def _pub_key_from_disk() -> str:
    from cryptography.hazmat.primitives import serialization
    priv_pem = (REPO / "data/integrations/sealing_private.pem").read_text()
    priv = serialization.load_pem_private_key(priv_pem.encode(), password=None)
    return priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()


# ── main ────────────────────────────────────────────────────────────────


def main() -> int:
    print(f"\n{DIM}Portal integrations — local end-to-end smoke{RESET}")

    # Mint the worker JWT the whole run needs (integ_worker role).
    secret = os.environ["PGRST_JWT_SECRET"]
    os.environ["INTEGRATIONS_WORKER_JWT"] = mint_jwt("integ_worker", secret)
    os.environ["INTEGRATIONS_KEY_FILE"] = str(REPO / "data/integrations/sealing_private.pem")

    stores = open_stores()
    if stores is None:
        fail("open_stores() returned None — check SUPABASE_URL and SUPABASE_KEY in .env")
    rest = _Rest(os.environ["SUPABASE_URL"], os.environ["SUPABASE_KEY"])

    step(0, "reset state (delete existing MELI credential/pending/connections)")
    clean(rest)
    ok("mercado_libre rows cleared across the three tables")

    step(1, "portal saves system credential (client_secret sealed)")
    step_1_portal_saves_credential(stores)

    step(2, "portal opens pending OAuth grant for a client account")
    public_key = stores[2].get("sealing_public_key")
    state = step_2_portal_opens_a_pending_grant(stores, public_key)

    step(3, "receiver boots + MELI redirects to /oauth/callback")
    receiver_url, _ = start_receiver_in_background()
    step_3_meli_redirects_to_receiver(receiver_url, state)

    step(4, "receiver sealed the code and marked pending as `recibido`")
    step_4_check_code_was_sealed(rest, state)

    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock_meli:
        # PostgREST is real — only mock the MELI HTTP host. Without this the
        # worker's DB reads would land on `responses` and fail.
        mock_meli.add_passthru("http://127.0.0.1:3002/")
        step(5, "worker `grants` unseals + exchanges the code with MELI (mocked)")
        step_5_worker_exchanges_the_code(stores, state, mock_meli)

        step(6, "connection is `activo` with sealed refresh token")
        step_6_check_connection_is_active(stores)

        step(7, "worker `refresh` rotates the refresh token (mocked)")
        step_7_worker_refreshes_the_token(rest, mock_meli)

    print(f"\n{GREEN}all steps passed — the portal ↔ receiver ↔ worker loop is closed locally.{RESET}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
