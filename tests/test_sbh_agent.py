"""The SBH Recommendation agent: what travels to the model, the cluster row ids, and how its answer reads in the chat."""
import pandas as pd

from ai.agent_call import build_agent_call
from ai.agents.sbh import chat_document
from ai.agents.sbh.context import KEYWORDS_PER_CLUSTER, MAX_CLUSTERS, MAX_KEYWORDS, build_context
from core.sbh.analysis import ANALYSIS_MODULE, build_analysis_input, sbh_row_labels
from core.sbh.targets import QueryShare, SpKeywordCoverage, recommend_targets

KNOWN = SpKeywordCoverage(frozenset({"vitamin c serum"}), account_label="Luna Kids · US", profile_id="111",
                          country_code="US")
UNKNOWN = SpKeywordCoverage()


def _mkl(rows) -> pd.DataFrame:
    return pd.DataFrame([{"Search Term": term, "SV": sv, "Relevance": 3.4, "Sugg. Bid": 1.2, "Launch Score": score}
                         for term, sv, score in rows])


MKL = _mkl([("vitamin a cream", 3000, 12.0), ("vitamin c serum", 1500, float("nan")),
            ("night vitamin oil", 700, 4.0), ("baby lotion", 400, 2.0)])
SHARES = {"vitamin a cream": QueryShare(2.0, 1.0, 90000, 300), "baby lotion": QueryShare(30.0, 25.0, 800, 12)}


def _input(mkl=MKL, coverage=KNOWN, lang="es"):
    targets = recommend_targets(mkl, SHARES, coverage.keyword_texts)
    return build_analysis_input(targets, coverage, brand="luna", mkl_keywords=len(mkl), sqp_queries=len(SHARES),
                                lang=lang)


def test_row_ids_name_the_clusters_most_search_volume_first():
    built = _input()
    _, docs, _ = build_context(built.data)

    assert sbh_row_labels(built.records) == {"G01": "vitamin", "G02": "other"}
    assert [doc["title"] for doc in docs] == ["Parámetros", "Clusters (2 filas)", "Keywords (4 filas)"]
    assert docs[1]["content"].splitlines()[1] == (
        "G01,vitamin,Vitamin Cream Serum Night,3,5200,1,2,0,1,1,1.2,vitamin a cream | vitamin c serum | "
        "night vitamin oil")


def test_the_parameters_name_the_brand_the_account_and_the_whole_mkl_figures():
    params = build_context(_input().data)[1][0]["content"]

    assert "Marca del SQP: luna" in params
    assert "Cuenta de Amazon Ads de la columna en_sp: Luna Kids · US" in params
    assert "- Targets de prioridad ALTA: 1" in params
    assert "- Targets que ya corren en SP: 1" in params
    assert "Viajaron todos los clusters: 2." in params
    assert "Viajaron todas las keywords: 4." in params


def test_without_an_account_the_in_sp_column_travels_as_unknown():
    built = _input(coverage=UNKNOWN)
    _, docs, _ = build_context(built.data)

    assert "Cuenta de Amazon Ads de la columna en_sp: ninguna, así que en_sp está sin dato" in docs[0]["content"]
    assert "Targets que ya corren en SP" not in docs[0]["content"]
    assert built.records[0]["en_sp"] is None
    assert docs[1]["content"].splitlines()[1].split(",")[8] == ""
    assert {line.split(",")[6] for line in docs[2]["content"].splitlines()[1:]} == {"sin dato"}


def test_each_keyword_travels_with_its_answers_in_words_and_a_missing_launch_score_empty():
    keywords = _input().data.keywords

    assert keywords[0] == {"keyword": "vitamin a cream", "cluster": "vitamin", "sv": 3000, "relevance": 3.4,
                           "is_pct": 2, "ps_pct": 1, "en_sp": "no", "mercado_compra": "sí", "prioridad": "ALTA",
                           "launch_score": 12}
    assert keywords[1]["en_sp"] == "sí" and keywords[1]["launch_score"] is None


def test_a_cluster_carries_its_top_keywords_by_search_volume():
    mkl = _mkl([(f"vitamin cream {index}", 400 + index, 1.0) for index in range(KEYWORDS_PER_CLUSTER + 3)])

    cluster = _input(mkl).records[0]

    assert cluster["keywords"] == KEYWORDS_PER_CLUSTER + 3
    assert cluster["top_keywords"].split(" | ")[0] == f"vitamin cream {KEYWORDS_PER_CLUSTER + 2}"
    assert len(cluster["top_keywords"].split(" | ")) == KEYWORDS_PER_CLUSTER


def test_more_clusters_and_keywords_than_travel_say_how_many_were_left_out():
    roots = ["".join(chr(ord("a") + int(digit)) for digit in f"{index:03d}") for index in range(MAX_CLUSTERS + 5)]
    # One-letter suffixes are not root words: each keyword clusters by its own root only.
    rows = [(f"{root} {suffix}", 500, 1.0) for root in roots for suffix in "qzkvw"]

    built = _input(_mkl(rows))
    params = build_context(built.data)[1][0]["content"]

    assert len(built.records) == MAX_CLUSTERS
    assert f"De {len(roots)} clusters viajaron {MAX_CLUSTERS}; los {len(roots) - MAX_CLUSTERS} restantes" in params
    assert f"De {len(rows)} keywords viajaron {MAX_KEYWORDS}; las {len(rows) - MAX_KEYWORDS} restantes" in params


def test_nothing_to_judge_builds_no_payload():
    built = _input(_mkl([("tiny", 10, 1.0)]))

    assert built.data is None and built.records == []


def test_the_same_data_digests_the_same_and_another_coverage_or_language_does_not():
    first = build_agent_call(ANALYSIS_MODULE, _input().data)

    assert first.input_digest == build_agent_call(ANALYSIS_MODULE, _input().data).input_digest
    assert first.input_digest != build_agent_call(ANALYSIS_MODULE, _input(coverage=UNKNOWN).data).input_digest
    assert first.input_digest != build_agent_call(ANALYSIS_MODULE, _input(lang="en").data).input_digest
    assert first.model == "claude-opus-5-5"


def test_the_chat_reading_names_the_cluster_its_headline_and_its_warning():
    result = {"synthesis": {"situation": "La marca casi no aparece en vitamin.", "week_actions": ["Lanzar G01"],
                            "mid_term": [], "risks": [], "executive_summary": "1 cluster para lanzar."},
              "clusters": [{"row_id": "G01", "razon": "3.000 búsquedas con 2% de share.", "veredicto": "LANZAR",
                            "confianza": "alta", "headline": "Vitamin A cream for night skin",
                            "advertencia": "vitamin c serum ya corre en SP."},
                           {"row_id": "G99", "razon": "no existe", "veredicto": "PROBAR", "confianza": "baja",
                            "headline": None, "advertencia": None}]}

    text = chat_document.reading_text(result, _input().records)

    assert ("G01 · vitamin → LANZAR · alta: 3.000 búsquedas con 2% de share. · headline propuesto: "
            "«Vitamin A cream for night skin» · advertencia: vitamin c serum ya corre en SP.") in text
    assert "G99" not in text
