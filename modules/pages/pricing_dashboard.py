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
    - Los parsers devuelven el DataFrame crudo. Las transformaciones a lookup que
      el HTML hace al cargar (awd: filtrado de filas metadata; izzi: offset de 2
      filas + columnas posicionales 0=SKU/5=stock) quedan para F3.3 — el contrato
      de F3.2 sólo define lookups para cogs/fee/maestro.
    - _parse_izzi SÍ replica la SELECCIÓN de parseo del HTML (L616-619):
      hoja 'Inventario 2526' con fallback a la primera hoja, y header=None para
      espejar `sheet_to_json(..., {header:1})` (array-de-arrays: ninguna fila se
      consume como header, acceso posicional íntegro). Sin header=None pandas
      perdería la fila 0 y rompería el offset/posicional de F3.3.
    - Los 3 parsers CSV detectan el separador como el HTML (L666-669): cuentan
      ';' vs ',' en la primera línea (semi > comma -> ';', si no ',') y leen con
      encoding='utf-8-sig'. El utf-8-sig preserva los nombres de columna verbatim
      (el HTML elimina el BOM con h.replace(/^\\uFEFF/,'')); sin él el primer
      header quedaría con prefijo BOM y el match por SKU fallaría en silencio.
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


def _detect_sep(data: bytes) -> str:
    """Replica la detección de separador del HTML (parseFile, L666-669).

        const firstLine = content.split('\\n')[0];
        const semiCount = (firstLine.match(/;/g)||[]).length;
        const commaCount = (firstLine.match(/,/g)||[]).length;
        const sep = semiCount > commaCount ? ';' : ',';

    Cuenta ';' vs ',' en la primera línea; semi > comma -> ';', si no ','.
    """
    first_line = data.decode("utf-8-sig", errors="replace").split("\n")[0]
    return ";" if first_line.count(";") > first_line.count(",") else ","


# =====================================================================
# B3 — 6 parsers cacheados (funciones puras, sin st.* adentro)
# =====================================================================
@st.cache_data(show_spinner=False)
def _parse_fba(data: bytes) -> pd.DataFrame:
    """CSV FBA (Amazon FBA Inventory). Lectura cruda, columnas verbatim.

    Separador autodetectado (;/,) y encoding utf-8-sig como el HTML.
    """
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=_detect_sep(data))


@st.cache_data(show_spinner=False)
def _parse_fee(data: bytes) -> pd.DataFrame:
    """CSV Fee (Amazon fee preview / settlement). Lectura cruda (sep ;/, autodetect)."""
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=_detect_sep(data))


@st.cache_data(show_spinner=False)
def _parse_awd(data: bytes) -> pd.DataFrame:
    """CSV AWD (Amazon Warehousing & Distribution). Lectura cruda (sep ;/, autodetect).

    El filtrado de filas metadata (Timestamp / Merchant ID) y la conversión a
    lookup `{SKU: Available in AWD (units)}` que hace el HTML al cargar quedan
    para F3.3 (no hay builder de awd en el contrato de F3.2).
    """
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=_detect_sep(data))


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
    """XLSX IZZI (inventario de tercero). Port de la SELECCIÓN del HTML (L616-619).

        const ws2 = wb2.Sheets['Inventario 2526'] || wb2.Sheets[wb2.SheetNames[0]];
        const raw2 = XLSX.utils.sheet_to_json(ws2, {header:1, defval:null});

    - Hoja 'Inventario 2526' con fallback a la primera hoja (el `||`).
    - header=None espeja `{header:1}` (array-de-arrays): ninguna fila se consume
      como header, columnas posicionales 0..N, todas las filas se preservan.
    El offset de 2 filas + mapeo posicional (0=SKU, 5=stock) queda para F3.3.
    """
    xls = pd.ExcelFile(BytesIO(data))
    sheet = "Inventario 2526" if "Inventario 2526" in xls.sheet_names else xls.sheet_names[0]
    return pd.read_excel(xls, sheet_name=sheet, header=None)


# =====================================================================
# B4 — 3 builders de lookups (NO cacheados — toman DataFrame)
# =====================================================================
def _build_cogs_lookup(df_pl: pd.DataFrame) -> dict[str, float | str]:
    """Port de buildCOGSLookup (HTML L970).

    Por cada fila con SKU no vacío busca las columnas que contengan
    'Total Cost Per Unit' y, recorriéndolas de la última a la primera, toma la
    primera con valor > 0 como COGS. Guarda además el mes en la key
    `'__month__' + sku` (string) — el consumidor (F3.3) lo usa como `cogs_as_of`.

    Política de SKU duplicado: last-valid-wins. Una fila posterior con COGS > 0
    sobrescribe; una fila sin COGS válido no escribe (preserva el valor previo).

    Tipo de retorno: `dict[str, float | str]`. El dict es MIXTO a propósito (port
    1:1 del HTML): las keys de SKU mapean a floats (COGS) y las keys `__month__*`
    a strings (el mes). Separar los meses en un dict aparte queda para v2.
    """
    lookup: dict[str, float | str] = {}
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
