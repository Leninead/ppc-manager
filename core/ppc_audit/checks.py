"""PPC Audit Pro's rules over AuditFrames: KPIs, structure checks, segments, deep checks and Target Graduation.

Pure pandas, no Streamlit: the page, its Excel, its AI payload and the MCP read the same AuditResult. A metric the
source does not know is NaN, and it stays out of every sum and every flag instead of counting as zero.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from core.ppc_audit.frames import (
    AD_GROUP_ID,
    ASIN,
    BIDDING_STRATEGY,
    CAMPAIGN_ID,
    CAMPAIGN_NAME,
    CLICKS,
    EXPRESSION,
    IMPRESSIONS,
    KEYWORD_TEXT,
    MATCH_TYPE,
    ORDERS,
    PERCENTAGE,
    PLACEMENT,
    SALES,
    SB_KEYWORDS,
    SB_SEARCH_TERMS,
    SD_TARGETS,
    SEARCH_TERM,
    SP_TARGET_METRICS,
    SP_TARGETS,
    SPEND,
    STATE,
    TARGETING_TYPE,
    AuditFrames,
)

PRODUCTS = ("SP", "SB", "SD")
ENABLED = "enabled"
PAUSED = "paused"
ARCHIVED = "archived"
MANUAL = "manual"
AUTO = "auto"
AUTO_GROUPS = ("close-match", "loose-match", "substitutes", "complements")
SEGMENT_COLUMNS = ("Segmento", "# Targets", "Spend", "Sales", "ACoS", "Clicks", "Orders", "CTR", "CVR", "CPC",
                   "% Spend")
TOP_CAMPAIGN_COLUMNS = (CAMPAIGN_NAME, TARGETING_TYPE, SPEND, SALES, "ACOS", ORDERS)
TOP_CAMPAIGNS = 5
TOP_WASTED_TERMS = 5
TOP_DUPLICATES = 10
WASTED_TERM_COLUMNS = (SEARCH_TERM, SPEND, CLICKS, IMPRESSIONS)
MIXED_MATCH_COLUMNS = (CAMPAIGN_NAME, "Match Types", "Keywords")
DUPLICATE_COLUMNS = ("Keyword", MATCH_TYPE, "# Campañas", "Spend_Total", "Sales_Total")
TARGET_TYPE_COLUMNS = ("Tipo", "Targets", SPEND, SALES, "ACoS", "% Spend")
PLACEMENT_COLUMNS = (PLACEMENT, "Campañas", "Promedio", "Min", "Max", "Con_Ajuste")
SKAG_COLUMNS = ("Tipo", "Campañas", "Spend_Total", "% Spend")
CAMPAIGN_IMPRESSIONS = "Campaign Impressions"
RECOMMENDATION = "Recomendación"

GRADUATE_PAUSED = "⏸️ YA PAUSADO"
GRADUATE_KEEP = "🛡️ MANTENER — keyword de marca"
GRADUATE_RAISE = "🔼 SUBIR BID — tuvo ventas, bid probable bajo"
GRADUATE_PAUSE = "🔴 PAUSAR — gastó sin convertir"
GRADUATE_SKAG = "🟡 GRADUAR A SKAG — mover a campaña propia con bid más alto"
# The recommendations without their emoji and hint, in the order the AM acts on them.
GRADUATION_LABELS = {GRADUATE_RAISE: "SUBIR BID", GRADUATE_PAUSE: "PAUSAR", GRADUATE_SKAG: "GRADUAR A SKAG",
                     GRADUATE_KEEP: "MANTENER", GRADUATE_PAUSED: "YA PAUSADO"}

AUTO_FROM_TARGETING = "targeting"
AUTO_FROM_SEARCH_TERMS = "search_terms"

# The API's placement codes as Campaign Manager names them; a Bulk File's own labels pass through.
PLACEMENT_LABELS = {
    "PLACEMENT_TOP": "Top of Search",
    "PLACEMENT_PRODUCT_PAGE": "Product Pages",
    "PLACEMENT_REST_OF_SEARCH": "Rest of Search",
    "SITE_AMAZON_BUSINESS": "Amazon Business",
}
_REVENUE_COLUMNS = ("Ordered Product Sales", "Ordered Product Sales Amount", "ordered product sales")
_SD_RETARGETING = "retarget|remarketing"
_SD_AUDIENCE = "audience"


@dataclass(frozen=True)
class ProductTotals:
    spend: float
    sales: float
    impressions: float
    clicks: float
    orders: float
    campaigns: int
    # Campaigns whose metrics the source does not know: they are out of the sums above.
    unknown: int


@dataclass(frozen=True)
class BusinessReportFigures:
    revenue: float
    organic_sales: float
    organic_pct: float
    tacos: float


@dataclass(frozen=True)
class WasteLine:
    waste: float  # spend of the rows that spent without selling
    count: int    # how many rows did
    spend: float  # all the spend of the rows


@dataclass(frozen=True)
class TargetWaste:
    # None where the source lacks the product's targets.
    sp: WasteLine | None
    sb: WasteLine | None
    sd: WasteLine | None
    total_waste: float
    pct: float


@dataclass(frozen=True)
class SearchTermWaste:
    sp: WasteLine | None
    sb: WasteLine | None
    total_waste: float
    # Over SP's search terms only, as the card has always said.
    pct: float
    top_terms: pd.DataFrame


@dataclass(frozen=True, eq=False)
class AuditResult:
    totals: dict[str, ProductTotals]
    business_report: BusinessReportFigures | None
    mixed_match: pd.DataFrame
    sp_match_types: dict[str, int]
    sb_match_types: dict[str, int]
    target_waste: TargetWaste
    search_term_waste: SearchTermWaste
    sp_segments: pd.DataFrame
    sb_segments: pd.DataFrame
    sd_segments: pd.DataFrame
    # Where the AUTO segments came from: the auto targeting groups, the search terms of auto campaigns, or "".
    auto_segments_source: str
    top_campaigns: pd.DataFrame
    target_types: pd.DataFrame
    duplicates: pd.DataFrame
    placements: pd.DataFrame
    bidding_strategies: pd.DataFrame
    skag: pd.DataFrame
    graduation: pd.DataFrame

    @property
    def mixed_match_campaigns(self) -> list[str]:
        return self.mixed_match[CAMPAIGN_NAME].astype(str).tolist()

    @property
    def spend(self) -> float:
        return sum(totals.spend for totals in self.totals.values())

    @property
    def sales(self) -> float:
        return sum(totals.sales for totals in self.totals.values())

    @property
    def impressions(self) -> float:
        return sum(totals.impressions for totals in self.totals.values())

    @property
    def clicks(self) -> float:
        return sum(totals.clicks for totals in self.totals.values())

    @property
    def orders(self) -> float:
        return sum(totals.orders for totals in self.totals.values())

    @property
    def acos(self) -> float:
        return acos(self.spend, self.sales)


def run_audit(frames: AuditFrames, *, brand_terms: tuple[str, ...] = (),
              business_report: pd.DataFrame | None = None) -> AuditResult:
    brand_terms = tuple(term.strip().lower() for term in brand_terms if term.strip())
    totals = {"SP": product_totals(frames.sp_campaigns), "SB": product_totals(frames.sb_campaigns),
              "SD": product_totals(frames.sd_campaigns)}
    running_sp_keywords = running_rows(frames.sp_keywords, frames.sp_campaigns, frames.sp_ad_groups)
    sp_segments, auto_source = sp_segment_table(frames)
    own_asins = business_report_asins(business_report) | advertised_asins(frames.sp_product_ads)
    return AuditResult(
        totals=totals,
        business_report=business_report_figures(business_report, sum(t.spend for t in totals.values()),
                                                 sum(t.sales for t in totals.values())),
        mixed_match=mixed_match_table(running_sp_keywords, frames.sp_campaigns),
        sp_match_types=match_type_counts(running_sp_keywords),
        sb_match_types=match_type_counts(running_rows(frames.sb_keywords, frames.sb_campaigns)),
        target_waste=target_waste(frames),
        search_term_waste=search_term_waste(frames),
        sp_segments=sp_segments,
        sb_segments=sb_segment_table(frames),
        sd_segments=sd_segment_table(frames),
        auto_segments_source=auto_source,
        top_campaigns=top_campaigns(frames.sp_campaigns),
        target_types=target_types(frames.sp_keywords, frames.sp_product_targets, brand_terms, own_asins),
        duplicates=duplicate_keywords(running_sp_keywords),
        placements=placement_adjustments(frames.sp_placements, frames.sp_campaigns),
        bidding_strategies=bidding_strategies(frames.sp_campaigns),
        skag=skag_buckets(frames),
        graduation=graduation_targets(frames.sp_keywords, frames.sp_ad_groups, brand_terms),
    )


def acos(spend: float, sales: float) -> float:
    """ACoS in percent; 0 when nothing sold, as the module has always shown it."""
    return (spend / sales * 100) if sales > 0 else 0


def product_totals(campaigns: pd.DataFrame) -> ProductTotals:
    spend = _numbers(campaigns, SPEND)
    return ProductTotals(
        spend=float(spend.sum()),
        sales=float(_numbers(campaigns, SALES).sum()),
        impressions=float(_numbers(campaigns, IMPRESSIONS).sum()),
        clicks=float(_numbers(campaigns, CLICKS).sum()),
        orders=float(_numbers(campaigns, ORDERS).sum()),
        campaigns=len(campaigns),
        unknown=int(spend.isna().sum()) if SPEND in campaigns.columns else 0,
    )


def business_report_figures(business_report: pd.DataFrame | None, ppc_spend: float,
                            ppc_sales: float) -> BusinessReportFigures | None:
    """Revenue, organic sales and TACoS from the Business Report's ordered product sales; None without them."""
    if business_report is None or business_report.empty:
        return None
    column = next((name for name in _REVENUE_COLUMNS if name in business_report.columns), None)
    if column is None:
        column = next((name for name in business_report.columns
                       if "ordered" in str(name).lower() and "sales" in str(name).lower()), None)
    if column is None:
        return None
    revenue = float(_money(business_report[column]).sum())
    if revenue <= 0:
        return None
    organic = max(0.0, revenue - ppc_sales)
    return BusinessReportFigures(revenue=revenue, organic_sales=organic, organic_pct=organic / revenue * 100,
                                 tacos=ppc_spend / revenue * 100)


