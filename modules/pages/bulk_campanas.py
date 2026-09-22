import io
import logging
import re
from functools import partial
from types import SimpleNamespace

import requests
import streamlit as st
import pandas as pd

from core.amazon_ads.campaign_analyzer import (
    ANALYSIS_MODULE,
    BUDGET_CAPPED_MIN_DAYS,
    LOW_TOP_OF_SEARCH_SHARE,
    NEW_CAMPAIGN_DAYS,
    SIGNALS_COLUMN,
    CampaignAnalyzerParams,
    analyzer_frame,
    provisional_days,
    with_diagnosis,
    with_signals,
)
from core.amazon_ads.campaign_provider import CAMPAIGN_ID, CAMPAIGN_NAME, TYPE
from core.amazon_ads.product_provider import (
    PRODUCT_CODES,
    PRODUCT_TYPES,
    TARGET_BID,
    TARGET_KIND,
    TARGET_MATCH,
    TARGET_PRODUCT,
    TARGET_TEXT,
    all_campaigns,
)
from core.chat import app_chat
from core.chat.screen_selection import (
    FROM_AMAZON_ADS,
    FROM_HAND_UPLOAD,
    HAND_UPLOAD_NOTE,
    ScreenSelection,
    ToolCall,
    account_window,
)
from core.currency_format import currency_symbol, money
from core.integrations.store import StoreError
from modules.pages.campaign_source import render_campaign_source

log = logging.getLogger(__name__)

# ══════════════════════════════════════════════════════════════════════
# Análisis IA (capa core/ai_tab sobre el agente ai/agents/bulk_campaigns)
# ══════════════════════════════════════════════════════════════════════

_AI_LABELS = {
    "title": "Análisis IA",
    "caption": "Lectura ejecutiva de la IA sobre el semáforo y las señales que ya calculó el módulo",
    "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
    "table_campaigns": "Campañas priorizadas — lectura IA",
    "col_item": "Campaña",
    "no_rows": "No hay campañas habilitadas con métricas para analizar en este período.",
    "no_performance": "El análisis IA necesita las métricas de las campañas: gasto, ventas y órdenes.",
    "file_source": ("El análisis IA guardado corre sobre las campañas sincronizadas de Amazon Ads. Con un archivo "
                    "subido a mano no hay dónde guardarlo: elegí una cuenta conectada."),
    "all_products": "Cubre Sponsored Products, Brands y Display, sin importar el producto elegido arriba.",
}
_AI_BADGE_COLORS = {
    "ACTUAR": "background-color:#EAF3DE;color:#173404",
    "ESPERAR": "background-color:#F1EFE8;color:#2C2C2A",
    "INVESTIGAR": "background-color:#FAEEDA;color:#412402",
}
# La causa que elige el agente, en el nombre llano que lee el AM.
_CAUSE_LABELS = {
    "SIN_ENTREGA": "Sin entrega",
    "SIN_CONVERSION": "Sin conversión",
    "COSTO_ALTO": "Costo alto",
    "RELEVANCIA_BAJA": "Relevancia baja",
    "TOPE_DE_PRESUPUESTO": "Tope de presupuesto",
    "BAJA_VISIBILIDAD": "Baja visibilidad",
    "EN_APRENDIZAJE": "En aprendizaje",
    "RENTABLE": "Rentable",
    "POCA_MUESTRA": "Poca muestra",
}
_ALL_PRODUCTS = "Todos"
MODULE_LABEL = "Bulk Campañas"
HAND_UPLOAD_ACCOUNT = "el Campaign CSV subido a mano"
_PRODUCT_HELP = ("Sponsored Brands y Display cuentan una compra después de un click o de una vista, a 14 días, como "
                 "Campaign Manager; Sponsored Products sólo después de un click. Las columnas «(clicks)» muestran "
                 "lo comparable entre productos.")
