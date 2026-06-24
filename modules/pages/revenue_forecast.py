"""M31 — Revenue Forecast (port del HTML standalone a módulo Streamlit).

Sección: Account Manager
Página: 📈 Revenue Forecast
Fase: 2 (INGESTA + VISUALIZACIÓN — parser by-date de Business Report +
config de cuenta editable + history table editable + quick stats con deltas
MoM/YoY + demo Dermaglos cargable). SIN motor de forecast (F3) ni persistencia
activa (F4).

Las Fases 3+ portearán generateForecast / recomputeForecastRow / seasonality /
ASIN drill-down. Este archivo deja todo el cableado listo para que esos pasos
sean aditivos (no hay refactor pendiente del state ni de la persistencia).

──────────────────────────────────────────────────────────────────────────────
Decisiones de diseño F1 (documentadas in-line)
──────────────────────────────────────────────────────────────────────────────

1. ACCESSOR DE CLIENTE ACTIVO (`_cur_client`)
   El HTML original usa un Proxy JavaScript que redirige `state.<algo>` al
   cliente activo (eg. `state.historical` → `state.clients[active].historical`).
   En Python NO existe equivalente directo y limpio del Proxy, así que se
   reemplaza por un accessor explícito: `_cur_client(state)` devuelve el dict
   del cliente activo. Para campos individuales que el motor futuro va a leer/
   escribir frecuentemente (historical, forecast, seasonality, asins,
   selectedAsin) se exponen getters/setters dedicados.

   El accessor acepta `state` como parámetro opcional con default
   `st.session_state` — esto lo hace TESTEABLE sin runtime Streamlit
   (los tests pasan un dict simulado).

2. STATE EN session_state PURO (Fase 1)
   El state nace en `st.session_state` con prefijo `m31_` para no colisionar
   con otros módulos. Inicialización idempotente vía `_ensure_state()`.

3. PERSISTENCIA DORMIDA (Patrón M30/Caso 2)
   Los helpers `_persist_clients()` / `_hydrate_clients()` están definidos y
   cablean a la API dedicada de `core.forecast_persistence`. Pero en Fase 1
   están GUARDIADOS por el flag `_PERSISTENCE_ENABLED = False` y NUNCA se
   invocan desde el flujo de inicialización. El state vive 100% en session_state.

   Para encender la persistencia en Fase 2:
       1) Setear `_PERSISTENCE_ENABLED = True`.
       2) Llamar `_hydrate_clients()` dentro de `_ensure_state()` cuando
          session_state esté vacío.
       3) Llamar `_persist_clients()` después de cualquier mutación
          (crear / borrar / actualizar campos persistibles).
       4) Si se persisten DataFrames (snapshots de forecast), agregar el
          schema `data/_schemas/revenue-forecast-v1.json` y validarlo.

   La persistencia respeta `_get_backend()` de core.forecast_persistence:
   local por default, Supabase sólo con flag `AGENCY_OS_FORECAST_BACKEND=
   "supabase"` + creds. Independiente del flag de Account Health.

4. CLIENTES M31 ≠ CLIENTES DE ACCOUNT HEALTH (D3 — convivencia, no unión)
   M31 mantiene su PROPIO catálogo de clientes y su PROPIA capa de
   persistencia (`core.forecast_persistence`). NO se unifica con `ah_*_configs`
   ni con `_list_clientes("account-health", ...)`. M31 vive en
   area="account-manager"; AH vive en area="account-health". Paths y tablas
   disjuntos. Si más adelante se decide unificar, el accessor `_cur_client`
   queda como única superficie de cambio.
"""

from __future__ import annotations

import json
import re
from datetime import date
from io import BytesIO
from typing import Any, Optional

import pandas as pd
import streamlit as st

from core.helpers import kpi_card

# Imports de la capa de persistencia DEDICADA a M31 (cableados pero DORMIDOS
# en F1). Capa separada de Account Health por decisión D3: los clientes M31
# conviven con AH pero NO comparten storage. Ver `core/forecast_persistence.py`
# para el contrato y la motivación.
from core.forecast_persistence import (
    _save_forecast_client,
    _load_forecast_client,
    _list_forecast_clients,
)


# ─────────────────────────────────────────────────────────────────────────────
# Constantes del módulo
# ─────────────────────────────────────────────────────────────────────────────

AREA = "account-manager"
MODULE_SLUG = "revenue-forecast"
SCHEMA_VERSION = 1

# Prefijo de keys en session_state. NUNCA reusar keys entre módulos.
_STATE_PREFIX = "m31_"
_K_CLIENTS = f"{_STATE_PREFIX}clients"
_K_ACCOUNT_MANAGERS = f"{_STATE_PREFIX}account_managers"
_K_ACTIVE_CLIENT_ID = f"{_STATE_PREFIX}active_client_id"

# ⚠ FLAG MAESTRO: persistencia DORMIDA en Fase 1. NO encender sin completar
# los 4 pasos documentados en el docstring del módulo.
_PERSISTENCE_ENABLED = False

