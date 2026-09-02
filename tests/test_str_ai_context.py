"""M2 STR - AI agent contract (ai/agents/str) and the module's display rows.

Scope: build_context (docs order, positional row_ids, derived CTR%, the
diagnostico_obligatorio flag, the cost_detected caveat, language), the
OUTPUT_SCHEMA conventions including the canonical platform synthesis, the
idempotency digest, the runtime state machine over a fake transport, and the
module-level row builders that join opinions back for core/ai_tab.
Excluded: the prompt itself (model judgment) and the Streamlit tab wiring.

Design rules:
- Anti-placebo rule: expected values hand-derived, never copied from the
  code under test (CTR% below: 20 clicks / 1000 impressions = 2.0).
- ZERO network: ai.client.ask is monkeypatched by the autouse fixture with a
  guard that fails on any real call; tests install their own fake on top.
- The runtime registry is process-global state: cleared before and after
  every test.
"""
import time

import pytest

import ai.client as ai_client
import ai.runtime as ai_runtime
from ai.agents.str.context import (
    HARV_PREFIX,
    MAX_CAMPAIGNS,
    NEG_PREFIX,
    OUTPUT_SCHEMA,
    StrData,
    build_context,
    make_ids,
)
from modules.pages.search_term_report import (
    _str_ai_rows,
    _str_campaign_rows,
    _str_harv_metrics,
    _str_neg_metrics,
    _STR_LABELS,
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


def _neg(term="alpha soap", clicks=20, imps=1000, orders=0, spend=5.0):
    return {"Search Term": term, "Campaign": "C1 - Broad", "Ad Group": "AG1",
            "Clicks": clicks, "Impressions": imps, "Spend": spend,
            "Orders": orders, "ACoS": 0, "Regla": "R2",
            "Match Type": "negativeExact", "Prioridad": "Alta"}


def _harv(term="soap bar", orders=4):
    return {"Search Term": term, "Campaign": "C2 - Exact", "Ad Group": "AG2",
            "Clicks": 30, "Orders": orders, "ACoS": 22.0, "CVR%": 13.3,
            "Bid Sugerido": 1.25, "Regla": "principal", "Prioridad": "Alta",
            "Ya en Exact": "Sí"}


def _data(idioma="es", cost_detected=True, campanas=None, brand_terms=None):
    if campanas is None:
        campanas = [{"Campaign": "Bleeder", "Impressions": 5000, "Clicks": 50,
                     "Spend": 40.0, "Sales": 0.0, "Orders": 0, "ACoS": 0.0},
                    {"Campaign": "Healthy", "Impressions": 900, "Clicks": 10,
                     "Spend": 8.0, "Sales": 60.0, "Orders": 2, "ACoS": 13.3}]
    return StrData(
        cliente="no declarado",
        brand_terms=brand_terms if brand_terms is not None else ["alpha"],
        target_acos=30.0, precio=20.0, cvr=5.25,
        umbral_clicks=38, umbral_spend=10.0,
        harvest_target_acos=30.0, harvest_precio=20.0,
        kpis={"Total Spend": "$48.00", "ACoS": "0.0%"},
        campanas=campanas,
        negativos=[_neg(), _neg("beta soap", clicks=40, imps=2000)],
        harvest=[_harv()],
        idioma=idioma, cost_detected=cost_detected,
    )


def _provider_response():
    synthesis = {"situation": "s", "week_actions": ["a1"], "mid_term": [],
                 "risks": [{"type": "DEFENSA_MARCA", "detail": "d",
                            "urgency": "ALTA"}]}
    return {"structured_output": {
                "negativos": [{"row_id": "N01", "razon": "r",
                               "categoria": "generico", "advertencia": None},
                              {"row_id": "N02", "razon": "r",
                               "categoria": "generico", "advertencia": None}],
                "harvest": [{"row_id": "H01", "razon": "r",
                             "categoria": "atributo",
                             "advertencia": "ya corre en exact"}],
                "campanas": [{"campaign": "Bleeder", "diagnostico": "sangra"}],
                "synthesis": synthesis},
            "session_id": "s1", "request_id": "r1", "text": ""}


def _wait(analysis, timeout=5.0):
    deadline = time.time() + timeout
    while analysis.running and time.time() < deadline:
        time.sleep(0.02)
    return analysis


class TestAgentOnDisk:
    def test_runtime_loads_str_agent(self):
        agent = ai_runtime._agent("str")
        assert agent["meta"]["model"] == "claude-opus-5"
        assert agent["meta"]["timeout_s"] == "900"
        assert "analista senior" in agent["system"]

    def test_str_agent_declares_no_provider_tools(self):
        # Analysis and chat stay deterministic-context only.
        assert ai_runtime.agent_tools("str") == []


class TestBuildContext:
    def test_five_docs_in_contract_order(self):
        _, docs, schema = build_context(_data())
        titles = [d["title"] for d in docs]
        assert titles[0] == "Parámetros"
        assert titles[1].startswith("KPIs de la cuenta")
        assert titles[2].startswith("Performance por campaña")
        assert titles[3].startswith("Candidatos a negativizar (2 filas)")
        assert titles[4].startswith("Candidatos a harvest (1 filas)")
        assert schema is OUTPUT_SCHEMA

    def test_row_ids_are_positional_per_list(self):
        _, docs, _ = build_context(_data())
        neg_lines = docs[3]["content"].splitlines()
        harv_lines = docs[4]["content"].splitlines()
        assert neg_lines[0].startswith("row_id,")
        assert neg_lines[1].startswith("N01,") and neg_lines[2].startswith("N02,")
        assert harv_lines[1].startswith("H01,")

    def test_negatives_gain_derived_ctr(self):
        # 20 clicks / 1000 impressions = 2.0
        _, docs, _ = build_context(_data())
        header = docs[3]["content"].splitlines()[0]
        first = docs[3]["content"].splitlines()[1]
        assert "CTR%" in header
        assert first.endswith(",2.0")

    def test_bleeding_campaign_is_flagged_mandatory(self):
        # Clicks 50 >= umbral 38 with 0 orders -> True; the healthy one -> False
        _, docs, _ = build_context(_data())
        lines = docs[2]["content"].splitlines()
        assert "diagnostico_obligatorio" in lines[0]
        bleeder = next(l for l in lines if l.startswith("Bleeder"))
        healthy = next(l for l in lines if l.startswith("Healthy"))
        assert bleeder.endswith("True") and healthy.endswith("False")

    def test_campaigns_capped_at_forty(self):
        camps = [{"Campaign": f"C{i}", "Clicks": 1, "Orders": 1}
                 for i in range(60)]
        _, docs, _ = build_context(_data(campanas=camps))
        assert f"top {MAX_CAMPAIGNS} por spend" in docs[2]["title"]
        assert len(docs[2]["content"].splitlines()) == 1 + MAX_CAMPAIGNS

    def test_cost_caveat_switches_with_flag(self):
        _, docs_ok, _ = build_context(_data(cost_detected=True))
        _, docs_no, _ = build_context(_data(cost_detected=False))
        assert "columna de costo detectada" in docs_ok[0]["content"]
        assert "NO detectada" in docs_no[0]["content"]

    def test_language_travels_inside_params(self):
        _, docs_es, _ = build_context(_data(idioma="es"))
        _, docs_en, _ = build_context(_data(idioma="en"))
        assert "es (español)" in docs_es[0]["content"]
        assert "en (English)" in docs_en[0]["content"]


class TestOutputSchemaConventions:
    def test_razon_declared_before_categoria(self):
        props = list(OUTPUT_SCHEMA["properties"]["negativos"]["items"]["properties"])
        assert props.index("razon") < props.index("categoria")

    def test_advertencia_nullable_with_closed_objects(self):
        item = OUTPUT_SCHEMA["properties"]["negativos"]["items"]
        assert item["properties"]["advertencia"]["type"] == ["string", "null"]
        assert item["additionalProperties"] is False
        assert set(item["required"]) == set(item["properties"])

    def test_synthesis_is_the_canonical_platform_shape(self):
        synth = OUTPUT_SCHEMA["properties"]["synthesis"]
        assert set(synth["required"]) == {"situation", "week_actions",
                                         "mid_term", "risks"}
        risk = synth["properties"]["risks"]["items"]
        assert set(risk["required"]) == {"type", "detail", "urgency"}
        assert risk["properties"]["urgency"]["enum"] == ["ALTA", "MEDIA"]
        assert "synthesis" in OUTPUT_SCHEMA["required"]


class TestDigestIdempotency:
    def test_same_data_same_digest_language_differs(self):
        _, d1, _ = ai_runtime._build("str", _data(idioma="es"))
        _, d2, _ = ai_runtime._build("str", _data(idioma="es"))
        _, d3, _ = ai_runtime._build("str", _data(idioma="en"))
        assert d1 == d2
        assert d1 != d3

    def test_slider_change_changes_the_digest(self):
        base = _data()
        moved = _data()
        moved.target_acos = 45.0
        _, d1, _ = ai_runtime._build("str", base)
        _, d2, _ = ai_runtime._build("str", moved)
        assert d1 != d2


class TestRuntimeStateMachine:
    def test_done_run_exposes_structured_output(self, monkeypatch):
        monkeypatch.setattr(ai_client, "ask", lambda **kw: _provider_response())
        a = _wait(ai_runtime.analyze("str", _data()))
        assert a.done and a.session_id == "s1"
        assert [n["row_id"] for n in a.result["negativos"]] == ["N01", "N02"]

    def test_provider_error_is_terminal_until_human_retry(self, monkeypatch):
        calls = {"n": 0}

        def _flaky(**kw):
            calls["n"] += 1
            if calls["n"] == 1:
                raise ai_client.ProviderDown("gateway down")
            return _provider_response()

        monkeypatch.setattr(ai_client, "ask", _flaky)
        a = _wait(ai_runtime.analyze("str", _data()))
        assert a.failed and calls["n"] == 1  # no automatic retries
        a.retry()
        _wait(a)
        assert a.done and calls["n"] == 2


class TestStrDisplayRows:
    _LABELS = _STR_LABELS["es"]

    def _records(self):
        return [_neg("alpha soap"), _neg("cat litter")]

    def test_positional_join_and_ghost_ids_ignored(self):
        opinions = [{"row_id": "N02", "razon": "r2", "categoria": "irrelevante",
                     "advertencia": None},
                    {"row_id": "N99", "razon": "ghost"}]
        rows = _str_ai_rows(self._records(), opinions, NEG_PREFIX, ["alpha"],
                            self._LABELS, _str_neg_metrics)
        assert rows[0]["reasoning"] == "" and rows[1]["reasoning"] == "r2"
        assert rows[1]["badges"] == ["irrelevante"]

    def test_category_hint_fires_both_directions(self):
        opinions = [{"row_id": "N01", "razon": "r", "categoria": "generico",
                     "advertencia": None},
                    {"row_id": "N02", "razon": "r", "categoria": "marca_propia",
                     "advertencia": None}]
        rows = _str_ai_rows(self._records(), opinions, NEG_PREFIX, ["alpha"],
                            self._LABELS, _str_neg_metrics)
        # "alpha soap" tagged generico despite matching the brand -> hint
        assert self._LABELS["cat_dudosa"] in rows[0]["badges"]
        # "cat litter" tagged marca_propia without matching it -> hint
        assert self._LABELS["cat_dudosa"] in rows[1]["badges"]

    def test_metrics_pills_hand_derived(self):
        assert _str_neg_metrics(_neg()) == ["20 clicks", "0 ord", "$5.00",
                                            "1000 impr"]
        harv = _str_harv_metrics(_harv())
        assert "ACoS 22.0%" in harv and "bid $1.25" in harv
        assert "ya en exact" in harv

    def test_campaign_pill_and_campaign_rows(self):
        rows = _str_ai_rows([_neg()], [], NEG_PREFIX, [], self._LABELS,
                            _str_neg_metrics)
        assert rows[0]["metrics"][-1] == "@ C1 - Broad"
        camp_rows = _str_campaign_rows([{"campaign": "Bleeder",
                                         "diagnostico": "sangra"}])
        assert camp_rows == [{"item": "Bleeder", "reasoning": "sangra"}]
