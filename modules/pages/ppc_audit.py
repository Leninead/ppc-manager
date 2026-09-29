"""PPC Audit Pro (M20): the account's audit from its synced Amazon Ads data, or from a hand-uploaded Bulk File.

The rules live in core/ppc_audit/checks.py and the MCP runs the same ones; this page draws their result, builds the
Excel and runs the AI analysis over it.
"""
import io
import logging
from datetime import date
from functools import partial

import pandas as pd
import streamlit as st

from ai.agents.ppc_audit.chat_document import row_item
from core.chat import app_chat
from core.chat.screen_selection import (
    FROM_AMAZON_ADS,
    FROM_HAND_UPLOAD,
    HAND_UPLOAD_NOTE,
    OLDER_DATA_NOTE,
    ScreenSelection,
    ToolCall,
    account_window,
)
from core.currency_format import money
from core.date_labels import date_range_label
from core.excel_text import force_text_cells
from core.helpers import kpi_card
from core.ppc_audit.analysis import ANALYSIS_MODULE, audit_row_labels, build_analysis_input
from core.ppc_audit.checks import (
    AUTO_FROM_SEARCH_TERMS,
    AUTO_FROM_TARGETING,
    CAMPAIGN_IMPRESSIONS,
    PRODUCTS,
    RECOMMENDATION,
    AuditResult,
    WasteLine,
    acos,
    run_audit,
)
from core.ppc_audit.frames import (
    SB_KEYWORDS,
    SB_SD_CAMPAIGNS,
    SB_SEARCH_TERMS,
    SD_TARGETS,
    SP_TARGET_METRICS,
    SP_TARGETS,
    AuditFrames,
)
from modules.pages.audit_source import MODULE_LABEL, AuditSource, render_audit_source

log = logging.getLogger(__name__)

XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
BRAND_TERMS_KEY = "audit_brand_terms"
BR_UPLOADER_KEY = "audit_br"
GRADUATION_FILTER_KEY = "audit_grad_filter"
DOWNLOAD_KEY = "audit_dl"
GRADUATION_COLUMNS = ["Campaign Name", "Ad Group Name", "Keyword Text", "Match Type", "Bid", "Spend", "Sales",
                      CAMPAIGN_IMPRESSIONS, RECOMMENDATION]
GRADUATION_EXPORT_COLUMNS = ["Campaign Name", "Ad Group Name", "Keyword Text", "Match Type", "Bid", "Spend", "Sales",
                             "Orders", CAMPAIGN_IMPRESSIONS, RECOMMENDATION]
PRODUCT_NAMES = {"SP": "Sponsored Products", "SB": "Sponsored Brands", "SD": "Sponsored Display"}
COUNT_COLUMNS = ("# Targets", "Targets", "Clicks", "Orders", CAMPAIGN_IMPRESSIONS)
PRODUCT_BAND_COLORS = {"SP": "#1d4b8f", "SB": "#6b2d8f", "SD": "#2a6e4e"}
API_GRADUATION_NOTE = ("El bid es el efectivo: el propio del keyword o, si no tiene, el default de su ad group. Se "
                       "excluyen los keywords de ad groups pausados o archivados.")
RUNNING_NOTE = ("Cuentan los keywords habilitados de campañas y ad groups habilitados: lo pausado no compite ni "
                "canibaliza.")
PLACEMENTS_NOT_LISTED = "Los ajustes por placement de esta cuenta todavía no se listaron."

_GRAD_COLORS = {
    "SUBIR BID": "background:#E8F5E9;",
    "PAUSAR": "background:#FFEBEE;",
    "GRADUAR": "background:#FFF8E1;",
    "MANTENER": "background:#E3F2FD;",
    "YA PAUSADO": "background:#F5F5F5;",
}
_VERDICT_COLORS = {
    "ACTUAR": "background-color:#EAF3DE;color:#173404",
    "ESPERAR": "background-color:#F1EFE8;color:#2C2C2A",
    "INVESTIGAR": "background-color:#FAEEDA;color:#412402",
}
_GROUP_TAGS = {"match_mixto": "Match types mixtos", "campana": "Top campaña", "duplicado": "Duplicado",
               "graduacion": "Target Graduation", "termino_sin_venta": "Search term sin ventas"}
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre la auditoría que ya calculó el módulo: qué hallazgos atender primero",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_title": "Hallazgos priorizados — lectura IA",
           "col_item": "Campaña, keyword o término",
           "counts": "{n} hallazgos priorizados",
           "no_rows": ("No hay campañas con match types mixtos, keywords duplicadas, targets sin impresiones ni "
                       "search terms sin ventas para analizar.")},
    "en": {"title": "AI analysis",
           "caption": "AI read on the audit the module already computed: which findings to act on first",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_title": "Prioritized findings — AI read",
           "col_item": "Campaign, keyword or term",
           "counts": "{n} findings prioritized",
           "no_rows": ("No campaigns with mixed match types, duplicate keywords, targets without impressions or "
                       "search terms without sales to analyze.")},
}


