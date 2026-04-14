import io

import streamlit as st
import pandas as pd

from core.helpers import read_sqp, extract_sqp_brand


def _find_col(df, must_contain, must_not_contain=None):
    """Find first column matching all keywords in must_contain, excluding must_not_contain."""
    for c in df.columns:
        cl = c.lower()
        if all(k in cl for k in must_contain):
            if must_not_contain and any(k in cl for k in must_not_contain):
                continue
            return c
    return None


def _to_num(df, col):
    if col and col in df.columns:
        return pd.to_numeric(
            df[col].astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


def _compute_market_share(df, query_col, precio):
    """Compute market share DataFrame from SQP data. Returns df_ms or None."""
    global_brand_clicks = df["_clk_b"].sum()
    global_brand_purch  = df["_pur_b"].sum()
    global_cvr = (global_brand_purch / global_brand_clicks) if global_brand_clicks > 0 else 0

    rows_ms = []
    for _, row in df.iterrows():
        query = str(row[query_col]).strip()
        imp_t = row["_imp_t"]; imp_b = row["_imp_b"]
        clk_t = row["_clk_t"]; clk_b = row["_clk_b"]
        pur_t = row["_pur_t"]; pur_b = row["_pur_b"]

        if imp_t == 0:
            continue

        is_pct = (imp_b / imp_t * 100) if imp_t > 0 else 0
        cs_pct = (clk_b / clk_t * 100) if clk_t > 0 else 0
        ps_pct = (pur_b / pur_t * 100) if pur_t > 0 else 0

        ctr_own = (clk_b / imp_t) if imp_t > 0 else 0
        cvr_own = (pur_b / clk_b) if clk_b > 0 else global_cvr
        rev_pot = imp_t * ctr_own * cvr_own * precio

        if is_pct > 30:
            estado = "🟢 Dominando"
        elif is_pct >= 10:
            estado = "🟡 Competitivo"
        else:
            estado = "🔴 Oportunidad"

        rows_ms.append({
            "Search Query": query,
            "Total Impressions": int(imp_t),
            "Impression Share %": round(is_pct, 1),
            "Click Share %": round(cs_pct, 1),
            "Purchase Share %": round(ps_pct, 1),
            "Revenue Potencial": round(rev_pot, 2),
            "Estado": estado,
        })

    if not rows_ms:
        return None
    return pd.DataFrame(rows_ms).sort_values("Revenue Potencial", ascending=False)


def _compute_gaps(df, query_col):
    """Compute gap analysis DataFrame from SQP data. Returns df_gap or None."""
    gaps = []
    for _, row in df.iterrows():
        query = str(row[query_col]).strip()
        imp_t = row["_imp_t"]; imp_b = row["_imp_b"]
        clk_b = row["_clk_b"]
        pur_t = row["_pur_t"]; pur_b = row["_pur_b"]

        is_pct     = (imp_b / imp_t * 100) if imp_t > 0 else 0
        market_cvr = (pur_t / imp_t * 100)  if imp_t > 0 else 0
        brand_cvr  = (pur_b / imp_b * 100)  if imp_b > 0 else 0

        matched = []

        # GAP 1 — No aparecés
        if imp_t > 1000 and imp_b == 0:
            matched.append(("🚫 No aparecés — agregar como keyword", "Alta"))

        # GAP 2 — Mercado convierte mejor
        if imp_b > 0 and market_cvr > 0 and brand_cvr > 0:
            if market_cvr > brand_cvr * 1.5:
                matched.append(("⚠️ Mercado convierte mejor — revisar listing o bid", "Media"))

        # GAP 3 — IS muy bajo en query con volumen
        if is_pct < 5 and imp_t > 2000 and imp_b > 0:
            matched.append(("📉 IS muy bajo — escalar bid", "Media"))

        if matched:
            best = min(matched, key=lambda x: 0 if x[1] == "Alta" else 1)
            all_labels = " | ".join(m[0] for m in matched)
            gaps.append({
                "Search Query": query,
                "Total Impressions": int(imp_t),
                "Brand IS%": round(is_pct, 1),
                "Market CVR%": round(market_cvr, 2),
                "Brand CVR%": round(brand_cvr, 2),
                "Tipo de Gap": all_labels,
                "Prioridad": best[1],
                "Acción sugerida": best[0],
            })

    if not gaps:
        return None
    df_gap = pd.DataFrame(gaps)
    prio_order = {"Alta": 0, "Media": 1}
    df_gap["_sort"] = df_gap["Prioridad"].map(prio_order)
    return df_gap.sort_values(["_sort", "Total Impressions"], ascending=[True, False]).drop(columns=["_sort"])


def render():
    st.header("🔍 Search Query Performance")
    st.caption("Datos de rendimiento de búsqueda orgánica exportados desde Amazon Brand Analytics.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Medir market share, detectar gaps y oportunidades orgánicas contra el mercado de Brand Analytics.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("SQP → Brand Analytics → Search Query Performance (.xlsx semanal).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Análisis Cruzado STR vs SQP (M4) para generar Plan de Acción.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el SQP\n"
            "2. Confirmá o ingresá la marca detectada\n"
            "3. Revisá Dashboard, Market Share (Dominando/Competitivo/Oportunidad)\n"
            "4. En Gap Analysis detectá queries con alto volumen donde no aparecés\n"
            "5. Descargá tabla de gaps"
        )

    file_sqp = st.file_uploader("Sube tu SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp")
    if not file_sqp:
        return

    df = read_sqp(file_sqp)
    file_sqp.seek(0)
    brand = extract_sqp_brand(file_sqp)
    st.success(f"✅ {len(df)} filas cargadas" + (f" · Marca: **{brand}**" if brand else ""))

    # Auto-detect columns
    query_col    = _find_col(df, ["search query"], ["score", "volume"])
    imp_total    = _find_col(df, ["impression", "total"])
    imp_brand    = _find_col(df, ["impression", "brand"])
    click_total  = _find_col(df, ["click", "total"], ["rate"])
    click_brand  = _find_col(df, ["click", "brand"], ["rate"])
    purch_total  = _find_col(df, ["purchase", "total"], ["rate"])
    purch_brand  = _find_col(df, ["purchase", "brand"], ["rate"])

    # Numeric series
    df["_imp_t"]   = _to_num(df, imp_total)
    df["_imp_b"]   = _to_num(df, imp_brand)
    df["_clk_t"]   = _to_num(df, click_total)
    df["_clk_b"]   = _to_num(df, click_brand)
    df["_pur_t"]   = _to_num(df, purch_total)
    df["_pur_b"]   = _to_num(df, purch_brand)

    # Pre-compute data for tabs 2, 3 and 4
    has_cols = bool(imp_total and imp_brand and query_col)
    df_ms  = None
    df_gap = None

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Vista General", "📈 Market Share", "🕳️ Gap Analysis", "🤖 Análisis IA",
    ])

    # ── TAB 1: Vista General (código original) ──────────────────────
    with tab1:
        st.dataframe(df, use_container_width=True)

    # ── TAB 2: Market Share ─────────────────────────────────────────
    with tab2:
        st.subheader("📈 Market Share")
        st.caption("Tu share of voice vs el mercado total por search query")

        if not has_cols:
            st.warning("No se encontraron columnas de Impressions Total/Brand o Search Query en el archivo SQP.")
        else:
            precio_sqp = st.number_input("Precio promedio ($)", min_value=1.0, value=30.0, step=1.0, key="sqp_precio")
            df_ms = _compute_market_share(df, query_col, precio_sqp)

            if df_ms is not None:
                n_dom  = (df_ms["Estado"] == "🟢 Dominando").sum()
                n_comp = (df_ms["Estado"] == "🟡 Competitivo").sum()
                n_opp  = (df_ms["Estado"] == "🔴 Oportunidad").sum()
                avg_is = df_ms["Impression Share %"].mean()

                sm1, sm2, sm3, sm4 = st.columns(4)
                sm1.metric("🟢 Dominando", n_dom)
                sm2.metric("🟡 Competitivo", n_comp)
                sm3.metric("🔴 Oportunidad", n_opp)
                sm4.metric("IS promedio", f"{avg_is:.1f}%")

                def _color_estado(val):
                    if "Dominando" in str(val):   return "background-color: #C6EFCE; color: #276221"
                    if "Competitivo" in str(val):  return "background-color: #FFEB9C; color: #9C5700"
                    if "Oportunidad" in str(val):  return "background-color: #FFC7CE; color: #9C0006"
                    return ""

                st.dataframe(
                    df_ms.style.applymap(_color_estado, subset=["Estado"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_ms), 800),
                )

                buf_ms = io.BytesIO()
                df_ms.to_excel(buf_ms, index=False)
                st.download_button(
                    "⬇️ Descargar Market Share (Excel)",
                    data=buf_ms.getvalue(),
                    file_name="sqp_market_share.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="ms_dl",
                )
            else:
                st.info("No hay datos de impresiones para calcular market share.")

    # ── TAB 3: Gap Analysis ─────────────────────────────────────────
    with tab3:
        st.subheader("🕳️ Gap Analysis")
        st.caption("Queries donde el mercado convierte bien pero vos no aparecés o rendís por debajo")

        if not has_cols:
            st.warning("No se encontraron columnas de Impressions o Search Query en el archivo SQP.")
        else:
            df_gap = _compute_gaps(df, query_col)

            if df_gap is not None:
                n_total   = len(df_gap)
                n_no_show = df_gap["Tipo de Gap"].str.contains("No aparecés").sum()
                n_mkt_cvr = df_gap["Tipo de Gap"].str.contains("Mercado convierte").sum()
                n_low_is  = df_gap["Tipo de Gap"].str.contains("IS muy bajo").sum()

                gm1, gm2, gm3, gm4 = st.columns(4)
                gm1.metric("Total gaps", n_total)
                gm2.metric("🚫 No aparecés", n_no_show)
                gm3.metric("⚠️ Mercado > vos", n_mkt_cvr)
                gm4.metric("📉 IS bajo", n_low_is)

                def _color_gap_prio(val):
                    if val == "Alta":  return "background-color: #FFC7CE; color: #9C0006"
                    return "background-color: #FFEB9C; color: #9C5700"

                st.dataframe(
                    df_gap.style.applymap(_color_gap_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_gap), 800),
                )

                buf_gap = io.BytesIO()
                df_gap.to_excel(buf_gap, index=False)
                st.download_button(
                    "⬇️ Descargar Gap Analysis (Excel)",
                    data=buf_gap.getvalue(),
                    file_name="sqp_gap_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="gap_dl",
                )
            else:
                st.info("No se encontraron gaps con los criterios actuales.")

    # ── TAB 4: Análisis IA ──────────────────────────────────────────
    with tab4:
        st.subheader("🤖 Análisis IA — PPC Senior")
        st.caption("Análisis ejecutivo generado por Claude basado en tus datos reales")

        if df_ms is None and df_gap is None:
            st.info("Completá los tabs Market Share y Gap Analysis primero "
                    "(necesitás columnas de Impressions Total/Brand en el SQP).")
        else:
            col_ai1, col_ai2 = st.columns([3, 1])
            with col_ai1:
                client_name_ai = st.text_input(
                    "Nombre del cliente",
                    value="", placeholder="Ej: Dermaglos",
                    key="sqp_client_ai",
                )
            with col_ai2:
                st.write("")
                st.write("")
                generar = st.button("🤖 Generar análisis", key="btn_sqp_ai", use_container_width=True)

            if generar:
                if not client_name_ai:
                    st.warning("Ingresá el nombre del cliente primero.")
                else:
                    with st.spinner("Analizando con Claude..."):
                        from core.ai_analyze import _claude_analyze, _build_sqp_prompt
                        ms_for_ai  = df_ms  if df_ms is not None  else pd.DataFrame()
                        gap_for_ai = df_gap if df_gap is not None else pd.DataFrame()
                        prompt = _build_sqp_prompt(ms_for_ai, gap_for_ai,
                                                   client_name_ai, brand or "la marca")
                        analisis = _claude_analyze(prompt)

                    st.markdown("---")
                    st.markdown(analisis)
                    st.markdown("---")

                    col_dl_a, col_dl_b = st.columns(2)
                    with col_dl_a:
                        st.download_button(
                            "⬇️ Descargar análisis (.txt)",
                            data=analisis,
                            file_name=f"analisis_sqp_{client_name_ai}.txt",
                            mime="text/plain",
                            use_container_width=True, key="ai_dl_txt",
                        )
                    with col_dl_b:
                        st.code(analisis, language=None)
