"""Capa de persistencia centralizada del Agency OS.

Toda I/O de módulos pasa por estos helpers. Implementa el contrato definido en
`.claude/skills/data-persistence-standard.md`. Los módulos NO leen ni escriben
Parquet/JSON/CSV directamente — siempre pasan por aquí.

API pública (10 helpers):
    _save_snapshot(df, area, cliente, modulo, period) -> Path
    _load_snapshot(area, cliente, modulo, period) -> pd.DataFrame | None
    _load_history(area, cliente, modulo) -> pd.DataFrame
    _rebuild_history(area, cliente, modulo) -> Path
    _append_log(row, area, cliente, modulo, log_name) -> Path
    _load_log(area, cliente, modulo, log_name, filters=None) -> pd.DataFrame
    _save_config(config, area, modulo, name, version) -> Path
    _load_config(area, modulo, name, version) -> dict
    _list_periods(area, cliente, modulo) -> list[str]
    _validate_against_schema(df, modulo, version) -> list[str]

Reglas duras:
- Cero lógica de negocio acá. Solo I/O.
- Cero borrados automáticos. El usuario decide cuándo limpiar `data/`.
- Cero paths hardcodeados — todo se construye desde (area, cliente, modulo).
- Lecturas cacheadas con @st.cache_data. Escrituras invalidan cache explícitamente.

Migration path (Fase 1 → Fase 2 → Fase 3): cuando se migre a SQLite o Postgres,
solo cambia la implementación interna de estas funciones. Las signatures se
mantienen. Los módulos NO se tocan.

Ver `.claude/skills/data-persistence-standard.md` para contexto completo.
"""

from __future__ import annotations

import json
import os
from io import StringIO
from pathlib import Path

import pandas as pd

try:
    import streamlit as st
    _HAS_STREAMLIT = True
except ImportError:
    # Permite usar este módulo en scripts standalone (testing, migrations) sin Streamlit.
    _HAS_STREAMLIT = False


# ─────────────────────────────────────────────────────────────────────────────
# Constantes
# ─────────────────────────────────────────────────────────────────────────────

DATA_ROOT = Path("data")
SCHEMAS_ROOT = DATA_ROOT / "_schemas"


# ─────────────────────────────────────────────────────────────────────────────
# Helpers internos (no exportados, no llamar desde módulos)
# ─────────────────────────────────────────────────────────────────────────────


def _module_dir(area: str, cliente: str, modulo: str) -> Path:
    """Construye el path canónico `data/<area>/<cliente>/<modulo>/` y lo crea si no existe."""
    base = DATA_ROOT / area / cliente / modulo
    base.mkdir(parents=True, exist_ok=True)
    return base


def _module_dir_agnostic(area: str, modulo: str) -> Path:
    """Variante para módulos client-agnostic (ej. Flat File Migrator).

    Estructura: `data/<area>/<modulo>/` (sin nivel cliente).
    """
    base = DATA_ROOT / area / modulo
    base.mkdir(parents=True, exist_ok=True)
    return base


def _matches_dtype(series: pd.Series, expected: str) -> bool:
    """Valida si una columna respeta el dtype declarado en el schema.

    Acepta nombres laxos: 'string'/'str'/'object', 'float64'/'float',
    'int64'/'int', 'bool', 'datetime'/'datetime64[ns]'.
    """
    actual = str(series.dtype)
    expected_low = expected.lower()

    if expected_low in {"string", "str", "object"}:
        return actual in {"object", "string"}
    if expected_low in {"float", "float64", "float32"}:
        return actual.startswith("float")
    if expected_low in {"int", "int64", "int32", "int16"}:
        return actual.startswith("int")
    if expected_low == "bool":
        return actual == "bool"
    if expected_low.startswith("datetime"):
        return actual.startswith("datetime")
    return actual == expected_low


def _cache_data(func):
    """Decorator que aplica @st.cache_data si Streamlit está disponible.

    Permite usar este módulo desde scripts standalone (testing, migrations).
    """
    if _HAS_STREAMLIT:
        return st.cache_data(show_spinner=False)(func)
    return func


