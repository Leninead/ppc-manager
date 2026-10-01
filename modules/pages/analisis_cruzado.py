"""Análisis Cruzado STR vs SQP (M4): what the market searches, from the brand's SQP, crossed with what the account's
Sponsored Products campaigns capture, from its Amazon Ads search terms.

The search terms come from the account the picker chooses. Its SP listing says which exact keywords exist (INV-11.2)
and its product ads which ASIN each ad group advertises. Without connected accounts, or when the AM asks, a Bulk File
uploaded by hand gives the same three from its sheets (core/cross_analysis/bulk_file.py); the rules live in
core/cross_analysis/.
"""
import hashlib
import io
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import partial

import pandas as pd
import streamlit as st

from ai.agents import make_ids
from ai.agents.cross_analysis.chat_document import row_item
from ai.agents.cross_analysis.context import ROW_PREFIX
from core.amazon_ads.active_keywords import enabled_exact_keyword_texts
from core.amazon_ads.report_provider import ProfileOption, ReportProvider, ReportReadError
from core.bulk.export import build_bid_update, build_keyword_create, write_bulk_excel
from core.bulk.parser import validate_bulk
from core.chat import app_chat
from core.cross_analysis.action_plan import (
    ACTION,
    ACTION_ADD,
    ACTION_ASIN,
    ACTION_BRAND_NO_DATA,
    ACTION_BRAND_OK,
    ACTION_CONQUEST,
    ACTION_DEFEND,
    ACTION_DO_NOT_ATTACK,
    ACTION_INVESTIGATE,
    ACTION_LOWER_BID,
    ACTION_MONITOR,
    ACTION_SCALE,
    BRAND_CVR,
    BRAND_PURCHASE_SHARE,
    BRAND_PURCHASES,
    BRAND_QUERY,
    CAMPAIGN_COUNT,
    CVR_MARKET_PARITY,
    FUNNEL_DIAGNOSIS,
    GENERIC_QUERY,
    IN_SEARCH_TERMS,
    MARKET_CLICKS,
    MARKET_CVR,
    MARKET_IMPRESSIONS,
    MARKET_PURCHASE_RATE,
    MARKET_PURCHASES,
    OPPORTUNITY_SCORE,
    QUERY,
    QUERY_SCORE,
    QUERY_TYPE,
    ActionPlanParams,
    build_action_plan,
    comma_terms,
    numeric_sqp,
    query_types,
    with_funnel_diagnosis,
)
from core.cross_analysis.analysis import (
    ANALYSIS_MODULE,
    brand_impression_share,
    build_analysis_input,
    cross_row_labels,
    plan_counts,
)
from core.cross_analysis.asin_summary import (
    ACOS,
    AD_SALES,
    AD_SPEND,
    ASIN,
    ASINS_WITH_TOP_TERMS,
    BR_SALES,
    BR_SESSIONS,
    CVR,
    AsinSummary,
    asin_summary,
    business_report_by_asin,
    top_terms,
)
from core.cross_analysis.bulk_file import BulkFileAccount, BulkFileError, read_bulk_file
from core.cross_analysis.plan_exports import (
    BULK_ACTIONS,
    BULK_CREATE_ACTIONS,
    CB_REASON,
    bulk_rows,
    campaign_builder_plan,
)
from core.cross_analysis.ranking_guards import (
    ALREADY_EXACT,
    NOT_NEGATABLE,
    ORIGIN,
    RANKING_KEYWORD,
    with_ranking_guards,
)
from core.currency_format import currency_symbol, money
from core.date_labels import data_of_day_phrase, date_range_label
from core.excel_text import force_text_cells
from core.helpers import extract_sqp_brand, read_sqp
from core.ppc_insights.asin_health import asin_coverage_caption
from core.search_term.frame import (
    CLICKS,
    PORTFOLIO_NAME,
    SEARCH_TERM,
    SOURCE_FILE,
    SPEND,
    SearchTermSource,
    orders_column,
    sales_column,
)
from modules.pages import search_term_source
from modules.pages.keyword_listing_source import listing_moment, load_keyword_listing, profile_option

log = logging.getLogger(__name__)

MODULE_LABEL = "Análisis Cruzado"
KEY_PREFIX = "cruzado"
# The upload button's own keys: the picker already owns the actions container of KEY_PREFIX.
BULK_PREFIX = "cruzado_bulk"
XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
TABLE_ROW_LIMIT = 1000
ADVERTISED_ASINS_TTL_SECONDS = 120
# INV-1: Amazon's auction takes no bid below this.
MINIMUM_AMAZON_BID = 0.10

EXACT_LISTED_CAPTION = "Keywords Exact de la cuenta: listado de Sponsored Products {listed} · {count}."
EXACT_NOT_LISTED_NOTE = ("Todavía no hay un listado de las campañas y keywords de Sponsored Products de esta cuenta: "
                         "se listan una vez por día. Mientras tanto, «♻️ Ya en Exact» queda sin dato.")
EXACT_REFUSED_NOTE = ("Amazon rechazó el listado de Sponsored Products de esta cuenta: «{refusal}». «♻️ Ya en Exact» "
                      "queda sin dato; si sigue así, avisale a un admin.")
EXACT_UNREADABLE_NOTE = "«♻️ Ya en Exact» queda sin dato."
EXACT_UNKNOWN_CAPTION = ("Sin listado de Sponsored Products de la cuenta, «♻️ Ya en Exact» no se puede calcular y "
                         "no se muestra.")
BULK_EXACT_UNKNOWN_CAPTION = ("Sin la hoja de campañas del Bulk File, «♻️ Ya en Exact» no se puede calcular y no se "
                              "muestra.")
NO_CONNECTION_BULK_HINT = ("Si conectás la cuenta en Sistema → Cuentas conectadas, los search terms llegan solos todos "
                           "los días y no hace falta el Bulk File. El SQP se sigue subiendo a mano.")
BULK_UPLOAD_LABEL = "Sube tu Bulk File (.xlsx)"
BULK_UPLOAD_HELP = ("El Bulk File completo, NO el Search Term Report standalone: es el único archivo que trae los IDs "
                    "numéricos que Amazon necesita para aplicar un bulk.")
EXACT_FROM_BULK_CAPTION = "Keywords Exact que trae la hoja de campañas del Bulk File · {count}."
BULK_UNSTATED_NOTE = ("El Bulk File no dice qué días cubre, su moneda ni su ventana de atribución: los importes se "
                      "muestran con $ y las ventas y órdenes, como de 7 días.")
NO_CAMPAIGNS_SHEET_WARNING = ("⚠️ El Bulk File no trae la hoja «Sponsored Products Campaigns» con sus keywords. El "
                              "cruce funciona igual, pero no se sabe qué keywords Exact existen y el ASIN de cada ad "
                              "group sale sólo del nombre de la campaña. Bajá el Bulk File completo para tenerlos.")
EMPTY_BULK_MESSAGE = ("La hoja de search terms del Bulk File no trae ningún término: bajalo de nuevo con un rango de "
                      "30 días o más.")
