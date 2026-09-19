"""Which Amazon Ads accounts a chat turn may reach, and in which region.

There is no control for this in the UI, on purpose. An AM asking the chat about
a client should not have to find a dropdown first: the chat has the analysis in
front of it and can ask "which client?" like a person would. What this module
supplies is the credential vehicle and the region, not the choice.

Two things pin a session and only one of them is negotiable:

* The **account** does not. Amazon's MCP takes the credentials alone (its
  "dynamic" default) and lets the model name the account on each call, which is
  the mode Amazon documents for agencies. The token belongs to the employee's
  authorization, not to any one account, and one authorization reaches every
  client that employee sees. So any active account works as the vehicle.

* The **region** does. `advertising-ai.amazon.com`, `-eu` and `-fe` are separate
  endpoints and a session opened on one cannot see the others' accounts. So a
  region has to be chosen before the session opens, from whatever the turn knows
  — the country of the analysis on screen — falling back to wherever the agency
  keeps most of its accounts.

The trade this makes: `FIXED` used to guarantee that no tool could read another
client's data. That guarantee is now a prompt instruction plus the audit trail.
It is not a privilege escalation — the employee already sees these accounts in
Amazon's own console, and every exposed tool is read-only — but a confused model
could show the wrong client's numbers, which is why the agent is told to name
the account it answers about.
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass

import streamlit as st

from ai import config as ai_config
from core.integrations.store import ACTIVE_STATUS, ClientAccount, Connection, open_stores

SLUG = "amazon_ads"
_CACHE_TTL_S = 120

# Amazon groups marketplaces into three advertising regions. Only the countries
# the agency actually sells in need to be right; an unknown one falls through to
# the busiest region rather than failing the turn.
_REGION_BY_COUNTRY = {
    "US": "NA", "CA": "NA", "MX": "NA", "BR": "NA",
    "UK": "EU", "GB": "EU", "DE": "EU", "FR": "EU", "ES": "EU", "IT": "EU",
    "NL": "EU", "SE": "EU", "PL": "EU", "BE": "EU", "IE": "EU", "TR": "EU",
    "EG": "EU", "SA": "EU", "AE": "EU", "IN": "EU", "ZA": "EU",
    "JP": "FE", "AU": "FE", "SG": "FE",
}
_DEFAULT_REGION = "NA"


@dataclass(frozen=True)
class AccountVehicle:
    """An active account used to reach a region: credentials plus its region."""

    account_id: int
    profile_id: str
    region: str
    country_code: str
    client: str


def region_for_country(country_code: str | None) -> str | None:
    """The advertising region a marketplace belongs to, or None if unknown."""
    return _REGION_BY_COUNTRY.get(str(country_code or "").strip().upper())


def build_vehicles(accounts: Iterable[ClientAccount],
                   connections: Iterable[Connection]) -> list[AccountVehicle]:
    """Every (account, profile) behind a live authorization, region resolved."""
    active = {c.id for c in connections if c.slug == SLUG and c.status == ACTIVE_STATUS}
    vehicles: list[AccountVehicle] = []
    for account in accounts:
        if account.slug != SLUG or account.connection_id not in active:
            continue
        for profile in account.profiles:
            profile_id = str(profile.get("profile_id") or "").strip()
            if not profile_id.isdigit():
                continue
            country = str(profile.get("country_code") or "").upper()
            # The account's own region is the authority; the country only fills
            # in when discovery could not record one.
            region = str(account.region or "").upper() or region_for_country(country)
            if not region:
                continue
            vehicles.append(AccountVehicle(
                account_id=account.id, profile_id=profile_id, region=region,
                country_code=country, client=account.client or account.name or "",
            ))
    vehicles.sort(key=lambda v: (v.client.lower(), v.country_code, v.profile_id))
    return vehicles


def pick_vehicle(vehicles: list[AccountVehicle],
                 country_hint: str | None = None) -> AccountVehicle | None:
    """One account that opens a session in the right region.

    The hint is the country of whatever the AM is looking at. With no usable
    hint the busiest region wins, which is where an agency's next question is
    most likely to land.
    """
    if not vehicles:
        return None
    wanted = region_for_country(country_hint)
    if wanted:
        in_region = [v for v in vehicles if v.region == wanted]
        if in_region:
            return in_region[0]
    busiest = Counter(v.region for v in vehicles).most_common(1)[0][0]
    fallback = [v for v in vehicles if v.region == busiest] or vehicles
    return fallback[0]


@st.cache_data(ttl=_CACHE_TTL_S, show_spinner=False)
def _load_vehicles() -> list[AccountVehicle]:
    stores = open_stores()
    if stores is None:
        return []
    _, connection_store, _ = stores
    try:
        accounts = connection_store.accounts_by_integration_slug().get(SLUG, [])
        connections = connection_store.by_integration_slug().get(SLUG, [])
    except Exception:  # noqa: BLE001 — a portal hiccup must not take the chat down
        return []
    return build_vehicles(accounts, connections)


def reachable_accounts() -> list[dict]:
    """What the chat may name, for the agent's context: client and marketplace."""
    return [{"client": v.client, "country": v.country_code, "region": v.region}
            for v in _load_vehicles()]


def request_scope(country_hint: str | None = None) -> dict | None:
    """The `ads_scope` for one chat turn, or None when nothing is connected."""
    if not ai_config.AI_ENABLED:
        return None
    vehicle = pick_vehicle(_load_vehicles(), country_hint)
    if vehicle is None:
        return None
    username = st.session_state.get("username") or st.session_state.get("name") or ""
    return {"account_id": vehicle.account_id, "profile_id": vehicle.profile_id,
            "requested_by": str(username or ""), "dynamic": True}
