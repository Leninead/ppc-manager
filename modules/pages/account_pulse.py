"""Account Pulse (M17): the account's daily health, this week against the prior one.

The ACoS, the TACoS and the campaigns come from the campaign reports of the Amazon Ads account the AM picks, over the
Business Report's own days. The rules live in core/account_pulse/.
"""
import hashlib
import io
import logging
from functools import partial

import pandas as pd
import streamlit as st
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.account_pulse.ads_by_week import AdWeeks, ads_by_week
from core.account_pulse.analysis import ANALYSIS_MODULE, build_analysis_input
from core.account_pulse.buybox import buybox_alerts
from core.account_pulse.campaigns import campaign_rows
from core.account_pulse.day_types import day_type
from core.chat import app_chat
from core.currency_format import excel_money_format, money
from core.date_labels import date_range_label
from core.helpers import kpi_card
from modules.pages.ad_account_block import (
    AccountAds,
    AdAccountTexts,
    ads_exceed_br_warning,
    read_account_ads,
    render_ad_account_block,
)

log = logging.getLogger(__name__)

MODULE_LABEL = "Account Pulse"
KEY_PREFIX = "ap"
TOP_CAMPAIGNS_SHOWN = 15

_ADS_TEXTS = AdAccountTexts(
    title="Publicidad de la cuenta",
    no_accounts=("No hay cuentas de Amazon Ads conectadas, así que no hay ACoS, TACoS ni campañas. Se conectan en "
                 "Sistema → Cuentas conectadas."),
    choose_account=("Elegí la cuenta y el país del BR para el ACoS y el TACoS de cada semana y sus campañas. El BR no "
                    "dice de qué cuenta es, así que no hay una por defecto."),
    first_load=("Estamos trayendo las campañas de esta cuenta por primera vez; cuando termine aparecen el ACoS, el "
                "TACoS y las campañas."),
    unreadable="Sin ACoS, TACoS ni campañas.",
    without_ads="Sin ACoS, TACoS ni campañas",
)
WEEKS_CAPTION = ("ACoS y TACoS de cada semana sobre sus días del BR con datos de ads: esta semana {this_week}, la "
                 "anterior {prior_week}. Sponsored Products con atribución de {attribution} días; Sponsored Brands y "
                 "Display como los cuenta Campaign Manager. Las ventas de ads se atribuyen al día del click: las de los "
                 "últimos días todavía pueden crecer.")

_VERDICT_COLORS = ("background-color:#FFEBEE;color:#9C0006", "background-color:#FAEEDA;color:#412402",
                   "background-color:#EAF3DE;color:#173404")
_AI_TEXTS = {
    "es": {"title": "Análisis IA",
           "caption": "Lectura de la IA sobre las cifras que ya calculó el módulo: qué cambió esta semana contra la "
                      "anterior, qué lo explica y si pide actuar",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "table_title": "Temas del módulo — lectura IA",
           "col_item": "Tema", "col_diag": "Veredicto",
           "counts": "{n} temas leídos",
           "stale_body": "Cambió lo que el análisis leyó, por ejemplo el target ACoS o los datos de ads. Lo que se "
                         "muestra abajo corresponde a los datos anteriores.",
           "topics": {"VENTAS": "Ventas", "TRAFICO": "Tráfico y conversión", "PUBLICIDAD": "Publicidad",
                      "BUYBOX": "Buy Box"},
           "verdicts": {"ACTUAR": "Actuar", "VIGILAR": "Vigilar", "OK": "OK"},
           "asins_below": "{n} ASINs bajo 95%",
           "lost_sales": "pérdida est. {amount}"},
    "en": {"title": "AI analysis",
           "caption": "AI read on the figures the module already computed: what changed this week against the prior "
                      "one, what explains it and whether it calls for action",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "table_title": "The module's topics — AI read",
           "col_item": "Topic", "col_diag": "Verdict",
           "counts": "{n} topics read",
           "stale_body": "What the analysis read changed, for example the target ACoS or the ads data. What is shown "
                         "below belongs to the previous data.",
           "topics": {"VENTAS": "Sales", "TRAFICO": "Traffic and conversion", "PUBLICIDAD": "Advertising",
                      "BUYBOX": "Buy Box"},
           "verdicts": {"ACTUAR": "Act", "VIGILAR": "Watch", "OK": "OK"},
           "asins_below": "{n} ASINs below 95%",
           "lost_sales": "est. loss {amount}"},
}

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

