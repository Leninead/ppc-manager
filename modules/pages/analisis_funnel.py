"""Análisis de Funnel (M8): cobertura de las campañas activas, brechas, campañas sugeridas y harvest.

Los search terms y las campañas llegan de Amazon Ads con una sola elección de cuenta, país y período; sin cuenta
conectada, de dos archivos subidos a mano. Las reglas viven en core/funnel/coverage.py, que también lee el MCP.
"""
import hashlib
import io
import logging
from functools import partial

import pandas as pd
import streamlit as st

from ai.agents.funnel.chat_document import row_item
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
from core.excel_text import force_text_cells
from core.funnel.analysis import ANALYSIS_MODULE, build_analysis_input, funnel_row_labels
from core.funnel.coverage import (
    DEFAULT_MATCH_TYPE,
    DEFAULT_MIN_ORDERS,
    MATCH_TYPES,
    MATCHED_BY_ID,
    SUGGESTED_MATCH_COLUMN,
    FunnelCoverage,
    FunnelInputError,
    cover,
    harvest_candidates,
    suggested_campaigns,
    visible_columns,
)
from core.search_term.frame import SOURCE_API
from core.ui.kpi_grid import Kpi, render_kpi_grid
from modules.pages import search_term_source
from modules.pages.campaign_source import render_campaigns_for
from modules.pages.search_term_source import count_label, date_range_label, render_source_picker, shows_older_data

log = logging.getLogger(__name__)

MODULE_LABEL = "Análisis de Funnel"
SEARCH_TERMS_KEY = "funnel"
CAMPAIGNS_KEY = "funnel_campaigns"
MATCH_TYPE_KEY = "match_type_sug"
MIN_ORDERS_KEY = "min_harvest"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
ACTIVE_CAMPAIGN_COLUMNS = ["Campaign name", "Type", "Portfolio name", "Campaign bid strategy",
                           "Campaign budget amount", "Impressions", "Clicks", "CTR", "Total cost", "CPC",
                           "Purchases", "Sales", "ACOS", "ROAS"]
IDLE_CAMPAIGN_COLUMNS = ["Campaign name", "Portfolio name", "Campaign budget amount", "Impressions", "Clicks",
                         "Total cost"]

MATCHED_BY_ID_NOTE = "Cruce por Campaign ID: una campaña renombrada en el período no se parte en dos."
MATCHED_BY_NAME_NOTE = ("Cruce por nombre de campaña: los archivos subidos a mano no traen IDs que se puedan "
                        "comparar, así que una campaña renombrada puede aparecer como activa sin tráfico y, a la "
                        "vez, como origen de términos «No encontrada».")
IDLE_NOTE = ("Una campaña activa sin tráfico no tuvo ni un search term con clicks en el período: Amazon sólo "
             "reporta términos con clicks.")
MANUAL_CAMPAIGNS_NOTE = ("Las campañas se subieron a mano: funnel_coverage lee las sincronizadas de la cuenta, que "
                         "pueden no coincidir con el archivo.")

_GROUP_TAGS = {"harvest": "Harvest", "brecha": "Campaña inactiva", "sin_trafico": "Sin tráfico"}
_VERDICT_COLORS = {
    "ACTUAR": "background-color:#EAF3DE;color:#173404",
    "ESPERAR": "background-color:#F1EFE8;color:#2C2C2A",
    "INVESTIGAR": "background-color:#FAEEDA;color:#412402",
}
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre la cobertura, las brechas y el harvest que ya calculó el módulo",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_title": "Filas priorizadas — lectura IA",
           "col_item": "Término o campaña",
           "counts": "{n} filas priorizadas",
           "no_rows": ("No hay candidatos a harvest, términos de campañas inactivas ni campañas activas sin "
                       "tráfico para analizar.")},
    "en": {"title": "AI analysis",
           "caption": "AI read on the coverage, the gaps and the harvest the module already computed",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_title": "Prioritized rows — AI read",
           "col_item": "Term or campaign",
           "counts": "{n} rows prioritized",
           "no_rows": "No harvest candidates, terms of inactive campaigns or idle active campaigns to analyze."},
}


