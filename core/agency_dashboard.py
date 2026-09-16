"""Agregador cross-cuenta del dashboard global de agencia (B2).

Arma, por cuenta y por mes, "esto proyecté / esto pasó" en las 5 métricas del
dashboard (Revenue / Ad Sales / Spend / ACOS / TACOS) con su cumplimiento.

Lógica pura sin UI: lo consume el módulo del dashboard. Vive en `core/` y no en
`modules/pages/` porque no es una página y `revenue_forecast.py` ya pasa las
6.000 líneas. La dependencia va en una sola dirección: este archivo importa de
`modules.pages.revenue_forecast` (M31 es la única fuente del dato), nunca al
revés. Importar M31 arrastra Streamlit por transitividad; este archivo no lo
usa.

API:
    _build_agency_dashboard(periods, clients=None) -> dict    (puro)
    _load_agency_clients() -> list[dict]                      (única que toca disco)
"""

from __future__ import annotations

import copy
from typing import Any, Optional

from core.forecast_persistence import _list_forecast_clients, _load_forecast_client
from modules.pages.revenue_forecast import (
    AREA,
    MODULE_SLUG,
    _get_baseline_snapshot,
    _loaded_float,
    _month_actual,
    _month_forecast,
    _month_key,
)

# Métricas con cumplimiento en % (real / forecast * 100).
_PCT_METRICS = ("revenue", "ventasPPC", "spend")

# Métricas con cumplimiento en DELTA DE PUNTOS (real - forecast).
_DELTA_METRICS = ("acos", "tacos")


# ─────────────────────────────────────────────────────────────────────────────
# Cálculo de cumplimiento
# ─────────────────────────────────────────────────────────────────────────────

def _pct(real: Optional[float], forecast: Optional[float]) -> Optional[float]:
    """real / forecast * 100, o None si falta alguno o el forecast es 0.

    None significa "no se puede calcular": nunca 0 ni infinito.
    """
    if real is None or forecast is None or forecast == 0:
        return None
    return real / forecast * 100


def _delta_pts(real: Optional[float], forecast: Optional[float]) -> Optional[float]:
    """real - forecast en puntos porcentuales, o None si falta alguno.

    Signo CRUDO: positivo = el real está por ENCIMA del forecast. En ACOS / TACOS
    eso es PEOR (se gastó más de lo planeado), al revés que en revenue. No se
    invierte acá: lo decide la presentación (B3).
    """
    if real is None or forecast is None:
        return None
    return real - forecast


def _accomplishment(actual: Optional[dict], forecast: Optional[dict]) -> dict:
    """Cumplimiento por métrica de un mes.

    - Revenue / Ad Sales (`ventasPPC`) / Spend → % (`_pct`).
    - ACOS / TACOS → delta en PUNTOS (`_delta_pts`), NO %. Un ACOS real de 31
      contra un target de 30 es +1.0, no 103,3%. Signo crudo (ver `_delta_pts`).

    Sin actual o sin forecast, todas las métricas van en None.
    """
    actual = actual or {}
    forecast = forecast or {}
    out = {m: _pct(actual.get(m), forecast.get(m)) for m in _PCT_METRICS}
    for metric in _DELTA_METRICS:
        out[metric] = _delta_pts(actual.get(metric), forecast.get(metric))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Forecast del baseline con el "0.0 sin target" neutralizado
# ─────────────────────────────────────────────────────────────────────────────

def _baseline_row(cur: dict, period: str) -> Optional[dict]:
    """Fila CRUDA del snapshot baseline para ese mes, o None.

    Hace falta para ver `acosTarget`, que `_month_forecast` no devuelve. Se
    resuelve acá y no extendiendo `_month_forecast` porque "un ACOS de 0 sin
    target no es un plan" es un criterio de ESTE consumidor: M31 muestra el 0
    tal cual en su propia tabla, y su contrato no cambia.
    """
    key = _month_key(period)
    baseline = _get_baseline_snapshot(cur)
    if key is None or baseline is None:
        return None
    return next(
        (r for r in baseline.get("forecast") or [] if r.get("date") == key), None
    )


def _forecast_cell(cur: dict, period: str) -> Optional[dict]:
    """`_month_forecast` con el ACOS proyectado de 0 sin `acosTarget` → None.

    ACOS: un `acos` de 0 cuya fila no tiene `acosTarget` cargado —criterio
    `_loaded_float`: None, '' y NaN son "sin dato"— se reporta como None. Un
    ACOS objetivo de 0% no describe ningún plan alcanzable (ventas publicitarias
    infinitas por peso gastado), y llegar crudo a un PDF que ve Dirección diría
    "target 0%". NO es que el motor escriba 0.0 cuando falta el target: al
    generar lo rellena con el ACOS promedio o 30, y si el AM borra la celda
    `_apply_forecast_edits` lo restaura a 30.0 (medido por el camino de la UI).
    El camino real de aparición es que el AM escriba 0 a mano, o una fila que
    no vino del motor. Un 0 con `acosTarget` 0 explícito se respeta, y un valor
    distinto de 0 nunca se toca.

    TACOS: se reporta TAL CUAL, sin mirar `tacosTarget`. `tacosTarget` es None
    por default en toda fila del motor, y un spend planeado de 0 da `tacos` 0.0:
    es la proyección correcta de un mes SIN pauta, no un dato faltante. Pasarlo
    a None escondería justo el caso donde el cumplimiento importa — gastar contra
    un plan de cero (real 2.5 vs plan 0 = +2.5 puntos).

    Returns:
        Copia del dict de `_month_forecast` (no muta el snapshot), o None.
    """
    forecast = _month_forecast(cur, period)
    if forecast is None:
        return None
    forecast = dict(forecast)
    row = _baseline_row(cur, period) or {}
    if forecast.get("acos") == 0 and _loaded_float(row.get("acosTarget")) is None:
        forecast["acos"] = None
    return forecast