def render():
    _header()
    _how_to_use()
    source = render_audit_source()
    if source is None:
        app_chat.withdraw_selection()
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    brand_col, report_col = st.columns(2)
    with brand_col:
        brand_input = st.text_input("Brand terms (separados por coma)",
                                    placeholder="ej: 360 essentials, escape plus, freedom plus", key=BRAND_TERMS_KEY)
    with report_col:
        report_file = st.file_uploader("💰 Business Report (.xlsx/.csv) — opcional", type=["xlsx", "csv"],
                                       key=BR_UPLOADER_KEY)
    brand_terms = tuple(term.strip().lower() for term in (brand_input or "").split(",") if term.strip())
    business_report = _read_business_report(report_file)

    frames = source.frames
    result = run_audit(frames, brand_terms=brand_terms, business_report=business_report)
    st.success(_loaded_line(frames))

    tab_kpis, tab_structure, tab_segments, tab_deep, tab_export, tab_graduation, tab_ai = st.tabs([
        "📊 KPIs Overview",
        "🛠️ Auditoría Estructura",
        "🎯 Performance Segmento",
        "🔍 Deep Checks",
        "📥 Export",
        "🎯 Target Graduation",
        "🤖 Análisis IA",
    ])
    with tab_kpis:
        _render_kpis(result, frames)
    with tab_structure:
        _render_structure_checks(result, frames)
    with tab_segments:
        _render_segments(result, frames)
    with tab_deep:
        _render_deep_checks(result, frames, brand_terms)
    with tab_export:
        _render_export(result, source)
    with tab_graduation:
        _render_graduation(result, frames)
    with tab_ai:
        _render_ai_tab(source, result, brand_terms)
    app_chat.share_selection(screen_selection(source, brand_terms))


def screen_selection(source: AuditSource, brand_terms: tuple[str, ...]) -> ScreenSelection:
    """What the chat reads about this screen: the account, the days, the brand terms and the call behind the audit."""
    values = (("brand terms", ", ".join(brand_terms) or "ninguno"),)
    if not source.from_amazon_ads:
        return ScreenSelection(module=MODULE_LABEL, account=source.label, source=FROM_HAND_UPLOAD, values=values,
                               notes=(HAND_UPLOAD_NOTE,))
    call = ToolCall("ppc_audit", account_window(source.profile_id, source.window_start, source.window_end)
                    + ((("brand_terms", list(brand_terms)),) if brand_terms else ()))
    return ScreenSelection(module=MODULE_LABEL, account=source.label, source=FROM_AMAZON_ADS,
                           profile_id=source.profile_id, window_start=source.window_start,
                           window_end=source.window_end, values=values, calls=(call,),
                           notes=(OLDER_DATA_NOTE,) if source.older_data else ())


def _header():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🛡️</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>PPC Audit Pro</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Auditoría de la estructura y el rendimiento de las campañas de Amazon Advertising</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Auditoría completa de la estructura de campañas: breakdown real SP/SB/SD, segmentos, deep "
                       "checks y Target Graduation, también de los keywords y targets sin tráfico.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("De la cuenta de Amazon Ads conectada que elijas. Sin cuenta conectada, o si preferís, del "
                       "Bulk File (.xlsx) de Campaign Manager → Bulk Operations. El Business Report es opcional, "
                       "para TACoS y revenue.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("PPC Insights (M18) para health score por ASIN o Bid Optimizer (M9) para ajustar bids.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí la cuenta, el país y el período (o subí el Bulk File a mano)\n"
            "2. Ingresá los brand terms y, si querés, subí el Business Report\n"
            "3. Revisá KPIs → Estructura → Performance → Deep Checks → Target Graduation\n"
            "4. Análisis IA: qué hallazgos atender primero\n"
            "5. Descargá el Excel de la auditoría"
        )


