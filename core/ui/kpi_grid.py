"""Grilla de KPI cards que se acomoda sola a la cantidad de tarjetas y al ancho disponible.

`kpi_card()` de core/helpers dibuja UNA tarjeta y deja el layout en manos del módulo, que hasta
ahora armaba `st.columns(n)` a mano: con 12 KPIs eso da filas de altura distinta según si la
tarjeta tiene delta o no, y en pantallas angostas las columnas se achican hasta romper el texto.
Acá el layout es una grilla CSS: las filas las decide el navegador por ancho disponible, y todas
las tarjetas de una fila miden lo mismo porque la grilla las estira.
"""
from __future__ import annotations

import html
from dataclasses import dataclass

CARD_BACKGROUND = "#FFF3E0"
CARD_BORDER = "#FFD9B3"
LABEL_COLOR = "#888"
VALUE_COLOR = "#1F1F1F"
DELTA_GOOD_COLOR = "#1B6B2F"
DELTA_BAD_COLOR = "#B71C1C"
DELTA_FLAT_COLOR = "#888"

# Debajo de este ancho la etiqueta de dos palabras empieza a cortarse.
MIN_CARD_WIDTH_PX = 190
MAX_COLUMNS = 5
GRID_CLASS = "cap-kpi-grid"
# Anchos donde una fila de 4-5 tarjetas ya no entra sin romper la etiqueta.
TABLET_BREAKPOINT_PX = 900
PHONE_BREAKPOINT_PX = 520
# El divisor que las páginas dibujan debajo trae ~1rem de margen propio: sin compensarlo acá,
# la banda queda con 26px arriba y 42 abajo y las tarjetas se ven pegadas al borde de arriba.
MARGIN_TOP_REM = 1.6
MARGIN_BOTTOM_REM = 0.6


@dataclass(frozen=True)
class Kpi:
    label: str
    value: str
    delta: float | None = None
    delta_good: bool = True


def delta_html(delta: float | None, delta_good: bool) -> str:
    """La línea de variación, o nada.

    Las tarjetas sin delta no reservan su lugar: la grilla ya las estira todas al alto de la fila
    (`align-items:stretch`), así que reservar el hueco sólo servía para correr el contenido hacia
    arriba y dejar las tarjetas descentradas.
    """
    if delta is None:
        return ""
    if delta > 0:
        arrow, color = "↑", DELTA_GOOD_COLOR if delta_good else DELTA_BAD_COLOR
    elif delta < 0:
        arrow, color = "↓", DELTA_BAD_COLOR if delta_good else DELTA_GOOD_COLOR
    else:
        arrow, color = "→", DELTA_FLAT_COLOR
    return (f"<div style='font-size:0.72rem;color:{color};font-weight:600;line-height:1.2'>"
            f"{arrow} {abs(delta):.1f}%</div>")


def kpi_card_html(kpi: Kpi) -> str:
    return (
        f"<div style='background:{CARD_BACKGROUND};border:1px solid {CARD_BORDER};border-radius:10px;"
        f"padding:0.8rem 1rem;text-align:center;display:flex;flex-direction:column;"
        f"align-items:center;justify-content:center;gap:0.15rem'>"
        f"<div style='font-size:0.72rem;color:{LABEL_COLOR};font-weight:600;text-transform:uppercase;"
        f"letter-spacing:0.05em;line-height:1.2'>{html.escape(str(kpi.label))}</div>"
        f"<div style='font-size:1.4rem;font-weight:800;color:{VALUE_COLOR};line-height:1.2'>"
        f"{html.escape(str(kpi.value))}</div>"
        f"{delta_html(kpi.delta, kpi.delta_good)}"
        f"</div>")


def balanced_columns(card_count: int) -> int:
    """Cuántas columnas dejan la última fila completa, sin pasar de MAX_COLUMNS.

    Con 12 KPIs, repartirlos por ancho disponible daba 5 + 5 + 2: la fila corta se lee como un
    error de carga. Se prefiere el reparto más ancho que divide justo, y si ninguno divide, 4.
    """
    if card_count <= 0:
        return 0
    if card_count <= MAX_COLUMNS:
        return card_count
    for columns in range(MAX_COLUMNS, 1, -1):
        if card_count % columns == 0:
            return columns
    return 4


def kpi_grid_html(kpis: list[Kpi], *, columns: int | None = None) -> str:
    """Las tarjetas en una grilla. `columns` fuerza el reparto; si no, se elige el balanceado.

    Las filas se angostan solas en tablet y caen a una sola columna en teléfono, así que la misma
    llamada sirve para 3 KPIs y para 12 sin scroll horizontal.
    """
    if not kpis:
        return ""
    count = columns or balanced_columns(len(kpis))
    cards = "".join(kpi_card_html(kpi) for kpi in kpis)
    # La clase lleva la cantidad de columnas: dos grillas distintas en la misma página no se pisan,
    # y dos iguales repiten la misma regla sin efecto.
    grid_class = f"{GRID_CLASS}-{count}"
    return (
        f"<style>.{grid_class}{{display:grid;gap:0.6rem;align-items:stretch;"
        f"margin:{MARGIN_TOP_REM}rem 0 {MARGIN_BOTTOM_REM}rem;"
        f"grid-template-columns:repeat({count},minmax(0,1fr));}}"
        f"@media(max-width:{TABLET_BREAKPOINT_PX}px){{.{grid_class}"
        f"{{grid-template-columns:repeat({min(count, 2)},minmax(0,1fr));}}}}"
        f"@media(max-width:{PHONE_BREAKPOINT_PX}px){{.{grid_class}{{grid-template-columns:1fr;}}}}"
        f"</style><div class='{grid_class}'>{cards}</div>")


def render_kpi_grid(kpis: list[Kpi], *, columns: int | None = None) -> None:
    import streamlit as st

    st.markdown(kpi_grid_html(kpis, columns=columns), unsafe_allow_html=True)
