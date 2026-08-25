"""M31 — Monthly Forecast (port del HTML standalone a módulo Streamlit).

El módulo se llamó "Revenue Forecast" hasta 2026-07-30. Se renombró SÓLO el
nombre visible: el archivo, el import y `MODULE_SLUG = "revenue-forecast"` siguen
con el nombre viejo a propósito — el slug es key de persistencia (ver su
comentario en L108). Si el código dice "revenue" y la UI dice "Monthly", es
deliberado.

Sección: Account Manager
Página: 📈 Monthly Forecast
Fase: 5 (MVP CERRADO — Estacionalidad UI + Export CSV). Consume el motor
puro F3 (`auto_detect_seasonality`, `generate_forecast`) sin modificarlo.
Cambiar la seasonality NO regenera el forecast automático (pisaría los
overrides F4). El aviso "regenerá arriba" invita al AM a re-aplicar
conscientemente cuando esté listo.

Fases previas (acumuladas):
    F1: esqueleto + state + accessor de cliente activo + persistencia DORMIDA.
    F2: parser by-date BR + merge histórico + quick stats + history table.
    F3: motor de forecast puro (generate_forecast / recompute_forecast_row /
        auto_detect_seasonality) — testeado, sin runtime Streamlit.
    F4: UI editable del forecast por-cuenta (controles + tabla + summary).
    F5: estacionalidad UI (toggle + 12 índices editables + auto-detect) +
        export CSV con 12 cols HTML + 6 cols de overrides manuales del AM.

Pendiente (post-MVP):
    F6: forecast por-ASIN (drill-down + bulk generation + parent rollup).
    Snapshots + persistencia activa + comparación vs Real (fin de mes).

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

import calendar
import copy
import html
import json
import math
import os
import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from io import BytesIO
from typing import Any, Optional

import pandas as pd
import plotly.graph_objects as go
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

# 🔴 KEY DE PERSISTENCIA — NO CAMBIAR AL RENOMBRAR EL MÓDULO.
# Es la 3ra parte de la PK de Supabase `(area, cliente, modulo, name)` en la
# tabla `forecast_clients`, y el nombre de la carpeta en disco:
#     data/account-manager/<cliente>/revenue-forecast/<name>.json
# Cambiarlo deja HUÉRFANOS todos los clientes ya guardados — el módulo arranca
# vacío y los datos viejos quedan inalcanzables por PK, sin ningún error.
# El módulo se renombró a "Monthly Forecast" el 2026-07-30 y este slug quedó
# intacto justamente por eso. Blindado en test_revenue_forecast_persistence.py.
MODULE_SLUG = "revenue-forecast"
SCHEMA_VERSION = 1

# Prefijo de keys en session_state. NUNCA reusar keys entre módulos.
_STATE_PREFIX = "m31_"
_K_CLIENTS = f"{_STATE_PREFIX}clients"
_K_ACCOUNT_MANAGERS = f"{_STATE_PREFIX}account_managers"
_K_ACTIVE_CLIENT_ID = f"{_STATE_PREFIX}active_client_id"

# ⚠ FLAG MAESTRO: persistencia ENCENDIDA en Fase 2. Cableada en `_ensure_state`
# (hidrata si el catálogo está vacío) + botón "💾 Guardar cliente" en `render()`
# + autosave post-demo-load y post-forecast-gen. Backend por default local; para
# Supabase, seteá `AGENCY_OS_FORECAST_BACKEND="supabase"` + creds (ver
# `core/forecast_persistence.py`).
_PERSISTENCE_ENABLED = True

# SOP in-app — Fase 4.
_SOP_MD = """
### Monthly Forecast — cómo usarlo (Fase 4)

Módulo de **forecast editable por-cuenta**. El AM carga histórico, lo
visualiza, y proyecta N meses al futuro ajustando overrides manualmente.

**Flujo del AM:**
1. **Cliente activo:** elegí (o creá vía demo) el cliente con el selector.
2. **Config de cuenta:** marketplace, moneda, modo YoY — quedan en el cliente.
3. **Cargar Business Report:** exportá de Amazon → Seller Central → Business Reports
   → "By Date · Sales and Traffic" (mensual). Subí el CSV o XLSX. La carga **se
   mergea** con el histórico: meses nuevos se agregan, los existentes se
   actualizan con los datos del CSV. **Spend** y **Ventas PPC** manuales **se
   conservan** entre uploads.
4. **History table:** editá Spend y Ventas PPC mes a mes — ACOS y TACOS reales
   se calculan al instante.
5. **Quick stats:** deltas MoM/YoY del último mes vs anterior y vs el mismo mes
   del año pasado.
6. **Forecast (F4):**
   - Configurá horizon (meses a proyectar), ventana MoM, mezcla MoM↔YoY, y
     toggle estacionalidad. Hacé clic en **"Generar forecast"**.
   - Editá overrides en la tabla: Revenue / AOV / Sessions / Spend / ACOS / TACOS
     / Stock Availability. Los outputs (revenue, units, AOV, ventas PPC, ACOS,
     TACOS) se recalculan al instante.
   - Si seteás **TACOS target**, el Spend lo maneja el motor (TACOS×Revenue).
   - **↺ Resetear overrides:** limpia manualRevenue/AOV/Sessions/tacosTarget
     de todas las filas.
   - El summary muestra totales y promedios del periodo proyectado.

**Demo Dermaglos:** 23 meses (jun-2024 a abr-2026) cargables con un click para
probar el flujo sin Business Report real.

**Próximas fases:**
- F5: exports (CSV/XLSX) + snapshots versionados + persistencia activa.
- F6: forecast por-ASIN (drill-down + bulk).
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
        "actual": [],              # F7-A: real mes a mes contra el forecast
                                   # (mismo shape que historical + partial/days_covered)
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

    # F2: hidratación desde persistencia. Solo si el catálogo está vacío
    # (idempotente: en reruns con clientes vivos en sesión NO pisa el trabajo del AM).
    if not state[_K_CLIENTS]:
        _try_hydrate(state)


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


def _get_actual(state: Optional[Any] = None) -> list:
    """Capa `actual` del cliente activo (F7-A). Lista vacía si no hay activo.

    Usa `.get` (no `[...]`) a propósito: los clientes persistidos ANTES de F7-A
    se hidratan sin la key `actual`, y el getter no debe romper con ellos.
    """
    c = _cur_client(state)
    return c.get("actual", []) if c else []


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
        # El cliente demo (seedeado local para que el selector nunca esté vacío)
        # NO se persiste — no debe ensuciar el backend / Supabase.
        if c.get("id") == "demo-client":
            continue
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
# Wrappers de resiliencia — Fase 2
# ─────────────────────────────────────────────────────────────────────────────
#
# La persistencia es un EXTRA sobre memoria: si el backend (Supabase o local)
# falla por red / permisos / creds inválidas, el AM debe poder seguir trabajando
# con su session_state intacto. Estos wrappers envuelven las llamadas y avisan
# con `st.error(...)` sin propagar la excepción. Devuelven `bool` (True=ok).
#
# Van ACÁ (no dentro de los helpers) porque los helpers son puros y no deberían
# conocer a `st.error`. La responsabilidad de "avisar al usuario" es de UI.

def _try_hydrate(state: Optional[Any] = None) -> bool:
    """Hidrata con resiliencia. Si el backend falla, avisa y NO rompe: session_state intacto."""
    try:
        _hydrate_clients(state)
        return True
    except Exception as exc:  # noqa: BLE001 — la persistencia es un extra; nunca rompe el flujo del AM
        st.error(
            f"No se pudo cargar el catálogo desde la nube — seguís con tu estado local. ({exc})"
        )
        return False


def _try_persist(state: Optional[Any] = None) -> bool:
    """Persiste con resiliencia. Si el backend falla, avisa y NO rompe: session_state intacto."""
    try:
        _persist_clients(state)
        return True
    except Exception as exc:  # noqa: BLE001 — la persistencia es un extra; nunca rompe el trabajo en memoria
        st.error(
            f"No se pudo guardar en la nube — tu trabajo sigue a salvo en memoria. ({exc})"
        )
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Frente M31-crear-cliente — flujo de creación de cliente (núcleo testeable)
# ─────────────────────────────────────────────────────────────────────────────
#
# Separa la LÓGICA de crear+activar+persistir de la UI del popover. Testeable
# sin runtime Streamlit: acepta `state` (dict simulado) y devuelve un status
# (ok, kind, msg) que la UI traduce a st.warning / st.success. La persistencia
# usa `_try_persist` (resiliente): si el backend falla, el cliente igual queda
# en session_state y el AM no pierde su trabajo.

def _create_client_flow(
    name: str,
    marketplace: str = "US",
    state: Optional[Any] = None,
) -> tuple[bool, str, str]:
    """Crea un cliente nuevo, lo deja activo y lo persiste.

    Secuencia crítica: validar → _new_client → append al catálogo →
    _set_active_client → _try_persist. El paso de persistencia es lo que hace
    que el cliente sobreviva a la recarga; sin él, muere al recargar.

    Args:
        name: nombre display del cliente (se trimea).
        marketplace: código de marketplace.
        state: dict-like; default `st.session_state`.

    Returns:
        (ok, kind, msg):
            (False, "warning", <msg>)  — no se creó (nombre vacío o duplicado).
            (True,  "success", <msg>)  — creado, activo y persistido (o al menos
                                          en sesión si el backend de persistencia
                                          falló — resiliencia).
    """
    if state is None:
        state = st.session_state

    clean = (name or "").strip()
    if not clean:
        return (False, "warning", "El nombre del cliente no puede estar vacío.")

    existing = state.get(_K_CLIENTS, [])
    if any((c.get("name") or "").strip().lower() == clean.lower() for c in existing):
        return (False, "warning", "Ya existe un cliente con ese nombre.")

    nuevo = _new_client(name=clean, marketplace=marketplace)
    state.setdefault(_K_CLIENTS, []).append(nuevo)
    _set_active_client(nuevo["id"], state=state)
    _try_persist(state=state)  # persiste; si falla, avisa por st.error pero el cliente queda en sesión
    return (True, "success", f"Cliente creado: {clean}")


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
    """Limpia tokens numéricos de Amazon BR y devuelve 0 si no parsea.

    HARDENING vs HTML original (parseNum L1271): el HTML solo quitaba `$,%`,
    lo que rompe con monedas reales de Amazon que usan prefijos de letras
    (ej. MX$, R$). Patrón canónico fallaba con "MX$5,121.00" → "MX5121.00" →
    ValueError → 0.0.

    Reglas (en orden):
        1. None / NaN / "" → 0.0.
        2. Numérico nativo → float directo.
        3. String: quitar comillas `"`, quitar prefijo letras+`$` (MX$, R$, US$),
           quitar `$`, `%`, comas (miles) y espacios. Mantener `.` y `-`.

    Casos cubiertos:
        "$210.76" → 210.76
        "MX$5,121.00" → 5121.0
        "$6,513.61" → 6513.61
        "$0.00" → 0.0
        "" → 0.0
        "7.07%" → 7.07
        '"$3,672.17"' → 3672.17 (CSV con quoting=ALL)
    """
    if v is None:
        return 0.0
    if isinstance(v, (int, float)) and not pd.isna(v):
        return float(v)
    s = str(v).strip()
    if not s:
        return 0.0
    # 1. Quitar comillas que sobran (algunos CSV de Amazon citan valores con coma).
    s = s.replace('"', "").replace("'", "").strip()
    # 2. Quitar prefijo de letras opcional + signo de moneda (MX$, R$, US$, $, €, etc.).
    s = re.sub(r"^[A-Za-z]+\$", "", s)
    s = re.sub(r"^[A-Za-z]+", "", s)  # por si hay "USD 100" sin $.
    # 3. Limpieza final: $, %, comas (miles), espacios. Preserva . y -.
    s = re.sub(r"[\$%,\s]", "", s)
    if not s or s in ("-", "."):
        return 0.0
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
    # CVR: el HTML buscaba 'unit session %' (legacy). Amazon BR by-date REAL
    # usa 'Order Item Session Percentage' (sin 'unit'). Probamos ambos.
    cvr_raw = (
        _find_by_keywords(norm_map, ["unit", "session"], ["b2b"])
        or _find_by_keywords(norm_map, ["order", "item", "session"], ["b2b"])
    )
    cvr = _parse_num(cvr_raw)

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


class ReportLacksSessionsError(ValueError):
    """Excepción dedicada: el BR cargado no incluye columna de Sessions/Tráfico.

    Se lanza cuando el CSV/XLSX viene del reporte "Sales and Orders by Month"
    (que solo trae revenue + units, sin tráfico) en lugar de "Sales and Traffic
    by Date". El forecast NECESITA sessions para la velocity, AOV, CVR y la
    proyección a futuro — ingerir sin sessions sería romper el motor F3
    silenciosamente.

    El caller (UI) debe atrapar esto y mostrar mensaje al AM: cargar el
    reporte correcto.
    """


_SESSIONLESS_HINT = (
    "Este reporte no incluye Sessions/CVR. "
    "Cargá el reporte 'Sales and Traffic' (By Date), "
    "que sí trae datos de tráfico."
)


def _detect_granularity(rows: list[dict]) -> str:
    """Detecta si las filas vienen diarias o mensuales.

    Heurística: si hay >1 fila por (año, mes), es DIARIO. Si cada (año, mes)
    tiene exactamente 1 fila, es MENSUAL. Casos borde:
        - 0 filas → "monthly" (no hay nada que agregar).
        - 1 fila → "monthly" (sin info, asumir mensual y no agregar).
    """
    if len(rows) <= 1:
        return "monthly"
    months_seen: dict[tuple[int, int], int] = {}
    for r in rows:
        try:
            y, m, _d = r["date"].split("-")
            key = (int(y), int(m))
        except (ValueError, AttributeError, KeyError):
            continue
        months_seen[key] = months_seen.get(key, 0) + 1
    if any(v > 1 for v in months_seen.values()):
        return "daily"
    return "monthly"


def _aggregate_daily_to_monthly(rows: list[dict]) -> list[dict]:
    """Agrega filas diarias a mensuales agrupando por (año, mes).

    Reglas:
        - revenue, revenueB2B, units, sessions, pageViews → SUMA.
        - buyBox → promedio simple (% es ratio, suma no tiene sentido).
        - cvr → RECALCULADO como units / sessions * 100 (NO promedio simple
          de los % diarios, que sesga). units es proxy de order items: el
          HTML mismo equipara cvr al "Order Item Session Percentage" pero el
          BR de Amazon by-date no expone order items por separado del total
          de units en este export, así que usamos units. Si sessions del mes
          es 0 → cvr = 0.
        - date → primer día del mes ISO (YYYY-MM-01).

    Si el grupo del mes no tiene filas con sessions, cvr cae a 0.
    """
    buckets: dict[tuple[int, int], list[dict]] = {}
    for r in rows:
        try:
            y, m, _d = r["date"].split("-")
            key = (int(y), int(m))
        except (ValueError, AttributeError, KeyError):
            continue
        buckets.setdefault(key, []).append(r)

    monthly: list[dict] = []
    for (y, m), group in sorted(buckets.items()):
        total_revenue = sum(g.get("revenue") or 0 for g in group)
        total_revenue_b2b = sum(g.get("revenueB2B") or 0 for g in group)
        total_units = sum(g.get("units") or 0 for g in group)
        total_sessions = sum(g.get("sessions") or 0 for g in group)
        total_page_views = sum(g.get("pageViews") or 0 for g in group)
        # buyBox: promedio simple (es %, no suma).
        buybox_vals = [g.get("buyBox") for g in group if g.get("buyBox") is not None]
        avg_buybox = (sum(buybox_vals) / len(buybox_vals)) if buybox_vals else 0
        # CVR recalculado desde totales (más fiel que avg de % diarios).
        recalc_cvr = (total_units / total_sessions * 100.0) if total_sessions > 0 else 0.0
        monthly.append({
            "date": f"{y:04d}-{m:02d}-01",
            "revenue": total_revenue,
            "revenueB2B": total_revenue_b2b,
            "units": total_units,
            "sessions": total_sessions,
            "pageViews": total_page_views,
            "buyBox": avg_buybox,
            "cvr": recalc_cvr,
        })
    return monthly


def _has_sessions_column(df: pd.DataFrame) -> bool:
    """True si el DataFrame tiene alguna columna de Sessions (excluyendo B2B y %).

    Se usa para rechazar el reporte "Sales and Orders by Month" (sin tráfico)
    antes de procesar filas. Match por header normalizado (sin BOM, sin
    separadores, lowercase).
    """
    for col in df.columns:
        nk = _norm_hdr(col)
        # Sessions Total (excluyendo Sessions - Total - B2B y Order Item Session Percentage).
        if "sessions" in nk and "b2b" not in nk and "percentage" not in nk:
            return True
    return False


