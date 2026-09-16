"""Tests de `_leer_planilla` — M37, lectura del archivo para el import de OCs.

`modules/pages/supply_ordenes.py::_leer_planilla(data, nombre) -> list[list]`
convierte el archivo que sube el AM en filas crudas para `core.supply_oc_import`.
NO parsea ni valida contenido: eso es del motor. Solo lee.

Es la pieza que puede romper en silencio, y por eso tiene tests propios: los
tres defaults de pandas que hay que desactivar no fallan, devuelven datos mal.

- **`header=None`.** El motor busca el header por su cuenta en las primeras 6
  filas. Si pandas se come la primera fila como encabezado, el motor no la ve y
  la planilla entera queda sin header detectable.
- **`dtype=object`.** Sin eso, una columna de SKU que sean todos dígitos se
  castea a número y '001' se vuelve 1. El SKU deja de matchear el maestro y
  nadie se entera.
- **NaN a ''.** El motor espera la celda vacía como '', y un NaN que viaja hasta
  la UI revienta el render de la tabla.
- **datetime a str.** El lector de Excel devuelve datetime en las celdas con
  formato fecha; el motor normaliza strings.

A diferencia de los módulos de `core/supply_*`, acá se importa una página de UI
(trae streamlit). Es correcto: esto ES la capa de UI, no la capa pura.

Los archivos se arman EN MEMORIA. Nada toca disco.
"""

from __future__ import annotations

import datetime
from io import BytesIO

import openpyxl
import pytest

from core.supply_oc_import import detectar_columnas, parsear_lineas
from modules.pages.supply_ordenes import _leer_planilla


# ─────────────────────────────────────────────────────────────────────────────
# Helpers — archivos en memoria
# ─────────────────────────────────────────────────────────────────────────────


def _xlsx(filas: list[list], filas_hoja2: list[list] | None = None) -> bytes:
    """Arma un .xlsx en memoria. `filas_hoja2` agrega una segunda hoja."""
    wb = openpyxl.Workbook()
    hoja = wb.active
    hoja.title = "Hoja1"
    for fila in filas:
        hoja.append(fila)
    if filas_hoja2 is not None:
        hoja2 = wb.create_sheet("Hoja2")
        for fila in filas_hoja2:
            hoja2.append(fila)
    buffer = BytesIO()
    wb.save(buffer)
    return buffer.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
# .xlsx
# ─────────────────────────────────────────────────────────────────────────────


class TestLeerXlsx:
    def test_xlsx_simple(self):
        filas = _leer_planilla(_xlsx([["A1", 5], ["A2", 3]]), "oc.xlsx")
        assert filas == [["A1", 5], ["A2", 3]]

    def test_la_primera_fila_no_se_consume_como_header(self):
        # Con el default de pandas, 'SKU'/'Cantidad' serían nombres de columna y
        # la fila desaparecería del resultado.
        filas = _leer_planilla(_xlsx([["SKU", "Cantidad"], ["A1", 5]]), "oc.xlsx")
        assert filas[0] == ["SKU", "Cantidad"]
        assert len(filas) == 2

    def test_sku_de_solo_digitos_sigue_siendo_str(self):
        # Sin dtype=object, '001' se castea a 1 y deja de matchear el maestro
        filas = _leer_planilla(_xlsx([["001", 5], ["002", 3]]), "oc.xlsx")
        assert filas[0][0] == "001"
        assert isinstance(filas[0][0], str)
        assert filas[1][0] == "002"

    def test_celda_vacia_es_string_vacio(self):
        filas = _leer_planilla(_xlsx([["A1", 5], ["A2", None]]), "oc.xlsx")
        assert filas[1][1] == ""

    def test_celda_con_formato_fecha(self):
        filas = _leer_planilla(
            _xlsx([["A1", 5, datetime.date(2026, 3, 15)]]), "oc.xlsx"
        )
        celda = filas[0][2]
        assert isinstance(celda, str)
        assert celda.startswith("2026-03-15")

    def test_lee_la_primera_hoja(self):
        data = _xlsx([["PRIMERA", 1]], filas_hoja2=[["SEGUNDA", 2]])
        filas = _leer_planilla(data, "oc.xlsx")
        assert filas[0][0] == "PRIMERA"
        assert all("SEGUNDA" not in [str(c) for c in fila] for fila in filas)

    def test_filas_de_distinto_largo(self):
        filas = _leer_planilla(
            _xlsx([["SKU", "Cantidad", "Fecha"], ["A1", 5], ["A2", 3, "15/3/2026"]]),
            "oc.xlsx",
        )
        assert len(filas) == 3
        assert filas[1][0] == "A1"
        # La celda que la fila no traía se completa como vacía, no como NaN
        assert filas[1][2] == ""

    def test_xlsx_vacio(self):
        assert _leer_planilla(_xlsx([]), "oc.xlsx") == []

    def test_bytes_que_no_son_xlsx(self):
        with pytest.raises(ValueError) as exc:
            _leer_planilla(b"esto no es un excel", "oc.xlsx")
        assert str(exc.value).strip()
        assert "oc.xlsx" in str(exc.value)


