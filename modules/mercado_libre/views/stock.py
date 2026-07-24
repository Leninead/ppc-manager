"""Vista de la Feature 2 — sugerencia de reposición de stock."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
from core.helpers import kpi_card
from core.persistence import _append_log, _load_log
from modules.mercado_libre.core.stock_advisor import resumen, sugerir_reposicion
from modules.mercado_libre.views.helpers import (badge, empty_state, fmt_decimal, fmt_money, fmt_num)

_COLOR_URGENCIA = {
    "critico": config.COLOR_EMPEORO,
    "alto": config.COLOR_AMARILLO,
    "medio": config.COLOR_SECUNDARIO,
    "ok": config.COLOR_MEJORO,
    "sin_ventas": config.COLOR_SIN_DATOS,
}

_ETIQUETA_URGENCIA = {
    "critico": "Crítico",
    "alto": "Alto",
    "medio": "Medio",
    "ok": "OK",
    "sin_ventas": "Sin ventas",
}


@st.dialog("Registrar stock en tránsito")
def dialogo_registrar_transito(cuenta: str, publicaciones: pd.DataFrame) -> None:
    """Alta de unidades en camino, con la fecha que informa el cliente."""
    st.caption(f"Cuenta: **{cuenta}**")

    opciones = []
    if publicaciones is not None and not publicaciones.empty:
        opciones = [
            f"{fila.mla} — {str(fila.titulo)[:60]}"
            for fila in publicaciones.itertuples(index=False)
        ]

    if opciones:
        elegida = st.selectbox("Publicación *", options=opciones,
                               key="meli_transito_publicacion")
        mla = elegida.split(" — ")[0]
    else:
        mla = st.text_input("MLA *", key="meli_transito_mla",
                            placeholder="MLA1176496460")

    unidades = st.number_input("Unidades en camino *", min_value=1, step=1,
                               key="meli_transito_unidades")
    fecha_llegada = st.date_input(
        "Fecha estimada de llegada *",
        value=date.today(),
        key="meli_transito_fecha",
        help=f"Decide si el envío cubre o no el horizonte de "
             f"{config.DIAS_COBERTURA_OBJETIVO} días. Lo que llega después no "
             "se descuenta de la sugerencia.",
    )
    nota = st.text_input("Nota", key="meli_transito_nota",
                         placeholder="Contenedor de agosto")

    col_cancelar, col_guardar = st.columns(2)
    if col_cancelar.button("Cancelar", key="meli_transito_cancel",
                           use_container_width=True):
        st.rerun()
    if col_guardar.button("Registrar", key="meli_transito_ok", type="primary",
                          use_container_width=True):
        if not mla:
            st.error("La publicación es obligatoria.")
            return
        _append_log(
            row={
                "mla": mla.strip().upper(),
                "unidades": float(unidades),
                "fecha_llegada": fecha_llegada.isoformat(),
                "nota": nota.strip(),
            },
            area=config.AREA,
            cliente=cuenta,
            modulo=config.MODULO_STOCK,
            log_name=config.LOG_TRANSITO,
        )
        st.success(f"{unidades} unidades en tránsito registradas para {mla}.")
        st.rerun()


def render(cuenta: str, rendimiento: pd.DataFrame | None,
           publicaciones: pd.DataFrame | None, dias_periodo: int | None) -> None:
    st.markdown("### 📦 Sugerencia de reposición")
    st.caption(
        f"Proyecta {config.DIAS_COBERTURA_OBJETIVO} días de cobertura sobre la "
        "velocidad de venta del último reporte, descontando lo que ya viene "
        "en camino."
    )

    if rendimiento is None or rendimiento.empty or publicaciones is None or publicaciones.empty:
        empty_state(
            "Faltan datos para calcular la sugerencia",
            "Se necesitan el reporte de rendimiento y el export de publicaciones "
            "cargados en la pestaña de importación.",
        )
        return

    transito = _load_log(config.AREA, cuenta, config.MODULO_STOCK,
                         config.LOG_TRANSITO)

    columna_boton, columna_info = st.columns([1.6, 4])
    with columna_boton:
        if st.button("🚚 Registrar tránsito", key="meli_btn_transito",
                     use_container_width=True):
            dialogo_registrar_transito(cuenta, publicaciones)
    with columna_info:
        st.caption(f"Envíos en tránsito registrados: **{len(transito)}**")

    sugerencias = sugerir_reposicion(
        rendimiento, publicaciones, transito,
        dias_periodo=dias_periodo,
    )
    if sugerencias.empty:
        empty_state("Sin publicaciones para analizar",
                    "Ninguna publicación activa quedó tras aplicar los filtros.")
        return

    st.divider()
    totales = resumen(sugerencias)
    columnas = st.columns(5)
    tarjetas = [
        ("Publicaciones activas", fmt_num(totales["publicaciones"])),
        ("A reponer", fmt_num(totales["a_reponer"])),
        ("Unidades sugeridas", fmt_num(totales["unidades_sugeridas"])),
        ("Críticos", fmt_num(totales["criticos"])),
        ("Sin ventas", fmt_num(totales["sin_ventas"])),
    ]
    for columna, (etiqueta, valor) in zip(columnas, tarjetas):
        with columna:
            st.markdown(kpi_card(label=etiqueta, value=valor),
                        unsafe_allow_html=True)
    st.markdown("")

    if totales["criticos"]:
        st.error(
            f"{totales['criticos']} publicación(es) tienen 7 días o menos de "
            "cobertura al ritmo de venta actual. Son las que hay que resolver "
            "esta semana."
        )

    solo_reponer = st.checkbox(
        "Mostrar solo las que necesitan reposición", value=True,
        key="meli_stock_filtro",
    )
    urgencias = st.multiselect(
        "Filtrar por urgencia",
        options=list(_ETIQUETA_URGENCIA),
        default=[],
        format_func=lambda clave: _ETIQUETA_URGENCIA[clave],
        key="meli_stock_urgencia",
    )

    mostrar = sugerencias
    if solo_reponer:
        mostrar = mostrar[mostrar["sugerido"] > 0]
    if urgencias:
        mostrar = mostrar[mostrar["urgencia"].isin(urgencias)]

    tabla = pd.DataFrame({
        "MLA": mostrar["mla"],
        "Título": mostrar["titulo"].astype(str).str.slice(0, 55),
        "Stock": mostrar["stock"],
        "En tránsito": mostrar["en_transito"],
        "Vendidas": mostrar["unidades"],
        "Venta/día": mostrar["velocidad_diaria"],
        "Días cobertura": mostrar["dias_cobertura"],
        "Sugerido": mostrar["sugerido"],
        "Facturación": mostrar["facturacion"],
        "Urgencia": mostrar["urgencia"].map(_ETIQUETA_URGENCIA),
    })

    st.dataframe(
        tabla.style.format({
            "Stock": fmt_num, "En tránsito": fmt_num, "Vendidas": fmt_num,
            "Sugerido": fmt_num, "Facturación": fmt_money,
            "Venta/día": lambda v: fmt_decimal(v, 2),
            "Días cobertura": lambda v: fmt_decimal(v, 1),
        }),
        use_container_width=True,
        hide_index=True,
    )

    tardio = sugerencias[sugerencias["transito_tardio"] > 0]
    if not tardio.empty:
        with st.expander(
            f"🚚 {len(tardio)} publicación(es) con tránsito fuera del horizonte"
        ):
            st.caption(
                f"Estas unidades llegan después de los "
                f"{config.DIAS_COBERTURA_OBJETIVO} días proyectados, así que no "
                "se descuentan de la sugerencia: no alcanzan a cubrir el período."
            )
            st.dataframe(
                tardio[["mla", "titulo", "transito_tardio", "sugerido"]],
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
