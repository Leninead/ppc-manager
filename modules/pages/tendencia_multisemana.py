import io
import hashlib

import streamlit as st
import pandas as pd

from core.helpers import read_sqp


def render():
    st.header("📈 Tendencia de Impresiones Multi-Semana")
    st.caption("Compará hasta 4 semanas de SQP para identificar keywords en alza, estables o en caída.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Ver evolución de queries a lo largo de 2-4 semanas para detectar estacionalidades y cambios de demanda.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("2 a 4 archivos SQP de semanas distintas (.xlsx) — Brand Analytics → Search Query Performance.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Bulk Campañas (M6) para ver cómo responden las campañas a esas tendencias.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí entre 2 y 4 SQPs\n"
            "2. Confirmá el orden cronológico\n"
            "3. Revisá pivot por Search Query con tendencias ↑ → ↓\n"
            "4. Filtrá por threshold de cambio (10% default)\n"
            "5. Descargá el Excel con tendencias"
        )

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

        # Detectar archivos duplicados por hash
        seen_hashes = {}
        unique_files = []
        for f in sqp_files:
            f.seek(0)
            file_hash = hashlib.md5(f.read()).hexdigest()
            f.seek(0)
            if file_hash in seen_hashes:
                st.warning(f"⚠️ \"{f.name}\" es idéntico a \"{seen_hashes[file_hash]}\" — se omite.")
            else:
                seen_hashes[file_hash] = f.name
                unique_files.append(f)
        sqp_files = unique_files

        if len(sqp_files) < 2:
            st.warning("Necesitás al menos 2 archivos distintos para ver la tendencia.")
            return

        weeks = []
        used_labels = set()
        for f in sqp_files:
            df_w = read_sqp(f)
            df_w = df_w.drop_duplicates(subset=[sqp_col_t] if sqp_col_t in df_w.columns else None)
            df_w[sqp_col_t] = df_w[sqp_col_t].str.lower().str.strip()
            if imp_col_t in df_w.columns:
                df_w[imp_col_t] = pd.to_numeric(df_w[imp_col_t], errors="coerce").fillna(0)
            # Extraer fecha desde Reporting Date o nombre de archivo
            label = None
            if "Reporting Date" in df_w.columns:
                label = str(df_w["Reporting Date"].dropna().iloc[0]) if not df_w["Reporting Date"].dropna().empty else f.name
            else:
                label = f.name
            # Desambiguar labels duplicados
            base_label = label
            suffix = 2
            while label in used_labels:
                label = f"{base_label} ({suffix})"
                suffix += 1
            used_labels.add(label)
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
            key="tendencia_dl",
        )
    elif len(sqp_files) == 1:
        st.warning("Subí al menos 2 semanas para ver la tendencia.")