def _note_row(ws, rn, text, ncols, h=30):
    ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=ncols)
    c = ws.cell(row=rn, column=1, value=f"  {text}")
    c.font = _font(size=8, color="555555"); c.alignment = _al("left", wrap=True); c.border = _bd()
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
    """Parse BR diario 14d → dict con daily_rows + PW/TW aggregates + el primer día de la semana actual."""
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

    return {"daily": daily_rows, "agg": agg, "this_week_start": pd.Timestamp(split_date).date()}


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


# ── Helpers de cálculo ───────────────────────────────────────────────
def _pct(tw, pw):
    try:
        if not pw or float(pw) == 0:
            return None
        return (float(tw) - float(pw)) / float(pw) * 100
    except Exception:
        return None


def _percent_text(value):
    return f"{value:.1f}%" if value is not None else "—"


def _week_acos_tacos(weeks: AdWeeks | None):
    """(ACoS TW, ACoS PW, TACoS TW, TACoS PW), None where a week has no ads data."""
    this_week = weeks.this_week if weeks is not None else None
    prior_week = weeks.prior_week if weeks is not None else None
    return (this_week.acos if this_week else None, prior_week.acos if prior_week else None,
            this_week.tacos if this_week else None, prior_week.tacos if prior_week else None)


def _weeks_caption(weeks: AdWeeks) -> str:
    def covered(week):
        return f"{week.covered_days} de {week.history_days} días" if week else "sin días con datos de ads"
    attribution = next((week.attribution_days for week in (weeks.this_week, weeks.prior_week) if week), 7)
    return WEEKS_CAPTION.format(this_week=covered(weeks.this_week), prior_week=covered(weeks.prior_week),
                                attribution=attribution)