def _read_business_report(uploaded) -> pd.DataFrame | None:
    if uploaded is None:
        return None
    buffer = io.BytesIO(uploaded.getvalue())
    try:
        report = pd.read_excel(buffer) if uploaded.name.endswith(".xlsx") else pd.read_csv(buffer)
    except (ValueError, UnicodeDecodeError, OSError) as exc:
        log.warning("ppc audit: business report %s could not be read: %s", uploaded.name, exc)
        st.error("No se pudo leer el Business Report. Subilo tal como lo exporta Seller Central (.csv o .xlsx).")
        return None
    report.columns = report.columns.str.strip()
    return report


def _loaded_line(frames: AuditFrames) -> str:
    origin = "Bulk cargado" if frames.from_file else "Datos de Amazon Ads cargados"
    return (f"✅ {origin} — SP: {len(frames.sp_campaigns)} campañas, {len(frames.sp_keywords)} keywords, "
            f"{len(frames.sp_product_targets)} PT | SB: {len(frames.sb_campaigns)} campañas | "
            f"SD: {len(frames.sd_campaigns)} campañas | SP STR: {len(frames.sp_search_terms)} terms")


def _badge(text, level="ok"):
    """HTML badge. level: ok | warn | crit."""
    styles = {
        "ok": "background:#e6f4ed;color:#2a6e4e;",
        "warn": "background:#fdf3e3;color:#c07a1a;",
        "crit": "background:#fbeae7;color:#c8402a;",
    }
    return (f"<span style='{styles.get(level, styles['ok'])}padding:3px 10px;border-radius:6px;"
            f"font-weight:600;font-size:0.82rem;'>{text}</span>")


def _styled_figures(frame: pd.DataFrame):
    # A Styler prints six decimals unless told otherwise.
    counts = [column for column in COUNT_COLUMNS if column in frame.columns]
    return (frame.style.format(precision=2, thousands=",", na_rep="—")
            .format("{:,.0f}", subset=counts, na_rep="—"))


def _color_acos(val):
    """Style callback for the ACoS column."""
    try:
        value = float(val)
    except (ValueError, TypeError):
        return ""
    if value <= 0:
        return "color:#999"
    if value <= 30:
        return "background:#e6f4ed;color:#2a6e4e"
    if value <= 55:
        return "background:#fdf3e3;color:#c07a1a"
    return "background:#fbeae7;color:#c8402a"


def _markdown_money(value: float, currency_code: str) -> str:
    # Two dollar signs in one Streamlit markdown string read as LaTeX.
    return money(value, currency_code).replace("$", "\\$")


def _band(product: str) -> None:
    st.markdown(
        f"<div style='background:{PRODUCT_BAND_COLORS[product]};color:white;padding:6px 14px;"
        f"border-radius:8px;font-weight:600;margin-bottom:0.5rem;'>{PRODUCT_NAMES[product]}</div>",
        unsafe_allow_html=True,
    )