def render():
    st.header("🔻 Análisis de Funnel")
    st.caption("Analizá cobertura de campañas activas, detectá brechas y generá sugerencias de harvesting.")
    st.divider()
    _how_to_use()

    search_terms = render_source_picker(key_prefix=SEARCH_TERMS_KEY, module_label=MODULE_LABEL)
    if search_terms is None:
        app_chat.withdraw_selection()
        return
    campaign_input = render_campaigns_for(CAMPAIGNS_KEY, search_terms)
    if campaign_input is None:
        app_chat.withdraw_selection()
        return

    try:
        coverage = cover(search_terms.frame, campaign_input.frame,
                         match_by_id=search_terms.source == SOURCE_API and campaign_input.source is not None)
    except FunnelInputError as exc:
        log.warning("funnel inputs unusable for %s: %s", search_terms.label, exc)
        st.error(str(exc))
        app_chat.withdraw_selection()
        return

    coverage_tab, suggested_tab, harvest_tab, analysis_tab = st.tabs(
        ["🔗 Cobertura", "📦 Campañas sugeridas", "🌾 Harvesting", "🤖 Análisis IA"])
    with coverage_tab:
        _render_coverage(coverage)
    with suggested_tab:
        match_type, suggested = _render_suggested(coverage)
    with harvest_tab:
        min_orders, harvest = _render_harvest(search_terms.frame, coverage)
    with analysis_tab:
        _render_ai_tab(search_terms, campaign_input, coverage, harvest, suggested, min_orders, match_type)

    older_data = search_terms.source == SOURCE_API and shows_older_data(SEARCH_TERMS_KEY, search_terms.profile_id)
    app_chat.share_selection(screen_selection(search_terms, min_orders=min_orders, match_type=match_type,
                                              campaigns_by_hand=campaign_input.source is None, older_data=older_data))


def screen_selection(search_terms, *, min_orders: int, match_type: str, campaigns_by_hand: bool,
                     older_data: bool) -> ScreenSelection:
    """What the chat reads about this screen: the account, the days, the values and the call behind its figures."""
    values = (("mínimo de órdenes para harvest", str(min_orders)),
              ("match type de las campañas sugeridas", match_type))
    if search_terms.source != SOURCE_API:
        return ScreenSelection(module=MODULE_LABEL, account=search_terms.label, source=FROM_HAND_UPLOAD,
                               values=values, notes=(HAND_UPLOAD_NOTE,))
    call = ToolCall("funnel_coverage", account_window(search_terms.profile_id, search_terms.window_start,
                                                      search_terms.window_end)
                    + (("min_orders", min_orders), ("match_type", match_type)))
    notes = tuple(note for note, applies in ((MANUAL_CAMPAIGNS_NOTE, campaigns_by_hand),
                                             (OLDER_DATA_NOTE, older_data)) if applies)
    return ScreenSelection(module=MODULE_LABEL, account=search_terms.label, source=FROM_AMAZON_ADS,
                           profile_id=search_terms.profile_id,
                           window_start=search_terms.window_start, window_end=search_terms.window_end,
                           values=values, calls=(call,), notes=notes)


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Detectar brechas en el funnel Auto → Broad → Phrase → Exact por ASIN y sugerir campañas "
                       "faltantes.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("Del Search Term Report y las campañas de la cuenta conectada de Amazon Ads. Sin cuenta "
                       "conectada: el STR y el Campaign CSV subidos a mano.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Bid Optimizer (M9) para recalcular bids de las nuevas campañas.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí la cuenta, el país y el período (o subí el STR y el Campaign CSV a mano)\n"
            "2. Cobertura: campañas activas, términos de campañas pausadas y campañas activas sin tráfico\n"
            "3. Campañas sugeridas: nombres con la convención Capybaras\n"
            "4. Harvesting: términos para cosechar en Exact o Phrase\n"
            "5. Análisis IA: lectura priorizada de todo lo anterior\n"
            "6. Descargá los Excel"
        )


