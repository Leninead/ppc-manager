"""DataDive REST client and normalizers onto the canonical MKL shape.

Read-only integration (GET /v1/niches, /v1/niches/{id}/keywords, /v1/quota):
per the spec these GETs consume no billable DataDive tokens — only rate limit
(dual, per IP and per API key, with no published numbers). The retry mirrors
core/ads_api (exponential backoff honouring Retry-After as seconds or as an
HTTP-date) so both external integrations behave the same way.

No Streamlit at module level: the UI and the caching live in the page (M21).
The key comes from DATADIVE_API_KEY, falling back to st.secrets["datadive"].
"""
from __future__ import annotations

import email.utils
import logging
import math
import os
import time

import pandas as pd

from modules.parsers.datadive import (
    COL_LAUNCH_SCORE,
    COL_RELEVANCE,
    COL_SEARCH_TERM,
    COL_SUGG_BID,
    COL_SV,
)

log = logging.getLogger("datadive")

DEFAULT_BASE_URL = "https://api.datadive.tools"
NICHES_PAGE_SIZE = 50
_MAX_NICHE_PAGES = 200  # safety cap; the real org has 287 niches (2026-09)
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_MAX_RETRIES = 5
_RETRY_AFTER_CAP_S = 300.0

_STATUS_MESSAGES = {
    401: "API key de DataDive inválida o vencida.",
    403: "La key no tiene acceso a este recurso (¿suscripción pausada o plan sin API?).",
    429: "Rate limit de DataDive excedido — esperá un minuto y reintentá.",
}


class DataDiveError(Exception):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def parse_retry_after(value: str | None, default_s: float) -> float:
    """Retry-After as seconds or an HTTP-date (RFC 7231), clamped to [0, 300s]."""
    if not value:
        return min(max(default_s, 0.0), _RETRY_AFTER_CAP_S)
    try:
        seconds = float(value)
    except ValueError:
        try:
            parsed = email.utils.parsedate_to_datetime(value)
        except (TypeError, ValueError):
            parsed = None
        if parsed is None:
            return min(max(default_s, 0.0), _RETRY_AFTER_CAP_S)
        seconds = parsed.timestamp() - time.time()
    if seconds != seconds:  # NaN slips past min/max and would break time.sleep
        seconds = default_s
    return min(max(seconds, 0.0), _RETRY_AFTER_CAP_S)


class DataDiveClient:
    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL,
                 timeout: int = 30, sleep=time.sleep, session=None,
                 max_retries: int = _MAX_RETRIES,
                 retry_after_cap_s: float = _RETRY_AFTER_CAP_S):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._sleep = sleep
        self._session = session
        self._max_retries = max(1, max_retries)
        self._retry_after_cap_s = retry_after_cap_s

    def request(self, path: str, params: dict | None = None) -> dict:
        if self._session is None:
            import requests  # deferred: importing this module must not need the network
            self._session = requests.Session()
        url = self.base_url + path
        response = None
        for attempt in range(self._max_retries):
            try:
                response = self._session.get(
                    url, params=params, headers={"x-api-key": self.api_key},
                    timeout=self.timeout)
            except Exception as e:
                raise DataDiveError(
                    f"No se pudo contactar a DataDive ({url}): {e}") from e
            if response.status_code == 200:
                try:
                    return response.json()
                except ValueError as e:
                    raise DataDiveError(
                        f"DataDive devolvió una respuesta no-JSON en {path}.") from e
            if response.status_code in _RETRY_STATUSES and attempt < self._max_retries - 1:
                wait = min(parse_retry_after(response.headers.get("Retry-After"),
                                             default_s=2.0 * (2 ** attempt)),
                           self._retry_after_cap_s)
                log.warning("DataDive %s en %s — retry en %.1fs (intento %d)",
                            response.status_code, path, wait, attempt + 1)
                self._sleep(wait)
                continue
            break
        status = response.status_code
        detail = (response.text or "")[:300]
        message = _STATUS_MESSAGES.get(
            status, f"DataDive respondió {status} en {path}.")
        raise DataDiveError(f"{message} ({status}: {detail})", status=status)

    def list_niches(self) -> list[dict]:
        """Every niche of the organization, deduped by nicheId.

        The endpoint advertises pagination but returns the full set on every
        page (measured: 6 identical pages of 287 niches), so results are
        deduped and the loop stops as soon as a page adds no new ids.
        """
        seen: dict[str, dict] = {}
        page = 1
        while page <= _MAX_NICHE_PAGES:
            body = self.request("/v1/niches", params={
                "pageSize": NICHES_PAGE_SIZE, "currentPage": page})
            data = body.get("data") or []
            new = 0
            for niche in data:
                if not isinstance(niche, dict):
                    continue
                niche_id = str(niche.get("nicheId") or "")
                if niche_id and niche_id not in seen:
                    seen[niche_id] = niche
                    new += 1
            last_page = body.get("lastPage")
            if (not data or new == 0 or not body.get("hasNext")
                    or (last_page and page >= last_page)):
                break
            page += 1
        return list(seen.values())

    def niche_keywords(self, niche_id: str) -> dict:
        """Raw GET /v1/niches/{id}/keywords — the whole MKL, unpaginated."""
        return self.request(f"/v1/niches/{niche_id}/keywords")

    def niche_competitors(self, niche_id: str) -> dict:
        """Raw GET /v1/niches/{id}/competitors — competitors plus the benchmark."""
        return self.request(f"/v1/niches/{niche_id}/competitors")

    def list_rank_radars(self) -> list[dict]:
        """Every rank radar of the organization (paginated server-side)."""
        radars: list[dict] = []
        page = 1
        while page <= _MAX_NICHE_PAGES:
            body = self.request("/v1/niches/rank-radars", params={
                "pageSize": NICHES_PAGE_SIZE, "currentPage": page})
            data = body.get("data")
            meta = data if isinstance(data, dict) else {}
            batch = meta.get("data") if isinstance(data, dict) else data
            batch = batch or []
            radars.extend(b for b in batch if isinstance(b, dict))
            last_page = meta.get("lastPage")
            if not batch or not meta.get("hasNext") or (last_page and page >= last_page):
                break
            page += 1
        return radars

    def rank_radar_keywords(self, radar_id: str, start_date: str,
                            end_date: str) -> list[dict]:
        """One rank radar in detail: an entry per tracked keyword carrying the
        daily rank series for the requested range (YYYY-MM-DD)."""
        body = self.request(f"/v1/niches/rank-radars/{radar_id}", params={
            "startDate": start_date, "endDate": end_date})
        data = body.get("data")
        return data if isinstance(data, list) else []

    def quota(self) -> dict:
        """Usage and capacity of the billable features; doubles as a key healthcheck."""
        return self.request("/v1/quota")


