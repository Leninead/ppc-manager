import io

import streamlit as st
import pandas as pd

from core.helpers import read_sqp, extract_sqp_brand


def render():
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
