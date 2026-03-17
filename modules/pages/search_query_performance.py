import streamlit as st

from core.helpers import read_sqp


def render():
    st.header("🔍 Search Query Performance")
    st.caption("Datos de rendimiento de búsqueda orgánica exportados desde Amazon Brand Analytics.")
    st.divider()
    file_sqp = st.file_uploader("Sube tu SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp")
    if file_sqp:
        df = read_sqp(file_sqp)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)
