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

from core.persistence import _load_config, _save_config


# =====================================================================
# Catálogo built-in de clientes (display → slug)
# =====================================================================
# No existe (todavía) un catálogo canónico de slugs en core/constants.py ni dirs
# en data/account-health/ — se usa este catálogo built-in. Ajustar si más adelante
# aparece una convención de slugs de Account Health.
_CLIENTES: dict[str, str] = {
    "Dermaglos": "dermaglos",
    "LTD / Love To Dream": "ltd",
    "Setex": "setex",
    "Mott & Bow": "mott-bow",
    "OPTIPET": "optipet",
}

# Defaults de SUBCAT_FEE_AVG: VERBATIM del HTML fuente (const SUBCAT_FEE_AVG, L578).
# Shape: {subcat: {ff, rf, ppc}} (NO float plano) — null del HTML -> None.
# Usado como seed inicial del config per-cliente la primera vez (replica HTML).
_DEFAULT_SUBCAT_FEE_AVG: dict[str, dict] = {
    "Poncho Clasico": {"ff": 7.0575, "rf": 12.6286, "ppc": 0.664},
    "Suéter": {"ff": 6.2794, "rf": 12.6367, "ppc": 0.4905},
    "Sombrero": {"ff": 10.3487, "rf": 24.3885, "ppc": 0.4609},
    "Gorro": {"ff": 4.452, "rf": 3.3375, "ppc": 0.2738},
    "Western Nueva CH": {"ff": 3.0259, "rf": 0.4263, "ppc": 0.2232},
    "Medias": {"ff": 4.5, "rf": None, "ppc": 0.915},
    "Banda de Tela Clasica EC": {"ff": 3.5497, "rf": 0.8685, "ppc": 0.2715},
    "Poncho Ecuador": {"ff": 7.8555, "rf": 14.7333, "ppc": 0.4108},
    "Banda de Tela Nueva EC": {"ff": 3.4073, "rf": 0.9042, "ppc": None},
    "Crin de Caballo": {"ff": 3.576, "rf": 6.3384, "ppc": 0.2912},
    "Cuerdas": {"ff": 3.32, "rf": None, "ppc": None},
    "Poncho Bandera": {"ff": 6.04, "rf": 8.5, "ppc": 0.4525},
    "Guantes": {"ff": 4.5, "rf": 2.0, "ppc": 0.4822},
    "Chinstrap Clasica CH": {"ff": 3.51, "rf": 0.75, "ppc": 0.3643},
    "Western Clasica CH": {"ff": 3.534, "rf": 0.96, "ppc": 0.2386},
    "Poncho Rayado": {"ff": None, "rf": None, "ppc": 0.1},
    "Hoodie Mexicano": {"ff": 7.45, "rf": 5.95, "ppc": 0.267},
    "Tagua": {"ff": None, "rf": None, "ppc": 0.347},
    "Bufanda": {"ff": 4.72, "rf": 5.95, "ppc": 0.4896},
    "Poncho Clint": {"ff": None, "rf": None, "ppc": 0.72},
    "Chinstrap Nueva CH": {"ff": 3.9489, "rf": 0.9083, "ppc": 0.3283},
    "Cavarly Band PK": {"ff": 4.3, "rf": 0.6067, "ppc": 0.251},
    "Ponchohoodie": {"ff": None, "rf": None, "ppc": 0.625},
    "Poncho Reversible": {"ff": 8.25, "rf": 7.65, "ppc": 0.3819},
    "Whiphala": {"ff": 3.42, "rf": 1.95, "ppc": 0.44},
}


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


# =====================================================================
# B7 — _enrich_record + _run_analysis (port de runAnalysis, HTML L800-924)
# =====================================================================
def _js_truthy(v) -> bool:
    """Replica la verdad de JS para cadenas `a || b`: None/NaN/0/0.0/''/False -> False;
    '0' (string no vacío) -> True (como en JS)."""
    if v is None:
        return False
    if isinstance(v, float) and math.isnan(v):
        return False
    return bool(v)