# ── Excel builder ────────────────────────────────────────────────────
def _build_account_pulse_excel(daily_data, br_child, campaigns, client_name="", target_acos=30.0, *,
                               weeks: AdWeeks | None = None, currency_code: str = "", ads_period: str = "",
                               ads_note: str = ""):
    agg = daily_data["agg"]
    daily = daily_data["daily"]
    show = partial(money, currency_code=currency_code)
    money_fmt = excel_money_format(currency_code)

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

    _kpi_row("Sales", agg["Sales_TW"], agg["Sales_PW"], show)
    _kpi_row("Units", agg["Units_TW"], agg["Units_PW"],
             lambda v: f"{int(v):,}")
    _kpi_row("Sessions", agg["Sessions_TW"], agg["Sessions_PW"],
             lambda v: f"{int(v):,}")
    _kpi_row("CVR %", agg["CVR_TW"], agg["CVR_PW"],
             lambda v: f"{v:.2f}%")

    # ACoS and TACoS of each week over its own days of the report.
    acos_tw, acos_pw, tacos_tw, tacos_pw = _week_acos_tacos(weeks)
    if weeks is not None:
        _kpi_row("ACoS %", acos_tw, acos_pw, _percent_text, inverse=True)
        _kpi_row("TACoS %", tacos_tw, tacos_pw, _percent_text, inverse=True)

    if agg.get("BuyBox_TW") is not None:
        _kpi_row("BuyBox %", agg["BuyBox_TW"], agg.get("BuyBox_PW"),
                 lambda v: f"{v:.1f}%" if v else "—")

    if weeks is not None:
        rn = _note_row(ws1, rn, _weeks_caption(weeks), NCOLS)
    elif ads_note:
        rn = _note_row(ws1, rn, f"Sin ACoS, TACoS ni campañas: {ads_note}.", NCOLS, h=18)

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
    if acos_tw is not None and acos_tw > target_acos * 1.5:
        diag_lines.append(f"ACoS {acos_tw:.1f}% supera 1.5x target ({target_acos:.0f}%) — optimizar bids y negativos.")
    bb_issues = buybox_alerts(br_child)
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
        kind, fest_name = day_type(dt)

        # Color by type
        if fest_name:
            row_bg = _ORG_P
            type_label = f"Festivo ({fest_name})"
        elif kind == "Finde":
            row_bg = _LGRAY
            type_label = "Fin de semana"
        else:
            row_bg = _WHITE
            type_label = "Laboral"

        _cell(ws2, rn, 1, str(dt), bg=row_bg, left=True)
        _cell(ws2, rn, 2, day_name, bg=row_bg)
        _cell(ws2, rn, 3, type_label, bg=row_bg, left=True)
        _cell(ws2, rn, 4, row["sales"], bg=row_bg, fmt=money_fmt)
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
        _cell(ws3, rn, 3, row["sales"], bg=row_bg, fmt=money_fmt)

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
            _cell(ws3, rn, 5, row["lost"], bg=_RED_L, fg=_RED, fmt=money_fmt, bold=True)
        else:
            _cell(ws3, rn, 5, show(0), bg=row_bg)

        ws3.row_dimensions[rn].height = 16

    # Total lost
    total_lost = sum(r["lost"] for r in bb_rows)
    if total_lost > 0:
        rn = 3 + len(bb_rows) + 1
        ws3.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=4)
        _cell(ws3, rn, 1, "TOTAL VENTAS PERDIDAS ESTIMADAS", bg=_RED_L, fg=_RED, bold=True, left=True)
        _cell(ws3, rn, 5, total_lost, bg=_RED_L, fg=_RED, fmt=money_fmt, bold=True)
        ws3.row_dimensions[rn].height = 20

    ws3.freeze_panes = "A3"

    # ── HOJA 4: Campañas ─────────────────────────────────────────
    ws4 = wb.create_sheet("Campañas")
    ws4.sheet_view.showGridLines = False
    CAMP_COLS = 9

    ws4.merge_cells(start_row=1, start_column=1, end_row=1, end_column=CAMP_COLS)
    title = f"{client_name} — Campañas" + (f" · {ads_period}" if ads_period else "")
    c = ws4.cell(row=1, column=1, value=title)
    c.fill = _fill(_ORG); c.font = _font(True, _WHITE, 14)
    c.alignment = _al("left"); c.border = _bd()
    ws4.row_dimensions[1].height = 26

    camp_hdrs = ["Campaign", "Producto", "Tipo", "Impressions", "Clicks", "Spend", "Sales", "ACoS %", "Orders"]
    _hdr(ws4, 2, camp_hdrs)

    ws4.column_dimensions["A"].width = 55
    ws4.column_dimensions["B"].width = 10
    ws4.column_dimensions["C"].width = 12
    for ci in range(4, CAMP_COLS + 1):
        ws4.column_dimensions[get_column_letter(ci)].width = 14

    for ri, camp in enumerate(campaigns):
        rn = 3 + ri
        row_bg = _WHITE if ri % 2 == 0 else _LGRAY

        _cell(ws4, rn, 1, camp["Campaign"][:60], bg=row_bg, left=True)
        _cell(ws4, rn, 2, camp["Product"], bg=row_bg)

        # Type color: NUEVA = green, HEREDADA = blue
        if camp["Age"] == "NUEVA":
            _cell(ws4, rn, 3, "NUEVA", bg=_GRN_L, fg=_GRN, bold=True)
        else:
            _cell(ws4, rn, 3, "HEREDADA", bg=_BLUE_L, fg=_BLUE, bold=True)

        _cell(ws4, rn, 4, camp["Impressions"], bg=row_bg, fmt="#,##0")
        _cell(ws4, rn, 5, camp["Clicks"], bg=row_bg, fmt="#,##0")
        _cell(ws4, rn, 6, camp["Spend"], bg=row_bg, fmt=money_fmt)
        _cell(ws4, rn, 7, camp["Sales"], bg=row_bg, fmt=money_fmt)

        # ACoS semáforo; a campaign that sold nothing has no ACoS
        acos_v = camp["ACoS"]
        if acos_v is None:
            _cell(ws4, rn, 8, "—", bg=row_bg)
        else:
            if acos_v <= target_acos:
                a_bg, a_fg = _GRN_L, _GRN
            elif acos_v <= target_acos * 1.5:
                a_bg, a_fg = _YEL_L, _YEL
            else:
                a_bg, a_fg = _RED_L, _RED
            _cell(ws4, rn, 8, f"{acos_v:.1f}%", bg=a_bg, fg=a_fg, bold=True)

        _cell(ws4, rn, 9, camp["Orders"], bg=row_bg, fmt="#,##0")
        ws4.row_dimensions[rn].height = 16

    if not campaigns:
        reason = ads_note or "ninguna campaña tuvo actividad en esos días"
        _note_row(ws4, 3, f"Sin campañas: {reason}.", CAMP_COLS, h=18)

    ws4.freeze_panes = "A3"

    # Save
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── render() ─────────────────────────────────────────────────────────
def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>📊</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>Account Pulse</div>"
        "<div style='font-size:0.82rem;color:#888;'>Monitor de salud diaria: BR diario 14d + BR by Child + cuenta de "
        "Amazon Ads → Excel 4 hojas</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()
    _how_to_use()

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

    st.markdown("#### 3 Publicidad — cuenta de Amazon Ads")
    ad_account = render_ad_account_block(KEY_PREFIX, _ADS_TEXTS)

    if not br_daily_file and not br_child_file:
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    st.divider()
    try:
        daily_data = _parse_br_daily(br_daily_file) if br_daily_file else None
        br_child = _parse_br_child(br_child_file) if br_child_file else {}
    except Exception as exc:  # an unreadable report must end in a message, not a traceback
        log.warning("Account Pulse: business report unreadable: %s", exc)
        st.error(f"No se pudo leer el Business Report: {exc}")
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    if daily_data is None:
        st.success(f"{len(br_child)} ASINs")
        profile = ad_account.profile
        _render_buybox_alerts(br_child, partial(money, currency_code=profile.currency_code if profile else ""))
        _render_empty_state()
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return

    history = _history(daily_data)
    ads = read_account_ads(ad_account, history, _ADS_TEXTS, with_campaigns=True)
    weeks = ads_by_week(history, ads.series, daily_data["this_week_start"]) if ads.series is not None else None
    campaigns = campaign_rows(ads.campaigns) if ads.campaigns is not None else []

    loaded = [f"BR diario: {len(daily_data['daily'])} días"]
    if br_child:
        loaded.append(f"{len(br_child)} ASINs")
    if ads.campaigns is not None:
        loaded.append(f"{len(campaigns)} campañas con actividad")
    st.success(" · ".join(loaded))

    pulse_tab, analysis_tab = st.tabs(["📊 Pulse", "🤖 Análisis IA"])
    with pulse_tab:
        _render_pulse(daily_data, br_child, ads, weeks, campaigns, client_name, target_acos)
    with analysis_tab:
        _render_ai_tab(daily_data, br_child if br_child_file else None, ads, weeks, campaigns, target_acos,
                       subject=ads.account or client_name.strip() or br_daily_file.name,
                       data_signature=_data_signature(br_daily_file, br_child_file, ads.profile_id))


