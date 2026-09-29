"""Plan de Acción of Análisis Cruzado: the action the module suggests for each SQP query.

Each query keeps the market figures of the SQP, the figures its search term had in the account's Amazon Ads report,
the IDs of the campaign that spent most on it and INV-11's marks. The rules are the page's, moved out of render();
the exact mark now reads the query itself against the account's SP listing, so a query that runs as an exact keyword
without clicks is marked too.
"""
from __future__ import annotations

import re
import unicodedata
from collections.abc import Mapping
from dataclasses import dataclass

import pandas as pd

from core.bulk.export import aggregate_str_with_top_campaign
from core.cross_analysis.ranking_guards import ALREADY_EXACT, NOT_NEGATABLE, ORIGIN, RANKING_KEYWORD, exact_marks
from core.ppc_metrics import acos_series, calc_cvr
from core.search_term.frame import AD_GROUP_NAME, CAMPAIGN_NAME, MATCH_TYPE, PORTFOLIO_NAME, SEARCH_TERM, SPEND

QUERY = "Search Query"
MARKET_IMPRESSIONS = "Impressions: Total Count"
QUERY_SCORE = "Search Query Score"
MARKET_CLICKS = "Clicks: Total Count"
MARKET_PURCHASES = "Purchases: Total Count"
MARKET_PURCHASE_RATE = "Purchases: Purchase Rate %"
BRAND_PURCHASES = "Purchases: Brand Count"
BRAND_PURCHASE_SHARE = "Purchases: Brand Share %"
BRAND_CLICKS = "Clicks: Brand Count"
BRAND_IMPRESSIONS = "Impressions: Brand Count"
OPPORTUNITY_SCORE = "Opportunity Score"
MARKET_CVR = "_cvr_mercado"
BRAND_CVR = "_cvr_marca"
FUNNEL_DIAGNOSIS = "_diagnostico_funnel"
FUNNEL_NO_DATA = "Sin datos"
FUNNEL_LIKE_MARKET = "Convertís como el mercado"
FUNNEL_BELOW_MARKET = "Convertís por debajo"
# Below this share of the market's conversion the brand converts worse than the query; a default, not a measured one.
CVR_MARKET_PARITY = 0.8

QUERY_TYPE = "Tipo"
BRAND_QUERY = "Marca"
GENERIC_QUERY = "Genérica"
ACTION = "Acción"
IN_SEARCH_TERMS = "En STR"
IN_SEARCH_TERMS_YES = "✅ Sí"
IN_SEARCH_TERMS_NO = "❌ No"
CAMPAIGN_COUNT = "_n_campaigns"
TERM_KEY = "_term_lower"
TERM_SPEND = "_str_spend"
TERM_SALES = "_str_sales"
TERM_ORDERS = "_str_orders"
TERM_ACOS = "_acos"

ACTION_ASIN = "⚫ ASIN (PT)"
ACTION_CONQUEST = "⚔️ CONQUEST (cross-brand)"
ACTION_BRAND_NO_DATA = "❔ SIN DATA (marca, sin métrica BS)"
ACTION_DEFEND = "🛡️ DEFENDER marca"
ACTION_BRAND_OK = "🏆 BRAND PURE OK"
ACTION_SCALE = "⚡ ESCALAR"
ACTION_ADD = "➕ AGREGAR keyword"
ACTION_DO_NOT_ATTACK = "🚫 NO ATACAR"
ACTION_INVESTIGATE = "🔍 INVESTIGAR"
ACTION_LOWER_BID = "⬇️ BAJAR BID"
ACTION_MONITOR = "👁️ MONITOREAR"

# What each plan row inherits from its term's top-spend row: the IDs, the keyword's own text, the portfolio and
# INV-11.1/.3's marks.
INHERITED_COLUMNS = ("_campaign_id", "_ad_group_id", "_keyword_id", "_keyword_type", "_keyword_text", PORTFOLIO_NAME,
                     "_origin_match_type", ORIGIN, NOT_NEGATABLE, RANKING_KEYWORD)