def _strip_row(raw: dict) -> dict:
    """Trim de la frontera de enrichment (decisión consciente F3.3).

    El HTML trimea cada celda del CSV en parseCSV (L733). Nuestros parsers F3.2 leen
    crudo (cerrados, NO se tocan). Acá replicamos el efecto NETO: strip de las celdas
    STRING de la fila FBA antes de las comparaciones del scoring (p.ej. health
    '  Excess  ' -> 'Excess'). Sólo aplica a la fila FBA (CSV); los valores del
    maestro vienen de XLSX y el HTML NO los trimea, así que NO se tocan.

    El descarte de filas con < 2 campos del parseCSV NO se portea: pd.read_csv deja
    esas filas con celdas NaN (ver tests TestCsvDivergenciasHTML), por lo que su
    'available' queda vacío y el filtro de activos de _run_analysis (available > 0)
    las descarta igual — sin necesidad de portear el descarte explícito.
    """
    return {k: (v.strip() if isinstance(v, str) else v) for k, v in raw.items()}


def _row_sku(raw: dict) -> str:
    """Replica `r['sku'] || r['SKU'] || ''` (con str()/strip de robustez)."""
    v = raw.get("sku")
    if not _js_truthy(v):
        v = raw.get("SKU")
    if not _js_truthy(v):
        return ""
    return str(v).strip()


def _effective_price(raw: dict) -> float:
    """Port de effectivePrice (HTML L927-932).

    sales-price || effective_price, luego featuredoffer-price || featured_price,
    luego your-price || your_price. Devuelve el primero > 0 (sp -> fp -> yp).
    """
    sp = raw.get("sales-price")
    if not _js_truthy(sp):
        sp = raw.get("effective_price")
    sp = _to_float(sp)
    fp = raw.get("featuredoffer-price")
    if not _js_truthy(fp):
        fp = raw.get("featured_price")
    fp = _to_float(fp)
    yp = raw.get("your-price")
    if not _js_truthy(yp):
        yp = raw.get("your_price")
    yp = _to_float(yp)
    return sp if sp > 0 else (fp if fp > 0 else yp)