def business_report_asins(business_report: pd.DataFrame | None) -> set[str]:
    """The ASINs of the first Business Report column that names them: the account's own products."""
    if business_report is None or business_report.empty:
        return set()
    column = next((name for name in business_report.columns if "asin" in str(name).lower()), None)
    if column is None:
        return set()
    return set(business_report[column].dropna().astype(str).str.strip().str.upper())


def advertised_asins(product_ads: pd.DataFrame) -> set[str]:
    if ASIN not in product_ads.columns:
        return set()
    asins = product_ads[ASIN].dropna().astype(str).str.strip().str.upper()
    return set(asins[asins.ne("")])


def running_rows(targets: pd.DataFrame, campaigns: pd.DataFrame, ad_groups: pd.DataFrame | None = None) -> pd.DataFrame:
    """What runs: enabled, in an enabled campaign, and not in an ad group listed as paused or archived.

    A campaign or ad group the source does not list counts as enabled, as Target Graduation reads them.
    """
    if targets.empty or STATE not in targets.columns:
        return targets.iloc[0:0]
    running = _states(targets).eq(ENABLED)
    if CAMPAIGN_ID in targets.columns:
        campaign_states = targets[CAMPAIGN_ID].map(_states_by_id(campaigns, CAMPAIGN_ID))
        running &= campaign_states.fillna(ENABLED).eq(ENABLED)
    if ad_groups is not None and AD_GROUP_ID in targets.columns:
        ad_group_states = targets[AD_GROUP_ID].map(_states_by_id(ad_groups, AD_GROUP_ID))
        running &= ad_group_states.fillna(ENABLED).eq(ENABLED)
    return targets[running]


