"""Tests de `core.supply.recepcion_import` — recepción de una OC por planilla.

Pedido de Fede: una OC Emitida de 109 líneas no se puede recibir a mano SKU por
SKU. La planilla trae el total ACUMULADO recibido por SKU, igual que la
pantalla manual, y se cruza contra las líneas de la OC antes de guardar nada.

Capa pura: las líneas de la OC y las de la planilla entran por parámetro. Nada
toca disco ni Streamlit.
"""

from __future__ import annotations

import copy
from pathlib import Path

from core.supply.oc_import import consolidar_duplicados, detectar_columnas, parsear_lineas
from core.supply.recepcion_import import (
    COLUMNAS_PLANTILLA,
    DESTINO_CERRADA,
    DESTINO_PARCIAL,
    MOTIVO_FUERA_DE_OC,
    MOTIVO_REPETIDO_EN_OC,
    MOTIVO_SOLO_MAYUSCULAS,
    cruzar_recepcion,
    fechas_planilla,
    filas_plantilla,
    sin_cantidad_vacia,
)


def _oc(*lineas: tuple) -> list[dict]:
    """(sku, qty, recibido) -> líneas de OC como las guarda `save_oc`."""
    return [{"sku": s, "qty": q, "recibido": r, "eta": ""} for s, q, r in lineas]