def _read_br_rows(data: bytes, filename: str) -> list[dict]:
    """Lee el BR (CSV/XLSX) y devuelve las filas EN SU GRANULARIDAD ORIGINAL.

    Extracción (F7-A1) de la primera mitad de `_parse_business_report`: leer el
    archivo, rechazar el reporte sin tráfico, mapear con `_map_row_by_date` y
    ordenar por fecha. NO agrega día→mes.

    Existe porque la capa `actual` necesita CONTAR DÍAS para saber si un mes está
    parcial, y la agregación los colapsa a 1 fila mensual. Sin este extract habría
    que duplicar la lectura de archivo en el camino de `actual`.

    Sin `@st.cache_data`: el cache vive en `_parse_business_report` /
    `_parse_actual_report`, que son los puntos de entrada públicos.

    Raises:
        ReportLacksSessionsError: si el archivo no incluye Sessions.
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

    # Rechazo temprano si NO hay sessions (reporte equivocado).
    # Hacemos esto ANTES del mapeo fila por fila porque queremos un error claro
    # al AM, no ingerir "a medias" con sessions=0 que rompe el motor F3.
    if not _has_sessions_column(df):
        raise ReportLacksSessionsError(_SESSIONLESS_HINT)

    # Iteramos dict por fila para reusar el mapeo verbatim.
    rows: list[dict] = []
    for raw in df.to_dict("records"):
        mapped = _map_row_by_date(raw)
        if mapped is not None:
            rows.append(mapped)
    rows.sort(key=lambda r: r["date"])
    return rows


def _to_monthly_rows(rows: list[dict]) -> list[dict]:
    """Normaliza filas del BR a mensuales (1 fila por mes, fecha YYYY-MM-01).

    Segunda mitad extraída de `_parse_business_report` (F7-A1), compartida con
    `_parse_actual_report` para no duplicar la rama de granularidad.

    El HTML original asume mensual (su demo es mensual ISO); los BRs reales
    by-date de Amazon vienen diarios. Si `_detect_granularity` dice "daily" se
    agrega; si dice "monthly" sólo se normaliza la fecha al día 01.
    """
    if _detect_granularity(rows) == "daily":
        return _aggregate_daily_to_monthly(rows)
    out: list[dict] = []
    for r in rows:
        row = dict(r)
        try:
            y, m, _d = row["date"].split("-")
            row["date"] = f"{int(y):04d}-{int(m):02d}-01"
        except (ValueError, AttributeError):
            pass
        out.append(row)
    return out


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_business_report(data: bytes, filename: str) -> list[dict]:
    """Parsea CSV o XLSX del BR by-date. Recibe bytes (no UploadedFile) para
    que el cache de Streamlit funcione (patrón M30).

    HARDENING vs HTML original: maneja BRs reales de Amazon (no solo el demo
    limpio). Cambios:
        1. Limpieza de moneda robusta (MX$, R$, $, etc.) — vía _parse_num.
        2. Rechazo explícito si falta columna Sessions → `ReportLacksSessionsError`.
        3. Detección de granularidad y agregación día→mes automática (Amazon
           by-date exporta diario; el forecast trabaja mensual).

    Devuelve la lista de rows mapeadas, ordenadas por date asc, y AGREGADAS
    a mensual si vienen diarias.

    Args:
        data: bytes crudos del archivo.
        filename: nombre del archivo (para decidir CSV vs XLSX por extensión).

    Returns:
        Lista de dicts con shape by-date (8 keys), siempre mensual.

    Raises:
        ReportLacksSessionsError: si el archivo no incluye Sessions (es el
            reporte equivocado — Sales and Orders by Month en vez de Sales
            and Traffic by Date).
    """
    return _to_monthly_rows(_read_br_rows(data, filename))


# ─────────────────────────────────────────────────────────────────────────────
# F7-A1 — Capa `actual`: el REAL mes a mes, para comparar contra el forecast
# ─────────────────────────────────────────────────────────────────────────────
#
# `actual` es una TERCERA serie que CONVIVE con `historical` y `forecast` — no
# pisa ninguna. Sale del MISMO Business Report que `historical`, así que tiene el
# MISMO shape: los accessors `from_hist` de las 10 métricas de `_METRICS`
# funcionan tal cual sobre estas filas (cero accessors nuevos).
#
# Lo único que agrega son 2 keys de cobertura, para poder marcar visualmente el
# mes que todavía está corriendo.


def _count_days_by_month(rows: list[dict]) -> dict[str, int]:
    """Días DISTINTOS presentes por mes. Clave: fecha del mes en ISO (YYYY-MM-01).

    Cuenta días únicos (dos filas del mismo día no inflan la cobertura). Filas con
    `date` ausente o malformado se saltean — mismo guard defensivo que
    `_detect_granularity`.
    """
    seen: dict[str, set] = {}
    for r in rows:
        try:
            y, m, d = r["date"].split("-")
            key = f"{int(y):04d}-{int(m):02d}-01"
        except (ValueError, AttributeError, KeyError, TypeError):
            continue
        seen.setdefault(key, set()).add(d)
    return {k: len(v) for k, v in seen.items()}


def _parse_actual_report(data: bytes, filename: str) -> list[dict]:
    """Parsea un BR y devuelve filas mensuales de la capa `actual`.

    Shape = el mismo de `_parse_business_report` (lo que alimenta `historical`)
    más 2 keys de cobertura:

        days_covered: Optional[int]   días con dato dentro de ese mes
        partial:      Optional[bool]  TRI-ESTADO

    Los tres estados de `partial`:
        True  → cobertura conocida e INCOMPLETA (BR diario, faltan días del mes)
        False → cobertura conocida y COMPLETA   (BR diario, mes cerrado)
        None  → cobertura DESCONOCIDA           (BR mensual: Amazon ya agregó)

    El caso `None` NO se resuelve acá: esta función es PURA (no llama a
    `date.today()`). Lo desambigua la UI comparando el mes de la fila contra hoy
    — mes en curso → parcial, mes pasado → cerrado. Asumir `True` a ciegas
    pintaría un mes CERRADO bajado en By Month como parcial en el evolutivo, que
    es un dato engañoso hacia el cliente.

    Multi-mes: cada mes se resuelve por separado (un BR diario de junio+julio da
    junio `partial=False` y julio `partial=True`). Eso es lo que hace evolutiva a
    la capa, en vez de "sólo el mes en curso".

    Borde conocido: un BR diario con UNA sola fila es indistinguible de un BR
    mensual (`_detect_granularity` lo llama "monthly") → `partial=None`. Sólo
    ocurre el día 1 del mes, y la UI lo resuelve igual que al resto de los `None`.

    Raises:
        ReportLacksSessionsError: si el archivo no incluye Sessions (heredado de
            `_read_br_rows`).
    """
    raw_rows = _read_br_rows(data, filename)
    # La cobertura sólo es medible si el BR vino diario: si Amazon ya agregó,
    # 1 fila por mes no dice cuántos días cubre.
    days_by_month = (
        _count_days_by_month(raw_rows)
        if _detect_granularity(raw_rows) == "daily"
        else {}
    )

    out: list[dict] = []
    for r in _to_monthly_rows(raw_rows):
        row = dict(r)
        covered = days_by_month.get(row["date"])
        row["days_covered"] = covered
        row["partial"] = (
            None if covered is None else covered < _days_in_month(row["date"])
        )
        out.append(row)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Fase 6.1a — Parser de UN snapshot por-ASIN (Detail Page Sales and Traffic
# By Child Item). Función pura, sin Streamlit. NO acumula multi-mes, NO hace
# rollup padre/hijo, NO infiere el mes (se pasa como parámetro `period`).
# Vive junto al parser by-date por cohesión ("consistente con el resto del
# módulo") y reutiliza `_parse_num` para la limpieza de moneda/comas/%.
# ─────────────────────────────────────────────────────────────────────────────

# Mapa header-normalizado (lower + strip + sin BOM) → clave interna snake_case.
# El match es EXACTO, así las columnas B2B ("... - Total - B2B",
# "... - B2B") NO se confunden con las Total. Las columnas B2B y de
# porcentajes de sesión/pageview se ignoran en v1 (decisión documentada:
# el forecast por-ASIN de F6.1b+ no las necesita todavía).
_ASIN_COL_MAP = {
    "(parent) asin": "parent_asin",
    "(child) asin": "child_asin",
    "title": "title",
    "sessions - total": "sessions",
    "page views - total": "page_views",
    "featured offer (buy box) percentage": "buy_box_pct",
    "units ordered": "units",
    "unit session percentage": "unit_session_pct",
    "ordered product sales": "revenue",
}

# Columnas numéricas (se limpian con _parse_num); el resto son strings.
_ASIN_NUM_FIELDS = {
    "sessions",
    "page_views",
    "buy_box_pct",
    "units",
    "unit_session_pct",
    "revenue",
}


def _norm_header(name: Any) -> str:
    """Normaliza un nombre de columna: quita BOM, colapsa espacios, lower."""
    s = str(name).replace("\ufeff", "").strip().lower()
    return re.sub(r"\s+", " ", s)


def _is_asin_report(header: Any) -> bool:
    """Detecta el BR por-ASIN (Detail Page Sales and Traffic By Child Item)
    por la presencia de la columna "(Child) ASIN" en el header.

    Solo DETECCIÓN — no hace routing (eso es F6.1b). Distingue este reporte
    del by-date del MVP (que tiene columna Date y NO tiene "(Child) ASIN").

    Args:
        header: una lista/iterable de nombres de columna, o el string crudo
            de la primera línea del CSV. Tolera BOM y espacios.

    Returns:
        True si aparece "(child) asin" entre las columnas normalizadas.
    """
    if header is None:
        return False
    if isinstance(header, str):
        cols = header.split(",")
    else:
        cols = list(header)
    return any(_norm_header(c) == "(child) asin" for c in cols)


# Nombre ISO: YYYY-MM en cualquier parte (ej. `dermaglos_2026-07.csv`).
_ASIN_PERIOD_ISO_RE = re.compile(r"(20\d{2})[-_]?(0[1-9]|1[0-2])")
# Naming REAL de Amazon: `BusinessReport-M-DD-YY.csv` (mes sin cero a la
# izquierda, año de 2 dígitos). El `(?!\d)` evita que un año de 4 dígitos
# (`...-2026`) se lea como `20`.
_ASIN_PERIOD_AMZ_RE = re.compile(
    r"businessreport-(\d{1,2})-(\d{1,2})-(\d{2})(?!\d)", re.IGNORECASE
)


def _infer_asin_period(filename: str) -> Optional[str]:
    """Infiere el período `YYYY-MM` del nombre del archivo By Child Item.

    Dos formatos, en este orden:

        1. ISO — `YYYY-MM` en cualquier parte del nombre (lo que ya soportaba
           el importer: archivos renombrados a mano por el AM).
        2. Amazon — `BusinessReport-M-DD-YY`, el naming REAL del export de
           Seller Central. Se ignora el día: el reporte es del MES.

    Por qué existe: el export de Amazon se llama `BusinessReport-8-04-26.csv`,
    que NO contiene `20\\d\\d` y por lo tanto NUNCA matcheaba el regex ISO. El
    importer caía siempre al `text_input` manual y, sin completarlo con el
    formato exacto, cortaba con un warning — se leía como "el importer no carga
    nada".

    Args:
        filename: nombre del archivo tal cual lo sube el AM.

    Returns:
        `"YYYY-MM"`, o None si ningún formato matcheó (el caller cae al input
        manual, que sigue siendo el fallback válido).
    """
    if not filename:
        return None

    m = _ASIN_PERIOD_ISO_RE.search(filename)
    if m:
        return f"{m.group(1)}-{m.group(2)}"

    m = _ASIN_PERIOD_AMZ_RE.search(filename)
    if m:
        month = int(m.group(1))
        if not 1 <= month <= 12:
            return None
        year = 2000 + int(m.group(3))
        return f"{year:04d}-{month:02d}"

    return None


def _parse_asin_report(file_or_bytes: Any, period: str) -> list[dict]:
    """Parsea UN snapshot por-ASIN a lista de dicts (1 por child ASIN).

    Snapshot puro: NO filtra filas (si el export incluye la fila del ASIN
    padre como su propio child, se devuelve tal cual — el rollup es F6.1b+).
    El reporte NO tiene columna Date; el mes se pasa como `period` y se
    estampa en cada fila.

    Args:
        file_or_bytes: bytes crudos, ruta (str/Path), o file-like abierto.
        period: etiqueta del mes al que corresponde el snapshot (ej. "2026-07").

    Returns:
        Lista de dicts con shape por-ASIN (10 keys):
            parent_asin, child_asin, title (strings),
            sessions, page_views, buy_box_pct, units, unit_session_pct,
            revenue (floats vía _parse_num), period (el parámetro).
    """
    # Normalizar la entrada a bytes para que pandas lea consistente (respeta
    # comillas → títulos con comas internas no rompen el parseo).
    if isinstance(file_or_bytes, bytes):
        data = file_or_bytes
    elif isinstance(file_or_bytes, (str, os.PathLike)):
        with open(file_or_bytes, "rb") as fh:
            data = fh.read()
    else:  # file-like
        data = file_or_bytes.read()
        if isinstance(data, str):
            data = data.encode("utf-8")

    df = pd.read_csv(
        BytesIO(data), dtype=str, encoding="utf-8-sig", keep_default_na=False
    )
    # Renombrar columnas a las claves internas (match exacto sobre normalizado).
    rename = {}
    for col in df.columns:
        key = _ASIN_COL_MAP.get(_norm_header(col))
        if key is not None:
            rename[col] = key
    df = df.rename(columns=rename)

    rows: list[dict] = []
    for _, r in df.iterrows():
        row = {
            "parent_asin": str(r.get("parent_asin", "")).strip(),
            "child_asin": str(r.get("child_asin", "")).strip(),
            "title": str(r.get("title", "")).strip(),
            "period": period,
        }
        for field in _ASIN_NUM_FIELDS:
            row[field] = _parse_num(r.get(field))
        rows.append(row)
    return rows


# ─────────────────────────────────────────────────────────────────────────────
# F6.1b — Acumulación multi-mes por-ASIN (funciones puras, sin Streamlit)
# ─────────────────────────────────────────────────────────────────────────────

def _drop_parent_rollup(rows: list[dict]) -> list[dict]:
    """Descarta filas de rollup padre (parent==child) que Amazon emite de forma
    inconsistente entre meses.

    Regla (validada con Dermaglos may/jun/jul 2026): parent==child es ROLLUP a
    descartar si ese parent_asin tiene >=1 fila con child_asin distinto en el MISMO
    snapshot; es STANDALONE a conservar si es la única fila de ese parent.
    Sin esto la acumulación inventa entradas/salidas falsas de ASINs.
    """
    from collections import defaultdict
    childs_by_parent: dict[str, set] = defaultdict(set)
    for r in rows:
        childs_by_parent[r["parent_asin"]].add(r["child_asin"])
    out: list[dict] = []
    for r in rows:
        p, c = r["parent_asin"], r["child_asin"]
        if p == c and len(childs_by_parent[p] - {p}) >= 1:
            continue
        out.append(r)
    return out


def _accumulate_asin_snapshots(
    snapshots: list[list[dict]],
    partial_periods: dict | None = None,
) -> dict:
    """Fusiona N snapshots por-ASIN en modelo acumulado con historial mensual.
    Cada snapshot se limpia con _drop_parent_rollup antes de fusionar. Outer join
    por child_asin (ASIN ausente en un mes = hueco, no error). parent_asin/title del
    snapshot más reciente. partial_periods opcional estampa partial/days_covered.

    Returns:
      {child_asin: {"parent_asin", "title", "history": [{period, sessions, page_views,
       buy_box_pct, units, unit_session_pct, revenue, [partial, days_covered]},
       ...ordenado por period asc]}}
    """
    partial_periods = partial_periods or {}
    model: dict = {}
    METRIC_KEYS = ("sessions", "page_views", "buy_box_pct", "units",
                   "unit_session_pct", "revenue")
    for snap in snapshots:
        clean = _drop_parent_rollup(snap)
        for r in clean:
            ca = r["child_asin"]
            entry = {"period": r["period"]}
            for k in METRIC_KEYS:
                entry[k] = r.get(k, 0.0)
            pp = partial_periods.get(r["period"])
            if pp is not None:
                entry["partial"] = True
                entry["days_covered"] = pp.get("days_covered")
            node = model.get(ca)
            if node is None:
                model[ca] = {"parent_asin": r["parent_asin"],
                             "title": r["title"], "history": [entry]}
            else:
                node["history"].append(entry)
                if r["period"] >= max(h["period"] for h in node["history"]):
                    node["parent_asin"] = r["parent_asin"]
                    node["title"] = r["title"]
    for node in model.values():
        node["history"].sort(key=lambda h: h["period"])
    return model


# ─────────────────────────────────────────────────────────────────────────────
# F6.3 — Adaptador history→motor + forecast por-ASIN (funciones puras)
# ─────────────────────────────────────────────────────────────────────────────

def _period_to_date(period: str) -> str:
    """'2026-05' → '2026-05-01' (el motor espera date ISO completa)."""
    return f"{period}-01"


def _asin_history_to_engine_rows(history: list[dict]) -> list[dict]:
    """Mapea el history de un ASIN (de _accumulate_asin_snapshots) al shape que
    consume generate_forecast: cada row necesita 'date' (ISO), 'revenue', 'units',
    'sessions', y 'cvr' (= unit_session_pct, el CVR por-sesión del reporte BR).
    spend/ventasPPC no vienen del reporte por-ASIN → se omiten (el motor los trata
    como 0 vía _js_number). Ordena asc por date.
    """
    rows = []
    for h in history:
        rows.append({
            "date": _period_to_date(h["period"]),
            "revenue": h.get("revenue", 0.0),
            "units": h.get("units", 0.0),
            "sessions": h.get("sessions", 0.0),
            "cvr": h.get("unit_session_pct", 0.0),
        })
    rows.sort(key=lambda r: r["date"])
    return rows


def _forecast_single_asin(history: list[dict], opts: dict,
                          yoy_mode: str = "auto") -> list[dict]:
    """Aplica el motor MoM/YoY existente a UN ASIN individual.
    Los meses marcados partial=True se EXCLUYEN del cálculo (un mes incompleto
    distorsiona el MoM: el motor lo leería como caída/suba real). El parcial sigue
    visible en las tablas; solo el forecast lo ignora. Requiere >=2 meses COMPLETOS.
    Devuelve [] si <2 meses completos.
    F6.3c: el forecast arranca en el mes siguiente al último mes CARGADO (incluye
    el parcial), no al último completo — así no re-proyecta un mes que las tablas
    ya muestran como real parcial (contradicción cliente-facing).
    """
    complete = [h for h in history if not h.get("partial")]
    engine_rows = _asin_history_to_engine_rows(complete)
    if len(engine_rows) < 2:
        return []
    # F6.3c: el forecast arranca en el mes siguiente al último mes CARGADO
    # (incluye el parcial), NO al último completo. Evita que el forecast
    # re-proyecte un mes que las tablas ya muestran como real parcial
    # (contradicción cliente-facing). El crecimiento MoM sigue anclado al
    # último mes COMPLETO dentro del motor (prev = engine_rows[-1]).
    last_loaded = max(h["period"] for h in history)
    start_from = _get_next_month_iso(_period_to_date(last_loaded))
    seasonality = auto_detect_seasonality(engine_rows) or {"enabled": False,
                                                            "indices": [1.0] * 12}
    return generate_forecast(opts, engine_rows, seasonality, yoy_mode,
                             start_from=start_from)


# ─────────────────────────────────────────────────────────────────────────────
# F6.2 — Helpers de tabla/totales por-ASIN (funciones puras, None/NaN→'' pre-Arrow)
# ─────────────────────────────────────────────────────────────────────────────

# ── Real vs forecast por ASIN ────────────────────────────────────────────────
#
# RESTRICCIÓN DURA: el reporte "Detail Page Sales and Traffic By Child Item" NO
# trae spend ni ventasPPC — Amazon no reporta inversión de Ads a nivel ASIN en
# ese export. Por eso el real-vs-forecast por ASIN sólo puede graficar las 4
# métricas que el reporte SÍ tiene. ACOS / TACOS / Spend / Ventas PPC por ASIN
# no existen y NO se inventan: quedan fuera del selector, a nivel cuenta.
#
# El "real" de un ASIN es su propio history acumulado (el último mes cargado,
# parcial incluido); el forecast arranca en el mes siguiente (F6.3c). O sea: la
# comparación es graficar ambas series en el mismo eje, no cruzar dos capas.

# E6 — el forecast por-ASIN se dispara con un botón explícito, no al elegir el
# ASIN. Usa los MISMOS opts de la proyección general (un único set de
# parámetros, para que ambas vistas sean reconciliables) y cachea el resultado
# POR ASIN en session_state. Estos dos helpers son puros para poder testear el
# gating sin runtime Streamlit.

def _asin_fc_cache_key(client_id: str, asin: str) -> str:
    """Key de session_state del forecast cacheado de UN asin de UN cliente.

    Incluye el asin para que cambiar de ASIN no muestre el forecast del
    anterior: cada ASIN se genera (y se re-muestra) por separado.
    """
    return f"rf_asin_fc_result_{client_id}_{asin}"


def _fc_params_caption(opts: dict) -> str:
    """Resumen legible de los parámetros de proyección: 'horizonte 3 meses ·
    ventana MoM 2 · mezcla 50% MoM [· estacionalidad ON]'.
    """
    txt = (
        f"horizonte {int(opts.get('horizon', 3))} meses · "
        f"ventana MoM {int(opts.get('momWindow', 3))} · "
        f"mezcla {int(opts.get('blend', 50))}% MoM"
    )
    if opts.get("useSeasonality"):
        txt += " · estacionalidad ON"
    return txt


_ASIN_CHART_METRICS: tuple = ("revenue", "sessions", "units", "cvr")


def _asin_realvs_forecast_series(history: list, fc: list,
                                 metric_id: str) -> dict:
    """Series real + forecast de UN ASIN para una de las 4 métricas permitidas.

    Reusa `_asin_history_to_engine_rows` para el mapeo de nombres del history
    (`unit_session_pct` → `cvr`), así el eje del real y el del forecast hablan
    el mismo idioma.

    El forecast arranca REPITIENDO el último punto real (bridge), igual que
    `_bridge` en los charts de cuenta: así las dos líneas se tocan.

    Args:
        history: `model[asin]["history"]` de `_accumulate_asin_snapshots`.
        fc: salida de `_forecast_single_asin` (puede ser []).
        metric_id: uno de `_ASIN_CHART_METRICS`.

    Returns:
        {"real": {"x", "y", "partial"}, "forecast": {"x", "y"}} — `x` en fecha
        ISO completa (`YYYY-MM-01`), `partial` alineado con el real.

    Raises:
        ValueError: si `metric_id` no está entre las 4 permitidas. Explícito a
            propósito: un chart vacío escondería que la métrica no existe a
            nivel ASIN.
    """
    if metric_id not in _ASIN_CHART_METRICS:
        raise ValueError(
            f"'{metric_id}' no está disponible por ASIN — el reporte By Child "
            f"Item no trae spend ni ventas PPC. Permitidas: "
            f"{', '.join(_ASIN_CHART_METRICS)}."
        )

    history = history or []
    rows = _asin_history_to_engine_rows(history)
    partial_by_period = {h["period"]: bool(h.get("partial")) for h in history}

    real_x = [r["date"] for r in rows]
    real_y = [_safe_num(r.get(metric_id)) for r in rows]
    partial = [partial_by_period.get(x[:7], False) for x in real_x]

    fc_x = [f["date"] for f in (fc or [])]
    fc_y = [_safe_num(f.get(metric_id)) for f in (fc or [])]
    if real_x and fc_x:
        fc_x = [real_x[-1]] + fc_x
        fc_y = [real_y[-1]] + fc_y

    return {
        "real": {"x": real_x, "y": real_y, "partial": partial},
        "forecast": {"x": fc_x, "y": fc_y},
    }


def _asin_realvs_forecast_chart(history: list, fc: list,
                                metric_id: str) -> "go.Figure":
    """Figura real (sólida) vs forecast (dashed) de UN ASIN.

    Cero estilo nuevo: los tokens salen de `_chart_trace` y `_METRICS`, los
    mismos de los 7 charts de cuenta. El mes parcial se marca con el punto hueco
    de siempre (`_MARKER_SIZE_PARTIAL`) sólo si el ASIN tiene alguno.
    """
    m = _METRICS[metric_id]
    fig = go.Figure()
    fig.update_layout(**_PLOTLY_LAYOUT)

    s = _asin_realvs_forecast_series(history, fc, metric_id)
    if not s["real"]["x"]:
        return fig

    partial = s["real"]["partial"] if any(s["real"]["partial"]) else None
    fig.add_trace(_chart_trace(
        s["real"]["x"], s["real"]["y"], f'{m["label"]} (real)',
        m["color"], "hist", partial=partial,
    ))
    if s["forecast"]["x"]:
        fig.add_trace(_chart_trace(
            s["forecast"]["x"], s["forecast"]["y"], f'{m["label"]} (forecast)',
            m["color"], "fc",
        ))

    unit = m["unit"]
    if unit == "currency":
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    elif unit == "percent":
        fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    else:
        fig.update_yaxes(tickformat=",.0f")
    return fig


def _build_asin_child_df(model: dict) -> pd.DataFrame:
    """Una fila por child_asin: columnas child_asin, title, parent_asin, y una
    columna revenue por period (pivote). Celdas de meses sin dato del ASIN quedan
    como '' (no NaN, no 0.0) pre-Arrow. Ordenado por revenue del período más
    reciente desc.
    """
    periods = sorted({h["period"] for node in model.values()
                      for h in node["history"]})
    latest = periods[-1] if periods else None
    rows = []
    for ca, node in model.items():
        rev_by_p = {h["period"]: h.get("revenue", 0.0) for h in node["history"]}
        row = {
            "child_asin": ca,
            "title": node.get("title", ""),
            "parent_asin": node.get("parent_asin", ""),
        }
        for p in periods:
            row[p] = rev_by_p.get(p, "")  # '' para meses sin dato (no NaN/0.0)
        row["_sort"] = rev_by_p.get(latest, 0.0) if latest else 0.0
        rows.append(row)
    rows.sort(key=lambda r: r["_sort"], reverse=True)
    for r in rows:
        del r["_sort"]
    df = pd.DataFrame(rows)
    # Belt-and-suspenders: cualquier NaN residual → '' antes de Arrow.
    df = df.where(pd.notna(df), "")
    return df


def _build_asin_parent_df(model: dict, all_periods: list[str]) -> pd.DataFrame:
    """Una fila por parent_asin: columnas parent_asin, title, y una columna
    revenue por period (suma de los childs del parent).

    E5 — título representativo del parent: un parent agrupa varios childs con
    títulos distintos, así que se elige el del child cuyo asin == parent_asin
    (el "padre real", que suele estar en el catálogo con su propio título). Si
    ese child no está en el modelo, se cae al primer título no vacío que
    aparezca para ese parent. `title` va primera después de parent_asin, igual
    que en la tabla Child.

    Celdas de períodos sin dato quedan como '' (no NaN, no 0.0) pre-Arrow.
    """
    pagg: dict = {}
    ptitle: dict = {}
    ptitle_fallback: dict = {}
    for asin, node in model.items():
        par = node.get("parent_asin", "")
        byp = pagg.setdefault(par, {})
        for h in node["history"]:
            byp[h["period"]] = byp.get(h["period"], 0.0) + _js_number(
                h.get("revenue"))
        node_title = (node.get("title") or "").strip()
        if asin == par and node_title:
            ptitle[par] = node_title
        elif node_title and par not in ptitle_fallback:
            ptitle_fallback[par] = node_title

    prows = []
    for par, byp in pagg.items():
        title = ptitle.get(par) or ptitle_fallback.get(par, "")
        row = {"parent_asin": par, "title": title}
        for p in all_periods:
            row[p] = byp.get(p, "")
        prows.append(row)
    pdf = pd.DataFrame(prows)
    pdf = pdf.where(pd.notna(pdf), "")
    return pdf


def _asin_account_totals(model: dict) -> list[dict]:
    """Totales por period sumando todos los ASINs: [{period, revenue, units,
    sessions}, ...] ordenado asc. Para nivel Cuenta y KPI cards.
    """
    from collections import defaultdict
    agg: dict = defaultdict(lambda: {"revenue": 0.0, "units": 0.0, "sessions": 0.0})
    for node in model.values():
        for h in node["history"]:
            a = agg[h["period"]]
            a["revenue"] += _js_number(h.get("revenue"))
            a["units"] += _js_number(h.get("units"))
            a["sessions"] += _js_number(h.get("sessions"))
    return [{"period": p, **agg[p]} for p in sorted(agg)]


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
    if value == "" or value is None or (isinstance(value, float) and math.isnan(value)):
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
            # Sentinel None (→ NaN) en vez de '' — mezclar float y str hace la
            # columna dtype object, que Streamlit 1.43.2 marca Arrow-incompatible
            # y DESHABILITA (data_editor.py:836-843). Eso congelaba la edición en
            # estado parcial (bug G1). None → NaN mantiene la columna float64
            # limpia; NaN se renderiza como celda vacía en NumberColumn.
            "Spend": spend_f,
            "Ventas PPC": vppc_f,
            "ACOS%": acos,
            "TACOS%": tacos,
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
# FORECAST ENGINE (F3) — lógica pura, sin runtime Streamlit
# ─────────────────────────────────────────────────────────────────────────────
#
# Port verbatim de las funciones JS del HTML (L1295-L1914, L2266-L2283). Diseño:
#
#   • Las funciones del motor NO leen `st.*` ni `_cur_client()` por dentro.
#     Reciben los datos como parámetros explícitos: `rows` (historical),
#     `seasonality` (dict), `yoy_mode` (str), `opts` (dict horizon/momWindow/
#     blend/useSeasonality). Esto las hace 100% testeables sin runtime.
#
#   • Un wrapper fino `_run_forecast_for_active_client(state=None)` lee del
#     accessor (`cur = _cur_client(state)`), extrae rows/seasonality/yoy_mode,
#     llama al motor puro, y MUTA `cur["forecast"]` in-place (es la ref viva).
#
#   • El parámetro `ctx` del HTML (ctx.rows / ctx.seasonality / ctx.marginPct)
#     se usa en el HTML para forecasts por-ASIN. NO se portea acá: en su lugar
#     las funciones reciben los datos como parámetros directos.
#
# Fidelidad numérica — replicado EXACTO:
#   1. mes 0-11 vía `date.fromisoformat(iso[:10]).month - 1` (JS getUTCMonth()).
#   2. `Math.round` (half-away-from-zero) ≠ `round()` Python (banker's). Donde
#      el HTML usa Math.round, acá `_round_half_up_int` / `_round_half_up_dec`.
#   3. Guards de división: `units || 1`, `sessions > 0`, `aov > 0`,
#      `Math.max(1, revenue)`, `prev > 0`, `count ? sum/count : 0`.
#   4. Truthy/falsy de JS para `value != null && value !== ''` → helper
#      `_js_truthy_present` (None y '' → False, 0 → True).


def _round_half_up_int(x: float) -> int:
    """Equivalente a `Math.round(x)` de JS (half-away-from-zero para >= 0).

    Python `round()` usa banker's rounding (half-even). Usamos `floor(x + 0.5)`
    que matchea JS para valores no-negativos (revenue/spend siempre lo son en
    este contexto). NaN se propaga como 0 fail-soft.
    """
    if x is None:
        return 0
    if isinstance(x, float) and math.isnan(x):
        return 0
    return math.floor(float(x) + 0.5)


def _round_half_up_dec(x: float, dec: int = 2) -> float:
    """Equivalente a `Math.round(x * 10**dec) / 10**dec` de JS.

    Replica el redondeo half-up del HTML L1903 (`Math.round(spend*100)/100`) y
    L1835 (`+x.toFixed(1)`). Usa `Decimal.quantize(ROUND_HALF_UP)` para evitar
    binary float drift.
    """
    if x is None:
        return 0.0
    if isinstance(x, float) and math.isnan(x):
        return 0.0
    q = Decimal("1").scaleb(-dec)  # 10^-dec
    return float(Decimal(str(float(x))).quantize(q, rounding=ROUND_HALF_UP))


def _js_truthy_present(v: Any) -> bool:
    """`v != null && v !== ''` de JS. None y '' → False; 0 → True; NaN → False.

    El HTML usa este pattern para distinguir "el AM cargó 0 explícitamente" de
    "el AM no cargó nada". Crítico en spend/ventasPPC/tacosTarget/manual*.
    """
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    if v == "":
        return False
    return True


def _js_number(v: Any) -> float:
    """Equivalente a `+v || 0` de JS: convierte a número; '', None, NaN, falla
    de parseo → 0. 0 numérico se preserva como 0 (no falsy en este wrapper —
    el `|| 0` solo entra cuando `+v` es NaN, lo cual NO incluye al 0 puro).

    Pero ojo: el HTML usa `+f.spend || 0` (L1905); ahí 0 y None y '' colapsan a
    0. Esa colisión es intencional del autor original — la replicamos.
    """
    if v is None:
        return 0.0
    if isinstance(v, bool):  # bool es subclass de int; protegerlo
        return float(int(v))
    if isinstance(v, (int, float)):
        if isinstance(v, float) and math.isnan(v):
            return 0.0
        return float(v)
    if v == "":
        return 0.0
    try:
        f = float(v)
        if math.isnan(f):
            return 0.0
        return f
    except (ValueError, TypeError):
        return 0.0


def _get_next_month_iso(iso: str) -> str:
    """Port de getNextMonthISO L1295. Avanza al primer día del mes siguiente.

    'YYYY-MM-DD' → 'YYYY-MM-01' del mes siguiente (maneja dic→ene del año
    siguiente).
    """
    y, m, _ = iso[:10].split("-")
    yi, mi = int(y), int(m)
    if mi == 12:
        return f"{yi + 1:04d}-01-01"
    return f"{yi:04d}-{mi + 1:02d}-01"


def _find_historical(iso: str, rows: list[dict]) -> Optional[dict]:
    """Port de findHistorical L1746."""
    for r in rows:
        if r.get("date") == iso:
            return r
    return None


def _same_month_last_year_engine(iso: str, rows: list[dict]) -> Optional[dict]:
    """Port de sameMonthLastYear L1749. Mismo mes-día, año - 1.

    Nota: el módulo ya tiene `_same_month_last_year` arriba (helper de quick
    stats, F2). Mantenemos copia interna del motor con la semántica exacta
    `setUTCFullYear(year-1)` + `findHistorical` — son funcionalmente
    equivalentes pero esta versión no toca el módulo F2 y deja el motor
    aislado.
    """
    try:
        y, m, d = iso[:10].split("-")
        target = f"{int(y) - 1:04d}-{m}-{d}"
    except (ValueError, AttributeError):
        return None
    return _find_historical(target, rows)


def _avg_mom_growth(field: str, window: int, rows: list[dict]) -> float:
    """Port de avgMoMGrowth L1722.

    n = min(window, len-1). Itera i de len-n a len-1. Suma (curr-prev)/prev
    SOLO si prev > 0. Promedia sobre `count` (no sobre n). len<2 → 0.
    """
    h = rows
    if len(h) < 2:
        return 0.0
    n = min(window, len(h) - 1)
    total = 0.0
    count = 0
    for i in range(len(h) - n, len(h)):
        prev = _js_number(h[i - 1].get(field))
        curr = _js_number(h[i].get(field))
        if prev > 0:
            total += (curr - prev) / prev
            count += 1
    return (total / count) if count else 0.0


def _yoy_growth(field: str, rows: list[dict]) -> float:
    """Port de yoyGrowth L1733.

    len < 13 → 0. Busca la fila con date EXACTAMENTE un año antes (mismo
    mes-día). Si no existe o yearAgo[field] es falsy (0/None) → 0.
    """
    h = rows
    if len(h) < 13:
        return 0.0
    last = h[-1]
    last_iso = last.get("date")
    if not last_iso:
        return 0.0
    try:
        y, m, d = last_iso[:10].split("-")
        ya_iso = f"{int(y) - 1:04d}-{m}-{d}"
    except (ValueError, AttributeError):
        return 0.0
    year_ago = _find_historical(ya_iso, h)
    if year_ago is None:
        return 0.0
    ya_val = year_ago.get(field)
    # `!yearAgo[field]` de JS: 0/null/undefined/'' → True (falsy). Replicamos.
    if not ya_val:
        return 0.0
    last_val = _js_number(last.get(field))
    return (last_val - float(ya_val)) / float(ya_val)


def _has_yoy_data(rows: list[dict]) -> bool:
    """Port de hasYoYData L1743."""
    return len(rows) >= 13


def _yoy_enabled(yoy_mode: str, rows: list[dict]) -> bool:
    """Port de la línea L1768:
       `(state.account.yoyMode === 'on') || (mode === 'auto' && hasYoYData(rows))`
    """
    if yoy_mode == "on":
        return True
    if yoy_mode == "auto" and _has_yoy_data(rows):
        return True
    return False


def _days_in_month(iso: str) -> int:
    """Port de `new Date(Date.UTC(y, m+1, 0)).getUTCDate()` (L1875).

    Devuelve los días del mes de la fecha. iso = 'YYYY-MM-DD'.
    """
    y, m, _ = iso[:10].split("-")
    return calendar.monthrange(int(y), int(m))[1]


def recompute_forecast_row(f: dict) -> dict:
    """Port verbatim de recomputeForecastRow L1873.

    Muta `f` in-place y lo devuelve (chainable). Asigna las mismas keys que el
    HTML L1913: revenue, aov, units, sessions, cvr, ventasPPC, tacos,
    pctVtasPPC, salesVelocity, acos, availability.

    Reglas:
      - manualRevenue / manualAOV / manualSessions overriden a Auto cuando set.
      - availability clamp 0-100; revenue *= avail/100 (sessions NO escala).
      - units = revenue / aov si aov > 0, else 0.
      - cvr = units / sessions * 100 si sessions > 0, else 0.
      - Si tacosTarget set y revenue > 0 → spend = revenue * tacosTarget/100
        (y `f.spend` se redondea a 2 decimales half-up).
        Si no → spend = `+f.spend || 0`.
      - ventasPPC = spend / (acos / 100) si acos > 0, else 0.
      - tacos = spend / revenue * 100 si revenue > 0.
      - salesVelocity = units / dim si dim > 0.
    """
    dim = _days_in_month(f["date"])

    revenue = (
        float(f["manualRevenue"]) if _js_truthy_present(f.get("manualRevenue"))
        else _js_number(f.get("revenueAuto"))
    )
    aov = (
        float(f["manualAOV"]) if _js_truthy_present(f.get("manualAOV"))
        else _js_number(f.get("aovAuto"))
    )
    sessions = (
        float(f["manualSessions"]) if _js_truthy_present(f.get("manualSessions"))
        else _js_number(f.get("sessionsAuto"))
    )

    # availability: HTML L1888 `(f.stockAvailability != null && !== '') ? +x : 100`.
    if _js_truthy_present(f.get("stockAvailability")):
        availability = _js_number(f["stockAvailability"])
    else:
        availability = 100.0
    if availability < 0:
        availability = 0.0
    if availability > 100:
        availability = 100.0
    avail_factor = availability / 100.0
    revenue = revenue * avail_factor

    units = (revenue / aov) if aov > 0 else 0.0
    cvr = ((units / sessions) * 100.0) if sessions > 0 else 0.0

    if _js_truthy_present(f.get("tacosTarget")) and revenue > 0:
        spend = revenue * (_js_number(f["tacosTarget"]) / 100.0)
        # HTML L1903: `f.spend = Math.round(spend * 100) / 100` (half-up 2 dec).
        f["spend"] = _round_half_up_dec(spend, 2)
    else:
        spend = _js_number(f.get("spend"))  # `+f.spend || 0`

    acos = _js_number(f.get("acosTarget"))
    ventas_ppc = (spend / (acos / 100.0)) if acos > 0 else 0.0
    tacos = ((spend / revenue) * 100.0) if revenue > 0 else 0.0
    pct_vtas_ppc = ((ventas_ppc / revenue) * 100.0) if revenue > 0 else 0.0
    sales_velocity = (units / dim) if dim > 0 else 0.0

    f.update({
        "revenue": revenue,
        "aov": aov,
        "units": units,
        "sessions": sessions,
        "cvr": cvr,
        "ventasPPC": ventas_ppc,
        "tacos": tacos,
        "pctVtasPPC": pct_vtas_ppc,
        "salesVelocity": sales_velocity,
        "acos": acos,
        "availability": availability,
    })
    return f


def generate_forecast(
    opts: dict,
    rows: list[dict],
    seasonality: dict,
    yoy_mode: str,
    start_from: Optional[str] = None,
) -> list[dict]:
    """Port verbatim de generateForecast L1761.

    Args:
        opts: dict con keys `horizon` (int meses), `momWindow` (int),
            `blend` (int 0-100, porcentaje MoM), `useSeasonality` (bool).
        rows: histórico (ya ordenado asc por date). Equivalente a
            `state.historical` del HTML.
        seasonality: dict {enabled: bool, indices: [12 floats]}.
        yoy_mode: 'auto' | 'on' | 'off'. Equivalente a `state.account.yoyMode`.
        start_from: ISO 'YYYY-MM-DD' opcional. Si viene, el forecast estampa su
            PRIMERA fila en ese mes (override del cursor). Si es None, arranca en
            el mes siguiente al último `rows` (comportamiento MVP original). El
            crecimiento MoM sigue anclado a `rows[-1]` en ambos casos.

    Returns:
        Lista de forecast rows con shape del HTML L1837-1858, ya pasados por
        `recompute_forecast_row`. Vacía si rows está vacío.

    NOTA: el `ctx` param del HTML (rows/seasonality/marginPct override) se
    expresa acá como parámetros directos `rows` y `seasonality`. El motor no
    distingue entre "global" y "por-ASIN" — el caller arma el ctx que quiera.
    """
    if not rows:
        return []

    horizon = int(opts["horizon"])
    mom_window = int(opts["momWindow"])
    blend = float(opts["blend"]) / 100.0  # % MoM
    use_season = bool(opts.get("useSeasonality", False))

    yoy_enabled = _yoy_enabled(yoy_mode, rows)

    g_rev = _avg_mom_growth("revenue", mom_window, rows)
    g_units = _avg_mom_growth("units", mom_window, rows)
    g_sess = _avg_mom_growth("sessions", mom_window, rows)
    y_rev = _yoy_growth("revenue", rows) if yoy_enabled else 0.0
    y_sess = _yoy_growth("sessions", rows) if yoy_enabled else 0.0
    # y_units no se usa en el HTML (línea 1776 lo calcula pero no lo aplica
    # en el loop — units se deriva de revenue/aov). Lo mantenemos para
    # fidelidad documental, pero NO entra en el cálculo. Comentado a propósito:
    # y_units = _yoy_growth("units", rows) if yoy_enabled else 0.0

    # Trailing avgs sobre los últimos 3 meses (L1779-1781).
    last3 = rows[-3:]
    if last3:
        avg_aov = sum(
            _js_number(r.get("revenue")) / (_js_number(r.get("units")) or 1)
            for r in last3
        ) / len(last3)
        avg_cvr = sum(_js_number(r.get("cvr")) for r in last3) / len(last3)
    else:
        avg_aov = 0.0
        avg_cvr = 0.0

    # avgTACOS sobre filas con spend cargado (L1784-1787). spend en USD;
    # divisor: max(1, revenue) para evitar div/0.
    ads_last3 = [r for r in last3 if _js_truthy_present(r.get("spend"))]
    if ads_last3:
        avg_tacos: Optional[float] = sum(
            _js_number(r["spend"]) / max(1.0, _js_number(r.get("revenue")))
            for r in ads_last3
        ) / len(ads_last3) * 100.0
    else:
        avg_tacos = None

    # avgACOSReal sobre filas con spend Y ventasPPC > 0 (L1788-1791).
    ads_acos_last3 = [
        r for r in last3
        if r.get("spend") is not None and _js_truthy_present(r.get("ventasPPC"))
        and _js_number(r.get("ventasPPC")) > 0
    ]
    # Nota: el HTML usa `r.spend != null` (sin chequear ''); preservamos su
    # filtro exacto: spend not None pero permite spend='' (que entra como 0).
    # Para alinear con el comportamiento defensivo del módulo, validamos
    # también que spend no sea '' usando _js_truthy_present arriba en TACOS;
    # para ACOS la condición original era más laxa.
    if ads_acos_last3:
        avg_acos_real: Optional[float] = sum(
            _js_number(r.get("spend")) / _js_number(r.get("ventasPPC"))
            for r in ads_acos_last3
        ) / len(ads_acos_last3) * 100.0
    else:
        avg_acos_real = None

    forecasts: list[dict] = []
    last_hist = rows[-1]
    prev: dict = dict(last_hist)  # copia defensiva
    curr_iso = start_from or _get_next_month_iso(last_hist["date"])

    for _ in range(horizon):
        m_idx = date.fromisoformat(curr_iso[:10]).month - 1  # 0-11
        year = date.fromisoformat(curr_iso[:10]).year

        # Revenue: blend MoM + YoY.
        mom_proj = _js_number(prev.get("revenue")) * (1.0 + g_rev)
        yoy_month = _same_month_last_year_engine(curr_iso, rows)
        yoy_proj = (
            _js_number(yoy_month.get("revenue")) * (1.0 + y_rev)
            if yoy_month is not None else mom_proj
        )
        if yoy_enabled and yoy_month is not None:
            rev_base = blend * mom_proj + (1.0 - blend) * yoy_proj
        else:
            rev_base = mom_proj

        # Seasonality. HTML L1811-1813: `indices[mIdx] || 1`.
        if use_season and seasonality.get("enabled"):
            sf_raw = seasonality.get("indices", [1.0] * 12)[m_idx]
            s_factor = float(sf_raw) if sf_raw else 1.0
        else:
            s_factor = 1.0
        revenue = rev_base * s_factor

        # Sessions: misma lógica.
        mom_sess = _js_number(prev.get("sessions")) * (1.0 + g_sess)
        yoy_sess = (
            _js_number(yoy_month.get("sessions")) * (1.0 + y_sess)
            if yoy_month is not None else mom_sess
        )
        if yoy_enabled and yoy_month is not None:
            sessions = blend * mom_sess + (1.0 - blend) * yoy_sess
        else:
            sessions = mom_sess
        # Sessions escala con seasonality cuando aplica (mismo factor que rev).
        sessions = sessions * (s_factor if (use_season and seasonality.get("enabled")) else 1.0)

        # AOV: estable alrededor del trailing avg (L1822-1824).
        aov = avg_aov
        if aov == 0:
            aov = revenue / max(1.0, _js_number(prev.get("units")))

        # Units: derivado de revenue/aov (L1827).
        if aov > 0:
            units = revenue / aov
        else:
            units = _js_number(prev.get("units")) * (1.0 + g_units)

        # CVR: derivado de units/sessions (L1829).
        cvr = ((units / sessions) * 100.0) if sessions > 0 else avg_cvr

        # Ads defaults (L1831-1835). tacosUse: avgTACOS/100 si hay; sino 0.10.
        tacos_use = (avg_tacos / 100.0) if (avg_tacos is not None) else 0.10
        spend_default = revenue * tacos_use
        # acosDefault: `avgACOSReal != null ? +avgACOSReal.toFixed(1) : 30`.
        acos_default = (
            _round_half_up_dec(avg_acos_real, 1)
            if avg_acos_real is not None else 30.0
        )

        f: dict = {
            "date": curr_iso,
            "year": year,
            "month": m_idx,
            # Editable inputs.
            "seasonality": s_factor,
            "blend": opts["blend"],
            "manualRevenue": None,
            "manualAOV": None,
            "manualSessions": None,
            # HTML L1847: `Math.round(spendDefault)` (half-up entero).
            "spend": _round_half_up_int(spend_default),
            "acosTarget": acos_default,
            "tacosTarget": None,
            # Base auto values.
            "revenueAuto": revenue,
            "sessionsAuto": sessions,
            "aovAuto": aov,
            # Computed (refreshed by recompute).
            "revenue": revenue,
            "units": units,
            "aov": aov,
            "sessions": sessions,
            "cvr": cvr,
            "salesVelocity": 0.0,
            "pctVtasPPC": 0.0,
            "ventasPPC": 0.0,
            "acos": acos_default,
            "tacos": 0.0,
        }
        recompute_forecast_row(f)
        forecasts.append(f)

        prev = {
            "revenue": f["revenue"],
            "units": f["units"],
            "sessions": f["sessions"],
            "cvr": f["cvr"],
        }
        curr_iso = _get_next_month_iso(curr_iso)

    return forecasts


def auto_detect_seasonality(rows: list[dict]) -> Optional[dict]:
    """Port de autoDetectSeasonality L2266 — versión PURA.

    El HTML llama `alert()` y `renderSeasonality()` + `saveState()`. Acá NO
    tocamos UI ni state global: si len < 12 devolvemos None (el caller en UI
    muestra el mensaje). Si len >= 12, devuelve un dict NUEVO
    `{enabled: True, indices: [12 floats]}` listo para asignar al cliente.

    Cálculo:
      - sums/counts por month-of-year sobre `revenue`.
      - avgPerMonth[m] = sums[m]/counts[m] si counts[m]>0 else 0.
      - overall = sum(avgPerMonth) / count(meses con avgPerMonth > 0).
      - indices[m] = round_half_up(avgPerMonth[m] / overall, 3) si > 0 else 1.

    Returns:
        dict {enabled, indices[12]} o None si len(rows) < 12.
    """
    if len(rows) < 12:
        return None

    sums = [0.0] * 12
    counts = [0] * 12
    for r in rows:
        try:
            m = date.fromisoformat(r["date"][:10]).month - 1
        except (ValueError, KeyError, TypeError):
            continue
        sums[m] += _js_number(r.get("revenue"))
        counts[m] += 1

    avg_per_month = [
        (sums[i] / counts[i]) if counts[i] > 0 else 0.0
        for i in range(12)
    ]
    months_with_data = [a for a in avg_per_month if a > 0]
    if not months_with_data:
        # Sin revenue positivo en ningún mes — overall sería 0/0. Defensivo:
        # devolvemos índices neutros sin marcar enabled (el HTML no contempla
        # este caso porque el botón solo se habilita con 12+ meses no nulos).
        return {"enabled": True, "indices": [1.0] * 12}
    overall = sum(avg_per_month) / len(months_with_data)

    indices = [
        _round_half_up_dec(a / overall, 3) if a > 0 else 1.0
        for a in avg_per_month
    ]
    return {"enabled": True, "indices": indices}


# ─────────────────────────────────────────────────────────────────────────────
# Wrapper Streamlit → motor puro (F3)
# ─────────────────────────────────────────────────────────────────────────────

def _run_forecast_for_active_client(
    opts: dict, state: Optional[Any] = None,
) -> list[dict]:
    """Lee el estado del cliente activo, llama al motor puro, MUTA forecast.

    Wrapper fino: lee rows/seasonality/yoy_mode del accessor `_cur_client`,
    invoca `generate_forecast`, y escribe el resultado en `cur["forecast"]`
    (mutación in-place de la ref viva en session_state). Devuelve la lista
    para que el caller pueda renderearla sin re-leer del state.

    Args:
        opts: dict {horizon, momWindow, blend, useSeasonality}.
        state: dict-like; default `st.session_state`.

    Returns:
        Lista de forecast rows (vacía si no hay cliente activo o histórico).
    """
    cur = _cur_client(state)
    if cur is None:
        return []
    rows = cur.get("historical", [])
    seasonality = cur.get("seasonality", {"enabled": False, "indices": [1.0] * 12})
    yoy_mode = cur.get("yoy_mode", "auto")
    forecasts = generate_forecast(opts, rows, seasonality, yoy_mode)
    cur["forecast"] = forecasts
    return forecasts


# ─────────────────────────────────────────────────────────────────────────────
# F6-G1 — Helpers puros de series para charts (bridge, YoY, accessors hist/fc)
# ─────────────────────────────────────────────────────────────────────────────
#
# Sin Streamlit, sin Plotly. Producen dicts {"x": [...], "y": [...]} listos para
# graficar. Las hist rows y las fc rows tienen SHAPE DISTINTO (port verbatim del
# HTML): aov/acos/tacos/salesVelocity NO existen en hist (se CALCULAN) pero SÍ en
# fc (los escribe recompute_forecast_row respetando los overrides acosTarget/
# tacosTarget del AM). Por eso cada métrica tiene DOS accessors: from_hist
# (calcula) y from_fc (LEE, nunca recalcula → respeta el override). Un solo
# _bridge cubre los 7 charts.


def _safe_num(v: Any) -> Optional[float]:
    """Normaliza a float para charts, con None cuando el dato está AUSENTE.

    None / '' / NaN → None (hueco en el chart, NO 0). Resto → float delegando en
    `_parse_num` (que ya cubre '$1,234', '1,234.5', '12%', 'MX$...'). 0 → 0.0.

    Reuso deliberado: NO se envuelve `_js_number` (su semántica JS colapsa
    ''/None/NaN → 0.0, lo opuesto a lo que el chart necesita, y no parsea monedas
    con coma/$/%). `_parse_num` es el parser rico existente; acá sólo se agrega el
    guard "ausente → None". Un único parser de números en el módulo.
    """
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    return _parse_num(v)


def _shift_period(date_iso: str, months: int) -> str:
    """Desplaza una fecha ISO por N meses. Aritmética entera sobre y*12 + (m-1).

    '2026-03-01', -12 → '2025-03-01'. Sin dateutil (no está en requirements).
    Devuelve siempre día 01.
    """
    y, m = int(date_iso[:4]), int(date_iso[5:7])
    total = y * 12 + (m - 1) + months
    ny, nm = divmod(total, 12)
    return f"{ny:04d}-{nm + 1:02d}-01"


# ── Accessors ────────────────────────────────────────────────────────────────
# Reads directos (revenue/units/sessions/cvr/spend/ventasPPC) via factory.
# Computados en hist (aov/acos/tacos/salesVelocity) con guards. En fc TODOS se
# leen (el motor ya los escribió respetando los overrides del AM).

def _reader(key: str):
    """Factory de accessor que lee `key` de la row vía _safe_num."""
    def _acc(r: dict) -> Optional[float]:
        return _safe_num(r.get(key))
    return _acc


def _acc_hist_aov(r: dict) -> Optional[float]:
    """AOV en hist = revenue/units (units>0, si no None)."""
    units = _safe_num(r.get("units"))
    rev = _safe_num(r.get("revenue"))
    if units and units > 0 and rev is not None:
        return rev / units
    return None


def _acc_hist_acos(r: dict) -> Optional[float]:
    """ACOS en hist = spend/ventasPPC*100 (spend no-None Y ventasPPC>0)."""
    spend = _safe_num(r.get("spend"))
    vppc = _safe_num(r.get("ventasPPC"))
    if spend is not None and vppc is not None and vppc > 0:
        return spend / vppc * 100.0
    return None


def _acc_hist_tacos(r: dict) -> Optional[float]:
    """TACOS en hist = spend/revenue*100 (spend no-None Y revenue>0)."""
    spend = _safe_num(r.get("spend"))
    rev = _safe_num(r.get("revenue"))
    if spend is not None and rev is not None and rev > 0:
        return spend / rev * 100.0
    return None


def _acc_hist_sales_velocity(r: dict) -> Optional[float]:
    """Sales velocity en hist = units / max(1, días del mes). Port verbatim del
    HTML `r.units / Math.max(1, dim)` (el guard es gratis, mantiene el port
    rastreable). Reusa `_days_in_month`."""
    units = _safe_num(r.get("units"))
    if units is None:
        return None
    return units / max(1, _days_in_month(r["date"]))


# ── Catálogo de métricas ─────────────────────────────────────────────────────
# metric_id = id del HTML tal cual (ventasPPC, salesVelocity camelCase) para que
# el port sea rastreable. Colores VERIFICADOS contra el HTML (L2330-2372).

_METRICS: dict = {
    "revenue":       {"label": "Revenue",        "unit": "currency", "color": "#FF3300",
                      "from_hist": _reader("revenue"),   "from_fc": _reader("revenue")},
    "units":         {"label": "Units Sold",     "unit": "count",    "color": "#E85B03",
                      "from_hist": _reader("units"),     "from_fc": _reader("units")},
    "sessions":      {"label": "Sessions",       "unit": "count",    "color": "#FBBF24",
                      "from_hist": _reader("sessions"),  "from_fc": _reader("sessions")},
    "cvr":           {"label": "CVR %",          "unit": "percent",  "color": "#34D399",
                      "from_hist": _reader("cvr"),       "from_fc": _reader("cvr")},
    "aov":           {"label": "AOV",            "unit": "currency", "color": "#60A5FA",
                      "from_hist": _acc_hist_aov,        "from_fc": _reader("aov")},
    "spend":         {"label": "Spend",          "unit": "currency", "color": "#A78BFA",
                      "from_hist": _reader("spend"),     "from_fc": _reader("spend")},
    "ventasPPC":     {"label": "Ventas PPC",     "unit": "currency", "color": "#F472B6",
                      "from_hist": _reader("ventasPPC"), "from_fc": _reader("ventasPPC")},
    "acos":          {"label": "ACOS %",         "unit": "percent",  "color": "#F87171",
                      "from_hist": _acc_hist_acos,       "from_fc": _reader("acos")},
    "tacos":         {"label": "TACOS %",        "unit": "percent",  "color": "#22D3EE",
                      "from_hist": _acc_hist_tacos,      "from_fc": _reader("tacos")},
    "salesVelocity": {"label": "Sales Velocity", "unit": "count",    "color": "#FB923C",
                      "from_hist": _acc_hist_sales_velocity, "from_fc": _reader("salesVelocity")},
}


def _series(rows: list, acc) -> dict:
    """Serie {x: [dates], y: [acc(row)]} sobre `rows` con el accessor dado."""
    return {"x": [r["date"] for r in rows], "y": [acc(r) for r in rows]}


def _bridge(hist_rows: list, fc_rows: list, from_hist, from_fc) -> tuple:
    """Devuelve (serie_hist, serie_fc). La serie fc ARRANCA repitiendo el último
    punto histórico (BRIDGE) → las líneas se tocan en el chart.

    El punto de bridge se computa con `from_hist` sobre la ÚLTIMA row histórica
    (el bridge ES el último punto hist, no un from_fc). Contratos:
      - con hist y fc: len(fc.x)==len(fc_rows)+1, fc.x[0]==hist.x[-1], fc.y[0]==hist.y[-1]
      - hist vacío → fc SIN bridge (len(fc.x)==len(fc_rows))
      - fc vacío → (serie_hist, {x:[],y:[]})
      - hist.y[-1] is None → el bridge copia None (no inventa valor)
    """
    serie_hist = _series(hist_rows, from_hist)
    if not fc_rows:
        return serie_hist, {"x": [], "y": []}
    fc_x = [f["date"] for f in fc_rows]
    fc_y = [from_fc(f) for f in fc_rows]
    if hist_rows:
        last = hist_rows[-1]
        fc_x = [last["date"]] + fc_x
        fc_y = [from_hist(last)] + fc_y   # bridge = último punto hist (from_hist)
    return serie_hist, {"x": fc_x, "y": fc_y}


def _actual_series(hist_rows: list, actual_rows: list, accessor) -> dict:
    """Serie de la capa `actual` (F7-A): {x, y, partial}, con bridge al histórico.

    La serie `actual` arranca repitiendo el último punto histórico — igual que la
    de forecast — para que ambas líneas salgan del MISMO lugar y se vea dónde
    divergen. Eso es exactamente la lectura que el AM necesita: real vs proyectado.

    Reusa `_bridge` sin tocarlo: como las filas de `actual` tienen shape de
    `historical`, `from_hist` y `from_fc` son el MISMO accessor, y el segundo
    elemento que devuelve `_bridge` ya es la serie puenteada que hace falta.

    El ancla es el último histórico ESTRICTAMENTE ANTERIOR al primer `actual`, no
    `hist_rows[-1]`: cuando un mes de `actual` cierra entra también a `historical`,
    y anclar al último a secas haría que la línea vuelva para atrás.

    `partial` viene alineado con x/y. El punto de bridge es un punto histórico
    (mes cerrado) → `False`. El resto copia el flag de cada fila, incluido `None`
    (cobertura desconocida — ver `_parse_actual_report`).

    Contratos:
      - actual vacío → {"x": [], "y": [], "partial": []}
      - sin histórico anterior al primer actual → SIN bridge
      - valor None en el punto de ancla → el bridge copia None (no inventa 0)
    """
    if not actual_rows:
        return {"x": [], "y": [], "partial": []}

    first_date = actual_rows[0]["date"]
    anchor_rows = [r for r in hist_rows if r["date"] < first_date]
    _hist_serie, serie = _bridge(anchor_rows, actual_rows, accessor, accessor)

    partial = [r.get("partial") for r in actual_rows]
    if len(serie["x"]) == len(actual_rows) + 1:      # hubo bridge
        partial = [False] + partial
    return {"x": serie["x"], "y": serie["y"], "partial": partial}


def _yoy_series(hist_rows: list, fc_rows: list, from_hist) -> dict:
    """Serie del mismo mes del año previo, sobre el eje COMPLETO (hist+fc), SIN
    bridge. La fuente es SIEMPRE `hist_rows` + `from_hist` (nunca fc: proyectar
    contra proyección no tiene sentido). Sin 12+ meses de match → valores None
    (lista alineada al eje, NO vacía).
    """
    axis = [r["date"] for r in hist_rows] + [f["date"] for f in fc_rows]
    by_date = {r["date"]: r for r in hist_rows}
    y = []
    for d in axis:
        prev = by_date.get(_shift_period(d, -12))
        y.append(from_hist(prev) if prev is not None else None)
    return {"x": axis, "y": y}


# ─────────────────────────────────────────────────────────────────────────────
# F6-G2 — Charts del patrón común (Plotly go.Figure, sin Streamlit)
# ─────────────────────────────────────────────────────────────────────────────
#
# _metric_chart es LA función genérica: los 4 charts del patrón (revenue,
# sessions, cvr, units) salen de acá parametrizados por metric_id. Hasta 3 traces
# (hist / forecast dashed / YoY dotted washed-out), reusando _bridge y _yoy_series
# de G1. NO recalcula nada, NO llama a Streamlit (el st.plotly_chart es de G5).

_CHART_GRID = "#1d1d1d"       # --line-2 (tema oscuro, default del OS)
_CHART_TICK = "#a8a8a8"       # --text-mute
_CHART_FONT = "JetBrains Mono, monospace"

# F7-A2 — color único de la línea `actual` (el REAL contra el forecast). Verde
# más saturado que el CVR del catálogo (#34D399) para que no se confundan cuando
# el chart de CVR muestre las dos.
_CHART_ACTUAL = "#22C55E"

# Tamaño y grosor de anillo del punto de un mes PARCIAL (mes en curso). Ver el
# docstring de `_chart_trace`: con los defaults el `circle-open` se dibuja pero
# no se ve.
#
# 🔴 CALIBRADO A OJO, NO DEDUCIDO. Este valor pasó por 11 → 8 → 12: el 8 salió de
# razonar la geometría sobre el papel (hueco = size - ring) y NO sobrevivió al
# chart renderizado. La aritmética da un hueco de 6px, pero contra una línea de
# 2px del mismo color el aro queda ilegible al tamaño real del punto. A 12 el
# hueco es de 10px → ~4px visibles a cada lado.
# Si hay que volver a tocarlo: mirando el chart, no la cuenta.
_MARKER_SIZE_PARTIAL = 12
_MARKER_RING_PARTIAL = 2

# Layout base VERIFICADO contra el HTML de Edu. Fondo transparente → hereda el
# tema de Streamlit; valores del tema OSCURO fijos (Streamlit no expone
# getComputedStyle). Los 10 colores de métrica son fijos en ambos temas.
_PLOTLY_LAYOUT: dict = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"family": _CHART_FONT, "color": _CHART_TICK, "size": 10},
    "hovermode": "x unified",
    "margin": {"l": 50, "r": 50, "t": 30, "b": 40},
    "legend": {"orientation": "h", "yanchor": "bottom", "y": 1.02,
               "xanchor": "left", "x": 0},
    "xaxis": {"gridcolor": _CHART_GRID, "zeroline": False,
              "tickfont": {"color": _CHART_TICK, "size": 10, "family": _CHART_FONT}},
    "yaxis": {"gridcolor": _CHART_GRID, "zeroline": False,
              "tickfont": {"color": _CHART_TICK, "size": 10, "family": _CHART_FONT}},
}


def _washed_color(hex6: str, alpha_hex: str = "88") -> str:
    """Convierte '#RRGGBB' + alpha hex ('88' del HTML) a 'rgba(r,g,b,a)'.

    El HTML usaba `color + "88"` (hex de 8 dígitos) para el trace YoY washed-out.
    Esta versión de Plotly RECHAZA el hex de 8 dígitos en line.color (sólo acepta
    #RRGGBB o rgba) → portamos el mismo alpha a rgba (0x88 = 136/255 ≈ 0.533).
    Mismo efecto visual, formato válido.
    """
    h = hex6.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    a = int(alpha_hex, 16) / 255.0
    return f"rgba({r},{g},{b},{a:.3f})"


# F7-A4 — verde despintado para la 2da línea `actual` en adelante de los charts
# MULTI-MÉTRICA (Ads, ACOS/TACOS, Custom). Mismo alpha que el YoY.
#
# Por qué: el reporte HTML se abre y se le saca screenshot. Ahí no hay hover, y
# dos (o más) líneas del MISMO verde son indistinguibles salvo por la legend.
# Con la 1ra sólida y el resto washed, cuál es cuál se lee de un vistazo.
#
# Se aplica en los builders, así que rige TAMBIÉN en la app — a propósito: si el
# export se viera distinto de la pantalla, el AM validaría una figura y mandaría
# otra. Los charts de UNA métrica (`_metric_chart`) no se tocan: ahí la única
# línea real sigue sólida.
_CHART_ACTUAL_WASHED = _washed_color(_CHART_ACTUAL)


def _metric_chart(metric_id: str, hist_rows: list, fc_rows: list,
                  show_yoy: bool = False,
                  actual_rows: Optional[list] = None) -> "go.Figure":
    """Construye la figura de UNA métrica del catálogo `_METRICS`.

    Hasta 4 traces: histórico (spline sólido), forecast (dashed, mismo color),
    YoY opcional (dotted, color washed-out `+"88"`) y `actual` opcional (sólido
    verde, F7-A2). Todos los valores salen de `_bridge`/`_yoy_series`/
    `_actual_series` con los accessors del catálogo — NO se recalcula nada.
    Eje Y formateado según `unit` (currency/count/percent).

    `actual_rows` None o [] → figura idéntica a la de antes de F7-A2.

    Guard: `hist_rows` vacío → figura VACÍA (con layout), NO excepción (fiel al
    HTML `if (state.historical.length === 0) return;`).
    """
    m = _METRICS[metric_id]
    fig = go.Figure()
    fig.update_layout(**_PLOTLY_LAYOUT)

    if not hist_rows:
        return fig

    hist, fc = _bridge(hist_rows, fc_rows, m["from_hist"], m["from_fc"])

    # Trace 1 — histórico (siempre).
    fig.add_trace(go.Scatter(
        x=hist["x"], y=hist["y"], name=m["label"],
        mode="lines+markers",
        line=dict(color=m["color"], width=2, shape="spline", smoothing=0.3),
        marker=dict(size=4),
        connectgaps=True,
    ))

    # Trace 2 — forecast (sólo si hay).
    if fc["x"]:
        fig.add_trace(go.Scatter(
            x=fc["x"], y=fc["y"], name=f'{m["label"]} (forecast)',
            mode="lines+markers",
            line=dict(color=m["color"], width=2, dash="dash",
                      shape="spline", smoothing=0.3),
            marker=dict(size=6),
            connectgaps=True,
        ))

    # Trace 3 — YoY (sólo si show_yoy).
    if show_yoy:
        yoy = _yoy_series(hist_rows, fc_rows, m["from_hist"])
        fig.add_trace(go.Scatter(
            x=yoy["x"], y=yoy["y"], name=f'{m["label"]} YoY',
            mode="lines+markers",
            line=dict(color=_washed_color(m["color"]), width=1, dash="dot",
                      shape="spline", smoothing=0.3),
            marker=dict(size=2),
            connectgaps=True,
        ))

    # Trace 4 — actual (F7-A2, sólo si el AM cargó el real).
    if actual_rows:
        tr = _actual_trace(hist_rows, actual_rows, m)
        if tr is not None:
            fig.add_trace(tr)

    # Eje Y según unidad.
    unit = m["unit"]
    if unit == "currency":
        fig.update_yaxes(tickprefix="$", tickformat=",.0f")
    elif unit == "percent":
        fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    else:  # count
        fig.update_yaxes(tickformat=",.0f")

    return fig


# ─────────────────────────────────────────────────────────────────────────────
# F6-G3 — Charts multi-métrica: Ads (spend+ventasPPC) y ACOS/TACOS
# ─────────────────────────────────────────────────────────────────────────────
#
# Estos 2 charts meten DOS métricas del catálogo en la MISMA figura (5 traces),
# por eso no salen de _metric_chart (una métrica por figura). Puro ensamblado:
# los valores vienen de _bridge/_yoy_series con los accessors de _METRICS. Cero
# cálculo nuevo. El estilo de trace se centraliza en _chart_trace (mismos tokens
# que G2) para que el lenguaje visual sea idéntico en los 7 charts.


def _chart_trace(x: list, y: list, name: str, color: str, role: str,
                 partial: Optional[list] = None) -> "go.Scatter":
    """Arma un go.Scatter con el estilo del módulo según `role`:
        'hist'   → sólido, width 2, marker 4
        'fc'     → dashed, width 2, marker 6   (dashed = forecast, en los 7 charts)
        'yoy'    → dotted, width 1, marker 2, color washed-out (_washed_color)
        'actual' → sólido, width 2, marker 5   (F7-A2: el REAL vs el forecast)
    Mismos tokens que _metric_chart (G2). Todos con spline 0.3 + connectgaps.

    `actual` va SÓLIDA a propósito: es dato real cerrado, con el mismo peso visual
    que la línea histórica. El dash queda reservado al forecast en los 7 charts.

    `partial` (F7-A2, ADITIVO): lista de `Optional[bool]` alineada con x/y que
    marca qué puntos son de un mes todavía en curso.
        None (default) → NADA se arma; el marker queda como siempre (size
                         escalar, sin symbol, sin line). Es lo que mantiene
                         intactos los roles viejos, que no lo pasan.
        lista          → se arman TRES arrays paralelos. Sólo `True` marca el
                         punto: `False` y `None` (cobertura desconocida, ver
                         `_parse_actual_report`) van llenos y del tamaño normal.

    Por qué tres arrays y no sólo `symbol` (hallazgo del smoke visual de A3):
    plotly.js estroquea los símbolos `-open` con `marker.line.width`, cuyo default
    de schema en scatter es 0 → cae a un fallback de 1px. Un anillo de 1px sobre
    un marcador de 5px, atravesado por la línea de 2px del MISMO color, deja medio
    píxel de hueco a cada lado: el `circle-open` se dibujaba, pero era ilegible.
    El tamaño salió de mirar el chart, no de la cuenta: con size 8 la aritmética
    daba 6px de hueco y ~2px visibles a cada lado, y aun así el aro no se leía al
    tamaño real del punto. `_MARKER_SIZE_PARTIAL` está en 12 (ver su comentario) →
    hueco de 10px, ~4px por lado. `line.width=0` en los no-parciales deja esos
    puntos exactos. El param NO está acoplado al role — si se pasa, se aplica.
    """
    if role == "hist":
        line = dict(color=color, width=2, shape="spline", smoothing=0.3)
        marker = dict(size=4)
    elif role == "fc":
        line = dict(color=color, width=2, dash="dash", shape="spline", smoothing=0.3)
        marker = dict(size=6)
    elif role == "actual":
        line = dict(color=color, width=2, shape="spline", smoothing=0.3)
        marker = dict(size=5)
    else:  # yoy
        line = dict(color=_washed_color(color), width=1, dash="dot",
                    shape="spline", smoothing=0.3)
        marker = dict(size=2)

    if partial is not None:
        base = marker["size"]
        marker["symbol"] = ["circle-open" if p is True else "circle" for p in partial]
        marker["size"] = [_MARKER_SIZE_PARTIAL if p is True else base for p in partial]
        marker["line"] = dict(
            color=line["color"],
            width=[_MARKER_RING_PARTIAL if p is True else 0 for p in partial],
        )

    return go.Scatter(x=x, y=y, name=name, mode="lines+markers",
                      line=line, marker=marker, connectgaps=True)


# ─────────────────────────────────────────────────────────────────────────────
# F7-A2 — la línea `actual` en los 7 charts
# ─────────────────────────────────────────────────────────────────────────────
#
# Los 4 builders (_metric_chart, _ads_chart, _acos_tacos_chart, _custom_chart)
# suman `actual_rows=None` AL FINAL de su firma. Con None o [] la figura es
# exactamente la de antes de F7-A2 — los tests de G2-G4 pasan sin tocarse.
#
# Toda la aritmética de la serie es de A1 (`_actual_series`): acá sólo se ensambla
# el trace. Cero cálculo nuevo, igual que G3/G4.


def _actual_trace(hist_rows: list, actual_rows: list, m: dict,
                  color: str = _CHART_ACTUAL) -> Optional["go.Scatter"]:
    """Trace `actual` de UNA métrica del catálogo, o None si la serie sale vacía.

    Usa `m["from_hist"]` (no `from_fc`): las filas de `actual` tienen shape de
    `historical`, así que los valores se CALCULAN igual que en el histórico. Es
    lo que hace que el ACOS real salga de spend/ventasPPC reales y no de los
    targets que el motor escribió en el forecast.

    `color` (F7-A4, ADITIVO): default `_CHART_ACTUAL` → los callers viejos y los
    charts de UNA métrica quedan exactamente igual. Los multi-métrica pasan
    `_CHART_ACTUAL_WASHED` de la 2da línea real en adelante.
    """
    a = _actual_series(hist_rows, actual_rows, m["from_hist"])
    if not a["x"]:
        return None
    return _chart_trace(a["x"], a["y"], f'{m["label"]} (real)',
                        color, "actual", partial=a["partial"])


def _ads_chart(hist_rows: list, fc_rows: list, show_yoy: bool = False,
               actual_rows: Optional[list] = None) -> "go.Figure":
    """Chart de Ads: spend + ventasPPC en la misma figura (hasta 7 traces).

    Trazas: Spend (hist/fc) + Ventas PPC (hist/fc) + UN solo YoY (el de SPEND —
    verbatim del HTML: con 5 líneas, un 2do YoY lo vuelve ilegible) + `actual` de
    AMBAS métricas (F7-A2). Eje Y en $ con `rangemode="tozero"` — es el ÚNICO de
    los 7 charts con beginAtZero (HTML L2653). Guard: hist vacío → figura vacía,
    sin excepción.

    Se dibujan las DOS líneas reales —no sólo spend— por simetría con el forecast,
    que también proyecta ambas: mostrar el real de una sola dejaría media
    comparación. Entre sí se distinguen POR COLOR (F7-A4): la 1ra va verde sólido
    y la 2da verde washed. Antes eran las dos del mismo verde y se separaban por
    legend + hover, lo que no sobrevive al screenshot del reporte HTML, que es
    estático. El orden es fijo (spend → ventasPPC), así que cuál queda sólida es
    estable entre reruns.
    """
    fig = go.Figure()
    fig.update_layout(**_PLOTLY_LAYOUT)
    if not hist_rows:
        return fig

    sp_hist, sp_fc = _bridge(hist_rows, fc_rows,
                             _METRICS["spend"]["from_hist"], _METRICS["spend"]["from_fc"])
    vp_hist, vp_fc = _bridge(hist_rows, fc_rows,
                             _METRICS["ventasPPC"]["from_hist"], _METRICS["ventasPPC"]["from_fc"])
    sp_color = _METRICS["spend"]["color"]
    vp_color = _METRICS["ventasPPC"]["color"]

    fig.add_trace(_chart_trace(sp_hist["x"], sp_hist["y"], "Spend (hist.)", sp_color, "hist"))
    if sp_fc["x"]:
        fig.add_trace(_chart_trace(sp_fc["x"], sp_fc["y"], "Spend (forecast)", sp_color, "fc"))
    fig.add_trace(_chart_trace(vp_hist["x"], vp_hist["y"], "Ventas PPC (hist.)", vp_color, "hist"))
    if vp_fc["x"]:
        fig.add_trace(_chart_trace(vp_fc["x"], vp_fc["y"], "Ventas PPC (forecast)", vp_color, "fc"))
    if show_yoy:
        sp_yoy = _yoy_series(hist_rows, fc_rows, _METRICS["spend"]["from_hist"])
        fig.add_trace(_chart_trace(sp_yoy["x"], sp_yoy["y"], "Spend año previo (YoY)", sp_color, "yoy"))

    # F7-A4 — `drawn` cuenta traces EFECTIVAMENTE dibujados, no posiciones del
    # loop: si el real de spend sale vacío, la sólida pasa a ser ventasPPC. Así
    # siempre hay exactamente UNA verde sólida cuando hay alguna línea real, en
    # vez de quedar una washed suelta sin referencia.
    if actual_rows:
        drawn = 0
        for mid in ("spend", "ventasPPC"):
            tr = _actual_trace(
                hist_rows, actual_rows, _METRICS[mid],
                color=_CHART_ACTUAL if drawn == 0 else _CHART_ACTUAL_WASHED,
            )
            if tr is not None:
                fig.add_trace(tr)
                drawn += 1

    fig.update_yaxes(tickprefix="$", tickformat=",.0f", rangemode="tozero")
    return fig


def _acos_tacos_chart(hist_rows: list, fc_rows: list,
                      show_yoy: bool = False,
                      actual_rows: Optional[list] = None) -> "go.Figure":
    """Chart de ACOS/TACOS: acos + tacos en la misma figura (hasta 5 traces).

    DESVIACIÓN CONSCIENTE DEL HTML (decisión de Lenin): en el HTML este era el
    ÚNICO chart que NO separaba hist/forecast en traces (concatenaba todo) y usaba
    `borderDash:[6,4]` en TACOS para distinguirlo de ACOS — o sea, "dashed"
    significaba dos cosas distintas según el chart. Como los 7 charts se ven
    juntos en el reporte cliente-facing, se NORMALIZA: **dashed = forecast en los
    7 charts, sin excepción**. Acá ACOS y TACOS se distinguen por COLOR (catálogo),
    nunca por dash; el dash queda reservado al tramo de forecast.

    Los valores del forecast salen de `from_fc` → LEEN `f["acos"]`/`f["tacos"]`
    (que el motor escribió respetando los overrides acosTarget/tacosTarget del AM).
    NUNCA se recalcula spend/ventasPPC*100 en el forecast (sería el bug F6.3c:
    chart ≠ tabla). Eje Y en % SIN rangemode (ese es exclusivo de Ads). Guard:
    hist vacío → figura vacía, sin excepción.
    """
    fig = go.Figure()
    fig.update_layout(**_PLOTLY_LAYOUT)
    if not hist_rows:
        return fig

    ac_hist, ac_fc = _bridge(hist_rows, fc_rows,
                             _METRICS["acos"]["from_hist"], _METRICS["acos"]["from_fc"])
    tc_hist, tc_fc = _bridge(hist_rows, fc_rows,
                             _METRICS["tacos"]["from_hist"], _METRICS["tacos"]["from_fc"])
    ac_color = _METRICS["acos"]["color"]
    tc_color = _METRICS["tacos"]["color"]

    fig.add_trace(_chart_trace(ac_hist["x"], ac_hist["y"], "ACOS %", ac_color, "hist"))
    if ac_fc["x"]:
        fig.add_trace(_chart_trace(ac_fc["x"], ac_fc["y"], "ACOS % (forecast)", ac_color, "fc"))
    fig.add_trace(_chart_trace(tc_hist["x"], tc_hist["y"], "TACOS %", tc_color, "hist"))
    if tc_fc["x"]:
        fig.add_trace(_chart_trace(tc_fc["x"], tc_fc["y"], "TACOS % (forecast)", tc_color, "fc"))
    if show_yoy:
        ac_yoy = _yoy_series(hist_rows, fc_rows, _METRICS["acos"]["from_hist"])
        fig.add_trace(_chart_trace(ac_yoy["x"], ac_yoy["y"], "ACOS año previo (YoY)", ac_color, "yoy"))

    # F7-A2 — ACOS/TACOS reales. Salen de `from_hist` sobre las filas de `actual`
    # (spend/ventasPPC/revenue REALES), NUNCA de los targets del forecast: la
    # gracia de este chart es ver si el target se está cumpliendo o no.
    # F7-A4 — 1ra sólida (ACOS), 2da washed (TACOS). Misma regla que Ads/Custom.
    if actual_rows:
        drawn = 0
        for mid in ("acos", "tacos"):
            tr = _actual_trace(
                hist_rows, actual_rows, _METRICS[mid],
                color=_CHART_ACTUAL if drawn == 0 else _CHART_ACTUAL_WASHED,
            )
            if tr is not None:
                fig.add_trace(tr)
                drawn += 1

    fig.update_yaxes(ticksuffix="%", tickformat=".1f")
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# F6-G4 — Chart custom: N métricas del catálogo en 1 figura, con doble eje Y
# ─────────────────────────────────────────────────────────────────────────────
#
# El HTML deja al usuario prender/apagar chips de las 10 métricas y las mete
# todas en un solo chart. Como las unidades conviven (currency + count + percent),
# hay hasta 2 ejes Y. Esta capa es PURA: recibe `metric_ids` como argumento; los
# chips/session_state son de G5. Reusa _bridge/_yoy_series/_chart_trace (cero
# estilos nuevos, cero recálculo).

# Formato de tick por unidad (mismos tokens que _metric_chart/_ads/_acos).
_AXIS_FMT: dict = {
    "currency": {"tickprefix": "$", "tickformat": ",.0f"},
    "count":    {"tickformat": ",.0f"},
    "percent":  {"ticksuffix": "%", "tickformat": ".1f"},
}


def _axis_split(metric_ids: list) -> tuple:
    """Devuelve (left_unit, right_unit) según la regla VERBATIM del HTML.

    `units_used` = unidades distintas EN ORDEN DE APARICIÓN en `metric_ids`.
      1 unidad         → (unit, None)                 eje único
      hay 'percent'    → (1ra no-percent, 'percent')  percent SIEMPRE a la derecha
      sin percent      → (units[0], units[1])         orden de aparición

    Sin métricas válidas → (None, None). El caso 3-unidades (currency+count+
    percent) manda count al eje derecho junto al percent — no hay 3er eje. Es el
    comportamiento que Edu ya vio; se porta tal cual (ver test del caso borde).
    """
    units_used: list = []
    for mid in metric_ids:
        m = _METRICS.get(mid)
        if m is None:
            continue
        if m["unit"] not in units_used:
            units_used.append(m["unit"])

    if not units_used:
        return None, None
    if len(units_used) == 1:
        return units_used[0], None
    if "percent" in units_used:
        left = next(u for u in units_used if u != "percent")
        return left, "percent"
    return units_used[0], units_used[1]


def _custom_chart(metric_ids: list, hist_rows: list, fc_rows: list,
                  show_yoy: bool = False,
                  actual_rows: Optional[list] = None) -> "go.Figure":
    """Chart custom: hasta 4 traces por métrica seleccionada, con doble eje Y.

    Guards: hist vacío → figura vacía; metric_ids vacío → figura vacía (el
    "mínimo 1 chip" se enforcea en G5); metric_id desconocido → se ignora
    (fiel al `if (!m) return;` del HTML). Los 3 traces de una métrica van al
    MISMO eje (el que le toca por su unidad). dashed=forecast, dotted=YoY —
    idéntico a los otros 6 charts. Sin rangemode (eso es de _ads_chart).
    """
    fig = go.Figure()
    fig.update_layout(**_PLOTLY_LAYOUT)
    if not hist_rows or not metric_ids:
        return fig

    left_unit, right_unit = _axis_split(metric_ids)

    # F7-A4 — igual que Ads/ACOS: la 1ra línea real dibujada va verde sólido y el
    # resto washed. Acá el contador vive FUERA del loop de métricas porque hay N.
    # `metric_ids` llega en orden de catálogo (G5 lo normaliza en L4301 y el
    # export en el wiring), así que cuál queda sólida es estable entre reruns.
    drawn_actual = 0

    for mid in metric_ids:
        m = _METRICS.get(mid)
        if m is None:
            continue
        yaxis = "y" if m["unit"] == left_unit else "y2"
        color = m["color"]
        hist, fc = _bridge(hist_rows, fc_rows, m["from_hist"], m["from_fc"])

        tr = _chart_trace(hist["x"], hist["y"], m["label"], color, "hist")
        tr.yaxis = yaxis
        fig.add_trace(tr)
        if fc["x"]:
            tr = _chart_trace(fc["x"], fc["y"], f'{m["label"]} (forecast)', color, "fc")
            tr.yaxis = yaxis
            fig.add_trace(tr)
        if show_yoy:
            yoy = _yoy_series(hist_rows, fc_rows, m["from_hist"])
            tr = _chart_trace(yoy["x"], yoy["y"], f'{m["label"]} YoY', color, "yoy")
            tr.yaxis = yaxis
            fig.add_trace(tr)
        if actual_rows:
            tr = _actual_trace(
                hist_rows, actual_rows, m,
                color=_CHART_ACTUAL if drawn_actual == 0 else _CHART_ACTUAL_WASHED,
            )
            if tr is not None:
                tr.yaxis = yaxis     # mismo eje que su métrica, o la escala miente
                fig.add_trace(tr)
                drawn_actual += 1

    # Eje izquierdo: merge sobre el yaxis de _PLOTLY_LAYOUT (conserva grid/tickfont).
    fig.update_layout(yaxis=_AXIS_FMT.get(left_unit, {}))
    # Eje derecho: sólo si hay 2da unidad. showgrid=False → no duplica grilla
    # (verbatim del HTML: grid.drawOnChartArea=false en el eje secundario).
    if right_unit is not None:
        ax2 = {
            "overlaying": "y", "side": "right", "showgrid": False,
            "zeroline": False, "gridcolor": _CHART_GRID,
            "tickfont": {"color": _CHART_TICK, "size": 10, "family": _CHART_FONT},
        }
        ax2.update(_AXIS_FMT.get(right_unit, {}))
        fig.update_layout(yaxis2=ax2)
    return fig


# ─────────────────────────────────────────────────────────────────────────────
# Render principal — Fase 2: selector + datos
# ─────────────────────────────────────────────────────────────────────────────

def _header() -> None:
    """Header estándar Capybaras (patrón module-architecture-standard)."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📈</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>Monthly Forecast</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Account Manager · proyección de revenue cliente-céntrica (Fase 2: ingesta + visualización)"
        "</div></div></div>",
        unsafe_allow_html=True,
    )
    st.divider()


