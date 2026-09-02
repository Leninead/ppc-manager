"""core/ai_tab - the reusable AI tab a module plugs in.

Scope: the pure lifecycle decision (full matrix), label merging, the render
kit in both languages (incl. the $-escape gotcha), and an AppTest smoke of
resolve_analysis + render_analysis over a fake agent and fake transport.
Excluded: STR/SQP modules (not migrated yet by design) and core/ai_chat
internals (covered by its consumers).

Design rules:
- Anti-placebo rule: expected values hand-derived, never copied from the
  code under test.
- ZERO network: ai.client.ask is monkeypatched in every runtime-touching
  test; the autouse fixture clears the process-global registry and the
  injected fake agent before and after each test.
- AppTest.from_string only for what needs the Streamlit runtime (house
  rule: never from_function).
"""
import types

import pytest
from streamlit.testing.v1 import AppTest

import ai.client as ai_client
import ai.runtime as ai_runtime
from core.ai_tab import (
    AnalysisAction,
    ai_chips_html,
    ai_labels,
    ai_notice_html,
    decide_analysis_action,
    escape_ai_text,
    opinion_table_html,
    synthesis_html,
    humanize_fields,
)

_FAKE_SLUG = "_layer_test"


@pytest.fixture(autouse=True)
def _isolated_runtime(monkeypatch):
    def _no_network(**kwargs):
        raise AssertionError("test attempted a real provider call")
    monkeypatch.setattr(ai_client, "ask", _no_network)
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    ai_runtime._agents.pop(_FAKE_SLUG, None)
    yield
    with ai_runtime._lock:
        ai_runtime._registry.clear()
    ai_runtime._agents.pop(_FAKE_SLUG, None)


class TestDecideAnalysisAction:
    def test_registry_hit_wins_over_everything(self):
        assert decide_analysis_action(
            peeked_exists=True, last_digest_exists=True,
            file_changed=True, previous_done=True) is AnalysisAction.USE

    def test_first_payload_of_the_session_fires(self):
        assert decide_analysis_action(
            peeked_exists=False, last_digest_exists=False,
            file_changed=True, previous_done=False) is AnalysisAction.AUTO_FIRE

    def test_new_file_fires_even_with_a_previous_analysis(self):
        assert decide_analysis_action(
            peeked_exists=False, last_digest_exists=True,
            file_changed=True, previous_done=True) is AnalysisAction.AUTO_FIRE

    def test_parameter_change_over_finished_analysis_is_stale(self):
        assert decide_analysis_action(
            peeked_exists=False, last_digest_exists=True,
            file_changed=False, previous_done=True) is AnalysisAction.STALE

    def test_parameter_change_without_usable_previous_is_pending(self):
        assert decide_analysis_action(
            peeked_exists=False, last_digest_exists=True,
            file_changed=False, previous_done=False) is AnalysisAction.PENDING


class TestLabels:
    def test_overrides_win_and_base_survives(self):
        labels = ai_labels("es", {"chat": "Análisis IA — SQP"})
        assert labels["chat"] == "Análisis IA — SQP"
        assert labels["retry"] == "Reintentar"

    def test_unknown_language_falls_back_to_spanish(self):
        assert ai_labels("pt")["retry"] == "Reintentar"

    def test_english_pack_is_english(self):
        assert ai_labels("en")["retry"] == "Retry"


