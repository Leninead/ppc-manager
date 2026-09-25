import streamlit as st
import pandas as pd
import io
import os
from html import escape as _escape
import re

from core.i18n import _I18N
from core import navigation
from core.chat import app_chat
from core.integrations.notice import accounts_needing_reauth, sync_alert_counts
from core.ui import sidebar as _sidebar
from core.ui import i18n
from core.constants import _BR_OPTIONAL_COLS, _PAGES
from core.helpers import _color_pct, extract_sqp_brand, read_sqp
from core.business_report.parser import _BIZ_DIR, _parse_business_report_map, _auto_load_business_report_map
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
from modules.pages.supply_proveedores import render as render_supply_proveedores
from modules.pages.supply_ordenes import render as render_supply_ordenes
from modules.pages.proposal_studio import render as render_proposal_studio
from modules.pages.case_study_studio import render as render_case_study_studio
from modules.pages.revenue_forecast import render as render_revenue_forecast
from modules.pages.sop_library import render as render_sop_library
from modules.mercado_libre.main import render as render_mercado_libre
from modules.pages.agency_dashboard_page import render as render_agency_dashboard
from modules.pages.accounts import render as render_accounts
from modules.pages.integrations import render as render_integrations
from modules.pages.chat_skills_page import render as render_chat_skills
from modules.pages.request_log import render as render_request_log
from core.integrations.roles import is_admin as _role_is_admin
from core.integrations.roles import resolve_role as _resolve_role
import streamlit_authenticator as stauth

st.set_page_config(page_title="Agency OS", layout="wide")

st.markdown(_sidebar.SIDEBAR_CSS, unsafe_allow_html=True)

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
    st.sidebar.caption(i18n.t("shell.local_mode.sidebar_caption"))
else:
    try:
        _creds = st.secrets["credentials"].to_dict()
        _cookie = st.secrets["cookie"]
    except _SECRET_ERRORS:
        st.error(i18n.t("shell.auth.secrets_missing"))
        st.stop()
    _authenticator = stauth.Authenticate(
        _creds,
        _cookie["name"],
        _cookie["key"],
        int(_cookie["expiry_days"]),
    )
    # The dict keys are the library's field ids, not copy: only the values
    # they map to are shown. The login screen is drawn before the sidebar
    # exists, so `app_lang` is unset here and this renders in Spanish — the
    # catalog's fallback, not an accident.
    _name, _auth_status, _username = _authenticator.login(
        fields={
            "Form name": i18n.t("shell.login.form_name"),
            "Username": i18n.t("shell.login.username"),
            "Password": i18n.t("shell.login.password"),
            "Login": i18n.t("shell.login.submit"),
        }
    )
    if _auth_status is False:
        st.error(i18n.t("shell.login.bad_credentials"))
        st.stop()
    elif _auth_status is None:
        st.stop()
# ── Fin auth ───────────────────────────────────────────────────────

# Resolved server-side on every run, never read from the cookie or from
# session_state: any of the 33 modules could write that key.
_role = _resolve_role(_username)
# Derived once here and passed down to the rail: recomputing it per button
# would call into `st.secrets` on every destination, every rerun.
_is_admin = _role_is_admin(_role)


if "parent_child_map" not in st.session_state:
    _auto_load_business_report_map()


if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "🏠 Inicio"

def _go_to(page):
    st.session_state["selected_page"] = page


def _nav_type(page):
    """`primary` marks the active page: without this, 33 destinations look identical."""
    return "primary" if st.session_state.get("selected_page") == page else "secondary"


# Both Sistema screens carry the dot: Integraciones is admin-only, and the
# Reautorizar button lives on Cuentas conectadas, where every employee can act.
_REAUTH_NOTICE_PAGES = ("🔌 Integraciones", "🔑 Cuentas conectadas")


def _nav_label(page: str) -> str:
    """Visible text for a destination: no emoji, plus an amber dot on the two
    Sistema screens when an authorization has stopped working or is about to,
    and a red or amber dot on the request log when the sync has open alerts."""
    label = navigation.visible_label(page)
    if page in _REAUTH_NOTICE_PAGES and accounts_needing_reauth():
        return f"{label} :orange[●]"
    # Checked only for admins: the page is hidden from everyone else, and the count costs a read.
    if page == navigation.REQUEST_LOG and _is_admin:
        errors, warnings = sync_alert_counts()
        if errors:
            return f"{label} :red[●]"
        if warnings:
            return f"{label} :orange[●]"
    return label


def _nav_button(page: str) -> None:
    """The label is what the user sees; `page` is the routing key and never changes."""
    st.button(
        _nav_label(page),
        icon=navigation.icon_for(page),
        use_container_width=True,
        on_click=_go_to,
        type=_nav_type(page),
        args=(page,),
        key=f"nav_{page}",
    )


