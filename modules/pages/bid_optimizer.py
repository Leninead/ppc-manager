"""Bid Optimizer: bid sugerido por ASIN desde el Search Term Report.

Los datos llegan del picker de Amazon Ads (o de un archivo subido a mano, su fallback);
el Inventory Report sigue siendo un upload opcional para el precio de lista.
"""
import html
import io
from functools import partial
from types import SimpleNamespace

import pandas as pd
import streamlit as st

from core.bid_analysis import (
    _PLACEMENT_RULES,
    NO_ASIN_WARNING,
    _limpiar_num,
    bid_ai_records,
    bid_row_labels,
    bids_by_asin,
    budget_midpoint,
    campaign_placements,
    detect_columns,
    resolve_asin_column,
)
from core.currency_format import currency_symbol, money
from core.search_term.frame import SOURCE_FILE
from core.ui.kpi_grid import Kpi, render_kpi_grid
from modules.pages.search_term_source import date_range_label, render_source_picker

# ══════════════════════════════════════════════════════════════════════
# AI analysis (capa core/ai_tab sobre el agente ai/agents/bid_optimizer)
# ══════════════════════════════════════════════════════════════════════

_AI_BADGE_COLORS = {
    "SUBIR": "background-color:#EAF3DE;color:#173404",
    "MANTENER": "background-color:#F1EFE8;color:#2C2C2A",
    "BAJAR": "background-color:#FAEEDA;color:#412402",
    "PAUSAR": "background-color:#FCEBEB;color:#501313",
}

_BID_LABELS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura ejecutiva de la IA sobre los bids que ya calculó el módulo",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_bids": "Bids priorizados — lectura IA",
           "col_item": "ASIN",
           "no_rows": "No hay ASINs con datos suficientes para analizar.",
           "file_source": ("El análisis IA guardado corre sobre los datos sincronizados de Amazon Ads. "
                           "Con un archivo subido a mano no hay dónde guardarlo: elegí una cuenta conectada.")},
    "en": {"title": "AI analysis",
           "caption": "Executive AI read over the bids the module already computed",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_bids": "Prioritized bids — AI read",
           "col_item": "ASIN",
           "no_rows": "No ASINs with enough data to analyze.",
           "file_source": ("The stored AI analysis runs on synced Amazon Ads data. A hand-uploaded file has "
                           "nowhere to store it: pick a connected account.")},
}


def _render_bid_ai_result(result, analysis, records, labels, currency_code):
    from core import ai_tab

    by_id = {f"A{i + 1:02d}": rec for i, rec in enumerate(records)}
    bids = result.get("bids") or []
    warnings = sum(1 for bid in bids if bid.get("advertencia"))
    st.markdown(ai_tab.ai_chips_html(warnings, f"{len(bids)} ASINs priorizados",
                                     analysis.elapsed, labels), unsafe_allow_html=True)
    row_labels = bid_row_labels(records)
    synthesis = ai_tab.map_synthesis_text(
        result.get("synthesis") or {}, lambda text: ai_tab.annotate_row_ids(text, row_labels))
    st.markdown(ai_tab.synthesis_html(synthesis, labels), unsafe_allow_html=True)

    rows = []
    for bid in bids:
        record = by_id.get(str(bid.get("row_id", "")))
        if record is None:
            continue
        # Las cifras que la razón cita tienen que estar en pantalla, o el AM no puede
        # auditar el juicio contra su propia tabla.
        rows.append({
            "row_id": str(bid.get("row_id", "")),
            "item": record["asin"],
            "metrics": [f"bid {money(record['bid_base'], currency_code)}",
                        f"CVR {record['cvr']:.1f}%", f"ACoS {record['acos']:.1f}%",
                        f"{record['orders']} órdenes",
                        f"spend {money(record['spend'], currency_code)}"],
            "badges": [bid.get("veredicto", "")],
            "confidence": str(bid.get("confianza", "")).upper(),
            "warning": bid.get("advertencia") or "",
            "reasoning": bid.get("razon", ""),
        })
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_bids"], labels, _AI_BADGE_COLORS),
                    unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════════════
# Excel exports (fuera de render(): aísla openpyxl del runtime de Streamlit)
# ══════════════════════════════════════════════════════════════════════