def _render_account_config(cur: dict) -> None:
    """Render del bloque "Configuración de la cuenta" (port del HTML L724-749).

    3 campos editables (marketplace, currency, yoy_mode). Cada cambio se
    escribe al cliente activo vía `_update_account_config`. Los inputs
    usan `key=` con el id del cliente para que cambiar de cliente NO les
    arrastre estado viejo.

    `margin` NO se expone: ningún cálculo del motor lo consume (el `ctx.marginPct`
    del HTML original nunca se portó). El campo sigue viviendo en el dict del
    cliente con su default para no romper lo ya persistido en Supabase.
    """
    st.markdown("##### Configuración de la cuenta")
    st.caption("Define el contexto base. Estos parámetros afectan el cálculo del forecast (F3).")

    col1, col2, col3 = st.columns(3)

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

    col_up, col_demo, col_clear = st.columns([2, 1, 1])
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
                _try_persist()  # autosave: histórico del cliente recién poblado
                st.success(f"Demo cargado: {n} meses.")
                st.rerun()
            else:
                st.error("No se pudo cargar el demo (sin cliente activo).")

    with col_clear:
        n_hist = len(cur.get("historical", []))
        with st.popover(
            "🗑️ Limpiar histórico",
            disabled=(n_hist == 0),
            help="Vacía el histórico del cliente activo. Útil antes de re-subir un reporte desde cero.",
        ):
            st.markdown(
                f"**¿Vaciar el histórico de _{cur['name']}_?**  \n"
                f"Se van a borrar **{n_hist} mes{'es' if n_hist != 1 else ''}** "
                f"de datos (incluyendo Spend y Ventas PPC manuales). "
                f"Esta acción no se puede deshacer."
            )
            if st.button(
                "Sí, vaciar histórico",
                key=f"rf_clear_confirm_{cur['id']}",
                type="primary",
            ):
                cur["historical"] = []
                _try_persist()
                st.success("Histórico vaciado. Re-subí el reporte para empezar de cero.")
                st.rerun()

    if uploaded is not None:
        # `.getvalue()` para que el parser cacheado reciba bytes (patrón M30).
        data = uploaded.getvalue()
        try:
            rows = _parse_business_report(data, uploaded.name)
        except ReportLacksSessionsError as e:
            # Reporte sin tráfico (típico: Sales and Orders by Month en lugar
            # de Sales and Traffic by Date). NO ingerir a medias — el motor
            # F3 necesita sessions. Mostrar mensaje claro al AM.
            st.error(str(e))
            return
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


