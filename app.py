import streamlit as st
import pandas as pd
import io
import os
import re

from core.i18n import _I18N
from core.constants import _BR_OPTIONAL_COLS, _PAGES
from core.helpers import _color_pct, extract_sqp_brand, read_sqp
from core.business_report import _BIZ_DIR, _parse_business_report_map, _auto_load_business_report_map
from modules.atom11.parser import (_parse_atom11, _detect_atom11_type, _extract_period_df,
                                   _summarize_daterange, _split_two_weeks)
from modules.atom11.analysis import _kpis, _generate_summary, _diag_items, _rec_items
from modules.atom11.parent_evolution import _build_parent_evolution, _generate_parent_evo_summary
from modules.atom11.excel_export import _build_atom11_excel
from modules.merchanspring.parser import _parse_merchanspring, _parse_merchanspring_pdf
from modules.merchanspring.excel_export import _build_ms_pdf_excel, _build_merchanspring_excel
from modules.merchanspring.style_helpers import _s_acos, _s_margin, _s_delta, _s_eff, _s_stock
from modules.pages.inicio import render as _render_inicio

st.set_page_config(page_title="PPC Manager", layout="wide")


if "parent_child_map" not in st.session_state:
    _auto_load_business_report_map()


if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "🏠 Inicio"

def _nav(page):
    st.session_state["selected_page"] = page

