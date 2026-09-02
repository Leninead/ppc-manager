"""Tests for the DataDive API client and the JSON -> canonical MKL normalizer.

The client is tested against a scripted HTTP session (no network) with sleep
injected; the normalizer payloads reproduce the edge cases measured in the real
spike payload (relevancy 0-1, "Outlier", null suggestedBid, null asinRanks).
"""
from __future__ import annotations

import pandas as pd
import pytest

from core.datadive import (
    DataDiveClient,
    DataDiveError,
    client_from_env,
    competitors_to_df,
    keywords_to_mkl_df,
    latest_research_date,
    parse_retry_after,
    rank_radar_to_df,
)


class FakeResponse:
    def __init__(self, status_code: int, body=None, headers=None, text=""):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}
        self.text = text

    def json(self):
        if self._body is None:
            raise ValueError("no body")
        return self._body


class FakeSession:
    """Return the scripted responses in order and record every request."""

    def __init__(self, responses: list):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        return self.responses.pop(0)


def _client(responses):
    sleeps: list[float] = []
    session = FakeSession(responses)
    client = DataDiveClient("test-key", sleep=sleeps.append, session=session)
    return client, session, sleeps


# ── request: auth header, retries, errors ────────────────────────────────────

def test_request_sends_api_key_header():
    client, session, _ = _client([FakeResponse(200, {"ok": True})])
    assert client.request("/v1/quota") == {"ok": True}
    assert session.calls[0]["headers"] == {"x-api-key": "test-key"}
    assert session.calls[0]["url"].endswith("/v1/quota")


def test_request_retries_on_429_honoring_retry_after_seconds():
    client, session, sleeps = _client([
        FakeResponse(429, headers={"Retry-After": "7"}),
        FakeResponse(200, {"ok": True}),
    ])
    assert client.request("/v1/niches") == {"ok": True}
    assert len(session.calls) == 2
    assert sleeps == [7.0]


def test_request_retries_on_500_with_exponential_backoff():
    client, _, sleeps = _client([
        FakeResponse(500), FakeResponse(502), FakeResponse(200, {"ok": True}),
    ])
    assert client.request("/v1/niches") == {"ok": True}
    assert sleeps == [2.0, 4.0]


def test_request_exhausted_retries_raise_with_status():
    client, session, _ = _client([FakeResponse(429)] * 5)
    with pytest.raises(DataDiveError) as e:
        client.request("/v1/niches")
    assert e.value.status == 429
    assert len(session.calls) == 5


def test_request_401_raises_without_retry():
    client, session, sleeps = _client([FakeResponse(401, text="bad key")])
    with pytest.raises(DataDiveError) as e:
        client.request("/v1/quota")
    assert e.value.status == 401
    assert "inválida" in str(e.value)
    assert len(session.calls) == 1 and sleeps == []


def test_parse_retry_after_clamps_and_parses_http_date():
    assert parse_retry_after("42", default_s=1) == 42.0
    assert parse_retry_after("9999", default_s=1) == 300.0
    assert parse_retry_after(None, default_s=8) == 8.0
    assert parse_retry_after("garbage", default_s=3) == 3.0
    # An HTTP-date in the past clamps to 0
    assert parse_retry_after("Wed, 21 Oct 2015 07:28:00 GMT", default_s=5) == 0.0
    # NaN parses as a float but slips past min/max, so it must fall to the default
    assert parse_retry_after("nan", default_s=2) == 2.0


# ── list_niches: pagination ──────────────────────────────────────────────────

def test_list_niches_paginates_until_last_page():
    page1 = {"data": [{"nicheId": "a" * 10}], "hasNext": True, "lastPage": 2}
    page2 = {"data": [{"nicheId": "b" * 10}], "hasNext": False, "lastPage": 2}
    client, session, _ = _client([FakeResponse(200, page1), FakeResponse(200, page2)])
    niches = client.list_niches()
    assert [n["nicheId"] for n in niches] == ["a" * 10, "b" * 10]
    assert session.calls[0]["params"] == {"pageSize": 50, "currentPage": 1}
    assert session.calls[1]["params"] == {"pageSize": 50, "currentPage": 2}


def test_list_niches_single_page():
    body = {"data": [{"nicheId": "x" * 10}], "hasNext": False, "lastPage": 1}
    client, session, _ = _client([FakeResponse(200, body)])
    assert len(client.list_niches()) == 1
    assert len(session.calls) == 1