def _enrich_record(raw: dict, lookups: dict) -> dict:
    """Port del bloque de construcción de `rec` de runAnalysis (HTML L814-913).

    `enrichRecord` del HTML (L925) es passthrough (solo se usa para sample data); el
    enriquecimiento real es este bloque inline, que acá se factoriza a una función.

    `raw` = fila FBA (ya trim-eada por _strip_row). `lookups` = bag de contexto que
    arma _run_analysis con las claves: maestro, fee, cogs, awd, izzi (los lookups de
    F3.2), más subcat_avg, model_avg, snapshot_date y subcat_fee_avg (de config).

    Setea restock_alert con el PATH-37 (L835-844: round(daily_rate*37)) — por eso el
    PATH-30 de _compute_score queda como dead-code (su guard `not restock_alert`).
    """
    maestro = lookups.get("maestro", {})
    fee_lk = lookups.get("fee", {})
    cogs_lk = lookups.get("cogs", {})
    awd_lk = lookups.get("awd", {})
    izzi_lk = lookups.get("izzi", {})

    sku = _row_sku(raw)
    sku_low = sku.lower()
    m = maestro.get(sku_low, {})
    fee = fee_lk.get(sku) or fee_lk.get(sku_low) or {}
    cogs = cogs_lk.get(sku) or cogs_lk.get(sku_low)
    price = _effective_price(raw)
    subcat_key = m.get("Subcategoria") or ""
    model_key = m.get("Modelo") or ""

    fba_av = _to_float(raw.get("available"))
    awd_av = awd_lk.get(sku) or awd_lk.get(sku_low) or 0
    izzi_av = izzi_lk.get(sku) or izzi_lk.get(sku_low) or 0
    tot_st = fba_av + awd_av + izzi_av
    has_bkp = (awd_av + izzi_av) > 0
    t7 = _to_float(raw.get("units-shipped-t7"))
    t30 = _to_float(raw.get("units-shipped-t30"))
    t90 = _to_float(raw.get("units-shipped-t90"))
    daily_r = (t30 * 0.7 + (t90 / 3) * 0.3) / 30
    fba_dos = _to_float(raw.get("days-of-supply"))
    if daily_r > 0:
        tot_dos = min(tot_st / daily_r, 999)
    else:
        tot_dos = 999 if tot_st > 0 else 0

    rst_alert = None
    if fba_dos <= 30 and has_bkp and tot_dos > 30:  # PATH-37 (sin guard daily_rate>0)
        to_mv = max(0, _round_half_up(daily_r * 37) - fba_av)
        mx = awd_av + izzi_av
        un = min(to_mv, mx)
        if un > 0:
            src = "AWD" if awd_av >= un else ("IZZI" if izzi_av >= un else "AWD+IZZI")
            rst_alert = f"Mover {_js_num(un)}u a FBA desde {src}"

    rec = {
        "sku": sku,
        "price": price,
        "your_price": _to_float(raw.get("your-price")),
        "asin": raw.get("asin") or "",
        "product_name": raw.get("product-name") or "",
        "snapshot_date": lookups.get("snapshot_date"),
        "Modelo": m.get("Modelo") or "",
        "Talla": m.get("Talla") or "",
        "Temporada": m.get("Temporada") or "",
        "Categoria": m.get("Categoria") or "",
        "Subcategoria": subcat_key,
        "fba_available": fba_av,
        "awd_available": awd_av,
        "izzi_available": izzi_av,
        "total_stock": tot_st,
        "available": fba_av,
        "has_backup": has_bkp,
        "restock_alert": rst_alert,
        "stock_incoming": _to_float(raw.get("inbound-quantity")) + _to_float(raw.get("Total Reserved Quantity")),
        "fba_dos": fba_dos,
        "total_dos": _round_half_up(tot_dos * 10) / 10,
        "daily_rate": _round_half_up(daily_r * 1000) / 1000,
        "sell_through": _to_float(raw.get("sell-through")),
        "dos": fba_dos,
        "t7": t7,
        "t30": t30,
        "t60": _to_float(raw.get("units-shipped-t60")),
        "t90": t90,
        "aging_0_180": _to_float(raw.get("inv-age-0-to-90-days")) + _to_float(raw.get("inv-age-91-to-180-days")),
        "aging_181_270": _to_float(raw.get("inv-age-181-to-270-days")),
        "aging_271_365": _to_float(raw.get("inv-age-271-to-365-days")),
        "aging_366plus": _to_float(raw.get("inv-age-366-to-455-days")) + _to_float(raw.get("inv-age-456-plus-days")),
        "health": raw.get("fba-inventory-level-health-status") or "",
        "rec_action": raw.get("recommended-action") or "",
        "alert": raw.get("alert") or "",
        "no_sale_6m": raw.get("no-sale-last-6-months") or "",
        "sales_rank": _to_float(raw.get("sales-rank")),
        "storage_cost": _to_float(raw.get("estimated-storage-cost-next-month")),
        "featuredoffer_price": _to_float(raw.get("featuredoffer-price")),
        "buybox_price": _to_float(raw.get("featuredoffer-price")),
        "cogs": cogs or None,
        "cogs_as_of": cogs_lk.get("__month__" + sku) or cogs_lk.get("__month__" + sku_low) or None,
        "fulfillment_fee": fee.get("fulfillment_fee") or None,
        "referral_fee": fee.get("referral_fee") or None,
        "ppc_fee": fee.get("ppc_fee") or None,
        "returns_fee": fee.get("returns_fee") or None,
        "units_sold_week": fee.get("units_sold_week") or 0,
        "subcat_avg": lookups.get("subcat_avg", {}).get(subcat_key) or None,
        "model_avg": lookups.get("model_avg", {}).get(model_key) or None,
        "ais_total": _compute_ais(raw),
    }

    # === Márgenes ===
    if (rec["price"] > 0 and rec["cogs"] is not None
            and rec["fulfillment_fee"] is not None and rec["referral_fee"] is not None):
        rec["gross_margin"] = (rec["price"] - rec["cogs"] - rec["fulfillment_fee"] - rec["referral_fee"]) / rec["price"] * 100
        rec["net_margin"] = rec["gross_margin"] - ((rec["ppc_fee"] or 0) / rec["price"] * 100)
    else:
        rec["gross_margin"] = None
        rec["net_margin"] = None

    # === Estimación de fees por subcat para los que faltan ===
    if rec["fulfillment_fee"] is None or rec["referral_fee"] is None:
        avg_fees = lookups.get("subcat_fee_avg", {}).get(rec["Subcategoria"]) or {}
        if rec["fulfillment_fee"] is None and avg_fees.get("ff") is not None:
            rec["fulfillment_fee"] = avg_fees["ff"]
            rec["fulfillment_fee_est"] = True
        if rec["referral_fee"] is None and avg_fees.get("rf") is not None:
            rec["referral_fee"] = avg_fees["rf"]
            rec["referral_fee_est"] = True
        if rec["ppc_fee"] is None and avg_fees.get("ppc") is not None:
            rec["ppc_fee"] = avg_fees["ppc"]
            rec["ppc_fee_est"] = True
        # Recalcular margen con fees estimadas
        if (rec["price"] > 0 and rec["cogs"]
                and rec["fulfillment_fee"] is not None and rec["referral_fee"] is not None):
            rec["gross_margin"] = (rec["price"] - rec["cogs"] - rec["fulfillment_fee"] - rec["referral_fee"]) / rec["price"] * 100
            rec["net_margin"] = rec["gross_margin"] - ((rec["ppc_fee"] or 0) / rec["price"] * 100)

    return rec