def mixed_match_table(keywords: pd.DataFrame, campaigns: pd.DataFrame) -> pd.DataFrame:
    """The campaigns whose running keywords mix match types: which ones and how many keywords."""
    if keywords.empty or not {CAMPAIGN_ID, MATCH_TYPE} <= set(keywords.columns):
        return pd.DataFrame(columns=list(MIXED_MATCH_COLUMNS))
    per_campaign = keywords.groupby(CAMPAIGN_ID)[MATCH_TYPE].agg(
        match_types=lambda values: " | ".join(sorted(set(values.astype(str)))), distinct="nunique", keywords="size")
    mixed = per_campaign[per_campaign["distinct"] > 1]
    names = _names_by_id(campaigns, keywords)
    return pd.DataFrame({CAMPAIGN_NAME: [names.get(campaign_id, campaign_id) for campaign_id in mixed.index],
                         "Match Types": mixed["match_types"].to_numpy(),
                         "Keywords": mixed["keywords"].astype(int).to_numpy()}, columns=list(MIXED_MATCH_COLUMNS))


def match_type_counts(keywords: pd.DataFrame) -> dict[str, int]:
    if keywords.empty or MATCH_TYPE not in keywords.columns:
        return {}
    return {str(match_type): int(count) for match_type, count in keywords[MATCH_TYPE].value_counts().items()}