def test_list_niches_dedupes_when_server_repeats_pages():
    # Measured live: /v1/niches returns the full set on EVERY page.
    full = {"data": [{"nicheId": "a" * 10}, {"nicheId": "b" * 10}],
            "hasNext": True, "lastPage": 6}
    client, session, _ = _client([FakeResponse(200, full), FakeResponse(200, full)])
    niches = client.list_niches()
    assert [n["nicheId"] for n in niches] == ["a" * 10, "b" * 10]
    assert len(session.calls) == 2  # stops once page 2 adds nothing new


# ── normalizer: canonical shape ──────────────────────────────────────────────

def _payload(keywords, envelope="object"):
    data = {"keywords": keywords, "latestResearchDate": "2026-01-07T20:54:55.443Z"}
    return {"data": [data] if envelope == "list" else data}


_KW = {
    "keyword": "hair serum",
    "searchVolume": 119293,
    "relevancy": 0.8,
    "asinRanks": {"B07814LBR9": None, "B0BJZ9GT1J": 1},
    "suggestedBid": {"max": 297, "min": 179, "median": 238},
}


def test_keywords_to_mkl_df_canonical_shape():
    df, asins = keywords_to_mkl_df(_payload([_KW]))
    assert list(df.columns) == ["Search Term", "SV", "Relevance", "Sugg. Bid",
                                "Launch Score", "B07814LBR9", "B0BJZ9GT1J"]
    row = df.iloc[0]
    assert row["Search Term"] == "hair serum"
    assert row["SV"] == 119293
    assert row["Relevance"] == pytest.approx(8.0)      # 0.8 * 10 -> UI scale
    assert row["Sugg. Bid"] == pytest.approx(2.38)     # cents -> dollars
    assert row["Launch Score"] == 447.0                # round(SV * 0.003 / rel)
    assert pd.isna(row["B07814LBR9"]) and row["B0BJZ9GT1J"] == 1
    assert asins == ["B07814LBR9", "B0BJZ9GT1J"]


def test_keywords_to_mkl_df_accepts_list_envelope():
    # The spec declares data as an array; the live API returns an object. Both count.
    df, _ = keywords_to_mkl_df(_payload([_KW], envelope="list"))
    assert len(df) == 1


def test_keywords_to_mkl_df_null_suggested_bid_and_outlier_relevancy():
    kw = dict(_KW, keyword="true classix", suggestedBid=None, relevancy="Outlier")
    df, _ = keywords_to_mkl_df(_payload([kw]))
    row = df.iloc[0]
    assert row["Sugg. Bid"] == 0.0
    assert row["Relevance"] == 0.0


def test_launch_score_replicates_datadive_frontend_formula():
    # round(SV * 0.003 / relevancy) when relevancy >= 0.4 — the formula from
    # DataDive's public bundle, validated 419/419 against a real export.
    kw_hi = dict(_KW, keyword="hair growth serum", searchVolume=287789,
                 relevancy=0.7777777777777778)
    kw_low = dict(_KW, keyword="poco relevante", relevancy=0.35)
    df, _ = keywords_to_mkl_df(_payload([kw_hi, kw_low]))
    assert df.iloc[0]["Launch Score"] == 1110.0
    assert pd.isna(df.iloc[1]["Launch Score"])


def test_launch_score_is_empty_not_zero_below_the_gate():
    """The bundle's arrow function has no else: below the gate it returns undefined,
    which DataDive renders as an empty cell. A 0 would read as "cheapest keyword
    here" — the inverse of the truth, since the score is a cost to rank.

    This branch is the one the 419/419 export check could NOT cover: that export's
    lowest relevancy was 0.444, so every row was above the gate.
    """
    below = dict(_KW, keyword="apenas debajo", searchVolume=10000, relevancy=0.39)
    at_gate = dict(_KW, keyword="justo en el borde", searchVolume=10000, relevancy=0.4)
    outlier = dict(_KW, keyword="outlier", searchVolume=10000, relevancy="Outlier")
    no_sv = dict(_KW, keyword="sin volumen", searchVolume=0, relevancy=0.9)
    df, _ = keywords_to_mkl_df(_payload([below, at_gate, outlier, no_sv]))

    assert pd.isna(df.iloc[0]["Launch Score"])          # 0.39 < 0.4
    assert df.iloc[1]["Launch Score"] == 75.0           # 0.4 is inclusive
    assert pd.isna(df.iloc[2]["Launch Score"])          # not a number
    assert pd.isna(df.iloc[3]["Launch Score"])          # falsy searchVolume

    # Never a zero: that is the whole point of the change.
    assert not (df["Launch Score"] == 0).any()


