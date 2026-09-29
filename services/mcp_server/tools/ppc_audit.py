"""ppc_audit: PPC Audit Pro of an account, with the module's own reads and rules (core/ppc_audit).

The SP structure as last listed, with and without traffic, and the window's metrics; the SP search terms; SB and SD.
`section` picks the list and `summary` carries the account's figures whatever the section.
"""
from __future__ import annotations

from typing import Literal

import pandas as pd

from core.amazon_ads.report_provider import ReportProvider
from core.ppc_audit.checks import (
    CAMPAIGN_IMPRESSIONS,
    GRADUATION_LABELS,
    PRODUCTS,
    RECOMMENDATION,
    AuditResult,
    WasteLine,
    acos,
    duplicate_keywords,
    running_rows,
    top_campaigns,
    run_audit,
    wasted_terms,
)
from core.ppc_audit.frames import (
    AD_GROUP_NAME,
    BID,
    CAMPAIGN_NAME,
    CLICKS,
    IMPRESSIONS,
    KEYWORD_TEXT,
    MATCH_TYPE,
    ORDERS,
    SALES,
    SEARCH_TERM,
    SPEND,
    TARGETING_TYPE,
    AuditFrames,
)
from core.ppc_audit.synced_reads import read_synced_audit
from services.mcp_server.limits import page
from services.mcp_server.tools.account_resolver import choose_account, profile_by_id
from services.mcp_server.tools.figures import _plain_number
from services.mcp_server.tools.windows import DEFAULT_DAYS, requested_window, window_payload

AuditSection = Literal["segments", "mixed_match", "duplicates", "graduation", "wasted_search_terms",
                       "top_campaigns", "target_types", "placements", "skag"]
SECTION_WHAT = {
    "segments": "segmentos",
    "mixed_match": "campañas con match types mixtos",
    "duplicates": "keywords duplicadas entre campañas",
    "graduation": "keywords sin impresiones en campañas con tráfico",
    "wasted_search_terms": "search terms sin ventas",
    "top_campaigns": "campañas de Sponsored Products",
    "target_types": "tipos de target",
    "placements": "placements",
    "skag": "formas de campaña manual",
}
AUDIT_SOURCE = ("De Amazon Ads, con las mismas lecturas y reglas que PPC Audit Pro: la estructura de Sponsored "
                "Products como se listó por última vez, también los keywords y targets sin tráfico, con las métricas "
                "del período de sus reportes; los search terms de Sponsored Products; y las campañas, keywords y "
                "search terms de Sponsored Brands y los targets de Sponsored Display.")
RUNNING_NOTE = ("mixed_match, duplicates, skag y running_sp_keywords_by_match_type cuentan sólo lo que corre: keywords "
                "habilitadas en campañas y ad groups habilitados.")
TARGET_TYPES_NEED_BRAND_TERMS = "target_types clasifica por brand terms: pasá brand_terms para esa sección."


def ppc_audit(rest, *, profile_id: str = "", account: str = "", days: int = DEFAULT_DAYS, date_from: str = "",
              date_to: str = "", section: AuditSection = "segments", brand_terms: tuple[str, ...] = (),
              offset: int = 0, limit: int = 50) -> dict:
    """PPC Audit Pro of an account: its KPIs by ad product, the spend without sales of its targets and search terms,
    its segments, its structure checks and Target Graduation, over its synced data.

    `section` picks the list; `summary` covers the whole account and window.
    """
    if section not in SECTION_WHAT:
        raise ValueError(f"section tiene que ser uno de: {', '.join(SECTION_WHAT)}")
    choice = choose_account(rest, profile_id, account, days=days, date_from=date_from, date_to=date_to)
    if choice.candidates:
        return choice.as_payload()
    profile = profile_by_id(rest, choice.profile_id)
    start, end, window_note = requested_window(profile, days, date_from, date_to)
    search_terms = ReportProvider(rest).search_terms(profile, start, end)
    synced = read_synced_audit(rest, profile, start, end, search_terms.frame,
                               attribution_days=search_terms.attribution_days)
    context = {"window": window_payload(start, end), "currency": search_terms.currency_code,
               "attribution_days": search_terms.attribution_days, "source": AUDIT_SOURCE}
    if window_note:
        context["window_note"] = window_note
    if synced.frames is None:
        return {**page([]).as_payload(what=SECTION_WHAT[section]), **context, "missing": [synced.missing_reason]}

    terms = tuple(term.strip().lower() for term in brand_terms if term.strip())
    result = run_audit(synced.frames, brand_terms=terms)
    running_keywords = running_rows(synced.frames.sp_keywords, synced.frames.sp_campaigns,
                                    synced.frames.sp_ad_groups)
    duplicates = duplicate_keywords(running_keywords, limit=None)
    rows = _section_rows(section, result, synced.frames, duplicates)
    payload = page(rows, offset=offset, limit=limit).as_payload(what=SECTION_WHAT[section])
    payload.update(context, summary=_summary(result, duplicates), parameters={"brand_terms": list(terms)},
                   rules_note=RUNNING_NOTE)
    notes = list(dict.fromkeys(synced.frames.unavailable.values()))
    notes += [f"Las métricas de {what} llegan hasta el {through.isoformat()}: los días siguientes de la ventana no "
              "están en sus cifras." for what, through in (("campañas", synced.campaigns_through),
                                                          ("keywords y targets", synced.targeting_through))
              if through is not None and through < end]
    if section == "target_types" and not terms:
        notes.append(TARGET_TYPES_NEED_BRAND_TERMS)
    if notes:
        payload["missing"] = notes
    return payload