with st.sidebar:
    if _authenticator is not None:
        _authenticator.logout(i18n.t("shell.sidebar.logout"), "sidebar")
    st.caption(f"👤 {_name}")
    # La marca subió a la fila del botón de colapsar (core/ui/sidebar.py), que
    # Streamlit deja vacía. Este bloque y su segundo divisor gastaban ~90px de
    # alto para repetir el nombre que ya está en la pestaña del navegador.
    st.divider()

    # Search replaces the whole rail while text is typed: filtering inside
    # closed expanders hides exactly what's being searched for.
    _search = st.text_input(
        i18n.t("shell.sidebar.search_label"),
        key="nav_search",
        placeholder=i18n.t("shell.sidebar.search_placeholder"),
        label_visibility="collapsed",
    ).strip()

    if _search:
        _hits = navigation.filter_pages(_search, _is_admin)
        for _page in _hits:
            _nav_button(_page)
        if not _hits:
            st.markdown(
                f"<div class='sb-no-results'>"
                f"{i18n.t('shell.sidebar.search_no_results')}</div>",
                unsafe_allow_html=True,
            )
    else:
        _nav_button(navigation.HOME)
        for _section in navigation.SECTIONS:
            # Count and buttons both come from the filtered tuple: reading the
            # count off `_section.pages` is what captioned "Sistema 2" over a
            # single button. A section left empty by the filter is skipped
            # outright — an expander that opens onto nothing reads as a bug.
            _pages = navigation.visible_pages(_section, _is_admin)
            if not _pages:
                continue
            with st.expander(
                f"{navigation.section_label(_section.title)} "
                f":gray[{len(_pages)}]",
                expanded=_section.open_by_default,
                icon=_section.icon,
            ):
                for _page in _pages:
                    _nav_button(_page)

    # Interface language + output language of the AI tabs, on one key that
    # `core.ui.i18n` and `core.ai_tab.app_language()` both read.
    #
    # Every argument here is language-invariant ON PURPOSE. Streamlit builds a
    # widget's identity from its own arguments — radio.py feeds `label`, the
    # format_func'd `options` and `help` into the element id. Translating any of
    # them changes the id on the run right after the click, which orphans the
    # stored value: the widget falls back to its default and writes "Español"
    # back over the choice, so the toggle bounced. The translated label is drawn
    # above instead, and the options are endonyms — a language names itself, the
    # way every language picker does.
    st.markdown(
        f"<p title='{_escape(i18n.t('shell.sidebar.ai_lang_help'), quote=True)}'>"
        f"{_escape(i18n.t('shell.sidebar.ai_lang_label'))}</p>",
        unsafe_allow_html=True,
    )
    st.radio(
        "Idioma / Language",          # constant: collapsed, read by screen readers only
        ("Español", "English"),
        horizontal=True,
        key="app_lang",
        label_visibility="collapsed",
    )

    _n_pe_parents = len(set(st.session_state.get("parent_child_map", {}).values()))
    _pe_label = (
        i18n.t("shell.sidebar.parent_child_ok", n=_n_pe_parents)
        if _n_pe_parents > 0 else i18n.t("shell.sidebar.parent_child_missing")
    )
    _pe_clase = "sb-salud-ok" if _n_pe_parents > 0 else "sb-salud-alerta"
    st.markdown(
        "<div style='margin-top:2rem;padding:0 0.5rem;'>"
        "<div class='sb-pie' style='line-height:1.6;'>"
        f"{i18n.t('shell.sidebar.footer_developed_by')}<br>"
        f"<span class='sb-marca'>{i18n.t('shell.sidebar.footer_author')}</span><br>"
        "<span class='sb-pie-tenue'>"
        f"{i18n.t('shell.sidebar.footer_agency')}</span></div>"
        f"<div class='{_pe_clase}' style='font-size:0.72rem;margin-top:0.4rem;'>"
        f"{_pe_label}</div>"
        "</div>",
        unsafe_allow_html=True,
    )

selected = st.session_state["selected_page"]

if _LOCAL_MODE:
    st.warning(i18n.t("shell.local_mode.banner"))

if selected == "🏠 Inicio":
    _render_inicio(username=_username, role=_role)

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

if selected == "🚚 Proveedores":
    render_supply_proveedores()

if selected == "📦 Órdenes de Compra":
    render_supply_ordenes()

if selected == "📋 Proposal Studio":
    render_proposal_studio()

if selected == "🏆 Case Study Studio":
    render_case_study_studio()

if selected == "🌐 Dashboard Global":
    render_agency_dashboard(username=_username, role=_role)

if selected == "📈 Monthly Forecast":
    render_revenue_forecast()

if selected == "📂 SOPs / Drive AM":
    render_sop_library()

if selected == "📂 SOPs / Drive PPC":
    render_sop_library(area="PPC")

if selected == "🛒 Mercado Libre":
    render_mercado_libre(username=_username, role=_role)

if selected == "🔑 Cuentas conectadas":
    render_accounts(username=_username, role=_role)

if selected == "🔌 Integraciones":
    render_integrations(username=_username, role=_role)

if selected == "🧠 Skills":
    render_chat_skills(username=_username, role=_role)

if selected == "🧾 Registro de solicitudes":
    render_request_log(username=_username, role=_role)

# After the page, so the analysis it just shared reaches this run's chat.
app_chat.mount_app_chat(selected, _username)
