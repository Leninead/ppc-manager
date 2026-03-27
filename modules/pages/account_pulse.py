import streamlit as st
import pandas as pd
import io
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter
from datetime import date as _date

# ── Paleta Capybaras ─────────────────────────────────────────────────
_ORG  = "E84000";  _ORG2 = "FF6B00";  _ORG_P = "FFF3E0"
_BLK  = "1F1F1F";  _WHT  = "FAFAFA"
_GRN  = "1B6B2F";  _GRN_L = "E8F5E9"
_RED  = "B71C1C";  _RED_L = "FFEBEE"
_YEL  = "9C5700";  _YEL_L = "FFEB9C"
_DGRAY = "2D3748"; _MGRAY = "CBD5E0"; _LGRAY = "F7FAFC"
_WHITE = "FFFFFF"
_BLUE  = "1E3A8A"; _BLUE_L = "DBEAFE"
_NAVY  = "0D1B3E"

_FESTIVOS_MX = {
    (1, 1): "Año Nuevo", (2, 3): "Constitución", (3, 17): "Juárez",
    (5, 1): "Día del Trabajo", (9, 16): "Independencia",
    (11, 2): "Día de Muertos", (11, 18): "Revolución", (12, 25): "Navidad",
}


# ── Helpers OpenPyXL ─────────────────────────────────────────────────
def _fill(c):
    return PatternFill("solid", fgColor=c)

def _font(bold=False, color="000000", size=9, name="Arial"):
    return Font(bold=bold, color=color, size=size, name=name)

def _bd():
    s = Side(style="thin", color=_MGRAY)
    return Border(left=s, right=s, top=s, bottom=s)

def _al(h="center", v="center", wrap=False):
    return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

def _cell(ws, r, c, val, bg=None, fg="000000", bold=False, fmt=None, size=9, left=False):
    cell = ws.cell(row=r, column=c, value=val)
    if bg:
        cell.fill = _fill(bg)
    cell.font = _font(bold=bold, color=fg, size=size)
    cell.alignment = _al("left" if left else "center")
    cell.border = _bd()
    if fmt:
        cell.number_format = fmt
    return cell

def _hdr(ws, rn, cols, h=14):
    for i, col in enumerate(cols, 1):
        c = ws.cell(row=rn, column=i, value=col)
        c.fill = _fill(_DGRAY); c.font = _font(True, _WHITE, 8)
        c.alignment = _al(); c.border = _bd()
    ws.row_dimensions[rn].height = h

def _sec(ws, rn, text, ncols, bg=None, fg=None, h=16):
    bg = bg or _DGRAY; fg = fg or _WHITE
    ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=ncols)
    c = ws.cell(row=rn, column=1, value=text)
    c.fill = _fill(bg); c.font = _font(True, fg, 10)
    c.alignment = _al("left"); c.border = _bd()
    ws.row_dimensions[rn].height = h
    return rn + 1


# ── Parsers ──────────────────────────────────────────────────────────
def _clean_numeric(series):
    return pd.to_numeric(
        series.astype(str).str.replace(r"[MX$,%$]", "", regex=True).str.replace(",", ""),
        errors="coerce",
    ).fillna(0)


def _find_col(df, keyword):
    for c in df.columns:
        if keyword.lower() in c.lower() and "b2b" not in c.lower():
            return c
    return None


