"""Tests de core/bulk_export.py — helper de bulks Amazon Ads SP.

El módulo es código puro (sin Streamlit, sin I/O de disco salvo el Excel
en memoria), así que se testea tal cual está.

Dos secciones con intención distinta:

  SECCIÓN A — INVARIANTES: si uno de estos falla, el código está mal.
  Codifican el contrato duro con Amazon (schema, orden de columnas, reparto
  válidas/inválidas). Ver `.claude/skills/ppc-business-invariants.md` INV-5.

  SECCIÓN B — CARACTERIZACIÓN: congelan el comportamiento ACTUAL, bugs
  incluidos. Un fallo acá no significa "se rompió": significa "cambió".
  Cada uno documenta en su docstring si lo que congela es deseado o es deuda.

Datos sintéticos inline. No se lee ningún archivo de cliente.
"""

from __future__ import annotations

import io

import pandas as pd
import pytest

from core.bulk_export import (
    _BULK_COLS,
    _BULK_SHEET_NAME,
    _METADATA_SHEET_NAME,
    _coerce_str,
    aggregate_str_with_top_campaign,
    build_amazon_bulk,
    write_bulk_excel,
)


# ---------------------------------------------------------------------
# Helper de datos
# ---------------------------------------------------------------------
def _row(**kw) -> dict:
    """Row válida por default. Cualquier clave se puede overridear.

    Default apunta a entity="Keyword" (match_type "exact" + bid numérico).
    Para Negative keyword hay que pasar match_type="negativeExact".
    """
    base = {
        "campaign_name": "Dermaglos - B0CYLMJJJC - SP - KW - EXACT - Core",
        "ad_group_name": "AG - vitamin a cream",
        "keyword_text": "vitamin a cream",
        "match_type": "exact",
        "bid": 1.25,
    }
    base.update(kw)
    return base


def _sheets(xlsx_bytes: bytes) -> dict:
    """Relee un xlsx en memoria -> {nombre_hoja: DataFrame}."""
    return pd.read_excel(io.BytesIO(xlsx_bytes), sheet_name=None)


# =====================================================================
# === SECCIÓN A: INVARIANTES (si fallan, el código está mal) ===========
# =====================================================================

def test_bulk_cols_orden_exacto():
    """A1 — bulk_df expone las 12 cols de _BULK_COLS, en ese orden exacto."""
    bulk_df, _ = build_amazon_bulk([_row()], entity="Keyword")

    assert list(bulk_df.columns) == _BULK_COLS
    assert len(_BULK_COLS) == 12


def test_claves_extra_no_se_cuelan_al_bulk():
    """A2 — claves anexas del caller no aparecen como columnas del bulk."""
    fila = _row(**{
        "Prioridad": "Alta",
        "Regla": "R2 — Sin conversion (CVR)",
        "Customer Search Term": "vitamin a cream",
    })

    bulk_df, _ = build_amazon_bulk([fila], entity="Keyword")

    assert list(bulk_df.columns) == _BULK_COLS
    for anexa in ("Prioridad", "Regla", "Customer Search Term"):
        assert anexa not in bulk_df.columns


def test_negative_keyword_fuerza_bid_vacio():
    """A3 — entity="Negative keyword" descarta el bid aunque venga poblado."""
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(match_type="negativeExact", bid=5.0)],
        entity="Negative keyword",
    )

    assert len(bulk_df) == 1
    assert invalid_df.empty
    assert bulk_df.iloc[0]["Bid"] == ""


def test_entity_invalido_levanta_valueerror():
    """A4 — un entity fuera de los dos válidos aborta con ValueError."""
    with pytest.raises(ValueError, match="entity invalido"):
        build_amazon_bulk([_row()], entity="Campaign")


def test_match_type_exact_invalido_para_negative_keyword():
    """A5 — "exact" no es match type válido en Negative keyword."""
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(match_type="exact")],
        entity="Negative keyword",
    )

    assert len(bulk_df) == 0
    assert len(invalid_df) == 1
    assert "Match Type invalido" in invalid_df.iloc[0]["_invalid_reason"]


def test_match_type_negative_invalido_para_keyword():
    """A6 — "negativeExact" no es match type válido en Keyword."""
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(match_type="negativeExact")],
        entity="Keyword",
    )

    assert len(bulk_df) == 0
    assert len(invalid_df) == 1
    assert "Match Type invalido" in invalid_df.iloc[0]["_invalid_reason"]


def test_row_sin_campaign_name_va_a_invalid():
    """A7 — sin Campaign Name la fila es inválida (Amazon: Missing Parent ID)."""
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(campaign_name="")],
        entity="Keyword",
        drop_invalid=True,
    )

    assert len(bulk_df) == 0
    assert len(invalid_df) == 1
    assert invalid_df.iloc[0]["_invalid_reason"] != ""
    assert "Campaign Name" in invalid_df.iloc[0]["_invalid_reason"]


