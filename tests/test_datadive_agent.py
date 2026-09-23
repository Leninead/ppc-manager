"""Tests for the ai/agents/datadive agent: serialized context and output contract."""
from __future__ import annotations

from ai.agents.datadive.context import (
    MAX_KEYWORDS,
    MklData,
    OUTPUT_SCHEMA,
    build_context,
    make_ids,
)


def _data(n_keywords: int = 3, **overrides) -> MklData:
    keywords = [{"term": f"kw {i}", "sv": 1000 - i, "relevance": 5.0,
                 "sugg_bid": 0.5, "mi_rank": None, "comps_rankeando": 2}
                for i in range(n_keywords)]
    base = dict(niche_label="SEVEN_SERUM", fuente="API DataDive",
                marketplace="com", my_asin="B0AAA00001", min_sv=100,
                min_rel=1.0, total_keywords=n_keywords,
                competitor_asins=["B0BBB00002"], keywords=keywords)
    base.update(overrides)
    return MklData(**base)


def test_agent_is_discovered_by_runtime():
    import ai.runtime as runtime
    assert "datadive" in runtime._agents
    meta = runtime._agents["datadive"]["meta"]
    assert meta.get("model") == "claude-opus-5-5"
    assert meta.get("timeout_s") == "3600"
    assert meta.get("tools") == "datadive, amazon_ads"


def test_ask_followup_sends_datadive_tools_profile(monkeypatch):
    import ai.client as ai_client
    import ai.runtime as runtime

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        ok = True

        def json(self):
            return {"text": "ok", "session_id": "s2"}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(json or {})
        captured["http_timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    text, sid = runtime.ask_followup(
        "datadive", "11111111-1111-1111-1111-111111111111", "hola")
    assert captured["tools"] == ["datadive"]
    assert captured["http_timeout"] == 3600  # a chat turn waits as long as the agent's timeout_s
    assert captured["max_turns"] > 1  # the agentic loop needs turns for tools
    assert text == "ok" and sid == "s2"


def test_ask_followup_without_session_opens_a_fresh_one(monkeypatch):
    """While the analysis is still running, a question the tools can answer (the
    quota, say) opens its own session instead of waiting."""
    import ai.client as ai_client
    import ai.runtime as runtime

    captured: dict = {}

    class FakeResponse:
        status_code = 200
        ok = True

        def json(self):
            return {"text": "quedan 166 dive tokens", "session_id": "nueva"}

    def fake_post(url, json=None, headers=None, timeout=None):
        captured.update(json or {})
        return FakeResponse()

    monkeypatch.setattr(ai_client.requests, "post", fake_post)
    text, sid = runtime.ask_followup("datadive", None, "que cuota queda?")
    assert "session_id" not in captured  # a fresh session, not a resume
    assert captured["tools"] == ["datadive"]
    assert sid == "nueva" and "166" in text


def test_agent_tools_reads_frontmatter():
    import ai.runtime as runtime
    assert runtime.agent_tools("datadive") == ["datadive", "amazon_ads"]


def test_build_context_returns_two_docs_and_schema():
    input_text, docs, schema = build_context(_data())
    assert "row_id" in input_text or "row_ids" in input_text
    assert [d["title"].split(" (")[0] for d in docs] == ["Parámetros",
                                                         "Keywords del niche"]
    assert schema is OUTPUT_SCHEMA


def test_keywords_doc_carries_row_ids_and_caps_rows():
    _, docs, _ = build_context(_data(n_keywords=MAX_KEYWORDS + 30))
    csv = docs[1]["content"]
    lines = csv.strip().splitlines()
    assert lines[0].startswith("row_id,")
    assert len(lines) == MAX_KEYWORDS + 1  # header plus the capped rows
    assert lines[1].startswith("K01,")


def test_params_doc_has_no_source_specific_caveats():
    # The Launch Score is computed in API mode too (the frontend formula), so no
    # source needs a special caveat under Parameters.
    _, docs_api, _ = build_context(_data(fuente="API DataDive"))
    _, docs_file, _ = build_context(_data(fuente="Archivo"))
    assert "launch_score" not in docs_api[0]["content"]
    assert docs_api[0]["content"].replace("API DataDive", "Archivo") == \
        docs_file[0]["content"]


def test_competitors_doc_is_optional_third_doc():
    _, docs_sin, _ = build_context(_data())
    assert len(docs_sin) == 2
    comps = [{"asin": "B0AAA00001", "brand": "X", "price": 20.0, "rating": 4.5,
              "reviews": 100, "sales_30d": 5000, "revenue_30d": 100000, "kws_p1": 50}]
    _, docs_con, _ = build_context(_data(competitors=comps))
    assert len(docs_con) == 3
    assert docs_con[2]["title"].startswith("Competidores del niche")
    assert "B0AAA00001" in docs_con[2]["content"]


def test_select_keywords_reserves_slots_for_the_long_tail():
    """A pure SV cut dropped the cheap tail and skewed the judgement towards
    'expensive niche'. A slice is reserved for the most relevant rows below it."""
    import pandas as pd

    from ai.agents.datadive.context import _SV_SLOTS, _TAIL_SLOTS, select_keywords

    # 200 rows: descending SV, plus a low-SV tail with high relevance.
    df = pd.DataFrame({
        "SV": list(range(200, 0, -1)),
        "Relevance": [1.0] * (_SV_SLOTS + 5) + [9.0] * (200 - _SV_SLOTS - 5),
    })
    out = select_keywords(df)
    assert len(out) == _SV_SLOTS + _TAIL_SLOTS
    assert out.iloc[0]["SV"] == 200                    # the head still comes first
    cola = out.iloc[_SV_SLOTS:]
    assert (cola["Relevance"] == 9.0).all()            # the tail gets in on relevance
    assert cola["SV"].max() < out.iloc[_SV_SLOTS - 1]["SV"]


