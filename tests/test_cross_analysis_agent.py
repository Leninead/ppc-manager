"""The Análisis Cruzado agent: what travels to the model, the query row ids, and how its answer reads in the chat."""
from ai.agent_call import build_agent_call
from ai.agents.cross_analysis import chat_document
from ai.agents.cross_analysis.context import MAX_QUERIES, build_context
from core.cross_analysis.action_plan import (
    QUERY,
    QUERY_TYPE,
    ActionPlanParams,
    build_action_plan,
    numeric_sqp,
    query_types,
    with_funnel_diagnosis,
)
from core.cross_analysis.analysis import ANALYSIS_MODULE, build_analysis_input, cross_row_labels, plan_counts
from core.cross_analysis.asin_summary import asin_summary
from core.cross_analysis.ranking_guards import with_ranking_guards
from core.search_term.frame import orders_column, sales_column
from tests.cross_analysis_data import search_terms, sqp, sqp_row, term_row

PARAMS = ActionPlanParams(target_acos=35.0, brand_terms=("luna",))
TERMS = [term_row("luna pajamas", keyword_type="EXACT", cost=4.0, sales=90.0, orders=3),
         term_row("sleep sack", campaign_id="3002", ad_group_id="4002", keyword_id="5002", cost=12.0, clicks=30,
                  portfolio="Ranking", portfolio_id="9"),
         term_row("cozy blanket", campaign_id="3003", ad_group_id="4003", keyword_id="7003", cost=10.0, sales=90.0,
                  orders=3, keyword_type="TARGETING_EXPRESSION_PREDEFINED", keyword_text="close-match")]
QUERIES = [sqp_row("baby swaddle", purchases=60, brand_purchases=4, brand_share=6.7),
           sqp_row("luna pajamas", purchases=20, brand_share=50.0),
           sqp_row("sleep sack", purchases=3, brand_purchases=0, brand_share=0.0),
           sqp_row("cozy blanket", purchases=5, brand_purchases=2, brand_share=40.0),
           sqp_row("quiet query", purchases=2, brand_purchases=0, brand_share=0.0)]


def _inputs(queries=QUERIES, exact=frozenset({"baby swaddle"}), lang="es", target=35.0):
    table = sqp(*queries)
    table[QUERY_TYPE] = query_types(table[QUERY], PARAMS.brand_terms)
    table = with_funnel_diagnosis(numeric_sqp(table))
    terms = with_ranking_guards(search_terms(*TERMS), exact)
    params = ActionPlanParams(target_acos=target, brand_terms=PARAMS.brand_terms)
    plan = build_action_plan(table, terms, exact, params, sales_column=sales_column(7), orders_column=orders_column(7))
    summary = asin_summary(terms, {"4001": frozenset({"B0CYLMJJJC"})}, {}, sales_column=sales_column(7),
                           orders_column=orders_column(7))
    built = build_analysis_input(plan, summary.rows, account="Luna Kids · US", period="1 – 27 sep 2026",
                                 currency="USD", brand="luna", exact_source="listado de hoy 09:12",
                                 asin_source="", parameters={"Target ACoS (%)": target},
                                 counts=plan_counts(plan, table, terms), lang=lang)
    return built, plan


def test_the_queries_travel_in_the_order_the_am_works_them():
    built, _ = _inputs()

    assert cross_row_labels(built.records) == {"X01": "cozy blanket", "X02": "baby swaddle", "X03": "luna pajamas",
                                              "X04": "sleep sack", "X05": "quiet query"}
    assert [record["accion"] for record in built.records] == ["ESCALAR", "AGREGAR", "DEFENDER", "BAJAR BID",
                                                              "MONITOREAR"]


