"""HTTP transport for the Mercado Libre REST API.

Design goals
------------
* Single-responsibility. This layer speaks HTTP; business logic lives in
  ``ingest``/``worker``. No parsing of Meli-specific payloads happens here.
* Deterministic error surface. Every non-2xx response — after retry/refresh —
  becomes a typed exception the caller can pattern-match on.
* Injectable session. Tests wire a fake session; production uses ``requests``.

Retry policy (in order)
-----------------------
1. 5xx  → up to 3 total attempts with exponential backoff (0.5, 1.0, 2.0 s).
2. 429  → sleep for ``Retry-After`` seconds (fallback 60), single retry.
3. 401  → call ``refresh_callback`` once, replace the access token, retry once.
         If still 401 or no callback is wired, raise ``AuthExpired``.
4. 404  → immediate ``NotFound``.

Concurrency
-----------
A class-level ``Semaphore`` caps concurrent in-flight requests per access token
to 8. That is a soft floor to keep us politely under Meli's per-app rate cap;
the caller is still responsible for backing off across identities.
"""
from __future__ import annotations

import threading
import time
from collections.abc import Callable, Iterator
from typing import Any

import requests

from core.integrations.oauth import TokenSet

_TIMEOUT_S = 20
_MAX_ATTEMPTS_5XX = 3
_BACKOFF_BASE_S = 0.5
_RETRY_AFTER_FALLBACK_S = 60
_MAX_CONCURRENT_PER_TOKEN = 8
_DEFAULT_PAGE_SIZE = 50


class MeliClientError(RuntimeError):
    """Base class for every transport-level error."""


class AuthExpired(MeliClientError):
    """The access token is dead and no refresh path recovered it."""


class RateLimited(MeliClientError):
    """Meli returned 429 and the retry did not clear the throttle."""


class NotFound(MeliClientError):
    """Meli returned 404 for the given resource."""


class ServerError(MeliClientError):
    """Meli returned 5xx after exhausting retries."""


# Shared registry of per-token semaphores so a caller building many
# ``MeliClient`` instances against the same identity does not multiply the
# concurrency budget. Keyed by the first 12 chars of the token — enough to
# distinguish identities without keeping the full secret in memory.
_SEMAPHORE_LOCK = threading.Lock()
_SEMAPHORES: dict[str, threading.Semaphore] = {}


def _semaphore_for(token: str) -> threading.Semaphore:
    key = (token or "")[:12]
    with _SEMAPHORE_LOCK:
        sem = _SEMAPHORES.get(key)
        if sem is None:
            sem = threading.Semaphore(_MAX_CONCURRENT_PER_TOKEN)
            _SEMAPHORES[key] = sem
        return sem


