"""core/ai_tab - the reusable AI tab a module plugs in.

Scope: the pure lifecycle decision (full matrix), label merging, the render
kit in both languages (incl. the $-escape gotcha), and an AppTest smoke of
resolve_analysis + render_analysis over a fake agent and fake transport.
Excluded: the STR/SQP/DataDive consumers (their own test files) and
core/ai_chat internals beyond the annotate path.

Design rules:
- Anti-placebo rule: expected values hand-derived, never copied from the
  code under test.
- ZERO network: ai.client.ask is monkeypatched in every runtime-touching
  test; the autouse fixture clears the process-global registry and the
  injected fake agent before and after each test.
- AppTest.from_string only for what needs the Streamlit runtime (house
  rule: never from_function).
"""
import re
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
    annotate_row_ids,
    map_synthesis_text,
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

    def test_a_table_whose_rows_have_no_diagnosis_drops_that_column(self):
        labels = ai_labels("es")
        with_column = opinion_table_html([self._ROW], "T", labels, {})
        without_column = opinion_table_html([self._ROW], "T", labels, {}, diagnosis_column=False)

        header_cells = lambda table: len(re.findall(r"<th[ >]", table))  # noqa: E731
        assert header_cells(with_column) == 3 and 'class="c-diag"' in with_column
        assert header_cells(without_column) == 2 and "c-diag" not in without_column
        assert "brita jug" in without_column

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

    def test_annotate_row_ids_appends_the_item_once(self):
        m = {"H59": "press on nails short almond", "H5": "x",
             "Q01": "brita water pitcher"}
        out = annotate_row_ids("Frenar H59 hasta validar; H5 no; H590 tampoco",
                               m)
        assert out == ("Frenar H59 (press on nails short almond) hasta "
                       "validar; H5 (x) no; H590 tampoco")
        # Only the first mention of an id in a text gets the item.
        assert annotate_row_ids("H59 sube; H59 baja", m) == \
            "H59 (press on nails short almond) sube; H59 baja"
        # The model already wrote the term next to the id: left untouched.
        same = "Decidir Q01 (brita water pitcher, $23,797.20 de oportunidad)"
        assert annotate_row_ids(same, m) == same
        assert annotate_row_ids("N01", {"N01": "a" * 60}) == \
            "N01 (" + "a" * 39 + "…)"
        assert annotate_row_ids("", m) == ""
        assert annotate_row_ids("H59", {}) == "H59"

    def test_replace_row_ids_writes_the_item_where_no_table_travels(self):
        from ai.agents.row_annotation import replace_row_ids
        m = {"N01": "brita filter", "N10": "zero water"}
        assert replace_row_ids("Negativizar N01 y N10; N100 no", m) == \
            "Negativizar «brita filter» y «zero water»; N100 no"
        assert replace_row_ids("N01", {"N01": ""}) == "N01"
        assert replace_row_ids("sin ids", {}) == "sin ids"

    def test_map_synthesis_text_touches_only_prose(self):
        s = {"situation": "s", "week_actions": ["a", "b"], "mid_term": [],
             "risks": [{"type": "T", "urgency": "ALTA", "detail": "d"}],
             "executive_summary": "e"}
        out = map_synthesis_text(s, str.upper)
        assert out["situation"] == "S" and out["week_actions"] == ["A", "B"]
        assert out["risks"] == [{"type": "T", "urgency": "ALTA", "detail": "D"}]
        assert out["executive_summary"] == "E"
        assert s["situation"] == "s"  # input not mutated

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

labels = ai_tab.ai_labels("es")
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
ai_tab.publish_analysis_to_chat("{_FAKE_SLUG}", analysis, "payload-1",
                                module_label="Smoke", subject="cuenta 1",
                                reading=lambda a: "lectura " + a.result["marker"])
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
        shared = at.session_state["app_chat_modules"][_FAKE_SLUG]
        assert shared.state == "current"
        assert [(doc["title"], doc["content"]) for doc in shared.analysis.documents] == [
            ("Smoke · cuenta 1 · Doc", "payload-1"), ("Smoke · cuenta 1 · Lectura de la IA", "lectura OK")]

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


