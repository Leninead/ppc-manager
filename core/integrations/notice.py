"""How many things need a person to act: authorizations dead or about to die, and sync alerts.

The sidebar reads this on every Streamlit rerun to decide whether to mark the
Integrations, Connected-accounts and Request-log links. That is why the reads
are cached and never propagate a failure: a database hiccup can't take the
whole navigation down.

Counting the consents that are about to expire, not only the ones already in
`needs_reauth`, is what turns a 365-day cliff into a warning with time to act.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import streamlit as st

from core.integrations import catalog, consent_expiry
from core.integrations.store import ACTIVE_STATUS, NEEDS_REAUTH, _Rest, _rest_credentials, open_stores
from core.integrations.sync_alerts import ERROR, load_alerts

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


@st.cache_data(ttl=60, show_spinner=False)
def sync_alert_counts() -> tuple[int, int]:
    """(errors, warnings) the request log shows. (0, 0) also without a database or when the read fails."""
    try:
        credentials = _rest_credentials()
        if credentials is None:
            return 0, 0
        alerts, _ = load_alerts(_Rest(*credentials), datetime.now(timezone.utc))
    except Exception as exc:
        log.warning("sync alerts: could not count them for the sidebar (%s)", exc)
        return 0, 0
    errors = sum(1 for alert in alerts if alert.severity == ERROR)
    return errors, len(alerts) - errors