class MeliClient:
    """Thin, resilient HTTP client for the Meli REST API.

    Parameters
    ----------
    access_token:
        Bearer token used to authenticate every request. Rotated in place when
        ``refresh_callback`` fires on a 401.
    refresh_callback:
        Optional zero-arg callable that returns a fresh ``TokenSet``. Called
        at most once per HTTP call, when Meli replies 401. The caller is
        responsible for persisting the rotated refresh token — this class only
        swaps in the new access token for the current process.
    session:
        Optional ``requests.Session`` (or duck-typed fake for tests). Defaults
        to a new ``requests.Session``.
    base_url:
        Base URL for every request. Defaults to the public Meli API.
    """

    def __init__(
        self,
        access_token: str,
        refresh_callback: Callable[[], TokenSet] | None = None,
        session: requests.Session | None = None,
        base_url: str = "https://api.mercadolibre.com",
    ):
        if not access_token:
            raise ValueError("access_token cannot be empty")
        self._access_token = access_token
        self._refresh_callback = refresh_callback
        self._session = session if session is not None else requests.Session()
        self._base_url = base_url.rstrip("/")
        self._sem = _semaphore_for(access_token)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def get(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """Issue a GET and return the JSON body as a dict.

        extra_headers are merged into the base auth/accept pair used by every
        request. Meli's Product Ads endpoints demand Api-Version and
        X-Product-Id on top of the bearer token, so callers need a way to
        tack them on without touching the base transport contract.
        """
        return self._request("GET", path, params=params, extra_headers=extra_headers)

    def post(
        self,
        path: str,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict:
        """Issue a POST with a JSON body and return the JSON response."""
        return self._request("POST", path, json=json, extra_headers=extra_headers)

    def paginate(
        self,
        path: str,
        params: dict[str, Any] | None = None,
        page_size: int = _DEFAULT_PAGE_SIZE,
        extra_headers: dict[str, str] | None = None,
    ) -> Iterator[Any]:
        """Yield every element from ``results`` across offset/limit pages.

        Follows Meli's ``paging.total`` cursor: keeps issuing GETs with the
        next ``offset`` until every advertised row has been yielded (or a page
        comes back empty, whichever happens first — Meli occasionally reports
        totals that overshoot the real dataset).
        """
        base_params: dict[str, Any] = dict(params or {})
        base_params.setdefault("limit", page_size)
        offset = int(base_params.get("offset", 0) or 0)

        while True:
            page_params = dict(base_params)
            page_params["offset"] = offset
            body = self.get(path, params=page_params, extra_headers=extra_headers)

            results = body.get("results") or []
            if not results:
                return
            for item in results:
                yield item

            paging = body.get("paging") or {}
            total = int(paging.get("total") or 0)
            offset += len(results)
            if total and offset >= total:
                return
            # Stop if the server returned fewer rows than the requested limit
            # (last page even when paging.total is missing or lies).
            if len(results) < int(page_params["limit"]):
                return

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
        _refreshed: bool = False,
    ) -> dict:
        """Perform one logical HTTP call with retry, refresh, and rate-limit handling."""
        url = self._build_url(path)

        with self._sem:
            response = self._send_with_5xx_retry(
                method, url, params=params, json=json, extra_headers=extra_headers
            )

        status = response.status_code

        if 200 <= status < 300:
            return _parse_json(response)

        if status == 404:
            raise NotFound(f"{method} {path} -> 404")

        if status == 429:
            retry_after = _parse_retry_after(response.headers)
            time.sleep(retry_after)
            with self._sem:
                response = self._send_with_5xx_retry(
                    method, url, params=params, json=json, extra_headers=extra_headers
                )
            if response.status_code == 429:
                raise RateLimited(f"{method} {path} -> 429 after Retry-After sleep")
            if 200 <= response.status_code < 300:
                return _parse_json(response)
            return self._raise_from(response, method, path)

        if status == 401:
            if _refreshed or self._refresh_callback is None:
                raise AuthExpired(f"{method} {path} -> 401 (no refresh path)")
            tokens = self._refresh_callback()
            if not tokens or not getattr(tokens, "access_token", ""):
                raise AuthExpired("refresh_callback returned no access token")
            self._access_token = tokens.access_token
            self._sem = _semaphore_for(self._access_token)
            return self._request(
                method,
                path,
                params=params,
                json=json,
                extra_headers=extra_headers,
                _refreshed=True,
            )

        return self._raise_from(response, method, path)

    def _send_with_5xx_retry(
        self,
        method: str,
        url: str,
        *,
        params: dict[str, Any] | None,
        json: dict[str, Any] | None,
        extra_headers: dict[str, str] | None = None,
    ) -> requests.Response:
        """Send one request, retrying up to 3 times on 5xx with exp backoff."""
        last: requests.Response | None = None
        for attempt in range(_MAX_ATTEMPTS_5XX):
            last = self._session.request(
                method,
                url,
                params=params,
                json=json,
                headers=self._headers(extra_headers),
                timeout=_TIMEOUT_S,
            )
            if last.status_code < 500:
                return last
            # 5xx: back off, then retry. No sleep after the final attempt.
            if attempt < _MAX_ATTEMPTS_5XX - 1:
                time.sleep(_BACKOFF_BASE_S * (2 ** attempt))
        assert last is not None  # loop always runs at least once
        return last

    def _raise_from(self, response: requests.Response, method: str, path: str) -> dict:
        status = response.status_code
        if status >= 500:
            raise ServerError(f"{method} {path} -> {status} after retries")
        # 4xx that is not 401/404/429 lands here.
        body = _safe_text(response)
        raise MeliClientError(f"{method} {path} -> {status}: {body[:200]}")

    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Accept": "application/json",
        }
        if extra:
            # Caller-supplied headers win over defaults so, e.g., a call can
            # override Accept when Meli requires a different content-type.
            for name, value in extra.items():
                if name and value is not None:
                    headers[str(name)] = str(value)
        return headers

    def _build_url(self, path: str) -> str:
        if path.startswith("http://") or path.startswith("https://"):
            return path
        if not path.startswith("/"):
            path = "/" + path
        return f"{self._base_url}{path}"


# ---------------------------------------------------------------------------
# Small helpers, module-scoped so tests can hit them if needed.
# ---------------------------------------------------------------------------
def _parse_json(response: requests.Response) -> dict:
    try:
        data = response.json()
    except ValueError as exc:
        raise MeliClientError(f"non-JSON response body: {exc}") from exc
    if isinstance(data, dict):
        return data
    # Some Meli endpoints return top-level lists; wrap them so the caller
    # always gets a dict shape and can decide how to unwrap.
    return {"results": data}


def _parse_retry_after(headers) -> float:
    raw = None
    try:
        raw = headers.get("Retry-After")
    except AttributeError:
        raw = None
    if not raw:
        return float(_RETRY_AFTER_FALLBACK_S)
    try:
        return max(0.0, float(raw))
    except (TypeError, ValueError):
        return float(_RETRY_AFTER_FALLBACK_S)


def _safe_text(response: requests.Response) -> str:
    try:
        return response.text or ""
    except Exception:
        return ""
