"""Command-line entry for MELI ingest.

Mirrors the structure of ``core.integrations.worker``: one process per run,
loads the sealing private key from disk, opens the sealed refresh token,
rotates it against Meli, and drives :func:`core.meli_api.ingest.sync_all`.

Usage::

    python -m core.meli_api.worker ingest [--client=SLUG]

The command exits ``0`` when every account synced without error, ``1`` if
one or more failed, and ``2`` when configuration or the sealing key is
missing (the sync did not even start).
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from typing import Any

import requests

from core.integrations import catalog, crypto, oauth
from core.integrations.store import CONNECTIONS_TABLE, CREDENTIALS_TABLE, _Rest
from core.meli_api import ingest
from core.meli_api.transport import MeliClient

log = logging.getLogger("meli_api.worker")

_SLUG = "mercado_libre"

# Base URLs are env-overridable so a local API fake can drive the pipeline
# end-to-end without touching api.mercadolibre.com. Both default to production.
_TOKEN_URL = os.environ.get(
    "MELI_TOKEN_URL_OVERRIDE", "https://api.mercadolibre.com/oauth/token"
).strip() or "https://api.mercadolibre.com/oauth/token"
_API_BASE_URL = os.environ.get(
    "MELI_API_BASE_URL", "https://api.mercadolibre.com"
).strip().rstrip("/") or "https://api.mercadolibre.com"


class WorkerError(RuntimeError):
    """Configuration or setup error — the ingest cannot even start."""


# ---------------------------------------------------------------------------
# Setup helpers
# ---------------------------------------------------------------------------
def _rest_worker() -> _Rest:
    """Build a ``_Rest`` bound to the worker JWT.

    Same env-var contract as ``core.integrations.worker._rest_worker`` — we
    intentionally do not import it to keep the two workers decoupled.
    """
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("INTEGRATIONS_WORKER_JWT", "").strip()
    if not (url and key):
        raise WorkerError("missing SUPABASE_URL or INTEGRATIONS_WORKER_JWT")
    return _Rest(url, key)


def _load_private_pem() -> str:
    """Read the sealing private key. Env var wins, then the mounted file.

    Never generates a key here — the integrations worker owns the keypair;
    a run of ``python -m core.integrations.worker keys`` installs it.
    """
    env_pem = os.environ.get(crypto.PRIVATE_KEY_ENV, "").strip()
    if env_pem:
        return env_pem.replace("\\n", "\n")
    path = crypto.private_key_path()
    if not path.is_file():
        raise WorkerError(
            f"sealing private key not found at {path}; "
            "run `python -m core.integrations.worker keys` first"
        )
    return path.read_text(encoding="ascii")


def _active_credential(rest: _Rest, private_pem: str) -> tuple[str, str]:
    """(client_id, client_secret) for Mercado Libre — opens the sealed half."""
    rows = rest.select(
        CREDENTIALS_TABLE,
        {
            "select": "public_fields,secret_sealed",
            "integration_slug": f"eq.{_SLUG}",
            "estado": "eq.activo",
            "limit": "1",
        },
    )
    if not rows:
        raise WorkerError(f"{_SLUG} has no active system credential")
    row = rows[0]
    client_id = str((row.get("public_fields") or {}).get("client_id", "")).strip()
    sealed = row.get("secret_sealed")
    if not (client_id and sealed):
        raise WorkerError(f"the {_SLUG} credential is incomplete")
    return client_id, crypto.unseal(sealed, private_pem)


# ---------------------------------------------------------------------------
# Rotation
# ---------------------------------------------------------------------------
class _TokenLoop:
    """Refresh loop shared by the initial exchange and the 401 fallback.

    Holds the current refresh token in plaintext so the ``MeliClient``'s
    refresh callback (fired on a 401) rotates against the freshest value
    the process has seen — not the one that was on disk when the sync
    started.
    """

    def __init__(
        self,
        rest: _Rest,
        conn: dict,
        client_id: str,
        client_secret: str,
        public_pem: str,
        current_refresh_plain: str,
        current_refresh_sealed: str,
    ):
        self._rest = rest
        self._conn_id = int(conn["id"])
        self._client_id = client_id
        self._client_secret = client_secret
        self._public_pem = public_pem
        self._current_plain = current_refresh_plain
        self._current_sealed = current_refresh_sealed

    def rotate(self) -> oauth.TokenSet:
        tokens = oauth.refresh(
            token_url=_TOKEN_URL,
            client_id=self._client_id,
            client_secret=self._client_secret,
            refresh_token=self._current_plain,
        )
        self._persist(tokens)
        return tokens

    def _persist(self, tokens: oauth.TokenSet) -> None:
        new_sealed = crypto.seal(tokens.refresh_token, self._public_pem)
        # Same invariant as core.integrations.worker._rotate_token: the previous
        # sealed generation is kept so a crash between refresh and update
        # does not orphan the account.
        self._rest.update(
            CONNECTIONS_TABLE,
            {"id": f"eq.{self._conn_id}"},
            {
                "refresh_token_sealed": new_sealed,
                "refresh_token_prev_sealed": self._current_sealed,
                "token_rotated_at": ingest._now_iso(),
                "access_expires_at": _expires_at_iso(tokens.expires_in),
                "last_error": "",
            },
        )
        self._current_plain = tokens.refresh_token
        self._current_sealed = new_sealed


def _expires_at_iso(expires_in: int) -> str | None:
    if not expires_in or expires_in <= 0:
        return None
    from datetime import datetime, timedelta, timezone

    return (
        datetime.now(timezone.utc) + timedelta(seconds=int(expires_in))
    ).isoformat()


# ---------------------------------------------------------------------------
# command_ingest
# ---------------------------------------------------------------------------
def command_ingest(client: str | None = None) -> int:
    """Sync every active Mercado Libre connection (or only ``cliente``)."""
    rest = _rest_worker()
    private_pem = _load_private_pem()
    public_pem = crypto.public_from_private(private_pem)

    params: dict[str, Any] = {
        "select": (
            "id,integration_slug,cliente,cuenta_externa_id,nombre_externo,"
            "marketplace,refresh_token_sealed,estado,scopes"
        ),
        "integration_slug": f"eq.{_SLUG}",
        "estado": "eq.activo",
    }
    if client:
        params["cliente"] = f"eq.{client}"

    try:
        connections = rest.select(CONNECTIONS_TABLE, params)
    except Exception as exc:
        raise WorkerError(f"could not read the accounts: {exc}") from exc

    if not connections:
        print("no accounts to sync")
        return 0

    integration = catalog.by_slug(_SLUG)
    if integration is None:
        raise WorkerError(f"unknown integration in catalog: {_SLUG}")

    client_id, client_secret = _active_credential(rest, private_pem)

    failed = 0
    for conn in connections:
        client_slug = conn.get("cliente") or "?"
        try:
            _ingest_one(
                rest,
                conn,
                private_pem=private_pem,
                public_pem=public_pem,
                client_id=client_id,
                client_secret=client_secret,
            )
            print(f"ok {client_slug}")
        except oauth.NeedsReauth as exc:
            failed += 1
            _mark_reauth(rest, conn, str(exc))
            print(f"reauth {client_slug}: {exc}")
        except Exception as exc:
            failed += 1
            _mark_error(rest, conn, str(exc))
            log.exception("ingest fallo para %s", client_slug)
            print(f"error {client_slug}: {exc}")
    return 1 if failed else 0


def _ingest_one(
    rest: _Rest,
    conn: dict,
    *,
    private_pem: str,
    public_pem: str,
    client_id: str,
    client_secret: str,
) -> None:
    """Refresh the identity's token, hydrate, and drive ``sync_all``."""
    sealed = conn.get("refresh_token_sealed")
    if not sealed:
        raise WorkerError(
            f"account {conn.get('client')!r} has no sealed refresh_token"
        )

    current_plain = crypto.unseal(sealed, private_pem)
    loop = _TokenLoop(
        rest=rest,
        conn=conn,
        client_id=client_id,
        client_secret=client_secret,
        public_pem=public_pem,
        current_refresh_plain=current_plain,
        current_refresh_sealed=sealed,
    )

    # Initial refresh — buys us a fresh access token before any request.
    tokens = loop.rotate()

    # Hydrate the identity now that we know the connection is valid.
    identity_id = ingest.hydrate_identity(rest, conn)

    client = MeliClient(
        access_token=tokens.access_token,
        refresh_callback=loop.rotate,
        base_url=_API_BASE_URL,
    )
    mla = str(conn.get("marketplace") or "MLA")
    user_id = str(conn.get("cuenta_externa_id") or "").strip()
    if not user_id:
        raise WorkerError(
            f"account {conn.get('client')!r} has no cuenta_externa_id"
        )
    ingest.sync_all(client, rest, identity_id, mla, user_id)


