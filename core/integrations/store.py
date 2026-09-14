"""Persistence for the integrations portal, over PostgREST.

Two invariants live in the migration's column-level GRANTs, not here:
`secret_sealed` and `refresh_token_sealed` can be written by the app and never
read back. That is why writes send `Prefer: return=minimal` — asking for the
representation forces a SELECT and PostgREST answers 403.
`core/persistence.py:431` hardcodes `return=representation`, so its transport
cannot be reused for this.

With no database configured, or before the migration has run, `open_stores()`
returns None and the page renders in its unconfigured state. Jenkins applies the
migrations after `compose up`, so a table missing for a moment is expected, not
exceptional.
"""
from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

SETTINGS_TABLE = "integration_settings"
CREDENTIALS_TABLE = "integration_credentials"
CONNECTIONS_TABLE = "integration_connections"
PENDING_GRANTS_TABLE = "integration_pending_grants"
AUDIT_TABLE = "integration_audit"
# Client accounts an authorization reaches, for providers where one consent
# covers many (Amazon Ads). Written by the worker; the app only reads.
ACCOUNTS_TABLE = "integration_accounts"

# Setting key that stores the public sealing key.
SEALING_KEY_SETTING = "sealing_public_key"

_TIMEOUT_S = 8

ACTIVE_STATUS = "activo"
INVALID_STATUS = "invalido"
PENDING_STATUS = "pendiente"
NEEDS_REAUTH = "needs_reauth"
REVOKED_STATUS = "revocado"

# The one provider that keeps its own copy of an account's state, in
# `meli_auth_identities`. Named here only so `set_status` can mirror onto it;
# this module stays otherwise provider-agnostic.
_MELI_SLUG = "mercado_libre"

# `secret_sealed` is deliberately absent: selecting it would 403 and take the
# whole page down with it.
_CREDENTIAL_COLUMNS = (
    "id,integration_slug,label,public_fields,secret_app,fingerprint,"
    "estado,created_by,rotated_by,created_at,updated_at"
)
_CONNECTION_COLUMNS = (
    "id,integration_slug,cliente,cuenta_externa_id,nombre_externo,marketplace,"
    "estado,scopes,consent_date,last_sync_at,last_error,conectado_por,"
    "token_rotated_at,metadata,created_at,updated_at"
)
_ACCOUNT_COLUMNS = (
    "id,integration_slug,cuenta_externa_id,nombre_externo,tipo,region,marketplaces,"
    "cliente,connection_id,profiles,first_seen_at,last_seen_at"
)


class StoreError(RuntimeError):
    """A write the user needs to see failed."""


@dataclass(frozen=True)
class CredentialStatus:
    slug: str
    fingerprint: str
    status: str
    created_by: str
    updated_at: str
    public_fields: dict = field(default_factory=dict)
    has_readable_secret: bool = False

    @property
    def is_active(self) -> bool:
        return self.status == ACTIVE_STATUS


@dataclass(frozen=True)
class Connection:
    id: int
    slug: str
    client: str
    external_account_id: str
    external_name: str
    marketplace: str
    status: str
    connected_by: str
    last_sync_at: str
    last_error: str
    consent_date: str
    metadata: dict = field(default_factory=dict)

    @property
    def is_healthy(self) -> bool:
        return self.status == ACTIVE_STATUS


@dataclass(frozen=True)
class ClientAccount:
    """A client's advertising account reached through an authorization.

    Only for providers with `discovers_accounts`; for Mercado Libre the
    `Connection` itself is the client account.
    """

    id: int
    slug: str
    external_id: str
    name: str
    account_type: str
    region: str
    marketplaces: tuple[str, ...]
    client: str
    connection_id: int | None
    profiles: tuple[dict, ...]
    first_seen_at: str
    last_seen_at: str


