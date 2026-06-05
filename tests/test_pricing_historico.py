"""Tests M30 F3.4/C4b — snapshot build + persistencia + import JSON.

_build_snapshot_df (47 col exactas, dtype coercion), _snapshot_date_from_resultados,
roundtrip _save_snapshot/_load_snapshot/_list_periods/_rebuild_history, _importar_historico_json.
Aísla DATA_ROOT/SCHEMAS_ROOT a tmp_path (no escribe en data/ real); cliente único por test.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from core import persistence as P
from modules.pages.pricing_dashboard import (
    _build_snapshot_df,
    _snapshot_date_from_resultados,
    _importar_historico_json,
    _SNAPSHOT_COLS,
)

AREA = "account-health"
MODULE_SLUG = "pricing-dashboard"
SCHEMA_VERSION = 1
SNAP_DATE = "2026-04-17"

REPO_ROOT = Path(__file__).resolve().parent.parent
REAL_SCHEMA_PATH = REPO_ROOT / "data" / "_schemas" / f"{MODULE_SLUG}-v{SCHEMA_VERSION}.json"

_SCHEMA_COLS = [c for c, _, _ in _SNAPSHOT_COLS]
_CACHED = ("_load_snapshot", "_load_history", "_list_periods")


def _clear_caches():
    if P._HAS_STREAMLIT:
        for name in _CACHED:
            fn = getattr(P, name, None)
            if fn is not None and hasattr(fn, "clear"):
                fn.clear()


@pytest.fixture
def isolated_data_root(tmp_path, monkeypatch):
    tmp_data = tmp_path / "data"
    tmp_schemas = tmp_data / "_schemas"
    tmp_schemas.mkdir(parents=True, exist_ok=True)
    (tmp_schemas / f"{MODULE_SLUG}-v{SCHEMA_VERSION}.json").write_text(
        REAL_SCHEMA_PATH.read_text(encoding="utf-8"), encoding="utf-8"
    )
    monkeypatch.setattr(P, "DATA_ROOT", tmp_data)
    monkeypatch.setattr(P, "SCHEMAS_ROOT", tmp_schemas)
    _clear_caches()
    yield tmp_data
    _clear_caches()


@pytest.fixture
def cliente(request):
    return f"test-{request.node.name}".replace("_", "-").lower()[:50]


def _rec(**over) -> dict:
    """Record full con TODAS las keys que lee _build_snapshot_df.
    Los campos de conteo van como float (como los emite el record vía _to_float)."""
    r = {
        "snapshot_date": SNAP_DATE,
        "sku": "SKU1",
        "asin": "B001",
        "product_name": "Poncho Clasico Test",
        "Modelo": "M1",
        "Talla": "L",
        "Temporada": "Invierno",
        "Categoria": "Poncho",
        "Subcategoria": "Poncho Clasico",
        "price": 20.0,
        "fba_available": 10.0,
        "awd_available": 0.0,
        "izzi_available": 0.0,
        "total_stock": 10.0,
        "has_backup": False,
        "t7": 1.0,
        "t30": 5.0,
        "t90": 12.0,
        "daily_rate": 0.5,
        "fba_dos": 50.0,
        "total_dos": 100.0,
        "cogs": 5.0,
        "fulfillment_fee": 1.0,
        "referral_fee": 1.0,
        "ppc_fee": 0.5,
        "fulfillment_fee_est": False,
        "referral_fee_est": False,
        "gross_margin": 65.0,
        "net_margin": 60.0,
        "aging_181_270": 0.0,
        "aging_271_365": 0.0,
        "aging_366plus": 0.0,
        "ais_total": 0.0,
        "health": "Healthy",
        "no_sale_6m": "0",
        "buybox_price": 0.0,
        "subcat_avg": None,
        "model_avg": None,
        "score": 5,
        "classification": "mantener",
        "reasons_down": [],
        "reasons_up": [],
        "suggestedPrice": None,
        "suggestedRationale": "",
        "restock_alert": None,
        "liq_min_price": 7.0,
        "is_liquidar": False,
    }
    r.update(over)
    return r


# =====================================================================
# _build_snapshot_df
# =====================================================================
class TestBuildSnapshotDf:
    def test_47_columnas_exactas_en_orden(self):
        df = _build_snapshot_df([_rec()], SNAP_DATE)
        assert list(df.columns) == _SCHEMA_COLS
        assert len(_SCHEMA_COLS) == 47

    def test_snapshot_date_columna_es_arg(self):
        # el record trae snapshot_date distinto: gana el arg
        df = _build_snapshot_df([_rec(snapshot_date="2099-01-01")], SNAP_DATE)
        assert df["snapshot_date"].tolist() == [SNAP_DATE]

    def test_int_coercion_float_a_int64(self):
        df = _build_snapshot_df([_rec(fba_available=10.0, total_stock=10.0)], SNAP_DATE)
        assert str(df["fba_available"].dtype) == "int64"
        assert df["fba_available"].iloc[0] == 10

    def test_float_none_es_nan_float64(self):
        df = _build_snapshot_df([_rec(suggestedPrice=None)], SNAP_DATE)
        assert str(df["suggested_price"].dtype) == "float64"
        assert pd.isna(df["suggested_price"].iloc[0])

    def test_string_none_a_vacio(self):
        df = _build_snapshot_df([_rec(asin=None)], SNAP_DATE)
        assert df["asin"].iloc[0] == ""

    def test_renombre_de_keys(self):
        # Modelo->modelo, fulfillment_fee->ff, suggestedPrice->suggested_price, etc.
        df = _build_snapshot_df([_rec(Modelo="MX", fulfillment_fee=2.5, subcat_avg=18.0)], SNAP_DATE)
        assert df["modelo"].iloc[0] == "MX"
        assert df["ff"].iloc[0] == 2.5
        assert df["subcat_avg_price"].iloc[0] == 18.0

    def test_reasons_a_json_string(self):
        df = _build_snapshot_df([_rec(reasons_down=["a", "b"])], SNAP_DATE)
        assert df["reasons_down"].iloc[0] == json.dumps(["a", "b"])
        # ausente -> "[]"
        df2 = _build_snapshot_df([_rec(reasons_up=None)], SNAP_DATE)
        assert df2["reasons_up"].iloc[0] == "[]"

    def test_bool_dtype(self):
        df = _build_snapshot_df([_rec(is_liquidar=True, has_backup=False)], SNAP_DATE)
        assert str(df["is_liquidar"].dtype) == "bool"
        assert df["is_liquidar"].iloc[0] is True or df["is_liquidar"].iloc[0]

    def test_record_parcial_completa_defaults(self):
        # solo sku -> las 47 columnas presentes con defaults por dtype
        df = _build_snapshot_df([{"sku": "X"}], SNAP_DATE)
        assert list(df.columns) == _SCHEMA_COLS
        assert df["fba_available"].iloc[0] == 0           # int default
        assert pd.isna(df["price"].iloc[0])               # float default NaN
        assert df["product_name"].iloc[0] == ""           # str default
        assert bool(df["is_liquidar"].iloc[0]) is False   # bool default

    def test_valida_schema_sin_errores(self, isolated_data_root):
        df = _build_snapshot_df([_rec(), _rec(sku="SKU2")], SNAP_DATE)
        errores = P._validate_against_schema(df, MODULE_SLUG, SCHEMA_VERSION)
        assert errores == []


# =====================================================================
# _snapshot_date_from_resultados
# =====================================================================
class TestSnapshotDate:
    def test_usa_el_del_dato(self):
        assert _snapshot_date_from_resultados([_rec(snapshot_date="2026-03-01")]) == "2026-03-01"

    def test_fallback_hoy_si_ausente(self):
        assert _snapshot_date_from_resultados([{"sku": "X"}]) == date.today().isoformat()

    def test_fallback_hoy_si_vacio(self):
        assert _snapshot_date_from_resultados([]) == date.today().isoformat()


# =====================================================================
# Roundtrip persistencia
# =====================================================================
class TestRoundtrip:
    def test_save_load_list_rebuild(self, isolated_data_root, cliente):
        df = _build_snapshot_df([_rec(), _rec(sku="SKU2")], SNAP_DATE)
        P._save_snapshot(df, AREA, cliente, MODULE_SLUG, SNAP_DATE)

        loaded = P._load_snapshot(AREA, cliente, MODULE_SLUG, SNAP_DATE)
        assert loaded is not None
        assert len(loaded) == 2
        assert list(loaded.columns) == _SCHEMA_COLS

        assert P._list_periods(AREA, cliente, MODULE_SLUG) == [SNAP_DATE]

        P._rebuild_history(AREA, cliente, MODULE_SLUG)
        hist = P._load_history(AREA, cliente, MODULE_SLUG)
        assert "_period" in hist.columns
        assert hist["_period"].iloc[0] == SNAP_DATE
        assert len(hist) == 2


# =====================================================================
# _importar_historico_json
# =====================================================================
def _payload(*dates) -> bytes:
    arr = [
        {"date": d, "skus": {
            "A": {"price": 20, "dos": 50, "t30": 5, "t7": 1, "score": -10,
                  "classification": "mantener", "gross_margin": 30, "health": "Healthy"}
        }}
        for d in dates
    ]
    return json.dumps(arr).encode("utf-8")


class TestImportarHistorico:
    def test_import_valido_persiste_y_rebuild(self, isolated_data_root, cliente):
        n = _importar_historico_json(_payload("2026-04-10", "2026-04-17"), cliente)
        assert n == 2
        assert P._list_periods(AREA, cliente, MODULE_SLUG) == ["2026-04-10", "2026-04-17"]
        hist = P._load_history(AREA, cliente, MODULE_SLUG)
        assert len(hist) == 2
        assert "_period" in hist.columns
        # mapeo dos->fba_dos
        assert set(hist["fba_dos"].tolist()) == {50.0}

    def test_import_shape_no_lista_raise(self, isolated_data_root, cliente):
        with pytest.raises(ValueError):
            _importar_historico_json(json.dumps({"no": "lista"}).encode("utf-8"), cliente)
        assert P._list_periods(AREA, cliente, MODULE_SLUG) == []  # nada persistido

    def test_import_entrada_invalida_no_persiste_parcial(self, isolated_data_root, cliente):
        # primera entrada válida, segunda inválida -> raise ANTES de tocar disco
        bad = json.dumps([
            {"date": "2026-04-10", "skus": {"A": {"price": 1, "dos": 2}}},
            {"falta": "date y skus"},
        ]).encode("utf-8")
        with pytest.raises(ValueError):
            _importar_historico_json(bad, cliente)
        assert P._list_periods(AREA, cliente, MODULE_SLUG) == []  # cero persistencia parcial

    def test_import_snapshot_valida_schema(self, isolated_data_root, cliente):
        _importar_historico_json(_payload("2026-04-10"), cliente)
        loaded = P._load_snapshot(AREA, cliente, MODULE_SLUG, "2026-04-10")
        assert P._validate_against_schema(loaded, MODULE_SLUG, SCHEMA_VERSION) == []