# SOP in-app — Fase 2.
_SOP_MD = """
### Revenue Forecast — cómo usarlo (Fase 2)

Módulo de **ingesta y visualización** del histórico de revenue. El motor de
forecast llega en F3, la persistencia entre sesiones en F4.

**Flujo del AM:**
1. **Cliente activo:** elegí (o creá vía demo) el cliente con el selector.
2. **Config de cuenta:** marketplace, moneda, margen, modo YoY — quedan en el cliente.
3. **Cargar Business Report:** exportá de Amazon → Seller Central → Business Reports
   → "By Date · Sales and Traffic" (mensual). Subí el CSV o XLSX. La carga **se
   mergea** con el histórico: meses nuevos se agregan, los existentes se
   actualizan con los datos del CSV. **Spend** y **Ventas PPC** manuales **se
   conservan** entre uploads.
4. **History table:** editá Spend y Ventas PPC mes a mes — ACOS y TACOS reales
   se calculan al instante.
5. **Quick stats:** deltas MoM/YoY del último mes vs anterior y vs el mismo mes
   del año pasado.

**Demo Dermaglos:** 23 meses (jun-2024 a abr-2026) cargables con un click para
probar el flujo sin Business Report real.

**Próximas fases:**
- F3: motor `generateForecast` + estacionalidad + drill-down por ASIN.
- F4: persistencia activa + snapshots versionados.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Modelo de cliente — constructor con defaults
# ─────────────────────────────────────────────────────────────────────────────

def _new_client(
    name: str,
    marketplace: str = "US",
    am_id: Optional[str] = None,
    margin: float = 0.30,
    currency: str = "USD",
    yoy_mode: str = "auto",
    client_id: Optional[str] = None,
) -> dict:
    """Constructor de un cliente nuevo con defaults completos (shape estable).

    El shape de retorno es el contrato que el motor futuro (Fase 2+) va a
    consumir. Cualquier cambio acá obliga a bumpear el schema.

    Notas de diseño:
    - `created_at` se genera al MOMENTO de la llamada (no en import-time),
      vía `date.today().isoformat()`. Esto evita capturar la fecha de import.
    - `seasonality.indices` arranca con 12 valores neutros (1.0) — un mes
      no tiene boost ni penalty hasta que el usuario los configure.
    - `client_id` se genera vía slug del nombre + timestamp si no se pasa.
      Determinístico cuando el caller lo provee (útil en tests).

    Args:
        name: nombre display del cliente.
        marketplace: código de marketplace (US, MX, ES, BR, CA…).
        am_id: id del Account Manager asignado. None = sin asignar.
        margin: margen bruto operativo (0.30 = 30%). Default neutro.
        currency: moneda en que vive el histórico (USD, MXN, EUR…).
        yoy_mode: modo de cálculo YoY ('auto', 'manual', 'off').
        client_id: id explícito; si None se genera del slug del name.

    Returns:
        dict con el shape completo del cliente (15 keys).
    """
    if client_id is None:
        slug = name.strip().lower().replace(" ", "-")
        # Timestamp de hoy para garantizar unicidad si se crean 2 clientes
        # con el mismo nombre.
        client_id = f"{slug}-{date.today().isoformat()}"

    return {
        "id": client_id,
        "name": name,
        "marketplace": marketplace,
        "am_id": am_id,
        "margin": margin,
        "currency": currency,
        "yoy_mode": yoy_mode,
        "historical": [],          # lista de dicts {date, revenue, units, …}
        "forecast": [],            # lista de dicts {date, projected_revenue, …}
        "snapshots": [],           # lista de snapshots versionados del forecast
        "seasonality": {
            "enabled": False,
            "indices": [1.0] * 12,  # 1 índice por mes (Ene..Dic), neutro = 1.0
        },
        "asins": [],               # lista de dicts {asin, name, share, …}
        "selected_asin": None,     # id del ASIN seleccionado para drill-down
        "created_at": date.today().isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# State management — inicialización idempotente
# ─────────────────────────────────────────────────────────────────────────────

def _ensure_state(state: Optional[Any] = None) -> None:
    """Siembra las keys del módulo en `state` si no existen (idempotente).

    Llamar al inicio de `render()`. Si las keys ya están, NO las pisa.

    Decisión F1: NO hidrata desde disco. El catálogo de clientes vive sólo
    en session_state durante esta fase. Para activar hidratación en F2, ver
    docstring del módulo (sección "Persistencia dormida").

    Args:
        state: dict-like (session_state o equivalente para tests). Si None,
            usa `st.session_state`.
    """
    if state is None:
        state = st.session_state

    if _K_CLIENTS not in state:
        state[_K_CLIENTS] = []
    if _K_ACCOUNT_MANAGERS not in state:
        state[_K_ACCOUNT_MANAGERS] = []
    if _K_ACTIVE_CLIENT_ID not in state:
        state[_K_ACTIVE_CLIENT_ID] = None


def _seed_demo_client_if_empty(state: Optional[Any] = None) -> None:
    """Siembra un cliente demo si el catálogo está vacío.

    Sólo para que el selector de cliente nunca se renderee con lista vacía
    en Fase 1. En F2+ esta lógica podría reemplazarse por una hidratación
    real desde disco.

    Args:
        state: dict-like; default `st.session_state`.
    """
    if state is None:
        state = st.session_state

    clients = state.get(_K_CLIENTS, [])
    if not clients:
        demo = _new_client(
            name="Demo Client",
            marketplace="US",
            margin=0.30,
            currency="USD",
            client_id="demo-client",
        )
        state[_K_CLIENTS] = [demo]
        state[_K_ACTIVE_CLIENT_ID] = demo["id"]


# ─────────────────────────────────────────────────────────────────────────────
# Accessor de cliente activo — reemplazo del Proxy JS del HTML
# ─────────────────────────────────────────────────────────────────────────────

def _cur_client(state: Optional[Any] = None) -> Optional[dict]:
    """Devuelve el dict del cliente activo, o None si no hay ninguno.

    REEMPLAZA EL PROXY JS DEL HTML ORIGINAL.
    El HTML usa un Proxy que redirige `state.<campo>` al cliente activo
    (eg. `state.historical` → `state.clients[active].historical`). En Python
    se reemplaza por este accessor explícito + getters/setters dedicados
    abajo. El motor de forecast (Fase 2+) lee TODO desde acá.

    Args:
        state: dict-like; default `st.session_state`.

    Returns:
        dict del cliente activo, o None si no hay cliente seleccionado o el
        id seleccionado no matchea ningún cliente.
    """
    if state is None:
        state = st.session_state

    active_id = state.get(_K_ACTIVE_CLIENT_ID)
    if active_id is None:
        return None

    for c in state.get(_K_CLIENTS, []):
        if c.get("id") == active_id:
            return c
    return None


def _set_active_client(client_id: Optional[str], state: Optional[Any] = None) -> bool:
    """Marca un cliente como activo por id.

    Si `client_id` no existe en el catálogo, NO cambia el activo y devuelve
    False (fail-soft: el caller decide cómo recuperarse — típicamente,
    refrescar el selector).

    Args:
        client_id: id del cliente a activar; None desactiva la selección.
        state: dict-like; default `st.session_state`.

    Returns:
        True si la selección se aplicó, False si el id no existe.
    """
    if state is None:
        state = st.session_state

    if client_id is None:
        state[_K_ACTIVE_CLIENT_ID] = None
        return True

    for c in state.get(_K_CLIENTS, []):
        if c.get("id") == client_id:
            state[_K_ACTIVE_CLIENT_ID] = client_id
            return True
    return False


# Getters dedicados — superficie estable para el motor F2+. Devuelven defaults
# vacíos si no hay cliente activo, así el motor no tiene que rectear el caso.

def _get_historical(state: Optional[Any] = None) -> list:
    """Histórico del cliente activo. Lista vacía si no hay activo."""
    c = _cur_client(state)
    return c["historical"] if c else []


def _get_forecast(state: Optional[Any] = None) -> list:
    """Forecast del cliente activo. Lista vacía si no hay activo."""
    c = _cur_client(state)
    return c["forecast"] if c else []


def _get_seasonality(state: Optional[Any] = None) -> dict:
    """Seasonality del cliente activo. Dict neutro si no hay activo."""
    c = _cur_client(state)
    if c is None:
        return {"enabled": False, "indices": [1.0] * 12}
    return c["seasonality"]


def _get_asins(state: Optional[Any] = None) -> list:
    """ASINs del cliente activo. Lista vacía si no hay activo."""
    c = _cur_client(state)
    return c["asins"] if c else []


def _get_selected_asin(state: Optional[Any] = None) -> Optional[str]:
    """ASIN seleccionado para drill-down. None si no hay activo o sin seleccionar."""
    c = _cur_client(state)
    return c["selected_asin"] if c else None


# ─────────────────────────────────────────────────────────────────────────────
# Persistencia — DORMIDA en Fase 1 (cableada pero NO invocada)
# ─────────────────────────────────────────────────────────────────────────────
#
# Estos helpers están definidos para que Fase 2 sólo tenga que (1) flippear
# `_PERSISTENCE_ENABLED = True` y (2) wirearlos en `_ensure_state` (hidratar)
# y en los puntos de mutación (persistir). Hoy son no-op completos:
#   - _hydrate_clients() devuelve [] (no toca disco).
#   - _persist_clients() es no-op (no toca disco).
#
# Cuando se enciendan, usan `_save_forecast_client` / `_load_forecast_client` /
# `_list_forecast_clients` de core.forecast_persistence (capa dedicada M31),
# que respetan su propio `_get_backend()` — local por default, Supabase con
# flag `AGENCY_OS_FORECAST_BACKEND="supabase"` + creds. NO comparte tablas con
# Account Health.

def _persist_clients(state: Optional[Any] = None) -> None:
    """Persiste el catálogo de clientes y el id activo. NO-OP en Fase 1.

    Cuando se encienda (F2+):
        - 1 client_config por cliente en (AREA, cliente_slug, MODULE_SLUG, "client").
        - 1 client_config global en (AREA, "_meta", MODULE_SLUG, "active") con
          el id activo.

    Args:
        state: dict-like; default `st.session_state`.
    """
    if not _PERSISTENCE_ENABLED:
        return  # dormido

    if state is None:
        state = st.session_state

    for c in state.get(_K_CLIENTS, []):
        _save_forecast_client(
            config=c,
            area=AREA,
            cliente=c["id"],
            modulo=MODULE_SLUG,
            name="client",
        )
    _save_forecast_client(
        config={"active_client_id": state.get(_K_ACTIVE_CLIENT_ID)},
        area=AREA,
        cliente="_meta",
        modulo=MODULE_SLUG,
        name="active",
    )


def _hydrate_clients(state: Optional[Any] = None) -> None:
    """Hidrata el catálogo desde disco. NO-OP en Fase 1.

    Cuando se encienda (F2+):
        - Lista clientes con `_list_forecast_clients(AREA, MODULE_SLUG)`.
        - Carga cada uno con `_load_forecast_client(AREA, cliente_slug,
          MODULE_SLUG, "client")`.
        - Carga el id activo desde `(_meta, MODULE_SLUG, "active")`.

    Args:
        state: dict-like; default `st.session_state`.
    """
    if not _PERSISTENCE_ENABLED:
        return  # dormido

    if state is None:
        state = st.session_state

    cliente_slugs = _list_forecast_clients(AREA, MODULE_SLUG)
    loaded = []
    for slug in cliente_slugs:
        if slug == "_meta":
            continue
        c = _load_forecast_client(AREA, slug, MODULE_SLUG, "client")
        if c:
            loaded.append(c)
    state[_K_CLIENTS] = loaded

    meta = _load_forecast_client(AREA, "_meta", MODULE_SLUG, "active")
    state[_K_ACTIVE_CLIENT_ID] = meta.get("active_client_id") if meta else None


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Constantes ES (port de MONTHS_ES / MONTHS_FULL, L1139-1140)
# ─────────────────────────────────────────────────────────────────────────────

_MONTHS_ES = [
    "Ene", "Feb", "Mar", "Abr", "May", "Jun",
    "Jul", "Ago", "Sep", "Oct", "Nov", "Dic",
]
_MONTHS_FULL = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
_MARKETPLACES = ["US", "MX", "ES", "BR", "CA", "UK", "DE", "FR", "IT", "JP"]
# Port verbatim del select del HTML L741-743 (sin reordenar).
_CURRENCIES = [
    "USD", "MXN", "EUR", "GBP", "CAD", "JPY", "BRL", "AUD",
    "INR", "AED", "SGD", "SAR", "TRY", "SEK", "PLN",
]
_YOY_MODES = ["auto", "on", "off"]


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Demo Dermaglos (port de DEMAGLOS_DATA L1242)
# ─────────────────────────────────────────────────────────────────────────────
#
# 23 registros mensuales, jun-2024 a abr-2026. Fiel al HTML L5899: al cargarlo,
# spend y ventasPPC arrancan en None (no vienen del CSV — los carga el AM).
# NOTA: la constante del HTML se llama DEMAGLOS sin R (typo del autor original).
# Respetamos su contenido, no su nombre — en Python le decimos DERMAGLOS_DATA.

_DERMAGLOS_DATA: list[dict] = json.loads("""
[{"date":"2024-06-01","revenue":1157.17,"revenueB2B":41.8,"units":249,"sessions":1486,"pageViews":1998,"buyBox":89.42,"cvr":16.76},
 {"date":"2024-07-01","revenue":1793.3,"revenueB2B":34.92,"units":123,"sessions":1396,"pageViews":2075,"buyBox":88.62,"cvr":8.81},
 {"date":"2024-08-01","revenue":1508.63,"revenueB2B":22.41,"units":91,"sessions":1125,"pageViews":1515,"buyBox":92.06,"cvr":8.09},
 {"date":"2024-09-01","revenue":1385.31,"revenueB2B":0,"units":88,"sessions":1144,"pageViews":1708,"buyBox":91.65,"cvr":7.69},
 {"date":"2024-10-01","revenue":2989.18,"revenueB2B":63.78,"units":209,"sessions":2382,"pageViews":3147,"buyBox":96.36,"cvr":8.77},
 {"date":"2024-11-01","revenue":2346.72,"revenueB2B":28.4,"units":204,"sessions":1982,"pageViews":2962,"buyBox":98.2,"cvr":10.29},
 {"date":"2024-12-01","revenue":2229.16,"revenueB2B":5.99,"units":171,"sessions":2153,"pageViews":3061,"buyBox":97.5,"cvr":7.94},
 {"date":"2025-01-01","revenue":3282.4,"revenueB2B":32.37,"units":236,"sessions":2314,"pageViews":3311,"buyBox":97.16,"cvr":10.2},
 {"date":"2025-02-01","revenue":4047.86,"revenueB2B":110.62,"units":291,"sessions":3152,"pageViews":4386,"buyBox":97.44,"cvr":9.23},
 {"date":"2025-03-01","revenue":5977.72,"revenueB2B":119.19,"units":555,"sessions":4970,"pageViews":7155,"buyBox":97.78,"cvr":11.17},
 {"date":"2025-04-01","revenue":5767.12,"revenueB2B":76.65,"units":424,"sessions":4515,"pageViews":6204,"buyBox":97.41,"cvr":9.39},
 {"date":"2025-05-01","revenue":5354.91,"revenueB2B":52.36,"units":395,"sessions":3923,"pageViews":5230,"buyBox":97.79,"cvr":10.07},
 {"date":"2025-06-01","revenue":5888.37,"revenueB2B":49.95,"units":407,"sessions":2745,"pageViews":3818,"buyBox":97.51,"cvr":14.83},
 {"date":"2025-07-01","revenue":6201.73,"revenueB2B":134.5,"units":458,"sessions":3368,"pageViews":4560,"buyBox":97.42,"cvr":13.6},
 {"date":"2025-08-01","revenue":5054.35,"revenueB2B":123.34,"units":330,"sessions":3102,"pageViews":4181,"buyBox":97.7,"cvr":10.64},
 {"date":"2025-09-01","revenue":5335.34,"revenueB2B":130.85,"units":361,"sessions":4195,"pageViews":5371,"buyBox":98.57,"cvr":8.61},
 {"date":"2025-10-01","revenue":6081.48,"revenueB2B":222.53,"units":433,"sessions":4576,"pageViews":5699,"buyBox":99.28,"cvr":9.46},
 {"date":"2025-11-01","revenue":5968.93,"revenueB2B":138.62,"units":534,"sessions":4042,"pageViews":5410,"buyBox":98.69,"cvr":13.21},
 {"date":"2025-12-01","revenue":4682.69,"revenueB2B":172.47,"units":313,"sessions":3415,"pageViews":4319,"buyBox":98.18,"cvr":9.17},
 {"date":"2026-01-01","revenue":5497.12,"revenueB2B":137.34,"units":354,"sessions":5957,"pageViews":7434,"buyBox":99.14,"cvr":5.94},
 {"date":"2026-02-01","revenue":5438.27,"revenueB2B":242.84,"units":358,"sessions":4231,"pageViews":5502,"buyBox":99.09,"cvr":8.46},
 {"date":"2026-03-01","revenue":5492.97,"revenueB2B":270.9,"units":391,"sessions":4261,"pageViews":5549,"buyBox":98.34,"cvr":9.18},
 {"date":"2026-04-01","revenue":5432.28,"revenueB2B":128.17,"units":368,"sessions":4522,"pageViews":5702,"buyBox":99.06,"cvr":8.14}]