def _render_kpis(result: AuditResult, frames: AuditFrames):
    currency = frames.currency_code
    totals = result.totals
    known = any(t.campaigns > t.unknown for t in totals.values())
    report = result.business_report
    if report is not None:
        first_row = st.columns(3)
        with first_row[0]:
            st.markdown(kpi_card("Revenue Total", money(report.revenue, currency)), unsafe_allow_html=True)
        with first_row[1]:
            st.markdown(kpi_card("Ventas Orgánicas", money(report.organic_sales, currency),
                                 delta=report.organic_pct), unsafe_allow_html=True)
            st.caption(f"{report.organic_pct:.1f}% del revenue")
        with first_row[2]:
            st.markdown(kpi_card("TACoS", f"{report.tacos:.1f}%", delta=report.tacos - 15, delta_good=False),
                        unsafe_allow_html=True)
            st.markdown(_tacos_badge(report.tacos), unsafe_allow_html=True)
    else:
        st.info("💡 Subí el Business Report para ver TACoS, Revenue y Ventas Orgánicas.")

    second_row = st.columns(3)
    with second_row[0]:
        st.markdown(kpi_card("ACoS Overall", f"{result.acos:.1f}%" if known else "—"), unsafe_allow_html=True)
        breakdown = [f"{product} {acos(totals[product].spend, totals[product].sales):.1f}%"
                     for product in PRODUCTS if totals[product].sales > 0]
        if breakdown:
            st.caption(" | ".join(breakdown))
    with second_row[1]:
        st.markdown(kpi_card("Impressions", f"{result.impressions:,.0f}" if known else "—"), unsafe_allow_html=True)
        shares = [f"{product} {totals[product].impressions / result.impressions * 100:.0f}%"
                  for product in PRODUCTS if totals[product].impressions > 0 and result.impressions > 0]
        if shares:
            st.caption(" | ".join(shares))
    with second_row[2]:
        st.markdown(kpi_card("PPC Spend", money(result.spend, currency) if known else "—"), unsafe_allow_html=True)
        if known:
            spends = " / ".join(f"{product} {_markdown_money(totals[product].spend, currency)}"
                                for product in PRODUCTS)
            st.caption(f"Sales: {_markdown_money(result.sales, currency)} | {spends}")

    st.markdown("")
    third_row = st.columns(4)
    ctr = (result.clicks / result.impressions * 100) if result.impressions > 0 else 0
    cvr = (result.orders / result.clicks * 100) if result.clicks > 0 else 0
    for column, (label, value) in zip(third_row, (("Clicks", f"{result.clicks:,.0f}"),
                                                  ("Orders", f"{result.orders:,.0f}"),
                                                  ("CTR", f"{ctr:.2f}%"), ("CVR", f"{cvr:.2f}%"))):
        with column:
            st.markdown(kpi_card(label, value if known else "—"), unsafe_allow_html=True)

    for note in _kpi_notes(result, frames, known):
        st.caption(note)


def _tacos_badge(tacos: float) -> str:
    if tacos < 10:
        return _badge("Excelente", "ok")
    if tacos < 20:
        return _badge("Saludable", "ok")
    if tacos < 35:
        return _badge("Alto", "warn")
    return _badge("Crítico", "crit")


def _kpi_notes(result: AuditResult, frames: AuditFrames, known: bool) -> list[str]:
    notes = []
    if not known and any(t.campaigns for t in result.totals.values()):
        notes.append("Las métricas de campañas del período todavía no se sincronizaron: los KPIs quedan vacíos, "
                     "no en cero.")
    else:
        unknown = sum(t.unknown for t in result.totals.values())
        if unknown:
            notes.append(f"{unknown} campañas sin métricas del período todavía (por ejemplo, Sponsored Brands del "
                         "formato anterior): no suman en los KPIs.")
    if SB_SD_CAMPAIGNS in frames.unavailable:
        notes.append(frames.unavailable[SB_SD_CAMPAIGNS])
    return notes


def _render_structure_checks(result: AuditResult, frames: AuditFrames):
    currency = frames.currency_code
    card_mixed, card_targets, card_terms = st.columns(3)

    with card_mixed:
        st.markdown("**Match Types Mixtos**")
        mixed = result.mixed_match_campaigns
        if not mixed:
            st.markdown(_badge("OK — 0 campañas mixtas", "ok"), unsafe_allow_html=True)
        else:
            st.markdown(_badge(f"REVISAR — {len(mixed)} campañas mixtas", "warn"), unsafe_allow_html=True)
            with st.expander(f"Ver {len(mixed)} campañas mixtas"):
                for name in mixed[:20]:
                    st.caption(f"• {name}")
        st.markdown("")
        st.caption("Distribución SP Keywords (habilitadas):")
        if result.sp_match_types:
            for match_type, count in result.sp_match_types.items():
                st.caption(f"  {match_type}: {count}")
        else:
            st.caption("  Sin datos")
        if result.sb_match_types:
            st.caption("Distribución SB Keywords (habilitadas):")
            for match_type, count in result.sb_match_types.items():
                st.caption(f"  {match_type}: {count}")
        st.caption(RUNNING_NOTE)

    with card_targets:
        st.markdown("**Target WAS (Wasted Ad Spend)**")
        waste = result.target_waste
        st.markdown(_waste_badge(waste.pct, "waste", (20, 40)), unsafe_allow_html=True)
        st.markdown(f"**{_markdown_money(waste.total_waste, currency)}** desperdicio en targets")
        for product, line, part in (("SP", waste.sp, SP_TARGETS), ("SB", waste.sb, SB_KEYWORDS),
                                    ("SD", waste.sd, SD_TARGETS)):
            st.caption(_waste_caption(product, line, "targets", currency, _missing(frames, part, product)))

    with card_terms:
        st.markdown("**Search Term WAS**")
        terms = result.search_term_waste
        st.markdown(_waste_badge(terms.pct, "SP ST waste", (25, 40)), unsafe_allow_html=True)
        st.markdown(f"**{_markdown_money(terms.total_waste, currency)}** desperdicio en search terms")
        st.caption(_waste_caption("SP", terms.sp, "terms", currency, ""))
        st.caption(_waste_caption("SB", terms.sb, "terms", currency, frames.unavailable.get(SB_SEARCH_TERMS, "")))
        if not terms.top_terms.empty:
            st.markdown("")
            st.caption("Top 5 SP search terms sin ventas:")
            st.dataframe(terms.top_terms, use_container_width=True, hide_index=True,
                         height=min(38 + 35 * len(terms.top_terms), 220))