ADVERTISED_ASINS_UNREADABLE = ("No se pudieron leer los productos anunciados de la cuenta: el ASIN sale sólo del "
                               "nombre de la campaña.")
NO_ASIN_WARNING = ("⚠️ Ningún search term tiene ASIN: los ad groups anuncian varios ASINs o no se listaron, y ningún "
                   "nombre de campaña lleva uno. Sin ASIN no hay análisis por producto: el gasto nunca se reparte "
                   "entre ASINs.")
NO_PRICE_ERROR = ("**Ninguna fila visible se puede subir a Amazon todavía.** Falta el precio promedio del producto: sin "
                  "él no se calcula el bid de ninguna fila. Cargalo arriba; si después quedan filas afuera, el detalle "
                  "está abajo.")
_GUARDS_BEFORE_EXACT = (
    "**Columnas de guarda.** **Origen** = por qué match type llegó el término. **🛑 No negativizable**: llegó por una "
    "keyword Exact o por product targeting; si rinde mal la acción es bajar bid o pausar, nunca negativizar (los de "
    "campañas Auto sí se pueden negativizar). **🏅 Ranking KW**: la campaña está en un portfolio RANKING o sin nombre "
    "sincronizado; cortarle tráfico cuesta posición orgánica, que no se recupera ajustando bids. **♻️ Ya en Exact**: "
)
_GUARDS_AFTER_EXACT = "Las tres informan: no cambian la acción."
GUARDS_CAPTION = (
    _GUARDS_BEFORE_EXACT + "la query ya existe como keyword Exact habilitada en la cuenta, tenga o no clicks en el "
    "período; agregarla o armarle otra campaña Exact la duplica. " + _GUARDS_AFTER_EXACT
)
BULK_GUARDS_CAPTION = (
    _GUARDS_BEFORE_EXACT + "la query ya existe como keyword Exact habilitada en la hoja de campañas del Bulk File; "
    "agregarla o armarle otra campaña Exact la duplica. Si el Bulk File se bajó sin **Campaign items with zero "
    "impressions**, no trae las keywords sin impresiones y esas no se marcan. " + _GUARDS_AFTER_EXACT
)

_ACTION_COLORS = {
    ACTION_SCALE: "background-color: #E8F5E9",
    ACTION_ADD: "background-color: #E3F2FD",
    ACTION_DEFEND: "background-color: #FFF8E1",
    ACTION_BRAND_OK: "background-color: #DCEDC8",
    ACTION_CONQUEST: "background-color: #EDE7F6",
    ACTION_LOWER_BID: "background-color: #FFF3E0",
    ACTION_DO_NOT_ATTACK: "background-color: #FFEBEE",
    ACTION_INVESTIGATE: "background-color: #F3E5F5",
    ACTION_BRAND_NO_DATA: "background-color: #ECEFF1",
    ACTION_ASIN: "background-color: #E0E0E0",
    ACTION_MONITOR: "",
}
_PLAN_COLUMN_NAMES = {
    MARKET_PURCHASES: "Purchases mercado",
    BRAND_PURCHASES: "Purchases marca",
    BRAND_PURCHASE_SHARE: "Brand Share %",
    OPPORTUNITY_SCORE: "Opp. Score",
    MARKET_IMPRESSIONS: "Impresiones",
    ORIGIN: "Origen",
    NOT_NEGATABLE: "🛑 No negativizable",
    RANKING_KEYWORD: "🏅 Ranking KW",
    ALREADY_EXACT: "♻️ Ya en Exact",
    PORTFOLIO_NAME: "Portfolio",
    CAMPAIGN_COUNT: "N campañas",
    MARKET_CVR: "CVR mercado %",
    BRAND_CVR: "CVR marca %",
    FUNNEL_DIAGNOSIS: "Diagnóstico funnel",
}
_VERDICT_COLORS = {
    "ACTUAR": "background-color:#EAF3DE;color:#173404",
    "ESPERAR": "background-color:#F1EFE8;color:#2C2C2A",
    "INVESTIGAR": "background-color:#FAEEDA;color:#412402",
}
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre el plan que ya calculó el módulo: qué acciones tomar primero y cuáles "
                      "esperar o investigar",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "no_rows": "El plan no tiene queries para analizar.",
           "table_title": "Queries en orden de prioridad — lectura IA",
           "col_item": "Query",
           "counts": "{n} queries priorizadas",
           "stale_body": "Cambió lo que el análisis leyó, por ejemplo el target ACoS o los competidores. Lo que se "
                         "muestra abajo corresponde a los datos anteriores."},
    "en": {"title": "AI analysis",
           "caption": "AI read on the plan the module already computed: which actions to take first and which to "
                      "wait on or investigate",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "no_rows": "The plan has no queries to analyze.",
           "table_title": "Queries by priority — AI read",
           "col_item": "Query",
           "counts": "{n} queries prioritized",
           "stale_body": "What the analysis read changed, for example the target ACoS or the competitors. What is "
                         "shown below belongs to the previous data."},
}


@dataclass(frozen=True)
class _AccountStructure:
    exact_keywords: frozenset[str] | None  # None while the account's SP listing is unknown
    exact_source: str  # what the AI reads about where the exact keywords come from
    ad_group_asins: dict[str, frozenset[str]]
    listed_at: datetime | None = None
    from_bulk_file: bool = False


@dataclass(frozen=True, eq=False)
class _CrossSource:
    search_terms: SearchTermSource
    structure: _AccountStructure
    option: ProfileOption | None  # None for a Bulk File, which belongs to no connected account


@dataclass(frozen=True)
class _PlanInputs:
    params: ActionPlanParams
    competitors_text: str
    catalog_text: str