""")


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Helpers de formato (port de fmtCurrency / fmtNum / fmtPct / parseNum)
# ─────────────────────────────────────────────────────────────────────────────

_CURRENCY_SYMBOLS = {
    "USD": "$", "MXN": "$", "EUR": "€", "GBP": "£", "CAD": "$", "JPY": "¥",
    "BRL": "R$", "AUD": "$", "INR": "₹", "AED": "د.إ", "SGD": "$",
    "SAR": "﷼", "TRY": "₺", "SEK": "kr", "PLN": "zł",
}


def _currency_symbol(currency: str) -> str:
    """Port de currencySymbol L1250: default '$' si la moneda no está en el dict."""
    return _CURRENCY_SYMBOLS.get(currency, "$")


def _fmt_currency(n: Optional[float], currency: str = "USD", dec: int = 0) -> str:
    """Port de fmtCurrency L1253 / fmtCurrency2 L1258 (parametrizable por dec)."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    sym = _currency_symbol(currency)
    return f"{sym}{n:,.{dec}f}"


def _fmt_num(n: Optional[float], dec: int = 0) -> str:
    """Port de fmtNum L1263."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    return f"{n:,.{dec}f}"


def _fmt_pct(n: Optional[float], dec: int = 1) -> str:
    """Port de fmtPct L1267."""
    if n is None or (isinstance(n, float) and pd.isna(n)):
        return "—"
    return f"{n:.{dec}f}%"


def _parse_num(v: Any) -> float:
    """Port de parseNum L1271: limpia $,% y , y devuelve 0 si no parsea."""
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    s = re.sub(r"[$,%]", "", str(v)).replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def _delta_pct(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
    """Port de deltaPct L1285: None si prev es 0/None/NaN."""
    if prev is None or curr is None:
        return None
    if isinstance(prev, float) and pd.isna(prev):
        return None
    if isinstance(curr, float) and pd.isna(curr):
        return None
    if prev == 0:
        return None
    return (curr - prev) / prev * 100.0


def _same_month_last_year(iso: str, rows: list[dict]) -> Optional[dict]:
    """Port de sameMonthLastYear L1749: busca el mismo mes/día del año pasado.

    El HTML usa Date.setUTCFullYear(-1) y slice(0,10). Acá: parseo del iso,
    resto 1 al año, recompongo. Devuelve el dict del histórico que matchea,
    o None si no existe.
    """
    try:
        # iso es YYYY-MM-DD; el HTML compara con findHistorical(slice(0,10)).
        # Replicamos: año-1, mismo mes, mismo día.
        year, month, day = iso.split("-")
        target = f"{int(year) - 1:04d}-{month}-{day}"
    except (ValueError, AttributeError):
        return None
    for r in rows:
        if r.get("date") == target:
            return r
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Parser by-date (port de mapRowByDate L1354)
# ─────────────────────────────────────────────────────────────────────────────

def _norm_hdr(s: Any) -> str:
    """Port del normHdr inline en mapRowByDate L1356:
       strip BOM, colapsar separadores () - : . / – —, lowercase.
    """
    raw = str(s or "")
    raw = raw.replace("﻿", "")
    raw = re.sub(r"[\(\)\-\:\.\/]", " ", raw)
    raw = re.sub(r"[–—]", " ", raw)
    raw = re.sub(r"\s+", " ", raw).strip().lower()
    return raw


def _find_by_keywords(
    norm_map: dict,
    required: list[str],
    forbidden: Optional[list[str]] = None,
) -> Any:
    """Port de findByKeywords inline en mapRowByDate L1360:
       primer header normalizado que contiene todos los `required` y ninguno
       de los `forbidden`; devuelve el value crudo o None.
    """
    forbidden = forbidden or []
    for nk in norm_map:
        if all(kw in nk for kw in required) and all(kw not in nk for kw in forbidden):
            v = norm_map[nk]
            # fiel al HTML L1365: salta vacíos y None
            if v != "" and v is not None and not (isinstance(v, float) and pd.isna(v)):
                return v
    return None


def _map_row_by_date(row: dict) -> Optional[dict]:
    """Port verbatim de mapRowByDate L1354. Devuelve None si no hay date.

    Mapeo (fiel al HTML):
        Date / fecha / Month        → date (ISO YYYY-MM-DD)
        Ordered Product Sales       → revenue (excl B2B)
        Ordered Product Sales B2B   → revenueB2B
        Units Ordered               → units (excl B2B)
        Sessions Total              → sessions (fallback: Browser + Mobile App)
        Page Views Total            → pageViews (fallback: Browser + Mobile App)
        Buy Box % / Featured Offer  → buyBox
        Unit Session %              → cvr

    spend y ventasPPC NO vienen del CSV — los inicializa mergeHistorical.
    """
    norm_map = {_norm_hdr(k): v for k, v in row.items()}

    # Date — fiel a L1372-1385.
    date_raw = (
        row.get("Date") or row.get("date") or row.get("Fecha") or row.get("Month")
        or _find_by_keywords(norm_map, ["date"])
        or _find_by_keywords(norm_map, ["fecha"])
        or _find_by_keywords(norm_map, ["month"])
    )
    if date_raw is None or (isinstance(date_raw, float) and pd.isna(date_raw)):
        return None

    d_str = str(date_raw).strip()
    iso: Optional[str] = None
    if re.match(r"^\d{4}-\d{2}-\d{2}", d_str):
        iso = d_str[:10]
    else:
        m = re.match(r"^(\d{1,2})\/(\d{1,2})\/(\d{2,4})$", d_str)
        if not m:
            return None
        # fiel al HTML L1380-1384: M/D/Y (formato US — NO D/M/Y).
        yr = int(m.group(3))
        if yr < 100:
            yr = 2000 + yr
        iso = f"{yr:04d}-{int(m.group(1)):02d}-{int(m.group(2)):02d}"

    revenue = _parse_num(_find_by_keywords(norm_map, ["ordered", "product", "sales"], ["b2b"]))
    revenue_b2b = _parse_num(_find_by_keywords(norm_map, ["ordered", "product", "sales", "b2b"]))
    units = _parse_num(_find_by_keywords(norm_map, ["units", "ordered"], ["b2b"]))

    # Sessions: prefer Total; else Browser + Mobile App. Fiel a L1393-1400.
    sess_total = _find_by_keywords(
        norm_map, ["sessions", "total"],
        ["b2b", "browser", "mobile", "app", "percentage"],
    )
    if sess_total is not None:
        sessions = _parse_num(sess_total)
    else:
        sb = _find_by_keywords(norm_map, ["sessions", "browser"], ["b2b", "percentage"])
        sa = (
            _find_by_keywords(norm_map, ["sessions", "mobile"], ["b2b", "percentage"])
            or _find_by_keywords(norm_map, ["sessions", "app"], ["b2b", "percentage"])
        )
        sessions = (_parse_num(sb) if sb is not None else 0) + (_parse_num(sa) if sa is not None else 0)

    # Page Views — mismo patrón. L1402-1410.
    pv_total = _find_by_keywords(
        norm_map, ["page", "views", "total"],
        ["b2b", "browser", "mobile", "app", "percentage"],
    )
    if pv_total is not None:
        page_views = _parse_num(pv_total)
    else:
        pb = _find_by_keywords(norm_map, ["page", "views", "browser"], ["b2b", "percentage"])
        pa = (
            _find_by_keywords(norm_map, ["page", "views", "mobile"], ["b2b", "percentage"])
            or _find_by_keywords(norm_map, ["page", "views", "app"], ["b2b", "percentage"])
        )
        page_views = (_parse_num(pb) if pb is not None else 0) + (_parse_num(pa) if pa is not None else 0)

    # Buy Box: 'buy box' o 'featured offer'. Fiel a L1412.
    buy_box = _parse_num(
        _find_by_keywords(norm_map, ["buy", "box"], ["b2b"])
        or _find_by_keywords(norm_map, ["featured", "offer"], ["b2b"])
    )
    cvr = _parse_num(_find_by_keywords(norm_map, ["unit", "session"], ["b2b"]))

    return {
        "date": iso,
        "revenue": revenue,
        "revenueB2B": revenue_b2b,
        "units": units,
        "sessions": sessions,
        "pageViews": page_views,
        "buyBox": buy_box,
        "cvr": cvr,
    }


@st.cache_data(show_spinner=False)
def _parse_business_report(data: bytes, filename: str) -> list[dict]:
    """Parsea CSV o XLSX del BR by-date. Recibe bytes (no UploadedFile) para
    que el cache de Streamlit funcione (patrón M30).

    El HTML solo soporta CSV vía PapaParse (L1334). Acá agregamos XLSX porque
    Amazon también permite ese export y es trivial con pandas. Si el archivo
    es XLSX, leemos la primera hoja; si es CSV, autodetectamos separador (el
    HTML usa PapaParse que ya lo hace).

    Devuelve la lista de rows mapeadas y ordenadas por date asc (fiel a
    `rows.sort((a,b) => a.date.localeCompare(b.date))`, L1344).

    Args:
        data: bytes crudos del archivo.
        filename: nombre del archivo (para decidir CSV vs XLSX por extensión).

    Returns:
        Lista de dicts con shape by-date (8 keys). Lista vacía si no se pudo
        parsear ninguna fila.
    """
    lower = filename.lower()
    if lower.endswith((".xlsx", ".xls")):
        df = pd.read_excel(BytesIO(data))
    else:
        # CSV. Autodetección de separador como en el resto del repo.
        sample = data[:4096].decode("utf-8-sig", errors="ignore")
        first_line = sample.split("\n", 1)[0] if sample else ""
        sep = ";" if first_line.count(";") > first_line.count(",") else ","
        df = pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=sep)

    # Iteramos dict por fila para reusar el mapeo verbatim.
    rows: list[dict] = []
    for raw in df.to_dict("records"):
        mapped = _map_row_by_date(raw)
        if mapped is not None:
            rows.append(mapped)
    rows.sort(key=lambda r: r["date"])
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Merge histórico (port de mergeHistorical L1694)
# ─────────────────────────────────────────────────────────────────────────────

def _merge_historical(existing: list[dict], incoming: list[dict]) -> tuple[list[dict], int, int]:
    """Port verbatim de mergeHistorical L1694.

    Reglas:
        - Match por `date`.
        - Si el mes ya existe: pisa campos del BR, PRESERVA spend/ventasPPC.
        - Si el mes es nuevo: agrega con spend=None, ventasPPC=None.
        - Output ordenado asc por date.

    Returns:
        (merged_list, added_count, updated_count).
    """
    by_date: dict[str, dict] = {r["date"]: dict(r) for r in existing}
    added = 0
    updated = 0
    for new_row in incoming:
        prev = by_date.get(new_row["date"])
        if prev is not None:
            manual_spend = prev.get("spend")
            manual_vppc = prev.get("ventasPPC")
            by_date[new_row["date"]] = {
                **new_row,
                "spend": manual_spend if manual_spend is not None else None,
                "ventasPPC": manual_vppc if manual_vppc is not None else None,
            }
            updated += 1
        else:
            by_date[new_row["date"]] = {**new_row, "spend": None, "ventasPPC": None}
            added += 1
    merged = sorted(by_date.values(), key=lambda r: r["date"])
    return merged, added, updated


def _load_demo_into_active(state: Optional[Any] = None) -> int:
    """Reemplaza el histórico del cliente activo con DERMAGLOS_DATA.

    Fiel al HTML L5898-5900: deep-copy del array constante + setear spend/
    ventasPPC en None. NO mergea — pisa el histórico actual.

    Returns:
        Cantidad de meses cargados (23 si el demo está completo).
    """
    if state is None:
        state = st.session_state
    c = _cur_client(state)
    if c is None:
        return 0
    # Deep-copy manual: dict por fila para no compartir referencias con la
    # constante (el AM puede editar spend/ventasPPC y no queremos mutar el demo).
    c["historical"] = [
        {**row, "spend": None, "ventasPPC": None} for row in _DERMAGLOS_DATA
    ]
    return len(c["historical"])


def _update_historical_row(idx: int, field: str, value: Any, state: Optional[Any] = None) -> bool:
    """Actualiza un campo (spend / ventasPPC) de una fila del histórico activo.

    Helper mínimo para que el data_editor de Streamlit pueda escribir cambios
    de vuelta al state. Mutación in-place sobre el dict del cliente activo
    (que es la referencia viva en session_state — no crea acceso nuevo).

    Args:
        idx: índice del registro en `historical` (NO en el sort desc del UI).
        field: 'spend' o 'ventasPPC'.
        value: nuevo valor (None / '' / número).
        state: dict-like; default `st.session_state`.

    Returns:
        True si se aplicó; False si no hay cliente activo o idx fuera de rango.
    """
    if state is None:
        state = st.session_state
    if field not in ("spend", "ventasPPC"):
        return False
    c = _cur_client(state)
    if c is None:
        return False
    hist = c.get("historical", [])
    if not (0 <= idx < len(hist)):
        return False
    # Normalizar vacío a None (fiel al HTML L2044: value === '' ? null : parseFloat).
    if value == "" or value is None:
        hist[idx][field] = None
    else:
        try:
            hist[idx][field] = float(value)
        except (ValueError, TypeError):
            hist[idx][field] = None
    return True


def _update_account_config(
    field: str, value: Any, state: Optional[Any] = None,
) -> bool:
    """Actualiza un campo de config del cliente activo (marketplace / currency /
    margin / yoy_mode). Mutación in-place sobre el dict del cliente activo.

    Args:
        field: 'marketplace' | 'currency' | 'margin' | 'yoy_mode'.
        value: nuevo valor.
        state: dict-like; default `st.session_state`.

    Returns:
        True si se aplicó; False si no hay cliente activo o field inválido.
    """
    if state is None:
        state = st.session_state
    if field not in ("marketplace", "currency", "margin", "yoy_mode"):
        return False
    c = _cur_client(state)
    if c is None:
        return False
    c[field] = value
    return True


# ─────────────────────────────────────────────────────────────────────────────
# Fase 2 — Quick stats (port de renderQuickStats L1919)
# ─────────────────────────────────────────────────────────────────────────────

def _build_quick_stats(historical: list[dict], currency: str = "USD") -> list[dict]:
    """Calcula las stat cards del último mes vs anterior y vs YoY.

    Port fiel de renderQuickStats L1919. Devuelve lista de dicts:
        {label, value, delta, delta_label}
    para que `render()` los pase a `kpi_card`.

    Lista base: 8 cards (Revenue/YoY/Sessions/CVR/Units/AOV/Velocity/BuyBox).
    Si el último mes tiene spend → agrega Spend; si además tiene ventasPPC →
    agrega ACOS real; el TACOS real se agrega siempre que haya spend.
    """
    if not historical:
        return []

    last = historical[-1]
    prev = historical[-2] if len(historical) >= 2 else None
    yoy = _same_month_last_year(last["date"], historical)

    cards: list[dict] = [
        {
            "label": "Revenue último mes",
            "value": _fmt_currency(last.get("revenue"), currency),
            "delta": _delta_pct(last.get("revenue"), prev.get("revenue")) if prev else None,
            "delta_label": "MoM",
        },
        {
            "label": "Revenue YoY",
            "value": _fmt_currency(yoy.get("revenue"), currency) if yoy else "—",
            "delta": _delta_pct(last.get("revenue"), yoy.get("revenue")) if yoy else None,
            "delta_label": "YoY",
        },
        {
            "label": "Sessions",
            "value": _fmt_num(last.get("sessions")),
            "delta": _delta_pct(last.get("sessions"), prev.get("sessions")) if prev else None,
            "delta_label": "MoM",
        },
        {
            "label": "Unit Session %",
            "value": _fmt_pct(last.get("cvr"), 2),
            "delta": _delta_pct(last.get("cvr"), prev.get("cvr")) if prev else None,
            "delta_label": "MoM",
        },
        {
            "label": "Units Sold",
            "value": _fmt_num(last.get("units")),
            "delta": _delta_pct(last.get("units"), prev.get("units")) if prev else None,
            "delta_label": "MoM",
        },
        {
            "label": "AOV",
            "value": _fmt_currency(
                last.get("revenue", 0) / max(1, last.get("units", 1) or 1),
                currency, dec=2,
            ),
            "delta": None,
            "delta_label": "",
        },
        {
            "label": "Sales Velocity",
            "value": _fmt_num((last.get("units", 0) or 0) / 30, 1) + " u/día",
            "delta": None,
            "delta_label": "",
        },
        {
            "label": "Buy Box %",
            "value": _fmt_pct(last.get("buyBox"), 1),
            "delta": None,
            "delta_label": "",
        },
    ]

    # Cards extra si hay ads data — fiel al HTML L1982-1994.
    last_spend = last.get("spend")
    last_vppc = last.get("ventasPPC")
    has_spend = last_spend is not None and last_spend != ""
    if has_spend:
        spend_f = float(last_spend)
        rev = last.get("revenue", 0) or 0
        last_tacos = (spend_f / rev * 100) if rev > 0 else None
        cards.append({
            "label": "Spend último mes",
            "value": _fmt_currency(spend_f, currency),
            "delta": None, "delta_label": "",
        })
        vppc_valid = last_vppc is not None and last_vppc != "" and float(last_vppc) > 0
        if vppc_valid:
            last_acos = spend_f / float(last_vppc) * 100
            cards.append({
                "label": "ACOS real",
                "value": _fmt_pct(last_acos, 1),
                "delta": None, "delta_label": "",
            })
        if last_tacos is not None:
            cards.append({
                "label": "TACOS real",
                "value": _fmt_pct(last_tacos, 1),
                "delta": None, "delta_label": "",
            })

    return cards


def _build_history_df(historical: list[dict], currency: str = "USD") -> pd.DataFrame:
    """Construye el DataFrame que va al `st.data_editor` para edición de spend
    y ventasPPC. Port de renderHistoryTable L2007.

    Columnas (en orden, fiel al HTML L2013):
        Mes | Revenue | Units | Sessions | CVR% | AOV | Spend | Ventas PPC | ACOS% | TACOS%

    Mes está sorted DESC (fiel a L2016-2018). Pero conservamos el índice
    original en `_idx` (oculto al renderer) para que las ediciones puedan
    mapearse de vuelta a `historical[i]` sin perder el orden de carga.

    Normalización Arrow-safe:
        - spend / ventasPPC None → '' (data_editor maneja strings vacíos OK).
        - Resto de números: NaN ya viene de pandas si parseNum devuelve 0,
          acá los dejamos float — Arrow los tolera.
    """
    if not historical:
        return pd.DataFrame(columns=[
            "_idx", "Mes", "Revenue", "Units", "Sessions", "CVR%", "AOV",
            "Spend", "Ventas PPC", "ACOS%", "TACOS%",
        ])

    rows = []
    for i, r in enumerate(historical):
        spend = r.get("spend")
        vppc = r.get("ventasPPC")
        spend_f = float(spend) if (spend is not None and spend != "") else None
        vppc_f = float(vppc) if (vppc is not None and vppc != "") else None
        rev = r.get("revenue", 0) or 0
        units = r.get("units", 0) or 0
        acos = (spend_f / vppc_f * 100) if (spend_f is not None and vppc_f and vppc_f > 0) else None
        tacos = (spend_f / rev * 100) if (spend_f is not None and rev > 0) else None

        # Month label "Enero 2026" — fiel a monthLabelFull L1281.
        try:
            year, month, _ = r["date"].split("-")
            mes_label = f"{_MONTHS_FULL[int(month) - 1]} {year}"
        except (ValueError, KeyError, IndexError):
            mes_label = r.get("date", "")

        rows.append({
            "_idx": i,
            "Mes": mes_label,
            "Revenue": rev,
            "Units": units,
            "Sessions": r.get("sessions", 0) or 0,
            "CVR%": r.get("cvr", 0) or 0,
            "AOV": rev / max(1, units),
            "Spend": "" if spend_f is None else spend_f,
            "Ventas PPC": "" if vppc_f is None else vppc_f,
            "ACOS%": "" if acos is None else acos,
            "TACOS%": "" if tacos is None else tacos,
        })

    df = pd.DataFrame(rows)
    # Sort DESC por date original (más nuevo arriba) — fiel a L2017.
    df["_sort_key"] = [historical[i]["date"] for i in df["_idx"]]
    df = df.sort_values("_sort_key", ascending=False).drop(columns=["_sort_key"]).reset_index(drop=True)
    return df


def _apply_history_edits(
    edited_df: pd.DataFrame, state: Optional[Any] = None,
) -> int:
    """Re-aplica las ediciones de Spend / Ventas PPC del data_editor al state.

    Recorre cada fila del df editado, lee `_idx` (preservado oculto) y escribe
    spend/ventasPPC vía `_update_historical_row` (que normaliza '' → None y
    cast a float).

    Returns:
        Cantidad de filas escritas (siempre = len del df si todas las idx son válidas).
    """
    if edited_df is None or edited_df.empty:
        return 0
    written = 0
    for _, row in edited_df.iterrows():
        idx = int(row["_idx"])
        # Solo escribimos los 2 campos editables — el resto del df es display-only.
        _update_historical_row(idx, "spend", row.get("Spend", ""), state=state)
        _update_historical_row(idx, "ventasPPC", row.get("Ventas PPC", ""), state=state)
        written += 1
    return written


# ─────────────────────────────────────────────────────────────────────────────
# Render principal — Fase 2: selector + datos
# ─────────────────────────────────────────────────────────────────────────────

def _header() -> None:
    """Header estándar Capybaras (patrón module-architecture-standard)."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📈</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>Revenue Forecast</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Account Manager · proyección de revenue cliente-céntrica (Fase 2: ingesta + visualización)"
        "</div></div></div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _render_account_config(cur: dict) -> None:
    """Render del bloque "Configuración de la cuenta" (port del HTML L724-749).

    4 campos editables (marketplace, currency, margin, yoy_mode). Cada cambio
    se escribe al cliente activo vía `_update_account_config`. Los inputs
    usan `key=` con el id del cliente para que cambiar de cliente NO les
    arrastre estado viejo.
    """
    st.markdown("##### Configuración de la cuenta")
    st.caption("Define el contexto base. Estos parámetros afectan el cálculo del forecast (F3).")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        try:
            mkt_idx = _MARKETPLACES.index(cur.get("marketplace", "US"))
        except ValueError:
            mkt_idx = 0
        # Sin key= (patrón F1): index= se recalcula de `cur` cada rerun, así el
        # widget refleja el cliente activo sin arrastre entre clientes. key= +
        # index= juntos es anti-patrón Streamlit 1.43.
        new_mkt = st.selectbox(
            "Marketplace", _MARKETPLACES, index=mkt_idx,
        )
        if new_mkt != cur.get("marketplace"):
            _update_account_config("marketplace", new_mkt)

    with col2:
        try:
            cur_idx = _CURRENCIES.index(cur.get("currency", "USD"))
        except ValueError:
            cur_idx = 0
        new_cur = st.selectbox(
            "Moneda", _CURRENCIES, index=cur_idx,
        )
        if new_cur != cur.get("currency"):
            _update_account_config("currency", new_cur)

    with col3:
        new_margin_pct = st.number_input(
            "Margen (%)", min_value=0.0, max_value=100.0,
            value=float(cur.get("margin", 0.30)) * 100,
            step=1.0,
            help="Margen bruto operativo. 30% = 0.30.",
        )
        new_margin = round(new_margin_pct / 100.0, 4)
        if new_margin != cur.get("margin"):
            _update_account_config("margin", new_margin)

    with col4:
        try:
            yoy_idx = _YOY_MODES.index(cur.get("yoy_mode", "auto"))
        except ValueError:
            yoy_idx = 0
        new_yoy = st.selectbox(
            "Modo YoY", _YOY_MODES, index=yoy_idx,
            help="auto = activar si hay datos YoY · on = forzar activado · off = forzar desactivado.",
        )
        if new_yoy != cur.get("yoy_mode"):
            _update_account_config("yoy_mode", new_yoy)


