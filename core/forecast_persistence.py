"""Capa de persistencia DEDICADA a M31 Monthly Forecast.

⚠️ El módulo se llamaba "Revenue Forecast" hasta 2026-07-30. Se renombró SÓLO el
nombre visible: el `modulo` que viaja en la PK y en los paths sigue siendo
`revenue-forecast` (ver `MODULE_SLUG` en modules/pages/revenue_forecast.py).
El desfasaje nombre-visible ↔ slug es deliberado — cambiar el slug dejaría
huérfanos los clientes ya guardados.

Separada de `core/persistence.py` (Account Health) por decisión D3 del
discovery: los clientes de M31 CONVIVEN con los de Account Health pero NO se
unifican. M31 tiene su propio shape (`historical[]` / `forecast[]` /
`seasonality{}` / `asins[]`) y NO debe escribir a tablas `ah_*` ni depender
del flag `AGENCY_OS_AH_BACKEND`.

Identidad propia:
    - Flag de backend:     AGENCY_OS_FORECAST_BACKEND  (vs AGENCY_OS_AH_BACKEND)
    - Tabla Supabase:      forecast_clients     (vs ah_client_configs)
    - Layout local:        data/<area>/<cliente>/<modulo>/<name>.json
      Para M31 concretamente → data/account-manager/<cliente_id>/revenue-forecast/<name>.json
      (paths disjuntos con AH, que usa area="account-health").

Infraestructura COMPARTIDA con AH (a propósito):
    - Mismas env vars de credenciales: SUPABASE_URL / SUPABASE_KEY.
    - Mismo lugar de secrets: st.secrets["supabase"]["url" / "key"].
      Eso es infra (la instancia Supabase). Lo que NO se comparte es el flag
      de selección de backend ni la tabla destino.

API pública (3 helpers — Fase 1 sólo necesita client-configs):
    _save_forecast_client(config, area, cliente, modulo, name) -> Path
    _load_forecast_client(area, cliente, modulo, name) -> dict
    _list_forecast_clients(area, modulo) -> list[str]

Reglas duras (heredadas del skill data-persistence-standard):
    - Cero lógica de negocio acá. Solo I/O.
    - Cero borrados automáticos. El usuario decide cuándo limpiar `data/`.
    - Cero paths hardcodeados — todo desde (area, cliente, modulo, name).
    - Lecturas cacheadas con @st.cache_data. Escrituras invalidan cache.

Estado: el flag default es local. Supabase está DORMIDO hasta que:
    1) M31 active `_PERSISTENCE_ENABLED = True` en revenue_forecast.py (F2+).
    2) Se cree la tabla `forecast_clients` en Supabase (DDL más abajo).
    3) Se setee `AGENCY_OS_FORECAST_BACKEND="supabase"` + creds en swap-day.
    4) RLS se configura recién en swap-day (NO ahora — la tabla nace dormida).

Patrón copiado (NO importado) de `core/persistence.py`:
    - `_storage_config` / `_backend_flag` / `_forecast_opt_in` / `_get_backend` /
      `_set_backend_for_testing` (singleton por proceso, opt-in explícito).
    - `_LocalBackend` con save/load/list de client-configs.
    - `_SupabaseBackend` con transport HTTP inyectable (testeable sin red).
    - Wrappers públicos con `@_cache_data` + invalidación tras escritura.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    # Permite usar este módulo en scripts standalone (testing) sin Streamlit.
    _HAS_STREAMLIT = False


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("data")


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────────────────────


def _module_dir(area: str, cliente: str, modulo: str) -> Path:
    """Construye `data/<area>/<cliente>/<modulo>/` y lo crea si no existe."""
    base = DATA_ROOT / area / cliente / modulo
    base.mkdir(parents=True, exist_ok=True)
    return base


def _cache_data(func):
    """Aplica @st.cache_data si Streamlit está disponible. Si no, no-op."""
    if _HAS_STREAMLIT:
        return st.cache_data(show_spinner=False)(func)
    return func


# ─────────────────────────────────────────────────────────────────────────────
# Backend local — Fase 1 (JSON en disco bajo DATA_ROOT)
# ─────────────────────────────────────────────────────────────────────────────


class _LocalBackend:
    """Backend Fase 1: JSON en disco local.

    Mismo layout que `core.persistence._LocalBackend` para client-configs, pero
    aislado: M31 vive en area="account-manager", AH en area="account-health".
    Paths nunca colisionan.

    NO cachea (cacheo vive en los wrappers públicos). Lee el global DATA_ROOT
    en cada llamada para respetar monkeypatch de tests.
    """

    def save_client_config(
        self,
        config: dict,
        area: str,
        cliente: str,
        modulo: str,
        name: str,
    ) -> Path:
        """Guarda un config JSON per-cliente en
        `data/<area>/<cliente>/<modulo>/<name>.json`.
        """
        base = _module_dir(area, cliente, modulo)
        out = base / f"{name}.json"
        out.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out

    def load_client_config(
        self,
        area: str,
        cliente: str,
        modulo: str,
        name: str,
    ) -> dict:
        p = DATA_ROOT / area / cliente / modulo / f"{name}.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))

    def list_clientes(self, area: str, modulo: str) -> list[str]:
        """Lista clientes con datos del módulo (carpeta `<modulo>/` poblada).

        Mismo criterio que el local de AH: escanea `DATA_ROOT/<area>/` y
        devuelve cada `<cliente>` que tenga subcarpeta `<modulo>/`. No requiere
        contenido específico — basta cualquier archivo bajo ella.
        """
        base = DATA_ROOT / area
        if not base.exists():
            return []
        out = []
        for p in sorted(base.iterdir()):
            if not p.is_dir():
                continue
            if (p / modulo).is_dir():
                out.append(p.name)
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Backend Supabase — DORMIDO (cableado pero no encendido)
# ─────────────────────────────────────────────────────────────────────────────
#
# Tabla destino: `forecast_clients` (NO `ah_client_configs`). Aislada de
# las tablas de Account Health para que el swap de M31 sea independiente.
#
# DDL — ejecutar UNA vez en Supabase antes de activar el backend remoto.
# RLS: se deja deshabilitada en este DDL; se activa recién en swap-day (F2),
# NO ahora (la tabla está dormida y nadie escribe).
#
#     create table if not exists forecast_clients (
#         area     text  not null,
#         cliente  text  not null,
#         modulo   text  not null,
#         name     text  not null,
#         data     jsonb not null,
#         primary key (area, cliente, modulo, name)
#     );
#     -- RLS disabled cuando se active (F2), no ahora.
#     -- alter table forecast_clients enable row level security;

_FORECAST_CLIENTS_TABLE = "forecast_clients"


class _ForecastTransport:
    """Transport HTTP por defecto sobre la API PostgREST de Supabase.

    Aislado para que `_SupabaseBackend` sea testeable sin red: los tests
    inyectan un transport en memoria con la misma interfaz (get/post/delete).
    `requests` se importa diferido (solo al instanciar) para no pagar el
    import si el backend activo es el local.
    """

    def __init__(self, url: str, key: str):
        import requests  # import diferido: solo si se usa el backend Supabase

        self._requests = requests
        self._base = url.rstrip("/") + "/rest/v1"
        self._headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        }

    def get(self, table: str, params: dict) -> list[dict]:
        r = self._requests.get(
            f"{self._base}/{table}", params=params, headers=self._headers, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def post(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        headers = dict(self._headers)
        prefer = "return=representation"
        if upsert:
            prefer += ",resolution=merge-duplicates"
        headers["Prefer"] = prefer
        r = self._requests.post(
            f"{self._base}/{table}", json=rows, headers=headers, timeout=30
        )
        r.raise_for_status()
        return r.json()

    def delete(self, table: str, params: dict) -> list[dict]:
        headers = dict(self._headers)
        headers["Prefer"] = "return=representation"
        r = self._requests.delete(
            f"{self._base}/{table}", params=params, headers=headers, timeout=30
        )
        r.raise_for_status()
        return r.json()


class _SupabaseBackend:
    """Backend remoto Fase 2+: PostgREST sobre Supabase, SIN SDK.

    Dormido por default. Sólo se instancia desde `_get_backend()` cuando hay
    credenciales Y el flag `AGENCY_OS_FORECAST_BACKEND` resuelto == "supabase".

    `transport` es inyectable (default: PostgREST sobre requests) → los tests
    pasan un fake en memoria sin tocar la red.

    Retornos tipo Path: pseudo-paths informativos `supabase://...`. M31 NO
    consume el valor de retorno para nada destructivo, así que el sentinel
    es seguro.
    """

    def __init__(self, url: str = "", key: str = "", transport=None):
        self._t = transport if transport is not None else _ForecastTransport(url, key)

    def save_client_config(
        self,
        config: dict,
        area: str,
        cliente: str,
        modulo: str,
        name: str,
    ) -> Path:
        """Upsert en `forecast_clients` por PK (area, cliente, modulo, name)."""
        row = {
            "area": area,
            "cliente": cliente,
            "modulo": modulo,
            "name": name,
            "data": config,
        }
        self._t.post(_FORECAST_CLIENTS_TABLE, [row], upsert=True)
        return Path(
            f"supabase://{_FORECAST_CLIENTS_TABLE}/{area}/{cliente}/{modulo}/{name}"
        )

    def load_client_config(
        self,
        area: str,
        cliente: str,
        modulo: str,
        name: str,
    ) -> dict:
        rows = self._t.get(
            _FORECAST_CLIENTS_TABLE,
            {
                "area": f"eq.{area}",
                "cliente": f"eq.{cliente}",
                "modulo": f"eq.{modulo}",
                "name": f"eq.{name}",
                "select": "data",
                "limit": "1",
            },
        )
        if not rows:
            return {}
        return rows[0]["data"]

    def list_clientes(self, area: str, modulo: str) -> list[str]:
        """Lista clientes con configs en (area, modulo) en `forecast_clients`.

        Sin tablas de snapshots aún en F1 — el universo de clientes coincide con
        quienes tienen al menos un client-config. Si F3+ agrega tabla de
        snapshots/history dedicada de forecast, este método debe unionar.
        """
        rows = self._t.get(
            _FORECAST_CLIENTS_TABLE,
            {
                "area": f"eq.{area}",
                "modulo": f"eq.{modulo}",
                "select": "cliente",
            },
        )
        clientes: set[str] = {r["cliente"] for r in rows if r.get("cliente")}
        return sorted(clientes)


# ─────────────────────────────────────────────────────────────────────────────
# Selector de backend — opt-in explícito (creds + flag), default local
# ─────────────────────────────────────────────────────────────────────────────


def _storage_config() -> tuple[str, str] | None:
    """Credenciales Supabase si están configuradas; None → no hay creds.

    Orden: env (SUPABASE_URL/SUPABASE_KEY) primero, luego
    `st.secrets["supabase"]` (Streamlit Cloud). Mismo patrón que core.persistence
    y M29 — la infra Supabase es compartida (una instancia, varias tablas).
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_KEY")
    if url and key:
        return url, key
    try:
        import streamlit as st

        sb = st.secrets.get("supabase")
        if sb and sb.get("url") and sb.get("key"):
            return sb["url"], sb["key"]
    except Exception:
        pass
    return None