def test_row_sin_ad_group_name_va_a_invalid():
    """A8 — sin Ad Group Name la fila es inválida (Amazon: Missing Parent ID)."""
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(ad_group_name="")],
        entity="Keyword",
        drop_invalid=True,
    )

    assert len(bulk_df) == 0
    assert len(invalid_df) == 1
    assert invalid_df.iloc[0]["_invalid_reason"] != ""
    assert "Ad Group Name" in invalid_df.iloc[0]["_invalid_reason"]


def test_invalid_df_siempre_tiene_columna_invalid_reason():
    """A9 — invalid_df expone "_invalid_reason" incluso con 0 filas.

    El caller hace `invalid_df["_invalid_reason"]` sin chequear si está vacío;
    si la columna desapareciera en el caso feliz, reventaría con KeyError.
    """
    bulk_df, invalid_df = build_amazon_bulk([_row()], entity="Keyword")

    assert len(bulk_df) == 1
    assert invalid_df.empty
    assert "_invalid_reason" in invalid_df.columns
    assert list(invalid_df.columns) == _BULK_COLS + ["_invalid_reason"]


def test_write_bulk_excel_devuelve_bytes_releibles():
    """A10 — el xlsx se relee y la hoja oficial trae las 12 cols."""
    bulk_df, _ = build_amazon_bulk([_row()], entity="Keyword")

    xlsx = write_bulk_excel(bulk_df)

    assert isinstance(xlsx, bytes)
    hojas = _sheets(xlsx)
    assert _BULK_SHEET_NAME in hojas
    assert _BULK_SHEET_NAME == "Sponsored Products Campaigns"
    assert list(hojas[_BULK_SHEET_NAME].columns) == _BULK_COLS


def test_write_bulk_excel_una_o_dos_hojas_segun_metadata():
    """A11 — metadata_df=None => 1 hoja; metadata poblada => 2 hojas."""
    bulk_df, _ = build_amazon_bulk([_row()], entity="Keyword")

    solo_bulk = _sheets(write_bulk_excel(bulk_df, None))
    assert list(solo_bulk.keys()) == [_BULK_SHEET_NAME]

    metadata_df = pd.DataFrame({"Regla": ["R2"], "Prioridad": ["Alta"]})
    con_meta = _sheets(write_bulk_excel(bulk_df, metadata_df))
    assert list(con_meta.keys()) == [_BULK_SHEET_NAME, _METADATA_SHEET_NAME]
    assert _METADATA_SHEET_NAME == "Metadata Capybaras"


def test_bulk_mixto_reparte_validas_e_invalidas():
    """A12 — 3 válidas + 2 inválidas se reparten 3 / 2 sin perder ninguna."""
    filas = [
        _row(keyword_text="kw ok 1"),
        _row(keyword_text="kw ok 2"),
        _row(keyword_text="kw ok 3"),
        _row(keyword_text="kw mala 1", campaign_name=""),
        _row(keyword_text="kw mala 2", ad_group_name=""),
    ]

    bulk_df, invalid_df = build_amazon_bulk(filas, entity="Keyword")

    assert len(bulk_df) == 3
    assert len(invalid_df) == 2
    assert set(bulk_df["Keyword Text"]) == {"kw ok 1", "kw ok 2", "kw ok 3"}
    assert set(invalid_df["Keyword Text"]) == {"kw mala 1", "kw mala 2"}


# =====================================================================
# === SECCIÓN B: CARACTERIZACIÓN ======================================
# === (congelan comportamiento actual, incluye bugs conocidos) =========
# =====================================================================

def test_carac_bid_no_convertible_se_silencia():
    """CARACTERIZACIÓN: bid basura se silencia. DEUDA — viola el espíritu de
    INV-5 (fila llega a Amazon sin bid y rebota). Si este test falla porque
    ahora marca la fila inválida, el cambio es CORRECTO: actualizá el test.

    `_coerce_bid` atrapa el TypeError/ValueError y devuelve "" sin avisar, y
    `_validate_row` ni siquiera mira el bid. La fila sale al bulk como válida.
    """
    bulk_df, invalid_df = build_amazon_bulk([_row(bid="abc")], entity="Keyword")

    assert len(bulk_df) == 1
    assert bulk_df.iloc[0]["Bid"] == ""
    assert invalid_df.empty


