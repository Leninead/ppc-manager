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
from modules.pages.search_term_report import render as _render_str
from modules.pages.search_query_performance import render as _render_sqp
from modules.pages.bulk_campanas import render as _render_bulk
from modules.pages.business_report import render as _render_br
from modules.pages.analisis_cruzado import render as _render_cruzado
from modules.pages.tendencia_multisemana import render as _render_tendencia
from modules.pages.analisis_funnel import render as _render_funnel
from modules.pages.atom11 import render as _render_atom11
from modules.pages.merchanspring import render as _render_ms
from modules.pages.weekly_client_report import render as render_weekly
from modules.pages.bid_optimizer import render as render_bid_optimizer
from modules.pages.campaign_builder import render as render_campaign_builder
from modules.pages.atom11_rules_builder import render as render_atom11_rules
from modules.pages.listing_compliance import render as render_listing_compliance
from modules.pages.listing_monitor import render as render_listing_monitor
from modules.pages.account_pulse import render as render_account_pulse
from modules.pages.ppc_forecast import render as render_ppc_forecast
from modules.pages.ppc_insights import render as render_ppc_insights
from modules.pages.ppc_audit import render as render_ppc_audit
from modules.pages.datadive_analyzer import render as render_datadive
from modules.pages.helium10_analyzer import render as render_helium10
from modules.pages.sbh_recommendation import render as render_sbh
from modules.pages.knowledge_base import render as render_knowledge
from modules.pages.gamboa_generator import render as render_gamboa_generator
from modules.pages.variation_builder import render as render_variation_builder
from modules.pages.flat_file_migrator import render as render_flat_file_migrator
from modules.pages.sku_progress_report import render as render_sku_progress
from modules.pages.pricing_dashboard import render as render_pricing_dashboard
from modules.pages.proposal_studio import render as render_proposal_studio
from modules.pages.case_study_studio import render as render_case_study_studio
from modules.pages.revenue_forecast import render as render_revenue_forecast
import streamlit_authenticator as stauth

st.set_page_config(page_title="Agency OS", layout="wide")

st.markdown("""
<style>
/* ── Sidebar fondo oscuro ─────────────────────────────────────── */
[data-testid="stSidebar"] {
    background-color: #1A1A1A !important;
    min-width: 180px !important;
    max-width: 180px !important;
}

/* ── Texto del sidebar ────────────────────────────────────────── */
[data-testid="stSidebar"] * {
    color: #CCCCCC !important;
}

/* ── Botones del sidebar ──────────────────────────────────────── */
[data-testid="stSidebar"] button {
    background-color: transparent !important;
    border: none !important;
    border-radius: 6px !important;
    color: #CCCCCC !important;
    font-size: 0.78rem !important;
    padding: 0.3rem 0.5rem !important;
    text-align: left !important;
    width: 100% !important;
    transition: background 0.15s ease !important;
}

[data-testid="stSidebar"] button:hover {
    background-color: #2A2A2A !important;
    color: #FFFFFF !important;
}

/* ── Labels de sección (markdown bold) ───────────────────────── */
[data-testid="stSidebar"] .stMarkdown p {
    color: #888888 !important;
    font-size: 0.68rem !important;
    font-weight: 700 !important;
    letter-spacing: 0.08em !important;
    text-transform: uppercase !important;
    margin: 0.75rem 0 0.25rem 0.5rem !important;
}

/* ── Labels custom HTML en sidebar ───────────────────────────── */
[data-testid="stSidebar"] .stMarkdown div {
    color: #E84000 !important;
    font-size: 0.85rem !important;
    font-weight: 800 !important;
}

/* ── Divider ──────────────────────────────────────────────────── */
[data-testid="stSidebar"] hr {
    border-color: #333333 !important;
    margin: 0.5rem 0 !important;
}

/* ── Título/caption del sidebar ───────────────────────────────── */
[data-testid="stSidebar"] h1,
[data-testid="stSidebar"] h2,
[data-testid="stSidebar"] h3 {
    color: #E84000 !important;
    font-size: 0.85rem !important;
}

/* ── Footer del sidebar ───────────────────────────────────────── */
[data-testid="stSidebar"] div[style*="margin-top:2rem"] {
    color: #555555 !important;
}

/* ── Ocultar el collapse arrow del sidebar ────────────────────── */
[data-testid="stSidebarCollapseButton"] {
    display: none !important;
}

/* ── Área principal — quitar padding excesivo ─────────────────── */
[data-testid="stAppViewContainer"] > .main {
    padding-left: 1rem !important;
}

/* ── Expanders del sidebar ──────────────────────────────────── */
[data-testid="stSidebar"] details {
    background-color: transparent !important;
    border: none !important;
    margin-bottom: 0 !important;
}

[data-testid="stSidebar"] details summary {
    color: #E84000 !important;
    font-size: 0.82rem !important;
    font-weight: 800 !important;
    letter-spacing: 0.05em !important;
    padding: 0.4rem 0.5rem !important;
}

[data-testid="stSidebar"] details summary:hover {
    color: #FF6B00 !important;
}
</style>
""", unsafe_allow_html=True)

