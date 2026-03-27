import streamlit as st

_NARANJA  = "#E84000"
_NEGRO    = "#1F1F1F"
_GRIS_CLR = "#F5F5F5"
_GRIS_TXT = "#888888"

_VERSION = "v3.0"
_DATE    = "2026-03-27"
_TOTAL_MODULOS = 22

_CHANGELOG = [
    ("2026-03-27", "Knowledge Base — explorador de notas .md con búsqueda, tags y categorías"),
    ("2026-03-27", "SBH Target Recommendation — targets SBH cruzando MKL+SQP+Campaign CSV"),
    ("2026-03-27", "Ranking Volatility — tab 4 en DataDive con std dev + PPC IS del SQP"),
    ("2026-03-27", "Workflow Wizard — flujo de trabajo guiado piramidal en Inicio"),
    ("2026-03-27", "Helium 10 Analyzer — Cerebro reverse ASIN, KW Research, Competitor Gap"),
    ("2026-03-27", "DataDive Analyzer — parsers MKL Keywords, Competitors y Rank Radar"),
    ("2026-03-27", "@st.cache_data en todos los parsers + keys únicos en download_buttons"),
    ("2026-03-26", "PPC Insights Engine — health score por ASIN cruzando STR+SQP+BR+Campaigns"),
    ("2026-03-26", "PPC Forecast — proyección de ventas con tendencia lineal + estacionalidad"),
    ("2026-03-26", "PPC Audit — auditoría integral con score de cuenta 0-100"),
    ("2026-03-26", "Account Pulse — monitor de salud diaria con ventas, BuyBox, campañas"),
    ("2026-03-26", "Bid Optimizer — tab Placements & Budget con referencia SOP"),
    ("2026-03-26", "Campaign Analyzer — upgrade a Auditoría PPC con naming check"),
    ("2026-03-26", "Weekly Client Report — changelog integrado en Excel"),
    ("2026-03-26", "STR Harvest — anti-canibalización automática con Campaign CSV"),
    ("2026-03-26", "Análisis Cruzado — tab PPC Insights por ASIN"),
    ("2026-03-23", "Atom11 Rules Builder — 274 rules por cuenta, multi-marca"),
    ("2026-03-21", "Campaign Builder — bulk Amazon listo para subir"),
    ("2026-03-21", "Bid Optimizer — bids por CVR real + Inventory Report"),
    ("2026-03-21", "Sidebar oscuro + rediseño Agency OS"),
]


def _area_card(emoji, titulo, descripcion, ownership, modulos, activo=True, grande=False, count=None):
    border_color = _NARANJA if activo else "#DDDDDD"
    bg_color     = "#FFFFFF" if activo else _GRIS_CLR
    badge_color  = "#E8F5E9" if activo else "#F5F5F5"
    badge_txt    = "#2E7D32" if activo else _GRIS_TXT
    badge_label  = f"✅ {count} módulos" if count else ("✅ activo" if activo else "🔒 próximamente")
    opacity      = "1" if activo else "0.55"

    mods_html = "".join([
        f"<span style='display:inline-block;background:#F0F0F0;border-radius:4px;"
        f"padding:2px 8px;margin:2px;font-size:0.70rem;color:#444;'>{m}</span>"
        for m in modulos
    ]) if modulos else ""

    emoji_size  = "2.4rem" if grande else "1.6rem"
    titulo_size = "1.2rem" if grande else "0.95rem"
    padding     = "1.8rem" if grande else "1.2rem"

    return (
        f"<div style='border:2px solid {border_color};border-radius:12px;"
        f"padding:{padding};margin-bottom:0.75rem;background:{bg_color};"
        f"opacity:{opacity};height:100%;'>"
        f"<div style='display:flex;align-items:center;gap:0.5rem;margin-bottom:0.6rem;'>"
        f"<span style='font-size:{emoji_size};'>{emoji}</span>"
        f"<span style='font-weight:700;font-size:{titulo_size};color:{_NEGRO};'>{titulo}</span>"
        f"<span style='margin-left:auto;background:{badge_color};color:{badge_txt};"
        f"font-size:0.70rem;padding:2px 8px;border-radius:20px;white-space:nowrap;'>{badge_label}</span>"
        f"</div>"
        f"<div style='font-size:0.80rem;color:#555;margin-bottom:0.5rem;line-height:1.4;'>{descripcion}</div>"
        f"<div style='font-size:0.72rem;color:{_GRIS_TXT};margin-bottom:0.5rem;'>"
        f"<strong>Ownership:</strong> {ownership}</div>"
        f"<div>{mods_html}</div>"
        f"</div>"
    )


