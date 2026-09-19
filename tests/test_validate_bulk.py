"""Tests de core.bulk.parser.validate_bulk — contrato INV-5.

Amazon hace rollback total: una sola fila invalida rechaza el archivo entero
(INV-5.4, evidencia report__60_ -> 0 de 8 filas aplicadas). Estos tests
verifican que cada defecto conocido se detecte ANTES de la descarga.

Datos 100% sinteticos. Los IDs numericos tienen la forma de los reales
(~15 digitos) pero no corresponden a ninguna cuenta.

Contrato: .claude/skills/ppc-business-invariants.md — INV-5.
"""

from __future__ import annotations

import pandas as pd
import pytest

from core.bulk.parser import ErrorBulk, validate_bulk


# ============================================================================
# Helpers
# ============================================================================

# IDs sinteticos con la forma que Amazon devuelve en modo REFERENCIA (INV-5.1).
CAMPAIGN_ID = "132313349237695"
AD_GROUP_ID = "271884452900011"
KEYWORD_ID = "375512123676480"

# Fila valida de referencia: negativo a nivel campana (INV-5.2, primera fila
# de la tabla). Todo test rompe este baseline campo por campo.
_FILA_BASE: dict[str, object] = {
    "Product": "Sponsored Products",
    "Entity": "Campaign Negative Keyword",
    "Operation": "Create",
    "Campaign ID": CAMPAIGN_ID,
    "Ad Group ID": "",
    "Keyword ID": "",
    "State": "enabled",
    "Bid": "",
    "Keyword Text": "zapatos rojos",
    "Match Type": "Negative Exact",
}


def _bulk(**kw: object) -> pd.DataFrame:
    """DataFrame de UNA fila valida, con los campos de kw pisados."""
    fila = dict(_FILA_BASE)
    fila.update(kw)
    return pd.DataFrame([fila], columns=list(_FILA_BASE))


def _bulk_filas(*filas: dict) -> pd.DataFrame:
    """DataFrame de N filas, cada dict pisando el baseline."""
    registros = []
    for kw in filas:
        fila = dict(_FILA_BASE)
        fila.update(kw)
        registros.append(fila)
    return pd.DataFrame(registros, columns=list(_FILA_BASE))


def _kw_create(**kw: object) -> dict:
    """Baseline de una keyword positiva nueva."""
    base = {
        "Entity": "Keyword",
        "Operation": "Create",
        "Ad Group ID": AD_GROUP_ID,
        "Keyword ID": "",
        "Match Type": "Exact",
        "Bid": 1.25,
    }
    base.update(kw)
    return base


def _neg_kw(**kw: object) -> dict:
    """Baseline de un negativo a nivel ad group."""
    base = {
        "Entity": "Negative Keyword",
        "Ad Group ID": AD_GROUP_ID,
        "Match Type": "Negative Exact",
        "Bid": "",
    }
    base.update(kw)
    return base


def _errores(res: list[ErrorBulk]) -> list[ErrorBulk]:
    return [e for e in res if e.severidad == "error"]


def _warnings(res: list[ErrorBulk]) -> list[ErrorBulk]:
    return [e for e in res if e.severidad == "warning"]


def _cols(res: list[ErrorBulk]) -> set[str]:
    return {e.columna for e in res}


# ============================================================================
# Bulks validos — la lista tiene que venir vacia
# ============================================================================

def test_campaign_negative_keyword_valido_no_da_errores():
    """INV-5.2 fila 1: Campaign ID numerico, Ad Group ID y Keyword ID vacios."""
    assert validate_bulk(_bulk()) == []


def test_negative_keyword_a_nivel_ad_group_valido():
    """INV-5.2 fila 2: negativo dentro de un ad group, con los dos IDs."""
    assert validate_bulk(_bulk(**_neg_kw())) == []


def test_keyword_create_valida():
    """INV-5.2 fila 3: keyword nueva, Keyword ID vacio, bid > 0."""
    assert validate_bulk(_bulk(**_kw_create())) == []


def test_keyword_update_con_keyword_id_valida():
    """INV-5.2 fila 4: update de bid, Keyword ID numerico obligatorio."""
    fila = _kw_create(Operation="Update", **{"Keyword ID": KEYWORD_ID})
    assert validate_bulk(_bulk(**fila)) == []


# ============================================================================
# E2 — Product
# ============================================================================