# ── Autenticación ──────────────────────────────────────────────────
# Excepción que lanza st.secrets si falta secrets.toml. En streamlit 1.43.2 es
# FileNotFoundError; versiones nuevas pueden usar StreamlitSecretNotFoundError.
# Import defensivo: cubrimos ambas sin romper si la clase no existe en esta versión.
try:
    from streamlit.errors import StreamlitSecretNotFoundError as _SecretNotFound
    _SECRET_ERRORS = (FileNotFoundError, KeyError, _SecretNotFound)
except ImportError:
    _SECRET_ERRORS = (FileNotFoundError, KeyError)

# Bypass de login para soak local. Default = auth ON. Cloud nunca setea esta var.
_LOCAL_MODE = os.environ.get("AGENCY_OS_LOCAL_MODE") == "1"

if _LOCAL_MODE:
    _authenticator = None
    _name, _auth_status, _username = "Local Dev", True, "local"
    st.sidebar.warning("🔓 Modo local — login desactivado (AGENCY_OS_LOCAL_MODE=1)")
else:
    try:
        _creds = st.secrets["credentials"].to_dict()
        _cookie = st.secrets["cookie"]
    except _SECRET_ERRORS:
        st.error(
            "❌ Falta `.streamlit/secrets.toml` o sus claves `credentials`/`cookie`. "
            "Copiá `secrets.toml.example` → `secrets.toml` y completá tus credenciales, "
            "o corré en modo local con la variable de entorno `AGENCY_OS_LOCAL_MODE=1`."
        )
        st.stop()
    _authenticator = stauth.Authenticate(
        _creds,
        _cookie["name"],
        _cookie["key"],
        int(_cookie["expiry_days"]),
    )
    _name, _auth_status, _username = _authenticator.login(
        fields={
            "Form name": "🦫 Agency OS",
            "Username": "Usuario",
            "Password": "Contraseña",
            "Login": "Ingresar",
        }
    )
    if _auth_status is False:
        st.error("❌ Usuario o contraseña incorrectos")
        st.stop()
    elif _auth_status is None:
        st.stop()
# ── Fin auth ───────────────────────────────────────────────────────


if "parent_child_map" not in st.session_state:
    _auto_load_business_report_map()


if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "🏠 Inicio"

def _nav(page):
    st.session_state["selected_page"] = page

