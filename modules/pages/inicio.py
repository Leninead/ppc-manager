import streamlit as st


def render():
    st.title("🦫 Capybaras Agency OS")
    st.subheader("PPC Manager — v1.0")
    st.divider()
    st.markdown("### Módulos disponibles")

    _HOME_MODULES = [
        ("📊", "Search Term Report",         "✅ activo"),
        ("🔍", "Search Query Performance",    "✅ activo"),
        ("📁", "Bulk Campañas",               "✅ activo"),
        ("💰", "Business Report",             "✅ activo"),
        ("🔗", "Análisis Cruzado STR vs SQP", "✅ activo"),
        ("📈", "Tendencia Multi-Semana",       "✅ activo"),
        ("🔻", "Análisis de Funnel",           "✅ activo"),
        ("🔬", "Reportes Atom 11",             "✅ activo"),
        ("🛡️", "Reportes MerchanSpring",       "✅ activo"),
    ]

    _cols = st.columns(3)
    for i, (emoji, nombre, estado) in enumerate(_HOME_MODULES):
        with _cols[i % 3]:
            st.markdown(
                f"<div style='border:1px solid #ddd;border-radius:10px;padding:1rem;margin-bottom:0.75rem;'>"
                f"<div style='font-size:2rem;'>{emoji}</div>"
                f"<div style='font-weight:600;margin:0.3rem 0;'>{nombre}</div>"
                f"<div style='font-size:0.85rem;'>{estado}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