def target_waste(frames: AuditFrames) -> TargetWaste:
    sp_targets = pd.concat([frames.sp_keywords, frames.sp_product_targets], ignore_index=True)
    lines = {
        "sp": None if {SP_TARGETS, SP_TARGET_METRICS} & frames.unavailable.keys() else waste_line(sp_targets),
        "sb": None if SB_KEYWORDS in frames.unavailable else waste_line(frames.sb_keywords),
        "sd": None if SD_TARGETS in frames.unavailable else waste_line(frames.sd_targets),
    }
    known = [line for line in lines.values() if line is not None]
    total_waste = sum(line.waste for line in known)
    total_spend = sum(line.spend for line in known)
    return TargetWaste(**lines, total_waste=total_waste,
                       pct=(total_waste / total_spend * 100) if total_spend > 0 else 0)


def search_term_waste(frames: AuditFrames) -> SearchTermWaste:
    sp = waste_line(frames.sp_search_terms)
    sb = None if SB_SEARCH_TERMS in frames.unavailable else waste_line(frames.sb_search_terms)
    total_waste = sp.waste + (sb.waste if sb is not None else 0)
    return SearchTermWaste(sp=sp, sb=sb, total_waste=total_waste,
                           pct=(sp.waste / sp.spend * 100) if sp.spend > 0 else 0,
                           top_terms=wasted_terms(frames.sp_search_terms))


def waste_line(rows: pd.DataFrame) -> WasteLine:
    """Spend without a single sale, over the rows whose metrics are known."""
    spend, sales = _numbers(rows, SPEND), _numbers(rows, SALES)
    wasted = (spend > 0) & (sales == 0)
    return WasteLine(waste=float(spend[wasted].sum()), count=int(wasted.sum()), spend=float(spend.sum()))


def wasted_terms(search_terms: pd.DataFrame, limit: int | None = TOP_WASTED_TERMS) -> pd.DataFrame:
    """The search terms that spent the most without selling; all of them with no limit."""
    term_column = _search_term_column(search_terms)
    if term_column is None:
        return pd.DataFrame(columns=list(WASTED_TERM_COLUMNS))
    spend, sales = _numbers(search_terms, SPEND), _numbers(search_terms, SALES)
    wasted = search_terms[(spend > 0) & (sales == 0)]
    columns = [term_column] + [column for column in (SPEND, CLICKS, IMPRESSIONS) if column in search_terms.columns]
    ranked = wasted.assign(**{SPEND: spend[wasted.index]}).sort_values(SPEND, ascending=False, kind="mergesort")
    if limit is not None:
        ranked = ranked.head(limit)
    return ranked[columns].rename(columns={term_column: SEARCH_TERM}).reset_index(drop=True)


def segment_row(label: str, rows: pd.DataFrame) -> dict:
    spend = float(_numbers(rows, SPEND).sum())
    sales = float(_numbers(rows, SALES).sum())
    clicks = float(_numbers(rows, CLICKS).sum())
    impressions = float(_numbers(rows, IMPRESSIONS).sum())
    orders = float(_numbers(rows, ORDERS).sum())
    return {
        "Segmento": label,
        "# Targets": len(rows),
        "Spend": round(spend, 2),
        "Sales": round(sales, 2),
        "ACoS": round(acos(spend, sales), 1),
        "Clicks": int(clicks),
        "Orders": int(orders),
        "CTR": round((clicks / impressions * 100) if impressions > 0 else 0, 2),
        "CVR": round((orders / clicks * 100) if clicks > 0 else 0, 2),
        "CPC": round((spend / clicks) if clicks > 0 else 0, 2),
        "% Spend": 0,
    }


def segment_table(rows: list[dict], total_spend: float) -> pd.DataFrame:
    for row in rows:
        row["% Spend"] = round((row["Spend"] / total_spend * 100) if total_spend > 0 else 0, 1)
    return pd.DataFrame(rows, columns=list(SEGMENT_COLUMNS))