def _pl(*lineas: tuple) -> list[dict]:
    """(sku, qty[, eta]) -> líneas como las devuelve `parsear_lineas`."""
    return [
        {"sku": ln[0], "qty": ln[1], "eta": ln[2] if len(ln) > 2 else ""}
        for ln in lineas
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Plantilla
# ─────────────────────────────────────────────────────────────────────────────


def test_plantilla_trae_header_y_una_fila_por_linea_de_la_oc():
    filas = filas_plantilla(_oc(("A-1", 10, 0), ("B-2", 5, 3)))
    assert filas[0] == list(COLUMNAS_PLANTILLA)
    assert filas[1:] == [["A-1", 10, 0, ""], ["B-2", 5, 3, ""]]


def test_plantilla_deja_vacia_la_columna_a_cargar():
    filas = filas_plantilla(_oc(("A-1", 10, 4)))
    assert filas[1][3] == ""


def test_plantilla_solo_la_ultima_columna_dice_cantidad():
    # detectar_columnas toma la PRIMERA columna con 'cantidad'/'qty'/'quantity':
    # si «Pedidas» o «Ya recibidas» la contuvieran, leería lo pedido como recibido.
    claves = ("cantidad", "qty", "quantity")
    for nombre in COLUMNAS_PLANTILLA[:3]:
        assert not any(c in nombre.lower() for c in claves), nombre
    assert "cantidad" in COLUMNAS_PLANTILLA[3].lower()


def test_plantilla_la_detecta_oc_import_con_cantidad_en_la_ultima_columna():
    filas = filas_plantilla(_oc(("A-1", 10, 0)))
    columnas = detectar_columnas(filas)
    assert columnas == {"fila_header": 0, "sku": 0, "qty": 3, "fecha": None}


def test_plantilla_de_oc_sin_lineas_trae_solo_el_header():
    assert filas_plantilla([]) == [list(COLUMNAS_PLANTILLA)]


def test_plantilla_ignora_lineas_que_no_son_dict():
    filas = filas_plantilla([None, {"sku": "A", "qty": 1, "recibido": 0}])
    assert filas[1:] == [["A", 1, 0, ""]]


def test_plantilla_recibido_faltante_sale_en_cero():
    filas = filas_plantilla([{"sku": "A", "qty": 2}])
    assert filas[1] == ["A", 2, 0, ""]


# ─────────────────────────────────────────────────────────────────────────────
# Filas sin cantidad
# ─────────────────────────────────────────────────────────────────────────────


def test_fila_con_cantidad_vacia_se_saltea_en_silencio():
    # La plantilla trae las 109 líneas; las que no llegaron quedan vacías y no
    # pueden aparecer como 109 descartes de 'cantidad no numerica'.
    filas = [list(COLUMNAS_PLANTILLA), ["A", 10, 0, ""], ["B", 5, 0, 5], ["C", 1, 0, "  "]]
    columnas = detectar_columnas(filas)
    lineas, descartadas = parsear_lineas(sin_cantidad_vacia(filas, columnas), columnas)
    assert lineas == [{"sku": "B", "qty": 5, "eta": ""}]
    assert descartadas == []


def test_sin_cantidad_vacia_conserva_la_numeracion_de_filas():
    filas = [list(COLUMNAS_PLANTILLA), ["A", 10, 0, ""], ["B", 5, 0, "x"]]
    columnas = detectar_columnas(filas)
    _, descartadas = parsear_lineas(sin_cantidad_vacia(filas, columnas), columnas)
    assert descartadas == [{"fila": 3, "valor": "B", "motivo": "cantidad no numerica"}]


def test_sin_cantidad_vacia_no_toca_header_ni_filas_de_arriba():
    filas = [["Recepción OC-1"], list(COLUMNAS_PLANTILLA), ["A", 1, 0, ""]]
    columnas = detectar_columnas(filas)
    resultado = sin_cantidad_vacia(filas, columnas)
    assert resultado[:2] == filas[:2]
    assert resultado[2] == []


def test_sin_cantidad_vacia_trata_la_celda_faltante_como_vacia():
    filas = [list(COLUMNAS_PLANTILLA), ["A", 1]]
    columnas = detectar_columnas(filas)
    assert sin_cantidad_vacia(filas, columnas)[1] == []


def test_sin_cantidad_vacia_deja_pasar_el_cero():
    # El 0 no es vacío: lo descarta parsear_lineas con su motivo.
    filas = [list(COLUMNAS_PLANTILLA), ["A", 1, 0, 0]]
    columnas = detectar_columnas(filas)
    assert sin_cantidad_vacia(filas, columnas)[1] == ["A", 1, 0, 0]


def test_sin_cantidad_vacia_no_muta_las_filas():
    filas = [list(COLUMNAS_PLANTILLA), ["A", 1, 0, ""]]
    original = copy.deepcopy(filas)
    sin_cantidad_vacia(filas, detectar_columnas(filas))
    assert filas == original


# ─────────────────────────────────────────────────────────────────────────────
# Cruce contra la OC
# ─────────────────────────────────────────────────────────────────────────────


def test_sku_de_la_oc_actualiza_el_recibido_con_el_acumulado():
    cruce = cruzar_recepcion(_oc(("A", 10, 2)), _pl(("A", 7)))
    assert cruce["lineas"][0]["recibido"] == 7
    assert cruce["aplicadas"] == [
        {"sku": "A", "pedidas": 10, "antes": 2, "despues": 7, "excede": False, "baja": False}
    ]


def test_el_acumulado_no_se_suma_a_lo_ya_recibido():
    # Subir dos veces la misma planilla no duplica nada.
    oc = _oc(("A", 10, 0))
    primera = cruzar_recepcion(oc, _pl(("A", 6)))
    segunda = cruzar_recepcion(primera["lineas"], _pl(("A", 6)))
    assert segunda["lineas"][0]["recibido"] == 6


def test_sku_que_no_esta_en_la_oc_se_rechaza_y_no_se_agrega():
    cruce = cruzar_recepcion(_oc(("A", 10, 0)), _pl(("A", 10), ("Z-9", 3)))
    assert [ln["sku"] for ln in cruce["lineas"]] == ["A"]
    assert cruce["rechazadas"] == [
        {"sku": "Z-9", "motivo": MOTIVO_FUERA_DE_OC, "sugerido": ""}
    ]


def test_sku_que_difiere_solo_en_mayusculas_se_rechaza_con_sugerencia():
    cruce = cruzar_recepcion(_oc(("Abc-1", 10, 0)), _pl(("ABC-1", 10)))
    assert cruce["lineas"][0]["recibido"] == 0
    assert cruce["rechazadas"] == [
        {"sku": "ABC-1", "motivo": MOTIVO_SOLO_MAYUSCULAS, "sugerido": "Abc-1"}
    ]


def test_mayusculas_con_varias_variantes_en_la_oc_las_sugiere_todas():
    cruce = cruzar_recepcion(_oc(("abc", 1, 0), ("Abc", 1, 0)), _pl(("ABC", 1)))
    assert cruce["rechazadas"][0]["sugerido"] == "Abc, abc"


def test_match_exacto_gana_aunque_haya_variante_en_mayusculas():
    cruce = cruzar_recepcion(_oc(("abc", 5, 0), ("ABC", 5, 0)), _pl(("ABC", 5)))
    assert cruce["rechazadas"] == []
    assert [ln["recibido"] for ln in cruce["lineas"]] == [0, 5]


def test_sku_repetido_en_la_oc_se_rechaza_por_ambiguo():
    oc = _oc(("A", 10, 0), ("A", 5, 0), ("B", 1, 0))
    cruce = cruzar_recepcion(oc, _pl(("A", 15), ("B", 1)))
    assert [ln["recibido"] for ln in cruce["lineas"]] == [0, 0, 1]
    assert cruce["rechazadas"] == [
        {"sku": "A", "motivo": MOTIVO_REPETIDO_EN_OC, "sugerido": ""}
    ]


def test_recibido_mayor_a_lo_pedido_se_aplica_con_aviso():
    cruce = cruzar_recepcion(_oc(("A", 10, 0)), _pl(("A", 12)))
    assert cruce["lineas"][0]["recibido"] == 12
    assert cruce["aplicadas"][0]["excede"] is True


def test_recibido_igual_a_lo_pedido_no_es_exceso():
    cruce = cruzar_recepcion(_oc(("A", 10, 0)), _pl(("A", 10)))
    assert cruce["aplicadas"][0]["excede"] is False


def test_acumulado_menor_a_lo_ya_recibido_se_aplica_marcado_como_baja():
    cruce = cruzar_recepcion(_oc(("A", 10, 8)), _pl(("A", 5)))
    assert cruce["lineas"][0]["recibido"] == 5
    assert cruce["aplicadas"][0]["baja"] is True


def test_lineas_que_no_vienen_en_la_planilla_no_se_tocan():
    oc = _oc(("A", 10, 0), ("B", 5, 3))
    cruce = cruzar_recepcion(oc, _pl(("A", 10)))
    assert cruce["lineas"][1] == oc[1]
    assert cruce["sin_tocar"] == 1


def test_la_linea_conserva_sus_otros_campos():
    oc = [{"sku": "A", "qty": 10, "recibido": 0, "eta": "2026-10-01", "nota": "x"}]
    cruce = cruzar_recepcion(oc, _pl(("A", 4)))
    assert cruce["lineas"][0] == {
        "sku": "A", "qty": 10, "recibido": 4, "eta": "2026-10-01", "nota": "x"
    }


def test_cruce_no_muta_las_entradas():
    oc = _oc(("A", 10, 0))
    planilla = _pl(("A", 4), ("Z", 1))
    oc_orig, pl_orig = copy.deepcopy(oc), copy.deepcopy(planilla)
    cruzar_recepcion(oc, planilla)
    assert oc == oc_orig
    assert planilla == pl_orig


def test_el_orden_de_las_lineas_es_el_de_la_oc():
    oc = _oc(("A", 1, 0), ("B", 1, 0), ("C", 1, 0))
    cruce = cruzar_recepcion(oc, _pl(("C", 1), ("A", 1)))
    assert [ln["sku"] for ln in cruce["lineas"]] == ["A", "B", "C"]
    assert [a["sku"] for a in cruce["aplicadas"]] == ["A", "C"]


def test_linea_de_oc_que_no_es_dict_se_conserva_tal_cual():
    oc = [None, {"sku": "A", "qty": 1, "recibido": 0}]
    cruce = cruzar_recepcion(oc, _pl(("A", 1)))
    assert cruce["lineas"][0] is None
    assert cruce["lineas"][1]["recibido"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Destino sugerido
# ─────────────────────────────────────────────────────────────────────────────


def test_destino_cerrada_si_todas_las_lineas_llegaron():
    cruce = cruzar_recepcion(_oc(("A", 10, 0), ("B", 5, 5)), _pl(("A", 10)))
    assert cruce["destino"] == DESTINO_CERRADA


def test_destino_parcial_si_falta_alguna_linea_aunque_no_venga_en_la_planilla():
    cruce = cruzar_recepcion(_oc(("A", 10, 0), ("B", 5, 0)), _pl(("A", 10)))
    assert cruce["destino"] == DESTINO_PARCIAL


def test_destino_cerrada_con_sobre_recepcion():
    cruce = cruzar_recepcion(_oc(("A", 10, 0)), _pl(("A", 11)))
    assert cruce["destino"] == DESTINO_CERRADA


def test_destino_parcial_si_una_linea_rechazada_queda_corta():
    cruce = cruzar_recepcion(_oc(("A", 10, 0)), _pl(("a", 10)))
    assert cruce["destino"] == DESTINO_PARCIAL


def test_cantidades_como_texto_o_float_se_leen_como_numero():
    oc = [{"sku": "A", "qty": "10", "recibido": 2.0}]
    cruce = cruzar_recepcion(oc, _pl(("A", 10)))
    assert cruce["aplicadas"][0]["pedidas"] == 10
    assert cruce["aplicadas"][0]["antes"] == 2
    assert cruce["destino"] == DESTINO_CERRADA


def test_caso_fede_109_lineas_llega_todo_menos_una():
    oc = _oc(*[(f"GMB-{i:03d}", 12, 0) for i in range(109)])
    planilla = _pl(*[(f"GMB-{i:03d}", 12) for i in range(108)])
    cruce = cruzar_recepcion(oc, planilla)
    assert len(cruce["aplicadas"]) == 108
    assert cruce["sin_tocar"] == 1
    assert cruce["rechazadas"] == []
    assert cruce["destino"] == DESTINO_PARCIAL


def test_de_la_plantilla_al_cruce_de_punta_a_punta():
    oc = _oc(("A", 10, 0), ("B", 5, 0), ("C", 2, 0))
    filas = filas_plantilla(oc)
    filas[1][3] = 10
    filas[2][3] = "3"
    filas.append(["Z", "", "", 4])
    columnas = detectar_columnas(filas)
    lineas, descartadas = parsear_lineas(sin_cantidad_vacia(filas, columnas), columnas)
    lineas, _ = consolidar_duplicados(lineas)
    cruce = cruzar_recepcion(oc, lineas)
    assert descartadas == []
    assert [ln["recibido"] for ln in cruce["lineas"]] == [10, 3, 0]
    assert [r["sku"] for r in cruce["rechazadas"]] == ["Z"]
    assert cruce["sin_tocar"] == 1


# ─────────────────────────────────────────────────────────────────────────────
# Fechas de la planilla
# ─────────────────────────────────────────────────────────────────────────────


def test_fechas_planilla_devuelve_las_distintas_ordenadas():
    lineas = _pl(("A", 1, "2026-09-20"), ("B", 1, "2026-09-18"), ("C", 1, "2026-09-20"))
    assert fechas_planilla(lineas) == ["2026-09-18", "2026-09-20"]


def test_fechas_planilla_ignora_las_vacias():
    assert fechas_planilla(_pl(("A", 1), ("B", 1, "  "))) == []


def test_modulo_sin_io_ni_dependencias_prohibidas():
    fuente = (
        Path(__file__).resolve().parents[1] / "core" / "supply" / "recepcion_import.py"
    ).read_text(encoding="utf-8")
    for prohibido in ("import streamlit", "persistence", "import pandas", "open(", "pd.read"):
        assert prohibido not in fuente, f"recepcion_import.py contiene {prohibido!r}"
