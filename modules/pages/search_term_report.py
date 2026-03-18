import io

import streamlit as st
import pandas as pd


def _detect_cols(df):
    """Auto-detect STR column names, return dict of canonical → actual column name."""
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
    }


def _to_num(df, col):
    if col and col in df.columns:
        return pd.to_numeric(df[col].astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""), errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


def render():
    st.header("📊 Search Term Report")
    st.caption("Análisis de términos de búsqueda con métricas de ACoS, gasto y ventas totales.")
    st.divider()
    file_str = st.file_uploader("Sube tu STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str")
    if not file_str:
        return

    df = pd.read_excel(file_str) if file_str.name.endswith(".xlsx") else pd.read_csv(file_str)
    st.success(f"✅ {len(df)} filas cargadas")

    cols = _detect_cols(df)

    # Numeric columns
    df["_spend"]  = _to_num(df, cols["spend"])
    df["_sales"]  = _to_num(df, cols["sales"])
    df["_orders"] = _to_num(df, cols["orders"])
    df["_clicks"] = _to_num(df, cols["clicks"])
    df["_imps"]   = _to_num(df, cols["impressions"])
    df["_acos"]   = _to_num(df, cols["acos"])
    df["_ctr"]    = _to_num(df, cols["ctr"])

    # Pre-init for tab4 (IA) scope
    df_neg = pd.DataFrame()
    df_harv = pd.DataFrame()

    tab1, tab2, tab3, tab4 = st.tabs(["📊 Vista General", "🔴 Negatives Mining", "🟢 Harvest Candidates", "🤖 Análisis IA"])

    # ── TAB 1: Vista General (código original) ──────────────────────
    with tab1:
        c1, c2, c3, c4 = st.columns(4)
        total_spend = df["_spend"].sum()
        total_sales = df["_sales"].sum()
        acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
        c1.metric("Total Spend", f"${total_spend:,.2f}")
        c2.metric("Total Sales", f"${total_sales:,.2f}")
        c3.metric("ACoS", f"{acos:.1f}%")
        c4.metric("Términos únicos", df.shape[0])
        st.dataframe(df, use_container_width=True)

        buf_str = io.BytesIO()
        df.to_excel(buf_str, index=False)
        st.download_button(
            "⬇️ Descargar STR completo (Excel)",
            data=buf_str.getvalue(),
            file_name="search_term_report.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True, key="str_dl",
        )

    # ── TAB 2: Negatives Mining ─────────────────────────────────────
    with tab2:
        st.subheader("🔴 Negatives Mining")
        st.caption("Términos candidatos a negativizar según reglas Capybaras 2026")

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
                f"Threshold dinámico Regla 2: **{max(10, round((1 / (cvr_avg / 100)) * 2))} clicks**")

        # Thresholds
        clicks_threshold = max(10, round((1 / (cvr_avg / 100)) * 2))
        spend_threshold = precio_producto * 0.50

        st_col = cols["search_term"]
        if not st_col:
            st.warning("No se encontró columna 'Customer Search Term' en el archivo.")
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

                # Regla 2 — No conversión por CVR (threshold dinámico)
                if clicks >= clicks_threshold and orders == 0:
                    matched_rules.append(("R2 — Sin conversión (CVR)", "negativeExact", "Alta"))

                # Regla 3 — Gasto sin conversión
                if spend >= spend_threshold and orders == 0:
                    matched_rules.append(("R3 — Gasto sin conversión", "negativeExact", "Alta"))

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
                mc2.metric("🔴 Alta", n_alta)
                mc3.metric("🟡 Media", n_media)
                mc4.metric("⚪ Revisar", n_review)

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
                    df_show.style.applymap(_color_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_show), 800),
                )

                # Export bulk-ready formato Amazon
                st.markdown("---")
                st.markdown("**📦 Export bulk-ready para Amazon**")
                st.caption("Columnas en formato Amazon Bulk. Campaign Name y Ad Group Name vacíos — el AM los completa.")
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
                        "⬇️ Descargar negativos bulk (.xlsx)",
                        data=buf.getvalue(),
                        file_name="negatives_bulk.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True, key="neg_dl",
                    )
                else:
                    st.info("No hay candidatos visibles para exportar.")
            else:
                st.success("✅ No se encontraron candidatos a negativizar con las reglas actuales.")

    # ── TAB 3: Harvest Candidates ─────────────────────────────────────
    with tab3:
        st.subheader("🟢 Harvest Candidates")
        st.caption("Términos listos para harvestear a Exact Match según reglas Capybaras 2026")

        hc1, hc2, hc3 = st.columns(3)
        with hc1:
            harv_target_acos = st.slider("Target ACoS (%)", 10, 80, 30, key="harv_target_acos")
        with hc2:
            harv_precio = st.number_input("Precio promedio ($)", min_value=1.0, value=30.0, step=1.0, key="harv_precio")
        with hc3:
            harv_min_clicks = st.number_input("Clicks mínimos para CVR", min_value=5, value=15, step=1, key="harv_min_clicks")

        st_col = cols["search_term"]
        if not st_col:
            st.warning("No se encontró columna 'Customer Search Term' en el archivo.")
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

                n_alta  = (df_harv["Prioridad"] == "Alta").sum()
                n_media = (df_harv["Prioridad"] == "Media").sum()
                avg_bid = df_harv["Bid Sugerido"].mean()

                hm1, hm2, hm3, hm4 = st.columns(4)
                hm1.metric("Total candidatos", len(df_harv))
                hm2.metric("🟢 Alta", n_alta)
                hm3.metric("🔵 Media", n_media)
                hm4.metric("Bid promedio", f"${avg_bid:.2f}")

                def _color_harv_prio(val):
                    if val == "Alta": return "background-color: #C6EFCE; color: #276221"
                    return "background-color: #DBEAFE; color: #1E3A8A"

                st.dataframe(
                    df_harv.style.applymap(_color_harv_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_harv), 800),
                )

                # Export bulk-ready formato Amazon
                st.markdown("---")
                st.markdown("**📦 Export bulk-ready para Amazon — Exact Match**")
                st.caption("Campaign Name y Ad Group Name vacíos — el AM los completa antes de subir.")
                df_hbulk = pd.DataFrame({
                    "Product": "",
                    "Entity": "Keyword",
                    "Operation": "Create",
                    "Campaign Name": "",
                    "Ad Group Name": "",
                    "Keyword": df_harv["Search Term"].values,
                    "Match Type": "exact",
                    "Max Bid": df_harv["Bid Sugerido"].values,
                })
                st.dataframe(df_hbulk, use_container_width=True)
                buf_h = io.BytesIO()
                df_hbulk.to_excel(buf_h, index=False)
                st.download_button(
                    "⬇️ Descargar Harvest Bulk (formato Amazon)",
                    data=buf_h.getvalue(),
                    file_name="harvest_exact_bulk.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="harv_dl",
                )
            else:
                st.info("No se encontraron candidatos de harvest con los criterios actuales.")

    # ── TAB 4: Análisis IA ─────────────────────────────────────────
    with tab4:
        st.subheader("🤖 Análisis IA — PPC Senior")
        st.caption("Análisis ejecutivo generado por Claude basado en los candidatos detectados")

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

        if st.button("🤖 Generar análisis", key="btn_str_ai", use_container_width=True):
            if not client_name_str:
                st.warning("Ingresá el nombre del cliente primero.")
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
                        "⬇️ Descargar análisis (.txt)",
                        data=analisis,
                        file_name=f"analisis_str_{client_name_str.replace(' ', '_')}.txt",
                        mime="text/plain",
                        use_container_width=True, key="dl_str_ai",
                    )
                with col_dl_b:
                    st.code(analisis, language=None)