def _to_int(raw, default: int = 0) -> int:
    if isinstance(raw, dict):  # the benchmark nests some values as {median, ...}
        raw = raw.get("median")
    try:
        v = pd.to_numeric(raw, errors="coerce")
    except (TypeError, ValueError):
        return default
    return default if pd.isna(v) else int(v)


def _to_float(raw, default: float = 0.0) -> float:
    if isinstance(raw, dict):
        raw = raw.get("median")
    try:
        v = pd.to_numeric(raw, errors="coerce")
    except (TypeError, ValueError):
        return default
    return default if pd.isna(v) else float(v)


# The day DataDive exposes the score in /keywords the official value wins and
# the replica below dies on its own, with nothing to migrate.
_OFFICIAL_LAUNCH_KEYS = ("launchScore", "launch_score")


def _launch_score_of(kw: dict, sv: int, relevancy: float) -> float:
    """The official Launch Score when the API carries it, else the replica."""
    for key in _OFFICIAL_LAUNCH_KEYS:
        if kw.get(key) is not None:
            return _to_float(kw[key])
    return _launch_score(sv, relevancy)


def _launch_score(sv: int, relevancy: float) -> float:
    """Exact replica of the formula in DataDive's public frontend bundle:
    round(SV * 0.003 / relevancy) when relevancy >= 0.4, else empty — the
    "estimated weekly sales needed to reach page one". Validated 419/419
    against a real export (SEVEN_SERUM, 2026-09-01); floor(x+0.5) reproduces
    JS Math.round.

    Their KB corroborates the semantics (weekly window, 40% threshold):
    support.datadive.tools/hc/en-us/articles/59878334218649-What-is-Launch-Score
    On suspected drift run scripts/check_launch_score_drift.py, which CI also
    runs weekly.

    Below the gate the bundle's arrow function falls off its `if` and returns
    undefined, which DataDive renders as an empty cell. NaN is that empty cell:
    the score is a COST to rank, so a 0 would read as "cheapest keyword here" —
    the opposite of "not computable".
    """
    if relevancy < 0.4 or not sv:
        return math.nan
    return float(math.floor(sv * (1 / relevancy) * 0.003 + 0.5))


