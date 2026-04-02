import io

import streamlit as st
import pandas as pd
import plotly.express as px

from core.helpers import kpi_card


@st.cache_data
def _load_str(data, name):
    """Cached reader for STR files."""
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


def _detect_cols(df):
    """Auto-detect STR column names, return dict of canonical -> actual column name."""
    def _find(keywords, exclude=None):
        for c in df.columns:
            cl = c.lower()
            if all(k in cl for k in keywords):
                if exclude and any(e in cl for e in exclude):
                    continue
                return c
        return None

    return {
        "search_term": _find(["customer search term"]) or _find(["search term"]) or _find(["query"]),
        "spend":       _find(["spend"]),
        "sales":       _find(["sales"], exclude=["other", "advertised"]),
        "orders":      _find(["order"], exclude=["other"]) or _find(["purchases"]),
        "clicks":      _find(["clicks"]) or _find(["click"]),
        "impressions": _find(["impressions"]) or _find(["impression"]),
        "acos":        _find(["acos"]),
        "ctr":         _find(["ctr"]) or _find(["click-through"]),
        "cvr":         _find(["conversion"]) or _find(["cvr"]),
        "campaign":    _find(["campaign name"]) or _find(["campaign"]),
        "ad_group":    _find(["ad group"]),
        "match_type":  _find(["match type"]) or _find(["targeting type"]),
        "portfolio":   _find(["portfolio name"]) or _find(["portfolio"]),
    }


def _to_num(df, col):
    if col and col in df.columns:
        return pd.to_numeric(df[col].astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""), errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


def _classify_term_type(term, brand_terms):
    """Classify a search term as Brand, Long-tail, or Generic."""
    t = str(term).lower().strip()
    if brand_terms and any(bt in t for bt in brand_terms):
        return "Brand"
    if len(t.split()) >= 4:
        return "Long-tail"
    return "Generic"


def _classify_status(row, target_acos):
    """Classify a row into an action status."""
    spend = row["_spend"]
    sales = row["_sales"]
    orders = row["_orders"]
    clicks = row["_clicks"]
    acos = (spend / sales * 100) if sales > 0 else 0

    if orders >= 3 and acos > 0 and acos < target_acos * 0.5:
        return "Escalar"
    if sales > 0 and acos <= target_acos:
        return "OK"
    if sales > 0 and acos > target_acos * 1.5:
        return "Reducir"
    if clicks > 10 and orders == 0:
        return "Revisar"
    if clicks >= 3 and sales == 0 and spend > 0:
        return "Negativa?"
    return "—"


def _is_brand_campaign(name):
    """Detect if a campaign name suggests brand/defensive."""
    n = str(name).lower()
    return any(kw in n for kw in ["branded", "brand", "defense", "defensive"])