def _missing(frames: AuditFrames, part: str, product: str) -> str:
    if product == "SP":
        return frames.unavailable.get(SP_TARGETS) or frames.unavailable.get(SP_TARGET_METRICS, "")
    return frames.unavailable.get(part, "")


def _waste_badge(pct: float, label: str, limits: tuple[int, int]) -> str:
    if pct < limits[0]:
        return _badge(f"OK — {pct:.1f}% {label}", "ok")
    if pct < limits[1]:
        return _badge(f"REVISAR — {pct:.1f}% {label}", "warn")
    return _badge(f"CRÍTICO — {pct:.1f}% {label}", "crit")


def _waste_caption(product: str, line: WasteLine | None, unit: str, currency: str, reason: str) -> str:
    if line is None:
        return f"{product}: sin dato — {reason}" if reason else f"{product}: sin dato"
    return f"{product}: {money(line.waste, currency)} ({line.count} {unit})"


def _render_segments(result: AuditResult, frames: AuditFrames):
    _band("SP")
    _segment_table(result.sp_segments, 500)
    for note in _sp_segment_notes(result, frames):
        st.caption(note)

    for product, segments, campaigns in (("SB", result.sb_segments, frames.sb_campaigns),
                                         ("SD", result.sd_segments, frames.sd_campaigns)):
        st.markdown("")
        if campaigns.empty:
            st.caption(_no_product_caption(product, frames))
            continue
        _band(product)
        _segment_table(segments, 300)
        if product == "SB" and SB_KEYWORDS in frames.unavailable:
            st.caption(f"Los segmentos por keyword quedan vacíos: {frames.unavailable[SB_KEYWORDS]}")


def _segment_table(segments: pd.DataFrame, max_height: int):
    if segments.empty:
        st.caption("Sin datos")
        return
    st.dataframe(_styled_figures(segments).map(_color_acos, subset=["ACoS"]), use_container_width=True,
                 hide_index=True, height=min(38 + 35 * len(segments), max_height))


def _sp_segment_notes(result: AuditResult, frames: AuditFrames) -> list[str]:
    notes = []
    missing = frames.unavailable.get(SP_TARGETS) or frames.unavailable.get(SP_TARGET_METRICS)
    if missing:
        notes.append(f"Los segmentos de keywords, product targeting y AUTO quedan vacíos: {missing}")
    auto_rows = result.sp_segments[result.sp_segments["Segmento"].str.startswith("AUTO")]
    if auto_rows["# Targets"].sum() > 0:
        if result.auto_segments_source == AUTO_FROM_TARGETING:
            notes.append("AUTO: métricas de los grupos de targeting automático (close-match, loose-match, "
                         "substitutes, complements), con todo su tráfico.")
        elif result.auto_segments_source == AUTO_FROM_SEARCH_TERMS:
            notes.append("AUTO: search terms de las campañas automáticas. El Search Term Report sólo trae términos "
                         "con clicks, así que sus impresiones quedan cortas.")
    return notes


def _no_product_caption(product: str, frames: AuditFrames) -> str:
    if frames.from_file:
        return f"Sin datos de {product} en este Bulk File"
    if SB_SD_CAMPAIGNS in frames.unavailable:
        return f"Sin datos de {product}: {frames.unavailable[SB_SD_CAMPAIGNS]}"
    return f"La cuenta no tiene campañas de {PRODUCT_NAMES[product]}."


