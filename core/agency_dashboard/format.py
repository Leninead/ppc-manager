"""Formato y semáforo del Dashboard Global de Agencia (M39).

Capa PURA: formatea las celdas de la tabla y decide su color. No toca Streamlit,
no lee disco y no calcula métricas — el cálculo vive en `core/agency_dashboard/dashboard.py`
(B2) y esto solo presenta lo que ese agregador devuelve.

Vive acá, y no en `modules/pages/agency_dashboard_page.py`, porque lo consumen
DOS lados: la pantalla y los exports (HTML / Excel / PDF). Tenerlo en la página
obligaba al export a importarla, y como la página importa al export para el
botón de descarga, eso cerraba un ciclo de imports que rompe de verdad
(`ImportError: cannot import name ... from partially initialized module`).

Una sola fuente de verdad del semáforo: si esto se duplicara, la pantalla y el
PDF que ve Dirección podrían pintar la misma celda de distinto color.
"""
from __future__ import annotations

from datetime import date
from typing import Optional

import pandas as pd

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

# Medio paso del formato de celda: `_fmt_acco` imprime el delta con 1 decimal
# ("{:+.1f}"), asi que cualquier magnitud menor a 0,05 se muestra como "+0.0" y
# es indistinguible de cero para quien mira la tabla. Por debajo de eso, el
# color acompaña a lo que dice la celda: verde.
_DELTA_EPS = 0.05

# Leyenda de la columna Acco para ACOS / TACOS. Vive acá y no en cada superficie
# porque la consumen las tres (pantalla, HTML y Excel) y tienen que decir lo
# mismo: ese número es un DESVÍO EN PUNTOS contra el plan, no un porcentaje de
# cumplimiento como en Revenue / Ad Sales / Ad Spend. Pedido de Dirección tras
# la validación del 16/09.
_LEYENDA_ACCO = (
    "En ACOS y TACOS, la columna Acco es el desvío en puntos contra el plan "
    "(real − plan): un valor positivo significa por encima de lo planeado."
)


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
    # El verde llega hasta +_DELTA_EPS (0,05) y no hasta 0: un delta de
    # +1,3e-06 se muestra "+0.0" y pintarlo amarillo contradice a la celda.
    # Bordes: +0.05 exacto va verde, +0.06 amarillo, y el rojo sigue en >2.
    if value <= _DELTA_EPS:
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


