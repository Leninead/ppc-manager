"""Vista de la Feature 1 — seguimiento del impacto de los cambios."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
from modules.mercado_libre.core.change_tracker import evaluar_cambios, marcar_solapamientos, resumen
from core.helpers import kpi_card
from core.persistence import _append_log, _load_history, _load_log
from modules.mercado_libre.views.helpers import (badge, color_resultado, color_variacion, empty_state,
                           fmt_num, fmt_pct)


@st.dialog("Registrar cambio en publicación")
def dialogo_registrar_cambio(cuenta: str, publicaciones: pd.DataFrame) -> None:
    """Alta de un cambio aplicado. Reemplaza al Google Sheet de modificaciones."""
    st.caption(f"Cuenta: **{cuenta}**")

    opciones = []
    if publicaciones is not None and not publicaciones.empty:
        opciones = [
            f"{fila.mla} — {str(fila.titulo)[:60]}"
            for fila in publicaciones.itertuples(index=False)
        ]

    if opciones:
        elegida = st.selectbox(
            "Publicación *", options=opciones, key="meli_cambio_publicacion"
        )
        mla = elegida.split(" — ")[0]
    else:
        mla = st.text_input(
            "MLA de la publicación *",
            key="meli_cambio_mla_manual",
            placeholder="MLA1176496460",
        )

    fecha_cambio = st.date_input(
        "Fecha en que se aplicó el cambio *",
        value=date.today(),
        key="meli_cambio_fecha",
        help="Es la fecha real del cambio en Mercado Libre, no la de hoy si "
             "lo estás cargando después.",
    )
    tipo = st.selectbox(
        "Tipo de cambio *", options=config.TIPOS_CAMBIO, key="meli_cambio_tipo"
    )
    st.caption(
        f"Métrica principal para este tipo: "
        f"**{config.METRICA_PRINCIPAL.get(tipo, 'conversion')}**. "
        "Se calculan las dos igual."
    )
    descripcion = st.text_input(
        "Descripción", key="meli_cambio_desc",
        placeholder="Título nuevo con keywords principales",
    )

    col_cancelar, col_guardar = st.columns(2)
    if col_cancelar.button("Cancelar", key="meli_cambio_cancel",
                           use_container_width=True):
        st.rerun()
    if col_guardar.button("Registrar", key="meli_cambio_ok", type="primary",
                          use_container_width=True):
        if not mla:
            st.error("La publicación es obligatoria.")
            return
        _append_log(
            row={
                "mla": mla.strip().upper(),
                "fecha_cambio": fecha_cambio.isoformat(),
                "tipo_cambio": tipo,
                "descripcion": descripcion.strip(),
            },
            area=config.AREA,
            cliente=cuenta,
            modulo=config.MODULO_RENDIMIENTO,
            log_name=config.LOG_CAMBIOS,
        )
        st.success(f"Cambio registrado para {mla}.")
        st.rerun()


def _kpis(conteo: dict) -> None:
    columnas = st.columns(5)
    orden = [
        (config.RESULTADO_MEJORO, True),
        (config.RESULTADO_NEUTRO, True),
        (config.RESULTADO_EMPEORO, False),
        (config.RESULTADO_SIN_DATOS, True),
        (config.RESULTADO_PENDIENTE, True),
    ]
    for columna, (clave, _) in zip(columnas, orden):
        with columna:
            st.markdown(
                kpi_card(
                    label=config.ETIQUETA_RESULTADO[clave],
                    value=str(conteo.get(clave, 0)),
                ),
                unsafe_allow_html=True,
            )


def render(cuenta: str, publicaciones: pd.DataFrame | None = None) -> None:
    st.markdown("### 📈 Seguimiento de cambios")
    st.caption(
        "Compara el rendimiento de cada publicación antes y después de cada "
        f"cambio, sobre ventanas de {config.VENTANA_DIAS} días."
    )

    historia = _load_history(config.AREA, cuenta, config.MODULO_RENDIMIENTO)
    cambios = _load_log(config.AREA, cuenta, config.MODULO_RENDIMIENTO,
                        config.LOG_CAMBIOS)

    columna_boton, columna_info = st.columns([1.4, 4])
    with columna_boton:
        if st.button("➕ Registrar cambio", key="meli_btn_cambio",
                     type="primary", use_container_width=True):
            dialogo_registrar_cambio(cuenta, publicaciones)
    with columna_info:
        periodos = 0 if historia.empty else historia["_period"].nunique()
        st.caption(
            f"Períodos cargados: **{periodos}** · "
            f"Cambios registrados: **{len(cambios)}**"
        )

    if cambios.empty:
        empty_state(
            "Todavía no hay cambios registrados",
            "Registrá el primer cambio para empezar a medir su impacto.",
        )
        return

    if periodos < 2:
        st.info(
            "El seguimiento necesita al menos dos períodos para poder comparar. "
            "Con un solo reporte cargado no hay contra qué medir los cambios: "
            "subí el siguiente reporte de rendimiento y los resultados aparecen "
            "automáticamente."
        )

    evaluacion = marcar_solapamientos(evaluar_cambios(historia, cambios))
    if evaluacion.empty:
        empty_state(
            "No se pudo evaluar ningún cambio",
            "Revisá que los cambios registrados tengan MLA y fecha válidos.",
        )
        return

    st.divider()
    _kpis(resumen(evaluacion))
    st.markdown("")

    solapados = int(evaluacion["solapado"].sum())
    if solapados:
        st.warning(
            f"{solapados} cambio(s) ocurrieron a menos de {config.VENTANA_DIAS} "
            "días de otro cambio sobre la misma publicación. Sus ventanas de "
            "comparación se pisan, así que el resultado del segundo arrastra el "
            "efecto del primero y no se les puede atribuir el mérito por separado."
        )

    filtro = st.multiselect(
        "Filtrar por resultado",
        options=list(config.ETIQUETA_RESULTADO),
        default=[],
        format_func=lambda clave: config.ETIQUETA_RESULTADO[clave],
        placeholder="Todos los resultados",
        key="meli_tracker_filtro",
    )
    mostrar = evaluacion[evaluacion["resultado"].isin(filtro)] if filtro else evaluacion

    tabla = pd.DataFrame({
        "MLA": mostrar["mla"],
        "Fecha": mostrar["fecha_cambio"],
        "Tipo": mostrar["tipo_cambio"],
        "Visitas antes": mostrar["visitas_antes"],
        "Visitas después": mostrar["visitas_despues"],
        "Δ Visitas": mostrar["var_visitas"],
        "Conv. antes": mostrar["conv_antes"],
        "Conv. después": mostrar["conv_despues"],
        "Δ Conversión": mostrar["var_conversion"],
        "Resultado": mostrar["resultado"].map(config.ETIQUETA_RESULTADO),
        "Motivo": mostrar["motivo"],
    })

    st.dataframe(
        tabla.style
        .map(color_variacion, subset=["Δ Visitas", "Δ Conversión"])
        .format({
            "Δ Visitas": lambda v: fmt_pct(v),
            "Δ Conversión": lambda v: fmt_pct(v),
            "Conv. antes": lambda v: fmt_pct(v, 2),
            "Conv. después": lambda v: fmt_pct(v, 2),
            "Visitas antes": fmt_num,
            "Visitas después": fmt_num,
        }),
        use_container_width=True,
        hide_index=True,
    )

    with st.expander("📖 Cómo se lee esta tabla"):
        st.markdown(
            f"""
- **Ventanas de comparación**: se toma el reporte que cubre los días previos al
  cambio y el primero que arranca después. Nunca se mezclan días de antes y de
  después en la misma ventana.
- **Métrica principal según el tipo**: los cambios de título, imágenes y envío
  se leen sobre visitas; los de precio, ficha y descripción sobre conversión.
  Las dos se calculan siempre, la clasificación usa la que corresponde.
- **Sin datos suficientes**: menos de {config.MIN_VISITAS_EVALUACION} visitas en
  alguna ventana. Con tan poco tráfico una sola venta mueve la conversión varios
  puntos, así que la variación se muestra pero no se cuenta como resultado.
- **Pendiente de evaluación**: el cambio es demasiado reciente o todavía falta
  cargar el reporte que lo cubre. No se perdió, aparece cuando llegue el dato.
"""
        )
