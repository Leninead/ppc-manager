"""Tests del backend Supabase para Account Health (core/persistence.py, Bloque 2/3).

CERO RED, CERO secrets.toml real:
- `_SupabaseBackend` se prueba con un fake transport en memoria inyectado
  (`_FakeTransport`) que replica la semántica PostgREST que usamos: filtro `eq`
  EXACTO y `post(upsert=True)` con merge-duplicates por PK.
- El selector `_get_backend()` se prueba monkeypatcheando env (y, para la rama
  "sin creds", `_storage_config` directo, porque el secrets.toml vivo del repo
  entregaría creds reales y rompería el determinismo).

Aislamiento del singleton: una fixture autouse resetea `_BACKEND` antes y después
de cada test de ESTE módulo, para que ninguna instancia Supabase con transport
real se filtre a otros tests de la suite.
"""

from __future__ import annotations

import json

import pandas as pd
import pandas.testing as pt
import pytest

from core import persistence as P


# ─────────────────────────────────────────────────────────────────────────────
# Fake transport PostgREST en memoria (eq exacto + upsert merge-duplicates)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeTransport:
    """Replica en memoria la porción de PostgREST que usa `_SupabaseBackend`.

    - `post(table, rows, upsert=True)`: guarda por PK; si la PK ya existe, la
      reemplaza (merge-duplicates).
    - `get(table, params)`: aplica filtros `eq.<valor>` por igualdad EXACTA de
      string (NO substring/prefijo) + `limit`. Ignora `select`/`order`/`offset`.
    """

    _PK = {
        P._SNAPSHOTS_TABLE: ("area", "cliente", "modulo", "period"),
        P._CONFIGS_TABLE: ("area", "modulo", "name", "version"),
    }
    _NON_FILTER = {"select", "limit", "order", "offset"}

    def __init__(self):
        self.tables: dict[str, dict[tuple, dict]] = {
            P._SNAPSHOTS_TABLE: {},
            P._CONFIGS_TABLE: {},
        }

    def _pk(self, table: str, row: dict) -> tuple:
        return tuple(row[c] for c in self._PK[table])

    def post(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        store = self.tables[table]
        out = []
        for row in rows:
            pk = self._pk(table, row)
            store[pk] = dict(row)  # upsert: reemplaza la fila con misma PK
            out.append(dict(row))
        return out

    def get(self, table: str, params: dict) -> list[dict]:
        rows = list(self.tables[table].values())
        limit = None
        for key, raw in params.items():
            if key in self._NON_FILTER:
                if key == "limit":
                    limit = int(raw)
                continue
            op, _, target = str(raw).partition(".")
            assert op == "eq", f"_FakeTransport solo soporta eq, recibido {raw!r}"
            # Igualdad EXACTA (replica eq de PostgREST; period con guiones como
            # '2026-W18' NO debe matchear '2026-W1' por prefijo).
            rows = [r for r in rows if str(r.get(key)) == target]
        if limit is not None:
            rows = rows[:limit]
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

AREA = "account-health"
CLIENTE = "test-supa"


@pytest.fixture(autouse=True)
def _reset_backend_singleton():
    """Resetea el singleton `_BACKEND` antes y después de cada test de este módulo.

    Evita que una instancia `_SupabaseBackend` (con transport real) construida por
    un test del selector se filtre al resto de la suite.
    """
    P._set_backend_for_testing(None)
    yield
    P._set_backend_for_testing(None)


@pytest.fixture
def backend():
    """`_SupabaseBackend` con fake transport — cero red."""
    return P._SupabaseBackend(transport=_FakeTransport())


# ─────────────────────────────────────────────────────────────────────────────
# Builders de DataFrames sintéticos
# ─────────────────────────────────────────────────────────────────────────────

# 47 columnas del schema pricing-dashboard-v1 (M30), en orden.
_M30_COLUMNS = [
    "snapshot_date", "sku", "asin", "product_name", "modelo", "talla", "temporada",
    "categoria", "subcategoria", "price", "fba_available", "awd_available",
    "izzi_available", "total_stock", "has_backup", "t7", "t30", "t90", "daily_rate",
    "fba_dos", "total_dos", "cogs", "ff", "rf", "ppc", "ff_est", "rf_est",
    "gross_margin", "net_margin", "aging_181_270", "aging_271_365", "aging_366plus",
    "ais_total", "health", "no_sale", "buybox_price", "subcat_avg_price",
    "model_avg_price", "score", "classification", "reasons_down", "reasons_up",
    "suggested_price", "suggested_rationale", "restock_alert", "liq_min_price",
    "is_liquidar",
]


def _make_m30_snapshot() -> pd.DataFrame:
    """DataFrame M30 de 47 columnas con dtypes variados (int/float/str/bool).

    La 2da fila incluye NaN en columnas FLOAT (ais_total, buybox_price,
    model_avg_price) Y None en columnas OBJECT (asin, health, no_sale, reasons_up,
    suggested_rationale, restock_alert) en la MISMA fila → valida que
    orient='table' no pierde fidelidad con nulls float/object mezclados.
    Las columnas int/bool quedan valuadas en ambas filas (sin nulls) para que
    pandas preserve int64/bool (NaN promovería int→float).
    """
    row1 = {
        "snapshot_date": "2026-04-17", "sku": "SKU-1", "asin": "B0AAA",
        "product_name": "Producto 1", "modelo": "M1", "talla": "L",
        "temporada": "verano", "categoria": "cat", "subcategoria": "sub",
        "price": 24.99, "fba_available": 120, "awd_available": 30,
        "izzi_available": 30, "total_stock": 180, "has_backup": True,
        "t7": 14, "t30": 60, "t90": 180, "daily_rate": 2.0, "fba_dos": 60.0,
        "total_dos": 90.0, "cogs": 8.5, "ff": 4.2, "rf": 3.75, "ppc": 1.1,
        "ff_est": False, "rf_est": False, "gross_margin": 0.66, "net_margin": 0.34,
        "aging_181_270": 0, "aging_271_365": 0, "aging_366plus": 0,
        "ais_total": 87.5, "health": "green", "no_sale": "",
        "buybox_price": 26.99, "subcat_avg_price": 25.5, "model_avg_price": 24.0,
        "score": 25, "classification": "subir",
        "reasons_down": json.dumps([]), "reasons_up": json.dumps(["subcat_avg>price"]),
        "suggested_price": 26.49, "suggested_rationale": "Push margin",
        "restock_alert": "", "liq_min_price": 0.0, "is_liquidar": False,
    }
    row2 = {
        "snapshot_date": "2026-04-17", "sku": "SKU-2", "asin": None,
        "product_name": "Producto 2", "modelo": "M2", "talla": "S",
        "temporada": "invierno", "categoria": "cat", "subcategoria": "sub",
        "price": 12.5, "fba_available": 200, "awd_available": 0,
        "izzi_available": 0, "total_stock": 200, "has_backup": False,
        "t7": 1, "t30": 4, "t90": 18, "daily_rate": 0.13, "fba_dos": 1538.0,
        "total_dos": 1538.0, "cogs": 6.0, "ff": 3.1, "rf": 1.87, "ppc": 0.4,
        "ff_est": False, "rf_est": True, "gross_margin": 0.52, "net_margin": 0.12,
        "aging_181_270": 0, "aging_271_365": 0, "aging_366plus": 60,
        "ais_total": float("nan"), "health": None, "no_sale": None,
        "buybox_price": float("nan"), "subcat_avg_price": 14.0,
        "model_avg_price": float("nan"), "score": -65, "classification": "liquidar",
        "reasons_down": json.dumps(["aging_366plus>50"]), "reasons_up": None,
        "suggested_price": 8.99, "suggested_rationale": None,
        "restock_alert": None, "liq_min_price": 7.5, "is_liquidar": True,
    }
    df = pd.DataFrame([row1, row2], columns=_M30_COLUMNS)
    return df


def _make_m28_snapshot() -> pd.DataFrame:
    """DataFrame estilo M28 sku-progress (15 columnas), todas valuadas."""
    return pd.DataFrame(
        [
            {
                "sku": "SKU-A", "asin": "B0A", "title": "Prod A",
                "image_url": "http://img/a.jpg", "link": "http://az/a",
                "week_iso": 14, "year": 2026, "week_label": "Mar 29-Abr 4",
                "sessions": 1000, "page_views": 1500, "units_ordered": 30,
                "total_order_items": 30, "unit_session_pct": 3.0,
                "ordered_product_sales": 600.0, "avg_price": 20.0,
            },
            {
                "sku": "SKU-B", "asin": "B0B", "title": "Prod B",
                "image_url": "http://img/b.jpg", "link": "http://az/b",
                "week_iso": 14, "year": 2026, "week_label": "Mar 29-Abr 4",
                "sessions": 500, "page_views": 700, "units_ordered": 10,
                "total_order_items": 10, "unit_session_pct": 2.0,
                "ordered_product_sales": 250.0, "avg_price": 25.0,
            },
        ]
    )


def _assert_roundtrip(out: pd.DataFrame, expected: pd.DataFrame) -> None:
    """Compara round-trip tolerante a dtype + None↔NaN.

    Estrategia: comparar máscaras isna() (posiciones de nulls preservadas) +
    valores no-nulos por separado. Evita el FutureWarning de pandas por comparar
    nan vs None en object, y es una aserción MÁS fuerte (afirma explícitamente la
    preservación de nulls).
    """
    out = out.reset_index(drop=True)
    expected = expected.reset_index(drop=True)
    assert list(out.columns) == list(expected.columns), "columnas/orden difieren"
    assert len(out) == len(expected), "cantidad de filas difiere"
    for col in expected.columns:
        assert out[col].isna().tolist() == expected[col].isna().tolist(), (
            f"posiciones de null difieren en '{col}'"
        )
        exp_nn = expected[col][expected[col].notna()].reset_index(drop=True)
        out_nn = out[col][out[col].notna()].reset_index(drop=True)
        pt.assert_series_equal(out_nn, exp_nn, check_dtype=False, check_names=False)


# ─────────────────────────────────────────────────────────────────────────────
# Round-trip de snapshots (serialización orient="table")
# ─────────────────────────────────────────────────────────────────────────────


def test_roundtrip_m30_47cols_with_mixed_nulls(backend):
    """Round-trip 47 cols con fila de NaN(float)+None(object) mezclados."""
    df_in = _make_m30_snapshot()
    assert df_in.shape[1] == 47, "el builder M30 debe tener 47 columnas"
    # Precondición: la fila 2 tiene null float Y null object simultáneamente.
    assert pd.isna(df_in.loc[1, "buybox_price"])  # float NaN
    assert df_in.loc[1, "asin"] is None  # object None

    backend.save_snapshot(df_in, AREA, CLIENTE, "pricing-dashboard", "2026-04-17")
    df_out = backend.load_snapshot(AREA, CLIENTE, "pricing-dashboard", "2026-04-17")

    assert df_out is not None
    _assert_roundtrip(df_out, df_in)

    # Fidelidad de dtype explícita (lo que valida orient="table").
    df_out = df_out.reset_index(drop=True)
    assert str(df_out["price"].dtype).startswith("float")
    assert str(df_out["buybox_price"].dtype).startswith("float")  # NaN no rompió float
    assert str(df_out["fba_available"].dtype).startswith("int")
    assert str(df_out["score"].dtype).startswith("int")
    assert df_out["is_liquidar"].dtype == bool
    assert df_out["asin"].dtype == object  # None no rompió object


def test_roundtrip_m28_15cols(backend):
    """Round-trip de un snapshot estilo M28 (15 cols)."""
    df_in = _make_m28_snapshot()
    assert df_in.shape[1] == 15
    backend.save_snapshot(df_in, AREA, CLIENTE, "sku-progress", "2026-W14")
    df_out = backend.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14")
    assert df_out is not None
    _assert_roundtrip(df_out, df_in)


def test_load_snapshot_inexistente_devuelve_none(backend):
    assert backend.load_snapshot(AREA, CLIENTE, "pricing-dashboard", "2099-W01") is None


def test_save_snapshot_idempotente_por_period(backend):
    """Re-guardar el mismo period sobreescribe (upsert merge-duplicates por PK)."""
    df1 = _make_m28_snapshot()
    backend.save_snapshot(df1, AREA, CLIENTE, "sku-progress", "2026-W14")
    df2 = _make_m28_snapshot()
    df2.loc[0, "avg_price"] = 99.99
    backend.save_snapshot(df2, AREA, CLIENTE, "sku-progress", "2026-W14")

    out = backend.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14")
    assert out.reset_index(drop=True).loc[0, "avg_price"] == 99.99
    assert backend.list_periods(AREA, CLIENTE, "sku-progress").count("2026-W14") == 1


# ─────────────────────────────────────────────────────────────────────────────
# Filtro eq EXACTO sobre period con guiones (no match laxo)
# ─────────────────────────────────────────────────────────────────────────────


def _mini(marker: str) -> pd.DataFrame:
    return pd.DataFrame([{"sku": marker, "price": 1.0}])


def test_period_eq_filter_es_exacto_no_prefijo(backend):
    """'2026-W18' NO debe resolver a '2026-W1' (prefijo) — eq exacto PostgREST."""
    backend.save_snapshot(_mini("W1"), AREA, CLIENTE, "m", "2026-W1")
    backend.save_snapshot(_mini("W18"), AREA, CLIENTE, "m", "2026-W18")
    backend.save_snapshot(_mini("DATE"), AREA, CLIENTE, "m", "2026-04-17")

    out18 = backend.load_snapshot(AREA, CLIENTE, "m", "2026-W18")
    out1 = backend.load_snapshot(AREA, CLIENTE, "m", "2026-W1")
    outd = backend.load_snapshot(AREA, CLIENTE, "m", "2026-04-17")
    assert out18.reset_index(drop=True).loc[0, "sku"] == "W18"
    assert out1.reset_index(drop=True).loc[0, "sku"] == "W1"
    assert outd.reset_index(drop=True).loc[0, "sku"] == "DATE"

    assert backend.list_periods(AREA, CLIENTE, "m") == ["2026-04-17", "2026-W1", "2026-W18"]


# ─────────────────────────────────────────────────────────────────────────────
# History (derivado: concat de snapshots, no almacenado)
# ─────────────────────────────────────────────────────────────────────────────


def test_load_history_concatena_con_period(backend):
    backend.save_snapshot(_mini("a"), AREA, CLIENTE, "m", "2026-W10")
    backend.save_snapshot(_mini("b"), AREA, CLIENTE, "m", "2026-W11")
    backend.save_snapshot(_mini("c"), AREA, CLIENTE, "m", "2026-W12")

    hist = backend.load_history(AREA, CLIENTE, "m")
    assert len(hist) == 3
    assert "_period" in hist.columns
    assert sorted(hist["_period"].tolist()) == ["2026-W10", "2026-W11", "2026-W12"]
    # cada fila lleva su marcador correcto
    by_period = dict(zip(hist["_period"], hist["sku"]))
    assert by_period == {"2026-W10": "a", "2026-W11": "b", "2026-W12": "c"}


def test_load_history_vacio_devuelve_df_vacio(backend):
    hist = backend.load_history(AREA, CLIENTE, "m")
    assert isinstance(hist, pd.DataFrame)
    assert hist.empty


def test_rebuild_history_sin_snapshots_raise(backend):
    with pytest.raises(FileNotFoundError):
        backend.rebuild_history(AREA, CLIENTE, "m")


def test_rebuild_history_con_snapshots_devuelve_sentinel(backend):
    backend.save_snapshot(_mini("a"), AREA, CLIENTE, "m", "2026-W10")
    out = backend.rebuild_history(AREA, CLIENTE, "m")
    # No persiste: devuelve un pseudo-path informativo supabase://...
    # (en Windows, Path() colapsa '//' y usa backslashes, así que no se puede
    # asertar el prefijo literal; basta confirmar el marcador 'supabase').
    assert "supabase" in str(out)
    assert not out.exists()  # el sentinel no corresponde a un archivo real


# ─────────────────────────────────────────────────────────────────────────────
# Config round-trip
# ─────────────────────────────────────────────────────────────────────────────


def test_save_load_config_roundtrip(backend):
    cfg = {
        "cliente": CLIENTE,
        "last_snapshot_date": "2026-04-17",
        "subcat_fee_avg": {"skincare-test": 0.15},
        "year": 2026,
        "schema_version": "v1",
    }
    backend.save_config(cfg, AREA, "pricing-dashboard", name=CLIENTE, version=1)
    loaded = backend.load_config(AREA, "pricing-dashboard", name=CLIENTE, version=1)
    assert loaded == cfg


def test_load_config_inexistente_devuelve_dict_vacio(backend):
    assert backend.load_config(AREA, "pricing-dashboard", name="nope", version=1) == {}


# ─────────────────────────────────────────────────────────────────────────────
# Unit del fake transport (lockea su semántica PostgREST)
# ─────────────────────────────────────────────────────────────────────────────


def test_fake_transport_upsert_merge_duplicates_por_pk():
    t = _FakeTransport()
    t.post(P._CONFIGS_TABLE, [{"area": "a", "modulo": "m", "name": "n",
                               "version": 1, "data": {"v": 1}}], upsert=True)
    t.post(P._CONFIGS_TABLE, [{"area": "a", "modulo": "m", "name": "n",
                               "version": 1, "data": {"v": 2}}], upsert=True)
    rows = t.get(P._CONFIGS_TABLE, {"area": "eq.a", "modulo": "eq.m",
                                    "name": "eq.n", "version": "eq.1", "select": "data"})
    assert len(rows) == 1 and rows[0]["data"] == {"v": 2}


def test_fake_transport_eq_es_exacto():
    t = _FakeTransport()
    t.post(P._SNAPSHOTS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                                 "period": "2026-W1", "data": "x"}], upsert=True)
    t.post(P._SNAPSHOTS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                                 "period": "2026-W18", "data": "y"}], upsert=True)
    rows = t.get(P._SNAPSHOTS_TABLE, {"area": "eq.a", "cliente": "eq.c",
                                      "modulo": "eq.m", "period": "eq.2026-W18"})
    assert len(rows) == 1 and rows[0]["data"] == "y"