def _run_analysis(records: list, lookups: dict, config: dict) -> list:
    """Port de runAnalysis (HTML L800-924). Orquestador del scoring.

    `records` = filas FBA crudas (list[dict]). `lookups` = {maestro, fee, cogs, awd,
    izzi} (los lookups de F3.2 ya construidos). `config` aporta SUBCAT_FEE_AVG y
    current_month. Devuelve la lista de records activos enriquecidos + scoreados (la
    forma del HTML: cada item es el dict que retorna _compute_score, con
    classification / suggestedPrice / restock_alert / score / etc.).

    is_liquidar y la clasificación (subir/bajar/liquidar/mantener) se resuelven dentro
    de _compute_score (igual que el HTML, donde están en computeScore): is_liquidar
    PRECEDE a la clasificación por puntaje.
    """
    rows = [_strip_row(r) for r in records]
    active = [r for r in rows if _to_float(r.get("available")) > 0]

    # Promedios por subcat y por modelo (sobre los activos), igual que el HTML.
    price_map: dict = {}
    for r in active:
        sku = _row_sku(r)
        m = lookups.get("maestro", {}).get(sku.lower(), {})
        price = _effective_price(r)
        subcat = m.get("Subcategoria") or ""
        modelo = m.get("Modelo") or ""
        price_map.setdefault(subcat, []).append(price)
        price_map.setdefault("__model__" + modelo, []).append(price)

    subcat_avg: dict = {}
    model_avg: dict = {}
    for k, arr0 in price_map.items():
        arr = [v for v in arr0 if v > 0]
        if k.startswith("__model__"):
            modelo = k.replace("__model__", "", 1)
            if len(arr) > 1:
                model_avg[modelo] = sum(arr) / len(arr)
        else:
            if len(arr) >= 10:
                subcat_avg[k] = sum(arr) / len(arr)

    if rows:
        snapshot_date = rows[0].get("snapshot-date") or date.today().isoformat()
    else:
        snapshot_date = date.today().isoformat()

    ctx = dict(lookups)
    ctx["subcat_avg"] = subcat_avg
    ctx["model_avg"] = model_avg
    ctx["snapshot_date"] = snapshot_date
    ctx["subcat_fee_avg"] = config.get("SUBCAT_FEE_AVG") or {}

    processed = []
    for raw in active:
        rec = _enrich_record(raw, ctx)
        processed.append(_compute_score(rec, config))
    return processed


