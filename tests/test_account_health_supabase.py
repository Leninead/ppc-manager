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

    Dos tipos de store según la tabla:
    - Tablas con PK (`ah_snapshots`, `ah_configs`) → dict[pk_tuple, row]. `post`
      hace merge-duplicates por PK (upsert).
    - Tabla append-only sin PK (`ah_logs`) → list. `post` APENDA (NO mergea) y
      asigna un surrogate `id` incremental si la fila no lo trae.

    `get`/`delete` aplican filtros `eq.<valor>` por igualdad EXACTA de string (NO
    substring/prefijo). Ignoran `select`/`limit`/`order`/`offset`.
    """

    _PK = {
        P._SNAPSHOTS_TABLE: ("area", "cliente", "modulo", "period"),
        P._CONFIGS_TABLE: ("area", "modulo", "name", "version"),
        P._CLIENT_CONFIGS_TABLE: ("area", "cliente", "modulo", "name"),
    }
    _NON_FILTER = {"select", "limit", "order", "offset"}

    def __init__(self):
        self.tables = {
            P._SNAPSHOTS_TABLE: {},        # dict por PK
            P._CONFIGS_TABLE: {},          # dict por PK
            P._CLIENT_CONFIGS_TABLE: {},   # dict por PK (con dimensión cliente)
            P._LOGS_TABLE: [],             # list append-only (sin PK)
        }
        self._log_seq = 0

    def _pk(self, table: str, row: dict) -> tuple:
        return tuple(row[c] for c in self._PK[table])

    def _rows(self, table: str) -> list[dict]:
        store = self.tables[table]
        return list(store.values()) if isinstance(store, dict) else list(store)

    def _matches(self, row: dict, params: dict) -> bool:
        for key, raw in params.items():
            if key in self._NON_FILTER:
                continue
            op, _, target = str(raw).partition(".")
            assert op == "eq", f"_FakeTransport solo soporta eq, recibido {raw!r}"
            # Igualdad EXACTA (replica eq de PostgREST; period con guiones como
            # '2026-W18' NO debe matchear '2026-W1' por prefijo).
            if str(row.get(key)) != target:
                return False
        return True

    def post(self, table: str, rows: list[dict], upsert: bool = False) -> list[dict]:
        store = self.tables[table]
        out = []
        for row in rows:
            if isinstance(store, dict):
                pk = self._pk(table, row)
                store[pk] = dict(row)  # upsert: reemplaza la fila con misma PK
                out.append(dict(row))
            else:
                # append-only (logs): NUNCA mergea; asigna surrogate id si falta
                r = dict(row)
                if "id" not in r:
                    self._log_seq += 1
                    r["id"] = self._log_seq
                store.append(r)
                out.append(dict(r))
        return out

    def get(self, table: str, params: dict) -> list[dict]:
        rows = [r for r in self._rows(table) if self._matches(r, params)]
        limit = params.get("limit")
        if limit is not None:
            rows = rows[: int(limit)]
        return [dict(r) for r in rows]

    def delete(self, table: str, params: dict) -> list[dict]:
        """Borra las filas que matchean TODOS los filtros `eq` (igualdad exacta).

        Devuelve la lista de filas borradas (replica `Prefer: return=representation`
        del transport real). Soporta store dict (por PK) y list (append-only).
        """
        store = self.tables[table]
        if isinstance(store, dict):
            deleted = []
            for pk in list(store.keys()):
                if self._matches(store[pk], params):
                    deleted.append(dict(store.pop(pk)))
            return deleted
        # list store (logs): conservar las que NO matchean
        deleted = [dict(r) for r in store if self._matches(r, params)]
        store[:] = [r for r in store if not self._matches(r, params)]
        return deleted


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


# ─────────────────────────────────────────────────────────────────────────────
# Borrados — _LocalBackend (tmp_path + monkeypatch DATA_ROOT, cero disco real)
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def local_backend(tmp_path, monkeypatch):
    """`_LocalBackend` apuntando a un DATA_ROOT temporal (no toca el repo)."""
    monkeypatch.setattr(P, "DATA_ROOT", tmp_path)
    return P._LocalBackend()


def test_local_delete_snapshot(local_backend):
    lb = local_backend
    lb.save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, "sku-progress", "2026-W14")
    assert lb.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is not None
    # existía → True, y ya no está
    assert lb.delete_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is True
    assert lb.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is None
    # borrar inexistente → False
    assert lb.delete_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is False


def test_local_delete_history(local_backend):
    lb = local_backend
    lb.save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, "sku-progress", "2026-W14")
    lb.rebuild_history(AREA, CLIENTE, "sku-progress")
    assert not lb.load_history(AREA, CLIENTE, "sku-progress").empty
    assert lb.delete_history(AREA, CLIENTE, "sku-progress") is True
    assert lb.load_history(AREA, CLIENTE, "sku-progress").empty
    # borrar inexistente → False
    assert lb.delete_history(AREA, CLIENTE, "sku-progress") is False


def test_local_delete_cliente_acotado_al_modulo(local_backend):
    """delete_cliente borra SOLO el dir del módulo; un módulo hermano del mismo
    cliente SOBREVIVE (no es cross-módulo)."""
    lb = local_backend
    lb.save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, "sku-progress", "2026-W14")
    # dir hermano de OTRO módulo del mismo cliente
    sibling = P.DATA_ROOT / AREA / CLIENTE / "pricing-dashboard"
    sibling.mkdir(parents=True, exist_ok=True)
    (sibling / "dummy.parquet").write_bytes(b"x")

    assert lb.delete_cliente(AREA, CLIENTE, "sku-progress") is True
    # el dir del módulo target desapareció
    assert not (P.DATA_ROOT / AREA / CLIENTE / "sku-progress").exists()
    # el hermano de otro módulo SOBREVIVE
    assert (sibling / "dummy.parquet").exists()
    # borrar de nuevo → False (ya no existe)
    assert lb.delete_cliente(AREA, CLIENTE, "sku-progress") is False


# ─────────────────────────────────────────────────────────────────────────────
# Borrados — _SupabaseBackend (fake transport, cero red)
# ─────────────────────────────────────────────────────────────────────────────


def test_supabase_delete_snapshot_filtra_pk_exacta(backend):
    backend.save_snapshot(_mini("W14"), AREA, CLIENTE, "sku-progress", "2026-W14")
    backend.save_snapshot(_mini("W15"), AREA, CLIENTE, "sku-progress", "2026-W15")
    assert backend.delete_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is True
    # solo W14 se fue; W15 sigue
    assert backend.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is None
    assert backend.load_snapshot(AREA, CLIENTE, "sku-progress", "2026-W15") is not None
    # borrar inexistente → False (nada matcheó)
    assert backend.delete_snapshot(AREA, CLIENTE, "sku-progress", "2026-W14") is False


def test_supabase_delete_cliente_filtra_por_modulo(backend):
    backend.save_snapshot(_mini("a"), AREA, CLIENTE, "sku-progress", "2026-W14")
    backend.save_snapshot(_mini("b"), AREA, CLIENTE, "sku-progress", "2026-W15")
    # otro módulo del mismo cliente NO debe borrarse
    backend.save_snapshot(_mini("c"), AREA, CLIENTE, "pricing-dashboard", "2026-04-17")

    assert backend.delete_cliente(AREA, CLIENTE, "sku-progress") is True
    assert backend.list_periods(AREA, CLIENTE, "sku-progress") == []
    assert backend.list_periods(AREA, CLIENTE, "pricing-dashboard") == ["2026-04-17"]
    # borrar de nuevo → False (ya no quedan filas del módulo)
    assert backend.delete_cliente(AREA, CLIENTE, "sku-progress") is False


def test_supabase_delete_history_es_noop_no_toca_transport():
    """delete_history NO debe llamar al transport y devuelve True (history derivado)."""

    class _ExplodingTransport:
        def get(self, *a, **k):
            raise AssertionError("delete_history no debe tocar el transport")

        def post(self, *a, **k):
            raise AssertionError("delete_history no debe tocar el transport")

        def delete(self, *a, **k):
            raise AssertionError("delete_history no debe tocar el transport")

    b = P._SupabaseBackend(transport=_ExplodingTransport())
    assert b.delete_history(AREA, CLIENTE, "sku-progress") is True


def test_fake_transport_delete_eq_es_exacto():
    """Lockea la semántica del fake: delete por eq exacto (no prefijo)."""
    t = _FakeTransport()
    t.post(P._SNAPSHOTS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                                 "period": "2026-W1", "data": "x"}], upsert=True)
    t.post(P._SNAPSHOTS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                                 "period": "2026-W18", "data": "y"}], upsert=True)
    deleted = t.delete(P._SNAPSHOTS_TABLE, {"area": "eq.a", "cliente": "eq.c",
                                            "modulo": "eq.m", "period": "eq.2026-W18"})
    assert len(deleted) == 1 and deleted[0]["period"] == "2026-W18"
    # W1 sobrevive (no match por prefijo)
    remaining = t.get(P._SNAPSHOTS_TABLE, {"area": "eq.a", "cliente": "eq.c",
                                           "modulo": "eq.m", "period": "eq.2026-W1"})
    assert len(remaining) == 1 and remaining[0]["period"] == "2026-W1"


# ─────────────────────────────────────────────────────────────────────────────
# Logs append-only (Bloque 2) — _LocalBackend (tmp_path) y _SupabaseBackend (fake)
# ─────────────────────────────────────────────────────────────────────────────

MODULO = "sku-progress"


def test_local_append_load_log_roundtrip(local_backend):
    """Comportamiento local histórico: 2 appends → load_log 2 filas + timestamp
    inyectado + filtro por igualdad."""
    lb = local_backend
    lb.append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")
    lb.append_log({"sku": "B", "label": "bullets"}, AREA, CLIENTE, MODULO, "optimizations")

    df = lb.load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert len(df) == 2
    assert "timestamp" in df.columns
    assert df["timestamp"].notna().all()  # inyectado en cada fila
    # orden de inserción preservado (append-order del parquet)
    assert df["sku"].tolist() == ["A", "B"]

    # filtro por igualdad
    only_a = lb.load_log(AREA, CLIENTE, MODULO, "optimizations", filters={"sku": "A"})
    assert only_a["sku"].tolist() == ["A"]


def test_local_append_log_respeta_timestamp_provisto(local_backend):
    """Si el row ya trae timestamp, NO se sobreescribe (verbatim del comportamiento)."""
    lb = local_backend
    lb.append_log(
        {"sku": "A", "label": "x", "timestamp": "2026-01-01T00:00:00"},
        AREA, CLIENTE, MODULO, "optimizations",
    )
    df = lb.load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert df.loc[0, "timestamp"] == "2026-01-01T00:00:00"


def test_supabase_append_log_es_insert_no_upsert(backend):
    """append_log INSERTA (no mergea por PK): 2 appends iguales = 2 filas."""
    backend.append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")
    backend.append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")

    df = backend.load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert len(df) == 2  # NO se pisaron entre sí
    assert "timestamp" in df.columns and df["timestamp"].notna().all()


def test_supabase_load_log_reconstruye_y_filtra(backend):
    """load_log reconstruye el DF desde el jsonb `data` y aplica filters (igualdad/isin)."""
    backend.append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")
    backend.append_log({"sku": "B", "label": "bullets"}, AREA, CLIENTE, MODULO, "optimizations")
    backend.append_log({"sku": "C", "label": "a+"}, AREA, CLIENTE, MODULO, "optimizations")

    full = backend.load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert len(full) == 3 and set(full["sku"]) == {"A", "B", "C"}

    # igualdad
    only_b = backend.load_log(AREA, CLIENTE, MODULO, "optimizations", filters={"sku": "B"})
    assert only_b["sku"].tolist() == ["B"]
    # isin (lista)
    ac = backend.load_log(AREA, CLIENTE, MODULO, "optimizations", filters={"sku": ["A", "C"]})
    assert sorted(ac["sku"].tolist()) == ["A", "C"]


def test_supabase_load_log_separado_por_log_name(backend):
    """Distintos log_name del mismo módulo no se mezclan."""
    backend.append_log({"sku": "A"}, AREA, CLIENTE, MODULO, "optimizations")
    backend.append_log({"sku": "Z"}, AREA, CLIENTE, MODULO, "events")
    opt = backend.load_log(AREA, CLIENTE, MODULO, "optimizations")
    ev = backend.load_log(AREA, CLIENTE, MODULO, "events")
    assert opt["sku"].tolist() == ["A"]
    assert ev["sku"].tolist() == ["Z"]


def test_supabase_load_log_vacio_devuelve_df_vacio(backend):
    df = backend.load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert isinstance(df, pd.DataFrame) and df.empty


def test_supabase_delete_cliente_tambien_borra_logs(backend):
    """delete_cliente ahora encadena el borrado de ah_logs (acotado al módulo):
    el log del módulo target queda vacío, pero el log de OTRO módulo del mismo
    cliente SOBREVIVE."""
    # snapshot + log del módulo target
    backend.save_snapshot(_mini("a"), AREA, CLIENTE, MODULO, "2026-W14")
    backend.append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")
    # log de OTRO módulo del mismo cliente
    backend.append_log({"sku": "Z"}, AREA, CLIENTE, "pricing-dashboard", "decisions-log")

    assert backend.delete_cliente(AREA, CLIENTE, MODULO) is True
    # target: snapshots y logs vacíos
    assert backend.list_periods(AREA, CLIENTE, MODULO) == []
    assert backend.load_log(AREA, CLIENTE, MODULO, "optimizations").empty
    # hermano: su log SOBREVIVE
    sib = backend.load_log(AREA, CLIENTE, "pricing-dashboard", "decisions-log")
    assert sib["sku"].tolist() == ["Z"]


def test_supabase_delete_cliente_solo_logs_devuelve_true(backend):
    """Si no hay snapshots pero sí logs, delete_cliente devuelve True (borró algo)."""
    backend.append_log({"sku": "A"}, AREA, CLIENTE, MODULO, "optimizations")
    assert backend.delete_cliente(AREA, CLIENTE, MODULO) is True
    assert backend.load_log(AREA, CLIENTE, MODULO, "optimizations").empty


def test_fake_transport_post_logs_apenda_no_mergea():
    """Lockea la semántica del fake para ah_logs: post sin upsert APENDA + asigna id."""
    t = _FakeTransport()
    t.post(P._LOGS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                            "log_name": "l", "data": {"sku": "A"}}], upsert=False)
    t.post(P._LOGS_TABLE, [{"area": "a", "cliente": "c", "modulo": "m",
                            "log_name": "l", "data": {"sku": "A"}}], upsert=False)
    rows = t.get(P._LOGS_TABLE, {"area": "eq.a", "cliente": "eq.c",
                                 "modulo": "eq.m", "log_name": "eq.l"})
    assert len(rows) == 2  # apendó, no mergeó
    assert {r["id"] for r in rows} == {1, 2}  # surrogate id incremental


# ─────────────────────────────────────────────────────────────────────────────
# Client-configs per-cliente (Bloque 3) — Local (tmp_path) y Supabase (fake)
# ─────────────────────────────────────────────────────────────────────────────


def _tracked_skus_dict(cliente: str) -> dict:
    return {
        "version": 1,
        "cliente": cliente,
        "skus": [
            {"sku": "DEMARPA0001S56", "asin": "B0A", "title": "Prod A",
             "image_url": "", "link": "", "added_at": "2026-W14"},
            {"sku": "DEMARPA0002S56", "asin": "B0B", "title": "Prod B",
             "image_url": "", "link": "", "added_at": "2026-W15"},
        ],
    }


def test_local_client_config_roundtrip_y_path_exacto(local_backend):
    """save/load round-trip + el archivo queda en el path histórico de M28."""
    lb = local_backend
    cfg = _tracked_skus_dict(CLIENTE)
    out = lb.save_client_config(cfg, AREA, CLIENTE, MODULO, "tracked-skus")

    # path EXACTO = data/<area>/<cliente>/<modulo>/tracked-skus.json (paridad M28)
    expected = P.DATA_ROOT / AREA / CLIENTE / MODULO / "tracked-skus.json"
    assert out == expected
    assert expected.exists()

    loaded = lb.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus")
    assert loaded == cfg


def test_local_client_config_inexistente_devuelve_dict_vacio(local_backend):
    assert local_backend.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {}


def test_supabase_client_config_roundtrip(backend):
    cfg = _tracked_skus_dict(CLIENTE)
    backend.save_client_config(cfg, AREA, CLIENTE, MODULO, "tracked-skus")
    assert backend.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == cfg


def test_supabase_client_config_pk_incluye_cliente(backend):
    """Mismo modulo+name pero distinto cliente NO colisiona (PK lleva cliente)."""
    cfg_a = _tracked_skus_dict("cli-a")
    cfg_b = _tracked_skus_dict("cli-b")
    backend.save_client_config(cfg_a, AREA, "cli-a", MODULO, "tracked-skus")
    backend.save_client_config(cfg_b, AREA, "cli-b", MODULO, "tracked-skus")

    assert backend.load_client_config(AREA, "cli-a", MODULO, "tracked-skus") == cfg_a
    assert backend.load_client_config(AREA, "cli-b", MODULO, "tracked-skus") == cfg_b


def test_supabase_client_config_upsert_pisa_mismo_pk(backend):
    backend.save_client_config({"v": 1}, AREA, CLIENTE, MODULO, "tracked-skus")
    backend.save_client_config({"v": 2}, AREA, CLIENTE, MODULO, "tracked-skus")
    # 1 sola fila, pisada
    assert backend.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {"v": 2}
    assert len(backend._t.tables[P._CLIENT_CONFIGS_TABLE]) == 1


def test_supabase_client_config_inexistente_devuelve_dict_vacio(backend):
    assert backend.load_client_config(AREA, CLIENTE, MODULO, "nope") == {}


def test_supabase_delete_cliente_tambien_borra_client_configs(backend):
    """delete_cliente encadena el borrado de ah_client_configs (acotado al módulo):
    el client-config del módulo target se va, el de OTRO módulo del mismo cliente
    SOBREVIVE."""
    backend.save_snapshot(_mini("a"), AREA, CLIENTE, MODULO, "2026-W14")
    backend.save_client_config(_tracked_skus_dict(CLIENTE), AREA, CLIENTE, MODULO, "tracked-skus")
    # client-config de OTRO módulo del mismo cliente
    backend.save_client_config({"k": "v"}, AREA, CLIENTE, "pricing-dashboard", "prefs")

    assert backend.delete_cliente(AREA, CLIENTE, MODULO) is True
    assert backend.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {}
    # hermano SOBREVIVE
    sib = backend.load_client_config(AREA, CLIENTE, "pricing-dashboard", "prefs")
    assert sib == {"k": "v"}


def test_supabase_delete_cliente_solo_client_config_devuelve_true(backend):
    """Si no hay snapshots ni logs pero sí client-config, delete_cliente → True."""
    backend.save_client_config({"k": "v"}, AREA, CLIENTE, MODULO, "tracked-skus")
    assert backend.delete_cliente(AREA, CLIENTE, MODULO) is True
    assert backend.load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {}


# ─────────────────────────────────────────────────────────────────────────────
# Invalidación de cache de los WRAPPERS PÚBLICOS (FIX 3 / n5)
# ─────────────────────────────────────────────────────────────────────────────
#
# Los tests de arriba llaman a los backends directo (sin pasar por los wrappers
# cacheados). Acá ejercitamos los wrappers `_save_*`/`_load_*`/`_delete_*` para
# verificar que tras una escritura/borrado la SIGUIENTE lectura por el wrapper
# refleja el cambio (no devuelve el valor cacheado viejo). En el entorno de tests
# Streamlit está instalado → `_HAS_STREAMLIT` True → los `@_cache_data` son cache
# REAL, así que estos tests ejercitan el path de invalidación de verdad (si se
# quita el `.clear()` correspondiente, el test falla con el valor stale).


def _clear_all_caches():
    """Limpia los caches st.cache_data module-level (la cache key NO incluye
    DATA_ROOT/backend, así que hay que limpiar entre tests para no arrastrar)."""
    for fn in (P._load_snapshot, P._load_history, P._list_periods,
               P._load_config, P._load_client_config):
        if hasattr(fn, "clear"):
            fn.clear()
    # P._load_log NO está cacheado (FIX M1) — no tiene .clear().


@pytest.fixture
def wrapper_local_env(tmp_path, monkeypatch):
    """Wrappers públicos sobre _LocalBackend con DATA_ROOT temporal."""
    monkeypatch.setattr(P, "DATA_ROOT", tmp_path)
    P._set_backend_for_testing(P._LocalBackend())
    _clear_all_caches()
    yield
    _clear_all_caches()
    P._set_backend_for_testing(None)


@pytest.fixture
def wrapper_supa_env():
    """Wrappers públicos sobre _SupabaseBackend(fake) — para invalidación donde el
    history se RECOMPUTA desde snapshots (no se lee de disco)."""
    P._set_backend_for_testing(P._SupabaseBackend(transport=_FakeTransport()))
    _clear_all_caches()
    yield
    _clear_all_caches()
    P._set_backend_for_testing(None)


def test_wrapper_save_snapshot_invalida_load_snapshot(wrapper_local_env):
    # primer load cachea None
    assert P._load_snapshot(AREA, CLIENTE, MODULO, "2026-W14") is None
    P._save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, MODULO, "2026-W14")
    # tras el save, el wrapper NO debe devolver el None cacheado
    out = P._load_snapshot(AREA, CLIENTE, MODULO, "2026-W14")
    assert out is not None and len(out) == 2


def test_wrapper_save_snapshot_invalida_list_periods(wrapper_local_env):
    assert P._list_periods(AREA, CLIENTE, MODULO) == []  # cachea vacío
    P._save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, MODULO, "2026-W14")
    assert P._list_periods(AREA, CLIENTE, MODULO) == ["2026-W14"]


def test_wrapper_delete_snapshot_invalida_history_supabase(wrapper_supa_env):
    """FIX m2: _delete_snapshot debe invalidar _load_history (Supabase recomputa)."""
    P._save_snapshot(_mini("a"), AREA, CLIENTE, MODULO, "2026-W14")
    P._save_snapshot(_mini("b"), AREA, CLIENTE, MODULO, "2026-W15")
    hist = P._load_history(AREA, CLIENTE, MODULO)  # cachea 2 filas
    assert len(hist) == 2
    assert P._delete_snapshot(AREA, CLIENTE, MODULO, "2026-W14") is True
    # sin el _load_history.clear() del fix, esto devolvería las 2 filas cacheadas
    hist2 = P._load_history(AREA, CLIENTE, MODULO)
    assert hist2["sku"].tolist() == ["b"]


def test_wrapper_append_log_load_log_roundtrip(wrapper_local_env):
    """_load_log no está cacheado: la lectura por wrapper refleja el append sin
    necesidad de invalidación (round-trip end-to-end por la API pública)."""
    assert P._load_log(AREA, CLIENTE, MODULO, "optimizations").empty
    P._append_log({"sku": "A", "label": "img"}, AREA, CLIENTE, MODULO, "optimizations")
    P._append_log({"sku": "B", "label": "bullets"}, AREA, CLIENTE, MODULO, "optimizations")
    df = P._load_log(AREA, CLIENTE, MODULO, "optimizations")
    assert df["sku"].tolist() == ["A", "B"]
    assert df["timestamp"].notna().all()


def test_wrapper_save_client_config_invalida_load(wrapper_local_env):
    assert P._load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {}  # cachea {}
    cfg = {"version": 1, "cliente": CLIENTE, "skus": [{"sku": "X"}]}
    P._save_client_config(cfg, AREA, CLIENTE, MODULO, "tracked-skus")
    # tras el save, el wrapper NO debe devolver el {} cacheado
    assert P._load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == cfg


def test_wrapper_delete_cliente_invalida_caches(wrapper_local_env):
    """Tras _delete_cliente, las lecturas por wrapper reflejan el borrado (no cache stale)."""
    P._save_snapshot(_make_m28_snapshot(), AREA, CLIENTE, MODULO, "2026-W14")
    P._save_client_config({"version": 1, "skus": [{"sku": "X"}]},
                          AREA, CLIENTE, MODULO, "tracked-skus")
    # primar caches
    assert P._load_snapshot(AREA, CLIENTE, MODULO, "2026-W14") is not None
    assert P._load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") != {}
    assert P._list_periods(AREA, CLIENTE, MODULO) == ["2026-W14"]

    assert P._delete_cliente(AREA, CLIENTE, MODULO) is True

    # todas las lecturas por wrapper reflejan el borrado
    assert P._load_snapshot(AREA, CLIENTE, MODULO, "2026-W14") is None
    assert P._load_client_config(AREA, CLIENTE, MODULO, "tracked-skus") == {}
    assert P._list_periods(AREA, CLIENTE, MODULO) == []