def test_carac_ids_se_llenan_con_los_nombres():
    """CARACTERIZACIÓN: los campos ID se llenan con el NOMBRE. Válido para
    CREATE de campañas nuevas (el ID actúa de etiqueta de linkeo interno),
    SOSPECHOSO para agregar a campañas existentes, donde Amazon espera el ID
    numérico. PENDIENTE de validar contra bulk real.
    """
    bulk_df, _ = build_amazon_bulk(
        [_row(campaign_name="Camp X", ad_group_name="AG Y")],
        entity="Keyword",
    )
    fila = bulk_df.iloc[0]

    assert fila["Campaign ID"] == fila["Campaign Name"] == "Camp X"
    assert fila["Ad Group ID"] == fila["Ad Group Name"] == "AG Y"
    assert fila["Portfolio ID"] == ""
    assert fila["Product"] == "Sponsored Products"


def test_carac_drop_invalid_false_duplica_la_fila():
    """CARACTERIZACIÓN: doble presencia. No sumar len() de ambos para
    reportar totales.

    Con drop_invalid=False la fila inválida se re-concatena al bulk PERO
    sigue estando en invalid_df. len(bulk)+len(invalid) sobrecuenta.
    """
    bulk_df, invalid_df = build_amazon_bulk(
        [_row(campaign_name="")],
        entity="Keyword",
        drop_invalid=False,
    )

    assert len(bulk_df) == 1
    assert len(invalid_df) == 1
    assert list(bulk_df.columns) == _BULK_COLS  # la col _invalid_reason no viaja


def test_carac_coerce_str_normaliza_nulos():
    """CARACTERIZACIÓN: None, NaN float y el string 'nan' colapsan a "".

    El tercer caso importa: pandas serializa NaN a "nan" al pasar por
    astype(str), y sin esta normalización un "nan" textual pasaría la
    validación de no-vacío y llegaría a Amazon como nombre de campaña.
    """
    assert _coerce_str(None) == ""
    assert _coerce_str(float("nan")) == ""
    assert _coerce_str("nan") == ""
    assert _coerce_str("NaN") == ""
    assert _coerce_str("  Camp X  ") == "Camp X"


def test_carac_aggregate_hereda_campaign_del_mayor_spend():
    """CARACTERIZACIÓN: ante un término en N campañas gana la de MAYOR SPEND
    (idxmax), y "_n_campaigns" queda como flag de ambigüedad para el AM.

    Deseado: la decisión de bid va contra el contexto que más pesa
    económicamente. El spend de salida es el SUM del grupo, no el del row top.
    """
    df_str = pd.DataFrame({
        "Customer Search Term": ["kw a", "kw a", "kw b"],
        "Spend": [10.0, 40.0, 5.0],
        "Campaign Name": ["Camp-Low", "Camp-High", "Camp-Solo"],
        "Ad Group": ["AG-Low", "AG-High", "AG-Solo"],
        "_orders": [1, 3, 2],
    })

    out = aggregate_str_with_top_campaign(
        df_str,
        term_col="Customer Search Term",
        spend_col="Spend",
        campaign_col="Campaign Name",
        ad_group_col="Ad Group",
        extra_agg={"_orders": "sum"},
    )
    fila_a = out[out["Customer Search Term"] == "kw a"].iloc[0]
    fila_b = out[out["Customer Search Term"] == "kw b"].iloc[0]

    assert fila_a["Campaign Name"] == "Camp-High"   # gana la de $40, no la de $10
    assert fila_a["Ad Group"] == "AG-High"
    assert fila_a["Spend"] == 50.0                  # SUM del grupo
    assert fila_a["_orders"] == 4
    assert fila_a["_n_campaigns"] == 2              # ambiguo: el AM debe revisar
    assert fila_b["_n_campaigns"] == 1


@pytest.mark.parametrize(
    "term_col, spend_col, esperado",
    [
        ("NO EXISTE", "Spend", "term_col"),
        ("Customer Search Term", "NO EXISTE", "spend_col"),
    ],
)
def test_carac_aggregate_valida_columnas_requeridas(term_col, spend_col, esperado):
    """CARACTERIZACIÓN: term_col y spend_col se validan con ValueError explícito.

    Deseado: falla ruidoso en vez de KeyError opaco de pandas adentro del
    groupby. Nótese la asimetría — campaign_col/ad_group_col NO se validan:
    si no existen se ignoran en silencio y el bulk sale sin Campaign Name.
    """
    df_str = pd.DataFrame({
        "Customer Search Term": ["kw a"],
        "Spend": [10.0],
        "Campaign Name": ["Camp-Solo"],
    })

    with pytest.raises(ValueError, match=esperado):
        aggregate_str_with_top_campaign(
            df_str,
            term_col=term_col,
            spend_col=spend_col,
            campaign_col="Campaign Name",
        )