# =====================================================================
# F3.4 / C1 — Config per-cliente + render scaffold
# =====================================================================
def _load_or_seed_config(cliente: str) -> dict:
    """Carga el config per-cliente; si no existe o le falta SUBCAT_FEE_AVG lo
    seedea con los defaults verbatim del HTML y lo persiste.

    CRÍTICO: nunca persiste current_month — ese valor vive solo en runtime
    (ver render). Persistir el mes congelaría isOffSeason en disco.
    """
    config = _load_config(
        area="account-health",
        modulo="pricing-dashboard",
        name=cliente,
        version=1,
    )
    if not config or "SUBCAT_FEE_AVG" not in config:
        config = {**(config or {}), "SUBCAT_FEE_AVG": dict(_DEFAULT_SUBCAT_FEE_AVG)}
        _save_config(
            config,
            area="account-health",
            modulo="pricing-dashboard",
            name=cliente,
            version=1,
        )
    return config


# =====================================================================
# F3.4 / C3 — Tabla principal (display) + styler + filtros
# =====================================================================
# El HTML NO tiene una "tabla principal" única: tiene 7 tabs por clasificación /
# criterio (bajar/subir/mantener/liquidar/awdfba/sinmargen/ais), cada uno con su
# propio set de columnas (TABLE_COLS). C3 SINTETIZA una tabla unificada de todos los
# SKUs con un filtro de Estado (clasificación). Los (key, header) son VERBATIM de las
# defs del HTML; los 7 layouts especializados quedan para las vistas de C4.
_COLS_PRINCIPAL: list[tuple[str, str]] = [
    ("score", "Score"),
    ("sku", "SKU"),
    ("Categoria", "Categoría"),
    ("Subcategoria", "Subcategoría"),
    ("Temporada", "Temp."),
    ("classification", "Estado"),
    ("price", "Precio Actual"),
    ("suggestedPrice", "Precio Sugerido"),
    ("buybox_price", "Buy Box"),
    ("gross_margin", "Margen"),
    ("fba_dos", "DoS FBA"),
    ("total_dos", "DoS Total"),
    ("fba_available", "Stock FBA"),
    ("t30", "T30"),
    ("sell_through", "Sell-T"),
    ("health", "Health"),
    ("restock_alert", "Reposición"),
]

_CLASIFS: list[str] = ["subir", "bajar", "liquidar", "mantener"]

# Tinte de fila por clasificación (síntesis para tabla unificada; en el HTML la
# clasificación ES el tab, no había color de fila). Hex *-light verbatim del :root.
_ROW_BG: dict[str, str] = {
    "bajar": "rgba(239,68,68,0.12)",     # --red-light
    "subir": "rgba(34,197,94,0.12)",     # --green-light
    "liquidar": "rgba(168,85,247,0.12)",  # --purple (a855f7) @ 0.12
    "mantener": "",                       # sin tinte
}

# Columnas que se muestran como moneda / % / redondeo (display; el valor sigue numérico).
_FMT_USD_KEYS = ("Precio Actual", "Precio Sugerido", "Buy Box")
_FMT_PCT_KEYS = ("Margen",)
_FMT_ROUND_KEYS = ("DoS FBA", "DoS Total")
_FMT_2DEC_KEYS = ("Sell-T",)