def _build_str_excel(df_f, df_original, kpi_dict, brand_terms):
    """Genera Excel multi-sheet con STR analizado. Retorna bytes."""
    buf = io.BytesIO()

    # Preparar hoja 1
    df_exp = df_f.copy() if len(df_f) > 0 else df_original.head(0).copy()
    rename_map = {}
    if "_term_type" in df_exp.columns:
        rename_map["_term_type"] = "Tipo Termino"
    if "_estado" in df_exp.columns:
        rename_map["_estado"] = "Estado"
    if rename_map:
        df_exp = df_exp.rename(columns=rename_map)
    drop_cols = [c for c in df_exp.columns if c.startswith("_")]
    df_exp = df_exp.drop(columns=drop_cols, errors="ignore")

    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Hoja 1 — siempre
        df_exp.to_excel(writer, sheet_name="STR Analizado", index=False)

        # Hoja 2 — KPIs
        kpi_rows = [[k, v] for k, v in kpi_dict.items()]
        pd.DataFrame(kpi_rows, columns=["Metrica", "Valor"]).to_excel(
            writer, sheet_name="Resumen KPIs", index=False
        )

        # Hoja 3 — Por Estado
        if len(df_f) > 0 and "_estado" in df_f.columns:
            est = df_f.groupby("_estado").agg(
                Terminos=("_estado", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
            ).reset_index().rename(columns={"_estado": "Estado"})
            est["ACoS"] = (est["Spend"] / est["Sales"].replace(0, float("nan")) * 100).fillna(0).round(1)
            est.sort_values("Spend", ascending=False).to_excel(
                writer, sheet_name="Por Estado", index=False
            )

        # Hoja 4 — Por Tipo Término
        if len(df_f) > 0 and "_term_type" in df_f.columns and brand_terms:
            tt = df_f.groupby("_term_type").agg(
                Terminos=("_term_type", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index().rename(columns={"_term_type": "Tipo"})
            tt["ACoS"] = (tt["Spend"] / tt["Sales"].replace(0, float("nan")) * 100).fillna(0).round(1)
            tt["% Spend"] = (tt["Spend"] / tt["Spend"].sum() * 100).round(1)
            if not tt.empty:
                tt.to_excel(writer, sheet_name="Por Tipo Termino", index=False)

    return buf.getvalue()


def render():
    st.header("Search Term Report")
    st.caption("Analisis de terminos de busqueda con metricas de ACoS, gasto y ventas totales.")
    st.divider()
    file_str = st.file_uploader("Sube tu STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str")
    if not file_str:
        return

    df_raw = _load_str(file_str.getvalue(), file_str.name)
    st.success(f"{len(df_raw)} filas cargadas")

    cols = _detect_cols(df_raw)

    # Numeric columns on raw df
    df_raw["_spend"]  = _to_num(df_raw, cols["spend"])
    df_raw["_sales"]  = _to_num(df_raw, cols["sales"])
    df_raw["_orders"] = _to_num(df_raw, cols["orders"])
    df_raw["_clicks"] = _to_num(df_raw, cols["clicks"])
    df_raw["_imps"]   = _to_num(df_raw, cols["impressions"])
    df_raw["_acos"]   = _to_num(df_raw, cols["acos"])
    df_raw["_ctr"]    = _to_num(df_raw, cols["ctr"])

    total_rows = len(df_raw)

    # ── CAMBIO 1: Filtro portfolio transversal ──────────────────────
    port_col = cols["portfolio"]
    if port_col and port_col in df_raw.columns:
        portfolios = sorted(df_raw[port_col].dropna().astype(str).str.strip().unique())
        portfolios = [p for p in portfolios if p and p != "" and p.lower() != "nan"]
    else:
        portfolios = []

    if portfolios:
        selected_ports = st.multiselect(
            "Filtrar por Portfolio",
            options=portfolios,
            default=portfolios,
            key="str_portfolio_filter",
        )
        if selected_ports and len(selected_ports) < len(portfolios):
            df = df_raw[df_raw[port_col].astype(str).str.strip().isin(selected_ports)].copy()
            st.caption(f"{len(df)} de {total_rows} filas (filtrado por portfolio)")
        else:
            df = df_raw.copy()
    else:
        df = df_raw.copy()

    # Pre-init for tab4 (IA) scope
    df_neg = pd.DataFrame()
    df_harv = pd.DataFrame()

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "Vista General",
        "Negatives Mining",
        "Harvest Candidates",
        "Analisis IA",
        "Por Campana",
    ])

    # ══════════════════════════════════════════════════════════════
    # TAB 1: Vista General ENRIQUECIDA
    # ══════════════════════════════════════════════════════════════
    with tab1:
        # ── Target ACoS slider ──────────────────────────────────
        target_acos = st.slider("Target ACoS (%)", 10, 80, 30, key="str_target_acos_tab1")

        # ── Brand terms input ───────────────────────────────────
        brand_input = st.text_input(
            "Brand terms (separados por coma)",
            placeholder="ej: dermaglos, dg, love to dream",
            key="str_brand_terms",
        )
        brand_terms = [t.strip().lower() for t in brand_input.split(",") if t.strip()] if brand_input else []

        # ── Term type classification ────────────────────────────
        st_col = cols["search_term"]
        if st_col and st_col in df.columns:
            df["_term_type"] = df[st_col].apply(lambda t: _classify_term_type(t, brand_terms))
        else:
            df["_term_type"] = "Generic"

        # ── 12 KPIs ────────────────────────────────────────────
        total_spend = df["_spend"].sum()
        total_sales = df["_sales"].sum()
        total_clicks = df["_clicks"].sum()
        total_imps = df["_imps"].sum()
        total_orders = df["_orders"].sum()
        acos_val = (total_spend / total_sales * 100) if total_sales > 0 else 0
        roas_val = (total_sales / total_spend) if total_spend > 0 else 0
        ctr_val = (total_clicks / total_imps * 100) if total_imps > 0 else 0
        cvr_val = (total_orders / total_clicks * 100) if total_clicks > 0 else 0
        cpc_val = (total_spend / total_clicks) if total_clicks > 0 else 0
        waste_spend = df[df["_sales"] == 0]["_spend"].sum()
        pct_waste = (waste_spend / total_spend * 100) if total_spend > 0 else 0
        rows_with_sales = (df["_sales"] > 0).sum()
        pct_conv = (rows_with_sales / len(df) * 100) if len(df) > 0 else 0

        # Row 1
        r1c1, r1c2, r1c3, r1c4 = st.columns(4)
        with r1c1:
            st.markdown(kpi_card("Total Spend", f"${total_spend:,.2f}"), unsafe_allow_html=True)
        with r1c2:
            st.markdown(kpi_card("Total Sales", f"${total_sales:,.2f}"), unsafe_allow_html=True)
        with r1c3:
            acos_delta = acos_val - target_acos
            st.markdown(kpi_card("ACoS", f"{acos_val:.1f}%", delta=acos_delta, delta_good=False), unsafe_allow_html=True)
        with r1c4:
            st.markdown(kpi_card("ROAS", f"{roas_val:.2f}x"), unsafe_allow_html=True)

        # Row 2
        r2c1, r2c2, r2c3, r2c4 = st.columns(4)
        with r2c1:
            st.markdown(kpi_card("Impressions", f"{total_imps:,.0f}"), unsafe_allow_html=True)
        with r2c2:
            st.markdown(kpi_card("Clicks", f"{total_clicks:,.0f}"), unsafe_allow_html=True)
        with r2c3:
            st.markdown(kpi_card("CTR Promedio", f"{ctr_val:.2f}%"), unsafe_allow_html=True)
        with r2c4:
            st.markdown(kpi_card("CVR Promedio", f"{cvr_val:.2f}%"), unsafe_allow_html=True)

        # Row 3
        r3c1, r3c2, r3c3, r3c4 = st.columns(4)
        with r3c1:
            st.markdown(kpi_card("CPC Promedio", f"${cpc_val:.2f}"), unsafe_allow_html=True)
        with r3c2:
            st.markdown(kpi_card("Orders", f"{total_orders:,.0f}"), unsafe_allow_html=True)
        with r3c3:
            st.markdown(kpi_card("% Waste", f"{pct_waste:.1f}%"), unsafe_allow_html=True)
        with r3c4:
            st.markdown(kpi_card("% Con Ventas", f"{pct_conv:.1f}%"), unsafe_allow_html=True)

        st.markdown("")

        # ── Filtros interactivos ────────────────────────────────
        st.markdown("#### Filtros")
        fc1, fc2, fc3, fc4 = st.columns(4)
        camp_col = cols["campaign"]
        match_col = cols["match_type"]

        with fc1:
            camp_options = ["Todas"]
            if camp_col and camp_col in df.columns:
                camp_options += sorted(df[camp_col].dropna().astype(str).unique())
            selected_camp = st.selectbox("Campana", camp_options, key="str_f_camp")
        with fc2:
            match_options = []
            if match_col and match_col in df.columns:
                match_options = sorted(df[match_col].dropna().astype(str).str.strip().unique())
            selected_match = st.multiselect("Match Type", match_options, default=[], key="str_f_match")
        with fc3:
            acos_max = st.number_input("ACoS max %", value=0, min_value=0, key="str_f_acos_max")
        with fc4:
            spend_min = st.number_input("Spend min $", value=0.0, min_value=0.0, step=0.5, key="str_f_spend_min")

        vista = st.radio(
            "Vista rapida",
            ["Todos", "Winners", "Sin ventas", "Top Sales", "Top Spend"],
            horizontal=True,
            key="str_vista",
        )

        # ── Apply filters ──────────────────────────────────────
        df_f = df.copy()
        if selected_camp != "Todas" and camp_col:
            df_f = df_f[df_f[camp_col].astype(str) == selected_camp]
        if selected_match and match_col:
            df_f = df_f[df_f[match_col].astype(str).str.strip().isin(selected_match)]
        if acos_max > 0:
            df_f = df_f[df_f["_acos"] <= acos_max]
        if spend_min > 0:
            df_f = df_f[df_f["_spend"] >= spend_min]

        # Vista rápida
        if vista == "Winners":
            df_f = df_f[(df_f["_orders"] >= 2) & (df_f["_acos"] > 0) & (df_f["_acos"] < target_acos)]
            df_f = df_f.sort_values("_acos", ascending=True)
        elif vista == "Sin ventas":
            df_f = df_f[(df_f["_spend"] > 0) & (df_f["_sales"] == 0)]
            df_f = df_f.sort_values("_spend", ascending=False)
        elif vista == "Top Sales":
            df_f = df_f.sort_values("_sales", ascending=False)
        elif vista == "Top Spend":
            df_f = df_f.sort_values("_spend", ascending=False)

        # ── Estado column ──────────────────────────────────────
        df_f["_estado"] = df_f.apply(lambda r: _classify_status(r, target_acos), axis=1)

        # ── Show table ─────────────────────────────────────────
        st.caption(f"Mostrando {len(df_f)} de {len(df)} filas")

        # Pick display columns
        display_cols = []
        for c in [cols["search_term"], cols["campaign"], cols["match_type"]]:
            if c and c in df_f.columns:
                display_cols.append(c)
        display_cols += ["_imps", "_clicks", "_spend", "_sales", "_orders", "_acos", "_term_type", "_estado"]
        display_cols = [c for c in display_cols if c in df_f.columns]

        def _color_estado(val):
            colors = {
                "Escalar": "background-color:#C6EFCE;color:#276221",
                "OK": "background-color:#E8F5E9;color:#2E7D32",
                "Reducir": "background-color:#FFC7CE;color:#9C0006",
                "Revisar": "background-color:#FFEB9C;color:#9C5700",
                "Negativa?": "background-color:#FFC7CE;color:#9C0006",
            }
            return colors.get(val, "color:#999")

        styled = df_f[display_cols].style.map(_color_estado, subset=["_estado"])
        st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_f), 600))

        # ── Charts ─────────────────────────────────────────────
        st.markdown("---")
        ch1, ch2 = st.columns(2)

        with ch1:
            st.markdown("**Spend vs Sales**")
            if len(df_f) > 0 and df_f["_spend"].sum() > 0:
                hover_col = cols["search_term"] if cols["search_term"] and cols["search_term"] in df_f.columns else None
                fig_scatter = px.scatter(
                    df_f[df_f["_spend"] > 0],
                    x="_spend", y="_sales",
                    color="_term_type",
                    hover_data=[hover_col] if hover_col else None,
                    labels={"_spend": "Spend ($)", "_sales": "Sales ($)", "_term_type": "Tipo"},
                    color_discrete_map={"Brand": "#06b6d4", "Generic": "#6366f1", "Long-tail": "#f59e0b"},
                )
                # Breakeven line
                max_spend = df_f["_spend"].max()
                breakeven_sales = max_spend / (target_acos / 100) if target_acos > 0 else max_spend
                fig_scatter.add_shape(
                    type="line", x0=0, y0=0, x1=max_spend, y1=breakeven_sales,
                    line=dict(color="rgba(255,255,255,0.3)", dash="dash", width=1),
                )
                fig_scatter.update_layout(
                    height=300, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#888",
                )
                st.plotly_chart(fig_scatter, use_container_width=True, key="str_scatter_chart")
            else:
                st.info("Sin datos para el scatter.")

        with ch2:
            st.markdown("**Funnel de Conversion**")
            f_imps = df_f["_imps"].sum()
            f_clicks = df_f["_clicks"].sum()
            f_orders = df_f["_orders"].sum()
            if f_imps > 0:
                pct_ctr = (f_clicks / f_imps * 100) if f_imps > 0 else 0
                pct_cvr = (f_orders / f_clicks * 100) if f_clicks > 0 else 0
                funnel_df = pd.DataFrame({
                    "Etapa": ["Impressions", "Clicks", "Orders"],
                    "Cantidad": [f_imps, f_clicks, f_orders],
                    "Paso": ["", f"{pct_ctr:.2f}% CTR", f"{pct_cvr:.2f}% CVR"],
                })
                fig_funnel = px.bar(
                    funnel_df, y="Etapa", x="Cantidad", orientation="h",
                    text="Paso",
                    color="Etapa",
                    color_discrete_sequence=["#6366f1", "#06b6d4", "#10b981"],
                )
                fig_funnel.update_layout(
                    height=300, margin=dict(l=20, r=20, t=20, b=20),
                    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
                    font_color="#888", showlegend=False,
                    yaxis=dict(autorange="reversed"),
                )
                fig_funnel.update_traces(textposition="inside", textfont_size=11)
                st.plotly_chart(fig_funnel, use_container_width=True, key="str_funnel_chart")
            else:
                st.info("Sin datos para el funnel.")

        # ── Term type distribution table ───────────────────────
        if brand_terms and st_col and st_col in df_f.columns:
            st.markdown("---")
            st.markdown("**Distribucion por tipo de termino**")
            tt_group = df_f.groupby("_term_type").agg(
                Terminos=("_term_type", "count"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index()
            tt_group.rename(columns={"_term_type": "Tipo"}, inplace=True)
            tt_group["ACoS"] = tt_group.apply(
                lambda r: round(r["Spend"] / r["Sales"] * 100, 1) if r["Sales"] > 0 else 0, axis=1
            )
            tt_group["% Spend"] = tt_group.apply(
                lambda r: round(r["Spend"] / total_spend * 100, 1) if total_spend > 0 else 0, axis=1
            )
            tt_group["Spend"] = tt_group["Spend"].apply(lambda x: f"${x:,.2f}")
            tt_group["Sales"] = tt_group["Sales"].apply(lambda x: f"${x:,.2f}")
            st.dataframe(tt_group, use_container_width=True, hide_index=True)

        # ── Download Excel multi-sheet ─────────────────────────
        st.markdown("---")
        from datetime import date
        _today = date.today().isoformat()

        kpi_dict = {
            "Total Spend": f"${total_spend:,.2f}",
            "Total Sales": f"${total_sales:,.2f}",
            "ACoS": f"{acos_val:.1f}%",
            "ROAS": f"{roas_val:.2f}x",
            "Impressions": f"{total_imps:,.0f}",
            "Clicks": f"{total_clicks:,.0f}",
            "CTR": f"{ctr_val:.2f}%",
            "CVR": f"{cvr_val:.2f}%",
            "CPC": f"${cpc_val:.2f}",
            "Orders": f"{total_orders:,.0f}",
            "% Waste": f"{pct_waste:.1f}%",
            "% Con Ventas": f"{pct_conv:.1f}%",
            "Target ACoS": f"{target_acos}%",
            "Fecha": _today,
        }

        try:
            excel_bytes = _build_str_excel(df_f, df, kpi_dict, brand_terms)
        except Exception as e:
            st.warning(f"Error generando Excel: {e}")
            buf_fallback = io.BytesIO()
            df_f.to_excel(buf_fallback, index=False)
            excel_bytes = buf_fallback.getvalue()

        st.download_button(
            "\u2b07\ufe0f Descargar STR Analizado (Excel)",
            data=excel_bytes,
            file_name=f"STR_analizado_{_today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key="str_dl",
        )

    # ══════════════════════════════════════════════════════════════
    # TAB 2: Negatives Mining (SIN CAMBIOS)
    # ══════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("Negatives Mining")
        st.caption("Terminos candidatos a negativizar segun reglas Capybaras 2026")

        nc1, nc2 = st.columns(2)
        with nc1:
            target_acos = st.slider("Target ACoS (%)", 10, 80, 30, key="neg_target_acos")
        with nc2:
            precio_producto = st.number_input(
                "Precio promedio del producto ($)",
                min_value=1.0, value=30.0, step=1.0, key="neg_precio",
            )

        # CVR promedio del STR cargado
        total_clicks = df["_clicks"].sum()
        total_orders = df["_orders"].sum()
        cvr_avg = (total_orders / total_clicks * 100) if total_clicks > 0 else 10.0
        st.info(f"CVR promedio del archivo: **{cvr_avg:.2f}%** — "
                f"Threshold dinamico Regla 2: **{max(10, round((1 / (cvr_avg / 100)) * 2))} clicks**")

        # Thresholds
        clicks_threshold = max(10, round((1 / (cvr_avg / 100)) * 2))
        spend_threshold = precio_producto * 0.50

        st_col = cols["search_term"]
        if not st_col:
            st.warning("No se encontro columna 'Customer Search Term' en el archivo.")
        else:
            candidates = []
            for idx, row in df.iterrows():
                term = str(row[st_col]).strip() if st_col else ""
                clicks = row["_clicks"]
                orders = row["_orders"]
                spend = row["_spend"]
                imps = row["_imps"]
                acos_r = row["_acos"]
                ctr_r = row["_ctr"]
                campaign = str(row[cols["campaign"]]).strip() if cols["campaign"] and pd.notna(row.get(cols["campaign"])) else ""

                matched_rules = []

                # Regla 2 — No conversion por CVR (threshold dinamico)
                if clicks >= clicks_threshold and orders == 0:
                    matched_rules.append(("R2 — Sin conversion (CVR)", "negativeExact", "Alta"))

                # Regla 3 — Gasto sin conversion
                if spend >= spend_threshold and orders == 0:
                    matched_rules.append(("R3 — Gasto sin conversion", "negativeExact", "Alta"))

                # Regla 5 — CTR bajo por irrelevancia
                if imps >= 2500 and ctr_r < 0.18 and orders == 0:
                    matched_rules.append(("R5 — CTR bajo + irrelevancia", "negativePhrase", "Media"))

                # Regla 4 — ACoS extremo (ya con ventas)
                if acos_r > 70 and 0 < orders < 5:
                    matched_rules.append(("R4 — ACoS extremo", "negativeExact", "Media"))

                # Regla 1 — Irrelevancia obvia (pocos clicks, 0 orders)
                if clicks >= 1 and orders == 0 and not matched_rules:
                    matched_rules.append(("R1 — Revisar manualmente", "negativeExact", "Revisar"))

                if matched_rules:
                    # Use highest priority rule
                    rule, match_type, priority = matched_rules[0]
                    candidates.append({
                        "Search Term": term,
                        "Campaign": campaign,
                        "Clicks": int(clicks),
                        "Impressions": int(imps),
                        "Spend": round(spend, 2),
                        "Orders": int(orders),
                        "ACoS": round(acos_r, 1) if orders > 0 else 0,
                        "Regla": rule,
                        "Match Type": match_type,
                        "Prioridad": priority,
                    })

            if candidates:
                df_neg = pd.DataFrame(candidates)
                prio_order = {"Alta": 0, "Media": 1, "Revisar": 2}
                df_neg["_sort"] = df_neg["Prioridad"].map(prio_order)
                df_neg = df_neg.sort_values(["_sort", "Spend"], ascending=[True, False]).drop(columns=["_sort"])

                n_alta   = (df_neg["Prioridad"] == "Alta").sum()
                n_media  = (df_neg["Prioridad"] == "Media").sum()
                n_review = (df_neg["Prioridad"] == "Revisar").sum()

                mc1, mc2, mc3, mc4 = st.columns(4)
                mc1.metric("Total candidatos", len(df_neg))
                mc2.metric("Alta", n_alta)
                mc3.metric("Media", n_media)
                mc4.metric("Revisar", n_review)

                prio_filter = st.multiselect(
                    "Filtrar por prioridad", ["Alta", "Media", "Revisar"],
                    default=["Alta", "Media"], key="neg_prio_filter",
                )
                df_show = df_neg[df_neg["Prioridad"].isin(prio_filter)] if prio_filter else df_neg

                def _color_prio(val):
                    if val == "Alta": return "background-color: #FFC7CE; color: #9C0006"
                    if val == "Media": return "background-color: #FFEB9C; color: #9C5700"
                    return "background-color: #F5F5F5; color: #666"

                st.dataframe(
                    df_show.style.map(_color_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_show), 800),
                )

                # Export bulk-ready formato Amazon
                st.markdown("---")
                st.markdown("**Export bulk-ready para Amazon**")
                st.caption("Columnas en formato Amazon Bulk. Campaign Name y Ad Group Name vacios — el AM los completa.")
                df_export = df_show.copy()
                if not df_export.empty:
                    df_bulk = pd.DataFrame({
                        "Product": "",
                        "Entity": "Negative keyword",
                        "Operation": "Create",
                        "Campaign Name": "",
                        "Ad Group Name": "",
                        "Customer Search Term": df_export["Search Term"].values,
                        "Match Type": df_export["Match Type"].values,
                        "Prioridad": df_export["Prioridad"].values,
                    })
                    st.dataframe(df_bulk, use_container_width=True)
                    buf = io.BytesIO()
                    df_bulk.to_excel(buf, index=False)
                    st.download_button(
                        "Descargar negativos bulk (.xlsx)",
                        data=buf.getvalue(),
                        file_name="negatives_bulk.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key="neg_dl",
                    )
                else:
                    st.info("No hay candidatos visibles para exportar.")
            else:
                st.success("No se encontraron candidatos a negativizar con las reglas actuales.")

    # ══════════════════════════════════════════════════════════════
    # TAB 3: Harvest Candidates (SIN CAMBIOS)
    # ══════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("Harvest Candidates")
        st.caption("Terminos listos para harvestear a Exact Match segun reglas Capybaras 2026")

        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            harv_target_acos = st.slider("Target ACoS (%)", 10, 80, 30, key="harv_target_acos")
        with hc2:
            harv_precio = st.number_input("Precio promedio ($)", min_value=1.0, value=30.0, step=1.0, key="harv_precio")
        with hc3:
            harv_min_clicks = st.number_input("Clicks minimos para CVR", min_value=5, value=15, step=1, key="harv_min_clicks")

        # ── Anti-canibalizacion: Campaign CSV opcional ────────────
        st.markdown("---")
        st.markdown("**Anti-canibalizacion** (opcional)")
        st.caption("Subi el Campaign CSV o Bulk para detectar keywords que ya estan en Exact activo.")
        file_camp_harv = st.file_uploader(
            "Campaign CSV / Bulk (.xlsx o .csv)",
            type=["xlsx", "csv"],
            key="harv_anti_canib",
        )

        existing_exact_kws = set()
        if file_camp_harv:
            try:
                df_camp_h = pd.read_excel(file_camp_harv) if file_camp_harv.name.endswith(".xlsx") else pd.read_csv(file_camp_harv)
                # Detectar columnas
                kw_col_h = next((c for c in df_camp_h.columns if "keyword" in c.lower() and "text" in c.lower()), None)
                if not kw_col_h:
                    kw_col_h = next((c for c in df_camp_h.columns if "keyword" in c.lower() or "targeting" in c.lower()), None)
                mt_col_h = next((c for c in df_camp_h.columns if "match type" in c.lower()), None)
                st_col_h = next((c for c in df_camp_h.columns if c.lower() == "state" or c.lower() == "status"), None)

                if kw_col_h:
                    df_kw = df_camp_h.copy()
                    # Filtrar solo Exact + Enabled
                    if mt_col_h:
                        df_kw = df_kw[df_kw[mt_col_h].astype(str).str.lower().str.strip().isin(["exact", "exact match"])]
                    if st_col_h:
                        df_kw = df_kw[df_kw[st_col_h].astype(str).str.lower().str.strip().isin(["enabled", "active"])]
                    existing_exact_kws = set(df_kw[kw_col_h].dropna().astype(str).str.lower().str.strip())
                    st.success(f"{len(existing_exact_kws)} keywords Exact activas detectadas")
                else:
                    st.warning("No se encontro columna de keywords en el archivo.")
            except Exception as e:
                st.warning(f"Error leyendo Campaign CSV: {e}")

        st.markdown("---")

        st_col = cols["search_term"]
        if not st_col:
            st.warning("No se encontro columna 'Customer Search Term' en el archivo.")
        else:
            harvests = []
            for _, row in df.iterrows():
                term = str(row[st_col]).strip()
                clicks = row["_clicks"]
                orders = row["_orders"]
                spend = row["_spend"]
                sales = row["_sales"]

                if orders == 0 or clicks == 0:
                    continue

                cvr_row = orders / clicks * 100
                acos_row = (spend / sales * 100) if sales > 0 else 999
                campaign = str(row[cols["campaign"]]).strip() if cols["campaign"] and pd.notna(row.get(cols["campaign"])) else ""

                matched = []
                best_prio = None

                # Regla 1 — Principal (SOP Capybaras)
                if orders >= 3 and acos_row <= 25.0:
                    matched.append("Regla principal")
                    best_prio = "Alta"

                # Regla 2 — CVR alto
                if cvr_row >= 10.0 and clicks >= harv_min_clicks and orders >= 1:
                    matched.append("CVR alto")
                    best_prio = best_prio or "Alta"

                # Regla 3 — Volumen (ranking benefit)
                if orders >= 5:
                    matched.append("Volumen")
                    if not best_prio:
                        best_prio = "Media"

                if matched:
                    bid = max(0.10, round((cvr_row / 100) * harv_precio * (harv_target_acos / 100), 2))
                    harvests.append({
                        "Search Term": term,
                        "Campaign": campaign,
                        "Clicks": int(clicks),
                        "Orders": int(orders),
                        "ACoS": round(acos_row, 1),
                        "CVR%": round(cvr_row, 1),
                        "Bid Sugerido": bid,
                        "Regla": " + ".join(matched),
                        "Prioridad": best_prio,
                    })

            if harvests:
                df_harv = pd.DataFrame(harvests)
                prio_order = {"Alta": 0, "Media": 1}
                df_harv["_sort"] = df_harv["Prioridad"].map(prio_order)
                df_harv = df_harv.sort_values(["_sort", "Orders"], ascending=[True, False]).drop(columns=["_sort"])

                # ── Anti-canibalizacion: marcar duplicados ────────────
                if existing_exact_kws:
                    df_harv["Ya en Exact"] = df_harv["Search Term"].str.lower().str.strip().isin(existing_exact_kws).map(
                        {True: "Ya en Exact activo", False: ""}
                    )
                    n_dupes = (df_harv["Ya en Exact"] != "").sum()
                    n_nuevos = len(df_harv) - n_dupes
                else:
                    df_harv["Ya en Exact"] = ""
                    n_dupes = 0
                    n_nuevos = len(df_harv)

                n_alta  = (df_harv["Prioridad"] == "Alta").sum()
                n_media = (df_harv["Prioridad"] == "Media").sum()
                avg_bid = df_harv["Bid Sugerido"].mean()

                if existing_exact_kws:
                    hm1, hm2, hm3, hm4, hm5 = st.columns(5)
                    hm1.metric("Total candidatos", len(df_harv))
                    hm2.metric("Alta", n_alta)
                    hm3.metric("Media", n_media)
                    hm4.metric("Bid promedio", f"${avg_bid:.2f}")
                    hm5.metric("Ya en Exact", n_dupes)
                else:
                    hm1, hm2, hm3, hm4 = st.columns(4)
                    hm1.metric("Total candidatos", len(df_harv))
                    hm2.metric("Alta", n_alta)
                    hm3.metric("Media", n_media)
                    hm4.metric("Bid promedio", f"${avg_bid:.2f}")

                def _color_harv_prio(val):
                    if val == "Alta": return "background-color: #C6EFCE; color: #276221"
                    return "background-color: #DBEAFE; color: #1E3A8A"

                def _color_exact_dup(val):
                    if val and "Ya en Exact" in str(val): return "background-color: #FFF3E0; color: #BF360C"
                    return ""

                style_cols = ["Prioridad"]
                styled_harv = df_harv.style.map(_color_harv_prio, subset=["Prioridad"])
                if existing_exact_kws:
                    styled_harv = styled_harv.map(_color_exact_dup, subset=["Ya en Exact"])

                st.dataframe(
                    styled_harv,
                    use_container_width=True,
                    height=min(38 + 35 * len(df_harv), 800),
                )

                # Export bulk-ready formato Amazon
                st.markdown("---")
                st.markdown("**Export bulk-ready para Amazon — Exact Match**")

                # Checkbox para incluir/excluir duplicados
                if existing_exact_kws and n_dupes > 0:
                    incluir_dupes = st.checkbox(
                        f"Incluir {n_dupes} keywords que ya estan en Exact activo",
                        value=False,
                        key="harv_include_dupes",
                    )
                    df_harv_export = df_harv if incluir_dupes else df_harv[df_harv["Ya en Exact"] == ""]
                    if not incluir_dupes:
                        st.caption(f"Exportando {len(df_harv_export)} keywords nuevas (excluidas {n_dupes} que ya estan en Exact).")
                    else:
                        st.caption("Exportando TODAS las keywords incluyendo las que ya estan en Exact.")
                else:
                    df_harv_export = df_harv
                    st.caption("Campaign Name y Ad Group Name vacios — el AM los completa antes de subir.")

                df_hbulk = pd.DataFrame({
                    "Product": "",
                    "Entity": "Keyword",
                    "Operation": "Create",
                    "Campaign Name": "",
                    "Ad Group Name": "",
                    "Keyword": df_harv_export["Search Term"].values,
                    "Match Type": "exact",
                    "Max Bid": df_harv_export["Bid Sugerido"].values,
                })
                st.dataframe(df_hbulk, use_container_width=True)
                buf_h = io.BytesIO()
                df_hbulk.to_excel(buf_h, index=False)
                st.download_button(
                    "Descargar Harvest Bulk (formato Amazon)",
                    data=buf_h.getvalue(),
                    file_name="harvest_exact_bulk.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="harv_dl",
                )
            else:
                st.info("No se encontraron candidatos de harvest con los criterios actuales.")

    # ══════════════════════════════════════════════════════════════
    # TAB 4: Analisis IA (SIN CAMBIOS)
    # ══════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("Analisis IA — PPC Senior")
        st.caption("Analisis ejecutivo generado por Claude basado en los candidatos detectados")

        client_name_str = st.text_input(
            "Nombre del cliente",
            placeholder="Ej: Love To Dream MX",
            key="str_client_ai",
        )

        ai_c1, ai_c2 = st.columns(2)
        with ai_c1:
            str_target_acos = st.slider("Target ACoS (%)", 10, 80, 30, key="str_ai_acos")
        with ai_c2:
            str_precio = st.number_input("Precio promedio ($)", min_value=1.0, value=30.0, step=1.0, key="str_ai_precio")

        if st.button("Generar analisis", key="btn_str_ai", use_container_width=True):
            if not client_name_str:
                st.warning("Ingresa el nombre del cliente primero.")
            else:
                with st.spinner("Analizando con Claude..."):
                    from core.ai_analyze import _claude_analyze, _build_str_prompt

                    # CVR promedio del STR
                    t_clicks = df["_clicks"].sum()
                    t_orders = df["_orders"].sum()
                    cvr_val = (t_orders / t_clicks * 100) if t_clicks > 0 else 10.0

                    prompt = _build_str_prompt(
                        df_neg, df_harv,
                        client_name_str, cvr_val, str_target_acos,
                    )
                    analisis = _claude_analyze(prompt)

                st.markdown("---")
                st.markdown(analisis)
                st.markdown("---")

                col_dl_a, col_dl_b = st.columns(2)
                with col_dl_a:
                    st.download_button(
                        "Descargar analisis (.txt)",
                        data=analisis,
                        file_name=f"analisis_str_{client_name_str.replace(' ', '_')}.txt",
                        mime="text/plain",
                        use_container_width=True, key="dl_str_ai",
                    )
                with col_dl_b:
                    st.code(analisis, language=None)

    # ══════════════════════════════════════════════════════════════
    # TAB 5: Por Campana (NUEVO)
    # ══════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("Performance por Campana")
        st.caption("Metricas agregadas desde el STR por campana. Clasificacion Brand/No Brand automatica.")

        camp_col = cols["campaign"]
        if not camp_col or camp_col not in df.columns:
            st.warning("No se encontro columna de campana en el archivo.")
        else:
            # ── Aggregate by campaign ──────────────────────────
            df_camp = df.groupby(camp_col).agg(
                Impressions=("_imps", "sum"),
                Clicks=("_clicks", "sum"),
                Spend=("_spend", "sum"),
                Sales=("_sales", "sum"),
                Orders=("_orders", "sum"),
            ).reset_index()

            df_camp.rename(columns={camp_col: "Campaign"}, inplace=True)
            df_camp["ACoS"] = df_camp.apply(
                lambda r: round(r["Spend"] / r["Sales"] * 100, 1) if r["Sales"] > 0 else 0, axis=1
            )
            df_camp["ROAS"] = df_camp.apply(
                lambda r: round(r["Sales"] / r["Spend"], 2) if r["Spend"] > 0 else 0, axis=1
            )
            df_camp["CTR"] = df_camp.apply(
                lambda r: round(r["Clicks"] / r["Impressions"] * 100, 2) if r["Impressions"] > 0 else 0, axis=1
            )
            df_camp["CVR"] = df_camp.apply(
                lambda r: round(r["Orders"] / r["Clicks"] * 100, 2) if r["Clicks"] > 0 else 0, axis=1
            )
            df_camp["CPC"] = df_camp.apply(
                lambda r: round(r["Spend"] / r["Clicks"], 2) if r["Clicks"] > 0 else 0, axis=1
            )
            df_camp["Tipo"] = df_camp["Campaign"].apply(
                lambda n: "Brand" if _is_brand_campaign(n) else "No Brand"
            )
            df_camp = df_camp.sort_values("Sales", ascending=False)

            # ── KPIs ──────────────────────────────────────────
            total_camps = len(df_camp)
            brand_camps = (df_camp["Tipo"] == "Brand").sum()
            nobrand_camps = total_camps - brand_camps
            top_spend_camp = df_camp.loc[df_camp["Spend"].idxmax(), "Campaign"] if len(df_camp) > 0 else "—"
            # Truncate long name
            top_spend_display = top_spend_camp[:35] + "..." if len(top_spend_camp) > 35 else top_spend_camp

            kc1, kc2, kc3, kc4 = st.columns(4)
            with kc1:
                st.markdown(kpi_card("Total Campanas", str(total_camps)), unsafe_allow_html=True)
            with kc2:
                st.markdown(kpi_card("Brand", str(brand_camps)), unsafe_allow_html=True)
            with kc3:
                st.markdown(kpi_card("No Brand", str(nobrand_camps)), unsafe_allow_html=True)
            with kc4:
                st.markdown(kpi_card("Mayor Spend", top_spend_display), unsafe_allow_html=True)

            st.markdown("")

            # ── Table with color coding ───────────────────────
            def _color_acos_camp(val):
                try:
                    v = float(val)
                    if v == 0:
                        return "color:#999"
                    if v <= 30:
                        return "background-color:#C6EFCE;color:#276221"
                    if v <= 55:
                        return "background-color:#FFEB9C;color:#9C5700"
                    return "background-color:#FFC7CE;color:#9C0006"
                except (ValueError, TypeError):
                    return ""

            def _color_brand_tipo(val):
                if val == "Brand":
                    return "background-color:#E0F7FA;color:#006064"
                return "background-color:#F5F5F5;color:#616161"

            display_camp_cols = ["Campaign", "Tipo", "Impressions", "Clicks", "Spend", "Sales",
                                 "Orders", "ACoS", "ROAS", "CTR", "CVR", "CPC"]

            styled_camp = df_camp[display_camp_cols].style\
                .map(_color_acos_camp, subset=["ACoS"])\
                .map(_color_brand_tipo, subset=["Tipo"])\
                .format({"Spend": "${:,.2f}", "Sales": "${:,.2f}", "CPC": "${:,.2f}",
                         "ACoS": "{:.1f}%", "CTR": "{:.2f}%", "CVR": "{:.2f}%", "ROAS": "{:.2f}x",
                         "Impressions": "{:,.0f}", "Clicks": "{:,.0f}", "Orders": "{:,.0f}"})

            st.dataframe(styled_camp, use_container_width=True, height=min(38 + 35 * len(df_camp), 600), hide_index=True)

            # ── Term type distribution by campaign ────────────
            st_col = cols["search_term"]
            if brand_terms and st_col and st_col in df.columns:
                st.markdown("---")
                st.markdown("**Distribucion Brand/Generic/Long-tail por campana**")

                df["_term_type_camp"] = df[st_col].apply(lambda t: _classify_term_type(t, brand_terms))
                tt_camp = df.groupby([camp_col, "_term_type_camp"]).agg(
                    Spend=("_spend", "sum"),
                ).reset_index()
                tt_pivot = tt_camp.pivot_table(
                    index=camp_col, columns="_term_type_camp", values="Spend", fill_value=0
                ).reset_index()
                tt_pivot.rename(columns={camp_col: "Campaign"}, inplace=True)

                # Add % columns
                for col_name in ["Brand", "Generic", "Long-tail"]:
                    if col_name not in tt_pivot.columns:
                        tt_pivot[col_name] = 0.0

                tt_pivot["Total"] = tt_pivot["Brand"] + tt_pivot["Generic"] + tt_pivot["Long-tail"]
                tt_pivot["% Brand"] = tt_pivot.apply(
                    lambda r: round(r["Brand"] / r["Total"] * 100, 1) if r["Total"] > 0 else 0, axis=1
                )
                tt_pivot = tt_pivot.sort_values("Total", ascending=False)

                show_cols = ["Campaign", "Brand", "Generic", "Long-tail", "Total", "% Brand"]
                st.dataframe(
                    tt_pivot[show_cols].style.format({
                        "Brand": "${:,.2f}", "Generic": "${:,.2f}",
                        "Long-tail": "${:,.2f}", "Total": "${:,.2f}", "% Brand": "{:.1f}%"
                    }),
                    use_container_width=True, hide_index=True,
                )

            # ── Download ──────────────────────────────────────
            st.markdown("---")
            from datetime import date as _date
            camp_today = _date.today().strftime("%Y-%m-%d")
            buf_camp = io.BytesIO()
            df_camp.to_excel(buf_camp, index=False)
            st.download_button(
                "Descargar Performance por Campana (Excel)",
                data=buf_camp.getvalue(),
                file_name=f"STR_por_campana_{camp_today}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True, key="str_camp_dl",
            )