# ─────────────────────────────────────────────────────────────────────────────
# F7-A3 — wiring de la capa `actual`
# ─────────────────────────────────────────────────────────────────────────────
#
# A1 dejó los helpers puros, A2 los charts listos para recibir `actual_rows`.
# Acá se conecta: uploader del mes real + la única pieza que necesita saber qué
# día es hoy.


def _resolve_partial(actual_rows: list, today: Optional[date] = None) -> list:
    """Cierra el `partial=None` que deja `_parse_actual_report` para el BR mensual.

    A1 es PURO: cuando Amazon ya agregó el mes (1 fila, sin días), no hay forma de
    medir la cobertura y deja `None` en vez de adivinar. Acá sí sabemos la fecha,
    así que se resuelve por comparación: el mes EN CURSO está corriendo (parcial),
    cualquier otro está cerrado.

    Lo que A1 SÍ midió (BR diario → `True`/`False`) NO se pisa: es la verdad del
    dato. Un julio subido a los 20 días sigue siendo parcial aunque julio ya haya
    cerrado.

    Devuelve COPIAS. `cur["actual"]` es el dato persistido del cliente y no debe
    quedar contaminado con un flag derivado de HOY — mañana la respuesta cambia.

    Args:
        actual_rows: filas de la capa `actual`.
        today: inyectable para tests; default `date.today()`.
    """
    if today is None:
        today = date.today()
    mes_en_curso = f"{today.year:04d}-{today.month:02d}-01"

    out: list[dict] = []
    for r in actual_rows:
        row = dict(r)
        if row.get("partial") is None:
            row["partial"] = (row.get("date") == mes_en_curso)
        out.append(row)
    return out