def sp_segment_table(frames: AuditFrames) -> tuple[pd.DataFrame, str]:
    """SP by match type, product targeting kind and auto group, then its total; plus where AUTO came from."""
    keywords, product_targets = frames.sp_keywords, frames.sp_product_targets
    rows = []
    if MATCH_TYPE in keywords.columns and not keywords.empty:
        rows += [segment_row(f"KW {match}", keywords[keywords[MATCH_TYPE] == match])
                 for match in ("Exact", "Phrase", "Broad")]
    if EXPRESSION in product_targets.columns and not product_targets.empty:
        expression = product_targets[EXPRESSION].astype(str)
        rows.append(segment_row("PT ASIN Targeting",
                                product_targets[expression.str.contains("asin", case=False, na=False)]))
        rows.append(segment_row("PT Category Targeting",
                                product_targets[expression.str.contains("category", case=False, na=False)]))
    auto_rows, auto_source = _auto_segment_rows(frames)
    rows += auto_rows
    rows.append(segment_row("TOTAL SP", frames.sp_campaigns))
    return segment_table(rows, float(_numbers(frames.sp_campaigns, SPEND).sum())), auto_source


def sb_segment_table(frames: AuditFrames) -> pd.DataFrame:
    if frames.sb_campaigns.empty:
        return segment_table([], 0)
    keywords = frames.sb_keywords
    rows = []
    if MATCH_TYPE in keywords.columns and not keywords.empty:
        rows += [segment_row(f"KW {match}", keywords[keywords[MATCH_TYPE] == match])
                 for match in ("Exact", "Phrase", "Broad")]
    rows.append(segment_row("TOTAL SB", frames.sb_campaigns))
    return segment_table(rows, float(_numbers(frames.sb_campaigns, SPEND).sum()))


def sd_segment_table(frames: AuditFrames) -> pd.DataFrame:
    """SD's campaigns by what their name says they target, then its total."""
    campaigns = frames.sd_campaigns
    if campaigns.empty:
        return segment_table([], 0)
    rows = []
    if CAMPAIGN_NAME in campaigns.columns:
        names = campaigns[CAMPAIGN_NAME].astype(str).str.lower()
        retargeting = names.str.contains(_SD_RETARGETING, na=False)
        audiences = names.str.contains(_SD_AUDIENCE, na=False) & ~retargeting
        rows += [segment_row("SD Retargeting", campaigns[retargeting]),
                 segment_row("SD Audiences", campaigns[audiences]),
                 segment_row("SD Product Targeting", campaigns[~retargeting & ~audiences])]
    rows.append(segment_row("TOTAL SD", campaigns))
    return segment_table(rows, float(_numbers(campaigns, SPEND).sum()))


def _auto_segment_rows(frames: AuditFrames) -> tuple[list[dict], str]:
    """AUTO from the auto targeting groups, which carry all their traffic; from the search terms of the auto
    campaigns only when the source does not list those groups (the report only has terms with clicks)."""
    product_targets = frames.sp_product_targets
    if EXPRESSION in product_targets.columns and not product_targets.empty:
        expression = product_targets[EXPRESSION].astype(str).str.lower().str.strip()
        if expression.isin(AUTO_GROUPS).any():
            return _auto_rows(product_targets, expression), AUTO_FROM_TARGETING
    search_terms = frames.sp_search_terms
    if EXPRESSION not in search_terms.columns:
        return [], ""
    auto_campaigns = _auto_campaign_keys(frames.sp_campaigns)
    join_column = next((column for column in (CAMPAIGN_ID, CAMPAIGN_NAME)
                        if column in search_terms.columns and auto_campaigns.get(column)), None)
    if join_column is not None:
        auto_terms = search_terms[search_terms[join_column].isin(auto_campaigns[join_column])]
    else:
        auto_terms = search_terms[search_terms[EXPRESSION].astype(str).str.strip() != ""]
    expression = auto_terms[EXPRESSION].astype(str).str.lower().str.strip()
    return _auto_rows(auto_terms, expression), AUTO_FROM_SEARCH_TERMS


def _auto_rows(rows: pd.DataFrame, expression: pd.Series) -> list[dict]:
    return [segment_row("AUTO Close Match", rows[expression == "close-match"]),
            segment_row("AUTO Loose Match", rows[expression == "loose-match"]),
            segment_row("AUTO Substitutes", rows[expression.str.contains("substitutes", na=False)]),
            segment_row("AUTO Complements", rows[expression.str.contains("complements", na=False)])]