def _backend_flag() -> str:
    """Flag de selección de backend M31 Monthly Forecast (normalizado).

    Precedencia: env `AGENCY_OS_FORECAST_BACKEND` GANA sobre secrets (permite
    forzar local por env aunque secrets diga supabase). Si la env no está
    seteada, lee el campo `forecast_backend` dentro de `[supabase]` en
    `st.secrets` — único lugar editable en swap-day sobre Streamlit Cloud.

    Devuelve el valor lowercase/strip, o "" si no hay nada.

    Nota: este flag es INDEPENDIENTE del flag de AH (`AGENCY_OS_AH_BACKEND` y
    secrets `[supabase].backend`). El operador puede tener AH en Supabase y
    M31 en local — o viceversa.
    """
    env_flag = os.environ.get("AGENCY_OS_FORECAST_BACKEND")
    if env_flag is not None:
        return env_flag.strip().lower()
    try:
        import streamlit as st

        sb = st.secrets.get("supabase")
        if sb:
            val = sb.get("forecast_backend")
            if val:
                return str(val).strip().lower()
    except Exception:
        pass
    return ""


def _forecast_opt_in() -> bool:
    """True solo si el operador habilitó explícitamente el backend Supabase para M31.

    La mera presencia de credenciales NO activa el backend remoto (eso rutearía
    a la red los tests que persisten a disco con creds vivas en secrets.toml). El
    swap productivo se hace seteando el flag a exactamente "supabase".
    """
    return _backend_flag() == "supabase"


