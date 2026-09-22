"""Análisis de Funnel rules: which search terms come from active campaigns and which from paused or missing ones,
which active campaigns got no search traffic, the campaigns to suggest and the terms to harvest.

The page and the MCP server compute them from here, so nothing here may import Streamlit or an agent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import pandas as pd

from core.amazon_ads.campaign_provider import SPONSORED_PRODUCTS
from core.search_term.candidates import detect_columns, numeric_column
from core.search_term.frame import ACOS

ENABLED = "ENABLED"
PAUSED = "PAUSED"
CAMPAIGN_NOT_FOUND = "No encontrada"
MATCHED_BY_ID = "Campaign ID"
MATCHED_BY_NAME = "nombre de campaña"

DEFAULT_MIN_ORDERS = 3
DEFAULT_MATCH_TYPE = "Phrase"
MATCH_TYPES = ("Phrase", "Exact", "Broad")
# SOP Capybaras: enough orders under this ACoS go straight to Exact.
EXACT_HARVEST_MAX_ACOS = 25.0

CAMPAIGN_STATE_COLUMN = "Estado de la campaña"
SOURCE_CAMPAIGN_COLUMN = "Campaña origen"
ACTIVE_CAMPAIGN_COLUMN = "En campaña activa"
SUGGESTED_MATCH_COLUMN = "Match Type Sugerido"
CVR_COLUMN = "CVR %"
SUGGESTED_COLUMNS = ["Customer Search Term", "Campaña origen (inactiva)", CAMPAIGN_STATE_COLUMN, "Producto inferido",
                     "ASIN inferido", "Match Type", "Nombre sugerido", "Clicks", "Spend", "Orders", "Sales"]
SEARCH_TERM_CAMPAIGN_ID = "_campaign_id"

_PRODUCT_AND_ASIN = re.compile(r"^(.+?)\s*-\s*(B[0-9A-Z]{9})\b", re.IGNORECASE)


class FunnelInputError(ValueError):
    """A report lacks a column the funnel needs; the message is written for the AM."""


@dataclass(frozen=True)
class OrdersAndSales:
    """Summed over search term rows; None when the report has no such column."""

    orders: float | None
    sales: float | None


@dataclass(frozen=True)
class FunnelCoverage:
    campaigns: pd.DataFrame
    active_campaigns: pd.DataFrame
    paused_campaigns: int
    # Sponsored Brands and Display rows of the campaign file: the search term report has no terms of theirs.
    other_products: int
    active_terms: pd.DataFrame
    gap_terms: pd.DataFrame
    idle_campaigns: pd.DataFrame
    matched_by: str
    columns: dict


def cover(search_terms: pd.DataFrame, campaigns: pd.DataFrame, *, match_by_id: bool) -> FunnelCoverage:
    """Crosses the search terms with the Sponsored Products campaigns, by Campaign ID when both sides carry it."""
    columns = detect_columns(visible_columns(search_terms))
    if not columns["search_term"] or not columns["campaign"]:
        raise FunnelInputError("El Search Term Report no trae las columnas de search term y de campaña.")
    campaign_name = campaign_column(campaigns, "campaign name")
    if campaign_name is None:
        raise FunnelInputError("El archivo de campañas no trae la columna «Campaign name».")

    sponsored, other_products = _sponsored_products(campaigns)
    state_column = campaign_column(sponsored, "state")
    states = (sponsored[state_column].fillna("").astype(str).str.strip().str.upper() if state_column
              else pd.Series(ENABLED, index=sponsored.index))
    id_column = campaign_column(sponsored, "campaign id")
    by_id = match_by_id and id_column is not None and SEARCH_TERM_CAMPAIGN_ID in search_terms.columns
    campaign_keys = _campaign_keys(sponsored[id_column] if by_id else sponsored[campaign_name], by_id)
    term_keys = _campaign_keys(search_terms[SEARCH_TERM_CAMPAIGN_ID] if by_id else search_terms[columns["campaign"]],
                               by_id)

    active = states.eq(ENABLED)
    from_active = term_keys.isin(set(campaign_keys[active]))
    gap_terms = search_terms[~from_active].copy()
    state_by_key = dict(zip(campaign_keys, states))
    gap_terms[CAMPAIGN_STATE_COLUMN] = term_keys[~from_active].map(state_by_key).fillna(CAMPAIGN_NOT_FOUND)
    return FunnelCoverage(
        campaigns=sponsored,
        active_campaigns=sponsored[active],
        paused_campaigns=int(states.eq(PAUSED).sum()),
        other_products=other_products,
        active_terms=search_terms[from_active],
        gap_terms=gap_terms,
        idle_campaigns=sponsored[active & ~campaign_keys.isin(set(term_keys))],
        matched_by=MATCHED_BY_ID if by_id else MATCHED_BY_NAME,
        columns=columns,
    )


def suggested_campaigns(gap_terms: pd.DataFrame, columns: dict, match_type: str) -> pd.DataFrame:
    """One new campaign per search term of a paused or missing campaign, named with the Capybaras convention."""
    if gap_terms.empty:
        return pd.DataFrame(columns=SUGGESTED_COLUMNS)
    term_column, campaign = columns["search_term"], columns["campaign"]
    totals = _term_totals(gap_terms, columns)
    rows = []
    for term, source_campaign, state in gap_terms.drop_duplicates(subset=term_column)[
            [term_column, campaign, CAMPAIGN_STATE_COLUMN]].itertuples(index=False):
        text = str(term).strip()
        product, asin = product_and_asin(source_campaign)
        prefix = f"{product} - {asin}" if product and asin else "[Producto] - [ASIN]"
        rows.append({
            "Customer Search Term": text,
            "Campaña origen (inactiva)": source_campaign,
            CAMPAIGN_STATE_COLUMN: state,
            "Producto inferido": product or "—",
            "ASIN inferido": asin or "—",
            "Match Type": match_type,
            "Nombre sugerido": f"{prefix} - SP - KW - {match_type} - {text.title()}",
            **totals.get(term, {}),
        })
    suggested = pd.DataFrame(rows, columns=SUGGESTED_COLUMNS)
    return suggested.sort_values("Spend", ascending=False, kind="mergesort").reset_index(drop=True)


def harvest_candidates(search_terms: pd.DataFrame, coverage: FunnelCoverage, min_orders: int) -> pd.DataFrame:
    """Search terms with at least `min_orders` orders across their campaigns, with the match type to harvest them in
    and whether one of those campaigns is active.

    Exact when the orders reach three times the minimum, or the minimum with ACoS at or under 25%; Phrase otherwise.
    """
    columns = coverage.columns
    term, campaign, orders = columns["search_term"], columns["campaign"], columns["orders"]
    if orders is None:
        raise FunnelInputError("El Search Term Report no trae la columna de órdenes, así que no hay harvest.")
    sales, spend, clicks = columns["sales"], columns["spend"], columns["clicks"]
    acos = acos_column(columns)
    metrics = [column for column in (columns["impressions"], clicks, orders, sales, spend) if column]
    numeric = search_terms[[term, campaign]].copy()
    for column in metrics:
        numeric[column] = numeric_column(search_terms, column)

    sources = numeric.groupby(term)[campaign].agg(
        lambda names: " | ".join(sorted(names.dropna().astype(str).unique()))).rename(SOURCE_CAMPAIGN_COLUMN)
    harvest = numeric.groupby(term, as_index=False)[metrics].sum()
    harvest.insert(1, SOURCE_CAMPAIGN_COLUMN, harvest[term].map(sources))
    harvest.insert(2, ACTIVE_CAMPAIGN_COLUMN, harvest[term].isin(set(coverage.active_terms[term])))
    harvest[acos] = (_ratio(harvest[spend], harvest[sales]) if spend and sales
                     else pd.Series(float("nan"), index=harvest.index))
    harvest[CVR_COLUMN] = (_ratio(harvest[orders], harvest[clicks]) if clicks
                           else pd.Series(float("nan"), index=harvest.index))
    harvest = harvest[harvest[orders] >= min_orders].copy()
    exact = (harvest[orders] >= min_orders * 3) | (harvest[acos] <= EXACT_HARVEST_MAX_ACOS)
    harvest[SUGGESTED_MATCH_COLUMN] = exact.map({True: "Exact", False: "Phrase"})
    return harvest.sort_values(orders, ascending=False, kind="mergesort").reset_index(drop=True)


def orders_and_sales(terms: pd.DataFrame, columns: dict) -> OrdersAndSales:
    """What a set of search term rows sold, e.g. those of the active campaigns against those of the rest."""
    orders, sales = (_plain_number(numeric_column(terms, columns[key]).sum()) if columns[key] else None
                     for key in ("orders", "sales"))
    return OrdersAndSales(orders=orders, sales=sales)


def acos_column(columns: dict) -> str:
    """Where harvest writes the recomputed ACoS: the report's own ACoS column, or the canonical name."""
    return columns["acos"] or ACOS


