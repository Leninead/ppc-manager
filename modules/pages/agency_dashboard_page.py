"""
Modulo: Dashboard Global de Agencia (M39)
Seccion: Direccion (admin-only)
Version: v1 — B3a-2 (tabla en pantalla; los exports llegan en B3b)

Pantalla de Direccion: proyectado vs real cross-cuenta en 5 metricas (Revenue /
Ad Sales / Spend / ACOS / TACOS), mes a mes, una tabla por cuenta.

Esta pagina NO calcula nada: toda la logica vive en `core/agency_dashboard.py`
(B2), que es pura y esta testeada. Aca solo se elige la ventana de meses, se
llama al agregador, se formatea y se pinta. El nombre del archivo lleva `_page`
a proposito, para no confundirlo con `core/agency_dashboard.py`.
"""
from __future__ import annotations

from datetime import date

import streamlit as st

from core.agency_dashboard import _build_agency_dashboard
# El formato y el semáforo viven en un módulo compartido: los consumen esta
# pantalla y los exports (B3b). Una sola fuente de verdad del color.
from core.agency_dashboard_export import _build_agency_excel, _build_agency_html
from core.agency_dashboard_format import (
    _account_df,
    _build_periods,
    _style_df,
)
from core.integrations import roles

MODULE_SLUG = "agency-dashboard"


_DEFAULT_ATRAS = 2
_DEFAULT_ADELANTE = 3

_SOP_MD = """
Esta pantalla compara, cuenta por cuenta y mes por mes, **lo que se proyecto
contra lo que paso**.

- **Actual** es el dato real del mes. Sale del historico de Monthly Forecast
  (M31) cuando el mes ya cerro y el AM le cargo el Spend, o de la capa del mes
  real cuando todavia esta corriendo.
- **Acco** es el cumplimiento contra el **plan oficial**: el snapshot marcado
  con ⭐ en M31. En Revenue, Ad Sales y Ad Spend es un porcentaje; en ACOS y
  TACOS es la diferencia en **puntos** contra el target.
- Una cuenta **sin plan cargado** aparece igual, con la columna Acco vacia. Que
  se vea el hueco es el punto: significa que falta marcar el baseline en M31.
- Un mes marcado con `*` esta **en curso**: el real cubre solo los dias
  transcurridos y se compara contra un plan de mes completo, asi que el
  cumplimiento se lee bajo.
"""

# ─────────────────────────────────────────────────────────────────────────────
# Render
# ─────────────────────────────────────────────────────────────────────────────

def _header() -> None:
    st.markdown("## 🌐 Dashboard Global")
    st.caption(
        "📊 Proyectado vs real por cuenta y por mes — Revenue · Ad Sales · Spend · "
        "ACOS · TACOS · "
        "Output: la foto de cumplimiento de la agencia para Direccion"
    )
    st.divider()


def render(username: str = "", role: str = roles.USER) -> None:
    """Punto de entrada del modulo. Llamado desde app.py con username y role.

    El guard de rol va ANTES de cargar nada: `ADMIN_ONLY` solo esconde el boton
    del riel, y esta pantalla muestra la facturacion de TODAS las cuentas.
    Mismo patron que `modules/pages/integrations.py`.
    """
    _header()

    if not roles.is_admin(role):
        st.info(
            "Esta pantalla es solo para Dirección. Si necesitás verla, pedí "
            "acceso de admin."
        )
        return

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    col_atras, col_adelante, _sp = st.columns([1, 1, 3])
    atras = col_atras.number_input(
        "Meses hacia atrás", min_value=0, max_value=12, step=1,
        value=_DEFAULT_ATRAS, key="m39_meses_atras",
        help="Cuántos meses cerrados se muestran antes del mes en curso.",
    )
    adelante = col_adelante.number_input(
        "Meses hacia adelante", min_value=0, max_value=12, step=1,
        value=_DEFAULT_ADELANTE, key="m39_meses_adelante",
        help="Meses proyectados. Sin real todavía: la columna Actual va vacía.",
    )

    periods = _build_periods(int(atras), int(adelante))
    data = _build_agency_dashboard(periods)
    accounts = data.get("accounts") or []

    if not accounts:
        st.info(
            "No hay cuentas con forecast cargado en M31 (Monthly Forecast). "
            "Cargá al menos un cliente ahí y marcá su plan oficial con ⭐ para "
            "que aparezca acá."
        )
        return

    st.caption(
        f"{len(accounts)} cuenta{'s' if len(accounts) != 1 else ''} · "
        f"{len(periods)} meses ({periods[0]} → {periods[-1]})"
    )

    # El HTML se arma en cada run: es barato (string puro sobre datos que ya
    # están en memoria) y así el archivo siempre refleja la ventana que el AM
    # tiene en pantalla, sin un botón de "generar" intermedio.
    hoy = date.today()
    col_html, col_xlsx, _sp_dl = st.columns([1, 1, 3])
    col_html.download_button(
        "⬇️ Descargar HTML",
        data=_build_agency_html(data, generated_at=hoy),
        file_name=f"dashboard-global-agencia-{hoy.isoformat()}.html",
        mime="text/html",
        key="m39_dl_html",
        help="Documento standalone: se abre con doble clic y se manda por mail.",
        use_container_width=True,
    )
    col_xlsx.download_button(
        "⬇️ Descargar Excel",
        data=_build_agency_excel(data, generated_at=hoy),
        file_name=f"dashboard-global-agencia-{hoy.isoformat()}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="m39_dl_xlsx",
        help="Mismo layout que la pantalla, con el semáforo en las métricas de %.",
        use_container_width=True,
    )

    algun_parcial = False
    for account in accounts:
        st.markdown("")
        df, hay_parcial = _account_df(account, periods)
        algun_parcial = algun_parcial or hay_parcial

        col_nombre, col_badge = st.columns([3, 2])
        col_nombre.markdown(f"#### {account.get('name') or account.get('client_id')}")
        if account.get("has_baseline"):
            col_badge.caption(
                f"⭐ Plan: {account.get('baseline_name')} "
                f"({account.get('baseline_created_at')})"
            )
        else:
            col_badge.caption("⚠️ sin plan cargado — marcá el baseline en M31")

        st.dataframe(
            _style_df(account, periods, df),
            use_container_width=True,
        )

    if algun_parcial:
        st.caption(
            "\\* Mes en curso (MtD): el real cubre solo los días transcurridos, "
            "y el cumplimiento se mide contra un plan de mes completo — se lee "
            "bajo a propósito, sin prorratear."
        )
