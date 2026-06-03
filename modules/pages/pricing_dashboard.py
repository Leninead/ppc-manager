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
    - DIVERGENCIA CONOCIDA: los parsers CSV usan pd.read_csv, NO replican el
      parseCSV custom del HTML (L704-739), que hace .trim() por celda, descarta
      filas con < 2 campos y filtra líneas vacías. Sin efecto en CSVs de Amazon
      bien formados; portear el trim/filtrado se difiere a F3.3 (donde el trim de
      columnas string sí impacta las comparaciones verbatim del scoring).
      Congelada en tests TestCsvDivergenciasHTML.
    - Las strings de Amazon NO se normalizan (verbatim).
"""

from __future__ import annotations

from datetime import date
from io import BytesIO
import math
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
    """CSV FBA (Amazon FBA Inventory). Lectura cruda con pd.read_csv.

    Separador autodetectado (;/,) y encoding utf-8-sig como el HTML. NO replica el
    parseCSV custom del HTML (L704-739: .trim() por celda, descarte de filas con
    < 2 campos, filtro de líneas vacías) — divergencia conocida sin efecto en CSVs
    de Amazon bien formados; el trim/filtrado se difiere a F3.3.
    """
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=_detect_sep(data))


@st.cache_data(show_spinner=False)
def _parse_fee(data: bytes) -> pd.DataFrame:
    """CSV Fee (Amazon fee preview / settlement). Lectura cruda con pd.read_csv.

    sep ;/, autodetect + utf-8-sig. NO replica el parseCSV custom del HTML
    (trim/descarte/filtro) — divergencia conocida, diferida a F3.3.
    """
    return pd.read_csv(BytesIO(data), encoding="utf-8-sig", sep=_detect_sep(data))


@st.cache_data(show_spinner=False)
def _parse_awd(data: bytes) -> pd.DataFrame:
    """CSV AWD (Amazon Warehousing & Distribution). Lectura cruda con pd.read_csv.

    sep ;/, autodetect + utf-8-sig. NO replica el parseCSV custom del HTML
    (trim/descarte/filtro) — divergencia conocida, diferida a F3.3. El filtrado de
    filas metadata (Timestamp / Merchant ID) y la conversión a lookup
    `{SKU: Available in AWD (units)}` que hace el HTML al cargar también quedan
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


# =====================================================================
# B5 — Scoring: _compute_ais (port de computeAIS, HTML L934-940)
# =====================================================================
# AIS = Aged Inventory Surcharge (NO "Amazon Inventory Score"). 8 buckets.
_AIS_BUCKETS = (
    "estimated-ais-181-210-days",
    "estimated-ais-211-240-days",
    "estimated-ais-241-270-days",
    "estimated-ais-271-300-days",
    "estimated-ais-301-330-days",
    "estimated-ais-331-365-days",
    "estimated-ais-366-455-days",
    "estimated-ais-456-plus-days",
)


def _compute_ais(record: dict) -> float:
    """Port de computeAIS (HTML L934-940). AIS = Aged Inventory Surcharge.

    Suma los 8 buckets `estimated-ais-*`. Cada celda pasa por _to_float (replica
    `parseFloat(r[c]||0)||0`): ausente / None / '' -> 0. Función pura.
    """
    return sum(_to_float(record.get(c)) for c in _AIS_BUCKETS)


# =====================================================================
# B6 — Scoring: _compute_score (port de computeScore, HTML L998-1151)
# =====================================================================
def _round_half_up(x: float) -> int:
    """Replica JS `Math.round(x)` = floor(x + 0.5) (difiere de round() de Python,
    que usa banker's rounding). Math.round(2.5)=3, round(2.5)=2."""
    return math.floor(x + 0.5)


def _to_fixed(x: float, n: int) -> str:
    """Replica JS `Number.prototype.toFixed(n)` para x >= 0 (único caso usado en
    computeScore: ais/st/gross siempre no-negativos en sus ramas)."""
    factor = 10 ** n
    r = math.floor(x * factor + 0.5) / factor
    return f"{r:.{n}f}"


def _js_num(x) -> str:
    """Replica JS `String(number)`: enteros sin '.0' (5.0 -> '5', 5.5 -> '5.5')."""
    f = float(x)
    return str(int(f)) if f == int(f) else repr(f)