def _k_actual_sig(cur: dict) -> str:
    """Key de session_state donde se firma el último archivo real ya procesado.

    Namespaced por cliente: cambiar de cliente NO arrastra la firma del anterior.
    """
    return f"{_STATE_PREFIX}actual_sig_{cur['id']}"


def _render_actual_upload(cur: dict) -> None:
    """Uploader del mes real: el BR del mes en curso, para comparar REAL vs forecast.

    Vive en su propia función y NO al final de `_render_upload_and_demo` a
    propósito: esa función corta con `return` cuando el BR del histórico falla al
    parsear, y un bloque agregado abajo quedaría invisible justo en ese caso.

    Mergea sobre `cur["actual"]` con `_merge_historical` — su contrato ya sirve
    tal cual (match por mes, preserva Spend/Ventas PPC manuales, ordena asc) y no
    toca `cur["historical"]`: las dos capas conviven.

    NO llama `_try_persist()`, igual que el uploader del histórico: el AM guarda
    las dos capas de una con el botón 💾.

    F7 · UX — el bloque va en `st.container(border=True)` con el título en el
    MISMO verde de la línea real. Los dos uploaders piden el mismo reporte y
    tenían la misma pinta (`#####` + caption + uploader collapsed): en el smoke el
    archivo se cargó 4 veces en el del histórico. El modo de falla es silencioso
    —`cur["actual"]` queda vacío y la línea verde simplemente no se dibuja, sin
    aviso— así que la separación tiene que verse ANTES de soltar el archivo. El
    verde es el mismo token del chart a propósito: el color del título es el color
    de la línea que el AM va a buscar.
    """
    with st.container(border=True):
        st.markdown(
            f"##### <span style='color:{_CHART_ACTUAL}'>●</span> Cargar mes real",
            unsafe_allow_html=True,
        )
        st.caption(
            "El mismo reporte \"By Date · Sales and Traffic\", pero del mes que "
            "está corriendo. Se dibuja como línea verde en los gráficos, contra "
            "el forecast — no toca el histórico. Si lo que querés es cargar meses "
            "cerrados, va arriba, en \"Cargar Business Report\"."
        )

        col_up, col_clear = st.columns([3, 1])
        with col_up:
            uploaded = st.file_uploader(
                "Mes real (CSV o XLSX)",
                type=["csv", "xlsx", "xls"],
                key=f"rf_actual_uploader_{cur['id']}",
                label_visibility="collapsed",
            )
        with col_clear:
            # El popover va ANTES del early return de abajo a propósito: sin
            # archivo cargado es justo cuando el AM quiere vaciar la capa.
            n_actual = len(cur.get("actual", []))
            with st.popover(
                "🗑️ Limpiar mes real",
                disabled=(n_actual == 0),
                help="Vacía SÓLO la capa del mes real. El histórico no se toca.",
            ):
                st.markdown(
                    f"**¿Vaciar el mes real de _{cur['name']}_?**  \n"
                    f"Se van a borrar **{n_actual} mes{'es' if n_actual != 1 else ''}** "
                    f"de la capa real (la línea verde de los gráficos). El "
                    f"histórico queda intacto. Esta acción no se puede deshacer."
                )
                if st.button(
                    "Sí, vaciar mes real",
                    key=f"rf_clear_actual_confirm_{cur['id']}",
                    type="primary",
                ):
                    cur["actual"] = []
                    st.session_state.pop(_k_actual_sig(cur), None)
                    _try_persist()
                    st.success("Mes real vaciado. Re-subí el reporte cuando quieras.")
                    st.rerun()

        if uploaded is None:
            return

        data = uploaded.getvalue()
        try:
            rows = _parse_actual_report(data, uploaded.name)
        except ReportLacksSessionsError as e:
            st.error(str(e))
            return
        except Exception as e:  # noqa: BLE001 — fail-soft al AM
            st.error(f"No se pudo parsear el archivo: {e}")
            return

        if not rows:
            st.warning(
                "No se reconocieron filas con formato by-date en este archivo. "
                "Verificá que tenga columnas 'Date' y 'Ordered Product Sales'."
            )
            return

        merged, _added, _updated = _merge_historical(cur.get("actual", []), rows)
        cur["actual"] = merged

        resueltas = _resolve_partial(merged)
        n = len(resueltas)
        msg = (
            f"✓ {n} mes{'es' if n != 1 else ''} con datos reales "
            f"cargado{'s' if n != 1 else ''}."
        )
        en_curso = [r["date"] for r in resueltas if r["partial"] is True]
        if en_curso:
            ultimo = en_curso[-1]
            nombre = f"{_MONTHS_FULL[int(ultimo[5:7]) - 1]} {ultimo[:4]}"
            msg += (
                f" {nombre} todavía está en curso: es un mes incompleto y se marca "
                f"con punto hueco en los gráficos."
            )
        st.success(msg)

        # Refresco tras el merge — UNA sola vez por archivo, nunca en loop.
        #
        # El `file_uploader` RETIENE el archivo entre reruns: un `st.rerun()`
        # desnudo acá vuelve a entrar por este mismo camino (parsea, mergea,
        # success) y dispara otro rerun — loop infinito. Por eso el guard: se
        # firma el archivo ya procesado en session_state y el rerun sale sólo
        # cuando la firma cambia (archivo nuevo o corregido).
        sig = (uploaded.name, len(data))
        k_sig = _k_actual_sig(cur)
        if st.session_state.get(k_sig) != sig:
            st.session_state[k_sig] = sig
            st.rerun()


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


# ─────────────────────────────────────────────────────────────────────────────
# FASE 4 — UI editable del forecast (por-cuenta)
# ─────────────────────────────────────────────────────────────────────────────
#
# Port de renderForecast (HTML L2064) + renderForecastSummary (L2193) + los
# controles de generación (HTML L794-817, handler en L5914-5927).
#
# Diseño F4:
#   - Helper PURO `_apply_forecast_edits(forecast_rows, edited_df)`: testeable
#     sin runtime Streamlit, aplica overrides y llama `recompute_forecast_row`
#     fila por fila.
#   - Helper PURO `_build_forecast_summary_cards(forecast, currency)`: port
#     de renderForecastSummary L2193, devuelve lista de 8 cards.
#   - Controles de generación: patrón F1 (sin `key=` + `value=`/`index=` juntos
#     — anti-patrón Streamlit 1.43). Usamos buffer mutable en session_state
#     `_K_FC_BUF` para persistir entre reruns SIN `key=` en widget.
#   - Forecast table: `st.data_editor` con `key=`, SIN `value=` (data_editor no
#     tiene value=). column_config marca read-only los campos computados.
#   - Recompute reactivo: mismo patrón que `_apply_history_edits` (F2): leemos
#     el df editado, mutamos in-place `cur["forecast"]`, `st.rerun()`.
#   - None handling: el data_editor con NumberColumn tolera None nativamente,
#     pero al LEER ediciones pandas devuelve NaN — normalizamos a None vía
#     `_value_or_none()`.
#
# NO se activa persistencia: el forecast vive en session_state (`cur["forecast"]`)
# durante F4. La persistencia llega en F5+ (junto con snapshots).

_K_FC_BUF = f"{_STATE_PREFIX}fc_buf"

# Defaults de los controles (fiel al HTML L796/799/803/808).
_FC_DEFAULTS = {
    "horizon": 3,       # 1..12
    "momWindow": 3,     # 1..12
    "blend": 50,        # 0..100 (% MoM, resto YoY)
    "useSeasonality": False,
}


def _value_or_none(v: Any) -> Optional[float]:
    """Normaliza valor del data_editor a None o float.

    pandas devuelve NaN cuando el AM deja una NumberColumn vacía. '' y None
    también pueden aparecer en runtime. Cualquiera de los tres → None.
    Numérico válido → float.
    """
    if v is None:
        return None
    if isinstance(v, str) and v.strip() == "":
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        return float(v)
    except (ValueError, TypeError):
        return None


def _apply_forecast_edits(
    forecast_rows: list[dict],
    edited_df: pd.DataFrame,
) -> int:
    """Helper PURO: aplica ediciones del data_editor al forecast y recomputa.

    Para cada fila editada:
        1. Lee los 7 overrides editables (manualRevenue, manualAOV,
           manualSessions, spend, acosTarget, tacosTarget, stockAvailability).
        2. Los normaliza con `_value_or_none` (NaN/''/None → None).
        3. Asigna al dict `forecast_rows[idx]`.
        4. Llama `recompute_forecast_row(f)` que muta in-place los campos
           computados (revenue, units, aov, sessions, cvr, ventasPPC, acos,
           tacos, pctVtasPPC, salesVelocity, availability) según las reglas
           del HTML (overrides Auto, availability clamp, tacosTarget driving
           spend, etc.).

    NO toca Streamlit. Recibe forecast_rows como lista mutable (la ref viva
    de `cur["forecast"]`) y el df editado. Devuelve la cantidad de filas
    procesadas.

    Args:
        forecast_rows: lista mutable de dicts forecast (será modificada).
        edited_df: DataFrame devuelto por st.data_editor con columna oculta
            `_idx` que mapea de vuelta al índice de forecast_rows.

    Returns:
        Cantidad de filas escritas.
    """
    if edited_df is None or edited_df.empty:
        return 0
    written = 0
    for _, row in edited_df.iterrows():
        try:
            idx = int(row["_idx"])
        except (ValueError, KeyError, TypeError):
            continue
        if not (0 <= idx < len(forecast_rows)):
            continue
        f = forecast_rows[idx]
        # Overrides editables — todos pasan por _value_or_none para normalizar.
        f["manualRevenue"] = _value_or_none(row.get("manualRevenue"))
        f["manualAOV"] = _value_or_none(row.get("manualAOV"))
        f["manualSessions"] = _value_or_none(row.get("manualSessions"))
        # acosTarget: si el AM lo borra, default 30 (consistencia con HTML L1669).
        acos_val = _value_or_none(row.get("acosTarget"))
        f["acosTarget"] = acos_val if acos_val is not None else 30.0
        # tacosTarget: None es válido y semántico ("no usar TACOS driving spend").
        f["tacosTarget"] = _value_or_none(row.get("tacosTarget"))
        # spend: si tacosTarget set, recompute lo SOBREESCRIBIRÁ (HTML L1903);
        # si no, este es el valor manual del AM. None → 0 vía _js_number.
        spend_val = _value_or_none(row.get("spend"))
        f["spend"] = spend_val if spend_val is not None else 0
        # stockAvailability: None → recompute usa default 100 (HTML L1888).
        f["stockAvailability"] = _value_or_none(row.get("stockAvailability"))
        recompute_forecast_row(f)
        written += 1
    return written