# ─────────────────────────────────────────────────────────────────────────────
# Selector _get_backend() — 3 ramas (monkeypatch env, determinista, sin red)
# ─────────────────────────────────────────────────────────────────────────────


def test_selector_sin_creds_devuelve_local(monkeypatch):
    """(a) Sin creds → Local, incluso con el flag en 'supabase'.

    Se monkeypatchea `_storage_config`→None porque el secrets.toml vivo del repo
    entregaría creds reales por el fallback a st.secrets (rompería determinismo).
    """
    monkeypatch.setattr(P, "_storage_config", lambda: None)
    monkeypatch.setenv("AGENCY_OS_AH_BACKEND", "supabase")
    assert isinstance(P._get_backend(), P._LocalBackend)


def test_selector_creds_sin_flag_devuelve_local(monkeypatch):
    """(b) Creds presentes + sin flag (flag != 'supabase') → Local."""
    monkeypatch.setenv("SUPABASE_URL", "https://dummy.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy-key")
    monkeypatch.setenv("AGENCY_OS_AH_BACKEND", "local")
    # sanity: hay creds por env
    assert P._storage_config() == ("https://dummy.supabase.co", "dummy-key")
    assert P._supabase_opt_in() is False
    assert isinstance(P._get_backend(), P._LocalBackend)


def test_selector_creds_con_flag_devuelve_supabase(monkeypatch):
    """(c) Creds + flag == 'supabase' → Supabase (transport real construido pero
    SIN llamadas de red: isinstance no dispara get/post)."""
    monkeypatch.setenv("SUPABASE_URL", "https://dummy.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "dummy-key")
    monkeypatch.setenv("AGENCY_OS_AH_BACKEND", "supabase")
    assert P._supabase_opt_in() is True
    assert isinstance(P._get_backend(), P._SupabaseBackend)


def test_backend_flag_env_gana_y_normaliza(monkeypatch):
    """El flag por env gana y se normaliza (lowercase/strip)."""
    monkeypatch.setenv("AGENCY_OS_AH_BACKEND", "  SuPaBaSe  ")
    assert P._backend_flag() == "supabase"
    assert P._supabase_opt_in() is True

    monkeypatch.setenv("AGENCY_OS_AH_BACKEND", "")
    assert P._backend_flag() == ""
    assert P._supabase_opt_in() is False


def test_storage_config_env_primero(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
    monkeypatch.setenv("SUPABASE_KEY", "k")
    assert P._storage_config() == ("https://x.supabase.co", "k")