def _section_rows(section: str, result: AuditResult, frames: AuditFrames, duplicates: pd.DataFrame) -> list[dict]:
    if section == "segments":
        return [{"product": product, **_segment_row(row)} for product, segments in
                (("SP", result.sp_segments), ("SB", result.sb_segments), ("SD", result.sd_segments))
                for _, row in segments.iterrows()]
    if section == "mixed_match":
        return [{"campaign": row[CAMPAIGN_NAME], "match_types": row["Match Types"],
                 "running_keywords": int(row["Keywords"])} for _, row in result.mixed_match.iterrows()]
    if section == "duplicates":
        return [{"keyword": row["Keyword"], "match_type": row[MATCH_TYPE], "campaigns": int(row["# Campañas"]),
                 "spend": _plain_number(row["Spend_Total"]), "sales": _plain_number(row["Sales_Total"])}
                for _, row in duplicates.iterrows()]
    if section == "graduation":
        return _graduation_rows(result.graduation)
    if section == "wasted_search_terms":
        return [{"search_term": row[SEARCH_TERM], "spend": _plain_number(row.get(SPEND)),
                 "clicks": _plain_number(row.get(CLICKS)), "impressions": _plain_number(row.get(IMPRESSIONS))}
                for _, row in wasted_terms(frames.sp_search_terms, limit=None).iterrows()]
    if section == "top_campaigns":
        return [{"campaign": row.get(CAMPAIGN_NAME), "targeting": row.get(TARGETING_TYPE),
                 "spend": _plain_number(row.get(SPEND)), "sales": _plain_number(row.get(SALES)),
                 "acos": _plain_number(row.get("ACOS")) if row.get(SALES) else None,
                 "orders": _plain_number(row.get(ORDERS))}
                for _, row in top_campaigns(frames.sp_campaigns, limit=None).iterrows()]
    if section == "target_types":
        return [{"type": row["Tipo"], "targets": int(row["Targets"]), "spend": _plain_number(row[SPEND]),
                 "sales": _plain_number(row[SALES]), "acos": _plain_number(row["ACoS"]) if row[SALES] else None,
                 "spend_share": _plain_number(row["% Spend"])} for _, row in result.target_types.iterrows()]
    if section == "placements":
        return [{"placement": row["Placement"], "enabled_campaigns": int(row["Campañas"]),
                 "average_pct": _plain_number(row["Promedio"]), "min_pct": _plain_number(row["Min"]),
                 "max_pct": _plain_number(row["Max"]), "campaigns_adjusting": int(row["Con_Ajuste"])}
                for _, row in result.placements.iterrows()]
    return [{"shape": row["Tipo"], "campaigns": int(row["Campañas"]), "spend": _plain_number(row["Spend_Total"]),
             "spend_share": _plain_number(row["% Spend"])} for _, row in result.skag.iterrows()]


