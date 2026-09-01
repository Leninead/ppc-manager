"""
Helper para emitir bulks Amazon Ads SP ejecutables.

Diseno:
  - build_amazon_bulk(rows, entity, ...) -> (bulk_df, invalid_df)
      Construye DataFrame de 12 cols schema Amazon. Valida que cada row tenga
      campaign_name + ad_group_name no vacios (sin eso Amazon rechaza con
      "Missing Parent ID"). Filas invalidas van al 2do DataFrame.

  - aggregate_str_with_top_campaign(df_str, ...) -> DataFrame
      Agrupa STR por termino preservando Campaign / Ad Group / Match Type
      del row con MAYOR SPEND (idxmax). Flag _n_campaigns para ambiguedad.

  - write_bulk_excel(bulk_df, metadata_df, ...) -> bytes
      Excel 2 hojas: "Sponsored Products Campaigns" (schema Amazon) +
      "Metadata Capybaras" (info contextual del analisis).

Usado por:
  - modules/pages/search_term_report.py — tab Negativizar (Negative keyword)
  - modules/pages/search_term_report.py — tab Harvest (Keyword)
  - modules/pages/analisis_cruzado.py   — tab Plan de Accion (Keyword)

Reglas duras Amazon Ads SP (NO negociables):
  - Campaign ID = Campaign Name en cada row (vacio = "Missing Parent ID")
  - Ad Group ID = Ad Group Name en cada row (idem)
  - Portfolio ID siempre vacio
  - Product hardcoded "Sponsored Products"
  - Negative keyword: Bid forzado a "" (Amazon rechaza Negative con bid)
  - Sheet name del bulk: "Sponsored Products Campaigns" (oficial; otros rebotan)
  - Header "State" en lowercase de valor ("enabled"), NO "Status"
"""

from __future__ import annotations

import io
from typing import Any, Iterable, Literal

import pandas as pd


# ============================================================================
# Constantes publicas
# ============================================================================

# Schema oficial Amazon Bulk SP — 12 columnas, ORDEN MANDATORIO
_BULK_COLS: list[str] = [
    "Product",
    "Entity",
    "Operation",
    "Campaign ID",
    "Ad Group ID",
    "Portfolio ID",
    "Campaign Name",
    "Ad Group Name",
    "State",
    "Bid",
    "Keyword Text",
    "Match Type",
]

_VALID_KW_MATCH_TYPES: set[str] = {"exact", "phrase", "broad"}
_VALID_NEG_MATCH_TYPES: set[str] = {
    "negativeExact",
    "negativePhrase",
    "negativeProductTarget",
}

_PRODUCT_SP: str = "Sponsored Products"
_BULK_SHEET_NAME: str = "Sponsored Products Campaigns"
_METADATA_SHEET_NAME: str = "Metadata Capybaras"


# ============================================================================
# Helpers privados
# ============================================================================

def _coerce_str(v: Any) -> str:
    """Convierte a string limpio. NaN/None/'nan' → ''."""
    if v is None:
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    s = str(v).strip()
    if s.lower() == "nan":
        return ""
    return s


def _coerce_bid(v: Any) -> str | float:
    """
    Convierte bid a float o ''. Reglas:
      - None / NaN / '' → ''
      - Numerico convertible → float redondeado a 2 decimales
      - No convertible → '' (el helper marca la fila como invalida aparte si era requerido)
    """
    if v is None or v == "":
        return ""
    if isinstance(v, float) and pd.isna(v):
        return ""
    try:
        f = float(v)
        if pd.isna(f):
            return ""
        return round(f, 2)
    except (TypeError, ValueError):
        return ""


def _validate_row(
    row: dict,
    *,
    entity: str,
    valid_kw_mt: set[str],
    valid_neg_mt: set[str],
) -> str | None:
    """
    Valida una row de entrada. Devuelve None si OK, o string con motivo de invalidez.
    """
    campaign = _coerce_str(row.get("campaign_name"))
    ad_group = _coerce_str(row.get("ad_group_name"))
    keyword = _coerce_str(row.get("keyword_text"))
    match_type = _coerce_str(row.get("match_type"))

    if not campaign:
        return "Campaign Name vacio (Amazon: Missing Parent ID)"
    if not ad_group:
        return "Ad Group Name vacio (Amazon: Missing Parent ID)"
    if not keyword:
        return "Keyword Text vacio"
    if not match_type:
        return "Match Type vacio"

    if entity == "Keyword":
        if match_type not in valid_kw_mt:
            return f"Match Type invalido para Keyword: '{match_type}' (validos: {sorted(valid_kw_mt)})"
    elif entity == "Negative keyword":
        if match_type not in valid_neg_mt:
            return f"Match Type invalido para Negative keyword: '{match_type}' (validos: {sorted(valid_neg_mt)})"

    return None


