"""M3 SQP - AI agent contract (ai/agents/sqp: context, schema, runtime).

Scope: build_context (docs, row_ids, language), OUTPUT_SCHEMA (conventions),
idempotency digest and the runtime state machine over a fake transport.
Excluded: the prompt itself (model judgment) and the tab UI (render).

Design rules:
- Anti-placebo rule: expected values hand-derived, never copied from the code
  under test.
- ZERO network, ZERO secrets: ai.client.ask is ALWAYS monkeypatched (an autouse
  fixture replaces it with a guard that fails if anything reaches the network);
  tests needing transport install their own fake on top.
- ai/runtime holds process-global state: the autouse fixture clears the
  registry before and after every test so nothing leaks into the suite.
- First AI-layer test file in the repo: it establishes the pattern.
"""
import time

import pytest

import ai.client as ai_client
import ai.runtime as ai_runtime
from ai.agents.sqp.context import (
    MAX_ROWS,
    OUTPUT_SCHEMA,
    QUERY_PREFIX,
    SqpData,
    WARNING_TYPES,
    build_context,
    make_ids,
)


@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch):
    def _no_network(**kwargs):
        raise AssertionError("test attempted a real provider call")
    monkeypatch.setattr(ai_client, "ask", _no_network)
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    yield
    with ai_runtime._lock:
        ai_runtime._registry.clear()


def _rollup_stub():
    return {
        "n_queries": 2,
        "weighted_shares": {"imp": 10.0, "click": 9.0, "cart": 8.0, "purchase": 7.0},
        "weighted_deltas": {"d_imp_click": -1.0, "d_click_cart": -1.0,
                            "d_cart_purchase": -1.0},
        "dominant_leak_stage": "pdp",
        "pct_rows_with_data": 50.0, "pct_invisible": 0.0,
        "pct_no_price_data": 0.0, "pct_integrity_ok": 100.0,
        "total_opp_usd": 100.0,
        "invisible": {"rows": 0, "opp_usd": 0.0},
        "gems": {"rows": 0, "top_queries": []},
        "defense_broken": {"rows": 0, "queries": []},
        "premium_risk_leaking": 0,
        "tail": {"rows": 0, "opp_usd": 0.0, "gems": 0, "invisible": 0},
        "thresholds": {"p25_d1": -1.0},
        "pre_flags": {"DEFENSA_MARCA_ROTA": False},
    }


def _data(language="es", signal_rows=None, brand_terms=None):
    if signal_rows is None:
        signal_rows = [
            {"query": "alpha cream", "imp_share": 90.0, "opp_usd": 200.0},
            {"query": "water jug", "imp_share": 0.0, "opp_usd": 40.0},
        ]
    return SqpData(brand="alpha", brand_terms=brand_terms or ["alpha"],
                   week="2026-08-29", rollup=_rollup_stub(),
                   signal_rows=signal_rows, language=language)


def _provider_response(n_queries):
    queries = [{"row_id": rid, "reasoning": "r", "query_type": "GENERICA",
                "funnel_diagnosis": "FUNNEL_SANO",
                "price_causality": "INDETERMINADO", "action": "MONITOREAR",
                "confidence": "ALTA", "warning": None}
               for rid in make_ids(QUERY_PREFIX, n_queries)]
    return {"structured_output": {"queries": queries, "synthesis": {
                "situation": "s", "week_actions": [], "mid_term": [],
                "risks": [], "executive_summary": "r"}},
            "session_id": "s1", "request_id": "r1", "text": ""}


def _wait(analysis, timeout=5.0):
    deadline = time.time() + timeout
    while analysis.running and time.time() < deadline:
        time.sleep(0.02)
    return analysis


class TestAgentOnDisk:
    def test_runtime_loads_sqp_agent(self):
        agent = ai_runtime._agent("sqp")
        assert agent["meta"]["model"] == "claude-opus-5"
        assert agent["meta"]["effort"] == "high"
        assert agent["meta"]["timeout_s"] == "3600"
        assert "analista senior" in agent["system"]

    def test_prompt_has_no_chat_rules_duplicated(self):
        # Chat rules live ONLY in _shared/chat.md; the runtime appends them.
        assert "chat" not in ai_runtime._agent("sqp")["system"][:200].lower()


class TestBuildContext:
    def test_three_docs_in_contract_order(self):
        _, docs, schema = build_context(_data())
        titles = [d["title"] for d in docs]
        assert titles[0] == "Parámetros"
        assert titles[1].startswith("Rollup de cuenta")
        assert titles[2].startswith("Señales por query")
        assert schema is OUTPUT_SCHEMA

    def test_row_ids_are_positional(self):
        _, docs, _ = build_context(_data())
        lines = docs[2]["content"].splitlines()
        assert lines[0].startswith("row_id,")
        assert lines[1].startswith("Q01,") and lines[2].startswith("Q02,")

    def test_empty_signal_rows_produce_empty_csv_without_crash(self):
        _, docs, _ = build_context(_data(signal_rows=[]))
        assert docs[2]["content"].strip() == ""

    def test_language_travels_inside_params(self):
        _, docs_es, _ = build_context(_data(language="es"))
        _, docs_en, _ = build_context(_data(language="en"))
        assert "es (español)" in docs_es[0]["content"]
        assert "en (English)" in docs_en[0]["content"]

    def test_preflags_reach_the_model_as_text(self):
        _, docs, _ = build_context(_data())
        assert "DEFENSA_MARCA_ROTA: false" in docs[1]["content"]