def _how_to_use():
    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Monitor de salud diaria con deltas WoW: ventas, units, sessions, CVR, ACoS y TACoS. Marca "
                       "fines de semana y festivos MX.")
        with col2:
            st.markdown("**📂 De dónde salen los datos**")
            st.caption("BR diario 14d (By Date) requerido y BR by Child opcional. La cuenta de Amazon Ads del BR "
                       "(opcional) trae el ACoS, el TACoS y las campañas de los mismos días.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Weekly Client Report (M14) para reporte formal o copiar mensaje Slack para comunicación rápida.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Ingresá nombre del cliente + Target ACoS\n"
            "2. Subí BR diario 14d (requerido) + BR by Child\n"
            "3. Elegí la cuenta y el país del BR para el ACoS, el TACoS y las campañas (opcional)\n"
            "4. Revisá los KPIs de la semana contra la anterior y el Análisis IA\n"
            "5. Descargá el Excel con 4 hojas (Resumen + Ventas Diarias + BuyBox + Campañas)"
        )


def _render_empty_state():
    st.markdown(
        "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
        "border-radius:12px;margin:1rem 0;'>"
        "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
        "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Cargá al menos el BR diario para generar el Excel.</div>"
        "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
        "Arrastrá o hacé click en el uploader de arriba</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def _history(daily_data) -> pd.DataFrame:
    """The daily report as the ads reads take it: one row per day with `_date` and `_sales`."""
    rows = daily_data["daily"]
    return pd.DataFrame({"_date": pd.to_datetime([row["date"] for row in rows]),
                         "_sales": [row["sales"] for row in rows]})


def _render_pulse(daily_data, br_child, ads: AccountAds, weeks: AdWeeks | None, campaigns, client_name,
                  target_acos):
    show = partial(money, currency_code=ads.currency_code)
    agg = daily_data["agg"]
    acos_tw, acos_pw, tacos_tw, tacos_pw = _week_acos_tacos(weeks)

    # ── KPI cards ────────────────────────────────────────
    cards = st.columns(6)
    with cards[0]:
        st.markdown(kpi_card("Sales TW", money(agg["Sales_TW"], ads.currency_code, decimals=0),
                             delta=_pct(agg["Sales_TW"], agg["Sales_PW"])), unsafe_allow_html=True)
    with cards[1]:
        st.markdown(kpi_card("Units TW", f"{int(agg['Units_TW']):,}", delta=_pct(agg["Units_TW"], agg["Units_PW"])),
                    unsafe_allow_html=True)
    with cards[2]:
        st.markdown(kpi_card("Sessions TW", f"{int(agg['Sessions_TW']):,}",
                             delta=_pct(agg["Sessions_TW"], agg["Sessions_PW"])), unsafe_allow_html=True)
    with cards[3]:
        st.markdown(kpi_card("CVR TW", f"{agg['CVR_TW']:.2f}%"), unsafe_allow_html=True)
    with cards[4]:
        st.markdown(kpi_card("ACoS TW", _percent_text(acos_tw), delta=_pct(acos_tw, acos_pw), delta_good=False),
                    unsafe_allow_html=True)
    with cards[5]:
        st.markdown(kpi_card("TACoS TW", _percent_text(tacos_tw), delta=_pct(tacos_tw, tacos_pw), delta_good=False),
                    unsafe_allow_html=True)
    if weeks is not None:
        st.caption(_weeks_caption(weeks))
    else:
        st.caption(f"Sin ACoS, TACoS ni campañas: {ads.no_ads_reason}.")
    if ads.split is not None and ads.split.ads_exceed_br:
        st.warning(ads_exceed_br_warning(ads.split))

    # ── Daily table preview ──────────────────────────────
    st.markdown("##### Ventas Diarias")
    daily_preview = []
    for row in daily_data["daily"]:
        dt = row["date"]
        kind, fest = day_type(dt)
        daily_preview.append({
            "Fecha": str(dt),
            "Día": ["Lun", "Mar", "Mié", "Jue", "Vie", "Sáb", "Dom"][dt.weekday()],
            "Tipo": f"Festivo ({fest})" if fest else ("Finde" if kind == "Finde" else "Laboral"),
            "Sales": show(row["sales"]),
            "Units": row["units"],
            "Sessions": row["sessions"],
        })
    st.dataframe(pd.DataFrame(daily_preview), use_container_width=True, hide_index=True)

    _render_buybox_alerts(br_child, show)

    # ── Top campaigns preview ────────────────────────────
    if campaigns:
        period = date_range_label(ads.split.start, ads.split.end)
        st.markdown(f"##### Top Campañas ({len(campaigns)} con actividad · {period})")
        st.dataframe(pd.DataFrame([{
            "Campaign": camp["Campaign"][:50],
            "Producto": camp["Product"],
            "Tipo": camp["Age"],
            "Spend": show(camp["Spend"]),
            "Sales": show(camp["Sales"]),
            "ACoS %": _percent_text(camp["ACoS"]),
            "Orders": camp["Orders"],
        } for camp in campaigns[:TOP_CAMPAIGNS_SHOWN]]), use_container_width=True, hide_index=True)

    # ── Download button ──────────────────────────────────
    st.divider()
    excel_buf = _build_account_pulse_excel(
        daily_data=daily_data,
        br_child=br_child,
        campaigns=campaigns,
        client_name=client_name or "Client",
        target_acos=target_acos,
        weeks=weeks,
        currency_code=ads.currency_code,
        ads_period=date_range_label(ads.split.start, ads.split.end) if ads.split is not None else "",
        ads_note=ads.no_ads_reason,
    )
    safe_n = (client_name or "report").replace(" ", "_")[:30]
    st.download_button(
        label="Descargar Account Pulse (.xlsx)",
        data=excel_buf.getvalue(),
        file_name=f"account_pulse_{safe_n}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True, key="ap_dl",
    )


def _render_buybox_alerts(br_child, show):
    alerts = buybox_alerts(br_child)
    if not alerts:
        return
    st.markdown(f"##### BuyBox Alerts ({len(alerts)} ASINs < 95%)")
    st.dataframe(pd.DataFrame([{
        "ASIN": alert["asin"],
        "Título": alert["title"][:40],
        "Sales": show(alert["sales"]),
        "BuyBox %": f"{alert['buybox']:.1f}%",
        "Ventas Perdidas": show(alert["lost_sales"]),
    } for alert in alerts]), use_container_width=True, hide_index=True)


def _render_ai_tab(daily_data, br_child, ads: AccountAds, weeks: AdWeeks | None, campaigns, target_acos, *,
                   subject: str, data_signature: str):
    from ai.agents.account_pulse import chat_document
    from ai.config import AI_ENABLED
    from core import ai_tab

    lang = ai_tab.app_language()
    texts = _AI_TEXTS.get(lang, _AI_TEXTS["es"])
    st.subheader(texts["title"])
    st.caption(texts["caption"])
    if not AI_ENABLED:
        st.caption(texts["disabled"])
        app_chat.withdraw_analysis(ANALYSIS_MODULE)
        return
    payload = build_analysis_input(daily_data, br_child, weeks=weeks, split=ads.split, series=ads.series,
                                   campaigns=campaigns, account=ads.account, ads_note=ads.no_ads_reason,
                                   currency_code=ads.currency_code, target_acos=target_acos, lang=lang)
    labels = ai_tab.ai_labels(lang, texts)
    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
    analysis = ai_tab.resolve_analysis(slug=ANALYSIS_MODULE, payload=payload, file_signature=data_signature,
                                       labels=labels, auto_fire=False)
    if analysis is not None:
        # A stale analysis read other figures: its rows show the ones it read.
        records = ai_tab.records_for_render(ANALYSIS_MODULE, analysis, payload,
                                            _ai_records(daily_data, br_child, ads, weeks, labels))
        ai_tab.render_analysis(analysis, slug=ANALYSIS_MODULE, labels=labels,
                               render_result=partial(_render_ai_result, records=records, labels=labels))
    ai_tab.publish_analysis_to_chat(
        ANALYSIS_MODULE, analysis, payload, module_label=MODULE_LABEL, subject=subject,
        reading=lambda finished: chat_document.reading_text(finished.result),
        country_code=ads.country_code, profile_id=ads.profile_id)


def _ai_records(daily_data, br_child, ads: AccountAds, weeks: AdWeeks | None, labels: dict) -> list[dict]:
    """The module's figures behind each topic the AI reads, as the opinion table names them."""
    show = partial(money, currency_code=ads.currency_code)
    agg, topics = daily_data["agg"], labels["topics"]
    sales_change = _pct(agg["Sales_TW"], agg["Sales_PW"])
    records = [
        {"tema": "VENTAS", "item": topics["VENTAS"],
         "metrics": [f"Sales TW {show(agg['Sales_TW'])}", f"PW {show(agg['Sales_PW'])}"]
                    + ([f"{sales_change:+.1f}%"] if sales_change is not None else [])},
        {"tema": "TRAFICO", "item": topics["TRAFICO"],
         "metrics": [f"Sessions TW {int(agg['Sessions_TW']):,}", f"PW {int(agg['Sessions_PW']):,}",
                     f"CVR TW {agg['CVR_TW']:.2f}%", f"PW {agg['CVR_PW']:.2f}%"]},
    ]
    if weeks is not None:
        acos_tw, acos_pw, tacos_tw, tacos_pw = _week_acos_tacos(weeks)
        records.append({"tema": "PUBLICIDAD", "item": topics["PUBLICIDAD"],
                        "metrics": [f"ACoS TW {_percent_text(acos_tw)}", f"PW {_percent_text(acos_pw)}",
                                    f"TACoS TW {_percent_text(tacos_tw)}", f"PW {_percent_text(tacos_pw)}"]})
    alerts = buybox_alerts(br_child) if br_child else []
    buybox_metrics = [f"BuyBox TW {agg['BuyBox_TW']:.1f}%"] if agg.get("BuyBox_TW") is not None else []
    if alerts:
        buybox_metrics += [labels["asins_below"].format(n=len(alerts)),
                           labels["lost_sales"].format(amount=show(sum(alert["lost_sales"] for alert in alerts)))]
    if buybox_metrics:
        records.append({"tema": "BUYBOX", "item": topics["BUYBOX"], "metrics": buybox_metrics})
    return records


def _render_ai_result(result, analysis, *, records, labels):
    from core import ai_tab

    rows = pulse_ai_rows(result.get("lecturas") or [], records, labels)
    warnings = sum(1 for row in rows if row["warning"])
    st.markdown(ai_tab.ai_chips_html(warnings, labels["counts"].format(n=len(rows)), analysis.elapsed, labels),
                unsafe_allow_html=True)
    st.markdown(ai_tab.synthesis_html(result.get("synthesis") or {}, labels), unsafe_allow_html=True)
    if rows:
        st.markdown(ai_tab.opinion_table_html(rows, labels["table_title"], labels, _verdict_colors(labels)),
                    unsafe_allow_html=True)


def pulse_ai_rows(readings: list, records: list, labels: dict) -> list[dict]:
    """Display rows for the opinion table: the topic, the module's figures behind it and the AI's verdict."""
    by_topic = {record["tema"]: record for record in records}
    rows = []
    for reading in readings:
        record = by_topic.get(reading.get("tema"))
        if record is None:
            continue
        verdict = str(reading.get("veredicto", "")).upper()
        rows.append({
            "item": record["item"],
            "metrics": record["metrics"],
            "badges": [labels["verdicts"].get(verdict, verdict)],
            "warning": reading.get("advertencia") or "",
            "reasoning": reading.get("razon", ""),
        })
    return rows


def _verdict_colors(labels: dict) -> dict:
    return dict(zip((labels["verdicts"][verdict] for verdict in ("ACTUAR", "VIGILAR", "OK")), _VERDICT_COLORS))


def _digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()[:16]


def _data_signature(br_daily_file, br_child_file, profile_id: str) -> str:
    """What changes when a report or the account under the analysis do, not when the target ACoS does."""
    child = _digest(br_child_file.getvalue()) if br_child_file else ""
    return f"{_digest(br_daily_file.getvalue())}|{child}|{profile_id}"
