"""PPC Insights rules: which ASIN each search term belongs to, its metrics, its health score and the AM's parameters.

No Streamlit and no AI: the page, the analysis worker and the MCP server build the same numbers from here, or
the analysis the worker stores would never match what the page shows.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field

import pandas as pd

from core.amazon_ads.advertised_asins import WITHOUT_ASIN, attribute_asins, grouped_asin_counts
from core.search_term.candidates import uses_dollar_price

# Where the report's ASINs came from: its own column, Amazon's product ads and campaign names, or nowhere.
FROM_FILE = "file"
ATTRIBUTED = "attributed"
NO_ASINS = "none"
RESOLVED_ASIN_COLUMN = "_asin"
# Stands for the whole report when no row has an ASIN; the page and the agent read it as the account.
WHOLE_ACCOUNT = "ALL"

# Points each part of the health score can give, and what it gives when its source is missing.
MAX_POINTS = {"cvr": 25, "buybox": 20, "acos": 25, "funnel": 15, "imp_share": 15}
NEUTRAL_POINTS = {"cvr": 12.0, "buybox": 10.0, "acos": 12.0, "funnel": 7, "imp_share": 7}
# A term that spent more than this with no order is a bleeder; wasted spend adds up the top ones.
BLEEDER_MIN_SPEND = 5
BLEEDERS_KEPT = 10
DEFAULT_TARGET_ACOS = 25
DEFAULT_DOLLAR_PRICE = 15.0


@dataclass(frozen=True)
class ResolvedAsins:
    """The report with its ASIN column, where the ASINs came from, and the % of spend per row origin.

    `grouped_asins` maps an ASIN taken from campaign names to how many ASINs its several-ASIN ad groups advertise.
    """

    frame: pd.DataFrame
    column: str | None
    source: str
    spend_share: dict
    report_spend: float = 0.0
    grouped_asins: dict = field(default_factory=dict)


def find_column(df, keyword, exclude="b2b"):
    for c in df.columns:
        cl = c.lower()
        if keyword.lower() in cl:
            if exclude and exclude.lower() in cl:
                continue
            return c
    return None


def clean_numbers(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(r"[$%,]", "", regex=True)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


def resolve_asins(str_df, ad_group_asins: dict | None = None) -> ResolvedAsins:
    """The file's own ASIN column when it has one; otherwise Amazon's product ads, then the campaign name."""
    spend_column = find_column(str_df, "Spend")
    spend = clean_numbers(str_df[spend_column]) if spend_column else pd.Series(0.0, index=str_df.index)
    report_spend = float(spend.sum())
    file_column = find_column(str_df, "Advertised ASIN") or find_column(str_df, "ASIN")
    if file_column is not None:
        has_asin = str_df[file_column].fillna("").astype(str).str.strip() != ""
        return ResolvedAsins(str_df, file_column, FROM_FILE,
                             _spend_share(spend, has_asin.map({True: FROM_FILE, False: WITHOUT_ASIN})), report_spend)

    ad_group_asins = ad_group_asins or {}
    campaign_column = find_column(str_df, "Campaign Name") or find_column(str_df, "Campaign")
    attribution = attribute_asins(str_df, ad_group_asins, campaign_column)
    share = _spend_share(spend, attribution.origins)
    if not attribution.asins.notna().any():
        return ResolvedAsins(str_df, None, NO_ASINS, share, report_spend)
    resolved = str_df.copy()
    resolved[RESOLVED_ASIN_COLUMN] = attribution.asins
    return ResolvedAsins(resolved, RESOLVED_ASIN_COLUMN, ATTRIBUTED, share, report_spend,
                         grouped_asin_counts(str_df, attribution, ad_group_asins))


def _spend_share(spend: pd.Series, origins: pd.Series) -> dict:
    """origin -> % of the report's spend, for the origins that have any."""
    total = float(spend.sum())
    if total <= 0:
        return {}
    by_origin = spend.groupby(origins).sum()
    return {str(origin): round(float(value) / total * 100, 1) for origin, value in by_origin.items() if value > 0}


