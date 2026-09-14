"""How many authorizations need a person to act: dead, or about to die.

The sidebar reads this on every Streamlit rerun to decide whether to mark the
Integrations and Connected-accounts links. That is why the read is cached and
never propagates a failure: a database hiccup can't take the whole navigation
down.

Counting the consents that are about to expire, not only the ones already in
`needs_reauth`, is what turns a 365-day cliff into a warning with time to act.
"""
from __future__ import annotations

import logging

import streamlit as st

from core.integrations import catalog, consent_expiry
from core.integrations.store import ACTIVE_STATUS, NEEDS_REAUTH, open_stores

log = logging.getLogger(__name__)


def needs_attention(connection) -> bool:
    """Dead consent, or a live one inside the expiry warning window."""
    status = (connection.status or "").strip().lower()
    if status == NEEDS_REAUTH:
        return True
    if status != ACTIVE_STATUS:
        return False
    integration = catalog.by_slug(connection.slug)
    lifetime = integration.refresh_token_lifetime_days if integration else 0
    return consent_expiry.is_expiring_soon(connection.consent_date, lifetime)


@st.cache_data(ttl=60, show_spinner=False)
def accounts_needing_reauth() -> int:
    """Authorizations to reauthorize, now or soon. Zero also when there is no database."""
    try:
        stores = open_stores()
    except Exception as exc:
        log.warning("integrations: could not open the database for the notice (%s)", exc)
        return 0
    if stores is None:
        return 0
    _, connections, _ = stores
    return sum(
        1
        for accounts in connections.by_integration_slug().values()
        for account in accounts
        if needs_attention(account)
    )
