import streamlit as st

_NARANJA  = "#E84000"
_NEGRO    = "#1F1F1F"
_GRIS_CLR = "#F5F5F5"
_GRIS_TXT = "#888888"


def _area_card(emoji, titulo, descripcion, ownership, modulos, activo=True, grande=False):
    border_color = _NARANJA if activo else "#DDDDDD"
    bg_color     = "#FFFFFF" if activo else _GRIS_CLR
    badge_color  = "#E8F5E9" if activo else "#F5F5F5"
    badge_txt    = "#2E7D32" if activo else _GRIS_TXT
    badge_label  = "✅ activo" if activo else "🔒 próximamente"
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
        f"El sistema operativo de la agencia — v2.0</div>"
        f"</div>"
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

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_area_card(
            "📊", "PPC",
            "Gestionamos campañas publicitarias en Amazon para maximizar ventas y rentabilidad, optimizando estrategias de PPC y performance."
            "<div style='margin-top:0.8rem;padding:0.75rem;background:#FFF3EE;"
            "border-radius:8px;border-left:3px solid #E84000;'>"
            "<div style='font-size:0.72rem;font-weight:700;color:#E84000;"
            "margin-bottom:0.4rem;letter-spacing:0.05em;'>FLUJO DE TRABAJO</div>"
            "<div style='font-size:0.75rem;color:#444;line-height:1.8;'>"
            "1️⃣ <b>STR</b> — Analizar keywords y negativizar<br>"
            "2️⃣ <b>SQP</b> — Analizar market share orgánico<br>"
            "3️⃣ <b>Análisis Cruzado</b> — Detectar oportunidades STR+SQP<br>"
            "4️⃣ <b>Tendencia</b> — Ver evolución multi-semana<br>"
            "5️⃣ <b>Bulk Campañas</b> — Diagnosticar salud de campañas<br>"
            "6️⃣ <b>Business Report</b> — Ver ventas totales y TACoS<br>"
            "7️⃣ <b>Análisis de Funnel</b> — Detectar brechas estructurales<br>"
            "8️⃣ <b>Bid Optimizer</b> — Calcular bids por ASIN<br>"
            "9️⃣ <b>Campaign Builder</b> — Generar bulk listo para subir"
            "</div></div>",
            "Guille Neuman",
            ["STR", "SQP", "Análisis Cruzado", "Tendencia",
             "Bulk Campañas", "Business Report",
             "Análisis de Funnel", "Bid Optimizer", "Campaign Builder"],
            activo=True, grande=True
        ), unsafe_allow_html=True)

    with col2:
        st.markdown(
            _area_card(
                "👥", "Account Manager",
                "Somos el nexo con el cliente: coordinamos equipos, analizamos resultados y garantizamos el cumplimiento de los objetivos de cada cuenta.",
                "Eduardo Maya",
                ["Reportes Atom 11", "Reportes MerchanSpring", "Weekly Client Report"],
                activo=True, grande=True
            ), unsafe_allow_html=True)

    st.markdown("<div style='margin-top:1.5rem;'></div>", unsafe_allow_html=True)

    # ── Fila 1 próximamente ───────────────────────────────────────────────
    st.markdown(
        f"<div style='font-weight:700;font-size:0.95rem;color:{_NEGRO};"
        f"margin-bottom:0.75rem;'>🔒 Próximamente</div>",
        unsafe_allow_html=True
    )

    col3, col4, col5 = st.columns(3)
    with col3:
        st.markdown(_area_card(
            "🚚", "Supply Chain",
            "Coordinamos abastecimiento, inventario y logística para asegurar disponibilidad y eficiencia operativa.",
            "Julian López / Federico Valero",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col4:
        st.markdown(_area_card(
            "🚦", "Tráfico Externo",
            "Impulsamos el crecimiento de las marcas con estrategias de medios, mailing y contenido que generan tráfico y posicionamiento.",
            "María Fernanda Rojas",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col5:
        st.markdown(_area_card(
            "🎨", "Diseño",
            "Creamos contenido visual estratégico para marcas y productos, potenciando su identidad y optimizando su impacto en Amazon y otros canales.",
            "Guido Pedregoza",
            [],
            activo=False
        ), unsafe_allow_html=True)

    # ── Fila 2 próximamente ───────────────────────────────────────────────
    col6, col7, col8 = st.columns(3)
    with col6:
        st.markdown(_area_card(
            "👔", "RRHH",
            "Cuidamos la cultura y el talento del equipo, impulsando el bienestar, la motivación y el crecimiento profesional dentro de la agencia.",
            "Keila Vivas",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col7:
        st.markdown(_area_card(
            "💼", "Sales",
            "Lideramos el desarrollo comercial de la agencia, generando nuevos leads, fortaleciendo relaciones con clientes y asegurando la rentabilidad de cada cuenta.",
            "—",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col8:
        st.markdown(_area_card(
            "🏥", "Account Health",
            "Mantenemos las cuentas en perfecto estado dentro de Amazon, resolviendo incidencias y asegurando el cumplimiento de políticas y métricas clave.",
            "—",
            [],
            activo=False
        ), unsafe_allow_html=True)

    # ── Fila 3 próximamente ───────────────────────────────────────────────
    col9, col10, col11 = st.columns(3)
    with col9:
        st.markdown(_area_card(
            "🛒", "Marketplaces",
            "Gestionamos la presencia y crecimiento de las marcas en Amazon, Mercado Libre y otros canales, asegurando operación, visibilidad y expansión clave.",
            "—",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col10:
        st.markdown(_area_card(
            "📈", "Dirección General",
            "Dashboard ejecutivo, rentabilidad por cliente y área, proyecciones y forecast con KPIs en tiempo real.",
            "—",
            [],
            activo=False
        ), unsafe_allow_html=True)

    with col11:
        st.markdown(_area_card(
            "🔌", "Expansión Futura",
            "API Amazon Ads directa, alertas automáticas de anomalías, notificaciones WhatsApp/Slack, multi-cuenta y multi-marketplace.",
            "—",
            [],
            activo=False
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