def _auto_campaign_keys(campaigns: pd.DataFrame) -> dict[str, set]:
    if TARGETING_TYPE not in campaigns.columns or campaigns.empty:
        return {}
    auto = campaigns[campaigns[TARGETING_TYPE].astype(str).str.lower() == AUTO]
    return {column: set(auto[column].dropna()) for column in (CAMPAIGN_ID, CAMPAIGN_NAME) if column in auto.columns}


def top_campaigns(campaigns: pd.DataFrame, limit: int | None = TOP_CAMPAIGNS) -> pd.DataFrame:
    """SP's campaigns that spent the most, with their ACoS computed from spend and sales; all with no limit."""
    if campaigns.empty or SPEND not in campaigns.columns:
        return pd.DataFrame(columns=list(TOP_CAMPAIGN_COLUMNS))
    spend, sales = _numbers(campaigns, SPEND), _numbers(campaigns, SALES)
    ranked = campaigns.assign(**{SPEND: spend, SALES: sales,
                                 "ACOS": [round(acos(s, v), 1) for s, v in zip(spend.fillna(0), sales.fillna(0))]})
    ranked = ranked.sort_values(SPEND, ascending=False, na_position="last", kind="mergesort")
    if limit is not None:
        ranked = ranked.head(limit)
    return ranked[[column for column in TOP_CAMPAIGN_COLUMNS if column in ranked.columns]].reset_index(drop=True)


def target_types(keywords: pd.DataFrame, product_targets: pd.DataFrame, brand_terms: tuple[str, ...],
                 own_asins: set[str]) -> pd.DataFrame:
    """Targets by kind: own brand, own ASIN, competitor ASIN or generic. Empty without brand terms."""
    if not brand_terms:
        return pd.DataFrame(columns=list(TARGET_TYPE_COLUMNS))
    parts = []
    if KEYWORD_TEXT in keywords.columns and not keywords.empty:
        text = keywords[KEYWORD_TEXT].astype(str).str.lower()
        own_brand = text.apply(lambda keyword: any(term in keyword for term in brand_terms))
        parts.append(_typed_targets(keywords, np.where(own_brand, "own_brand", "generic")))
    if EXPRESSION in product_targets.columns and not product_targets.empty:
        expression = product_targets[EXPRESSION].astype(str)
        asin = expression.str.upper().str.extract(r"([A-Z0-9]{10})", expand=False)
        names_asin = expression.str.lower().str.contains("asin", na=False) & asin.notna()
        kinds = np.select([names_asin & asin.isin(own_asins), names_asin], ["own_asin", "competitor_asin"],
                          default="generic")
        parts.append(_typed_targets(product_targets, kinds))
    if not parts:
        return pd.DataFrame(columns=list(TARGET_TYPE_COLUMNS))
    typed = pd.concat(parts, ignore_index=True)
    by_type = typed.groupby("Tipo").agg(Targets=("Tipo", "count"), Spend=(SPEND, "sum"),
                                        Sales=(SALES, "sum")).reset_index()
    by_type["ACoS"] = [round(acos(spend, sales), 1) for spend, sales in zip(by_type[SPEND], by_type[SALES])]
    total_spend = by_type[SPEND].sum()
    by_type["% Spend"] = [round((spend / total_spend * 100) if total_spend > 0 else 0, 1) for spend in by_type[SPEND]]
    return by_type.sort_values(SPEND, ascending=False, kind="mergesort")[list(TARGET_TYPE_COLUMNS)].reset_index(
        drop=True)


def _typed_targets(rows: pd.DataFrame, kinds) -> pd.DataFrame:
    return pd.DataFrame({"Tipo": kinds, SPEND: _numbers(rows, SPEND).fillna(0).to_numpy(),
                         SALES: _numbers(rows, SALES).fillna(0).to_numpy()})