# ─────────────────────────────────────────────────────────────────────────────
# .csv
# ─────────────────────────────────────────────────────────────────────────────


class TestLeerCsv:
    def test_csv_separado_por_comas(self):
        filas = _leer_planilla(b"SKU,Cantidad\nA1,5\nA2,3\n", "oc.csv")
        assert filas == [["SKU", "Cantidad"], ["A1", "5"], ["A2", "3"]]

    def test_csv_separado_por_punto_y_coma(self):
        # Excel en español exporta con ';'
        filas = _leer_planilla(b"SKU;Cantidad\nA1;5\nA2;3\n", "oc.csv")
        assert filas == [["SKU", "Cantidad"], ["A1", "5"], ["A2", "3"]]

    def test_csv_con_bom(self):
        # utf-8-sig se come el BOM que Excel escribe al principio del archivo
        filas = _leer_planilla(b"\xef\xbb\xbfSKU,Cantidad\nA1,5\n", "oc.csv")
        assert filas[0][0] == "SKU"
        assert not filas[0][0].startswith("﻿")

    def test_la_primera_fila_no_se_consume_como_header(self):
        filas = _leer_planilla(b"SKU,Cantidad\nA1,5\n", "oc.csv")
        assert filas[0] == ["SKU", "Cantidad"]
        assert len(filas) == 2

    def test_celda_vacia_es_string_vacio(self):
        filas = _leer_planilla(b"SKU,Cantidad\nA1,\n", "oc.csv")
        assert filas[1][1] == ""

    def test_sku_de_solo_digitos_sigue_siendo_str(self):
        filas = _leer_planilla(b"SKU,Cantidad\n001,5\n", "oc.csv")
        assert filas[1][0] == "001"
        assert isinstance(filas[1][0], str)

    def test_csv_de_una_sola_columna(self):
        # Devuelve las filas de una columna, NO lanza. Con el `sep=None` de
        # pandas este caso salía corrupto: su sniffer no acota los delimitadores
        # y elegía la letra 'U' de 'SKU', partiendo cada SKU en dos. Por eso
        # _sep_csv sniffea solo entre , ; tab | y cae a ',' cuando no hay pistas.
        filas = _leer_planilla(b"SKU\nA1\nA2", "oc.csv")
        assert filas == [["SKU"], ["A1"], ["A2"]]

    def test_bytes_que_no_son_csv(self):
        # No lanza: la basura pasa al motor, que no va a encontrar header y deja
        # que la pantalla lo diga. Decisión tomada: una regla menos acá.
        filas = _leer_planilla(b"\x00\x01\x02\x03", "oc.csv")
        assert detectar_columnas(filas) is None

    def test_csv_vacio(self):
        with pytest.raises(ValueError) as exc:
            _leer_planilla(b"", "oc.csv")
        assert str(exc.value).strip()
        assert "oc.csv" in str(exc.value)


# Los proveedores exportan desde su Excel y su locale (Peru, Ecuador, Bolivia,
# China, Pakistan). Asumir UTF-8 en todos rechaza archivos buenos: un CSV en
# UTF-16 (lo que escribe el "Guardar como" de Excel en algunas variantes) no se
# podia ni abrir. La cascada es BOM utf-16 -> utf-8-sig -> cp1252 -> latin-1.
_TEXTO_CON_ACENTOS = "SKU,Desc\nA1,Ñandú Algodón\n"
_ESPERADO_CON_ACENTOS = [["SKU", "Desc"], ["A1", "Ñandú Algodón"]]