class TestSessionHelpers:
    def _fake_st(self, monkeypatch, state=None):
        from core import ai_tab
        fake = types.SimpleNamespace(session_state=state if state is not None else {})
        monkeypatch.setattr(ai_tab, "st", fake)
        return ai_tab, fake

    def test_app_language_follows_the_sidebar_radio(self, monkeypatch):
        ai_tab, fake = self._fake_st(monkeypatch, {"app_lang": "English"})
        assert ai_tab.app_language() == "en"
        fake.session_state.clear()
        assert ai_tab.app_language() == "es"

    def test_records_for_render_keeps_the_rows_of_each_digest(self, monkeypatch):
        """A STALE analysis must join against the rows it was built from:
        the store is keyed by digest and only refreshed when the current
        payload digests to the analysis shown."""
        ai_tab, fake = self._fake_st(monkeypatch)
        peeked = {"digest": "d1"}
        monkeypatch.setattr(ai_tab.ai_runtime, "peek",
                            lambda slug, payload: types.SimpleNamespace(**peeked))
        shown = types.SimpleNamespace(digest="d1")
        assert ai_tab.records_for_render("x", shown, "p1", ["r1"]) == ["r1"]
        peeked["digest"] = "d2"  # sliders changed: current payload is d2, d1 still shown
        assert ai_tab.records_for_render("x", shown, "p2", ["r2"]) == ["r1"]
        unknown = types.SimpleNamespace(digest="d9")  # nothing stored: current rows
        assert ai_tab.records_for_render("x", unknown, "p9", ["r9"]) == ["r9"]
        for i in range(10):
            peeked["digest"] = f"e{i}"
            ai_tab.records_for_render("x", types.SimpleNamespace(digest=f"e{i}"),
                                      "p", [i], keep=3)
        assert list(fake.session_state["x_ai_records_store"]) == ["e7", "e8", "e9"]


