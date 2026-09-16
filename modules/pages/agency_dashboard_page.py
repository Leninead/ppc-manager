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
from typing import Optional

import pandas as pd
import streamlit as st

from core.agency_dashboard import _build_agency_dashboard
from core.integrations import roles

MODULE_SLUG = "agency-dashboard"

# Filas de la tabla, en el orden del mockup de Direccion. Cada una es
# (key en el dict de datos, etiqueta visible).
_METRICS: tuple[tuple[str, str], ...] = (
    ("revenue", "Revenue"),
    ("ventasPPC", "Ad Sales"),
    ("spend", "Ad Spend"),
    ("acos", "ACOS"),
    ("tacos", "TACOS"),
)

# Metricas cuyo cumplimiento viene en % (real / forecast * 100). Las que NO
# estan aca (acos, tacos) vienen en DELTA DE PUNTOS, con signo crudo.
_PCT_METRICS = frozenset({"revenue", "ventasPPC", "spend"})

_MESES_ABBR = ("Ene", "Feb", "Mar", "Abr", "May", "Jun",
               "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")

# Semaforo del mockup: fondos suaves, texto negro legible encima.
_VERDE = "#E8F5E9"
_AMARILLO = "#FFF8E1"
_ROJO = "#FFEBEE"

# Umbral de tolerancia para ACOS / TACOS, en PUNTOS porcentuales.
_DELTA_TOLERANCIA = 2.0

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
# Helpers puros — ventana de meses
# ─────────────────────────────────────────────────────────────────────────────

def _build_periods(atras: int, adelante: int,
                   hoy: Optional[date] = None) -> list[str]:
    """Ventana de meses "YYYY-MM" alrededor del mes actual, inclusive.

    Args:
        atras: meses hacia atras del actual.
        adelante: meses hacia adelante del actual.
        hoy: inyectable para tests; default `date.today()`.

    Returns:
        Lista ordenada asc, de largo `atras + 1 + adelante`.
    """
    if hoy is None:
        hoy = date.today()
    base = hoy.year * 12 + (hoy.month - 1)
    out = []
    for i in range(-int(atras), int(adelante) + 1):
        y, m = divmod(base + i, 12)
        out.append(f"{y:04d}-{m + 1:02d}")
    return out


def _month_label(period: str, with_year: bool) -> str:
    """"2026-08" → "Ago" (o "Ago 26" si la ventana cruza años).

    El año se agrega SOLO cuando hace falta: con una ventana que va de
    noviembre a febrero, tres "Ene" sin año serían ambiguos.
    """
    try:
        year, month = period.split("-")
        label = _MESES_ABBR[int(month) - 1]
    except (ValueError, IndexError, AttributeError):
        return str(period)
    return f"{label} {year[2:]}" if with_year else label


# ─────────────────────────────────────────────────────────────────────────────
# Helpers puros — formato de celda
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_actual(metric_id: str, value, currency: str) -> str:
    """Celda "Actual": moneda para Revenue / Ad Sales / Ad Spend, % para los
    ratios. None → '' (mes futuro o metrica sin dato).

    Los montos van sin decimales: en un tablero de Direccion los centavos son
    ruido.
    """
    if value is None:
        return ""
    if metric_id in _PCT_METRICS:
        return f"{currency} {value:,.0f}"
    return f"{value:.1f}%"


def _fmt_acco(metric_id: str, value) -> str:
    """Celda "Acco" (cumplimiento). None → ''.

    Revenue / Ad Sales / Ad Spend: porcentaje del plan ("90.0%").
    ACOS / TACOS: DELTA EN PUNTOS con signo explicito ("+1.0" / "-1.0"), NUNCA
    porcentaje. Un ACOS real de 31 contra un target de 30 es +1 punto, no
    103,3%; el signo es lo que se lee de un vistazo.
    """
    if value is None:
        return ""
    if metric_id in _PCT_METRICS:
        return f"{value:.1f}%"
    return f"{value:+.1f}"