with st.sidebar:
    if _authenticator is not None:
        _authenticator.logout("↩ Cerrar sesión", "sidebar")
    st.caption(f"👤 {_name}")
    st.divider()
    st.markdown(
        "<div style='padding:0.75rem 0.5rem 0.25rem;'>"
        "<span style='font-size:1.4rem;'>🦫</span>"
        "<span style='font-size:0.75rem;font-weight:800;color:#E84000;"
        "margin-left:0.4rem;vertical-align:middle;'>Agency OS</span>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    st.button("🏠 Inicio", use_container_width=True, on_click=_nav,
              args=("🏠 Inicio",), key="nav_home")

    with st.expander("📊 PPC", expanded=True):
        for _pg in [
            "📊 Search Term Report",
            "🔍 Search Query Performance",
            "🔗 Análisis Cruzado STR vs SQP",
            "📈 Tendencia Multi-Semana",
            "📁 Bulk Campañas",
            "💰 Business Report",
            "🔻 Análisis de Funnel",
            "🧠 Bid Optimizer",
            "🚀 Campaign Builder",
            "⚙️ Atom11 Rules Builder",
        ]:
            st.button(_pg, use_container_width=True, on_click=_nav,
                      args=(_pg,), key=f"nav_{_pg}")

    with st.expander("🔬 RESEARCH", expanded=False):
        for _pg in [
            "🧲 DataDive Analyzer",
            "🧲 Helium 10 Analyzer",
            "📢 SBH Recommendation",
            "🔎 PPC Insights",
            "📈 PPC Forecast",
            "🛡️ PPC Audit",
            "📊 Account Pulse",
        ]:
            st.button(_pg, use_container_width=True, on_click=_nav,
                      args=(_pg,), key=f"nav_{_pg}")

    with st.expander("👥 ACCOUNT", expanded=False):
        for _pg in [
            "🔬 Reportes Atom 11",
            "🛡️ Reportes MerchanSpring",
            "📊 Weekly Client Report",
            "👁️ Listing Monitor",
            "🛡️ Listing Compliance",
            "📊 Gamboa Generator",
            "🧬 Variation Builder",
            "📈 Revenue Forecast",
        ]:
            st.button(_pg, use_container_width=True, on_click=_nav,
                      args=(_pg,), key=f"nav_{_pg}")

    with st.expander("📋 SALES DIRECTOR", expanded=False):
        st.button("📋 Proposal Studio", use_container_width=True, on_click=_nav,
                  args=("📋 Proposal Studio",), key="nav_📋 Proposal Studio")
        st.button("🏆 Case Study Studio", use_container_width=True, on_click=_nav,
                  args=("🏆 Case Study Studio",), key="nav_🏆 Case Study Studio")

    with st.expander("📚 KNOWLEDGE", expanded=False):
        st.button("📚 Knowledge Base", use_container_width=True, on_click=_nav,
                  args=("📚 Knowledge Base",), key="nav_📚 Knowledge Base")

    with st.expander("🏥 ACCOUNT HEALTH", expanded=False):
        st.button("🗂️ Flat File Migrator", use_container_width=True, on_click=_nav,
                  args=("🗂️ Flat File Migrator",), key="nav_🗂️ Flat File Migrator")
        st.button("🏥 SKU Progress Report", use_container_width=True, on_click=_nav,
                  args=("🏥 SKU Progress Report",), key="nav_🏥 SKU Progress Report")
        st.button("💲 Pricing Dashboard", use_container_width=True, on_click=_nav,
                  args=("💲 Pricing Dashboard",), key="nav_💲 Pricing Dashboard")

    _n_pe_parents = len(set(st.session_state.get("parent_child_map", {}).values()))
    _pe_label = (
        f"🧬 {_n_pe_parents} parents"
        if _n_pe_parents > 0 else "⚠️ Sin mapeo"
    )
    _pe_color = "#4caf50" if _n_pe_parents > 0 else "#ff9800"
    st.markdown(
        "<div style='margin-top:2rem;padding:0 0.5rem;'>"
        "<div style='font-size:0.78rem;font-weight:600;color:#AAAAAA;"
        "line-height:1.6;'>Desarrollado por<br>"
        "<span style='color:#E84000;font-weight:800;font-size:0.85rem;'>"
        "Lenin Acosta</span><br>"
        "<span style='color:#777777;'>Capybaras Agency · 2026</span></div>"
        f"<div style='font-size:0.72rem;color:{_pe_color};"
        f"margin-top:0.4rem;'>{_pe_label}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

selected = st.session_state["selected_page"]

if _LOCAL_MODE:
    st.warning("🔓 MODO LOCAL — login desactivado. No usar en producción.")

if selected == "🏠 Inicio":
    _render_inicio()

if selected == "📊 Search Term Report":
    _render_str()

if selected == "🔍 Search Query Performance":
    _render_sqp()

if selected == "📁 Bulk Campañas":
    _render_bulk()

if selected == "💰 Business Report":
    _render_br()

if selected == "🔗 Análisis Cruzado STR vs SQP":
    _render_cruzado()

if selected == "📈 Tendencia Multi-Semana":
    _render_tendencia()


if selected == "🔻 Análisis de Funnel":
    _render_funnel()

if selected == "🔬 Reportes Atom 11":
    _render_atom11()

if selected == "🛡️ Reportes MerchanSpring":
    _render_ms()

if selected == "📊 Weekly Client Report":
    render_weekly()

if selected == "🧠 Bid Optimizer":
    render_bid_optimizer()

if selected == "🚀 Campaign Builder":
    render_campaign_builder()

if selected == "⚙️ Atom11 Rules Builder":
    render_atom11_rules()

if selected == "👁️ Listing Monitor":
    render_listing_monitor()

if selected == "🧲 DataDive Analyzer":
    render_datadive()

if selected == "🧲 Helium 10 Analyzer":
    render_helium10()

if selected == "📢 SBH Recommendation":
    render_sbh()

if selected == "🔎 PPC Insights":
    render_ppc_insights()

if selected == "📈 PPC Forecast":
    render_ppc_forecast()

if selected == "🛡️ PPC Audit":
    render_ppc_audit()

if selected == "📊 Account Pulse":
    render_account_pulse()

if selected == "📚 Knowledge Base":
    render_knowledge(_name, _username)

if selected == "🛡️ Listing Compliance":
    render_listing_compliance()

if selected == "📊 Gamboa Generator":
    render_gamboa_generator()

if selected == "🧬 Variation Builder":
    render_variation_builder()

if selected == "🗂️ Flat File Migrator":
    render_flat_file_migrator()

if selected == "🏥 SKU Progress Report":
    render_sku_progress()

if selected == "💲 Pricing Dashboard":
    render_pricing_dashboard()

if selected == "📋 Proposal Studio":
    render_proposal_studio()

if selected == "🏆 Case Study Studio":
    render_case_study_studio()

if selected == "📈 Revenue Forecast":
    render_revenue_forecast()