def _resultados_to_df(resultados: list[dict]) -> pd.DataFrame:
    """Convierte la lista de records de _run_analysis a un DataFrame de display.

    PURO. Selecciona y ordena por _COLS_PRINCIPAL (solo keys presentes), renombra a
    los headers verbatim, y reemplaza None/NaN -> '' SOLO en columnas object (para no
    romper Arrow). Las columnas numéricas se dejan numéricas (sort/format en el styler).
    resultados vacío -> DataFrame() vacío.
    """
    if not resultados:
        return pd.DataFrame()
    df = pd.DataFrame(resultados)
    keys = [k for k, _ in _COLS_PRINCIPAL if k in df.columns]
    df = df[keys].rename(columns={k: h for k, h in _COLS_PRINCIPAL})
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].where(df[col].notna(), "")
    return df


def _aplicar_filtros(df: pd.DataFrame, filtros: dict) -> pd.DataFrame:
    """Filtra el DataFrame de display. PURO; devuelve copia, no muta el original.

    Replica los filtros del HTML (populateTable): búsqueda substring + Categoría /
    Temporada / Health exactos. Agrega el filtro de Estado (clasificación) — síntesis
    de la tabla unificada. Filtro vacío/None = no filtra.

    Divergencia con el HTML: la búsqueda allá matchea sku OR Modelo OR product_name;
    acá la tabla principal solo expone SKU, así que la búsqueda es por SKU (substring).
    """
    if df.empty:
        return df.copy()
    out = df
    search = (filtros.get("search") or "").strip().lower()
    if search and "SKU" in out.columns:
        out = out[out["SKU"].astype(str).str.lower().str.contains(search, regex=False)]
    clasif = filtros.get("clasif") or []
    if clasif and "Estado" in out.columns:
        out = out[out["Estado"].isin(clasif)]
    cat = filtros.get("cat") or ""
    if cat and "Categoría" in out.columns:
        out = out[out["Categoría"] == cat]
    temp = filtros.get("temp") or ""
    if temp and "Temp." in out.columns:
        out = out[out["Temp."] == temp]
    health = filtros.get("health") or ""
    if health and "Health" in out.columns:
        out = out[out["Health"] == health]
    return out.copy()


def _fmt_usd(v):
    return "—" if pd.isna(v) else f"${v:.2f}"


def _fmt_pct(v):
    return "—" if pd.isna(v) else f"{v:.1f}%"


def _fmt_round(v):
    return "—" if pd.isna(v) else f"{v:.0f}"


def _fmt_2dec(v):
    return "—" if pd.isna(v) else f"{v:.2f}"


def _margin_color(v):
    """Color de Margen verbatim de la detail-view del HTML (L1547):
    <0 rojo · <15 naranja · <25 dorado · >=25 verde."""
    if pd.isna(v):
        return ""
    if v < 0:
        return "color: #ef4444"
    if v < 15:
        return "color: #f59e0b"
    if v < 25:
        return "color: #eab308"
    return "color: #22c55e"


def _dosfba_color(v):
    """DoS FBA verbatim (bajar/'dos' HTML L1257): >=180 rojo · >=120 naranja."""
    if pd.isna(v):
        return ""
    if v >= 180:
        return "color: #ef4444"
    if v >= 120:
        return "color: #f59e0b"
    return ""


def _dostotal_color(v):
    """DoS Total verbatim (subir HTML L1275): <=30 rojo · <=60 naranja."""
    if pd.isna(v):
        return ""
    if v <= 30:
        return "color: #ef4444"
    if v <= 60:
        return "color: #f59e0b"
    return ""


