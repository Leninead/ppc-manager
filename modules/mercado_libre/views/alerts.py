"""Feature 3 view — Product Ads campaign alerts."""
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

_SHORT_LABEL = {
    NIVEL_ROJO: "🔴 Rojo",
    NIVEL_AMARILLO: "🟡 Amarillo",
    NIVEL_OK: "🟢 OK",
}


def _color_level(value):
    for key, label in _SHORT_LABEL.items():
        if value == label:
            return f"color: {COLOR_NIVEL[key]}; font-weight: 600"
    return ""


def render(account: str, ads: pd.DataFrame | None) -> None:
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

    totals = resumen(ads)

    cols = st.columns(5)
    cards = [
        ("Inversión", fmt_money(totals["inversion"])),
        ("Ingresos", fmt_money(totals["ingresos"])),
        ("ACOS global", f"{totals['acos']:.1f}%" if totals["acos"] else "—"),
        ("Alertas rojas", fmt_num(totals["rojos"])),
        ("Alertas amarillas", fmt_num(totals["amarillos"])),
    ]
    for col, (label, value) in zip(cols, cards):
        with col:
            st.markdown(kpi_card(label=label, value=value),
                        unsafe_allow_html=True)
    st.markdown("")

    by_campaign = alertas_por_campana(ads)
    st.markdown("#### Por campaña")
    st.caption(
        "El ACOS y el ROAS de la campaña se calculan sobre la inversión total, "
        "no promediando los anuncios: así un anuncio chico no pesa lo mismo que "
        "uno que se lleva la mayor parte del presupuesto."
    )
    campaign_table = pd.DataFrame({
        "Campaña": by_campaign["campana"],
        "Anuncios": by_campaign["anuncios"],
        "Clics": by_campaign["clics"],
        "Inversión": by_campaign["inversion"],
        "Ingresos": by_campaign["ingresos"],
        "ACOS": by_campaign["acos"],
        "ROAS": by_campaign["roas"],
        "Nivel": by_campaign["nivel"].map(_SHORT_LABEL),
    })
    st.dataframe(
        campaign_table.style
        .map(_color_level, subset=["Nivel"])
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

    alerts_df = alertas_por_anuncio(ads)
    if alerts_df.empty:
        st.info(
            f"Ningún anuncio alcanzó los {config.MIN_CLICS_ALERTA} clics "
            "necesarios para evaluar su eficiencia en este período."
        )
    else:
        only_alerts = st.checkbox(
            "Mostrar solo los que tienen alerta", value=True,
            key="meli_ads_filtro",
        )
        visible = alerts_df[alerts_df["nivel"] != NIVEL_OK] if only_alerts else alerts_df

        no_revenue = visible[
            (visible["ingresos"].fillna(0) == 0) & (visible["inversion"].fillna(0) > 0)
        ]
        if not no_revenue.empty:
            loss = no_revenue["inversion"].sum()
            st.error(
                f"{len(no_revenue)} anuncio(s) gastaron "
                f"{fmt_money(loss)} sin generar ningún ingreso en el período. "
                "Son los primeros a revisar."
            )

        ad_table = pd.DataFrame({
            "Campaña": visible["campana"],
            "MLA": visible["mla"],
            "Anuncio": visible["anuncio"].astype(str).str.slice(0, 45),
            "Clics": visible["clics"],
            "Inversión": visible["inversion"],
            "Ingresos": visible["ingresos"],
            "ACOS": visible["acos"],
            "ROAS": visible["roas"],
            "Nivel": visible["nivel"].map(_SHORT_LABEL),
        })
        st.dataframe(
            ad_table.style
            .map(_color_level, subset=["Nivel"])
            .format({
                "Clics": fmt_num, "Inversión": fmt_money, "Ingresos": fmt_money,
                "ACOS": lambda v: f"{v:.1f}%" if pd.notna(v) else "—",
                "ROAS": lambda v: fmt_decimal(v, 2),
            }),
            use_container_width=True, hide_index=True,
        )

    no_impressions = anuncios_sin_impresiones(ads)
    few_clicks = anuncios_con_pocos_clics(ads)

    # The two remaining blocks are DIAGNOSTIC cases, not action rows for
    # the AM. They used to occupy two side-by-side `st.dataframe(...,
    # height=280)` panels with hundreds of repeated MLA ids (measured: 224
    # without impressions · 25 with few clicks on a real client). A one-line
    # summary + expander for the detail reclaims 560 px of screen without
    # losing access to the listing when the ids really need to be inspected.
    if not (no_impressions.empty and few_clicks.empty):
        st.divider()
        pieces = []
        if not no_impressions.empty:
            pieces.append(
                f"**{len(no_impressions)}** sin impresiones — puja, "
                "presupuesto o estado"
            )
        if not few_clicks.empty:
            pieces.append(
                f"**{len(few_clicks)}** con menos de "
                f"{config.MIN_CLICS_ALERTA} clics — sin datos para juzgar"
            )
        st.caption("Sin evaluar: " + " · ".join(pieces) + ".")

        with st.expander("Ver los anuncios sin evaluar", expanded=False):
            if not no_impressions.empty:
                st.markdown(f"**Sin impresiones ({len(no_impressions)})**")
                st.caption(
                    "Acá el problema no es la rentabilidad sino que el "
                    "anuncio no se está mostrando: puja, presupuesto o estado."
                )
                st.dataframe(no_impressions, use_container_width=True,
                             hide_index=True, height=280)
            if not few_clicks.empty:
                if not no_impressions.empty:
                    st.divider()
                st.markdown(f"**Pocos clics ({len(few_clicks)})**")
                st.caption(
                    f"Tuvieron impresiones pero menos de "
                    f"{config.MIN_CLICS_ALERTA} clics. Todavía no hay datos "
                    "suficientes para juzgar su eficiencia."
                )
                st.dataframe(few_clicks, use_container_width=True,
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