def _render_coverage(coverage: FunnelCoverage):
    render_kpi_grid([
        Kpi("Campañas activas", count_label(len(coverage.active_campaigns))),
        Kpi("Pausadas", count_label(coverage.paused_campaigns)),
        Kpi("Total de Sponsored Products", count_label(len(coverage.campaigns))),
    ])
    st.caption(MATCHED_BY_ID_NOTE if coverage.matched_by == MATCHED_BY_ID else MATCHED_BY_NAME_NOTE)
    if coverage.other_products:
        st.caption(f"Quedaron afuera {count_label(coverage.other_products)} campañas de Sponsored Brands y Display: "
                   "el Search Term Report sólo trae términos de Sponsored Products.")

    st.markdown("#### Campañas activas")
    shown = [column for column in ACTIVE_CAMPAIGN_COLUMNS if column in coverage.active_campaigns.columns]
    st.dataframe(coverage.active_campaigns[shown] if shown else coverage.active_campaigns,
                 use_container_width=True, hide_index=True)

    st.markdown("---")
    render_kpi_grid([
        Kpi("Términos de campañas activas", count_label(len(coverage.active_terms))),
        Kpi("Términos de campañas inactivas", count_label(len(coverage.gap_terms))),
        Kpi("Campañas activas sin tráfico", count_label(len(coverage.idle_campaigns))),
    ])

    st.markdown("#### Términos del STR provenientes de campañas activas")
    st.dataframe(visible_columns(coverage.active_terms), use_container_width=True, hide_index=True)

    st.markdown("#### Términos del STR de campañas pausadas o no encontradas")
    gaps = visible_columns(coverage.gap_terms)
    st.dataframe(gaps, use_container_width=True, hide_index=True)
    st.download_button(
        label=f"⬇️ Exportar {count_label(len(gaps))} términos de campañas inactivas",
        data=_xlsx(gaps), file_name="str_campanas_inactivas.xlsx", mime=XLSX_MIME,
        use_container_width=True, key="funnel_dl_inactivas")

    st.markdown("#### Campañas activas sin términos en el STR")
    st.caption(IDLE_NOTE)
    if coverage.idle_campaigns.empty:
        st.success("Todas las campañas activas tuvieron search terms con clicks en el período.")
    else:
        idle_shown = [column for column in IDLE_CAMPAIGN_COLUMNS if column in coverage.idle_campaigns.columns]
        st.dataframe(coverage.idle_campaigns[idle_shown], use_container_width=True, hide_index=True)


def _render_suggested(coverage: FunnelCoverage) -> tuple[str, pd.DataFrame]:
    st.markdown("### Campañas Sugeridas")
    st.info("Nombres generados siguiendo el convention: Producto - ASIN - SP - KW - MatchType - Keyword")
    match_type = st.selectbox("Match Type por defecto", list(MATCH_TYPES), index=MATCH_TYPES.index(DEFAULT_MATCH_TYPE),
                              key=MATCH_TYPE_KEY)
    suggested = suggested_campaigns(coverage.gap_terms, coverage.columns, match_type)
    if suggested.empty:
        st.success("No hay términos de campañas inactivas para sugerir.")
        return match_type, suggested
    st.caption("Ordenadas por gasto: primero los términos que más gastaron desde una campaña inactiva.")
    st.dataframe(suggested, use_container_width=True, hide_index=True)
    st.download_button(
        label=f"⬇️ Exportar {count_label(len(suggested))} campañas sugeridas a Excel",
        data=_xlsx(suggested), file_name="campanas_sugeridas.xlsx", mime=XLSX_MIME,
        use_container_width=True, key="funnel_dl_sugeridas")
    return match_type, suggested


def _render_harvest(search_terms: pd.DataFrame, coverage: FunnelCoverage) -> tuple[int, pd.DataFrame]:
    st.markdown("### Harvesting")
    st.info("Términos del STR con ventas suficientes para cosechar como keywords.")
    min_orders = int(st.number_input("Mínimo de órdenes para cosechar", min_value=1, value=DEFAULT_MIN_ORDERS,
                                     step=1, key=MIN_ORDERS_KEY))
    try:
        harvest = harvest_candidates(search_terms, coverage, min_orders)
    except FunnelInputError as exc:
        st.warning(str(exc))
        return min_orders, pd.DataFrame()

    exact = int((harvest[SUGGESTED_MATCH_COLUMN] == "Exact").sum())
    render_kpi_grid([
        Kpi("Términos para cosechar", count_label(len(harvest))),
        Kpi("→ Exact", count_label(exact)),
        Kpi("→ Phrase", count_label(len(harvest) - exact)),
    ])
    st.markdown(f"**Criterio:** Exact si órdenes ≥ {min_orders * 3} o (órdenes ≥ {min_orders} y ACoS ≤ 25%) · "
                "Phrase en el resto")
    st.dataframe(harvest, use_container_width=True, hide_index=True)
    st.download_button(
        label=f"⬇️ Exportar {count_label(len(harvest))} términos para cosechar",
        data=_xlsx(harvest), file_name="harvesting.xlsx", mime=XLSX_MIME,
        use_container_width=True, key="funnel_dl_harvest")
    return min_orders, harvest


