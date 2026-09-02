"""Tests de core/bulk_parser.py contra el Bulk File sintético.

Fixture: tests/fixtures/bulk_sintetico.xlsx, generado por
tests/fixtures/make_bulk_fixture.py. Datos 100% inventados.

Cada test anota el invariante que verifica cuando aplica.
Contrato: .claude/skills/ppc-business-invariants.md
"""

from __future__ import annotations

import importlib.util
import math
import re
from pathlib import Path

import pandas as pd
import pytest

from core.bulk_parser import (
    calcular_cvr_cuenta,
    calcular_cvr_por_campana,
    clicks_threshold,
    get_exact_activas,
    get_portfolio_por_campaign,
    parse_bulk_campaigns,
    parse_bulk_str,
    spend_threshold,
)

_FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
FIXTURE = _FIXTURES_DIR / "bulk_sintetico.xlsx"
GENERADOR = _FIXTURES_DIR / "make_bulk_fixture.py"


def _asegurar_fixture() -> Path:
    """Genera el .xlsx si no está.

    El binario queda fuera de git: la regla `BULK_*.xlsx` del .gitignore lo
    matchea (git es case-insensitive en Windows). Da igual — es un artefacto
    derivado y el generador sí está versionado. Regenerarlo acá evita que un
    clone limpio arranque con 44 tests rojos.
    """
    if not FIXTURE.exists():
        spec = importlib.util.spec_from_file_location("make_bulk_fixture", GENERADOR)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.main()
    return FIXTURE

# IDs de campaña del fixture (ver make_bulk_fixture.py)
C1_RANKING = "132313349237695"
C2_DISCOVERY = "214785693021447"
C3_CONQUEST = "398021456778312"
C4_AUTO = "471209865533104"    # 25 clicks -> por debajo de min_clicks=30
C5_PROFIT = "556677889900112"
C6_CERO = "667788990011223"    # 0 clicks -> división por cero

# El CST de la fila 2, que además existe como keyword Exact enabled.
CST_FILA_2 = "sleep sack winter"

# Índices 0-based de las filas de product targeting (filas 4 y 11 del mapa).
IDX_PT = [3, 10]


@pytest.fixture(scope="module")
def df_str() -> pd.DataFrame:
    return parse_bulk_str(_asegurar_fixture())


@pytest.fixture(scope="module")
def df_camp() -> pd.DataFrame:
    return parse_bulk_campaigns(_asegurar_fixture())


# ---------------------------------------------------------------------
# El fixture existe y tiene la forma esperada
# ---------------------------------------------------------------------

def test_generador_de_fixture_versionado():
    """El .xlsx es descartable; el script que lo produce no."""
    assert GENERADOR.exists()
    assert _asegurar_fixture().exists()


def test_str_tiene_14_filas(df_str):
    assert len(df_str) == 14


# ---------------------------------------------------------------------
# INV-5.1 — los IDs tienen que salir como string de dígitos
# ---------------------------------------------------------------------

@pytest.mark.parametrize(
    "col",
    ["Campaign ID", "Ad Group ID", "Keyword ID", "Product Targeting ID"],
)
def test_ids_salen_como_string(df_str, col):
    """INV-5.1 — ningún ID puede quedar como float o int en el df parseado."""
    assert col in df_str.columns
    for v in df_str[col]:
        assert isinstance(v, str), f"{col} trajo {type(v).__name__}: {v!r}"


def test_keyword_id_sin_notacion_cientifica_ni_punto_cero(df_str):
    """INV-5.1 — el float64 de origen se renderiza como '4.091515e+14' en
    pantalla y como '409151500000001.0' al escribir a archivo. Amazon
    rechaza las dos formas.
    """
    ids = [v for v in df_str["Keyword ID"] if v != ""]
    assert ids, "el fixture debería tener filas de keyword"

    for v in ids:
        assert "e+" not in v.lower(), f"notación científica en {v!r}"
        assert "." not in v, f"sufijo decimal en {v!r}"
        assert v.isdigit(), f"{v!r} no es un ID de dígitos"
        assert len(v) == 15, f"{v!r} no tiene 15 dígitos"