# ─────────────────────────────────────────────────────────────────────────────
# Backend de almacenamiento — capa swappeable (local / Supabase)
# ─────────────────────────────────────────────────────────────────────────────
#
# Los 7 helpers públicos de snapshot/history/config delegan en el backend activo.
# Fase 1 = `_LocalBackend` (Parquet/JSON en disco). El swap a Supabase (Bloque 2)
# solo cambia qué backend devuelve `_get_backend()`; los wrappers públicos, sus
# firmas y el manejo de cache NO cambian. `_append_log`/`_load_log` quedan fuera
# de esta abstracción por ahora (siguen siendo I/O local directa).


class _LocalBackend:
    """Backend Fase 1: Parquet/JSON en disco local bajo DATA_ROOT.

    Contiene la implementación histórica de los 7 helpers de snapshot/history/
    config. NO cachea (el cacheo vive en los wrappers públicos `@_cache_data`) y
    NO invalida cache (eso lo hacen los wrappers tras una escritura). Lee el
    global `DATA_ROOT` en cada llamada para respetar el monkeypatch de los tests.
    """

    # — Snapshots —

    def save_snapshot(
        self,
        df: pd.DataFrame,
        area: str,
        cliente: str,
        modulo: str,
        period: str,
    ) -> Path:
        base = _module_dir(area, cliente, modulo)
        out = base / f"{period}.parquet"
        df.to_parquet(out, compression="snappy", index=False)
        return out

    def load_snapshot(
        self,
        area: str,
        cliente: str,
        modulo: str,
        period: str,
    ) -> pd.DataFrame | None:
        p = DATA_ROOT / area / cliente / modulo / f"{period}.parquet"
        if not p.exists():
            return None
        return pd.read_parquet(p)

    def list_periods(self, area: str, cliente: str, modulo: str) -> list[str]:
        base = DATA_ROOT / area / cliente / modulo
        if not base.exists():
            return []
        periods = []
        for p in base.glob("*.parquet"):
            name = p.stem
            # Excluir: history aggregator (_*) + logs append-only canonicos del Agency OS
            if name.startswith("_"):
                continue
            if name in ("optimizations", "events", "decisions-log"):
                continue
            periods.append(name)
        return sorted(periods)

    # — History —

    def load_history(self, area: str, cliente: str, modulo: str) -> pd.DataFrame:
        p = DATA_ROOT / area / cliente / modulo / "_history.parquet"
        if not p.exists():
            return pd.DataFrame()
        return pd.read_parquet(p)

    def rebuild_history(self, area: str, cliente: str, modulo: str) -> Path:
        base = _module_dir(area, cliente, modulo)
        periods = self.list_periods(area, cliente, modulo)
        if not periods:
            raise FileNotFoundError(
                f"No hay snapshots en {base} para reconstruir history"
            )

        frames = []
        for period in periods:
            df = pd.read_parquet(base / f"{period}.parquet")
            df = df.copy()
            df["_period"] = period
            frames.append(df)

        history = pd.concat(frames, ignore_index=True)
        out = base / "_history.parquet"
        history.to_parquet(out, compression="snappy", index=False)
        return out

    # — Configs —

    def save_config(
        self,
        config: dict,
        area: str,
        modulo: str,
        name: str,
        version: int,
    ) -> Path:
        base = _module_dir_agnostic(area, modulo)
        out = base / f"{name}-v{version}.json"
        out.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        return out

    def load_config(self, area: str, modulo: str, name: str, version: int) -> dict:
        p = DATA_ROOT / area / modulo / f"{name}-v{version}.json"
        if not p.exists():
            return {}
        return json.loads(p.read_text(encoding="utf-8"))


# ─────────────────────────────────────────────────────────────────────────────
# Backend Supabase (Fase 2) — PostgREST vía requests (sin SDK)
# ─────────────────────────────────────────────────────────────────────────────
#
# Adaptado del patrón de M29 (`core/proposal_persistence.py`). Persiste snapshots
# y configs de Account Health en dos tablas PostgREST. El history NO se almacena:
# es derivado (concat de snapshots en query-time), igual que en local.