def health_score_parts(acos, target_acos, cvr, buybox, funnel_complete, imp_share) -> dict:
    """The five parts of the health score; a part without its source gives its NEUTRAL_POINTS."""
    if cvr and cvr > 0:
        cvr_score = min(MAX_POINTS["cvr"], (cvr / 15) * MAX_POINTS["cvr"])
    else:
        cvr_score = NEUTRAL_POINTS["cvr"]

    if buybox is not None:
        bb_score = min(MAX_POINTS["buybox"], (buybox / 95) * MAX_POINTS["buybox"]) if buybox > 0 else 5.0
    else:
        bb_score = NEUTRAL_POINTS["buybox"]

    if acos is not None and acos > 0 and target_acos > 0:
        ratio = acos / target_acos
        if ratio <= 1:
            acos_score = 25
        elif ratio <= 1.5:
            acos_score = 18
        elif ratio <= 2:
            acos_score = 10
        else:
            acos_score = max(0, 25 - ratio * 8)
    else:
        acos_score = NEUTRAL_POINTS["acos"]

    if funnel_complete is None:
        funnel_score = NEUTRAL_POINTS["funnel"]
    elif funnel_complete:
        funnel_score = 15
    else:
        funnel_score = 8

    if imp_share is not None:
        if imp_share >= 30:
            is_score = 15
        elif imp_share >= 10:
            is_score = 10
        elif imp_share > 0:
            is_score = 5
        else:
            is_score = 2
    else:
        is_score = NEUTRAL_POINTS["imp_share"]

    return {"cvr": cvr_score, "buybox": bb_score, "acos": acos_score, "funnel": funnel_score, "imp_share": is_score}


def health_score(acos, target_acos, cvr, buybox, funnel_complete, imp_share) -> int:
    return round(sum(health_score_parts(acos, target_acos, cvr, buybox, funnel_complete, imp_share).values()))


