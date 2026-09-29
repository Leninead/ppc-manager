"""PPC Forecast (M19): the Business Report's daily sales projected with their trend and their weekend difference.

The ad spend and ad sales behind the organic vs paid split come from the campaign reports of the Amazon Ads account
the AM picks, over the Business Report's own days. The rules live in core/ppc_forecast/.
"""
import hashlib
import io
import logging
from functools import partial

import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

from core.business_report.paid_split import spend_for_target
from core.chat import app_chat
from core.currency_format import currency_symbol, money
from core.date_labels import date_range_label
from core.helpers import kpi_card
from core.ppc_forecast.analysis import ANALYSIS_MODULE, build_analysis_input
from core.ppc_forecast.projection import DATE, PROJECTED_SALES, SalesForecast, forecast_sales
from modules.pages.ad_account_block import (
    AccountAds,
    AdAccountTexts,
    ads_exceed_br_warning,
    read_account_ads,
    render_ad_account_block,
)

log = logging.getLogger(__name__)

MODULE_LABEL = "PPC Forecast"
KEY_PREFIX = "forecast"
_GENERATED_FOR_KEY = "forecast_generated_for"

ADS_BLOCK_TITLE = "Ventas de ads de la cuenta"
NO_ACCOUNTS_NOTE = ("No hay cuentas de Amazon Ads conectadas, así que no hay desglose orgánico vs paid ni spend "
                    "estimado. Se conectan en Sistema → Cuentas conectadas.")
CHOOSE_ACCOUNT_NOTE = ("Elegí la cuenta y el país del BR para separar las ventas de ads de las orgánicas y estimar el "
                       "spend para el objetivo. El BR no dice de qué cuenta es, así que no hay una por defecto.")
FIRST_LOAD_NOTE = "Estamos trayendo las campañas de esta cuenta por primera vez; cuando termine aparece el desglose."
UNREADABLE_NOTE = "Sin desglose orgánico vs paid ni spend estimado."
SPLIT_CAPTION = ("{covered} de {total} días del BR tienen datos de ads ({window} · {products}). Sponsored Products "
                 "con atribución de {attribution} días; Sponsored Brands y Display como los cuenta Campaign Manager. "
                 "Las ventas de ads se atribuyen al día del click: las de los últimos días todavía pueden crecer.")
BUDGET_HELP = ("Spend de ads ÷ ventas del BR (TACoS) en los días con datos de ads, aplicado a las ventas con el "
               "crecimiento objetivo. Supone que el TACoS no cambia al subir el spend.")

_ADS_TEXTS = AdAccountTexts(title=ADS_BLOCK_TITLE, no_accounts=NO_ACCOUNTS_NOTE, choose_account=CHOOSE_ACCOUNT_NOTE,
                            first_load=FIRST_LOAD_NOTE, unreadable=UNREADABLE_NOTE, without_ads="Sin desglose")

_CONFIDENCE_COLORS = ("background-color:#EAF3DE;color:#173404", "background-color:#FAEEDA;color:#412402",
                      "background-color:#FFEBEE;color:#9C0006")
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre las cifras que ya calculó el módulo: qué tanto confiar en la proyección "
                      "y en el spend estimado, y qué hacer esta semana",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_title": "Cifras del módulo — lectura IA",
           "col_item": "Cifra", "col_diag": "Confianza",
           "counts": "{n} cifras leídas",
           "stale_body": "Cambió lo que el análisis leyó, por ejemplo el crecimiento objetivo, el horizonte o los "
                         "datos de ads. Lo que se muestra abajo corresponde a los datos anteriores.",
           "projection_item": "Ventas proyectadas ({days} días)",
           "budget_item": "Spend estimado para el objetivo",
           "with_growth": "con +{growth}%: {amount}",
           "levels": {"alta": "Alta", "media": "Media", "baja": "Baja"}},
    "en": {"title": "AI analysis",
           "caption": "AI read on the figures the module already computed: how far to trust the projection and the "
                      "spend estimate, and what to do this week",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_title": "The module's figures — AI read",
           "col_item": "Figure", "col_diag": "Confidence",
           "counts": "{n} figures read",
           "stale_body": "What the analysis read changed, for example the growth target, the horizon or the ads "
                         "data. What is shown below belongs to the previous data.",
           "projection_item": "Projected sales ({days} days)",
           "budget_item": "Estimated spend for the target",
           "with_growth": "with +{growth}%: {amount}",
           "levels": {"alta": "High", "media": "Medium", "baja": "Low"}},
}