_SNAPSHOTS_TABLE = "ah_snapshots"
_CONFIGS_TABLE = "ah_configs"


class _PersistenceTransport:
    """Transport HTTP por defecto sobre la API PostgREST de Supabase.

    Copia adaptada del `_RequestsTransport` de M29. Aislado en su propia clase
    para que `_SupabaseBackend` sea testeable sin red: los tests inyectan un
    transport en memoria con la misma interfaz (get/post). No se importa
    `requests` a nivel módulo (solo al instanciar) para no pagar el import si el
    backend activo es el local.
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


class _SupabaseBackend:
    """Backend Fase 2: persistencia en Supabase vía PostgREST (REST puro, sin SDK).

    Esquema SQL (ejecutar UNA vez en el proyecto Supabase antes del swap-day —
    este código NO crea las tablas):

        create table if not exists ah_snapshots (
            area     text    not null,
            cliente  text    not null,
            modulo   text    not null,
            period   text    not null,
            data     text    not null,   -- df.to_json(orient="table")
            primary key (area, cliente, modulo, period)
        );

        create table if not exists ah_configs (
            area     text    not null,
            modulo   text    not null,
            name     text    not null,
            version  integer not null,
            data     jsonb   not null,
            primary key (area, modulo, name, version)
        );

    El history NO es una tabla: `load_history` concatena los snapshots de
    (area, cliente, modulo) en query-time (paridad con el `_history.parquet`
    derivado del backend local). `rebuild_history` NO persiste — solo valida que
    haya snapshots (raise FileNotFoundError si no, igual que local).

    `transport` es inyectable (default: PostgREST sobre requests) → los tests
    pasan un fake en memoria sin tocar la red.

    Retornos tipo Path: pseudo-paths informativos `supabase://...`. M30 NO lee el
    valor de retorno de _save_snapshot/_rebuild_history/_save_config (verificado
    en Bloque 1), así que el sentinel es seguro.
    """

    def __init__(self, url: str = "", key: str = "", transport=None):
        self._t = transport if transport is not None else _PersistenceTransport(url, key)

    @staticmethod
    def _is_snapshot_period(name: str | None) -> bool:
        """Mismo filtro de exclusión que `_LocalBackend.list_periods`."""
        if not name or name.startswith("_"):
            return False
        if name in ("optimizations", "events", "decisions-log"):
            return False
        return True

    # — Snapshots —

    def save_snapshot(
        self,
        df: pd.DataFrame,
        area: str,
        cliente: str,
        modulo: str,
        period: str,
    ) -> Path:
        row = {
            "area": area,
            "cliente": cliente,
            "modulo": modulo,
            "period": period,
            "data": df.to_json(orient="table"),
        }
        # upsert por PK (area,cliente,modulo,period): idempotente por period,
        # igual que el sobreescribir del .parquet en local.
        self._t.post(_SNAPSHOTS_TABLE, [row], upsert=True)
        return Path(f"supabase://{_SNAPSHOTS_TABLE}/{area}/{cliente}/{modulo}/{period}")

    def load_snapshot(
        self,
        area: str,
        cliente: str,
        modulo: str,
        period: str,
    ) -> pd.DataFrame | None:
        rows = self._t.get(
            _SNAPSHOTS_TABLE,
            {
                "area": f"eq.{area}",
                "cliente": f"eq.{cliente}",
                "modulo": f"eq.{modulo}",
                "period": f"eq.{period}",
                "select": "data",
                "limit": "1",
            },
        )
        if not rows:
            return None
        return pd.read_json(StringIO(rows[0]["data"]), orient="table")

    def list_periods(self, area: str, cliente: str, modulo: str) -> list[str]:
        rows = self._t.get(
            _SNAPSHOTS_TABLE,
            {
                "area": f"eq.{area}",
                "cliente": f"eq.{cliente}",
                "modulo": f"eq.{modulo}",
                "select": "period",
            },
        )
        periods = [
            r["period"] for r in rows if self._is_snapshot_period(r.get("period"))
        ]
        return sorted(periods)

    # — History —

    def load_history(self, area: str, cliente: str, modulo: str) -> pd.DataFrame:
        rows = self._t.get(
            _SNAPSHOTS_TABLE,
            {
                "area": f"eq.{area}",
                "cliente": f"eq.{cliente}",
                "modulo": f"eq.{modulo}",
                "select": "period,data",
            },
        )
        snapshots = sorted(
            (r for r in rows if self._is_snapshot_period(r.get("period"))),
            key=lambda r: r["period"],
        )
        frames = []
        for r in snapshots:
            df = pd.read_json(StringIO(r["data"]), orient="table")
            df = df.copy()
            df["_period"] = r["period"]
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def rebuild_history(self, area: str, cliente: str, modulo: str) -> Path:
        # History es derivado (load_history concatena en query-time): NO se
        # persiste. Replicamos el raise del local para paridad de contrato.
        periods = self.list_periods(area, cliente, modulo)
        if not periods:
            raise FileNotFoundError(
                f"No hay snapshots en supabase://{_SNAPSHOTS_TABLE}/{area}/{cliente}/"
                f"{modulo} para reconstruir history"
            )
        return Path(
            f"supabase://{_SNAPSHOTS_TABLE}/{area}/{cliente}/{modulo}/_history"
        )

    # — Configs —

    def save_config(
        self,
        config: dict,
        area: str,
        modulo: str,
        name: str,
        version: int,
    ) -> Path:
        row = {
            "area": area,
            "modulo": modulo,
            "name": name,
            "version": version,
            "data": config,
        }
        self._t.post(_CONFIGS_TABLE, [row], upsert=True)
        return Path(f"supabase://{_CONFIGS_TABLE}/{area}/{modulo}/{name}-v{version}")

    def load_config(self, area: str, modulo: str, name: str, version: int) -> dict:
        rows = self._t.get(
            _CONFIGS_TABLE,
            {
                "area": f"eq.{area}",
                "modulo": f"eq.{modulo}",
                "name": f"eq.{name}",
                "version": f"eq.{version}",
                "select": "data",
                "limit": "1",
            },
        )
        if not rows:
            return {}
        return rows[0]["data"]


# ─────────────────────────────────────────────────────────────────────────────
# Selector de backend — opt-in explícito (creds + flag), default local
# ─────────────────────────────────────────────────────────────────────────────


def _storage_config() -> tuple[str, str] | None:
    """Credenciales Supabase si están configuradas; None → no hay creds.

    Orden: env (SUPABASE_URL/SUPABASE_KEY) primero, luego
    `st.secrets["supabase"]` (Streamlit Cloud). Acceso a st.secrets con import
    diferido + try/except para no romper fuera de un runtime Streamlit (tests,
    scripts) ni acoplar este módulo a streamlit. Mismo patrón que M29.
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
    """Resuelve el flag de selección de backend Account Health (normalizado).

    Precedencia: env `AGENCY_OS_AH_BACKEND` GANA sobre secrets (permite forzar
    local por env aunque secrets diga supabase). Si la env no está seteada, lee
    el campo `backend` dentro de `[supabase]` en `st.secrets` — único lugar
    editable en swap-day sobre Streamlit Cloud. Acceso a st.secrets con import
    diferido + try/except (no rompe fuera de Streamlit).

    Devuelve el valor lowercase/strip, o "" si no hay nada.
    """
    env_flag = os.environ.get("AGENCY_OS_AH_BACKEND")
    if env_flag is not None:
        return env_flag.strip().lower()
    try:
        import streamlit as st

        sb = st.secrets.get("supabase")
        if sb:
            val = sb.get("backend")
            if val:
                return str(val).strip().lower()
    except Exception:
        pass
    return ""