def analyze_asins(str_df, sqp_df, br_df, camp_df, target_acos, asin_column=None):
    asin_data = {}

    # Detect STR columns
    col_asin    = asin_column or find_column(str_df, "Advertised ASIN") or find_column(str_df, "ASIN")
    col_term    = find_column(str_df, "Customer Search Term") or find_column(str_df, "Search Term")
    col_spend   = find_column(str_df, "Spend")
    col_sales   = find_column(str_df, "7 Day Total Sales") or find_column(str_df, "Sales")
    col_orders  = find_column(str_df, "7 Day Total Orders") or find_column(str_df, "Orders")
    col_clicks  = find_column(str_df, "Clicks")

    # Clean numeric STR columns
    for col in [col_spend, col_sales, col_orders, col_clicks]:
        if col and str_df[col].dtype == object:
            str_df[col] = clean_numbers(str_df[col])

    # Determine ASINs
    if col_asin and col_asin in str_df.columns:
        asins = str_df[col_asin].dropna().unique().tolist()
        asins = [a for a in asins if str(a).startswith("B0") or (len(str(a)) == 10 and str(a)[0] == "B")]
    else:
        # No ASIN column — treat entire STR as one group
        asins = [WHOLE_ACCOUNT]

    for asin in asins:
        if col_asin and col_asin in str_df.columns and asin != WHOLE_ACCOUNT:
            adf = str_df[str_df[col_asin] == asin].copy()
        else:
            adf = str_df.copy()

        # STR metrics
        spend  = float(adf[col_spend].sum())  if col_spend  else 0.0
        sales  = float(adf[col_sales].sum())  if col_sales  else 0.0
        orders = float(adf[col_orders].sum()) if col_orders else 0.0
        clicks = float(adf[col_clicks].sum()) if col_clicks else 0.0

        acos = (spend / sales * 100) if sales > 0 else None
        cvr  = (orders / clicks * 100) if clicks > 0 else None

        # Top keywords by sales
        top_kws = pd.DataFrame()
        if col_term and col_sales and col_term in adf.columns:
            top_kws = (
                adf.groupby(col_term, as_index=False)
                .agg({
                    col_sales:  "sum",
                    col_spend:  "sum" if col_spend else None,
                    col_orders: "sum" if col_orders else None,
                })
                .dropna(subset=[col_sales])
                .nlargest(5, col_sales)
                .rename(columns={col_term: "Search Term", col_sales: "Sales",
                                  col_spend: "Spend", col_orders: "Orders"})
            )

        # Bleeders — spend with 0 orders
        bleeders = pd.DataFrame()
        if col_term and col_spend and col_orders and col_term in adf.columns:
            mask = (adf[col_spend] > BLEEDER_MIN_SPEND) & (adf[col_orders] == 0)
            bleeders = (
                adf[mask][[col_term, col_spend]]
                .rename(columns={col_term: "Search Term", col_spend: "Spend"})
                .sort_values("Spend", ascending=False)
                .head(BLEEDERS_KEPT)
            )
        wasted_spend = float(bleeders["Spend"].sum()) if not bleeders.empty else 0.0

        # SQP metrics
        imp_share     = None
        purchase_share = None
        sqp_gaps       = 0

        if sqp_df is not None:
            col_q   = find_column(sqp_df, "Search Query")
            col_ti  = find_column(sqp_df, "Total Impressions") or find_column(sqp_df, "Impressions")
            col_bi  = next(
                (c for c in sqp_df.columns if "brand" in c.lower() and "impression" in c.lower()),
                None,
            )
            col_tp  = find_column(sqp_df, "Total Purchases") or find_column(sqp_df, "Total Purchase")
            col_bp  = next(
                (c for c in sqp_df.columns if "brand" in c.lower() and "purchase" in c.lower()),
                None,
            )

            if col_ti and col_bi:
                for col in [col_ti, col_bi, col_tp, col_bp]:
                    if col and sqp_df[col].dtype == object:
                        sqp_df[col] = clean_numbers(sqp_df[col])
                total_imp = float(sqp_df[col_ti].sum()) if col_ti else 0
                brand_imp = float(sqp_df[col_bi].sum()) if col_bi else 0
                imp_share = (brand_imp / total_imp * 100) if total_imp > 0 else 0.0

                if col_tp and col_bp:
                    total_pur = float(sqp_df[col_tp].sum())
                    brand_pur = float(sqp_df[col_bp].sum())
                    purchase_share = (brand_pur / total_pur * 100) if total_pur > 0 else 0.0

                if col_q and col_ti and col_bi:
                    gap_mask = (sqp_df[col_ti] > 500) & (sqp_df[col_bi] == 0)
                    sqp_gaps = int(gap_mask.sum())

        # BR metrics
        sessions  = None
        buybox    = None
        br_units  = None
        br_cvr    = None

        if br_df is not None:
            col_br_asin = (find_column(br_df, "(Child) ASIN") or
                           find_column(br_df, "Child ASIN") or
                           find_column(br_df, "ASIN"))
            if col_br_asin and asin != WHOLE_ACCOUNT:
                br_row = br_df[br_df[col_br_asin].astype(str).str.strip() == str(asin)]
            else:
                br_row = br_df

            if not br_row.empty:
                col_sess = find_column(br_row, "Sessions")
                col_bb   = next(
                    (c for c in br_row.columns
                     if ("buy box" in c.lower() or "buybox" in c.lower() or "featured offer" in c.lower())
                     and "b2b" not in c.lower()),
                    None,
                )
                col_units = find_column(br_row, "Units Ordered")

                if col_sess:
                    s = br_row[col_sess].iloc[0]
                    sessions = float(clean_numbers(pd.Series([s])).iloc[0])
                if col_bb:
                    bb = br_row[col_bb].iloc[0]
                    buybox = float(clean_numbers(pd.Series([bb])).iloc[0])
                if col_units and col_sess and sessions and sessions > 0:
                    units = float(clean_numbers(pd.Series([br_row[col_units].iloc[0]])).iloc[0])
                    br_units = units
                    br_cvr = (units / sessions * 100)

        # Campaign coverage
        n_campaigns    = None
        campaign_types = None
        funnel_complete = None

        if camp_df is not None:
            col_cname  = find_column(camp_df, "Campaign Name") or find_column(camp_df, "Campaign")
            col_state  = find_column(camp_df, "State") or find_column(camp_df, "Status")
            col_target = find_column(camp_df, "Targeting Type") or find_column(camp_df, "Campaign Type")

            if col_cname:
                cdf = camp_df.copy()
                if col_state:
                    cdf = cdf[cdf[col_state].astype(str).str.lower() == "enabled"]

                if asin != WHOLE_ACCOUNT:
                    mask = cdf[col_cname].astype(str).str.lower().str.contains(asin.lower(), na=False)
                    cdf = cdf[mask]

                n_campaigns = len(cdf)
                types_found = set()
                for cname in cdf[col_cname].astype(str):
                    nl = cname.lower()
                    if "auto" in nl or "discovery" in nl:
                        types_found.add("Auto")
                    if "broad" in nl:
                        types_found.add("Broad")
                    if "phrase" in nl:
                        types_found.add("Phrase")
                    if "exact" in nl:
                        types_found.add("Exact")
                    if "pat" in nl or "asin" in nl or "conq" in nl or "competitor" in nl:
                        types_found.add("PAT")

                if col_target:
                    for ttype in cdf[col_target].astype(str):
                        tl = ttype.lower()
                        if "auto" in tl:
                            types_found.add("Auto")
                        if "manual" in tl:
                            types_found.add("Manual")

                campaign_types = ", ".join(sorted(types_found)) if types_found else "—"
                funnel_complete = ("Auto" in types_found and "Exact" in types_found) or \
                                  ("Auto" in types_found and "Broad" in types_found and "Exact" in types_found)

        parts = health_score_parts(
            acos=acos,
            target_acos=target_acos,
            cvr=cvr if cvr is not None else br_cvr,
            buybox=buybox,
            funnel_complete=funnel_complete,
            imp_share=imp_share,
        )

        asin_data[asin] = {
            "spend":          spend,
            "sales":          sales,
            "orders":         orders,
            "clicks":         clicks,
            "acos":           acos,
            "cvr":            cvr if cvr is not None else br_cvr,
            "wasted_spend":   wasted_spend,
            "top_kws":        top_kws,
            "bleeders":       bleeders,
            "imp_share":      imp_share,
            "purchase_share": purchase_share,
            "sqp_gaps":       sqp_gaps,
            "sessions":       sessions,
            "buybox":         buybox,
            "br_units":       br_units,
            "n_campaigns":    n_campaigns,
            "campaign_types": campaign_types,
            "funnel_complete":funnel_complete,
            "health_score":   round(sum(parts.values())),
            "health_parts":   parts,
        }

    return asin_data


@dataclass(frozen=True)
class InsightsAnalysisParams:
    """What the AM sets on the page that changes the analysis."""

    target_acos: int
    price: float | None

    @classmethod
    def defaults(cls, currency_code: str) -> InsightsAnalysisParams:
        # A price of 15 means nothing in pesos or yen, so only dollar accounts start with one.
        return cls(DEFAULT_TARGET_ACOS, DEFAULT_DOLLAR_PRICE if uses_dollar_price(currency_code) else None)

    @classmethod
    def from_dict(cls, values: dict, currency_code: str) -> InsightsAnalysisParams:
        base = cls.defaults(currency_code)
        try:
            target_acos = int(values.get("target_acos", base.target_acos))
        except (TypeError, ValueError):
            target_acos = base.target_acos
        return cls(target_acos, _price(values.get("price", base.price)))

    def as_dict(self) -> dict:
        return {"target_acos": self.target_acos, "price": self.price}

    @property
    def digest(self) -> str:
        blob = json.dumps(self.as_dict(), sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _price(value) -> float | None:
    if value is None or value == "":
        return None
    try:
        price = float(value)
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None
