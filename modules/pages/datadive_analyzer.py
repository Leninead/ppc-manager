import io
from datetime import datetime

import numpy as np
import streamlit as st
import pandas as pd

from core.helpers import read_sqp, kpi_card
from modules.parsers import datadive as _dd


# ═══════════════════════════════════════════════════════════════════════
# Cached parsers
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_mkl(data, name):
    return _dd.parse_mkl(data, name)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_competitors(data, name):
    return _dd.parse_competitors(data, name)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_rank_radar(data, name):
    return _dd.parse_rank_radar(data, name)


# ═══════════════════════════════════════════════════════════════════════
# Style helpers
# ═══════════════════════════════════════════════════════════════════════

def _color_score(val, green_thresh, yellow_thresh):
    try:
        v = float(val)
        if v >= green_thresh:
            return "background-color: #E8F5E9; color: #1B5E20"
        elif v >= yellow_thresh:
            return "background-color: #FFF8E1; color: #F57F17"
        else:
            return "background-color: #FFEBEE; color: #B71C1C"
    except (ValueError, TypeError):
        return ""


# ═══════════════════════════════════════════════════════════════════════
# Render
# ═══════════════════════════════════════════════════════════════════════

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🧲</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>DataDive Analyzer</div>"
        "<div style='font-size:0.82rem;color:#888;'>Análisis de exports de DataDive: MKL Keywords, Competitors, Rank Radar y Ranking Volatility.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Research de competidores: keywords de mercado, matriz comparativa, rank tracking y volatilidad cruzada con PPC IS.")
        with col2:
            st.markdown("**📂 Archivos necesarios**")
            st.caption("DataDive → Export: MKL Keywords, Competitors, Rank Radar (.xlsx). SQP opcional para cruzar con PPC IS en Tab 4.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Helium 10 Analyzer (M16) o Campaign Builder (M10) con keywords detectadas.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Tab 1: subí MKL → detectá ASINs competidores y keyword gaps\n"
            "2. Tab 2: subí Competitors → comparación tu ASIN vs Niche Median\n"
            "3. Tab 3: subí Rank Radar → ranking orgánico diario y tendencias\n"
            "4. Tab 4: cruzá Rank Radar + SQP → detectá volátiles sin PPC (RIESGO)\n"
            "5. Tab 5: subí tu MKL + MKL competidor → gap analysis unificado"
        )

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📖 MKL Keywords",
        "⚔️ Competitors",
        "📡 Rank Radar",
        "📊 Ranking + PPC IS",
        "🏆 Competitor Intel",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MKL Keywords
    # ══════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("📖 Master Keyword List")
        st.caption("Archivo: niche-*-keywords.xlsx de DataDive")

        file_mkl = st.file_uploader("Sube tu MKL (.xlsx)", type=["xlsx"], key="dd_mkl")
        if file_mkl:
            df_mkl, competitor_asins = _parse_mkl(file_mkl.getvalue(), file_mkl.name)
            if df_mkl.empty:
                st.warning("No se pudieron extraer keywords del archivo.")
            else:
                st.success(f"✅ {len(df_mkl)} keywords · {len(competitor_asins)} competidores detectados")

                my_asin = st.text_input(
                    "Tu ASIN (para detectar gaps)", placeholder="B0XXXXXXXXX", key="dd_mkl_asin",
                ).strip().upper()

                fc1, fc2 = st.columns(2)
                min_sv = fc1.number_input("SV mínimo", min_value=0, value=100, step=50, key="dd_mkl_sv")
                min_rel = fc2.slider("Relevancia mínima", 0.0, 10.0, 1.0, 0.5, key="dd_mkl_rel")

                df_filtered = df_mkl[
                    (df_mkl["SV"] >= min_sv) & (df_mkl["Relevance"] >= min_rel)
                ].copy()

                if my_asin and my_asin in df_filtered.columns:
                    df_filtered["Mi Ranking"] = df_filtered[my_asin]
                    df_filtered["Rankeado"] = df_filtered["Mi Ranking"].notna().map({True: "✅ Sí", False: "❌ No"})
                elif my_asin:
                    df_filtered["Mi Ranking"] = None
                    df_filtered["Rankeado"] = "❌ No"

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(kpi_card("Keywords", str(len(df_filtered))), unsafe_allow_html=True)
                with k2:
                    st.markdown(kpi_card("SV total", f"{df_filtered['SV'].sum():,.0f}"), unsafe_allow_html=True)
                with k3:
                    st.markdown(kpi_card("SV promedio", f"{df_filtered['SV'].mean():,.0f}" if len(df_filtered) else "—"), unsafe_allow_html=True)
                with k4:
                    if my_asin:
                        ranked_count = df_filtered["Mi Ranking"].notna().sum() if "Mi Ranking" in df_filtered.columns else 0
                        st.markdown(kpi_card(f"Rankeadas ({my_asin[:10]})", f"{ranked_count}/{len(df_filtered)}"), unsafe_allow_html=True)
                    else:
                        st.markdown(kpi_card("Competidores", str(len(competitor_asins))), unsafe_allow_html=True)

                display_cols = ["Search Term", "SV", "Relevance", "Launch Score", "Sugg. Bid"]
                if "Mi Ranking" in df_filtered.columns:
                    display_cols += ["Mi Ranking", "Rankeado"]

                df_show = df_filtered[
                    [c for c in display_cols if c in df_filtered.columns]
                ].sort_values("SV", ascending=False).reset_index(drop=True)

                def _color_ranked(val):
                    if "Sí" in str(val):
                        return "background-color: #E8F5E9; color: #1B5E20"
                    if "No" in str(val):
                        return "background-color: #FFEBEE; color: #B71C1C"
                    return ""

                styled = df_show.style
                if "Relevance" in df_show.columns:
                    styled = styled.map(lambda v: _color_score(v, 3, 2), subset=["Relevance"])
                if "Launch Score" in df_show.columns:
                    styled = styled.map(lambda v: _color_score(v, 7, 4), subset=["Launch Score"])
                if "Rankeado" in df_show.columns:
                    styled = styled.map(_color_ranked, subset=["Rankeado"])
                st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_show), 600))

                if my_asin and "Mi Ranking" in df_filtered.columns:
                    st.markdown("---")
                    st.markdown("#### 🕳️ Keyword Gaps")
                    st.caption(f"Keywords donde tu ASIN ({my_asin}) NO rankea pero competidores sí.")
                    df_gaps = df_filtered[df_filtered["Mi Ranking"].isna()].copy()
                    comp_cols = [c for c in competitor_asins if c in df_gaps.columns and c != my_asin]
                    if comp_cols:
                        df_gaps["Competidores rankeados"] = df_gaps[comp_cols].notna().sum(axis=1)
                        df_gaps = df_gaps[df_gaps["Competidores rankeados"] > 0]
                    if not df_gaps.empty:
                        df_gaps = df_gaps.sort_values("SV", ascending=False)
                        g1, g2 = st.columns(2)
                        with g1:
                            st.markdown(kpi_card("Gaps detectados", str(len(df_gaps))), unsafe_allow_html=True)
                        with g2:
                            st.markdown(kpi_card("SV perdido", f"{df_gaps['SV'].sum():,.0f}"), unsafe_allow_html=True)
                        gap_cols = ["Search Term", "SV", "Relevance", "Launch Score"]
                        if "Competidores rankeados" in df_gaps.columns:
                            gap_cols.append("Competidores rankeados")
                        st.dataframe(
                            df_gaps[[c for c in gap_cols if c in df_gaps.columns]].reset_index(drop=True),
                            use_container_width=True, height=min(38 + 35 * len(df_gaps), 500),
                        )
                    else:
                        st.success("✅ No se detectaron gaps.")

                st.markdown("---")
                buf_mkl = io.BytesIO()
                df_filtered.to_excel(buf_mkl, index=False)
                st.download_button(
                    f"⬇️ Exportar {len(df_filtered)} keywords (Excel)",
                    data=buf_mkl.getvalue(),
                    file_name="datadive_mkl_keywords.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_mkl_dl",
                )
        else:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo niche-*-keywords.xlsx exportado desde DataDive.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — Competitors
    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("⚔️ Competitor Analysis")
        st.caption("Archivo: niche-*-competitors.xlsx de DataDive")

        file_comp = st.file_uploader("Sube tu Competitors (.xlsx)", type=["xlsx"], key="dd_comp")
        if file_comp:
            df_comp, median_data = _parse_competitors(file_comp.getvalue(), file_comp.name)
            if df_comp.empty:
                st.warning("No se pudieron extraer datos de competidores.")
            else:
                st.success(f"✅ {len(df_comp)} competidores detectados")
                my_asin_comp = st.text_input(
                    "Tu ASIN (para destacar)", placeholder="B0XXXXXXXXX", key="dd_comp_asin",
                ).strip().upper()

                revenue_col = next((c for c in df_comp.columns if "revenue" in c.lower()), None)
                sales_col = next((c for c in df_comp.columns if "30d sales" in c.lower() or "sales" in c.lower()), None)
                price_col = next((c for c in df_comp.columns if "price" in c.lower()), None)
                rating_col = next((c for c in df_comp.columns if "rating" in c.lower()), None)
                review_col = next((c for c in df_comp.columns if "review" in c.lower()), None)
                kws_col = next((c for c in df_comp.columns if "kws on p1" in c.lower() or "kws" in c.lower()), None)

                sort_col = revenue_col or sales_col
                if sort_col and sort_col in df_comp.columns:
                    df_comp = df_comp.sort_values(sort_col, ascending=False).reset_index(drop=True)

                if my_asin_comp and my_asin_comp in df_comp["ASIN"].values:
                    my_row = df_comp[df_comp["ASIN"] == my_asin_comp].iloc[0]
                    st.markdown("#### Tu ASIN vs Niche Median")
                    mc1, mc2, mc3, mc4 = st.columns(4)
                    def _compare(col, label, fmt="${:.2f}", col_obj=None):
                        if col and col in my_row.index:
                            my_val = pd.to_numeric(str(my_row[col]).replace("$", "").replace(",", ""), errors="coerce")
                            med_val = pd.to_numeric(str(median_data.get(col, "")).replace("$", "").replace(",", ""), errors="coerce")
                            if pd.notna(my_val):
                                delta = None
                                if pd.notna(med_val) and med_val != 0:
                                    delta = f"{((my_val - med_val) / med_val * 100):+.0f}% vs median"
                                col_obj.metric(label, fmt.format(my_val), delta=delta)
                    _compare(price_col, "Tu Precio", "${:.2f}", mc1)
                    _compare(rating_col, "Tu Rating", "{:.1f} ⭐", mc2)
                    _compare(review_col, "Tus Reviews", "{:.0f}", mc3)
                    _compare(kws_col, "Tus KWs en P1", "{:.0f}", mc4)
                    st.markdown("---")

                def _highlight_my_asin(row):
                    if my_asin_comp and row.get("ASIN") == my_asin_comp:
                        return ["background-color: #FFF3E0"] * len(row)
                    return [""] * len(row)

                styled_comp = df_comp.style.apply(_highlight_my_asin, axis=1)
                if rating_col and rating_col in df_comp.columns:
                    styled_comp = styled_comp.map(lambda v: _color_score(v, 4.5, 4.0), subset=[rating_col])
                st.dataframe(styled_comp, use_container_width=True, height=min(38 + 35 * len(df_comp), 600))

                st.markdown("---")
                buf_comp = io.BytesIO()
                df_comp.to_excel(buf_comp, index=False)
                st.download_button(
                    f"⬇️ Exportar {len(df_comp)} competidores (Excel)",
                    data=buf_comp.getvalue(), file_name="datadive_competitors.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_comp_dl",
                )
        else:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo niche-*-competitors.xlsx exportado desde DataDive.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — Rank Radar
    # ══════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("📡 Rank Radar")
        st.caption("Archivo: [product-name].xlsx de DataDive Rank Radar")

        file_rr = st.file_uploader("Sube tu Rank Radar (.xlsx)", type=["xlsx"], key="dd_rr")
        if file_rr:
            df_rr, date_cols_rr, agg_data = _parse_rank_radar(file_rr.getvalue(), file_rr.name)
            if df_rr.empty:
                st.warning("No se pudieron extraer datos del Rank Radar.")
            else:
                st.success(f"✅ {len(df_rr)} keywords · {len(date_cols_rr)} días de ranking")

                if len(date_cols_rr) >= 2:
                    first_dates = date_cols_rr[:min(7, len(date_cols_rr) // 2)]
                    last_dates = date_cols_rr[max(len(date_cols_rr) // 2, len(date_cols_rr) - 7):]

                    def _calc_trend(row):
                        old_vals = [row.get(d) for d in first_dates if pd.notna(row.get(d))]
                        new_vals = [row.get(d) for d in last_dates if pd.notna(row.get(d))]
                        if not old_vals or not new_vals:
                            return "—"
                        avg_old = sum(old_vals) / len(old_vals)
                        avg_new = sum(new_vals) / len(new_vals)
                        if avg_old == 0:
                            return "—"
                        if avg_new < avg_old * 0.9:
                            return "↑ Mejorando"
                        elif avg_new > avg_old * 1.1:
                            return "↓ Cayendo"
                        return "→ Estable"

                    df_rr["Tendencia"] = df_rr.apply(_calc_trend, axis=1)
                    for d in reversed(date_cols_rr):
                        if d in df_rr.columns and df_rr[d].notna().any():
                            df_rr["Rank Actual"] = df_rr[d]
                            break

                ppc_cols = ["PPC Exact", "PPC Phrase", "PPC Broad", "PPC Auto"]
                ppc_available = [c for c in ppc_cols if c in df_rr.columns]
                if ppc_available:
                    df_rr["PPC Activo"] = df_rr[ppc_available].fillna(0).sum(axis=1).apply(
                        lambda x: "✅ Sí" if x > 0 else "❌ No"
                    )

                # ── Historial de ranking entre cargas ────────────────────
                _RANK_HISTORY_KEY = "dd_rank_history"
                if _RANK_HISTORY_KEY not in st.session_state:
                    st.session_state[_RANK_HISTORY_KEY] = []

                rr_kw_col = "Search Term" if "Search Term" in df_rr.columns else (
                    "Keyword Phrase" if "Keyword Phrase" in df_rr.columns else None
                )
                rr_rank_cols = [c for c in df_rr.columns if "Rank" in c and "Actual" in c]
                if not rr_rank_cols and "Median Rank" in df_rr.columns:
                    rr_rank_cols = ["Median Rank"]

                if rr_kw_col and rr_rank_cols:
                    rr_rank_col = rr_rank_cols[0]
                    existing_names = [s["filename"] for s in st.session_state[_RANK_HISTORY_KEY]]
                    if file_rr.name not in existing_names:
                        st.session_state[_RANK_HISTORY_KEY].append({
                            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "filename": file_rr.name,
                            "data": df_rr[[rr_kw_col, rr_rank_col]].copy().rename(
                                columns={rr_rank_col: "Rank"}
                            ),
                        })
                        if len(st.session_state[_RANK_HISTORY_KEY]) > 5:
                            st.session_state[_RANK_HISTORY_KEY].pop(0)

                    history = st.session_state[_RANK_HISTORY_KEY]
                    if len(history) >= 2:
                        st.markdown("---")
                        st.markdown("#### 📊 Evolución de ranking entre cargas")
                        prev_snap = history[-2]["data"]
                        curr_snap = history[-1]["data"]

                        df_delta = pd.merge(
                            prev_snap, curr_snap,
                            on=rr_kw_col, how="outer", suffixes=("_prev", "_curr"),
                        )
                        df_delta["Delta"] = df_delta["Rank_prev"] - df_delta["Rank_curr"]

                        def _trend_label(d):
                            if pd.isna(d):
                                return "🆕 Nuevo"
                            if d > 0:
                                return "🟢 Subió"
                            if d < 0:
                                return "🔴 Bajó"
                            return "→ Igual"

                        df_delta["Cambio"] = df_delta["Delta"].apply(_trend_label)

                        n_subio = (df_delta["Delta"] > 0).sum()
                        n_bajo = (df_delta["Delta"] < 0).sum()
                        avg_delta = df_delta["Delta"].mean()

                        rk1, rk2, rk3 = st.columns(3)
                        with rk1:
                            st.markdown(kpi_card("Subieron", str(n_subio)), unsafe_allow_html=True)
                        with rk2:
                            st.markdown(kpi_card("Bajaron", str(n_bajo)), unsafe_allow_html=True)
                        with rk3:
                            delta_str = f"{avg_delta:+.1f} pos" if pd.notna(avg_delta) else "—"
                            st.markdown(kpi_card("Delta promedio", delta_str), unsafe_allow_html=True)

                        st.caption(
                            f"Comparando: {history[-2]['filename']} vs {history[-1]['filename']}"
                        )
                        st.dataframe(
                            df_delta.sort_values("Delta", ascending=False, na_position="last"),
                            use_container_width=True, height=400,
                        )
                        st.info(
                            f"📚 {len(history)} snapshots guardados en esta sesión. "
                            "Subí otro archivo Rank Radar para ver la evolución."
                        )
                        st.markdown("---")

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(kpi_card("Keywords", str(len(df_rr))), unsafe_allow_html=True)
                if "Tendencia" in df_rr.columns:
                    with k2:
                        st.markdown(kpi_card("Mejorando", str((df_rr["Tendencia"] == "↑ Mejorando").sum())), unsafe_allow_html=True)
                    with k3:
                        st.markdown(kpi_card("Cayendo", str((df_rr["Tendencia"] == "↓ Cayendo").sum())), unsafe_allow_html=True)
                if "PPC Activo" in df_rr.columns:
                    with k4:
                        st.markdown(kpi_card("Con PPC", str((df_rr["PPC Activo"] == "✅ Sí").sum())), unsafe_allow_html=True)

                display_cols_rr = ["Search Term", "SV", "Relevance", "Median Rank"]
                if "Rank Actual" in df_rr.columns:
                    display_cols_rr.append("Rank Actual")
                if "Tendencia" in df_rr.columns:
                    display_cols_rr.append("Tendencia")
                if "PPC Activo" in df_rr.columns:
                    display_cols_rr.append("PPC Activo")
                for pc in ppc_available:
                    display_cols_rr.append(pc)
                if "SQ Score" in df_rr.columns:
                    display_cols_rr.append("SQ Score")

                available_display = [c for c in display_cols_rr if c in df_rr.columns]
                df_rr_show = df_rr[available_display].copy()
                if "SV" in df_rr_show.columns:
                    df_rr_show = df_rr_show.sort_values("SV", ascending=False).reset_index(drop=True)

                def _color_trend(val):
                    if "Mejorando" in str(val):
                        return "background-color: #E8F5E9; color: #1B5E20"
                    if "Cayendo" in str(val):
                        return "background-color: #FFEBEE; color: #B71C1C"
                    if "Estable" in str(val):
                        return "background-color: #F5F5F5; color: #666"
                    return ""

                def _color_ppc_rr(val):
                    if "Sí" in str(val):
                        return "background-color: #E8F5E9"
                    if "No" in str(val):
                        return "background-color: #FFF8E1"
                    return ""

                styled_rr = df_rr_show.style
                if "Tendencia" in df_rr_show.columns:
                    styled_rr = styled_rr.map(_color_trend, subset=["Tendencia"])
                if "PPC Activo" in df_rr_show.columns:
                    styled_rr = styled_rr.map(_color_ppc_rr, subset=["PPC Activo"])
                st.dataframe(styled_rr, use_container_width=True, height=min(38 + 35 * len(df_rr_show), 600))

                if date_cols_rr and "Search Term" in df_rr.columns:
                    st.markdown("---")
                    st.markdown("#### 📈 Ranking diario (top keywords)")
                    chart_candidates = df_rr.nlargest(20, "SV") if "SV" in df_rr.columns else df_rr.head(20)
                    available_terms = chart_candidates["Search Term"].dropna().unique().tolist()[:20]
                    selected_terms = st.multiselect(
                        "Keywords para el gráfico", options=available_terms,
                        default=available_terms[:5], key="dd_rr_chart_kws",
                    )
                    if selected_terms:
                        chart_data = df_rr[df_rr["Search Term"].isin(selected_terms)][
                            ["Search Term"] + [d for d in date_cols_rr if d in df_rr.columns]
                        ].set_index("Search Term").T
                        chart_data.index.name = "Date"
                        st.line_chart(chart_data, use_container_width=True)

                if "PPC Activo" in df_rr.columns:
                    st.markdown("---")
                    st.markdown("#### 🎯 PPC Coverage")
                    n_with_ppc = (df_rr["PPC Activo"] == "✅ Sí").sum()
                    n_without_ppc = (df_rr["PPC Activo"] == "❌ No").sum()
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        st.markdown(kpi_card("Con PPC activo", str(n_with_ppc)), unsafe_allow_html=True)
                    with pc2:
                        st.markdown(kpi_card("Sin PPC (oportunidades)", str(n_without_ppc)), unsafe_allow_html=True)
                    if n_without_ppc > 0:
                        with st.expander(f"Ver {n_without_ppc} keywords sin PPC"):
                            no_ppc = df_rr[df_rr["PPC Activo"] == "❌ No"]
                            no_ppc_cols = [c for c in ["Search Term", "SV", "Relevance", "Rank Actual", "Tendencia"] if c in no_ppc.columns]
                            st.dataframe(
                                no_ppc[no_ppc_cols].sort_values("SV", ascending=False) if "SV" in no_ppc.columns else no_ppc[no_ppc_cols],
                                use_container_width=True, hide_index=True,
                            )

                st.markdown("---")
                buf_rr = io.BytesIO()
                export_cols = [c for c in df_rr.columns if c not in date_cols_rr]
                recent_dates = date_cols_rr[-7:] if len(date_cols_rr) >= 7 else date_cols_rr
                export_cols += [d for d in recent_dates if d in df_rr.columns]
                df_rr[[c for c in export_cols if c in df_rr.columns]].to_excel(buf_rr, index=False)
                st.download_button(
                    f"⬇️ Exportar Rank Radar ({len(df_rr)} keywords)",
                    data=buf_rr.getvalue(), file_name="datadive_rank_radar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_rr_dl",
                )
        else:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo de Rank Radar exportado desde DataDive.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )

    # ══════════════════════════════════════════════════════════════════
    # TAB 4 — Ranking Volatility + PPC Impression Share
    # ══════════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("📊 Ranking Volatility + PPC Impression Share")
        st.caption("Cruzá el Rank Radar (ranking orgánico diario) con SQP (impression share) para detectar riesgos y oportunidades.")

        vc1, vc2 = st.columns(2)
        with vc1:
            file_rr_v = st.file_uploader("Rank Radar (.xlsx)", type=["xlsx"], key="dd_vol_rr")
        with vc2:
            file_sqp_v = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="dd_vol_sqp")

        if not file_rr_v:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el Rank Radar de DataDive y opcionalmente el SQP de Amazon.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            df_v, date_cols_v, _ = _parse_rank_radar(file_rr_v.getvalue(), file_rr_v.name)
            if df_v.empty:
                st.warning("No se pudieron extraer datos del Rank Radar.")
            else:
                # ── Parse SQP if provided ────────────────────────────
                sqp_is = {}  # keyword_lower -> impression share %
                if file_sqp_v:
                    df_sqp_v = read_sqp(file_sqp_v)
                    sqp_query_col = next((c for c in df_sqp_v.columns if "search query" in c.lower()), None)
                    sqp_is_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "brand" in c.lower() and "share" in c.lower()), None)
                    if not sqp_is_col:
                        # Try count-based: Brand / Total
                        imp_total_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "total" in c.lower() and "count" in c.lower()), None)
                        imp_brand_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "brand" in c.lower() and "count" in c.lower()), None)
                        if imp_total_col and imp_brand_col and sqp_query_col:
                            df_sqp_v[imp_total_col] = pd.to_numeric(df_sqp_v[imp_total_col], errors="coerce").fillna(0)
                            df_sqp_v[imp_brand_col] = pd.to_numeric(df_sqp_v[imp_brand_col], errors="coerce").fillna(0)
                            for _, r in df_sqp_v.iterrows():
                                q = str(r[sqp_query_col]).strip().lower()
                                t = r[imp_total_col]
                                b = r[imp_brand_col]
                                if t > 0:
                                    sqp_is[q] = round(b / t * 100, 1)
                    elif sqp_query_col and sqp_is_col:
                        df_sqp_v[sqp_is_col] = pd.to_numeric(df_sqp_v[sqp_is_col], errors="coerce").fillna(0)
                        for _, r in df_sqp_v.iterrows():
                            q = str(r[sqp_query_col]).strip().lower()
                            sqp_is[q] = round(r[sqp_is_col], 1)
                    if sqp_is:
                        st.success(f"✅ SQP cargado — {len(sqp_is)} queries con impression share")

                # ── Volatility calculation ────────────────────────────
                date_cols_available = [d for d in date_cols_v if d in df_v.columns]
                if len(date_cols_available) < 3:
                    st.warning("Se necesitan al menos 3 días de ranking para calcular volatilidad.")
                else:
                    st.success(f"✅ {len(df_v)} keywords · {len(date_cols_available)} días de datos")

                    ppc_cols_v = ["PPC Exact", "PPC Phrase", "PPC Broad", "PPC Auto"]
                    ppc_avail_v = [c for c in ppc_cols_v if c in df_v.columns]

                    rows_vol = []
                    for _, row in df_v.iterrows():
                        term = str(row.get("Search Term", "")).strip()
                        if not term or term.lower() == "nan":
                            continue

                        ranks = [row[d] for d in date_cols_available if pd.notna(row.get(d))]
                        ranks_numeric = [r for r in ranks if isinstance(r, (int, float)) and r > 0]

                        if not ranks_numeric:
                            continue

                        std_val = float(np.std(ranks_numeric)) if len(ranks_numeric) >= 2 else 0
                        current_rank = ranks_numeric[-1] if ranks_numeric else None
                        avg_rank = sum(ranks_numeric) / len(ranks_numeric)

                        if std_val < 2:
                            volatility = "🟢 ESTABLE"
                        elif std_val <= 5:
                            volatility = "🟡 VOLÁTIL"
                        else:
                            volatility = "🔴 MUY VOLÁTIL"

                        has_ppc = False
                        if ppc_avail_v:
                            ppc_sum = sum(row.get(c, 0) or 0 for c in ppc_avail_v)
                            has_ppc = ppc_sum > 0

                        ppc_is_val = sqp_is.get(term.lower(), None)
                        sv = row.get("SV", 0)
                        sv = sv if pd.notna(sv) else 0

                        # Flags
                        flag = ""
                        if "VOLÁTIL" in volatility and not has_ppc:
                            flag = "⚠️ RIESGO — volátil sin PPC"
                        elif "ESTABLE" in volatility and current_rank and current_rank <= 10 and has_ppc:
                            flag = "💰 OPORTUNIDAD — estable top 10 con PPC activo"

                        rows_vol.append({
                            "Keyword": term,
                            "SV": int(sv),
                            "Rank Actual": int(current_rank) if current_rank else None,
                            "Avg Rank": round(avg_rank, 1),
                            "Std Dev": round(std_val, 2),
                            "Volatilidad": volatility,
                            "PPC Activo": "✅" if has_ppc else "❌",
                            "PPC IS %": ppc_is_val,
                            "Flag": flag,
                        })

                    if not rows_vol:
                        st.info("No hay keywords con datos de ranking suficientes.")
                    else:
                        df_vol = pd.DataFrame(rows_vol).sort_values("SV", ascending=False).reset_index(drop=True)

                        # KPIs
                        n_risk = (df_vol["Flag"].str.contains("RIESGO", na=False)).sum()
                        n_opp = (df_vol["Flag"].str.contains("OPORTUNIDAD", na=False)).sum()
                        vk1, vk2, vk3, vk4 = st.columns(4)
                        with vk1:
                            st.markdown(kpi_card("Keywords analizadas", str(len(df_vol))), unsafe_allow_html=True)
                        with vk2:
                            st.markdown(kpi_card("Estables", str((df_vol["Volatilidad"] == "🟢 ESTABLE").sum())), unsafe_allow_html=True)
                        with vk3:
                            st.markdown(kpi_card("Muy volátiles", str((df_vol["Volatilidad"] == "🔴 MUY VOLÁTIL").sum())), unsafe_allow_html=True)
                        with vk4:
                            st.markdown(kpi_card("Riesgos / Oportunidades", f"{n_risk} / {n_opp}"), unsafe_allow_html=True)

                        # Filter
                        vol_filter = st.multiselect(
                            "Filtrar por volatilidad",
                            options=["🟢 ESTABLE", "🟡 VOLÁTIL", "🔴 MUY VOLÁTIL"],
                            default=["🟡 VOLÁTIL", "🔴 MUY VOLÁTIL"],
                            key="dd_vol_filter",
                        )
                        df_vol_show = df_vol[df_vol["Volatilidad"].isin(vol_filter)] if vol_filter else df_vol

                        def _color_vol(val):
                            if "ESTABLE" in str(val):
                                return "background-color: #E8F5E9; color: #1B5E20"
                            if "MUY VOLÁTIL" in str(val):
                                return "background-color: #FFEBEE; color: #B71C1C"
                            if "VOLÁTIL" in str(val):
                                return "background-color: #FFF8E1; color: #F57F17"
                            return ""

                        def _color_flag(val):
                            if "RIESGO" in str(val):
                                return "background-color: #FFEBEE; color: #B71C1C"
                            if "OPORTUNIDAD" in str(val):
                                return "background-color: #E8F5E9; color: #1B5E20"
                            return ""

                        styled_vol = df_vol_show.style.map(_color_vol, subset=["Volatilidad"])
                        if "Flag" in df_vol_show.columns:
                            styled_vol = styled_vol.map(_color_flag, subset=["Flag"])
                        st.dataframe(styled_vol, use_container_width=True, height=min(38 + 35 * len(df_vol_show), 600))

                        # Export
                        st.markdown("---")
                        buf_vol = io.BytesIO()
                        df_vol.to_excel(buf_vol, index=False)
                        st.download_button(
                            f"⬇️ Exportar Ranking Volatility ({len(df_vol)} keywords)",
                            data=buf_vol.getvalue(),
                            file_name="datadive_ranking_volatility.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dd_vol_dl",
                        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 5 — Competitor Intelligence
    # ══════════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("🏆 Competitor Intelligence — Vista Unificada")
        st.caption(
            "Subí tu MKL + el de un competidor para comparación directa. "
            "Opcionalmente agregá Cerebro de H10."
        )

        col_u1, col_u2 = st.columns(2)
        with col_u1:
            my_mkl = st.file_uploader("Tu MKL Keywords (.xlsx)", type=["xlsx"], key="dd_ci_my_mkl")
        with col_u2:
            comp_mkl = st.file_uploader("MKL Competidor (.xlsx)", type=["xlsx"], key="dd_ci_comp_mkl")

        h10_file = st.file_uploader(
            "Cerebro H10 del competidor (opcional)", type=["xlsx"], key="dd_ci_h10",
        )

        if not my_mkl or not comp_mkl:
            st.markdown(
                "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
                "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
                "<div style='font-size:1.5rem;'>🏆</div>"
                "<div style='font-weight:600;margin-top:0.5rem;'>Subí ambos MKL para comparar</div>"
                "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
                "DataDive → Niche → Keywords → Export para tu ASIN y el competidor</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            # Parse both MKL files
            df_my = _parse_mkl(my_mkl.getvalue(), my_mkl.name)
            df_comp = _parse_mkl(comp_mkl.getvalue(), comp_mkl.name)

            if df_my.empty or df_comp.empty:
                st.error("❌ No se pudo parsear uno de los MKL. Verificá el formato.")
            else:
                # Detect keyword column
                kw_col = "Search Term"
                if kw_col not in df_my.columns:
                    for c in df_my.columns:
                        if "keyword" in c.lower() or "search" in c.lower() or "term" in c.lower():
                            kw_col = c
                            break

                # Merge outer
                df_merged = pd.merge(
                    df_my, df_comp,
                    on=kw_col, how="outer",
                    suffixes=("_mine", "_comp"),
                )

                # Detect rank columns
                rank_cols_mine = [c for c in df_merged.columns if "rank" in c.lower() and "_mine" in c.lower()]
                rank_cols_comp = [c for c in df_merged.columns if "rank" in c.lower() and "_comp" in c.lower()]
                rank_mine = rank_cols_mine[0] if rank_cols_mine else None
                rank_comp = rank_cols_comp[0] if rank_cols_comp else None

                # SV columns
                sv_cols_mine = [c for c in df_merged.columns if "sv" in c.lower() and "_mine" in c.lower()]
                sv_cols_comp = [c for c in df_merged.columns if "sv" in c.lower() and "_comp" in c.lower()]
                sv_mine = sv_cols_mine[0] if sv_cols_mine else None
                sv_comp = sv_cols_comp[0] if sv_cols_comp else None

                # Classify gap
                def _classify_gap(row):
                    has_mine = pd.notna(row.get(rank_mine)) and row.get(rank_mine, 0) > 0 if rank_mine else False
                    has_comp = pd.notna(row.get(rank_comp)) and row.get(rank_comp, 0) > 0 if rank_comp else False
                    if has_mine and has_comp:
                        return "🤝 Ambos rankean"
                    elif has_mine and not has_comp:
                        return "✅ Solo yo"
                    elif not has_mine and has_comp:
                        return "🔴 Solo competidor"
                    return "⚫ Ninguno"

                df_merged["Gap"] = df_merged.apply(_classify_gap, axis=1)

                # If H10 Cerebro provided, add extra columns
                if h10_file:
                    try:
                        df_h10 = pd.read_excel(io.BytesIO(h10_file.getvalue()))
                        df_h10.columns = df_h10.columns.str.strip()
                        h10_kw_col = None
                        for c in df_h10.columns:
                            if "keyword" in c.lower():
                                h10_kw_col = c
                                break
                        if h10_kw_col:
                            h10_cols_to_add = []
                            for c in ["Search Volume", "Organic Rank", "Sponsored Rank"]:
                                if c in df_h10.columns:
                                    h10_cols_to_add.append(c)
                            if h10_cols_to_add:
                                df_h10_slim = df_h10[[h10_kw_col] + h10_cols_to_add].copy()
                                df_h10_slim = df_h10_slim.rename(columns={
                                    h10_kw_col: kw_col,
                                    **{c: f"H10_{c}" for c in h10_cols_to_add},
                                })
                                df_merged = pd.merge(df_merged, df_h10_slim, on=kw_col, how="left")
                                st.success(f"✅ Cerebro H10 integrado — {len(df_h10_slim)} keywords cruzadas")
                    except Exception as e:
                        st.warning(f"⚠️ Error procesando Cerebro H10: {e}")

                # KPI cards
                gap_counts = df_merged["Gap"].value_counts()
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(
                        kpi_card("Ambos rankean", str(gap_counts.get("🤝 Ambos rankean", 0))),
                        unsafe_allow_html=True,
                    )
                with k2:
                    st.markdown(
                        kpi_card("Solo yo", str(gap_counts.get("✅ Solo yo", 0))),
                        unsafe_allow_html=True,
                    )
                with k3:
                    st.markdown(
                        kpi_card("Solo competidor", str(gap_counts.get("🔴 Solo competidor", 0))),
                        unsafe_allow_html=True,
                    )
                with k4:
                    st.markdown(
                        kpi_card("Total keywords", str(len(df_merged))),
                        unsafe_allow_html=True,
                    )

                # Filter by gap type
                gap_options = sorted(df_merged["Gap"].unique().tolist())
                gap_filter = st.multiselect(
                    "Filtrar por gap",
                    options=gap_options,
                    default=["🔴 Solo competidor"],
                    key="dd_ci_gap_filter",
                )

                df_show = df_merged[df_merged["Gap"].isin(gap_filter)] if gap_filter else df_merged

                # Color coding
                def _color_gap(val):
                    if "Solo competidor" in str(val):
                        return "background:#FFEBEE;color:#B71C1C"
                    if "Solo yo" in str(val):
                        return "background:#E8F5E9;color:#1B5E20"
                    if "Ambos" in str(val):
                        return "background:#FFF8E1;color:#F57F17"
                    return "background:#F5F5F5;color:#888"

                styled_ci = df_show.reset_index(drop=True).style.map(_color_gap, subset=["Gap"])
                st.dataframe(styled_ci, use_container_width=True, height=500)

                # Export
                st.markdown("---")
                buf_ci = io.BytesIO()
                df_merged.to_excel(buf_ci, index=False)
                st.download_button(
                    f"⬇️ Exportar Competitor Intel ({len(df_merged)} keywords)",
                    data=buf_ci.getvalue(),
                    file_name="competitor_intelligence.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_ci_dl",
                )