BRAND_DEFENSE_SHARE = 70
SCALE_ACOS_FACTOR = 0.7
SCALE_MIN_ORDERS = 2
LOWER_BID_ACOS_FACTOR = 2
DO_NOT_ATTACK_MIN_PURCHASES = 500
INVESTIGATE_MIN_OPPORTUNITY = 40
INVESTIGATE_MAX_SHARE = 5
INVESTIGATE_MAX_PURCHASES = 300

_ASIN_QUERY = re.compile(r"^b0[a-z0-9]{8}$")
# Filled with 0 before the plan, as the page's shared block always did; the brand columns keep NaN = no data.
_FILLED_SQP_COLUMNS = (MARKET_IMPRESSIONS, QUERY_SCORE, MARKET_PURCHASES, MARKET_PURCHASE_RATE, MARKET_CLICKS)
_SPARSE_SQP_COLUMNS = (BRAND_PURCHASES, BRAND_PURCHASE_SHARE)
_SUMMED_ON_DEDUPE = (MARKET_IMPRESSIONS, MARKET_PURCHASES, BRAND_PURCHASES, MARKET_CLICKS)


@dataclass(frozen=True)
class ActionPlanParams:
    target_acos: float
    brand_terms: tuple[str, ...] = ()  # accentless, lower case
    competitors: tuple[str, ...] = ()
    catalog_asins: tuple[str, ...] = ()


def accentless_text(value) -> str:
    """Lower case, without accents and with single spaces: how brand, competitor and ASIN terms are matched."""
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    text = unicodedata.normalize("NFKD", str(value)).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", text).strip().lower()


def comma_terms(text: str) -> tuple[str, ...]:
    """The accentless terms of a comma-separated input, without the empty ones."""
    terms = (accentless_text(part) for part in str(text or "").split(","))
    return tuple(term for term in terms if term)


def query_types(queries: pd.Series, brand_terms: tuple[str, ...]) -> pd.Series:
    """Marca when the query mentions one of the brand terms, Genérica otherwise."""
    def query_type(query) -> str:
        text = accentless_text(query)
        return BRAND_QUERY if text and any(term in text for term in brand_terms) else GENERIC_QUERY
    return queries.map(query_type)


def numeric_sqp(sqp: pd.DataFrame) -> pd.DataFrame:
    """A copy of the SQP with its figures as numbers: market counts filled with 0, brand counts NaN when missing."""
    numeric = sqp.copy()
    for column in _FILLED_SQP_COLUMNS:
        if column in numeric.columns:
            numeric[column] = pd.to_numeric(numeric[column], errors="coerce").fillna(0)
    for column in _SPARSE_SQP_COLUMNS:
        if column in numeric.columns:
            numeric[column] = pd.to_numeric(numeric[column], errors="coerce")
    return numeric


def with_funnel_diagnosis(sqp: pd.DataFrame) -> pd.DataFrame:
    """A copy of the numeric SQP with the market's and the brand's CVR and whether the brand converts like the market.

    The brand's CVR mixes organic and paid clicks, so it is the whole brand's in that query, not its ads'.
    """
    diagnosed = sqp.copy()
    for column in (BRAND_CLICKS, BRAND_PURCHASES):
        if column in diagnosed.columns:
            diagnosed[column] = pd.to_numeric(diagnosed[column], errors="coerce")
    market_cvr = (_cvr(diagnosed[MARKET_PURCHASES], diagnosed[MARKET_CLICKS])
                  if MARKET_PURCHASES in diagnosed.columns and MARKET_CLICKS in diagnosed.columns else None)
    brand_cvr = (_cvr(diagnosed[BRAND_PURCHASES], diagnosed[BRAND_CLICKS])
                 if BRAND_PURCHASES in diagnosed.columns and BRAND_CLICKS in diagnosed.columns else None)
    if market_cvr is not None and brand_cvr is not None:
        diagnosed[FUNNEL_DIAGNOSIS] = [_funnel_diagnosis(market, brand) for market, brand in zip(market_cvr, brand_cvr)]
    # Rounded after the diagnosis, which reads the exact rates.
    if market_cvr is not None:
        diagnosed[MARKET_CVR] = market_cvr.round(2)
    if brand_cvr is not None:
        diagnosed[BRAND_CVR] = brand_cvr.round(2)
    return diagnosed