def launch_score_drifted(df: pd.DataFrame, min_rows: int = 20,
                         tolerance: float = 0.2) -> bool:
    """Has the Launch Score replica stopped matching a real export?

    An .xlsx export carries the TRUE Launch Score, so every file the AM uploads
    audits the formula for free — no cron, no credentials, nobody having to
    remember. Only rows where the formula applies are compared (relevance >= 4.0
    on the 0-10 scale) and rounding is tolerated.
    """
    needed = {COL_SV, COL_RELEVANCE, COL_LAUNCH_SCORE}
    if df is None or df.empty or not needed <= set(df.columns):
        return False
    sv = pd.to_numeric(df[COL_SV], errors="coerce")
    rel = pd.to_numeric(df[COL_RELEVANCE], errors="coerce")
    real = pd.to_numeric(df[COL_LAUNCH_SCORE], errors="coerce")
    comparable = (rel >= 4.0) & (sv > 0) & real.notna() & (real > 0)
    if int(comparable.sum()) < min_rows:
        return False  # too few rows to accuse anyone of drifting
    expected = (sv[comparable] * 0.003 / (rel[comparable] / 10)).round()
    off = (expected - real[comparable]).abs() > 1
    return bool(off.mean() > tolerance)


def keywords_to_mkl_df(payload: dict) -> tuple[pd.DataFrame, list[str]]:
    """/keywords JSON -> parse_mkl's canonical DataFrame plus the ASIN list.

    Contract validated against a real payload (spike 2026-09): relevancy 0-1 (or
    the string "Outlier"), suggestedBid in cents and sometimes null as a whole,
    asinRanks where null means "does not rank". The endpoint carries no Launch
    Score, so it is derived (see _launch_score_of).
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        # The spec declares an array; the live API returns an object. Accept both.
        data = data[0] if data else {}
    if not isinstance(data, dict):
        data = {}

    asin_order: list[str] = []
    rows = []
    for kw in data.get("keywords") or []:
        term = str(kw.get("keyword") or "").strip()
        if not term:
            continue
        sv = _to_int(kw.get("searchVolume"))
        relevancy = _to_float(kw.get("relevancy"))
        bid = kw.get("suggestedBid")
        median_cents = _to_float(bid.get("median")) if isinstance(bid, dict) else 0.0
        row = {
            COL_SEARCH_TERM: term,
            COL_SV: sv,
            COL_RELEVANCE: round(relevancy * 10, 2),
            COL_SUGG_BID: round(median_cents / 100, 2),
            COL_LAUNCH_SCORE: _launch_score_of(kw, sv, relevancy),
        }
        ranks = kw.get("asinRanks")
        if not isinstance(ranks, dict):  # tolerate spec-vs-payload drift, same as the envelope
            ranks = {}
        for asin_raw, rank in ranks.items():
            asin = str(asin_raw).strip().upper()
            if asin not in asin_order:
                asin_order.append(asin)
            rank_val = pd.to_numeric(rank, errors="coerce")
            row[asin] = int(rank_val) if pd.notna(rank_val) and rank_val > 0 else None
        rows.append(row)

    if not rows:
        return pd.DataFrame(), []
    canonical = [COL_SEARCH_TERM, COL_SV, COL_RELEVANCE, COL_SUGG_BID, COL_LAUNCH_SCORE]
    df = pd.DataFrame(rows).reindex(columns=canonical + asin_order)
    return df, asin_order


def _unwrap_data(payload: dict) -> dict:
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        # The spec declares an array; the live API returns an object. Accept both.
        data = data[0] if data else {}
    return data if isinstance(data, dict) else {}


def _age_text(epoch_ms) -> str:
    """listingCreationDate (epoch ms) -> "8 yrs, 2 mos", the export's own format."""
    ts = _to_float(epoch_ms, default=0.0)
    if ts <= 0:
        return ""
    months = max(0, int((time.time() - ts / 1000) / (365.25 * 86400 / 12)))
    return f"{months // 12} yrs, {months % 12} mos"