# ── Helpers numéricos ────────────────────────────────────────────────────────

def _clean_num(series):
    """Limpia $, %, comas y convierte a float."""
    return (
        pd.to_numeric(
            series.astype(str)
            .str.replace(r"[\$%,]", "", regex=True)
            .str.strip(),
            errors="coerce",
        ).fillna(0.0)
    )


# ── Parsers ──────────────────────────────────────────────────────────────────

@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_br_daily(file_bytes, fname):
    """Parsea BR diario. Retorna DataFrame con columnas _date, _sales, _units, _sess (NaN si el BR no las trae)."""
    df = pd.read_excel(io.BytesIO(file_bytes)) if fname.endswith(".xlsx") else pd.read_csv(io.BytesIO(file_bytes))
    df.columns = df.columns.str.strip()

    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    sales_col = next(
        (c for c in df.columns if "ordered product sales" in c.lower() and "b2b" not in c.lower()),
        None,
    )
    units_col = next(
        (c for c in df.columns if "units ordered" in c.lower() and "b2b" not in c.lower()),
        None,
    )
    sess_col = next(
        (c for c in df.columns if "sessions" in c.lower() and "total" in c.lower() and "b2b" not in c.lower()),
        None,
    )

    if not date_col:
        raise ValueError("No se encontró columna Date en el archivo.")
    if not sales_col:
        raise ValueError("No se encontró columna Ordered Product Sales en el archivo.")

    df["_date"] = pd.to_datetime(df[date_col], format="mixed", dayfirst=False, errors="coerce")
    df = df.dropna(subset=["_date"])
    df["_sales"] = _clean_num(df[sales_col])
    # A column the report does not carry is unknown, not zero: the AI reads these.
    df["_units"] = _clean_num(df[units_col]) if units_col else float("nan")
    df["_sess"] = _clean_num(df[sess_col]) if sess_col else float("nan")

    df = df.sort_values("_date").reset_index(drop=True)
    return df


# ── Excel export ─────────────────────────────────────────────────────────────

def _build_forecast_excel(forecast: SalesForecast, n_days: int, needed_spend: float | None, client_name: str,
                          currency_code: str):
    """Construye Excel con 2 hojas: Resumen + Proyección Diaria."""
    HDR_FILL = PatternFill("solid", fgColor="E84000")
    HDR_FONT = Font(bold=True, color="FFFFFF", size=11)
    ALT_FILL = PatternFill("solid", fgColor="FFF3E0")
    CENTER = Alignment(horizontal="center", vertical="center")
    thin = Side(style="thin", color="DDDDDD")
    BORDER = Border(left=thin, right=thin, top=thin, bottom=thin)
    show = partial(money, currency_code=currency_code)

    wb = Workbook()

    # ── Hoja 1: Resumen ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"

    # Título branding
    ws.merge_cells("A1:D1")
    title_cell = ws["A1"]
    titulo = f"PPC Forecast — {client_name}" if client_name else "PPC Forecast"
    title_cell.value = titulo
    title_cell.fill = HDR_FILL
    title_cell.font = Font(bold=True, color="FFFFFF", size=13)
    title_cell.alignment = CENTER
    ws.row_dimensions[1].height = 24

    ws.append([])  # blank row

    # Métricas históricas
    ws.append(["Métrica", "Valor"])
    for cell in ws[ws.max_row]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER

    ratio = forecast.trend.weekend_ratio
    metric_rows = [
        ("Días de datos", n_days),
        ("Ventas promedio/día", show(forecast.average_daily_sales)),
        ("Tendencia por día", _signed_money(forecast.trend.slope, currency_code)),
        ("Ratio Finde/Laboral", f"{ratio:.2f}x" if ratio is not None else "sin dato"),
        ("Horizonte de proyección (días)", forecast.horizon),
        ("Total ventas proyectadas", show(forecast.projected_sales)),
        ("Total ventas con crecimiento objetivo", show(forecast.sales_with_growth)),
        ("Spend estimado para objetivo", show(needed_spend) if needed_spend is not None else "sin dato"),
    ]

    for i, (label, val) in enumerate(metric_rows):
        ws.append([label, val])
        row_idx = ws.max_row
        for cell in ws[row_idx]:
            cell.border = BORDER
            if i % 2 == 1:
                cell.fill = ALT_FILL

    ws.column_dimensions["A"].width = 38
    ws.column_dimensions["B"].width = 24

    # ── Hoja 2: Proyección Diaria ────────────────────────────────────────────
    ws2 = wb.create_sheet("Proyección Diaria")
    proj_df = forecast.projection

    headers = list(proj_df.columns)
    ws2.append(headers)
    for cell in ws2[1]:
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = CENTER
        cell.border = BORDER

    for i, row in proj_df.iterrows():
        ws2.append(list(row))
        row_idx = ws2.max_row
        for cell in ws2[row_idx]:
            cell.border = BORDER
            if i % 2 == 1:
                cell.fill = ALT_FILL
        # Color tipo finde
        tipo_cell = ws2.cell(row=row_idx, column=4)
        if tipo_cell.value == "Fin de semana":
            tipo_cell.fill = PatternFill("solid", fgColor="FFF3E0")

    for col_idx, col in enumerate(["A", "B", "C", "D"], start=1):
        ws2.column_dimensions[col].width = 22

    ws2.freeze_panes = "A2"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _signed_money(value: float, currency_code: str) -> str:
    return f"{'+' if value >= 0 else ''}{money(value, currency_code)}/día"


