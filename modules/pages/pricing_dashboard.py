"""M30 — Pricing Dashboard (port del HTML standalone a módulo Streamlit).

F3.2 — Parsers + lookups. SOLO parsing + construcción de lookups.
Sin scoring, sin enrichment, sin UI, sin router, sin persistencia (esas fases
son F3.3 / F3.4). Este archivo todavía NO expone render() — nada routea aquí.

Fuente de verdad: `.claude/porting-sources/pricing-dashboard.html` (gitignored).
El comportamiento de los builders se porta 1:1 de las funciones JS:
    - buildFeeLookup     (HTML L941)  -> _build_fee_lookup
    - buildCOGSLookup    (HTML L970)  -> _build_cogs_lookup
    - buildMaestroLookup (HTML L986)  -> _build_maestro_lookup
y los 6 file inputs (HTML L254-291 / parseFile L611) -> los 6 _parse_*.

Notas de fidelidad documentadas en el reporte de F3.2:
    - Los 6 parsers devuelven el DataFrame crudo (read_csv / read_excel). Las
      transformaciones especiales de awd (filtrado de filas metadata) e izzi
      (hoja 'Inventario 2526', offset de 2 filas, columnas posicionales 0/5)
      NO están en F3.2: el HTML las hace al cargar, pero el contrato de F3.2
      sólo define lookups para cogs/fee/maestro. Quedan para F3.3.
    - CSV se lee con encoding='utf-8-sig' para preservar los nombres de columna
      verbatim (el HTML elimina el BOM con h.replace(/^\\uFEFF/,'')). Sin esto el
      primer header quedaría con prefijo BOM y el match por SKU fallaría en
      silencio — exactamente el bug que el contrato pide evitar.
    - Las strings de Amazon NO se normalizan (verbatim).
"""

from __future__ import annotations

from io import BytesIO
import re

import pandas as pd
import streamlit as st


# =====================================================================
# Helpers internos
# =====================================================================
def _to_float(v) -> float:
    """Replica JS `parseFloat(v) || 0`.

    null/undefined/NaN/'' -> 0.0; "12abc" -> 12.0 (parseFloat toma el prefijo
    numérico); valor numérico -> float(v).
    """
    if v is None:
        return 0.0
    try:
        if pd.isna(v):
            return 0.0
    except (TypeError, ValueError):
        pass
    try:
        return float(v)
    except (TypeError, ValueError):
        m = re.match(r"\s*[-+]?\d*\.?\d+", str(v))
        return float(m.group()) if m else 0.0


def _sku_key(v) -> str:
    """Replica `(r['X'] || '').trim()` con str() forzado.

    str() siempre antes de usar como key, para evitar el bug de float-key
    (match silencioso). Celdas vacías / NaN -> '' (el caller las descarta).
    """
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if v is None:
        return ""
    return str(v).strip()


# =====================================================================
# B3 — 6 parsers cacheados (funciones puras, sin st.* adentro)
# =====================================================================
@st.cache_data(show_spinner=False)
def _parse_fba(data: bytes) -> pd.DataFrame:
    """CSV FBA (Amazon FBA Inventory). Lectura cruda, columnas verbatim."""
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def _parse_fee(data: bytes) -> pd.DataFrame:
    """CSV Fee (Amazon fee preview / settlement). Lectura cruda."""
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def _parse_awd(data: bytes) -> pd.DataFrame:
    """CSV AWD (Amazon Warehousing & Distribution). Lectura cruda.

    El filtrado de filas metadata (Timestamp / Merchant ID) y la conversión a
    lookup `{SKU: Available in AWD (units)}` que hace el HTML al cargar quedan
    para F3.3 (no hay builder de awd en el contrato de F3.2).
    """
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig")


@st.cache_data(show_spinner=False)
def _parse_pl(data: bytes) -> pd.DataFrame:
    """XLSX P&L / COGS (primera hoja). Lectura cruda, columnas verbatim."""
    return pd.read_excel(BytesIO(data))


@st.cache_data(show_spinner=False)
def _parse_maestro(data: bytes) -> pd.DataFrame:
    """XLSX Maestro de productos (primera hoja). Lectura cruda."""
    return pd.read_excel(BytesIO(data))


@st.cache_data(show_spinner=False)
def _parse_izzi(data: bytes) -> pd.DataFrame:
    """XLSX IZZI (inventario de tercero). Lectura cruda (primera hoja).

    El HTML lee la hoja 'Inventario 2526' con offset de 2 filas y columnas
    posicionales (0=SKU, 5=stock) para armar el lookup. Eso queda para F3.3
    (no hay builder de izzi en el contrato de F3.2).
    """
    return pd.read_excel(BytesIO(data))


