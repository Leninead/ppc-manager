"""The PPC Audit Pro agent's payload, built from what the module computed, and its answer as the chat reads it."""
import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.ppc_audit.chat_document import reading_text, row_item
from ai.agents.ppc_audit.context import MAX_GRADUATION, build_context
from core.ppc_audit.analysis import ANALYSIS_MODULE, audit_row_labels, build_analysis_input
from core.ppc_audit.checks import run_audit
from core.ppc_audit.frames import SB_SEARCH_TERMS, AuditFrames
from core.search_term.frame import SOURCE_API
from modules.pages.ppc_audit import audit_ai_rows
from tests.test_ppc_audit_checks import PARTS, _campaign, _keyword

ANSWER = {"synthesis": {"situation": "La cuenta tiene keywords que no reciben tráfico.",
                        "week_actions": ["Subir el bid de U05"], "mid_term": [], "risks": [],
                        "executive_summary": "1 keyword para subir el bid."},
          "hallazgos": [{"row_id": "U05", "razon": "Vendió 30 y hoy tiene 0 impresiones.", "veredicto": "ACTUAR",
                         "confianza": "alta", "advertencia": None},
                        {"row_id": "U01", "razon": "Mezcla Exact y Phrase.", "veredicto": "INVESTIGAR",
                         "confianza": "media", "advertencia": "Revisar si es a propósito."},
                        {"row_id": "U99", "razon": "no existe", "veredicto": "ESPERAR", "confianza": "baja",
                         "advertencia": None}]}


def _frames(unavailable=None, **parts) -> AuditFrames:
    frames = {part: pd.DataFrame() for part in PARTS}
    frames.update({part: pd.DataFrame(rows) for part, rows in parts.items()})
    return AuditFrames(**frames, source=SOURCE_API, currency_code="USD", unavailable=dict(unavailable or {}))


def _account(**extra) -> AuditFrames:
    return _frames(
        sp_campaigns=[_campaign("1", "Luna Exact", spend=90, sales=300, clicks=60, impressions=2000, orders=6),
                      _campaign("2", "Luna Broad", spend=40, sales=0, clicks=20, impressions=900)],
        sp_keywords=[_keyword("1", "luna pajamas", "Exact", spend=50, sales=300, orders=6, impressions=1500),
                     _keyword("1", "luna sleep", "Phrase", spend=40, impressions=500),
                     _keyword("2", "luna pajamas", "Exact", spend=40, impressions=900),
                     _keyword("2", "paused quiet", "Exact", state="paused", impressions=0),
                     _keyword("1", "sold quiet", "Exact", sales=30, orders=1, impressions=0),
                     _keyword("1", "never quiet", "Exact", impressions=0)],
        sp_search_terms=[{"Customer Search Term": "cheap pajamas", "Spend": 12, "Sales": 0, "Clicks": 6,
                          "Impressions": 300}],
        **extra,
    )


def _input(frames: AuditFrames, brand_terms=("luna",), lang="es"):
    result = run_audit(frames, brand_terms=brand_terms)
    return build_analysis_input(frames, result, account_label="Luna Kids · US", period_label="9–22 sep 2026",
                                currency_code="USD", attribution_days=7, brand_terms=brand_terms, lang=lang)


def test_nothing_to_judge_gives_no_payload():
    frames = _frames(sp_campaigns=[_campaign("1", "Quiet account")])

    analysis = _input(frames)

    assert analysis.data is None and analysis.records == []


def test_the_rows_travel_in_one_numbering_group_after_group():
    analysis = _input(_account(), brand_terms=())

    groups = [record["grupo"] for record in analysis.records]
    assert groups == ["match_mixto", "campana", "campana", "duplicado", "graduacion", "graduacion",
                      "termino_sin_venta"]
    labels = audit_row_labels(analysis.records)
    assert labels == {"U01": "Luna Exact", "U02": "Luna Exact", "U03": "Luna Broad", "U04": "luna pajamas",
                      "U05": "sold quiet", "U06": "never quiet", "U07": "cheap pajamas"}
    graduation = [record for record in analysis.records if record["grupo"] == "graduacion"]
    assert [record["recomendacion"] for record in graduation] == ["SUBIR BID", "GRADUAR A SKAG"]
    assert graduation[0]["impresiones_campana"] == 2000


