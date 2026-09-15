"""Login with Amazon access tokens for the ingestion worker, cached per connection.

Opens the sealed refresh token with the worker's private key; nothing here is
ever logged or persisted besides the needs_reauth state.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from core.integrations import catalog, crypto, oauth, worker
from core.integrations.amazon_identity import SLUG
from core.integrations.store import ACTIVE_STATUS, CONNECTIONS_TABLE, _Rest

log = logging.getLogger(__name__)

# Refresh ahead of expiry so a token never dies halfway through a report poll.
EXPIRY_MARGIN_SECONDS = 300


class ConnectionUnavailable(RuntimeError):
    """The connection is missing or not active, so no token can be minted."""


class TokenManager:
    def __init__(self, rest: _Rest, private_pem: str, *, session: requests.Session | None = None,
                 clock: Callable[[], float] = time.monotonic):
        self._rest = rest
        self._private_pem = private_pem
        self._session = session
        self._clock = clock
        self._client_id = ""
        self._cached_tokens: dict[int, tuple[str, float]] = {}

    def access_token(self, connection_id: int, force_refresh: bool = False) -> str:
        cached = self._cached_tokens.get(connection_id)
        if cached and not force_refresh and self._clock() < cached[1]:
            return cached[0]

        connection = self._load_connection(connection_id)
        client_id, client_secret = self._current_credential(connection_id)
        refresh_token = crypto.unseal(connection["refresh_token_sealed"], self._private_pem)
        try:
            tokens = oauth.refresh(
                token_url=_token_url(),
                client_id=client_id,
                client_secret=client_secret,
                refresh_token=refresh_token,
                session=self._session,
                rotates=False,
            )
        except oauth.NeedsReauth as exc:
            self._cached_tokens.pop(connection_id, None)
            log.warning("amazon_ads: connection %s needs re-authorization", connection_id)
            worker._mark_needs_reauth(self._rest, connection, exc)
            raise
        if not tokens.access_token:
            raise oauth.OAuthError("Login with Amazon returned no access token")

        valid_until = self._clock() + max(tokens.expires_in - EXPIRY_MARGIN_SECONDS, 0)
        self._cached_tokens[connection_id] = (tokens.access_token, valid_until)
        return tokens.access_token

    def client_id(self) -> str:
        """The client id of the credential behind the latest refresh, so it matches the tokens in use."""
        if not self._client_id:
            self._current_credential(None)
        return self._client_id

    def forget(self, connection_id: int) -> None:
        self._cached_tokens.pop(connection_id, None)

    def token_source(self, connection_id: int) -> Callable[[bool], str]:
        return lambda force_refresh: self.access_token(connection_id, force_refresh)

    def _current_credential(self, connection_id: int | None) -> tuple[str, str]:
        # Read on every real refresh: an admin can rotate or remove the credential while this process runs.
        try:
            client_id, client_secret = worker._active_credential(self._rest, SLUG, self._private_pem)
        except worker.WorkerError as exc:
            if connection_id is not None:
                self.forget(connection_id)
            raise ConnectionUnavailable(f"amazon_ads has no usable client credential: {exc}") from exc
        self._client_id = client_id
        return client_id, client_secret

    def _load_connection(self, connection_id: int) -> dict:
        rows = self._rest.select(
            CONNECTIONS_TABLE,
            {
                "select": "id,integration_slug,cliente,estado,refresh_token_sealed",
                "id": f"eq.{connection_id}",
                "integration_slug": f"eq.{SLUG}",
                "limit": "1",
            },
        )
        if not rows:
            raise ConnectionUnavailable(f"amazon_ads connection {connection_id} does not exist")
        connection = rows[0]
        if connection.get("estado") != ACTIVE_STATUS:
            self._cached_tokens.pop(connection_id, None)
            raise ConnectionUnavailable(
                f"amazon_ads connection {connection_id} is {connection.get('estado') or 'unknown'}"
            )
        if not connection.get("refresh_token_sealed"):
            raise ConnectionUnavailable(f"amazon_ads connection {connection_id} has no refresh token")
        return connection


def _token_url() -> str:
    integration = catalog.by_slug(SLUG)
    if integration is None or not integration.token_url:
        raise ConnectionUnavailable("amazon_ads is missing from the integrations catalog")
    return integration.token_url