def _build_bid_excel(df_export):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_export.to_excel(writer, sheet_name="Bid Calculator", index=False)
    return buf.getvalue()


def _build_placements_excel(df_campaigns, df_reference):
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_campaigns.to_excel(writer, sheet_name="Placements por Campaña", index=False)
        df_reference.to_excel(writer, sheet_name="Referencia Placements", index=False)
    return buf.getvalue()


def _header():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.7rem;margin-bottom:0.2rem'>"
        "<span style='font-size:2rem'>🧠</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;color:#1F1F1F'>Bid Optimizer</div>"
        "<div style='font-size:0.82rem;color:#888'>Bids sugeridos por ASIN calculados desde el "
        "Search Term Report. CVR y precio de ads — más preciso que el Business Report.</div>"
        "</div></div>", unsafe_allow_html=True)
    st.divider()


def _empty_state(text):
    st.markdown(
        f"<div style='border:1px dashed #FFD9B3;border-radius:10px;padding:1.6rem;"
        f"text-align:center;color:#888'><div style='font-size:1.6rem'>📂</div>"
        f"<div style='margin-top:0.4rem'>{html.escape(text)}</div></div>",
        unsafe_allow_html=True)


def _period_label(source):
    if source.window_start and source.window_end:
        return date_range_label(source.window_start, source.window_end)
    return ""