# =====================================================================
# B4 — 3 builders de lookups (NO cacheados — toman DataFrame)
# =====================================================================
def _build_cogs_lookup(df_pl: pd.DataFrame) -> dict[str, float]:
    """Port de buildCOGSLookup (HTML L970).

    Por cada fila con SKU no vacío busca las columnas que contengan
    'Total Cost Per Unit' y, recorriéndolas de la última a la primera, toma la
    primera con valor > 0 como COGS. Guarda además el mes en la key
    `'__month__' + sku` (string) — el consumidor (F3.3) lo usa como `cogs_as_of`.

    Política de SKU duplicado: last-valid-wins. Una fila posterior con COGS > 0
    sobrescribe; una fila sin COGS válido no escribe (preserva el valor previo).

    Nota de tipo: el contrato declara `dict[str, float]`, pero por fidelidad al
    HTML las keys `__month__*` mapean a strings (el mes). El dict resultante es
    mixto float / str. Documentado en el reporte de F3.2.
    """
    lookup: dict[str, float] = {}
    for r in df_pl.to_dict("records"):
        sku = _sku_key(r.get("SKU"))
        if not sku:
            continue
        cogs_cols = [k for k in r.keys() if "Total Cost Per Unit" in str(k)]
        cogs = None
        month = None
        for i in range(len(cogs_cols) - 1, -1, -1):
            v = _to_float(r.get(cogs_cols[i]))
            if v > 0:
                cogs = v
                month = (
                    str(cogs_cols[i])
                    .replace("Total Cost Per Unit \n", "")
                    .replace(" (USD)", "")
                    .strip()
                )
                break
        if cogs:
            lookup[sku] = cogs
            lookup["__month__" + sku] = month
    return lookup


def _build_fee_lookup(df_fee: pd.DataFrame) -> dict[str, dict]:
    """Port de buildFeeLookup (HTML L941).

    Agrupa por MSKU. Acumula las fees por unidad (sólo valores > 0) y suma las
    unidades vendidas. El resultado por SKU promedia cada fee (None si no hubo
    ningún valor > 0) y deja la suma de unidades.

    Política de SKU duplicado: AGREGA (promedia fees, suma units) — no es
    last-wins; todas las filas del mismo MSKU contribuyen.

    Value: {fulfillment_fee, referral_fee, ppc_fee, units_sold_week}.
    """
    acc: dict[str, dict] = {}
    for r in df_fee.to_dict("records"):
        sku = _sku_key(r.get("MSKU"))
        if not sku:
            continue
        if sku not in acc:
            acc[sku] = {
                "fulfillment_fee": [],
                "referral_fee": [],
                "ppc_fee": [],
                "units_sold_week": 0.0,
            }
        l = acc[sku]
        ff = _to_float(r.get("FBA fulfillment fees per unit"))
        rf = _to_float(r.get("Referral fee per unit"))
        ppc = _to_float(r.get("Sponsored Products charge per unit"))
        if ff > 0:
            l["fulfillment_fee"].append(ff)
        if rf > 0:
            l["referral_fee"].append(rf)
        if ppc > 0:
            l["ppc_fee"].append(ppc)
        l["units_sold_week"] += _to_float(r.get("Units sold"))

    def _avg(arr):
        return (sum(arr) / len(arr)) if arr else None

    result: dict[str, dict] = {}
    for sku, l in acc.items():
        result[sku] = {
            "fulfillment_fee": _avg(l["fulfillment_fee"]),
            "referral_fee": _avg(l["referral_fee"]),
            "ppc_fee": _avg(l["ppc_fee"]),
            "units_sold_week": l["units_sold_week"],
        }
    return result


def _build_maestro_lookup(df_maestro: pd.DataFrame) -> dict[str, dict]:
    """Port de buildMaestroLookup (HTML L986).

    Key = SKU.trim().lower(); value = la fila completa (dict). El consumidor
    lee Modelo / Talla / Temporada / Categoria / Subcategoria de ese dict.

    Política de SKU duplicado: last-wins (la fila posterior sobrescribe).
    """
    lookup: dict[str, dict] = {}
    for r in df_maestro.to_dict("records"):
        sku = _sku_key(r.get("SKU"))
        if sku:
            lookup[sku.lower()] = r
    return lookup