def _segment_row(row: pd.Series) -> dict:
    return {"segment": row["Segmento"], "targets": int(row["# Targets"]), "spend": _plain_number(row["Spend"]),
            "sales": _plain_number(row["Sales"]), "acos": _plain_number(row["ACoS"]) if row["Sales"] else None,
            "clicks": int(row["Clicks"]), "orders": int(row["Orders"]),
            "ctr": _plain_number(row["CTR"]) if row["Clicks"] else None,
            "cvr": _plain_number(row["CVR"]) if row["Clicks"] else None,
            "cpc": _plain_number(row["CPC"]) if row["Clicks"] else None, "spend_share": _plain_number(row["% Spend"])}


def _graduation_rows(graduation: pd.DataFrame) -> list[dict]:
    """Every keyword without impressions, the ones the AM acts on first: raise the bid, pause, graduate, keep."""
    if graduation.empty:
        return []
    order = {label: rank for rank, label in enumerate(GRADUATION_LABELS)}
    ranked = graduation.assign(
        _rank=graduation[RECOMMENDATION].map(order),
        _impressions=pd.to_numeric(graduation[CAMPAIGN_IMPRESSIONS], errors="coerce"),
    ).sort_values(["_rank", "_impressions"], ascending=[True, False], kind="mergesort")
    return [{"keyword": row.get(KEYWORD_TEXT), "match_type": row.get(MATCH_TYPE), "campaign": row.get(CAMPAIGN_NAME),
             "ad_group": row.get(AD_GROUP_NAME), "bid": _plain_number(row.get(BID)),
             "campaign_impressions": _plain_number(row[CAMPAIGN_IMPRESSIONS]), "spend": _plain_number(row.get(SPEND)),
             "sales": _plain_number(row.get(SALES)), "orders": _plain_number(row.get(ORDERS)),
             "recommendation": GRADUATION_LABELS[row[RECOMMENDATION]]} for _, row in ranked.iterrows()]


def _summary(result: AuditResult, duplicates: pd.DataFrame) -> dict:
    products = {}
    for product in PRODUCTS:
        totals = result.totals[product]
        if not totals.campaigns:
            continue
        known = totals.campaigns > totals.unknown
        products[product] = {
            "campaigns": totals.campaigns, "campaigns_without_metrics": totals.unknown,
            "spend": _plain_number(totals.spend) if known else None,
            "sales": _plain_number(totals.sales) if known else None,
            "acos": round(acos(totals.spend, totals.sales), 1) if known and totals.sales else None,
            "impressions": int(totals.impressions) if known else None,
            "clicks": int(totals.clicks) if known else None, "orders": int(totals.orders) if known else None,
        }
    waste, terms = result.target_waste, result.search_term_waste
    summary = {
        "products": products,
        "totals": {"spend": _plain_number(result.spend), "sales": _plain_number(result.sales),
                   "acos": round(result.acos, 1) if result.sales else None,
                   "impressions": int(result.impressions), "clicks": int(result.clicks),
                   "orders": int(result.orders)},
        "target_waste": {"spend_without_sales": _plain_number(waste.total_waste), "pct_of_target_spend":
                         round(waste.pct, 1), **{product: _waste(line) for product, line in
                                                  (("sp", waste.sp), ("sb", waste.sb), ("sd", waste.sd))}},
        "search_term_waste": {"spend_without_sales": _plain_number(terms.total_waste),
                              "sp_pct_of_search_term_spend": round(terms.pct, 1), "sp": _waste(terms.sp),
                              "sb": _waste(terms.sb)},
        "mixed_match_campaigns": len(result.mixed_match),
        "running_sp_keywords_by_match_type": dict(result.sp_match_types),
        "duplicate_keywords": len(duplicates),
        "graduation": {GRADUATION_LABELS[label]: int(count)
                       for label, count in result.graduation[RECOMMENDATION].value_counts().items()}
        if not result.graduation.empty else {},
        "auto_segments_from": result.auto_segments_source or None,
        "bidding_strategies": {str(strategy): int(count) for strategy, count in
                               zip(result.bidding_strategies["Bidding Strategy"], result.bidding_strategies["Count"])},
    }
    return summary


def _waste(line: WasteLine | None) -> dict | None:
    if line is None:
        return None
    return {"spend_without_sales": _plain_number(line.waste), "rows": line.count, "spend": _plain_number(line.spend)}
