import streamlit as st
import pandas as pd


def render():
    st.header("💰 Business Report")
    st.caption("Reporte de ventas y sesiones exportado desde Amazon Seller Central.")
    st.divider()
    file_br = st.file_uploader("Sube tu Business Report (.xlsx o .csv)", type=["xlsx", "csv"], key="br")
    if file_br:
        df = pd.read_excel(file_br) if file_br.name.endswith(".xlsx") else pd.read_csv(file_br)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)