def _compute_score(record: dict, config: dict) -> dict:
    """Port verbatim de computeScore (HTML L998-1151).

    20+ reglas con pesos ENTEROS. Asimétrico: classification 'bajar' si score <= -50,
    'subir' si score >= 20 (con desvío a 'mantener' si hay restock + total_dos>60).
    is_liquidar (regla dura) gana sobre cualquier puntaje. Devuelve la forma del HTML:
    el record completo + score / reasons_down / reasons_up / classification /
    suggestedPrice / suggestedRationale / restock_alert / liq_min_price / is_liquidar.

    `config` provee `current_month` (1-12) para isOffSeason — el HTML lo toma de
    `new Date().getMonth()+1`; acá viene de config (fallback a date.today().month)
    para que el scoring sea determinístico/testeable. SUBCAT_FEE_AVG NO se usa acá
    (se aplica en _enrich_record).

    Incluye el PATH-30 del restock (L1028-1036: round(daily_rate*30)) VERBATIM con su
    guard `not restock_alert`. Es dead-code efectivo porque _enrich_record ya setea
    restock_alert con el PATH-37 antes — se portea igual, NO se arregla.
    """
    score = 0
    reasons_down: list = []
    reasons_up: list = []
    is_winter = (record.get("Temporada") or "") == "Invierno"
    current_month = config.get("current_month")
    if current_month is None:
        current_month = date.today().month
    is_off_season = is_winter and (4 <= current_month <= 9)

    fba_dos = record.get("fba_dos")
    if fba_dos is None:
        fba_dos = record.get("dos") or 0
    total_dos = record.get("total_dos")
    if total_dos is None:
        total_dos = fba_dos
    has_bkp = record.get("has_backup") or False
    fba_avail = record.get("fba_available") or record.get("available") or 0
    total_stock = record.get("total_stock") or fba_avail
    t7 = record.get("t7") or 0
    t30 = record.get("t30") or 0
    st_ = record.get("sell_through") or 0
    aging181 = (record.get("aging_181_270") or 0) + (record.get("aging_271_365") or 0)
    aging366 = record.get("aging_366plus") or 0
    health = record.get("health") or record.get("fba-inventory-level-health-status") or ""
    ais = record.get("ais_total") or 0
    no_sale = str(record.get("no_sale_6m") or "")

    # === LIQUIDAR (independent check) ===
    is_liquidar = (fba_dos >= 365 and t30 <= 2) or (aging366 > 0 and t30 <= 3)

    # === AWD→FBA check (PATH-30, dead-code por el guard !restock_alert) ===
    awd_avail = record.get("awd_available") or 0
    izzi_avail = record.get("izzi_available") or 0
    daily_rate = record.get("daily_rate") or 0
    restock_alert = record.get("restock_alert") or None
    if (not restock_alert) and fba_dos <= 30 and has_bkp and total_dos > 30 and daily_rate > 0:
        to_move = max(0, _round_half_up(daily_rate * 30) - fba_avail)
        max_mov = awd_avail + izzi_avail
        units = min(to_move, max_mov)
        if units > 0:
            src = "AWD" if awd_avail >= units else ("IZZI" if izzi_avail >= units else "AWD+IZZI")
            restock_alert = f"Mover {_js_num(units)}u desde {src}"

    # === DoS: BAJAR usa FBA only ===
    if fba_dos >= 180:
        score -= 30
        reasons_down.append("DoS FBA " + str(_round_half_up(fba_dos)) + "d")
    elif fba_dos >= 120:
        score -= 18
        reasons_down.append("DoS FBA " + str(_round_half_up(fba_dos)) + "d")
    elif fba_dos >= 90:
        score -= 10

    # === DoS: SUBIR usa Total ===
    if total_dos <= 14 and total_stock > 0 and not has_bkp:
        score += 35
        reasons_up.append("DoS crítico " + str(_round_half_up(total_dos)) + "d")
    elif total_dos <= 30 and total_stock > 0 and not has_bkp:
        score += 25
        reasons_up.append("DoS bajo " + str(_round_half_up(total_dos)) + "d")

    # Off-season: peso reducido, FBA DoS only
    if is_off_season and fba_dos >= 90:
        score -= 8
        reasons_down.append("Off-season (Invierno)")

    # Health
    if health == "Excess":
        score -= 20
        reasons_down.append("FBA Excess")
    elif health == "Low stock" and not has_bkp:
        score += 20
        reasons_up.append("Low stock")
    elif health == "Out of stock" and not has_bkp:
        score += 30
        reasons_up.append("Out of stock")

    # Aging (always bad)
    if aging181 > 0 and fba_dos >= 90:
        score -= 10
        reasons_down.append("Aging 181-365d")
    if aging366 > 0:
        score -= 20
        reasons_down.append("Aging 366+d")
    if ais > 0:
        score -= 15
        reasons_down.append("AIS $" + _to_fixed(ais, 2))

    # === VENTAS ===
    if t30 == 0 and fba_dos > 30:
        score -= 20
        reasons_down.append("0 ventas T30")
    elif st_ <= 0.5 and fba_dos > 60 and t30 < 5:
        score -= 20
        reasons_down.append("Sell-through " + _to_fixed(st_, 2))
    elif st_ <= 0.5 and fba_dos > 60:
        score -= 5

    if st_ > 3:
        score += 20
        reasons_up.append("Sell-through " + _to_fixed(st_, 2))
    elif st_ > 2:
        score += 10
        reasons_up.append("ST alto")

    if no_sale == "1" or no_sale == "true":
        score -= 25
        reasons_down.append("Sin ventas 6m")

    rate_t7 = t7 * 4.3
    if t30 > 0 and rate_t7 > t30 * 1.3:
        score += 10
        reasons_up.append("Ventas T7↑")
    if t30 > 2 and rate_t7 < t30 * 0.5:
        score -= 8
        reasons_down.append("Ventas T7↓")

    # === PRECIOS ===
    price = record.get("price") or record.get("effective_price") or 0
    buybox = record.get("buybox_price") or record.get("featuredoffer-price") or 0
    subcat_avg_p = record.get("subcat_avg") or None
    if buybox > 0 and price > 0:
        bb_gap = (price - buybox) / buybox
        if bb_gap > 0.20:
            score -= 15
            reasons_down.append("Precio +" + str(_round_half_up(bb_gap * 100)) + "% vs BB")
        elif bb_gap > 0.10:
            score -= 8
            reasons_down.append("Precio +" + str(_round_half_up(bb_gap * 100)) + "% vs BB")
        elif bb_gap < -0.05:
            score += 10
            reasons_up.append("Precio bajo BB")
    if subcat_avg_p and price > 0:
        p_gap = (price - subcat_avg_p) / subcat_avg_p
        if p_gap < -0.15:
            score += 8
            reasons_up.append("Precio -" + str(_round_half_up(-p_gap * 100)) + "% vs subcat")
        elif p_gap > 0.15:
            score -= 5
            reasons_down.append("Precio +" + str(_round_half_up(p_gap * 100)) + "% vs subcat")

    # === MARGEN ===
    gross = record.get("gross_margin")
    margin_block = False
    if gross is not None:
        if gross < 0:
            score -= 20
            reasons_down.append("Margen negativo")
            margin_block = True
        elif gross < 15:
            reasons_down.append("Margen " + _to_fixed(gross, 1) + "%")
            margin_block = True
        elif gross >= 40:
            score += 8

    # === PRECIO MÍNIMO LIQUIDACIÓN ===
    cogs = record.get("cogs")
    ff = record.get("fulfillment_fee")
    rf = record.get("referral_fee")
    ppc = record.get("ppc_fee") or 0
    ff_est = record.get("fulfillment_fee_est") or False
    rf_est = record.get("referral_fee_est") or False
    fee_note = " (fees est.)" if (ff_est or rf_est) else ""
    if cogs and ff is not None and rf is not None:
        liq_min_price = _round_half_up((cogs + (ff or 0) + (rf or 0) + ppc) * 100) / 100
        floor_15pct = _round_half_up((cogs + (ff or 0) + (rf or 0)) / 0.85 * 100) / 100
    else:
        liq_min_price = None
        floor_15pct = None

    # === CLASIFICACIÓN ===
    if is_liquidar:
        classification = "liquidar"
    elif score <= -50:
        classification = "bajar"
    elif score >= 20:
        if restock_alert and total_dos > 60:
            classification = "mantener"
        else:
            classification = "subir"
    else:
        classification = "mantener"

    if margin_block and classification == "bajar" and gross < 15:
        classification = "mantener"
        reasons_down.append("⚠ Bloqueado: margen bajo")

    # === PRECIO SUGERIDO ===
    suggested_price = None
    suggested_rationale = ""
    if classification == "bajar":
        if buybox > 0:
            tgt = buybox * 0.97
        elif subcat_avg_p:
            tgt = subcat_avg_p * 0.92
        elif price > 0:
            tgt = price * 0.88
        else:
            tgt = None
        if tgt is not None:
            if floor_15pct:
                tgt = max(tgt, floor_15pct)  # never below 15% margin
            suggested_price = _round_half_up(tgt * 100) / 100
            if floor_15pct and suggested_price == floor_15pct:
                suggested_rationale = "Floor: margen 15%" + fee_note
            else:
                suggested_rationale = "Buy Box / Prom. subcat" + fee_note
    elif classification == "subir":
        if buybox > 0 and price < buybox:
            tgt = buybox * 0.99
        elif subcat_avg_p and price < subcat_avg_p:
            tgt = min(price * 1.10, subcat_avg_p * 0.97)
        else:
            tgt = price * 1.07
        suggested_price = _round_half_up(tgt * 100) / 100
        suggested_rationale = "Oportunidad al alza"
    elif classification == "liquidar":
        if liq_min_price and price > 0:
            suggested_price = max(liq_min_price, _round_half_up(price * 0.60 * 100) / 100)
            suggested_rationale = "Liquidación: mín. costo+fees" + fee_note
        elif price > 0:
            suggested_price = _round_half_up(price * 0.60 * 100) / 100
            suggested_rationale = "Liquidación: -40% (sin datos costo)"

    return {
        **record,
        "score": score,
        "reasons_down": reasons_down,
        "reasons_up": reasons_up,
        "classification": classification,
        "suggestedPrice": suggested_price,
        "suggestedRationale": suggested_rationale,
        "restock_alert": restock_alert,
        "liq_min_price": liq_min_price,
        "is_liquidar": is_liquidar,
    }
