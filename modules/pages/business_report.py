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
    file_br = st.file_uploader("Sube tu Business Report (.xlsx o .csv)", type=["xlsx", "csv"], key="br")
    if file_br:
        df = _load_br(file_br.getvalue(), file_br.name)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)