# ── Render ───────────────────────────────────────────────────────────────────

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📈</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>PPC Forecast</div>"
        "<div style='font-size:0.82rem;color:#888;'>Proyección de ventas y spend basada en tendencia histórica + estacionalidad.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    _how_to_use()

    # ── Inputs globales ──────────────────────────────────────────────────────
    col_a, col_b, col_c = st.columns(3)
    with col_a:
        target_growth = st.slider(
            "Crecimiento objetivo (%)",
            min_value=0, max_value=100, value=10, step=5,
            help="Cuánto quieres crecer sobre la proyección de tendencia base.",
        )
    with col_b:
        horizon = st.selectbox(
            "Horizonte de proyección (días)",
            options=[7, 14, 30],
            index=1,
        )
    with col_c:
        client_name = st.text_input("Nombre del cliente (para el Excel)", value="")

    st.markdown("---")

    file_br = st.file_uploader(
        "BR Diario (.csv o .xlsx) — requerido",
        type=["csv", "xlsx"],
        key="forecast_br",
        help="Business Report > By Date > Sales and Traffic. Mínimo 14 días.",
    )
    ad_account = render_ad_account_block(KEY_PREFIX, _ADS_TEXTS)

    if not file_br:
        _render_empty_state()
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    br_bytes = file_br.getvalue()
    try:
        history = _parse_br_daily(br_bytes, file_br.name)
    except Exception as e:  # an unreadable report must end in a message, not a traceback
        log.warning("PPC Forecast: business report %s unreadable: %s", file_br.name, e)
        st.error(f"Error al leer BR Diario: {e}")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    n_days = len(history)
    if n_days < 7:
        st.error("El archivo tiene menos de 7 días de datos. Se necesitan al menos 7 días para proyectar.")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    if n_days < 14:
        st.warning(f"Sólo hay {n_days} días de datos. La proyección será menos precisa. Se recomiendan al menos 14 días.")

    # ── Botón principal ──────────────────────────────────────────────────────
    signature = _inputs_signature(br_bytes, horizon, target_growth)
    if st.button("Generar Forecast", type="primary", key="forecast_run"):
        st.session_state[_GENERATED_FOR_KEY] = signature
    if st.session_state.get(_GENERATED_FOR_KEY) != signature:
        st.info(f"Archivo cargado: {file_br.name} ({n_days} días). Haz clic en 'Generar Forecast' para continuar.")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    forecast = forecast_sales(history, horizon, target_growth)
    ads = read_account_ads(ad_account, history, _ADS_TEXTS)
    forecast_tab, analysis_tab = st.tabs(["📈 Forecast", "🤖 Análisis IA"])
    with forecast_tab:
        _render_forecast(forecast, n_days, ads, history, client_name)
    with analysis_tab:
        _render_ai_tab(history, forecast, ads, subject=ads.account or client_name.strip() or file_br.name,
                       data_signature=_data_signature(br_bytes, ads.profile_id))


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Proyección de ventas con una tendencia lineal y la diferencia de fin de semana, ajustadas "
                       "juntas. Recomendación de budget con el TACoS de la cuenta.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("BR Diario (By Date → Sales and Traffic) mínimo 14 días, ideal 30+. La cuenta de Amazon Ads "
                       "del BR (opcional) separa las ventas de ads de las orgánicas y estima el spend.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Ajustar budgets en Campaign Manager según escenario elegido y revisar Account Pulse (M21) semanalmente.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Configurá crecimiento objetivo + horizonte (7/14/30 días)\n"
            "2. Subí el BR diario (mínimo 14 días)\n"
            "3. Elegí la cuenta y el país del BR para el desglose orgánico vs paid (opcional)\n"
            "4. Tocá Generar Forecast: gráfico histórico + proyección, desglose y spend estimado\n"
            "5. Análisis IA: qué tanto confiar en la proyección y qué hacer esta semana\n"
            "6. Descargá el Excel con 2 hojas (resumen + proyección diaria)"
        )


