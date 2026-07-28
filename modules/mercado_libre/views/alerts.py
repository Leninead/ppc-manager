"""Vista de la Feature 3 — alertas de campañas de Product Ads."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from modules.mercado_libre import config
from modules.mercado_libre.core.ads_alerts import (COLOR_NIVEL, ETIQUETA_NIVEL, NIVEL_AMARILLO,
                             NIVEL_OK, NIVEL_ROJO, alertas_por_anuncio,
                             alertas_por_campana, anuncios_con_pocos_clics,
                             anuncios_sin_impresiones, resumen)
from core.helpers import kpi_card
from modules.mercado_libre.views.helpers import badge, empty_state, fmt_decimal, fmt_money, fmt_num

_ETIQUETA_CORTA = {
    NIVEL_ROJO: "🔴 Rojo",
    NIVEL_AMARILLO: "🟡 Amarillo",
    NIVEL_OK: "🟢 OK",
}


def _color_nivel(valor):
    for clave, etiqueta in _ETIQUETA_CORTA.items():
        if valor == etiqueta:
            return f"color: {COLOR_NIVEL[clave]}; font-weight: 600"
    return ""


def render(cuenta: str, ads: pd.DataFrame | None) -> None:
    st.markdown("### 🎯 Alertas de campañas")
    st.caption(
        f"Marca en amarillo lo que supera {config.ACOS_ALERTA_AMARILLA:g}% de "
        f"ACOS y en rojo lo que cae por debajo de {config.ROAS_ALERTA_ROJA:g} "
        f"de ROAS, sobre anuncios con al menos {config.MIN_CLICS_ALERTA} clics."
    )

    if ads is None or ads.empty:
        empty_state(
            "Sin reporte de publicidad cargado",
            "Subí el reporte semanal de Product Ads en la pestaña de importación.",
        )
        return

    totales = resumen(ads)

    columnas = st.columns(5)
    tarjetas = [
        ("Inversión", fmt_money(totales["inversion"])),
        ("Ingresos", fmt_money(totales["ingresos"])),
        ("ACOS global", f"{totales['acos']:.1f}%" if totales["acos"] else "—"),
        ("Alertas rojas", fmt_num(totales["rojos"])),
        ("Alertas amarillas", fmt_num(totales["amarillos"])),
    ]
    for columna, (etiqueta, valor) in zip(columnas, tarjetas):
        with columna:
            st.markdown(kpi_card(label=etiqueta, value=valor),
                        unsafe_allow_html=True)
    st.markdown("")

    por_campana = alertas_por_campana(ads)
    st.markdown("#### Por campaña")
    st.caption(
        "El ACOS y el ROAS de la campaña se calculan sobre la inversión total, "
        "no promediando los anuncios: así un anuncio chico no pesa lo mismo que "
        "uno que se lleva la mayor parte del presupuesto."
    )
    tabla_campana = pd.DataFrame({
        "Campaña": por_campana["campana"],
        "Anuncios": por_campana["anuncios"],
        "Clics": por_campana["clics"],
        "Inversión": por_campana["inversion"],
        "Ingresos": por_campana["ingresos"],
        "ACOS": por_campana["acos"],
        "ROAS": por_campana["roas"],
        "Nivel": por_campana["nivel"].map(_ETIQUETA_CORTA),
    })
    st.dataframe(
        tabla_campana.style
        .map(_color_nivel, subset=["Nivel"])
        .format({
            "Clics": fmt_num, "Anuncios": fmt_num,
            "Inversión": fmt_money, "Ingresos": fmt_money,
            "ACOS": lambda v: f"{v:.1f}%" if pd.notna(v) else "—",
            "ROAS": lambda v: fmt_decimal(v, 2),
        }),
        use_container_width=True, hide_index=True,
    )

    st.divider()
    st.markdown("#### Por anuncio")

    alertas = alertas_por_anuncio(ads)
    if alertas.empty:
        st.info(
            f"Ningún anuncio alcanzó los {config.MIN_CLICS_ALERTA} clics "
            "necesarios para evaluar su eficiencia en este período."
        )
    else:
        solo_alertas = st.checkbox(
            "Mostrar solo los que tienen alerta", value=True,
            key="meli_ads_filtro",
        )
        mostrar = alertas[alertas["nivel"] != NIVEL_OK] if solo_alertas else alertas

        sin_ingresos = mostrar[
            (mostrar["ingresos"].fillna(0) == 0) & (mostrar["inversion"].fillna(0) > 0)
        ]
        if not sin_ingresos.empty:
            perdida = sin_ingresos["inversion"].sum()
            st.error(
                f"{len(sin_ingresos)} anuncio(s) gastaron "
                f"{fmt_money(perdida)} sin generar ningún ingreso en el período. "
                "Son los primeros a revisar."
            )

        tabla_anuncio = pd.DataFrame({
            "Campaña": mostrar["campana"],
            "MLA": mostrar["mla"],
            "Anuncio": mostrar["anuncio"].astype(str).str.slice(0, 45),
            "Clics": mostrar["clics"],
            "Inversión": mostrar["inversion"],
            "Ingresos": mostrar["ingresos"],
            "ACOS": mostrar["acos"],
            "ROAS": mostrar["roas"],
            "Nivel": mostrar["nivel"].map(_ETIQUETA_CORTA),
        })
        st.dataframe(
            tabla_anuncio.style
            .map(_color_nivel, subset=["Nivel"])
            .format({
                "Clics": fmt_num, "Inversión": fmt_money, "Ingresos": fmt_money,
                "ACOS": lambda v: f"{v:.1f}%" if pd.notna(v) else "—",
                "ROAS": lambda v: fmt_decimal(v, 2),
            }),
            use_container_width=True, hide_index=True,
        )

    sin_impresiones = anuncios_sin_impresiones(ads)
    pocos_clics = anuncios_con_pocos_clics(ads)

    st.divider()
    columna_izq, columna_der = st.columns(2)

    with columna_izq:
        st.markdown(f"#### Sin impresiones ({len(sin_impresiones)})")
        st.caption(
            "Acá el problema no es la rentabilidad sino que el anuncio no se "
            "está mostrando: puja, presupuesto o estado."
        )
        if sin_impresiones.empty:
            st.success("Todos los anuncios tuvieron impresiones.")
        else:
            st.dataframe(sin_impresiones, use_container_width=True,
                         hide_index=True, height=280)

    with columna_der:
        st.markdown(f"#### Pocos clics ({len(pocos_clics)})")
        st.caption(
            f"Tuvieron impresiones pero menos de {config.MIN_CLICS_ALERTA} "
            "clics. Se listan para dejar constancia: todavía no hay datos "
            "suficientes para juzgar su eficiencia."
        )
        if pocos_clics.empty:
            st.success("Sin anuncios en esta zona.")
        else:
            st.dataframe(pocos_clics, use_container_width=True,
                         hide_index=True, height=280)

    with st.expander("📖 Sobre los umbrales configurados"):
        st.markdown(
            f"""
Los dos cortes actuales no son independientes entre sí. Un ROAS de
{config.ROAS_ALERTA_ROJA:g} equivale a un ACOS del 33%, así que **todo anuncio
en rojo también supera el corte amarillo de {config.ACOS_ALERTA_AMARILLA:g}%**.
En la práctica la alerta roja funciona como un subconjunto más grave de la
amarilla, no como un criterio distinto.

Si lo que se busca es que sean dos niveles separados, el corte rojo tendría que
moverse hacia un ROAS cercano a 6,7 (o el amarillo hacia un ACOS del 33%). Los
dos valores se editan en `config.py` sin tocar la lógica.
"""
        )