def render():
    _header()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Calcular bid óptimo por ASIN usando CVR real, precio y target ACoS. "
                       "Fórmula: bid = CVR × precio × target ACoS.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("Del STR de la cuenta conectada de Amazon Ads. Opcional: Inventory Report "
                       "(.txt) para el precio de lista.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Campaign Builder (M10) para generar bulks con esos bids.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Elegí la cuenta y el período (o subí un STR a mano)\n"
            "2. Ingresá el Target ACoS y, si lo tenés, el Inventory Report\n"
            "3. Revisá el semáforo: ESCALAR / OK / REVISAR / SIN DATA\n"
            "4. Tab Placements & Budget: referencia SOP por tipo de campaña\n"
            "5. Tab Análisis IA: lectura ejecutiva sobre los bids calculados\n"
            "6. Descargá el bulk con los bids ajustados")

    target_acos = st.slider(
        "Target ACoS (%)", min_value=5, max_value=80, value=25, step=1,
        help="ACoS objetivo. Se usa para calcular bid base = CVR × precio × target ACoS.")

    source = render_source_picker(key_prefix="bid_opt", module_label="Bid Optimizer")

    file_inv = st.file_uploader(
        "Inventory Report (.txt o .csv) — opcional, para precio de lista exacto",
        type=["txt", "csv"], key="bid_opt_inv",
        help="Reports → Fulfillment → Inventory → All Listings Report. Si no lo subís, se usa el "
             "precio promedio de venta del STR.")

    if source is None:
        return

    df = source.frame
    currency_code = source.currency_code
    symbol = currency_symbol(currency_code)

    cols = detect_columns(df)
    df, col_asin, asin_source = resolve_asin_column(df, cols)

    missing = [name for name, key in (("Clicks", "clicks"), ("Orders", "orders"),
                                      ("Sales", "sales"), ("Spend", "spend"))
               if cols[key] is None]
    if missing:
        st.error(f"Faltan columnas en el Search Term Report: {', '.join(missing)}.")
        return
    if col_asin is None:
        st.warning(NO_ASIN_WARNING)
        return

    precio_map = {}
    if file_inv:
        try:
            df_inv = pd.read_csv(file_inv, sep="\t")
            df_inv.columns = [c.strip().lower() for c in df_inv.columns]
            if "asin" in df_inv.columns and "price" in df_inv.columns:
                df_inv["price"] = df_inv["price"].apply(_limpiar_num)
                precio_map = dict(zip(df_inv["asin"], df_inv["price"]))
                st.success(f"Inventory Report cargado — {len(precio_map)} precios de lista.")
            else:
                st.warning("El Inventory Report no trae las columnas ASIN y Price; se usa el "
                           "precio promedio de venta del STR.")
        except (ValueError, OSError, pd.errors.ParserError) as exc:
            st.warning(f"No se pudo leer el Inventory Report ({exc}); se usa el precio promedio "
                       "de venta del STR.")

    df_asin = bids_by_asin(df, cols, col_asin, target_acos, precio_map)
    precio_fuente = "Inventory Report (precio de lista)" if precio_map else "STR (precio promedio de venta)"

    money_format = f"{symbol}%.2f"
    # Lo consumen la tab de placements y el payload de la IA: se calcula una sola vez.
    camp_rows = campaign_placements(df, cols) if cols["campaign"] else []
    key_ajuste = "bid_opt_ajustes"
    if key_ajuste not in st.session_state:
        st.session_state[key_ajuste] = {}

    bid_tab1, bid_tab2, bid_tab3 = st.tabs(
        ["💰 Bid Calculator", "📍 Placements & Budget", "🤖 Análisis IA"])

    # ── Tab 1 — Bid Calculator ────────────────────────────────────────
    with bid_tab1:
        bid_prom = df_asin[df_asin["_bid_base"] > 0]["_bid_base"].mean()
        total_sales = df_asin[cols["sales"]].sum()
        acos_cuenta = (df_asin[cols["spend"]].sum() / total_sales * 100) if total_sales > 0 else 0

        render_kpi_grid([
            Kpi("ASINs analizados", len(df_asin)),
            Kpi("Bid promedio sugerido", money(bid_prom, currency_code) if bid_prom > 0 else "—"),
            Kpi("ACoS cuenta", f"{acos_cuenta:.1f}%"),
            Kpi("Escalar", int((df_asin["Estado"] == "🟢 ESCALAR").sum())),
            Kpi("Revisar", int((df_asin["Estado"] == "🔴 REVISAR").sum())),
        ])

        st.markdown("---")
        st.markdown("#### Bids sugeridos por ASIN")
        st.caption(f"CVR de ads reales del STR. Precio desde: {precio_fuente}. ASIN {asin_source}. "
                   "Ajustá el % por ASIN si querés afinar el bid.")

        df_tabla = pd.DataFrame({
            "Estado": df_asin["Estado"].values,
            "ASIN": df_asin[col_asin].values,
            "Clicks": df_asin[cols["clicks"]].astype(int).values,
            "Orders": df_asin[cols["orders"]].astype(int).values,
            "CVR % (ads)": df_asin["_cvr"].round(2).values,
            "Precio prom": df_asin["_precio"].round(2).values,
            "ACoS actual (%)": df_asin["_acos"].round(1).values,
            "Bid Base": df_asin["_bid_base"].values,
            "Ajuste %": [st.session_state[key_ajuste].get(str(a), 0)
                         for a in df_asin[col_asin].values],
        })

        df_editada = st.data_editor(
            df_tabla,
            column_config={
                "Ajuste %": st.column_config.NumberColumn(
                    "Ajuste %", help="Ej: +20 sube el bid 20%, -30 lo baja 30%.",
                    min_value=-50, max_value=100, step=5, format="%d%%"),
                "Precio prom": st.column_config.NumberColumn("Precio prom", format=money_format),
                "Bid Base": st.column_config.NumberColumn("Bid Base", format=money_format),
                "Estado": st.column_config.TextColumn("Estado", width="small"),
                "ASIN": st.column_config.TextColumn("ASIN", width="medium"),
            },
            disabled=["Estado", "ASIN", "Clicks", "Orders", "CVR % (ads)",
                      "Precio prom", "ACoS actual (%)", "Bid Base"],
            use_container_width=True, key="bid_editor")

        for _, row in df_editada.iterrows():
            st.session_state[key_ajuste][str(row["ASIN"])] = row["Ajuste %"]

        df_editada["Bid Final"] = [
            round(base * (1 + ajuste / 100), 2)
            for base, ajuste in zip(df_editada["Bid Base"], df_editada["Ajuste %"])]

        st.markdown("---")
        st.markdown("#### Resultado con Bid Final")
        st.dataframe(
            df_editada, use_container_width=True,
            column_config={
                "Precio prom": st.column_config.NumberColumn("Precio prom", format=money_format),
                "Bid Base": st.column_config.NumberColumn("Bid Base", format=money_format),
                "Bid Final": st.column_config.NumberColumn("Bid Final", format=money_format),
            })

        st.markdown("---")
        df_export = df_editada.copy()
        df_export["Target ACoS %"] = target_acos
        df_export["Moneda"] = currency_code or "no declarada"
        st.download_button(
            label=f"📥 Exportar bulk bids ({len(df_export)} ASINs)",
            data=_build_bid_excel(df_export), file_name="bid_optimizer.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="download_bid_opt")

    # ── Tab 2 — Placements & Budget ───────────────────────────────────
    with bid_tab2:
        st.markdown("### 📍 Placement Modifiers & Budget")
        st.caption("Referencia de placement modifiers y budget sugerido por tipo de campaña "
                   "(SOP Capybaras 2026).")

        st.markdown("#### Tabla de referencia")
        df_placements = pd.DataFrame([{
            "Tipo de Campaña": rule["Tipo de Campaña"],
            "ToS Modifier %": rule["ToS Modifier %"],
            "PDP Modifier %": rule["PDP Modifier %"],
            "Budget sugerido/día": f"{money(rule['budget_min'], currency_code)}–"
                                   f"{money(rule['budget_max'], currency_code)}",
        } for rule in _PLACEMENT_RULES])

        def _color_tos(val):
            if val >= 50:
                return "background-color: #E8F5E9; color: #1B5E20"
            if val >= 25:
                return "background-color: #FFF8E1; color: #F57F17"
            if val > 0:
                return "background-color: #FFF3E0; color: #BF360C"
            return ""

        def _color_pdp(val):
            if val >= 50:
                return "background-color: #E3F2FD; color: #0D47A1"
            if val > 0:
                return "background-color: #FFF8E1; color: #F57F17"
            return ""

        st.dataframe(
            df_placements.style.map(_color_tos, subset=["ToS Modifier %"])
                               .map(_color_pdp, subset=["PDP Modifier %"]),
            use_container_width=True, hide_index=True)

        st.info("**ToS** = Top of Search (primera página, sobre el fold). "
                "**PDP** = Product Detail Page (en listings de competidores). "
                "Los modifiers se suman al bid base calculado en la tab anterior.")

        st.markdown("---")
        st.markdown("#### Placements sugeridos por campaña")
        st.caption("Según el naming convention detectado en el STR del período cargado.")

        if cols["campaign"] is None:
            _empty_state("Este reporte no trae nombre de campaña, así que no se pueden sugerir "
                         "placements.")
        else:
            if not camp_rows:
                _empty_state("No hay campañas con datos en este período.")
            else:
                df_camp_pl = pd.DataFrame(camp_rows)
                render_kpi_grid([
                    Kpi("Campañas analizadas", len(df_camp_pl)),
                    Kpi("Con ToS modifier", int((df_camp_pl["ToS %"] > 0).sum())),
                    Kpi("Con PDP modifier", int((df_camp_pl["PDP %"] > 0).sum())),
                ])

                tipos = ["Todos"] + sorted(df_camp_pl["Tipo Detectado"].unique().tolist())
                filtro_tipo = st.selectbox("Filtrar por tipo", tipos, key="pl_filtro_tipo")
                df_camp_show = (df_camp_pl if filtro_tipo == "Todos"
                                else df_camp_pl[df_camp_pl["Tipo Detectado"] == filtro_tipo])
                st.dataframe(
                    df_camp_show, use_container_width=True, hide_index=True,
                    height=min(38 + 35 * len(df_camp_show), 600),
                    column_config={
                        "Spend": st.column_config.NumberColumn("Spend", format=money_format),
                        "Sales": st.column_config.NumberColumn("Sales", format=money_format),
                    })

                st.markdown("---")
                st.markdown("#### 💵 Budget diario estimado")
                total_budget = sum(budget_midpoint(row["Tipo Detectado"]) for row in camp_rows)
                render_kpi_grid([Kpi("Budget diario total estimado",
                                     f"{money(total_budget, currency_code)}/día")])
                st.caption("Punto medio del rango sugerido por el SOP para cada tipo de campaña. "
                           "Es una referencia, no el budget real de la cuenta.")

                st.markdown("---")
                st.download_button(
                    label=f"📥 Exportar Placements ({len(df_camp_pl)} campañas)",
                    data=_build_placements_excel(df_camp_pl, df_placements),
                    file_name="bid_optimizer_placements.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="download_placements")

    # ── Tab 3 — Análisis IA (guardado: lo genera el worker, la pantalla lo busca por huella) ──
    with bid_tab3:
        from core import ai_tab

        bid_labels = _BID_LABELS["es"]
        st.subheader(bid_labels["title"])
        st.caption(bid_labels["caption"])

        from ai.config import AI_ENABLED
        if not AI_ENABLED:
            st.caption(bid_labels["disabled"])
        elif source.source == SOURCE_FILE:
            st.info(bid_labels["file_source"])
        else:
            _render_bid_stored_analysis(source, df, target_acos, currency_code, bid_labels)


@st.cache_data(ttl=600, show_spinner=False)
def _previous_frame(source):
    """El tramo anterior del mismo largo, para que el agente lea qué cambió. None si no hay."""
    from core.amazon_ads.report_provider import ReportReadError, ReportProvider
    from core.bid_analysis import previous_window
    from modules.pages import search_term_source

    if source.window_start is None or source.window_end is None:
        return None
    profile = next((option for option in search_term_source._available_profiles()
                    if option.profile_id == source.profile_id), None)
    rest = search_term_source._open_rest()
    if profile is None or rest is None:
        return None
    start, end = previous_window(source.window_start, source.window_end)
    if profile.data_from is not None and start < profile.data_from:
        return None
    try:
        return ReportProvider(rest).search_terms(profile, start, end).frame
    except ReportReadError:
        return None


def _render_bid_stored_analysis(source, frame, target_acos, currency_code, bid_labels):
    """Busca el análisis de exactamente estos datos y parámetros; si no existe, ofrece pedirlo."""
    from ai.agent_call import build_agent_call
    from ai.agents.bid_optimizer import chat_document as bid_chat_document
    from core import ai_tab
    from core.chat import app_chat
    from core.ai_analysis import stored_tab
    from core.bid_analysis import ANALYSIS_MODULE, BidAnalysisParams, build_analysis_input
    from modules.pages import search_term_source

    params = BidAnalysisParams(int(target_acos))
    analysis_input = build_analysis_input(
        frame, target_acos=params.target_acos, account_label=source.label,
        period_label=_period_label(source), currency_code=currency_code,
        # La misma comparación que arma el worker: si difieren, difiere la huella y nunca matchea.
        previous_frame=_previous_frame(source))
    if analysis_input.data is None:
        st.info(bid_labels["no_rows"])
        return

    labels = ai_tab.ai_labels("es", bid_labels)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    settings = stored_tab._settings(ANALYSIS_MODULE, source.profile_id, search_term_source._open_rest)
    account_params = BidAnalysisParams.from_dict(settings.params) if settings else BidAnalysisParams.defaults()

    def _render(stored):
        # Las filas son las que leyó ESE análisis, no las de esta corrida: los row_ids que cita son suyos.
        _render_bid_ai_result(stored.result, SimpleNamespace(elapsed=int((stored.duration_ms or 0) / 1000)),
                              stored.records, labels, currency_code)

    result = stored_tab.render_stored_analysis(
        module=ANALYSIS_MODULE, key_prefix="bid_opt", source=source,
        input_digest=build_agent_call(ANALYSIS_MODULE, analysis_input.data).input_digest,
        params=params, account_params=account_params, open_rest=search_term_source._open_rest,
        current_username=search_term_source._current_username, render_result=_render,
        timezone=search_term_source.DISPLAY_TIMEZONE)

    if result.analysis is None:
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    records = result.analysis.records
    app_chat.share_analysis(app_chat.ChatAnalysis(
        module=ANALYSIS_MODULE, key=f"{ANALYSIS_MODULE}:{result.analysis.input_digest}", subject=source.label,
        documents=tuple({"title": f"Bid Optimizer · {source.label} · {document['title']}",
                         "content": document["content"]}
                        for document in build_agent_call(ANALYSIS_MODULE, analysis_input.data).call["context"])
        + ({"title": f"Bid Optimizer · {source.label} · Lectura de la IA",
            "content": bid_chat_document.reading_text(result.analysis.result, records)},),
        annotate=partial(ai_tab.annotate_row_ids, labels_by_id=bid_row_labels(records)),
        country_code="", profile_id=source.profile_id))