def _build_forecast_summary_cards(
    forecast: list[dict], currency: str = "USD",
) -> list[dict]:
    """Helper PURO: port de renderForecastSummary L2193.

    Calcula 8 totales/promedios del forecast y devuelve cards en el formato
    que consume `kpi_card`: {label, value}.

    Fórmulas (fieles al HTML L2193-2210):
        - Revenue total = sum(f.revenue)
        - Units totales = sum(f.units)
        - Sessions totales = sum(f.sessions)
        - Spend total = sum(f.spend)
        - Ventas PPC totales = sum(f.ventasPPC)
        - ACOS prom = spend / max(1, ventasPPC) * 100
        - TACOS prom = spend / max(1, revenue) * 100
        - AOV prom = revenue / max(1, units)

    `max(1, x)` evita div/0 cuando los totales son 0 (mismo guard del HTML).

    Args:
        forecast: lista de forecast rows (post-recompute).
        currency: símbolo de moneda para el format.

    Returns:
        Lista de 8 dicts {label, value}; cada `value` ya viene formateado
        como string listo para mostrar.
    """
    if not forecast:
        return []
    totals = {"revenue": 0.0, "units": 0.0, "sessions": 0.0,
              "spend": 0.0, "ventasPPC": 0.0}
    for f in forecast:
        totals["revenue"] += _js_number(f.get("revenue"))
        totals["units"] += _js_number(f.get("units"))
        totals["sessions"] += _js_number(f.get("sessions"))
        totals["spend"] += _js_number(f.get("spend"))
        totals["ventasPPC"] += _js_number(f.get("ventasPPC"))

    acos_prom = totals["spend"] / max(1.0, totals["ventasPPC"]) * 100.0
    tacos_prom = totals["spend"] / max(1.0, totals["revenue"]) * 100.0
    aov_prom = totals["revenue"] / max(1.0, totals["units"])

    return [
        {"label": "Revenue total", "value": _fmt_currency(totals["revenue"], currency)},
        {"label": "Units totales", "value": _fmt_num(totals["units"])},
        {"label": "Sessions totales", "value": _fmt_num(totals["sessions"])},
        {"label": "Spend total", "value": _fmt_currency(totals["spend"], currency)},
        {"label": "Ventas PPC totales", "value": _fmt_currency(totals["ventasPPC"], currency)},
        {"label": "ACOS prom.", "value": _fmt_pct(acos_prom, 1)},
        {"label": "TACOS prom.", "value": _fmt_pct(tacos_prom, 1)},
        {"label": "AOV prom.", "value": _fmt_currency(aov_prom, currency, dec=2)},
    ]


def _build_forecast_df(forecast: list[dict]) -> pd.DataFrame:
    """Construye el DataFrame para `st.data_editor` del forecast.

    Columnas (en orden):
        _idx (oculta) | Mes | manualRevenue | manualAOV | manualSessions |
        spend | acosTarget | tacosTarget | stockAvailability |
        revenue | aov | units | sessions | cvr | salesVelocity |
        ventasPPC | acos | tacos | pctVtasPPC

    Editables (sin disabled en column_config): los 7 overrides.
    Read-only: las 10 computadas.

    Notas Arrow-safe:
        - manual* y tacosTarget y stockAvailability: pueden ser None — se dejan
          como None puro (NumberColumn lo tolera y muestra celda vacía).
          NO usar '' (mezclar None y float rompe Arrow en NumberColumn).
        - spend, acosTarget: SIEMPRE numéricos (la generación los inicializa
          con int/float; recompute los mantiene numéricos).
    """
    if not forecast:
        return pd.DataFrame(columns=[
            "_idx", "Mes",
            "manualRevenue", "manualAOV", "manualSessions",
            "spend", "acosTarget", "tacosTarget", "stockAvailability",
            "revenue", "aov", "units", "sessions", "cvr", "salesVelocity",
            "ventasPPC", "acos", "tacos", "pctVtasPPC",
        ])

    rows = []
    for i, f in enumerate(forecast):
        try:
            year, month, _ = f["date"].split("-")
            mes_label = f"{_MONTHS_FULL[int(month) - 1]} {year}"
        except (ValueError, KeyError, IndexError):
            mes_label = f.get("date", "")

        rows.append({
            "_idx": i,
            "Mes": mes_label,
            # Editables (overrides — None puro, NumberColumn maneja).
            "manualRevenue": f.get("manualRevenue"),
            "manualAOV": f.get("manualAOV"),
            "manualSessions": f.get("manualSessions"),
            "spend": _js_number(f.get("spend")),
            "acosTarget": _js_number(f.get("acosTarget")),
            "tacosTarget": f.get("tacosTarget"),
            "stockAvailability": f.get("stockAvailability"),
            # Read-only (computadas por recompute).
            "revenue": _js_number(f.get("revenue")),
            "aov": _js_number(f.get("aov")),
            "units": _js_number(f.get("units")),
            "sessions": _js_number(f.get("sessions")),
            "cvr": _js_number(f.get("cvr")),
            "salesVelocity": _js_number(f.get("salesVelocity")),
            "ventasPPC": _js_number(f.get("ventasPPC")),
            "acos": _js_number(f.get("acos")),
            "tacos": _js_number(f.get("tacos")),
            "pctVtasPPC": _js_number(f.get("pctVtasPPC")),
        })
    return pd.DataFrame(rows)


def _reset_forecast_overrides(cur: dict) -> int:
    """Resetea los overrides manuales de TODAS las filas del forecast del cliente.

    Fiel al botón ↺ del HTML L2179-2189 pero aplicado global (HTML lo hace
    por-fila — global es el patrón razonable para Streamlit donde el rerun
    completo no permite triggers per-cell limpios).

    Para cada fila: manualRevenue / manualAOV / manualSessions / tacosTarget
    a None, luego `recompute_forecast_row` que refleja el reset en las
    computadas (revenue cae a revenueAuto, etc.).

    NO toca spend ni acosTarget (esos son inputs PROPIOS del AM, no overrides
    sobre el cálculo automático — fiel al HTML que solo limpia los 4 manuales).

    Args:
        cur: dict del cliente activo (será mutado).

    Returns:
        Cantidad de filas reseteadas (= len(forecast)).
    """
    forecast = cur.get("forecast", [])
    for f in forecast:
        f["manualRevenue"] = None
        f["manualAOV"] = None
        f["manualSessions"] = None
        f["tacosTarget"] = None
        recompute_forecast_row(f)
    return len(forecast)


# ─────────────────────────────────────────────────────────────────────────────
# Snapshots de forecast nombrados — funciones PURAS
# ─────────────────────────────────────────────────────────────────────────────
#
# El AM genera un forecast, lo guarda con un nombre de estrategia ("Agresivo",
# "Conservador"…) y puede tener VARIOS por cliente sin que uno pise al otro.
# Viven en `cur["snapshots"]`, o sea DENTRO del dict del cliente: la tabla
# `forecast_clients` guarda el cliente entero como JSON, así que persisten solos
# con `_try_persist()` — cero DDL, cero tabla nueva.
#
# Todo lo que se guarda pasa por `copy.deepcopy`: si se guardara la referencia
# viva, editar un override en la tabla del forecast le cambiaría los números al
# snapshot ya guardado, que es exactamente lo que el AM quiere evitar.


def _save_forecast_snapshot(cur: dict, name: str, opts: dict) -> Optional[dict]:
    """Guarda el forecast actual del cliente como snapshot nombrado.

    Args:
        cur: dict del cliente activo (será mutado — se appendea a `snapshots`).
        name: nombre libre del AM (ej. "Agresivo"). Vacío → None.
        opts: los opts con que se generó el forecast (horizon/momWindow/blend/
            useSeasonality). Se deep-copea para que el buffer vivo no lo mute.

    Returns:
        El snapshot creado, o None si el nombre está vacío o no hay forecast
        que guardar (un snapshot vacío no le sirve a nadie).
    """
    clean_name = (name or "").strip()
    if not clean_name:
        return None
    forecast = cur.get("forecast") or []
    if not forecast:
        return None

    created_at = date.today().isoformat()
    base_id = f"{_cliente_slug(clean_name)}-{created_at}"
    existing = {s.get("id") for s in cur.get("snapshots", [])}
    snap_id = base_id
    n = 2
    while snap_id in existing:
        snap_id = f"{base_id}-{n}"
        n += 1

    snap = {
        "id": snap_id,
        "name": clean_name,
        "created_at": created_at,
        "opts": copy.deepcopy(opts or {}),
        "forecast": copy.deepcopy(forecast),
        "seasonality": copy.deepcopy(
            cur.get("seasonality") or {"enabled": False, "indices": [1.0] * 12}
        ),
    }
    cur.setdefault("snapshots", []).append(snap)
    return snap


def _list_forecast_snapshots(cur: dict) -> list[dict]:
    """Snapshots del cliente, en orden de creación (el más viejo primero)."""
    return cur.get("snapshots", [])


def _load_forecast_snapshot(cur: dict, snapshot_id: str) -> bool:
    """Restaura un snapshot al forecast ACTIVO del cliente.

    Pisa `cur["forecast"]` y `cur["seasonality"]` con copias del snapshot — el
    snapshot queda intacto y se puede volver a cargar las veces que haga falta.

    Returns:
        True si el id existía y se restauró; False si no se encontró.
    """
    for s in cur.get("snapshots", []):
        if s.get("id") == snapshot_id:
            cur["forecast"] = copy.deepcopy(s.get("forecast") or [])
            cur["seasonality"] = copy.deepcopy(
                s.get("seasonality") or {"enabled": False, "indices": [1.0] * 12}
            )
            return True
    return False


def _delete_forecast_snapshot(cur: dict, snapshot_id: str) -> bool:
    """Borra un snapshot por id. Returns True si borró algo."""
    snaps = cur.get("snapshots", [])
    keep = [s for s in snaps if s.get("id") != snapshot_id]
    if len(keep) == len(snaps):
        return False
    cur["snapshots"] = keep
    return True


def _build_snapshot_comparison_df(cur: dict, snapshot_ids: list) -> pd.DataFrame:
    """Tabla comparativa: una fila por snapshot, los 8 totales como columnas.

    Reusa `_build_forecast_summary_cards` — los mismos números que el AM ve en
    "Resumen de la proyección", sin recalcular nada. Los valores vienen ya
    formateados como string (Arrow-safe por construcción).

    Args:
        cur: dict del cliente activo.
        snapshot_ids: ids a comparar; los que no existan se ignoran.

    Returns:
        DataFrame con columna "Snapshot" + las 8 de totales. Vacío si ningún id
        matcheó.
    """
    currency = cur.get("currency", "USD")
    by_id = {s.get("id"): s for s in cur.get("snapshots", [])}

    rows: list[dict] = []
    for sid in snapshot_ids:
        snap = by_id.get(sid)
        if snap is None:
            continue
        row = {"Snapshot": snap.get("name", "")}
        for card in _build_forecast_summary_cards(snap.get("forecast") or [], currency):
            row[card["label"]] = card["value"]
        rows.append(row)

    if not rows:
        return pd.DataFrame(columns=["Snapshot"])
    df = pd.DataFrame(rows)
    return df.where(pd.notna(df), "")


def _ensure_fc_buf(state: Optional[Any] = None) -> dict:
    """Devuelve el buffer de los controles de generación, inicializándolo si no existe.

    Patrón "Plan D" (buffer mutable) — permite que widgets sin `key=` persistan
    sus valores entre reruns leyendo `value=buf[field]`. Evita el anti-patrón
    `key=` + `value=` juntos (que Streamlit 1.43 rechaza).
    """
    if state is None:
        state = st.session_state
    if _K_FC_BUF not in state:
        state[_K_FC_BUF] = dict(_FC_DEFAULTS)
    return state[_K_FC_BUF]


def _render_forecast_controls(cur: dict) -> Optional[dict]:
    """Render de los 4 controles + botón "Generar forecast" (port HTML L794-817).

    Args:
        cur: dict del cliente activo.

    Returns:
        opts dict si el AM hizo click en "Generar forecast", sino None.
        El caller decide si invocar `_run_forecast_for_active_client(opts)`.
    """
    st.markdown("##### Generar proyección")
    st.caption(
        "El motor combina crecimiento MoM y YoY (cuando aplica), aplica "
        "estacionalidad si está activa, y deja los campos clave editables abajo."
    )
    buf = _ensure_fc_buf()
    # E1: tope de la ventana MoM = meses de historial cargado (mín. 12). Evita
    # que el AM pida más meses de los que existen — _avg_mom_growth no tendría
    # datos — pero permite usar todo el historial cuando supera los 12 meses.
    _mom_max = max(12, len(cur.get("historical", [])))

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        # NO `key=` + `value=` juntos (anti-patrón). Leemos del buffer.
        new_horizon = st.number_input(
            "Meses a proyectar",
            min_value=1, max_value=12, step=1,
            value=int(buf.get("horizon", 3)),
        )
        buf["horizon"] = int(new_horizon)
    with col2:
        new_mom = st.number_input(
            "Ventana MoM (meses)",
            min_value=1, max_value=_mom_max, step=1,
            # El buffer es GLOBAL (no por cliente) y no se resetea al cambiar de
            # cliente: sin este clamp, venir de un cliente con historial largo
            # (momWindow 20) a uno corto (_mom_max 12) hace que Streamlit levante
            # StreamlitValueAboveMaxError y se caiga la página.
            value=min(int(buf.get("momWindow", 3)), _mom_max),
        )
        buf["momWindow"] = int(new_mom)
    with col3:
        new_blend = st.slider(
            "Mezcla MoM ↔ YoY (%MoM)",
            min_value=0, max_value=100, step=1,
            value=int(buf.get("blend", 50)),
            help=f"{int(buf.get('blend', 50))}% MoM · "
                 f"{100 - int(buf.get('blend', 50))}% YoY",
        )
        buf["blend"] = int(new_blend)
    with col4:
        new_season = st.checkbox(
            "Aplicar estacionalidad",
            value=bool(buf.get("useSeasonality", False)),
            help="Usa los índices del cliente (Sí, usar índices).",
        )
        buf["useSeasonality"] = bool(new_season)

    historical = cur.get("historical", [])
    insufficient = len(historical) < 2

    btn_col, info_col = st.columns([1, 3])
    with btn_col:
        clicked = st.button(
            "Generar forecast",
            key=f"rf_fc_gen_btn_{cur['id']}",
            type="primary",
            disabled=insufficient,
            help="Calcula el forecast usando los parámetros de arriba.",
        )
    with info_col:
        forecast = cur.get("forecast", [])
        if forecast:
            last_hist = historical[-1] if historical else None
            base_iso = last_hist["date"] if last_hist else "—"
            st.caption(
                f"{len(forecast)} meses generados a partir de {base_iso}."
            )
        elif insufficient:
            st.caption(
                "⚠️ Cargá al menos 2 meses de historial para generar el forecast."
            )

    if clicked and not insufficient:
        return dict(buf)
    return None


def _render_forecast_table(cur: dict) -> None:
    """Render del data_editor del forecast (port HTML L2064 — cards → tabla).

    Diferencia con el HTML: el HTML usa cards por mes (con inputs sueltos +
    output grid). Streamlit no tiene un widget equivalente de "card editable",
    así que portamos a un data_editor: las filas son los meses, las columnas
    son inputs (editables) + outputs (read-only). Funcionalmente equivalente.
    """
    forecast = cur.get("forecast", [])
    if not forecast:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:1.5rem;"
            "text-align:center;background:#FFF3E0;'>"
            "<div style='font-size:1.2rem;'>≋</div>"
            "<div style='font-weight:600;margin-top:0.4rem;'>Aún no hay proyección</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.2rem;'>"
            "Configurá los parámetros de arriba y hacé clic en \"Generar forecast\".</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown("##### Forecast editable")
    st.caption(
        "Editá overrides (manualRevenue / manualAOV / manualSessions / Spend / "
        "ACOS target / TACOS target / Stock Availability) — los outputs "
        "(revenue, units, AOV, sessions, CVR, ventas PPC, ACOS, TACOS) se "
        "recalculan al instante. "
        "**Tip:** si seteás TACOS target, el Spend lo maneja el cálculo "
        "(TACOS × Revenue) y tu input manual de Spend se sobreescribe."
    )

    df = _build_forecast_df(forecast)

    # data_editor con column_config: editables sin disabled; computadas disabled.
    edited = st.data_editor(
        df,
        key=f"rf_fc_editor_{cur['id']}",
        hide_index=True,
        use_container_width=True,
        column_config={
            "_idx": None,
            "Mes": st.column_config.TextColumn("Mes", disabled=True),
            # Editables.
            "manualRevenue": st.column_config.NumberColumn(
                "Revenue (override)", format="%.2f",
                help="Vacío = usa Auto del motor.",
            ),
            "manualAOV": st.column_config.NumberColumn(
                "AOV (override)", format="%.2f",
                help="Vacío = usa Auto del motor.",
            ),
            "manualSessions": st.column_config.NumberColumn(
                "Sessions (override)", format="%d",
                help="Vacío = usa Auto del motor.",
            ),
            "spend": st.column_config.NumberColumn(
                "Spend", format="%.2f",
                help="Inversión Ads (USD). Si TACOS target está set, se "
                     "sobreescribe con TACOS×Revenue al recomputar.",
            ),
            "acosTarget": st.column_config.NumberColumn(
                "ACOS target %", format="%.1f",
                help="ACOS objetivo del forecast.",
            ),
            "tacosTarget": st.column_config.NumberColumn(
                "TACOS target %", format="%.1f",
                help="Si está set, el spend se calcula como TACOS×Revenue.",
            ),
            "stockAvailability": st.column_config.NumberColumn(
                "Stock Avail. %", format="%.1f", min_value=0.0, max_value=100.0,
                help="Disponibilidad de stock (0-100). Escala el revenue del mes.",
            ),
            # Read-only.
            "revenue": st.column_config.NumberColumn("Revenue", format="%.2f", disabled=True),
            "aov": st.column_config.NumberColumn("AOV", format="%.2f", disabled=True),
            "units": st.column_config.NumberColumn("Units", format="%d", disabled=True),
            "sessions": st.column_config.NumberColumn("Sessions", format="%d", disabled=True),
            "cvr": st.column_config.NumberColumn("CVR%", format="%.2f", disabled=True),
            "salesVelocity": st.column_config.NumberColumn(
                "Sales Velocity", format="%.1f", disabled=True,
                help="Units / días del mes.",
            ),
            "ventasPPC": st.column_config.NumberColumn("Ventas PPC", format="%.2f", disabled=True),
            "acos": st.column_config.NumberColumn("ACOS%", format="%.1f", disabled=True),
            "tacos": st.column_config.NumberColumn("TACOS%", format="%.1f", disabled=True),
            "pctVtasPPC": st.column_config.NumberColumn("% Vtas PPC", format="%.1f", disabled=True),
        },
    )

    # Reactividad: mismo patrón que F2 (_apply_history_edits + rerun).
    if edited is not None and not edited.equals(df):
        _apply_forecast_edits(cur["forecast"], edited)
        st.rerun()


def _render_forecast_summary(cur: dict) -> None:
    """Render de los kpi_cards del summary (port HTML L2193 totals)."""
    forecast = cur.get("forecast", [])
    if not forecast:
        return
    st.markdown("##### Resumen de la proyección")
    st.caption("Totales y promedios para el periodo proyectado.")
    cards = _build_forecast_summary_cards(forecast, cur.get("currency", "USD"))
    for i in range(0, len(cards), 4):
        row = cards[i:i + 4]
        cols = st.columns(4)
        for col, card in zip(cols, row):
            with col:
                st.markdown(
                    kpi_card(card["label"], card["value"], delta=None, delta_good=True),
                    unsafe_allow_html=True,
                )


# ─────────────────────────────────────────────────────────────────────────────
# FASE 5 — Estacionalidad UI + Export CSV
# ─────────────────────────────────────────────────────────────────────────────
#
# F5 = MVP close: (1) UI de estacionalidad (toggle + 12 índices editables +
# auto-detect) y (2) export CSV del forecast a disco.
#
# NO regenera el forecast automático al cambiar seasonality — hacerlo pisaría
# los overrides manuales del AM en F4 sin aviso. En cambio, F5 muta
# cur["seasonality"] y muestra un aviso ("regenera desde arriba para aplicar").
# El botón "Generar forecast" de F4 (con su checkbox useSeasonality) es el
# punto de aplicación autorizado — el AM acepta ahí el trade-off.
#
# Fuente HTML: renderSeasonality (L2243), autoDetectSeasonality (L2266 —
# ya portado en F3 como `auto_detect_seasonality`), exportForecastCSV (L2858).
# Extensión pedida vs HTML: agregar 6 columnas de overrides manuales del AM
# (Manual Revenue, Manual AOV, Manual Sessions, ACOS Target%, TACOS Target%,
# Stock Availability%) al final del CSV. El HTML no las exporta; usuario
# las quiere para auditoría.

_SEASONALITY_HELP = (
    "Los índices multiplican el revenue base del mes correspondiente. "
    "1.00 = neutro. >1.05 (verde) = mes fuerte; <0.95 (rojo) = mes flojo. "
    "El botón 'Auto-detectar' requiere al menos 12 meses de historial."
)


def _build_forecast_csv(forecast: list[dict], cliente_name: str) -> str:
    """Port de exportForecastCSV L2858, con extensión de overrides manuales.

    Formato:
        - Header 12 cols HTML + 6 cols overrides.
        - Formatos numéricos fielmente portados del HTML:
            revenue/aov/salesVelocity/spend/ventasPPC/acos/tacos/pctVtasPPC → 2 dec.
            cvr → 2 dec (HTML L2870 `f.cvr.toFixed(2)`).
            units/sessions → 0 dec (redondeo half-up implícito por int()).
        - Overrides (manualRevenue/AOV/Sessions/acosTarget/tacosTarget/
          stockAvailability): vacío si None/absent, `.2f` si set.
        - Line endings LF (fiel al HTML `\\n`).

    NOTA (fidelidad JS): `toFixed(0)` en JS redondea half-away-from-zero, pero
    la diferencia con `int(round(x))` es negligible acá porque `units` y
    `sessions` vienen ya como floats grandes bien definidos. Preservamos
    `_round_half_up_int` para consistencia con el motor.

    Args:
        forecast: lista de forecast rows (mismo shape que cur["forecast"]).
                  Puede ser [] — devuelve solo el header.
        cliente_name: nombre del cliente (para header comment o metadatos
                      futuros; hoy no se inyecta en el body).

    Returns:
        CSV como string, encoding UTF-8. Sin BOM (Excel lo lee OK).
    """
    header = [
        # 12 columnas HTML (orden verbatim).
        "Date", "Revenue", "AOV", "Units", "Sales Velocity",
        "Sessions", "CVR%", "Spend", "Ventas PPC",
        "ACOS%", "TACOS%", "% Vtas PPC",
        # 6 columnas extendidas (overrides manuales del AM en F4).
        "Manual Revenue", "Manual AOV", "Manual Sessions",
        "ACOS Target%", "TACOS Target%", "Stock Availability%",
    ]
    lines = [",".join(header)]

    for f in forecast:
        def _fmt_opt(v: Any) -> str:
            """Override → '.2f' si set (truthy-present), '' si None/absent."""
            if not _js_truthy_present(v):
                return ""
            return f"{_js_number(v):.2f}"

        row = [
            f.get("date", ""),
            f"{_js_number(f.get('revenue')):.2f}",
            f"{_js_number(f.get('aov')):.2f}",
            f"{_round_half_up_int(_js_number(f.get('units')))}",
            f"{_js_number(f.get('salesVelocity')):.2f}",
            f"{_round_half_up_int(_js_number(f.get('sessions')))}",
            f"{_js_number(f.get('cvr')):.2f}",
            f"{_js_number(f.get('spend')):.2f}",
            f"{_js_number(f.get('ventasPPC')):.2f}",
            f"{_js_number(f.get('acos')):.2f}",
            f"{_js_number(f.get('tacos')):.2f}",
            f"{_js_number(f.get('pctVtasPPC')):.2f}",
            # Overrides — vacío o formateado.
            _fmt_opt(f.get("manualRevenue")),
            _fmt_opt(f.get("manualAOV")),
            _fmt_opt(f.get("manualSessions")),
            _fmt_opt(f.get("acosTarget")),
            _fmt_opt(f.get("tacosTarget")),
            _fmt_opt(f.get("stockAvailability")),
        ]
        lines.append(",".join(row))

    return "\n".join(lines)