def test_launch_score_matches_real_export_values():
    """Golden rows lifted from a real DataDive export (niche SAc3DGGJfI, 419
    keywords, 2026-08-31): the export carries DataDive's OWN Launch Score, so
    these pin the replica against the source of truth rather than against itself.

    Sampled across the whole range the export covers — both extremes of Launch
    Score, of SV and of relevancy, plus the quartiles. The export's lowest
    relevancy is 0.4444, which is exactly why it can only certify the computed
    branch; the empty branch is covered by the test above.
    """
    # (searchVolume, relevancy, Launch Score as DataDive exported it)
    real_rows = [
        (917, 1.0, 3.0),
        (250, 1.0, 1.0),
        (119293, 0.8888888888888888, 403.0),
        (250, 0.8888888888888888, 1.0),
        (287789, 0.7777777777777778, 1110.0),
        (567, 0.6666666666666666, 3.0),
        (1158, 0.5555555555555556, 6.0),
        (250, 0.5555555555555556, 1.0),
        (60321, 0.4444444444444444, 407.0),
        (55118, 0.4444444444444444, 372.0),
    ]
    kws = [dict(_KW, keyword=f"kw {i}", searchVolume=sv, relevancy=rel)
           for i, (sv, rel, _) in enumerate(real_rows)]
    df, _ = keywords_to_mkl_df(_payload(kws))
    got = list(df["Launch Score"])
    expected = [ls for _, _, ls in real_rows]
    assert got == expected


def test_official_launch_score_wins_over_the_replica():
    """The day DataDive exposes the field, the official one wins with no migration."""
    kw = dict(_KW, launchScore=999)
    df, _ = keywords_to_mkl_df(_payload([kw]))
    assert df.iloc[0]["Launch Score"] == 999.0   # not the formula's 1110


def test_launch_score_drift_detector():
    """A real export audits the formula: a match stays quiet, a recalibration warns."""
    from core.datadive import launch_score_drifted

    sv = pd.Series(range(1000, 1000 + 40 * 100, 100), dtype=float)
    rel = pd.Series([8.0] * 40)
    ok = pd.DataFrame({"SV": sv, "Relevance": rel,
                       "Launch Score": (sv * 0.003 / (rel / 10)).round()})
    assert launch_score_drifted(ok) is False

    drifted = ok.copy()
    drifted["Launch Score"] = (drifted["Launch Score"] * 1.6).round()
    assert launch_score_drifted(drifted) is True

    # Too small a sample, or missing columns: it accuses nothing.
    assert launch_score_drifted(ok.head(5)) is False
    assert launch_score_drifted(pd.DataFrame()) is False
    assert launch_score_drifted(ok.drop(columns=["Launch Score"])) is False


def test_keywords_to_mkl_df_skips_empty_terms_and_empty_payloads():
    kw = dict(_KW, keyword="  ")
    df, asins = keywords_to_mkl_df(_payload([kw]))
    assert df.empty and asins == []
    df2, asins2 = keywords_to_mkl_df({})
    assert df2.empty and asins2 == []


def test_keywords_to_mkl_df_tolerates_non_dict_asin_ranks():
    # Spec-vs-payload drift (like the envelope): a list must not crash it.
    kw = dict(_KW, asinRanks=["B0AAA00001"])
    df, asins = keywords_to_mkl_df(_payload([kw]))
    assert len(df) == 1 and asins == []


def test_keywords_to_mkl_df_unions_asins_across_keywords():
    kw1 = dict(_KW, asinRanks={"B0AAA00001": 3})
    kw2 = dict(_KW, keyword="otra kw", asinRanks={"B0BBB00002": None})
    df, asins = keywords_to_mkl_df(_payload([kw1, kw2]))
    assert asins == ["B0AAA00001", "B0BBB00002"]
    assert pd.isna(df.iloc[0]["B0BBB00002"])  # kw1 does not carry that ASIN -> NaN


def test_latest_research_date_reads_both_envelopes():
    assert latest_research_date(_payload([])) == "2026-01-07T20:54:55.443Z"
    assert latest_research_date(_payload([], envelope="list")).startswith("2026")
    assert latest_research_date({}) == ""


# ── rank radars ──────────────────────────────────────────────────────────────

def test_list_rank_radars_unwraps_paginated_envelope():
    page1 = {"data": {"pageSize": 50, "currentPage": 1, "hasNext": True,
                      "lastPage": 2, "data": [{"id": "r1"}]}}
    page2 = {"data": {"pageSize": 50, "currentPage": 2, "hasNext": False,
                      "lastPage": 2, "data": [{"id": "r2"}]}}
    client, session, _ = _client([FakeResponse(200, page1), FakeResponse(200, page2)])
    radars = client.list_rank_radars()
    assert [r["id"] for r in radars] == ["r1", "r2"]
    assert len(session.calls) == 2


