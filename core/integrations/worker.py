"""Worker side of the integrations portal — the only place secrets are opened.

Runs from an ephemeral container that mounts the key volume and carries the
worker JWT. The always-on app container has neither, so a full compromise of
Streamlit yields sealed blobs and nothing else.

Installing the worker IS running it: the keypair is created on first run and the
public half published to the database, so nobody carries a key between a browser
and a server.

    python -m core.integrations.worker keys      install / verify the keypair
    python -m core.integrations.worker grants    exchange authorization codes
    python -m core.integrations.worker refresh   rotate refresh tokens, expire consents
    python -m core.integrations.worker discover  re-list the client accounts each
                                                 authorization reaches, without
                                                 asking anyone to consent again

Provider-specific knowledge lives in two places only: the catalog (hosts,
scopes, whether the refresh token rotates, how long a consent lives) and the
identity resolver registered per slug below. Everything else here is generic.
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

from core.integrations import amazon_identity, catalog, crypto, oauth
from core.integrations.connection_identity import ConnectionIdentity
from core.integrations.store import (
    ACCOUNTS_TABLE,
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
# Login with Amazon codes die after 5 minutes, Mercado Libre's after 10. A code
# received earlier than this cannot be exchanged any more, and trying reads as
# "the permission expired", which sends the operator after the wrong cause.
CODE_TTL_MINUTES = 10
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
            "select": "id,integration_slug,cliente,marketplace,state,verifier_sealed,"
                      "code_sealed,solicitado_por",
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
                {"estado": "fallido", "error": _grant_failure_text(exc)},
            )
            rest.audit("grant_failed", slug=slug, actor="worker", detail={"error": type(exc).__name__})
            print(f"error {slug} · {pending['cliente']}: {exc}")

    # After the loop, never inside it: every grant gets exchanged and committed
    # before a single (slow) sync starts, so a sync that hangs cannot strand a
    # later authorization in `recibido`.
    _first_sync_meli(connected)
    return 1 if failed_count else 0


def _grant_failure_text(exc: Exception) -> str:
    """`invalid_grant` on an authorization code means the code expired or was
    already used — the worker got there late — not that a permission lapsed."""
    if isinstance(exc, oauth.NeedsReauth):
        return f"el código de autorización venció o ya fue usado; hay que autorizar de nuevo ({exc})"[:500]
    return str(exc)[:500]


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


def _meli_identity(tokens: oauth.TokenSet, *, client_id: str, requested_by: str) -> ConnectionIdentity:
    """The seller who consented is the client account: one row, named after the
    nickname, disambiguated by site on a collision."""
    _ = (client_id, requested_by)
    nickname, site_id = _fetch_meli_identity(tokens.access_token)
    return ConnectionIdentity(
        external_id=tokens.user_id,
        client_base=nickname,
        external_name=nickname,
        marketplace=site_id,
        collision_suffix=site_id.lower(),
    )


# Who a token belongs to is the one question each provider answers its own way.
_IDENTITY_RESOLVERS = {
    _MELI_SLUG: _meli_identity,
    amazon_identity.SLUG: amazon_identity.resolve_identity,
}


def _resolve_identity(slug: str, tokens: oauth.TokenSet, *, client_id: str,
                      requested_by: str, pending: dict | None = None) -> ConnectionIdentity:
    resolver = _IDENTITY_RESOLVERS.get(slug)
    if resolver is not None:
        return resolver(tokens, client_id=client_id, requested_by=requested_by)
    if not tokens.user_id:
        # Without a stable id every grant would upsert onto the same
        # (slug, '') row and silently overwrite the previous account's token.
        raise WorkerError(f"{slug} returned no account id and has no identity resolver")
    placeholders = pending or {}
    return ConnectionIdentity(
        external_id=tokens.user_id,
        client_base=placeholders.get("cliente") or tokens.user_id,
        marketplace=placeholders.get("marketplace") or "",
    )


def _resolve_client_slug(rest: _Rest, table: str, slug: str, client_base: str,
                         external_account_id: str, suffix: str) -> str:
    """Resolve slug collisions: same label across two different accounts.

    The unique constraint is (integration_slug, cuenta_externa_id) — two
    accounts *can* share the `cliente` label, but that leaves the agency
    guessing which is which. If the base slug is already taken by a
    different external id, suffix it (site for MELI, region for Amazon).
    """
    try:
        rows = rest.select(
            table,
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
    if not others or not suffix:
        return client_base
    return f"{client_base}-{suffix}"


def _exchange_grant(rest: _Rest, pending: dict, private_pem: str,
                    redirect_uri: str) -> str:
    """Close one grant and return the `cliente` slug the connection ended up on.

    The slug is the caller's only way to know *which* account just came online:
    the pending row carries a `_pending_xxx` placeholder and the real one is
    resolved here by the provider's identity resolver. `command_grants` uses it
    to sync a Mercado Libre account immediately instead of leaving it empty
    until the nightly ingest.
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

    requested_by = pending.get("solicitado_por") or ""
    identity = _resolve_identity(slug, tokens, client_id=client_id,
                                 requested_by=requested_by, pending=pending)
    client = _resolve_client_slug(rest, CONNECTIONS_TABLE, slug, _slugify(identity.client_base),
                                  identity.external_id, identity.collision_suffix)

    public_pem = crypto.public_from_private(private_pem)

    # Upsert, not insert: reauthorizing carries the same cuenta_externa_id,
    # which the table declares unique together with the slug. A plain insert
    # died with 409 and the account stayed in needs_reauth forever.
    rest.upsert(
        CONNECTIONS_TABLE,
        {
            "integration_slug": slug,
            "cliente": client,
            "cuenta_externa_id": identity.external_id,
            "nombre_externo": identity.external_name,
            "marketplace": identity.marketplace,
            "refresh_token_sealed": crypto.seal(tokens.refresh_token, public_pem),
            "token_rotated_at": _now_iso(),
            "access_expires_at": _expiry_iso(tokens.expires_in),
            # Login with Amazon does not echo the scopes back; the catalog knows.
            "scopes": list(tokens.scopes) or list(integration.scopes),
            "estado": "activo",
            # The merge only overwrites columns in the payload: without this a
            # successful exchange would leave the previous error visible on screen.
            "last_error": "",
            "consent_date": date.today().isoformat(),
            "conectado_por": requested_by,
            "metadata": identity.metadata,
        },
        on_conflict="integration_slug,cuenta_externa_id",
    )
    if integration.discovers_accounts:
        _store_discovered_accounts(rest, slug, identity)

    rest.update(PENDING_GRANTS_TABLE, {"id": f"eq.{pending['id']}"}, {"estado": "canjeado"})
    rest.audit("grant_exchanged", slug=slug, actor="worker",
               detail={"cliente": client, "accounts": len(identity.accounts)})
    return client