def test_e2_product_distinto_de_sponsored_products():
    res = validate_bulk(_bulk(Product="Sponsored Brands"))
    assert _cols(_errores(res)) == {"Product"}
    assert "Sponsored Products" in _errores(res)[0].mensaje


# ============================================================================
# E3 — Entity
# ============================================================================

def test_e3_entity_con_casing_incorrecto_es_invalido():
    """'Negative keyword' con k minuscula NO es el valor canonico."""
    res = validate_bulk(_bulk(Entity="Negative keyword"))
    errores = _errores(res)
    assert "Entity" in _cols(errores)
    assert any("Negative Keyword" in e.mensaje for e in errores)


def test_e3_entity_inventado_es_invalido():
    res = validate_bulk(_bulk(Entity="Negativo"))
    assert "Entity" in _cols(_errores(res))


# ============================================================================
# E4 — Operation
# ============================================================================

def test_e4_operation_invalida():
    res = validate_bulk(_bulk(Operation="Crear"))
    errores = _errores(res)
    assert _cols(errores) == {"Operation"}
    assert "Create" in errores[0].mensaje


# ============================================================================
# E5 — State
# ============================================================================

def test_e5_state_invalido():
    """Amazon quiere 'enabled' en minuscula, no 'Enabled' ni 'activo'."""
    res = validate_bulk(_bulk(State="Enabled"))
    assert _cols(_errores(res)) == {"State"}


# ============================================================================
# E6 — Match Type segun Entity (INV-5.3)
# ============================================================================

def test_e6_campaign_negative_exact_esta_prohibido():
    """report__60_: 8/8 filas rechazadas por este unico valor."""
    res = validate_bulk(_bulk(**{"Match Type": "campaignNegativeExact"}))
    errores = _errores(res)
    assert _cols(errores) == {"Match Type"}
    mensaje = errores[0].mensaje
    assert 'Invalid value: "campaignNegativeExact" for column: "Match Type"' in mensaje
    assert "Negative Exact" in mensaje


def test_e6_camelcase_negative_exact_sugiere_title_case():
    """negativeExact NO tiene validacion empirica: se exige Title Case."""
    res = validate_bulk(_bulk(**{"Match Type": "negativeExact"}))
    errores = _errores(res)
    assert _cols(errores) == {"Match Type"}
    assert "'Negative Exact'" in errores[0].mensaje


def test_e6_camelcase_exact_en_keyword_sugiere_title_case():
    fila = _kw_create(**{"Match Type": "exact"})
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Match Type"}
    assert "'Exact'" in errores[0].mensaje


def test_e6_match_type_positivo_en_entity_negativa_es_error():
    res = validate_bulk(_bulk(**{"Match Type": "Exact"}))
    assert _cols(_errores(res)) == {"Match Type"}


def test_e6_match_type_negativo_en_keyword_es_error():
    fila = _kw_create(**{"Match Type": "Negative Exact"})
    res = validate_bulk(_bulk(**fila))
    assert _cols(_errores(res)) == {"Match Type"}


def test_e6_product_targeting_acepta_match_type_positivo():
    fila = _kw_create(Entity="Product Targeting", **{"Match Type": "Broad"})
    res = validate_bulk(_bulk(**fila))
    assert "Match Type" not in _cols(_errores(res))


# ============================================================================
# E7 — Campos obligatorios por Entity (INV-5.2)
# ============================================================================

def test_e7_campaign_negative_keyword_con_ad_group_id_es_error_de_nivel():
    """El negativo a nivel campana no pertenece a ningun ad group."""
    res = validate_bulk(_bulk(**{"Ad Group ID": AD_GROUP_ID}))
    errores = _errores(res)
    assert _cols(errores) == {"Ad Group ID"}
    assert "Negative Keyword" in errores[0].mensaje


def test_e7_keyword_update_sin_keyword_id():
    fila = _kw_create(Operation="Update", **{"Keyword ID": ""})
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Keyword ID"}


def test_e7_keyword_create_con_keyword_id_lleno():
    fila = _kw_create(**{"Keyword ID": KEYWORD_ID})
    res = validate_bulk(_bulk(**fila))
    assert _cols(_errores(res)) == {"Keyword ID"}


def test_e7_negative_keyword_sin_ad_group_id():
    fila = _neg_kw(**{"Ad Group ID": ""})
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Ad Group ID"}
    assert "Missing Parent ID" in errores[0].mensaje