def test_keyword_id_vacio_en_filas_pt(df_str):
    """INV-5.1 — NaN se normaliza a "", nunca al string 'nan'."""
    for idx in IDX_PT:
        v = df_str.loc[idx, "Keyword ID"]
        assert v == "", f"fila {idx}: esperaba '' y vino {v!r}"
        assert v != "nan"


def test_product_targeting_id_vacio_en_filas_de_keyword(df_str):
    """Espejo del anterior: las filas de keyword no tienen PT ID."""
    filas_kw = [i for i in df_str.index if i not in IDX_PT]
    for idx in filas_kw:
        assert df_str.loc[idx, "Product Targeting ID"] == ""


def test_campaign_id_conserva_los_15_digitos(df_str):
    """Un int64 de 15 dígitos no puede perder precisión al pasar a string."""
    assert set(df_str["Campaign ID"]) == {
        C1_RANKING, C2_DISCOVERY, C3_CONQUEST, C4_AUTO, C5_PROFIT, C6_CERO
    }


# ---------------------------------------------------------------------
# Normalización de nombres de columna
# ---------------------------------------------------------------------

def test_columnas_sin_sufijo_informational(df_str):
    """El sufijo '(Informational only)' estorba para indexar."""
    for c in df_str.columns:
        assert "(Informational only)" not in c, f"columna sin normalizar: {c!r}"

    for esperada in ("Campaign Name", "Ad Group Name", "Portfolio Name",
                     "Campaign State"):
        assert esperada in df_str.columns


def test_columnas_campaigns_sin_sufijo_informational(df_camp):
    for c in df_camp.columns:
        assert "(Informational only)" not in c
    assert "Portfolio Name" in df_camp.columns


def test_acentos_y_espacios_sobreviven_al_parseo(df_str):
    """La campaña C5 tiene acentos y espacios extra: no se corrompen."""
    nombre = df_str.loc[13, "Campaign Name"]
    assert "Crémá" in nombre
    assert "—" in nombre
    assert nombre.startswith("  ") and nombre.endswith("  ")


# ---------------------------------------------------------------------
# INV-11.1 — flags de origen
# ---------------------------------------------------------------------

def test_es_product_targeting_solo_en_filas_pt(df_str):
    """INV-11.1 — el flag marca exactamente las filas de product targeting."""
    marcadas = df_str.index[df_str["_es_product_targeting"]].tolist()
    assert marcadas == IDX_PT


def test_origen_match_type_vacio_en_filas_pt(df_str):
    """INV-11.1 — una fila PT no tiene match type de keyword."""
    for idx in IDX_PT:
        assert df_str.loc[idx, "_origen_match_type"] == ""


def test_origen_match_type_normaliza_a_title_case(df_str):
    """INV-5.3 — Amazon exporta el casing inconsistente; la fila 14 viene
    con 'broad' en minúscula y tiene que salir 'Broad'.
    """
    assert df_str.loc[13, "Match Type"] == "broad"        # crudo del archivo
    assert df_str.loc[13, "_origen_match_type"] == "Broad"  # normalizado

    validos = {"Exact", "Phrase", "Broad", ""}
    assert set(df_str["_origen_match_type"]) <= validos


def test_origen_match_type_identifica_las_exact(df_str):
    """INV-11.1 — la fila 1 viene de Exact: es la que hay que excluir."""
    assert df_str.loc[0, "_origen_match_type"] == "Exact"
    assert (df_str["_origen_match_type"] == "Exact").sum() == 1


# ---------------------------------------------------------------------
# INV-11.2 — guard anti-Exact-activo
# ---------------------------------------------------------------------

def test_get_exact_activas_excluye_la_pausada(df_camp):
    """INV-11.2 — una Exact pausada no le saca tráfico a nada, así que no
    bloquea la negativización.
    """
    activas = get_exact_activas(df_camp)
    assert "picnic blanket waterproof" not in activas  # está paused
    assert len(activas) == 4


