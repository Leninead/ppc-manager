import io

import streamlit as st
import pandas as pd


@st.cache_data
def _load_br(data, name):
    """Cached reader for Business Report files."""
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


def render():
    st.header("💰 Business Report")
    st.caption("Reporte de ventas y sesiones exportado desde Amazon Seller Central.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Ver ventas, sesiones, CVR y BuyBox por ASIN. Es la fuente del Parent-Child map.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Business Report → Seller Central → Reports → Business Reports → By Date o By ASIN (.csv).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Análisis de Funnel (M8) para detectar brechas de cobertura por ASIN.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el BR (By Date o By ASIN)\n"
            "2. Revisá métricas por ASIN (Sales, Sessions, CVR, BuyBox)\n"
            "3. Identificá ASINs con CVR bajo o BuyBox < 80%\n"
            "4. Guardá el BR en `data/business_report/` para cargar Parent-Child automáticamente\n"
            "5. Descargá el resumen si hace falta"
        )

    file_br = st.file_uploader("Sube tu Business Report (.xlsx o .csv)", type=["xlsx", "csv"], key="br")
    if file_br:
        df = _load_br(file_br.getvalue(), file_br.name)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)
