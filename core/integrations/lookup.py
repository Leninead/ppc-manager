"""The portal is the single source of truth for credentials.

The app reads from the database and from nowhere else. Environment variables and
`secrets.toml` are NOT a fallback — having three places where a key can live is
the sprawl this portal exists to end — they are a MIGRATION SOURCE. The first
time one is found, it is imported into the database and from then on there is
one copy only.

If the import cannot be performed (no database yet), the old value is returned
so the module that consumes it does not break, but the state is reported as
pending migration instead of pretending everything is fine.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass

import streamlit as st

from core.integrations import catalog
from core.integrations.store import StoreError, open_stores

log = logging.getLogger(__name__)

PORTAL = "portal"
PENDING_MIGRATION = "pendiente_de_migrar"
NONE_SRC = "ninguna"

_TTL_S = 60


@dataclass(frozen=True)
class Origin:
    source: str
    detail: str = ""

    @property
    def is_configured(self) -> bool:
        return self.source != NONE_SRC

    @property
    def pending_migration(self) -> bool:
        return self.source == PENDING_MIGRATION


def system_secret(slug: str) -> str | None:
    """The secret an integration must use."""
    return _resolve(slug)[0]


def invalidate_cache() -> None:
    """After a save, the new credential must count immediately.

    Without this the screen would say "loaded" for up to a minute before the
    module that consumes it actually uses the new value.
    """
    _read_from_portal.clear()


def origin_of(slug: str) -> Origin:
    """Where the credential lives, without returning it."""
    return _resolve(slug)[1]


def _resolve(slug: str) -> tuple[str | None, Origin]:
    integration = catalog.by_slug(slug)
    if integration is None:
        return None, Origin(NONE_SRC)

    from_portal = _from_portal(slug)
    if from_portal:
        return from_portal, Origin(PORTAL)

    inherited, detail = _inherited(integration)
    if not inherited:
        return None, Origin(NONE_SRC)

    # If an admin already removed the credential from the portal, do NOT
    # re-import it from env/secrets on the next render — otherwise "Quitar"
    # is a lie: the row would be resurrected on every load.
    stores = open_stores()
    if stores is not None and stores[0].was_removed(slug):
        return None, Origin(NONE_SRC)

    if _import(slug, inherited, detail):
        invalidate_cache()
        # This string composes into UI copy at
        # modules/pages/integrations.py L697 ("Quedó en {origen.detail}"),
        # so the leading label stays Spanish to keep the sentence uniform.
        return inherited, Origin(PORTAL, f"importada de {detail}")
    return inherited, Origin(PENDING_MIGRATION, detail)


def _inherited(integration) -> tuple[str, str]:
    """Where the credential lived before the portal. Only for migrating it."""
    if integration.env_var:
        value = os.environ.get(integration.env_var, "").strip()
        if value:
            return value, integration.env_var
    if integration.secrets_section:
        value = _from_secrets(integration.secrets_section, integration.secrets_key)
        if value:
            return value, f"{integration.secrets_section}.{integration.secrets_key}"
    return "", ""


def _import(slug: str, value: str, detail: str) -> bool:
    stores = open_stores()
    if stores is None:
        return False
    try:
        stores[0].save(
            # `user` lands in `integration_credentials.created_by` and
            # surfaces in the UI (integrations.py L471: "Cargada por"),
            # so the label stays Spanish.
            slug=slug, secret=value, sealed=False, user=f"migración desde {detail}"
        )
    except (StoreError, Exception) as exc:
        log.warning("integrations: could not migrate %s from %s (%s)", slug, detail, exc)
        return False
    log.info("integrations: %s migrated from %s into the portal", slug, detail)
    return True


def _from_portal(slug: str) -> str | None:
    return _read_from_portal(slug)


# Only the network call is cached. The environment and secrets.toml are read
# live every time: they are cheap, and caching them would delay a change
# becoming visible. It is global on purpose — a system credential is the same
# for every user, unlike a client token, which is never shared across sessions.
@st.cache_data(ttl=_TTL_S, show_spinner=False)
def _read_from_portal(slug: str) -> str | None:
    stores = open_stores()
    if stores is None:
        return None
    return stores[0].read_app_secret(slug)


def _from_secrets(section: str, key: str) -> str:
    try:
        return str(st.secrets.get(section, {}).get(key, "")).strip()
    except Exception:
        return ""
