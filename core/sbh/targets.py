"""Which MKL keywords to target with Sponsored Brand Headline: their priority, their cluster and its headline.

The rules the page always applied, moved here unchanged, with one addition: whether a keyword already runs in
Sponsored Products can be unknown, and then the table says so instead of saying it does not.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from core.amazon_ads.active_keywords import normalized_keyword

COL_KEYWORD = "Keyword"
COL_SV = "SV"
COL_RELEVANCE = "Relevance"
COL_IMPRESSION_SHARE = "IS %"
COL_PURCHASE_SHARE = "PS %"
COL_IN_SP = "En SP"
COL_MARKET_BUYING = "Market Buying"
COL_PRIORITY = "Prioridad"
COL_LAUNCH_SCORE = "Launch Score"
COL_CLUSTER = "Cluster"
COL_HEADLINE = "Headline Sugerido"
TARGET_COLUMNS = [COL_KEYWORD, COL_SV, COL_RELEVANCE, COL_IMPRESSION_SHARE, COL_PURCHASE_SHARE, COL_IN_SP,
                  COL_MARKET_BUYING, COL_PRIORITY, COL_LAUNCH_SCORE, COL_CLUSTER, COL_HEADLINE]
CLUSTER_COLUMNS = ["Cluster", "KWs", "SV_Total", "Alta", "Headline"]

PRIORITY_HIGH = "🔴 ALTA"
PRIORITY_MEDIUM = "🟡 MEDIA"
PRIORITY_LOW = "🟢 BAJA"
PRIORITIES = (PRIORITY_HIGH, PRIORITY_MEDIUM, PRIORITY_LOW)
YES = "✅"
NO = "❌"
UNKNOWN = "—"
OTHER_CLUSTER = "other"
SINGLE_CLUSTER = "general"
MIN_SEARCH_VOLUME = 300

_SQP_COUNT_FRAGMENTS = {
    "impressions_total": ("impression", "total", "count"),
    "impressions_brand": ("impression", "brand", "count"),
    "purchases_total": ("purchase", "total", "count"),
    "purchases_brand": ("purchase", "brand", "count"),
}
_MIN_KEYWORDS_PER_ROOT = 3
_HEADLINE_KEYWORDS = 5
_HEADLINE_WORDS = 4
_STOP_WORDS = frozenset({"for", "the", "and", "with", "a", "an", "in", "on", "to", "of",
                         "de", "para", "con", "en", "el", "la", "los", "las", "y", "del"})


class SqpFormatError(ValueError):
    """The SQP export lacks the column its queries are read from."""


@dataclass(frozen=True)
class QueryShare:
    impression_share: float  # IS %: the brand's share of the query's impressions
    purchase_share: float    # PS %: the brand's share of the query's purchases
    total_impressions: int
    total_purchases: int


@dataclass(frozen=True)
class SpKeywordCoverage:
    """The Sponsored Products keywords that run in the account chosen on screen."""

    # None when there is no account, no listing or no reading: unknown, never "none of them".
    keyword_texts: frozenset[str] | None = None
    account_label: str = ""
    profile_id: str = ""
    country_code: str = ""
    listed_at: datetime | None = None

    @property
    def known(self) -> bool:
        return self.keyword_texts is not None


@dataclass(frozen=True)
class SbhTargets:
    keywords: pd.DataFrame  # TARGET_COLUMNS, one row per target: priority first, then search volume
    clusters: pd.DataFrame  # CLUSTER_COLUMNS, one row per cluster, most search volume first


def query_shares(sqp: pd.DataFrame) -> dict[str, QueryShare]:
    """Lowercased query -> the brand's shares of it; raises SqpFormatError without a "Search Query" column."""
    query_column = _sqp_column(sqp, "search query")
    if query_column is None:
        raise SqpFormatError("No se encontró columna 'Search Query' en el SQP.")
    count_columns = {name: _sqp_column(sqp, *fragments) for name, fragments in _SQP_COUNT_FRAGMENTS.items()}
    numeric = sqp.copy()
    for column in count_columns.values():
        if column is not None:
            numeric[column] = pd.to_numeric(numeric[column], errors="coerce").fillna(0)

    shares = {}
    for _, row in numeric.iterrows():
        query = str(row[query_column]).strip().lower()
        imp_total, imp_brand, pur_total, pur_brand = (row.get(column, 0) if column else 0
                                                      for column in count_columns.values())
        shares[query] = QueryShare(
            impression_share=round(imp_brand / imp_total * 100, 1) if imp_total > 0 else 0,
            purchase_share=round(pur_brand / pur_total * 100, 1) if pur_total > 0 else 0,
            total_impressions=int(imp_total),
            total_purchases=int(pur_total),
        )
    return shares