def _supabase_opt_in() -> bool:
    """True solo si el operador habilitó explícitamente el backend Supabase.

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
    (`_supabase_opt_in()`). Si falta cualquiera de los dos → `_LocalBackend`.

    Consecuencia: al mergear a main sin flag, todo sigue local (cero regresión).
    El swap real se activa agregando `backend = "supabase"` al secrets de Cloud
    DESPUÉS de crear las tablas.
    """
    global _BACKEND
    if _BACKEND is None:
        if _supabase_opt_in():
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
# Snapshots — datos cambiantes en el tiempo (semanal/mensual/diario)
# ─────────────────────────────────────────────────────────────────────────────


def _save_snapshot(
    df: pd.DataFrame,
    area: str,
    cliente: str,
    modulo: str,
    period: str,
) -> Path:
    """Guarda un snapshot en `data/<area>/<cliente>/<modulo>/<period>.parquet`.

    Args:
        df: DataFrame a persistir.
        area: 'account-health', 'ppc', etc. (kebab-case).
        cliente: slug del cliente (kebab-case).
        modulo: slug del módulo (kebab-case).
        period: '2026-W18', '2026-04', '2026-05-06', etc. (formato ISO).

    Returns:
        Path al archivo escrito.

    Notes:
        - Sobreescribe el archivo si ya existe (idempotente por period).
        - Invalida el cache de _load_snapshot automáticamente.
    """
    out = _get_backend().save_snapshot(df, area, cliente, modulo, period)
    # Invalidar cache de lecturas
    if _HAS_STREAMLIT and hasattr(_load_snapshot, "clear"):
        _load_snapshot.clear()
        _list_periods.clear()
    return out