def _render_deep_checks(result: AuditResult, frames: AuditFrames, brand_terms: tuple[str, ...]):
    st.markdown("**Top 5 Campañas SP por Spend**")
    if frames.sp_campaigns.empty:
        st.caption("Sin datos de campañas SP")
    elif result.top_campaigns.empty:
        st.caption("Sin campañas SP con spend")
    else:
        st.dataframe(result.top_campaigns, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**Clasificación de Targets**")
    if not brand_terms:
        st.info("Ingresá brand terms arriba para clasificar targets por tipo (own brand, competitor, generic)")
    elif result.target_types.empty:
        st.caption("Sin keywords ni PT para clasificar")
    else:
        st.dataframe(_styled_figures(result.target_types).map(_color_acos, subset=["ACoS"]), use_container_width=True,
                     hide_index=True)
        if not frames.from_file:
            st.caption("ASINs propios: los que la cuenta anuncia en Sponsored Products, más los del Business Report.")

    st.markdown("---")
    st.markdown("**Duplicación de Targets (Keywords en 2+ campañas)**")
    if frames.sp_keywords.empty:
        st.caption("Sin datos suficientes de keywords SP")
    elif result.duplicates.empty:
        st.caption("No se detectaron keywords duplicadas entre campañas")
    else:
        st.dataframe(result.duplicates, use_container_width=True, hide_index=True)
    st.caption(RUNNING_NOTE)

    st.markdown("---")
    st.markdown("**Bid Adjustments por Placement**")
    if result.placements.empty:
        st.caption("Sin datos de Bid Adjustments" if frames.from_file else PLACEMENTS_NOT_LISTED)
    else:
        st.dataframe(result.placements, use_container_width=True, hide_index=True)
        st.caption("Campañas habilitadas; Con_Ajuste cuenta las que suben el bid en ese placement.")
    if not result.bidding_strategies.empty:
        st.caption("Distribución Bidding Strategy (campañas habilitadas):")
        st.dataframe(result.bidding_strategies, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("**SKAG vs Bolsa (targets por campaña manual)**")
    if result.skag.empty:
        st.caption("Sin campañas manuales habilitadas con targets activos")
    else:
        st.dataframe(result.skag, use_container_width=True, hide_index=True)
        st.caption("Campañas manuales habilitadas, por cuántos keywords y product targets corren en ellas.")


def _render_export(result: AuditResult, source: AuditSource):
    today = date.today().isoformat()
    try:
        excel_bytes = build_audit_excel(result, kpi_rows(result, source, today))
    except (ValueError, OSError) as exc:
        log.exception("ppc audit: the Excel could not be built for %s", source.label)
        st.error(f"No se pudo generar el Excel: {exc}")
        return
    st.download_button(
        "⬇️ Descargar Auditoría Completa (Excel)",
        data=excel_bytes,
        file_name=f"PPC_Audit_{today}.xlsx",
        mime=XLSX_MIME,
        use_container_width=True,
        key=DOWNLOAD_KEY,
    )


def kpi_rows(result: AuditResult, source: AuditSource, today: str) -> dict[str, str]:
    currency = source.frames.currency_code
    rows = {
        "Total PPC Spend": money(result.spend, currency),
        "Total PPC Sales": money(result.sales, currency),
        "ACoS Overall": f"{result.acos:.1f}%",
        "Impressions": f"{result.impressions:,.0f}",
        "Clicks": f"{result.clicks:,.0f}",
        "Orders": f"{result.orders:,.0f}",
        "SP Campañas": str(result.totals["SP"].campaigns),
        "SB Campañas": str(result.totals["SB"].campaigns),
        "SD Campañas": str(result.totals["SD"].campaigns),
        "Fuente": "Amazon Ads" if source.from_amazon_ads else "Bulk File subido a mano",
        "Cuenta": source.label,
        "Fecha": today,
    }
    if source.window_start and source.window_end:
        rows["Período"] = date_range_label(source.window_start, source.window_end)
    report = result.business_report
    if report is not None:
        rows["Revenue Total"] = money(report.revenue, currency)
        rows["TACoS"] = f"{report.tacos:.1f}%"
        rows["Ventas Orgánicas"] = money(report.organic_sales, currency)
    return rows


def build_audit_excel(result: AuditResult, kpis: dict[str, str]) -> bytes:
    """The audit as a workbook: KPIs, segments, the three structure checks, top campaigns, target types,
    duplicates and Target Graduation."""
    target_waste, term_waste = result.target_waste, result.search_term_waste
    mixed = result.mixed_match_campaigns
    audit_rows = [
        ["Match Types Mixtos", f"{len(mixed)} campañas mixtas",
         ", ".join(mixed[:5]) + ("..." if len(mixed) > 5 else "") if mixed else "Ninguna"],
        ["Target WAS", f"{target_waste.total_waste:,.2f} ({target_waste.pct:.1f}%)",
         " | ".join(f"{product}: {_excel_waste(line)}" for product, line in
                    (("SP", target_waste.sp), ("SB", target_waste.sb), ("SD", target_waste.sd)))],
        ["Search Term WAS", f"{term_waste.total_waste:,.2f} ({term_waste.pct:.1f}%)",
         " | ".join(f"{product}: {_excel_waste(line, ' terms')}" for product, line in
                    (("SP", term_waste.sp), ("SB", term_waste.sb)))],
    ]
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        pd.DataFrame(list(kpis.items()), columns=["Metrica", "Valor"]).to_excel(
            writer, sheet_name="Resumen KPIs", index=False)
        segments = [part for segment in (result.sp_segments, result.sb_segments, result.sd_segments)
                    if not segment.empty for part in (pd.DataFrame([{"Segmento": ""}]), segment)][1:]
        if segments:
            pd.concat(segments, ignore_index=True).to_excel(writer, sheet_name="Performance Segmento", index=False)
        pd.DataFrame(audit_rows, columns=["Check", "Resultado", "Detalle"]).to_excel(
            writer, sheet_name="Auditoria", index=False)
        for sheet_name, table in (("Top Campanas", result.top_campaigns),
                                  ("Clasificacion Targets", result.target_types),
                                  ("Duplicacion Targets", result.duplicates)):
            if not table.empty:
                table.to_excel(writer, sheet_name=sheet_name, index=False)
        if not result.graduation.empty:
            columns = [column for column in GRADUATION_EXPORT_COLUMNS if column in result.graduation.columns]
            result.graduation[columns].to_excel(writer, sheet_name="Target Graduation", index=False)
        # Keywords and campaign names are text: one that starts with "=" must never run as a formula.
        force_text_cells(writer.book)
    return buffer.getvalue()


def _excel_waste(line: WasteLine | None, unit: str = "") -> str:
    if line is None:
        return "sin dato"
    return f"{line.waste:,.2f}" + (f" ({line.count}{unit})" if unit else "")


def _render_graduation(result: AuditResult, frames: AuditFrames):
    st.markdown("#### Targets con 0 impresiones en campañas activas")
    st.caption("Identifica keywords/targets que no reciben tráfico aunque su campaña sí. "
               "Posibles causas: bid muy bajo, keyword irrelevante o duplicada.")
    if not frames.from_file:
        st.caption(API_GRADUATION_NOTE)
    missing = frames.unavailable.get(SP_TARGETS) or frames.unavailable.get(SP_TARGET_METRICS)
    if missing:
        st.info(missing)
        return
    graduation = result.graduation
    if graduation.empty:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>✅</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Sin targets huérfanos</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
            "Todos los targets en campañas activas tienen impresiones</div>"
            "</div>", unsafe_allow_html=True,
        )
        return

    recommendations = graduation[RECOMMENDATION]
    total = len(graduation)
    raise_bid = int(recommendations.str.contains("SUBIR BID", na=False).sum())
    pause = int(recommendations.str.contains("PAUSAR", na=False).sum())
    graduate = int(recommendations.str.contains("GRADUAR", na=False).sum())
    keep = int(recommendations.str.contains("MANTENER", na=False).sum())
    cards = st.columns(4)
    for column, (label, value) in zip(cards, (("Targets sin impresiones", total), ("Subir Bid", raise_bid),
                                              ("Pausar", pause),
                                              ("Mantener (marca)" if keep else "Graduar a SKAG",
                                               keep if keep else graduate))):
        with column:
            st.markdown(kpi_card(label, str(value)), unsafe_allow_html=True)

    options = sorted(recommendations.unique().tolist())
    selected = st.multiselect("Filtrar por recomendación", options=options, default=options,
                              key=GRADUATION_FILTER_KEY)
    shown = graduation[recommendations.isin(selected)]
    columns = [column for column in GRADUATION_COLUMNS if column in shown.columns]
    if columns:
        styled = _styled_figures(shown[columns].reset_index(drop=True)).apply(_graduation_style, axis=1)
        st.dataframe(styled, use_container_width=True, height=450)
        st.caption(f"Mostrando {len(shown)} de {total} targets")


def _graduation_style(row):
    recommendation = str(row.get(RECOMMENDATION, ""))
    style = next((css for key, css in _GRAD_COLORS.items() if key in recommendation), "")
    return [style] * len(row)


def _render_ai_tab(source: AuditSource, result: AuditResult, brand_terms: tuple[str, ...]):
    from ai.agents.ppc_audit import chat_document
    from ai.config import AI_ENABLED
    from core import ai_tab

    lang = ai_tab.app_language()
    texts = _AI_TEXTS.get(lang, _AI_TEXTS["es"])
    st.subheader(texts["title"])
    st.caption(texts["caption"])
    if not AI_ENABLED:
        st.caption(texts["disabled"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    currency = source.frames.currency_code
    analysis_input = build_analysis_input(
        source.frames, result, account_label=source.label, period_label=_period_label(source),
        currency_code=currency, attribution_days=source.attribution_days, brand_terms=brand_terms, lang=lang)
    if analysis_input.data is None:
        st.info(texts["no_rows"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    payload = analysis_input.data
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload, file_signature=source.signature,
                                       labels=labels, auto_fire=False)
    records = analysis_input.records
    if analysis is not None:
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload, analysis_input.records)
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels,
                                                     currency_code=currency))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=source.label,
        reading=lambda finished, _records=records: chat_document.reading_text(finished.result, _records),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=audit_row_labels(records)),
        country_code=source.country_code, profile_id=source.profile_id)