# ─────────────────────────────────────────────────────────────────────────────
# Agregador
# ─────────────────────────────────────────────────────────────────────────────

def _build_account(cur: dict, periods: list[str]) -> dict:
    """Bloque de una cuenta: identidad, baseline y una celda por mes."""
    baseline = _get_baseline_snapshot(cur)
    months: dict[str, dict] = {}
    for period in periods:
        actual = _month_actual(cur, period)
        forecast = _forecast_cell(cur, period)
        months[period] = {
            "actual": actual,
            "forecast": forecast,
            "accomplishment": _accomplishment(actual, forecast),
            "partial": actual.get("partial") if actual else None,
        }
    return {
        "client_id": str(cur.get("id") or ""),
        "name": str(cur.get("name") or ""),
        "currency": str(cur.get("currency") or "USD"),
        "has_baseline": baseline is not None,
        "baseline_name": baseline.get("name") if baseline else None,
        "baseline_created_at": baseline.get("created_at") if baseline else None,
        "months": months,
    }


def _build_agency_dashboard(
    periods: list[str], clients: Optional[list[dict]] = None,
) -> dict:
    """Arma el dashboard cross-cuenta: actual, forecast y cumplimiento por mes.

    Reglas:
        1. Revenue / Ad Sales / Spend: cumplimiento = real / forecast * 100.
           Falta alguno o forecast 0 → None (nunca 0 ni infinito).
        2. ACOS / TACOS: DELTA EN PUNTOS = real - forecast, NO %. Signo crudo:
           positivo = real por encima del target, que en ACOS/TACOS es PEOR. La
           trampa obvia es invertirlo acá; no se invierte, lo colorea B3.
        3. ACOS proyectado 0 sin `acosTarget` cargado en la fila → None, y su
           cumplimiento también. TACOS proyectado se reporta tal cual: un 0.0 es
           un plan sin pauta, no un dato faltante (ver `_forecast_cell`).
        4. MtD PARCIAL CRUDO: con `partial=True` el cumplimiento se calcula igual,
           SIN prorratear el forecast por días transcurridos. `partial` viaja en
           la celda para que B3 lo marque. Prorratear es una decisión de
           presentación todavía no confirmada con Dirección; si se confirma, va
           en B3 sin tocar esta función.

    Las cuentas SIN baseline entran igual (`has_baseline=False`, forecast y
    cumplimiento en None): que una cuenta aparezca vacía dice "falta cargar el
    plan", y esconderla sería perder esa información.

    Args:
        periods: meses "YYYY-MM" en el orden en que se muestran. Lo decide quien
            llama: no se deriva ni se calcula con la fecha de hoy. Vacío →
            cuentas sin meses, sin error.
        clients: dicts de cliente ya cargados. None → `_load_agency_clients()`.
            Existe para que los tests no toquen disco. No se mutan.

    Returns:
        {"periods": [...], "accounts": [{client_id, name, currency, has_baseline,
        baseline_name, baseline_created_at, months: {period: {actual, forecast,
        accomplishment, partial}}}]}. Cuentas ordenadas por nombre
        (case-insensitive, desempate por client_id): mismo input → mismo output,
        sin depender del orden del disco.
    """
    periods = list(periods or [])
    if clients is None:
        clients = _load_agency_clients()
    accounts = [_build_account(c, periods) for c in clients]
    accounts.sort(key=lambda a: (a["name"].casefold(), a["client_id"]))
    return {"periods": periods, "accounts": accounts}


# ─────────────────────────────────────────────────────────────────────────────
# Carga desde disco — la ÚNICA función del archivo con I/O
# ─────────────────────────────────────────────────────────────────────────────

def _load_agency_clients() -> list[dict]:
    """Carga todos los clientes de M31 desde la persistencia (local o remota).

    Lista con `_list_forecast_clients(AREA, MODULE_SLUG)`, saltea `_meta` y carga
    cada `client.json`. Los que vuelven vacíos se saltean, y un cliente que no se
    puede leer (JSON corrupto, error del backend) también: una cuenta rota no
    tumba el dashboard de las demás.

    Returns:
        Lista de dicts de cliente, en el orden en que los lista el backend, en
        COPIAS PROFUNDAS.

    El deepcopy es DEFENSIVO, no una optimización: el dashboard no puede
    depender de qué devuelve el backend de turno. Medido en este entorno:
    `_LocalBackend` relee el archivo y devuelve un objeto nuevo por llamada, y
    con `st.cache_data` activo el wrapper también entrega una copia — en esos
    dos caminos la copia sobra. Pero un backend que guarde estado EN MEMORIA
    (los fakes de los tests hoy; cualquier cache in-process mañana) devuelve la
    referencia viva, y un consumidor que la mute ensuciaría el estado de M31 —
    el mismo dict que el módulo persiste.

    Costo medido (B2b, clientes sintéticos): ~40 ms con 80 cuentas, ~30% del
    tiempo de carga en frío (106-168 ms). Aceptable para un dashboard que se
    abre y se lee.
    """
    out: list[dict] = []
    for slug in _list_forecast_clients(AREA, MODULE_SLUG):
        if slug == "_meta":
            continue
        try:
            data: Any = _load_forecast_client(AREA, slug, MODULE_SLUG, "client")
        except Exception:  # noqa: BLE001 — una cuenta rota no tumba el resto
            continue
        if isinstance(data, dict) and data:
            out.append(copy.deepcopy(data))
    return out