with st.sidebar:
    st.title("🦫 Capybaras Agency OS")
    st.caption("PPC Manager — v1.0")
    st.divider()

    st.button("🏠 Inicio", use_container_width=True, on_click=_nav, args=("🏠 Inicio",), key="nav_home")

    st.markdown("**📊 Análisis**")
    for _pg in ["📊 Search Term Report", "🔍 Search Query Performance", "📁 Bulk Campañas", "💰 Business Report"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔗 Cruce y Tendencias**")
    for _pg in ["🔗 Análisis Cruzado STR vs SQP", "📈 Tendencia Multi-Semana"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔺 Automatización**")
    st.button("🔻 Análisis de Funnel", use_container_width=True, on_click=_nav, args=("🔻 Análisis de Funnel",), key="nav_funnel")

    st.markdown("**📋 Reportes**")
    for _pg in ["🔬 Reportes Atom 11", "🛡️ Reportes MerchanSpring"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    _n_pe_parents = len(set(st.session_state.get("parent_child_map", {}).values()))
    _pe_label = (
        f"🧬 Parent-Child: {_n_pe_parents} parents cargados"
        if _n_pe_parents > 0 else
        "⚠️ Sin mapeo — agregá Business Report a data/business_report/"
    )
    _pe_color = "#4caf50" if _n_pe_parents > 0 else "#ff9800"
    st.markdown(
        "<div style='margin-top:2rem;font-size:0.72rem;color:#888;'>"
        "Desarrollado por Lenin Acosta · Capybaras Agency · 2026"
        "</div>"
        f"<div style='font-size:0.72rem;color:{_pe_color};margin-top:0.35rem;'>"
        f"{_pe_label}"
        "</div>",
        unsafe_allow_html=True,
    )

selected = st.session_state["selected_page"]

if selected == "🏠 Inicio":
    _render_inicio()

if selected == "📊 Search Term Report":
    st.header("📊 Search Term Report")
    st.caption("Análisis de términos de búsqueda con métricas de ACoS, gasto y ventas totales.")
    st.divider()
    file_str = st.file_uploader("Sube tu STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str")
    if file_str:
        df = pd.read_excel(file_str) if file_str.name.endswith(".xlsx") else pd.read_csv(file_str)
        st.success(f"✅ {len(df)} filas cargadas")
        
        col1, col2, col3, col4 = st.columns(4)
        spend_col = next((c for c in df.columns if "spend" in c.lower()), None)
        sales_col = next((c for c in df.columns if "sales" in c.lower() and "other" not in c.lower() and "advertised" not in c.lower()), None)
        if spend_col and sales_col:
            total_spend = pd.to_numeric(df[spend_col], errors="coerce").sum()
            total_sales = pd.to_numeric(df[sales_col], errors="coerce").sum()
            acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
            col1.metric("Total Spend", f"${total_spend:,.2f}")
            col2.metric("Total Sales", f"${total_sales:,.2f}")
            col3.metric("ACoS", f"{acos:.1f}%")
            col4.metric("Términos únicos", df.shape[0])
        
        st.dataframe(df, use_container_width=True)

if selected == "🔍 Search Query Performance":
    st.header("🔍 Search Query Performance")
    st.caption("Datos de rendimiento de búsqueda orgánica exportados desde Amazon Brand Analytics.")
    st.divider()
    file_sqp = st.file_uploader("Sube tu SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp")
    if file_sqp:
        df = read_sqp(file_sqp)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "📁 Bulk Campañas":
    st.header("📁 Bulk File de Campañas")
    st.caption("Archivo bulk exportado desde Amazon Ads con todas las campañas, grupos y keywords.")
    st.divider()
    file_bulk = st.file_uploader("Sube tu Bulk (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk")
    if file_bulk:
        df = pd.read_excel(file_bulk) if file_bulk.name.endswith(".xlsx") else pd.read_csv(file_bulk)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "💰 Business Report":
    st.header("💰 Business Report")
    st.caption("Reporte de ventas y sesiones exportado desde Amazon Seller Central.")
    st.divider()
    file_br = st.file_uploader("Sube tu Business Report (.xlsx o .csv)", type=["xlsx", "csv"], key="br")
    if file_br:
        df = pd.read_excel(file_br) if file_br.name.endswith(".xlsx") else pd.read_csv(file_br)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "🔗 Análisis Cruzado STR vs SQP":
    st.header("🔗 Análisis Cruzado STR vs SQP")
    st.caption("Detectá oportunidades cruzando términos de búsqueda pagos (STR) con orgánicos (SQP).")
    st.divider()
    st.info("Subí ambos archivos para comparar qué términos aparecen en cada reporte y detectar oportunidades.")

    col_str, col_sqp = st.columns(2)
    with col_str:
        file_str_x = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_x")
    with col_sqp:
        file_sqp_x = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp_x")

    if file_str_x and file_sqp_x:
        df_str = pd.read_excel(file_str_x) if file_str_x.name.endswith(".xlsx") else pd.read_csv(file_str_x)
        brand_name = extract_sqp_brand(file_sqp_x)
        df_sqp = read_sqp(file_sqp_x)

        str_col = "Customer Search Term"
        sqp_col = "Search Query"

        if brand_name:
            st.success(f"Marca detectada: **{brand_name.title()}**")
            brand_terms = [t.strip() for t in brand_name.split(",")]
            df_sqp["Tipo"] = df_sqp[sqp_col].str.lower().str.strip().apply(
                lambda q: "Marca" if any(t in q for t in brand_terms) else "Genérica"
            )
        else:
            st.warning("No se detectó la marca en el archivo SQP. Todas las keywords se clasifican como genéricas.")
            df_sqp["Tipo"] = "Genérica"

        if str_col not in df_str.columns:
            st.error(f"El STR no tiene la columna '{str_col}'.")
        elif sqp_col not in df_sqp.columns:
            st.error(f"El SQP no tiene la columna '{sqp_col}'.")
        else:
            terms_str = set(df_str[str_col].dropna().str.lower().str.strip())
            terms_sqp = set(df_sqp[sqp_col].dropna().str.lower().str.strip())

            in_both = terms_str & terms_sqp
            only_str = terms_str - terms_sqp
            only_sqp = terms_sqp - terms_str

            c1, c2, c3 = st.columns(3)
            c1.metric("En ambos", len(in_both))
            c2.metric("Solo en STR (no en SQP)", len(only_str))
            c3.metric("Solo en SQP (oportunidades)", len(only_sqp))

            opp_sqp = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)]
            n_marca    = (opp_sqp["Tipo"] == "Marca").sum()
            n_generica = (opp_sqp["Tipo"] == "Genérica").sum()
            m1, m2 = st.columns(2)
            m1.metric("Oportunidades de marca", n_marca)
            m2.metric("Oportunidades genéricas", n_generica)

            # ── Convertir columnas numéricas del SQP ────────────────────────
            imp_col   = "Impressions: Total Count"
            score_col = "Search Query Score"
            pur_col   = "Purchases: Total Count"
            prate_col = "Purchases: Purchase Rate %"
            for c in [imp_col, score_col, pur_col, prate_col, "Clicks: Total Count"]:
                if c in df_sqp.columns:
                    df_sqp[c] = pd.to_numeric(df_sqp[c], errors="coerce").fillna(0)

            # ── Filtros globales ─────────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### Filtros")
            f1, f2, f3, f4 = st.columns(4)
            min_imp   = f1.number_input("Mínimo de impresiones", min_value=0, value=0, step=100)
            min_score = f2.number_input("Mínimo Search Query Score", min_value=0, value=0, step=1)
            min_pur   = f3.number_input("Mínimo de purchases", min_value=0, value=0, step=1)
            tipo_filtro = f4.selectbox("Tipo de keyword", ["Todas", "Marca", "Genérica"])

            def apply_filters(df):
                d = df.copy()
                if imp_col in d.columns:
                    d = d[d[imp_col] >= min_imp]
                if score_col in d.columns:
                    d = d[d[score_col] >= min_score]
                if pur_col in d.columns:
                    d = d[d[pur_col] >= min_pur]
                if "Tipo" in d.columns and tipo_filtro != "Todas":
                    d = d[d["Tipo"] == tipo_filtro]
                if imp_col in d.columns:
                    d = d.sort_values(imp_col, ascending=False)
                return d

            st.markdown("---")

            # ── Tabla 1: en ambos ────────────────────────────────────────────
            st.markdown("#### Términos en ambos reportes")
            sqp_cols_merge = [sqp_col] + [c for c in [score_col, imp_col, "Clicks: Total Count", pur_col] if c in df_sqp.columns]
            sqp_subset = df_sqp[sqp_cols_merge].copy()
            sqp_subset[sqp_col] = sqp_subset[sqp_col].str.lower().str.strip()
            merged = df_str[df_str[str_col].str.lower().str.strip().isin(in_both)].copy()
            merged[str_col] = merged[str_col].str.lower().str.strip()
            merged = merged.merge(sqp_subset, left_on=str_col, right_on=sqp_col, how="left", suffixes=("_STR", "_SQP"))
            st.dataframe(apply_filters(merged), use_container_width=True)

            # ── Tabla 2: solo en SQP (oportunidades) ────────────────────────
            st.markdown("#### Términos solo en SQP (sin campaña activa — posibles oportunidades)")
            df_oportunidades = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)].copy()

            score_norm_cols = [c for c in [imp_col, "Clicks: Total Count", prate_col] if c in df_oportunidades.columns]
            if score_norm_cols:
                norm = df_oportunidades[score_norm_cols].apply(
                    lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() != s.min() else 0
                )
                df_oportunidades.insert(1, "Opportunity Score", (norm.sum(axis=1) / len(score_norm_cols) * 100).round(1))

            df_oportunidades_filtrado = apply_filters(df_oportunidades)
            st.dataframe(df_oportunidades_filtrado, use_container_width=True)

            buffer = io.BytesIO()
            df_oportunidades_filtrado.to_excel(buffer, index=False)
            st.download_button(
                label=f"⬇️ Exportar {len(df_oportunidades_filtrado)} oportunidades a Excel",
                data=buffer.getvalue(),
                file_name="oportunidades_sqp.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            # ── Tabla 3: solo en STR ─────────────────────────────────────────
            st.markdown("#### Términos solo en STR (sin datos de búsqueda orgánica)")
            df_solo_str = df_str[df_str[str_col].str.lower().str.strip().isin(only_str)].copy()
            st.dataframe(df_solo_str, use_container_width=True)

if selected == "📈 Tendencia Multi-Semana":
    st.header("📈 Tendencia de Impresiones Multi-Semana")
    st.caption("Compará hasta 4 semanas de SQP para identificar keywords en alza, estables o en caída.")
    st.divider()
    st.info("Subí hasta 4 archivos SQP de distintas semanas para ver la tendencia por keyword.")

    sqp_files = []
    cols_up = st.columns(4)
    for i, col in enumerate(cols_up):
        f = col.file_uploader(f"Semana {i+1}", type=["xlsx", "csv"], key=f"sqp_trend_{i}")
        if f:
            sqp_files.append(f)

    if len(sqp_files) >= 2:
        imp_col_t = "Impressions: Total Count"
        sqp_col_t = "Search Query"

        weeks = []
        for f in sqp_files:
            df_w = read_sqp(f)
            df_w[sqp_col_t] = df_w[sqp_col_t].str.lower().str.strip()
            if imp_col_t in df_w.columns:
                df_w[imp_col_t] = pd.to_numeric(df_w[imp_col_t], errors="coerce").fillna(0)
            # Extraer fecha desde Reporting Date o nombre de archivo
            label = None
            if "Reporting Date" in df_w.columns:
                label = str(df_w["Reporting Date"].dropna().iloc[0]) if not df_w["Reporting Date"].dropna().empty else f.name
            else:
                label = f.name
            weeks.append((label, df_w[[sqp_col_t, imp_col_t]].rename(columns={imp_col_t: label})))

        df_trend = weeks[0][1]
        for _, df_w in weeks[1:]:
            df_trend = df_trend.merge(df_w, on=sqp_col_t, how="outer").fillna(0)

        week_cols = [w[0] for w in weeks]
        first_col, last_col = week_cols[0], week_cols[-1]

        def tendencia(row):
            v1, v2 = row[first_col], row[last_col]
            if v2 > v1 * 1.1:
                return "↑"
            elif v2 < v1 * 0.9:
                return "↓"
            return "→"

        df_trend["Tendencia"] = df_trend.apply(tendencia, axis=1)
        df_trend = df_trend[[sqp_col_t, "Tendencia"] + week_cols].sort_values(last_col, ascending=False)

        st.markdown(f"↑ sube >10% · ↓ baja >10% · → estable")

        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Total keywords", len(df_trend))
        t2.metric("↑ Subiendo", (df_trend["Tendencia"] == "↑").sum())
        t3.metric("→ Estables",  (df_trend["Tendencia"] == "→").sum())
        t4.metric("↓ Bajando",   (df_trend["Tendencia"] == "↓").sum())

        row_height = 35
        header_height = 38
        st.dataframe(df_trend, use_container_width=True, height=header_height + row_height * len(df_trend))

        buffer_t = io.BytesIO()
        df_trend.to_excel(buffer_t, index=False)
        st.download_button(
            label="⬇️ Exportar tendencias a Excel",
            data=buffer_t.getvalue(),
            file_name="tendencia_sqp.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    elif len(sqp_files) == 1:
        st.warning("Subí al menos 2 semanas para ver la tendencia.")

if selected == "🔻 Análisis de Funnel":
    st.header("🔻 Análisis de Funnel")
    st.caption("Analizá cobertura de campañas activas, detectá brechas y generá sugerencias de harvesting.")
    st.divider()
    st.info("Subí el Bulk de campañas y el STR para ver cobertura por campaña.")

    col_bulk_f, col_str_f = st.columns(2)
    with col_bulk_f:
        file_bulk_f = st.file_uploader("Bulk de campañas (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk_f")
    with col_str_f:
        file_str_f = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_f")

    if file_bulk_f:
        df_bulk = pd.read_excel(file_bulk_f) if file_bulk_f.name.endswith(".xlsx") else pd.read_csv(file_bulk_f)
        df_bulk.columns = df_bulk.columns.str.strip()

        # Columnas reales del bulk de Amazon
        # State: ENABLED / PAUSED / ARCHIVED  (cada fila = una campaña)
        state_col = next((c for c in df_bulk.columns if c.lower() == "state"), None)
        camp_col  = next((c for c in df_bulk.columns if c.lower() == "campaign name"), None)
        type_col  = next((c for c in df_bulk.columns if c.lower() == "type"), None)

        if state_col:
            df_active = df_bulk[df_bulk[state_col].str.upper().str.strip() == "ENABLED"].copy()
        else:
            df_active = df_bulk.copy()

        # Métricas de campañas activas
        n_camps = len(df_active)
        n_tipos = df_active[type_col].value_counts() if type_col else None

        m1, m2, m3 = st.columns(3)
        m1.metric("Campañas activas", n_camps)
        m2.metric("Pausadas",  len(df_bulk[df_bulk[state_col].str.upper().str.strip() == "PAUSED"]) if state_col else "—")
        m3.metric("Total en Bulk", len(df_bulk))

        if type_col and n_tipos is not None:
            st.markdown("**Campañas activas por tipo:**  " + "  ·  ".join(f"**{k}**: {v}" for k, v in n_tipos.items()))

        st.markdown("#### Campañas activas")
        display_cols = [c for c in ["Campaign name", "Type", "Portfolio name", "Campaign bid strategy",
                                     "Campaign budget amount", "Impressions", "Clicks", "CTR",
                                     "Total cost", "CPC", "Purchases", "Sales", "ACOS", "ROAS"]
                        if c in df_active.columns]
        st.dataframe(df_active[display_cols] if display_cols else df_active, use_container_width=True)

        st.markdown("---")

        # Cruce con STR por nombre de campaña
        if file_str_f:
            df_str_f_data = pd.read_excel(file_str_f) if file_str_f.name.endswith(".xlsx") else pd.read_csv(file_str_f)
            df_str_f_data.columns = df_str_f_data.columns.str.strip()

            str_term_col = "Customer Search Term"
            str_camp_col = next((c for c in df_str_f_data.columns if c.lower() == "campaign name"), None)

            if str_term_col not in df_str_f_data.columns:
                st.error(f"El STR no tiene la columna '{str_term_col}'.")
            elif camp_col is None or str_camp_col is None:
                st.error("No se encontró la columna 'Campaign name' en el Bulk o en el STR.")
            else:
                active_camps = set(df_active[camp_col].dropna().str.lower().str.strip())
                df_str_f_data["_camp_norm"] = df_str_f_data[str_camp_col].str.lower().str.strip()

                df_str_activo  = df_str_f_data[df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")
                df_str_inactivo = df_str_f_data[~df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")

                camps_sin_str = active_camps - set(df_str_f_data["_camp_norm"])

                c1, c2, c3 = st.columns(3)
                c1.metric("Términos STR de campañas activas",   len(df_str_activo))
                c2.metric("Términos STR de campañas inactivas", len(df_str_inactivo))
                c3.metric("Campañas activas sin tráfico en STR", len(camps_sin_str))

                st.markdown("#### Términos del STR provenientes de campañas activas")
                st.dataframe(df_str_activo, use_container_width=True)

                st.markdown("#### Términos del STR de campañas pausadas o no encontradas")
                df_gaps = df_str_inactivo
                st.dataframe(df_gaps, use_container_width=True)

                buf_gaps = io.BytesIO()
                df_gaps.to_excel(buf_gaps, index=False)
                st.download_button(
                    label=f"⬇️ Exportar {len(df_gaps)} términos de campañas inactivas",
                    data=buf_gaps.getvalue(),
                    file_name="str_campanas_inactivas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

                if camps_sin_str:
                    st.markdown("#### Campañas activas sin términos en el STR")
                    st.dataframe(pd.DataFrame(sorted(camps_sin_str), columns=["Campaign name"]), use_container_width=True)

                # ── Campañas Sugeridas ───────────────────────────────────────
                st.markdown("---")
                st.markdown("### Campañas Sugeridas")
                st.info("Nombres generados siguiendo el convention: Producto - ASIN - SP - KW - MatchType - Keyword")

                if str_term_col in df_gaps.columns and str_camp_col in df_gaps.columns and len(df_gaps) > 0:
                    match_type = st.selectbox("Match Type por defecto", ["Phrase", "Exact", "Broad"], key="match_type_sug")

                    def extract_producto_asin(camp_name):
                        """Extrae Producto y ASIN del nombre de campaña (formato: Producto - ASIN - ...)."""
                        m = re.match(r'^(.+?)\s*-\s*(B[0-9A-Z]{9})\b', str(camp_name), re.IGNORECASE)
                        if m:
                            return m.group(1).strip(), m.group(2).upper()
                        return None, None

                    rows = []
                    for _, row in df_gaps[[str_term_col, str_camp_col]].drop_duplicates(subset=str_term_col).iterrows():
                        term = str(row[str_term_col]).strip()
                        producto, asin = extract_producto_asin(row[str_camp_col])
                        if producto and asin:
                            suggested = f"{producto} - {asin} - SP - KW - {match_type} - {term.title()}"
                        else:
                            suggested = f"[Producto] - [ASIN] - SP - KW - {match_type} - {term.title()}"
                        rows.append({
                            "Customer Search Term": term,
                            "Campaña origen (inactiva)": row[str_camp_col],
                            "Producto inferido": producto or "—",
                            "ASIN inferido": asin or "—",
                            "Match Type": match_type,
                            "Nombre sugerido": suggested,
                        })

                    df_sugeridas = pd.DataFrame(rows)
                    st.dataframe(df_sugeridas, use_container_width=True)

                    buf_sug = io.BytesIO()
                    df_sugeridas.to_excel(buf_sug, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_sugeridas)} campañas sugeridas a Excel",
                        data=buf_sug.getvalue(),
                        file_name="campanas_sugeridas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                else:
                    st.success("No hay términos de campañas inactivas para sugerir.")

                # ── Harvesting ───────────────────────────────────────────────
                st.markdown("---")
                st.markdown("### Harvesting")
                st.info("Términos del STR con ventas suficientes para cosechar como keywords.")

                orders_col  = "7 Day Total Orders (#)"
                sales_col_h = "7 Day Total Sales"
                acos_col_h  = "Total Advertising Cost of Sales (ACOS)"
                cvr_col     = "7 Day Conversion Rate"

                harvest_cols = [c for c in [str_term_col, "Impressions", "Clicks", orders_col,
                                            sales_col_h, "Spend", acos_col_h, cvr_col]
                                if c in df_str_f_data.columns]

                if orders_col not in df_str_f_data.columns:
                    st.warning(f"El STR no tiene la columna '{orders_col}'.")
                else:
                    min_ventas = st.number_input("Mínimo de órdenes para cosechar", min_value=1, value=3, step=1, key="min_harvest")

                    for c in [orders_col, sales_col_h, acos_col_h, cvr_col, "Impressions", "Clicks", "Spend"]:
                        if c in df_str_f_data.columns:
                            df_str_f_data[c] = pd.to_numeric(df_str_f_data[c], errors="coerce").fillna(0)

                    camp_agg = df_str_f_data.groupby(str_term_col)[str_camp_col].apply(
                        lambda x: " | ".join(sorted(x.dropna().unique()))
                    ).reset_index().rename(columns={str_camp_col: "Campaña origen"})

                    df_harvest_agg = (
                        df_str_f_data[harvest_cols]
                        .groupby(str_term_col, as_index=False)
                        .agg({c: "sum" for c in harvest_cols if c != str_term_col})
                        .merge(camp_agg, on=str_term_col, how="left")
                    )

                    # Mover "Campaña origen" como segunda columna
                    cols = df_harvest_agg.columns.tolist()
                    cols.insert(1, cols.pop(cols.index("Campaña origen")))
                    df_harvest_agg = df_harvest_agg[cols]

                    # Recalcular ACoS agregado
                    if sales_col_h in df_harvest_agg.columns and "Spend" in df_harvest_agg.columns:
                        df_harvest_agg[acos_col_h] = (
                            df_harvest_agg["Spend"] / df_harvest_agg[sales_col_h].replace(0, float("nan")) * 100
                        ).round(2)

                    df_harvest_agg = df_harvest_agg[df_harvest_agg[orders_col] >= min_ventas].copy()

                    def suggest_match(row):
                        orders = row[orders_col]
                        acos   = row.get(acos_col_h, 100)
                        if orders >= min_ventas * 3 or (orders >= min_ventas and acos <= 25):
                            return "Exact"
                        return "Phrase"

                    df_harvest_agg["Match Type Sugerido"] = df_harvest_agg.apply(suggest_match, axis=1)
                    df_harvest_agg = df_harvest_agg.sort_values(orders_col, ascending=False)

                    n_exact  = (df_harvest_agg["Match Type Sugerido"] == "Exact").sum()
                    n_phrase = (df_harvest_agg["Match Type Sugerido"] == "Phrase").sum()
                    h1, h2, h3 = st.columns(3)
                    h1.metric("Términos para cosechar", len(df_harvest_agg))
                    h2.metric("→ Exact",  n_exact)
                    h3.metric("→ Phrase", n_phrase)

                    st.markdown(f"**Criterio:** Exact si órdenes ≥ {min_ventas * 3} o (órdenes ≥ {min_ventas} y ACoS ≤ 25%) · Phrase en el resto")
                    st.dataframe(df_harvest_agg, use_container_width=True)

                    buf_harv = io.BytesIO()
                    df_harvest_agg.to_excel(buf_harv, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_harvest_agg)} términos para cosechar",
                        data=buf_harv.getvalue(),
                        file_name="harvesting.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
        else:
            st.markdown("#### Todas las campañas del Bulk")
            st.dataframe(df_bulk, use_container_width=True)

if selected == "🔬 Reportes Atom 11":
    st.header("🔬 Reportes Atom 11")
    st.caption("Subí 1 archivo para el resumen del periodo, o 2 archivos para comparación automática WoW / MoM.")
    st.divider()

    _cfg_col1, _cfg_col2 = st.columns([3, 1])
    with _cfg_col1:
        client_name = st.text_input("Nombre del cliente (aparece en el Excel)", placeholder="Ej: Dermaglos Argentina", key="atom11_client")
    with _cfg_col2:
        _lang_opt = st.radio("Idioma del Excel", ["Español", "English"], horizontal=True, key="atom11_lang")
    lang_code = "en" if _lang_opt == "English" else "es"

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        file_a1 = st.file_uploader("Periodo 1 \u2014 anterior (o unico archivo)", type=["xlsx"], key="atom11_f1")
    with col_u2:
        file_a2 = st.file_uploader("Periodo 2 \u2014 actual (opcional, para comparacion)", type=["xlsx"], key="atom11_f2")

    if file_a1:
        try:
            df1, ec1, cm1, fmt1 = _parse_atom11(file_a1)
            tipo = _detect_atom11_type(ec1)
            metrics1 = list(dict.fromkeys(m for _, m, _ in cm1))
            periods1 = list(dict.fromkeys(p for _, _, p in cm1))

            # ── Two-file comparison ───────────────────────────────────────────
            if file_a2:
                df2, ec2, cm2, fmt2 = _parse_atom11(file_a2)
                tipo2 = _detect_atom11_type(ec2)
                metrics2 = list(dict.fromkeys(m for _, m, _ in cm2))
                periods2 = list(dict.fromkeys(p for _, _, p in cm2))

                if ec1[0].lower() != ec2[0].lower():
                    st.error(f"Los archivos son de tipos distintos ({tipo} vs {tipo2}). Subi dos archivos del mismo tipo.")
                else:
                    # Collapse each file to a single-period df
                    if fmt1 == "DateRange":
                        df1_s, per1 = _summarize_daterange(df1, ec1, cm1)
                    else:
                        per1 = periods1[-1] if fmt1 == "WoW" else periods1[0]
                        df1_s = _extract_period_df(df1, ec1, cm1, per1)

                    if fmt2 == "DateRange":
                        df2_s, per2 = _summarize_daterange(df2, ec2, cm2)
                    else:
                        per2 = periods2[-1] if fmt2 == "WoW" else periods2[0]
                        df2_s = _extract_period_df(df2, ec2, cm2, per2)

                    comp_lbl = "WoW" if "week" in per1.lower() or "week" in per2.lower() else "MoM"
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Comparacion {comp_lbl}:** {per1}  \u2192  {per2}")

                    merged = df1_s.merge(df2_s, on=ec1, how="outer",
                                         suffixes=(f" ({per1})", f" ({per2})"))
                    for c in merged.columns:
                        if c not in ec1:
                            merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)

                    display = merged[ec1].copy()
                    delta_cols = []
                    for metric in list(dict.fromkeys(metrics1 + metrics2)):
                        pc = f"{metric} ({per1})"; cc = f"{metric} ({per2})"
                        if pc in merged.columns and cc in merged.columns:
                            display[pc] = merged[pc]
                            display[cc] = merged[cc]
                            pct_v = ((merged[cc] - merged[pc]) / merged[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    # Derived ACoS & CPC
                    for suf in [per1, per2]:
                        sp_c = f"Spend ({suf})"; sl_c = f"Sales ({suf})"; cl_c = f"Clicks ({suf})"
                        if sp_c in display.columns and sl_c in display.columns:
                            display[f"ACoS ({suf})"] = (display[sp_c] / display[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in display.columns and cl_c in display.columns:
                            display[f"CPC ({suf})"] = (display[sp_c] / display[cl_c].replace(0, float("nan"))).round(2)

                    kc = _kpis(df2_s); kp = _kpis(df1_s)
                    per_c = per2; per_p = per1
                    df_curr = df2_s

            # ── Single file ───────────────────────────────────────────────────
            else:
                if fmt1 == "WoW":
                    prev_p = periods1[0]; curr_p = periods1[-1]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **WoW:** {prev_p}  \u2192  {curr_p}")
                    display = df1[ec1].copy()
                    delta_cols = []
                    for metric in metrics1:
                        pc = f"{metric}|{prev_p}"; cc = f"{metric}|{curr_p}"
                        if pc in df1.columns and cc in df1.columns:
                            display[f"{metric} ({prev_p})"] = df1[pc]
                            display[f"{metric} ({curr_p})"] = df1[cc]
                            pct_v = ((df1[cc] - df1[pc]) / df1[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    for period in [prev_p, curr_p]:
                        sp_c = f"Spend|{period}"; sl_c = f"Sales|{period}"; cl_c = f"Clicks|{period}"
                        if sp_c in df1.columns and sl_c in df1.columns:
                            display[f"ACoS ({period})"] = (df1[sp_c] / df1[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in df1.columns and cl_c in df1.columns:
                            display[f"CPC ({period})"] = (df1[sp_c] / df1[cl_c].replace(0, float("nan"))).round(2)
                    df_curr = _extract_period_df(df1, ec1, cm1, curr_p)
                    df_prev = _extract_period_df(df1, ec1, cm1, prev_p)
                    kc = _kpis(df_curr); kp = _kpis(df_prev)
                    per_c = curr_p; per_p = prev_p

                elif fmt1 == "MoM":
                    period = periods1[0]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **MoM:** {period}")
                    df_curr = _extract_period_df(df1, ec1, cm1, period)
                    display = df_curr.copy()
                    if "Spend" in display.columns and "Sales" in display.columns:
                        display["ACoS"] = (display["Spend"] / display["Sales"].replace(0, float("nan")) * 100).round(2)
                    if "Spend" in display.columns and "Clicks" in display.columns:
                        display["CPC"] = (display["Spend"] / display["Clicks"].replace(0, float("nan"))).round(2)
                    delta_cols = []
                    kc = _kpis(df_curr); kp = None
                    per_c = period; per_p = ""

                else:  # DateRange
                    two_weeks = _split_two_weeks(df1, ec1, cm1)
                    if two_weeks:
                        df_prev, df_curr, per_p, per_c = two_weeks
                        st.info(
                            f"**Tipo detectado:** {tipo}  \u00b7  "
                            f"**WoW auto-detectado (2 semanas):**  "
                            f"Sem 1: {per_p}  \u2192  Sem 2: {per_c}"
                        )
                        _sfx_prev = _I18N[lang_code]["col_prev_sfx"]
                        _sfx_curr = _I18N[lang_code]["col_curr_sfx"]
                        display    = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            if metric in df_prev.columns and metric in df_curr.columns:
                                display[f"{metric} {_sfx_prev}"] = df_prev[metric]
                                display[f"{metric} {_sfx_curr}"] = df_curr[metric]
                                pct_v = (
                                    (df_curr[metric] - df_prev[metric])
                                    / df_prev[metric].replace(0, float("nan")) * 100
                                ).round(1)
                                d_col = f"{metric} \u0394%"
                                display[d_col] = pct_v
                                delta_cols.append(d_col)
                        for suffix, df_s in [(_sfx_prev, df_prev), (_sfx_curr, df_curr)]:
                            if "Spend" in df_s.columns and "Sales" in df_s.columns:
                                display[f"ACoS {suffix}"] = (
                                    df_s["Spend"] / df_s["Sales"].replace(0, float("nan")) * 100
                                ).round(2)
                            if "Spend" in df_s.columns and "Clicks" in df_s.columns:
                                display[f"CPC {suffix}"] = (
                                    df_s["Spend"] / df_s["Clicks"].replace(0, float("nan"))
                                ).round(2)
                        kc = _kpis(df_curr)
                        kp = _kpis(df_prev)
                    else:
                        df_curr, period_lbl = _summarize_daterange(df1, ec1, cm1)
                        st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Date Range:** {period_lbl}")
                        dates = periods1
                        display = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            for date in dates:
                                col = f"{metric}|{date}"
                                if col in df1.columns:
                                    display[f"{metric} {date}"] = df1[col]
                            date_cols = [f"{metric}|{d}" for d in dates if f"{metric}|{d}" in df1.columns]
                            if date_cols:
                                display[f"{metric} Total"] = df1[date_cols].sum(axis=1)
                            if len(dates) >= 2:
                                fc = f"{metric}|{dates[0]}"; lc = f"{metric}|{dates[-1]}"
                                if fc in df1.columns and lc in df1.columns:
                                    d_col = f"{metric} \u0394%"
                                    display[d_col] = ((df1[lc] - df1[fc]) / df1[fc].replace(0, float("nan")) * 100).round(1)
                                    delta_cols.append(d_col)
                        kc = _kpis(df_curr); kp = None
                        per_c = period_lbl; per_p = ""

            # ── KPI cards ─────────────────────────────────────────────────────
            st.markdown("---")
            kpi_defs_display = [
                ("Impressions", "{:,.0f}",  False),
                ("Clicks",      "{:,.0f}",  False),
                ("Spend",       "${:,.2f}", False),
                ("Sales",       "${:,.2f}", False),
                ("ACoS",        "{:.1f}%",  True),
                ("ROAS",        "{:.2f}x",  False),
                ("CTR",         "{:.2f}%",  False),
                ("CVR",         "{:.2f}%",  False),
            ]
            _kpi_chunk_size = 4
            for _kpi_start in range(0, len(kpi_defs_display), _kpi_chunk_size):
                _kpi_chunk = kpi_defs_display[_kpi_start:_kpi_start + _kpi_chunk_size]
                kpi_row = st.columns(len(_kpi_chunk))
                for i, (label, fmt_str, lower_better) in enumerate(_kpi_chunk):
                    cv = kc.get(label, 0) or 0
                    val_str = fmt_str.format(cv)
                    if kp is not None:
                        pv = kp.get(label, 0) or 0
                        if pv != 0:
                            d = (cv - pv) / pv * 100
                            kpi_row[i].metric(label, val_str, delta=f"{d:+.1f}%",
                                              delta_color="inverse" if lower_better else "normal")
                        else:
                            kpi_row[i].metric(label, val_str)
                    else:
                        kpi_row[i].metric(label, val_str)

            # ── Comparison table ──────────────────────────────────────────────
            st.markdown("---")
            if delta_cols:
                styled = display.style.map(_color_pct, subset=delta_cols)
                st.dataframe(styled, use_container_width=True)
            else:
                st.dataframe(display, use_container_width=True)

            # ── Executive summary ─────────────────────────────────────────────
            top_rows = None
            if "Sales" in df_curr.columns and len(df_curr) > 0:
                top_rows = df_curr.nlargest(3, "Sales").to_dict("records")

            summary_text = _generate_summary(tipo, ec1[0], kc, kp or None, per_c, per_p, top_rows, lang=lang_code)

            _expander_lbl = "View Executive Summary" if lang_code == "en" else "Ver Resumen Ejecutivo del cliente"
            st.markdown("---")
            with st.expander(_expander_lbl, expanded=True):
                st.text(summary_text)

            # ── Parent Evolution — compute before export ───────────────────────
            _pe_df  = None
            _pe_err = None
            if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
                _pe_df, _pe_err = _build_parent_evolution(
                    df1, ec1, cm1, fmt1,
                    st.session_state["parent_child_map"],
                    st.session_state.get("parent_child_names", {}),
                    br_df=st.session_state.get("br_extra_df"),
                    lang=lang_code,
                )

            # ── Export ────────────────────────────────────────────────────────
            buf = _build_atom11_excel(display, kc, kp, tipo, per_c, per_p or "", delta_cols,
                                      client_name=client_name, entity_col=ec1[0], top_rows=top_rows,
                                      lang=lang_code, parent_evo_df=_pe_df)
            safe_name = per_c[:15].replace(" ", "_").replace(",", "").replace("\u2192", "-")
            st.download_button(
                label="⬇️ Descargar análisis completo — Excel con KPIs + Tabla + Resumen Ejecutivo",
                data=buf.getvalue(),
                file_name=f"atom11_{tipo.lower().replace(' ', '_')}_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="atom11_export",
                use_container_width=True,
            )

            # ── 🧬 Evolución por Parent ASIN ─────────────────────────────────
            st.markdown("---")
            st.markdown("### 🧬 Evolución por Parent ASIN")
            _t_pe = _I18N.get(lang_code, _I18N["es"])
            if "parent_child_map" not in st.session_state or not st.session_state["parent_child_map"]:
                st.info(_t_pe["pe_no_map"])
            elif _pe_err:
                st.warning(_pe_err)
            elif _pe_df is not None and not _pe_df.empty:
                st.caption(f"{len(_pe_df)} {_t_pe['pe_caption']}")
                _pe_pct_cols = [c for c in _pe_df.columns if "%" in c]
                _pe_styled = _pe_df.style.map(_color_pct, subset=_pe_pct_cols) if _pe_pct_cols else _pe_df.style
                st.dataframe(_pe_styled, use_container_width=True, hide_index=True)
                with st.expander(_t_pe["pe_expander_lbl"]):
                    st.code(_generate_parent_evo_summary(_pe_df, lang=lang_code), language=None)
            else:
                st.info(_t_pe["pe_no_rows"])

        except Exception as e:
            st.error(f"Error al procesar los archivos: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ── Business Report — mapeo activo + input opcional para marca nueva ─────
    st.markdown("---")
    st.markdown("### 📂 Mapeo Parent-Child")

    # Estado del mapeo activo
    if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
        _n_ch = len(st.session_state["parent_child_map"])
        _n_pr = len(set(st.session_state["parent_child_map"].values()))
        _src  = st.session_state.get("_cat_source_file", "archivo desconocido")
        _has_br_extra = (
            st.session_state.get("br_extra_df") is not None
            and not st.session_state["br_extra_df"].empty
        )
        _extra_note = f" · {len([c for c in _BR_OPTIONAL_COLS if c in st.session_state['br_extra_df'].columns])} métricas BR" if _has_br_extra else ""
        st.caption(f"📂 Mapeo activo: `{_src}` — {_n_pr} parents · {_n_ch} children{_extra_note}")
        _map_df = pd.DataFrame(
            [{"Child ASIN": k, "Parent ASIN": v}
             for k, v in st.session_state["parent_child_map"].items()]
        )
        _map_names = st.session_state.get("parent_child_names", {})
        if _map_names:
            _map_df["Título"] = _map_df["Child ASIN"].map(_map_names).fillna("")
        with st.expander(f"Ver mapeo completo ({len(_map_df)} children)", expanded=False):
            st.dataframe(_map_df, use_container_width=True, hide_index=True)
    else:
        st.warning(
            "No se encontró mapeo automático. "
            "Colocá el Business Report CSV en `data/business_report/` o subilo abajo."
        )

    # ── Input opcional para marca nueva ──────────────────────────────────────
    st.markdown("**¿Marca nueva?** Subí el Business Report aquí")
    _new_br_file = st.file_uploader(
        "Business Report (.csv o .xlsx)",
        type=["csv", "xlsx"],
        key="atom11_new_br",
        label_visibility="collapsed",
    )

    if _new_br_file:
        try:
            _new_bytes = _new_br_file.getvalue()
            _new_c_map, _new_n_map, _new_br_df = _parse_business_report_map(_new_br_file)

            # Actualizar mapeo en session_state
            st.session_state["parent_child_map"]   = _new_c_map
            st.session_state["parent_child_names"] = _new_n_map
            st.session_state["br_extra_df"]        = _new_br_df
            st.session_state["_cat_source_file"]   = _new_br_file.name

            _new_n_pr = len(set(_new_c_map.values()))
            _new_n_ch = len(_new_c_map)
            st.success(f"✅ Nuevo mapeo cargado: {_new_n_pr} parents · {_new_n_ch} children")

            # Proponer guardar permanentemente
            _save_ext    = os.path.splitext(_new_br_file.name)[1].lower() or ".csv"
            _save_prefix = (client_name.strip().replace(" ", "") if client_name.strip() else "Cliente")
            _save_name   = f"{_save_prefix}_Business_Report{_save_ext}"
            _save_path   = os.path.join(_BIZ_DIR, _save_name)

            st.info(
                f"¿Querés guardar este archivo en `data/business_report/` "
                f"para que quede permanente para esta marca?"
            )
            st.caption(f"Se guardaría como: `{_save_name}`")

            _btn_yes, _btn_no, _ = st.columns([1, 1, 3])

            if _btn_yes.button("💾 Sí, guardar", key="br_save_yes", use_container_width=True):
                os.makedirs(_BIZ_DIR, exist_ok=True)
                with open(_save_path, "wb") as _fout:
                    _fout.write(_new_bytes)
                st.session_state["_cat_source_file"] = _save_name
                st.success(f"✅ Guardado como `{_save_name}` en `data/business_report/`")

            if _btn_no.button("🚫 Solo esta sesión", key="br_save_no", use_container_width=True):
                st.info("Mapeo activo solo para esta sesión, no se guardó en disco.")

        except Exception as _new_e:
            st.error(f"Error al parsear el Business Report: {_new_e}")

if selected == "🛡️ Reportes MerchanSpring":
    st.header("🛡️ Reportes MerchanSpring")
    st.caption("Subí el reporte semanal de MerchanSpring (.xlsx o .pdf) para ver el dashboard y exportar el informe profesional.")
    st.divider()

    ms_client = st.text_input(
        "Nombre del cliente (aparece en el Excel)",
        placeholder="Ej: Love To Dream",
        key="ms_client",
    )
    ms_file = st.file_uploader(
        "Arrastrá el archivo MerchanSpring (.xlsx o .pdf)",
        type=["xlsx", "pdf"],
        key="ms_upload",
    )

    if ms_file:
        try:
            is_pdf = ms_file.name.lower().endswith(".pdf")

            if is_pdf:
                ms_data = _parse_merchanspring_pdf(ms_file)
            else:
                ms_data = _parse_merchanspring(ms_file)

            st.markdown(f"### {ms_data.get('title', '')}")
            st.caption(ms_data.get("period", ""))

            # ── KPI cards ────────────────────────────────────────────────
            kpis = ms_data.get("kpis", [])
            if kpis:
                _ms_chunk_size = 4
                for _ms_start in range(0, len(kpis), _ms_chunk_size):
                    _ms_chunk = kpis[_ms_start:_ms_start + _ms_chunk_size]
                    kpi_cols = st.columns(len(_ms_chunk))
                    for ki, kpi in enumerate(_ms_chunk):
                        delta_str = kpi["delta"].replace("vs prior: ", "")
                        with kpi_cols[ki]:
                            st.metric(label=kpi["name"], value=kpi["val"], delta=delta_str)

            st.divider()

            if is_pdf:
                # ── Section detection log ──────────────────────────────────
                _slog = ms_data.get("sections_log", [])
                if _slog:
                    _all_ok  = all(ic == "✅" for ic, _, _ in _slog)
                    _has_err = any(ic == "❌" for ic, _, _ in _slog)
                    _exp_icon = "✅" if _all_ok else ("❌" if _has_err else "⚠️")
                    with st.expander(f"{_exp_icon} Secciones detectadas en el PDF ({len(_slog)} analizadas)", expanded=_has_err):
                        for _ic, _sec, _det in _slog:
                            st.markdown(f"{_ic} &nbsp; **{_sec}** — {_det}")

                # ── PDF dashboard ─────────────────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventory & Health", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Productos más vendidos en el período")
                    df = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No se encontraron datos de top sellers.")

                with ms_t2:
                    st.warning("⚠️ Advertising no conectado en MerchantSpring")
                    st.info(
                        "Para ver datos de advertising, conectá tu cuenta de Amazon Ads en MerchantSpring:\n\n"
                        "**MerchantSpring → Settings → Integrations → Amazon Advertising**\n\n"
                        "Una vez conectado, los datos aparecerán automáticamente en el próximo reporte."
                    )

                with ms_t3:
                    # Inventario
                    df = ms_data.get("inv_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.caption("Inventario de productos")
                        style = df.style
                        if "Stock Status" in df.columns:
                            style = style.map(_s_stock, subset=["Stock Status"])
                        st.dataframe(style, use_container_width=True, hide_index=True)
                    st.divider()
                    # P&L métricas
                    pnl_m_tab = ms_data.get("pnl_metrics", {})
                    if pnl_m_tab:
                        m_cols = st.columns(4)
                        for i, (k, v) in enumerate(pnl_m_tab.items()):
                            with m_cols[i]:
                                st.metric(label=k, value=v)
                    pnl_df_tab = ms_data.get("pnl_df", pd.DataFrame())
                    if not pnl_df_tab.empty:
                        st.caption("P&L — Estado de Resultados")
                        st.dataframe(pnl_df_tab, use_container_width=True, hide_index=True)
                    pp_df_tab = ms_data.get("prod_profit_df", pd.DataFrame())
                    if not pp_df_tab.empty:
                        st.caption("Rentabilidad por producto")
                        st.dataframe(pp_df_tab, use_container_width=True, hide_index=True)
                    st.divider()
                    # Health
                    health_tab = ms_data.get("health_data", {})
                    if health_tab:
                        st.caption("Salud del Catálogo")
                        h_cols = st.columns(3)
                        for i, (k, v) in enumerate(health_tab.items()):
                            with h_cols[i % 3]:
                                st.metric(label=k, value=v)

                with ms_t4:
                    st.caption("Comparación semana a semana — Sales y Units disponibles desde PDF. TACoS / Ad Sales / Ad Spend requieren conexión de Amazon Ads.")
                    sum_wow = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not sum_wow.empty:
                        def _pw(tw, ws):
                            try:
                                p = float(str(ws).replace("%","").replace("+","").strip())
                                d = 1 + p / 100
                                if d == 0: return "-"
                                v = float(str(tw).replace("$","").replace(",","").strip())
                                return round(v / d, 2) if v else "-"
                            except: return "-"
                        wow_rows = []
                        for _, r in sum_wow.iterrows():
                            wow_rows.append({
                                "Product":            r.get("Product",""),
                                "ASIN":               r.get("ASIN",""),
                                "Sales (This Week)":  r.get("Total Sales ($)",""),
                                "Sales (Prior Week)": _pw(r.get("Total Sales ($)",0), r.get("Sales WoW (%)","−")),
                                "Sales Δ %":          r.get("Sales WoW (%)","-"),
                                "Units (This Week)":  r.get("Units Sold",""),
                                "Units (Prior Week)": _pw(r.get("Units Sold",0), r.get("Units WoW (%)","−")),
                                "Units Δ %":          r.get("Units WoW (%)","-"),
                                "Sessions":           "-",
                                "CVR":                "-",
                                "TACoS":              "—",
                                "Ad Sales":           "—",
                                "Organic Sales":      r.get("Total Sales ($)",""),
                                "Ad Spend":           "—",
                                "Profit Δ %":         "-",
                            })
                        wow_display = pd.DataFrame(wow_rows)
                        delta_cols_wow = ["Sales Δ %", "Units Δ %"]
                        style_wow = wow_display.style
                        for dc in delta_cols_wow:
                            if dc in wow_display.columns:
                                style_wow = style_wow.map(_s_delta, subset=[dc])
                        st.dataframe(style_wow, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay datos de WoW disponibles.")

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_ms_pdf_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export_pdf",
                    use_container_width=True,
                )

            else:
                # ── Excel dashboard (original) ────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventario & Salud", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Tabla de productos — resumen de la semana analizada")
                    df = ms_data["summary_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "TACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["TACoS (%)"])
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t2:
                    st.caption("Análisis de publicidad por producto")
                    df = ms_data["adv_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "Ad Efficiency" in df.columns:
                        style = style.map(_s_eff, subset=["Ad Efficiency"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t3:
                    st.caption("Inventario y salud del producto")
                    df = ms_data["inv_df"].copy()
                    style = df.style
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    if "Stock Status" in df.columns:
                        style = style.map(_s_stock, subset=["Stock Status"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t4:
                    st.caption("Comparación semana a semana por producto")
                    df = ms_data["wow_df"].copy()
                    delta_cols = [c for c in df.columns if c.endswith("|Δ %")]
                    style = df.style
                    if delta_cols:
                        style = style.map(_s_delta, subset=delta_cols)
                    st.dataframe(style, use_container_width=True, hide_index=True)

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_merchanspring_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export",
                    use_container_width=True,
                )

        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            import traceback
            st.code(traceback.format_exc())