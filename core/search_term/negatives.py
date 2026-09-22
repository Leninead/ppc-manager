"""Negative-keyword candidates from a search term frame, and the subset that is safe to bulk-upload.

Rules are M2's negatives mining with the SOP corrections of .claude/skills/ppc-business-invariants.md.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

from core.amazon_ads.report_provider import (
    KEYWORD_MATCH_TYPES,
    ORIGIN_AUTO,
    ORIGIN_BROAD,
    ORIGIN_EXACT,
    ORIGIN_PHRASE,
    ORIGIN_PRODUCT_TARGETING,
)
from core.bulk.keyword_text import negative_keyword_text_problem
from core.search_term.frame import ANY_WINDOW_PURCHASES, PORTFOLIO_NAME_MISSING, SEARCH_TERM, orders_column

ACTION_NEGATIVE = "Negativo"
ACTION_LOWER_BID = "Bajar bid"
ACTION_REVIEW = "Revisar manualmente"

NEGATIVE_EXACT = "Negative Exact"
NEGATIVE_PHRASE = "Negative Phrase"

PRIORITY_HIGH = "Alta"
PRIORITY_MEDIUM = "Media"
PRIORITY_REVIEW = "Revisar"

RULE_FEW_CLICKS = "R1 — Pocos clicks sin venta"
RULE_NO_CONVERSION_CLICKS = "R2 — Sin conversión (CVR)"
RULE_NO_CONVERSION_SPEND = "R3 — Gasto sin conversión"
RULE_EXTREME_ACOS = "R4 — ACoS extremo"
RULE_LOW_CTR = "R5 — CTR bajo + irrelevancia"

LOW_CTR_MIN_IMPRESSIONS = 2500
LOW_CTR_MAX_PERCENT = 0.18
EXTREME_ACOS_MIN_PERCENT = 70.0
EXTREME_ACOS_MAX_ORDERS = 5

EXCLUDED_EXACT_ORIGIN = "Viene de una keyword Exact: si rinde mal se baja el bid o se pausa, no se negativiza."
EXCLUDED_PRODUCT_TARGETING_ORIGIN = "Viene de Product Targeting: si rinde mal se baja el bid o se pausa el target."
EXCLUDED_UNKNOWN_ORIGIN = (
    "No se sabe de qué targeting viene el término, así que no se puede confirmar que sea negativizable."
)
EXCLUDED_CONVERTS = "El término tiene órdenes en este ad group: lo que convierte no se negativiza."
EXCLUDED_CAMPAIGN_NOT_ENABLED = "La campaña no está activa ({status})."
EXCLUDED_NOT_A_QUERY = "El término no es una búsqueda (un ASIN o «*»): no se puede cargar como keyword negativa."
EXCLUDED_INVALID_KEYWORD_TEXT = "Amazon no acepta este texto como keyword negativa: {problem}."
EXCLUDED_ACTIVE_EXACT = "Ya corre como keyword Exact activa en la cuenta."
EXCLUDED_OWN_KEYWORD = "Es una keyword propia de este ad group: negativizarla le corta su propio tráfico."
EXCLUDED_PHRASE_BLOCKS = (
    "La frase negativa bloquearía búsquedas que convierten o una keyword Exact activa de este ad group."
)
EXCLUDED_MISSING_IDS = "Faltan los IDs de campaña o de ad group para armar el bulk."
EXCLUDED_RANKING_PORTFOLIO = "Está en un portfolio RANKING ({portfolio}): se protege el ranking orgánico."
EXCLUDED_UNNAMED_PORTFOLIO = (
    "El portfolio ({portfolio}) no tiene nombre sincronizado: no se puede confirmar que no sea RANKING."
)
EXCLUDED_DUPLICATE = "Duplicado: el mismo negativo ya va en el bulk."

EXACT_GUARD_PARTIAL_NOTE = (
    "Los controles de keywords Exact activas y de keywords propias del ad group son parciales: solo ven las "
    "keywords que tuvieron clicks en el período elegido, así que revisá Campaign Manager antes de subir el bulk."
)
AD_GROUP_STATE_UNVERIFIED_NOTE = (
    "El estado de los ad groups no se verifica: si alguno está pausado o archivado, sacá sus negativos del "
    "archivo antes de subirlo."
)

_BULK_ORIGINS = (ORIGIN_BROAD, ORIGIN_PHRASE, ORIGIN_AUTO)
_PRIORITY_ORDER = {PRIORITY_HIGH: 0, PRIORITY_MEDIUM: 1, PRIORITY_REVIEW: 2}
_ASIN_TERM = re.compile(r"^b0[a-z0-9]{8}$", re.IGNORECASE)
_ISBN10_ASIN_TERM = re.compile(r"^\d{9}[\dx]$", re.IGNORECASE)
_RANKING_PORTFOLIO = "RANKING"
_ENABLED = "enabled"
_BULK_FRAME_COLUMNS = (SEARCH_TERM, "_campaign_id", "_ad_group_id", "_keyword_type", "_ad_keyword_status",
                       "_keyword_text", "_origin_match_type")
# Amazon negatives can match close variants, so the guards err toward protection: "bag" and "bags" are one word.
_PLURAL_SUFFIXES = ("s", "es")

_AdGroupKey = tuple[str, str]
_Tokens = tuple[str, ...]


@dataclass(frozen=True)
class NegativeCandidate:
    search_term: str
    campaign: str
    ad_group: str
    clicks: int
    impressions: int
    spend: float
    orders: int
    acos: float | None
    rule: str
    action: str
    match_type: str
    priority: str
    campaign_id: str = ""
    ad_group_id: str = ""
    origin_match_type: str = ""
    campaign_status: str = ""
    portfolio: str = ""
    portfolio_name_missing: bool = False


@dataclass(frozen=True)
class BulkExclusion:
    candidate: NegativeCandidate
    reason: str
    # True only for the RANKING / unnamed-portfolio guard, which the user may lift term by term (INV-11.3).
    releasable: bool = False


@dataclass(frozen=True)
class _RuleOutcome:
    rule: str
    action: str
    match_type: str
    priority: str


_NO_CONVERSION_CLICKS = _RuleOutcome(RULE_NO_CONVERSION_CLICKS, ACTION_NEGATIVE, NEGATIVE_EXACT, PRIORITY_HIGH)
_NO_CONVERSION_SPEND = _RuleOutcome(RULE_NO_CONVERSION_SPEND, ACTION_NEGATIVE, NEGATIVE_EXACT, PRIORITY_HIGH)
_LOW_CTR = _RuleOutcome(RULE_LOW_CTR, ACTION_NEGATIVE, NEGATIVE_PHRASE, PRIORITY_MEDIUM)
_FEW_CLICKS = _RuleOutcome(RULE_FEW_CLICKS, ACTION_REVIEW, NEGATIVE_EXACT, PRIORITY_REVIEW)
# INV-11.4: extreme ACoS with orders lowers the bid; there is no negative to suggest.
_EXTREME_ACOS = _RuleOutcome(RULE_EXTREME_ACOS, ACTION_LOWER_BID, "", PRIORITY_MEDIUM)


@dataclass(frozen=True)
class AdGroupGuards:
    """What the unfiltered frame says about each ad group, read once per bulk selection."""

    active_exact_terms: set[str]
    converting_terms: set[tuple[str, str, str]]
    exact_origin_terms: set[tuple[str, str, str]]
    product_targeting_origin_terms: set[tuple[str, str, str]]
    converting_tokens: dict[_AdGroupKey, set[_Tokens]]
    enabled_exact_tokens: dict[_AdGroupKey, set[_Tokens]]
    own_keyword_tokens: dict[_AdGroupKey, set[_Tokens]]


def evaluate_candidates(frame: pd.DataFrame, cols: dict, *, clicks_threshold: int,
                        spend_threshold: float) -> list[NegativeCandidate]:
    """Candidates sorted by priority then spend; `cols` is M2's `_detect_cols` mapping for `frame`."""
    search_term_column = cols.get("search_term")
    if not search_term_column or search_term_column not in frame.columns:
        raise ValueError("search term frame has no search term column")

    search_terms = _texts(frame, search_term_column)
    campaigns = _texts(frame, cols.get("campaign"))
    ad_groups = _texts(frame, cols.get("ad_group"))
    portfolios = _texts(frame, cols.get("portfolio"))
    portfolio_names_missing = _flags(frame, PORTFOLIO_NAME_MISSING)
    campaign_ids = _texts(frame, "_campaign_id")
    ad_group_ids = _texts(frame, "_ad_group_id")
    origins = _texts(frame, "_origin_match_type")
    campaign_statuses = _texts(frame, "_campaign_status")
    clicks = _numbers(frame, cols.get("clicks"))
    orders = _numbers(frame, cols.get("orders"))
    spend = _numbers(frame, cols.get("spend"))
    impressions = _numbers(frame, cols.get("impressions"))
    acos = _numbers(frame, cols.get("acos"))
    ctr = _numbers(frame, cols.get("ctr"))

    candidates = []
    for position in range(len(frame)):
        outcome = _first_matching_rule(
            clicks=clicks[position], orders=orders[position], spend=spend[position],
            impressions=impressions[position], ctr=ctr[position], acos=acos[position],
            clicks_threshold=clicks_threshold, spend_threshold=spend_threshold,
        )
        if outcome is None:
            continue
        candidates.append(NegativeCandidate(
            search_term=search_terms[position],
            campaign=campaigns[position],
            ad_group=ad_groups[position],
            clicks=int(clicks[position]),
            impressions=int(impressions[position]),
            spend=round(float(spend[position]), 2),
            orders=int(orders[position]),
            acos=round(float(acos[position]), 1) if orders[position] > 0 else None,
            rule=outcome.rule,
            action=outcome.action,
            match_type=outcome.match_type,
            priority=outcome.priority,
            campaign_id=campaign_ids[position],
            ad_group_id=ad_group_ids[position],
            origin_match_type=origins[position].upper(),
            campaign_status=campaign_statuses[position],
            portfolio=portfolios[position],
            portfolio_name_missing=portfolio_names_missing[position],
        ))
    return sorted(candidates, key=lambda candidate: (_PRIORITY_ORDER[candidate.priority], -candidate.spend))