def _cvr(purchases: pd.Series, clicks: pd.Series) -> pd.Series:
    # An all-None column would stay object dtype, which Arrow cannot render.
    return pd.to_numeric(pd.Series([calc_cvr(purchase, click) for purchase, click in zip(purchases, clicks)],
                                   index=purchases.index), errors="coerce")


def _funnel_diagnosis(market_cvr, brand_cvr) -> str:
    if pd.isna(market_cvr) or pd.isna(brand_cvr):
        return FUNNEL_NO_DATA
    return FUNNEL_LIKE_MARKET if brand_cvr >= market_cvr * CVR_MARKET_PARITY else FUNNEL_BELOW_MARKET


def search_term_totals(search_terms: pd.DataFrame, *, sales_column: str, orders_column: str) -> pd.DataFrame:
    """One row per search term: its totals, and the campaign, ad group, IDs and marks of its top-spend row."""
    terms = search_terms.copy()
    for column in (SPEND, sales_column, orders_column):
        terms[column] = pd.to_numeric(terms[column], errors="coerce").fillna(0)
    totals = aggregate_str_with_top_campaign(
        terms, term_col=SEARCH_TERM, spend_col=SPEND, campaign_col=CAMPAIGN_NAME, ad_group_col=AD_GROUP_NAME,
        match_type_col=MATCH_TYPE, extra_agg={orders_column: "sum", sales_column: "sum"},
        extra_inherit=list(INHERITED_COLUMNS),
    )
    totals[TERM_KEY] = totals[SEARCH_TERM].astype(str).str.lower().str.strip()
    # INV-7: NaN where the term sold nothing, never 0.
    totals[TERM_ACOS] = acos_series(totals[SPEND], totals[sales_column])
    return totals.rename(columns={SPEND: TERM_SPEND, sales_column: TERM_SALES, orders_column: TERM_ORDERS})


def suggested_action(query: Mapping, term: Mapping | None, params: ActionPlanParams) -> str:
    """The action for one deduplicated SQP query.

    `term` is the query's row of search_term_totals, None when the query is not a search term of the report.
    """
    query_text = accentless_text(query.get(QUERY, ""))
    market_purchases = query.get(MARKET_PURCHASES, 0)
    brand_purchases = query.get(BRAND_PURCHASES, 0)
    brand_share = query.get(BRAND_PURCHASE_SHARE, 0)
    opportunity = query.get(OPPORTUNITY_SCORE, 0)
    in_search_terms = term is not None

    # BUG-5: an ASIN or one of the account's catalog ASINs is a product target, not a keyword.
    if _ASIN_QUERY.match(query_text.replace(" ", "")) or (
            params.catalog_asins and any(asin in query_text for asin in params.catalog_asins)):
        return ACTION_ASIN

    is_brand = query.get(QUERY_TYPE, GENERIC_QUERY) == BRAND_QUERY or (
        params.brand_terms and any(term_text in query_text for term_text in params.brand_terms))
    if is_brand:
        if params.competitors and any(competitor in query_text for competitor in params.competitors):
            return ACTION_CONQUEST
        if pd.isna(brand_share):
            return ACTION_BRAND_NO_DATA
        return ACTION_DEFEND if brand_share < BRAND_DEFENSE_SHARE else ACTION_BRAND_OK

    acos = term[TERM_ACOS] if in_search_terms else None
    orders = term[TERM_ORDERS] if in_search_terms else 0
    spend = term[TERM_SPEND] if in_search_terms else 0
    sales = term[TERM_SALES] if in_search_terms else 0
    # BUG-6: scaling needs positive market evidence; NaN is no data, not relevance.
    relevance_confirmed = ((pd.notna(brand_share) and brand_share > 0)
                           or (pd.notna(brand_purchases) and brand_purchases > 0))
    if (in_search_terms and pd.notna(acos) and acos <= params.target_acos * SCALE_ACOS_FACTOR
            and orders >= SCALE_MIN_ORDERS and relevance_confirmed):
        return ACTION_SCALE
    if not in_search_terms and pd.notna(brand_purchases) and brand_purchases > 0 and market_purchases > 0:
        return ACTION_ADD
    if market_purchases > DO_NOT_ATTACK_MIN_PURCHASES and (pd.isna(brand_share) or brand_share == 0):
        return ACTION_DO_NOT_ATTACK
    if (opportunity > INVESTIGATE_MIN_OPPORTUNITY and (pd.isna(brand_share) or brand_share < INVESTIGATE_MAX_SHARE)
            and market_purchases < INVESTIGATE_MAX_PURCHASES):
        return ACTION_INVESTIGATE
    # INV-6: spend without sales has a NaN ACoS, so it is caught before the ACoS rule; negating would need INV-11.
    if in_search_terms and spend > 0 and sales <= 0:
        return ACTION_LOWER_BID
    if in_search_terms and pd.notna(acos) and acos > params.target_acos * LOWER_BID_ACOS_FACTOR:
        return ACTION_LOWER_BID
    return ACTION_MONITOR