def _render_empty_state():
    st.markdown(
        "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
        "border-radius:12px;margin:1rem 0;'>"
        "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
        "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Sube el BR Diario para comenzar.</div>"
        "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
        "Arrastrá o hacé click en el uploader de arriba</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _render_forecast(forecast: SalesForecast, n_days: int, ads: AccountAds, history: pd.DataFrame,
                     client_name: str):
    show = partial(money, currency_code=ads.currency_code)
    trend = forecast.trend
    needed_spend = spend_for_target(ads.split, forecast.sales_with_growth)

    # ── SECCIÓN 1: Métricas históricas ───────────────────────────────────────
    st.subheader("Métricas Históricas")
    ratio = trend.weekend_ratio
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.markdown(kpi_card("Días de datos", str(n_days)), unsafe_allow_html=True)
    with c2:
        st.markdown(kpi_card("Ventas promedio/día", show(forecast.average_daily_sales)), unsafe_allow_html=True)
    with c3:
        st.markdown(kpi_card("Tendencia", _signed_money(trend.slope, ads.currency_code)), unsafe_allow_html=True)
    with c4:
        st.markdown(kpi_card("Ratio Finde/Laboral", f"{ratio:.2f}x" if ratio is not None else "—"),
                    unsafe_allow_html=True)

    # ── SECCIÓN 2: Gráfico ───────────────────────────────────────────────────
    st.subheader("Tendencia Histórica + Proyección")

    hist_dates = [d.strftime("%Y-%m-%d") for d in history["_date"]]
    hist_sales = history["_sales"].tolist()
    proj_dates = forecast.projection[DATE].tolist()
    proj_sales = forecast.projection[PROJECTED_SALES].tolist()

    all_dates = hist_dates + proj_dates
    chart_df = pd.DataFrame(
        {
            "Ventas Reales ($)": hist_sales + [None] * forecast.horizon,
            "Ventas Proyectadas ($)": [None] * len(hist_sales) + proj_sales,
        },
        index=all_dates,
    )
    # Añadir el último punto histórico como primer punto proyectado para continuidad visual
    if hist_sales:
        chart_df.loc[hist_dates[-1], "Ventas Proyectadas ($)"] = hist_sales[-1]

    st.line_chart(chart_df)

    # ── SECCIÓN 3: Resumen de proyección ─────────────────────────────────────
    st.subheader(f"Resumen — Próximos {forecast.horizon} días")
    c1, c2, c3 = st.columns(3)
    c1.metric(
        f"Ventas proyectadas ({forecast.horizon}d)",
        show(forecast.projected_sales),
    )
    c2.metric(
        f"Con crecimiento +{forecast.target_growth}%",
        show(forecast.sales_with_growth),
        delta=f"+{show(forecast.sales_with_growth - forecast.projected_sales)}",
    )
    c3.metric(
        "Spend estimado para objetivo",
        show(needed_spend) if needed_spend is not None else "—",
        help=BUDGET_HELP if needed_spend is not None else f"Sin dato: {ads.no_ads_reason}.",
    )

    # ── SECCIÓN 4: Tabla de proyección diaria ────────────────────────────────
    with st.expander("Ver tabla de proyección diaria"):
        st.dataframe(
            forecast.projection,
            use_container_width=True,
            column_config={
                PROJECTED_SALES: st.column_config.NumberColumn(
                    PROJECTED_SALES, format=f"{currency_symbol(ads.currency_code)}%.2f"
                ),
            },
        )

    # ── SECCIÓN 5: Desglose orgánico vs paid ─────────────────────────────────
    _render_split(ads, show)

    # ── Export Excel ─────────────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("Exportar")
    try:
        excel_buf = _build_forecast_excel(forecast, n_days, needed_spend, client_name, ads.currency_code)
        fname_out = f"PPC_Forecast_{client_name.replace(' ', '_') + '_' if client_name else ''}{forecast.horizon}d.xlsx"
        st.download_button(
            label="Descargar Forecast Excel",
            data=excel_buf,
            file_name=fname_out,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="forecast_dl",
        )
    except Exception as e:
        st.error(f"Error al generar Excel: {e}")