_BACKEND: "_LocalBackend | _SupabaseBackend | None" = None


def _get_backend():
    """Devuelve el backend de persistencia activo (singleton por proceso).

    Selección opt-in explícito: devuelve `_SupabaseBackend` SOLO si hay
    credenciales (`_storage_config()`) Y el flag resuelto == "supabase"
    (`_forecast_opt_in()`). Si falta cualquiera de los dos → `_LocalBackend`.

    Consecuencia: al mergear a main sin flag, todo sigue local (cero regresión).
    Singleton independiente del de AH — son procesos in-memory distintos aunque
    apunten a la misma instancia Supabase.
    """
    global _BACKEND
    if _BACKEND is None:
        if _forecast_opt_in():
            cfg = _storage_config()
            if cfg:
                _BACKEND = _SupabaseBackend(*cfg)
        if _BACKEND is None:
            _BACKEND = _LocalBackend()
    return _BACKEND


def _set_backend_for_testing(backend) -> None:
    """Inyecta un backend alternativo (tests). Pasar None resetea el singleton
    para que la próxima llamada a `_get_backend()` lo reconstruya."""
    global _BACKEND
    _BACKEND = backend


# ─────────────────────────────────────────────────────────────────────────────
# API pública — wrappers con cache + invalidación
# ─────────────────────────────────────────────────────────────────────────────


