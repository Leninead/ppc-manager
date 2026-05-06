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
    base = _module_dir(area, cliente, modulo)
    out = base / f"{period}.parquet"
    df.to_parquet(out, compression="snappy", index=False)
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
    p = DATA_ROOT / area / cliente / modulo / f"{period}.parquet"
    if not p.exists():
        return None
    return pd.read_parquet(p)


@_cache_data
def _list_periods(area: str, cliente: str, modulo: str) -> list[str]:
    """Lista los periods con snapshot disponible, ordenados ascendentemente.

    Filtra archivos especiales (que empiezan con `_`) y solo cuenta los `.parquet`
    que parecen snapshots (`YYYY-WW`, `YYYY-MM`, `YYYY-MM-DD`).
    """
    base = DATA_ROOT / area / cliente / modulo
    if not base.exists():
        return []
    periods = []
    for p in base.glob("*.parquet"):
        name = p.stem
        if name.startswith("_"):
            continue
        periods.append(name)
    return sorted(periods)


# ─────────────────────────────────────────────────────────────────────────────
# History — agregador cross-período para queries WoW/MoM
# ─────────────────────────────────────────────────────────────────────────────


@_cache_data
def _load_history(area: str, cliente: str, modulo: str) -> pd.DataFrame:
    """Lee `_history.parquet` con TODOS los snapshots concatenados.

    Devuelve DataFrame vacío si no existe. Cada fila tiene columna `_period`
    indicando de qué snapshot proviene.
    """
    p = DATA_ROOT / area / cliente / modulo / "_history.parquet"
    if not p.exists():
        return pd.DataFrame()
    return pd.read_parquet(p)


def _rebuild_history(area: str, cliente: str, modulo: str) -> Path:
    """Reconstruye `_history.parquet` desde todos los snapshots del módulo.

    Concatena todos los `<period>.parquet` y agrega columna `_period`. Sobreescribe
    el _history.parquet existente.

    Returns:
        Path al `_history.parquet` reconstruido.

    Raises:
        FileNotFoundError si no hay ningún snapshot para concatenar.
    """
    base = _module_dir(area, cliente, modulo)
    periods = _list_periods(area, cliente, modulo)
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
    base = _module_dir_agnostic(area, modulo)
    out = base / f"{name}-v{version}.json"
    out.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    # Invalidar cache
    if _HAS_STREAMLIT and hasattr(_load_config, "clear"):
        _load_config.clear()
    return out


@_cache_data
def _load_config(area: str, modulo: str, name: str, version: int) -> dict:
    """Lee un config JSON. Devuelve {} si no existe."""
    p = DATA_ROOT / area / modulo / f"{name}-v{version}.json"
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


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