def duplicate_keywords(keywords: pd.DataFrame, limit: int | None = TOP_DUPLICATES) -> pd.DataFrame:
    """The same keyword and match type running in two or more campaigns, the most spend first; all with no limit."""
    if keywords.empty or not {KEYWORD_TEXT, CAMPAIGN_ID, MATCH_TYPE} <= set(keywords.columns):
        return pd.DataFrame(columns=list(DUPLICATE_COLUMNS))
    grouped = keywords.assign(
        _keyword=keywords[KEYWORD_TEXT].astype(str).str.lower().str.strip(),
        _match=keywords[MATCH_TYPE].astype(str).str.strip(),
        _spend=_numbers(keywords, SPEND), _sales=_numbers(keywords, SALES),
    ).groupby(["_keyword", "_match"]).agg(campaigns=(CAMPAIGN_ID, "nunique"), spend=("_spend", "sum"),
                                          sales=("_sales", "sum")).reset_index()
    duplicates = grouped[grouped["campaigns"] >= 2].sort_values("spend", ascending=False, kind="mergesort")
    if limit is not None:
        duplicates = duplicates.head(limit)
    return pd.DataFrame({
        "Keyword": duplicates["_keyword"], MATCH_TYPE: duplicates["_match"],
        "# Campañas": duplicates["campaigns"].astype(int),
        "Spend_Total": duplicates["spend"].round(2), "Sales_Total": duplicates["sales"].round(2),
    }, columns=list(DUPLICATE_COLUMNS)).reset_index(drop=True)


def placement_adjustments(placements: pd.DataFrame, campaigns: pd.DataFrame) -> pd.DataFrame:
    """Each placement's bid adjustment over the enabled campaigns: how many, average, range and how many adjust it."""
    if placements.empty or not {PLACEMENT, PERCENTAGE} <= set(placements.columns):
        return pd.DataFrame(columns=list(PLACEMENT_COLUMNS))
    enabled = placements
    if CAMPAIGN_ID in placements.columns:
        states = placements[CAMPAIGN_ID].map(_states_by_id(campaigns, CAMPAIGN_ID))
        enabled = placements[states.fillna(ENABLED).eq(ENABLED)]
    percentage = pd.to_numeric(enabled[PERCENTAGE], errors="coerce").fillna(0)
    label = enabled[PLACEMENT].map(lambda code: PLACEMENT_LABELS.get(str(code), code))
    table = pd.DataFrame({PLACEMENT: label, "_pct": percentage}).groupby(PLACEMENT).agg(
        Campañas=("_pct", "count"), Promedio=("_pct", "mean"), Min=("_pct", "min"), Max=("_pct", "max"),
        Con_Ajuste=("_pct", lambda values: int((values > 0).sum()))).reset_index()
    table["Promedio"] = table["Promedio"].round(1)
    return table[list(PLACEMENT_COLUMNS)]


def bidding_strategies(campaigns: pd.DataFrame) -> pd.DataFrame:
    """How many enabled campaigns use each bidding strategy."""
    if campaigns.empty or BIDDING_STRATEGY not in campaigns.columns:
        return pd.DataFrame(columns=[BIDDING_STRATEGY, "Count"])
    enabled = campaigns[_states(campaigns).eq(ENABLED)] if STATE in campaigns.columns else campaigns
    strategy = enabled[BIDDING_STRATEGY].dropna().astype(str).str.strip()
    counts = strategy[strategy.ne("")].value_counts()
    return pd.DataFrame({BIDDING_STRATEGY: counts.index, "Count": counts.to_numpy()})


def skag_buckets(frames: AuditFrames) -> pd.DataFrame:
    """Enabled manual campaigns by how many targets run in them: SKAG, normal or bag."""
    campaigns = frames.sp_campaigns
    if campaigns.empty or not {CAMPAIGN_ID, TARGETING_TYPE} <= set(campaigns.columns):
        return pd.DataFrame(columns=list(SKAG_COLUMNS))
    manual = campaigns[_states(campaigns).eq(ENABLED)
                       & campaigns[TARGETING_TYPE].astype(str).str.lower().eq(MANUAL)]
    targets = pd.concat([frames.sp_keywords, frames.sp_product_targets], ignore_index=True)
    running = running_rows(targets, campaigns, frames.sp_ad_groups)
    if running.empty or CAMPAIGN_ID not in running.columns:
        return pd.DataFrame(columns=list(SKAG_COLUMNS))
    running = running[running[CAMPAIGN_ID].isin(set(manual[CAMPAIGN_ID]))]
    per_campaign = running.assign(_spend=_numbers(running, SPEND)).groupby(CAMPAIGN_ID).agg(
        targets=(CAMPAIGN_ID, "count"), spend=("_spend", "sum"))
    if per_campaign.empty:
        return pd.DataFrame(columns=list(SKAG_COLUMNS))
    kind = np.select([per_campaign["targets"] == 1, per_campaign["targets"] <= 10],
                     ["SKAG (1 target)", "Normal (2-10)"], default="Bolsa (11+)")
    summary = per_campaign.assign(Tipo=kind).groupby("Tipo").agg(
        Campañas=("Tipo", "count"), Spend_Total=("spend", "sum")).reset_index()
    total_spend = summary["Spend_Total"].sum()
    summary["% Spend"] = [round((spend / total_spend * 100) if total_spend > 0 else 0, 1)
                          for spend in summary["Spend_Total"]]
    summary["Spend_Total"] = summary["Spend_Total"].round(2)
    return summary[list(SKAG_COLUMNS)]