def _render_upload_and_demo(cur: dict) -> None:
    """Render del bloque "Cargar Business Report" + botón demo (port del HTML L751-765).

    El uploader acepta CSV y XLSX. Al subir, parsea con `_parse_business_report`,
    mergea con `_merge_historical` (preserva spend/ventasPPC), escribe al
    cliente activo y muestra resumen "+ X meses nuevos · Y actualizados".

    El botón "Cargar demo Dermaglos" pisa el histórico actual (NO mergea, fiel
    al HTML L5898-5900).
    """
    st.markdown("##### Cargar Business Report")
    st.caption(
        "Exportá de Amazon → Seller Central → Business Reports → "
        "\"By Date · Sales and Traffic\". CSV o XLSX, mensual."
    )

    col_up, col_demo = st.columns([2, 1])
    with col_up:
        uploaded = st.file_uploader(
            "Business Report (CSV o XLSX)",
            type=["csv", "xlsx", "xls"],
            key=f"rf_br_uploader_{cur['id']}",
            label_visibility="collapsed",
        )
    with col_demo:
        if st.button(
            "Cargar demo Dermaglos",
            key=f"rf_demo_btn_{cur['id']}",
            help="Reemplaza el histórico actual con 23 meses de prueba (jun-2024 a abr-2026).",
        ):
            n = _load_demo_into_active()
            if n > 0:
                st.success(f"Demo cargado: {n} meses.")
                st.rerun()
            else:
                st.error("No se pudo cargar el demo (sin cliente activo).")

    if uploaded is not None:
        # `.getvalue()` para que el parser cacheado reciba bytes (patrón M30).
        data = uploaded.getvalue()
        try:
            rows = _parse_business_report(data, uploaded.name)
        except Exception as e:  # noqa: BLE001 — fail-soft al AM
            st.error(f"No se pudo parsear el archivo: {e}")
            return

        if not rows:
            st.warning(
                "No se reconocieron filas con formato by-date en este archivo. "
                "Verificá que tenga columnas 'Date' y 'Ordered Product Sales'."
            )
            return

        merged, added, updated = _merge_historical(cur.get("historical", []), rows)
        cur["historical"] = merged
        parts = []
        if added:
            parts.append(f"{added} mes{'es' if added != 1 else ''} nuevo{'s' if added != 1 else ''}")
        if updated:
            parts.append(f"{updated} mes{'es' if updated != 1 else ''} actualizado{'s' if updated != 1 else ''}")
        st.success(f"✓ {' · '.join(parts)} (Spend y Ventas PPC manuales se conservaron).")