@_cache_data
def _load_snapshot(
    area: str,
    cliente: str,
    modulo: str,
    period: str,
) -> pd.DataFrame | None:
    """Lee un snapshot. Devuelve None si el archivo no existe."""
    return _get_backend().load_snapshot(area, cliente, modulo, period)


@_cache_data
def _list_periods(area: str, cliente: str, modulo: str) -> list[str]:
    """Lista los periods con snapshot disponible, ordenados ascendentemente.

    Filtra archivos especiales (que empiezan con `_`) y solo cuenta los `.parquet`
    que parecen snapshots (`YYYY-WW`, `YYYY-MM`, `YYYY-MM-DD`).
    """
    return _get_backend().list_periods(area, cliente, modulo)


# ─────────────────────────────────────────────────────────────────────────────
# History — agregador cross-período para queries WoW/MoM
# ─────────────────────────────────────────────────────────────────────────────


@_cache_data
def _load_history(area: str, cliente: str, modulo: str) -> pd.DataFrame:
    """Lee `_history.parquet` con TODOS los snapshots concatenados.

    Devuelve DataFrame vacío si no existe. Cada fila tiene columna `_period`
    indicando de qué snapshot proviene.
    """
    return _get_backend().load_history(area, cliente, modulo)


def _rebuild_history(area: str, cliente: str, modulo: str) -> Path:
    """Reconstruye `_history.parquet` desde todos los snapshots del módulo.

    Concatena todos los `<period>.parquet` y agrega columna `_period`. Sobreescribe
    el _history.parquet existente.

    Returns:
        Path al `_history.parquet` reconstruido.

    Raises:
        FileNotFoundError si no hay ningún snapshot para concatenar.
    """
    out = _get_backend().rebuild_history(area, cliente, modulo)

    # Invalidar cache
    if _HAS_STREAMLIT and hasattr(_load_history, "clear"):
        _load_history.clear()

    return out


# ─────────────────────────────────────────────────────────────────────────────
# Logs append-only — eventos históricos inmutables
# ─────────────────────────────────────────────────────────────────────────────


def _append_log(
    row: dict,
    area: str,
    cliente: str,
    modulo: str,
    log_name: str,
) -> Path:
    """Agrega 1 fila a un log append-only.

    Args:
        row: dict con la fila a agregar. Si no incluye 'timestamp', se agrega ISO 8601.
        area, cliente, modulo: ubicación canónica.
        log_name: nombre del log sin extensión (ej. 'optimizations', 'events',
                  'decisions-log').

    Returns:
        Path al archivo del log.

    Notes:
        - Crea el archivo si no existe.
        - Cada llamada hace lectura+concat+escritura. Si necesitás appendear miles
          de rows en loop, hacé un batch write con _save_snapshot en lugar de N
          appends.
        - Invalida el cache de _load_log automáticamente.
    """
    base = _module_dir(area, cliente, modulo)
    log_path = base / f"{log_name}.parquet"

    if "timestamp" not in row:
        row = {**row, "timestamp": pd.Timestamp.now().isoformat()}

    new_row_df = pd.DataFrame([row])

    if log_path.exists():
        existing = pd.read_parquet(log_path)
        combined = pd.concat([existing, new_row_df], ignore_index=True)
    else:
        combined = new_row_df

    combined.to_parquet(log_path, compression="snappy", index=False)

    # Invalidar cache
    if _HAS_STREAMLIT and hasattr(_load_log, "clear"):
        _load_log.clear()

    return log_path


