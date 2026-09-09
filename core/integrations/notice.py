"""How many client accounts need the vendor to re-authorize.

The sidebar reads this on every Streamlit rerun to decide whether to mark the
Integrations link. That is why the read is cached and never propagates a
failure: a database hiccup can't take the whole navigation down.
"""
from __future__ import annotations

import logging

import streamlit as st

from core.integrations.store import open_stores

log = logging.getLogger(__name__)

REVOKED_STATE = "needs_reauth"


@st.cache_data(ttl=60, show_spinner=False)
def accounts_needing_reauth() -> int:
    """Accounts whose consent expired. Zero also when there is no database."""
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
        if account.status == REVOKED_STATE
    )
