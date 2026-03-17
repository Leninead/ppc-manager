import streamlit as st
import pandas as pd


def render():
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
