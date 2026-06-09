"""Tests de los helpers PUROS de las vistas M30 F3.4/C4a.

_records_to_df (generalización de C3), _vista_liquidar/_sinmargen/_ais y _resumen_stats.
Criterios verbatim de finishAnalysis (HTML L1175-1181) + populateResumenCharts.
Records sintéticos con las keys reales de _run_analysis/_compute_score.
"""

import pandas as pd
import pytest

from modules.pages.pricing_dashboard import (
    _records_to_df,
    _resultados_to_df,
    _vista_liquidar,
    _vista_sinmargen,
    _vista_ais,
    _resumen_stats,
    _COLS_PRINCIPAL,
    _COLS_LIQUIDAR,
    _COLS_SINMARGEN,
    _COLS_AIS,
)


def _rec(**over) -> dict:
    r = {
        "sku": "SKU1",
        "Categoria": "Poncho",
        "Subcategoria": "Poncho Clasico",
        "Temporada": "Invierno",
        "classification": "mantener",
        "score": 0,
        "price": 20.0,
        "suggestedPrice": None,
        "buybox_price": 0.0,
        "gross_margin": 30.0,
        "net_margin": 28.0,
        "cogs": 5.0,
        "fulfillment_fee": 1.0,
        "referral_fee": 1.0,
        "ppc_fee": 0.5,
        "liq_min_price": None,
        "fba_dos": 50.0,
        "total_dos": 100.0,
        "fba_available": 10,
        "awd_available": 0,
        "izzi_available": 0,
        "daily_rate": 0.5,
        "t30": 5,
        "t7": 1,
        "sell_through": 1.5,
        "health": "Healthy",
        "restock_alert": None,
        "ais_total": 0.0,
        "aging_181_270": 0,
        "aging_271_365": 0,
        "aging_366plus": 0,
        "no_sale_6m": "0",
        "reasons_down": [],
        "reasons_up": [],
    }
    r.update(over)
    return r


# =====================================================================
# _records_to_df (generalización)
# =====================================================================
class TestRecordsToDf:
    def test_respeta_cols_pasadas(self):
        cols = [("sku", "SKU"), ("price", "Precio")]
        df = _records_to_df([_rec()], cols)
        assert list(df.columns) == ["SKU", "Precio"]

    def test_none_object_a_vacio(self):
        df = _records_to_df([_rec(restock_alert=None)], [("restock_alert", "Acción")])
        assert df.loc[0, "Acción"] == ""

    def test_lista_se_une_con_punto_y_coma(self):
        df = _records_to_df([_rec(reasons_down=["a", "b", "c"])], [("reasons_down", "Motivo")])
        assert df.loc[0, "Motivo"] == "a; b; c"

    def test_numericas_intactas(self):
        df = _records_to_df([_rec(price=19.99)], [("price", "Precio")])
        assert df.loc[0, "Precio"] == 19.99

    def test_vacio_da_df_vacio(self):
        assert _records_to_df([], _COLS_PRINCIPAL).empty

    def test_resultados_to_df_backcompat(self):
        # _resultados_to_df sigue usando _COLS_PRINCIPAL
        df = _resultados_to_df([_rec()])
        assert list(df.columns) == [h for _, h in _COLS_PRINCIPAL]


# =====================================================================
# Vistas — criterio verbatim + columnas + vacío + no-mutación
# =====================================================================
class TestVistaLiquidar:
    def test_criterio_classification_liquidar(self):
        recs = [_rec(sku="A", classification="liquidar"),
                _rec(sku="B", classification="bajar")]
        out = _vista_liquidar(recs)
        assert out["SKU"].tolist() == ["A"]

    def test_columnas_liquidar(self):
        out = _vista_liquidar([_rec(classification="liquidar")])
        assert list(out.columns) == [h for _, h in _COLS_LIQUIDAR]

    def test_orden_t30_asc(self):
        recs = [_rec(sku="A", classification="liquidar", t30=9),
                _rec(sku="B", classification="liquidar", t30=2)]
        out = _vista_liquidar(recs)
        assert out["SKU"].tolist() == ["B", "A"]

    def test_sin_matches_vacio(self):
        assert _vista_liquidar([_rec(classification="subir")]).empty

    def test_no_muta_input(self):
        recs = [_rec(classification="liquidar")]
        _vista_liquidar(recs)
        assert len(recs) == 1 and recs[0]["classification"] == "liquidar"