def _mirror_on_identity(rest: _Rest, conn: dict, changes: dict) -> None:
    """Carry a connection's health over to its Meli identity row.

    Both tables describe the same seller account; leaving the identity as
    `activo` while the connection is dead makes the two disagree and any
    consumer that schedules off the identity keeps retrying a token that
    cannot work.
    """
    user_id = str(conn.get("cuenta_externa_id") or "").strip()
    if not user_id:
        return
    try:
        rest.update(ingest.IDENTITIES_TABLE, {"user_id": f"eq.{user_id}"}, changes)
    except Exception as exc:
        log.warning("could not mirror state onto the identity of %s: %s",
                    conn.get("cliente"), exc)


def _mark_error(rest: _Rest, conn: dict, message: str) -> None:
    changes = {"last_error": message[:500]}
    try:
        rest.update(CONNECTIONS_TABLE, {"id": f"eq.{conn['id']}"}, changes)
    except Exception as exc:
        log.warning("could not persist last_error for %s: %s", conn.get("cliente"), exc)
    _mirror_on_identity(rest, conn, changes)


def _mark_reauth(rest: _Rest, conn: dict, message: str) -> None:
    changes = {"estado": "needs_reauth", "last_error": message[:500]}
    try:
        rest.update(CONNECTIONS_TABLE, {"id": f"eq.{conn['id']}"}, changes)
    except Exception as exc:
        log.warning("could not mark needs_reauth for %s: %s", conn.get("cliente"), exc)
    _mirror_on_identity(rest, conn, changes)


# ---------------------------------------------------------------------------
# argparse entry point
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s %(name)s: %(message)s"
    )
    parser = argparse.ArgumentParser(prog="meli_api.worker")
    sub = parser.add_subparsers(dest="command", required=True)
    p_ingest = sub.add_parser("ingest", help="sync every active MELI account")
    p_ingest.add_argument(
        "--client",
        default=None,
        help="restrict the sync to this client (the slug in integration_connections.cliente)",
    )
    args = parser.parse_args(argv)

    try:
        if args.command == "ingest":
            return command_ingest(client=args.client)
    except (WorkerError, crypto.SealError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    parser.error(f"unknown command: {args.command}")
    return 2  # unreachable but keeps mypy quiet


if __name__ == "__main__":
    raise SystemExit(main())
