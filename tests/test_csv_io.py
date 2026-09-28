"""Tests de core/csv_io.py: encoding y separador de un CSV subido por el usuario.

encoding_csv y sep_csv son los _encoding_csv y _sep_csv de
modules/pages/supply_ordenes.py, movidos a core/ sin cambios de logica para que
los use tambien pricing_dashboard.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.csv_io import (
    BOMS_UTF16,
    DELIMITADORES_CSV,
    ENCODINGS_CSV,
    encoding_csv,
    sep_csv,
)

_CSV_IO = Path(__file__).resolve().parents[1] / "core" / "csv_io.py"

_POSICION_DEL_ACENTO = 6972
_FILA_DEL_ACENTO = "SKU-ACENTO,Pl"


def _fees_de_marcos() -> bytes:
    """CSV de fees en cp1252 con una 'á' (0xe1) justo en el byte 6972."""
    texto = "MSKU,Descripcion,Fee\n"
    i = 0
    while True:
        fila = f"SKU-{i:04d},Producto estandar,1.00\n"
        if len(texto) + len(fila) + len(_FILA_DEL_ACENTO) > _POSICION_DEL_ACENTO:
            break
        texto += fila
        i += 1
    relleno = "x" * (_POSICION_DEL_ACENTO - len(texto) - len(_FILA_DEL_ACENTO))
    texto += "SKU-ACENTO," + relleno + "Plátano,2.50\n"
    return texto.encode("cp1252")


class TestEncodingCsv:
    def test_bom_utf16_little_endian(self):
        assert encoding_csv(b"\xff\xfeS\x00K\x00U\x00") == "utf-16"

    def test_bom_utf16_big_endian(self):
        assert encoding_csv(b"\xfe\xff\x00S\x00K\x00U") == "utf-16"

    def test_ascii_plano(self):
        assert encoding_csv(b"SKU,Qty\nA1,5\n") == "utf-8-sig"

    def test_utf8_con_acentos(self):
        assert encoding_csv("SKU,Desc\nA1,Camión\n".encode("utf-8")) == "utf-8-sig"

    def test_utf8_con_bom(self):
        assert encoding_csv(b"\xef\xbb\xbfSKU,Qty\nA1,5\n") == "utf-8-sig"

    def test_cp1252_con_acentos(self):
        assert encoding_csv(b"SKU,Desc\nA1,Pl\xe1tano\n") == "cp1252"

    def test_byte_que_no_existe_en_cp1252_cae_a_latin1(self):
        assert encoding_csv(b"SKU,Desc\nA1,\x81raro\n") == "latin-1"

    def test_bytes_vacios_no_explotan(self):
        assert encoding_csv(b"") == "utf-8-sig"

    @pytest.mark.parametrize(
        "data",
        [
            b"",
            b"SKU\n",
            b"\xff\xfe",
            b"\xef\xbb\xbf",
            b"\x81\x8d\x8f\x90\x9d",
            bytes(range(256)),
        ],
    )
    def test_siempre_devuelve_un_encoding(self, data):
        encoding = encoding_csv(data)
        assert isinstance(encoding, str) and encoding
        data.decode(encoding)


class TestCasoDeMarcos:
    # Reproduces the UnicodeDecodeError (byte 0xe1) Marcos reported in _parse_fee on 2026-09-24.

    def test_el_acento_cae_en_la_posicion_reportada(self):
        assert _fees_de_marcos().index(b"\xe1") == _POSICION_DEL_ACENTO

    @pytest.mark.parametrize("encoding_fijo", ["utf-8", "utf-8-sig"])
    def test_con_utf8_fijo_falla(self, encoding_fijo):
        with pytest.raises(UnicodeDecodeError) as error:
            _fees_de_marcos().decode(encoding_fijo)
        assert error.value.start == _POSICION_DEL_ACENTO

    def test_la_cascada_detecta_cp1252(self):
        assert encoding_csv(_fees_de_marcos()) == "cp1252"

    def test_con_la_cascada_se_lee_y_conserva_el_acento(self):
        data = _fees_de_marcos()
        texto = data.decode(encoding_csv(data))
        assert "Plátano" in texto


class TestSepCsv:
    @pytest.mark.parametrize(
        "data, esperado",
        [
            (b"SKU,Cantidad\nA1,5\nA2,7\n", ","),
            (b"SKU;Cantidad\nA1;5\nA2;7\n", ";"),
            (b"SKU\tCantidad\nA1\t5\nA2\t7\n", "\t"),
            (b"SKU|Cantidad\nA1|5\nA2|7\n", "|"),
        ],
        ids=["coma", "punto_y_coma", "tab", "pipe"],
    )
    def test_detecta_el_separador(self, data, esperado):
        assert sep_csv(data, "utf-8-sig") == esperado

    def test_una_sola_columna_no_se_parte(self):
        # pandas' own sniffer would split this on the letter 'U'.
        assert sep_csv(b"SKU\nA1\nA2\n", "utf-8-sig") == ","

    def test_sin_delimitador_claro_cae_a_coma(self):
        assert sep_csv(b"hola mundo\nchau\n", "utf-8-sig") == ","

    def test_bytes_vacios_caen_a_coma(self):
        assert sep_csv(b"", "utf-8-sig") == ","

    def test_sniffea_el_texto_del_encoding_que_recibe(self):
        data = "SKU;Cantidad\nA1;5\nA2;7\n".encode("utf-16")
        assert sep_csv(data, "utf-16") == ";"


class TestBomYHeaders:
    # pricing_dashboard relies on utf-8-sig to strip the BOM from the first header (docstring L24-28).

    def test_utf8_con_bom_no_deja_bom_en_el_primer_header(self):
        data = "﻿MSKU,Fee\nA,1\n".encode("utf-8")
        texto = data.decode(encoding_csv(data))
        assert not texto.startswith("﻿")
        assert texto.split("\n")[0].split(",")[0] == "MSKU"

    def test_utf16_no_deja_bom_en_el_primer_header(self):
        data = "MSKU,Fee\nA,1\n".encode("utf-16")
        texto = data.decode(encoding_csv(data))
        assert not texto.startswith("﻿")
        assert texto.split("\n")[0].split(",")[0] == "MSKU"


class TestPureza:
    @pytest.mark.parametrize("prohibido", ["import streamlit", "import pandas", "pd.read"])
    def test_no_depende_de_streamlit_ni_pandas(self, prohibido):
        assert prohibido not in _CSV_IO.read_text(encoding="utf-8")

    def test_constantes_portadas_sin_cambios(self):
        assert ENCODINGS_CSV == ("utf-8-sig", "cp1252", "latin-1")
        assert BOMS_UTF16 == (b"\xff\xfe", b"\xfe\xff")
        assert DELIMITADORES_CSV == ",;\t|"
