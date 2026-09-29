"""The PPC Audit Pro agent's payload, built from what the module already computed, without Streamlit."""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from ai.agents import make_ids
from ai.agents.ppc_audit.chat_document import row_item
from ai.agents.ppc_audit.context import (
    MAX_CAMPAIGNS,
    MAX_DUPLICATES,
    MAX_WASTED_TERMS,
    ROW_PREFIX,
    AuditData,
    records_of,
)
from core.ppc_audit.checks import (
    AUTO_FROM_SEARCH_TERMS,
    AUTO_FROM_TARGETING,
    CAMPAIGN_IMPRESSIONS,
    GRADUATE_PAUSED,
    GRADUATION_LABELS,
    PRODUCTS,
    RECOMMENDATION,
    AuditResult,
    WasteLine,
    acos,
    duplicate_keywords,
    running_rows,
    top_campaigns,
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

ANALYSIS_MODULE = "ppc_audit"
GROUP_MIXED = "match_mixto"
GROUP_CAMPAIGN = "campana"
GROUP_DUPLICATE = "duplicado"
GROUP_GRADUATION = "graduacion"
GROUP_WASTED_TERM = "termino_sin_venta"
_AUTO_SOURCES = {AUTO_FROM_TARGETING: "los grupos de targeting automático, con todo su tráfico",
                 AUTO_FROM_SEARCH_TERMS: "los search terms de las campañas automáticas, sólo términos con clicks"}
_SOURCE_LABELS = {True: "Bulk File subido a mano", False: "Amazon Ads"}


@dataclass(frozen=True)
class AuditAnalysisInput:
    """The agent payload plus the rows its row_ids point to; `data` is None when there is nothing to judge."""

    data: AuditData | None
    records: list


def build_analysis_input(frames: AuditFrames, result: AuditResult, *, account_label: str, period_label: str,
                         currency_code: str, attribution_days: int | None, brand_terms: tuple[str, ...],
                         lang: str) -> AuditAnalysisInput:
    running_keywords = running_rows(frames.sp_keywords, frames.sp_campaigns, frames.sp_ad_groups)
    duplicates = duplicate_keywords(running_keywords, limit=None)
    mixed = [_mixed_record(row) for _, row in result.mixed_match.iterrows()]
    campaigns = [_campaign_record(row) for _, row in top_campaigns(frames.sp_campaigns, MAX_CAMPAIGNS).iterrows()]
    duplicate_rows = [_duplicate_record(row) for _, row in duplicates.head(MAX_DUPLICATES).iterrows()]
    graduation = _graduation_records(result.graduation)
    terms = [_wasted_term_record(row) for _, row in wasted_terms(frames.sp_search_terms, MAX_WASTED_TERMS).iterrows()]
    if not (mixed or duplicate_rows or graduation or terms):
        return AuditAnalysisInput(None, [])
    data = AuditData(
        account_label=account_label, period_label=period_label, currency_code=currency_code,
        attribution_days=attribution_days, source=_SOURCE_LABELS[frames.from_file],
        brand_terms=list(brand_terms), counts=_counts(result, duplicates), missing=_missing(frames),
        segments=_segment_records(result), mixed=mixed, campaigns=campaigns, duplicates=duplicate_rows,
        graduation=graduation, wasted_terms=terms, idioma=lang,
    )
    return AuditAnalysisInput(data, records_of(data))


def audit_row_labels(records: list) -> dict[str, str]:
    """row_id -> the campaign, keyword or term behind it, to annotate the ids the synthesis and the chat cite (U03)."""
    return {row_id: row_item(record) for row_id, record in zip(make_ids(ROW_PREFIX, len(records)), records)}


def _counts(result: AuditResult, duplicates: pd.DataFrame) -> dict:
    counts: dict = {}
    for product in PRODUCTS:
        totals = result.totals[product]
        if not totals.campaigns:
            continue
        counts[f"Campañas de {product}"] = totals.campaigns
        if totals.unknown:
            counts[f"Campañas de {product} sin métricas del período"] = totals.unknown
        if totals.campaigns > totals.unknown:
            counts[f"Gasto de {product}"] = round(totals.spend, 2)
            counts[f"Ventas de {product}"] = round(totals.sales, 2)
            counts[f"ACoS de {product} (%)"] = round(acos(totals.spend, totals.sales), 1)
    if any(t.campaigns > t.unknown for t in result.totals.values()):
        counts["Gasto total"] = round(result.spend, 2)
        counts["Ventas totales"] = round(result.sales, 2)
        counts["ACoS total (%)"] = round(result.acos, 1)
        counts["Impresiones"] = int(result.impressions)
        counts["Clicks"] = int(result.clicks)
        counts["Órdenes"] = int(result.orders)
    report = result.business_report
    if report is not None:
        counts["Revenue total del Business Report"] = round(report.revenue, 2)
        counts["Ventas orgánicas"] = round(report.organic_sales, 2)
        counts["TACoS (%)"] = round(report.tacos, 1)

    waste = result.target_waste
    counts["Gasto sin ventas en targets"] = round(waste.total_waste, 2)
    counts["Gasto sin ventas en targets (% del gasto en targets)"] = round(waste.pct, 1)
    for product, line in (("SP", waste.sp), ("SB", waste.sb), ("SD", waste.sd)):
        counts[f"Gasto sin ventas en targets de {product}"] = _waste_text(line, "targets")
    terms = result.search_term_waste
    counts["Gasto sin ventas en search terms de SP"] = _waste_text(terms.sp, "términos")
    counts["Gasto sin ventas en search terms de SP (% de su gasto)"] = round(terms.pct, 1)
    counts["Gasto sin ventas en search terms de SB"] = _waste_text(terms.sb, "términos")

    counts["Campañas con match types mixtos"] = len(result.mixed_match)
    if result.sp_match_types:
        counts["Keywords habilitadas de SP por match type"] = _pairs(result.sp_match_types)
    counts["Keywords duplicadas entre campañas"] = len(duplicates)
    if not result.skag.empty:
        counts["Campañas manuales habilitadas por forma"] = _pairs(dict(zip(result.skag["Tipo"],
                                                                              result.skag["Campañas"])))
    if not result.graduation.empty:
        by_recommendation = result.graduation[RECOMMENDATION].value_counts()
        counts["Target Graduation por recomendación"] = _pairs(
            {GRADUATION_LABELS[label]: int(count) for label, count in by_recommendation.items()})
    if result.auto_segments_source in _AUTO_SOURCES:
        counts["Segmentos AUTO desde"] = _AUTO_SOURCES[result.auto_segments_source]
    if not result.target_types.empty:
        counts["Gasto por tipo de target (%)"] = _pairs(dict(zip(result.target_types["Tipo"],
                                                                  result.target_types["% Spend"])))
    if not result.placements.empty:
        counts["Campañas habilitadas que ajustan cada placement"] = _pairs(
            {f"{placement} (de {total})": adjusted for placement, total, adjusted
             in zip(result.placements["Placement"], result.placements["Campañas"], result.placements["Con_Ajuste"])})
    return counts


def _missing(frames: AuditFrames) -> list[str]:
    return list(dict.fromkeys(frames.unavailable.values()))


def _segment_records(result: AuditResult) -> list[dict]:
    records = []
    for product, segments in (("SP", result.sp_segments), ("SB", result.sb_segments), ("SD", result.sd_segments)):
        for _, row in segments.iterrows():
            records.append({
                "producto": product, "segmento": row["Segmento"], "targets": _plain(row["# Targets"]),
                "spend": _plain(row["Spend"]), "sales": _plain(row["Sales"]),
                "acos": _plain(row["ACoS"]) if row["Sales"] else None, "clicks": _plain(row["Clicks"]),
                "orders": _plain(row["Orders"]), "ctr": _plain(row["CTR"]) if row["Clicks"] else None,
                "cvr": _plain(row["CVR"]) if row["Clicks"] else None, "cpc": _plain(row["CPC"]) if row["Clicks"] else None,
                "pct_spend": _plain(row["% Spend"]),
            })
    return records


def _mixed_record(row: pd.Series) -> dict:
    return {"grupo": GROUP_MIXED, "campana": str(row[CAMPAIGN_NAME]).strip(), "match_types": row["Match Types"],
            "keywords": _plain(row["Keywords"])}


def _campaign_record(row: pd.Series) -> dict:
    sales = _plain(row.get(SALES))
    return {"grupo": GROUP_CAMPAIGN, "campana": str(row.get(CAMPAIGN_NAME, "")).strip(),
            "targeting": str(row.get(TARGETING_TYPE, "") or "").strip(), "spend": _plain(row.get(SPEND)),
            "sales": sales, "acos": _plain(row.get("ACOS")) if sales else None, "orders": _plain(row.get(ORDERS))}


def _duplicate_record(row: pd.Series) -> dict:
    return {"grupo": GROUP_DUPLICATE, "keyword": row["Keyword"], "match_type": row[MATCH_TYPE],
            "campanas": _plain(row["# Campañas"]), "spend": _plain(row["Spend_Total"]),
            "sales": _plain(row["Sales_Total"])}


def _graduation_records(graduation: pd.DataFrame) -> list[dict]:
    """The actionable ones in the order the AM acts on them; the keywords already paused stay out."""
    if graduation.empty:
        return []
    actionable = graduation[graduation[RECOMMENDATION].ne(GRADUATE_PAUSED)]
    order = {label: rank for rank, label in enumerate(GRADUATION_LABELS)}
    ranked = actionable.assign(
        _rank=actionable[RECOMMENDATION].map(order),
        _impressions=pd.to_numeric(actionable[CAMPAIGN_IMPRESSIONS], errors="coerce"),
        _spend=pd.to_numeric(actionable[SPEND], errors="coerce") if SPEND in actionable.columns else 0.0,
    ).sort_values(["_rank", "_impressions", "_spend"], ascending=[True, False, False], kind="mergesort")
    return [{
        "grupo": GROUP_GRADUATION, "keyword": str(row.get(KEYWORD_TEXT, "")).strip(),
        "match_type": row.get(MATCH_TYPE, ""), "campana": str(row.get(CAMPAIGN_NAME, "")).strip(),
        "ad_group": str(row.get(AD_GROUP_NAME, "") or "").strip(), "bid": _plain(row.get(BID)),
        "impresiones_campana": _plain(row[CAMPAIGN_IMPRESSIONS]), "spend": _plain(row.get(SPEND)),
        "sales": _plain(row.get(SALES)), "orders": _plain(row.get(ORDERS)),
        "recomendacion": GRADUATION_LABELS[row[RECOMMENDATION]],
    } for _, row in ranked.iterrows()]


def _wasted_term_record(row: pd.Series) -> dict:
    return {"grupo": GROUP_WASTED_TERM, "termino": str(row[SEARCH_TERM]).strip(), "spend": _plain(row.get(SPEND)),
            "clicks": _plain(row.get(CLICKS)), "impressions": _plain(row.get(IMPRESSIONS))}


def _waste_text(line: WasteLine | None, unit: str) -> str:
    if line is None:
        return "sin dato"
    return f"{_plain(round(line.waste, 2))} en {line.count} {unit}"


def _pairs(values: dict) -> str:
    return ", ".join(f"{label} {_plain(value)}" for label, value in values.items())


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