def _cliente_slug(name: str) -> str:
    """Normaliza el nombre para filename: lower + espacios→'_' + strip especial.

    Fiel al espíritu del HTML L2882 `state.account.name || 'cuenta'` pero
    filesystem-safe. Ejemplos:
        'Dermaglos'         → 'dermaglos'
        'Love To Dream MX'  → 'love_to_dream_mx'
        ''                  → 'cuenta'
    """
    if not name:
        return "cuenta"
    slug = re.sub(r"[^\w\s-]", "", name, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[\s-]+", "_", slug)
    return slug or "cuenta"


def _apply_seasonality_edits(
    seasonality: dict,
    edited_df: pd.DataFrame,
) -> int:
    """Aplica ediciones del data_editor de estacionalidad al dict del cliente.

    Para cada fila (12 meses): lee "Índice" del df editado, normaliza NaN/None
    con `_js_number` (que ya trata None/NaN/'' como 0) y REEMPLAZA por 1.0
    cuando el resultado es 0 (fiel al `|| 1` del HTML L2259).

    NO clampea a [min, max] — el column_config del data_editor ya limita al
    editar en UI; los tests operan sobre dfs libres y esperan clamp del widget
    (no de la lógica pura).

    Args:
        seasonality: dict {enabled, indices[12]} — será mutado in-place.
        edited_df: DataFrame con columnas ["Mes", "Índice"] (12 filas).

    Returns:
        Cantidad de índices actualizados (esperado: 12).
    """
    if edited_df is None or edited_df.empty:
        return 0
    indices = seasonality.get("indices", [1.0] * 12)
    if len(indices) != 12:
        indices = [1.0] * 12
    # Iteración por índice de fila (0-11 = meses Ene-Dic).
    written = 0
    for i, (_, row) in enumerate(edited_df.iterrows()):
        if i >= 12:
            break
        raw = row.get("Índice")
        v = _js_number(raw)
        # Fiel al HTML L2259 `|| 1`: vacío/0 → 1.
        indices[i] = float(v) if v else 1.0
        written += 1
    seasonality["indices"] = indices
    return written


def _render_seasonality_section(cur: dict) -> None:
    """Render de la sección "Estacionalidad" (port HTML L2243).

    Layout:
        1. Toggle "Aplicar estacionalidad" (mutación directa a
           cur["seasonality"]["enabled"]).
        2. Botón "Auto-detectar" (llama `auto_detect_seasonality`, warning si
           <12 meses).
        3. `st.data_editor` con 12 filas: columna "Mes" read-only, "Índice"
           editable (min 0.1, max 3.0, step 0.01).
        4. Info: "para aplicar, regenerá el forecast arriba".

    NO llama `_run_forecast_for_active_client` — cambiar seasonality no
    regenera automático (pisaría overrides F4). El AM regenera desde el
    botón F4 cuando quiere aplicar.
    """
    st.divider()
    st.markdown("### 📅 Estacionalidad")
    st.caption(_SEASONALITY_HELP)

    seas = cur.get("seasonality") or {"enabled": False, "indices": [1.0] * 12}
    # Guard: si algún flujo antiguo dejó indices con longitud distinta.
    if len(seas.get("indices") or []) != 12:
        seas["indices"] = [1.0] * 12
    cur["seasonality"] = seas

    # (1) Toggle enabled. NO `key=`+`value=` juntos: leemos return.
    new_enabled = st.checkbox(
        "Aplicar estacionalidad",
        value=bool(seas.get("enabled", False)),
        help="Cuando está activo, el motor multiplica el revenue base por el "
             "índice del mes al generar el forecast. Requiere marcar también "
             "'Aplicar estacionalidad' en los controles de arriba y regenerar.",
    )
    if bool(new_enabled) != bool(seas.get("enabled", False)):
        seas["enabled"] = bool(new_enabled)
        # Sin regenerado automático — solo mutación.
        st.rerun()

    # (2) Botón auto-detectar.
    col_btn, col_msg = st.columns([1, 3])
    with col_btn:
        auto_clicked = st.button(
            "🔍 Auto-detectar",
            key=f"rf_seas_auto_btn_{cur['id']}",
            help="Calcula los 12 índices a partir del promedio de revenue "
                 "por mes-de-año en el histórico. Requiere >=12 meses.",
        )
    with col_msg:
        historical = cur.get("historical", [])
        if len(historical) < 12:
            st.caption(
                f"⚠️ {len(historical)} meses cargados. Auto-detectar requiere "
                "12+ meses. Podés editar los índices manualmente abajo."
            )
    if auto_clicked:
        result = auto_detect_seasonality(historical)
        if result is None:
            st.warning(
                "Se necesitan al menos 12 meses de historial para auto-detectar."
            )
        else:
            cur["seasonality"] = result
            st.success(
                "✓ Índices calculados desde el histórico. Regenerá el forecast "
                "arriba para aplicarlos."
            )
            st.rerun()

    # (3) Editor de los 12 índices. Consistente con F4 (data_editor).
    df_seas = pd.DataFrame({
        "Mes": _MONTHS_FULL[:12],
        "Índice": [float(v) if v else 1.0 for v in seas["indices"]],
    })
    edited = st.data_editor(
        df_seas,
        key=f"rf_seas_editor_{cur['id']}",
        hide_index=True,
        num_rows="fixed",
        column_config={
            "Mes": st.column_config.TextColumn("Mes", disabled=True),
            "Índice": st.column_config.NumberColumn(
                "Índice",
                min_value=0.1,
                max_value=3.0,
                step=0.01,
                format="%.2f",
                help="1.00 = neutro. >1.05 mes fuerte, <0.95 mes flojo.",
            ),
        },
        use_container_width=True,
    )
    if edited is not None and not edited.equals(df_seas):
        _apply_seasonality_edits(seas, edited)
        st.info(
            "Índices actualizados en el estado del cliente. Regenerá el "
            "forecast arriba (con el checkbox 'Aplicar estacionalidad') "
            "para verlos aplicados."
        )
        st.rerun()

    # (4) Aviso persistente cuando la estacionalidad está activa pero el
    # forecast se generó sin ella (o viceversa). El "seasonality" por fila
    # del forecast refleja el sFactor aplicado en la última generación.
    forecast = cur.get("forecast", [])
    if forecast and seas.get("enabled"):
        # Sample: si TODAS las filas tienen seasonality == 1.0 pero el AM
        # activó la estacionalidad, es señal de que hay que regenerar.
        all_neutral = all(
            abs(_js_number(f.get("seasonality")) - 1.0) < 1e-9 for f in forecast
        )
        if all_neutral:
            st.caption(
                "ℹ️ La estacionalidad está activa pero el forecast actual se "
                "generó sin ella. Regenerá arriba para aplicarla."
            )


def _render_export_section(cur: dict) -> None:
    """Sección "Exportar" — download button del CSV del forecast (F5).

    Fiel al patrón M30: builder puro FUERA de render (`_build_forecast_csv`),
    render solo cablea el download button. Skipeado si no hay forecast.

    Filename: `forecast_{slug}_{YYYY-MM-DD}.csv` — fecha generada en RUNTIME
    (no import-time) para que rerun tras rerun refleje el día actual.
    """
    forecast = cur.get("forecast", [])
    if not forecast:
        return  # Sin forecast, no hay export.
    st.divider()
    st.markdown("### 📤 Exportar")
    st.caption(
        f"Descarga el forecast en CSV: {len(forecast)} meses proyectados "
        "con las 12 columnas del HTML original + 6 columnas de overrides "
        "manuales del AM (Manual Revenue/AOV/Sessions, ACOS/TACOS Target, "
        "Stock Availability)."
    )
    csv_str = _build_forecast_csv(forecast, cur.get("name", ""))
    fname = (
        f"forecast_{_cliente_slug(cur.get('name', ''))}_"
        f"{date.today().isoformat()}.csv"
    )
    st.download_button(
        label="⬇️ Descargar forecast CSV",
        data=csv_str.encode("utf-8"),
        file_name=fname,
        mime="text/csv",
        key=f"rf_export_csv_{cur['id']}",
        help=(
            "CSV UTF-8 sin BOM. Incluye todas las columnas del HTML original "
            "y las 6 columnas de overrides manuales al final."
        ),
    )

    # ── Reporte HTML (G6) — deliverable cliente-facing con los 7 charts ──
    # Corre DENTRO del guard `if not forecast: return` de arriba → acá el
    # forecast está garantizado. No se toca ese guard: un "Monthly Forecast
    # report" sin forecast no es un deliverable.
    st.markdown("#### Reporte HTML")
    st.caption(
        "Documento self-contained con los 7 gráficos interactivos, el resumen "
        "de la proyección y el detalle mes a mes. Respeta el toggle YoY y la "
        "selección del chart Custom de la sección Gráficas. Se abre en "
        "cualquier browser."
    )
    # Buffer keyless (gotcha 1.43.2: nunca key= + value= juntos). No se
    # persiste: la nota es por-descarga.
    note = st.text_area(
        "Nota para el cliente (opcional)",
        value="",
        placeholder="Contexto de la proyección, supuestos, próximos pasos…",
    )
    # RESPETA lo que el AM está viendo en Gráficas (G5): toggle YoY + selección
    # del chart Custom. `.get(..., default)` porque los buffers sólo se siembran
    # si la sección Gráficas llegó a renderizar.
    yoy = st.session_state.get(_K_CHARTS_YOY, True)
    custom = st.session_state.get(_K_CHARTS_CUSTOM, ["revenue"])
    # `actual` va CRUDO: `_build_export_html` resuelve el `partial` puertas
    # adentro (un solo punto de verdad, ver su docstring).
    html_str = _build_export_html(
        cur, note=note or "", show_yoy=yoy, custom_metrics=custom,
        actual_rows=cur.get("actual", []),
    )
    fname_html = (
        f"forecast_{_cliente_slug(cur.get('name', ''))}_"
        f"{date.today().isoformat()}.html"
    )
    st.download_button(
        label="📄 Descargar reporte HTML",
        data=html_str.encode("utf-8"),
        file_name=fname_html,
        mime="text/html",
        key=f"rf_export_html_{cur['id']}",
        help=(
            "Los gráficos se sirven desde el CDN de Plotly → el reporte pesa "
            "cientos de KB (no 24MB) pero necesita internet para dibujarlos."
        ),
    )


def _render_forecast_section(cur: dict) -> None:
    """Orquestador del bloque "Forecast" (F4): controles + tabla + summary + reset.

    Llamado desde `render()` DESPUÉS de `_render_history_table`. Si el AM no
    tiene historial, el botón se deshabilita y la tabla muestra empty state.
    """
    st.divider()
    st.markdown("### 📈 Forecast")

    opts = _render_forecast_controls(cur)
    if opts is not None:
        n = len(_run_forecast_for_active_client(opts))
        if n > 0:
            _try_persist()  # autosave: forecast recién generado
            st.success(f"✓ {n} meses de forecast generados.")
            st.rerun()
        else:
            st.warning("No se generó el forecast (sin historial o sin cliente activo).")

    st.markdown("")
    _render_forecast_table(cur)

    if cur.get("forecast"):
        st.markdown("")
        col_reset, _ = st.columns([1, 3])
        with col_reset:
            if st.button(
                "↺ Resetear overrides",
                key=f"rf_fc_reset_btn_{cur['id']}",
                help="Limpia manualRevenue/AOV/Sessions y tacosTarget de TODAS "
                     "las filas, y recalcula el forecast desde el motor.",
            ):
                n = _reset_forecast_overrides(cur)
                if n > 0:
                    st.success(f"✓ {n} filas reseteadas.")
                    st.rerun()
        st.markdown("")
        _render_forecast_summary(cur)
        _render_snapshots_section(cur)


def _render_snapshots_section(cur: dict) -> None:
    """Snapshots nombrados del forecast: guardar / cargar / borrar / comparar.

    Se llama al final de `_render_forecast_section`, sólo cuando hay forecast.
    Todo lo que muta se persiste con `_try_persist()` porque `cur["snapshots"]`
    viaja dentro del JSON del cliente.
    """
    st.divider()
    st.markdown("#### 📸 Snapshots de forecast")
    st.caption(
        "Guardá esta proyección con un nombre (ej. estrategia 'Agresivo' / "
        "'Normal') para comparar enfoques sin pisar el actual."
    )

    # ── a) Guardar ───────────────────────────────────────────────────────────
    name_key = f"rf_snap_name_{cur['id']}"
    col_name, col_save = st.columns([3, 1])
    with col_name:
        # Sin `value=` — key= + value= juntos es anti-patrón en 1.43.2.
        st.text_input(
            "Nombre / estrategia",
            key=name_key,
            placeholder="Agresivo · Normal · Conservador…",
        )
    with col_save:
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        if st.button(
            "💾 Guardar snapshot",
            key=f"rf_snap_save_btn_{cur['id']}",
            use_container_width=True,
        ):
            raw_name = (st.session_state.get(name_key) or "").strip()
            if not raw_name:
                st.warning("Poné un nombre para el snapshot.")
            else:
                snap = _save_forecast_snapshot(cur, raw_name, dict(_ensure_fc_buf()))
                if snap is None:
                    st.warning("Generá un forecast antes de guardar snapshot.")
                else:
                    _try_persist()
                    st.success(f"Snapshot «{snap['name']}» guardado.")
                    st.rerun()

    # ── b) Lista ─────────────────────────────────────────────────────────────
    snaps = _list_forecast_snapshots(cur)
    if not snaps:
        st.caption("Todavía no hay snapshots guardados para este cliente.")
        return

    st.markdown("")
    for s in snaps:
        c_name, c_date, c_load, c_del = st.columns([3, 2, 1, 1])
        with c_name:
            st.markdown(f"**{s.get('name', '')}**")
        with c_date:
            st.caption(f"{s.get('created_at', '')} · {len(s.get('forecast', []))} meses")
        with c_load:
            if st.button(
                "Cargar",
                key=f"rf_snap_load_{cur['id']}_{s['id']}",
                use_container_width=True,
                help="Pisa el forecast y la estacionalidad actuales con los del snapshot.",
            ):
                if _load_forecast_snapshot(cur, s["id"]):
                    _try_persist()
                    st.success(f"Snapshot «{s.get('name', '')}» cargado.")
                    st.rerun()
        with c_del:
            if st.button(
                "🗑️",
                key=f"rf_snap_del_{cur['id']}_{s['id']}",
                use_container_width=True,
                help="Borra este snapshot. No toca el forecast activo.",
            ):
                if _delete_forecast_snapshot(cur, s["id"]):
                    _try_persist()
                    st.rerun()

    # ── c) Comparar ──────────────────────────────────────────────────────────
    if len(snaps) < 2:
        return

    st.markdown("")
    labels = {s["id"]: s.get("name", "") for s in snaps}
    sel_ids = st.multiselect(
        "Comparar snapshots",
        [s["id"] for s in snaps],
        format_func=lambda sid: labels.get(sid, sid),
        key=f"rf_snap_cmp_{cur['id']}",
        help="Elegí 2 o más para ver sus totales lado a lado.",
    )
    if len(sel_ids) >= 2:
        st.dataframe(
            _build_snapshot_comparison_df(cur, sel_ids),
            hide_index=True,
            use_container_width=True,
        )


# ─────────────────────────────────────────────────────────────────────────────
# F6-G5 — Wiring UI de los 7 charts (tabs + st.pills + toggle YoY)
# ─────────────────────────────────────────────────────────────────────────────
#
# CERO lógica: pasa hist/forecast (del cliente activo) a los charts PUROS de
# G1-G4 y los muestra en tabs. Buffers keyless en session_state (gotcha 1.43.2:
# nunca key= + default=/value= juntos). El chart custom SIEMPRE se dibuja con el
# BUFFER (nunca con el return de st.pills) → deseleccionar el último chip se
# ignora silencioso, verbatim del HTML (`if (sel.length === 0) return;`).

_K_CHARTS_YOY = f"{_STATE_PREFIX}charts_yoy"
_K_CHARTS_CUSTOM = f"{_STATE_PREFIX}charts_custom"


def _render_charts_section(cur: dict) -> None:
    """Sección GRÁFICAS (G5 + F7-A2): 7 charts en tabs + toggle YoY global.

    Sólo wiring. La 3ª serie (`actual`) se resuelve contra hoy y se pasa a los 7;
    si el AM no cargó el mes real, `actual_rows=[]` y los charts se ven igual que
    antes de F7 (garantizado por A2, sin guards extra acá).
    """
    st.divider()
    st.markdown("### 📊 Gráficas")

    hist_rows = cur.get("historical", [])
    if not hist_rows:
        st.info("Cargá el histórico para ver los gráficos.")
        return
    fc_rows = cur.get("forecast", [])
    actual_rows = _resolve_partial(cur.get("actual", []))

    # Buffers (una sola vez, defaults del HTML).
    if _K_CHARTS_CUSTOM not in st.session_state:
        st.session_state[_K_CHARTS_CUSTOM] = ["revenue"]   # HTML L2378
    if _K_CHARTS_YOY not in st.session_state:
        st.session_state[_K_CHARTS_YOY] = True             # HTML L937 (checked)

    # Toggle YoY global (aplica a los 7 charts). Buffer keyless.
    yoy = st.toggle("Mostrar YoY", value=st.session_state[_K_CHARTS_YOY],
                    help="Compara contra el mismo mes del año previo (línea punteada).")
    st.session_state[_K_CHARTS_YOY] = yoy

    # F7 · UX — hay histórico pero no mes real: la línea verde no existe y nada
    # lo dice. Es el mismo síntoma de haber cargado el BR en el uploader
    # equivocado, así que el hint nombra el bloque exacto al que hay que ir. Va
    # como caption y no como warning: no falta nada, es una función sin estrenar.
    if not actual_rows:
        st.caption(
            "Cargá el mes en curso en \"● Cargar mes real\" para ver la línea "
            "real contra el forecast."
        )

    tabs = st.tabs(["Revenue", "Sessions", "CVR", "Units", "Ads",
                    "ACOS/TACOS", "Custom"])

    with tabs[0]:
        st.plotly_chart(_metric_chart("revenue", hist_rows, fc_rows, yoy,
                                      actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[1]:
        st.plotly_chart(_metric_chart("sessions", hist_rows, fc_rows, yoy,
                                      actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[2]:
        st.plotly_chart(_metric_chart("cvr", hist_rows, fc_rows, yoy,
                                      actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[3]:
        st.plotly_chart(_metric_chart("units", hist_rows, fc_rows, yoy,
                                      actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[4]:
        st.plotly_chart(_ads_chart(hist_rows, fc_rows, yoy,
                                   actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[5]:
        st.plotly_chart(_acos_tacos_chart(hist_rows, fc_rows, yoy,
                                          actual_rows=actual_rows),
                        use_container_width=True)
    with tabs[6]:
        sel = st.pills(
            "Métricas",
            options=list(_METRICS.keys()),
            format_func=lambda mid: _METRICS[mid]["label"],
            selection_mode="multi",
            default=st.session_state[_K_CHARTS_CUSTOM],   # SIN key=
        )
        # Mínimo 1 chip: vacío → IGNORAR (el buffer NO se actualiza).
        if sel:
            st.session_state[_K_CHARTS_CUSTOM] = sel
        # Orden de catálogo (eje izquierdo estable entre reruns). El chart SIEMPRE
        # se dibuja con el BUFFER, nunca con `sel`.
        selected = [mid for mid in _METRICS
                    if mid in st.session_state[_K_CHARTS_CUSTOM]]
        st.plotly_chart(_custom_chart(selected, hist_rows, fc_rows, yoy,
                                      actual_rows=actual_rows),
                        use_container_width=True)


# ─────────────────────────────────────────────────────────────────────────────
# F6-G6 — Export HTML self-contained (7 charts Plotly + design system Capybaras)
# ─────────────────────────────────────────────────────────────────────────────
#
# DECISIÓN DE ARQUITECTURA (Lenin): el reporte NO es una réplica del export
# Chart.js del HTML de Edu. Es un documento propio, con el design system de
# Capybaras, que embebe los MISMOS charts Plotly que el AM ve en pantalla (G1-G5).
# Es el "cobro" de haber elegido Plotly sobre Chart.js en G1: los charts del
# reporte son interactivos (hover, zoom) sin escribir una línea de JS.
#
# Capa PURA: estas 3 funciones no tocan Streamlit ni session_state. El wiring
# (`_render_export_section`) les pasa `cur` y el buffer de YoY. Testeables como
# strings, sin runtime ni browser.
#
# REUSO (no se duplica nada):
#   - `_metric_chart` / `_ads_chart` / `_acos_tacos_chart` / `_custom_chart` (G1-G4)
#   - `_fmt_currency` / `_fmt_num` / `_fmt_pct` (L628+) — ya devuelven '—' para None
#   - `_build_forecast_summary_cards` (L3063) — los 8 totales, ya formateados
#   - `_cliente_slug` (L3517) — filename filesystem-safe
#   - `html.escape` (stdlib) — en vez de un `_esc` propio

# Design system Capybaras (tema oscuro, default del OS). Tokens alineados con
# los del chart (`_CHART_GRID`/`_CHART_TICK`/`_CHART_FONT`, L2394+): el reporte y
# los charts embebidos comparten paleta, no se pelean.
_SHELL_CSS = """
:root{
  --bg:#000000; --panel:#0a0a0a; --line:#2a2a2a; --line-2:#1d1d1d;
  --text:#FFFFFF; --text-mute:#a8a8a8; --accent:#E84000;
}
*{box-sizing:border-box;}
body{
  margin:0; background:var(--bg); color:var(--text);
  font-family:'Geist',system-ui,-apple-system,sans-serif;
  font-size:14px; line-height:1.6;
}
.wrap{max-width:1100px; margin:0 auto; padding:40px 28px 64px;}
h1,h2{font-family:'Bricolage Grotesque',Georgia,serif; font-weight:600; margin:0;}
h1{font-size:2rem; letter-spacing:-0.02em;}
h2{font-size:1.15rem; margin:0 0 12px; letter-spacing:-0.01em;}
header{border-bottom:1px solid var(--line); padding-bottom:24px; margin-bottom:32px;}
.brand{
  font-family:'Bricolage Grotesque',Georgia,serif; font-weight:700;
  font-size:0.8rem; letter-spacing:0.14em; text-transform:uppercase;
  color:var(--accent); margin-bottom:10px;
}
.meta{color:var(--text-mute); font-size:0.82rem; margin-top:6px;}
.note{
  background:var(--panel); border:1px solid var(--line);
  border-left:3px solid var(--accent); border-radius:6px;
  padding:14px 18px; margin-bottom:32px; color:var(--text-mute);
}
section{margin-bottom:40px;}
.cards{display:flex; flex-wrap:wrap; gap:12px;}
.card{
  flex:1 1 180px; background:var(--panel); border:1px solid var(--line);
  border-radius:8px; padding:14px 16px;
}
.card .label{
  color:var(--text-mute); font-size:0.7rem; text-transform:uppercase;
  letter-spacing:0.08em; margin-bottom:6px;
}
.card .value{
  font-family:'JetBrains Mono',ui-monospace,monospace;
  font-size:1.25rem; font-weight:600; color:var(--text);
}
.chart{margin-bottom:36px;}
table{width:100%; border-collapse:collapse; font-family:'JetBrains Mono',ui-monospace,monospace; font-size:0.8rem;}
thead th{
  color:var(--text-mute); font-weight:500; font-size:0.68rem;
  text-transform:uppercase; letter-spacing:0.08em; text-align:right;
  padding:10px 12px; border-bottom:1px solid var(--line);
}
thead th:first-child{text-align:left;}
tbody td{padding:9px 12px; text-align:right; border-bottom:1px solid var(--line-2);}
tbody td:first-child{text-align:left; color:var(--text-mute);}
tbody tr:last-child td{border-bottom:none;}
footer{
  border-top:1px solid var(--line); padding-top:20px; margin-top:48px;
  color:var(--text-mute); font-size:0.75rem;
}
"""

_EXPORT_FONTS = (
    '<link rel="preconnect" href="https://fonts.googleapis.com">'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?'
    "family=Bricolage+Grotesque:wght@600;700&family=Geist:wght@400;500&"
    'family=JetBrains+Mono:wght@400;600&display=swap">'
)

# Los 7 charts del reporte, en el mismo orden que las tabs de G5.
_EXPORT_CHART_TITLES = [
    "Revenue", "Sessions", "CVR", "Units", "Ads", "ACOS/TACOS", "Custom",
]


def _fig_to_div(fig: "go.Figure", first: bool) -> str:
    """Convierte UNA figura a HTML embebible (sin `<html>`, sólo el div + script).

    🔴 LOAD-BEARING — TAMAÑO DEL ARCHIVO. `to_html()` embebe plotly.js (~3.5MB)
    en CADA figura por default. Con 7 figuras el reporte pesaría ~24MB y Gmail
    lo rebota. Fix en dos partes:
        - `include_plotlyjs="cdn"` (NO `True`): la lib se sirve desde el CDN de
          Plotly, no se embebe → el archivo queda en cientos de KB.
        - Sólo la PRIMERA figura la carga (`first=True`); las otras 6 pasan
          `False` y reusan la lib ya cargada en el documento.
    El test `test_export_loads_plotlyjs_once` afirma esto contando el marcador
    `cdn.plot.ly` (== 1). Si alguien cambia esto a `True`, el test lo caza.

    Trade-off del CDN: el reporte necesita internet para dibujar los charts.
    Aceptado — es un deliverable que se manda por mail y se abre en un browser
    con conexión; 24MB no es una alternativa real.
    """
    return fig.to_html(
        full_html=False,
        include_plotlyjs="cdn" if first else False,
        config={"displayModeBar": False},
    )


def _table_cell(v: Any) -> Optional[float]:
    """Normaliza un valor de celda a float o None (para que los `_fmt_*` den '—').

    Los `_fmt_*` (L628+) ya mapean None/NaN → '—', pero explotan con `''`
    (`f"{'':,.0f}"` → TypeError). Este normalizador cubre el hueco: None, '',
    no-numérico y NaN colapsan a None → '—'.
    """
    if v is None or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _forecast_table_html(fc_rows: list, currency: str = "USD") -> str:
    """Tabla HTML del forecast — una fila por mes proyectado.

    Columnas: Mes, Revenue, Units, Sessions, CVR, ACOS, TACOS.
    Formato delegado a los `_fmt_*` existentes (currency respeta la moneda de la
    cuenta, NO hardcodea '$'). Valores ausentes → '—' vía `_table_cell`.
    El `date` se escapa con `html.escape` — viene de datos, podría traer `<`/`&`.

    `fc_rows` vacío → devuelve '' (el caller decide si omite la sección).
    """
    if not fc_rows:
        return ""
    head = ["Mes", "Revenue", "Units", "Sessions", "CVR", "ACOS", "TACOS"]
    out = ["<table><thead><tr>"]
    out += [f"<th>{html.escape(h)}</th>" for h in head]
    out.append("</tr></thead><tbody>")
    for f in fc_rows:
        cells = [
            html.escape(str(f.get("date", "") or "—")),
            _fmt_currency(_table_cell(f.get("revenue")), currency),
            _fmt_num(_table_cell(f.get("units"))),
            _fmt_num(_table_cell(f.get("sessions"))),
            _fmt_pct(_table_cell(f.get("cvr")), 2),
            _fmt_pct(_table_cell(f.get("acos"))),
            _fmt_pct(_table_cell(f.get("tacos"))),
        ]
        out.append("<tr>" + "".join(f"<td>{c}</td>" for c in cells) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def _export_shell(title: str, body: str) -> str:
    """Envuelve `body` en el documento completo (head + fonts + CSS + wrap)."""
    return (
        "<!DOCTYPE html>\n"
        '<html lang="es">\n<head>\n'
        '<meta charset="UTF-8">\n'
        '<meta name="viewport" content="width=device-width, initial-scale=1">\n'
        f"<title>{html.escape(title)}</title>\n"
        f"{_EXPORT_FONTS}\n"
        f"<style>{_SHELL_CSS}</style>\n"
        "</head>\n<body>\n"
        f'<div class="wrap">\n{body}\n</div>\n'
        "</body>\n</html>\n"
    )


def _build_export_html(
    cur: dict,
    note: str = "",
    show_yoy: bool = True,
    custom_metrics: Optional[list] = None,
    actual_rows: Optional[list] = None,
) -> str:
    """Reporte HTML self-contained del forecast: 7 charts Plotly + resumen + tabla.

    Args:
        cur: dict del cliente activo (keys: name, currency, historical, forecast).
        note: nota opcional del AM para el cliente. Se escapa (`html.escape`) —
              es texto libre que termina en un documento que se manda por mail.
        show_yoy: se propaga a los 7 charts. Default True para que los tests NO
                  dependan de session_state; el wiring le pasa el buffer real de
                  G5 (`_K_CHARTS_YOY`) → el reporte RESPETA el toggle del AM en
                  vez de forzar un valor.
        custom_metrics: métricas del 7º chart (Custom). None o `[]` → `["revenue"]`
                  (default del HTML L2378). El caso `[]` se cubre a propósito:
                  `_custom_chart([])` devuelve figura VACÍA, y un chart en blanco
                  en un deliverable es peor que el default. G5 ya enforcea el
                  mínimo de 1 chip, así que en producción no se dispara.
                  Mismo patrón que `show_yoy`: param
                  con default en vez de leer session_state, para que la capa
                  siga PURA y testeable. El wiring le pasa el buffer real de G5
                  (`_K_CHARTS_CUSTOM`) → el Custom del reporte refleja lo que el
                  AM eligió en pantalla, en vez de ser un duplicado del chart de
                  Revenue.
        actual_rows: capa `actual` CRUDA (F7-A4). None o `[]` → el reporte sale
                  exactamente como antes de A4, sin línea verde: el default
                  mantiene retrocompatible a todo caller viejo.
                  A diferencia de `show_yoy`/`custom_metrics`, acá NO se pide el
                  dato ya resuelto: el `partial=None` que deja
                  `_parse_actual_report` se cierra ACÁ ADENTRO con
                  `_resolve_partial`, un solo punto de verdad. Meterle
                  `date.today()` a esta función no agrega una dependencia
                  temporal nueva — ya la tiene para el `gen` del header.

    Returns:
        Documento HTML completo como string.

    Guard: `historical` vacío → documento MÍNIMO con un mensaje, NO excepción.
    En producción no se dispara (el guard de `_render_export_section` ya exige
    forecast, que no existe sin historial); queda como red de seguridad.
    """
    name = cur.get("name") or "Cuenta"
    currency = cur.get("currency", "USD")
    hist = cur.get("historical", []) or []
    fc = cur.get("forecast", []) or []
    gen = date.today().isoformat()

    head = (
        "<header>\n"
        '<div class="brand">Capybaras</div>\n'
        f"<h1>{html.escape(name)}</h1>\n"
        f'<div class="meta">Monthly Forecast · generado el {gen}</div>\n'
        "</header>"
    )

    if not hist:
        body = (
            f"{head}\n"
            '<section><p class="meta">Sin datos para exportar. Cargá el '
            "histórico para generar el reporte.</p></section>"
        )
        return _export_shell(f"Forecast · {name}", body)

    parts = [head]

    if note.strip():
        parts.append(f'<div class="note">{html.escape(note.strip())}</div>')

    # Resumen — reusa el builder puro del summary de F4 (8 cards ya formateados).
    cards = _build_forecast_summary_cards(fc, currency)
    if cards:
        cards_html = "".join(
            f'<div class="card"><div class="label">{html.escape(c["label"])}</div>'
            f'<div class="value">{html.escape(str(c["value"]))}</div></div>'
            for c in cards
        )
        parts.append(
            f'<section><h2>Resumen de la proyección</h2>'
            f'<div class="cards">{cards_html}</div></section>'
        )

    # F7-A4 — la capa `actual` se resuelve UNA vez, acá, y de acá baja a los 7.
    actual = _resolve_partial(actual_rows) if actual_rows else []

    # Orden de catálogo, igual que G5 en L4301. El buffer de los chips guarda el
    # orden en que el AM los fue tocando, no el del catálogo, y ese orden decide
    # dos cosas: qué línea real va sólida (F7-A4) y cuál es el eje izquierdo
    # (`_axis_split` mira la 1ra unidad que aparece). Sin normalizar, el Custom
    # del reporte podía salir distinto del que el AM validó en pantalla.
    custom_ids = [mid for mid in _METRICS if mid in (custom_metrics or ["revenue"])]

    # Los 7 charts — se CONSTRUYEN llamando a los charts puros de G1-G4, con el
    # mismo `show_yoy` que el AM tiene en pantalla. Orden = tabs de G5.
    figs = [
        _metric_chart("revenue", hist, fc, show_yoy, actual_rows=actual),
        _metric_chart("sessions", hist, fc, show_yoy, actual_rows=actual),
        _metric_chart("cvr", hist, fc, show_yoy, actual_rows=actual),
        _metric_chart("units", hist, fc, show_yoy, actual_rows=actual),
        _ads_chart(hist, fc, show_yoy, actual_rows=actual),
        _acos_tacos_chart(hist, fc, show_yoy, actual_rows=actual),
        _custom_chart(custom_ids, hist, fc, show_yoy, actual_rows=actual),
    ]
    charts_html = "".join(
        f'<div class="chart"><h2>{html.escape(t)}</h2>'
        f"{_fig_to_div(f, first=(i == 0))}</div>"
        for i, (t, f) in enumerate(zip(_EXPORT_CHART_TITLES, figs))
    )
    parts.append(f"<section>{charts_html}</section>")

    table = _forecast_table_html(fc, currency)
    if table:
        parts.append(f"<section><h2>Detalle del forecast</h2>{table}</section>")

    parts.append(
        f"<footer>Generado por Agency OS · Capybaras Agency · {gen[:4]}</footer>"
    )
    return _export_shell(f"Forecast · {name}", "\n".join(parts))


def _render_asin_section(cur: dict) -> None:
    """Sección F6.2 — Por ASIN: multi-upload de reportes By Child Item, acumulación
    al vuelo (sin persistencia), niveles child/parent/cuenta y forecast por-ASIN
    (F6.3). Respeta gotchas 1.43.2: sin st.form, sin key=+value= juntos (se
    pre-siembra session_state para inputs con default computado), keys namespaced
    por cur['id'], data_editor read-only, None/NaN→'' pre-Arrow.
    """
    st.divider()
    st.markdown("### 🧩 Por ASIN")
    st.caption(
        "Subí los reportes mensuales \"Detail Page Sales and Traffic\" "
        "(Seller Central → Business Reports → By ASIN). Se acumulan al vuelo "
        "para ver historial y forecast por ASIN (no se guardan todavía)."
    )

    files = st.file_uploader(
        "Detail Page Sales and Traffic (By ASIN) — un CSV por mes",
        type=["csv"],
        accept_multiple_files=True,
        key=f"rf_asin_uploader_{cur['id']}",
    )
    if not files:
        st.info(
            "Subí 2+ meses del reporte Detail Page Sales and Traffic (By ASIN) "
            "para ver historial y forecast por ASIN."
        )
        return

    currency = cur.get("currency", "USD")
    _period_valid = re.compile(r"^20\d{2}-(0[1-9]|1[0-2])$")

    # 1) Derivar period por archivo (del nombre; fallback text_input).
    periods: list[str] = []
    for f in files:
        inferred = _infer_asin_period(f.name)
        if inferred:
            periods.append(inferred)
        else:
            pin = st.text_input(
                f"Período de {f.name} (formato YYYY-MM)",
                key=f"rf_asin_period_{cur['id']}_{f.name}",
            )
            periods.append((pin or "").strip())

    if not all(_period_valid.match(p) for p in periods):
        st.warning(
            "Falta el período de algún archivo (o formato inválido). Completá "
            "cada período como YYYY-MM (ej. 2026-07) para continuar."
        )
        return

    # 2) Parsear cada archivo + validar formato By Child Item.
    snapshots: list[list[dict]] = []
    for f, period in zip(files, periods):
        raw = f.getvalue()
        header = raw.split(b"\n", 1)[0].decode("utf-8-sig", errors="replace")
        if not _is_asin_report(header):
            st.error(f"{f.name} no parece un reporte Detail Page Sales and Traffic (By ASIN).")
            return
        try:
            snapshots.append(_parse_asin_report(raw, period))
        except Exception as e:  # noqa: BLE001 — fail-soft al AM
            st.error(f"No se pudo parsear {f.name}: {e}")
            return

    # 3) Días cubiertos por período (partial). Pre-sembramos session_state para
    # tener default computado SIN pasar value=+key= juntos (gotcha 1.43.2).
    partial_periods: dict = {}
    uniq_periods = sorted(set(periods))
    st.markdown("##### Días cubiertos por mes")
    st.caption("Bajá el número si el mes está incompleto (ej. corte parcial).")
    day_cols = st.columns(min(4, len(uniq_periods)))
    for i, period in enumerate(uniq_periods):
        dim = _days_in_month(_period_to_date(period))
        k = f"rf_asin_days_{cur['id']}_{period}"
        if k not in st.session_state:
            st.session_state[k] = dim
        with day_cols[i % len(day_cols)]:
            d = st.number_input(
                f"Días — {period}",
                min_value=1, max_value=dim, step=1, key=k,
            )
        if int(d) < dim:
            partial_periods[period] = {"days_covered": int(d)}

    # 4) Acumular.
    model = _accumulate_asin_snapshots(snapshots, partial_periods=partial_periods)
    if not model:
        st.warning("No se acumuló ningún ASIN (revisá los archivos).")
        return

    # 5) KPI cards de cuenta (nivel agregado, último período).
    totals = _asin_account_totals(model)
    latest = totals[-1] if totals else {"period": "—", "revenue": 0.0,
                                        "units": 0.0, "sessions": 0.0}
    cards = [
        {"label": "ASINs", "value": _fmt_num(len(model))},
        {"label": f"Revenue {latest['period']}",
         "value": _fmt_currency(latest["revenue"], currency)},
        {"label": f"Units {latest['period']}",
         "value": _fmt_num(latest["units"])},
        {"label": f"Sessions {latest['period']}",
         "value": _fmt_num(latest["sessions"])},
    ]
    kpi_cols = st.columns(4)
    for col, card in zip(kpi_cols, cards):
        with col:
            st.markdown(
                kpi_card(card["label"], card["value"], delta=None, delta_good=True),
                unsafe_allow_html=True,
            )

    # 6) Selector de nivel + tabla read-only.
    st.markdown("")
    level = st.radio(
        "Nivel", ["Child ASIN", "Parent", "Cuenta"],
        horizontal=True, key=f"rf_asin_level_{cur['id']}",
    )
    all_periods = sorted({h["period"] for node in model.values()
                          for h in node["history"]})

    if level == "Child ASIN":
        df = _build_asin_child_df(model)
        st.data_editor(
            df, key=f"rf_asin_child_editor_{cur['id']}", disabled=True,
            hide_index=True, use_container_width=True,
        )
    elif level == "Parent":
        pdf = _build_asin_parent_df(model, all_periods)
        st.data_editor(
            pdf, key=f"rf_asin_parent_editor_{cur['id']}", disabled=True,
            hide_index=True, use_container_width=True,
        )
    else:  # Cuenta
        cdf = pd.DataFrame(totals)
        cdf = cdf.where(pd.notna(cdf), "")
        st.data_editor(
            cdf, key=f"rf_asin_account_editor_{cur['id']}", disabled=True,
            hide_index=True, use_container_width=True,
        )

    # 7) Forecast por ASIN (F6.3).
    st.markdown("")
    st.markdown("##### Forecast por ASIN")
    asin_keys = list(model.keys())
    sel = st.selectbox(
        "ASIN a proyectar",
        asin_keys,
        format_func=lambda a: f"{a} — {(model[a].get('title') or '')[:40]}",
        key=f"rf_asin_fc_sel_{cur['id']}",
    )
    buf = _ensure_fc_buf()
    opts = {
        "horizon": int(buf.get("horizon", 3)),
        "momWindow": int(buf.get("momWindow", 3)),
        "blend": int(buf.get("blend", 50)),
        "useSeasonality": bool(buf.get("useSeasonality", False)),
    }
    # E6: no se calcula solo al elegir el ASIN — lo dispara el AM con el botón,
    # y el resultado queda cacheado por-ASIN hasta que regenere.
    st.caption(
        "Usa los parámetros de la proyección general de arriba: "
        + _fc_params_caption(opts)
    )
    gen_clicked = st.button(
        "Generar forecast por ASIN",
        key=f"rf_asin_fc_gen_{cur['id']}",
        type="primary",
    )

    _fc_cache_key = _asin_fc_cache_key(cur["id"], sel)
    if gen_clicked:
        # Guardamos también los opts USADOS: si el AM cambia los controles de
        # arriba sin regenerar, el caption tiene que seguir describiendo lo que
        # realmente se proyectó, no los valores nuevos.
        st.session_state[_fc_cache_key] = {
            "fc": _forecast_single_asin(model[sel]["history"], opts),
            "opts": dict(opts),
        }

    _cached = st.session_state.get(_fc_cache_key)
    if _cached is None:
        st.caption("Todavía no generaste el forecast de este ASIN.")
    elif not _cached["fc"]:
        st.info("Se necesitan 2+ meses COMPLETOS para proyectar este ASIN (los meses parciales se excluyen del cálculo).")
    else:
        fc = _cached["fc"]
        _used = _cached.get("opts", {})
        st.caption("Proyectado con: " + _fc_params_caption(_used))
        if _used != opts:
            st.caption(
                "⚠️ Los parámetros de arriba cambiaron desde que generaste este "
                "forecast — volvé a generar para que refleje los nuevos."
            )
        # Real vs forecast del ASIN. Sólo 4 métricas: el reporte By Child Item
        # no trae spend ni ventas PPC, así que ACOS/TACOS/Spend viven a nivel
        # cuenta y no se ofrecen acá.
        metric_id = st.radio(
            "Métrica",
            list(_ASIN_CHART_METRICS),
            format_func=lambda mid: _METRICS[mid]["label"],
            horizontal=True,
            key=f"rf_asin_fc_metric_{cur['id']}",
            help="El reporte Detail Page Sales and Traffic no reporta inversión de Ads por ASIN "
                 "— ACOS, TACOS y Spend sólo existen a nivel cuenta.",
        )
        st.plotly_chart(
            _asin_realvs_forecast_chart(model[sel]["history"], fc, metric_id),
            use_container_width=True,
        )


        fdf = pd.DataFrame([{
            "Período": r["date"][:7],
            "Revenue": r.get("revenue", 0.0),
            "Units": r.get("units", 0.0),
            "Sessions": r.get("sessions", 0.0),
        } for r in fc])
        fdf = fdf.where(pd.notna(fdf), "")
        st.data_editor(
            fdf, key=f"rf_asin_fc_editor_{cur['id']}", disabled=True,
            hide_index=True, use_container_width=True,
            column_config={
                "Revenue": st.column_config.NumberColumn("Revenue", format="%.2f"),
                "Units": st.column_config.NumberColumn("Units", format="%.0f"),
                "Sessions": st.column_config.NumberColumn("Sessions", format="%.0f"),
            },
        )


def render() -> None:
    """Entry point del Monthly Forecast (M31) — sección Account Manager.

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

    # Selector + popover "➕ Nuevo cliente" pegado (columns, NO expander — gotcha 1.43.2).
    col_sel, col_new = st.columns([4, 1])
    with col_sel:
        selected_label = st.selectbox("Cliente", labels, index=default_idx)
    with col_new:
        # Spacer para alinear el botón con el input (el selectbox tiene label arriba).
        st.markdown("<div style='height:1.7rem'></div>", unsafe_allow_html=True)
        with st.popover("➕ Nuevo cliente", use_container_width=True):
            st.markdown("**Crear cliente nuevo**")
            new_name = st.text_input("Nombre del cliente", key="rf_new_client_name")
            new_mkt = st.selectbox("Marketplace", _MARKETPLACES, key="rf_new_client_mkt")
            if st.button("Crear", key="rf_new_client_create_btn", type="primary"):
                _ok, _kind, _msg = _create_client_flow(new_name, new_mkt)
                if _kind == "warning":
                    st.warning(_msg)
                else:
                    st.success(_msg)
                    # NO hacer .pop() de los keys de los widgets: modificar un key
                    # ya instanciado tira StreamlitAPIException. El st.rerun cierra
                    # el popover al quedar el cliente nuevo activo.
                    st.rerun()

    selected_id = label_to_id[selected_label]
    if selected_id != active_id:
        _set_active_client(selected_id)

    cur = _cur_client()
    if cur is None:
        st.warning("No hay cliente activo.")
        return

    st.caption(
        f"Cliente activo: **{cur['name']}** (`{cur['id']}`) · "
        f"marketplace {cur['marketplace']}"
    )

    if st.button(
        "💾 Guardar cliente",
        key="rf_save_client_btn",
        help="Persiste el catálogo de clientes (nube o disco local según config).",
    ):
        if _try_persist():
            st.success("Guardado ✓")

    # 4) Aviso de fase.
    st.info(
        "🚧 **Fase 5 — MVP cerrado.** Estacionalidad UI + Export CSV activos. "
        "Falta forecast por-ASIN (F6) y snapshots/vs-Real (post-MVP). "
        "Los clientes y su forecast se guardan en Supabase."
    )

    # 5) Sección DATOS — port del HTML L721-785.
    st.divider()
    _render_account_config(cur)
    st.markdown("")
    _render_upload_and_demo(cur)
    st.markdown("")
    _render_actual_upload(cur)
    st.markdown("")
    _render_quick_stats(cur)
    st.markdown("")
    _render_history_table(cur)

    # 6) Sección FORECAST (F4) — port del HTML L788-820 (controles) +
    # L2064 (cards/tabla) + L2193 (summary).
    _render_forecast_section(cur)

    # 6a) Sección GRÁFICAS (G5) — 7 charts (hist + forecast) en tabs + toggle YoY.
    _render_charts_section(cur)

    # 6b) Sección POR ASIN (F6.2 + F6.3) — multi-upload By Child Item + niveles + forecast.
    _render_asin_section(cur)

    # 7) Sección ESTACIONALIDAD (F5) — port del HTML L2243.
    _render_seasonality_section(cur)

    # 8) Sección EXPORT (F5) — port del HTML L2858 con extensión de overrides.
    _render_export_section(cur)