class TestRenderKit:
    _ROW = {"item": "brita jug", "type_tag": "GENERICA",
            "metrics": ["imp 1.0%"], "badges": ["SIN_VISIBILIDAD"],
            "confidence": "MEDIA", "warning": "check sample",
            "reasoning": "opp $23,797.20 at stake"}
    _SYNTH = {"situation": "s", "week_actions": ["a1"], "mid_term": ["m1"],
              "risks": [{"type": "COBERTURA_BAJA", "detail": "d",
                         "urgency": "MEDIA"}]}

    @pytest.mark.parametrize("lang", ["es", "en"])
    def test_all_builders_render(self, lang):
        labels = ai_labels(lang)
        table = opinion_table_html([self._ROW], "T", labels,
                                   {"SIN_VISIBILIDAD": "background:#EEE"})
        assert "brita jug" in table and "SIN_VISIBILIDAD" in table
        assert labels["conf_label"] in table
        synth = synthesis_html(self._SYNTH, labels)
        assert "a1" in synth and "COBERTURA_BAJA" in synth
        assert "3" in ai_chips_html(3, "40 items", 120, labels)
        notice = ai_notice_html(labels["stale_title"], labels["stale_body"])
        assert labels["stale_title"] in notice

    @pytest.mark.parametrize("lang", ["es", "en"])
    def test_synthesis_sections_carry_visible_headings(self, lang):
        """The numbered actions were printed without a heading, so the AM
        could not tell suggestions from the situation text: every list block
        now opens with its labelled section title, and the actions heading
        carries the "AM decides" hint as a tooltip."""
        labels = ai_labels(lang)
        synth = synthesis_html(self._SYNTH, labels)
        for key in ("actions_title", "mid_term_title", "risks_title"):
            assert labels[key].upper() in synth.upper()
        assert f'title="{labels["actions_hint"]}"' in synth
        assert synth.index(labels["actions_title"]) < synth.index("a1")
        assert synth.index("a1") < synth.index(labels["mid_term_title"])
        assert synth.index("m1") < synth.index(labels["risks_title"])

    def test_synthesis_omits_headings_of_empty_sections(self):
        labels = ai_labels("es")
        synth = synthesis_html({"situation": "s", "week_actions": [],
                                "mid_term": [], "risks": []}, labels)
        for key in ("actions_title", "mid_term_title", "risks_title"):
            assert labels[key] not in synth

    def test_row_id_is_printed_ahead_of_the_item(self):
        """The synthesis cites rows by id (N07, Q03): the table must show
        that id next to the term or the AM cannot find the row."""
        table = opinion_table_html([{**self._ROW, "row_id": "Q07"}], "T",
                                   ai_labels("es"), {})
        assert "Q07" in table
        assert table.index("Q07") < table.index("brita jug")
        # Rows without an id (campaign diagnoses) render exactly as before.
        plain = opinion_table_html([self._ROW], "T", ai_labels("es"), {})
        assert "monospace;font-size:13px;background:#F1EFE8" not in plain

    def test_dollar_signs_escaped_against_latex(self):
        table = opinion_table_html([self._ROW], "T", ai_labels("es"), {})
        assert "&#36;23,797.20" in table

    def test_humanize_fields_rewrites_whole_tokens_only(self):
        g = {"imp_b": "impresiones de la marca", "imp_share": "share de "
             "impresiones", "pur_t": "compras del mercado",
             "is_invisible": "marca sin visibilidad", "d1": "caída 1"}
        text = ("pur_t 1753: imp_b 21, imp_share 0.0 marcan is_invisible; "
                "x.imp_b y imp_bx quedan; d1 -3.2, id1 no")
        out = humanize_fields(text, g)
        assert out.startswith("compras del mercado 1753: impresiones de la "
                              "marca 21, share de impresiones 0.0 marcan "
                              "marca sin visibilidad")
        assert "x.imp_b" in out and "imp_bx" in out and "id1" in out
        assert "caída 1 -3.2" in out
        assert "imp_share" not in out.replace("share de impresiones", "")

    def test_humanize_fields_is_a_no_op_without_leaks_or_glossary(self):
        assert humanize_fields("$23,797.20 en juego", {"imp_b": "x"}) == \
            "$23,797.20 en juego"
        assert humanize_fields("imp_b 3", {}) == "imp_b 3"
        assert humanize_fields(None, {"imp_b": "x"}) == ""

    def test_unknown_badge_gets_the_default_style(self):
        table = opinion_table_html([self._ROW], "T", ai_labels("es"), {})
        assert "background-color:#F5F5F5" in table

    def test_zero_warnings_chip(self):
        labels = ai_labels("es")
        assert labels["no_warnings"] in ai_chips_html(0, "x", 1, labels)


_SMOKE_SCRIPT = f"""
import time
import streamlit as st
from core import ai_tab

labels = ai_tab.ai_labels("es", {{"chat": "smoke chat"}})
analysis = ai_tab.resolve_analysis(
    slug="{_FAKE_SLUG}", payload="payload-1",
    file_signature="sig-1", labels=labels)

deadline = time.time() + 5
while analysis is not None and analysis.running and time.time() < deadline:
    time.sleep(0.02)

def _render(result, a):
    st.markdown("LAYER_RESULT " + result["marker"] + " " + a.digest[:8])

if analysis is not None:
    ai_tab.render_analysis(analysis, slug="{_FAKE_SLUG}", labels=labels,
                             render_result=_render)
ai_tab.mount_analysis_chat("{_FAKE_SLUG}", analysis, lang="es",
                             labels=labels)
"""


class TestLifecycleSmoke:
    def _install_fake_agent(self, monkeypatch):
        ai_runtime._agents[_FAKE_SLUG] = {
            "meta": {"model": "opus"},
            "system": "layer smoke system",
            "context": types.SimpleNamespace(build_context=lambda d: (
                "input", [{"title": "Doc", "content": str(d)}], None)),
        }
        monkeypatch.setattr(
            ai_client, "ask",
            lambda **kw: {"structured_output": {"marker": "OK"},
                          "session_id": "smoke-sid", "request_id": "r1",
                          "text": ""})

    def test_auto_fire_renders_result_and_sets_session_keys(self, monkeypatch):
        self._install_fake_agent(monkeypatch)
        at = AppTest.from_string(_SMOKE_SCRIPT)
        at.run(timeout=15)
        assert not at.exception
        rendered = " ".join(str(m.value) for m in at.markdown)
        assert "LAYER_RESULT OK" in rendered
        assert at.session_state[f"{_FAKE_SLUG}_ai_file_sig"] == "sig-1"
        assert at.session_state[f"{_FAKE_SLUG}_ai_last_digest"]

    def test_second_run_reuses_the_registry_entry(self, monkeypatch):
        self._install_fake_agent(monkeypatch)
        calls = {"n": 0}
        real = ai_client.ask

        def _counting(**kw):
            calls["n"] += 1
            return real(**kw)
        monkeypatch.setattr(ai_client, "ask", _counting)
        at = AppTest.from_string(_SMOKE_SCRIPT)
        at.run(timeout=15)
        at.run(timeout=15)
        assert not at.exception
        assert calls["n"] == 1  # idempotent digest: one paid run