# Export label -> (API field, transform). The tab finds columns by substring
# over these labels, so they are the contract with the UI.
_COMP_FIELDS = [
    ("Brand", "brand", lambda v: str(v or "")),
    ("Rating", "rating", _to_float),
    ("Price", "price", _to_float),
    ("SV on P1 (Share of Voice)", "svRankedOnP1", _to_int),
    ("Seller's Country", "sellerCountry", lambda v: str(v or "")),
    ("Variations", "numberOfVariations", _to_int),
    ("Outlier Search Volume", "outlierSV", _to_int),
    ("30d Outlier Keywords", "outlierKws", _to_int),
    ("Review Count", "reviewCount", _to_int),
    ("Listing Age", "listingCreationDate", _age_text),
    ("30d Sales", "sales", _to_int),
    ("30d Revenue", "revenue", _to_int),
    ("Fulfillment", "fulfillment", lambda v: str(v or "")),
    ("KWs on P1", "kwRankedOnP1", _to_int),
    ("KWs on P1 Percentage", "kwRankedOnP1Percent", lambda v: round(_to_float(v) * 100, 1)),
    ("SV on P1 Percentage", "svRankedOnP1Percent", lambda v: round(_to_float(v) * 100, 1)),
    ("Advertised KWs", "advertisedKws", _to_int),
    ("Advertised KWs Percentage", "advertisedKwsPercent", lambda v: round(_to_float(v) * 100, 1)),
    ("KWs with TOS Ads", "tosKwsAds", _to_int),
    ("KWs with TOS Ads Percentage", "tosKwsAdsPercent", lambda v: round(_to_float(v) * 100, 1)),
    ("SV with TOS Ads", "tosSvAds", _to_int),
    ("SV with TOS Ads Percentage", "tosSvAdsPercent", lambda v: round(_to_float(v) * 100, 1)),
    ("Category", "category", lambda v: str(v or "")),
]


def competitors_to_df(payload: dict) -> tuple[pd.DataFrame, dict]:
    """/competitors JSON -> (df using the export labels, niche medians).

    Same contract parse_competitors builds from the xlsx: one row per ASIN with
    the export's textual labels, plus a {label: median} dict from the benchmark.
    Percentages come out numeric (0-100); the API sends them as 0-1 fractions.
    """
    data = _unwrap_data(payload)
    rows = []
    for comp in data.get("competitors") or []:
        if not isinstance(comp, dict):
            continue
        asin = str(comp.get("asin") or "").strip().upper()
        if not asin:
            continue
        row = {"ASIN": asin}
        for label, field, transform in _COMP_FIELDS:
            row[label] = transform(comp.get(field))
        rows.append(row)

    benchmark = data.get("benchmark")
    median_data: dict = {}
    if isinstance(benchmark, dict):
        for label, field, transform in _COMP_FIELDS:
            if field in benchmark:
                median_data[label] = transform(benchmark.get(field))

    return (pd.DataFrame(rows) if rows else pd.DataFrame()), median_data


def rank_radar_to_df(keywords: list[dict]) -> tuple[pd.DataFrame, list[str], dict]:
    """Rank radar detail -> parse_rank_radar's shape: (df, date_cols, agg).

    df: Search Term / SV / Relevance (0-10) / Median Rank plus one column per
    date (YYYY-MM-DD) holding that day's organic rank. The API carries neither
    the PPC nor the SQ Score columns of the export; the tab guards for those.
    """
    rows = []
    all_dates: set[str] = set()
    for kw in keywords or []:
        if not isinstance(kw, dict):
            continue
        term = str(kw.get("keyword") or "").strip()
        if not term:
            continue
        row = {
            COL_SEARCH_TERM: term,
            COL_SV: _to_int(kw.get("searchVolume")),
            COL_RELEVANCE: round(_to_float(kw.get("relevancy")) * 10, 2),
        }
        organic = []
        for r in kw.get("ranks") or []:
            if not isinstance(r, dict):
                continue
            date = str(r.get("date") or "")[:10]
            rank = pd.to_numeric(r.get("organicRank"), errors="coerce")
            if date and pd.notna(rank):
                row[date] = float(rank)
                organic.append(float(rank))
                all_dates.add(date)
        row["Median Rank"] = float(pd.Series(organic).median()) if organic else None
        rows.append(row)
    if not rows:
        return pd.DataFrame(), [], {}
    date_cols = sorted(all_dates)
    ordered = [COL_SEARCH_TERM, COL_SV, COL_RELEVANCE, "Median Rank"] + date_cols
    return pd.DataFrame(rows).reindex(columns=ordered), date_cols, {}


def latest_research_date(payload: dict) -> str:
    """latestResearchDate from a /keywords payload, or "" when absent."""
    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        data = data[0] if data else {}
    if not isinstance(data, dict):
        return ""
    return str(data.get("latestResearchDate") or "")


def client_from_env(*, max_retries: int = _MAX_RETRIES,
                    retry_after_cap_s: float = _RETRY_AFTER_CAP_S) -> DataDiveClient | None:
    """A client when a key is configured, else None.

    One resolver decides where the key comes from (portal, env, secrets) so the
    Integraciones page can never claim a different source than the one in use.
    """
    try:
        from core.integrations.lookup import system_secret  # deferred: needs Streamlit
        key = (system_secret("datadive") or "").strip()
    except Exception:
        key = os.environ.get("DATADIVE_API_KEY", "").strip()
    if not key:
        return None
    return DataDiveClient(key, max_retries=max_retries,
                          retry_after_cap_s=retry_after_cap_s)