def _render_quick_stats(cur: dict) -> None:
    """Render del bloque "Indicadores actuales" (port del HTML L767-771)."""
    st.markdown("##### Indicadores actuales")
    st.caption("Promedios y tendencias derivadas del historial cargado.")

    historical = cur.get("historical", [])
    if not historical:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:1.5rem;"
            "text-align:center;background:#FFF3E0;'>"
            "<div style='font-size:1.2rem;'>◌</div>"
            "<div style='font-weight:600;margin-top:0.4rem;'>Sin datos</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.2rem;'>"
            "Cargá un CSV o usá el ejemplo Dermaglos.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    cards = _build_quick_stats(historical, currency=cur.get("currency", "USD"))
    # Layout 4 por fila — patrón Capybaras kpi_card.
    for i in range(0, len(cards), 4):
        row = cards[i:i + 4]
        cols = st.columns(4)
        for col, card in zip(cols, row):
            with col:
                # `kpi_card` espera (label, value, delta, delta_good).
                # delta_good=True para todos (revenue/sessions/units suben → verde;
                # CVR sube → verde también, aceptable para v1).
                st.markdown(
                    kpi_card(
                        card["label"],
                        card["value"],
                        delta=card.get("delta"),
                        delta_good=True,
                    ),
                    unsafe_allow_html=True,
                )