def _connection_id(rest: _Rest, slug: str, external_id: str) -> int | None:
    rows = rest.select(
        CONNECTIONS_TABLE,
        {
            "select": "id",
            "integration_slug": f"eq.{slug}",
            "cuenta_externa_id": f"eq.{external_id}",
            "limit": "1",
        },
    )
    return int(rows[0]["id"]) if rows else None


def _store_discovered_accounts(rest: _Rest, slug: str, identity: ConnectionIdentity,
                               connection_id: int | None = None) -> None:
    """One `integration_accounts` row per client account the authorization
    reaches, keyed by the provider's entity id so the same client seen by two
    employees is one row that points at whoever saw it last.

    `cliente` is only written for a row that does not exist yet: it is the
    label the agency may edit later, and a re-discovery must not undo that.
    """
    if connection_id is None:
        connection_id = _connection_id(rest, slug, identity.external_id)
    existing = {
        str(row.get("cuenta_externa_id") or "")
        for row in rest.select(
            ACCOUNTS_TABLE,
            {"select": "cuenta_externa_id", "integration_slug": f"eq.{slug}"},
        )
    }
    seen_at = _now_iso()
    for account in identity.accounts:
        row = {
            "integration_slug": slug,
            "cuenta_externa_id": account.external_id,
            "nombre_externo": account.name,
            "tipo": account.account_type,
            "region": account.region,
            "marketplaces": list(account.marketplaces),
            "connection_id": connection_id,
            "profiles": list(account.profiles),
            "last_seen_at": seen_at,
            "updated_at": seen_at,
        }
        if account.external_id not in existing:
            row["cliente"] = _resolve_client_slug(
                rest, ACCOUNTS_TABLE, slug, _slugify(account.name),
                account.external_id, account.region.lower(),
            )
        rest.upsert(ACCOUNTS_TABLE, row, on_conflict="integration_slug,cuenta_externa_id")
    log.info("%s: %d client accounts recorded for %s", slug, len(identity.accounts),
             identity.external_id)


def command_refresh() -> int:
    rest = _rest_worker()
    private_pem = ensure_keys(rest)
    public_pem = crypto.public_from_private(private_pem)

    _expire_consents(rest)

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
            _mark_needs_reauth(rest, connection, exc)
            print(f"reauth {connection['integration_slug']} · {connection['cliente']}")
        except Exception as exc:
            failed_count += 1
            log.error("could not rotate %s: %s", connection["id"], exc)
            print(f"error  {connection['integration_slug']} · {connection['cliente']}: {exc}")
    return 1 if failed_count else 0


def _mark_needs_reauth(rest: _Rest, connection: dict, exc: Exception) -> None:
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


def _rotate_token(rest: _Rest, connection: dict, private_pem: str, public_pem: str) -> oauth.TokenSet:
    """Mint a fresh access token and persist whatever the provider handed back.

    A rotating provider (Mercado Libre) has already spent the old token by the
    time this returns, so the replacement is persisted before anything else can
    fail — and the previous generation is kept so a crash here does not orphan
    the account. A non-rotating one (Login with Amazon) keeps its token; only
    the timestamps move, which is what makes this pass a liveness probe.
    """
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
        rotates=integration.refresh_rotates,
    )
    changes = {
        "token_rotated_at": _now_iso(),
        "access_expires_at": _expiry_iso(tokens.expires_in),
        "last_error": "",
    }
    if integration.refresh_rotates or tokens.refresh_token != current_token:
        changes["refresh_token_sealed"] = crypto.seal(tokens.refresh_token, public_pem)
    if integration.refresh_rotates:
        changes["refresh_token_prev_sealed"] = connection["refresh_token_sealed"]
    rest.update(CONNECTIONS_TABLE, {"id": f"eq.{connection['id']}"}, changes)
    rest.audit("token_refresh", slug=slug, actor="worker", detail={"cliente": connection["cliente"]})
    return tokens