def build_action_plan(sqp: pd.DataFrame, search_terms: pd.DataFrame, exact_keywords: frozenset[str] | None,
                      params: ActionPlanParams, *, sales_column: str, orders_column: str) -> pd.DataFrame:
    """Every SQP query once, with its action, whether it is in the report, its term's figures, IDs and marks.

    `sqp` carries the Tipo column; `search_terms` is the canonical frame with INV-11's marks.
    """
    totals = search_term_totals(search_terms, sales_column=sales_column, orders_column=orders_column)
    first_by_term = totals.drop_duplicates(TERM_KEY)
    terms_by_key = {key: row for key, row in zip(first_by_term[TERM_KEY], first_by_term.to_dict("records"))}

    plan = _with_opportunity_score(_deduplicated(numeric_sqp(sqp)))
    keys = plan[QUERY].astype(str).str.lower().str.strip()
    plan[ACTION] = [suggested_action(row, terms_by_key.get(key), params)
                    for key, row in zip(keys, plan.to_dict("records"))]
    plan[IN_SEARCH_TERMS] = keys.isin(terms_by_key.keys()).map({True: IN_SEARCH_TERMS_YES,
                                                                 False: IN_SEARCH_TERMS_NO})
    carried = [column for column in (*INHERITED_COLUMNS, CAMPAIGN_NAME, AD_GROUP_NAME, MATCH_TYPE, CAMPAIGN_COUNT,
                                     TERM_SPEND, TERM_SALES, TERM_ORDERS, TERM_ACOS) if column in first_by_term.columns]
    plan[TERM_KEY] = keys
    plan = plan.merge(first_by_term[[TERM_KEY, *carried]], on=TERM_KEY, how="left")
    for column in (NOT_NEGATABLE, RANKING_KEYWORD):
        if column in plan.columns:
            plan[column] = plan[column].eq(True)
    plan[ALREADY_EXACT] = exact_marks(plan[QUERY], exact_keywords)
    return plan


def _deduplicated(sqp: pd.DataFrame) -> pd.DataFrame:
    """BUG-2/3: a multi-month SQP repeats a query; volumes add up, the share averages, the rest keeps the first."""
    if QUERY not in sqp.columns:
        return sqp
    aggregations = {column: ("sum" if column in _SUMMED_ON_DEDUPE else "mean" if column == BRAND_PURCHASE_SHARE
                             else "first")
                    for column in sqp.columns if column != QUERY}
    return sqp.groupby(QUERY, as_index=False).agg(aggregations)


def _with_opportunity_score(plan: pd.DataFrame) -> pd.DataFrame:
    if not all(column in plan.columns for column in (MARKET_IMPRESSIONS, MARKET_CLICKS, BRAND_PURCHASE_SHARE)):
        return plan
    scored = plan.copy()
    impressions = scored[MARKET_IMPRESSIONS].fillna(0)
    clicks = scored[MARKET_CLICKS].fillna(0)
    impressions_scaled = (impressions - impressions.min()) / (impressions.max() - impressions.min() + 1e-9)
    clicks_scaled = (clicks - clicks.min()) / (clicks.max() - clicks.min() + 1e-9)
    share_scaled = scored[BRAND_PURCHASE_SHARE].fillna(0) / 100
    # 0-100 like Tab 1's score: INVESTIGAR's threshold of 40 is on that scale.
    scored[OPPORTUNITY_SCORE] = ((impressions_scaled * 0.4 + clicks_scaled * 0.3 + share_scaled * 0.3) * 100).round(1)
    return scored