# ─────────────────────────────────────────────────────────────────────────────
# Helper puro — semaforo
# ─────────────────────────────────────────────────────────────────────────────
#
# ⚠️ LOS DOS REGIMENES SON OPUESTOS. No unificar.
#
# Revenue / Ad Sales / Ad Spend traen un % de cumplimiento: MAS es MEJOR.
#     >= 90    verde · 85-89,99 amarillo · < 85 rojo
#
# ACOS / TACOS traen un DELTA EN PUNTOS con signo crudo (real - plan), donde
# POSITIVO significa que el real quedo POR ENCIMA del target, o sea que se
# gasto MAS de lo planeado: MAS es PEOR.
#     <= 0     verde  (en el target o mejor)
#     0 a +2   amarillo
#     > +2     rojo
#
# Leer un +1 de ACOS con la regla de revenue lo pintaria rojo (1 << 85) cuando
# en realidad es una desviacion chica. El test
# `test_acos_signo_invertido` blinda esta diferencia.

def _acco_color(metric_id: str, value) -> str:
    """Color de fondo de una celda Acco. '' si no hay dato (sin color)."""
    if value is None:
        return ""
    if metric_id in _PCT_METRICS:
        if value >= 90:
            return _VERDE
        if value >= 85:
            return _AMARILLO
        return _ROJO
    # acos / tacos: delta en puntos, positivo = peor.
    if value <= 0:
        return _VERDE
    if value <= _DELTA_TOLERANCIA:
        return _AMARILLO
    return _ROJO


# ─────────────────────────────────────────────────────────────────────────────
# Armado de la tabla de una cuenta
# ─────────────────────────────────────────────────────────────────────────────

def _account_df(account: dict, periods: list[str]) -> tuple[pd.DataFrame, bool]:
    """DataFrame de display de una cuenta + si tiene algun mes en curso.

    Filas: las 5 metricas del mockup. Columnas: dos por mes ("Ago Actual",
    "Ago Acco"), aplanadas porque Streamlit no hace multi-header nativo. Un mes
    en curso lleva `*` en su etiqueta.

    TODAS las celdas son `str` — nunca None ni NaN: el DataFrame va a
    `st.dataframe` y una columna con None mezclado es justo lo que rompe la
    conversion a Arrow.

    Args:
        account: un elemento de `data["accounts"]`.
        periods: la ventana, en orden de display.

    Returns:
        (df, hay_parcial).
    """
    currency = account.get("currency") or "USD"
    months = account.get("months") or {}
    with_year = len({p[:4] for p in periods}) > 1

    columnas: list[str] = []
    datos: dict[str, list[str]] = {}
    hay_parcial = False

    for period in periods:
        cell = months.get(period) or {}
        actual = cell.get("actual") or {}
        acco = cell.get("accomplishment") or {}
        parcial = cell.get("partial") is True
        hay_parcial = hay_parcial or parcial

        label = _month_label(period, with_year) + ("*" if parcial else "")
        col_actual, col_acco = f"{label} Actual", f"{label} Acco"
        columnas += [col_actual, col_acco]
        datos[col_actual] = [
            _fmt_actual(mid, actual.get(mid), currency) for mid, _ in _METRICS
        ]
        datos[col_acco] = [_fmt_acco(mid, acco.get(mid)) for mid, _ in _METRICS]

    df = pd.DataFrame(datos, index=[label for _, label in _METRICS])
    return df[columnas], hay_parcial


def _style_df(account: dict, periods: list[str], df: pd.DataFrame):
    """Aplica el semaforo a las columnas Acco. Devuelve un Styler."""
    months = account.get("months") or {}
    # Mapa columna Acco -> period, para leer el valor CRUDO (el del DataFrame ya
    # es string formateado y no sirve para comparar).
    col_period: dict[str, str] = {}
    for period, col in zip(periods, [c for c in df.columns if c.endswith(" Acco")]):
        col_period[col] = period

    def _colores(frame: pd.DataFrame) -> pd.DataFrame:
        out = pd.DataFrame("", index=frame.index, columns=frame.columns)
        for col, period in col_period.items():
            acco = (months.get(period) or {}).get("accomplishment") or {}
            for (mid, label) in _METRICS:
                color = _acco_color(mid, acco.get(mid))
                if color:
                    out.loc[label, col] = f"background-color: {color}; color: #1F1F1F;"
        return out

    return df.style.apply(_colores, axis=None)


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