def product_and_asin(campaign_name) -> tuple[str | None, str | None]:
    """Product and ASIN from a campaign named "Producto - ASIN - ...", or (None, None)."""
    match = _PRODUCT_AND_ASIN.match(str(campaign_name))
    if match is None:
        return None, None
    return match.group(1).strip(), match.group(2).upper()


def campaign_column(frame: pd.DataFrame, name: str) -> str | None:
    """The campaign file's column whose header is `name`, whatever its case and spacing."""
    return next((column for column in frame.columns if str(column).strip().lower() == name), None)


def visible_columns(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame without the hidden ids the Amazon Ads rows carry at the end."""
    return frame[[column for column in frame.columns if not str(column).startswith("_")]]


def _sponsored_products(campaigns: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    type_column = campaign_column(campaigns, "type")
    if type_column is None:
        return campaigns, 0
    is_sponsored = campaigns[type_column].fillna("").astype(str).str.strip().str.casefold().eq(
        SPONSORED_PRODUCTS.casefold())
    return campaigns[is_sponsored], int((~is_sponsored).sum())


def _campaign_keys(values: pd.Series, by_id: bool) -> pd.Series:
    keys = values.fillna("").astype(str).str.strip()
    return keys if by_id else keys.str.lower()


def _term_totals(gap_terms: pd.DataFrame, columns: dict) -> dict:
    """Search term -> its clicks, spend, orders and sales summed over its gap rows."""
    totals = pd.DataFrame({"term": gap_terms[columns["search_term"]]})
    for label, key in (("Clicks", "clicks"), ("Spend", "spend"), ("Orders", "orders"), ("Sales", "sales")):
        totals[label] = numeric_column(gap_terms, columns[key])
    summed = totals.groupby("term").sum()
    return {term: {label: _plain_number(value) for label, value in row.items()} for term, row in summed.iterrows()}


def _ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return (numerator / denominator.where(denominator > 0) * 100).round(2)


def _plain_number(value):
    number = float(value)
    return int(number) if number.is_integer() else round(number, 2)
