"""Which Amazon Ads region a turn reads live, and the account that opens it: the app's rules, minus Streamlit.

`core.chat.ads_scope.request_scope()` reads the username from `st.session_state`; the pure functions it builds on
are reused here with a cache of their own.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass

from ai import config as ai_config
from core.chat import ads_scope
from core.integrations.store import open_stores

log = logging.getLogger(__name__)

_CACHE_S = 120
REGION_COUNTRIES = {"NA": "US, CA, MX, BR", "EU": "Europa, Medio Oriente e India", "FE": "JP, AU, SG"}


@dataclass(frozen=True)
class TurnScope:
    ads_scope: dict | None
    region: str | None


class AccountScopes:
    def __init__(self, load_vehicles=None, clock=time.monotonic):
        self._load = load_vehicles or _load_vehicles
        self._clock = clock
        self._vehicles: tuple[float, list[ads_scope.AccountVehicle]] | None = None
        self._lock = threading.Lock()

    def for_country(self, country: str, requested_by: str) -> TurnScope:
        """The account that opens a live Amazon Ads session in the country's region, or the busiest region."""
        if not ai_config.AI_ENABLED:
            return TurnScope(None, None)
        vehicle = ads_scope.pick_vehicle(self._cached_vehicles(), country or None)
        if vehicle is None:
            return TurnScope(None, None)
        scope = {"account_id": vehicle.account_id, "profile_id": vehicle.profile_id,
                 "requested_by": requested_by, "dynamic": True}
        return TurnScope(scope, vehicle.region)

    def _cached_vehicles(self) -> list[ads_scope.AccountVehicle]:
        with self._lock:
            if self._vehicles and self._clock() - self._vehicles[0] < _CACHE_S:
                return self._vehicles[1]
        vehicles = self._load()
        with self._lock:
            self._vehicles = (self._clock(), vehicles)
        return vehicles


def _load_vehicles() -> list[ads_scope.AccountVehicle]:
    stores = open_stores()
    if stores is None:
        return []
    _, connections, _ = stores
    try:
        return ads_scope.build_vehicles(connections.accounts_by_integration_slug().get(ads_scope.SLUG, []),
                                        connections.by_integration_slug().get(ads_scope.SLUG, []))
    except Exception as exc:  # noqa: BLE001 — a portal hiccup costs the live Amazon Ads tools, not the turn
        log.warning("Amazon Ads accounts not read; the turn goes without live Amazon Ads: %s", exc)
        return []