def test_get_exact_activas_normaliza_lowercase_y_strip(df_camp):
    """El fixture trae '  Merino Wool Swaddle  ' con espacios y mayúsculas."""
    activas = get_exact_activas(df_camp)
    assert "merino wool swaddle" in activas
    assert "  Merino Wool Swaddle  " not in activas
    for kw in activas:
        assert kw == kw.strip().lower()


def test_cst_de_fila_2_dispara_el_guard(df_str, df_camp):
    """INV-11.2 — el caso central: la fila 2 tiene 45 clicks sin órdenes
    (negativizable por INV-3), pero su search term ya existe como Exact
    activa, así que NO se negativiza.
    """
    assert df_str.loc[1, "Customer Search Term"] == CST_FILA_2
    assert df_str.loc[1, "Clicks"] == 45
    assert df_str.loc[1, "Orders"] == 0

    assert CST_FILA_2 in get_exact_activas(df_camp)


def test_get_exact_activas_sin_columnas_devuelve_set_vacio():
    """Guard inactivo (INV-10) en vez de reventar."""
    assert get_exact_activas(pd.DataFrame()) == set()


# ---------------------------------------------------------------------
# INV-11.3 — portfolio por campaña
# ---------------------------------------------------------------------

def test_get_portfolio_por_campaign_mapea(df_camp):
    """INV-11.3 — RANKING es el portfolio cuyos términos van protegidos."""
    mapa = get_portfolio_por_campaign(df_camp)

    assert mapa[C1_RANKING] == "RANKING"
    assert mapa[C2_DISCOVERY] == "DISCOVERY"
    assert mapa[C3_CONQUEST] == "CONQUEST"
    assert mapa[C5_PROFIT] == "PROFIT"
    assert len(mapa) == 6


def test_portfolio_keys_son_strings(df_camp):
    """Tienen que poder cruzarse contra el Campaign ID del STR, que es str."""
    mapa = get_portfolio_por_campaign(df_camp)
    for k in mapa:
        assert isinstance(k, str)
        assert k.isdigit()


def test_filas_de_ranking_identificables_via_portfolio(df_str, df_camp):
    """INV-11.3 — el cruce completo: las filas 1 y 5 vienen de RANKING."""
    mapa = get_portfolio_por_campaign(df_camp)
    portfolios = df_str["Campaign ID"].map(mapa)

    assert portfolios.loc[0] == "RANKING"
    assert portfolios.loc[4] == "RANKING"
    assert (portfolios == "RANKING").sum() == 2


# ---------------------------------------------------------------------
# INV-3 — CVR y thresholds
# ---------------------------------------------------------------------

def test_cvr_por_campana_excluye_las_de_pocos_clicks(df_str):
    """INV-3 — sin estadística suficiente no se calcula CVR propio; el
    caller cae al CVR de cuenta.
    """
    cvr = calcular_cvr_por_campana(df_str, min_clicks=30)

    assert C4_AUTO not in cvr, "25 clicks < 30, no debería entrar"
    assert C1_RANKING in cvr, "90 clicks, sí entra"
    assert C3_CONQUEST in cvr, "exactamente 30 clicks: el piso es inclusivo"


def test_cvr_por_campana_no_explota_con_cero_clicks(df_str):
    """La campaña C6 tiene una sola fila, con Spend>0 y Clicks==0."""
    cvr = calcular_cvr_por_campana(df_str, min_clicks=0)
    assert C6_CERO not in cvr


def test_cvr_por_campana_valores(df_str):
    """C2: 15 órdenes sobre 188 clicks."""
    cvr = calcular_cvr_por_campana(df_str, min_clicks=30)
    assert cvr[C2_DISCOVERY] == pytest.approx(15 / 188)
    assert cvr[C1_RANKING] == 0.0


def test_cvr_cuenta_valor(df_str):
    """19 órdenes sobre 370 clicks en todo el archivo."""
    assert calcular_cvr_cuenta(df_str) == pytest.approx(19 / 370)


def test_cvr_cuenta_df_vacio_devuelve_cero():
    assert calcular_cvr_cuenta(pd.DataFrame()) == 0.0


def test_cvr_cuenta_sin_clicks_devuelve_cero():
    df = pd.DataFrame({"Clicks": [0, 0], "Orders": [0, 0]})
    assert calcular_cvr_cuenta(df) == 0.0


