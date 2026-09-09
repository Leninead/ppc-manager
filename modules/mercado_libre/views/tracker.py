"""Feature 1 view — tracking the impact of changes."""
from __future__ import annotations

from datetime import date

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
from modules.mercado_libre.core.change_tracker import evaluar_cambios, marcar_solapamientos, resumen
from core.helpers import kpi_card
from core.persistence import _append_log, _load_history, _load_log
from modules.mercado_libre.views.helpers import (badge, color_result, color_variation, empty_state,
                           fmt_num, fmt_pct)


@st.dialog("Registrar cambio en publicación")
def dialog_register_change(account: str, listings: pd.DataFrame) -> None:
    """Record an applied change. Replaces the Google Sheet of modifications."""
    st.caption(f"Cuenta: **{account}**")

    options = []
    if listings is not None and not listings.empty:
        options = [
            f"{row.mla} — {str(row.titulo)[:60]}"
            for row in listings.itertuples(index=False)
        ]

    if options:
        chosen = st.selectbox(
            "Publicación *", options=options, key="meli_cambio_publicacion"
        )
        mla = chosen.split(" — ")[0]
    else:
        mla = st.text_input(
            "MLA de la publicación *",
            key="meli_cambio_mla_manual",
            placeholder="MLA1176496460",
        )

    change_date = st.date_input(
        "Fecha en que se aplicó el cambio *",
        value=date.today(),
        key="meli_cambio_fecha",
        help="Es la fecha real del cambio en Mercado Libre, no la de hoy si "
             "lo estás cargando después.",
    )
    change_type = st.selectbox(
        "Tipo de cambio *", options=config.TIPOS_CAMBIO, key="meli_cambio_tipo"
    )
    st.caption(
        f"Métrica principal para este tipo: "
        f"**{config.METRICA_PRINCIPAL.get(change_type, 'conversion')}**. "
        "Se calculan las dos igual."
    )
    description = st.text_input(
        "Descripción", key="meli_cambio_desc",
        placeholder="Título nuevo con keywords principales",
    )

    col_cancel, col_save = st.columns(2)
    if col_cancel.button("Cancelar", key="meli_cambio_cancel",
                           use_container_width=True):
        st.rerun()
    if col_save.button("Registrar", key="meli_cambio_ok", type="primary",
                          use_container_width=True):
        if not mla:
            st.error("La publicación es obligatoria.")
            return
        _append_log(
            row={
                "mla": mla.strip().upper(),
                "fecha_cambio": change_date.isoformat(),
                "tipo_cambio": change_type,
                "descripcion": description.strip(),
            },
            area=config.AREA,
            cliente=account,
            modulo=config.MODULO_RENDIMIENTO,
            log_name=config.LOG_CAMBIOS,
        )
        st.success(f"Cambio registrado para {mla}.")
        st.rerun()


def _kpis(counts: dict) -> None:
    cols = st.columns(5)
    order = [
        (config.RESULTADO_MEJORO, True),
        (config.RESULTADO_NEUTRO, True),
        (config.RESULTADO_EMPEORO, False),
        (config.RESULTADO_SIN_DATOS, True),
        (config.RESULTADO_PENDIENTE, True),
    ]
    for col, (key, _) in zip(cols, order):
        with col:
            st.markdown(
                kpi_card(
                    label=config.ETIQUETA_RESULTADO[key],
                    value=str(counts.get(key, 0)),
                ),
                unsafe_allow_html=True,
            )


def render(account: str, listings: pd.DataFrame | None = None) -> None:
    st.markdown("### 📈 Seguimiento de cambios")
    st.caption(
        "Compara el rendimiento de cada publicación antes y después de cada "
        f"cambio, sobre ventanas de {config.VENTANA_DIAS} días."
    )

    history = _load_history(config.AREA, account, config.MODULO_RENDIMIENTO)
    changes = _load_log(config.AREA, account, config.MODULO_RENDIMIENTO,
                        config.LOG_CAMBIOS)

    col_button, col_info = st.columns([1.4, 4])
    with col_button:
        if st.button("➕ Registrar cambio", key="meli_btn_cambio",
                     type="primary", use_container_width=True):
            dialog_register_change(account, listings)
    with col_info:
        periods = 0 if history.empty else history["_period"].nunique()
        st.caption(
            f"Períodos cargados: **{periods}** · "
            f"Cambios registrados: **{len(changes)}**"
        )

    if changes.empty:
        empty_state(
            "Todavía no hay cambios registrados",
            "Registrá el primer cambio para empezar a medir su impacto.",
        )
        return

    if periods < 2:
        st.info(
            "El seguimiento necesita al menos dos períodos para poder comparar. "
            "Con un solo reporte cargado no hay contra qué medir los cambios: "
            "subí el siguiente reporte de rendimiento y los resultados aparecen "
            "automáticamente."
        )

    evaluation = marcar_solapamientos(evaluar_cambios(history, changes))
    if evaluation.empty:
        empty_state(
            "No se pudo evaluar ningún cambio",
            "Revisá que los cambios registrados tengan MLA y fecha válidos.",
        )
        return

    st.divider()
    _kpis(resumen(evaluation))
    st.markdown("")

    overlaps = int(evaluation["solapado"].sum())
    if overlaps:
        st.warning(
            f"{overlaps} cambio(s) ocurrieron a menos de {config.VENTANA_DIAS} "
            "días de otro cambio sobre la misma publicación. Sus ventanas de "
            "comparación se pisan, así que el resultado del segundo arrastra el "
            "efecto del primero y no se les puede atribuir el mérito por separado."
        )

    filter_val = st.multiselect(
        "Filtrar por resultado",
        options=list(config.ETIQUETA_RESULTADO),
        default=[],
        format_func=lambda key: config.ETIQUETA_RESULTADO[key],
        placeholder="Todos los resultados",
        key="meli_tracker_filtro",
    )
    visible = evaluation[evaluation["resultado"].isin(filter_val)] if filter_val else evaluation

    table = pd.DataFrame({
        "MLA": visible["mla"],
        "Fecha": visible["fecha_cambio"],
        "Tipo": visible["tipo_cambio"],
        "Visitas antes": visible["visitas_antes"],
        "Visitas después": visible["visitas_despues"],
        "Δ Visitas": visible["var_visitas"],
        "Conv. antes": visible["conv_antes"],
        "Conv. después": visible["conv_despues"],
        "Δ Conversión": visible["var_conversion"],
        "Resultado": visible["resultado"].map(config.ETIQUETA_RESULTADO),
        "Motivo": visible["motivo"],
    })

    st.dataframe(
        table.style
        .map(color_variation, subset=["Δ Visitas", "Δ Conversión"])
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
