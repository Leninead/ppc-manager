"""Feature 2 view — stock restock suggestions."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
from core.helpers import kpi_card
from core.persistence import _append_log, _load_log
from modules.mercado_libre.core.stock_advisor import resumen, sugerir_reposicion
from modules.mercado_libre.views.helpers import (badge, empty_state, fmt_decimal, fmt_money, fmt_num)

_URGENCY_COLOR = {
    "critico": config.COLOR_EMPEORO,
    "alto": config.COLOR_AMARILLO,
    "medio": config.COLOR_SECUNDARIO,
    "ok": config.COLOR_MEJORO,
    "sin_ventas": config.COLOR_SIN_DATOS,
}

_URGENCY_LABEL = {
    "critico": "🔴 Crítico",
    "alto": "🟠 Alto",
    "medio": "🔵 Medio",
    "ok": "🟢 OK",
    "sin_ventas": "⚪ Sin ventas",
}


def _color_urgency(value):
    """Color the urgency cell with the config colors (matches alerts.py)."""
    for key, label in _URGENCY_LABEL.items():
        if value == label:
            return f"color: {_URGENCY_COLOR[key]}; font-weight: 600"
    return ""


@st.dialog("Registrar stock en tránsito")
def dialog_register_in_transit(account: str, listings: pd.DataFrame) -> None:
    """Record in-transit units with the client-reported arrival date."""
    st.caption(f"Cuenta: **{account}**")

    options = []
    if listings is not None and not listings.empty:
        options = [
            f"{row.mla} — {str(row.titulo)[:60]}"
            for row in listings.itertuples(index=False)
        ]

    if options:
        chosen = st.selectbox("Publicación *", options=options,
                               key="meli_transito_publicacion")
        mla = chosen.split(" — ")[0]
    else:
        mla = st.text_input("MLA *", key="meli_transito_mla",
                            placeholder="MLA1176496460")

    units = st.number_input("Unidades en camino *", min_value=1, step=1,
                               key="meli_transito_unidades")
    arrival_date = st.date_input(
        "Fecha estimada de llegada *",
        value=date.today(),
        key="meli_transito_fecha",
        help=f"Decide si el envío cubre o no el horizonte de "
             f"{config.DIAS_COBERTURA_OBJETIVO} días. Lo que llega después no "
             "se descuenta de la sugerencia.",
    )
    note = st.text_input("Nota", key="meli_transito_nota",
                         placeholder="Contenedor de agosto")

    col_cancel, col_save = st.columns(2)
    if col_cancel.button("Cancelar", key="meli_transito_cancel",
                           use_container_width=True):
        st.rerun()
    if col_save.button("Registrar", key="meli_transito_ok", type="primary",
                          use_container_width=True):
        if not mla:
            st.error("La publicación es obligatoria.")
            return
        _append_log(
            row={
                "mla": mla.strip().upper(),
                "unidades": float(units),
                "fecha_llegada": arrival_date.isoformat(),
                "nota": note.strip(),
            },
            area=config.AREA,
            cliente=account,
            modulo=config.MODULO_PUBLICACIONES,
            log_name=config.LOG_TRANSITO,
        )
        st.success(f"{units} unidades en tránsito registradas para {mla}.")
        st.rerun()


def render(account: str, performance: pd.DataFrame | None,
           listings: pd.DataFrame | None, days_in_period: int | None) -> None:
    st.markdown("### 📦 Sugerencia de reposición")
    st.caption(
        f"Proyecta {config.DIAS_COBERTURA_OBJETIVO} días de cobertura sobre la "
        "velocidad de venta del último reporte, descontando lo que ya viene "
        "en camino."
    )

    if performance is None or performance.empty or listings is None or listings.empty:
        empty_state(
            "Faltan datos para calcular la sugerencia",
            "Se necesitan el reporte de rendimiento y el export de publicaciones "
            "cargados en la pestaña de importación.",
        )
        return

    in_transit = _load_log(config.AREA, account, config.MODULO_PUBLICACIONES,
                         config.LOG_TRANSITO)

    col_button, col_info = st.columns([1.6, 4])
    with col_button:
        if st.button("🚚 Registrar tránsito", key="meli_btn_transito",
                     use_container_width=True):
            dialog_register_in_transit(account, listings)
    with col_info:
        st.caption(f"Envíos en tránsito registrados: **{len(in_transit)}**")

    if len(in_transit) == 0:
        st.caption(
            "Todavía no hay envíos en tránsito cargados. La columna 'En tránsito' "
            "va a mostrar 0 hasta que registres alguno."
        )

    suggestions = sugerir_reposicion(
        performance, listings, in_transit,
        dias_periodo=days_in_period,
    )
    if suggestions.empty:
        empty_state("Sin publicaciones para analizar",
                    "Ninguna publicación activa quedó tras aplicar los filtros.")
        return

    st.divider()
    totals = resumen(suggestions)
    cols = st.columns(5)
    cards = [
        ("Publicaciones activas", fmt_num(totals["publicaciones"])),
        ("A reponer", fmt_num(totals["a_reponer"])),
        ("Unidades sugeridas", fmt_num(totals["unidades_sugeridas"])),
        ("Críticos", fmt_num(totals["criticos"])),
        ("Sin ventas", fmt_num(totals["sin_ventas"])),
    ]
    for col, (label, value) in zip(cols, cards):
        with col:
            st.markdown(kpi_card(label=label, value=value),
                        unsafe_allow_html=True)
    st.markdown("")

    if totals["criticos"]:
        st.error(
            f"{totals['criticos']} publicación(es) tienen 7 días o menos de "
            "cobertura al ritmo de venta actual. Son las que hay que resolver "
            "esta semana."
        )

    only_to_restock = st.checkbox(
        "Mostrar solo las que necesitan reposición", value=True,
        key="meli_stock_filtro",
    )
    urgencies = st.multiselect(
        "Filtrar por urgencia",
        options=list(_URGENCY_LABEL),
        default=[],
        format_func=lambda key: _URGENCY_LABEL[key],
        placeholder="Todas las urgencias",
        key="meli_stock_urgencia",
    )

    visible = suggestions
    if only_to_restock:
        visible = visible[visible["sugerido"] > 0]
    if urgencies:
        visible = visible[visible["urgencia"].isin(urgencies)]

    table = pd.DataFrame({
        "MLA": visible["mla"],
        "Título": visible["titulo"].astype(str).str.slice(0, 55),
        "Stock": visible["stock"],
        "En tránsito": visible["en_transito"],
        "Vendidas": visible["unidades"],
        "Venta/día": visible["velocidad_diaria"],
        "Días cobertura": visible["dias_cobertura"],
        "Sugerido": visible["sugerido"],
        "Facturación": visible["facturacion"],
        "Urgencia": visible["urgencia"].map(_URGENCY_LABEL),
    })

    st.dataframe(
        table.style
        .map(_color_urgency, subset=["Urgencia"])
        .format({
            "Stock": fmt_num, "En tránsito": fmt_num, "Vendidas": fmt_num,
            "Sugerido": fmt_num, "Facturación": fmt_money,
            "Venta/día": lambda v: fmt_decimal(v, 2),
            "Días cobertura": lambda v: fmt_decimal(v, 1),
        }),
        use_container_width=True,
        hide_index=True,
    )

    late = suggestions[suggestions["transito_tardio"] > 0]
    if not late.empty:
        with st.expander(
            f"🚚 {len(late)} publicación(es) con tránsito fuera del horizonte"
        ):
            st.caption(
                f"Estas unidades llegan después de los "
                f"{config.DIAS_COBERTURA_OBJETIVO} días proyectados, así que no "
                "se descuentan de la sugerencia: no alcanzan a cubrir el período."
            )
            st.dataframe(
                late[["mla", "titulo", "transito_tardio", "sugerido"]],
                use_container_width=True, hide_index=True,
            )

    with st.expander("📖 Cómo se calcula"):
        st.markdown(
            f"""
- **Velocidad de venta**: unidades vendidas dividido los días que cubre el
  reporte. Se usan los días reales del período, no un valor fijo, porque los
  reportes de MELI no siempre miden la misma cantidad de días.
- **Necesidad**: velocidad diaria por {config.DIAS_COBERTURA_OBJETIVO} días.
- **Sugerido**: necesidad menos stock menos tránsito que llega a tiempo.
- **Urgencia**: se ordena por días de cobertura y no por cantidad sugerida.
  Un producto de alto volumen con stock de sobra no es urgente; uno que vende
  poco pero se queda sin stock en tres días, sí.
- **Excluidas**: publicaciones pausadas, inactivas o finalizadas, y el stock de
  FULL que el equipo saca antes de exportar la planilla.
"""
        )
