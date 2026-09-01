"""
Parser del Bulk File de Amazon Ads (Sponsored Products).

Por que existe:
  El STR standalone que se bajaba de Campaign Manager NO trae los IDs
  numericos de Amazon. Sin esos IDs, todo bulk generado a partir de el es
  inejecutable en modo REFERENCIA (INV-5.1): pone el NOMBRE de campana en
  Campaign ID, que solo resuelve al CREAR entidades nuevas.

  El Bulk File completo si los trae. Su hoja "SP Search Term Report" ata
  cada search term a Campaign ID / Ad Group ID / Keyword ID reales, y la
  hoja "Sponsored Products Campaigns" aporta Portfolio Name, Match Type y
  State — los tres datos que INV-11 necesita para no negativizar contra el
  ranking organico.

Regla dura de este modulo:
  Los cuatro campos de ID salen SIEMPRE como string. Un ID en float64 se
  renderiza como "4.091515e+14" en pantalla y como "409151500000001.0" al
  escribirlo a archivo. Amazon rechaza las dos formas. La conversion es
  float -> int -> str, y NaN -> "".

Alcance:
  Solo parseo y helpers de calculo. La clasificacion de negativos y el
  harvest NO viven aca.

Sin dependencia de Streamlit a proposito: el modulo es codigo puro y por
eso testeable sin levantar la app. El cacheo (@st.cache_data) es
responsabilidad del caller.

Contrato: .claude/skills/ppc-business-invariants.md — INV-3, INV-5, INV-11.
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


# ============================================================================
# Constantes publicas
# ============================================================================

SHEET_STR: str = "SP Search Term Report"
SHEET_CAMPAIGNS: str = "Sponsored Products Campaigns"

# Sufijo que Amazon le cuelga a las columnas de solo-lectura. Estorba para
# indexar, y el mismo dato aparece con y sin el segun la hoja.
_SUFIJO_INFO: str = " (Informational only)"

# Columnas que son IDs y por lo tanto van si o si a string.
_ID_COLS: tuple[str, ...] = (
    "Campaign ID",
    "Ad Group ID",
    "Keyword ID",
    "Product Targeting ID",
    "Portfolio ID",
    "Ad ID",
)

# Valores canonicos de Match Type positivo (INV-5.3).
_MATCH_TYPES_CANONICOS: dict[str, str] = {
    "exact": "Exact",
    "phrase": "Phrase",
    "broad": "Broad",
}


# ============================================================================
# Helpers privados
# ============================================================================

def _norm_col(nombre: str) -> str:
    """Saca el sufijo '(Informational only)' y espacios sobrantes."""
    s = str(nombre).strip()
    if s.endswith(_SUFIJO_INFO):
        s = s[: -len(_SUFIJO_INFO)]
    return s.strip()


def _id_to_str(v: Any) -> str:
    """
    Normaliza un ID de Amazon a string de digitos.

    float64 -> int -> str, para matar tanto la notacion cientifica
    ("4.091515e+14") como el sufijo decimal ("409151500000001.0").
    NaN / None / "" / "nan" -> "".
    Si el valor no es numerico se devuelve tal cual (puede ser un alias
    de INV-5.1, que es un string arbitrario y valido).
    """
    if v is None:
        return ""
    if isinstance(v, float):
        if pd.isna(v):
            return ""
        return str(int(v))
    if isinstance(v, (int,)) and not isinstance(v, bool):
        return str(v)

    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "nat", "<na>"):
        return ""
    try:
        return str(int(float(s)))
    except (TypeError, ValueError):
        return s  # alias no numerico: se respeta


def _ids_a_string(df: pd.DataFrame) -> pd.DataFrame:
    """Aplica _id_to_str a todas las columnas de ID presentes en el df."""
    for col in _ID_COLS:
        if col in df.columns:
            df[col] = df[col].map(_id_to_str)
    return df


def _match_type_canonico(v: Any) -> str:
    """
    Lleva el Match Type a Title Case (INV-5.3).

    Amazon no es consistente con el casing entre exports. Devuelve "" para
    filas sin match type (product targeting).
    """
    s = str(v).strip() if v is not None else ""
    if s == "" or s.lower() in ("nan", "none"):
        return ""
    return _MATCH_TYPES_CANONICOS.get(s.lower(), s)


def _num(df: pd.DataFrame, col: str) -> pd.Series:
    """Columna como numerica con NaN->0. Serie de ceros si la col no existe."""
    if col not in df.columns:
        return pd.Series(0.0, index=df.index, dtype="float64")
    return pd.to_numeric(df[col], errors="coerce").fillna(0.0)


# ============================================================================
# API publica — parseo
# ============================================================================

def parse_bulk_str(file: Any) -> pd.DataFrame:
    """
    Lee la hoja "SP Search Term Report" del Bulk File.

    Args:
        file: ruta, bytes o file-like con el .xlsx del bulk.

    Returns:
        DataFrame con las columnas del reporte, mas:
          - IDs (Campaign/Ad Group/Keyword/Product Targeting) como string
          - nombres de columna sin el sufijo "(Informational only)"
          - "_origen_match_type": Match Type de origen en Title Case
            (Exact/Phrase/Broad), "" si la fila es product targeting.
            Es el dato que INV-11.1 usa para excluir candidatos.
          - "_es_product_targeting": True si Keyword ID esta vacio y
            Product Targeting ID no.

    Raises:
        ValueError: si el archivo no tiene la hoja esperada.
    """
    df = _leer_hoja(file, SHEET_STR)
    df.columns = [_norm_col(c) for c in df.columns]
    df = _ids_a_string(df)

    kw_id = df["Keyword ID"] if "Keyword ID" in df.columns else pd.Series("", index=df.index)
    pt_id = df["Product Targeting ID"] if "Product Targeting ID" in df.columns else pd.Series("", index=df.index)

    df["_es_product_targeting"] = (kw_id.astype(str) == "") & (pt_id.astype(str) != "")

    if "Match Type" in df.columns:
        df["_origen_match_type"] = df["Match Type"].map(_match_type_canonico)
    else:
        df["_origen_match_type"] = ""
    # Una fila de product targeting no tiene match type de keyword.
    df.loc[df["_es_product_targeting"], "_origen_match_type"] = ""

    return df


def parse_bulk_campaigns(file: Any) -> pd.DataFrame:
    """
    Lee la hoja "Sponsored Products Campaigns" del Bulk File.

    Mismo tratamiento de IDs (string) y de nombres de columna que
    parse_bulk_str. Es la fuente de INV-11.2 (Exact activas) y de
    INV-11.3 (portfolio por campana).

    Raises:
        ValueError: si el archivo no tiene la hoja esperada.
    """
    df = _leer_hoja(file, SHEET_CAMPAIGNS)
    df.columns = [_norm_col(c) for c in df.columns]
    return _ids_a_string(df)


def _leer_hoja(file: Any, sheet: str) -> pd.DataFrame:
    """Lee una hoja del xlsx con error explicito si no existe."""
    try:
        return pd.read_excel(file, sheet_name=sheet)
    except ValueError as exc:
        raise ValueError(
            f"El archivo no tiene la hoja {sheet!r}. "
            "Verifica que sea el Bulk File completo de Campaign Manager "
            "(Bulk Operations), no el Search Term Report standalone."
        ) from exc


# ============================================================================
# API publica — lookups sobre la hoja de campanas
# ============================================================================

def get_exact_activas(df_campaigns: pd.DataFrame) -> set[str]:
    """
    Keywords Exact ACTIVAS de la cuenta, normalizadas a lowercase + strip.

    Fuente del guard INV-11.2: un search term que ya existe como Exact
    activa no se negativiza, por mal que rinda en Broad o Phrase.

    Filtro: Entity == "Keyword" AND Match Type == "Exact" AND
    State == "enabled". Las pausadas y archivadas NO cuentan — si esta
    pausada, negativizar el termino no le saca trafico a nada.

    Returns:
        set de Keyword Text. Vacio si el df no trae las columnas necesarias.
    """
    requeridas = {"Entity", "Match Type", "State", "Keyword Text"}
    if not requeridas.issubset(df_campaigns.columns):
        return set()

    def _lower(col: str) -> pd.Series:
        return df_campaigns[col].astype(str).str.strip().str.lower()

    mask = (
        (_lower("Entity") == "keyword")
        & (_lower("Match Type") == "exact")
        & (_lower("State") == "enabled")
    )
    textos = df_campaigns.loc[mask, "Keyword Text"].dropna().astype(str).str.strip().str.lower()
    return set(t for t in textos if t)


def get_portfolio_por_campaign(df_campaigns: pd.DataFrame) -> dict[str, str]:
    """
    Mapa Campaign ID (string) -> Portfolio Name.

    Fuente de INV-11.3: los terminos de campanas en portfolio RANKING se
    marcan como ranking keyword por default y no se negativizan.

    Solo se leen las filas Entity == "Campaign", que son las que definen el
    portfolio. Campanas sin portfolio quedan fuera del dict.
    """
    if "Campaign ID" not in df_campaigns.columns:
        return {}
    if "Portfolio Name" not in df_campaigns.columns:
        return {}

    df = df_campaigns
    if "Entity" in df.columns:
        df = df[df["Entity"].astype(str).str.strip().str.lower() == "campaign"]

    out: dict[str, str] = {}
    for cid, portfolio in zip(df["Campaign ID"], df["Portfolio Name"]):
        cid_s = str(cid).strip()
        p_s = "" if portfolio is None else str(portfolio).strip()
        if cid_s and p_s and p_s.lower() != "nan":
            out[cid_s] = p_s
    return out


# ============================================================================
# API publica — calculo de thresholds (INV-3)
# ============================================================================

def calcular_cvr_por_campana(
    df_str: pd.DataFrame,
    min_clicks: int = 30,
) -> dict[str, float]:
    """
    CVR de PPC por campana: orders totales / clicks totales de esa campana.

    Args:
        df_str: salida de parse_bulk_str.
        min_clicks: piso de clicks para que la campana tenga estadistica
            suficiente. Por debajo, la campana NO entra al dict y el caller
            debe caer al CVR de cuenta (ver calcular_cvr_cuenta).

    Returns:
        dict Campaign ID (string) -> CVR en fraccion (0.10 == 10%).
        Las campanas con 0 clicks nunca entran: no hay division por cero.
    """
    if df_str.empty or "Campaign ID" not in df_str.columns:
        return {}

    tmp = pd.DataFrame({
        "cid": df_str["Campaign ID"].astype(str),
        "clicks": _num(df_str, "Clicks"),
        "orders": _num(df_str, "Orders"),
    })
    agg = tmp.groupby("cid", as_index=True)[["clicks", "orders"]].sum()

    out: dict[str, float] = {}
    for cid, fila in agg.iterrows():
        clicks = float(fila["clicks"])
        if clicks <= 0 or clicks < min_clicks:
            continue
        out[str(cid)] = float(fila["orders"]) / clicks
    return out


def calcular_cvr_cuenta(df_str: pd.DataFrame) -> float:
    """
    CVR agregado de todas las filas. Fallback de calcular_cvr_por_campana.

    Returns:
        CVR en fraccion. 0.0 si no hay clicks (evita la division por cero).
    """
    if df_str.empty:
        return 0.0
    clicks = float(_num(df_str, "Clicks").sum())
    if clicks <= 0:
        return 0.0
    return float(_num(df_str, "Orders").sum()) / clicks


def clicks_threshold(cvr: float) -> int:
    """
    Clicks sin orden necesarios para negativizar (INV-3).

        max(10, ceil((1 / cvr) * 2))

    CVR 20% -> 10 (minimo absoluto) | 10% -> 20 | 5% -> 40 | 2% -> 100.

    Args:
        cvr: CVR del producto en fraccion (0.10 == 10%).

    Returns:
        Threshold de clicks. Si cvr <= 0 devuelve 100, el valor mas
        conservador de la tabla: sin CVR conocido no se mata nada barato.
    """
    if cvr is None or cvr <= 0:
        return 100
    return max(10, math.ceil((1.0 / cvr) * 2))


def spend_threshold(precio: float) -> float:
    """
    Spend sin ventas necesario para negativizar (INV-3): precio * 0.50.

    Producto de $30 -> negativizar si gasto $15 sin convertir.
    """
    return float(precio) * 0.50