def render():
    st.header("🔗 Análisis Cruzado STR vs SQP")
    st.caption("Cruzá lo que busca el mercado (SQP) con lo que capturan tus campañas de Sponsored Products "
               "(search terms de Amazon Ads, o de un Bulk File).")
    st.divider()
    _how_to_use()

    cross = _render_source()
    if cross is None:
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    source, structure, option = cross.search_terms, cross.structure, cross.option
    file_sqp = st.file_uploader("SQP de la marca (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp_x")
    if file_sqp is None:
        _render_empty_state("Subí el SQP de la marca para cruzarlo con los search terms de la cuenta.",
                            "Brand Analytics → Search Query Performance, vista de marca")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    brand_name = extract_sqp_brand(file_sqp)
    sqp = read_sqp(file_sqp)
    if QUERY not in sqp.columns:
        st.error(f"El SQP no tiene la columna '{QUERY}'.")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    brand_name = _confirmed_brand(brand_name)
    sqp[QUERY_TYPE] = query_types(sqp[QUERY], comma_terms(brand_name))
    sqp = with_funnel_diagnosis(numeric_sqp(sqp))
    search_terms = with_ranking_guards(source.frame, structure.exact_keywords)
    sales_col = sales_column(source.attribution_days)
    orders_col = orders_column(source.attribution_days)

    cross_tab, plan_tab, asin_tab, ai_tab_panel = st.tabs(
        ["🔗 Análisis Cruzado", "🎯 Plan de Acción", "📊 PPC Insights por ASIN", "🤖 Análisis IA"])
    with cross_tab:
        _render_cross_tab(search_terms, sqp)
    with plan_tab:
        plan, plan_inputs = _render_plan_tab(sqp, search_terms, structure, brand_name, source.currency_code,
                                             sales_col, orders_col)
    with asin_tab:
        summary, business_report_digest = _render_asin_tab(search_terms, sqp, structure, source.currency_code,
                                                           sales_col, orders_col)
    with ai_tab_panel:
        _render_ai_tab(plan, summary, sqp, search_terms, source=source, option=option, brand_name=brand_name,
                       structure=structure, plan_inputs=plan_inputs,
                       data_signature=_data_signature(source.signature, file_sqp.getvalue(),
                                                      business_report_digest, structure))


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Cruzar tus campañas (search terms) contra el mercado (SQP) y generar un Plan de Acción.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("Los search terms, las keywords Exact y el ASIN de cada ad group salen de la cuenta de Amazon "
                       "Ads que elijas; sin cuenta conectada, o con «Subir archivo manualmente», de un Bulk File. El "
                       "SQP de la marca se sube a mano; el Business Report by ASIN es opcional.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Campaign Builder (M10) con el Plan para Campaign Builder, o el bulk directo en Bulk "
                       "Operations.")
        st.markdown("**📥 Cómo bajar el Bulk File (si no usás la cuenta):**")
        st.markdown(
            "1. Campaign Manager → **Bulk Operations**\n"
            "2. En *Create & download custom spreadsheet*, elegí un rango de **30 días o más**. Con menos, los "
            "términos no juntan clicks suficientes y los umbrales del análisis no llegan a dispararse.\n"
            "3. Tildá **Sponsored Products**.\n"
            "4. En las opciones de datos, tildá **Search term data** (*Sponsored products search term data*). **Sin "
            "esa opción el archivo no trae la hoja que este módulo necesita.**\n"
            "5. En *Exclude*, destildá **Campaign items with zero impressions**, que viene tildado. Si no, el archivo "
            "no trae las keywords sin impresiones en el rango y «♻️ Ya en Exact» no las ve.\n"
            "6. Download → subí el `.xlsx` tal cual, sin abrirlo ni guardarlo de nuevo."
        )
        st.caption("⚠️ **No sirve el Search Term Report standalone.** Se parece, pero no trae los IDs numéricos de "
                   "campaña, ad group y keyword, y sin esos IDs Amazon rechaza cualquier bulk que generemos.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí la cuenta, el país y el período de Amazon Ads, o subí el Bulk File\n"
            "2. Subí el SQP de la marca\n"
            "3. Tab Cruce: revisá En ambos / Solo STR / Solo SQP y el diagnóstico de funnel\n"
            "4. Tab Plan de Acción: revisá la columna Acción y las columnas de guarda "
            "(🛑 No negativizable · 🏅 Ranking KW · ♻️ Ya en Exact)\n"
            "5. Descargá el bulk para Bulk Operations o el plan para Campaign Builder\n"
            "6. Tab Análisis IA: qué acciones tomar primero"
        )


