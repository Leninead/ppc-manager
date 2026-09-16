"""
Modulo: Dashboard Global de Agencia (M39)
Seccion: Direccion (admin-only)
Version: v1 — B3a-1 (registro; la tabla llega en B3a-2)

Pantalla de Direccion: proyectado vs real cross-cuenta en 5 metricas (Revenue /
Ad Sales / Spend / ACOS / TACOS), mes a mes.

Esta pagina NO calcula nada: toda la logica vive en `core/agency_dashboard.py`
(B2), que es pura y esta testeada. Aca solo se elige la ventana de meses, se
llama al agregador y se muestra el resultado. El nombre del archivo lleva
`_page` a proposito, para no confundirlo con `core/agency_dashboard.py`.
"""
from __future__ import annotations

import streamlit as st

MODULE_SLUG = "agency-dashboard"


def _header() -> None:
    st.markdown("## 🌐 Dashboard Global")
    st.caption(
        "📊 Proyectado vs real por cuenta y por mes — Revenue · Ad Sales · Spend · "
        "ACOS · TACOS · "
        "Output: la foto de cumplimiento de la agencia para Direccion"
    )
    st.divider()


def render() -> None:
    """Punto de entrada del modulo. Llamado desde app.py."""
    _header()
    st.info(
        "🚧 **En construccion.** El agregador cross-cuenta ya esta listo "
        "(`core/agency_dashboard.py`); la tabla en pantalla llega en el proximo "
        "bloque."
    )