def negative_key(candidate: NegativeCandidate) -> tuple[str, str, str, str]:
    """(campaign_id, ad_group_id, normalized term, match type): one negative in the bulk, and its release key."""
    return (candidate.campaign_id, candidate.ad_group_id, _normalized_term(candidate.search_term),
            candidate.match_type)


def select_for_bulk(candidates: list[NegativeCandidate], frame: pd.DataFrame, *,
                    released_ranking: frozenset[tuple] = frozenset(),
                    guards: AdGroupGuards | None = None) -> tuple[list[dict], list[BulkExclusion]]:
    """Rows for `core.bulk.export.build_adgroup_negative` from the Negativo candidates, plus why the rest stay out.

    `frame` must be the unfiltered API frame: the ad group guards read every row of it. RANKING and
    unnamed-portfolio candidates stay out unless their `negative_key` is in `released_ranking`.
    Pass `guards` from `ad_group_guards(frame)` to select from the same frame again without re-reading it.
    """
    if guards is None:
        guards = ad_group_guards(frame)

    rows: list[dict] = []
    exclusions: list[BulkExclusion] = []
    selected_keys: set[tuple[str, str, str, str]] = set()
    for candidate in candidates:
        if candidate.action != ACTION_NEGATIVE:
            continue
        key = negative_key(candidate)
        reason = _blocking_reason(candidate, guards)
        releasable = False
        if reason is None and key not in released_ranking:
            reason = _portfolio_reason(candidate)
            releasable = reason is not None
        if reason is None and key in selected_keys:
            reason = EXCLUDED_DUPLICATE
        if reason is not None:
            exclusions.append(BulkExclusion(candidate=candidate, reason=reason, releasable=releasable))
            continue
        selected_keys.add(key)
        rows.append({
            "campaign_id": candidate.campaign_id,
            "ad_group_id": candidate.ad_group_id,
            "keyword_text": candidate.search_term.strip(),
            "match_type": candidate.match_type,
            "campaign_name": candidate.campaign,
            "ad_group_name": candidate.ad_group,
        })
    return rows, exclusions


