import streamlit as st
import pandas as pd


def render():
    st.header("📁 Bulk File de Campañas")
    st.caption("Archivo bulk exportado desde Amazon Ads con todas las campañas, grupos y keywords.")
    st.divider()
    file_bulk = st.file_uploader("Sube tu Bulk (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk")
    if file_bulk:
        df = pd.read_excel(file_bulk) if file_bulk.name.endswith(".xlsx") else pd.read_csv(file_bulk)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)
