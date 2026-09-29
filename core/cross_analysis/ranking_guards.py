"""INV-11's marks on the search terms Análisis Cruzado reads from Amazon Ads.

Where each term came from, whether its campaign's portfolio is protected, and whether it already exists as an enabled
exact keyword of the account. The marks inform the AM; they never change the action the module suggests.
"""
from __future__ import annotations

import pandas as pd

from core.amazon_ads.active_keywords import normalized_keyword
from core.amazon_ads.report_provider import (
    ORIGIN_AUTO,
    ORIGIN_BROAD,
    ORIGIN_EXACT,
    ORIGIN_PHRASE,
    ORIGIN_PRODUCT_TARGETING,
)
from core.search_term.frame import PORTFOLIO_NAME, PORTFOLIO_NAME_MISSING, SEARCH_TERM
from core.search_term.negatives import is_ranking_protected

ORIGIN = "_origen_match_type"
NOT_NEGATABLE = "_no_negativizable"
RANKING_KEYWORD = "_es_ranking_kw"
ALREADY_EXACT = "_ya_en_exact"

ORIGIN_LABELS = {
    ORIGIN_EXACT: "Exact",
    ORIGIN_PHRASE: "Phrase",
    ORIGIN_BROAD: "Broad",
    ORIGIN_AUTO: "Auto",
    ORIGIN_PRODUCT_TARGETING: "Product Targeting",
}


def with_ranking_guards(search_terms: pd.DataFrame, exact_keywords: frozenset[str] | None) -> pd.DataFrame:
    """A copy of the canonical search term frame with INV-11's marks.

    INV-11.1: a term reached through an exact keyword or a product target is not negatable; one from an auto
    campaign is. INV-11.3: RANKING portfolios, and portfolios whose name never synced, are protected.
    INV-11.2: `exact_keywords` None (the account's SP listing is unknown) leaves that mark unknown, never False.
    """
    guarded = search_terms.copy()
    origins = _texts(guarded, "_origin_match_type").str.upper()
    guarded[ORIGIN] = origins.map(ORIGIN_LABELS).fillna("")
    guarded[NOT_NEGATABLE] = origins.isin((ORIGIN_EXACT, ORIGIN_PRODUCT_TARGETING))
    guarded[RANKING_KEYWORD] = [is_ranking_protected(portfolio, missing) for portfolio, missing
                                in zip(_texts(guarded, PORTFOLIO_NAME), _flags(guarded, PORTFOLIO_NAME_MISSING))]
    guarded[ALREADY_EXACT] = exact_marks(guarded[SEARCH_TERM], exact_keywords)
    return guarded


def exact_marks(texts: pd.Series, exact_keywords: frozenset[str] | None) -> pd.Series:
    """Whether each text is an enabled exact keyword of the account; NA while the account's listing is unknown."""
    if exact_keywords is None:
        return pd.Series(pd.NA, index=texts.index, dtype="boolean")
    return texts.map(lambda text: normalized_keyword(text) in exact_keywords).astype("boolean")


def _texts(frame: pd.DataFrame, column: str) -> pd.Series:
    if column not in frame.columns:
        return pd.Series("", index=frame.index, dtype="object")
    return frame[column].fillna("").astype(str).str.strip()


def _flags(frame: pd.DataFrame, column: str) -> list[bool]:
    if column not in frame.columns:
        return [False] * len(frame)
    return [value is True or str(value).strip().casefold() in ("true", "1") for value in frame[column]]