def _first_matching_rule(*, clicks: float, orders: float, spend: float, impressions: float, ctr: float,
                         acos: float, clicks_threshold: int, spend_threshold: float) -> _RuleOutcome | None:
    if orders == 0:
        if clicks >= clicks_threshold:
            return _NO_CONVERSION_CLICKS
        if spend >= spend_threshold:
            return _NO_CONVERSION_SPEND
        if impressions >= LOW_CTR_MIN_IMPRESSIONS and ctr < LOW_CTR_MAX_PERCENT:
            return _LOW_CTR
        if clicks >= 1:
            return _FEW_CLICKS
        return None
    if 0 < orders < EXTREME_ACOS_MAX_ORDERS and acos > EXTREME_ACOS_MIN_PERCENT:
        return _EXTREME_ACOS
    return None


def _blocking_reason(candidate: NegativeCandidate, guards: AdGroupGuards) -> str | None:
    origin = candidate.origin_match_type.strip().upper()
    if origin == ORIGIN_EXACT:
        return EXCLUDED_EXACT_ORIGIN
    if origin == ORIGIN_PRODUCT_TARGETING:
        return EXCLUDED_PRODUCT_TARGETING_ORIGIN
    if origin not in _BULK_ORIGINS:
        return EXCLUDED_UNKNOWN_ORIGIN
    term = _normalized_term(candidate.search_term)
    ad_group = (candidate.campaign_id.strip(), candidate.ad_group_id.strip())
    term_in_ad_group = (*ad_group, term)
    # A negative applies to the whole ad group, so a sibling row reached through Exact or PT protects the term.
    if term_in_ad_group in guards.exact_origin_terms:
        return EXCLUDED_EXACT_ORIGIN
    if term_in_ad_group in guards.product_targeting_origin_terms:
        return EXCLUDED_PRODUCT_TARGETING_ORIGIN
    if candidate.orders > 0 or term_in_ad_group in guards.converting_terms:
        return EXCLUDED_CONVERTS
    if candidate.campaign_status.strip().casefold() != _ENABLED:
        return EXCLUDED_CAMPAIGN_NOT_ENABLED.format(status=candidate.campaign_status.strip() or "sin estado")
    if term == "*" or _ASIN_TERM.match(term) or _ISBN10_ASIN_TERM.match(term):
        return EXCLUDED_NOT_A_QUERY
    keyword_text_problem = negative_keyword_text_problem(candidate.search_term.strip(), candidate.match_type)
    if keyword_text_problem:
        return EXCLUDED_INVALID_KEYWORD_TEXT.format(problem=keyword_text_problem)
    if term in guards.active_exact_terms:
        return EXCLUDED_ACTIVE_EXACT
    tokens = tuple(term.split())
    if candidate.match_type == NEGATIVE_PHRASE and (
            _blocks_any(tokens, guards.converting_tokens.get(ad_group, ()), NEGATIVE_PHRASE)
            or _blocks_any(tokens, guards.enabled_exact_tokens.get(ad_group, ()), NEGATIVE_PHRASE)):
        return EXCLUDED_PHRASE_BLOCKS
    if _blocks_any(tokens, guards.own_keyword_tokens.get(ad_group, ()), candidate.match_type):
        return EXCLUDED_OWN_KEYWORD
    if not ad_group[0] or not ad_group[1]:
        return EXCLUDED_MISSING_IDS
    return None