def _parse_br_daily(file):
    """Parse BR diario 14d → dict con daily_rows + PW/TW aggregates."""
    fname = file.name if hasattr(file, "name") else ""
    df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)

    date_col = next((c for c in df.columns if "date" in c.lower()), None)
    if not date_col:
        raise ValueError("BR diario: no se encontró columna Date")

    df["_date"] = pd.to_datetime(df[date_col], format="mixed", dayfirst=False)
    df = df.sort_values("_date")

    sales_col = _find_col(df, "Ordered Product Sales")
    units_col = _find_col(df, "Units Ordered")
    sess_col  = _find_col(df, "Sessions - Total")
    bb_col    = _find_col(df, "Featured Offer (Buy Box) Percentage")

    for tag, col in [("_sales", sales_col), ("_units", units_col),
                     ("_sess", sess_col), ("_bb", bb_col)]:
        if col:
            df[tag] = _clean_numeric(df[col])

    dates = sorted(df["_date"].unique())
    if len(dates) < 7:
        raise ValueError(f"BR diario: solo {len(dates)} fechas, se necesitan al menos 7")

    split_date = dates[-7]
    pw_df = df[df["_date"] < split_date]
    tw_df = df[df["_date"] >= split_date]

    def _sum(d, tag):
        return round(d[tag].sum(), 2) if tag in d else 0
    def _avg(d, tag):
        return round(d[tag].mean(), 2) if tag in d else 0

    # daily rows
    daily_rows = []
    for _, row in df.iterrows():
        dt = row["_date"].date() if hasattr(row["_date"], "date") else row["_date"]
        daily_rows.append({
            "date": dt,
            "sales": float(row.get("_sales", 0)),
            "units": int(row.get("_units", 0)),
            "sessions": int(row.get("_sess", 0)),
        })

    agg = {
        "Sales_TW": _sum(tw_df, "_sales"), "Sales_PW": _sum(pw_df, "_sales"),
        "Units_TW": _sum(tw_df, "_units"), "Units_PW": _sum(pw_df, "_units"),
        "Sessions_TW": _sum(tw_df, "_sess"), "Sessions_PW": _sum(pw_df, "_sess"),
        "BuyBox_TW": _avg(tw_df, "_bb") if "_bb" in tw_df else None,
        "BuyBox_PW": _avg(pw_df, "_bb") if "_bb" in pw_df else None,
    }
    # CVR = Units / Sessions
    agg["CVR_TW"] = round(agg["Units_TW"] / agg["Sessions_TW"] * 100, 2) if agg["Sessions_TW"] > 0 else 0
    agg["CVR_PW"] = round(agg["Units_PW"] / agg["Sessions_PW"] * 100, 2) if agg["Sessions_PW"] > 0 else 0

    return {"daily": daily_rows, "agg": agg}


def _parse_br_child(file):
    """Parse BR by Child ASIN → dict {asin: {Title, Sales, Sessions, BuyBox, ...}}."""
    fname = file.name if hasattr(file, "name") else ""
    df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)

    asin_col = _find_col(df, "Child) ASIN") or _find_col(df, "ASIN")
    title_col = _find_col(df, "Title")
    sales_col = _find_col(df, "Ordered Product Sales")
    sess_col  = _find_col(df, "Sessions - Total")
    units_col = _find_col(df, "Units Ordered")
    bb_col    = _find_col(df, "Featured Offer") or _find_col(df, "Buy Box")

    if not asin_col:
        raise ValueError("BR by Child: no se encontró columna ASIN")

    df = df.dropna(subset=[asin_col])
    for tag, col in [("_sales", sales_col), ("_sess", sess_col),
                     ("_units", units_col), ("_bb", bb_col)]:
        if col:
            df[tag] = _clean_numeric(df[col])

    result = {}
    for _, row in df.iterrows():
        asin = str(row[asin_col]).strip()
        if not asin or asin == "nan":
            continue
        title = str(row[title_col]).strip()[:60] if title_col else asin
        sales = float(row.get("_sales", 0))
        sess  = int(row.get("_sess", 0))
        units = int(row.get("_units", 0))
        bb_raw = float(row.get("_bb", 0)) if "_bb" in row.index else None
        if bb_raw is not None and sess == 0:
            bb_raw = None
        result[asin] = {
            "Title": title, "Sales": sales, "Sessions": sess,
            "Units": units, "BuyBox": bb_raw,
        }
    return result