class TestOutputSchemaConventions:
    def test_reasoning_declared_before_every_verdict(self):
        props = list(OUTPUT_SCHEMA["properties"]["queries"]["items"]["properties"])
        assert props.index("reasoning") < props.index("query_type")
        assert props.index("reasoning") < props.index("funnel_diagnosis")
        assert props.index("reasoning") < props.index("action")

    def test_warning_nullable_with_closed_objects(self):
        item = OUTPUT_SCHEMA["properties"]["queries"]["items"]
        assert item["properties"]["warning"]["type"] == ["string", "null"]
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"])

    def test_risks_enum_is_the_closed_warning_list(self):
        risk = (OUTPUT_SCHEMA["properties"]["synthesis"]["properties"]
                ["risks"]["items"])
        assert risk["properties"]["type"]["enum"] == WARNING_TYPES

    def test_warning_types_cover_module_preflags_plus_standing(self):
        import pandas as pd
        from modules.pages.search_query_performance import (
            _compute_account_rollup, _compute_funnel_signals)
        df = pd.DataFrame({"Search Query": ["a"], "Search Query Volume": [10],
                           "Impressions: Total Count": [100],
                           "Impressions: Brand Count": [10],
                           "Purchases: Total Count": [10],
                           "Purchases: Brand Count": [1]})
        signals, th = _compute_funnel_signals(df, "Search Query", [])
        flags = set(_compute_account_rollup(signals, th)["pre_flags"])
        standing = {"CAVEAT_ATRIBUCION_24H", "FOTO_SEMANAL_SIN_TENDENCIA"}
        assert flags | standing == set(WARNING_TYPES)


class TestDigestIdempotency:
    def test_same_data_same_digest_different_language_differs(self):
        _, d1, _ = ai_runtime._build("sqp", _data(language="es"))
        _, d2, _ = ai_runtime._build("sqp", _data(language="es"))
        _, d3, _ = ai_runtime._build("sqp", _data(language="en"))
        assert d1 == d2
        assert d1 != d3

    def test_brand_terms_change_the_digest(self):
        _, d1, _ = ai_runtime._build("sqp", _data(brand_terms=["alpha"]))
        _, d2, _ = ai_runtime._build("sqp", _data(brand_terms=["alpha", "alfa"]))
        assert d1 != d2

    def test_analyze_is_idempotent_per_digest(self, monkeypatch):
        monkeypatch.setattr(ai_client, "ask",
                            lambda **kw: _provider_response(2))
        a1 = ai_runtime.analyze("sqp", _data())
        a2 = ai_runtime.analyze("sqp", _data())
        assert a1 is a2
        _wait(a1)
        assert a1.done


class TestRuntimeStateMachine:
    def test_done_run_exposes_structured_output_and_session(self, monkeypatch):
        monkeypatch.setattr(ai_client, "ask",
                            lambda **kw: _provider_response(2))
        a = _wait(ai_runtime.analyze("sqp", _data()))
        assert a.done
        assert a.session_id == "s1"
        assert [q["row_id"] for q in a.result["queries"]] == ["Q01", "Q02"]

    def test_missing_structured_output_fails_in_spanish(self, monkeypatch):
        monkeypatch.setattr(
            ai_client, "ask",
            lambda **kw: {"structured_output": None, "session_id": "s1",
                          "request_id": "r1", "text": "prose"})
        a = _wait(ai_runtime.analyze("sqp", _data()))
        assert a.failed
        assert a.error == "La IA no devolvió el formato pactado."

    def test_provider_error_is_terminal_until_human_retry(self, monkeypatch):
        calls = {"n": 0}

        def _flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ai_client.ProviderDown("gateway down")
            return _provider_response(2)

        monkeypatch.setattr(ai_client, "ask", _flaky)
        a = _wait(ai_runtime.analyze("sqp", _data()))
        assert a.failed and calls["n"] == 1  # no automatic retries
        a.retry()
        _wait(a)
        assert a.done and calls["n"] == 2

    def test_max_rows_constant_matches_module_cap(self):
        from modules.pages.search_query_performance import _TOP_ROWS
        assert MAX_ROWS == _TOP_ROWS


def test_digest_includes_the_system_prompt():
    """A prompt edit changes the digest, so the platform shows the STALE
    banner instead of silently reusing an analysis built on the old rules."""
    from ai.runtime import _digest
    docs = [{"title": "t", "content": "c"}]
    a = _digest("sqp", "system v1", "input", docs, "opus", None)
    b = _digest("sqp", "system v2", "input", docs, "opus", None)
    assert a != b
    assert a == _digest("sqp", "system v1", "input", docs, "opus", None)
