"""Encoding de los CSV de pricing_dashboard (_parse_fba, _parse_fee, _parse_awd).

Los tres leen con utf-8-sig fijo. Marcos reporto el 24/09 un UnicodeDecodeError
(byte 0xe1) en _parse_fee con un CSV de fees exportado en cp1252. El fix pasa el
encoding de las tres lecturas a core.csv_io.encoding_csv, sin tocar _detect_sep.
"""

from __future__ import annotations

import pytest

from modules.pages.pricing_dashboard import (
    _detect_sep,
    _parse_awd,
    _parse_fba,
    _parse_fee,
)

_ACENTO = "Plátano"

_CSV_CP1252 = {
    "fee": (_parse_fee, "MSKU,Descripcion,Units sold\nABC,Plátano,10\n", "Descripcion"),
    "fba": (_parse_fba, "sku,product-name,afn-fulfillable-quantity\nABC,Plátano,5\n", "product-name"),
    "awd": (_parse_awd, "SKU,Product Name,Available in AWD (units)\nABC,Plátano,7\n", "Product Name"),
}
_PARSERS = [pytest.param(*_CSV_CP1252[nombre], id=nombre) for nombre in _CSV_CP1252]


class TestBugDeMarcos:
    @pytest.mark.parametrize("parser, texto, columna", _PARSERS)
    def test_un_csv_cp1252_se_lee_y_conserva_el_acento(self, parser, texto, columna):
        df = parser(texto.encode("cp1252"))
        assert df.iloc[0][columna] == _ACENTO


class TestLoQueYaAndaNoCambia:
    def test_utf8_separado_por_coma(self):
        df = _parse_fee(b"MSKU,Units sold\nABC,10\n")
        assert list(df.columns) == ["MSKU", "Units sold"]
        assert df.iloc[0]["MSKU"] == "ABC"
        assert df.iloc[0]["Units sold"] == 10

    def test_utf8_separado_por_punto_y_coma(self):
        df = _parse_fee(b"MSKU;Units sold\nABC;10\n")
        assert list(df.columns) == ["MSKU", "Units sold"]
        assert df.iloc[0]["Units sold"] == 10

    @pytest.mark.parametrize("parser", [_parse_fba, _parse_fee, _parse_awd], ids=["fba", "fee", "awd"])
    def test_utf8_con_bom_no_deja_bom_en_el_primer_header(self, parser):
        # A BOM left on the first header makes the SKU match fail silently (docstring L24-28).
        df = parser("﻿MSKU,Units sold\nABC,10\n".encode("utf-8"))
        assert not df.columns[0].startswith("﻿")
        assert df.columns[0] == "MSKU"

    def test_punto_y_coma_entre_comillas_sigue_ganando(self):
        # Frozen HTML behavior: _detect_sep counts ';' inside quotes too.
        data = b'"a;b;c",d\n"x;y;z",w\n'
        assert _detect_sep(data) == ";"
        assert list(_parse_fee(data).columns) == ["a;b;c,d"]


class TestDetectSepIntacto:
    @pytest.mark.parametrize(
        "data, esperado",
        [
            (b"SKU;Descripci\xf3n;Fee\nA;Pl\xe1tano;1\n", ";"),
            (b"SKU,Descripci\xf3n,Fee\nA,Pl\xe1tano,1\n", ","),
        ],
        ids=["punto_y_coma", "coma"],
    )
    def test_un_csv_cp1252_no_rompe_la_deteccion(self, data, esperado):
        assert _detect_sep(data) == esperado