def _parse_campaigns(file):
    """Parse Campaign CSV → list of campaign dicts."""
    df = pd.read_csv(file)

    camp_col   = _find_col(df, "Campaign Name") or _find_col(df, "Campaign name")
    imp_col    = _find_col(df, "Impressions")
    click_col  = _find_col(df, "Clicks")
    spend_col  = _find_col(df, "Spend") or _find_col(df, "Cost")
    sales_col  = _find_col(df, "Sales")
    orders_col = _find_col(df, "Orders") or _find_col(df, "Purchases")

    if not camp_col:
        raise ValueError("Campaign CSV: no se encontró columna Campaign Name")

    for tag, col in [("_imp", imp_col), ("_click", click_col),
                     ("_spend", spend_col), ("_sales", sales_col),
                     ("_orders", orders_col)]:
        if col:
            df[tag] = _clean_numeric(df[col])

    agg_map = {}
    for tag in ["_imp", "_click", "_spend", "_sales", "_orders"]:
        if tag in df:
            agg_map[tag] = "sum"

    if not agg_map:
        return []

    camp_df = df.groupby(camp_col, as_index=False).agg(agg_map)
    camp_df = camp_df.sort_values("_spend", ascending=False) if "_spend" in camp_df else camp_df

    result = []
    for _, r in camp_df.iterrows():
        imp  = int(r.get("_imp", 0))
        clk  = int(r.get("_click", 0))
        spd  = float(r.get("_spend", 0))
        sal  = float(r.get("_sales", 0))
        ords = int(r.get("_orders", 0))
        acos = round(spd / sal * 100, 1) if sal > 0 else 0
        result.append({
            "Campaign": str(r[camp_col]),
            "Impressions": imp, "Clicks": clk,
            "Spend": round(spd, 2), "Sales": round(sal, 2),
            "ACoS": acos, "Orders": ords,
        })
    return result


# ── Helpers de cálculo ───────────────────────────────────────────────
def _pct(tw, pw):
    try:
        if not pw or float(pw) == 0:
            return None
        return (float(tw) - float(pw)) / float(pw) * 100
    except Exception:
        return None


def _day_type(dt):
    """Returns (type_label, is_festivo_name_or_None) for a date."""
    key = (dt.month, dt.day)
    if key in _FESTIVOS_MX:
        return "Festivo", _FESTIVOS_MX[key]
    if dt.weekday() >= 5:
        return "Finde", None
    return "Laboral", None


def _detect_campaign_age(name):
    """Detect NUEVA vs HEREDADA based on naming convention."""
    import re
    # Capybaras naming usually has structured format with date markers or SP/SD prefix
    # Newer campaigns tend to have structured names like "[Product] - [ASIN] - SP - KW - ..."
    patterns_new = [
        r"\bSP\b.*\bKW\b",      # SP - KW pattern
        r"\bSP\b.*\bPAT\b",     # SP - PAT pattern
        r"\bSD\b.*\bRET\b",     # SD - RET pattern
        r"202[5-9]",             # year in name
    ]
    for pat in patterns_new:
        if re.search(pat, name, re.IGNORECASE):
            return "NUEVA"
    return "HEREDADA"


