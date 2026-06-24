"""M31 — Revenue Forecast (port del HTML standalone a módulo Streamlit).

Sección: Account Manager
Página: 📈 Revenue Forecast
Fase: 1 (ESQUELETO — sin motor de forecast, sin tabs, sin generación de
proyecciones). Solo: modelo de state + accessor de cliente activo +
capa de persistencia DORMIDA + registro en navegación + selector de cliente.

Las Fases 2+ portearán generateForecast / recomputeForecastRow / seasonality /
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

from datetime import date
from typing import Any, Optional

import streamlit as st

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

# SOP in-app — placeholder mínimo Fase 1.
_SOP_MD = """
### Revenue Forecast — cómo usarlo (Fase 1)

Módulo en construcción. Esta fase sólo expone la **selección de cliente**:
crea/elige el cliente activo. El motor de forecast (generación de proyecciones,
estacionalidad, drill-down por ASIN) llega en la **Fase 2**.

**Estado actual:**
- Catálogo de clientes vive en sesión (no persiste entre reinicios).
- Si no hay clientes, se siembra un cliente demo automáticamente.
- Al cambiar el selector, el "cliente activo" se actualiza.

**Próximas fases:**
- F2: parsers de histórico + motor `generateForecast`.
- F3: estacionalidad + drill-down por ASIN.
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
# Render principal — Fase 1: selector + caption, NADA más
# ─────────────────────────────────────────────────────────────────────────────

def _header() -> None:
    """Header estándar Capybaras (patrón module-architecture-standard)."""
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📈</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>Revenue Forecast</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Account Manager · proyección de revenue cliente-céntrica (Fase 1: esqueleto)"
        "</div></div></div>",
        unsafe_allow_html=True,
    )
    st.divider()


def render() -> None:
    """Entry point del Revenue Forecast (M31) — sección Account Manager.

    Fase 1: SOLO header + expander de ayuda + selector de cliente + caption
    "Cliente activo". NO renderea tabs, NO corre motor de forecast, NO
    persiste a disco. El motor llega en Fase 2+.
    """
    _header()

    with st.expander("📘 Cómo usar este módulo", expanded=False):
        st.markdown(_SOP_MD)

    # 1) Inicializar state (idempotente) + seed demo si vacío.
    _ensure_state()
    _seed_demo_client_if_empty()

    clients = st.session_state.get(_K_CLIENTS, [])

    # 2) Empty state defensivo (en teoría no se llega acá por el seed demo,
    # pero queda como guard si alguna F2+ desactiva el seed).
    if not clients:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>📂</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>No hay clientes cargados</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
            "La gestión de catálogo de clientes llega en Fase 2.</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # 3) Selector de cliente — patrón M30 (sin key=, se usa el return).
    # Construimos labels "name (marketplace)" y mapeamos label→id para
    # mostrar nombres humanos pero trabajar con ids estables.
    label_to_id = {f"{c['name']} ({c['marketplace']})": c["id"] for c in clients}
    labels = list(label_to_id.keys())

    # Calcular el índice del cliente activo para que el selectbox arranque
    # mostrándolo (sin esto, Streamlit defaultea al primero de la lista y
    # quedaría desincronizado del state).
    active_id = st.session_state.get(_K_ACTIVE_CLIENT_ID)
    try:
        active_label = next(lbl for lbl, cid in label_to_id.items() if cid == active_id)
        default_idx = labels.index(active_label)
    except StopIteration:
        default_idx = 0

    selected_label = st.selectbox("Cliente", labels, index=default_idx)
    selected_id = label_to_id[selected_label]

    # Aplicar cambio de selección al state si difiere del activo actual.
    if selected_id != active_id:
        _set_active_client(selected_id)

    # 4) Caption con el cliente activo — ÚNICA salida visible de F1.
    cur = _cur_client()
    if cur:
        st.caption(
            f"Cliente activo: **{cur['name']}** (`{cur['id']}`) · "
            f"marketplace {cur['marketplace']} · margin {int(cur['margin'] * 100)}%"
        )

    # 5) Aviso explícito de fase — para que el operador no espere features F2+.
    st.info(
        "🚧 **Fase 1 — esqueleto.** El selector de cliente está activo. "
        "El motor de forecast, la estacionalidad y el drill-down por ASIN "
        "llegan en la **Fase 2**. La persistencia entre sesiones llega en la **Fase 4**."
    )
