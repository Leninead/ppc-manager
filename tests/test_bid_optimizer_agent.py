"""The Bid Optimizer agent: what travels to the model, and how its answer reads in the chat."""
import pandas as pd
import pytest

from ai import agent_call
from ai.agents.bid_optimizer import chat_document
from ai.agents.bid_optimizer.context import MAX_ASINS, BidData, build_context


def _record(asin="B0TEST00001", **overrides):
    record = {"asin": asin, "clicks": 120, "orders": 14, "cvr": 11.67, "price": 19.99,
              "spend": 84.5, "sales": 279.86, "acos": 30.2, "bid_base": 0.58, "estado": "OK"}
    record.update(overrides)
    return record


def _data(**overrides):
    payload = {"account_label": "Dermaglos US", "period_label": "1 – 14 sep 2026",
               "currency_code": "USD", "target_acos": 25, "price_source": "STR (precio promedio)",
               "asin_source": "extraído del nombre de la campaña", "total_asins": 2,
               "asins": [_record(), _record("B0TEST00002", orders=0, cvr=0.0, bid_base=0.0,
                                            estado="SIN DATA")],
               "campaigns": [{"Campaign": "DG - B0TEST00001 - SP - KW - EXACT", "Tipo Detectado":
                              "Exact Ranking", "ToS %": 50, "PDP %": 0, "Spend": 84.5,
                              "Sales": 279.86, "ACoS %": 30.2, "Orders": 14}]}
    payload.update(overrides)
    return BidData(**payload)


def test_the_documents_carry_the_parameters_the_asins_and_the_campaigns():
    _, docs, schema = build_context(_data())

    titles = [doc["title"] for doc in docs]
    assert titles[0] == "Parámetros"
    assert "Bids sugeridos por ASIN" in titles[1]
    assert "Placements sugeridos por campaña" in titles[2]
    assert schema["required"] == ["bids", "synthesis"]


def test_every_asin_row_gets_a_correlative_row_id():
    _, docs, _ = build_context(_data())

    rows = pd.read_csv(pd.io.common.StringIO(docs[1]["content"]))
    assert list(rows["row_id"]) == ["A01", "A02"]
    assert list(rows["asin"]) == ["B0TEST00001", "B0TEST00002"]


def test_the_parameters_state_the_target_the_currency_and_where_the_asin_came_from():
    _, docs, _ = build_context(_data())

    params = docs[0]["content"]
    assert "Target ACoS del tab: 25%" in params
    assert "Moneda: USD" in params
    assert "extraído del nombre de la campaña" in params


def test_without_campaigns_the_third_document_is_not_sent():
    _, docs, _ = build_context(_data(campaigns=[]))

    assert len(docs) == 2


def test_a_truncated_list_tells_the_agent_the_rows_left_out_do_not_exist():
    many = [_record(f"B0TEST{index:05d}") for index in range(MAX_ASINS + 5)]

    _, docs, _ = build_context(_data(asins=many, total_asins=len(many)))

    assert f"Quedaron 5 filas fuera del documento" in docs[0]["content"]
    rows = pd.read_csv(pd.io.common.StringIO(docs[1]["content"]))
    assert len(rows) == MAX_ASINS


def test_a_complete_list_says_so_instead_of_reporting_a_truncation():
    _, docs, _ = build_context(_data())

    assert "Sin truncamiento" in docs[0]["content"]


def test_the_agent_call_resolves_the_prompt_and_both_fingerprints():
    call = agent_call.build_agent_call("bid_optimizer", _data())

    assert call.model == "claude-opus-5"
    assert "analista senior de Amazon PPC" in call.call["system"]
    assert call.input_digest and call.agent_version


def test_the_same_payload_digests_the_same_and_a_changed_target_does_not():
    first = agent_call.build_agent_call("bid_optimizer", _data())
    same = agent_call.build_agent_call("bid_optimizer", _data())
    other = agent_call.build_agent_call("bid_optimizer", _data(target_acos=40))

    assert first.input_digest == same.input_digest
    assert first.input_digest != other.input_digest


@pytest.fixture
def result():
    return {
        "bids": [{"row_id": "A01", "razon": "CVR 11.7% sostiene el bid.", "veredicto": "SUBIR",
                  "confianza": "alta", "advertencia": None},
                 {"row_id": "A02", "razon": "Sin clicks no hay señal.", "veredicto": "MANTENER",
                  "confianza": "baja", "advertencia": "Revisar antes de tocar el bid."}],
        "synthesis": {"situation": "La cuenta corre a 30% de ACoS.", "week_actions": ["Subir A01"],
                      "mid_term": [], "risks": [], "executive_summary": "ACoS 30.2%."},
    }


def test_the_chat_reading_names_the_asin_behind_every_row_id(result):
    text = chat_document.reading_text(result, _data().asins)

    assert "A01 · B0TEST00001" in text
    assert "SUBIR · alta" in text
    assert "advertencia: Revisar antes de tocar el bid." in text
    assert "Resumen ejecutivo: ACoS 30.2%." in text


def test_the_chat_reading_drops_row_ids_the_documents_never_carried(result):
    result["bids"].append({"row_id": "A99", "razon": "inventada", "veredicto": "PAUSAR",
                           "confianza": "alta", "advertencia": None})

    text = chat_document.reading_text(result, _data().asins)

    assert "A99" not in text
