"""Worker side of the integrations portal — the only place secrets are opened.

Runs from an ephemeral container that mounts the key volume and carries the
worker JWT. The always-on app container has neither, so a full compromise of
Streamlit yields sealed blobs and nothing else.

Installing the worker IS running it: the keypair is created on first run and the
public half published to the database, so nobody carries a key between a browser
and a server.

    python -m core.integrations.worker keys      install / verify the keypair
    python -m core.integrations.worker grants    exchange authorization codes
    python -m core.integrations.worker refresh   rotate refresh tokens
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import sys
import unicodedata
from datetime import date, datetime, timedelta, timezone

import requests

from core.integrations import catalog, crypto, oauth
from core.integrations.store import (
    SEALING_KEY_SETTING,
    CONNECTIONS_TABLE,
    CREDENTIALS_TABLE,
    PENDING_GRANTS_TABLE,
    _Rest,
)

log = logging.getLogger("integrations.worker")

REDIRECT_URI_ENV = "INTEGRATIONS_REDIRECT_URI"

# A code is worth minutes; a stale pending row is noise that hides real failures.
GRANT_TTL_MINUTES = 30
# Refresh with room to spare rather than at the cliff.
REFRESH_BEFORE_DAYS = 30


class WorkerError(RuntimeError):
    """The run cannot continue."""


def _rest_worker() -> _Rest:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("INTEGRATIONS_WORKER_JWT", "").strip()
    if not (url and key):
        raise WorkerError("missing SUPABASE_URL or INTEGRATIONS_WORKER_JWT")
    return _Rest(url, key)


def _redirect_uri() -> str:
    uri = os.environ.get(REDIRECT_URI_ENV, "").strip()
    if not uri:
        raise WorkerError(f"missing {REDIRECT_URI_ENV}")
    return uri


def _active_credential(rest: _Rest, slug: str, private_pem: str) -> tuple[str, str]:
    """(client_id, client_secret) for an integration, opening the sealed half."""
    rows = rest.select(
        CREDENTIALS_TABLE,
        {
            "select": "public_fields,secret_sealed",
            "integration_slug": f"eq.{slug}",
            "estado": "eq.activo",
            "limit": "1",
        },
    )
    if not rows:
        raise WorkerError(f"{slug} has no active system credential")
    row = rows[0]
    client_id = str((row.get("public_fields") or {}).get("client_id", "")).strip()
    sealed = row.get("secret_sealed")
    if not (client_id and sealed):
        raise WorkerError(f"credential for {slug} is incomplete")
    return client_id, crypto.unseal(sealed, private_pem)


def ensure_keys(rest: _Rest) -> str:
    """The worker's own keypair, created on first run and published by itself.

    Runs before every command, so installing the worker is just running it. The
    private half is never printed: a secret on stdout ends up in a CI log.
    """
    private_pem, public_pem, created = crypto.load_or_create_private_key()
    stored = rest.get_setting(SEALING_KEY_SETTING)

    # A fresh key next to a key the database already published means the private
    # half went missing — a wiped volume, a `docker compose down -v`, or the
    # worker run from another project directory. Publishing the new one would
    # overwrite the only pointer to material that can no longer be opened, and
    # every sealed credential and refresh token would be lost with no error
    # anywhere. Refuse, and say which of the two situations this is.
    if created and stored and stored != public_pem:
        raise WorkerError(
            "a sealing key is already published but the private half is gone from "
            f"{crypto.private_key_path()}. Publishing the new one would make every "
            "sealed credential and refresh token permanently unreadable. Restore the "
            "`integrations_keys` volume from backup (deploy/db/backup.sh). If you "
            "really mean to start over, clear "
            f"integration_settings.{SEALING_KEY_SETTING} first and re-authorize every "
            "account by hand."
        )

    if created:
        log.info("encryption key generated at %s", crypto.private_key_path())
    if stored != public_pem:
        rest.upsert_setting(SEALING_KEY_SETTING, public_pem, "worker")
        log.info("public key published: the portal can now seal credentials")
    return private_pem


def command_keys() -> int:
    """Idempotent: create the keypair if missing and publish the public half to the DB."""
    ensure_keys(_rest_worker())
    print(f"worker ready · encryption key at {crypto.private_key_path()}")
    return 0


def command_grants() -> int:
    rest = _rest_worker()
    private_pem = ensure_keys(rest)
    redirect_uri = _redirect_uri()

    _expire_pending_grants(rest)
    pending_rows = rest.select(
        PENDING_GRANTS_TABLE,
        {
            "select": "id,integration_slug,cliente,marketplace,state,verifier_sealed,code_sealed",
            "estado": "eq.recibido",
            "order": "created_at.asc",
        },
    )
    if not pending_rows:
        print("no authorizations to exchange")
        return 0

    failed_count = 0
    connected: list[str] = []
    for pending in pending_rows:
        slug = pending["integration_slug"]
        try:
            # The returned slug, not `pending['cliente']`: for Mercado Libre the
            # pending row still holds the `_pending_xxx` placeholder, so the log
            # used to name a client nobody could look up.
            client = _exchange_grant(rest, pending, private_pem, redirect_uri)
            print(f"ok    {slug} · {client}")
            if slug == _MELI_SLUG:
                connected.append(client)
        except Exception as exc:
            failed_count += 1
            log.error("could not exchange %s/%s: %s", slug, pending["cliente"], exc)
            rest.update(
                PENDING_GRANTS_TABLE,
                {"id": f"eq.{pending['id']}"},
                {"estado": "fallido", "error": str(exc)[:500]},
            )
            rest.audit("grant_failed", slug=slug, actor="worker", detail={"error": type(exc).__name__})
            print(f"error {slug} · {pending['cliente']}: {exc}")

    # After the loop, never inside it: every grant gets exchanged and committed
    # before a single (slow) sync starts, so a sync that hangs cannot strand a
    # later authorization in `recibido`.
    _first_sync_meli(connected)
    return 1 if failed_count else 0


def _first_sync_meli(clients: list[str]) -> None:
    """Pull the freshly connected accounts' data now instead of at 23:30.

    Without this an account appears `Activa` and completely empty until the
    nightly ingest — up to a day of an operator looking at a connection that
    works and shows nothing.

    It has to happen in this process and nowhere else: the sealing private key
    lives only in the worker's volume, so neither Streamlit nor the receiver can
    open the refresh token the sync needs. The most either of them could do is
    leave a note in a queue that this same worker would have to drain anyway.

    Failures are logged and swallowed on purpose, and deliberately do not move
    the exit code. The account IS connected — the grant was exchanged and
    committed above — so reporting the whole run as failed because a catalogue
    was slow would call a working connection broken, and the nightly ingest
    retries on its own.
    """
    if not clients:
        return

    # Deferred import: this module is the provider-agnostic one, and
    # `core.meli_api` drags in the whole ingest pipeline. `keys` and `refresh`
    # must not pay for it, and a host that runs no MELI integration must not
    # need it importable at all.
    from core.meli_api.worker import command_ingest

    for client in clients:
        print(f"sync  {_MELI_SLUG} · {client} (first sync)")
        try:
            if command_ingest(client=client) != 0:
                print(f"warn  first sync incomplete for {client} — "
                      f"the nightly ingest will retry")
        except Exception as exc:
            log.warning("first sync failed for %s (the nightly ingest retries): %s",
                        client, exc)
            print(f"warn  first sync failed for {client}: {exc}")


_MELI_SLUG = "mercado_libre"
_MELI_USERS_ME = "https://api.mercadolibre.com/users/me"
_MELI_USERS_ME_TIMEOUT_S = 10


def _slugify(text: str) -> str:
    """Nickname or free text → kebab-case slug fit for `cliente`."""
    normalized = unicodedata.normalize("NFKD", str(text))
    normalized = "".join(c for c in normalized if not unicodedata.combining(c))
    normalized = re.sub(r"[^a-zA-Z0-9]+", "-", normalized).strip("-")
    return normalized.lower() or "cuenta"


def _fetch_meli_identity(access_token: str) -> tuple[str, str]:
    """Ask MELI whose account this token belongs to.

    Returns (nickname, site_id). site_id maps 1-1 to the marketplace column
    (`MLA` = Argentina, `MLM` = México, `MLB` = Brasil, ...).
    """
    try:
        response = requests.get(
            _MELI_USERS_ME,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            },
            timeout=_MELI_USERS_ME_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise WorkerError(f"could not query /users/me on Mercado Libre: {exc}") from exc

    if response.status_code >= 400:
        raise WorkerError(
            f"Mercado Libre rejected /users/me (HTTP {response.status_code})"
        )
    try:
        body = response.json()
    except ValueError as exc:
        raise WorkerError("unreadable response from /users/me") from exc

    nickname = str(body.get("nickname") or "").strip()
    site_id = str(body.get("site_id") or "").strip()
    if not nickname or not site_id:
        raise WorkerError("Mercado Libre returned /users/me without nickname or site_id")
    return nickname, site_id


def _resolve_client_slug(rest: _Rest, slug: str, client_base: str, external_account_id: str,
                   site_id: str) -> str:
    """Resolve slug collisions: same nickname across two MELI accounts.

    The unique constraint is (integration_slug, cuenta_externa_id) — two
    accounts *can* share the `cliente` label, but that leaves the agency
    guessing which is which. If the base slug is already taken by a
    different external id, suffix it with the site.
    """
    try:
        rows = rest.select(
            CONNECTIONS_TABLE,
            {
                "select": "cuenta_externa_id",
                "integration_slug": f"eq.{slug}",
                "cliente": f"eq.{client_base}",
                "limit": "5",
            },
        )
    except Exception:
        # A read failure here is not worth aborting the exchange — the upsert
        # itself is the authoritative check.
        return client_base
    others = [f for f in rows if str(f.get("cuenta_externa_id") or "") != external_account_id]
    if not others:
        return client_base
    return f"{client_base}-{site_id.lower()}"


def _exchange_grant(rest: _Rest, pending: dict, private_pem: str,
                    redirect_uri: str) -> str:
    """Close one grant and return the `cliente` slug the connection ended up on.

    The slug is the caller's only way to know *which* account just came online:
    for Mercado Libre the pending row carried a `_pending_xxx` placeholder and
    the real one is resolved here from /users/me. `command_grants` uses it to
    sync that account immediately instead of leaving it empty until the nightly
    ingest.
    """
    slug = pending["integration_slug"]
    integration = catalog.by_slug(slug)
    if integration is None:
        raise WorkerError(f"unknown integration: {slug}")

    client_id, client_secret = _active_credential(rest, slug, private_pem)
    verifier = crypto.unseal(pending["verifier_sealed"], private_pem)
    code = crypto.unseal(pending["code_sealed"], private_pem)

    tokens = oauth.exchange_code(
        token_url=integration.token_url,
        client_id=client_id,
        client_secret=client_secret,
        code=code,
        redirect_uri=redirect_uri,
        verifier=verifier,
    )

    # For Mercado Libre we auto-fill `cliente` and `marketplace` from
    # /users/me: the connect dialog asks the operator for nothing, so the
    # pending row carries placeholder values that must be resolved here.
    client = pending.get("cliente") or ""
    marketplace = pending.get("marketplace") or ""
    if slug == _MELI_SLUG:
        nickname, site_id = _fetch_meli_identity(tokens.access_token)
        client = _resolve_client_slug(rest, slug, _slugify(nickname), tokens.user_id, site_id)
        marketplace = site_id

    public_pem = crypto.public_from_private(private_pem)

    # Upsert, not insert: reauthorizing carries the same cuenta_externa_id,
    # which the table declares unique together with the slug. A plain insert
    # died with 409 and the account stayed in needs_reauth forever.
    rest.upsert(
        CONNECTIONS_TABLE,
        {
            "integration_slug": slug,
            "cliente": client,
            "cuenta_externa_id": tokens.user_id,
            "marketplace": marketplace,
            "refresh_token_sealed": crypto.seal(tokens.refresh_token, public_pem),
            "token_rotated_at": _now_iso(),
            "access_expires_at": _expiry_iso(tokens.expires_in),
            "scopes": list(tokens.scopes),
            "estado": "activo",
            # The merge only overwrites columns in the payload: without this a
            # successful exchange would leave the previous error visible on screen.
            "last_error": "",
            "consent_date": date.today().isoformat(),
            "conectado_por": pending.get("solicitado_por") or "",
        },
        on_conflict="integration_slug,cuenta_externa_id",
    )
    rest.update(PENDING_GRANTS_TABLE, {"id": f"eq.{pending['id']}"}, {"estado": "canjeado"})
    rest.audit("grant_exchanged", slug=slug, actor="worker", detail={"cliente": client})
    return client


def command_refresh() -> int:
    rest = _rest_worker()
    private_pem = ensure_keys(rest)
    public_pem = crypto.public_from_private(private_pem)

    cutoff = (datetime.now(timezone.utc) - timedelta(days=REFRESH_BEFORE_DAYS)).isoformat()
    connections = rest.select(
        CONNECTIONS_TABLE,
        {
            "select": "id,integration_slug,cliente,refresh_token_sealed,token_rotated_at",
            "estado": "eq.activo",
            "or": f"(token_rotated_at.is.null,token_rotated_at.lt.{cutoff})",
        },
    )
    if not connections:
        print("no tokens to rotate")
        return 0

    failed_count = 0
    for connection in connections:
        try:
            _rotate_token(rest, connection, private_pem, public_pem)
            print(f"ok    {connection['integration_slug']} · {connection['cliente']}")
        except oauth.NeedsReauth as exc:
            failed_count += 1
            rest.update(
                CONNECTIONS_TABLE,
                {"id": f"eq.{connection['id']}"},
                {"estado": "needs_reauth", "last_error": str(exc)[:500]},
            )
            rest.audit(
                "token_refresh_failed",
                slug=connection["integration_slug"],
                actor="worker",
                detail={"cliente": connection["cliente"]},
            )
            print(f"reauth {connection['integration_slug']} · {connection['cliente']}")
        except Exception as exc:
            failed_count += 1
            log.error("could not rotate %s: %s", connection["id"], exc)
            print(f"error  {connection['integration_slug']} · {connection['cliente']}: {exc}")
    return 1 if failed_count else 0


def _rotate_token(rest: _Rest, connection: dict, private_pem: str, public_pem: str) -> None:
    slug = connection["integration_slug"]
    integration = catalog.by_slug(slug)
    if integration is None:
        raise WorkerError(f"unknown integration: {slug}")

    client_id, client_secret = _active_credential(rest, slug, private_pem)
    current_token = crypto.unseal(connection["refresh_token_sealed"], private_pem)
    tokens = oauth.refresh(
        token_url=integration.token_url,
        client_id=client_id,
        client_secret=client_secret,
        refresh_token=current_token,
    )
    # The old token is already spent by the call above, so the replacement is
    # persisted before anything else can fail — and the previous generation is
    # kept so a crash here does not orphan the account.
    rest.update(
        CONNECTIONS_TABLE,
        {"id": f"eq.{connection['id']}"},
        {
            "refresh_token_sealed": crypto.seal(tokens.refresh_token, public_pem),
            "refresh_token_prev_sealed": connection["refresh_token_sealed"],
            "token_rotated_at": _now_iso(),
            "access_expires_at": _expiry_iso(tokens.expires_in),
            "last_error": "",
        },
    )
    rest.audit("token_refresh", slug=slug, actor="worker", detail={"cliente": connection["cliente"]})


def _expire_pending_grants(rest: _Rest) -> None:
    cutoff = (datetime.now(timezone.utc) - timedelta(minutes=GRANT_TTL_MINUTES)).isoformat()
    try:
        rest.update(
            PENDING_GRANTS_TABLE,
            {"estado": "eq.pendiente", "created_at": f"lt.{cutoff}"},
            {"estado": "vencido"},
        )
    except Exception as exc:
        log.warning("could not expire old grants: %s", exc)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expiry_iso(expires_in: int) -> str | None:
    if expires_in <= 0:
        return None
    return (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(prog="integrations.worker")
    parser.add_argument("command", choices=("keys", "grants", "refresh"))
    args = parser.parse_args(argv)

    commands = {"keys": command_keys, "grants": command_grants, "refresh": command_refresh}
    try:
        return commands[args.command]()
    except (WorkerError, crypto.SealError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
