"""Tests de core/supply_oc_import.py — M37, carga masiva de órdenes de compra.

Pedido de Fede tras testear el punto 1: carga OCs de ~150 SKUs y hoy solo puede
hacerlo línea por línea (el diálogo de alta tope en 20 líneas). Este módulo es
la capa pura del import: recibe las filas del archivo como listas de Python y
devuelve líneas listas para `save_oc`. Quien lee el Excel/CSV es la página.

Reglas portadas de `mergeOCsLab` y `normDate` del Laboratorio de Compras
(`notes/supply-chain/originales/laboratorio-compras-2026-08-17.html` L745-756 y
L637). Los valores esperados se derivan de esas reglas, no se eligen a ojo.

Los invariantes que se defienden acá:

- **Header tolerante, pero acotado.** Se busca en las primeras 6 filas, por
  substring y sin distinguir mayúsculas: 'sku' + ('cantidad' | 'qty' |
  'quantity'), con 'fecha' | 'eta' opcional. Fuera de esa ventana no hay header.
- **Lo descartado se explica; lo vacío no.** Una fila de ejemplo o con cantidad
  inválida va a `descartadas` con motivo y número de fila del ARCHIVO (base 1,
  lo que el usuario ve en Excel). Una fila vacía o sin SKU se saltea en silencio:
  no es un error, es el final de la planilla.
- **Duplicado exacto se suma; duplicado por mayúsculas NO.** En el maestro de
  Gamboa hay 34 SKUs que difieren solo en capitalización y no se sabe si son
  productos distintos. Se avisa, no se decide.
- **Vacío no es cero.** Una celda de cantidad vacía es un dato que falta: se
  descarta como 'cantidad no numerica' para que el usuario la vea.
- **Redondeo de mitades hacia arriba.** floor(v + 0.5), como el Math.round del
  HTML; no el round() de Python.
- **Fechas en formato latino.** 'D/M/YYYY' es día primero.
- **Lógica pura.** Cero disco, cero Streamlit, cero capa de persistencia.

`descartadas[i]['valor']` es la celda de SKU (str, strip): el usuario busca la
fila por el SKU, no por la cantidad.

Forma exacta de los avisos de `consolidar_duplicados`:
    {'tipo': 'duplicado', 'sku': str, 'veces': int, 'qty_total': int}
    {'tipo': 'case', 'skus': list[str]}   # skus ordenado con sorted()
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.supply_oc_import import (
    consolidar_duplicados,
    detectar_columnas,
    parsear_lineas,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────


def _cols(sku: int = 0, qty: int = 1, fecha: int | None = None, fila_header: int = 0) -> dict:
    """Columnas con la forma que devuelve detectar_columnas, armadas a mano para
    probar parsear_lineas aislado de la detección."""
    return {"fila_header": fila_header, "sku": sku, "qty": qty, "fecha": fecha}


def _es_int(valor) -> bool:
    return isinstance(valor, int) and not isinstance(valor, bool)


# ─────────────────────────────────────────────────────────────────────────────
# detectar_columnas
# ─────────────────────────────────────────────────────────────────────────────


class TestDetectarColumnas:
    def test_header_en_fila_cero(self):
        resultado = detectar_columnas([["SKU", "Cantidad"], ["A1", 5]])
        assert resultado["fila_header"] == 0
        assert resultado["sku"] == 0
        assert resultado["qty"] == 1

    def test_header_despues_de_tres_filas_de_titulo(self):
        filas = [
            ["Orden de compra"],
            ["Proveedor X"],
            [],
            ["SKU", "Cantidad"],
            ["A1", 5],
        ]
        assert detectar_columnas(filas)["fila_header"] == 3

    def test_header_fuera_de_la_ventana_de_seis_filas(self):
        # Filas 0-5 son títulos; el header cae en la fila 6 -> fuera de ventana
        filas = [["Titulo"]] * 6 + [["SKU", "Cantidad"], ["A1", 5]]
        assert detectar_columnas(filas) is None

    def test_match_por_substring(self):
        resultado = detectar_columnas([["Codigo SKU", "Cantidad pedida"]])
        assert resultado is not None
        assert resultado["sku"] == 0
        assert resultado["qty"] == 1

    def test_case_insensitive(self):
        resultado = detectar_columnas([["sku", "CANTIDAD"]])
        assert resultado is not None
        assert resultado["sku"] == 0
        assert resultado["qty"] == 1

    def test_sinonimo_qty(self):
        resultado = detectar_columnas([["SKU", "Qty"]])
        assert resultado is not None
        assert resultado["qty"] == 1

    def test_sinonimo_quantity(self):
        resultado = detectar_columnas([["SKU", "Quantity"]])
        assert resultado is not None
        assert resultado["qty"] == 1

    def test_columna_fecha_presente(self):
        resultado = detectar_columnas([["SKU", "Cantidad", "Fecha de llegada"]])
        assert resultado["fecha"] == 2

    def test_columna_eta_presente(self):
        resultado = detectar_columnas([["SKU", "ETA", "Cantidad"]])
        assert resultado["fecha"] == 1
        assert resultado["qty"] == 2

    def test_sin_columna_fecha(self):
        resultado = detectar_columnas([["SKU", "Cantidad"]])
        assert resultado["fecha"] is None

    def test_falta_columna_sku(self):
        assert detectar_columnas([["Codigo", "Cantidad"], ["A1", 5]]) is None

    def test_falta_columna_cantidad(self):
        assert detectar_columnas([["SKU", "Descripcion"], ["A1", "x"]]) is None

    def test_lista_vacia(self):
        assert detectar_columnas([]) is None

    def test_orden_invertido(self):
        resultado = detectar_columnas([["Cantidad", "SKU"]])
        assert resultado["sku"] == 1
        assert resultado["qty"] == 0

    def test_fecha_no_cae_en_la_columna_del_sku(self):
        # 'SKU ETA' contiene 'eta', pero ya es la columna del SKU: se excluye
        resultado = detectar_columnas([["SKU ETA", "Cantidad"]])
        assert resultado["sku"] == 0
        assert resultado["qty"] == 1
        assert resultado["fecha"] is None

    def test_fecha_en_columna_propia_sigue_detectandose(self):
        resultado = detectar_columnas([["SKU", "Cantidad", "Fecha ETA"]])
        assert resultado["fecha"] == 2


# ─────────────────────────────────────────────────────────────────────────────
# parsear_lineas
# ─────────────────────────────────────────────────────────────────────────────


class TestParsearLineas:
    def test_fila_normal(self):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", 5]], _cols())
        assert ok == [{"sku": "A1", "qty": 5, "eta": ""}]
        assert _es_int(ok[0]["qty"])
        assert descartadas == []

    def test_qty_float_se_redondea(self):
        ok, _ = parsear_lineas([["SKU", "Cantidad"], ["A1", 10.6]], _cols())
        assert ok[0]["qty"] == 11
        assert _es_int(ok[0]["qty"])

    def test_qty_string_numerico(self):
        ok, _ = parsear_lineas([["SKU", "Cantidad"], ["A1", "25"]], _cols())
        assert ok[0]["qty"] == 25
        assert _es_int(ok[0]["qty"])

    def test_qty_cero_descartada(self):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", 0]], _cols())
        assert ok == []
        assert len(descartadas) == 1
        assert descartadas[0]["motivo"] == "cantidad <= 0"
        assert descartadas[0]["valor"] == "A1"

    def test_qty_negativa_descartada(self):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", -3]], _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "cantidad <= 0"
        assert descartadas[0]["valor"] == "A1"

    def test_qty_no_numerica_descartada(self):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", "abc"]], _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "cantidad no numerica"
        assert descartadas[0]["valor"] == "A1"

    def test_valor_de_descartada_es_la_celda_sku(self):
        # El usuario busca la fila por el SKU, no por la cantidad
        filas = [["SKU", "Cantidad"], ["  HAT-009 ", "abc"]]
        _, descartadas = parsear_lineas(filas, _cols())
        assert descartadas[0]["valor"] == "HAT-009"

    # floor(v+0.5), NO round(): Python redondea 2.5 a 2 (banker's rounding) y el Math.round del HTML a 3. Paridad con laboratorio-compras-2026-08-17.html L752.
    @pytest.mark.parametrize(
        "valor, esperado",
        [(2.5, 3), (3.5, 4), (10.4, 10), (10.6, 11), (0.6, 1)],
    )
    def test_redondeo_mitades_hacia_arriba(self, valor, esperado):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", valor]], _cols())
        assert descartadas == []
        assert ok[0]["qty"] == esperado
        assert _es_int(ok[0]["qty"])

    def test_redondeo_a_cero_descartada(self):
        # floor(0.4 + 0.5) = floor(0.9) = 0 -> cantidad <= 0
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", 0.4]], _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "cantidad <= 0"
        assert descartadas[0]["valor"] == "A1"

    # Vacío no es cero: es un dato que falta, y el usuario tiene que verlo.
    @pytest.mark.parametrize("celda", ["", None, "   "], ids=["vacia", "none", "espacios"])
    def test_cantidad_vacia_es_no_numerica(self, celda):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", celda]], _cols())
        assert ok == []
        assert len(descartadas) == 1
        assert descartadas[0]["motivo"] == "cantidad no numerica"
        assert descartadas[0]["valor"] == "A1"

    # Paridad PARCIAL con NUMX (laboratorio-compras-2026-08-17.html L636): se
    # portan quitar todos los espacios (incluido \xa0) y la coma decimal. NO se
    # porta el parseFloat que toma el prefijo numérico de un texto ("12 u" -> 12):
    # adivina sobre un dato ambiguo y preferimos que lo mire una persona. Tampoco
    # hay separador de miles: coma y punto juntos es 'cantidad no numerica'.
    @pytest.mark.parametrize(
        "celda, esperado",
        [
            ("1,5", 2),        # 1.5 -> floor(1.5 + 0.5) = 2
            ("2,5", 3),        # 2.5 -> floor(2.5 + 0.5) = 3
            (" 10 ", 10),
            ("1 000", 1000),   # espacio como separador
            ("1\xa0000", 1000),  # espacio duro de Excel
        ],
        ids=["coma-1_5", "coma-2_5", "espacios", "espacio-miles", "espacio-duro"],
    )
    def test_numx_parcial_acepta(self, celda, esperado):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", celda]], _cols())
        assert descartadas == []
        assert ok[0]["qty"] == esperado
        assert _es_int(ok[0]["qty"])

    @pytest.mark.parametrize(
        "celda",
        [
            "12 u", "12-15", "1.500,25", "1,500.25",
            "1_000", "1e3", "1E3", "inf", "nan",
            "٥",  # cinco árabe-índico: \d lo aceptaría, [0-9] no
        ],
        ids=[
            "prefijo-texto", "rango", "miles-punto", "miles-coma",
            "guion-bajo", "cientifica", "cientifica-mayus", "inf", "nan",
            "digito-unicode",
        ],
    )
    def test_numx_parcial_rechaza(self, celda):
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", celda]], _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "cantidad no numerica"
        assert descartadas[0]["valor"] == "A1"

    def test_signo_negativo_en_texto_es_numero_valido_pero_cantidad_invalida(self):
        # '-5' cumple el formato (signo opcional): el motivo es la cantidad, no
        # el formato. floor(-5 + 0.5) = -5 -> cantidad <= 0
        ok, descartadas = parsear_lineas([["SKU", "Cantidad"], ["A1", "-5"]], _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "cantidad <= 0"
        assert descartadas[0]["valor"] == "A1"

    def test_fila_de_ejemplo_descartada(self):
        filas = [["SKU", "Cantidad", "Notas"], ["A1", 5, "Ejemplo, no borrar"]]
        ok, descartadas = parsear_lineas(filas, _cols())
        assert ok == []
        assert descartadas[0]["motivo"] == "fila de ejemplo"
        assert descartadas[0]["valor"] == "A1"

    def test_fila_totalmente_vacia_no_se_registra(self):
        filas = [["SKU", "Cantidad"], [], ["", ""], ["A1", 5]]
        ok, descartadas = parsear_lineas(filas, _cols())
        assert ok == [{"sku": "A1", "qty": 5, "eta": ""}]
        assert descartadas == []

    def test_sku_vacio_o_espacios_no_se_registra(self):
        filas = [["SKU", "Cantidad"], ["", 5], ["   ", 7], ["A1", 5]]
        ok, descartadas = parsear_lineas(filas, _cols())
        assert [ln["sku"] for ln in ok] == ["A1"]
        assert descartadas == []

    def test_sku_con_espacios_se_limpia(self):
        ok, _ = parsear_lineas([["SKU", "Cantidad"], ["  A1  ", 5]], _cols())
        assert ok[0]["sku"] == "A1"

    def test_numero_de_fila_es_del_archivo_base_uno(self):
        # Header en índice 0 (fila 1 del Excel); fila mala en índice 1 -> fila 2
        filas = [["SKU", "Cantidad"], ["A1", 0]]
        _, descartadas = parsear_lineas(filas, _cols())
        assert descartadas[0]["fila"] == 2
        assert descartadas[0]["valor"] == "A1"

    def test_varias_descartadas_con_su_fila(self):
        # índice 1 ok | 2 qty 0 (fila 3) | 3 ok | 4 'abc' (fila 5) | 5 vacía |
        # 6 ejemplo (fila 7)
        filas = [
            ["SKU", "Cantidad", "Notas"],
            ["A1", 5, ""],
            ["A2", 0, ""],
            ["A3", 8, ""],
            ["A4", "abc", ""],
            [],
            ["A5", 9, "ejemplo"],
        ]
        ok, descartadas = parsear_lineas(filas, _cols())
        assert [ln["sku"] for ln in ok] == ["A1", "A3"]
        assert [(d["fila"], d["valor"], d["motivo"]) for d in descartadas] == [
            (3, "A2", "cantidad <= 0"),
            (5, "A4", "cantidad no numerica"),
            (7, "A5", "fila de ejemplo"),
        ]

    def test_sin_filas_validas(self):
        filas = [["SKU", "Cantidad"], ["A1", 0], ["A2", "abc"]]
        ok, descartadas = parsear_lineas(filas, _cols())
        assert ok == []
        assert [(d["fila"], d["valor"], d["motivo"]) for d in descartadas] == [
            (2, "A1", "cantidad <= 0"),
            (3, "A2", "cantidad no numerica"),
        ]

    def test_lineas_ok_sin_recibido(self):
        ok, _ = parsear_lineas([["SKU", "Cantidad"], ["A1", 5], ["A2", 3]], _cols())
        assert all("recibido" not in ln for ln in ok)


# ─────────────────────────────────────────────────────────────────────────────
# Normalización de fecha (normDate, HTML L637) — vía parsear_lineas
# ─────────────────────────────────────────────────────────────────────────────


def _eta(celda) -> str:
    filas = [["SKU", "Cantidad", "Fecha"], ["A1", 5, celda]]
    ok, _ = parsear_lineas(filas, _cols(fecha=2))
    return ok[0]["eta"]


class TestNormalizarFecha:
    def test_iso(self):
        assert _eta("2026-03-15") == "2026-03-15"

    def test_iso_con_hora_se_corta(self):
        assert _eta("2026-03-15T10:00:00") == "2026-03-15"

    def test_dia_primero(self):
        # 15/3/2026 -> año 2026, mes 3 -> '03', día 15
        assert _eta("15/3/2026") == "2026-03-15"

    def test_anio_de_dos_digitos(self):
        # 5/3/26 -> año '20' + '26', mes '03', día '05'
        assert _eta("5/3/26") == "2026-03-05"

    def test_celda_vacia(self):
        assert _eta("") == ""

    def test_sin_columna_fecha(self):
        filas = [["SKU", "Cantidad"], ["A1", 5], ["A2", 3]]
        ok, _ = parsear_lineas(filas, _cols(fecha=None))
        assert [ln["eta"] for ln in ok] == ["", ""]

    def test_texto_que_no_es_fecha(self):
        # Primeros 10 caracteres: 'a confirma'
        assert _eta("a confirmar con proveedor") == "a confirma"


# ─────────────────────────────────────────────────────────────────────────────
# consolidar_duplicados
# ─────────────────────────────────────────────────────────────────────────────


def _ln(sku: str, qty: int, eta: str = "") -> dict:
    return {"sku": sku, "qty": qty, "eta": eta}


def _avisos_exactos(avisos: list[dict]) -> list[dict]:
    return [a for a in avisos if a.get("tipo") == "duplicado"]


def _avisos_case(avisos: list[dict]) -> list[dict]:
    return [a for a in avisos if a.get("tipo") == "case"]


class TestConsolidarDuplicados:
    def test_sin_duplicados(self):
        lineas = [_ln("A1", 5), _ln("A2", 3)]
        consolidadas, avisos = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("A1", 5), _ln("A2", 3)]
        assert avisos == []

    def test_mismo_sku_exacto_se_suma(self):
        lineas = [_ln("X1", 100), _ln("X1", 50), _ln("X1", 25)]
        consolidadas, avisos = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("X1", 175)]
        assert avisos == [{"tipo": "duplicado", "sku": "X1", "veces": 3, "qty_total": 175}]

    def test_difieren_solo_en_mayusculas_no_se_consolidan(self):
        lineas = [_ln("AAG105", 10), _ln("Aag105", 4)]
        consolidadas, avisos = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("AAG105", 10), _ln("Aag105", 4)]
        assert avisos == [{"tipo": "case", "skus": ["AAG105", "Aag105"]}]

    def test_skus_del_aviso_case_van_ordenados(self):
        # Entrada en orden inverso al alfabético: 'skus' sale sorted()
        # ('AAG105' < 'Aag105' porque 'A' < 'a'), no en orden de aparición.
        lineas = [_ln("Aag105", 4), _ln("AAG105", 10)]
        consolidadas, avisos = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("Aag105", 4), _ln("AAG105", 10)]
        assert avisos == [{"tipo": "case", "skus": ["AAG105", "Aag105"]}]

    def test_mezcla_exacto_y_case(self):
        lineas = [
            _ln("X1", 10),
            _ln("AAG105", 7),
            _ln("X1", 5),
            _ln("Aag105", 2),
        ]
        consolidadas, avisos = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("X1", 15), _ln("AAG105", 7), _ln("Aag105", 2)]

        # El orden entre avisos de distinto tipo no está definido: se filtran por tipo.
        assert len(avisos) == 2
        assert _avisos_exactos(avisos) == [
            {"tipo": "duplicado", "sku": "X1", "veces": 2, "qty_total": 15}
        ]
        assert _avisos_case(avisos) == [{"tipo": "case", "skus": ["AAG105", "Aag105"]}]

    def test_orden_de_aparicion(self):
        lineas = [_ln("C3", 1), _ln("A1", 2), _ln("B2", 3), _ln("A1", 4)]
        consolidadas, _ = consolidar_duplicados(lineas)
        assert [ln["sku"] for ln in consolidadas] == ["C3", "A1", "B2"]

    # ETA al consolidar = la de la PRIMERA aparición del SKU. Es una decisión, no
    # un descuido: se preserva el orden de aparición igual que con las líneas, y
    # no se "completan huecos" con la ETA de una fila posterior. Si la primera
    # viene vacía, queda vacía.

    def test_eta_consolidada_es_la_primera(self):
        lineas = [_ln("X1", 10, "2026-03-01"), _ln("X1", 5, "2026-04-15")]
        consolidadas, _ = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("X1", 15, "2026-03-01")]

    def test_eta_consolidada_primera_vacia_gana(self):
        lineas = [_ln("X1", 10, ""), _ln("X1", 5, "2026-04-15")]
        consolidadas, _ = consolidar_duplicados(lineas)
        assert consolidadas == [_ln("X1", 15, "")]

    def test_lista_vacia(self):
        assert consolidar_duplicados([]) == ([], [])

    def test_una_sola_linea(self):
        consolidadas, avisos = consolidar_duplicados([_ln("A1", 5)])
        assert consolidadas == [_ln("A1", 5)]
        assert avisos == []


# ─────────────────────────────────────────────────────────────────────────────
# End-to-end — archivo de proveedor simulado
# ─────────────────────────────────────────────────────────────────────────────


class TestCasoCompleto:
    def test_archivo_de_proveedor(self):
        filas = [
            ["Orden de compra — Proveedor Shenzhen"],                       # 0 título
            ["Emitida por: Compras"],                                       # 1 título
            ["SKU", "Descripción", "Cantidad", "Fecha ETA"],                # 2 header (fila 3)
            ["HAT-EJ", "Ejemplo: no borrar", 10, "1/10/2026"],              # 3 ejemplo (fila 4)
            ["HAT-001", "Sombrero negro", 100, "15/10/2026"],               # 4 ok
            ["HAT-002", "Sombrero gris", 50.0, "15/10/2026"],               # 5 ok
            ["HAT-003", "Gorra", "30", "20/10/2026"],                       # 6 ok
            ["HAT-001", "Sombrero negro", 25, "15/10/2026"],                # 7 ok, duplicado exacto
            ["HAT-004", "Visera", 12, ""],                                  # 8 ok, sin ETA
            ["HAT-005", "Boina", 0, "20/10/2026"],                          # 9 qty 0 (fila 10)
            [],                                                             # 10 vacía
        ]

        columnas = detectar_columnas(filas)
        assert columnas == {"fila_header": 2, "sku": 0, "qty": 2, "fecha": 3}

        ok, descartadas = parsear_lineas(filas, columnas)
        assert ok == [
            {"sku": "HAT-001", "qty": 100, "eta": "2026-10-15"},
            {"sku": "HAT-002", "qty": 50, "eta": "2026-10-15"},
            {"sku": "HAT-003", "qty": 30, "eta": "2026-10-20"},
            {"sku": "HAT-001", "qty": 25, "eta": "2026-10-15"},
            {"sku": "HAT-004", "qty": 12, "eta": ""},
        ]
        assert [(d["fila"], d["valor"], d["motivo"]) for d in descartadas] == [
            (4, "HAT-EJ", "fila de ejemplo"),
            (10, "HAT-005", "cantidad <= 0"),
        ]

        consolidadas, avisos = consolidar_duplicados(ok)
        # HAT-001: 100 + 25 = 125, en la posición de su primera aparición y con
        # la ETA de esa primera fila.
        assert consolidadas == [
            {"sku": "HAT-001", "qty": 125, "eta": "2026-10-15"},
            {"sku": "HAT-002", "qty": 50, "eta": "2026-10-15"},
            {"sku": "HAT-003", "qty": 30, "eta": "2026-10-20"},
            {"sku": "HAT-004", "qty": 12, "eta": ""},
        ]
        assert avisos == [
            {"tipo": "duplicado", "sku": "HAT-001", "veces": 2, "qty_total": 125}
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Pureza
# ─────────────────────────────────────────────────────────────────────────────


class TestPureza:
    def test_modulo_sin_io_ni_dependencias_prohibidas(self):
        fuente = (
            Path(__file__).resolve().parents[1] / "core" / "supply_oc_import.py"
        ).read_text(encoding="utf-8")
        for prohibido in (
            "import streamlit",
            "supply_persistence",
            "import pandas",
            "open(",
            "pd.read",
        ):
            assert prohibido not in fuente, f"core/supply_oc_import.py contiene {prohibido!r}"
