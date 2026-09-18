"""HTTP client for the Amazon Ads API: auth headers, retries, throttling, typed errors.

Speaks HTTP only; report and portfolio semantics live in their own modules.
"""
from __future__ import annotations

import logging
import time
from collections.abc import Callable

import requests

from core.integrations.amazon_identity import ADS_API_HOSTS

log = logging.getLogger(__name__)

CLIENT_ID_HEADER = "Amazon-Advertising-API-ClientId"
SCOPE_HEADER = "Amazon-Advertising-API-Scope"
MAX_RETRY_AFTER_SECONDS = 30.0
_ERROR_BODY_CHARS = 2000


class AdsApiError(RuntimeError):
    """Amazon answered with a status the caller did not expect, or never answered."""

    def __init__(self, message: str, *, status: int | None = None, body: str = ""):
        super().__init__(message)
        self.status = status
        self.body = body


class AdsThrottled(AdsApiError):
    """Still throttled (HTTP 429) after every retry."""

    def __init__(self, message: str, *, status: int | None = 429, body: str = "",
                 retry_after_s: float | None = None):
        super().__init__(message, status=status, body=body)
        self.retry_after_s = retry_after_s


class AdsAccessDenied(AdsApiError):
    """401/403 that a fresh token did not fix: the user cannot reach this profile."""


class AdsApiClient:
    def __init__(
        self,
        *,
        region: str,
        token_source: Callable[[bool], str],
        client_id: str = "",
        client_id_source: Callable[[], str] | None = None,
        session: requests.Session | None = None,
        sleep: Callable[[float], None] = time.sleep,
        max_retries: int = 3,
        timeout_s: int = 60,
    ):
        """Pass `client_id_source` when the client id can change while the client lives: it is read on every request."""
        host = ADS_API_HOSTS.get(region)
        if host is None:
            raise ValueError(f"unknown Amazon Ads region: {region!r}")
        if client_id_source is None and not client_id:
            raise ValueError("client_id cannot be empty")

        def fixed_client_id() -> str:
            return client_id

        self.region = region
        self._host = host
        self._client_id_source = client_id_source or fixed_client_id
        self._token_source = token_source
        self._session = session or requests.Session()
        self._sleep = sleep
        self._max_retries = max_retries
        self._timeout_s = timeout_s

    def request(
        self,
        method: str,
        path: str,
        *,
        profile_id: str | None = None,
        json_body: dict | None = None,
        content_type: str | None = None,
        accept: str | None = None,
        expected: tuple[int, ...] = (200,),
    ) -> requests.Response:
        retries_used = 0
        token_refreshed = False
        force_refresh = False
        while True:
            access_token = self._token_source(force_refresh)
            force_refresh = False
            retry_after = None
            network_error = None
            try:
                response = self._send(method, path, profile_id, json_body, content_type, accept,
                                      access_token)
            except requests.RequestException as exc:
                network_error = exc
                reason = f"no response ({type(exc).__name__})"
                failure = AdsApiError(f"{method} {path}: {reason}")
            else:
                status = response.status_code
                if status in expected:
                    return response
                if status == 401 and not token_refreshed:
                    log.info("amazon_ads: %s %s -> 401, refreshing the access token once", method, path)
                    token_refreshed = force_refresh = True
                    continue
                body = _body_text(response)
                if status in (401, 403):
                    raise AdsAccessDenied(f"{method} {path} -> HTTP {status}", status=status, body=body)
                if status != 429 and status < 500:
                    raise AdsApiError(f"{method} {path} -> HTTP {status}: {body[:300]}", status=status, body=body)
                reason = f"HTTP {status}"
                if status == 429:
                    retry_after = _retry_after_seconds(response)
                    failure = AdsThrottled(f"{method} {path}: throttled after {retries_used} retries",
                                           body=body, retry_after_s=retry_after)
                else:
                    failure = AdsApiError(f"{method} {path} -> HTTP {status} after {retries_used} retries",
                                          status=status, body=body)

            if retries_used >= self._max_retries:
                raise failure from network_error
            retries_used += 1
            self._back_off(method, path, reason, retries_used, retry_after)

    def _send(self, method: str, path: str, profile_id: str | None, json_body: dict | None,
              content_type: str | None, accept: str | None, access_token: str) -> requests.Response:
        headers = {
            CLIENT_ID_HEADER: self._client_id_source(),
            "Authorization": f"Bearer {access_token}",
        }
        if profile_id:
            headers[SCOPE_HEADER] = str(profile_id)
        if content_type:
            headers["Content-Type"] = content_type
        # The v3 entity endpoints answer 415 to the default `*/*`; reporting and portfolios do not.
        if accept:
            headers["Accept"] = accept
        return self._session.request(
            method,
            f"{self._host}{path}",
            headers=headers,
            json=json_body,
            timeout=self._timeout_s,
        )

    def _back_off(self, method: str, path: str, reason: str, attempt: int,
                  retry_after: float | None) -> None:
        delay = min(retry_after, MAX_RETRY_AFTER_SECONDS) if retry_after is not None else 2.0 ** (attempt - 1)
        log.warning("amazon_ads: %s %s -> %s, retry %d/%d in %.1f s",
                    method, path, reason, attempt, self._max_retries, delay)
        self._sleep(delay)


def _retry_after_seconds(response: requests.Response) -> float | None:
    raw = (response.headers or {}).get("Retry-After")
    if raw is None:
        return None
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return None


def _body_text(response: requests.Response) -> str:
    try:
        return (response.text or "")[:_ERROR_BODY_CHARS]
    except (UnicodeDecodeError, AttributeError):
        return ""