def _style_principal(df: pd.DataFrame):
    """Devuelve un Styler: tinte de fila por Estado + colores condicionales de celda
    (hex verbatim del HTML) + formato moneda/%/round. NO stringifica numéricas."""
    cols = set(df.columns)

    def _row_style(row):
        bg = _ROW_BG.get(row.get("Estado", ""), "")
        css = f"background-color: {bg}" if bg else ""
        return [css] * len(row)

    sty = df.style.apply(_row_style, axis=1)
    if "Margen" in cols:
        sty = sty.map(_margin_color, subset=["Margen"])
    if "DoS FBA" in cols:
        sty = sty.map(_dosfba_color, subset=["DoS FBA"])
    if "DoS Total" in cols:
        sty = sty.map(_dostotal_color, subset=["DoS Total"])

    fmt = {}
    for k in _FMT_USD_KEYS:
        if k in cols:
            fmt[k] = _fmt_usd
    for k in _FMT_PCT_KEYS:
        if k in cols:
            fmt[k] = _fmt_pct
    for k in _FMT_ROUND_KEYS:
        if k in cols:
            fmt[k] = _fmt_round
    for k in _FMT_2DEC_KEYS:
        if k in cols:
            fmt[k] = _fmt_2dec
    return sty.format(fmt, na_rep="—")