@pytest.mark.parametrize(
    "cvr, esperado",
    [
        (0.20, 10),   # mínimo absoluto
        (0.10, 20),
        (0.05, 40),
        (0.02, 100),
        (0.0, 100),   # sin CVR conocido -> el más conservador
    ],
)
def test_clicks_threshold_tabla_del_sop(cvr, esperado):
    """INV-3 — la tabla textual del skill."""
    assert clicks_threshold(cvr) == esperado


@pytest.mark.parametrize("cvr", [0.20, 0.25, 0.50, 0.80, 1.0])
def test_clicks_threshold_nunca_baja_de_10(cvr):
    """INV-3 — 10 clicks es el piso absoluto, por alto que sea el CVR."""
    assert clicks_threshold(cvr) >= 10


def test_clicks_threshold_cvr_negativo_es_conservador():
    assert clicks_threshold(-0.5) == 100


def test_clicks_threshold_redondea_hacia_arriba():
    """ceil, no round: 1/0.03*2 = 66.67 -> 67, no 67 por redondeo casual."""
    assert clicks_threshold(0.03) == math.ceil((1 / 0.03) * 2)
    assert clicks_threshold(0.03) == 67


def test_spend_threshold():
    """INV-3 — precio * 0.50."""
    assert spend_threshold(30) == 15.0
    assert spend_threshold(9.99) == pytest.approx(4.995)


# ---------------------------------------------------------------------
# Errores de input
# ---------------------------------------------------------------------

def test_hoja_faltante_da_error_orientativo(tmp_path):
    """Si el AM sube el STR standalone en vez del Bulk File, el mensaje
    tiene que decirle qué bajar.
    """
    ruta = tmp_path / "no_es_bulk.xlsx"
    pd.DataFrame({"Customer Search Term": ["kw"]}).to_excel(
        ruta, sheet_name="Sheet1", index=False
    )

    with pytest.raises(ValueError, match="Bulk File"):
        parse_bulk_str(ruta)


# ---------------------------------------------------------------------
# M6 — la columna "Product" del Bulk File NO es una columna de ASIN
# ---------------------------------------------------------------------

def test_columna_product_no_se_toma_como_asin():
    """La hoja "SP Search Term Report" trae una columna `Product` que vale
    'Sponsored Products' en TODAS las filas.

    La deteccion difusa que M6 usaba antes la tomaba como columna de ASIN y
    armaba un ASIN fantasma llamado "Sponsored Products" con el 100% del
    spend. Falla silenciosa: el analisis por ASIN parecia andar y estaba
    agrupando toda la cuenta en una sola fila. El ASIN real sale de las filas
    `Product Ad` de la hoja de campanas.
    """
    from modules.pages.analisis_cruzado import _asin_por_ad_group

    df_str = parse_bulk_str(str(FIXTURE))
    assert "Product" in df_str.columns
    assert set(df_str["Product"].unique()) == {"Sponsored Products"}, (
        "si el fixture cambia, este test deja de proteger lo que dice proteger"
    )

    df_campaigns = parse_bulk_campaigns(str(FIXTURE))
    mapa = _asin_por_ad_group.__wrapped__(df_campaigns)

    assert mapa, "la hoja de campanas tiene filas Product Ad con ASIN"
    assert "Sponsored Products" not in mapa.values()
    for asin in mapa.values():
        # El fixture usa ASINs sinteticos, asi que se valida la forma general
        # (prefijo B0 + alfanumerico), no el largo exacto de un ASIN real.
        assert re.fullmatch(r"B0[A-Z0-9]+", asin), f"{asin!r} no parece un ASIN"


def test_asin_por_ad_group_sin_filas_product_ad_devuelve_vacio():
    """Sin el dato no se inventa un fallback: Tab 3 avisa y no muestra nada."""
    from modules.pages.analisis_cruzado import _asin_por_ad_group

    df = pd.DataFrame({
        "Entity": ["Campaign", "Keyword"],
        "Ad Group ID": ["111", "222"],
        "ASIN": ["", ""],
    })
    assert _asin_por_ad_group.__wrapped__(df) == {}