def test_the_documents_carry_the_parameters_and_one_table_per_group():
    frames = _account(sb_campaigns=[_campaign("5", "SB brand", spend=10)])
    frames.unavailable[SB_SEARCH_TERMS] = "Los search terms de Sponsored Brands todavía no se sincronizaron."
    input_text, docs, schema = build_context(_input(frames).data)

    titles = [document["title"] for document in docs]
    assert titles[0] == "Parámetros" and titles[1].startswith("Performance por segmento")
    assert "Target Graduation: keywords sin impresiones en campañas con tráfico (2 filas)" in titles
    parameters = docs[0]["content"]
    assert "Fuente: Amazon Ads" in parameters and "Brand terms: luna" in parameters
    assert "- Gasto de SP: 130" in parameters and "- Campañas con match types mixtos: 1" in parameters
    assert "Lo que la fuente no tiene:\n- Los search terms de Sponsored Brands todavía no se sincronizaron." in parameters
    assert "- Gasto sin ventas en search terms de SB: sin dato" in parameters
    graduation = next(document for document in docs if document["title"].startswith("Target Graduation"))
    assert graduation["content"].splitlines()[0].startswith("row_id,keyword,match_type,campana")
    segments = docs[1]["content"]
    assert segments.startswith("producto,segmento,targets") and "row_id" not in segments
    assert all("\r" not in document["content"] for document in docs)
    assert schema["required"] == ["hallazgos", "synthesis"] and "Citá row_ids exactos" in input_text


def test_a_long_group_says_how_many_rows_stayed_out():
    quiet = [_keyword("1", f"quiet {index}", impressions=0) for index in range(MAX_GRADUATION + 5)]
    frames = _frames(sp_campaigns=[_campaign("1", "Big", spend=10)],
                     sp_keywords=[_keyword("1", "busy", impressions=100)] + quiet)

    analysis = _input(frames, brand_terms=())
    parameters = build_context(analysis.data)[1][0]["content"]

    assert sum(record["grupo"] == "graduacion" for record in analysis.records) == MAX_GRADUATION
    assert (f"Target Graduation: keywords sin impresiones en campañas con tráfico: de {MAX_GRADUATION + 5} "
            f"viajaron {MAX_GRADUATION}") in parameters


def test_the_same_data_fingerprints_the_same_and_new_brand_terms_do_not():
    first = build_agent_call(ANALYSIS_MODULE, _input(_account()).data)
    again = build_agent_call(ANALYSIS_MODULE, _input(_account()).data)
    other = build_agent_call(ANALYSIS_MODULE, _input(_account(), brand_terms=("sleep",)).data)

    assert first.input_digest == again.input_digest
    assert first.input_digest != other.input_digest


def test_the_chat_reads_each_verdict_with_the_item_behind_its_row_id():
    records = _input(_account(), brand_terms=()).records

    text = reading_text(ANSWER, records)

    assert "La cuenta tiene keywords que no reciben tráfico." in text
    assert "U05 · graduacion · sold quiet → ACTUAR · alta: Vendió 30 y hoy tiene 0 impresiones." in text
    assert "U01 · match_mixto · Luna Exact → INVESTIGAR · media" in text and "advertencia: Revisar" in text
    assert "U99" not in text


def test_the_item_of_a_row_is_its_keyword_its_term_or_its_campaign():
    assert row_item({"keyword": "luna", "campana": "C"}) == "luna"
    assert row_item({"termino": " cheap "}) == "cheap"
    assert row_item({"campana": "Luna Exact"}) == "Luna Exact"


def test_the_ai_rows_show_the_group_the_figures_and_the_verdict():
    records = _input(_account(), brand_terms=()).records

    rows = audit_ai_rows(ANSWER["hallazgos"], records, "USD")

    assert [row["row_id"] for row in rows] == ["U05", "U01"]
    assert rows[0]["item"] == "sold quiet" and rows[0]["type_tag"] == "Target Graduation"
    assert rows[0]["metrics"] == ["gasto $0.00", "ventas $30.00", "2,000 impresiones de su campaña", "SUBIR BID"]
    assert rows[1]["metrics"] == ["Exact | Phrase", "4 keywords"] and rows[1]["badges"] == ["INVESTIGAR"]
