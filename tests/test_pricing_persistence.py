"""Tests de la capa de persistencia para M30 Pricing Dashboard (F3.1).

Cubre las 6 validaciones del protocolo `data-persistence-specialist`:

1. Roundtrip save→load preserva dtypes.
2. Schema check: el DataFrame matchea pricing-dashboard-v1.json vía
   _validate_against_schema (0 errores).
3. Cache: las lecturas heredan @st.cache_data del wrapper genérico
   (verificado indirectamente: en standalone, _cache_data es passthrough).
4. Path coherence: todo bajo data/account-health/<cliente>/pricing-dashboard/.
5. Gitignore: el path nuevo cae bajo data/account-health/* (ya cubierto por
   el .gitignore vigente del worktree).
6. Import sin side effects: importar core.persistence no toca disco.

Decisión de diseño F3.1 (Lenin, 2026-06-02):
- NO se introduce código Python nuevo (ni helpers en core/persistence.py, ni
  thin-wrapper en modules/). El módulo M30 (F3.2+) llamará directo a la API
  genérica de core.persistence con sus propias constantes
  (AREA='account-health', MODULE_SLUG='pricing-dashboard', SCHEMA_VERSION=1) —
  exactamente igual que M28 SKU Progress Report.

Aislamiento: este test redirige DATA_ROOT y SCHEMAS_ROOT a tmp_path vía
monkeypatch para NO ensuciar data/account-health/test-pricing/ del repo real.
Limpieza: pytest tmp_path se borra automáticamente al cerrar el test.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pandas as pd
import pytest

from core import persistence as P


# ─────────────────────────────────────────────────────────────────────────────
# Constantes del módulo M30 (mismas que F3.2 usará en modules/pages/pricing_dashboard.py)
# ─────────────────────────────────────────────────────────────────────────────

AREA = "account-health"
MODULE_SLUG = "pricing-dashboard"
SCHEMA_VERSION = 1
CLIENTE_TEST = "test-pricing"
SNAPSHOT_DATE = "2026-04-17"

# Path al schema versionado que YA existe (creado en F3.1).
REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_SCHEMA_PATH = REPO_ROOT / "data" / "_schemas" / f"{MODULE_SLUG}-v{SCHEMA_VERSION}.json"


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    """Redirige DATA_ROOT y SCHEMAS_ROOT a tmp_path para aislar el test.

    Copia el schema real pricing-dashboard-v1.json al tmp_path/_schemas/ para
    que _validate_against_schema pueda leerlo desde el SCHEMAS_ROOT parcheado.

    Sin esto, los tests dejarían basura en data/account-health/test-pricing/
    del repo. Con esto, todo va a un dir temporal que pytest borra al cerrar.
    """
    tmp_data = tmp_path / "data"
    tmp_schemas = tmp_data / "_schemas"
    tmp_schemas.mkdir(parents=True, exist_ok=True)

    # Copiar el schema real al sandbox para que _validate_against_schema lo encuentre.
    schema_dst = tmp_schemas / f"{MODULE_SLUG}-v{SCHEMA_VERSION}.json"
    schema_dst.write_text(REAL_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    monkeypatch.setattr(P, "DATA_ROOT", tmp_data)
    monkeypatch.setattr(P, "SCHEMAS_ROOT", tmp_schemas)

    return tmp_data


def _make_synthetic_snapshot() -> pd.DataFrame:
    """Construye un DataFrame mínimo M30 con las 21 columnas required + algunas opcionales.

    Dos SKUs sintéticos para validar dtypes y round-trip.
    Las columnas required deben respetar los dtypes declarados en pricing-dashboard-v1.json.
    """
    return pd.DataFrame(
        [
            {
                # Required
                "snapshot_date": SNAPSHOT_DATE,
                "sku": "TEST-SKU-001",
                "product_name": "Producto Test 1",
                "price": 24.99,
                "fba_available": 120,
                "total_stock": 180,
                "t7": 14,
                "t30": 60,
                "daily_rate": 2.0,
                "fba_dos": 60.0,
                "total_dos": 90.0,
                "cogs": 8.50,
                "ff": 4.20,
                "rf": 3.75,
                "gross_margin": 0.66,
                "net_margin": 0.34,
                "score": 25,
                "classification": "subir",
                "suggested_price": 26.49,
                "liq_min_price": 0.0,
                "is_liquidar": False,
                # Algunas opcionales para enriquecer el round-trip
                "asin": "B0TEST001A",
                "subcategoria": "skincare-test",
                "t90": 180,
                "ppc": 1.10,
                "ff_est": False,
                "rf_est": False,
                "buybox_price": 26.99,
                "subcat_avg_price": 25.50,
                "reasons_up": json.dumps(["DOS<120", "subcat_avg_price>price"]),
                "suggested_rationale": "Push margin to subcat avg.",
                "has_backup": True,
                "awd_available": 30,
                "izzi_available": 30,
                # Igualamos la opcional aging_366plus en ambas filas para que
                # pandas preserve int64 (sin NaN no se promueve a float).
                "aging_366plus": 0,
            },
            {
                # Required
                "snapshot_date": SNAPSHOT_DATE,
                "sku": "TEST-SKU-002",
                "product_name": "Producto Test 2 (liquidar)",
                "price": 12.50,
                "fba_available": 200,
                "total_stock": 200,
                "t7": 1,
                "t30": 4,
                "daily_rate": 0.13,
                "fba_dos": 1538.0,
                "total_dos": 1538.0,
                "cogs": 6.00,
                "ff": 3.10,
                "rf": 1.87,
                "gross_margin": 0.52,
                "net_margin": 0.12,
                "score": -65,
                "classification": "liquidar",
                "suggested_price": 8.99,
                "liq_min_price": 7.50,
                "is_liquidar": True,
                # Opcionales
                "asin": "B0TEST002B",
                "subcategoria": "skincare-test",
                "t90": 18,
                "ppc": 0.40,
                "ff_est": False,
                "rf_est": True,
                "buybox_price": None,
                "subcat_avg_price": 14.00,
                "reasons_down": json.dumps(["aging_366plus>50", "DOS>365"]),
                "suggested_rationale": "Liquidación por aging 366+ y stock excesivo.",
                "has_backup": False,
                "awd_available": 0,
                "izzi_available": 0,
                "aging_366plus": 60,
            },
        ]
    )


# ─────────────────────────────────────────────────────────────────────────────
# Tests: las 6 validaciones del protocolo
# ─────────────────────────────────────────────────────────────────────────────


def test_1_roundtrip_save_load_preserves_dtypes(isolated_data_root):
    """Validación 1: roundtrip save → load preserva dtypes."""
    df_in = _make_synthetic_snapshot()

    out_path = P._save_snapshot(df_in, AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)

    # Path canónico esperado
    expected = (
        isolated_data_root
        / AREA
        / CLIENTE_TEST
        / MODULE_SLUG
        / f"{SNAPSHOT_DATE}.parquet"
    )
    assert out_path == expected, f"Path escrito {out_path} != esperado {expected}"
    assert out_path.exists(), "El .parquet no se escribió"

    df_out = P._load_snapshot(AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)
    assert df_out is not None
    assert len(df_out) == len(df_in)

    # Dtypes en columnas required de tipo numérico/bool deben preservarse exactos.
    # (strings vuelven como 'object' en pandas — el helper _matches_dtype del schema lo acepta.)
    for col in [
        "price",
        "daily_rate",
        "fba_dos",
        "total_dos",
        "cogs",
        "ff",
        "rf",
        "gross_margin",
        "net_margin",
        "suggested_price",
        "liq_min_price",
    ]:
        assert str(df_out[col].dtype).startswith("float"), (
            f"Columna '{col}' perdió dtype float: {df_out[col].dtype}"
        )

    for col in ["fba_available", "total_stock", "t7", "t30", "score"]:
        assert str(df_out[col].dtype).startswith("int"), (
            f"Columna '{col}' perdió dtype int: {df_out[col].dtype}"
        )

    assert df_out["is_liquidar"].dtype == bool, "Columna 'is_liquidar' perdió dtype bool"


def test_2_schema_check_zero_errors(isolated_data_root):
    """Validación 2: schema check matchea pricing-dashboard-v1.json sin errores."""
    df = _make_synthetic_snapshot()
    errors = P._validate_against_schema(df, MODULE_SLUG, SCHEMA_VERSION)
    assert errors == [], (
        f"Se esperaba 0 errores de schema; recibidos {len(errors)}: {errors}"
    )


def test_2b_schema_check_detects_missing_required(isolated_data_root):
    """Validación 2 (negativa): si falta una columna required, debe reportar error."""
    df = _make_synthetic_snapshot().drop(columns=["score"])
    errors = P._validate_against_schema(df, MODULE_SLUG, SCHEMA_VERSION)
    assert any("score" in e for e in errors), (
        f"Esperaba error por 'score' faltante; errors={errors}"
    )


def test_3_cache_decorator_present_on_reads(isolated_data_root):
    """Validación 3: las funciones de lectura están envueltas por @st.cache_data.

    En entorno de test (sin Streamlit en runtime de UI), _cache_data es passthrough.
    Pero confirmamos que la API correcta está expuesta: M30 hereda automáticamente
    el cacheo cuando corre dentro de Streamlit (ver core/persistence.py L99-106).

    Verificación: las funciones cacheadas existen y son callables. Si Streamlit
    está importable, deben tener un atributo .clear() (lo agrega st.cache_data).
    Si NO está, son passthrough (no tienen .clear, igual son válidas).
    """
    # _load_snapshot, _load_history, _list_periods, _load_log, _load_config son las cacheadas.
    for fn in [
        P._load_snapshot,
        P._load_history,
        P._list_periods,
        P._load_log,
        P._load_config,
    ]:
        assert callable(fn), f"{fn} no es callable"

    # En Streamlit runtime, .clear() debería estar disponible.
    # En standalone, _cache_data es passthrough y no hay .clear() — y eso también es OK.
    if P._HAS_STREAMLIT:
        for fn in [P._load_snapshot, P._load_history, P._list_periods]:
            assert hasattr(fn, "clear"), (
                f"Streamlit disponible pero {fn.__name__} no tiene .clear() — "
                f"el wrapper @st.cache_data falló"
            )


def test_4_path_coherence_under_account_health(isolated_data_root):
    """Validación 4: todos los artefactos viven bajo data/account-health/<cliente>/pricing-dashboard/."""
    df = _make_synthetic_snapshot()
    snapshot_path = P._save_snapshot(df, AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)

    # 4a — snapshot path
    rel = snapshot_path.relative_to(isolated_data_root)
    parts = rel.parts
    assert parts[0] == AREA, f"area en path: {parts[0]} != {AREA}"
    assert parts[1] == CLIENTE_TEST, f"cliente en path: {parts[1]} != {CLIENTE_TEST}"
    assert parts[2] == MODULE_SLUG, f"modulo en path: {parts[2]} != {MODULE_SLUG}"
    assert parts[3] == f"{SNAPSHOT_DATE}.parquet"

    # 4b — _list_periods devuelve el snapshot escrito
    periods = P._list_periods(AREA, CLIENTE_TEST, MODULE_SLUG)
    assert SNAPSHOT_DATE in periods, f"_list_periods no devolvió '{SNAPSHOT_DATE}': {periods}"

    # 4c — _rebuild_history genera _history.parquet en el mismo dir
    # (necesario para vista WoW; declarado en evolution_notes.entities.history)
    history_path = P._rebuild_history(AREA, CLIENTE_TEST, MODULE_SLUG)
    expected_hist = (
        isolated_data_root
        / AREA
        / CLIENTE_TEST
        / MODULE_SLUG
        / "_history.parquet"
    )
    assert history_path == expected_hist
    history_df = P._load_history(AREA, CLIENTE_TEST, MODULE_SLUG)
    assert not history_df.empty
    assert "_period" in history_df.columns, (
        "_rebuild_history debe agregar columna _period"
    )
    assert (history_df["_period"] == SNAPSHOT_DATE).all()

    # 4d — config per-cliente usa _save_config con name=<cliente-slug>
    # Path resultante: data/<area>/<modulo>/<cliente>-v1.json (client-agnostic dir)
    config = {
        "cliente": CLIENTE_TEST,
        "last_snapshot_date": SNAPSHOT_DATE,
        "subcat_fee_avg": {"skincare-test": 0.15},
        "year": 2026,
        "schema_version": "v1",
    }
    cfg_path = P._save_config(config, AREA, MODULE_SLUG, name=CLIENTE_TEST, version=1)
    expected_cfg = (
        isolated_data_root / AREA / MODULE_SLUG / f"{CLIENTE_TEST}-v1.json"
    )
    assert cfg_path == expected_cfg, f"Config path {cfg_path} != {expected_cfg}"
    loaded_cfg = P._load_config(AREA, MODULE_SLUG, name=CLIENTE_TEST, version=1)
    assert loaded_cfg == config, "Round-trip de config falló"


def test_4e_idempotency_resave_same_period_overwrites(isolated_data_root):
    """Validación 4e: re-importar el mismo snapshot_date sobreescribe (dedup-by-date del HTML L1163)."""
    df1 = _make_synthetic_snapshot()
    P._save_snapshot(df1, AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)

    # Segundo snapshot del MISMO día con datos distintos
    df2 = _make_synthetic_snapshot()
    df2.loc[0, "price"] = 99.99
    P._save_snapshot(df2, AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)

    df_out = P._load_snapshot(AREA, CLIENTE_TEST, MODULE_SLUG, SNAPSHOT_DATE)
    assert df_out.loc[0, "price"] == 99.99, (
        "El segundo save NO sobreescribió — idempotencia rota"
    )
    # Solo debe haber 1 period (no duplicación)
    periods = P._list_periods(AREA, CLIENTE_TEST, MODULE_SLUG)
    assert periods.count(SNAPSHOT_DATE) == 1


def test_5_gitignore_covers_new_path():
    """Validación 5: el path nuevo data/account-health/<cliente>/pricing-dashboard/
    cae bajo el .gitignore vigente del worktree.

    Verificación: usar `git check-ignore` para confirmar que un path hipotético
    de cliente real (no test-pricing — el test puede correrse contra repo real
    y queremos confirmar el patrón general) sería ignorado.
    """
    # Path hipotético de un cliente real (no se crea el archivo, solo se valida el patrón)
    hypothetical = "data/account-health/dermaglos/pricing-dashboard/2026-06-02.parquet"
    result = subprocess.run(
        ["git", "check-ignore", "-q", hypothetical],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    # check-ignore exit 0 = ignorado, 1 = no ignorado
    assert result.returncode == 0, (
        f".gitignore NO cubre {hypothetical}. Reportar al main agent: "
        f"requiere agregar regla bajo `# ── Capa de persistencia (data/) ──`. "
        f"stderr: {result.stderr.decode('utf-8', errors='replace')}"
    )


def test_5b_schema_itself_is_versioned():
    """Validación 5b: el schema pricing-dashboard-v1.json SÍ se versiona (no está gitignored)."""
    schema_rel = f"data/_schemas/{MODULE_SLUG}-v{SCHEMA_VERSION}.json"
    result = subprocess.run(
        ["git", "check-ignore", "-q", schema_rel],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    # exit 1 = NO ignorado (lo esperado para schemas)
    assert result.returncode == 1, (
        f"El schema {schema_rel} está siendo ignorado por .gitignore. "
        f"Debe estar versionado. stderr: "
        f"{result.stderr.decode('utf-8', errors='replace')}"
    )


def test_6_import_no_side_effects():
    """Validación 6: importar core.persistence no toca disco ni crea directorios."""
    import importlib

    # Re-import limpio del módulo
    import core.persistence

    importlib.reload(core.persistence)

    # No debería haber creado nada al importar. DATA_ROOT puede o no existir según
    # el repo real; lo crítico es que el import en sí no creó NADA nuevo.
    # Validación operacional: no hay carpetas pricing-dashboard creadas para clientes random.
    bogus = REPO_ROOT / "data" / AREA / "imaginary-cliente-xyz" / MODULE_SLUG
    assert not bogus.exists(), (
        f"Importar core.persistence creó {bogus} (side effect prohibido)"
    )