_WITHOUT_METRICS_NOTE = ("{n} campañas de Sponsored Brands del formato anterior no tienen métricas en la API de "
                         "Amazon: no se diagnostican ni cuentan en los totales.")
_WITHOUT_METRICS_NOTE_ONE = ("1 campaña de Sponsored Brands del formato anterior no tiene métricas en la API de "
                             "Amazon: no se diagnostica ni cuenta en los totales.")
_TARGETS_WAITING = "Los targets de esta cuenta todavía no se sincronizaron: Target Graduation aparece cuando lleguen."
_PRODUCT_TARGETS_WAITING = "Todavía no hay targets de {product} para evaluar en el período."
_NO_IDLE_TARGETS = "Todos los targets habilitados ({n}), en campañas habilitadas, tuvieron impresiones en el período."

_SIGNALS_HELP = (
    f"Marcas que no cambian el diagnóstico. Limitada por presupuesto: dentro del target y gastó al menos el 95% "
    f"de su presupuesto del día en {BUDGET_CAPPED_MIN_DAYS} días o más. Nueva: empezó hace menos de "
    f"{NEW_CAMPAIGN_DAYS} días. Baja visibilidad: en PAUSAR o REVISAR con menos del "
    f"{LOW_TOP_OF_SEARCH_SHARE:g}% de las impresiones de arriba de la búsqueda."
)


# ── Naming convention Capybaras: [Marca] | [ASIN] | [MKT] | [Tipo] | [Match] | [Cluster]
_NAMING_PATTERN = re.compile(
    r'^[^|]+\|'    # Marca
    r'\s*B0[A-Z0-9]{8}\s*\|'  # ASIN
    r'[^|]+\|'    # MKT (SP/SB/SD)
    r'[^|]+\|'    # Tipo (KW/PAT/AUTO)
    r'[^|]+\|'    # Match (Exact/Broad/Phrase)
    r'.+$',       # Cluster
    re.IGNORECASE
)

_NAMING_LOOSE = re.compile(r'B0[A-Z0-9]{8}', re.IGNORECASE)


def _check_naming(name):
    """Retorna (is_capybaras, has_asin) para un campaign name."""
    n = str(name).strip()
    is_capy = bool(_NAMING_PATTERN.match(n))
    has_asin = bool(_NAMING_LOOSE.search(n))
    return is_capy, has_asin