def _expire_consents(rest: _Rest) -> None:
    """A consent past its provider's lifetime is dead whether or not the token
    still answers: mark it before anyone relies on it. Never breaks the run."""
    today = date.today()
    for integration in catalog.all_integrations():
        lifetime = integration.refresh_token_lifetime_days
        if lifetime <= 0:
            continue
        cutoff = (today - timedelta(days=lifetime)).isoformat()
        try:
            rows = rest.select(
                CONNECTIONS_TABLE,
                {
                    "select": "id,cliente,consent_date",
                    "integration_slug": f"eq.{integration.slug}",
                    "estado": "eq.activo",
                    "consent_date": f"lt.{cutoff}",
                },
            )
            for row in rows:
                rest.update(
                    CONNECTIONS_TABLE,
                    {"id": f"eq.{row['id']}"},
                    {"estado": "needs_reauth",
                     "last_error": f"el consentimiento venció ({lifetime} días)"},
                )
                rest.audit("consent_expired", slug=integration.slug, actor="worker",
                           detail={"cliente": row.get("cliente"),
                                   "consent_date": row.get("consent_date")})
                print(f"expired {integration.slug} · {row.get('cliente')}")
        except Exception as exc:
            log.warning("could not expire consents for %s: %s", integration.slug, exc)


def command_discover() -> int:
    """Re-run identity discovery on every live authorization of a provider whose
    accounts are discovered, so a client added to an employee's Amazon user
    shows up without asking that employee to consent again."""
    rest = _rest_worker()
    private_pem = ensure_keys(rest)
    public_pem = crypto.public_from_private(private_pem)

    slugs = [i.slug for i in catalog.all_integrations() if i.discovers_accounts]
    if not slugs:
        print("no integration discovers accounts")
        return 0
    connections = rest.select(
        CONNECTIONS_TABLE,
        {
            "select": "id,integration_slug,cliente,cuenta_externa_id,refresh_token_sealed,conectado_por",
            "integration_slug": f"in.({','.join(slugs)})",
            "estado": "eq.activo",
        },
    )
    if not connections:
        print("no authorizations to discover")
        return 0

    failed_count = 0
    for connection in connections:
        slug = connection["integration_slug"]
        try:
            tokens = _rotate_token(rest, connection, private_pem, public_pem)
            client_id, _ = _active_credential(rest, slug, private_pem)
            identity = _resolve_identity(slug, tokens, client_id=client_id,
                                         requested_by=connection.get("conectado_por") or "")
            if identity.external_id != connection["cuenta_externa_id"]:
                raise WorkerError(
                    f"token answers for {identity.external_id}, row is {connection['cuenta_externa_id']}"
                )
            rest.update(
                CONNECTIONS_TABLE,
                {"id": f"eq.{connection['id']}"},
                {"marketplace": identity.marketplace, "metadata": identity.metadata},
            )
            _store_discovered_accounts(rest, slug, identity, connection_id=int(connection["id"]))
            print(f"ok    {slug} · {connection['cliente']} · {len(identity.accounts)} accounts")
        except oauth.NeedsReauth as exc:
            failed_count += 1
            _mark_needs_reauth(rest, connection, exc)
            print(f"reauth {slug} · {connection['cliente']}")
        except Exception as exc:
            failed_count += 1
            log.error("could not discover %s: %s", connection["id"], exc)
            print(f"error  {slug} · {connection['cliente']}: {exc}")
    return 1 if failed_count else 0


def _expire_pending_grants(rest: _Rest) -> None:
    now = datetime.now(timezone.utc)
    stale_pending = (now - timedelta(minutes=GRANT_TTL_MINUTES)).isoformat()
    stale_received = (now - timedelta(minutes=CODE_TTL_MINUTES)).isoformat()
    try:
        rest.update(
            PENDING_GRANTS_TABLE,
            {"estado": "eq.pendiente", "created_at": f"lt.{stale_pending}"},
            {"estado": "vencido"},
        )
        rest.update(
            PENDING_GRANTS_TABLE,
            {"estado": "eq.recibido", "updated_at": f"lt.{stale_received}"},
            {"estado": "vencido",
             "error": "el código de autorización venció antes de que el worker lo canjeara"},
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
    parser.add_argument("command", choices=("keys", "grants", "refresh", "discover"))
    args = parser.parse_args(argv)

    commands = {
        "keys": command_keys,
        "grants": command_grants,
        "refresh": command_refresh,
        "discover": command_discover,
    }
    try:
        return commands[args.command]()
    except (WorkerError, crypto.SealError, requests.RequestException) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
