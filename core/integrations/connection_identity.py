"""What an identity resolver hands back to the worker after a token exchange.

Each OAuth provider answers "whose account is this token for?" in its own way
(Mercado Libre with `/users/me`, Login with Amazon with `/user/profile` plus the
Ads API profiles). The worker only ever sees this shape, so it can persist a
connection without knowing which provider it came from.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DiscoveredAccount:
    """A client account reachable through one authorization.

    `external_id` is the provider's stable id for the account (Amazon: the
    entity id, which repeats across marketplaces of the same seller) and is the
    upsert key. `region` names the API host the account lives on.
    """

    external_id: str
    name: str
    account_type: str
    region: str
    marketplaces: tuple[str, ...]
    profiles: tuple[dict, ...] = ()


@dataclass(frozen=True)
class ConnectionIdentity:
    """The identity of one authorization, plus whatever accounts it reaches.

    `external_id` must be stable across re-consents of the same account: it is
    the upsert key, so an unstable one would duplicate rows on every
    reauthorization. `collision_suffix` disambiguates `client_base` when two
    different accounts slugify to the same label.
    """

    external_id: str
    client_base: str
    external_name: str = ""
    marketplace: str = ""
    collision_suffix: str = ""
    metadata: dict = field(default_factory=dict)
    accounts: tuple[DiscoveredAccount, ...] = ()