# ============================================================================
# API publica
# ============================================================================

def build_amazon_bulk(
    rows: Iterable[dict] | pd.DataFrame,
    *,
    entity: Literal["Keyword", "Negative keyword"],
    operation: str = "Create",
    state: str = "enabled",
    drop_invalid: bool = True,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Construye un bulk Amazon Ads SP valido con 12 columnas en orden.

    Args:
        rows: lista de dicts (o DataFrame con cols equivalentes). Cada row:
            {
                "campaign_name": str (NO vacio — si vacio, fila va a invalid_df),
                "ad_group_name": str (NO vacio — idem),
                "keyword_text":  str,
                "match_type":    str (exact/phrase/broad o negativeExact/negativePhrase/negativeProductTarget),
                "bid":           float | str | None (solo Keyword; ignorado en Negative)
            }
        entity: "Keyword" o "Negative keyword"
        operation: "Create" por default (otros valores: "Update", "Archive")
        state: "enabled" por default
        drop_invalid: si True, filas invalidas se separan a invalid_df (recomendado)

    Returns:
        (bulk_df, invalid_df):
          - bulk_df: 12 cols schema Amazon, en orden. Solo filas validas si drop_invalid=True.
          - invalid_df: filas que no entraron al bulk + col "_invalid_reason".
                       Si no hay invalidas → DataFrame vacio con la col "_invalid_reason".

    Raises:
        ValueError: si entity no es uno de los dos validos.
    """
    if entity not in ("Keyword", "Negative keyword"):
        raise ValueError(
            f"entity invalido: {entity!r}. Validos: 'Keyword', 'Negative keyword'."
        )

    # Normalizar input a lista de dicts
    if isinstance(rows, pd.DataFrame):
        rows_list = rows.to_dict(orient="records")
    else:
        rows_list = list(rows)

    valid_records: list[dict] = []
    invalid_records: list[dict] = []

    for row in rows_list:
        reason = _validate_row(
            row,
            entity=entity,
            valid_kw_mt=_VALID_KW_MATCH_TYPES,
            valid_neg_mt=_VALID_NEG_MATCH_TYPES,
        )

        campaign = _coerce_str(row.get("campaign_name"))
        ad_group = _coerce_str(row.get("ad_group_name"))
        keyword = _coerce_str(row.get("keyword_text"))
        match_type = _coerce_str(row.get("match_type"))

        # Bid: solo para Keyword. Negative keyword fuerza vacio (Amazon rechaza Negative con bid)
        if entity == "Keyword":
            bid_val = _coerce_bid(row.get("bid"))
        else:
            bid_val = ""

        record = {
            "Product": _PRODUCT_SP,
            "Entity": entity,
            "Operation": operation,
            "Campaign ID": campaign,       # = Campaign Name (regla Amazon Bulk Capybaras)
            "Ad Group ID": ad_group,        # = Ad Group Name
            "Portfolio ID": "",             # SIEMPRE vacio
            "Campaign Name": campaign,
            "Ad Group Name": ad_group,
            "State": state,
            "Bid": bid_val,
            "Keyword Text": keyword,
            "Match Type": match_type,
        }

        if reason is None:
            valid_records.append(record)
        else:
            invalid_record = dict(record)
            invalid_record["_invalid_reason"] = reason
            invalid_records.append(invalid_record)

    bulk_df = pd.DataFrame(valid_records, columns=_BULK_COLS)
    invalid_df = pd.DataFrame(
        invalid_records,
        columns=_BULK_COLS + ["_invalid_reason"],
    )

    # Si drop_invalid=False → meter las invalidas en el bulk tambien (caveat: rebotaran en Amazon)
    if not drop_invalid and not invalid_df.empty:
        bulk_df = pd.concat(
            [bulk_df, invalid_df[_BULK_COLS]],
            ignore_index=True,
        )

    return bulk_df, invalid_df


def aggregate_str_with_top_campaign(
    df_str: pd.DataFrame,
    *,
    term_col: str,
    spend_col: str,
    campaign_col: str | None,
    ad_group_col: str | None = None,
    match_type_col: str | None = None,
    extra_agg: dict | None = None,
) -> pd.DataFrame:
    """
    Agrupa STR por termino preservando Campaign Name / Ad Group / Match Type
    del row con MAYOR SPEND (criterio: idxmax sobre spend dentro del grupo).

    Si un term aparece en N campanas, gana la que invirtio mas. La decision
    de bid va contra el contexto que mas pesa economicamente.

    Args:
        df_str: STR raw cargado
        term_col: nombre de columna de search term (ej "Customer Search Term")
        spend_col: nombre de columna spend (criterio idxmax)
        campaign_col: nombre columna Campaign Name (None = no se preserva)
        ad_group_col: nombre columna Ad Group (None = no se preserva)
        match_type_col: nombre columna Match Type (None = no se preserva)
        extra_agg: dict {col: agg_func} para sumar otras metricas
                   (ej {"_sales": "sum", "_orders": "sum"})

    Returns:
        DataFrame agrupado por term_col con cols:
          - term_col
          - cols de extra_agg agregadas
          - campaign_col (si != None) — Campaign del row con max spend
          - ad_group_col (si != None) — Ad Group del row con max spend
          - match_type_col (si != None) — Match Type del row con max spend
          - "_n_campaigns" (siempre, int) — cuantas campanas distintas tenia el term.
            N > 1 = ambiguo, AM debe revisar.

    Notas:
      - Si term_col tiene NaN, esas filas se descartan antes del groupby.
      - Si spend_col tiene NaN, se rellena con 0 para idxmax.
    """
    if term_col not in df_str.columns:
        raise ValueError(f"term_col {term_col!r} no esta en df_str.columns")
    if spend_col not in df_str.columns:
        raise ValueError(f"spend_col {spend_col!r} no esta en df_str.columns")

    df = df_str.copy()
    df = df.dropna(subset=[term_col])
    df[spend_col] = pd.to_numeric(df[spend_col], errors="coerce").fillna(0)

    # ── Paso 1: idxmax sobre spend por termino → row con mas inversion
    top_idx = df.groupby(term_col)[spend_col].idxmax()

    # ── Paso 2: cols a heredar del row top
    inherit_cols: list[str] = [term_col]
    if campaign_col and campaign_col in df.columns:
        inherit_cols.append(campaign_col)
    if ad_group_col and ad_group_col in df.columns:
        inherit_cols.append(ad_group_col)
    if match_type_col and match_type_col in df.columns:
        inherit_cols.append(match_type_col)

    top_rows = df.loc[top_idx, inherit_cols].reset_index(drop=True)

    # ── Paso 3: agregaciones extra (sum spend/sales/orders/...)
    agg_dict: dict = {spend_col: "sum"}
    if extra_agg:
        agg_dict.update(extra_agg)
    base = df.groupby(term_col, as_index=False).agg(agg_dict)

    # ── Paso 4: contar N campanas distintas por term (flag de ambiguedad)
    if campaign_col and campaign_col in df.columns:
        n_camps = (
            df.groupby(term_col)[campaign_col]
            .nunique(dropna=True)
            .rename("_n_campaigns")
            .reset_index()
        )
    else:
        n_camps = pd.DataFrame({term_col: base[term_col].unique(), "_n_campaigns": 1})

    # ── Paso 5: merge todo
    out = base.merge(top_rows, on=term_col, how="left").merge(
        n_camps, on=term_col, how="left"
    )

    # idxmax sobre spend trae el spend del row top, no el sum.
    # Sobreescribir spend_col con el SUM (base) — merge ya lo trae correcto desde base.

    return out


def write_bulk_excel(
    bulk_df: pd.DataFrame,
    metadata_df: pd.DataFrame | None = None,
    *,
    bulk_sheet_name: str = _BULK_SHEET_NAME,
    metadata_sheet_name: str = _METADATA_SHEET_NAME,
) -> bytes:
    """
    Genera Excel multi-hoja para download.

    Args:
        bulk_df: DataFrame con 12 cols schema Amazon (output de build_amazon_bulk).
        metadata_df: DataFrame opcional con info contextual (Accion, Brand Share, etc).
                     Esta hoja NO se sube a Amazon; queda como referencia del AM.
        bulk_sheet_name: por default "Sponsored Products Campaigns" (oficial Amazon).
                         Si lo cambias podes romper compat con templates Amazon.
        metadata_sheet_name: por default "Metadata Capybaras".

    Returns:
        bytes — listo para io.BytesIO().getvalue() o st.download_button(data=...).
    """
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        bulk_df.to_excel(writer, sheet_name=bulk_sheet_name, index=False)
        if metadata_df is not None and not metadata_df.empty:
            metadata_df.to_excel(writer, sheet_name=metadata_sheet_name, index=False)
    return buf.getvalue()