@_cache_data
def _load_log(
    area: str,
    cliente: str,
    modulo: str,
    log_name: str,
    filters: dict | None = None,
) -> pd.DataFrame:
    """Lee un log append-only y opcionalmente filtra por columnas.

    Args:
        filters: dict {col: valor} para filtrar por igualdad. Si valor es lista,
                 filtra por isin. Devuelve DataFrame vacío si el log no existe.

    Ejemplo:
        _load_log('account-health', 'gamboa', 'sku-progress', 'optimizations',
                  filters={'sku': 'demarpa0001s56'})
    """
    p = DATA_ROOT / area / cliente / modulo / f"{log_name}.parquet"
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_parquet(p)
    if filters:
        for col, val in filters.items():
            if col not in df.columns:
                continue
            if isinstance(val, (list, tuple, set)):
                df = df[df[col].isin(val)]
            else:
                df = df[df[col] == val]
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Configs — JSON versionado por módulo
# ─────────────────────────────────────────────────────────────────────────────


def _save_config(
    config: dict,
    area: str,
    modulo: str,
    name: str,
    version: int,
) -> Path:
    """Guarda un config JSON en `data/<area>/<modulo>/<name>-v<version>.json`.

    Configs son client-agnostic por default (sin nivel cliente en el path).
    Si necesitás un config por cliente, usá _save_snapshot con un DataFrame de 1 fila
    o agregá el cliente como key dentro del JSON.

    Args:
        config: dict serializable a JSON.
        area: 'account-health', 'ppc', etc.
        modulo: slug del módulo.
        name: nombre lógico del config (ej. 'aliases', 'subcat-fee-avg').
        version: entero >= 1.

    Returns:
        Path al archivo escrito.
    """
    out = _get_backend().save_config(config, area, modulo, name, version)
    # Invalidar cache
    if _HAS_STREAMLIT and hasattr(_load_config, "clear"):
        _load_config.clear()
    return out


@_cache_data
def _load_config(area: str, modulo: str, name: str, version: int) -> dict:
    """Lee un config JSON. Devuelve {} si no existe."""
    return _get_backend().load_config(area, modulo, name, version)


# ─────────────────────────────────────────────────────────────────────────────
# Schemas — validación de DataFrames contra contratos versionados
# ─────────────────────────────────────────────────────────────────────────────


def _validate_against_schema(
    df: pd.DataFrame,
    modulo: str,
    version: int,
) -> list[str]:
    """Valida que un DataFrame respete el schema declarado.

    Lee `data/_schemas/<modulo>-v<version>.json` y verifica:
      1. Todas las columnas marcadas `required: true` están presentes.
      2. Las columnas presentes tienen el dtype declarado.
      3. Columnas marcadas `deprecated: true` se ignoran (warning, no error).

    Returns:
        Lista de mensajes de error. Vacía si el DataFrame es válido.
    """
    schema_path = SCHEMAS_ROOT / f"{modulo}-v{version}.json"
    if not schema_path.exists():
        return [f"Schema no existe: {schema_path}"]

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    errors: list[str] = []

    columns_spec = schema.get("columns", {})
    for col, spec in columns_spec.items():
        if spec.get("deprecated", False):
            continue

        required = spec.get("required", False)
        if required and col not in df.columns:
            errors.append(f"Falta columna obligatoria: {col}")
            continue

        if col in df.columns:
            expected_dtype = spec.get("dtype", "")
            if expected_dtype and not _matches_dtype(df[col], expected_dtype):
                errors.append(
                    f"Tipo incorrecto en '{col}': "
                    f"esperado {expected_dtype}, recibido {df[col].dtype}"
                )

    return errors