def test_e7_sin_campaign_id_es_error():
    res = validate_bulk(_bulk(**{"Campaign ID": ""}))
    assert _cols(_errores(res)) == {"Campaign ID"}


# ============================================================================
# E8 — Formato de los IDs
# ============================================================================

def test_e8_id_con_decimal_es_error():
    """375512123676480.0 = el ID se parseo como float."""
    res = validate_bulk(_bulk(**{"Campaign ID": "375512123676480.0"}))
    errores = _errores(res)
    assert _cols(errores) == {"Campaign ID"}
    assert "decimales" in errores[0].mensaje


def test_e8_id_en_notacion_cientifica_es_error():
    res = validate_bulk(_bulk(**{"Campaign ID": "4.42e+14"}))
    errores = _errores(res)
    assert _cols(errores) == {"Campaign ID"}
    assert len(errores) == 1, "un solo mensaje por celda, el mas especifico"
    assert "cientifica" in errores[0].mensaje


def test_e8_id_nan_es_error():
    fila = _neg_kw(**{"Ad Group ID": "nan"})
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Ad Group ID"}
    assert "nan" in errores[0].mensaje


def test_e8_alias_no_numerico_no_es_error():
    """INV-5.1 modo ALIAS: un string arbitrario es valido al crear."""
    fila = _kw_create(**{
        "Campaign ID": "SU-AGE-HARVEST-001",
        "Ad Group ID": "SU-AGE-HARVEST-001-AG",
    })
    assert validate_bulk(_bulk(**fila)) == []


# ============================================================================
# E9 — Keyword Text
# ============================================================================

def test_e9_keyword_text_vacio_es_error():
    res = validate_bulk(_bulk(**{"Keyword Text": ""}))
    assert _cols(_errores(res)) == {"Keyword Text"}


@pytest.mark.parametrize("entity_row", [{}, _neg_kw()], ids=["campaign_negative", "adgroup_negative"])
@pytest.mark.parametrize("keyword_text, match_type, fragment", [
    ("100% algodon", "Negative Exact", "«%»"),
    ("bolsa de dormir 1/2 tog", "Negative Exact", "«/»"),
    ("bolsa de dormir para bebe", "Negative Phrase", "5 palabras"),
    ("uno dos tres cuatro cinco seis siete ocho nueve diez once", "Negative Exact", "11 palabras"),
    ("x" * 81, "Negative Exact", "81 caracteres"),
])
def test_e9_negative_keyword_text_amazon_rejects_is_an_error(entity_row, keyword_text, match_type, fragment):
    res = validate_bulk(_bulk(**{**entity_row, "Keyword Text": keyword_text, "Match Type": match_type}))

    errores = _errores(res)
    assert _cols(errores) == {"Keyword Text"}
    assert fragment in errores[0].mensaje


def test_e9_negative_keyword_text_within_limits_is_valid():
    fila = _neg_kw(**{"Keyword Text": "mac & cheese bowl", "Match Type": "Negative Phrase"})
    assert validate_bulk(_bulk(**fila)) == []


def test_e9_positive_keyword_text_keeps_its_current_rules():
    fila = _kw_create(**{"Keyword Text": "tallas 1/2 y 3/4 para bebe recien nacido de invierno calido"})
    assert _errores(validate_bulk(_bulk(**fila))) == []


# ============================================================================
# E10 — Bid
# ============================================================================

def test_e10_keyword_sin_bid_es_error():
    fila = _kw_create(Bid="")
    res = validate_bulk(_bulk(**fila))
    assert _cols(_errores(res)) == {"Bid"}


def test_e10_keyword_con_bid_cero_es_error():
    fila = _kw_create(Bid=0)
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Bid"}
    assert "mayor a 0" in errores[0].mensaje


def test_e10_keyword_con_bid_no_numerico_es_error():
    fila = _kw_create(Bid="$1.20")
    res = validate_bulk(_bulk(**fila))
    assert _cols(_errores(res)) == {"Bid"}


def test_e10_negative_keyword_con_bid_es_error():
    """Amazon rechaza un negativo que traiga bid."""
    fila = _neg_kw(Bid=0.75)
    res = validate_bulk(_bulk(**fila))
    errores = _errores(res)
    assert _cols(errores) == {"Bid"}
    assert "no lleva Bid" in errores[0].mensaje