def recommend_targets(mkl: pd.DataFrame, shares: dict[str, QueryShare],
                      sp_keywords: frozenset[str] | None) -> SbhTargets:
    """The MKL keywords worth an SBH target, prioritized and clustered; `sp_keywords` None is unknown coverage.

    Unknown coverage prioritizes every keyword as not running in SP, as the page did without the Campaign CSV.
    """
    rows = []
    for _, mkl_row in mkl.iterrows():
        term = str(mkl_row.get("Search Term", "")).strip()
        search_volume = mkl_row.get("SV", 0)
        share = shares.get(term.lower())
        impression_share = share.impression_share if share else 0
        market_buying = share is not None and share.total_purchases > 0
        in_sp = sp_keywords is not None and normalized_keyword(term) in sp_keywords

        priority = _priority(search_volume, impression_share, market_buying, in_sp)
        if priority is None:
            continue
        rows.append({
            COL_KEYWORD: term,
            COL_SV: int(search_volume),
            COL_RELEVANCE: round(mkl_row.get("Relevance", 0), 1),
            COL_IMPRESSION_SHARE: impression_share,
            COL_PURCHASE_SHARE: share.purchase_share if share else 0,
            COL_IN_SP: UNKNOWN if sp_keywords is None else YES if in_sp else NO,
            COL_MARKET_BUYING: YES if market_buying else NO,
            COL_PRIORITY: priority,
            COL_LAUNCH_SCORE: round(mkl_row.get("Launch Score", 0), 1),
        })
    if not rows:
        return SbhTargets(pd.DataFrame(columns=TARGET_COLUMNS), pd.DataFrame(columns=CLUSTER_COLUMNS))

    order = {priority: rank for rank, priority in enumerate(PRIORITIES)}
    targets = pd.DataFrame(rows)
    targets["_sort"] = targets[COL_PRIORITY].map(order)
    targets = (targets.sort_values(["_sort", COL_SV], ascending=[True, False])
               .drop(columns=["_sort"]).reset_index(drop=True))
    targets[COL_CLUSTER] = _clusters(targets[COL_KEYWORD])
    headlines = _cluster_headlines(targets)
    targets[COL_HEADLINE] = targets[COL_CLUSTER].map(headlines)
    return SbhTargets(targets, _cluster_summary(targets))


def root_words(phrase: object) -> list[str]:
    """The words a keyword clusters by: lowercase letters only, without stop words or words under three letters."""
    words = re.findall(r"[a-z]+", str(phrase).lower())
    return [word for word in words if word not in _STOP_WORDS and len(word) > 2]


def _sqp_column(sqp: pd.DataFrame, *fragments: str) -> str | None:
    return next((column for column in sqp.columns if all(fragment in column.lower() for fragment in fragments)), None)


def _priority(search_volume, impression_share, market_buying: bool, in_sp: bool) -> str | None:
    if search_volume >= 1000 and impression_share < 10 and market_buying and not in_sp:
        return PRIORITY_HIGH
    if search_volume >= 500 and impression_share < 20 and (not in_sp or impression_share < 5):
        return PRIORITY_MEDIUM
    if search_volume >= MIN_SEARCH_VOLUME:
        return PRIORITY_LOW
    return None


def _clusters(keywords: pd.Series) -> list[str]:
    """Each keyword's most shared root among those in three or more keywords, "other" without one."""
    roots_by_keyword = {keyword: root_words(keyword) for keyword in keywords}
    counter = Counter()
    for keyword in keywords:
        counter.update(roots_by_keyword[keyword])
    common_roots = {word for word, count in counter.items() if count >= _MIN_KEYWORDS_PER_ROOT}
    if not common_roots:
        return [SINGLE_CLUSTER] * len(keywords)
    clusters = []
    for keyword in keywords:
        matches = [root for root in roots_by_keyword[keyword] if root in common_roots]
        clusters.append(max(matches, key=lambda root: counter[root]) if matches else OTHER_CLUSTER)
    return clusters


def _cluster_headlines(targets: pd.DataFrame) -> dict[str, str]:
    """The four most repeated root words of each cluster's first five keywords, in title case."""
    headlines = {}
    for cluster in targets[COL_CLUSTER].unique():
        words = []
        for keyword in targets.loc[targets[COL_CLUSTER] == cluster, COL_KEYWORD].tolist()[:_HEADLINE_KEYWORDS]:
            words.extend(root_words(keyword))
        top_words = [word for word, _ in Counter(words).most_common(_HEADLINE_WORDS)]
        headlines[cluster] = " ".join(word.title() for word in top_words) if top_words else cluster.title()
    return headlines


def _cluster_summary(targets: pd.DataFrame) -> pd.DataFrame:
    return (
        targets.groupby(COL_CLUSTER)
        .agg(KWs=(COL_KEYWORD, "count"), SV_Total=(COL_SV, "sum"),
             Alta=(COL_PRIORITY, lambda priorities: (priorities == PRIORITY_HIGH).sum()),
             Headline=(COL_HEADLINE, "first"))
        .sort_values("SV_Total", ascending=False)
        .reset_index()
    )