def fingerprint(value: str) -> str:
    """Names *which* credential is loaded without revealing any of it."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:6]


class _Rest:
    """Minimal PostgREST client that can write columns it cannot read."""

    def __init__(self, url: str, key: str, session: requests.Session | None = None):
        # `core/persistence.py:421` appends `/rest/v1` here for the same reason:
        # the VPS points SUPABASE_URL at `http://rest-gateway`, and its Caddy
        # strips `/rest/v1` before proxying to PostgREST (`handle_path /rest/v1/*`).
        # Without this, the portal talks straight to Caddy's fallback (200 with
        # body "rest-gateway") and every SELECT parses as garbage.
        base = url.rstrip("/")
        self._url = base if base.endswith("/rest/v1") else f"{base}/rest/v1"
        self._key = key
        self._session = session or requests.Session()

    def _headers(self, *, minimal: bool) -> dict:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal" if minimal else "return=representation",
        }

    def select(self, table: str, params: dict) -> list[dict]:
        response = self._session.get(
            f"{self._url}/{table}",
            params=params,
            headers=self._headers(minimal=False),
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()
        return response.json()

    def insert(self, table: str, row: dict) -> None:
        response = self._session.post(
            f"{self._url}/{table}",
            json=row,
            headers=self._headers(minimal=True),
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()

    def upsert(self, table: str, row: dict, on_conflict: str | None = None) -> None:
        """Insert that reconciles against the row a unique index already holds.

        Reauthorizing a seller account writes the same (slug, cuenta_externa_id)
        pair the table declares unique, so a plain insert raises 409 and the
        grant can never close. `on_conflict` names the columns of the unique
        constraint PostgREST should merge against — without it, PostgREST
        defaults to the primary key and treats the incoming row as new (still
        raising 409 on the secondary unique).
        """
        headers = self._headers(minimal=True)
        headers["Prefer"] = "return=minimal,resolution=merge-duplicates"
        params = {"on_conflict": on_conflict} if on_conflict else None
        response = self._session.post(
            f"{self._url}/{table}",
            json=row,
            params=params,
            headers=headers,
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()

    def update(self, table: str, params: dict, changes: dict, stamp: bool = True) -> None:
        changes = dict(changes)
        if stamp:
            # Most portal tables carry an updated_at trigger column; the few
            # that don't (meli_ingestion_runs, meli_locks) opt out via stamp=False.
            changes.setdefault("updated_at", datetime.now(timezone.utc).isoformat())
        response = self._session.patch(
            f"{self._url}/{table}",
            params=params,
            json=changes,
            headers=self._headers(minimal=True),
            timeout=_TIMEOUT_S,
        )
        response.raise_for_status()

    def get_setting(self, key: str) -> str | None:
        rows = self.select(SETTINGS_TABLE, {"select": "valor", "clave": f"eq.{key}", "limit": "1"})
        return (rows[0].get("valor") or None) if rows else None

    def upsert_setting(self, key: str, value: str, actor: str) -> None:
        existing = self.select(SETTINGS_TABLE, {"select": "clave", "clave": f"eq.{key}", "limit": "1"})
        if existing:
            self.update(SETTINGS_TABLE, {"clave": f"eq.{key}"}, {"valor": value, "updated_by": actor})
        else:
            self.insert(SETTINGS_TABLE, {"clave": key, "valor": value, "updated_by": actor})

    def audit(self, action: str, *, slug: str | None, actor: str, detail: dict | None = None) -> None:
        """The trail must never take down the operation it records."""
        try:
            self.insert(
                AUDIT_TABLE,
                {
                    "actor": actor or "unknown",
                    "accion": action,
                    "integration_slug": slug,
                    "detalle": detail or {},
                },
            )
        except Exception as exc:
            log.warning("integrations: could not audit %s/%s (%s)", action, slug, exc)


class SettingsStore:
    """Portal configuration that is not secret — today, the sealing public key.

    It lives in the database rather than an environment variable so an admin can
    generate it from the screen. Putting it in an env var would mean an SSH
    session, which is the thing this portal exists to remove.
    """

    def __init__(self, rest: _Rest):
        self._rest = rest

    def get(self, key: str) -> str | None:
        try:
            rows = self._rest.select(
                SETTINGS_TABLE, {"select": "valor", "clave": f"eq.{key}", "limit": "1"}
            )
        except Exception as exc:
            log.warning("integrations: could not read setting %s (%s)", key, exc)
            return None
        return (rows[0].get("valor") or None) if rows else None

    def set(self, key: str, value: str, user: str = "") -> None:
        try:
            existing = self._rest.select(
                SETTINGS_TABLE, {"select": "clave", "clave": f"eq.{key}", "limit": "1"}
            )
            if existing:
                self._rest.update(
                    SETTINGS_TABLE, {"clave": f"eq.{key}"}, {"valor": value, "updated_by": user}
                )
            else:
                self._rest.insert(
                    SETTINGS_TABLE, {"clave": key, "valor": value, "updated_by": user}
                )
        except Exception as exc:
            raise StoreError(_error_message(exc, "guardar la configuración")) from exc
        self._rest.audit("setting_set", slug=None, actor=user, detail={"clave": key})


class CredentialStore:
    """System-tier credentials: one per integration."""

    def __init__(self, rest: _Rest):
        self._rest = rest
        # An empty {} means two opposite things: "nothing stored" and "the read
        # failed". Without splitting them, an intermittent PostgREST paints
        # "Sin configurar" over credentials that actually exist.
        self.read_failed = False

    def list_states(self) -> dict[str, CredentialStatus]:
        self.read_failed = False
        try:
            rows = self._rest.select(
                CREDENTIALS_TABLE,
                {"select": _CREDENTIAL_COLUMNS, "estado": f"eq.{ACTIVE_STATUS}"},
            )
        except Exception as exc:
            log.warning("integrations: could not read credentials (%s)", exc)
            self.read_failed = True
            return {}
        return {row["integration_slug"]: _to_credential_status(row) for row in rows}

    def read_app_secret(self, slug: str) -> str | None:
        """The plaintext of an app-readable credential, or None for a sealed one."""
        try:
            rows = self._rest.select(
                CREDENTIALS_TABLE,
                {
                    "select": "secret_app",
                    "integration_slug": f"eq.{slug}",
                    "estado": f"eq.{ACTIVE_STATUS}",
                    "limit": "1",
                },
            )
        except Exception as exc:
            log.warning("integrations: could not read the secret for %s (%s)", slug, exc)
            return None
        return (rows[0].get("secret_app") or None) if rows else None

    def public_fields(self, slug: str) -> dict:
        status = self.list_states().get(slug)
        return status.public_fields if status else {}

    def was_removed(self, slug: str) -> bool:
        """True when an admin removed the credential (row exists, status=invalido).

        Used by the migration path to avoid resurrecting a credential the
        admin just retired: a row that lives in ``.env`` would otherwise be
        re-imported on every render because ``list_states`` only surfaces
        active rows.
        """
        try:
            rows = self._rest.select(
                CREDENTIALS_TABLE,
                {
                    "select": "id",
                    "integration_slug": f"eq.{slug}",
                    "estado": f"eq.{INVALID_STATUS}",
                    "limit": "1",
                },
            )
        except Exception as exc:
            log.warning("integrations: could not check tombstone for %s (%s)", slug, exc)
            return False
        return bool(rows)

    def save(
        self,
        *,
        slug: str,
        secret: str,
        sealed: bool,
        public_fields: dict | None = None,
        user: str = "",
    ) -> None:
        """Retires the live credential and writes the replacement.

        Two statements rather than an upsert: `ON CONFLICT DO UPDATE` reads
        `excluded` over the sealed column, which this role cannot select.
        """
        column = "secret_sealed" if sealed else "secret_app"
        try:
            self._soft_delete(slug, user)
            self._rest.insert(
                CREDENTIALS_TABLE,
                {
                    "integration_slug": slug,
                    "public_fields": public_fields or {},
                    column: secret,
                    "fingerprint": fingerprint(secret),
                    "estado": ACTIVE_STATUS,
                    "created_by": user,
                },
            )
        except Exception as exc:
            raise StoreError(_error_message(exc, "guardar la credencial")) from exc
        self._rest.audit("credential_create", slug=slug, actor=user)

    def remove(self, slug: str, user: str = "") -> None:
        """Marks the credential invalid. The row survives so the trail does."""
        try:
            self._soft_delete(slug, user)
        except Exception as exc:
            raise StoreError(_error_message(exc, "quitar la credencial")) from exc
        self._rest.audit("credential_disable", slug=slug, actor=user)

    def _soft_delete(self, slug: str, user: str) -> None:
        self._rest.update(
            CREDENTIALS_TABLE,
            {"integration_slug": f"eq.{slug}", "estado": f"eq.{ACTIVE_STATUS}"},
            {"estado": INVALID_STATUS, "rotated_by": user},
        )


class ConnectionStore:
    """Client-tier authorizations: N per integration, one per seller account."""

    def __init__(self, rest: _Rest):
        self._rest = rest
        self.read_failed = False

    def by_integration_slug(self) -> dict[str, list[Connection]]:
        self.read_failed = False
        try:
            rows = self._rest.select(
                CONNECTIONS_TABLE,
                {"select": _CONNECTION_COLUMNS, "order": "cliente.asc"},
            )
        except Exception as exc:
            log.warning("integrations: could not read connections (%s)", exc)
            self.read_failed = True
            return {}
        grouped: dict[str, list[Connection]] = {}
        for row in rows:
            connection = _to_connection(row)
            grouped.setdefault(connection.slug, []).append(connection)
        return grouped

    def accounts_by_integration_slug(self) -> dict[str, list[ClientAccount]]:
        """Client accounts discovered by the worker, grouped by provider.

        A missing table (migration not applied yet) reads as no accounts, not
        as a broken page: the authorizations still render on their own.
        """
        try:
            rows = self._rest.select(
                ACCOUNTS_TABLE,
                {"select": _ACCOUNT_COLUMNS, "order": "nombre_externo.asc"},
            )
        except Exception as exc:
            log.warning("integrations: could not read client accounts (%s)", exc)
            return {}
        grouped: dict[str, list[ClientAccount]] = {}
        for row in rows:
            account = _to_client_account(row)
            grouped.setdefault(account.slug, []).append(account)
        return grouped

    def open_grant(
        self,
        *,
        slug: str,
        client: str,
        marketplace: str,
        state: str,
        verifier_sealed: str,
        user: str,
    ) -> None:
        """Records an in-flight authorization. The row is the state, not the tab."""
        try:
            self._rest.insert(
                PENDING_GRANTS_TABLE,
                {
                    "integration_slug": slug,
                    "cliente": client,
                    "marketplace": marketplace,
                    "state": state,
                    "verifier_sealed": verifier_sealed,
                    "solicitado_por": user,
                },
            )
        except Exception as exc:
            raise StoreError(_error_message(exc, "iniciar la autorización")) from exc
        self._rest.audit("grant_start", slug=slug, actor=user, detail={"cliente": client})

    def record_code(self, *, state: str, code_sealed: str) -> bool:
        """Hands the sealed code to the worker. False if the state is unknown."""
        try:
            rows = self._rest.select(
                PENDING_GRANTS_TABLE,
                {"select": "id", "state": f"eq.{state}", "estado": f"eq.{PENDING_STATUS}", "limit": "1"},
            )
            if not rows:
                return False
            self._rest.update(
                PENDING_GRANTS_TABLE,
                {"state": f"eq.{state}"},
                {"code_sealed": code_sealed, "estado": "recibido"},
            )
        except Exception as exc:
            log.warning("integrations: could not record the code (%s)", exc)
            return False
        return True

    def pending_grants(self) -> list[dict]:
        try:
            return self._rest.select(
                PENDING_GRANTS_TABLE,
                {
                    "select": "id,integration_slug,cliente,marketplace,estado,created_at",
                    "estado": f"in.({PENDING_STATUS},recibido)",
                    "order": "created_at.desc",
                },
            )
        except Exception as exc:
            log.warning("integrations: could not read pending grants (%s)", exc)
            return []

    def set_status(self, *, connection_id: int, status: str, user: str, slug: str) -> None:
        try:
            self._rest.update(CONNECTIONS_TABLE, {"id": f"eq.{connection_id}"}, {"estado": status})
        except Exception as exc:
            raise StoreError(_error_message(exc, "cambiar el estado de la cuenta")) from exc
        self._rest.audit(
            f"connection_{status}", slug=slug, actor=user, detail={"connection_id": connection_id}
        )
        self._mirror_status_on_provider(connection_id=connection_id, status=status, slug=slug)

    def _mirror_status_on_provider(self, *, connection_id: int, status: str,
                                   slug: str) -> None:
        """Carry the new state to the provider's own account table, if it keeps one.

        Mercado Libre mirrors every connection in `meli_auth_identities`, and the
        two disagreeing is what makes a disconnected account still look live to
        anything scheduling off the identity. Only the ingest worker's failure
        paths used to mirror, so a disconnection from the portal left the tables
        out of step — observed in production on 2026-09-09, `revocado` on the
        connection against `activo` on the identity.

        Doing it here rather than in the UI covers every caller at once: the
        remove dialog today, and whatever revokes a connection tomorrow.

        Deferred import behind the slug guard, for the same reason
        `worker._first_sync_meli` uses one — this module is provider-agnostic
        and must not drag the Mercado Libre pipeline in to touch a Walmart
        credential.

        Failures are logged, never raised. The status change is already
        committed and audited above; an operator who asked to disconnect an
        account must not see that fail because a mirror write did.
        """
        if slug != _MELI_SLUG:
            return
        try:
            rows = self._rest.select(
                CONNECTIONS_TABLE,
                {
                    "select": "cuenta_externa_id",
                    "id": f"eq.{connection_id}",
                    "limit": "1",
                },
            )
            external_id = str((rows or [{}])[0].get("cuenta_externa_id") or "")
            from core.meli_api.ingest import mirror_identity_status

            mirror_identity_status(self._rest, external_id, status)
        except Exception as exc:
            log.warning("could not mirror connection %s state onto its identity: %s",
                        connection_id, exc)


def _to_credential_status(row: dict) -> CredentialStatus:
    return CredentialStatus(
        slug=row.get("integration_slug", ""),
        fingerprint=row.get("fingerprint") or "",
        status=row.get("estado") or "",
        created_by=row.get("created_by") or "",
        updated_at=row.get("updated_at") or "",
        public_fields=row.get("public_fields") or {},
        has_readable_secret=bool(row.get("secret_app")),
    )


def _to_connection(row: dict) -> Connection:
    return Connection(
        id=int(row.get("id") or 0),
        slug=row.get("integration_slug", ""),
        client=row.get("cliente") or "",
        external_account_id=row.get("cuenta_externa_id") or "",
        external_name=row.get("nombre_externo") or "",
        marketplace=row.get("marketplace") or "",
        status=row.get("estado") or "",
        connected_by=row.get("conectado_por") or "",
        last_sync_at=row.get("last_sync_at") or "",
        last_error=row.get("last_error") or "",
        consent_date=row.get("consent_date") or "",
        metadata=row.get("metadata") or {},
    )


def _to_client_account(row: dict) -> ClientAccount:
    connection_id = row.get("connection_id")
    return ClientAccount(
        id=int(row.get("id") or 0),
        slug=row.get("integration_slug", ""),
        external_id=row.get("cuenta_externa_id") or "",
        name=row.get("nombre_externo") or "",
        account_type=row.get("tipo") or "",
        region=row.get("region") or "",
        marketplaces=tuple(row.get("marketplaces") or ()),
        client=row.get("cliente") or "",
        connection_id=int(connection_id) if connection_id is not None else None,
        profiles=tuple(row.get("profiles") or ()),
        first_seen_at=row.get("first_seen_at") or "",
        last_seen_at=row.get("last_seen_at") or "",
    )


def _error_message(exc: Exception, action: str) -> str:
    """Translate the failure into something a person can act on.

    A urllib3 dump on screen helps nobody: the cause is logged and the user
    gets the next step.
    """
    log.error("integrations: failed to %s (%s)", action, exc)

    if isinstance(exc, requests.HTTPError) and exc.response is not None:
        code = exc.response.status_code
        if code == 404:
            return (
                f"No se pudo {action}: al portal le falta su tabla en la base de datos. "
                "Es un paso de instalación del servidor; avisale al equipo de sistemas."
            )
        if code in (401, 403):
            return (
                f"No se pudo {action}: la aplicación no tiene permiso sobre esa tabla. "
                "Avisale al equipo de sistemas."
            )
        if code >= 500:
            return f"No se pudo {action}: la base de datos respondió con un error. Probá de nuevo en un minuto."
        return f"No se pudo {action}: la base de datos rechazó el pedido."

    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return (
            f"No se pudo {action}: el portal no llega a la base de datos. "
            "Suele ser algo del servidor; avisale al equipo de sistemas."
        )

    return f"No se pudo {action}. Quedó registrado en el log del servidor."


def _rest_credentials() -> tuple[str, str] | None:
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_KEY", "").strip()
    if not (url and key):
        try:
            import streamlit as st  # deferred: core must import without Streamlit

            conf = st.secrets.get("supabase", {})
            url = url or str(conf.get("url", "")).strip()
            key = key or str(conf.get("key", "")).strip()
        except Exception:
            pass
    return (url, key) if (url and key) else None


def open_stores() -> tuple[CredentialStore, ConnectionStore, SettingsStore] | None:
    """The three stores, or None when there is no database configured."""
    credentials = _rest_credentials()
    if credentials is None:
        return None
    rest = _Rest(*credentials)
    return CredentialStore(rest), ConnectionStore(rest), SettingsStore(rest)