def _render_history_table(cur: dict) -> None:
    """Render del bloque "Historial mensual" (port del HTML L773-784)."""
    st.markdown("##### Historial mensual")
    st.caption(
        "Datos crudos del Business Report + inversión de Ads (que captura el AM "
        "manualmente — Amazon NO los incluye en este reporte). ACOS y TACOS se "
        "calculan cuando Spend y Ventas PPC están cargados."
    )

    historical = cur.get("historical", [])
    if not historical:
        st.caption("Sin historial cargado.")
        return

    df = _build_history_df(historical, currency=cur.get("currency", "USD"))

    # data_editor: solo Spend y Ventas PPC editables; el resto read-only.
    edited = st.data_editor(
        df,
        key=f"rf_history_editor_{cur['id']}",
        hide_index=True,
        use_container_width=True,
        column_config={
            "_idx": None,  # ocultar índice interno
            "Mes": st.column_config.TextColumn("Mes", disabled=True),
            "Revenue": st.column_config.NumberColumn("Revenue", format="%.2f", disabled=True),
            "Units": st.column_config.NumberColumn("Units", format="%d", disabled=True),
            "Sessions": st.column_config.NumberColumn("Sessions", format="%d", disabled=True),
            "CVR%": st.column_config.NumberColumn("CVR%", format="%.2f", disabled=True),
            "AOV": st.column_config.NumberColumn("AOV", format="%.2f", disabled=True),
            "Spend": st.column_config.NumberColumn(
                "Spend", format="%.2f", help="Inversión de Ads del mes (manual).",
            ),
            "Ventas PPC": st.column_config.NumberColumn(
                "Ventas PPC", format="%.2f", help="Ventas atribuidas a Ads del mes (manual).",
            ),
            "ACOS%": st.column_config.NumberColumn("ACOS%", format="%.1f", disabled=True),
            "TACOS%": st.column_config.NumberColumn("TACOS%", format="%.1f", disabled=True),
        },
    )

    # Re-aplicar ediciones al state. Streamlit rerun deja `edited` con los
    # valores nuevos antes de re-renderizar — los persistimos para que el
    # próximo render del data_editor + las quick stats vean los cambios.
    if edited is not None and not edited.equals(df):
        _apply_history_edits(edited)
        # Rerun para que las quick stats reflejen el ACOS/TACOS nuevos.
        st.rerun()