def render():
    st.header("📁 Bulk File de Campañas")
    st.caption("Campañas de Amazon Ads con sus métricas, de la cuenta conectada o de un archivo subido a mano.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Ver estructura de campañas y diagnosticar estado con semáforo automático (pausar/revisar/escalar/fantasmas).")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("De las campañas de la cuenta conectada de Amazon Ads, o del Campaign CSV exportado "
                       "de Campaign Manager.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Business Report (M7) para cruzar con salud del catálogo.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí la cuenta y el período (o subí el Campaign CSV a mano)\n"
            "2. Ingresá Target ACoS + precio promedio\n"
            "3. Tab Campaign Analyzer: revisá semáforo (PAUSAR, REVISAR, ESCALAR, FANTASMA)\n"
            "4. Tab Auditoría: revisá naming convention y target graduation\n"
            "5. Descargá el Excel y pausá manualmente en Campaign Manager las rojas"
        )

    campaign_input = render_campaign_source("bulk")
    if campaign_input is not None:
        df_bulk_raw, product_choice = _campaigns_to_show(campaign_input)
        without_metrics = campaign_input.products.without_metrics if campaign_input.products is not None else frozenset()
        currency = campaign_input.currency_code
        st.success(f"✅ {len(df_bulk_raw)} filas cargadas")

        bulk_tab1, bulk_tab2, bulk_tab3 = st.tabs(["📋 Vista General", "🚦 Campaign Analyzer", "🤖 Análisis IA"])
        source = campaign_input.source
        # Los parámetros del semáforo, que la pestaña IA necesita; None si el archivo no trae métricas.
        analysis_params = None

        # ══════════════════════════════════════════════════════════════════
        # TAB 1 — Vista General (raw)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab1:
            st.dataframe(df_bulk_raw, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════
        # TAB 2 — Campaign Analyzer (Auditoría PPC)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab2:
            st.markdown("### 🚦 Campaign Analyzer")
            st.caption("Diagnóstico automático de campañas. Los thresholds los define el AM según el objetivo de la cuenta.")

            # ── Detectar si el archivo tiene columnas de performance ──────
            _REQUIRED_PERF = ["State", "Total cost", "Sales", "Purchases"]
            _missing_perf = [c for c in _REQUIRED_PERF if c not in df_bulk_raw.columns]
            has_perf = not _missing_perf
            _has_impr = "Impressions" in df_bulk_raw.columns
            _has_acos = "ACOS" in df_bulk_raw.columns
            _has_roas = "ROAS" in df_bulk_raw.columns

            if not has_perf:
                st.warning(
                    f"⚠️ Este archivo no tiene las columnas mínimas para el análisis "
                    f"({', '.join(_missing_perf)}). Subí el Campaign CSV descargado desde "
                    "Campaign Manager con las métricas incluidas."
                )
            else:
                # ── Campañas habilitadas con sus métricas (reglas en core/amazon_ads/campaign_analyzer.py) ──
                # Las SB del formato anterior no tienen métricas en la API: afuera, nunca como fantasmas.
                analyzed = df_bulk_raw
                if without_metrics and CAMPAIGN_ID in df_bulk_raw.columns:
                    analyzed = df_bulk_raw[~df_bulk_raw[CAMPAIGN_ID].isin(without_metrics)]
                    _render_without_metrics(df_bulk_raw[df_bulk_raw[CAMPAIGN_ID].isin(without_metrics)])
                analyzer = analyzer_frame(analyzed)

                # ── Inputs del AM ─────────────────────────────────────────
                # Abren con los parámetros guardados de la cuenta, que son con los que el worker genera su análisis.
                defaults = _account_params(source)
                st.markdown("#### ⚙️ Configuración de la cuenta")
                cfg1, cfg2, cfg3 = st.columns(3)
                target_acos_ca = cfg1.number_input(
                    "Target ACoS (%)",
                    min_value=1.0, max_value=200.0, value=float(defaults.target_acos), step=1.0,
                    help="ACoS objetivo para esta cuenta. Define los umbrales de REVISAR y ESCALAR."
                )
                spend_pausar = cfg2.number_input(
                    f"Spend mínimo para PAUSAR ({currency_symbol(currency)})",
                    min_value=1.0, value=float(defaults.spend_to_pause), step=1.0,
                    help="Spend acumulado sin órdenes a partir del cual se recomienda pausar. El AM lo ajusta según el objetivo de la cuenta."
                )
                min_orders_escalar = cfg3.number_input(
                    "Mínimo de órdenes para ESCALAR",
                    min_value=1, value=int(defaults.min_orders_to_scale), step=1,
                    help="Órdenes mínimas confirmadas para recomendar escalar."
                )
                analysis_params = CampaignAnalyzerParams(float(target_acos_ca), float(spend_pausar),
                                                         int(min_orders_escalar))

                st.markdown("---")

                # ── Diagnóstico y señales ─────────────────────────────────
                df_ca = with_signals(
                    with_diagnosis(analyzer, analysis_params),
                    source.signal_inputs if source is not None else None, analysis_params,
                    window_start=source.window_start if source is not None else None,
                    window_end=source.window_end if source is not None else None)
                has_signals = bool((df_ca[SIGNALS_COLUMN] != "").any())

                # ── Naming convention check ──────────────────────────────
                camp_col = 'Campaign name'
                if camp_col in df_ca.columns:
                    naming_results = df_ca[camp_col].apply(_check_naming)
                    df_ca['_naming_capy'] = naming_results.apply(lambda x: x[0])
                    df_ca['_naming_asin'] = naming_results.apply(lambda x: x[1])

                    n_capy = df_ca['_naming_capy'].sum()
                    n_asin_only = (~df_ca['_naming_capy'] & df_ca['_naming_asin']).sum()
                    n_bad = (~df_ca['_naming_capy'] & ~df_ca['_naming_asin']).sum()

                    df_ca['Naming'] = df_ca.apply(
                        lambda r: "✅ Capybaras" if r['_naming_capy']
                        else ("🟡 Tiene ASIN" if r['_naming_asin'] else "🔴 Sin estándar"),
                        axis=1
                    )

                # ── Target Graduation: targets con 0 impresiones = candidatos a pausar ─────────
                # Con Amazon Ads salen de las listas de keywords y targets; con archivo, de su columna Targeting.
                tgt_display, tgt_caption = None, ""
                if source is not None:
                    tgt_display, tgt_caption = _api_target_graduation(campaign_input.idle_targets, product_choice)
                else:
                    tgt_col = next((c for c in df_ca.columns if 'targeting' in c.lower() and 'type' not in c.lower()), None)
                    if tgt_col and _has_impr:
                        tgt_rows = df_ca[df_ca[tgt_col].notna() & (df_ca[tgt_col].astype(str).str.strip() != "")]
                        df_tgt_dead = tgt_rows[tgt_rows['_impr'] == 0]
                        if len(df_tgt_dead):
                            tgt_show_cols = [c for c in [camp_col, tgt_col, '_spend', '_clicks'] if c in df_tgt_dead.columns]
                            tgt_display = df_tgt_dead[tgt_show_cols].rename(columns={'_spend': 'Spend', '_clicks': 'Clicks'})
                            tgt_caption = f"**{len(df_tgt_dead)} targets** con 0 impresiones en el período completo. Candidatos a pausar."
                has_tgt_graduation = tgt_display is not None and not tgt_display.empty

                # ── KPIs globales ─────────────────────────────────────────
                total_spend   = df_ca['_spend'].sum()
                total_sales   = df_ca['_sales'].sum()
                total_acos    = (total_spend / total_sales * 100) if total_sales > 0 else 0
                spend_recup   = df_ca[df_ca['Diagnóstico'] == '🔴 PAUSAR']['_spend'].sum()

                k1, k2, k3, k4, k5 = st.columns(5)
                k1.metric("Campañas analizadas", len(df_ca))
                k2.metric("Total Spend", money(total_spend, currency))
                k3.metric("Total Sales", money(total_sales, currency))
                k4.metric("ACoS cuenta", f"{total_acos:.1f}%")
                k5.metric("💰 Spend recuperable", money(spend_recup, currency),
                          help="Spend acumulado en campañas marcadas como PAUSAR")

                _avisos = []
                if not _has_impr:
                    _avisos.append(
                        "no incluye **Impressions** — el diagnóstico FANTASMA se calcula con Clicks"
                    )
                if not _has_acos:
                    _origen = "ROAS" if _has_roas else "Spend / Sales"
                    _avisos.append(f"no incluye **ACOS** — se calcula a partir de {_origen}")
                if _avisos:
                    st.caption("ℹ️ El archivo " + "; ".join(_avisos) + ". El resto del análisis no cambia.")
                if source is not None:
                    _provisional = provisional_days(source.window_start, source.window_end)
                    if _provisional:
                        st.caption("Los últimos días del período (" + " y ".join(day.strftime("%d/%m") for day in
                                                                              _provisional)
                                   + ") todavía pueden sumar ventas atribuidas a sus clicks.")

                # ── Conteo por diagnóstico ────────────────────────────────
                st.markdown("#### Resumen por diagnóstico")
                diag_counts = df_ca['Diagnóstico'].value_counts()
                dc1, dc2, dc3, dc4, dc5 = st.columns(5)
                dc1.metric("👻 Fantasmas",  diag_counts.get("👻 FANTASMA", 0))
                dc2.metric("🔴 Pausar",     diag_counts.get("🔴 PAUSAR", 0))
                dc3.metric("🟡 Revisar",    diag_counts.get("🟡 REVISAR", 0))
                dc4.metric("✅ Escalar",    diag_counts.get("✅ ESCALAR", 0))
                dc5.metric("⚪ OK",         diag_counts.get("⚪ OK", 0))

                # ── Naming convention resumen ────────────────────────────
                if camp_col in df_ca.columns:
                    st.markdown("#### Naming Convention")
                    nc1, nc2, nc3 = st.columns(3)
                    nc1.metric("✅ Capybaras estándar", int(n_capy))
                    nc2.metric("🟡 Tiene ASIN (parcial)", int(n_asin_only))
                    nc3.metric("🔴 Sin estándar", int(n_bad))

                    if n_bad > 0:
                        with st.expander(f"Ver {int(n_bad)} campañas sin naming estándar"):
                            df_bad_naming = df_ca[~df_ca['_naming_capy'] & ~df_ca['_naming_asin']][[camp_col, '_spend', '_orders']].copy()
                            df_bad_naming.columns = ['Campaign', 'Spend', 'Orders']
                            st.dataframe(df_bad_naming.sort_values('Spend', ascending=False), use_container_width=True, hide_index=True)

                # ── Target Graduation ─────────────────────────────────────
                if has_tgt_graduation:
                    st.markdown("#### Target Graduation")
                    st.caption(tgt_caption)
                    with st.expander(f"Ver {len(tgt_display)} targets sin impresiones"):
                        st.dataframe(tgt_display, use_container_width=True, hide_index=True)
                elif source is not None and tgt_caption:
                    st.caption(tgt_caption)

                st.markdown("---")

                # ── Filtro por diagnóstico ────────────────────────────────
                opciones_diag = ["Todos"] + sorted(df_ca['Diagnóstico'].unique().tolist())
                filtro_diag = st.selectbox("Filtrar por diagnóstico", opciones_diag, key="ca_filtro_diag")

                df_show = df_ca if filtro_diag == "Todos" else df_ca[df_ca['Diagnóstico'] == filtro_diag]

                # ── Tabla semáforo ────────────────────────────────────────
                show_cols = ['Diagnóstico', 'Campaign name', 'Portfolio name',
                             '_spend', '_sales', '_acos', '_orders', '_impr', '_clicks']
                if camp_col in df_ca.columns and '_naming_capy' in df_ca.columns:
                    show_cols.insert(2, 'Naming')
                if has_signals:
                    show_cols.insert(1, SIGNALS_COLUMN)
                if 'Campaign start date' in df_show.columns:
                    show_cols.append('Campaign start date')
                if 'Campaign bid strategy' in df_show.columns:
                    show_cols.append('Campaign bid strategy')

                if not _has_impr:
                    show_cols = [c for c in show_cols if c != '_impr']

                rename_map = {
                    '_spend': f"Spend ({currency_symbol(currency)})",
                    '_sales': f"Sales ({currency_symbol(currency)})",
                    '_acos': 'ACoS (%)',
                    '_orders': 'Purchases',
                    '_impr': 'Impressions',
                    '_clicks': 'Clicks',
                }

                df_tabla = (
                    df_show[[c for c in show_cols if c in df_show.columns]]
                    .rename(columns=rename_map)
                    .sort_values('Diagnóstico')
                    .reset_index(drop=True)
                )

                # Color de fondo por diagnóstico
                def _color_diag(val):
                    colors = {
                        "🔴 PAUSAR":  "background-color: #FFEBEE",
                        "🟡 REVISAR": "background-color: #FFFDE7",
                        "✅ ESCALAR": "background-color: #E8F5E9",
                        "👻 FANTASMA":"background-color: #F5F5F5",
                        "⚪ OK":      "",
                    }
                    return colors.get(val, "")

                style_subsets = ['Diagnóstico']
                styled = df_tabla.style.map(_color_diag, subset=style_subsets)
                st.dataframe(styled, use_container_width=True, height=500,
                             column_config={SIGNALS_COLUMN: st.column_config.TextColumn(
                                 SIGNALS_COLUMN, help=_SIGNALS_HELP)} if has_signals else None)

                # ── Nota aclaratoria ──────────────────────────────────────
                st.info("💡 **Las pausas se ejecutan manualmente en Campaign Manager.** El bulk update requiere Campaign ID numérico — este diagnóstico es tu guía de acción.")

                # ── Export ────────────────────────────────────────────────
                buf_ca = io.BytesIO()
                with pd.ExcelWriter(buf_ca, engine="openpyxl") as writer:
                    df_tabla.to_excel(writer, sheet_name="Diagnóstico", index=False)
                    if has_tgt_graduation:
                        tgt_display.to_excel(writer, sheet_name="Targets 0 Impr", index=False)
                st.download_button(
                    label=f"⬇️ Exportar diagnóstico ({len(df_tabla)} campañas)",
                    data=buf_ca.getvalue(),
                    file_name="campaign_analyzer.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_ca"
                )

        # ══════════════════════════════════════════════════════════════════
        # TAB 3 — Análisis IA (guardado: lo genera el worker, la pantalla lo busca por huella)
        # ══════════════════════════════════════════════════════════════════
        with bulk_tab3:
            _render_ai_tab(source, analysis_params, campaign_input.products)
        app_chat.share_selection(screen_selection(source, product_choice=product_choice, params=analysis_params))
    else:
        app_chat.withdraw_selection()


def screen_selection(source, *, product_choice: str, params) -> ScreenSelection:
    """What the chat reads about this screen: the account, the days, the thresholds and the calls behind them.

    `params` is None when the campaigns carry no metrics, and then there is no diagnosis to reproduce.
    """
    values = [("producto", product_choice)]
    if params is not None:
        values += [("target ACoS", f"{params.target_acos:g}%"),
                   ("gasto mínimo para PAUSAR", f"{params.spend_to_pause:g}"),
                   ("órdenes mínimas para ESCALAR", str(params.min_orders_to_scale))]
    if source is None:
        return ScreenSelection(module=MODULE_LABEL, account=HAND_UPLOAD_ACCOUNT, source=FROM_HAND_UPLOAD,
                               values=tuple(values), notes=(HAND_UPLOAD_NOTE,))
    window = account_window(source.profile_id, source.window_start, source.window_end)
    product = (("product", PRODUCT_CODES[product_choice]),) if product_choice in PRODUCT_CODES else ()
    thresholds = (() if params is None else
                  (("target_acos", params.target_acos), ("spend_to_pause", params.spend_to_pause),
                   ("min_orders_to_scale", params.min_orders_to_scale)))
    return ScreenSelection(module=MODULE_LABEL, account=source.label, source=FROM_AMAZON_ADS,
                           profile_id=source.profile_id,
                           window_start=source.window_start, window_end=source.window_end, values=tuple(values),
                           calls=(ToolCall("campaign_health", window + product + thresholds),
                                  ToolCall("idle_targets", window + product)))


def _campaigns_to_show(campaign_input) -> tuple[pd.DataFrame, str]:
    """(las campañas a mostrar, el producto elegido). Con SB o SD sincronizadas, un filtro por producto;
    el análisis IA cubre los tres productos sin importar el filtro."""
    products = campaign_input.products
    if products is None or products.frame.empty:
        return campaign_input.frame, _ALL_PRODUCTS
    combined = all_campaigns(campaign_input.frame, products)
    present = [name for name in PRODUCT_TYPES.values() if (combined[TYPE] == name).any()]
    choice = st.segmented_control("Producto", options=[_ALL_PRODUCTS, *present], default=_ALL_PRODUCTS,
                                  key="bulk_product", help=_PRODUCT_HELP) or _ALL_PRODUCTS
    if choice == _ALL_PRODUCTS:
        return combined, choice
    return combined[combined[TYPE] == choice].reset_index(drop=True), choice


def _render_without_metrics(campaigns: pd.DataFrame) -> None:
    if campaigns.empty:
        return
    count = len(campaigns)
    st.caption(_WITHOUT_METRICS_NOTE_ONE if count == 1 else _WITHOUT_METRICS_NOTE.format(n=count))
    with st.expander("Ver 1 campaña sin métricas en la API" if count == 1
                     else f"Ver {count} campañas sin métricas en la API"):
        st.dataframe(campaigns[[CAMPAIGN_NAME, "State"]], use_container_width=True, hide_index=True)


def _api_target_graduation(idle_targets, product_choice: str) -> tuple[pd.DataFrame | None, str]:
    """(tabla, leyenda) de los targets habilitados sin impresiones, para el producto elegido."""
    if idle_targets is None or not idle_targets.considered:
        return None, _TARGETS_WAITING
    frame = idle_targets.frame
    considered = sum(idle_targets.considered.values())
    if product_choice != _ALL_PRODUCTS:
        short = next(key for key, name in PRODUCT_TYPES.items() if name == product_choice)
        frame = frame[frame[TARGET_PRODUCT] == short]
        considered = idle_targets.considered.get(short, 0)
        if considered == 0:
            return None, _PRODUCT_TARGETS_WAITING.format(product=product_choice)
    display = frame[[TARGET_PRODUCT, CAMPAIGN_NAME, TARGET_TEXT, TARGET_KIND, TARGET_MATCH, TARGET_BID]]
    if display.empty:
        return None, _NO_IDLE_TARGETS.format(n=considered)
    caption = (f"**{len(display)} de {considered} targets** habilitados, en campañas habilitadas, "
               "sin una impresión en el período. Candidatos a pausar o a subir la puja.")
    return display.reset_index(drop=True), caption


def _account_params(source) -> CampaignAnalyzerParams:
    """Los parámetros guardados de la cuenta, o los de siempre para un archivo o si la base no contesta."""
    if source is None:
        return CampaignAnalyzerParams.defaults()
    from core.ai_analysis import stored_tab
    from modules.pages import search_term_source

    try:
        settings = stored_tab._settings(ANALYSIS_MODULE, source.profile_id, search_term_source._open_rest)
    except (requests.RequestException, StoreError) as exc:
        log.warning("bulk campaigns: account parameters of %s could not be read: %s", source.profile_id, exc)
        return CampaignAnalyzerParams.defaults()
    return CampaignAnalyzerParams.from_dict(settings.params) if settings else CampaignAnalyzerParams.defaults()


def _render_ai_tab(source, params, products=None) -> None:
    from ai.config import AI_ENABLED

    st.subheader(_AI_LABELS["title"])
    st.caption(_AI_LABELS["caption"])
    if products is not None and not products.frame.empty:
        st.caption(_AI_LABELS["all_products"])
    if not AI_ENABLED:
        st.caption(_AI_LABELS["disabled"])
    elif source is None:
        st.info(_AI_LABELS["file_source"])
    elif params is None:
        st.info(_AI_LABELS["no_performance"])
    else:
        _render_stored_analysis(source, params, products)


def _render_stored_analysis(source, params, products=None) -> None:
    """Busca el análisis de exactamente estas campañas y parámetros; si no existe, ofrece pedirlo."""
    from ai.agent_call import build_agent_call
    from ai.agents.bulk_campaigns import chat_document
    from core import ai_tab
    from core.chat import app_chat
    from core.ai_analysis import stored_tab
    from core.bulk_campaigns.analysis import build_analysis_input, campaign_row_labels
    from core.date_labels import date_range_label
    from modules.pages import search_term_source

    # El mismo payload que arma el worker: si difieren, difiere la huella y nunca encuentra su análisis.
    analysis_input = build_analysis_input(
        source.frame, signal_inputs=source.signal_inputs, params=params, account_label=source.label,
        period_label=date_range_label(source.window_start, source.window_end), currency_code=source.currency_code,
        attribution_days=source.attribution_days, window_start=source.window_start, window_end=source.window_end,
        products=products)
    if analysis_input.data is None:
        st.info(_AI_LABELS["no_rows"])
        return

    labels = ai_tab.ai_labels("es", _AI_LABELS)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    call = build_agent_call(ANALYSIS_MODULE, analysis_input.data)

    def _render(stored):
        # Las filas son las que leyó ESE análisis, no las de esta corrida: los row_ids que cita son suyos.
        _render_ai_result(stored.result, SimpleNamespace(elapsed=int((stored.duration_ms or 0) / 1000)),
                          stored.records, labels, source.currency_code)

    result = stored_tab.render_stored_analysis(
        module=ANALYSIS_MODULE, key_prefix="bulk", source=source, input_digest=call.input_digest,
        params=params, account_params=_account_params(source), open_rest=search_term_source._open_rest,
        current_username=search_term_source._current_username, render_result=_render,
        timezone=search_term_source.DISPLAY_TIMEZONE)

    if result.analysis is None:
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    records = result.analysis.records
    app_chat.share_analysis(app_chat.ChatAnalysis(
        module=ANALYSIS_MODULE, key=f"{ANALYSIS_MODULE}:{result.analysis.input_digest}", subject=source.label,
        documents=tuple({"title": f"Bulk Campañas · {source.label} · {document['title']}",
                         "content": document["content"]} for document in call.call["context"])
        + ({"title": f"Bulk Campañas · {source.label} · Lectura de la IA",
            "content": chat_document.reading_text(result.analysis.result, records)},),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=campaign_row_labels(records)),
        profile_id=source.profile_id))