def render() -> None:
    """Entry point del Pricing Dashboard (M30) — sección Account Health.

    F3.4/C2 — uploaders + wiring de _run_analysis (en memoria, sin disco).
    Tabla principal + styler + filtros (C3) y vistas + histórico / persistencia
    (C4) se agregan en commits posteriores de esta misma fase.
    """
    st.title("💲 Pricing Dashboard")
    st.caption("Account Health · scoring de pricing semanal por SKU")

    # current_month derivado UNA sola vez por run. NO se persiste (ver _load_or_seed_config).
    current_month = date.today().month

    # Selector de cliente (catálogo built-in). Sin key= (disciplina Plan D); se usa el return.
    cliente_display = st.selectbox("Cliente", list(_CLIENTES.keys()))
    cliente = _CLIENTES[cliente_display]

    # Config per-cliente: seed de SUBCAT_FEE_AVG la primera vez.
    config = _load_or_seed_config(cliente)

    # Config de corrida: mes inyectado en memoria, SIN mutar el de disco.
    run_config = {**config, "current_month": current_month}

    # ── Carga de fuentes (en memoria, sin disco) ──
    st.divider()
    st.caption(f"Cliente activo: **{cliente_display}** (`{cliente}`)")

    st.subheader("Cargar fuentes")
    col_csv, col_xlsx = st.columns(2)
    with col_csv:
        fba_file = st.file_uploader("FBA (CSV)", type="csv")
        fee_file = st.file_uploader("Fees (CSV)", type="csv")
        awd_file = st.file_uploader("AWD (CSV)", type="csv")
    with col_xlsx:
        pl_file = st.file_uploader("P&L / COGS (XLSX)", type=["xlsx"])
        maestro_file = st.file_uploader("Maestro (XLSX)", type=["xlsx"])
        izzi_file = st.file_uploader("Izzi inventario (XLSX)", type=["xlsx"])

    # FBA es la espina dorsal: sin FBA no hay análisis. El resto enriquece (opcional).
    if st.button("Analizar", disabled=fba_file is None):
        # Parseo: los parsers F3.2 toman bytes (.getvalue()).
        fba_df = _parse_fba(fba_file.getvalue())
        fee_df = _parse_fee(fee_file.getvalue()) if fee_file else None
        pl_df = _parse_pl(pl_file.getvalue()) if pl_file else None
        maestro_df = _parse_maestro(maestro_file.getvalue()) if maestro_file else None
        # awd/izzi se parsean para validar legibilidad, pero NO se integran todavía:
        # no existe builder df -> lookup {sku: unidades} (deuda F3.2→F3.3, ver aviso abajo).
        awd_df = _parse_awd(awd_file.getvalue()) if awd_file else None
        izzi_df = _parse_izzi(izzi_file.getvalue()) if izzi_file else None

        # Lookups SOLO de las fuentes con builder presente; ausentes -> {} (tolerado por
        # los .get() de _enrich_record). Keys = las que lee _run_analysis (PASO 0c).
        lookups = {
            "cogs": _build_cogs_lookup(pl_df) if pl_df is not None else {},
            "fee": _build_fee_lookup(fee_df) if fee_df is not None else {},
            "maestro": _build_maestro_lookup(maestro_df) if maestro_df is not None else {},
            "awd": {},   # sin builder todavía -> backup stock AWD = 0
            "izzi": {},  # sin builder todavía -> backup stock Izzi = 0
        }

        # records = espina FBA como lista de dicts; run_config trae current_month en memoria.
        records = fba_df.to_dict("records")
        st.session_state["m30_resultados"] = _run_analysis(records, lookups, run_config)

        # Deuda visible: AWD/Izzi cargados pero no integrados (no hay builder de lookup).
        pendientes = [n for n, df in (("AWD", awd_df), ("Izzi", izzi_df)) if df is not None]
        st.session_state["m30_aviso_backup"] = (
            f"⚠ {' y '.join(pendientes)} cargado(s) pero NO integrado(s) al análisis: "
            "falta el builder de lookup {sku: unidades} (deuda F3.2→F3.3). "
            "Backup stock = 0 por ahora." if pendientes else ""
        )

    # ── Tabla principal + filtros (display en memoria) ──
    resultados = st.session_state.get("m30_resultados")
    if not resultados:
        st.info("Cargá las fuentes y dale a **Analizar** para ver la tabla.")
        return

    df = _resultados_to_df(resultados)

    # Strip de métricas resumen (la vista 'resumen' completa es C4).
    clasifs = [r.get("classification") for r in resultados]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Subir", clasifs.count("subir"))
    m2.metric("Bajar", clasifs.count("bajar"))
    m3.metric("Liquidar", clasifs.count("liquidar"))
    m4.metric("Mantener", clasifs.count("mantener"))
    aviso = st.session_state.get("m30_aviso_backup")
    if aviso:
        st.caption(aviso)

    # Filtros — Plan D: buffer mutable en session_state, widgets sin key=, se usa el return.
    buf = st.session_state.setdefault(
        "m30_filtros", {"clasif": [], "cat": "", "temp": "", "health": "", "search": ""}
    )
    fc = st.columns(5)
    with fc[0]:
        buf["clasif"] = st.multiselect("Estado", _CLASIFS, default=buf["clasif"])
    with fc[1]:
        cats = [""] + sorted({c for c in df.get("Categoría", pd.Series(dtype=object)) if c})
        buf["cat"] = st.selectbox(
            "Categoría", cats,
            index=cats.index(buf["cat"]) if buf["cat"] in cats else 0,
            format_func=lambda c: c or "(todas)",
        )
    with fc[2]:
        temps = [""] + sorted({t for t in df.get("Temp.", pd.Series(dtype=object)) if t})
        buf["temp"] = st.selectbox(
            "Temporada", temps,
            index=temps.index(buf["temp"]) if buf["temp"] in temps else 0,
            format_func=lambda t: t or "(todas)",
        )
    with fc[3]:
        healths = [""] + sorted({h for h in df.get("Health", pd.Series(dtype=object)) if h})
        buf["health"] = st.selectbox(
            "Health", healths,
            index=healths.index(buf["health"]) if buf["health"] in healths else 0,
            format_func=lambda h: h or "(todas)",
        )
    with fc[4]:
        buf["search"] = st.text_input("Buscar SKU", value=buf["search"])

    df_f = _aplicar_filtros(df, buf)  # filtrar ANTES de estilizar (alineación de índice)
    st.caption(f"{len(df_f)} de {len(df)} SKUs")
    st.dataframe(_style_principal(df_f), use_container_width=True, hide_index=True)
