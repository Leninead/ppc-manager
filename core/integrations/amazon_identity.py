"""Who authorized, and which client accounts they can reach, on Amazon Ads.

Worker-only: it runs on the access token the exchange just minted and must
never be imported by the Streamlit app.

Login with Amazon puts no account id in its token response, so the stable
identity of an authorization is the LWA user id from `/user/profile` (scope
`profile:user_id`, nothing else about the person). The client accounts come
from the Ads API: `GET /v2/profiles` on each regional host, which lists every
advertising profile the consenting user can see there. Capybaras employees are
invited into each client's account with their own Amazon user, so one consent
by one employee reaches many clients — hence accounts are a list, not a field.

A regional host that fails is recorded, never raised: the authorization is real
and worth persisting even when Amazon Ads has nothing to say yet.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

from core.integrations.connection_identity import ConnectionIdentity, DiscoveredAccount
from core.integrations.oauth import TokenSet

log = logging.getLogger(__name__)

SLUG = "amazon_ads"
LWA_PROFILE_URL = "https://api.amazon.com/user/profile"
ADS_API_HOSTS = {
    "NA": "https://advertising-api.amazon.com",
    "EU": "https://advertising-api-eu.amazon.com",
    "FE": "https://advertising-api-fe.amazon.com",
}
PROFILES_PATH = "/v2/profiles"
ACCESS_EDIT = "edit"
ACCESS_VIEW = "view"
# Profiles with view-only permission are hidden by default; asking for the
# report program with view access is how Amazon documents surfacing them.
_VIEW_ONLY_QUERY = {"accessLevel": ACCESS_VIEW, "apiProgram": "report"}
TIMEOUT_S = 10


class DiscoveryError(RuntimeError):
    """Amazon did not say who the token belongs to, or what it can see."""


@dataclass(frozen=True)
class AdsProfile:
    profile_id: str
    region: str
    country_code: str
    marketplace_id: str
    account_type: str
    account_name: str
    entity_id: str
    access: str
    timezone: str = ""
    currency_code: str = ""

    def as_row(self) -> dict:
        return {
            "profile_id": self.profile_id,
            "country_code": self.country_code,
            "marketplace_id": self.marketplace_id,
            "access": self.access,
            "timezone": self.timezone,
            "currency_code": self.currency_code,
        }


def fetch_lwa_user_id(access_token: str, session: requests.Session | None = None) -> str:
    http = session or requests.Session()
    try:
        response = http.get(
            LWA_PROFILE_URL,
            headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise DiscoveryError(f"could not query {LWA_PROFILE_URL}: {exc}") from exc
    if response.status_code >= 400:
        raise DiscoveryError(f"Login with Amazon rejected /user/profile (HTTP {response.status_code})")
    try:
        body = response.json()
    except ValueError as exc:
        raise DiscoveryError("unreadable response from /user/profile") from exc
    user_id = str(body.get("user_id") or "").strip()
    if not user_id:
        raise DiscoveryError("Login with Amazon returned /user/profile without user_id")
    return user_id


def list_profiles(
    host: str,
    access_token: str,
    client_id: str,
    access_level: str,
    session: requests.Session | None = None,
) -> list[dict]:
    http = session or requests.Session()
    try:
        response = http.get(
            f"{host}{PROFILES_PATH}",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Amazon-Advertising-API-ClientId": client_id,
                "Accept": "application/json",
            },
            params=_VIEW_ONLY_QUERY if access_level == ACCESS_VIEW else None,
            timeout=TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise DiscoveryError(f"could not reach {host}: {exc}") from exc
    if response.status_code >= 400:
        raise DiscoveryError(f"HTTP {response.status_code} from {host}{PROFILES_PATH}")
    try:
        body = response.json()
    except ValueError as exc:
        raise DiscoveryError(f"unreadable profiles response from {host}") from exc
    return body if isinstance(body, list) else []


def discover_profiles(
    access_token: str,
    client_id: str,
    session: requests.Session | None = None,
) -> tuple[tuple[AdsProfile, ...], dict[str, str]]:
    """Every profile the user can see, across the three regions.

    Returns the profiles and, per region that could not be queried, the reason.
    A profile present in the edit listing is `edit`; one that only appears in
    the view listing is `view`.
    """
    profiles: list[AdsProfile] = []
    errors: dict[str, str] = {}
    for region, host in ADS_API_HOSTS.items():
        try:
            editable = list_profiles(host, access_token, client_id, ACCESS_EDIT, session)
            viewable = list_profiles(host, access_token, client_id, ACCESS_VIEW, session)
        except DiscoveryError as exc:
            errors[region] = str(exc)
            log.warning("amazon_ads: profiles unavailable on %s: %s", region, exc)
            continue
        by_id: dict[str, AdsProfile] = {}
        for raw in editable:
            parsed = _parse_profile(raw, region, ACCESS_EDIT)
            if parsed:
                by_id[parsed.profile_id] = parsed
        for raw in viewable:
            parsed = _parse_profile(raw, region, ACCESS_VIEW)
            if parsed and parsed.profile_id not in by_id:
                by_id[parsed.profile_id] = parsed
        profiles.extend(by_id.values())
    return tuple(profiles), errors


def _parse_profile(raw: dict, region: str, access: str) -> AdsProfile | None:
    profile_id = str(raw.get("profileId") or "").strip()
    if not profile_id:
        return None
    info = raw.get("accountInfo") or {}
    return AdsProfile(
        profile_id=profile_id,
        region=region,
        country_code=str(raw.get("countryCode") or "").strip().upper(),
        marketplace_id=str(info.get("marketplaceStringId") or "").strip(),
        account_type=str(info.get("type") or "").strip().lower(),
        account_name=str(info.get("name") or "").strip(),
        entity_id=str(info.get("id") or "").strip(),
        access=access,
        timezone=str(raw.get("timezone") or "").strip(),
        currency_code=str(raw.get("currencyCode") or "").strip().upper(),
    )


def group_accounts(profiles: tuple[AdsProfile, ...]) -> tuple[DiscoveredAccount, ...]:
    """One account per (region, entity): a seller in US, CA and MX is one client
    with three marketplaces, not three clients. The entity id repeats across
    the marketplaces of one seller and differs between regions."""
    grouped: dict[tuple[str, str], list[AdsProfile]] = {}
    for profile in profiles:
        key = (profile.region, profile.entity_id or profile.profile_id)
        grouped.setdefault(key, []).append(profile)

    accounts: list[DiscoveredAccount] = []
    for (region, entity_id), members in grouped.items():
        first = members[0]
        accounts.append(
            DiscoveredAccount(
                external_id=entity_id,
                name=first.account_name or f"{first.account_type} {entity_id}".strip(),
                account_type=first.account_type,
                region=region,
                marketplaces=tuple(sorted({m.country_code for m in members if m.country_code})),
                profiles=tuple(m.as_row() for m in members),
            )
        )
    accounts.sort(key=lambda account: (account.name.lower(), account.region))
    return tuple(accounts)


def resolve_identity(
    tokens: TokenSet,
    *,
    client_id: str,
    requested_by: str,
    session: requests.Session | None = None,
) -> ConnectionIdentity:
    """The authorization's identity: the LWA user, labelled by who requested it,
    carrying every client account the token reaches."""
    user_id = fetch_lwa_user_id(tokens.access_token, session)
    profiles, errors = discover_profiles(tokens.access_token, client_id, session)
    accounts = group_accounts(profiles)
    countries = sorted({p.country_code for p in profiles if p.country_code})
    return ConnectionIdentity(
        external_id=user_id,
        client_base=requested_by or "amazon",
        marketplace=" ".join(countries),
        collision_suffix="amazon",
        metadata={
            "discovery": {
                "profiles": len(profiles),
                "accounts": len(accounts),
                "errors": errors,
                "at": datetime.now(timezone.utc).isoformat(),
            }
        },
        accounts=accounts,
    )