def _render_ai_result(result, analysis, records, labels, currency_code) -> None:
    from core import ai_tab
    from core.bulk_campaigns.analysis import campaign_row_labels

    row_labels = campaign_row_labels(records)
    by_id = dict(zip(row_labels, records))
    items = result.get("campaigns") or []
    warnings = sum(1 for item in items if item.get("advertencia"))
    st.markdown(ai_tab.ai_chips_html(warnings, f"{len(items)} campañas priorizadas", analysis.elapsed, labels),
                unsafe_allow_html=True)
    synthesis = ai_tab.map_synthesis_text(
        result.get("synthesis") or {}, lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)

    rows = []
    for item in items:
        record = by_id.get(str(item.get("row_id", "")))
        if record is None:
            continue
        # Las cifras que la razón cita tienen que estar en pantalla, o el AM no puede auditar el juicio.
        orders = record.get("orders", 0)
        metrics = [record.get("diagnostico", ""), f"gasto {money(record.get('spend', 0), currency_code)}",
                   f"ACoS {record['acos']:.1f}%" if record.get("acos") is not None else "sin ventas",
                   f"{orders} orden" if orders == 1 else f"{orders} órdenes"]
        if record.get("senales"):
            metrics.append(record["senales"])
        rows.append({
            "row_id": str(item.get("row_id", "")),
            "item": record.get("campaign", ""),
            "metrics": metrics,
            "badges": [item.get("veredicto", ""), _CAUSE_LABELS.get(item.get("causa"), item.get("causa") or "")],
            "confidence": str(item.get("confianza", "")).upper(),
            "warning": item.get("advertencia") or "",
            "reasoning": item.get("razon", ""),
        })
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_campaigns"], labels, _AI_BADGE_COLORS),
                    unsafe_allow_html=True)
