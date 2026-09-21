"""The PPC Insights agent: what it reads, how its rows are named and the text the chat gets."""
import pandas as pd

from ai import agent_call
from ai.agents.ppc_insights import chat_document
from ai.agents.ppc_insights.context import MAX_ASINS, build_context
from core.ppc_insights.analysis import (
    ANALYSIS_MODULE,
    InsightsAnalysisParams,
    build_analysis_input,
    canonical_analysis_window,
    insights_row_labels,
)
from core.ppc_insights.asin_health import MAX_POINTS, NEUTRAL_POINTS
from core.search_term.frame import console_columns

ATTRIBUTION_DAYS = 7


def _frame(rows):
    frame = pd.DataFrame(rows)
    for column in console_columns(ATTRIBUTION_DAYS):
        if column not in frame.columns:
            frame[column] = 0
    return frame[console_columns(ATTRIBUTION_DAYS) + ["_ad_group_id"]]


def _row(ad_group, spend=10.0, sales=40.0, orders=2, clicks=20, term="vitamin a cream"):
    return {"Customer Search Term": term, "Campaign Name": "DG - SP - KW", "_ad_group_id": ad_group, "Spend": spend,
            "7 Day Total Sales": sales, "7 Day Total Orders (#)": orders, "Clicks": clicks, "Impressions": 500}


def _input(frame=None, mapping=None, params=None, **files):
    return build_analysis_input(
        frame if frame is not None else _frame([_row("AG1", spend=50.0), _row("AG2", spend=80.0)]),
        params=params or InsightsAnalysisParams(25, 15.0), account_label="dermaglos · US",
        period_label="10 – 16 sep 2026", currency_code="USD",
        ad_group_asins=mapping or {"AG1": frozenset({"B0CYLMJJJC"}), "AG2": frozenset({"B0CYLM4L23"})}, **files)


def test_the_rows_go_by_spend_and_the_row_ids_name_their_asin():
    records = _input().records

    assert [record["asin"] for record in records] == ["B0CYLM4L23", "B0CYLMJJJC"]
    assert insights_row_labels(records) == {"P01": "B0CYLM4L23", "P02": "B0CYLMJJJC"}


def test_the_same_data_and_parameters_give_the_same_digest_and_new_parameters_another():
    digest = agent_call.build_agent_call(ANALYSIS_MODULE, _input().data).input_digest

    assert agent_call.build_agent_call(ANALYSIS_MODULE, _input().data).input_digest == digest
    assert agent_call.build_agent_call(
        ANALYSIS_MODULE, _input(params=InsightsAnalysisParams(30, 15.0)).data).input_digest != digest
    assert agent_call.build_agent_call(
        ANALYSIS_MODULE, _input(params=InsightsAnalysisParams(25, None)).data).input_digest != digest


def test_without_the_optional_files_the_parameters_say_which_parts_are_neutral():
    _, docs, _ = build_context(_input().data)
    parameters = docs[0]["content"]

    assert "SIN DATO: BuyBox, Funnel, Impression Share" in parameters
    assert "SQP no; Business Report no; Campaign CSV no" in parameters
    assert f"CVR {MAX_POINTS['cvr']} · {NEUTRAL_POINTS['cvr']:g}" in parameters
    assert "Precio promedio del producto: 15.00" in parameters


def test_the_rows_carry_the_score_parts_and_the_document_has_unix_line_endings():
    _, docs, _ = build_context(_input().data)
    table = docs[1]["content"]

    header = table.splitlines()[0].split(",")
    assert header[:8] == ["row_id", "asin", "health_score", "pts_cvr", "pts_buybox", "pts_acos", "pts_funnel",
                          "pts_imp_share"]
    assert "\r" not in table
    assert "sessions" not in header and "campanas" not in header