def _render_empty_state(title: str, where: str):
    st.markdown(
        "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;border-radius:12px;margin:1rem 0;'>"
        "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
        f"<div style='font-size:0.95rem;color:#666;font-weight:600;'>{title}</div>"
        f"<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>{where}</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_source() -> _CrossSource | None:
    """The account the picker chooses, with its structure; a Bulk File without accounts or when the AM asks for one."""
    search_term_source._keep_choices(KEY_PREFIX)
    # With data already on screen, a failed accounts read keeps it (the picker warns) instead of asking for a file.
    if search_term_source._last_source(KEY_PREFIX) is None and not search_term_source._available_profiles():
        return _render_bulk_upload(hint=NO_CONNECTION_BULK_HINT)
    if st.session_state.get(search_term_source.picker_key(KEY_PREFIX, "manual")):
        return _render_bulk_mode()
    source = search_term_source.render_source_picker(KEY_PREFIX, allow_manual=False, module_label=MODULE_LABEL)
    if source is None:
        _render_bulk_action()
        return None
    option = profile_option(source.profile_id)
    return _CrossSource(source, _account_structure(option), option)


def _render_bulk_action():
    actions_key = search_term_source.picker_key(BULK_PREFIX, "actions")
    st.markdown(search_term_source._actions_css(actions_key), unsafe_allow_html=True)
    with st.container(key=actions_key):
        st.button("Subir archivo manualmente", key=search_term_source.picker_key(BULK_PREFIX, "upload_manual"),
                  type="secondary", icon=":material/upload:", on_click=search_term_source._set_manual_mode,
                  args=(KEY_PREFIX, True))


def _render_bulk_mode() -> _CrossSource | None:
    with st.container(border=True):
        note_col, back_col = st.columns([4.2, 1.8], vertical_alignment="center")
        note_col.markdown(search_term_source.MANUAL_MODE_NOTE)
        back_col.button("Volver a datos de Amazon Ads", key=search_term_source.picker_key(KEY_PREFIX, "back_to_api"),
                        type="tertiary", icon=":material/arrow_back:", on_click=search_term_source._set_manual_mode,
                        args=(KEY_PREFIX, False))
        return _render_bulk_upload(hint="")


def _render_bulk_upload(*, hint: str) -> _CrossSource | None:
    uploaded = st.file_uploader(BULK_UPLOAD_LABEL, type=["xlsx"], key=search_term_source.picker_key(KEY_PREFIX, "file"),
                                help=BULK_UPLOAD_HELP)
    if hint:
        st.caption(hint)
    if uploaded is None:
        _render_empty_state("Subí el Bulk File para cruzar sus search terms con el SQP de la marca.",
                            "Campaign Manager → Bulk Operations, con Sponsored Products y Search term data")
        return None
    try:
        bulk = _read_bulk_file(uploaded.getvalue(), uploaded.name)
    except BulkFileError as exc:
        log.warning("cross analysis: bulk file %s could not be read: %s", uploaded.name, exc)
        st.error(str(exc))
        return None
    if bulk.search_terms.frame.empty:
        st.info(EMPTY_BULK_MESSAGE)
        return None
    if bulk.exact_keywords is None:
        st.warning(NO_CAMPAIGNS_SHEET_WARNING)
        exact_source = "el Bulk File no trae la hoja de campañas con sus keywords: no se sabe cuáles existen"
    else:
        exact_count = _exact_count_label(len(bulk.exact_keywords))
        st.caption(EXACT_FROM_BULK_CAPTION.format(count=exact_count))
        exact_source = (f"hoja de campañas del Bulk File, que trae {exact_count}; si se bajó sin «Campaign items with "
                        "zero impressions», no trae las que no tuvieron impresiones")
    st.caption(BULK_UNSTATED_NOTE)
    structure = _AccountStructure(bulk.exact_keywords, exact_source, bulk.ad_group_asins, from_bulk_file=True)
    return _CrossSource(bulk.search_terms, structure, option=None)


@st.cache_data(max_entries=3, ttl=3600, show_spinner="Leyendo el Bulk File…")
def _read_bulk_file(file_bytes: bytes, file_name: str) -> BulkFileAccount:
    return read_bulk_file(file_bytes, file_name)


def _account_structure(option: ProfileOption | None) -> _AccountStructure:
    """Mounts the listing line under the picker, the Bulk File upload beside it; the exact keywords stay unknown until
    the listing can be read."""
    info_col, action_col = st.columns([4.2, 3.8], vertical_alignment="center")
    with action_col:
        _render_bulk_action()
    if option is None:
        info_col.caption(EXACT_NOT_LISTED_NOTE)
        return _AccountStructure(None, "no hay listado de Amazon Ads de la cuenta: no se sabe cuáles existen", {})
    now = datetime.now(timezone.utc)
    exact_keywords, listed_at = None, None
    try:
        listing = load_keyword_listing(option, search_term_source.profile_today(option, now))
    except ReportReadError as exc:
        log.warning("cross analysis: SP listing of profile %s unreadable: %s", option.profile_id, exc)
        info_col.warning(f"{exc} {EXACT_UNREADABLE_NOTE}")
        exact_source = "no se pudo leer el listado de Amazon Ads: no se sabe cuáles existen"
    else:
        if listing.known:
            exact_keywords, listed_at = enabled_exact_keyword_texts(listing.rows), listing.listed_at
            info_col.caption(EXACT_LISTED_CAPTION.format(listed=listing_moment(listed_at, now, data_of_day_phrase),
                                                         count=_exact_count_label(len(exact_keywords))))
            exact_source = (f"listado diario de Sponsored Products de la cuenta, con {len(exact_keywords)} keywords "
                            "Exact habilitadas")
        elif listing.refusal:
            info_col.caption(EXACT_REFUSED_NOTE.format(refusal=listing.refusal))
            exact_source = "Amazon rechazó el listado de la cuenta: no se sabe cuáles existen"
        else:
            info_col.caption(EXACT_NOT_LISTED_NOTE)
            exact_source = "todavía no hay listado de Amazon Ads de la cuenta: no se sabe cuáles existen"
    return _AccountStructure(exact_keywords, exact_source, _ad_group_asins(option.profile_id), listed_at)


def _exact_count_label(count: int) -> str:
    if count == 1:
        return "1 keyword Exact habilitada"
    return f"{search_term_source.count_label(count)} keywords Exact habilitadas"


@st.cache_data(ttl=ADVERTISED_ASINS_TTL_SECONDS, show_spinner=False)
def _advertised_asins(profile_id: str) -> dict[str, frozenset[str]]:
    rest = search_term_source._open_rest()
    return ReportProvider(rest).advertised_asins(profile_id) if rest is not None else {}


def _ad_group_asins(profile_id: str) -> dict[str, frozenset[str]]:
    """Amazon's ASINs for each ad group of the account; none when they cannot be read, and the page says so."""
    try:
        return _advertised_asins(profile_id)
    except ReportReadError as exc:
        log.warning("cross analysis: advertised ASINs of profile %s unreadable: %s", profile_id, exc)
        st.warning(ADVERTISED_ASINS_UNREADABLE)
        return {}


def _confirmed_brand(detected: str | None) -> str:
    """The brand the SQP names, or the one the AM types when the SQP names none; "" when neither."""
    if detected:
        st.success(f"Marca detectada: **{detected.title()}**")
        return detected
    typed = st.text_input("⚠️ No se detectó la marca automáticamente. Ingresá el nombre (ej: dermaglos):",
                          key="marca_manual_input", placeholder="ej: dermaglos")
    if typed.strip():
        st.success(f"Marca configurada manualmente: **{typed.strip().title()}**")
        return typed.strip().lower()
    st.warning("No se detectó la marca en el archivo SQP. Podés ingresarla arriba para clasificar correctamente.")
    return ""


# ── Tab 1 — Cruce ─────────────────────────────────────────────────────────────


def _render_cross_tab(search_terms: pd.DataFrame, sqp: pd.DataFrame):
    report_keys = search_terms[SEARCH_TERM].astype(str).str.lower().str.strip()
    query_keys = sqp[QUERY].astype(str).str.lower().str.strip()
    in_both = set(report_keys) & set(query_keys)
    only_report = set(report_keys) - set(query_keys)
    only_sqp = set(query_keys) - set(report_keys)

    c1, c2, c3 = st.columns(3)
    c1.metric("En ambos", len(in_both))
    c2.metric("Solo en STR (no en SQP)", len(only_report))
    c3.metric("Solo en SQP (oportunidades)", len(only_sqp))
    opportunities = sqp[query_keys.isin(only_sqp)]
    m1, m2 = st.columns(2)
    m1.metric("Oportunidades de marca", int((opportunities[QUERY_TYPE] == BRAND_QUERY).sum()))
    m2.metric("Oportunidades genéricas", int((opportunities[QUERY_TYPE] == GENERIC_QUERY).sum()))
    _render_origin_spend(search_terms)

    st.markdown("---")
    st.markdown("#### Filtros")
    f1, f2, f3, f4 = st.columns(4)
    min_impressions = f1.number_input("Mínimo de impresiones", min_value=0, value=0, step=100, key="cruzado_min_imp")
    min_score = f2.number_input("Mínimo Search Query Score", min_value=0, value=0, step=1, key="cruzado_min_score")
    min_purchases = f3.number_input("Mínimo de purchases", min_value=0, value=0, step=1, key="cruzado_min_pur")
    query_type = f4.selectbox("Tipo de keyword", ["Todas", BRAND_QUERY, GENERIC_QUERY], key="cruzado_tipo")

    def filtered(frame: pd.DataFrame) -> pd.DataFrame:
        shown = frame
        if MARKET_IMPRESSIONS in shown.columns:
            shown = shown[shown[MARKET_IMPRESSIONS] >= min_impressions]
        if QUERY_SCORE in shown.columns:
            shown = shown[shown[QUERY_SCORE] >= min_score]
        if MARKET_PURCHASES in shown.columns:
            shown = shown[shown[MARKET_PURCHASES] >= min_purchases]
        if QUERY_TYPE in shown.columns and query_type != "Todas":
            shown = shown[shown[QUERY_TYPE] == query_type]
        if MARKET_IMPRESSIONS in shown.columns:
            shown = shown.sort_values(MARKET_IMPRESSIONS, ascending=False)
        return shown

    st.markdown("---")
    st.markdown("#### Términos en ambos reportes")
    funnel_columns = [column for column in (MARKET_CVR, BRAND_CVR, FUNNEL_DIAGNOSIS) if column in sqp.columns]
    sqp_columns = [QUERY] + [column for column in (QUERY_SCORE, MARKET_IMPRESSIONS, MARKET_CLICKS, MARKET_PURCHASES)
                             if column in sqp.columns] + funnel_columns
    market = sqp[sqp_columns].assign(**{QUERY: query_keys})
    both = search_terms.loc[report_keys.isin(in_both), _visible_columns(search_terms)].copy()
    both[SEARCH_TERM] = both[SEARCH_TERM].astype(str).str.lower().str.strip()
    merged = both.merge(market, left_on=SEARCH_TERM, right_on=QUERY, how="left", suffixes=("_STR", "_SQP"))
    _render_table(filtered(merged))
    if funnel_columns:
        st.caption(
            "**Cómo leer el diagnóstico de funnel.** *Convertís como el mercado* + share bajo = problema de "
            "**tráfico**: no aparecés lo suficiente, y eso se ataca con PPC (subir bid, agregar la keyword). "
            "*Convertís por debajo* = problema de **listing, precio o reviews**: subir bids acá compra clicks que no "
            f"cierran. El umbral de paridad es {CVR_MARKET_PARITY:.0%} del CVR del mercado y no tiene respaldo "
            "empírico: ajustalo por categoría. El CVR de la marca sale de *Clicks: Brand Count*, que mezcla orgánico "
            "y pago: es el de tu marca entera en esa query, **no el de tus ads**."
        )

    st.markdown("#### Términos solo en SQP (sin campaña activa — posibles oportunidades)")
    opportunities = sqp[query_keys.isin(only_sqp)].copy()
    score_columns = [column for column in (MARKET_IMPRESSIONS, MARKET_CLICKS, MARKET_PURCHASE_RATE)
                     if column in opportunities.columns]
    if score_columns:
        # A constant column scales to zeros, kept as a column so the frame never collapses into a Series.
        scaled = opportunities[score_columns].apply(
            lambda values: (values - values.min()) / (values.max() - values.min()) if values.max() != values.min()
            else values * 0)
        opportunities.insert(1, OPPORTUNITY_SCORE, (scaled.sum(axis=1) / len(score_columns) * 100).round(1))
    opportunities = filtered(opportunities)
    st.dataframe(opportunities, use_container_width=True)
    st.download_button(
        label=f"⬇️ Exportar {len(opportunities)} oportunidades a Excel",
        data=_xlsx_bytes({"Oportunidades": opportunities}),
        file_name="oportunidades_sqp.xlsx",
        mime=XLSX_MIME,
        use_container_width=True,
        key="cruzado_dl_opp",
    )

    st.markdown("#### Términos solo en STR (sin datos de búsqueda orgánica)")
    only_report_rows = search_terms.loc[report_keys.isin(only_report), _visible_columns(search_terms)]
    _render_table(only_report_rows.sort_values(SPEND, ascending=False))


def _render_origin_spend(search_terms: pd.DataFrame):
    """How the period's spend splits by the targeting the terms came through."""
    with st.expander("📊 Gasto por origen del término", expanded=False):
        origins = search_terms[ORIGIN].replace("", "Sin origen")
        spend = pd.to_numeric(search_terms[SPEND], errors="coerce").fillna(0)
        by_origin = (pd.DataFrame({"Origen": origins, "_spend": spend}).groupby("Origen")
                     .agg(Filas=("_spend", "size"), Gasto=("_spend", "sum")).reset_index()
                     .sort_values("Gasto", ascending=False))
        total = float(spend.sum())
        by_origin["% del gasto"] = (by_origin["Gasto"] / total * 100).round(1) if total > 0 else None
        st.dataframe(by_origin, use_container_width=True, hide_index=True)
        if total > 0:
            keyword_share = float(spend[origins.isin(("Exact", "Phrase", "Broad"))].sum()) / total * 100
            st.caption(f"El {keyword_share:.1f}% del gasto viene de keywords (Exact, Phrase o Broad); el resto, de "
                       "campañas Auto y de product targeting, cuyos bids no se cambian desde este export.")


def _visible_columns(frame: pd.DataFrame) -> list[str]:
    return [column for column in frame.columns if not str(column).startswith("_")]


def _render_table(frame: pd.DataFrame):
    """At most TABLE_ROW_LIMIT rows, in the frame's order, saying how many were left out."""
    st.dataframe(frame.head(TABLE_ROW_LIMIT), use_container_width=True)
    if len(frame) > TABLE_ROW_LIMIT:
        st.caption(f"Se muestran las primeras {search_term_source.count_label(TABLE_ROW_LIMIT)} de "
                   f"{search_term_source.count_label(len(frame))} filas.")


# ── Tab 2 — Plan de Acción ────────────────────────────────────────────────────


def _render_plan_tab(sqp: pd.DataFrame, search_terms: pd.DataFrame, structure: _AccountStructure, brand_name: str,
                     currency_code: str, sales_col: str, orders_col: str) -> tuple[pd.DataFrame, _PlanInputs]:
    st.markdown("### 🎯 Plan de Acción")
    st.caption("Resumen ejecutivo accionable. Cada término clasificado con una acción concreta.")
    target_acos = st.number_input("Target ACoS (%)", min_value=1.0, max_value=200.0, value=35.0, step=1.0,
                                  key="pa_target_acos")
    competitors_col, catalog_col = st.columns(2)
    competitors_text = competitors_col.text_input(
        "Competidores conocidos (opcional, separados por coma)", value="", key="ac_competidores",
        help="Ej: 'rayban, meta, oakley'. Si la query menciona tu marca + un competidor, clasifica CONQUEST, no "
             "DEFENDER.")
    catalog_text = catalog_col.text_input(
        "ASINs propios del cliente (opcional, separados por coma)", value="", key="ac_catalogo_asins",
        help="Si la query es uno de estos ASINs, se trata como product targeting y no entra al bulk de keywords.")
    inputs = _PlanInputs(ActionPlanParams(target_acos=target_acos, brand_terms=comma_terms(brand_name),
                                          competitors=comma_terms(competitors_text),
                                          catalog_asins=comma_terms(catalog_text)),
                         competitors_text.strip(), catalog_text.strip())
    plan = build_action_plan(sqp, search_terms, structure.exact_keywords, inputs.params, sales_column=sales_col,
                             orders_column=orders_col)
    st.markdown("---")

    action_counts = plan[ACTION].value_counts()
    st.markdown("#### Resumen de acciones")
    kpi_columns = st.columns(max(1, min(len(action_counts), 7)))
    for position, (action, count) in enumerate(action_counts.items()):
        kpi_columns[position % len(kpi_columns)].metric(action, count)
    st.markdown("---")

    options = ["Todas"] + sorted(plan[ACTION].unique().tolist())
    chosen = st.selectbox("Filtrar por acción", options, key="pa_filtro_accion")
    visible = plan if chosen == "Todas" else plan[plan[ACTION] == chosen]
    exact_known = structure.exact_keywords is not None
    columns = [column for column in (ACTION, QUERY, QUERY_TYPE, IN_SEARCH_TERMS, MARKET_PURCHASES, BRAND_PURCHASES,
                                     BRAND_PURCHASE_SHARE, OPPORTUNITY_SCORE, MARKET_IMPRESSIONS, ORIGIN,
                                     NOT_NEGATABLE, RANKING_KEYWORD, ALREADY_EXACT, PORTFOLIO_NAME, CAMPAIGN_COUNT)
               if column in visible.columns and (column != ALREADY_EXACT or exact_known)]
    table = visible[columns].rename(columns=_PLAN_COLUMN_NAMES).sort_values(ACTION).reset_index(drop=True)
    st.dataframe(table.style.map(lambda action: _ACTION_COLORS.get(action, ""), subset=[ACTION]),
                 use_container_width=True, height=500)
    st.caption(BULK_GUARDS_CAPTION if structure.from_bulk_file else GUARDS_CAPTION)
    if not exact_known:
        st.caption(BULK_EXACT_UNKNOWN_CAPTION if structure.from_bulk_file else EXACT_UNKNOWN_CAPTION)
    campaign_counts = (pd.to_numeric(visible[CAMPAIGN_COUNT], errors="coerce") if CAMPAIGN_COUNT in visible.columns
                       else pd.Series(dtype="float64"))
    ambiguous = int((campaign_counts.fillna(1) > 1).sum())
    if ambiguous:
        st.warning(
            f"⚠️ **{ambiguous} términos corren en más de una campaña.** Heredan los IDs de la de **mayor spend**, así "
            "que la acción se va a aplicar sobre esa y no sobre las demás. Es una elección del módulo, no un dato de "
            "Amazon: revisá esas filas (columna *N campañas*) antes de subir el bulk."
        )

    st.markdown("---")
    st.markdown("#### 📦 Export")
    missing_exact_source = ("Sin la hoja de campañas del Bulk File" if structure.from_bulk_file
                            else "Sin listado de la cuenta")
    _render_plan_exports(visible, target_acos, currency_code, exact_known, missing_exact_source)
    return plan, inputs


def _render_plan_exports(visible: pd.DataFrame, target_acos: float, currency_code: str, exact_known: bool,
                         missing_exact_source: str):
    st.markdown("##### Bulk para Amazon (Bulk Operations)")
    st.caption("Cambia bids de keywords que ya existen (ESCALAR, BAJAR BID) y agrega keywords a ad groups que ya "
               "existen (AGREGAR, DEFENDER), con los IDs de la campaña que más gastó en cada término.")
    price_col, cvr_col = st.columns(2)
    price = price_col.number_input(
        f"Precio promedio del producto ({currency_symbol(currency_code)})", min_value=0.0, value=0.0, step=0.5,
        key="ac_precio_prom",
        help="Bid = (CVR/100) x precio x (target ACoS/100). Sin precio no se puede calcular el bid y las filas "
             "quedan fuera del bulk.")
    cvr_default = cvr_col.number_input(
        "CVR default (%): se aplica a todas las keywords", min_value=0.0, max_value=100.0, value=10.0, step=0.5,
        key="ac_cvr_default")
    bid = None
    if price > 0:
        raw_bid = (cvr_default / 100) * price * (target_acos / 100)
        bid = max(MINIMUM_AMAZON_BID, round(raw_bid, 2))
        if raw_bid < MINIMUM_AMAZON_BID:
            st.warning(_escaped(
                f"El bid que sale de la fórmula es {money(raw_bid, currency_code, decimals=4)}, por debajo del mínimo "
                f"de Amazon ({money(MINIMUM_AMAZON_BID, currency_code)}). Se exporta al mínimo, **pero eso rompe tu "
                f"target**: con un CVR de {cvr_default:.1f}% y un precio de {money(price, currency_code)} estos "
                "términos no son rentables a ningún bid que Amazon acepte. Revisá precio, CVR o target antes de "
                "subir el archivo."))

    rows = bulk_rows(visible, bid)
    bulk_create, invalid_create = build_keyword_create(rows.creates)
    bulk_update, invalid_update = build_bid_update(rows.updates)
    valid_parts = [part for part in (bulk_create, bulk_update) if not part.empty]
    bulk_df = pd.concat(valid_parts, ignore_index=True) if valid_parts else bulk_create
    invalid_parts = [part for part in (invalid_create, invalid_update) if not part.empty]
    invalid_df = pd.concat(invalid_parts, ignore_index=True) if invalid_parts else invalid_create
    metadata = _plan_metadata(visible, set(rows.already_exact), set(rows.same_keyword))

    not_bulkable = sorted(visible.loc[~visible[ACTION].isin(BULK_ACTIONS), ACTION].unique().tolist())
    reasons = []
    if not_bulkable:
        reasons.append(f"{int((~visible[ACTION].isin(BULK_ACTIONS)).sum())} por acción no accionable "
                       f"({', '.join(not_bulkable)})")
    if rows.already_exact:
        reasons.append(f"{len(rows.already_exact)} porque ya existen como keyword Exact habilitada")
    if rows.same_keyword:
        reasons.append(f"{len(rows.same_keyword)} porque otra fila ya actualiza la misma keyword")
    if not invalid_df.empty:
        reasons.append(f"{len(invalid_df)} por datos faltantes")
    detail = f" ({'; '.join(reasons)})" if reasons else ""
    st.info(f"Exportando **{len(bulk_df)} de {len(visible)}** filas visibles a la hoja del bulk{detail}. Las "
            f"{len(visible)} van completas a la hoja Metadata.")
    if not exact_known:
        st.caption(f"{missing_exact_source} no se pudo verificar si las keywords a agregar ya existen como Exact: "
                   "revisalas en Campaign Manager antes de subir el archivo.")

    if bulk_df.empty:
        st.error(NO_PRICE_ERROR if bid is None and not invalid_df.empty else
                 "**Ninguna fila visible se puede subir a Amazon.** Con el filtro actual no quedó ninguna acción "
                 "bulkeable, o a todas les falta algún ID. Lo más común: términos que sólo aparecen en el SQP (no están "
                 "en ninguna campaña todavía, así que no tienen Campaign ID), o términos de campañas Auto y de Product "
                 "Targeting, que no llegan por una keyword y por eso no se les puede cambiar el bid desde acá. El "
                 "detalle está abajo.")
        if not invalid_df.empty:
            with st.expander(f"Ver el detalle de las {len(invalid_df)} filas rechazadas", expanded=False):
                st.dataframe(invalid_df[["Keyword Text", "Match Type", "_invalid_reason"]],
                             use_container_width=True, hide_index=True)
        if not metadata.empty:
            st.caption("Mientras tanto podés bajar el análisis. **No es un bulk**: no se sube a Amazon, es la tabla "
                       "de decisiones para trabajarla a mano.")
            st.download_button(label=f"⬇️ Descargar análisis ({len(metadata)} términos, NO subible)",
                               data=_xlsx_bytes({"Metadata": metadata}), file_name="plan_accion_analisis.xlsx",
                               mime=XLSX_MIME, key="download_plan_accion_meta")
    else:
        errors = [error for error in validate_bulk(bulk_df) if error.severidad == "error"]
        if errors:
            st.error(f"**El bulk tiene {len(errors)} errores y no se puede descargar.** Amazon rechaza el archivo "
                     "COMPLETO si una sola fila está mal: una fila mala y las otras tampoco se aplican.")
            st.dataframe(pd.DataFrame([{"Fila": error.fila if error.fila >= 0 else "—", "Columna": error.columna,
                                        "Valor": error.valor, "Qué hacer": error.mensaje} for error in errors]),
                         use_container_width=True, hide_index=True)
        else:
            st.dataframe(bulk_df, use_container_width=True)
            st.download_button(label=f"⬇️ Descargar Plan de Acción bulk ({len(bulk_df)} filas)",
                               data=write_bulk_excel(bulk_df, metadata), file_name="plan_accion_bulk.xlsx",
                               mime=XLSX_MIME, key="download_plan_accion")

    st.markdown("##### Plan para Campaign Builder")
    st.caption("Las keywords con las que Campaign Builder (M10) arma campañas Exact nuevas: subí este archivo en su "
               "Paso 1.")
    builder_plan = campaign_builder_plan(visible)
    kept, left_out = builder_plan.rows, builder_plan.left_out
    reasons = left_out[CB_REASON].value_counts()
    detail = "; ".join(f"{count}: {reason}" for reason, count in reasons.items())
    st.info(f"**{len(kept)} de {len(visible)}** filas visibles van al plan para Campaign Builder."
            + (f" Quedan afuera {len(left_out)} ({detail})." if len(left_out) else ""))
    if not builder_plan.exact_checked:
        st.caption(f"{missing_exact_source} no se pudo verificar cuáles ya existen como keyword Exact: revisalas en "
                   "Campaign Manager antes de lanzarlas.")
    if not left_out.empty:
        with st.expander(f"Ver las {len(left_out)} filas que quedaron afuera del plan", expanded=False):
            st.dataframe(left_out, use_container_width=True, hide_index=True)
    if kept.empty:
        return
    st.download_button(label=f"⬇️ Descargar plan para Campaign Builder ({len(kept)} keywords)",
                       data=_xlsx_bytes({"Plan de Acción": kept, "Fuera del plan": left_out}),
                       file_name="plan_accion_campaign_builder.xlsx", mime=XLSX_MIME,
                       key="download_plan_campaign_builder")


def _plan_metadata(visible: pd.DataFrame, already_exact: set[str], same_keyword: set[str]) -> pd.DataFrame:
    """INV-5.5: the analysis columns travel on their own sheet, never on the bulk's."""
    columns = [column for column in (QUERY, ACTION, QUERY_TYPE, IN_SEARCH_TERMS, MARKET_PURCHASES, BRAND_PURCHASES,
                                     BRAND_PURCHASE_SHARE, OPPORTUNITY_SCORE, MARKET_IMPRESSIONS, MARKET_CVR,
                                     BRAND_CVR, FUNNEL_DIAGNOSIS) if column in visible.columns]
    metadata = visible[columns].rename(columns=_PLAN_COLUMN_NAMES).copy()
    metadata["Motivo exclusión del bulk"] = [
        _bulk_exclusion(action, str(query).strip(), already_exact, same_keyword)
        for action, query in zip(visible[ACTION], visible[QUERY])
    ]
    return metadata.reset_index(drop=True)


def _bulk_exclusion(action: str, query: str, already_exact: set[str], same_keyword: set[str]) -> str:
    if action not in BULK_ACTIONS:
        return "Acción no accionable como fila de bulk"
    if action in BULK_CREATE_ACTIONS and query in already_exact:
        return "Ya existe como keyword Exact habilitada en la cuenta"
    if action not in BULK_CREATE_ACTIONS and query in same_keyword:
        return "Otra fila del bulk ya actualiza la misma keyword"
    return ""


# ── Tab 3 — PPC Insights por ASIN ─────────────────────────────────────────────


def _render_asin_tab(search_terms: pd.DataFrame, sqp: pd.DataFrame, structure: _AccountStructure, currency_code: str,
                     sales_col: str, orders_col: str) -> tuple[AsinSummary, str]:
    st.markdown("### 📊 PPC Insights por ASIN")
    st.caption("Performance de los search terms por ASIN anunciado + market share del SQP. Subí el BR by ASIN para "
               "enriquecer.")
    file_br = st.file_uploader("Business Report by ASIN (opcional, .csv/.xlsx)", type=["csv", "xlsx"],
                               key="cruzado_br_asin")
    business_report, business_report_digest = {}, ""
    if file_br is not None:
        report_bytes = file_br.getvalue()
        business_report_digest = hashlib.sha256(report_bytes).hexdigest()[:16]
        try:
            business_report = business_report_by_asin(_read_table(report_bytes, file_br.name))
        except Exception as exc:  # an uploaded file can fail in any way the Excel and CSV readers do
            log.warning("cross analysis: business report %s unreadable: %s", file_br.name, exc)
            st.warning(f"⚠️ No se pudo leer el Business Report: {exc}")
        else:
            st.success(f"✅ BR cargado — {len(business_report)} ASINs")
    st.markdown("---")

    summary = asin_summary(search_terms, structure.ad_group_asins, business_report, sales_column=sales_col,
                           orders_column=orders_col)
    if summary.resolved.column is None:
        st.warning(NO_ASIN_WARNING)
        return summary, business_report_digest
    coverage = asin_coverage_caption(summary.resolved.source, summary.resolved.spend_share)
    if coverage:
        st.caption(coverage)

    rows = summary.rows
    st.markdown(f"#### {len(rows)} ASINs con gasto")
    k1, k2, k3 = st.columns(3)
    k1.metric("ASINs con ads", len(rows))
    brand_share = brand_impression_share(sqp)
    k2.metric("Impression Share global", f"{brand_share:.1f}%" if brand_share is not None else "—")
    total_spend, total_sales = float(rows[AD_SPEND].sum()), float(rows[AD_SALES].sum())
    k3.metric("ACoS promedio", f"{total_spend / total_sales * 100:.1f}%" if total_sales > 0 else "—")
    money_column = st.column_config.NumberColumn(format=f"{currency_symbol(currency_code)}%.2f")
    percent_column = st.column_config.NumberColumn(format="%.1f%%")
    st.dataframe(
        # printf formats can't group thousands, so the sessions take theirs from the Styler.
        rows.style.format("{:,.0f}", subset=[BR_SESSIONS], na_rep="").map(_acos_color, subset=[ACOS]),
        use_container_width=True, hide_index=True,
        column_config={AD_SPEND: money_column, AD_SALES: money_column, ACOS: percent_column, CVR: percent_column,
                       BR_SALES: money_column},
    )
    st.caption("ACoS y CVR vacíos = el ASIN no registró ventas (o clicks) en el período: no es un 0, es ausencia de "
               "dato. «Agrupa» = el ASIN salió del nombre de la campaña en ad groups que anuncian varios ASINs: es la "
               "etiqueta de una familia, no un producto solo.")

    st.markdown("---")
    st.markdown("#### Top 5 keywords por ASIN")
    queries = set(sqp[QUERY].dropna().astype(str).str.lower().str.strip())
    for record in rows.head(ASINS_WITH_TOP_TERMS).to_dict("records"):
        asin = record[ASIN]
        own_terms = summary.terms[summary.terms[summary.resolved.column] == asin]
        acos = record[ACOS]
        acos_text = f"{acos:.1f}%" if pd.notna(acos) else "s/d"
        with st.expander(f"{asin} | ACoS {acos_text} | {money(record[AD_SPEND], currency_code)} spend"):
            best = top_terms(summary, asin, sales_column=sales_col)
            st.dataframe(best[[SEARCH_TERM, SPEND, sales_col, orders_col, CLICKS]], use_container_width=True,
                         hide_index=True)
            gaps = queries - set(own_terms[SEARCH_TERM].dropna().astype(str).str.lower().str.strip())
            if gaps:
                st.caption(f"🔍 {len(gaps)} queries del SQP no tienen ads para este ASIN — posibles gaps de cobertura.")
    st.download_button(label=f"📥 Exportar Insights por ASIN ({len(rows)} ASINs)",
                       data=_xlsx_bytes({"Insights por ASIN": rows}), file_name="ppc_insights_asin.xlsx",
                       mime=XLSX_MIME, key="download_insights_asin")
    return summary, business_report_digest


def _acos_color(value) -> str:
    # NaN is no sales (INV-7): no color, since green would read as efficient.
    if pd.isna(value) or value <= 0:
        return ""
    if value < 25:
        return "background-color: #E8F5E9; color: #1B5E20"
    if value < 50:
        return "background-color: #FFF8E1; color: #F57F17"
    return "background-color: #FFEBEE; color: #B71C1C"


def _read_table(data: bytes, file_name: str) -> pd.DataFrame:
    buffer = io.BytesIO(data)
    return pd.read_excel(buffer) if file_name.lower().endswith(".xlsx") else pd.read_csv(buffer)


# ── Tab 4 — Análisis IA ───────────────────────────────────────────────────────


def _render_ai_tab(plan: pd.DataFrame, summary: AsinSummary, sqp: pd.DataFrame, search_terms: pd.DataFrame, *,
                   source: SearchTermSource, option: ProfileOption | None, brand_name: str,
                   structure: _AccountStructure, plan_inputs: _PlanInputs, data_signature: str):
    from ai.agents.cross_analysis import chat_document
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
    period = (date_range_label(source.window_start, source.window_end)
              if source.window_start is not None and source.window_end is not None else "")
    parameters = {
        "Target ACoS (%)": plan_inputs.params.target_acos,
        "Competidores cargados": plan_inputs.competitors_text or "ninguno",
        "ASINs propios cargados": plan_inputs.catalog_text or "ninguno",
    }
    analysis_input = build_analysis_input(
        plan, summary.rows, account=source.label, period=period, currency=source.currency_code, brand=brand_name,
        exact_source=structure.exact_source,
        asin_source=asin_coverage_caption(summary.resolved.source, summary.resolved.spend_share),
        parameters=parameters, counts=plan_counts(plan, sqp, search_terms), lang=lang,
        from_bulk_file=source.source == SOURCE_FILE)
    if analysis_input.data is None:
        st.info(texts["no_rows"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    payload = analysis_input.data
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload, file_signature=data_signature,
                                       labels=labels, auto_fire=False)
    records = analysis_input.records
    if analysis is not None:
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload, analysis_input.records)
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels,
                                                     currency_code=source.currency_code))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=source.label,
        reading=lambda finished, _records=records: chat_document.reading_text(finished.result, _records),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=cross_row_labels(records)),
        country_code=option.country_code if option is not None else "", profile_id=source.profile_id)


