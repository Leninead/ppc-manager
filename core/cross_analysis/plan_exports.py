"""The two files the Plan de Acción of Análisis Cruzado exports, each valid for whoever reads it.

The Amazon bulk changes bids of keywords that exist and adds keywords to ad groups that exist: its rows carry the IDs
of the search term's top-spend campaign and Amazon rejects any column of its own (INV-5.5). Campaign Builder reads a
different file: its first sheet with Keyword, Acción sugerida, Purchases mercado and Brand Share %, the contract M10
builds new campaigns from, every keyword in exact match.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.report_provider import KEYWORD_MATCH_TYPES
from core.cross_analysis.action_plan import (
    ACTION,
    ACTION_ADD,
    ACTION_DEFEND,
    ACTION_LOWER_BID,
    ACTION_SCALE,
    BRAND_PURCHASE_SHARE,
    IN_SEARCH_TERMS,
    MARKET_PURCHASES,
    QUERY,
    QUERY_TYPE,
)
from core.cross_analysis.ranking_guards import ALREADY_EXACT, ORIGIN, ORIGIN_LABELS
from core.search_term.frame import AD_GROUP_NAME, CAMPAIGN_NAME

BULK_CREATE_ACTIONS = (ACTION_ADD, ACTION_DEFEND)
BULK_UPDATE_ACTIONS = (ACTION_SCALE, ACTION_LOWER_BID)
BULK_ACTIONS = BULK_CREATE_ACTIONS + BULK_UPDATE_ACTIONS
# CONQUEST stays out on purpose: targeting a rival's brand is the AM's explicit call (trademark risk).
CAMPAIGN_BUILDER_ACTIONS = (ACTION_SCALE, ACTION_ADD, ACTION_DEFEND)
MATCH_TYPE_BY_ACTION = {ACTION_ADD: "Phrase", ACTION_DEFEND: "Exact", ACTION_SCALE: "Exact", ACTION_LOWER_BID: "Exact"}

CB_KEYWORD = "Keyword"
CB_ACTION = "Acción sugerida"
CB_MARKET_PURCHASES = "Purchases mercado"
CB_BRAND_SHARE = "Brand Share %"
CB_CONTRACT_COLUMNS = (CB_KEYWORD, CB_ACTION, CB_MARKET_PURCHASES, CB_BRAND_SHARE)
CB_QUERY_TYPE = "Tipo"
CB_IN_SEARCH_TERMS = "En STR"
CB_REASON = "Motivo"

NOT_IN_CAMPAIGN_BUILDER = "Campaign Builder sólo arma campañas nuevas de ESCALAR, AGREGAR y DEFENDER."
ALREADY_EXACT_IN_ACCOUNT = ("Ya existe como keyword Exact habilitada en la cuenta: Campaign Builder crearía otra "
                            "igual.")

_KEYWORD_ORIGINS = {ORIGIN_LABELS[match_type] for match_type in KEYWORD_MATCH_TYPES}


@dataclass(frozen=True)
class BulkRows:
    """The plan rows as `core.bulk.export` builders take them: keywords to create and bids to update."""

    creates: list[dict]
    updates: list[dict]
    # Queries left out of the creates because they already exist as an enabled exact keyword of the account.
    already_exact: list[str]
    # Queries left out of the updates because another row already updates the keyword they came through.
    same_keyword: list[str]


@dataclass(frozen=True)
class CampaignBuilderPlan:
    rows: pd.DataFrame  # CB_CONTRACT_COLUMNS first: the sheet Campaign Builder reads
    left_out: pd.DataFrame  # the visible rows that stayed out, with CB_REASON
    exact_checked: bool  # False while the account's listing is unknown: duplicates could not be looked for


def bulk_rows(plan_rows: pd.DataFrame, bid: float | None) -> BulkRows:
    """The Amazon bulk rows of the plan's actionable actions; a row without the IDs it needs stays invalid, never
    invented, so the builders reject it with its reason (INV-5.4).

    A keyword the account already has as an enabled exact is never created again: in its own ad group Amazon would
    reject the duplicate, and in another one it would compete with the one that exists. An update names the keyword it
    changes, with that keyword's text, once: a broad or phrase keyword reaches many terms of the plan.
    """
    creates, updates, already_exact, same_keyword = [], [], [], []
    updated_keyword_ids = set()
    for row in plan_rows[plan_rows[ACTION].isin(BULK_ACTIONS)].to_dict("records"):
        action = row[ACTION]
        query = str(row.get(QUERY, "")).strip()
        if action in BULK_CREATE_ACTIONS and _known_true(row.get(ALREADY_EXACT)):
            already_exact.append(query)
            continue
        entry = {
            "campaign_id": _text(row.get("_campaign_id")),
            "ad_group_id": _text(row.get("_ad_group_id")),
            "campaign_name": _text(row.get(CAMPAIGN_NAME)),
            "ad_group_name": _text(row.get(AD_GROUP_NAME)),
            "keyword_text": query,
            "bid": bid,
        }
        if action in BULK_UPDATE_ACTIONS:
            # Auto and product target rows carry a target id, which is not a keyword: they get none and stay out
            # under the query that names them.
            keyword_id = _keyword_id(row)
            if keyword_id in updated_keyword_ids:
                same_keyword.append(query)
                continue
            if keyword_id:
                updated_keyword_ids.add(keyword_id)
                entry["keyword_text"] = _text(row.get("_keyword_text"))
            entry["keyword_id"] = keyword_id
            origin = _text(row.get(ORIGIN))
            entry["match_type"] = origin if origin in _KEYWORD_ORIGINS else MATCH_TYPE_BY_ACTION[action]
            updates.append(entry)
        else:
            entry["match_type"] = MATCH_TYPE_BY_ACTION[action]
            creates.append(entry)
    return BulkRows(creates, updates, already_exact, same_keyword)


def campaign_builder_plan(plan_rows: pd.DataFrame) -> CampaignBuilderPlan:
    """The visible rows Campaign Builder can turn into new exact campaigns, and why the others stayed out."""
    eligible = plan_rows[ACTION].isin(CAMPAIGN_BUILDER_ACTIONS)
    exact_known = ALREADY_EXACT in plan_rows.columns and plan_rows[ALREADY_EXACT].notna().all()
    already_exact = plan_rows[ALREADY_EXACT].eq(True) if exact_known else pd.Series(False, index=plan_rows.index)
    kept = plan_rows[eligible & ~already_exact]
    rows = pd.DataFrame({
        CB_KEYWORD: kept[QUERY].astype(str).str.strip(),
        CB_ACTION: kept[ACTION],
        CB_MARKET_PURCHASES: _column(kept, MARKET_PURCHASES),
        CB_BRAND_SHARE: _column(kept, BRAND_PURCHASE_SHARE),
        CB_QUERY_TYPE: _column(kept, QUERY_TYPE),
        CB_IN_SEARCH_TERMS: _column(kept, IN_SEARCH_TERMS),
    }).reset_index(drop=True)
    reasons = pd.Series(NOT_IN_CAMPAIGN_BUILDER, index=plan_rows.index).where(~eligible, ALREADY_EXACT_IN_ACCOUNT)
    left = plan_rows[~eligible | already_exact]
    left_out = pd.DataFrame({CB_KEYWORD: left[QUERY].astype(str).str.strip(), CB_ACTION: left[ACTION],
                             CB_REASON: reasons[left.index]}).reset_index(drop=True)
    return CampaignBuilderPlan(rows=rows, left_out=left_out, exact_checked=exact_known)


def _known_true(value) -> bool:
    return value is not None and not pd.isna(value) and bool(value)


def _keyword_id(row: Mapping) -> str:
    keyword_type = _text(row.get("_keyword_type")).upper()
    return _text(row.get("_keyword_id")) if keyword_type in KEYWORD_MATCH_TYPES else ""


def _column(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column] if column in frame.columns else pd.Series(pd.NA, index=frame.index)


def _text(value) -> str:
    return "" if value is None or pd.isna(value) else str(value).strip()
