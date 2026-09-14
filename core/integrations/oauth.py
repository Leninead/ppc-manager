"""OAuth authorization-code flow with PKCE, split across the trust boundary.

The app builds the consent URL and seals the PKCE verifier; only the worker can
open that verifier and exchange the code, because only the worker can open the
client secret. That split is why the authorization code never buys anything on
its own if the app is compromised.

Whether a refresh token rotates is a per-provider fact, declared in the catalog
(`Integration.refresh_rotates`). Mercado Libre's is single-use and rotates on
every refresh, so `refresh()` returns the new one and the caller must persist it
in the same transaction that consumed the old one. Login with Amazon echoes the
same token back, and may omit it; `rotates=False` keeps the one that was sent.
"""
from __future__ import annotations

import base64
import hashlib
import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import requests

_TIMEOUT_S = 15
_VERIFIER_BYTES = 48
_STATE_BYTES = 16


class OAuthError(RuntimeError):
    """The provider rejected the exchange or the response was unusable."""


class NeedsReauth(OAuthError):
    """The refresh token is dead — only the account owner can fix this."""


@dataclass(frozen=True)
class PendingGrant:
    state: str
    verifier: str
    challenge: str


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_in: int
    scopes: tuple[str, ...]
    user_id: str


def start_grant() -> PendingGrant:
    verifier = secrets.token_urlsafe(_VERIFIER_BYTES)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return PendingGrant(state=secrets.token_urlsafe(_STATE_BYTES), verifier=verifier, challenge=challenge)


def consent_url(
    *,
    authorize_url: str,
    client_id: str,
    redirect_uri: str,
    grant: PendingGrant,
    scopes: tuple[str, ...] = (),
) -> str:
    parametros = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": grant.state,
        "code_challenge": grant.challenge,
        "code_challenge_method": "S256",
    }
    if scopes:
        parametros["scope"] = " ".join(scopes)
    return f"{authorize_url}?{urlencode(parametros)}"


def exchange_code(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    code: str,
    redirect_uri: str,
    verifier: str,
    session: requests.Session | None = None,
) -> TokenSet:
    return _post_token(
        token_url,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "client_secret": client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        session,
    )


def refresh(
    *,
    token_url: str,
    client_id: str,
    client_secret: str,
    refresh_token: str,
    session: requests.Session | None = None,
    rotates: bool = True,
) -> TokenSet:
    return _post_token(
        token_url,
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
        },
        session,
        expect_rotation=rotates,
    )


def _post_token(
    token_url: str,
    payload: dict,
    session: requests.Session | None,
    expect_rotation: bool = True,
) -> TokenSet:
    http = session or requests.Session()
    try:
        response = http.post(
            token_url,
            data=payload,
            headers={"Accept": "application/json"},
            timeout=_TIMEOUT_S,
        )
    except requests.RequestException as exc:
        raise OAuthError(f"no se pudo contactar al proveedor: {exc}") from exc

    try:
        body = response.json()
    except ValueError:
        raise OAuthError(f"respuesta ilegible del proveedor (HTTP {response.status_code})")

    if response.status_code >= 400:
        error = str(body.get("error", "")).strip()
        detail = str(body.get("message") or body.get("error_description") or "").strip()
        if error == "invalid_grant":
            raise NeedsReauth(detail or "el permiso caducó o ya fue usado")
        raise OAuthError(f"{error or response.status_code}: {detail}".strip(": "))

    new_refresh = str(body.get("refresh_token", "")).strip()
    if payload["grant_type"] == "refresh_token" and not new_refresh:
        if expect_rotation:
            # A provider that rotates must return the replacement; losing it here
            # would leave the stored token already spent and unrecoverable.
            raise OAuthError("el proveedor no devolvió un refresh token nuevo")
        new_refresh = payload["refresh_token"]

    scopes = tuple(str(body.get("scope", "")).split()) if body.get("scope") else ()
    return TokenSet(
        access_token=str(body.get("access_token", "")),
        refresh_token=new_refresh,
        expires_in=int(body.get("expires_in") or 0),
        scopes=scopes,
        user_id=str(body.get("user_id") or ""),
    )