def _render_ai_tab(search_terms, campaign_input, coverage, harvest, suggested, min_orders, match_type):
    from ai.agents.funnel import chat_document
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
    currency_code = search_terms.currency_code or campaign_input.currency_code
    analysis_input = build_analysis_input(
        coverage, harvest, suggested, account_label=search_terms.label, period_label=_period_label(search_terms),
        currency_code=currency_code, attribution_days=search_terms.attribution_days, min_orders=min_orders,
        match_type=match_type, lang=lang)
    if analysis_input.data is None:
        st.info(texts["no_rows"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    payload = analysis_input.data
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload,
                                       file_signature=_data_signature(search_terms, campaign_input), labels=labels,
                                       auto_fire=False)
    records = analysis_input.records
    if analysis is not None:
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload, analysis_input.records)
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels,
                                                     currency_code=currency_code))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=search_terms.label,
        reading=lambda finished, _records=records: chat_document.reading_text(finished.result, _records),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=funnel_row_labels(records)),
        country_code=_country_code(search_terms), profile_id=search_terms.profile_id)


def _render_ai_result(result, analysis, *, records, labels, currency_code):
    from core import ai_tab

    opinions = result.get("filas") or []
    warnings = sum(1 for opinion in opinions if opinion.get("advertencia"))
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(opinions)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    row_labels = funnel_row_labels(records)
    synthesis = ai_tab.map_synthesis_text(result.get("synthesis") or {},
                                          lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)
    rows = funnel_ai_rows(opinions, records, currency_code)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _VERDICT_COLORS),
                    unsafe_allow_html=True)


def funnel_ai_rows(opinions: list, records: list, currency_code: str) -> list[dict]:
    """Display rows for the opinion table: the term or campaign, its group, its figures and the AI's read."""
    by_id = dict(zip(funnel_row_labels(records), records))
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
    group = record.get("grupo")
    if group == "harvest":
        acos = f"ACoS {record['acos']}%" if record.get("acos") is not None else "sin ventas"
        return [f"{record.get('orders')} órdenes", f"ventas {money(record.get('sales') or 0, currency_code)}", acos,
                f"→ {record.get('match_sugerido')}"]
    if group == "brecha":
        return [str(record.get("estado_campana", "")), f"gasto {money(record.get('spend') or 0, currency_code)}",
                f"{record.get('orders')} órdenes"]
    metrics = [f"{record.get('impressions') or 0} impresiones"]
    if record.get("presupuesto") is not None:
        metrics.append(f"presupuesto {money(record['presupuesto'], currency_code)}/día")
    return metrics


def _country_code(search_terms) -> str:
    """The marketplace of the account on screen, for the chat's Amazon Ads region; "" for a file."""
    if search_terms.source != SOURCE_API:
        return ""
    profile = next((option for option in search_term_source._available_profiles()
                    if option.profile_id == search_terms.profile_id), None)
    return profile.country_code if profile is not None else ""


def _period_label(search_terms) -> str:
    if search_terms.window_start is None or search_terms.window_end is None:
        return ""
    return date_range_label(search_terms.window_start, search_terms.window_end)


def _data_signature(search_terms, campaign_input) -> str:
    """What changes when the data under the analysis does, not when a value on screen does."""
    campaigns = pd.util.hash_pandas_object(campaign_input.frame, index=False).values.tobytes()
    return f"{search_terms.signature}|{hashlib.sha256(campaigns).hexdigest()[:16]}"


def _xlsx(frame: pd.DataFrame) -> bytes:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False)
        # Search terms are typed by shoppers: one that starts with "=" must stay text, never run as a formula.
        force_text_cells(writer.book)
    return buffer.getvalue()