def _save_forecast_client(
    config: dict,
    area: str,
    cliente: str,
    modulo: str,
    name: str,
) -> Path:
    """Guarda un config per-cliente de M31. Invalida cache de _load_forecast_client.

    Análogo a `_save_client_config` de core.persistence, pero ruteado al
    backend dedicado de M31 (`forecast_clients` en Supabase, o
    `data/<area>/<cliente>/<modulo>/<name>.json` en local).
    """
    out = _get_backend().save_client_config(config, area, cliente, modulo, name)
    if _HAS_STREAMLIT and hasattr(_load_forecast_client, "clear"):
        _load_forecast_client.clear()
        # un cliente nuevo se "materializa" al guardar su primer config
        _list_forecast_clients.clear()
    return out


@_cache_data
def _load_forecast_client(area: str, cliente: str, modulo: str, name: str) -> dict:
    """Lee un config per-cliente de M31. Devuelve {} si no existe."""
    return _get_backend().load_client_config(area, cliente, modulo, name)


@_cache_data
def _list_forecast_clients(area: str, modulo: str) -> list[str]:
    """Lista clientes de M31 con datos en (area, modulo), orden alfabético.

    Local: clientes con carpeta `<modulo>/` poblada en disco bajo `data/<area>/`.
    Supabase: distinct `cliente` en `forecast_clients` para (area, modulo).

    NO comparte universo con `_list_clientes` de core.persistence — son tablas
    y paths separados. Un cliente puede existir en AH pero no en M31, y
    viceversa.
    """
    return _get_backend().list_clientes(area, modulo)