def _render_ai_result(result, analysis, *, records, labels, currency_code):
    from core import ai_tab

    opinions = result.get("consultas") or []
    rows = cross_ai_rows(opinions, records, currency_code)
    warnings = sum(1 for row in rows if row["warning"])
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(opinions)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    row_labels = cross_row_labels(records)
    synthesis = ai_tab.map_synthesis_text(result.get("synthesis") or {},
                                          lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _VERDICT_COLORS),
                    unsafe_allow_html=True)


def cross_ai_rows(opinions: list, records: list, currency_code: str) -> list[dict]:
    """Display rows for the opinion table: the query, the module's action, its figures and the AI's read."""
    by_id = dict(zip(make_ids(ROW_PREFIX, len(records)), records))
    rows = []
    for opinion in opinions:
        row_id = str(opinion.get("row_id", ""))
        record = by_id.get(row_id)
        if record is None:
            continue
        rows.append({
            "row_id": row_id,
            "item": row_item(record),
            "type_tag": record.get("accion", ""),
            "metrics": _query_metrics(record, currency_code),
            "badges": [opinion.get("veredicto", "")],
            "confidence": str(opinion.get("confianza", "")).upper(),
            "warning": opinion.get("advertencia") or "",
            "reasoning": opinion.get("razon", ""),
        })
    return rows