def test_each_query_travels_with_its_marks_in_words_and_missing_figures_empty():
    built, _ = _inputs()
    by_query = {record["consulta"]: record for record in built.records}

    assert by_query["baby swaddle"]["en_str"] == "no" and by_query["baby swaddle"]["gasto"] is None
    assert by_query["baby swaddle"]["ya_en_exact"] == "sí"
    assert by_query["sleep sack"]["ranking_kw"] == "sí" and by_query["sleep sack"]["acos"] is None
    assert by_query["luna pajamas"]["no_negativizable"] == "sí" and by_query["luna pajamas"]["origen"] == "Exact"
    assert by_query["cozy blanket"]["origen"] == "Auto" and by_query["cozy blanket"]["no_negativizable"] == "no"
    assert by_query["cozy blanket"]["acos"] == 11.1


def test_without_a_listing_the_exact_mark_travels_as_unknown():
    built, _ = _inputs(exact=None)

    assert {record["ya_en_exact"] for record in built.records} == {"sin dato"}


def test_the_parameters_carry_the_account_the_sources_and_the_whole_plan_figures():
    built, _ = _inputs()
    _, docs, _ = build_context(built.data)
    params = docs[0]["content"]

    assert [doc["title"] for doc in docs] == ["Parámetros", "Plan de Acción (5 filas)", "ASINs (1 filas)"]
    assert "Cuenta de Amazon Ads de los search terms: Luna Kids · US" in params
    assert "Keywords Exact de la cuenta: listado de hoy 09:12" in params
    assert "- Queries del SQP, sin repetir: 5" in params
    assert "- Queries con acción AGREGAR: 1" in params
    assert "- Queries que ya existen como keyword Exact habilitada: 1" in params
    assert "Viajaron todas las queries del plan: 5." in params
    assert docs[1]["content"].splitlines()[0].startswith("row_id,consulta,accion,tipo,en_str")


def test_more_queries_than_travel_say_how_many_were_left_out():
    queries = [sqp_row(f"query {index:03d}", purchases=3, brand_purchases=0, brand_share=0.0)
               for index in range(MAX_QUERIES + 7)]

    built, _ = _inputs(queries=queries)
    params = build_context(built.data)[1][0]["content"]

    assert len(built.records) == MAX_QUERIES
    assert f"De {MAX_QUERIES + 7} queries del plan viajaron {MAX_QUERIES}; las 7 restantes" in params


def test_the_same_data_digests_the_same_and_another_parameter_or_language_does_not():
    first = build_agent_call(ANALYSIS_MODULE, _inputs()[0].data)

    assert first.input_digest == build_agent_call(ANALYSIS_MODULE, _inputs()[0].data).input_digest
    assert first.input_digest != build_agent_call(ANALYSIS_MODULE, _inputs(target=20.0)[0].data).input_digest
    assert first.input_digest != build_agent_call(ANALYSIS_MODULE, _inputs(lang="en")[0].data).input_digest
    assert first.model == "claude-opus-5-5"


def test_an_empty_plan_builds_no_payload():
    built = build_analysis_input(_inputs()[1].iloc[0:0], _inputs()[1].iloc[0:0], account="", period="", currency="",
                                 brand="", exact_source="", asin_source="", parameters={}, counts={}, lang="es")

    assert built.data is None and built.records == []


def test_the_chat_reading_names_the_query_the_modules_action_and_the_verdict():
    result = {"synthesis": {"situation": "La marca vende por queries que no captura.", "week_actions": ["Agregar X02"],
                            "mid_term": [], "risks": [], "executive_summary": "2 queries para actuar."},
              "consultas": [{"row_id": "X02", "razon": "60 compras del mercado.", "veredicto": "ESPERAR",
                             "confianza": "media", "advertencia": "Ya existe como Exact."},
                            {"row_id": "X99", "razon": "no existe", "veredicto": "ACTUAR", "confianza": "baja",
                             "advertencia": None}]}

    text = chat_document.reading_text(result, _inputs()[0].records)

    assert ("X02 · baby swaddle · AGREGAR → ESPERAR · media: 60 compras del mercado. · advertencia: Ya existe como "
            "Exact.") in text
    assert "X99" not in text