def test_rank_radar_to_df_builds_date_columns_and_median():
    kws = [
        {"keyword": "water based lube", "searchVolume": 71783, "relevancy": 0.3,
         "ranks": [{"date": "2026-08-11", "organicRank": 101, "impressionRank": None},
                   {"date": "2026-08-12", "organicRank": 99, "impressionRank": 5},
                   {"date": "2026-08-13", "organicRank": None, "impressionRank": 5}]},
        {"keyword": "personal lubricant", "searchVolume": 5000, "relevancy": 0.8,
         "ranks": []},
    ]
    df, date_cols, agg = rank_radar_to_df(kws)
    assert date_cols == ["2026-08-11", "2026-08-12"]  # the all-null day does not count
    row = df.iloc[0]
    assert row["Search Term"] == "water based lube"
    assert row["SV"] == 71783
    assert row["Relevance"] == pytest.approx(3.0)
    assert row["Median Rank"] == pytest.approx(100.0)
    assert row["2026-08-11"] == 101
    assert pd.isna(df.iloc[1]["2026-08-11"]) and pd.isna(df.iloc[1]["Median Rank"])
    assert agg == {}


def test_rank_radar_to_df_empty():
    df, dates, agg = rank_radar_to_df([])
    assert df.empty and dates == [] and agg == {}


def test_rank_radar_to_df_new_radar_without_data_yet():
    # A freshly created radar: keywords but empty ranks. It must not break the tab —
    # it returns valid rows, with no date columns and a null Median Rank.
    df, dates, agg = rank_radar_to_df(
        [{"keyword": "kw uno", "searchVolume": 100, "relevancy": 0.5, "ranks": []}])
    assert not df.empty and dates == []
    assert list(df.columns) == ["Search Term", "SV", "Relevance", "Median Rank"]
    assert pd.isna(df.iloc[0]["Median Rank"])


# ── competitors_to_df ────────────────────────────────────────────────────────

_COMP = {
    "asin": "b09wmt8hyb",
    "brand": "The Ordinary",
    "rating": 4,
    "price": 24,
    "reviewCount": 1500,
    "sales": 54635,
    "revenue": 1311240,
    "kwRankedOnP1": 386,
    "kwRankedOnP1Percent": 0.9212,
    "svRankedOnP1": 1092198,
    "numberOfVariations": 1,
    "category": "Beauty & Personal Care",
}


def test_competitors_to_df_emits_export_labels():
    payload = {"data": {"competitors": [_COMP], "benchmark": {"price": 30,
                                                             "rating": 4.2,
                                                             "sales": 20000}}}
    df, medians = competitors_to_df(payload)
    row = df.iloc[0]
    assert row["ASIN"] == "B09WMT8HYB"
    assert row["Brand"] == "The Ordinary"
    assert row["30d Sales"] == 54635
    assert row["30d Revenue"] == 1311240
    assert row["KWs on P1"] == 386
    assert row["KWs on P1 Percentage"] == pytest.approx(92.1)  # fraction -> 0-100
    assert medians["Price"] == 30.0 and medians["30d Sales"] == 20000


def test_competitors_to_df_tolerates_dict_benchmark_values_and_empty():
    payload = {"data": {"competitors": [_COMP],
                        "benchmark": {"listingCreationDate": {"median": 0},
                                      "price": {"median": 25}}}}
    _, medians = competitors_to_df(payload)
    assert medians["Price"] == 25.0
    df, med = competitors_to_df({})
    assert df.empty and med == {}


def test_competitors_to_df_skips_rows_without_asin():
    payload = {"data": {"competitors": [dict(_COMP, asin=""), _COMP]}}
    df, _ = competitors_to_df(payload)
    assert len(df) == 1


# ── client_from_env ──────────────────────────────────────────────────────────

def test_client_from_env_reads_env_key(monkeypatch):
    monkeypatch.setenv("DATADIVE_API_KEY", "k-123")
    client = client_from_env()
    assert client is not None and client.api_key == "k-123"


def test_client_from_env_none_without_key(monkeypatch):
    # No env var and no [datadive] section in secrets means no client. secrets is
    # stubbed so the test does not depend on the local secrets.toml.
    monkeypatch.delenv("DATADIVE_API_KEY", raising=False)
    import streamlit
    monkeypatch.setattr(streamlit, "secrets", {}, raising=False)
    assert client_from_env() is None
