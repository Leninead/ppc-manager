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

st.set_page_config(page_title="PPC Manager", layout="wide")


if "parent_child_map" not in st.session_state:
    _auto_load_business_report_map()


if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "🏠 Inicio"

def _nav(page):
    st.session_state["selected_page"] = page

with st.sidebar:
    st.title("🦫 Capybaras Agency OS")
    st.caption("PPC Manager — v1.0")
    st.divider()

    st.button("🏠 Inicio", use_container_width=True, on_click=_nav, args=("🏠 Inicio",), key="nav_home")

    st.markdown("**📊 Análisis**")
    for _pg in ["📊 Search Term Report", "🔍 Search Query Performance", "📁 Bulk Campañas", "💰 Business Report"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔗 Cruce y Tendencias**")
    for _pg in ["🔗 Análisis Cruzado STR vs SQP", "📈 Tendencia Multi-Semana"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔺 Automatización**")
    st.button("🔻 Análisis de Funnel", use_container_width=True, on_click=_nav, args=("🔻 Análisis de Funnel",), key="nav_funnel")

    st.markdown("**📋 Reportes**")
    for _pg in ["🔬 Reportes Atom 11", "🛡️ Reportes MerchanSpring"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    _n_pe_parents = len(set(st.session_state.get("parent_child_map", {}).values()))
    _pe_label = (
        f"🧬 Parent-Child: {_n_pe_parents} parents cargados"
        if _n_pe_parents > 0 else
        "⚠️ Sin mapeo — agregá Business Report a data/business_report/"
    )
    _pe_color = "#4caf50" if _n_pe_parents > 0 else "#ff9800"
    st.markdown(
        "<div style='margin-top:2rem;font-size:0.72rem;color:#888;'>"
        "Desarrollado por Lenin Acosta · Capybaras Agency · 2026"
        "</div>"
        f"<div style='font-size:0.72rem;color:{_pe_color};margin-top:0.35rem;'>"
        f"{_pe_label}"
        "</div>",
        unsafe_allow_html=True,
    )

selected = st.session_state["selected_page"]

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