def render() -> None:
    """Entry point del Revenue Forecast (M31) — sección Account Manager.

    Fase 2: header + ayuda + selector de cliente + 4 secciones de la pestaña
    Datos (config de cuenta, upload BR + demo, quick stats, history table).
    SIN motor de forecast (F3), SIN persistencia activa (F4).
    """
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    # 1) Inicializar state (idempotente) + seed demo si vacío.
    _ensure_state()
    _seed_demo_client_if_empty()

    clients = st.session_state.get(_K_CLIENTS, [])

    # 2) Empty state defensivo (en teoría no se llega por el seed demo,
    # guard si alguna fase futura desactiva el seed).
    if not clients:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>📂</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>No hay clientes cargados</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
            "La gestión de catálogo de clientes llega en una fase posterior.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # 3) Selector de cliente — patrón M30 (sin key=, se usa el return).
    label_to_id = {f"{c['name']} ({c['marketplace']})": c["id"] for c in clients}
    labels = list(label_to_id.keys())

    active_id = st.session_state.get(_K_ACTIVE_CLIENT_ID)
    try:
        active_label = next(lbl for lbl, cid in label_to_id.items() if cid == active_id)
        default_idx = labels.index(active_label)
    except StopIteration:
        default_idx = 0

    selected_label = st.selectbox("Cliente", labels, index=default_idx)
    selected_id = label_to_id[selected_label]
    if selected_id != active_id:
        _set_active_client(selected_id)

    cur = _cur_client()
    if cur is None:
        st.warning("No hay cliente activo.")
        return

    st.caption(
        f"Cliente activo: **{cur['name']}** (`{cur['id']}`) · "
        f"marketplace {cur['marketplace']} · margin {int(cur['margin'] * 100)}%"
    )

    # 4) Aviso de fase.
    st.info(
        "🚧 **Fase 2 — ingesta + visualización.** El motor de forecast llega en F3 "
        "y la persistencia entre sesiones en F4."
    )

    # 5) Sección DATOS — port del HTML L721-785.
    st.divider()
    _render_account_config(cur)
    st.markdown("")
    _render_upload_and_demo(cur)
    st.markdown("")
    _render_quick_stats(cur)
    st.markdown("")
    _render_history_table(cur)