class TestEncodingCsv:
    def test_utf16_con_bom(self):
        filas = _leer_planilla(_TEXTO_CON_ACENTOS.encode("utf-16"), "oc.csv")
        assert filas == _ESPERADO_CON_ACENTOS

    def test_cp1252_con_acentos(self):
        # Excel en Windows en español. En UTF-8 estos bytes no decodifican.
        filas = _leer_planilla(_TEXTO_CON_ACENTOS.encode("cp1252"), "oc.csv")
        assert filas == _ESPERADO_CON_ACENTOS

    def test_utf8_con_acentos_sigue_andando(self):
        filas = _leer_planilla(_TEXTO_CON_ACENTOS.encode("utf-8"), "oc.csv")
        assert filas == _ESPERADO_CON_ACENTOS

    def test_latin1_como_ultimo_recurso(self):
        # 0x81 no existe en cp1252: el archivo cae al ultimo escalon y se lee
        # igual, en vez de rechazarse.
        filas = _leer_planilla(b"SKU,Desc\nA1,\x81raro\n", "oc.csv")
        assert filas[0] == ["SKU", "Desc"]
        assert filas[1][0] == "A1"

    def test_el_sniffer_y_la_lectura_comparten_encoding(self):
        # Punto y coma dentro de un UTF-16: si el sniffer mirara un texto
        # decodificado distinto del que parsea pandas, el separador no aparecería.
        filas = _leer_planilla("SKU;Cantidad\nA1;5\n".encode("utf-16"), "oc.csv")
        assert filas == [["SKU", "Cantidad"], ["A1", "5"]]


# ─────────────────────────────────────────────────────────────────────────────
# Extensión
# ─────────────────────────────────────────────────────────────────────────────


class TestExtension:
    def test_extension_desconocida(self):
        with pytest.raises(ValueError):
            _leer_planilla(b"SKU,Cantidad\nA1,5\n", "archivo.txt")

    def test_sin_extension(self):
        with pytest.raises(ValueError):
            _leer_planilla(b"SKU,Cantidad\nA1,5\n", "archivo")

    def test_xlsx_en_mayusculas(self):
        filas = _leer_planilla(_xlsx([["A1", 5]]), "OC.XLSX")
        assert filas == [["A1", 5]]

    def test_csv_en_mayusculas(self):
        filas = _leer_planilla(b"SKU,Cantidad\nA1,5\n", "OC.CSV")
        assert filas[1] == ["A1", "5"]

    def test_mensaje_menciona_las_extensiones_aceptadas(self):
        with pytest.raises(ValueError) as exc:
            _leer_planilla(b"x", "archivo.pdf")
        mensaje = str(exc.value).lower()
        assert "xlsx" in mensaje
        assert "csv" in mensaje


# ─────────────────────────────────────────────────────────────────────────────
# Las dos piezas juntas
# ─────────────────────────────────────────────────────────────────────────────


class TestIntegracionConElMotor:
    def test_planilla_realista_de_proveedor(self):
        data = _xlsx(
            [
                ["Orden de compra - Proveedor Shenzhen"],          # 0 título
                ["Emitida por: Compras"],                          # 1 título
                ["SKU", "Cantidad", "Fecha"],                      # 2 header
                ["HAT-EJ", 10, "Ejemplo: no borrar"],              # 3 ejemplo
                ["HAT-001", 100, "15/10/2026"],                    # 4 ok
                ["HAT-002", 50, datetime.date(2026, 10, 20)],      # 5 ok, fecha real
                ["HAT-003", 30, None],                             # 6 ok, sin fecha
            ]
        )

        filas = _leer_planilla(data, "oc_shenzhen.xlsx")

        columnas = detectar_columnas(filas)
        assert columnas == {"fila_header": 2, "sku": 0, "qty": 1, "fecha": 2}

        ok, descartadas = parsear_lineas(filas, columnas)
        assert ok == [
            {"sku": "HAT-001", "qty": 100, "eta": "2026-10-15"},
            # La celda con formato fecha llega como str y el motor la corta a ISO
            {"sku": "HAT-002", "qty": 50, "eta": "2026-10-20"},
            {"sku": "HAT-003", "qty": 30, "eta": ""},
        ]
        assert [(d["fila"], d["valor"], d["motivo"]) for d in descartadas] == [
            (4, "HAT-EJ", "fila de ejemplo")
        ]
