"""Tests de los helpers PUROS de la tabla principal M30 F3.4/C3.

_resultados_to_df y _aplicar_filtros (display + filtros). El styler no se testea
(es display). Los records sintéticos usan las keys reales de _run_analysis/_compute_score.
"""

import math

import pandas as pd
import pytest

from modules.pages.pricing_dashboard import (
    _resultados_to_df,
    _aplicar_filtros,
    _COLS_PRINCIPAL,
)

_HEADERS = [h for _, h in _COLS_PRINCIPAL]


def _rec(**over) -> dict:
    """Record sintético con las keys principales (las que produce _run_analysis)."""
    r = {
        "score": 0,
        "sku": "SKU1",
        "Categoria": "Poncho",
        "Subcategoria": "Poncho Clasico",
        "Temporada": "Invierno",
        "classification": "mantener",
        "price": 20.0,
        "suggestedPrice": None,
        "buybox_price": 0.0,
        "gross_margin": 30.0,
        "fba_dos": 50.0,
        "total_dos": 100.0,
        "fba_available": 10,
        "t30": 5,
        "sell_through": 1.5,
        "health": "Healthy",
        "restock_alert": None,
    }
    r.update(over)
    return r


# =====================================================================
# _resultados_to_df
# =====================================================================
class TestResultadosToDf:
    def test_orden_de_columnas_es_headers(self):
        df = _resultados_to_df([_rec()])
        assert list(df.columns) == _HEADERS

    def test_vacio_da_df_vacio(self):
        df = _resultados_to_df([])
        assert df.empty
        assert list(df.columns) == []

    def test_none_en_object_se_vuelve_string_vacio(self):
        # restock_alert None -> '' (columna object, evita romper Arrow)
        df = _resultados_to_df([_rec(restock_alert=None)])
        assert df.loc[0, "Reposición"] == ""

    def test_numericas_quedan_numericas(self):
        df = _resultados_to_df([_rec(price=19.99, gross_margin=12.3)])
        assert df.loc[0, "Precio Actual"] == 19.99
        assert isinstance(df.loc[0, "Precio Actual"], float)
        assert df.loc[0, "Margen"] == 12.3

    def test_numerica_con_none_queda_nan_no_string(self):
        # suggestedPrice None en columna numérica -> NaN (no '')
        df = _resultados_to_df([_rec(suggestedPrice=15.0), _rec(suggestedPrice=None)])
        assert df.loc[0, "Precio Sugerido"] == 15.0
        assert pd.isna(df.loc[1, "Precio Sugerido"])

    def test_solo_keys_presentes(self):
        # un record sin 'score' -> esa columna se omite (no crashea)
        rec = _rec()
        del rec["score"]
        df = _resultados_to_df([rec])
        assert "Score" not in df.columns
        assert "SKU" in df.columns


# =====================================================================
# _aplicar_filtros
# =====================================================================
def _df3() -> pd.DataFrame:
    return _resultados_to_df([
        _rec(sku="ABC", classification="subir", Categoria="Poncho",
             Temporada="Invierno", health="Healthy"),
        _rec(sku="XYZ", classification="bajar", Categoria="Gorro",
             Temporada="Verano", health="Excess"),
        _rec(sku="ABD", classification="liquidar", Categoria="Poncho",
             Temporada="Invierno", health="Low stock"),
    ])


class TestAplicarFiltros:
    def test_filtro_vacio_no_filtra(self):
        df = _df3()
        out = _aplicar_filtros(df, {})
        assert len(out) == 3

    def test_filtro_estado(self):
        out = _aplicar_filtros(_df3(), {"clasif": ["subir"]})
        assert out["SKU"].tolist() == ["ABC"]

    def test_filtro_estado_multi(self):
        out = _aplicar_filtros(_df3(), {"clasif": ["subir", "liquidar"]})
        assert set(out["SKU"]) == {"ABC", "ABD"}

    def test_filtro_categoria_exacto(self):
        out = _aplicar_filtros(_df3(), {"cat": "Poncho"})
        assert set(out["SKU"]) == {"ABC", "ABD"}

    def test_filtro_temporada_exacto(self):
        out = _aplicar_filtros(_df3(), {"temp": "Verano"})
        assert out["SKU"].tolist() == ["XYZ"]

    def test_filtro_health_exacto(self):
        out = _aplicar_filtros(_df3(), {"health": "Excess"})
        assert out["SKU"].tolist() == ["XYZ"]

    def test_busqueda_substring_sku(self):
        out = _aplicar_filtros(_df3(), {"search": "ab"})  # case-insensitive
        assert set(out["SKU"]) == {"ABC", "ABD"}

    def test_combinacion_filtros(self):
        out = _aplicar_filtros(_df3(), {"cat": "Poncho", "clasif": ["liquidar"]})
        assert out["SKU"].tolist() == ["ABD"]

    def test_no_muta_original(self):
        df = _df3()
        antes = len(df)
        _aplicar_filtros(df, {"clasif": ["subir"]})
        assert len(df) == antes  # el original sigue completo

    def test_df_vacio_devuelve_vacio(self):
        out = _aplicar_filtros(pd.DataFrame(), {"clasif": ["subir"]})
        assert out.empty