def render():
    # ── Header ────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:1rem;margin-bottom:0.25rem;'>"
        f"<span style='font-size:2.5rem;'>🦫</span>"
        f"<div>"
        f"<div style='font-size:1.6rem;font-weight:800;color:{_NEGRO};'>Capybaras Agency OS</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};'>"
        f"El sistema operativo de la agencia — {_VERSION} — {_DATE}</div>"
        f"</div>"
        f"<div style='margin-left:auto;background:#1A1A1A;color:{_NARANJA};"
        f"padding:0.5rem 1rem;border-radius:8px;font-weight:800;font-size:1.1rem;'>"
        f"{_TOTAL_MODULOS} módulos activos</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Áreas activas ─────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-weight:700;font-size:0.95rem;color:{_NEGRO};"
        f"margin-bottom:0.75rem;'>🟢 Áreas activas</div>",
        unsafe_allow_html=True
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(_area_card(
            "📊", "PPC Manager",
            "Gestionamos campañas publicitarias en Amazon para maximizar ventas y rentabilidad."
            "<div style='margin-top:0.8rem;padding:0.75rem;background:#FFF3EE;"
            "border-radius:8px;border-left:3px solid #E84000;'>"
            "<div style='font-size:0.72rem;font-weight:700;color:#E84000;"
            "margin-bottom:0.4rem;letter-spacing:0.05em;'>FLUJO DE TRABAJO</div>"
            "<div style='font-size:0.75rem;color:#444;line-height:1.8;'>"
            "1️⃣ <b>STR</b> — Negativizar + Harvestear<br>"
            "2️⃣ <b>SQP</b> — Market share orgánico<br>"
            "3️⃣ <b>Análisis Cruzado</b> — Oportunidades STR+SQP<br>"
            "4️⃣ <b>Tendencia</b> — Evolución multi-semana<br>"
            "5️⃣ <b>Bulk Campañas</b> — Diagnóstico + Auditoría<br>"
            "6️⃣ <b>Business Report</b> — Ventas y TACoS<br>"
            "7️⃣ <b>Funnel</b> — Brechas estructurales<br>"
            "8️⃣ <b>Bid Optimizer</b> — Bids + Placements<br>"
            "9️⃣ <b>Campaign Builder</b> — Bulk listo para Amazon<br>"
            "🔟 <b>Atom11 Rules</b> — Automatización"
            "</div></div>",
            "Guille Neuman",
            ["STR", "SQP", "Análisis Cruzado", "Tendencia",
             "Bulk Campañas", "Business Report", "Funnel",
             "Bid Optimizer", "Campaign Builder"],
            activo=True, count=10
        ), unsafe_allow_html=True)

    with col2:
        st.markdown(_area_card(
            "👥", "Account Manager",
            "Reportes, monitoreo y comunicación con el cliente.",
            "Eduardo Maya",
            ["Reportes Atom 11", "MerchanSpring", "Weekly Report", "Account Pulse"],
            activo=True, count=4
        ), unsafe_allow_html=True)

    with col3:
        st.markdown(_area_card(
            "🔬", "Research & Intelligence",
            "Análisis profundo de nicho, competidores y salud de cuenta. Herramientas de investigación avanzadas para decisiones estratégicas.",
            "Lenin Acosta",
            ["DataDive", "Helium 10", "SBH Recommendation",
             "PPC Insights", "PPC Forecast", "PPC Audit", "Account Pulse"],
            activo=True, count=7
        ), unsafe_allow_html=True)

    col_kb = st.columns([1])
    with col_kb[0]:
        st.markdown(_area_card(
            "📚", "Knowledge Base",
            "Repositorio centralizado de notas, aprendizajes y documentación del equipo. Buscar por tags, categorías y texto libre.",
            "Lenin Acosta",
            ["Explorar notas", "Agregar nota", "Búsqueda por tags"],
            activo=True
        ), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # ── Changelog reciente ────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-weight:700;font-size:0.95rem;color:{_NEGRO};"
        f"margin-bottom:0.75rem;'>📝 Changelog reciente</div>",
        unsafe_allow_html=True
    )

    changelog_html = "".join([
        f"<div style='display:flex;gap:0.75rem;padding:0.35rem 0;"
        f"border-bottom:1px solid #F0F0F0;font-size:0.78rem;'>"
        f"<span style='color:{_GRIS_TXT};white-space:nowrap;min-width:85px;'>{date}</span>"
        f"<span style='color:#333;'>{desc}</span></div>"
        for date, desc in _CHANGELOG[:10]
    ])

    st.markdown(
        f"<div style='background:#FAFAFA;border-radius:8px;padding:0.75rem 1rem;"
        f"border:1px solid #EEE;max-height:280px;overflow-y:auto;'>{changelog_html}</div>",
        unsafe_allow_html=True
    )

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # ── Workflow Wizard ──────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-weight:700;font-size:0.95rem;color:{_NEGRO};"
        f"margin-bottom:0.75rem;'>🗺️ Flujo de trabajo guiado</div>",
        unsafe_allow_html=True
    )

    def _wf_level(level_num, emoji, title, color, modules_list, desc):
        """Build a workflow level row."""
        btns_html = " ".join(
            f"<span style='display:inline-block;background:{color}15;border:1px solid {color};"
            f"border-radius:4px;padding:2px 8px;margin:2px;font-size:0.72rem;color:{color};"
            f"font-weight:600;'>{m}</span>"
            for m in modules_list
        )
        return (
            f"<div style='display:flex;align-items:center;gap:0.75rem;padding:0.6rem 0.75rem;"
            f"margin-bottom:0.4rem;background:#FAFAFA;border-radius:8px;"
            f"border-left:4px solid {color};'>"
            f"<div style='min-width:28px;text-align:center;font-size:1.1rem;'>{emoji}</div>"
            f"<div style='flex:1;'>"
            f"<div style='font-size:0.82rem;font-weight:700;color:{_NEGRO};'>"
            f"Nivel {level_num}: {title}</div>"
            f"<div style='font-size:0.72rem;color:#777;margin:2px 0 4px;'>{desc}</div>"
            f"<div>{btns_html}</div>"
            f"</div></div>"
        )

    wf_html = ""
    wf_html += _wf_level(1, "📥", "Subí tus datos", "#2196F3",
        ["STR", "SQP", "Bulk", "BR", "DataDive", "Helium 10", "Account Pulse"],
        "Archivos base desde Amazon, DataDive y Helium 10")
    wf_html += _wf_level(2, "🔍", "Analizá", "#FF9800",
        ["Análisis Cruzado", "Funnel", "Tendencia", "PPC Audit"],
        "Cruzar datos, detectar brechas y auditar la cuenta")
    wf_html += _wf_level(3, "🧠", "Inteligencia", "#9C27B0",
        ["PPC Insights", "Forecast", "DataDive", "SBH Targets"],
        "Health score, proyecciones, volatilidad y targeting SBH")
    wf_html += _wf_level(4, "🚀", "Ejecutá", "#4CAF50",
        ["Campaign Builder", "Bid Optimizer", "Atom11 Rules"],
        "Generar bulks, ajustar bids y crear rules de automatización")
    wf_html += _wf_level(5, "📊", "Reportá", "#E84000",
        ["Weekly Report", "Account Pulse", "Knowledge Base"],
        "Reportes semanales, monitoreo diario y documentar aprendizajes")

    st.markdown(wf_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # ── Próximamente ──────────────────────────────────────────────────────
    st.markdown(
        f"<div style='font-weight:700;font-size:0.95rem;color:{_NEGRO};"
        f"margin-bottom:0.75rem;'>🔒 Próximamente</div>",
        unsafe_allow_html=True
    )

    col3, col4, col5 = st.columns(3)
    with col3:
        st.markdown(_area_card(
            "🚚", "Supply Chain",
            "Abastecimiento, inventario y logística.",
            "Julian López / Federico Valero", [], activo=False
        ), unsafe_allow_html=True)

    with col4:
        st.markdown(_area_card(
            "🚦", "Tráfico Externo",
            "Medios, mailing y contenido para tráfico externo.",
            "María Fernanda Rojas", [], activo=False
        ), unsafe_allow_html=True)

    with col5:
        st.markdown(_area_card(
            "🎨", "Diseño",
            "Contenido visual para marcas y productos.",
            "Guido Pedregoza", [], activo=False
        ), unsafe_allow_html=True)

    col6, col7, col8 = st.columns(3)
    with col6:
        st.markdown(_area_card(
            "👔", "RRHH",
            "Cultura, talento y crecimiento del equipo.",
            "Keila Vivas", [], activo=False
        ), unsafe_allow_html=True)

    with col7:
        st.markdown(_area_card(
            "💼", "Sales",
            "Desarrollo comercial y nuevos leads.",
            "—", [], activo=False
        ), unsafe_allow_html=True)

    with col8:
        st.markdown(_area_card(
            "🏥", "Account Health",
            "Incidencias y cumplimiento de políticas Amazon.",
            "—", [], activo=False
        ), unsafe_allow_html=True)

    col9, col10, col11 = st.columns(3)
    with col9:
        st.markdown(_area_card(
            "🛒", "Marketplaces",
            "Expansión a Amazon, Mercado Libre y otros canales.",
            "—", [], activo=False
        ), unsafe_allow_html=True)

    with col10:
        st.markdown(_area_card(
            "📈", "Dirección General",
            "Dashboard ejecutivo, rentabilidad y KPIs.",
            "—", [], activo=False
        ), unsafe_allow_html=True)

    with col11:
        st.markdown(_area_card(
            "🔌", "Expansión Futura",
            "API Amazon Ads, alertas, WhatsApp/Slack, multi-cuenta.",
            "—", [], activo=False
        ), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)
    st.divider()

    # ── Footer ────────────────────────────────────────────────────────────
    st.markdown(
        f"<div style='text-align:center;padding:1.5rem 0;'>"
        f"<div style='font-size:0.95rem;color:{_GRIS_TXT};margin-bottom:0.3rem;'>"
        f"Desarrollado por</div>"
        f"<div style='font-size:1.3rem;font-weight:800;color:{_NARANJA};'>"
        f"Lenin Acosta</div>"
        f"<div style='font-size:0.85rem;color:{_GRIS_TXT};margin-top:0.2rem;'>"
        f"Capybaras Agency · 2026</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