def _render_ai_result(result, analysis, *, records, labels, currency_code):
    from core import ai_tab

    opinions = result.get("hallazgos") or []
    warnings = sum(1 for opinion in opinions if opinion.get("advertencia"))
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(opinions)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    row_labels = audit_row_labels(records)
    synthesis = ai_tab.map_synthesis_text(result.get("synthesis") or {},
                                          lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)
    rows = audit_ai_rows(opinions, records, currency_code)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _VERDICT_COLORS),
                    unsafe_allow_html=True)


def audit_ai_rows(opinions: list, records: list, currency_code: str) -> list[dict]:
    """Display rows for the opinion table: the campaign, keyword or term, its group, its figures and the AI's read."""
    by_id = dict(zip(audit_row_labels(records), records))
    rows = []
    for opinion in opinions:
        row_id = str(opinion.get("row_id", ""))
        record = by_id.get(row_id)
        if record is None:
            continue
        rows.append({
            "row_id": row_id,
            "item": row_item(record),
            "type_tag": _GROUP_TAGS.get(record.get("grupo"), ""),
            "metrics": _row_metrics(record, currency_code),
            "badges": [opinion.get("veredicto", "")],
            "confidence": str(opinion.get("confianza", "")).upper(),
            "warning": opinion.get("advertencia") or "",
            "reasoning": opinion.get("razon", ""),
        })
    return rows


def _row_metrics(record: dict, currency_code: str) -> list[str]:
    metrics = []
    if record.get("match_types"):
        metrics += [str(record["match_types"]), f"{record.get('keywords')} keywords"]
    if record.get("spend") is not None:
        metrics.append(f"gasto {money(record['spend'], currency_code)}")
    if record.get("sales") is not None:
        metrics.append(f"ventas {money(record['sales'], currency_code)}")
    if record.get("acos") is not None:
        metrics.append(f"ACoS {record['acos']}%")
    if record.get("campanas") is not None:
        metrics.append(f"{record['campanas']} campañas")
    if record.get("impresiones_campana") is not None:
        metrics.append(f"{record['impresiones_campana']:,} impresiones de su campaña")
    if record.get("recomendacion"):
        metrics.append(str(record["recomendacion"]))
    return metrics


def _period_label(source: AuditSource) -> str:
    if source.window_start is None or source.window_end is None:
        return ""
    return date_range_label(source.window_start, source.window_end)