def _query_metrics(record: dict, currency_code: str) -> list[str]:
    share = record.get("share_compras_marca")
    metrics = [f"{record.get('compras_mercado') or 0} compras del mercado",
               f"marca {share}% de las compras" if share is not None else "share de la marca sin dato"]
    if record.get("en_str") == "sí":
        metrics.append(f"{money(record.get('gasto'), currency_code)} gasto")
        acos = record.get("acos")
        metrics.append(f"ACoS {acos}%" if acos is not None else "sin ventas")
    else:
        metrics.append("sin clicks en las campañas")
    if record.get("ya_en_exact") == "sí":
        metrics.append("ya existe como Exact")
    return metrics


# ── Helpers ───────────────────────────────────────────────────────────────────


def _xlsx_bytes(sheets: dict[str, pd.DataFrame]) -> bytes:
    """An .xlsx with one sheet per frame; a term that starts with = stays text, never a formula."""
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in sheets.items():
            frame.to_excel(writer, sheet_name=name, index=False)
        force_text_cells(writer.book)
    return buffer.getvalue()


def _escaped(text: str) -> str:
    # Two $ amounts in one markdown block read as LaTeX in Streamlit.
    return text.replace("$", "\\$")


def _data_signature(source_signature: str, sqp_bytes: bytes, business_report_digest: str,
                    structure: _AccountStructure) -> str:
    """What changes when the data under the analysis does, not when a value on screen does."""
    sqp_digest = hashlib.sha256(sqp_bytes).hexdigest()[:16]
    listing = structure.listed_at.isoformat() if structure.listed_at is not None else structure.exact_source
    return f"{source_signature}|{sqp_digest}|{business_report_digest}|{listing}"
