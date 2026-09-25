"""The SBH Recommendation agent's payload, built from the targets the module already computed, without Streamlit."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids
from ai.agents.sbh.chat_document import row_item
from ai.agents.sbh.context import KEYWORDS_PER_CLUSTER, ROW_PREFIX, SbhData, records_of
from core.sbh.targets import (
    COL_CLUSTER,
    COL_IMPRESSION_SHARE,
    COL_IN_SP,
    COL_KEYWORD,
    COL_LAUNCH_SCORE,
    COL_MARKET_BUYING,
    COL_PRIORITY,
    COL_PURCHASE_SHARE,
    COL_RELEVANCE,
    COL_SV,
    NO,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_MEDIUM,
    UNKNOWN,
    YES,
    SbhTargets,
    SpKeywordCoverage,
)

ANALYSIS_MODULE = "sbh"
_PRIORITY_NAMES = {PRIORITY_HIGH: "ALTA", PRIORITY_MEDIUM: "MEDIA", PRIORITY_LOW: "BAJA"}
_ANSWERS = {YES: "sí", NO: "no", UNKNOWN: "sin dato"}


@dataclass(frozen=True)
class SbhAnalysisInput:
    """The agent payload plus the clusters its row_ids point to; `data` is None when there is nothing to judge."""

    data: SbhData | None
    records: list


def build_analysis_input(targets: SbhTargets, coverage: SpKeywordCoverage, *, brand: str, mkl_keywords: int,
                         sqp_queries: int, lang: str) -> SbhAnalysisInput:
    keywords = targets.keywords
    if keywords.empty:
        return SbhAnalysisInput(None, [])
    priorities = keywords[COL_PRIORITY]
    counts = {
        "Keywords del MKL": mkl_keywords,
        "Queries del SQP": sqp_queries,
        "Targets recomendados, con 300 búsquedas o más": len(keywords),
        "Targets de prioridad ALTA": int((priorities == PRIORITY_HIGH).sum()),
        "Targets de prioridad MEDIA": int((priorities == PRIORITY_MEDIUM).sum()),
        "Targets de prioridad BAJA": int((priorities == PRIORITY_LOW).sum()),
        "Clusters": len(targets.clusters),
        **({"Targets que ya corren en SP": int((keywords[COL_IN_SP] == YES).sum())} if coverage.known else {}),
    }
    data = SbhData(
        brand=brand,
        sp_account=coverage.account_label if coverage.known else "",
        counts=counts,
        clusters=[_cluster_record(cluster, keywords, coverage.known) for _, cluster in targets.clusters.iterrows()],
        keywords=[_keyword_record(keyword) for _, keyword in keywords.iterrows()],
        idioma=lang,
    )
    return SbhAnalysisInput(data, records_of(data))


def sbh_row_labels(records: list) -> dict[str, str]:
    """row_id -> the cluster behind it, to annotate the ids the synthesis and the chat cite (G03)."""
    return {row_id: row_item(record) for row_id, record in zip(make_ids(ROW_PREFIX, len(records)), records)}


def _cluster_record(cluster: pd.Series, keywords: pd.DataFrame, coverage_known: bool) -> dict:
    members = keywords[keywords[COL_CLUSTER] == cluster["Cluster"]]
    priorities = members[COL_PRIORITY]
    top = members.nlargest(KEYWORDS_PER_CLUSTER, COL_SV)
    return {
        "cluster": cluster["Cluster"],
        "headline_modulo": cluster["Headline"],
        "keywords": int(cluster["KWs"]),
        "sv_total": int(cluster["SV_Total"]),
        "alta": int((priorities == PRIORITY_HIGH).sum()),
        "media": int((priorities == PRIORITY_MEDIUM).sum()),
        "baja": int((priorities == PRIORITY_LOW).sum()),
        "en_sp": int((members[COL_IN_SP] == YES).sum()) if coverage_known else None,
        "mercado_compra": int((members[COL_MARKET_BUYING] == YES).sum()),
        "is_ponderado": _search_weighted(members[COL_IMPRESSION_SHARE], members[COL_SV]),
        "top_keywords": " | ".join(top[COL_KEYWORD]),
    }


def _keyword_record(keyword: pd.Series) -> dict:
    return {
        "keyword": keyword[COL_KEYWORD],
        "cluster": keyword[COL_CLUSTER],
        "sv": int(keyword[COL_SV]),
        "relevance": _plain(keyword[COL_RELEVANCE]),
        "is_pct": _plain(keyword[COL_IMPRESSION_SHARE]),
        "ps_pct": _plain(keyword[COL_PURCHASE_SHARE]),
        "en_sp": _ANSWERS[keyword[COL_IN_SP]],
        "mercado_compra": _ANSWERS[keyword[COL_MARKET_BUYING]],
        "prioridad": _PRIORITY_NAMES[keyword[COL_PRIORITY]],
        "launch_score": _plain(keyword[COL_LAUNCH_SCORE]),
    }


def _search_weighted(shares: pd.Series, search_volume: pd.Series):
    """The cluster's share weighted by each keyword's searches: a big keyword weighs more than a tiny one."""
    volume = pd.to_numeric(search_volume, errors="coerce").fillna(0)
    total = volume.sum()
    if total <= 0:
        return None
    return _plain(round(float((pd.to_numeric(shares, errors="coerce").fillna(0) * volume).sum() / total), 1))


def _plain(value):
    """JSON-safe: numpy numbers become Python ones, and a missing value is None, never NaN."""
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return value
    if math.isnan(number):
        return None
    return int(number) if number.is_integer() else round(number, 2)