def _render_split(ads: AccountAds, show):
    st.subheader("Desglose Orgánico vs Paid")
    split = ads.split
    if split is None:
        st.caption(f"Sin desglose: {ads.no_ads_reason}.")
        return
    if split.ads_exceed_br:
        st.warning(ads_exceed_br_warning(split))
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card("Spend de ads", show(split.ad_spend)), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card("Ventas de ads", show(split.ad_sales)), unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card("ACoS", f"{split.acos:.1f}%" if split.acos is not None else "—"), unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card("Ventas orgánicas estimadas", show(split.organic_sales)), unsafe_allow_html=True)
    st.caption(SPLIT_CAPTION.format(covered=split.covered_days, total=split.history_days,
                                    window=date_range_label(split.start, split.end),
                                    products=" · ".join(split.products) or "sin campañas con actividad",
                                    attribution=split.attribution_days))
    if split.paid_share is not None:
        split_df = pd.DataFrame(
            {
                "Canal": ["Paid (Ads)", "Orgánico"],
                "Ventas": [show(split.ad_sales), show(split.organic_sales)],
                "% del Total": [round(split.paid_share, 1), round(100.0 - split.paid_share, 1)],
            }
        )
        st.dataframe(split_df, use_container_width=True, hide_index=True)


def _render_ai_tab(history: pd.DataFrame, forecast: SalesForecast, ads: AccountAds, *, subject: str,
                   data_signature: str):
    from ai.agents.ppc_forecast import chat_document
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
    payload = build_analysis_input(history, forecast, split=ads.split, ads=ads.series, account=ads.account,
                                   ads_note=ads.no_ads_reason, currency_code=ads.currency_code, lang=lang)
    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload, file_signature=data_signature,
                                       labels=labels, auto_fire=False)
    if analysis is not None:
        # A stale analysis read other figures: its rows show the ones it read.
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload, _ai_records(forecast, ads, labels))
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=subject,
        reading=lambda finished: chat_document.reading_text(finished.result),
        country_code=ads.country_code, profile_id=ads.profile_id)


def _ai_records(forecast: SalesForecast, ads: AccountAds, labels: dict) -> list[dict]:
    """The module's figures the AI reads, as the opinion table names them."""
    show = partial(money, currency_code=ads.currency_code)
    records = [{"tema": "PROYECCION", "item": labels["projection_item"].format(days=forecast.horizon),
                "metrics": [show(forecast.projected_sales),
                            labels["with_growth"].format(growth=forecast.target_growth,
                                                         amount=show(forecast.sales_with_growth))]}]
    needed_spend = spend_for_target(ads.split, forecast.sales_with_growth)
    if needed_spend is not None:
        records.append({"tema": "PRESUPUESTO", "item": labels["budget_item"], "metrics": [show(needed_spend)]})
    return records


def _render_ai_result(result, analysis, *, records, labels):
    from core import ai_tab

    rows = forecast_ai_rows(result.get("lecturas") or [], records, labels)
    warnings = sum(1 for row in rows if row["warning"])
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(rows)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    st.markdown(ai_tab.synthesis_html(result.get("synthesis") or {}, labels), unsafe_allow_html=True)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _confidence_colors(labels)),
                    unsafe_allow_html=True)


def forecast_ai_rows(readings: list, records: list, labels: dict) -> list[dict]:
    """Display rows for the opinion table: the module's figure, its value and the AI's confidence in it."""
    by_topic = {record["tema"]: record for record in records}
    rows = []
    for reading in readings:
        record = by_topic.get(reading.get("tema"))
        if record is None:
            continue
        level = str(reading.get("confianza", "")).lower()
        rows.append({
            "item": record["item"],
            "metrics": record["metrics"],
            "badges": [labels["levels"].get(level, level)],
            "warning": reading.get("advertencia") or "",
            "reasoning": reading.get("razon", ""),
        })
    return rows


def _confidence_colors(labels: dict) -> dict:
    return dict(zip((labels["levels"][level] for level in ("alta", "media", "baja")), _CONFIDENCE_COLORS))


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _inputs_signature(br_bytes: bytes, horizon: int, target_growth: int) -> str:
    """What "Generar Forecast" computed from: the forecast stays on screen until it changes."""
    return f"{_digest(br_bytes)}|{horizon}|{target_growth}"


def _data_signature(br_bytes: bytes, profile_id: str) -> str:
    """What changes when the Business Report or the account under the analysis do, not when a parameter does."""
    return f"{_digest(br_bytes)}|{profile_id}"