def test_params_warns_when_declared_asin_is_not_in_the_niche():
    """An ASIN absent from the dive leaves mi_rank empty in every row: that is
    missing data, not an absence of ranking — and without the notice the agent
    emitted gaps over evidence that did not exist."""
    _, docs_ok, _ = build_context(_data(my_asin="B0AAA00001"))
    _, docs_bad, _ = build_context(_data(my_asin="B0AAA00001",
                                         my_asin_en_niche=False))
    assert "CALIDAD DE DATOS" not in docs_ok[0]["content"]
    assert "CALIDAD DE DATOS" in docs_bad[0]["content"]
    # With no ASIN declared, neither of the two notices applies.
    _, docs_none, _ = build_context(_data(my_asin=""))
    assert "CALIDAD DE DATOS" not in docs_none[0]["content"]
    assert "figura entre los ASINs rastreados" not in docs_none[0]["content"]


def test_schema_forces_an_actionable_decision_per_row():
    """The output must carry the PPC decision, not just the diagnosis."""
    cluster = OUTPUT_SCHEMA["properties"]["clusters"]["items"]
    assert "match_type" in cluster["required"]
    assert set(cluster["properties"]["match_type"]["enum"]) == {
        "exact", "phrase", "broad", "product_targeting"}
    gap = OUTPUT_SCHEMA["properties"]["gaps"]["items"]
    assert {"via", "confianza"} <= set(gap["required"])
    assert set(gap["properties"]["via"]["enum"]) == {
        "PPC_AHORA", "LISTING_PRIMERO", "NO_ATACABLE"}
    # urgency is no longer a free string: the render prints it verbatim.
    risks = OUTPUT_SCHEMA["properties"]["synthesis"]["properties"]["risks"]
    assert set(risks["items"]["properties"]["urgency"]["enum"]) == {
        "alta", "media", "baja"}
    # The caps the prompt states are now enforced by the schema.
    assert OUTPUT_SCHEMA["properties"]["clusters"]["maxItems"] == 8
    assert OUTPUT_SCHEMA["properties"]["gaps"]["maxItems"] == 10


def test_chat_rules_are_scoped_to_chat_turns():
    """chat.md is concatenated onto the ANALYSIS system prompt too, so it must say
    explicitly that its limits do not govern the schema fields."""
    import ai.runtime as runtime
    assert "EXCLUSIVAMENTE los turnos de chat" in runtime._CHAT_RULES
    assert "NO alcanza a la salida por schema" in runtime._CHAT_RULES


def test_schema_emits_canonical_synthesis_shape():
    # core/ai_tab.synthesis_html requires this shape from every new agent.
    synth = OUTPUT_SCHEMA["properties"]["synthesis"]
    assert set(synth["required"]) == {"situation", "week_actions", "mid_term",
                                     "risks", "executive_summary"}
    risk = synth["properties"]["risks"]["items"]
    assert set(risk["required"]) == {"type", "detail", "urgency"}


def test_make_ids_are_stable_and_positional():
    assert make_ids("K", 3) == ["K01", "K02", "K03"]
    assert make_ids("K", 101)[-1] == "K101"


def test_gap_rows_print_the_row_id_ahead_of_the_term():
    """The synthesis cites gaps as K07: the gaps table must show that id next
    to the term, otherwise the AM cannot find the row it refers to."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from core import ai_tab
from modules.pages.datadive_analyzer import _render_mkl_ai_result

class A:
    elapsed = 3

records = [{"term": "dog vitamins", "sv": 1200, "relevance": 3.1,
            "comps_rankeando": 4, "launch_score": 12, "mi_rank": None},
           {"term": "senior dog joint chews", "sv": 800, "relevance": 4.0,
            "comps_rankeando": 6, "launch_score": 0, "mi_rank": 31}]
result = {"clusters": [], "gaps": [
    {"row_id": "K02", "via": "PPC_AHORA", "confianza": "alta",
     "razon": "r", "advertencia": None}],
    "synthesis": {"situation": "s", "week_actions": ["Atacar K02 primero"],
                  "mid_term": [], "risks": []}}
_render_mkl_ai_result(result, A(), records, ai_tab.ai_labels("es"))
'''
    at = AppTest.from_string(script)
    at.run(timeout=30)
    assert not at.exception
    html = " ".join(str(m.value) for m in at.markdown)
    assert "K02" in html
    assert html.index("K02") < html.index("senior dog joint chews")
    assert "K01" not in html  # only rows the AI named are listed as gaps
    # The synthesis cites K02: the term is appended so the prose reads alone.
    assert "K02 (senior dog joint chews) primero" in html


def test_row_labels_map_positional_ids_to_terms():
    from modules.pages.datadive_analyzer import _dd_row_labels
    assert _dd_row_labels([{"term": "a"}, {"term": " b "}]) == {"K01": "a",
                                                                 "K02": "b"}
    assert _dd_row_labels([]) == {}