class TestPublishAnalysisToChat:
    """What the app chat reads about a tab, for each state of its analysis."""

    @pytest.fixture
    def tab(self, monkeypatch):
        from core import ai_tab, app_chat
        state = {"selected_page": "🔍 Search Query Performance"}
        monkeypatch.setattr(app_chat, "st", types.SimpleNamespace(session_state=state))
        builds = []

        def _build(slug, payload):
            builds.append(payload)
            return types.SimpleNamespace(call={"context": [{"title": "Señales", "content": f"filas de {payload}"}]})
        monkeypatch.setattr(ai_tab.agent_call, "build_agent_call", _build)
        return ai_tab, state, builds

    @staticmethod
    def _analysis(state="done", digest="d1"):
        return types.SimpleNamespace(digest=digest, result={"marker": "M"}, running=state == "running",
                                     failed=state == "failed", done=state == "done")

    @staticmethod
    def _publish(ai_tab, analysis, payload="p1"):
        ai_tab.publish_analysis_to_chat("sqp", analysis, payload, module_label="SQP", subject="marca luna",
                                        reading=lambda a: f"lectura {a.result['marker']} de {a.digest}",
                                        annotate=str.upper, country_code="US")

    def test_a_current_analysis_shares_its_documents_and_the_reading(self, tab, monkeypatch):
        ai_tab, state, builds = tab
        shown = self._analysis()
        monkeypatch.setattr(ai_tab.ai_runtime, "peek", lambda slug, payload: shown)

        self._publish(ai_tab, shown)

        entry = state["app_chat_modules"]["sqp"]
        assert (entry.state, entry.page) == ("current", "🔍 Search Query Performance")
        assert [doc["title"] for doc in entry.analysis.documents] == [
            "SQP · marca luna · Señales", "SQP · marca luna · Lectura de la IA"]
        assert entry.analysis.documents[1]["content"] == "lectura M de d1"
        assert (entry.analysis.key, entry.analysis.country_code, entry.analysis.annotate("q01")) == (
            "sqp:d1", "US", "Q01")

    def test_the_documents_are_built_once_per_analysis(self, tab, monkeypatch):
        ai_tab, _, builds = tab
        shown = self._analysis()
        monkeypatch.setattr(ai_tab.ai_runtime, "peek", lambda slug, payload: shown)

        self._publish(ai_tab, shown)
        self._publish(ai_tab, shown)

        assert builds == ["p1"]

    def test_a_stale_analysis_stays_readable_but_flagged_and_comes_back_when_the_parameters_do(
            self, tab, monkeypatch):
        ai_tab, state, builds = tab
        shown = self._analysis()
        current = {"analysis": shown}
        monkeypatch.setattr(ai_tab.ai_runtime, "peek", lambda slug, payload: current["analysis"])
        self._publish(ai_tab, shown)

        current["analysis"] = None  # a slider moved: the current payload has no analysis yet
        self._publish(ai_tab, shown, payload="p2")
        assert state["app_chat_modules"]["sqp"].state == "outdated"
        assert state["app_chat_modules"]["sqp"].analysis.key == "sqp:d1"

        current["analysis"] = shown
        self._publish(ai_tab, shown)
        assert state["app_chat_modules"]["sqp"].state == "current"
        assert builds == ["p1"]

    def test_a_stale_analysis_never_shared_is_not_rebuilt_from_the_current_payload(self, tab, monkeypatch):
        ai_tab, state, builds = tab
        monkeypatch.setattr(ai_tab.ai_runtime, "peek", lambda slug, payload: None)

        self._publish(ai_tab, self._analysis(digest="old"), payload="new")

        assert "sqp" not in state["app_chat_modules"]
        assert builds == []

    @pytest.mark.parametrize("analysis_state", ["running", "failed"])
    def test_an_analysis_without_result_shares_only_its_state(self, tab, analysis_state):
        ai_tab, state, builds = tab

        self._publish(ai_tab, self._analysis(analysis_state))

        entry = state["app_chat_modules"]["sqp"]
        assert (entry.state, entry.analysis, builds) == (analysis_state, None, [])

    def test_no_analysis_withdraws_what_the_tab_had_shared(self, tab, monkeypatch):
        ai_tab, state, _ = tab
        shown = self._analysis()
        monkeypatch.setattr(ai_tab.ai_runtime, "peek", lambda slug, payload: shown)
        self._publish(ai_tab, shown)

        self._publish(ai_tab, None)

        assert "sqp" not in state["app_chat_modules"]


def test_floating_chat_shows_each_answer_as_annotated_when_it_arrived():
    """The bubbles print the annotation stored with the answer, never a new one;
    the history keeps the raw text and user bubbles are untouched."""
    from streamlit.testing.v1 import AppTest

    script = '''
import streamlit as st
from core.ai_chat import ChatTurn, floating_chat

st.session_state["aichat_t_hist"] = [
    {"role": "user", "text": "que es H59"},
    {"role": "assistant", "text": "Frenar H59 esta semana",
     "shown": "Frenar H59 (press on nails) esta semana"}]
floating_chat(chat_id="t", agent="str", title="T", session_key=lambda: "k", turn=lambda: ChatTurn(
    annotate=lambda text: text.replace("H59", "H59 (otro cliente)")))
st.markdown("RAW:" + st.session_state["aichat_t_hist"][1]["text"])
'''
    at = AppTest.from_string(script)
    at.run(timeout=30)
    assert not at.exception
    html = " ".join(str(m.value) for m in at.markdown)
    assert "Frenar H59 (press on nails) esta semana" in html
    assert "otro cliente" not in html and "que es H59 (" not in html
    assert "RAW:Frenar H59 esta semana" in html