def test_the_optional_files_add_their_columns_and_leave_the_neutral_list():
    br = pd.DataFrame({"(Child) ASIN": ["B0CYLMJJJC"], "Sessions - Total": ["1,000"],
                       "Featured Offer (Buy Box) Percentage": ["90%"], "Units Ordered": ["50"]})
    camp = pd.DataFrame({"Campaign Name": ["DG - B0CYLMJJJC - SP - AUTO"], "State": ["enabled"]})

    analysis_input = _input(br_df=br, camp_df=camp)
    _, docs, _ = build_context(analysis_input.data)
    hero = next(record for record in analysis_input.records if record["asin"] == "B0CYLMJJJC")

    assert (hero["sessions"], hero["buybox"], hero["cvr_br"]) == (1000.0, 90.0, 5.0)
    assert hero["campanas"] == 1 and hero["funnel"] == "parcial"
    assert "SIN DATO: Impression Share valen" in docs[0]["content"]


def test_the_share_of_spend_without_an_asin_reaches_the_parameters():
    frame = _frame([_row("AG1", spend=60.0), _row("AG3", spend=40.0)])

    _, docs, _ = build_context(_input(frame=frame).data)

    assert "producto anunciado del ad group 60.0% · sin ASIN 40.0%" in docs[0]["content"]


def test_a_row_taken_from_the_campaign_name_tells_the_agent_how_many_asins_it_groups():
    family_row = {**_row("AG2", spend=90.0), "Campaign Name": "DG - B0FAMILY01 - SP - KW"}
    frame = _frame([_row("AG1", spend=50.0), family_row])
    mapping = {"AG1": frozenset({"B0CYLMJJJC"}), "AG2": frozenset({"B0CHILD0001", "B0CHILD0002"})}

    analysis_input = _input(frame=frame, mapping=mapping)
    _, docs, _ = build_context(analysis_input.data)

    family = next(record for record in analysis_input.records if record["asin"] == "B0FAMILY01")
    hero = next(record for record in analysis_input.records if record["asin"] == "B0CYLMJJJC")
    assert family["asins_agrupados"] == 2 and "asins_agrupados" not in hero
    assert "asins_agrupados" in docs[1]["content"].splitlines()[0]
    assert "aunque ese ad group no lo anuncie" in docs[0]["content"]


def test_more_asins_than_the_cap_are_announced_as_left_out():
    rows = [_row(f"AG{i}", spend=float(100 + i)) for i in range(MAX_ASINS + 5)]
    mapping = {f"AG{i}": frozenset({f"B0TEST{i:04d}"}) for i in range(MAX_ASINS + 5)}

    analysis_input = _input(frame=_frame(rows), mapping=mapping)
    _, docs, _ = build_context(analysis_input.data)

    assert len(analysis_input.records) == MAX_ASINS
    assert "Quedaron 5 filas fuera del documento" in docs[0]["content"]


def test_an_empty_report_has_nothing_to_send():
    assert _input(frame=_frame([_row("AG1")]).iloc[0:0]).data is None


def test_the_chat_reads_each_opinion_with_the_asin_behind_its_row_id():
    records = _input().records
    result = {"synthesis": {"situation": "P01 gasta sin vender.", "week_actions": [], "mid_term": [], "risks": []},
              "asins": [{"row_id": "P01", "razon": "gastó 80 sin vender", "foco": "DESPERDICIO",
                         "confianza": "alta", "advertencia": None},
                        {"row_id": "P09", "razon": "no existe", "foco": "ACOS", "confianza": "baja",
                         "advertencia": None}]}

    text = chat_document.reading_text(result, records)

    assert "P01 · B0CYLM4L23" in text and "DESPERDICIO · alta: gastó 80 sin vender" in text
    assert "P09" not in text.split("prioridad")[1]


def test_the_canonical_window_is_the_seven_days_the_picker_opens_on():
    from datetime import date

    assert canonical_analysis_window(date(2026, 7, 11), date(2026, 9, 16)) == (date(2026, 9, 10), date(2026, 9, 16))