def _portfolio_reason(candidate: NegativeCandidate) -> str | None:
    if _RANKING_PORTFOLIO in candidate.portfolio.upper():
        return EXCLUDED_RANKING_PORTFOLIO.format(portfolio=candidate.portfolio.strip())
    if candidate.portfolio_name_missing:
        return EXCLUDED_UNNAMED_PORTFOLIO.format(portfolio=candidate.portfolio.strip())
    return None


def ad_group_guards(frame: pd.DataFrame) -> AdGroupGuards:
    """What the unfiltered API frame says about every ad group; raises ValueError when the frame is not bulk-ready."""
    missing = [column for column in _BULK_FRAME_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"search term frame is not bulk-ready, missing columns {missing}")
    campaign_ids = _texts(frame, "_campaign_id")
    ad_group_ids = _texts(frame, "_ad_group_id")
    terms = [_normalized_term(term) for term in _texts(frame, SEARCH_TERM)]
    origins = [origin.upper() for origin in _texts(frame, "_origin_match_type")]
    keyword_types = [keyword_type.upper() for keyword_type in _texts(frame, "_keyword_type")]
    keyword_statuses = [status.casefold() for status in _texts(frame, "_ad_keyword_status")]
    keyword_texts = [_normalized_term(text) for text in _texts(frame, "_keyword_text")]
    purchases = _any_window_purchases(frame)

    active_exact_terms: set[str] = set()
    converting_terms: set[tuple[str, str, str]] = set()
    exact_origin_terms: set[tuple[str, str, str]] = set()
    product_targeting_origin_terms: set[tuple[str, str, str]] = set()
    converting_tokens: dict[_AdGroupKey, set[_Tokens]] = defaultdict(set)
    enabled_exact_tokens: dict[_AdGroupKey, set[_Tokens]] = defaultdict(set)
    own_keyword_tokens: dict[_AdGroupKey, set[_Tokens]] = defaultdict(set)
    for position in range(len(frame)):
        ad_group = (campaign_ids[position], ad_group_ids[position])
        term_in_ad_group = (*ad_group, terms[position])
        if origins[position] == ORIGIN_EXACT:
            exact_origin_terms.add(term_in_ad_group)
        elif origins[position] == ORIGIN_PRODUCT_TARGETING:
            product_targeting_origin_terms.add(term_in_ad_group)
        if purchases[position] > 0:
            converting_terms.add(term_in_ad_group)
            converting_tokens[ad_group].add(tuple(terms[position].split()))
        keyword_tokens = tuple(keyword_texts[position].split())
        if not keyword_tokens or keyword_types[position] not in KEYWORD_MATCH_TYPES:
            continue
        own_keyword_tokens[ad_group].add(keyword_tokens)
        if keyword_types[position] == ORIGIN_EXACT and keyword_statuses[position] == _ENABLED:
            active_exact_terms.add(keyword_texts[position])
            enabled_exact_tokens[ad_group].add(keyword_tokens)
    return AdGroupGuards(
        active_exact_terms=active_exact_terms, converting_terms=converting_terms,
        exact_origin_terms=exact_origin_terms, product_targeting_origin_terms=product_targeting_origin_terms,
        converting_tokens=converting_tokens, enabled_exact_tokens=enabled_exact_tokens,
        own_keyword_tokens=own_keyword_tokens,
    )