def test_e10_campaign_negative_keyword_con_bid_es_error():
    res = validate_bulk(_bulk(Bid=0.75))
    assert _cols(_errores(res)) == {"Bid"}


# ============================================================================
# Acumulacion y casos borde
# ============================================================================

def test_una_fila_con_tres_problemas_devuelve_tres_errores():
    """No se corta en el primero: el AM tiene que ver todo de una."""
    res = validate_bulk(_bulk(
        Entity="Negative keyword",
        Operation="Crear",
        State="activo",
    ))
    errores = _errores(res)
    assert len(errores) == 3
    assert _cols(errores) == {"Entity", "Operation", "State"}


def test_df_vacio_devuelve_exactamente_un_error():
    vacio = pd.DataFrame(columns=list(_FILA_BASE))
    res = validate_bulk(vacio)
    assert len(res) == 1
    assert res[0].severidad == "error"
    assert res[0].fila == -1


def test_e1_columna_obligatoria_faltante_es_un_solo_error_de_archivo():
    df = _bulk().drop(columns=["Keyword ID"])
    res = validate_bulk(df)
    de_archivo = [e for e in _errores(res) if e.fila == -1]
    assert len(de_archivo) == 1
    assert "Keyword ID" in de_archivo[0].mensaje


def test_valor_se_trunca_a_50_chars():
    largo = "a" * 120
    res = validate_bulk(_bulk(Product=largo))
    assert len(_errores(res)[0].valor) == 50


def test_no_muta_el_df_recibido():
    """INV-8: la validacion no toca el DataFrame del caller."""
    df = _bulk()
    antes = df.copy(deep=True)
    validate_bulk(df)
    pd.testing.assert_frame_equal(df, antes)


# ============================================================================
# Warnings — no bloquean la descarga
# ============================================================================

def test_w1_mezcla_de_id_numerico_y_alias_es_warning_no_error():
    """INV-5.1: puede ser legitimo, pero es raro."""
    df = _bulk_filas(
        _neg_kw(),  # Campaign ID numerico, entidad existente
        _kw_create(**{
            "Campaign ID": "SU-AGE-HARVEST-001",
            "Ad Group ID": "SU-AGE-HARVEST-001-AG",
            "Keyword Text": "botas negras",
        }),
    )
    res = validate_bulk(df)
    assert _errores(res) == []
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert warnings[0].fila == -1
    assert warnings[0].columna == "Campaign ID"


def test_w2_keyword_duplicada_en_misma_campana_ad_group_y_match_type():
    df = _bulk_filas(_neg_kw(), _neg_kw())
    res = validate_bulk(df)
    assert _errores(res) == []
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert warnings[0].fila == 1
    assert warnings[0].columna == "Keyword Text"


def test_w2_mismo_termino_en_otro_match_type_no_es_duplicado():
    df = _bulk_filas(
        _neg_kw(**{"Match Type": "Negative Exact"}),
        _neg_kw(**{"Match Type": "Negative Phrase"}),
    )
    assert validate_bulk(df) == []


def test_w3_bid_alto_es_warning_no_error():
    fila = _kw_create(Bid=25.00)
    res = validate_bulk(_bulk(**fila))
    assert _errores(res) == []
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert warnings[0].columna == "Bid"


def test_w3_bid_de_20_no_dispara_warning():
    """El umbral es estricto: 20.00 pasa, 20.01 avisa."""
    assert validate_bulk(_bulk(**_kw_create(Bid=20.00))) == []


def test_w4_mas_de_500_filas_es_warning():
    filas = [_neg_kw(**{"Keyword Text": f"termino {n}"}) for n in range(501)]
    res = validate_bulk(_bulk_filas(*filas))
    assert _errores(res) == []
    warnings = _warnings(res)
    assert len(warnings) == 1
    assert "501" in warnings[0].mensaje


def test_bulk_con_warnings_pero_sin_errores_se_puede_descargar():
    """El gate de la UI mira solo severidad == 'error'."""
    df = _bulk_filas(
        _kw_create(Bid=25.00, **{"Keyword Text": "botas negras"}),
        _neg_kw(),
    )
    res = validate_bulk(df)
    assert [e for e in res if e.severidad == "error"] == []
    assert _warnings(res) != []