def graduation_targets(keywords: pd.DataFrame, ad_groups: pd.DataFrame,
                       brand_terms: tuple[str, ...] = ()) -> pd.DataFrame:
    """Keywords without a single impression in campaigns that did have traffic, each with its recommendation.

    Keywords of an ad group listed as paused or archived are left out: their ad group, not their bid, keeps them
    quiet.
    """
    if keywords.empty or not {CAMPAIGN_ID, IMPRESSIONS} <= set(keywords.columns):
        return pd.DataFrame()
    impressions = _numbers(keywords, IMPRESSIONS)
    campaign_impressions = impressions.groupby(keywords[CAMPAIGN_ID]).sum()
    quiet = keywords[impressions == 0]
    if AD_GROUP_ID in quiet.columns:
        ad_group_states = quiet[AD_GROUP_ID].map(_states_by_id(ad_groups, AD_GROUP_ID))
        quiet = quiet[~ad_group_states.isin((PAUSED, ARCHIVED))]
    quiet = quiet.assign(**{CAMPAIGN_IMPRESSIONS: quiet[CAMPAIGN_ID].map(campaign_impressions).fillna(0)})
    orphans = quiet[quiet[CAMPAIGN_IMPRESSIONS] > 0].copy()
    if orphans.empty:
        return pd.DataFrame()
    state = _states(orphans)
    text = (orphans[KEYWORD_TEXT].astype(str).str.lower() if KEYWORD_TEXT in orphans.columns
            else pd.Series("", index=orphans.index))
    spend = _numbers(orphans, SPEND).fillna(0)
    sales = _numbers(orphans, SALES).fillna(0)
    orders = _numbers(orphans, ORDERS).fillna(0)
    own_brand = (text.apply(lambda keyword: any(term in keyword for term in brand_terms)) if brand_terms
                 else pd.Series(False, index=orphans.index))
    orphans[RECOMMENDATION] = np.select(
        [state.ne(ENABLED), own_brand, (sales > 0) | (orders > 0), (spend > 0) & (orders == 0)],
        [GRADUATE_PAUSED, GRADUATE_KEEP, GRADUATE_RAISE, GRADUATE_PAUSE], default=GRADUATE_SKAG)
    return orphans


def _numbers(frame: pd.DataFrame, column: str) -> pd.Series:
    """The column as numbers, NaN kept (an unknown metric); an absent column is all NaN."""
    if column not in frame.columns:
        return pd.Series(np.nan, index=frame.index, dtype="float64")
    return pd.to_numeric(frame[column], errors="coerce").astype("float64")


def _money(column: pd.Series) -> pd.Series:
    return pd.to_numeric(column.astype(str).str.replace(r"[\$%,]", "", regex=True), errors="coerce").fillna(0)


def _states(frame: pd.DataFrame) -> pd.Series:
    return frame[STATE].astype(str).str.strip().str.lower()


def _states_by_id(frame: pd.DataFrame, id_column: str) -> dict:
    if frame.empty or not {id_column, STATE} <= set(frame.columns):
        return {}
    return dict(zip(frame[id_column], _states(frame)))


def _names_by_id(campaigns: pd.DataFrame, rows: pd.DataFrame) -> dict:
    """Campaign id -> its name: the campaign's own row first, then any row that carries it."""
    names = {}
    for frame in (rows, campaigns):
        if {CAMPAIGN_ID, CAMPAIGN_NAME} <= set(frame.columns):
            named = frame[frame[CAMPAIGN_NAME].notna() & frame[CAMPAIGN_NAME].astype(str).str.strip().ne("")]
            names.update(zip(named[CAMPAIGN_ID], named[CAMPAIGN_NAME].astype(str)))
    return names


def _search_term_column(search_terms: pd.DataFrame) -> str | None:
    if SEARCH_TERM in search_terms.columns:
        return SEARCH_TERM
    return next((column for column in search_terms.columns
                 if "search" in str(column).lower() and "term" in str(column).lower()), None)