# ── Excel builder ────────────────────────────────────────────────────
def _build_account_pulse_excel(daily_data, br_child, campaigns, client_name="",
                                target_acos=30.0):
    agg = daily_data["agg"]
    daily = daily_data["daily"]

    wb = Workbook()
    wb.remove(wb.active)

    # ── HOJA 1: Resumen Ejecutivo ────────────────────────────────
    ws1 = wb.create_sheet("Resumen Ejecutivo")
    ws1.sheet_view.showGridLines = False
    NCOLS = 6
    ws1.column_dimensions["A"].width = 25
    ws1.column_dimensions["B"].width = 18
    ws1.column_dimensions["C"].width = 18
    ws1.column_dimensions["D"].width = 18
    ws1.column_dimensions["E"].width = 18
    ws1.column_dimensions["F"].width = 18

    # Header branding
    ws1.merge_cells(start_row=1, start_column=1, end_row=2, end_column=NCOLS)
    c = ws1.cell(row=1, column=1, value=f"  {client_name} — Account Pulse")
    c.fill = _fill(_ORG); c.font = _font(True, _WHITE, 16, "Arial")
    c.alignment = _al("left", wrap=True); c.border = _bd()
    ws1.row_dimensions[1].height = 24
    ws1.row_dimensions[2].height = 20

    ws1.merge_cells(start_row=3, start_column=1, end_row=3, end_column=NCOLS)
    c = ws1.cell(row=3, column=1, value="  Capybaras Agency | Amazon PPC Management")
    c.fill = _fill(_BLK); c.font = _font(True, _WHITE, 9)
    c.alignment = _al("left"); c.border = _bd()
    ws1.row_dimensions[3].height = 16

    # KPI table
    rn = 5
    rn = _sec(ws1, rn, "KPIs — SEMANA ACTUAL vs ANTERIOR", NCOLS, bg=_DGRAY, fg=_WHITE)

    kpi_hdrs = ["Métrica", "This Week", "Prior Week", "Variación %", "Estado", ""]
    _hdr(ws1, rn, kpi_hdrs)
    rn += 1

    def _kpi_row(label, tw_val, pw_val, fmt_fn, inverse=False):
        nonlocal rn
        delta = _pct(tw_val, pw_val)
        # Determine status
        if delta is None:
            status = "—"
            status_bg, status_fg = _LGRAY, "000000"
        elif (inverse and delta < -2) or (not inverse and delta > 2):
            status = "OK"
            status_bg, status_fg = _GRN_L, _GRN
        elif (inverse and delta > 5) or (not inverse and delta < -5):
            status = "ALERTA"
            status_bg, status_fg = _RED_L, _RED
        else:
            status = "ESTABLE"
            status_bg, status_fg = _YEL_L, _YEL

        _cell(ws1, rn, 1, label, left=True, bold=True)
        _cell(ws1, rn, 2, fmt_fn(tw_val), bold=True)
        _cell(ws1, rn, 3, fmt_fn(pw_val))
        if delta is not None:
            d_bg = _GRN_L if ((not inverse and delta > 2) or (inverse and delta < -2)) else (
                _RED_L if ((not inverse and delta < -5) or (inverse and delta > 5)) else _YEL_L)
            d_fg = _GRN if ((not inverse and delta > 2) or (inverse and delta < -2)) else (
                _RED if ((not inverse and delta < -5) or (inverse and delta > 5)) else _YEL)
            _cell(ws1, rn, 4, f"{delta:+.1f}%", bg=d_bg, fg=d_fg, bold=True)
        else:
            _cell(ws1, rn, 4, "—")
        _cell(ws1, rn, 5, status, bg=status_bg, fg=status_fg, bold=True)
        ws1.row_dimensions[rn].height = 18
        rn += 1

    _kpi_row("Sales", agg["Sales_TW"], agg["Sales_PW"],
             lambda v: f"${v:,.2f}")
    _kpi_row("Units", agg["Units_TW"], agg["Units_PW"],
             lambda v: f"{int(v):,}")
    _kpi_row("Sessions", agg["Sessions_TW"], agg["Sessions_PW"],
             lambda v: f"{int(v):,}")
    _kpi_row("CVR %", agg["CVR_TW"], agg["CVR_PW"],
             lambda v: f"{v:.2f}%")

    # ACoS & TACoS from campaigns
    total_spend = sum(c["Spend"] for c in campaigns) if campaigns else 0
    total_ad_sales = sum(c["Sales"] for c in campaigns) if campaigns else 0
    g_acos = (total_spend / total_ad_sales * 100) if total_ad_sales > 0 else None
    g_tacos = (total_spend / agg["Sales_TW"] * 100) if agg["Sales_TW"] > 0 and total_spend > 0 else None

    if g_acos is not None:
        _kpi_row("ACoS %", g_acos, None,
                 lambda v: f"{v:.1f}%" if v else "—", inverse=True)
    if g_tacos is not None:
        _kpi_row("TACoS %", g_tacos, None,
                 lambda v: f"{v:.1f}%" if v else "—", inverse=True)

    if agg.get("BuyBox_TW") is not None:
        _kpi_row("BuyBox %", agg["BuyBox_TW"], agg.get("BuyBox_PW"),
                 lambda v: f"{v:.1f}%" if v else "—")

    rn += 1

    # Diagnostic text
    rn = _sec(ws1, rn, "DIAGNÓSTICO AUTOMÁTICO", NCOLS, bg=_ORG, fg=_WHITE)
    diag_lines = []
    s_d = _pct(agg["Sales_TW"], agg["Sales_PW"])
    if s_d is not None:
        if s_d > 5:
            diag_lines.append(f"Ventas subieron {s_d:+.1f}% — semana positiva.")
        elif s_d < -5:
            diag_lines.append(f"Ventas cayeron {s_d:+.1f}% — revisar tráfico y conversión.")
        else:
            diag_lines.append(f"Ventas estables ({s_d:+.1f}%).")
    se_d = _pct(agg["Sessions_TW"], agg["Sessions_PW"])
    if se_d is not None and se_d < -10:
        diag_lines.append(f"Tráfico bajó {se_d:.1f}% — revisar ranking orgánico y budget de campañas.")
    cvr_d = _pct(agg["CVR_TW"], agg["CVR_PW"])
    if cvr_d is not None and cvr_d < -10:
        diag_lines.append(f"CVR bajó {cvr_d:.1f}% — revisar listings, precio y reviews.")
    if g_acos is not None and g_acos > target_acos * 1.5:
        diag_lines.append(f"ACoS {g_acos:.1f}% supera 1.5x target ({target_acos:.0f}%) — optimizar bids y negativos.")
    bb_issues = [(a, d["BuyBox"]) for a, d in br_child.items()
                 if d.get("BuyBox") is not None and d["BuyBox"] < 95 and d.get("Sessions", 0) > 0]
    if bb_issues:
        diag_lines.append(f"{len(bb_issues)} ASINs con BuyBox < 95% — revisar pricing/stock.")
    if not diag_lines:
        diag_lines.append("Sin alertas críticas. Cuenta saludable.")

    for line in diag_lines:
        ws1.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=NCOLS)
        c = ws1.cell(row=rn, column=1, value=f"  {line}")
        c.font = _font(size=9); c.alignment = _al("left", wrap=True); c.border = _bd()
        ws1.row_dimensions[rn].height = 20
        rn += 1

    rn += 1
    # Summary text block
    pos = sum(1 for d in [s_d, se_d, cvr_d] if d is not None and d > 0)
    neg = sum(1 for d in [s_d, se_d, cvr_d] if d is not None and d < 0)
    if pos >= 2:
        trend_txt = "Semana positiva. Mantener estrategia y escalar campañas top."
    elif neg >= 2:
        trend_txt = "Semana con áreas de mejora. Revisar keywords de bajo rendimiento y ajustar bids."
    else:
        trend_txt = "Semana estable. Monitorear conversión y explorar nuevas keywords."

    rn = _sec(ws1, rn, "CONCLUSIÓN", NCOLS, bg=_NAVY, fg=_WHITE)
    ws1.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=NCOLS)
    c = ws1.cell(row=rn, column=1, value=f"  {trend_txt}")
    c.font = _font(bold=True, size=10); c.alignment = _al("left", wrap=True); c.border = _bd()
    ws1.row_dimensions[rn].height = 24

    # ── HOJA 2: Ventas Diarias ───────────────────────────────────
    ws2 = wb.create_sheet("Ventas Diarias")
    ws2.sheet_view.showGridLines = False

    DAYS_ES = {0: "Lunes", 1: "Martes", 2: "Miércoles", 3: "Jueves",
               4: "Viernes", 5: "Sábado", 6: "Domingo"}

    ws2.merge_cells(start_row=1, start_column=1, end_row=1, end_column=6)
    c = ws2.cell(row=1, column=1, value=f"{client_name} — Ventas Diarias")
    c.fill = _fill(_ORG); c.font = _font(True, _WHITE, 14)
    c.alignment = _al("left"); c.border = _bd()
    ws2.row_dimensions[1].height = 26

    day_hdrs = ["Fecha", "Día", "Tipo", "Sales", "Units", "Sessions"]
    _hdr(ws2, 2, day_hdrs)

    ws2.column_dimensions["A"].width = 14
    ws2.column_dimensions["B"].width = 12
    ws2.column_dimensions["C"].width = 14
    ws2.column_dimensions["D"].width = 14
    ws2.column_dimensions["E"].width = 10
    ws2.column_dimensions["F"].width = 12

    for ri, row in enumerate(daily):
        rn = 3 + ri
        dt = row["date"]
        day_name = DAYS_ES.get(dt.weekday(), "")
        day_type, fest_name = _day_type(dt)

        # Color by type
        if fest_name:
            row_bg = _ORG_P
            type_label = f"Festivo ({fest_name})"
        elif day_type == "Finde":
            row_bg = _LGRAY
            type_label = "Fin de semana"
        else:
            row_bg = _WHITE
            type_label = "Laboral"

        _cell(ws2, rn, 1, str(dt), bg=row_bg, left=True)
        _cell(ws2, rn, 2, day_name, bg=row_bg)
        _cell(ws2, rn, 3, type_label, bg=row_bg, left=True)
        _cell(ws2, rn, 4, row["sales"], bg=row_bg, fmt='"$"#,##0.00')
        _cell(ws2, rn, 5, row["units"], bg=row_bg, fmt="#,##0")
        _cell(ws2, rn, 6, row["sessions"], bg=row_bg, fmt="#,##0")
        ws2.row_dimensions[rn].height = 16

    ws2.freeze_panes = "A3"

    # ── HOJA 3: BuyBox & ASINs ───────────────────────────────────
    ws3 = wb.create_sheet("BuyBox & ASINs")
    ws3.sheet_view.showGridLines = False

    ws3.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)
    c = ws3.cell(row=1, column=1, value=f"{client_name} — BuyBox & ASINs")
    c.fill = _fill(_ORG); c.font = _font(True, _WHITE, 14)
    c.alignment = _al("left"); c.border = _bd()
    ws3.row_dimensions[1].height = 26

    bb_hdrs = ["ASIN", "Título", "Sales", "BuyBox %", "Ventas Perdidas Est."]
    _hdr(ws3, 2, bb_hdrs)

    ws3.column_dimensions["A"].width = 16
    ws3.column_dimensions["B"].width = 45
    ws3.column_dimensions["C"].width = 14
    ws3.column_dimensions["D"].width = 12
    ws3.column_dimensions["E"].width = 20

    # Build and sort by economic impact
    bb_rows = []
    for asin, d in br_child.items():
        sales = d.get("Sales", 0)
        bb = d.get("BuyBox")
        if bb is None:
            bb = 100.0  # assume 100 if unknown
        lost = sales * (1 - bb / 100) if bb < 100 else 0
        bb_rows.append({
            "asin": asin, "title": d.get("Title", ""),
            "sales": sales, "bb": bb if d.get("BuyBox") is not None else None,
            "lost": round(lost, 2),
        })

    bb_rows.sort(key=lambda x: x["lost"], reverse=True)

    for ri, row in enumerate(bb_rows):
        rn = 3 + ri
        row_bg = _WHITE if ri % 2 == 0 else _LGRAY

        _cell(ws3, rn, 1, row["asin"], bg=row_bg, left=True)
        _cell(ws3, rn, 2, row["title"], bg=row_bg, left=True)
        _cell(ws3, rn, 3, row["sales"], bg=row_bg, fmt='"$"#,##0.00')

        bb_val = row["bb"]
        if bb_val is not None:
            if bb_val >= 95:
                bb_bg, bb_fg = _GRN_L, _GRN
            elif bb_val >= 80:
                bb_bg, bb_fg = _YEL_L, _YEL
            else:
                bb_bg, bb_fg = _RED_L, _RED
            _cell(ws3, rn, 4, f"{bb_val:.1f}%", bg=bb_bg, fg=bb_fg, bold=True)
        else:
            _cell(ws3, rn, 4, "—", bg=row_bg)

        if row["lost"] > 0:
            _cell(ws3, rn, 5, row["lost"], bg=_RED_L, fg=_RED, fmt='"$"#,##0.00', bold=True)
        else:
            _cell(ws3, rn, 5, "$0.00", bg=row_bg)

        ws3.row_dimensions[rn].height = 16

    # Total lost
    total_lost = sum(r["lost"] for r in bb_rows)
    if total_lost > 0:
        rn = 3 + len(bb_rows) + 1
        ws3.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=4)
        _cell(ws3, rn, 1, "TOTAL VENTAS PERDIDAS ESTIMADAS", bg=_RED_L, fg=_RED, bold=True, left=True)
        _cell(ws3, rn, 5, total_lost, bg=_RED_L, fg=_RED, fmt='"$"#,##0.00', bold=True)
        ws3.row_dimensions[rn].height = 20

    ws3.freeze_panes = "A3"

    # ── HOJA 4: Campañas ─────────────────────────────────────────
    ws4 = wb.create_sheet("Campañas")
    ws4.sheet_view.showGridLines = False

    ws4.merge_cells(start_row=1, start_column=1, end_row=1, end_column=8)
    c = ws4.cell(row=1, column=1, value=f"{client_name} — Campañas")
    c.fill = _fill(_ORG); c.font = _font(True, _WHITE, 14)
    c.alignment = _al("left"); c.border = _bd()
    ws4.row_dimensions[1].height = 26

    camp_hdrs = ["Campaign", "Tipo", "Impressions", "Clicks", "Spend", "Sales", "ACoS %", "Orders"]
    _hdr(ws4, 2, camp_hdrs)

    ws4.column_dimensions["A"].width = 55
    ws4.column_dimensions["B"].width = 12
    for ci in range(3, 9):
        ws4.column_dimensions[get_column_letter(ci)].width = 14

    for ri, camp in enumerate(campaigns):
        rn = 3 + ri
        row_bg = _WHITE if ri % 2 == 0 else _LGRAY
        age = _detect_campaign_age(camp["Campaign"])

        _cell(ws4, rn, 1, camp["Campaign"][:60], bg=row_bg, left=True)

        # Type color: NUEVA = green, HEREDADA = blue
        if age == "NUEVA":
            _cell(ws4, rn, 2, "NUEVA", bg=_GRN_L, fg=_GRN, bold=True)
        else:
            _cell(ws4, rn, 2, "HEREDADA", bg=_BLUE_L, fg=_BLUE, bold=True)

        _cell(ws4, rn, 3, camp["Impressions"], bg=row_bg, fmt="#,##0")
        _cell(ws4, rn, 4, camp["Clicks"], bg=row_bg, fmt="#,##0")
        _cell(ws4, rn, 5, camp["Spend"], bg=row_bg, fmt='"$"#,##0.00')
        _cell(ws4, rn, 6, camp["Sales"], bg=row_bg, fmt='"$"#,##0.00')

        # ACoS semáforo
        acos_v = camp["ACoS"]
        if acos_v <= target_acos:
            a_bg, a_fg = _GRN_L, _GRN
        elif acos_v <= target_acos * 1.5:
            a_bg, a_fg = _YEL_L, _YEL
        else:
            a_bg, a_fg = _RED_L, _RED
        _cell(ws4, rn, 7, f"{acos_v:.1f}%", bg=a_bg, fg=a_fg, bold=True)

        _cell(ws4, rn, 8, camp["Orders"], bg=row_bg, fmt="#,##0")
        ws4.row_dimensions[rn].height = 16

    ws4.freeze_panes = "A3"

    # Save
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── render() ─────────────────────────────────────────────────────────
def render():
    st.header("📅 Account Pulse")
    st.caption("Monitor de salud diaria: BR diario 14d + BR by Child + Campaign CSV → Excel 4 hojas")
    st.divider()

    client_name = st.text_input("Nombre del cliente", placeholder="Ej: Love To Dream MX",
                                 key="ap_client")
    target_acos = st.slider("Target ACoS %", 5, 100, 30, key="ap_target_acos")

    st.markdown("#### 1 Business Report — 14 días diario")
    st.caption("Sales Dashboard → By Date → Sales and Traffic · Rango: 14 días")
    br_daily_file = st.file_uploader("BR diario 14 días (.csv/.xlsx)",
                                      type=["csv", "xlsx"], key="ap_br_daily")

    st.markdown("#### 2 Business Report — By Child Item")
    st.caption("By ASIN → Detail Page Sales and Traffic By Child Item")
    br_child_file = st.file_uploader("BR by Child Item (.csv/.xlsx)",
                                      type=["csv", "xlsx"], key="ap_br_child")

    st.markdown("#### 3 Campaign Report")
    st.caption("Campaign Manager → mismo date range de 14 días")
    camp_file = st.file_uploader("Campaign CSV (.csv)", type=["csv"], key="ap_campaign")

    if br_daily_file or br_child_file or camp_file:
        st.divider()
        try:
            daily_data = _parse_br_daily(br_daily_file) if br_daily_file else None
            br_child   = _parse_br_child(br_child_file) if br_child_file else {}
            campaigns  = _parse_campaigns(camp_file) if camp_file else []

            # Status messages
            msgs = []
            if daily_data:
                msgs.append(f"BR diario: {len(daily_data['daily'])} días")
            if br_child:
                msgs.append(f"{len(br_child)} ASINs")
            if campaigns:
                msgs.append(f"{len(campaigns)} campañas")
            st.success(" · ".join(msgs))

            # ── KPI cards ────────────────────────────────────────
            if daily_data:
                agg = daily_data["agg"]
                c1, c2, c3, c4, c5 = st.columns(5)

                def _dp(tw, pw):
                    if not pw or pw == 0:
                        return None
                    return (tw - pw) / pw * 100

                d_sales = _dp(agg["Sales_TW"], agg["Sales_PW"])
                d_units = _dp(agg["Units_TW"], agg["Units_PW"])
                d_sess  = _dp(agg["Sessions_TW"], agg["Sessions_PW"])

                c1.metric("Sales TW", f"${agg['Sales_TW']:,.0f}",
                          f"{d_sales:+.1f}%" if d_sales else None)
                c2.metric("Units TW", f"{int(agg['Units_TW']):,}",
                          f"{d_units:+.1f}%" if d_units else None)
                c3.metric("Sessions TW", f"{int(agg['Sessions_TW']):,}",
                          f"{d_sess:+.1f}%" if d_sess else None)
                c4.metric("CVR TW", f"{agg['CVR_TW']:.2f}%")

                total_spend = sum(c["Spend"] for c in campaigns) if campaigns else 0
                total_ad_sales = sum(c["Sales"] for c in campaigns) if campaigns else 0
                g_acos = (total_spend / total_ad_sales * 100) if total_ad_sales > 0 else None
                c5.metric("ACoS", f"{g_acos:.1f}%" if g_acos else "—")

            # ── Daily table preview ──────────────────────────────
            if daily_data:
                st.markdown("##### Ventas Diarias")
                daily_preview = []
                for row in daily_data["daily"]:
                    dt = row["date"]
                    day_type, fest = _day_type(dt)
                    tipo = f"Festivo ({fest})" if fest else ("Finde" if day_type == "Finde" else "Laboral")
                    daily_preview.append({
                        "Fecha": str(dt),
                        "Día": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dt.weekday()],
                        "Tipo": tipo,
                        "Sales": f"${row['sales']:,.2f}",
                        "Units": row["units"],
                        "Sessions": row["sessions"],
                    })
                st.dataframe(pd.DataFrame(daily_preview), use_container_width=True, hide_index=True)

            # ── BuyBox issues ────────────────────────────────────
            if br_child:
                bb_issues = [(a, d) for a, d in br_child.items()
                             if d.get("BuyBox") is not None and d["BuyBox"] < 95
                             and d.get("Sessions", 0) > 0]
                if bb_issues:
                    st.markdown(f"##### BuyBox Alerts ({len(bb_issues)} ASINs < 95%)")
                    bb_preview = []
                    for asin, d in sorted(bb_issues, key=lambda x: x[1].get("Sales", 0), reverse=True):
                        lost = d["Sales"] * (1 - d["BuyBox"] / 100)
                        bb_preview.append({
                            "ASIN": asin,
                            "Título": d["Title"][:40],
                            "Sales": f"${d['Sales']:,.2f}",
                            "BuyBox %": f"{d['BuyBox']:.1f}%",
                            "Ventas Perdidas": f"${lost:,.2f}",
                        })
                    st.dataframe(pd.DataFrame(bb_preview), use_container_width=True, hide_index=True)

            # ── Top campaigns preview ────────────────────────────
            if campaigns:
                st.markdown(f"##### Top Campañas ({len(campaigns)} total)")
                camp_preview = []
                for camp in campaigns[:15]:
                    camp_preview.append({
                        "Campaign": camp["Campaign"][:50],
                        "Spend": f"${camp['Spend']:,.2f}",
                        "Sales": f"${camp['Sales']:,.2f}",
                        "ACoS %": f"{camp['ACoS']:.1f}%",
                        "Orders": camp["Orders"],
                    })
                st.dataframe(pd.DataFrame(camp_preview), use_container_width=True, hide_index=True)

            # ── Download button ──────────────────────────────────
            st.divider()
            if daily_data:
                excel_buf = _build_account_pulse_excel(
                    daily_data=daily_data,
                    br_child=br_child,
                    campaigns=campaigns,
                    client_name=client_name or "Client",
                    target_acos=target_acos,
                )
                safe_n = (client_name or "report").replace(" ", "_")[:30]
                st.download_button(
                    label="Descargar Account Pulse (.xlsx)",
                    data=excel_buf.getvalue(),
                    file_name=f"account_pulse_{safe_n}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="ap_dl",
                )
            else:
                st.info("Cargá al menos el BR diario para generar el Excel.")

        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            st.code(traceback.format_exc())