class TestVistaSinMargen:
    def test_criterio_margen_menor_15_no_none(self):
        recs = [_rec(sku="A", gross_margin=10.0),
                _rec(sku="B", gross_margin=20.0),
                _rec(sku="C", gross_margin=None)]  # None excluido
        out = _vista_sinmargen(recs)
        assert out["SKU"].tolist() == ["A"]

    def test_orden_margen_asc(self):
        recs = [_rec(sku="A", gross_margin=12.0), _rec(sku="B", gross_margin=3.0)]
        out = _vista_sinmargen(recs)
        assert out["SKU"].tolist() == ["B", "A"]

    def test_columnas_sinmargen(self):
        out = _vista_sinmargen([_rec(gross_margin=5.0)])
        assert list(out.columns) == [h for _, h in _COLS_SINMARGEN]

    def test_sin_matches_vacio(self):
        assert _vista_sinmargen([_rec(gross_margin=40.0)]).empty


class TestVistaAis:
    def test_criterio_ais_mayor_cero(self):
        recs = [_rec(sku="A", ais_total=3.0), _rec(sku="B", ais_total=0.0)]
        out = _vista_ais(recs)
        assert out["SKU"].tolist() == ["A"]

    def test_orden_ais_desc(self):
        recs = [_rec(sku="A", ais_total=2.0), _rec(sku="B", ais_total=9.0)]
        out = _vista_ais(recs)
        assert out["SKU"].tolist() == ["B", "A"]

    def test_columnas_ais(self):
        out = _vista_ais([_rec(ais_total=1.0)])
        assert list(out.columns) == [h for _, h in _COLS_AIS]

    def test_sin_matches_vacio(self):
        assert _vista_ais([_rec(ais_total=0.0)]).empty


# =====================================================================
# _resumen_stats
# =====================================================================
class TestResumenStats:
    def test_conteos_por_clasificacion(self):
        recs = [_rec(classification="subir"), _rec(classification="subir"),
                _rec(classification="bajar"), _rec(classification="liquidar"),
                _rec(classification="mantener")]
        s = _resumen_stats(recs)
        assert s["subir"] == 2
        assert s["bajar"] == 1
        assert s["liquidar"] == 1
        assert s["mantener"] == 1

    def test_ais_sinmargen_restock(self):
        recs = [
            _rec(ais_total=3.0, gross_margin=10.0, restock_alert="Mover 5u"),
            _rec(ais_total=0.0, gross_margin=40.0, restock_alert=None),
        ]
        s = _resumen_stats(recs)
        assert s["ais"] == 1
        assert s["sinmargen"] == 1
        assert s["restock"] == 1

    def test_alertas_criticas(self):
        recs = [
            _rec(gross_margin=-5.0, ais_total=7.0, no_sale_6m="1"),
            _rec(gross_margin=20.0, ais_total=2.0, no_sale_6m="0"),
        ]
        s = _resumen_stats(recs)
        assert s["margen_negativo"] == 1   # gross_margin < 0
        assert s["ais_gt5"] == 1           # ais_total > 5
        assert s["sin_venta_6m"] == 1      # no_sale_6m == '1'

    def test_no_sale_acepta_int_1(self):
        s = _resumen_stats([_rec(no_sale_6m=1)])
        assert s["sin_venta_6m"] == 1

    def test_cat_bajar_distribucion(self):
        recs = [
            _rec(classification="bajar", Categoria="Poncho"),
            _rec(classification="bajar", Categoria="Poncho"),
            _rec(classification="bajar", Categoria="Gorro"),
            _rec(classification="subir", Categoria="Sombrero"),  # no bajar -> no cuenta
        ]
        s = _resumen_stats(recs)
        assert s["cat_bajar"][0] == ("Poncho", 2)
        assert ("Gorro", 1) in s["cat_bajar"]
        assert all(cat != "Sombrero" for cat, _ in s["cat_bajar"])