def _any_window_purchases(frame: pd.DataFrame) -> np.ndarray:
    # Seller frames show 7-day orders, but a purchase inside the 14-day window still means the term converts.
    columns = [column for column in (orders_column(7), orders_column(14), ANY_WINDOW_PURCHASES)
               if column in frame.columns]
    if not columns:
        raise ValueError("search term frame is not bulk-ready, it has no orders column")
    return np.max([_numbers(frame, column) for column in columns], axis=0)


def _blocks_any(negative_tokens: _Tokens, protected: Iterable[_Tokens], match_type: str) -> bool:
    """Whether a negative of `match_type` with these words would block any of the `protected` word sequences."""
    if not negative_tokens:
        return False
    if match_type == NEGATIVE_PHRASE:
        return any(_contains_run(negative_tokens, words) for words in protected)
    return any(_same_words(negative_tokens, words) for words in protected)


def _contains_run(run: _Tokens, words: _Tokens) -> bool:
    size = len(run)
    return any(_same_words(run, words[start:start + size]) for start in range(len(words) - size + 1))


def _same_words(left: _Tokens, right: _Tokens) -> bool:
    return len(left) == len(right) and all(map(_same_word, left, right))


def _same_word(left: str, right: str) -> bool:
    if left == right:
        return True
    shorter, longer = sorted((left, right), key=len)
    return any(longer == shorter + suffix for suffix in _PLURAL_SUFFIXES)


def _normalized_term(term) -> str:
    return " ".join(str(term).split()).casefold()


def _texts(frame: pd.DataFrame, column: str | None) -> list[str]:
    if not column or column not in frame.columns:
        return [""] * len(frame)
    values = frame[column]
    return values.astype(str).str.strip().where(values.notna(), "").tolist()


def _flags(frame: pd.DataFrame, column: str) -> list[bool]:
    if column not in frame.columns:
        return [False] * len(frame)
    return [bool(value) if isinstance(value, (bool, np.bool_)) else str(value).strip().casefold() in ("true", "1")
            for value in frame[column]]


def _numbers(frame: pd.DataFrame, column: str | None) -> np.ndarray:
    if not column or column not in frame.columns:
        return np.zeros(len(frame))
    values = frame[column]
    if pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values):
        return values.fillna(0).to_numpy(dtype="float64")
    # Same cleanup as M2's `_to_num`, so a console file scores exactly as it does in the page today.
    cleaned = values.astype(str).str.replace(r"[MX$,%]", "", regex=True)
    return pd.to_numeric(cleaned, errors="coerce").fillna(0).to_numpy(dtype="float64")
