import streamlit as st
import pandas as pd
import io
import os
import re

from core.i18n import _I18N
from core.constants import _BR_OPTIONAL_COLS, _PAGES
from core.helpers import _color_pct, extract_sqp_brand, read_sqp


def _parse_atom11(filepath):
    """Parse an Atom 11 Excel file into a flat DataFrame.

    Returns (df_flat, entity_cols, col_map, fmt) where:
      - df_flat: rows are entities, columns are entity names + "Metric|Period" keys
      - entity_cols: list of entity column names (e.g. ["ASIN"] or ["Portfolio", "CampaignType"])
      - col_map: list of (col_idx, metric_name, period_label)
      - fmt: "WoW" | "MoM" | "DateRange"
    """
    filepath_str = filepath.name if hasattr(filepath, "name") else str(filepath)
    if filepath_str.lower().endswith(".csv"):
        raw = pd.read_csv(filepath, header=None, dtype=str, encoding="utf-8-sig")
    else:
        raw = pd.read_excel(filepath, header=None, dtype=str)

    # Row 2 holds entity column names at the start; stop at first blank cell
    entity_cols = []
    for val in raw.iloc[2]:
        s = str(val).strip() if pd.notna(val) else ""
        if s and s.lower() != "nan":
            entity_cols.append(s)
        else:
            break
    n_entity = len(entity_cols)

    # Build col_map from rows 0 (metric) and 1 (period)
    current_metric = None
    col_map = []
    for ci in range(n_entity, len(raw.columns)):
        m = str(raw.iloc[0, ci]).strip() if pd.notna(raw.iloc[0, ci]) else ""
        p = str(raw.iloc[1, ci]).strip() if pd.notna(raw.iloc[1, ci]) else ""
        if m and m.lower() != "nan":
            current_metric = m
        if p and p.lower() != "nan" and current_metric:
            col_map.append((ci, current_metric, p))

    # Detect format from period labels
    periods = [p for _, _, p in col_map]
    if any("week" in p.lower() for p in periods):
        fmt = "WoW"
    elif any(re.match(r"\d{4}-\d{2}-\d{2}", p) for p in periods):
        fmt = "DateRange"
    else:
        fmt = "MoM"

    # Parse data rows (3+) with forward-fill on entity col 0
    rows = []
    last0 = None
    for ri in range(3, len(raw)):
        row = raw.iloc[ri]
        v0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if v0 and v0.lower() != "nan":
            last0 = v0
        elif last0:
            v0 = last0
        if not v0 or v0.lower() == "nan":
            continue

        rec = {entity_cols[0]: v0}
        for i in range(1, n_entity):
            v = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ""
            rec[entity_cols[i]] = "" if v.lower() == "nan" else v
        for ci, metric, period in col_map:
            v = row.iloc[ci]
            rec[f"{metric}|{period}"] = pd.to_numeric(
                str(v) if pd.notna(v) else "", errors="coerce"
            )
        rows.append(rec)

    return pd.DataFrame(rows), entity_cols, col_map, fmt



# ── Atom 11 helpers ───────────────────────────────────────────────────────────
_ENTITY_TYPE_LABELS = {
    "asin":          "ASIN",
    "portfolioname": "Portfolio",
    "campaigntype":  "Campaign Type",
    "keyword":       "Keyword",
}

def _detect_atom11_type(entity_cols):
    return _ENTITY_TYPE_LABELS.get(entity_cols[0].lower(), entity_cols[0]) if entity_cols else "Desconocido"

def _extract_period_df(df_flat, entity_cols, col_map, period_label):
    """Return a DataFrame with entity_cols + plain metric columns for one period."""
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))
    result = df_flat[entity_cols].copy()
    for metric in metrics:
        col = f"{metric}|{period_label}"
        if col in df_flat.columns:
            result[metric] = df_flat[col]
    return result

def _summarize_daterange(df_flat, entity_cols, col_map):
    """Sum all date columns per metric. Returns (df, period_label)."""
    periods = list(dict.fromkeys(p for _, _, p in col_map))
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))
    result = df_flat[entity_cols].copy()
    for metric in metrics:
        date_cols = [f"{metric}|{p}" for p in periods if f"{metric}|{p}" in df_flat.columns]
        if date_cols:
            result[metric] = df_flat[date_cols].sum(axis=1)
    return result, f"{periods[0]}\u2192{periods[-1]}"


def _split_two_weeks(df_flat, entity_cols, col_map):
    """Detect if a DateRange file spans exactly 14 days and split into two 7-day weeks.

    Returns (df_w1, df_w2, label_w1, label_w2) or None if not a 14-day range.
    Week 1 (Valor Anterior) = days 1-7, Week 2 (Valor Actual) = days 8-14.
    """
    from datetime import timedelta
    periods = list(dict.fromkeys(p for _, _, p in col_map))
    parsed = []
    for p in periods:
        try:
            parsed.append((p, pd.to_datetime(p).date()))
        except Exception:
            return None
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[1])
    first_date = parsed[0][1]
    last_date  = parsed[-1][1]
    if (last_date - first_date).days + 1 != 14:
        return None
    mid_date      = first_date + timedelta(days=7)
    week1_periods = [p for p, d in parsed if d < mid_date]
    week2_periods = [p for p, d in parsed if d >= mid_date]
    if not week1_periods or not week2_periods:
        return None
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))

    def _sum_week(wperiods):
        res = df_flat[entity_cols].copy()
        for metric in metrics:
            dcols = [f"{metric}|{p}" for p in wperiods if f"{metric}|{p}" in df_flat.columns]
            if dcols:
                res[metric] = df_flat[dcols].sum(axis=1)
        return res

    df_w1   = _sum_week(week1_periods)
    df_w2   = _sum_week(week2_periods)
    label_w1 = f"{week1_periods[0]} \u2192 {week1_periods[-1]}"
    label_w2 = f"{week2_periods[0]} \u2192 {week2_periods[-1]}"
    return df_w1, df_w2, label_w1, label_w2

def _kpis(df):
    """Compute aggregate KPI dict from a single-period DataFrame."""
    def s(c):
        return float(pd.to_numeric(df[c], errors="coerce").fillna(0).sum()) if c in df.columns else 0.0
    im, cl, sp, sl, or_ = s("Impressions"), s("Clicks"), s("Spend"), s("Sales"), s("Orders")
    return {
        "Impressions": im,   "Clicks": cl,  "Spend": sp,  "Sales": sl,  "Orders": or_,
        "ACoS": round(sp / sl * 100, 2) if sl > 0 else 0.0,
        "ROAS": round(sl / sp,       2) if sp > 0 else 0.0,
        "CTR":  round(cl / im * 100, 2) if im > 0 else 0.0,
        "CVR":  round(or_ / cl * 100,2) if cl > 0 else 0.0,
        "CPC":  round(sp / cl,       2) if cl > 0 else 0.0,
    }

def _generate_summary(tipo, entity_col, kc, kp=None, per_c="", per_p="", top_rows=None, lang="es"):
    t = _I18N[lang]

    def pct_chg(curr, prev):
        return ((curr - prev) / prev * 100) if prev and prev != 0 else None

    sp, sl, cl, im, or_ = kc["Spend"], kc["Sales"], kc["Clicks"], kc["Impressions"], kc["Orders"]
    acos, roas, ctr, cvr, cpc = kc["ACoS"], kc["ROAS"], kc["CTR"], kc["CVR"], kc["CPC"]
    sep = "=" * 62
    L = [sep, f"  {t['s_title']} \u2014 {tipo.upper()}", sep,
         f"  {t['s_period']} {per_c}"]
    if per_p:
        L.append(f"  {t['s_comparison']} {per_p}")
    L += ["", f"  {t['s_metrics']}",
          f"    {t['s_spend']}  ${sp:>12,.2f}",
          f"    {t['s_sales']}  ${sl:>12,.2f}",
          f"    ACoS:                    {acos:>11.1f}%",
          f"    ROAS:                    {roas:>11.2f}x",
          f"    {t['s_impr']}  {im:>12,.0f}",
          f"    Clicks:                  {cl:>12,.0f}",
          f"    CTR:                     {ctr:>11.2f}%",
          f"    CVR:                     {cvr:>11.2f}%",
          f"    {t['s_cpc']}  ${cpc:>11.2f}", ""]

    if kp:
        sp_p, sl_p, cl_p, im_p = kp["Spend"], kp["Sales"], kp["Clicks"], kp["Impressions"]
        acos_p = kp["ACoS"]
        def fmt_d(curr, prev, inv=False):
            d = pct_chg(curr, prev)
            if d is None: return "  -"
            arrow = "^" if d > 0 else "v"
            good = (d > 0) != inv
            tag = "  OK" if good else "  !!"
            return f"{tag} {arrow} {abs(d):.1f}%"
        acos_delta = acos - acos_p
        L += [f"  {t['s_variation']}",
              f"    {t['s_inv_short']} {fmt_d(sp, sp_p)}",
              f"    {t['s_sal_short']} {fmt_d(sl, sl_p)}",
              f"    Clicks:       {fmt_d(cl, cl_p)}",
              f"    {t['s_impr_short']} {fmt_d(im, im_p)}",
              f"    ACoS:         {'  !!' if acos_delta > 0 else '  OK'} {'+' if acos_delta > 0 else ''}{acos_delta:.1f}pp", ""]

    L.append(f"  {t['s_diag']}")
    if sl == 0:
        L.append(f"    {t['s_no_sales']}")
    elif acos < 15:
        L.append(f"    {t['s_acos_great'].format(acos)}")
    elif acos < 25:
        L.append(f"    {t['s_acos_ok'].format(acos)}")
    elif acos < 40:
        L.append(f"    {t['s_acos_warn'].format(acos)}")
    else:
        L.append(f"    {t['s_acos_bad'].format(acos)}")
    if im > 0:
        if ctr < 0.2:
            L.append(f"    {t['s_ctr_vlow'].format(ctr)}")
        elif ctr < 0.5:
            L.append(f"    {t['s_ctr_low'].format(ctr)}")
        else:
            L.append(f"    {t['s_ctr_ok'].format(ctr)}")
    if cl > 0:
        if cvr < 5:
            L.append(f"    {t['s_cvr_low'].format(cvr)}")
        elif cvr < 15:
            L.append(f"    {t['s_cvr_ok'].format(cvr)}")
        else:
            L.append(f"    {t['s_cvr_high'].format(cvr)}")
    L.append("")

    if top_rows:
        n = min(3, len(top_rows))
        L.append(f"  TOP {n} {tipo.upper()} {t['s_top']}")
        for i, row in enumerate(top_rows[:n], 1):
            name = row.get(entity_col, "-")
            r_sl = row.get("Sales", 0) or 0
            r_sp = row.get("Spend", 0) or 0
            r_acos = (r_sp / r_sl * 100) if r_sl > 0 else 0
            L.append(f"    {i}. {name}: ${r_sl:,.2f} {t['s_sales_lbl']} | ACoS {r_acos:.1f}%")
        L.append("")

    L.append(f"  {t['s_recs']}")
    recs = []
    if acos > 40:
        recs += [t["sr_reduce_bids"], t["sr_negative"]]
    elif acos > 25:
        recs.append(t["sr_opt_bids"])
    elif acos < 10 and sp > 50:
        recs.append(t["sr_scale"])
    if ctr < 0.3 and im > 1000:
        recs += [t["sr_ab_test"], t["sr_relevance"]]
    if cvr < 5 and cl > 100:
        recs.append(t["sr_listing"])
    if kp:
        sl_d = pct_chg(sl, kp["Sales"]); sp_d = pct_chg(sp, kp["Spend"])
        if sl_d is not None and sl_d < -15:
            recs.append(t["sr_sales_down"].format(abs(sl_d)))
        if sp_d is not None and sl_d is not None and sp_d > 10 and sl_d < sp_d - 10:
            recs.append(t["sr_spend_grow"])
    if not recs:
        recs += [t["sr_maintain"], t["sr_longtail"]]
    for i, r in enumerate(recs, 1):
        L.append(f"    {i}. {r}")
    L += ["", sep, f"  {t['s_footer']}", sep]
    return "\n".join(L)



def _diag_items(kc, kp=None, lang="es"):
    """Return list of (status, text) diagnostic items based on KPI values."""
    t    = _I18N[lang]
    acos = kc.get("ACoS", 0) or 0
    ctr  = kc.get("CTR",  0) or 0
    cvr  = kc.get("CVR",  0) or 0
    sl   = kc.get("Sales",0) or 0
    items = []
    if sl == 0:
        items.append(("error", t["d_no_sales"]))
    elif acos < 15:
        items.append(("ok",    t["d_acos_great"].format(acos)))
    elif acos < 30:
        items.append(("ok",    t["d_acos_ok"].format(acos)))
    elif acos < 60:
        items.append(("warn",  t["d_acos_warn"].format(acos)))
    else:
        items.append(("error", t["d_acos_bad"].format(acos)))
    if ctr > 0:
        if ctr < 0.2:   items.append(("error", t["d_ctr_vlow"].format(ctr)))
        elif ctr < 0.5: items.append(("warn",  t["d_ctr_low"].format(ctr)))
        else:           items.append(("ok",    t["d_ctr_ok"].format(ctr)))
    if cvr > 0:
        if cvr < 5:    items.append(("warn",  t["d_cvr_low"].format(cvr)))
        elif cvr < 15: items.append(("ok",    t["d_cvr_ok"].format(cvr)))
        else:          items.append(("ok",    t["d_cvr_high"].format(cvr)))
    if kp:
        sl_p = kp.get("Sales", 0) or 0; acos_p = kp.get("ACoS", 0) or 0
        if sl_p > 0:
            sl_d = (sl - sl_p) / sl_p * 100; ad = acos - acos_p
            if sl_d > 10:    items.append(("ok",    t["d_sales_up"].format(sl_d)))
            elif sl_d < -10: items.append(("error", t["d_sales_down"].format(abs(sl_d))))
            if ad < -3:      items.append(("ok",    t["d_acos_better"].format(abs(ad))))
            elif ad > 3:     items.append(("warn",  t["d_acos_worse"].format(ad)))
    return items


def _rec_items(kc, kp=None, lang="es"):
    """Return list of recommendation strings based on KPI values."""
    t    = _I18N[lang]
    acos = kc.get("ACoS", 0) or 0; ctr = kc.get("CTR", 0) or 0
    cvr  = kc.get("CVR",  0) or 0; sp  = kc.get("Spend", 0) or 0
    im   = kc.get("Impressions", 0) or 0; cl = kc.get("Clicks", 0) or 0
    recs = []
    if acos > 40:
        recs += [t["r_reduce_bids"], t["r_negative"]]
    elif acos > 25:
        recs.append(t["r_opt_bids"])
    elif acos < 10 and sp > 50:
        recs.append(t["r_scale"])
    if ctr < 0.3 and im > 1000:
        recs += [t["r_ab_test"], t["r_relevance"]]
    if cvr < 5 and cl > 100:
        recs.append(t["r_listing"])
    if kp:
        sl_d = ((kc["Sales"] - kp["Sales"]) / kp["Sales"] * 100) if kp.get("Sales") else None
        sp_d = ((kc["Spend"] - kp["Spend"]) / kp["Spend"] * 100) if kp.get("Spend") else None
        if sl_d is not None and sl_d < -15:
            recs.append(t["r_sales_down"].format(abs(sl_d)))
        if sp_d is not None and sl_d is not None and sp_d > 10 and sl_d < sp_d - 10:
            recs.append(t["r_spend_grow"])
    if not recs:
        recs += [t["r_maintain"], t["r_longtail"]]
    return recs

def _build_atom11_excel(display_df, kc, kp, tipo, per_c, per_p, delta_cols,
                        client_name="", entity_col="", top_rows=None, lang="es",
                        parent_evo_df=None):
    """Build a professional 3-sheet Excel report. No formula-causing characters."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    t = _I18N[lang]

    # Palette (no # prefix in openpyxl)
    NAVY  = "1F3864"; WHITE = "FFFFFF"; LGRAY = "F5F5F5"; FAFAFA = "FAFAFA"
    MGRAY = "BDBDBD"; DGRAY = "424242"; BLUE_D = "1565C0"
    GRN_L = "E8F5E9"; GRN_D = "2E7D32"
    YEL_L = "FFF8E1"; YEL_D = "F57F17"
    RED_L = "FFEBEE"; RED_D = "C62828"

    def fl(color): return PatternFill("solid", fgColor=color)
    def ft(color=DGRAY, bold=False, sz=10):
        return Font(color=color, bold=bold, size=sz, name="Arial")
    def bd():
        s = Side(style="thin", color=MGRAY)
        return Border(left=s, right=s, top=s, bottom=s)
    def al(h="left", v="center", wrap=False):
        return Alignment(horizontal=h, vertical=v, wrap_text=wrap)

    def merged_row(ws, r, ncols, value, font_obj, fill_obj, align_obj, height=18):
        """Write a value into a merged full-width row. Returns next row index."""
        end_col = get_column_letter(ncols)
        ws.merge_cells(f"A{r}:{end_col}{r}")
        c = ws.cell(row=r, column=1)
        c.value = value; c.font = font_obj
        c.fill = fill_obj; c.alignment = align_obj
        ws.row_dimensions[r].height = height
        return r + 1

    def kpi_colors(label, value):
        if label == "ACoS":
            return (GRN_L, GRN_D) if value < 30 else ((YEL_L, YEL_D) if value < 60 else (RED_L, RED_D))
        if label == "ROAS":
            return (GRN_L, GRN_D) if value >= 3 else ((YEL_L, YEL_D) if value >= 1.5 else (RED_L, RED_D))
        if label == "CTR":
            return (GRN_L, GRN_D) if value >= 0.5 else ((YEL_L, YEL_D) if value >= 0.2 else (RED_L, RED_D))
        if label == "CVR":
            return (GRN_L, GRN_D) if value >= 10 else ((YEL_L, YEL_D) if value >= 5 else (RED_L, RED_D))
        return LGRAY, DGRAY

    KPI_TABLE = [
        (t["kpi_impressions"], "Impressions", "{:,.0f}",  False),
        (t["kpi_clicks"],      "Clicks",      "{:,.0f}",  False),
        (t["kpi_spend"],       "Spend",       "${:,.2f}", False),
        (t["kpi_sales"],       "Sales",       "${:,.2f}", False),
        (t["kpi_orders"],      "Orders",      "{:,.0f}",  False),
        ("ACoS",               "ACoS",        "{:.1f}%",  True),
        ("ROAS",               "ROAS",        "{:.2f}x",  False),
        ("CTR",                "CTR",         "{:.2f}%",  False),
        ("CVR",                "CVR",         "{:.2f}%",  False),
        ("CPC",                "CPC",         "${:.2f}",  True),
    ]
    COLORED_KPI = {"ACoS", "ROAS", "CTR", "CVR"}

    wb = Workbook()

    # =========================================================================
    # SHEET 1 — Informe Cliente (client-facing)
    # =========================================================================
    ws1 = wb.active
    ws1.title = t["sheet1"]
    ws1.sheet_view.showGridLines = False
    ws1.sheet_view.zoomScale = 90
    NC1 = 5
    for col, w in zip("ABCDE", (30, 20, 20, 14, 14)):
        ws1.column_dimensions[col].width = w

    r = 1
    # Branding strip
    r = merged_row(ws1, r, NC1, "PPC MANAGER",
                   ft(MGRAY, False, 8), fl(NAVY), al("right"), 12)
    # Main title
    r = merged_row(ws1, r, NC1, t["report_title"],
                   Font(name="Arial", size=22, color=WHITE, bold=True), fl(NAVY), al("center"), 44)
    # Tipo + client name
    sub = f"{tipo.upper()}   |   {client_name}" if client_name else tipo.upper()
    r = merged_row(ws1, r, NC1, sub,
                   Font(name="Arial", size=12, color=MGRAY), fl(NAVY), al("center"), 24)
    # Period info
    p_txt = f"{t['period_lbl']}: {per_c}" + (f"   |   {t['comparison_lbl']}: {per_p}" if per_p else "")
    r = merged_row(ws1, r, NC1, p_txt, ft(LGRAY, False, 9), fl(NAVY), al("center"), 18)
    r += 1  # spacer

    # KPI section header
    r = merged_row(ws1, r, NC1, f"  {t['kpi_section']}",
                   ft(WHITE, True, 11), fl(BLUE_D), al("left"), 22)
    # Column headers
    ws1.row_dimensions[r].height = 16
    for ci, h_txt in enumerate([t["col_metric"], t["col_current"], t["col_previous"], t["col_change"], ""], 1):
        c = ws1.cell(row=r, column=ci)
        c.value = h_txt; c.font = ft(WHITE, True, 9)
        c.fill = fl(DGRAY); c.alignment = al("center"); c.border = bd()
    r += 1

    for label, key, fmt_str, lower_better in KPI_TABLE:
        cv = kc.get(key, 0) or 0
        pv = (kp.get(key, 0) or 0) if kp else None
        is_col = label in COLORED_KPI
        vfl, vfc = kpi_colors(label, cv)
        curr_str = fmt_str.format(cv)
        prev_str = fmt_str.format(pv) if pv is not None else "-"
        if pv is not None and pv != 0:
            dpct = (cv - pv) / pv * 100
            is_good = (dpct < 0) if lower_better else (dpct > 0)
            # Use "^"/"v" arrows — never "+" to avoid Excel formula errors
            arrow = "^" if dpct > 0 else "v"
            delta_str = f"{arrow} {abs(dpct):.1f}%"
            d_fl, d_fc = (GRN_L, GRN_D) if is_good else (RED_L, RED_D)
        else:
            delta_str = "-"; d_fl, d_fc = LGRAY, DGRAY
        ws1.row_dimensions[r].height = 20
        for ci, (val, bg, fc, bold, halign) in enumerate([
            (label,     LGRAY,               DGRAY,          True,   "left"),
            (curr_str,  vfl if is_col else LGRAY, vfc if is_col else DGRAY, is_col, "center"),
            (prev_str,  LGRAY,               DGRAY,          False,  "center"),
            (delta_str, d_fl,                d_fc,           True,   "center"),
            ("",        LGRAY,               DGRAY,          False,  "center"),
        ], 1):
            c = ws1.cell(row=r, column=ci)
            c.value = val; c.fill = fl(bg)
            c.font = Font(name="Arial", size=10, color=fc, bold=bold)
            c.alignment = al(halign); c.border = bd()
        r += 1
    r += 1  # spacer

    # Top performers
    if top_rows and entity_col:
        r = merged_row(ws1, r, NC1, f"  TOP {min(3, len(top_rows))} {tipo.upper()} {t['top_by_sales']}",
                       ft(WHITE, True, 11), fl(BLUE_D), al("left"), 22)
        for i, row_d in enumerate(top_rows[:3], 1):
            name  = str(row_d.get(entity_col, "-"))
            r_sl  = row_d.get("Sales", 0) or 0
            r_sp  = row_d.get("Spend", 0) or 0
            r_acos = (r_sp / r_sl * 100) if r_sl > 0 else 0
            line  = f"  {i}.  {name}   |   {t['sales_label']}: ${r_sl:,.2f}   |   ACoS: {r_acos:.1f}%"
            bg    = [GRN_L, LGRAY, FAFAFA][i - 1]
            r = merged_row(ws1, r, NC1, line, ft(DGRAY, False, 10), fl(bg), al("left"), 18)
        r += 1

    # Diagnostic section
    r = merged_row(ws1, r, NC1, f"  {t['diag_section']}",
                   ft(WHITE, True, 11), fl(BLUE_D), al("left"), 22)
    STATUS_MAP = {
        "ok":    (GRN_L, GRN_D, "OK      "),
        "warn":  (YEL_L, YEL_D, t["st_warn"]),
        "error": (RED_L, RED_D, t["st_error"]),
    }
    for status, text in _diag_items(kc, kp, lang=lang):
        bg, fc, badge = STATUS_MAP.get(status, (LGRAY, DGRAY, "        "))
        r = merged_row(ws1, r, NC1, f"  [{badge}]   {text}",
                       ft(fc, False, 10), fl(bg), al("left"), 18)
    r += 1

    # Recommendations
    r = merged_row(ws1, r, NC1, f"  {t['rec_section']}",
                   ft(WHITE, True, 11), fl(BLUE_D), al("left"), 22)
    for i, rec in enumerate(_rec_items(kc, kp, lang=lang), 1):
        alt_bg = LGRAY if i % 2 == 0 else FAFAFA
        r = merged_row(ws1, r, NC1, f"  {i}.  {rec}",
                       ft(DGRAY, False, 10), fl(alt_bg),
                       Alignment(horizontal="left", vertical="center", wrap_text=True), 28)
    r += 1
    merged_row(ws1, r, NC1, t["footer"],
               ft(MGRAY, False, 8), fl(NAVY), al("right"), 14)

    # =========================================================================
    # SHEET 2 — KPIs
    # =========================================================================
    ws2 = wb.create_sheet(t["sheet2"])
    ws2.sheet_view.showGridLines = False
    ws2.sheet_view.zoomScale = 90
    NC2 = 4
    for col, w in zip("ABCD", (20, 18, 18, 16)):
        ws2.column_dimensions[col].width = w

    r2 = 1
    r2 = merged_row(ws2, r2, NC2, t["kpi_comparative"],
                    Font(name="Arial", size=14, color=WHITE, bold=True), fl(NAVY), al("center"), 30)
    sub2 = f"{t['current_lbl']}: {per_c}" + (f"   |   {t['previous_lbl']}: {per_p}" if per_p else "")
    r2 = merged_row(ws2, r2, NC2, sub2, ft(LGRAY, False, 9), fl(NAVY), al("center"), 16)
    r2 += 1

    ws2.row_dimensions[r2].height = 16
    h2 = [t["col_metric"], f"{t['current_lbl']} ({per_c[:12]})",
          f"{t['previous_lbl']} ({per_p[:12]})" if per_p else t["previous_lbl"], t["col_change"]]
    for ci, h_txt in enumerate(h2, 1):
        c = ws2.cell(row=r2, column=ci)
        c.value = h_txt; c.font = ft(WHITE, True, 9)
        c.fill = fl(DGRAY); c.alignment = al("center"); c.border = bd()
    r2 += 1

    for label, key, fmt_str, lower_better in KPI_TABLE:
        cv = kc.get(key, 0) or 0
        pv = (kp.get(key, 0) or 0) if kp else None
        is_col = label in COLORED_KPI
        vfl, vfc = kpi_colors(label, cv)
        ws2.row_dimensions[r2].height = 18

        for ci, (val, bg, fc, bold) in enumerate([
            (label,               LGRAY,               DGRAY,          True),
            (fmt_str.format(cv),  vfl if is_col else LGRAY, vfc if is_col else DGRAY, is_col),
            (fmt_str.format(pv) if pv is not None else "-", LGRAY, DGRAY, False),
        ], 1):
            c = ws2.cell(row=r2, column=ci)
            c.value = val; c.font = Font(name="Arial", size=10, color=fc, bold=bold)
            c.fill = fl(bg); c.alignment = al("center" if ci > 1 else "left"); c.border = bd()

        # Delta column — written as string to avoid Excel formula issues
        c = ws2.cell(row=r2, column=4)
        if pv is not None and pv != 0:
            dpct = (cv - pv) / pv * 100
            is_good = (dpct < 0) if lower_better else (dpct > 0)
            arrow = "^" if dpct > 0 else "v"
            c.value = f"{arrow} {abs(dpct):.1f}%"
            c.font = Font(name="Arial", size=10, color=GRN_D if is_good else RED_D, bold=True)
            c.fill = fl(GRN_L if is_good else RED_L)
        else:
            c.value = "-"; c.font = ft(DGRAY, False, 10); c.fill = fl(LGRAY)
        c.alignment = al("center"); c.border = bd()
        r2 += 1

    # =========================================================================
    # SHEET 3 — Datos (comparison table)
    # =========================================================================
    ws3 = wb.create_sheet(t["sheet3"])
    ws3.sheet_view.showGridLines = False
    ws3.sheet_view.zoomScale = 90
    ws3.freeze_panes = "A3"

    cols3 = list(display_df.columns)
    delta_set = set(delta_cols)
    NC3 = max(len(cols3), 1)

    r3 = 1
    r3 = merged_row(ws3, r3, NC3, f"{t['detail_header']}   {tipo.upper()}   {per_c}",
                    Font(name="Arial", size=11, color=WHITE, bold=True), fl(NAVY), al("left"), 22)
    ws3.row_dimensions[r3].height = 16
    for ci, col_name in enumerate(cols3, 1):
        c = ws3.cell(row=r3, column=ci)
        c.value = col_name; c.font = ft(WHITE, True, 9)
        c.fill = fl(NAVY); c.alignment = al("center"); c.border = bd()
        ws3.column_dimensions[get_column_letter(ci)].width = min(max(len(str(col_name)) + 2, 10), 35)
    r3 += 1

    for ri, (_, row_vals) in enumerate(display_df.iterrows()):
        row_bg = LGRAY if ri % 2 == 0 else FAFAFA
        ws3.row_dimensions[r3].height = 15
        for ci, col_name in enumerate(cols3, 1):
            val = row_vals[col_name]
            safe_val = None if (isinstance(val, float) and val != val) else val
            c = ws3.cell(row=r3, column=ci)
            c.value = safe_val; c.border = bd(); c.alignment = al("center")
            if col_name in delta_set and isinstance(safe_val, (int, float)):
                is_good = safe_val > 0
                c.font = Font(name="Arial", size=9, color=GRN_D if is_good else RED_D, bold=True)
                c.fill = fl(GRN_L if is_good else RED_L)
            else:
                c.font = ft(DGRAY, False, 9); c.fill = fl(row_bg)
        r3 += 1

    # ── Parent Evolution sheet (optional) ────────────────────────────────────
    if parent_evo_df is not None and not parent_evo_df.empty:
        ws_pe = wb.create_sheet("Parent Evolution")
        ws_pe.sheet_view.showGridLines = False
        ws_pe.sheet_view.zoomScale = 90
        cols_pe = list(parent_evo_df.columns)
        pct_cols_pe = {c for c in cols_pe if "%" in c}

        # Header row
        ws_pe.row_dimensions[1].height = 22
        for ci, col_name in enumerate(cols_pe, 1):
            c = ws_pe.cell(row=1, column=ci)
            c.value = col_name
            c.font = ft(WHITE, True, 9)
            c.fill = fl(NAVY)
            c.alignment = al("center")
            c.border = bd()
            ws_pe.column_dimensions[get_column_letter(ci)].width = min(max(len(str(col_name)) + 3, 12), 32)

        # Data rows
        for ri, (_, row_vals) in enumerate(parent_evo_df.iterrows()):
            row_bg = LGRAY if ri % 2 == 0 else FAFAFA
            ws_pe.row_dimensions[ri + 2].height = 15
            for ci, col_name in enumerate(cols_pe, 1):
                val = row_vals[col_name]
                safe_val = None if (isinstance(val, float) and val != val) else val
                c = ws_pe.cell(row=ri + 2, column=ci)
                c.value = safe_val
                c.border = bd()
                c.alignment = al("center")
                if col_name in pct_cols_pe and isinstance(safe_val, (int, float)) and safe_val is not None:
                    is_good = safe_val > 0
                    c.font = Font(name="Arial", size=9, color=GRN_D if is_good else RED_D, bold=True)
                    c.fill = fl(GRN_L if is_good else RED_L)
                else:
                    c.font = ft(DGRAY, False, 9)
                    c.fill = fl(row_bg)

    buf = io.BytesIO()
    wb.save(buf)
    return buf



def _parse_business_report_map(filepath_or_file):
    """Parse a Business Report CSV/XLSX for Parent-Child ASIN mapping.

    Required columns : "(Parent) ASIN", "(Child) ASIN"
    Optional column  : "Title"
    Extra optional   : any column in _BR_OPTIONAL_COLS
    Standalones      : rows where (Parent) ASIN == (Child) ASIN treated as own parent
    CSV format       : BOM-aware (utf-8-sig), numbers may contain $, commas, %

    Returns:
        child_to_parent : dict  {child_asin: parent_asin}
        asin_to_title   : dict  {asin: title}
        br_df           : DataFrame with "__asin" + present optional cols (numeric), or None
    """
    COL_PARENT = "(Parent) ASIN"
    COL_CHILD  = "(Child) ASIN"
    COL_TITLE  = "Title"

    # ── Detect extension robustly ─────────────────────────────────────────────
    if isinstance(filepath_or_file, str):
        _ext = os.path.splitext(filepath_or_file)[1].lower()
    elif hasattr(filepath_or_file, "name"):
        _ext = os.path.splitext(filepath_or_file.name)[1].lower()
    else:
        _ext = ".csv"   # BytesIO or unknown → assume CSV

    try:
        if _ext == ".csv":
            df = pd.read_csv(filepath_or_file, dtype=str, encoding="utf-8-sig")
        else:
            df = pd.read_excel(filepath_or_file, dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo: {e}")

    # Strip BOM and whitespace from column names
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]

    missing_required = [c for c in [COL_PARENT, COL_CHILD] if c not in df.columns]
    if missing_required:
        raise ValueError(
            f"Columnas requeridas no encontradas: {missing_required}. "
            f"Columnas disponibles: {list(df.columns[:20])}"
        )

    has_title    = COL_TITLE in df.columns
    present_opts = [c for c in _BR_OPTIONAL_COLS if c in df.columns]

    # ── Build mapping dicts ───────────────────────────────────────────────────
    child_to_parent = {}
    asin_to_title   = {}

    for _, row in df.iterrows():
        parent = str(row[COL_PARENT]).strip() if pd.notna(row[COL_PARENT]) else ""
        child  = str(row[COL_CHILD]).strip()  if pd.notna(row[COL_CHILD])  else ""

        if not parent or parent.lower() == "nan":
            continue
        if not child or child.lower() == "nan":
            continue

        if has_title:
            t = str(row[COL_TITLE]).strip() if pd.notna(row[COL_TITLE]) else ""
            if t and t.lower() != "nan":
                asin_to_title[child]  = t
                asin_to_title[parent] = t

        child_to_parent[child] = parent

    # ── Build optional-metrics DataFrame with proper numeric conversion ───────
    br_df = None
    if present_opts:
        keep  = [COL_CHILD] + present_opts
        br_df = df[[c for c in keep if c in df.columns]].copy()
        br_df = br_df.rename(columns={COL_CHILD: "__asin"})

        for c in present_opts:
            if c not in br_df.columns:
                continue
            # Clean Amazon number formats: "$1,408.59" / "1,162" / "30.90%"
            cleaned = (
                br_df[c].astype(str)
                .str.replace(r"[$,%]", "", regex=True)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            br_df[c] = pd.to_numeric(cleaned, errors="coerce")

        br_df = br_df.dropna(subset=["__asin"])
        br_df["__asin"] = br_df["__asin"].str.strip()

    return child_to_parent, asin_to_title, br_df


def _build_parent_evolution(df_flat, ec1, cm1, fmt1, child_to_parent, asin_to_title,
                            br_df=None, lang="es"):
    """Group Atom 11 ASIN-level PPC data by Parent ASIN.

    Crosses df_flat[entity_col] directly with child_to_parent by ASIN.
    Output columns:
      Parent ASIN | Nombre | Ventas WoW (%) | Ventas últ. 7d | Ventas 7d ant. |
      [Ventas últ. 30d] | [Ventas últ. 90d] | [BR optional cols aggregated]

    br_df: optional DataFrame with "__asin" + BR optional cols (already numeric).
    Returns (DataFrame, error_message_or_None).
    """
    t          = _I18N.get(lang, _I18N["es"])
    entity_col = ec1[0]

    df = df_flat.copy()
    df["__parent"] = df[entity_col].astype(str).map(child_to_parent)
    df_mapped = df.dropna(subset=["__parent"])

    if df_mapped.empty:
        return None, (
            "No se encontraron ASINs del reporte en el mapeo Parent-Child. "
            "Verificá que el Business Report CSV sea del mismo cliente que el reporte Atom 11."
        )

    # i18n column name aliases
    C_WOW  = t["col_sales_wow"]
    C_CURR = t["col_sales_current"]
    C_PREV = t["col_sales_prev"]
    C_30D  = t["col_sales_30d"]
    C_90D  = t["col_sales_90d"]

    def _sum(grp, cols):
        present = [c for c in cols if c in df.columns]
        if not present:
            return 0.0
        return float(pd.to_numeric(grp[present].values.flatten(), errors="coerce").sum())

    def _wow_pct(curr, prev):
        return round((curr - prev) / prev * 100, 1) if prev else None

    parent_rows = []

    if fmt1 == "DateRange":
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        try:
            periods_sorted = sorted(periods, key=lambda p: pd.to_datetime(p))
        except Exception:
            periods_sorted = periods
        n = len(periods_sorted)

        def sc(ps):
            return [f"Sales|{p}" for p in ps]

        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}

            if n >= 14:
                v7c = _sum(grp, sc(periods_sorted[-7:]))
                v7p = _sum(grp, sc(periods_sorted[-14:-7]))
                row[C_WOW]  = _wow_pct(v7c, v7p)
                row[C_CURR] = round(v7c, 2)
                row[C_PREV] = round(v7p, 2)
            elif n >= 2:
                mid = n // 2
                vc  = _sum(grp, sc(periods_sorted[mid:]))
                vp  = _sum(grp, sc(periods_sorted[:mid]))
                row[C_WOW]  = _wow_pct(vc, vp)
                row[C_CURR] = round(vc, 2)
                row[C_PREV] = round(vp, 2)
            else:
                row[C_CURR] = round(_sum(grp, sc(periods_sorted)), 2)

            if n >= 30:
                row[C_30D] = round(_sum(grp, sc(periods_sorted[-30:])), 2)
            if n >= 90:
                row[C_90D] = round(_sum(grp, sc(periods_sorted[-90:])), 2)

            parent_rows.append(row)

    elif fmt1 == "WoW":
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        curr_p  = periods[-1]
        prev_p  = periods[0] if len(periods) >= 2 else None

        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}
            cc  = f"Sales|{curr_p}"
            cv  = float(pd.to_numeric(grp[cc], errors="coerce").sum()) if cc in df.columns else 0.0
            if prev_p:
                pc = f"Sales|{prev_p}"
                pv = float(pd.to_numeric(grp[pc], errors="coerce").sum()) if pc in df.columns else 0.0
                row[C_WOW]  = _wow_pct(cv, pv)
                row[C_PREV] = round(pv, 2)
            row[C_CURR] = round(cv, 2)
            parent_rows.append(row)

    else:  # MoM / single period
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        period  = periods[0] if periods else ""
        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}
            col = f"Sales|{period}"
            if col in df.columns:
                row[C_CURR] = round(
                    float(pd.to_numeric(grp[col], errors="coerce").sum()), 2
                )
            parent_rows.append(row)

    if not parent_rows:
        return None, "No se pudo generar la tabla de evolución por Parent ASIN."

    result = pd.DataFrame(parent_rows)

    # Merge BR optional metrics aggregated by parent
    if br_df is not None and not br_df.empty:
        br_copy = br_df.copy()
        br_copy["__parent"] = br_copy["__asin"].map(child_to_parent)
        br_copy = br_copy.dropna(subset=["__parent"])
        if not br_copy.empty:
            opt_cols = [c for c in _BR_OPTIONAL_COLS if c in br_copy.columns]
            if opt_cols:
                br_agg = (
                    br_copy.groupby("__parent")[opt_cols]
                    .sum(numeric_only=True)
                    .reset_index()
                    .rename(columns={"__parent": "Parent ASIN"})
                )
                result = result.merge(br_agg, on="Parent ASIN", how="left")

    return result, None


def _generate_parent_evo_summary(pe_df, lang="es"):
    """Build a copiable executive summary from a Parent Evolution DataFrame.

    Uses i18n keys from _I18N so the output matches the ES/EN toggle.
    """
    t        = _I18N.get(lang, _I18N["es"])
    C_WOW    = t["col_sales_wow"]
    C_CURR   = t["col_sales_current"]
    C_PREV   = t["col_sales_prev"]
    C_ORD1   = t["col_total_orders"]   # "Total Order Items"
    C_ORD2   = t["col_units_ordered"]  # "Units Ordered"

    sep   = "=" * 62
    lines = [sep, f"  {t['pe_summary_title']}", sep, ""]

    total_curr   = 0.0
    total_prev   = 0.0
    total_orders = 0
    has_prev     = C_PREV in pe_df.columns
    has_wow      = C_WOW  in pe_df.columns

    for _, row in pe_df.iterrows():
        raw_name = row.get("Nombre", "") or row.get("Parent ASIN", "")
        name     = str(raw_name).strip()
        if not name or name.lower() == "nan":
            name = str(row.get("Parent ASIN", "")).strip()
        if len(name) > 45:
            name = name[:42] + "..."

        curr = float(row.get(C_CURR, 0) or 0)
        prev = float(row.get(C_PREV, 0) or 0) if has_prev else None
        wow  = row.get(C_WOW) if has_wow else None

        orders = 0
        for oc in [C_ORD1, C_ORD2]:
            if oc in row.index:
                v = row.get(oc)
                if pd.notna(v):
                    try:
                        orders = int(float(v))
                        break
                    except (ValueError, TypeError):
                        pass

        total_curr   += curr
        total_orders += orders
        if prev is not None:
            total_prev += prev

        if prev is not None and pd.notna(wow):
            w = float(wow)
            if w >= 0:
                lines.append("  " + t["pe_summary_wow_pos"].format(
                    name=name, pct=abs(w), curr=f"{curr:,.2f}",
                    prev=f"{prev:,.2f}", orders=orders))
            else:
                lines.append("  " + t["pe_summary_wow_neg"].format(
                    name=name, pct=w, curr=f"{curr:,.2f}",
                    prev=f"{prev:,.2f}", orders=orders))
        else:
            lines.append("  " + t["pe_summary_no_prev"].format(
                name=name, curr=f"{total_curr:,.2f}", orders=orders))

    lines.append("")
    ts = f"{total_curr:,.2f}"
    if total_prev > 0:
        tw = round((total_curr - total_prev) / total_prev * 100, 1)
        lines.append("  " + t["pe_summary_total_wow"].format(
            total_sales=ts, total_orders=total_orders, wow=tw))
    else:
        lines.append("  " + t["pe_summary_total"].format(
            total_sales=ts, total_orders=total_orders))

    lines.append(sep)
    return "\n".join(lines)



# ── MerchanSpring helpers ─────────────────────────────────────────────────────

def _parse_merchanspring(file):
    """Parse a MerchanSpring weekly report Excel (4-sheet format)."""
    xl = pd.ExcelFile(file)
    result = {}

    def _safe(v):
        s = str(v).strip() if pd.notna(v) else ""
        return "" if s.lower() == "nan" else s

    def _parse_simple_sheet(idx, header_row_idx, data_start_idx):
        raw = pd.read_excel(xl, sheet_name=idx, header=None, dtype=str)
        hdrs = [_safe(v) for v in raw.iloc[header_row_idx] if _safe(v)]
        rows = []
        for ri in range(data_start_idx, len(raw)):
            r = raw.iloc[ri]
            v0 = _safe(r.iloc[0])
            if not v0 or "TOTALS" in v0.upper():
                continue
            rec = {h: (_safe(r.iloc[j]) if j < len(r) else "") for j, h in enumerate(hdrs)}
            rows.append(rec)
        return pd.DataFrame(rows, columns=hdrs)

    # ── Summary (sheet 0) ──────────────────────────────────────────────────
    raw0 = pd.read_excel(xl, sheet_name=0, header=None, dtype=str)
    result["title"]  = _safe(raw0.iloc[1, 0])
    result["period"] = _safe(raw0.iloc[2, 0])

    kpis = []
    for col in [0, 2, 4, 6, 8]:
        name  = _safe(raw0.iloc[5, col]) if col < raw0.shape[1] else ""
        val   = _safe(raw0.iloc[6, col]) if col < raw0.shape[1] else ""
        delta = _safe(raw0.iloc[7, col]) if col < raw0.shape[1] else ""
        if name:
            kpis.append({"name": name, "val": val, "delta": delta})
    result["kpis"] = kpis
    result["summary_df"] = _parse_simple_sheet(0, 11, 12)

    # ── Advertising (sheet 1) ─────────────────────────────────────────────
    result["adv_df"] = _parse_simple_sheet(1, 2, 3)

    # ── Inventory & Health (sheet 2) ──────────────────────────────────────
    result["inv_df"] = _parse_simple_sheet(2, 2, 3)

    # ── WoW Comparison (sheet 3) ──────────────────────────────────────────
    raw3 = pd.read_excel(xl, sheet_name=3, header=None, dtype=str)
    n_cols = len(raw3.columns)
    wow_cols = []
    cur_metric = None
    for ci in range(n_cols):
        v2 = _safe(raw3.iloc[2, ci])
        v3 = _safe(raw3.iloc[3, ci])
        if v2:
            cur_metric = v2
        if ci < 2:
            wow_cols.append(v3 if v3 else f"col{ci}")
        else:
            sub = v3 if v3 else "val"
            wow_cols.append(f"{cur_metric}|{sub}" if cur_metric else sub)
    rows = []
    for ri in range(4, len(raw3)):
        r = raw3.iloc[ri]
        v0 = _safe(r.iloc[0])
        if not v0 or "TOTALS" in v0.upper():
            continue
        rec = {col: (_safe(r.iloc[j]) if j < len(r) else "") for j, col in enumerate(wow_cols)}
        rows.append(rec)
    result["wow_df"] = pd.DataFrame(rows, columns=wow_cols)
    result["wow_metrics"] = list(dict.fromkeys(c.split("|")[0] for c in wow_cols if "|" in c))
    return result


def _parse_merchanspring_pdf(file):
    """Parse a MerchantSpring weekly report PDF into a dashboard-ready dict.

    Searches across the full concatenated text of all pages instead of assuming
    a fixed page layout. Builds a sections_log with detection results for each
    known section so the UI can report what was and wasn't found.
    """
    import pdfplumber
    import re
    import warnings
    warnings.filterwarnings("ignore")

    with pdfplumber.open(file) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]

    full_text  = "\n".join(pages)
    result     = {}
    slog       = []   # [(icon, section_name, detail)]

    # ── Title & period ────────────────────────────────────────────────────
    title_m = re.search(r'^(WoW .+)$', full_text, re.MULTILINE)
    result["title"] = title_m.group(1).strip() if title_m else "MerchanSpring Report"

    period_m   = re.search(r'Time period:\s*(.+)',      full_text)
    comp_m     = re.search(r'Comparison period:\s*(.+)', full_text)
    period_str = period_m.group(1).strip() if period_m else ""
    comp_str   = comp_m.group(1).strip()   if comp_m   else ""
    result["period"] = f"{period_str}  vs  {comp_str}" if comp_str else period_str
    slog.append(("✅" if period_str else "⚠️", "Header / Period",
                 period_str if period_str else "Not detected — title or period line missing"))

    # ── KPIs ──────────────────────────────────────────────────────────────
    kpis  = []
    rev_m = re.search(r'Revenue ordered\s+Ordered units\s*\n([\$\d,]+)\s+(\d+)', full_text)
    delta_m = re.search(
        r'Revenue ordered\s+Ordered units\s*\n[\$\d,]+\s+\d+\s*\n\w+\s*\n([\+\-]?\d+(?:\.\d+)?%)\s+([\+\-]?\d+(?:\.\d+)?%)',
        full_text
    )
    if rev_m:
        d1 = delta_m.group(1) if delta_m else ""
        d2 = delta_m.group(2) if delta_m else ""
        kpis.append({"name": "Revenue Ordered", "val": rev_m.group(1), "delta": f"vs prior: {d1}"})
        kpis.append({"name": "Ordered Units",   "val": rev_m.group(2), "delta": f"vs prior: {d2}"})

    pv_m = re.search(r'Page views.*?\n([\d,]+)\s+[\d\.]+%\s+([\d,]+)', full_text, re.DOTALL)
    pv_d = re.search(
        r'Page views.*?\n[\d,]+\s+[\d\.]+%\s+[\d,]+\s+[\d\.]+%\s*\n([\+\-]?\d+(?:\.\d+)?%)',
        full_text, re.DOTALL
    )
    if pv_m:
        kpis.append({"name": "Page Views", "val": pv_m.group(1), "delta": f"vs prior: {pv_d.group(1)}" if pv_d else ""})
        kpis.append({"name": "Sessions",   "val": pv_m.group(2), "delta": ""})

    bb_m = re.search(r'Avg Retail\s+Buybox win.*?\n[\$\d,\.]+\s+([\d\.]+%)', full_text, re.DOTALL)
    if bb_m:
        kpis.append({"name": "Buybox Win", "val": bb_m.group(1), "delta": ""})

    result["kpis"] = kpis[:5]
    slog.append(("✅" if kpis else "❌", "KPI Summary",
                 f"{len(kpis)} metrics found" if kpis else "Revenue / Page views blocks not found"))

    # ── Traffic and conversion summary (overall) ──────────────────────────
    tc_sum_m = re.search(
        r'Traffic and conversion summary\b(.*?)(?=Traffic and conversion by product|Top sellers|Worst sellers|P&L|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    traffic_summary = {}
    if tc_sum_m:
        tsb = tc_sum_m.group(1)
        # Each metric: extract value + nearest WoW delta on following lines
        def _tc_metric(text, val_pat, is_ppt=False):
            vm = re.search(val_pat, text, re.IGNORECASE)
            if not vm:
                return "-", "-"
            val = vm.group(1)
            # Look up to 200 chars after the value for a delta (+/-X% or ppt)
            window = text[vm.end(): vm.end() + 200]
            if is_ppt:
                dm = re.search(r'([\+\-]?\d+(?:\.\d+)?\s*ppt)', window, re.IGNORECASE)
            else:
                dm = re.search(r'([\+\-]\d+(?:\.\d+)?%)', window)
            return val, (dm.group(1) if dm else "-")

        tc_kpi_defs = [
            ("Revenue ordered", r'Revenue ordered\s+(-?[\$\d,\.]+)', False),
            ("Ordered units",   r'Ordered units\s+(\d[\d,]*)',        False),
            ("Page views",      r'Page views\s+(\d[\d,]*)',           False),
            ("Conv.",           r'\bConv\.?\s+([\d\.]+%|-)',           True),
            ("Sessions",        r'Sessions\s+(\d[\d,]*)',              False),
            ("S. Conv.",        r'S\.?\s*Conv\.?\s+([\d\.]+%|-)',      True),
            ("Avg Retail",      r'Avg Retail\s+(-?[\$\d,\.]+)',       False),
            ("Buybox win",      r'Buybox win\s+([\d\.]+%|-)',          True),
            ("Mobile S.",       r'Mobile S\.?\s+([\d\.]+%|-)',         False),
            ("B2C sales",       r'B2C sales\s+(-?[\$\d,\.]+)',        False),
        ]
        for key, pat, is_ppt in tc_kpi_defs:
            val, delta = _tc_metric(tsb, pat, is_ppt)
            traffic_summary[key] = val
            traffic_summary[key + " delta"] = delta
    result["traffic_summary"] = traffic_summary
    _ts_found = sum(1 for k, v in traffic_summary.items() if not k.endswith(" delta") and v != "-")
    slog.append(("✅" if _ts_found > 0 else "❌",
                 "Traffic & Conversion Summary",
                 f"{_ts_found} metrics found" if _ts_found > 0 else "Section not found"))

    # ── Helper: walk lines to match (name, data_match, asin, sku) ─────────
    def _product_blocks(text, data_re):
        out, lines, i = [], text.split('\n'), 0
        while i < len(lines):
            ln = lines[i].strip()
            if not ln or ln.startswith('ASIN:') or ln.startswith('http') or ln.startswith('3/'):
                i += 1; continue
            if i + 2 < len(lines):
                dm = data_re.match(lines[i + 1].strip())
                am = re.match(r'ASIN:\s*(\w+)\s*\|\s*SKU:\s*(.+)', lines[i + 2].strip())
                if dm and am:
                    out.append((ln, dm, am.group(1).strip(), am.group(2).strip()))
                    i += 3; continue
            i += 1
        return out

    # ── Top sellers ───────────────────────────────────────────────────────
    top_sec_m = re.search(
        r'(?:Top sellers\b|PRODUCT\s+SALES\s+UNITS SOLD\s+INVENTORY)(.*?)(?=\nWorst sellers|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    top_section = top_sec_m.group(1) if top_sec_m else ""
    top_pat = re.compile(
        r'^(\$[\d,\.]+)\s+([\-\+\d]+%|-)\s+(\d+)\s+([\-\+\d]+%|-)\s+([\d,]+)in stock$'
    )
    top_sellers = []
    for name, dm, asin, sku in _product_blocks(top_section, top_pat):
        try:
            sales_val = float(dm.group(1).replace("$","").replace(",",""))
            inv_val   = int(dm.group(5).replace(",",""))
        except:
            sales_val, inv_val = 0, 0
        top_sellers.append({
            "Product":         name,
            "ASIN":            asin,
            "Total Sales ($)": sales_val,
            "Sales WoW (%)":   dm.group(2),
            "Units Sold":      int(dm.group(3)) if dm.group(3).isdigit() else 0,
            "Units WoW (%)":   dm.group(4),
            "Inventory":       inv_val,
        })
    if top_sellers:
        slog.append(("✅", "Top Sellers",   f"{len(top_sellers)} products parsed"))
    elif top_sec_m:
        slog.append(("⚠️", "Top Sellers",   "Section header found but no product rows matched"))
    else:
        slog.append(("❌", "Top Sellers",   "Section header not found in PDF"))

    # ── Worst sellers ─────────────────────────────────────────────────────
    worst_sec_m = re.search(
        r'Worst sellers.*?LAST SALE\s*\n(.*?)(?=\nAdvertising performance|\nP&L|\nProfit|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    worst_section = worst_sec_m.group(1) if worst_sec_m else ""
    worst_pat = re.compile(r'^(\d+\+?)\s+([\d,]+)in stock$')
    worst_sellers = []
    for name, dm, asin, sku in _product_blocks(worst_section, worst_pat):
        try:
            inv_val = int(dm.group(2).replace(",",""))
        except:
            inv_val = 0
        worst_sellers.append({
            "Product":              name,
            "ASIN":                 asin,
            "Days Since Last Sale": dm.group(1),
            "Inventory":            inv_val,
        })
    if worst_sellers:
        slog.append(("✅", "Worst Sellers", f"{len(worst_sellers)} products parsed"))
    elif worst_sec_m:
        slog.append(("⚠️", "Worst Sellers", "Section header found but no product rows matched"))
    else:
        slog.append(("❌", "Worst Sellers", "Section not found in PDF"))

    # ── P&L / Channel profit ─────────────────────────────────────────────
    # Anchor: "Channel profit" or "Profit and loss" header, or first known line item
    pnl_anchor = re.search(
        r'(?:Channel profit|Profit and loss|Shipped product sales|Net revenue|PROFIT\b)',
        full_text, re.IGNORECASE
    )
    if pnl_anchor:
        _ps = max(0, pnl_anchor.start() - 300)
        pnl_text = full_text[_ps: _ps + 5000]
    else:
        pnl_text = full_text[max(0, len(full_text) - 5000):]

    def _pnl_val(text, label):
        # Handles multi-column rows ($ / % INCOME / $ PER UNIT) — always takes first numeric
        m = re.search(rf'{re.escape(label)}\s+(-?[\$\d,\.]+|-)', text, re.IGNORECASE)
        return m.group(1) if m else "-"

    pnl_items = [
        ("Shipped Product Sales",   "Shipped product sales"),
        ("Sales Tax",                "Sales tax"),
        ("Refunds",                  "Refunds"),
        ("Reimbursements",           "Reimbursements"),
        ("Promotions",               "Promotions"),
        ("Other Income",             "Other income"),
        ("Net Revenue",              "Net revenue"),
        ("Advertising",              "Advertising"),
        ("Selling Fees",             "Selling fees"),
        ("Fulfilment & Shipping",    "Fulfilment and shipping"),
        ("Cancellations & Refunds",  "Cancellations and Refunds"),
        ("Cost of Goods",            "Cost of goods"),
        ("Other Expenses",           "Other expenses"),
        ("Total Expenses",           "Total expenses"),
        ("PROFIT",                   "PROFIT"),
    ]
    pnl_rows, pnl_found = [], 0
    for display, key in pnl_items:
        val = _pnl_val(pnl_text, key)
        if val != "-":
            pnl_found += 1
        # % of Net Revenue: second numeric token on the same row (may be a %)
        pct_m = re.search(
            rf'{re.escape(key)}\s+(?:-?[\$\d,\.]+|-)\s+(-?[\d\.]+%|-)', pnl_text, re.IGNORECASE
        )
        pnl_rows.append({"Item": display, "Amount ($)": val,
                         "% of Net Revenue": pct_m.group(1) if pct_m else "-"})

    result["pnl_df"] = pd.DataFrame(pnl_rows) if pnl_found > 0 else pd.DataFrame()

    profit_pct_m  = re.search(r'Profit\s*%\s+([\d\.]+%)',            pnl_text, re.IGNORECASE)
    orders_m      = re.search(r'\bOrders\s+(\d[\d,]*)',               pnl_text, re.IGNORECASE)
    units_sold_m  = re.search(r'\bUnits\s+(\d[\d,]*)',                pnl_text, re.IGNORECASE)
    tacos_m       = re.search(r'TACOS?\s*%?\s+([\d\.]+%|-)',          pnl_text, re.IGNORECASE)
    payout_m      = re.search(r'ESTIMATED\s+PAYOUT\s+(-?[\$\d,\.]+)',pnl_text, re.IGNORECASE)
    fees_pct_m    = re.search(r'Total\s+fees\s*%\s+([\d\.]+%|-)',     pnl_text, re.IGNORECASE)
    refunds_pct_m = re.search(r'Refunds\s*%\s+([\d\.]+%|-)',          pnl_text, re.IGNORECASE)
    units_ref_m   = re.search(r'Units\s+refunded\s+(\d[\d,]*)',       pnl_text, re.IGNORECASE)
    result["pnl_metrics"] = {
        "Profit %":         profit_pct_m.group(1)  if profit_pct_m  else "-",
        "Orders":           orders_m.group(1)      if orders_m      else "-",
        "Units":            units_sold_m.group(1)  if units_sold_m  else "-",
        "TACoS %":          tacos_m.group(1)       if tacos_m       else "-",
        "Estimated Payout": payout_m.group(1)      if payout_m      else "-",
        "Total Fees %":     fees_pct_m.group(1)    if fees_pct_m    else "-",
        "Refunds %":        refunds_pct_m.group(1) if refunds_pct_m else "-",
        "Units Refunded":   units_ref_m.group(1)   if units_ref_m   else "-",
    }
    slog.append(("✅" if pnl_found > 0 else "❌", "P&L",
                 f"{pnl_found} line items found" if pnl_found > 0 else "P&L / Channel Profit section not found in PDF"))

    # ── Product-level profitability ───────────────────────────────────────
    prod_sec_m = re.search(
        r'(?:Product-level profitability\b.*?\n|PRODUCT\s+SHIPPED PRODUCT SALES.*?\n)(.*?)(?=HEALTH STATUS|ACTIVE PRODUCTS|Seller health|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    prod_section = prod_sec_m.group(1) if prod_sec_m else ""
    prod_pat = re.compile(
        r'^(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(\d+)$'
    )

    def _fval(s):
        try: return float(s.replace("$","").replace(",",""))
        except: return None

    prod_profit = []
    for name, dm, asin, sku in _product_blocks(prod_section, prod_pat):
        prod_profit.append({
            "Product":           name,
            "ASIN":              asin,
            "Shipped Sales ($)": _fval(dm.group(1)),
            "Selling Fees ($)":  _fval(dm.group(2)),
            "Fulfilment ($)":    _fval(dm.group(3)),
            "Profit ($)":        _fval(dm.group(4)),
            "Units":             int(dm.group(5)) if dm.group(5).isdigit() else 0,
        })
    result["prod_profit_df"] = pd.DataFrame(prod_profit) if prod_profit else pd.DataFrame()
    if prod_profit:
        slog.append(("✅", "Product Profitability", f"{len(prod_profit)} products parsed"))
    elif prod_sec_m:
        slog.append(("⚠️", "Product Profitability", "Section header found but no product rows matched"))
    else:
        slog.append(("❌", "Product Profitability", "Section not found in PDF"))

    # ── Seller health / Health status ─────────────────────────────────────
    # Anchor: "HEALTH STATUS" or "Seller health"
    health_block_m = re.search(
        r'(?:HEALTH STATUS|Seller health)\b(.*?)(?=Traffic and conversion|Top sellers|Worst sellers|Advertising|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    _hb = health_block_m.group(1) if health_block_m else full_text

    inactive_m      = re.search(r'Inactive listings\s+Listing enhancements\s*\n(\d+)\s+(\d+)', _hb)
    suppressed_m    = re.search(r'Suppressed listings\s+Return requests\s*\n(\d+)\s+(\d+)',    _hb)
    active_m        = re.search(r'ACTIVE PRODUCTS\s+OVERALL STATUS\s*\n(\d+)',                 _hb)
    winrate_m       = re.search(r'WIN RATE\s*\n(\d+%)',                                        _hb)
    overall_stat_m  = re.search(r'OVERALL STATUS\s*\n?\d*\s*(Good|Warning|Critical)',          _hb, re.IGNORECASE)
    health_status_m = re.search(r'(?:Health Status|HEALTH STATUS)\s*[:\-]?\s*(Good|Warning|Critical)', _hb, re.IGNORECASE)
    health_data = {
        "Health Status":        (health_status_m or overall_stat_m).group(1) if (health_status_m or overall_stat_m) else "-",
        "Inactive Listings":    inactive_m.group(1)   if inactive_m   else "-",
        "Listing Enhancements": inactive_m.group(2)   if inactive_m   else "-",
        "Suppressed Listings":  suppressed_m.group(1) if suppressed_m else "-",
        "Return Requests":      suppressed_m.group(2) if suppressed_m else "-",
        "Active Products":      active_m.group(1)     if active_m     else "-",
        "Overall Status":       overall_stat_m.group(1) if overall_stat_m else "-",
        "Buybox Win Rate":      winrate_m.group(1)    if winrate_m    else "-",
    }
    result["health_data"] = health_data
    health_found = any(v != "-" for v in health_data.values())
    slog.append(("✅" if health_found else "❌", "Health Status",
                 "Catalog health metrics found" if health_found else "Health section not found in PDF"))

    # ── Traffic and conversion by product – Parent ────────────────────────
    tc_parent_m = re.search(
        r'Traffic and conversion by product\s*[-–]?\s*Parent\b(.*?)(?=Traffic and conversion by product\s*[-–]?\s*Child|Cancellations|Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    tc_parent_rows = []
    if tc_parent_m:
        tc_block = tc_parent_m.group(1)
        tc_row_re = re.compile(
            r'^(.+?)\s+([\d,]+)\s+(-?[\$\d,\.]+)\s+(\d+)\s+([\d\.]+%)\s+([\d\.]+%)',
            re.MULTILINE
        )
        for m in tc_row_re.finditer(tc_block):
            tc_parent_rows.append({
                "Product":          m.group(1).strip(),
                "Page Views":       m.group(2),
                "Ordered Revenue":  m.group(3),
                "Ordered Units":    m.group(4),
                "Conversion":       m.group(5),
                "Buybox Win %":     m.group(6),
            })
    result["tc_parent_df"] = pd.DataFrame(tc_parent_rows) if tc_parent_rows else pd.DataFrame()
    result["traffic_by_product_parent_df"] = result["tc_parent_df"]
    slog.append(("✅" if tc_parent_rows else ("⚠️" if tc_parent_m else "❌"),
                 "Traffic by Product - Parent",
                 f"{len(tc_parent_rows)} rows" if tc_parent_rows else ("Section found but no rows matched" if tc_parent_m else "Section not found")))

    # ── Traffic and conversion by product – Child ─────────────────────────
    tc_child_m = re.search(
        r'Traffic and conversion by product\s*[-–]?\s*Child\b(.*?)(?=Cancellations|Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    tc_child_rows = []
    if tc_child_m:
        tc_block = tc_child_m.group(1)
        tc_row_re = re.compile(
            r'^(.+?)\s+([\d,]+)\s+(-?[\$\d,\.]+)\s+(\d+)\s+([\d\.]+%)\s+([\d\.]+%)',
            re.MULTILINE
        )
        for m in tc_row_re.finditer(tc_block):
            tc_child_rows.append({
                "Product":         m.group(1).strip(),
                "Page Views":      m.group(2),
                "Ordered Revenue": m.group(3),
                "Ordered Units":   m.group(4),
                "Conversion":      m.group(5),
                "Buybox Win %":    m.group(6),
            })
    result["tc_child_df"] = pd.DataFrame(tc_child_rows) if tc_child_rows else pd.DataFrame()
    result["traffic_by_product_child_df"] = result["tc_child_df"]
    slog.append(("✅" if tc_child_rows else ("⚠️" if tc_child_m else "❌"),
                 "Traffic by Product - Child",
                 f"{len(tc_child_rows)} rows" if tc_child_rows else ("Section found but no rows matched" if tc_child_m else "Section not found")))

    # ── Cancellations and Refunds Summary ────────────────────────────────
    def _cr_val(text, label):
        m = re.search(rf'{re.escape(label)}\s+(-?[\$\d,\.]+%?|-)', text, re.IGNORECASE)
        return m.group(1) if m else "-"

    cr_m = re.search(
        r'Cancellations and Refunds Summary(.*?)(?=Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    cr_data = {}
    if cr_m:
        cr_block = cr_m.group(1)
        for lbl in ["Gross Sales", "Net Sales", "Cancelled Sales", "Refunded Sales", "Cancel Rate", "Refund Rate"]:
            cr_data[lbl] = _cr_val(cr_block, lbl)
    result["cancellations_data"] = cr_data
    result["cancellations_summary"] = cr_data
    slog.append(("✅" if cr_data else "❌", "Cancellations & Refunds Summary",
                 f"{sum(1 for v in cr_data.values() if v != '-')} metrics found" if cr_data else "Section not found"))

    # ── Sales by category ─────────────────────────────────────────────────
    cat_m = re.search(
        r'Sales by category\b(.*?)(?=Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    cat_rows = []
    if cat_m:
        cat_block = cat_m.group(1)
        cat_re = re.compile(
            r'^(.+?)\s+(-?[\$\d,\.]+)\s+(\d+)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)',
            re.MULTILINE
        )
        for m in cat_re.finditer(cat_block):
            cat_rows.append({
                "Category":       m.group(1).strip(),
                "This Period":    m.group(2),
                "Units":          m.group(3),
                "Av. Unit Price": m.group(4),
                "Av. Order Size": m.group(5),
            })
    result["sales_by_category_df"] = pd.DataFrame(cat_rows) if cat_rows else pd.DataFrame()
    slog.append(("✅" if cat_rows else ("⚠️" if cat_m else "❌"),
                 "Sales by Category",
                 f"{len(cat_rows)} rows" if cat_rows else ("Section found but no rows matched" if cat_m else "Section not found")))

    # ── Sales by country ─────────────────────────────────────────────────
    cty_m = re.search(
        r'Sales by country\b(.*?)(?=Sales by brand|Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    cty_rows = []
    if cty_m:
        cty_block = cty_m.group(1)
        cty_re = re.compile(
            r'^([A-Z][A-Za-z\s]+?)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+(\d+)',
            re.MULTILINE
        )
        for m in cty_re.finditer(cty_block):
            cty_rows.append({
                "Country":           m.group(1).strip(),
                "Comparison Period": m.group(2),
                "This Period":       m.group(3),
                "Units":             m.group(4),
            })
    result["sales_by_country_df"] = pd.DataFrame(cty_rows) if cty_rows else pd.DataFrame()
    slog.append(("✅" if cty_rows else ("⚠️" if cty_m else "❌"),
                 "Sales by Country",
                 f"{len(cty_rows)} rows" if cty_rows else ("Section found but no rows matched" if cty_m else "Section not found")))

    # ── Sales by brand ───────────────────────────────────────────────────
    brand_m = re.search(
        r'Sales by brand\b(.*?)(?=Top products|Review status|Advertising performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    brand_rows = []
    if brand_m:
        brand_block = brand_m.group(1)
        brand_re = re.compile(
            r'^(.+?)\s+(-?[\$\d,\.]+)\s+(\d+)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)',
            re.MULTILINE
        )
        for m in brand_re.finditer(brand_block):
            brand_rows.append({
                "Brand":          m.group(1).strip(),
                "This Period":    m.group(2),
                "Units":          m.group(3),
                "Av. Unit Price": m.group(4),
                "Av. Order Size": m.group(5),
            })
    result["sales_by_brand_df"] = pd.DataFrame(brand_rows) if brand_rows else pd.DataFrame()
    slog.append(("✅" if brand_rows else ("⚠️" if brand_m else "❌"),
                 "Sales by Brand",
                 f"{len(brand_rows)} rows" if brand_rows else ("Section found but no rows matched" if brand_m else "Section not found")))

    # ── Top products by BSR ───────────────────────────────────────────────
    bsr_m = re.search(
        r'Top products by BSR\b(.*?)(?=Review status|Advertising performance|Shipping performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    bsr_rows = []
    if bsr_m:
        bsr_block = bsr_m.group(1)
        bsr_re = re.compile(
            r'^(.+?)\s+#?([\d,]+)\s+(-?[\$\d,\.]+)\s+([\d,]+)',
            re.MULTILINE
        )
        asin_sku_re = re.compile(r'ASIN:\s*(\w+)\s*\|\s*SKU:\s*(.+)')
        lines_bsr = bsr_block.split('\n')
        i = 0
        while i < len(lines_bsr):
            ln = lines_bsr[i].strip()
            if i + 1 < len(lines_bsr):
                dm = bsr_re.match(ln)
                am = asin_sku_re.match(lines_bsr[i + 1].strip()) if dm else None
                if dm and am:
                    bsr_rows.append({
                        "Product":   dm.group(1).strip(),
                        "BSR":       dm.group(2),
                        "Sales":     dm.group(3),
                        "Inventory": dm.group(4),
                        "ASIN":      am.group(1).strip(),
                        "SKU":       am.group(2).strip(),
                    })
                    i += 2; continue
            i += 1
    result["top_bsr_df"] = pd.DataFrame(bsr_rows) if bsr_rows else pd.DataFrame()
    slog.append(("✅" if bsr_rows else ("⚠️" if bsr_m else "❌"),
                 "Top Products by BSR",
                 f"{len(bsr_rows)} rows" if bsr_rows else ("Section found but no rows matched" if bsr_m else "Section not found")))

    # ── Review status ────────────────────────────────────────────────────
    rev_sec_m = re.search(
        r'Review status\b(.*?)(?=Advertising performance|Shipping performance|Buy Box|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    review_data = {}
    if rev_sec_m:
        rb = rev_sec_m.group(1)
        for lbl in ["Total Orders", "Scheduled", "Sent", "Excluded"]:
            m = re.search(rf'{re.escape(lbl)}\s+(\d[\d,]*)', rb, re.IGNORECASE)
            review_data[lbl] = m.group(1) if m else "-"
    result["review_data"] = review_data
    result["review_status"] = review_data
    slog.append(("✅" if any(v != "-" for v in review_data.values()) else "❌",
                 "Review Status",
                 f"{sum(1 for v in review_data.values() if v != '-')} metrics found" if review_data else "Section not found"))

    # ── Advertising performance summary ──────────────────────────────────
    adv_sum_m = re.search(
        r'Advertising performance summary\b(.*?)(?=Advertising performance by campaign|Advertising campaign performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    adv_summary = {}
    if adv_sum_m:
        ab = adv_sum_m.group(1)
        adv_kpi_map = {
            "Total Ad Sales":  r'TOTAL AD SALES\s+(-?[\$\d,\.]+)',
            "Total Spend":     r'TOTAL SPEND\s+(-?[\$\d,\.]+)',
            "ACoS":            r'\bACOS\s+([\d\.]+%|-)',
            "ROAS":            r'\bROAS\s+([\d\.]+|-)',
            "TACoS":           r'\bTACOS\s+([\d\.]+%|-)',
            "TROAS":           r'\bTROAS\s+([\d\.]+|-)',
            "Impressions":     r'Impressions\s+([\d,]+)',
            "Clicks":          r'Clicks\s+([\d,]+)',
            "Orders":          r'Orders\s+(\d+)',
            "Units":           r'\bUnits\s+(\d+)',
            "CPC":             r'\bCPC\s+(-?[\$\d,\.]+)',
            "Conv":            r'\bCONV\s+([\d\.]+%|-)',
            "NTB Units":       r'\bNTB\s+Units\s+(\d[\d,]*)',
        }
        for key, pat in adv_kpi_map.items():
            m = re.search(pat, ab, re.IGNORECASE)
            adv_summary[key] = m.group(1) if m else "-"
    result["adv_summary"] = adv_summary
    slog.append(("✅" if any(v != "-" for v in adv_summary.values()) else "❌",
                 "Advertising Performance Summary",
                 f"{sum(1 for v in adv_summary.values() if v != '-')} metrics found" if adv_summary else "Section not found"))

    # ── Advertising performance by campaign type ──────────────────────────
    adv_type_m = re.search(
        r'Advertising performance by campaign type\b(.*?)(?=Advertising campaign performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    adv_type_rows = []
    if adv_type_m:
        atb = adv_type_m.group(1)
        for ctype in ["Sponsored Products", "Sponsored Brands", "Sponsored Display"]:
            # Format A: "Sponsored Products $10,776 (92.31%) ACOS: 45.8%"
            # Format B: "Sponsored Products $10,776 45.8%"
            m = re.search(
                rf'{re.escape(ctype)}\s+(?:Sales:?\s*)?(-?[\$\d,\.]+)\s*(?:\(([\d\.]+%|-)\))?\s*(?:ACOS:?\s*)?([\d\.]+%|-)',
                atb, re.IGNORECASE
            )
            if m:
                adv_type_rows.append({
                    "Campaign Type": ctype,
                    "Sales":         m.group(1),
                    "Sales pct":     m.group(2) if m.group(2) else "-",
                    "ACOS":          m.group(3),
                })
    result["adv_by_type_df"] = pd.DataFrame(adv_type_rows) if adv_type_rows else pd.DataFrame()
    slog.append(("✅" if adv_type_rows else ("⚠️" if adv_type_m else "❌"),
                 "Advertising by Campaign Type",
                 f"{len(adv_type_rows)} types found" if adv_type_rows else ("Section found but no types matched" if adv_type_m else "Section not found")))

    # ── Advertising campaign performance ─────────────────────────────────
    adv_camp_m = re.search(
        r'Advertising campaign performance\b(.*?)(?=Top performing product ads|Top performing keywords|Shipping performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    campaigns_rows = []
    if adv_camp_m:
        acb = adv_camp_m.group(1)
        camp_re = re.compile(
            r'^(.+?)\s+(enabled|paused|archived)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)',
            re.MULTILINE | re.IGNORECASE
        )
        for m in camp_re.finditer(acb):
            campaigns_rows.append({
                "Name":     m.group(1).strip(),
                "Status":   m.group(2),
                "Ad Sales": m.group(3),
                "Spend":    m.group(4),
                "ACoS":     m.group(5),
            })
    result["campaigns_df"] = pd.DataFrame(campaigns_rows) if campaigns_rows else pd.DataFrame()
    slog.append(("✅" if campaigns_rows else ("⚠️" if adv_camp_m else "❌"),
                 "Advertising Campaign Performance",
                 f"{len(campaigns_rows)} campaigns parsed" if campaigns_rows else ("Section found but no rows matched" if adv_camp_m else "Section not found")))

    # ── Top performing product ads ────────────────────────────────────────
    prod_ads_m = re.search(
        r'Top performing product ads\b(.*?)(?=Top performing keywords|Shipping performance|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    prod_ads_rows = []
    if prod_ads_m:
        pab = prod_ads_m.group(1)
        # Try extended pattern with ASIN (10-char alphanumeric) column
        pa_re_asin = re.compile(
            r'^(.+?)\s+(.+?)\s+(.+?)\s+([A-Z0-9]{10})\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)',
            re.MULTILINE
        )
        pa_re_base = re.compile(
            r'^(.+?)\s+(.+?)\s+(.+?)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)',
            re.MULTILINE
        )
        for m in pa_re_asin.finditer(pab):
            prod_ads_rows.append({
                "Campaign":  m.group(1).strip(),
                "Ad Group":  m.group(2).strip(),
                "Product":   m.group(3).strip(),
                "ASIN":      m.group(4),
                "Ad Sales":  m.group(5),
                "Spend":     m.group(6),
                "ACoS":      m.group(7),
            })
        if not prod_ads_rows:
            for m in pa_re_base.finditer(pab):
                prod_ads_rows.append({
                    "Campaign":  m.group(1).strip(),
                    "Ad Group":  m.group(2).strip(),
                    "Product":   m.group(3).strip(),
                    "ASIN":      "-",
                    "Ad Sales":  m.group(4),
                    "Spend":     m.group(5),
                    "ACoS":      m.group(6),
                })
    result["top_product_ads_df"] = pd.DataFrame(prod_ads_rows) if prod_ads_rows else pd.DataFrame()
    slog.append(("✅" if prod_ads_rows else ("⚠️" if prod_ads_m else "❌"),
                 "Top Performing Product Ads",
                 f"{len(prod_ads_rows)} rows" if prod_ads_rows else ("Section found but no rows matched" if prod_ads_m else "Section not found")))

    # ── Top performing keywords ───────────────────────────────────────────
    top_kw_m = re.search(
        r'Top performing keywords\b(.*?)(?=Shipping performance|Buy Box|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    top_kw_rows = []
    if top_kw_m:
        tkb = top_kw_m.group(1)
        # Try extended pattern with Match Type column (Broad/Phrase/Exact)
        kw_re_mt = re.compile(
            r'^(.+?)\s+(.+?)\s+(.+?)\s+(Broad|Phrase|Exact)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)',
            re.MULTILINE | re.IGNORECASE
        )
        kw_re_base = re.compile(
            r'^(.+?)\s+(.+?)\s+(.+?)\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)',
            re.MULTILINE
        )
        for m in kw_re_mt.finditer(tkb):
            top_kw_rows.append({
                "Campaign":   m.group(1).strip(),
                "Ad Group":   m.group(2).strip(),
                "Keyword":    m.group(3).strip(),
                "Match Type": m.group(4),
                "Ad Sales":   m.group(5),
                "Spend":      m.group(6),
                "ACoS":       m.group(7),
            })
        if not top_kw_rows:
            for m in kw_re_base.finditer(tkb):
                top_kw_rows.append({
                    "Campaign":   m.group(1).strip(),
                    "Ad Group":   m.group(2).strip(),
                    "Keyword":    m.group(3).strip(),
                    "Match Type": "-",
                    "Ad Sales":   m.group(4),
                    "Spend":      m.group(5),
                    "ACoS":       m.group(6),
                })
    result["top_keywords_df"] = pd.DataFrame(top_kw_rows) if top_kw_rows else pd.DataFrame()
    slog.append(("✅" if top_kw_rows else ("⚠️" if top_kw_m else "❌"),
                 "Top Performing Keywords",
                 f"{len(top_kw_rows)} rows" if top_kw_rows else ("Section found but no rows matched" if top_kw_m else "Section not found")))

    # ── Shipping performance ──────────────────────────────────────────────
    ship_m = re.search(
        r'Shipping performance\b(.*?)(?=Buy Box|Review status|\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    shipping_data = {}
    if ship_m:
        sb = ship_m.group(1)
        for lbl in ["Late shipment rate", "Invoice defect rate", "On time delivery rate",
                    "Valid order tracking rate", "Cancellation rate"]:
            m = re.search(rf'{re.escape(lbl)}\s+([\d\.]+%|-)', sb, re.IGNORECASE)
            shipping_data[lbl] = m.group(1) if m else "-"
    result["shipping_data"] = shipping_data
    result["shipping_performance"] = shipping_data
    slog.append(("✅" if any(v != "-" for v in shipping_data.values()) else "❌",
                 "Shipping Performance",
                 f"{sum(1 for v in shipping_data.values() if v != '-')} metrics found" if shipping_data else "Section not found"))

    # ── Buy Box summary snapshot ──────────────────────────────────────────
    bb_snap_m = re.search(
        r'Buy Box summary snapshot\b(.*?)(?=\Z)',
        full_text, re.DOTALL | re.IGNORECASE
    )
    buybox_data = {}
    if bb_snap_m:
        bbs = bb_snap_m.group(1)
        bb_map = {
            "Active Products": r'ACTIVE PRODUCTS\s+(\d+)',
            "Losers":          r'LOSERS\s+(\d+)',
            "Win Rate":        r'WIN RATE\s+([\d\.]+%)',
            "Overall Status":  r'OVERALL STATUS\s+(\w+)',
        }
        for key, pat in bb_map.items():
            m = re.search(pat, bbs, re.IGNORECASE)
            buybox_data[key] = m.group(1) if m else "-"
    result["buybox_snapshot"] = buybox_data
    result["buybox_summary"] = buybox_data
    slog.append(("✅" if any(v != "-" for v in buybox_data.values()) else "❌",
                 "Buy Box Summary",
                 f"{sum(1 for v in buybox_data.values() if v != '-')} metrics found" if buybox_data else "Section not found"))

    # ── DataFrames for dashboard ──────────────────────────────────────────
    result["summary_df"] = pd.DataFrame(top_sellers) if top_sellers else pd.DataFrame()

    inv_rows = []
    for ts in top_sellers:
        inv = ts.get("Inventory", 0) or 0
        inv_rows.append({
            "Product":              ts["Product"],
            "ASIN":                 ts["ASIN"],
            "Total Sales ($)":      ts.get("Total Sales ($)", 0),
            "Units Sold":           ts.get("Units Sold", 0),
            "Inventory":            inv,
            "Days Since Last Sale": "< 7",
            "Stock Status":         "🟢 In Stock" if inv > 0 else "🔴 Out of Stock",
            "Segment":              "Top Seller",
        })
    for ws_row in worst_sellers:
        inv  = ws_row.get("Inventory", 0) or 0
        days = ws_row.get("Days Since Last Sale", "")
        inv_rows.append({
            "Product":              ws_row["Product"],
            "ASIN":                 ws_row["ASIN"],
            "Total Sales ($)":      "",
            "Units Sold":           "",
            "Inventory":            inv,
            "Days Since Last Sale": days,
            "Stock Status":         "🔴 No Stock" if inv == 0 else "🟡 Slow Mover",
            "Segment":              "Worst Seller",
        })
    result["inv_df"]       = pd.DataFrame(inv_rows) if inv_rows else pd.DataFrame()

    # ── Advertising Products (adv_df) ────────────────────────────────────
    # Anchor: "Products" section within the advertising portion of the PDF.
    # Search from adv summary position onward so we don't match unrelated "Products" headers.
    _adv_search_start = adv_sum_m.start() if adv_sum_m else 0
    adv_prod_sec_m = re.search(
        r'(?:^|\n)Products?\s*\n(.*?)(?=Advertising performance by campaign|Advertising campaign performance|Top performing product|Shipping performance|Buy Box|Review status|\Z)',
        full_text[_adv_search_start:], re.DOTALL | re.IGNORECASE
    )
    adv_prod_rows = []
    if adv_prod_sec_m:
        apb = adv_prod_sec_m.group(1)
        # Format A: product_blocks pattern (name / data line / ASIN: | SKU:)
        ap_block_pat = re.compile(
            r'^(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)\s+([\d\.]+%|-)\s*$'
        )
        for name, dm, asin, sku in _product_blocks(apb, ap_block_pat):
            adv_prod_rows.append({
                "Product":  name,
                "ASIN":     asin,
                "Ad Sales": dm.group(1),
                "Spend":    dm.group(2),
                "ACoS":     dm.group(3),
                "Conv":     dm.group(4),
            })
        # Format B: inline row with ASIN column (10-char alphanumeric)
        if not adv_prod_rows:
            ap_inline_re = re.compile(
                r'^(.+?)\s+([A-Z0-9]{10})\s+(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)\s+([\d\.]+%|-)',
                re.MULTILINE
            )
            for m in ap_inline_re.finditer(apb):
                adv_prod_rows.append({
                    "Product":  m.group(1).strip(),
                    "ASIN":     m.group(2),
                    "Ad Sales": m.group(3),
                    "Spend":    m.group(4),
                    "ACoS":     m.group(5),
                    "Conv":     m.group(6),
                })
    result["adv_df"] = pd.DataFrame(adv_prod_rows) if adv_prod_rows else pd.DataFrame()
    slog.append(("✅" if adv_prod_rows else ("⚠️" if adv_prod_sec_m else "❌"),
                 "Advertising Products",
                 f"{len(adv_prod_rows)} products parsed" if adv_prod_rows
                 else ("Section found but no rows matched" if adv_prod_sec_m
                       else "Section not found")))

    result["wow_df"]       = pd.DataFrame()
    result["wow_metrics"]  = []
    result["sections_log"] = slog
    return result


def _build_ms_pdf_excel(data, client_name=""):
    """Generate a 4-sheet Excel matching NorseTradesman structure from parsed MerchantSpring PDF."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    import io

    wb = Workbook()
    wb.remove(wb.active)

    NAVY  = "0D1B3E"; DGRAY = "2D3748"; LGRAY = "F7FAFC"
    GRN_L = "C6EFCE"; GRN_D = "276221"
    YEL_L = "FFEB9C"; YEL_D = "9C5700"
    RED_L = "FFC7CE"; RED_D = "9C0006"
    ORG_L = "FFE0B2"; ORG_D = "BF360C"
    WHITE = "FFFFFF"

    def _fill(h):  return PatternFill("solid", fgColor=h)
    def _font(bold=False, color="000000", size=9, name="Arial"):
        return Font(bold=bold, color=color, size=size, name=name)
    def _bd():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)
    def _al(h="center", wrap=False):
        return Alignment(horizontal=h, vertical="center", wrap_text=wrap)
    def _num(v):
        try: return float(str(v).replace("$","").replace(",",""))
        except: return None

    def _title_block(ws, title_txt, period_txt, n):
        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 18
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
        c = ws.cell(row=1, column=1, value=title_txt)
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 13); c.alignment = _al("center")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
        c = ws.cell(row=2, column=1, value=period_txt)
        c.fill = _fill(DGRAY); c.font = _font(False, WHITE, 10); c.alignment = _al("center")

    def _hdr(ws, rn, vals, start_col=1):
        ws.row_dimensions[rn].height = 16
        for i, v in enumerate(vals):
            c = ws.cell(row=rn, column=start_col + i, value=v)
            c.fill = _fill(NAVY); c.font = _font(True, WHITE, 9)
            c.border = _bd(); c.alignment = _al("center")

    def _cell(ws, rn, cn, val, bg=WHITE, fg="000000", bold=False, fmt=None, left=False):
        c = ws.cell(row=rn, column=cn, value=val)
        c.fill = _fill(bg); c.font = _font(bold, fg)
        c.border = _bd(); c.alignment = _al("left" if left else "center")
        if fmt: c.number_format = fmt

    def _no_data_row(ws, rn, n, msg="No data available in this report"):
        ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=n)
        c = ws.cell(row=rn, column=1, value=msg)
        c.fill = _fill(YEL_L); c.font = _font(False, YEL_D, 9)
        c.alignment = _al("left"); c.border = _bd()
        ws.row_dimensions[rn].height = 16
        return rn + 1

    def _write_df(ws, df, start_row, col_fmts=None):
        col_fmts = col_fmts or {}
        for ri, row in df.iterrows():
            rn  = start_row + ri
            bg  = WHITE if ri % 2 == 0 else LGRAY
            ws.row_dimensions[rn].height = 15
            for ci, col in enumerate(df.columns):
                val = row[col]
                n   = _num(val)
                fmt = col_fmts.get(col)
                if fmt is None:
                    cl = col.lower()
                    if "($)" in col:        fmt = "$#,##0.00"
                    elif "(%)" in col:      fmt = "0.00"
                    elif "inventory" in cl: fmt = "#,##0"
                    elif "units" in cl:     fmt = "#,##0"
                display = n if (n is not None and fmt and fmt != "@") else (val if val != "" else "")
                _cell(ws, rn, ci + 1, display, bg=bg, fmt=fmt, left=(ci < 2))

    def _parse_wow_pct(s):
        try: return float(str(s).replace("%","").replace("+","").strip())
        except: return None

    def _calc_prior(this_week_val, wow_pct_str):
        pct = _parse_wow_pct(wow_pct_str)
        if pct is None: return "-"
        divisor = 1 + pct / 100
        if divisor == 0: return "-"
        try:
            tw = float(str(this_week_val).replace("$","").replace(",","").strip())
            if tw == 0: return "-"
            return tw / divisor
        except: return "-"

    title  = client_name or data.get("title", "MerchanSpring Report")
    period = data.get("period", "")

    # ── Sheet 1: "📊 Summary" ─────────────────────────────────────────────
    ws1 = wb.create_sheet("📊 Summary")
    ws1.sheet_view.showGridLines = False
    kpis  = data.get("kpis", [])
    n_kpi = max(len(kpis) * 2, 10)
    _title_block(ws1, title, period, n_kpi)

    for ki, kpi in enumerate(kpis[:5]):
        col = ki * 2 + 1
        if col + 1 <= n_kpi:
            ws1.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
        c = ws1.cell(row=4, column=col, value=kpi["name"])
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 9); c.alignment = _al("center")
        ws1.row_dimensions[4].height = 14
        if col + 1 <= n_kpi:
            ws1.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
        c = ws1.cell(row=5, column=col, value=kpi["val"])
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 14); c.alignment = _al("center")
        ws1.row_dimensions[5].height = 24
        if col + 1 <= n_kpi:
            ws1.merge_cells(start_row=6, start_column=col, end_row=6, end_column=col + 1)
        dt  = kpi.get("delta", "")
        db  = GRN_L if "+" in dt else (RED_L if "-" in dt else "E2E8F0")
        df_ = GRN_D if "+" in dt else (RED_D if "-" in dt else "000000")
        c = ws1.cell(row=6, column=col, value=dt)
        c.fill = _fill(db); c.font = _font(False, df_, 9); c.alignment = _al("center")
        ws1.row_dimensions[6].height = 14

    sum_df = data.get("summary_df", pd.DataFrame())
    if not sum_df.empty:
        _hdr(ws1, 8, list(sum_df.columns))
        _write_df(ws1, sum_df.reset_index(drop=True), 9)
        for i, col in enumerate(sum_df.columns):
            ws1.column_dimensions[get_column_letter(i+1)].width = 42 if col == "Product" else (14 if col == "ASIN" else 13)
    else:
        _no_data_row(ws1, 8, n_kpi)
    ws1.freeze_panes = "C9"

    # ── Sheet 2: "📣 Advertising" ─────────────────────────────────────────
    ws2 = wb.create_sheet("📣 Advertising")
    ws2.sheet_view.showGridLines = False
    ADV_COLS = ["Product", "ASIN", "Impressions", "CTR (%)", "CPC ($)",
                "Ad Spend ($)", "Ad Sales ($)", "ACoS (%)", "Conv. Rate (%)", "Ad Efficiency"]
    n2 = len(ADV_COLS)
    _title_block(ws2, title, period, n2)

    # Banner rows 3–6
    banner_rows = [
        (3, "⚠️  Advertising no conectado en MerchantSpring",                              ORG_L, ORG_D, True,  10, 20),
        (4, "Para ver datos de advertising, conectá tu cuenta de Amazon Ads en MerchantSpring:", YEL_L, YEL_D, False, 9,  16),
        (5, "MerchantSpring → Settings → Integrations → Amazon Advertising",               YEL_L, YEL_D, False, 9,  16),
        (6, "Una vez conectado, los datos aparecerán automáticamente en el próximo reporte.", YEL_L, YEL_D, False, 9,  16),
    ]
    for rn, text, bg, fg, bold, sz, ht in banner_rows:
        ws2.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=n2)
        c = ws2.cell(row=rn, column=1, value=text)
        c.fill = _fill(bg); c.font = _font(bold, fg, sz)
        c.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
        c.border = _bd()
        ws2.row_dimensions[rn].height = ht

    ws2.row_dimensions[7].height = 8   # spacer
    _hdr(ws2, 8, ADV_COLS)
    for i, col in enumerate(ADV_COLS):
        ws2.column_dimensions[get_column_letter(i+1)].width = 42 if col == "Product" else (14 if col == "ASIN" else 13)
    ws2.freeze_panes = "C9"

    # ── Sheet 3: "📦 Inventory & Health" ─────────────────────────────────
    ws3 = wb.create_sheet("📦 Inventory & Health")
    ws3.sheet_view.showGridLines = False
    inv_df  = data.get("inv_df",         pd.DataFrame())
    pnl_df  = data.get("pnl_df",         pd.DataFrame())
    pnl_m   = data.get("pnl_metrics",    {})
    pp_df   = data.get("prod_profit_df", pd.DataFrame())
    health  = data.get("health_data",    {})
    n3 = max(len(inv_df.columns) if not inv_df.empty else 8, 8)
    _title_block(ws3, title, period, n3)

    # Section title helper
    def _sec_title(ws, rn, text, n):
        ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=n)
        c = ws.cell(row=rn, column=1, value=text)
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 10)
        c.alignment = _al("left"); c.border = _bd()
        ws.row_dimensions[rn].height = 18

    # ── Section 1: Inventario ─────────────────────────────────────────────
    _sec_title(ws3, 3, "Inventario de Productos", n3)
    cur = 4
    if inv_df.empty:
        cur = _no_data_row(ws3, cur, n3)
    if not inv_df.empty:
        idf3 = inv_df.reset_index(drop=True)
        _hdr(ws3, cur, list(idf3.columns)); cur += 1
        _write_df(ws3, idf3, cur)
        # Stock Status coloring
        sc_ci = list(idf3.columns).index("Stock Status") + 1 if "Stock Status" in idf3.columns else None
        if sc_ci:
            for ri in range(len(idf3)):
                vl = str(idf3.iloc[ri]["Stock Status"]).lower()
                if "in stock"  in vl: bg3, fg3 = GRN_L, GRN_D
                elif "slow"    in vl: bg3, fg3 = YEL_L, YEL_D
                elif "no stock" in vl or "out" in vl: bg3, fg3 = RED_L, RED_D
                elif "partial" in vl: bg3, fg3 = ORG_L, ORG_D
                else: bg3, fg3 = None, None
                if bg3:
                    c3 = ws3.cell(row=cur + ri, column=sc_ci)
                    c3.fill = _fill(bg3); c3.font = _font(color=fg3, size=9)
        cur += len(idf3)
    ws3.row_dimensions[cur].height = 8; cur += 1  # spacer

    # ── Section 2: P&L ────────────────────────────────────────────────────
    _sec_title(ws3, cur, "P&L — Estado de Resultados", n3); cur += 1
    # Metric cards (4 pairs)
    metric_items = [
        ("Profit %", pnl_m.get("Profit %","-")),
        ("Orders",   pnl_m.get("Orders","-")),
        ("Units",    pnl_m.get("Units","-")),
        ("TACoS %",  pnl_m.get("TACoS %","-")),
    ]
    for mi, (mk, mv) in enumerate(metric_items):
        col_s = mi * 2 + 1; col_e = col_s + 1
        if col_e <= n3:
            ws3.merge_cells(start_row=cur, start_column=col_s, end_row=cur, end_column=col_e)
        c = ws3.cell(row=cur, column=col_s, value=mk)
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 9); c.alignment = _al("center")
        if col_e <= n3:
            ws3.merge_cells(start_row=cur+1, start_column=col_s, end_row=cur+1, end_column=col_e)
        c2 = ws3.cell(row=cur+1, column=col_s, value=mv)
        c2.fill = _fill(NAVY); c2.font = _font(True, WHITE, 12); c2.alignment = _al("center")
    ws3.row_dimensions[cur].height = 14
    ws3.row_dimensions[cur+1].height = 22
    cur += 2
    ws3.row_dimensions[cur].height = 6; cur += 1  # spacer

    if pnl_df.empty:
        cur = _no_data_row(ws3, cur, n3)
    if not pnl_df.empty:
        _hdr(ws3, cur, list(pnl_df.columns)); cur += 1
        pnl_data = pnl_df.reset_index(drop=True)
        for ri in range(len(pnl_data)):
            rn = cur + ri
            item = str(pnl_data.iloc[ri]["Item"])
            ws3.row_dimensions[rn].height = 15
            if item in ("Net Revenue", "PROFIT"):
                bg3, fg3, bold3 = NAVY, WHITE, True
            elif item == "Total Expenses":
                bg3, fg3, bold3 = DGRAY, WHITE, True
            else:
                bg3, fg3, bold3 = (WHITE if ri % 2 == 0 else LGRAY), "000000", False
            for ci, col in enumerate(pnl_df.columns):
                _cell(ws3, rn, ci+1, pnl_data.iloc[ri][col], bg=bg3, fg=fg3, bold=bold3, left=(ci==0))
        cur += len(pnl_data)
    ws3.row_dimensions[cur].height = 8; cur += 1  # spacer

    # ── Section 3: Product Profitability ──────────────────────────────────
    if not pp_df.empty:
        _sec_title(ws3, cur, "Product-Level Profitability", n3); cur += 1
        pp3 = pp_df.reset_index(drop=True)
        _hdr(ws3, cur, list(pp3.columns)); cur += 1
        _write_df(ws3, pp3, cur)
        cur += len(pp3)
        ws3.row_dimensions[cur].height = 8; cur += 1  # spacer

    # ── Section 4: Health Status ──────────────────────────────────────────
    _sec_title(ws3, cur, "Salud del Catálogo", n3); cur += 1
    health_items_list = [
        ("Active Products",     health.get("Active Products",     "-")),
        ("Buybox Win Rate",      health.get("Buybox Win Rate",      "-")),
        ("Inactive Listings",    health.get("Inactive Listings",    "-")),
        ("Listing Enhancements", health.get("Listing Enhancements", "-")),
        ("Suppressed Listings",  health.get("Suppressed Listings",  "-")),
        ("Return Requests",      health.get("Return Requests",      "-")),
    ]
    for hi, (hk, hv) in enumerate(health_items_list):
        rn = cur + hi
        ws3.row_dimensions[rn].height = 18
        row_bg = LGRAY if hi % 2 == 0 else WHITE
        ws3.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=2)
        c1 = ws3.cell(row=rn, column=1, value=hk)
        c1.fill = _fill(DGRAY); c1.font = _font(True, WHITE, 10)
        c1.alignment = _al("left"); c1.border = _bd()
        ws3.merge_cells(start_row=rn, start_column=3, end_row=rn, end_column=4)
        c2 = ws3.cell(row=rn, column=3, value=hv)
        c2.fill = _fill(row_bg); c2.font = _font(True, "000000", 12)
        c2.alignment = _al("center"); c2.border = _bd()

    # Column widths for sheet 3
    for i, col in enumerate(inv_df.columns if not inv_df.empty else []):
        ws3.column_dimensions[get_column_letter(i+1)].width = 42 if col == "Product" else (14 if col == "ASIN" else 14)
    ws3.freeze_panes = "C5"

    # ── Sheet 4: "📈 WoW Comparison" ──────────────────────────────────────
    ws4 = wb.create_sheet("📈 WoW Comparison")
    ws4.sheet_view.showGridLines = False

    WOW_GROUPS = [
        ("SALES",         ["This Week", "Prior Week", "\u0394 %"], False),
        ("UNITS",         ["This Week", "Prior Week", "\u0394 %"], False),
        ("SESSIONS",      ["This Week", "Prior Week", "\u0394 %"], False),
        ("CVR",           ["This Week", "Prior Week", "\u0394 %"], False),
        ("TACoS",         ["This Week", "Prior Week", "\u0394 %"], True),
        ("AD SALES",      ["This Week", "Prior Week", "\u0394 %"], True),
        ("ORGANIC SALES", ["This Week", "Prior Week", "\u0394 %"], False),
        ("AD SPEND",      ["This Week", "Prior Week", "\u0394 %"], True),
        ("PROFIT",        ["\u0394 %"],                            False),
    ]
    total_wow_cols = 2 + sum(len(subs) for _, subs, _ in WOW_GROUPS)  # 27
    _title_block(ws4, title, period, total_wow_cols)

    # Row 3: fixed labels for Product/ASIN + group headers
    ws4.row_dimensions[3].height = 16
    for ci_fix, lbl in ((1, "Product"), (2, "ASIN")):
        c = ws4.cell(row=3, column=ci_fix, value=lbl)
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 9)
        c.alignment = _al("center"); c.border = _bd()
    ci = 3
    for grp_name, subs, is_orange in WOW_GROUPS:
        span = len(subs)
        grp_fill = ORG_L if is_orange else DGRAY
        grp_font_color = ORG_D if is_orange else WHITE
        if span > 1:
            ws4.merge_cells(start_row=3, start_column=ci, end_row=3, end_column=ci + span - 1)
        c = ws4.cell(row=3, column=ci, value=grp_name)
        c.fill = _fill(grp_fill); c.font = _font(True, grp_font_color, 9)
        c.alignment = _al("center"); c.border = _bd()
        ci += span

    # Row 4: sub-headers
    sub_hdr_vals = ["Product", "ASIN"]
    for _, subs, _ in WOW_GROUPS:
        sub_hdr_vals.extend(subs)
    _hdr(ws4, 4, sub_hdr_vals)

    # Rows 5+: product data
    sum4 = data.get("summary_df", pd.DataFrame())
    if not sum4.empty:
        sum4 = sum4.reset_index(drop=True)
        for ri in range(len(sum4)):
            rn  = 5 + ri
            row = sum4.iloc[ri]
            ws4.row_dimensions[rn].height = 15
            row_bg = WHITE if ri % 2 == 0 else LGRAY

            sales_tw   = row.get("Total Sales ($)", 0)
            sales_wow  = row.get("Sales WoW (%)", "-")
            sales_pw   = _calc_prior(sales_tw, sales_wow)
            sales_d    = _parse_wow_pct(sales_wow)

            units_tw   = row.get("Units Sold", 0)
            units_wow  = row.get("Units WoW (%)", "-")
            units_pw   = _calc_prior(units_tw, units_wow)
            units_d    = _parse_wow_pct(units_wow)

            def _dc(cn, val, fmt=None, delta=False, left=False):
                if delta and isinstance(val, float):
                    if val > 5:   bg4, fg4 = GRN_L, GRN_D
                    elif val < -5: bg4, fg4 = RED_L, RED_D
                    else:          bg4, fg4 = YEL_L, YEL_D
                else:
                    bg4, fg4 = row_bg, "000000"
                _cell(ws4, rn, cn, val, bg=bg4, fg=fg4, fmt=fmt, left=left or (cn <= 2))

            _dc(1, str(row.get("Product", "")), left=True)
            _dc(2, str(row.get("ASIN", "")),    left=True)
            # SALES
            _dc(3,  sales_tw,  "$#,##0.00")
            _dc(4,  sales_pw,  "$#,##0.00" if isinstance(sales_pw, float) else None)
            _dc(5,  sales_d,   "0.00", delta=True)
            # UNITS
            _dc(6,  units_tw,  "#,##0")
            _dc(7,  units_pw,  "#,##0" if isinstance(units_pw, float) else None)
            _dc(8,  units_d,   "0.00", delta=True)
            # SESSIONS (not available)
            for cn in (9, 10, 11):  _dc(cn, "-")
            # CVR (not available)
            for cn in (12, 13, 14): _dc(cn, "-")
            # TACoS (not connected)
            for cn in (15, 16, 17): _dc(cn, "\u2014")
            # AD SALES (not connected)
            for cn in (18, 19, 20): _dc(cn, "\u2014")
            # ORGANIC SALES (proxy = Total Sales, no ads)
            _dc(21, sales_tw,  "$#,##0.00")
            _dc(22, "-")
            _dc(23, sales_d,   "0.00", delta=True)
            # AD SPEND (not connected)
            for cn in (24, 25, 26): _dc(cn, "\u2014")
            # PROFIT Δ %
            _dc(27, "-")

    # Note row below data
    note_rn = 5 + (len(sum4) if not sum4.empty else 0) + 1
    ws4.merge_cells(start_row=note_rn, start_column=1, end_row=note_rn, end_column=total_wow_cols)
    nc = ws4.cell(row=note_rn, column=1,
                  value="* TACoS, Ad Sales y Ad Spend no disponibles \u2014 conectar Amazon Ads en MerchantSpring: Settings \u2192 Integrations")
    nc.fill = _fill(YEL_L); nc.font = _font(False, YEL_D, 8)
    nc.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws4.row_dimensions[note_rn].height = 20

    # Column widths
    ws4.column_dimensions["A"].width = 42
    ws4.column_dimensions["B"].width = 14
    for ci_w in range(3, total_wow_cols + 1):
        ws4.column_dimensions[get_column_letter(ci_w)].width = 11
    ws4.freeze_panes = "C5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _build_merchanspring_excel(data, client_name=""):
    """Generate professional MerchanSpring-style Excel with 4 sheets."""
    from openpyxl import Workbook
    from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
    from openpyxl.utils import get_column_letter
    import io

    wb = Workbook()
    wb.remove(wb.active)

    # Palette
    NAVY  = "0D1B3E"; DGRAY = "2D3748"; LGRAY = "F7FAFC"
    GRN_L = "C6EFCE"; GRN_D = "276221"
    YEL_L = "FFEB9C"; YEL_D = "9C5700"
    RED_L = "FFC7CE"; RED_D = "9C0006"
    ORG_L = "FFE0B2"; ORG_D = "BF360C"
    WHITE = "FFFFFF"

    def _fill(h): return PatternFill("solid", fgColor=h)
    def _font(bold=False, color="000000", size=9, name="Arial"):
        return Font(bold=bold, color=color, size=size, name=name)
    def _bd():
        s = Side(style="thin", color="CCCCCC")
        return Border(left=s, right=s, top=s, bottom=s)
    def _al(h="center", wrap=False):
        return Alignment(horizontal=h, vertical="center", wrap_text=wrap)

    def _title_block(ws, title_txt, period_txt, n):
        ws.row_dimensions[1].height = 28
        ws.row_dimensions[2].height = 18
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=n)
        c = ws.cell(row=1, column=1, value=title_txt)
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 13); c.alignment = _al("center")
        ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=n)
        c = ws.cell(row=2, column=1, value=period_txt)
        c.fill = _fill(DGRAY); c.font = _font(False, WHITE, 10); c.alignment = _al("center")

    def _hdr_row(ws, rn, vals, start_col=1):
        ws.row_dimensions[rn].height = 16
        for i, v in enumerate(vals):
            c = ws.cell(row=rn, column=start_col + i, value=v)
            c.fill = _fill(NAVY); c.font = _font(True, WHITE, 9)
            c.border = _bd(); c.alignment = _al("center")

    def _dc(ws, rn, cn, val, bg="FFFFFF", fg="000000", bold=False, fmt=None, left=False):
        c = ws.cell(row=rn, column=cn, value=val)
        c.fill = _fill(bg); c.font = _font(bold, fg)
        c.border = _bd(); c.alignment = _al("left" if left else "center")
        if fmt: c.number_format = fmt

    def _num(v):
        try: return float(v)
        except: return None

    def _acos_clr(v):
        f = _num(v)
        if f is None: return None, None
        if f < 30:  return GRN_L, GRN_D
        if f < 60:  return YEL_L, YEL_D
        return RED_L, RED_D

    def _margin_clr(v):
        f = _num(v)
        if f is None: return None, None
        if f >= 40: return GRN_L, GRN_D
        if f >= 20: return YEL_L, YEL_D
        return RED_L, RED_D

    def _delta_clr(v):
        f = _num(v)
        if f is None: return None, None
        if f > 5:   return GRN_L, GRN_D
        if f < -5:  return RED_L, RED_D
        return YEL_L, YEL_D

    def _fill_df(ws, df, start_row, color_rules=None):
        """Write a DataFrame into ws starting at start_row, alternating row bg."""
        cols = list(df.columns)
        for ri in range(len(df)):
            rn = start_row + ri
            ws.row_dimensions[rn].height = 15
            row_bg = "FFFFFF" if ri % 2 == 0 else LGRAY
            for ci, col in enumerate(cols):
                raw_val = df.iloc[ri][col]
                num_val = _num(raw_val)
                bg, fg = row_bg, "000000"
                fmt = None
                if color_rules:
                    for rule_col, clr_fn, rule_fmt in color_rules:
                        if col == rule_col:
                            cb, cf = clr_fn(raw_val)
                            if cb: bg, fg = cb, cf
                            fmt = rule_fmt
                            break
                # auto format guesses
                if fmt is None:
                    cl = col.lower()
                    if "($)" in col or "profit ($)" in col: fmt = "$#,##0.00"
                    elif "(%)" in col or "%" in col: fmt = "0.00"
                    elif col in ("Units Sold", "Inventory", "Inventory (Units)", "Impressions"): fmt = "#,##0"
                    elif "|this week" in cl or "|prior week" in cl:
                        if any(x in cl for x in ("sales", "spend", "profit")): fmt = "$#,##0.00"
                        elif any(x in cl for x in ("cvr", "tacos", "sessions", "units")): fmt = "0.00"
                        else: fmt = "#,##0"
                    elif "|delta" in cl or "|d %" in cl or "delta" in cl:
                        fmt = "0.00"
                display = num_val if num_val is not None else (raw_val if raw_val else "")
                left = ci < 2
                _dc(ws, rn, ci + 1, display, bg, fg, fmt=fmt, left=left)

    title = client_name or data.get("title", "MerchanSpring Report")
    period = data.get("period", "")

    # ── Sheet 1: Summary ───────────────────────────────────────────────────
    ws1 = wb.create_sheet("Summary")
    ws1.sheet_view.showGridLines = False
    sum_df = data["summary_df"]
    sum_cols = list(sum_df.columns)
    n = max(len(sum_cols), 10)
    _title_block(ws1, title, period, n)

    # KPI block rows 4-6
    kpis = data.get("kpis", [])
    for ki, kpi in enumerate(kpis[:5]):
        col = ki * 2 + 1
        # name
        if col + 1 <= n:
            ws1.merge_cells(start_row=4, start_column=col, end_row=4, end_column=col + 1)
        c = ws1.cell(row=4, column=col, value=kpi["name"])
        c.fill = _fill(DGRAY); c.font = _font(True, WHITE, 9); c.alignment = _al("center")
        ws1.row_dimensions[4].height = 14
        # value
        if col + 1 <= n:
            ws1.merge_cells(start_row=5, start_column=col, end_row=5, end_column=col + 1)
        c = ws1.cell(row=5, column=col, value=kpi["val"])
        c.fill = _fill(NAVY); c.font = _font(True, WHITE, 14); c.alignment = _al("center")
        ws1.row_dimensions[5].height = 24
        # delta
        if col + 1 <= n:
            ws1.merge_cells(start_row=6, start_column=col, end_row=6, end_column=col + 1)
        dt = kpi["delta"]
        db = GRN_L if "+" in dt else (RED_L if "-" in dt else "E2E8F0")
        df_ = GRN_D if "+" in dt else (RED_D if "-" in dt else "000000")
        c = ws1.cell(row=6, column=col, value=dt)
        c.fill = _fill(db); c.font = _font(False, df_, 9); c.alignment = _al("center")
        ws1.row_dimensions[6].height = 14

    _hdr_row(ws1, 8, sum_cols)
    _fill_df(ws1, sum_df, 9, color_rules=[
        ("ACoS (%)",        _acos_clr,   "0.00"),
        ("TACoS (%)",       _acos_clr,   "0.00"),
        ("Profit Margin %", _margin_clr, "0.00"),
    ])
    # column widths
    for i, col in enumerate(sum_cols):
        ltr = get_column_letter(i + 1)
        ws1.column_dimensions[ltr].width = 42 if col == "Product" else (14 if col == "ASIN" else 13)
    ws1.freeze_panes = "C9"

    # ── Sheet 2: Advertising ───────────────────────────────────────────────
    ws2 = wb.create_sheet("Advertising")
    ws2.sheet_view.showGridLines = False
    adv_df = data["adv_df"]
    adv_cols = list(adv_df.columns)
    _title_block(ws2, title, period, len(adv_cols))

    def _eff_clr(v):
        vl = str(v).lower()
        if "poor" in vl:    return RED_L, RED_D
        if "good" in vl or "great" in vl: return GRN_L, GRN_D
        if "average" in vl: return YEL_L, YEL_D
        return None, None

    _hdr_row(ws2, 3, adv_cols)
    _fill_df(ws2, adv_df, 4, color_rules=[
        ("ACoS (%)",       _acos_clr, "0.00"),
        ("Ad Efficiency",  _eff_clr,  None),
    ])
    for i, col in enumerate(adv_cols):
        ws2.column_dimensions[get_column_letter(i + 1)].width = 42 if col == "Product" else (14 if col == "ASIN" else 13)
    ws2.freeze_panes = "C4"

    # ── Sheet 3: Inventory & Health ────────────────────────────────────────
    ws3 = wb.create_sheet("Inventory & Health")
    ws3.sheet_view.showGridLines = False
    inv_df = data["inv_df"]
    inv_cols = list(inv_df.columns)
    _title_block(ws3, title, period, len(inv_cols))

    def _stock_clr(v):
        vl = str(v).lower()
        if "in stock" in vl:  return GRN_L, GRN_D
        if "partial" in vl:   return ORG_L, ORG_D
        if "critical" in vl:  return RED_L, RED_D
        return None, None

    _hdr_row(ws3, 3, inv_cols)
    _fill_df(ws3, inv_df, 4, color_rules=[
        ("Profit Margin %", _margin_clr, "0.00"),
        ("Stock Status",    _stock_clr,  None),
    ])
    for i, col in enumerate(inv_cols):
        ws3.column_dimensions[get_column_letter(i + 1)].width = 42 if col == "Product" else (14 if col == "ASIN" else 13)
    ws3.freeze_panes = "C4"

    # ── Sheet 4: WoW Comparison ────────────────────────────────────────────
    ws4 = wb.create_sheet("WoW Comparison")
    ws4.sheet_view.showGridLines = False
    wow_df = data["wow_df"]
    wow_cols = list(wow_df.columns)
    metrics = data.get("wow_metrics", [])
    _title_block(ws4, title, period, len(wow_cols))

    # Row 3: metric group merged headers
    ws4.row_dimensions[3].height = 14
    ci = 3  # 1-indexed start after Product + ASIN
    for metric in metrics:
        mc = [c for c in wow_cols if c.startswith(f"{metric}|")]
        span = len(mc)
        if span == 0:
            continue
        if span > 1:
            ws4.merge_cells(start_row=3, start_column=ci, end_row=3, end_column=ci + span - 1)
        c_obj = ws4.cell(row=3, column=ci, value=metric)
        c_obj.fill = _fill(DGRAY); c_obj.font = _font(True, WHITE, 9)
        c_obj.alignment = _al("center")
        ci += span

    sub_hdrs = [c.split("|", 1)[1] if "|" in c else c for c in wow_cols]
    _hdr_row(ws4, 4, sub_hdrs)

    delta_rules = [(c, _delta_clr, "0.00") for c in wow_cols if c.endswith("|Δ %") or "|D %" in c]
    _fill_df(ws4, wow_df, 5, color_rules=delta_rules)

    for i, col in enumerate(wow_cols):
        ltr = get_column_letter(i + 1)
        ws4.column_dimensions[ltr].width = 42 if col == "Product" else (14 if col == "ASIN" else 11)
    ws4.freeze_panes = "C5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


st.set_page_config(page_title="PPC Manager", layout="wide")

# ── Auto-load Business Report map from data/business_report/ ─────────────────
_BIZ_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "business_report")

def _auto_load_business_report_map():
    """Scan _BIZ_DIR for the first CSV/XLSX and load the parent-child map."""
    if not os.path.isdir(_BIZ_DIR):
        return False
    for fname in sorted(os.listdir(_BIZ_DIR)):
        if fname.lower().endswith((".csv", ".xlsx")):
            try:
                c_map, n_map, br_df = _parse_business_report_map(
                    os.path.join(_BIZ_DIR, fname)
                )
                st.session_state["parent_child_map"]   = c_map
                st.session_state["parent_child_names"] = n_map
                st.session_state["br_extra_df"]        = br_df
                st.session_state["_cat_source_file"]   = fname
                return True
            except Exception:
                continue
    return False

if "parent_child_map" not in st.session_state:
    _auto_load_business_report_map()


if "selected_page" not in st.session_state:
    st.session_state["selected_page"] = "🏠 Inicio"

def _nav(page):
    st.session_state["selected_page"] = page

with st.sidebar:
    st.title("🦫 Capybaras Agency OS")
    st.caption("PPC Manager — v1.0")
    st.divider()

    st.button("🏠 Inicio", use_container_width=True, on_click=_nav, args=("🏠 Inicio",), key="nav_home")

    st.markdown("**📊 Análisis**")
    for _pg in ["📊 Search Term Report", "🔍 Search Query Performance", "📁 Bulk Campañas", "💰 Business Report"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔗 Cruce y Tendencias**")
    for _pg in ["🔗 Análisis Cruzado STR vs SQP", "📈 Tendencia Multi-Semana"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    st.markdown("**🔺 Automatización**")
    st.button("🔻 Análisis de Funnel", use_container_width=True, on_click=_nav, args=("🔻 Análisis de Funnel",), key="nav_funnel")

    st.markdown("**📋 Reportes**")
    for _pg in ["🔬 Reportes Atom 11", "🛡️ Reportes MerchanSpring"]:
        st.button(_pg, use_container_width=True, on_click=_nav, args=(_pg,), key=f"nav_{_pg}")

    _n_pe_parents = len(set(st.session_state.get("parent_child_map", {}).values()))
    _pe_label = (
        f"🧬 Parent-Child: {_n_pe_parents} parents cargados"
        if _n_pe_parents > 0 else
        "⚠️ Sin mapeo — agregá Business Report a data/business_report/"
    )
    _pe_color = "#4caf50" if _n_pe_parents > 0 else "#ff9800"
    st.markdown(
        "<div style='margin-top:2rem;font-size:0.72rem;color:#888;'>"
        "Desarrollado por Lenin Acosta · Capybaras Agency · 2026"
        "</div>"
        f"<div style='font-size:0.72rem;color:{_pe_color};margin-top:0.35rem;'>"
        f"{_pe_label}"
        "</div>",
        unsafe_allow_html=True,
    )

selected = st.session_state["selected_page"]

if selected == "🏠 Inicio":
    st.title("🦫 Capybaras Agency OS")
    st.subheader("PPC Manager — v1.0")
    st.divider()
    st.markdown("### Módulos disponibles")

    _HOME_MODULES = [
        ("📊", "Search Term Report",         "✅ activo"),
        ("🔍", "Search Query Performance",    "✅ activo"),
        ("📁", "Bulk Campañas",               "✅ activo"),
        ("💰", "Business Report",             "✅ activo"),
        ("🔗", "Análisis Cruzado STR vs SQP", "✅ activo"),
        ("📈", "Tendencia Multi-Semana",       "✅ activo"),
        ("🔻", "Análisis de Funnel",           "✅ activo"),
        ("🔬", "Reportes Atom 11",             "✅ activo"),
        ("🛡️", "Reportes MerchanSpring",       "✅ activo"),
    ]

    _cols = st.columns(3)
    for i, (emoji, nombre, estado) in enumerate(_HOME_MODULES):
        with _cols[i % 3]:
            st.markdown(
                f"<div style='border:1px solid #ddd;border-radius:10px;padding:1rem;margin-bottom:0.75rem;'>"
                f"<div style='font-size:2rem;'>{emoji}</div>"
                f"<div style='font-weight:600;margin:0.3rem 0;'>{nombre}</div>"
                f"<div style='font-size:0.85rem;'>{estado}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

if selected == "📊 Search Term Report":
    st.header("📊 Search Term Report")
    st.caption("Análisis de términos de búsqueda con métricas de ACoS, gasto y ventas totales.")
    st.divider()
    file_str = st.file_uploader("Sube tu STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str")
    if file_str:
        df = pd.read_excel(file_str) if file_str.name.endswith(".xlsx") else pd.read_csv(file_str)
        st.success(f"✅ {len(df)} filas cargadas")
        
        col1, col2, col3, col4 = st.columns(4)
        spend_col = next((c for c in df.columns if "spend" in c.lower()), None)
        sales_col = next((c for c in df.columns if "sales" in c.lower() and "other" not in c.lower() and "advertised" not in c.lower()), None)
        if spend_col and sales_col:
            total_spend = pd.to_numeric(df[spend_col], errors="coerce").sum()
            total_sales = pd.to_numeric(df[sales_col], errors="coerce").sum()
            acos = (total_spend / total_sales * 100) if total_sales > 0 else 0
            col1.metric("Total Spend", f"${total_spend:,.2f}")
            col2.metric("Total Sales", f"${total_sales:,.2f}")
            col3.metric("ACoS", f"{acos:.1f}%")
            col4.metric("Términos únicos", df.shape[0])
        
        st.dataframe(df, use_container_width=True)

if selected == "🔍 Search Query Performance":
    st.header("🔍 Search Query Performance")
    st.caption("Datos de rendimiento de búsqueda orgánica exportados desde Amazon Brand Analytics.")
    st.divider()
    file_sqp = st.file_uploader("Sube tu SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp")
    if file_sqp:
        df = read_sqp(file_sqp)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "📁 Bulk Campañas":
    st.header("📁 Bulk File de Campañas")
    st.caption("Archivo bulk exportado desde Amazon Ads con todas las campañas, grupos y keywords.")
    st.divider()
    file_bulk = st.file_uploader("Sube tu Bulk (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk")
    if file_bulk:
        df = pd.read_excel(file_bulk) if file_bulk.name.endswith(".xlsx") else pd.read_csv(file_bulk)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "💰 Business Report":
    st.header("💰 Business Report")
    st.caption("Reporte de ventas y sesiones exportado desde Amazon Seller Central.")
    st.divider()
    file_br = st.file_uploader("Sube tu Business Report (.xlsx o .csv)", type=["xlsx", "csv"], key="br")
    if file_br:
        df = pd.read_excel(file_br) if file_br.name.endswith(".xlsx") else pd.read_csv(file_br)
        st.success(f"✅ {len(df)} filas cargadas")
        st.dataframe(df, use_container_width=True)

if selected == "🔗 Análisis Cruzado STR vs SQP":
    st.header("🔗 Análisis Cruzado STR vs SQP")
    st.caption("Detectá oportunidades cruzando términos de búsqueda pagos (STR) con orgánicos (SQP).")
    st.divider()
    st.info("Subí ambos archivos para comparar qué términos aparecen en cada reporte y detectar oportunidades.")

    col_str, col_sqp = st.columns(2)
    with col_str:
        file_str_x = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_x")
    with col_sqp:
        file_sqp_x = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp_x")

    if file_str_x and file_sqp_x:
        df_str = pd.read_excel(file_str_x) if file_str_x.name.endswith(".xlsx") else pd.read_csv(file_str_x)
        brand_name = extract_sqp_brand(file_sqp_x)
        df_sqp = read_sqp(file_sqp_x)

        str_col = "Customer Search Term"
        sqp_col = "Search Query"

        if brand_name:
            st.success(f"Marca detectada: **{brand_name.title()}**")
            brand_terms = [t.strip() for t in brand_name.split(",")]
            df_sqp["Tipo"] = df_sqp[sqp_col].str.lower().str.strip().apply(
                lambda q: "Marca" if any(t in q for t in brand_terms) else "Genérica"
            )
        else:
            st.warning("No se detectó la marca en el archivo SQP. Todas las keywords se clasifican como genéricas.")
            df_sqp["Tipo"] = "Genérica"

        if str_col not in df_str.columns:
            st.error(f"El STR no tiene la columna '{str_col}'.")
        elif sqp_col not in df_sqp.columns:
            st.error(f"El SQP no tiene la columna '{sqp_col}'.")
        else:
            terms_str = set(df_str[str_col].dropna().str.lower().str.strip())
            terms_sqp = set(df_sqp[sqp_col].dropna().str.lower().str.strip())

            in_both = terms_str & terms_sqp
            only_str = terms_str - terms_sqp
            only_sqp = terms_sqp - terms_str

            c1, c2, c3 = st.columns(3)
            c1.metric("En ambos", len(in_both))
            c2.metric("Solo en STR (no en SQP)", len(only_str))
            c3.metric("Solo en SQP (oportunidades)", len(only_sqp))

            opp_sqp = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)]
            n_marca    = (opp_sqp["Tipo"] == "Marca").sum()
            n_generica = (opp_sqp["Tipo"] == "Genérica").sum()
            m1, m2 = st.columns(2)
            m1.metric("Oportunidades de marca", n_marca)
            m2.metric("Oportunidades genéricas", n_generica)

            # ── Convertir columnas numéricas del SQP ────────────────────────
            imp_col   = "Impressions: Total Count"
            score_col = "Search Query Score"
            pur_col   = "Purchases: Total Count"
            prate_col = "Purchases: Purchase Rate %"
            for c in [imp_col, score_col, pur_col, prate_col, "Clicks: Total Count"]:
                if c in df_sqp.columns:
                    df_sqp[c] = pd.to_numeric(df_sqp[c], errors="coerce").fillna(0)

            # ── Filtros globales ─────────────────────────────────────────────
            st.markdown("---")
            st.markdown("#### Filtros")
            f1, f2, f3, f4 = st.columns(4)
            min_imp   = f1.number_input("Mínimo de impresiones", min_value=0, value=0, step=100)
            min_score = f2.number_input("Mínimo Search Query Score", min_value=0, value=0, step=1)
            min_pur   = f3.number_input("Mínimo de purchases", min_value=0, value=0, step=1)
            tipo_filtro = f4.selectbox("Tipo de keyword", ["Todas", "Marca", "Genérica"])

            def apply_filters(df):
                d = df.copy()
                if imp_col in d.columns:
                    d = d[d[imp_col] >= min_imp]
                if score_col in d.columns:
                    d = d[d[score_col] >= min_score]
                if pur_col in d.columns:
                    d = d[d[pur_col] >= min_pur]
                if "Tipo" in d.columns and tipo_filtro != "Todas":
                    d = d[d["Tipo"] == tipo_filtro]
                if imp_col in d.columns:
                    d = d.sort_values(imp_col, ascending=False)
                return d

            st.markdown("---")

            # ── Tabla 1: en ambos ────────────────────────────────────────────
            st.markdown("#### Términos en ambos reportes")
            sqp_cols_merge = [sqp_col] + [c for c in [score_col, imp_col, "Clicks: Total Count", pur_col] if c in df_sqp.columns]
            sqp_subset = df_sqp[sqp_cols_merge].copy()
            sqp_subset[sqp_col] = sqp_subset[sqp_col].str.lower().str.strip()
            merged = df_str[df_str[str_col].str.lower().str.strip().isin(in_both)].copy()
            merged[str_col] = merged[str_col].str.lower().str.strip()
            merged = merged.merge(sqp_subset, left_on=str_col, right_on=sqp_col, how="left", suffixes=("_STR", "_SQP"))
            st.dataframe(apply_filters(merged), use_container_width=True)

            # ── Tabla 2: solo en SQP (oportunidades) ────────────────────────
            st.markdown("#### Términos solo en SQP (sin campaña activa — posibles oportunidades)")
            df_oportunidades = df_sqp[df_sqp[sqp_col].str.lower().str.strip().isin(only_sqp)].copy()

            score_norm_cols = [c for c in [imp_col, "Clicks: Total Count", prate_col] if c in df_oportunidades.columns]
            if score_norm_cols:
                norm = df_oportunidades[score_norm_cols].apply(
                    lambda s: (s - s.min()) / (s.max() - s.min()) if s.max() != s.min() else 0
                )
                df_oportunidades.insert(1, "Opportunity Score", (norm.sum(axis=1) / len(score_norm_cols) * 100).round(1))

            df_oportunidades_filtrado = apply_filters(df_oportunidades)
            st.dataframe(df_oportunidades_filtrado, use_container_width=True)

            buffer = io.BytesIO()
            df_oportunidades_filtrado.to_excel(buffer, index=False)
            st.download_button(
                label=f"⬇️ Exportar {len(df_oportunidades_filtrado)} oportunidades a Excel",
                data=buffer.getvalue(),
                file_name="oportunidades_sqp.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True,
            )

            # ── Tabla 3: solo en STR ─────────────────────────────────────────
            st.markdown("#### Términos solo en STR (sin datos de búsqueda orgánica)")
            df_solo_str = df_str[df_str[str_col].str.lower().str.strip().isin(only_str)].copy()
            st.dataframe(df_solo_str, use_container_width=True)

if selected == "📈 Tendencia Multi-Semana":
    st.header("📈 Tendencia de Impresiones Multi-Semana")
    st.caption("Compará hasta 4 semanas de SQP para identificar keywords en alza, estables o en caída.")
    st.divider()
    st.info("Subí hasta 4 archivos SQP de distintas semanas para ver la tendencia por keyword.")

    sqp_files = []
    cols_up = st.columns(4)
    for i, col in enumerate(cols_up):
        f = col.file_uploader(f"Semana {i+1}", type=["xlsx", "csv"], key=f"sqp_trend_{i}")
        if f:
            sqp_files.append(f)

    if len(sqp_files) >= 2:
        imp_col_t = "Impressions: Total Count"
        sqp_col_t = "Search Query"

        weeks = []
        for f in sqp_files:
            df_w = read_sqp(f)
            df_w[sqp_col_t] = df_w[sqp_col_t].str.lower().str.strip()
            if imp_col_t in df_w.columns:
                df_w[imp_col_t] = pd.to_numeric(df_w[imp_col_t], errors="coerce").fillna(0)
            # Extraer fecha desde Reporting Date o nombre de archivo
            label = None
            if "Reporting Date" in df_w.columns:
                label = str(df_w["Reporting Date"].dropna().iloc[0]) if not df_w["Reporting Date"].dropna().empty else f.name
            else:
                label = f.name
            weeks.append((label, df_w[[sqp_col_t, imp_col_t]].rename(columns={imp_col_t: label})))

        df_trend = weeks[0][1]
        for _, df_w in weeks[1:]:
            df_trend = df_trend.merge(df_w, on=sqp_col_t, how="outer").fillna(0)

        week_cols = [w[0] for w in weeks]
        first_col, last_col = week_cols[0], week_cols[-1]

        def tendencia(row):
            v1, v2 = row[first_col], row[last_col]
            if v2 > v1 * 1.1:
                return "↑"
            elif v2 < v1 * 0.9:
                return "↓"
            return "→"

        df_trend["Tendencia"] = df_trend.apply(tendencia, axis=1)
        df_trend = df_trend[[sqp_col_t, "Tendencia"] + week_cols].sort_values(last_col, ascending=False)

        st.markdown(f"↑ sube >10% · ↓ baja >10% · → estable")

        t1, t2, t3, t4 = st.columns(4)
        t1.metric("Total keywords", len(df_trend))
        t2.metric("↑ Subiendo", (df_trend["Tendencia"] == "↑").sum())
        t3.metric("→ Estables",  (df_trend["Tendencia"] == "→").sum())
        t4.metric("↓ Bajando",   (df_trend["Tendencia"] == "↓").sum())

        row_height = 35
        header_height = 38
        st.dataframe(df_trend, use_container_width=True, height=header_height + row_height * len(df_trend))

        buffer_t = io.BytesIO()
        df_trend.to_excel(buffer_t, index=False)
        st.download_button(
            label="⬇️ Exportar tendencias a Excel",
            data=buffer_t.getvalue(),
            file_name="tendencia_sqp.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
        )
    elif len(sqp_files) == 1:
        st.warning("Subí al menos 2 semanas para ver la tendencia.")

if selected == "🔻 Análisis de Funnel":
    st.header("🔻 Análisis de Funnel")
    st.caption("Analizá cobertura de campañas activas, detectá brechas y generá sugerencias de harvesting.")
    st.divider()
    st.info("Subí el Bulk de campañas y el STR para ver cobertura por campaña.")

    col_bulk_f, col_str_f = st.columns(2)
    with col_bulk_f:
        file_bulk_f = st.file_uploader("Bulk de campañas (.xlsx o .csv)", type=["xlsx", "csv"], key="bulk_f")
    with col_str_f:
        file_str_f = st.file_uploader("STR (.xlsx o .csv)", type=["xlsx", "csv"], key="str_f")

    if file_bulk_f:
        df_bulk = pd.read_excel(file_bulk_f) if file_bulk_f.name.endswith(".xlsx") else pd.read_csv(file_bulk_f)
        df_bulk.columns = df_bulk.columns.str.strip()

        # Columnas reales del bulk de Amazon
        # State: ENABLED / PAUSED / ARCHIVED  (cada fila = una campaña)
        state_col = next((c for c in df_bulk.columns if c.lower() == "state"), None)
        camp_col  = next((c for c in df_bulk.columns if c.lower() == "campaign name"), None)
        type_col  = next((c for c in df_bulk.columns if c.lower() == "type"), None)

        if state_col:
            df_active = df_bulk[df_bulk[state_col].str.upper().str.strip() == "ENABLED"].copy()
        else:
            df_active = df_bulk.copy()

        # Métricas de campañas activas
        n_camps = len(df_active)
        n_tipos = df_active[type_col].value_counts() if type_col else None

        m1, m2, m3 = st.columns(3)
        m1.metric("Campañas activas", n_camps)
        m2.metric("Pausadas",  len(df_bulk[df_bulk[state_col].str.upper().str.strip() == "PAUSED"]) if state_col else "—")
        m3.metric("Total en Bulk", len(df_bulk))

        if type_col and n_tipos is not None:
            st.markdown("**Campañas activas por tipo:**  " + "  ·  ".join(f"**{k}**: {v}" for k, v in n_tipos.items()))

        st.markdown("#### Campañas activas")
        display_cols = [c for c in ["Campaign name", "Type", "Portfolio name", "Campaign bid strategy",
                                     "Campaign budget amount", "Impressions", "Clicks", "CTR",
                                     "Total cost", "CPC", "Purchases", "Sales", "ACOS", "ROAS"]
                        if c in df_active.columns]
        st.dataframe(df_active[display_cols] if display_cols else df_active, use_container_width=True)

        st.markdown("---")

        # Cruce con STR por nombre de campaña
        if file_str_f:
            df_str_f_data = pd.read_excel(file_str_f) if file_str_f.name.endswith(".xlsx") else pd.read_csv(file_str_f)
            df_str_f_data.columns = df_str_f_data.columns.str.strip()

            str_term_col = "Customer Search Term"
            str_camp_col = next((c for c in df_str_f_data.columns if c.lower() == "campaign name"), None)

            if str_term_col not in df_str_f_data.columns:
                st.error(f"El STR no tiene la columna '{str_term_col}'.")
            elif camp_col is None or str_camp_col is None:
                st.error("No se encontró la columna 'Campaign name' en el Bulk o en el STR.")
            else:
                active_camps = set(df_active[camp_col].dropna().str.lower().str.strip())
                df_str_f_data["_camp_norm"] = df_str_f_data[str_camp_col].str.lower().str.strip()

                df_str_activo  = df_str_f_data[df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")
                df_str_inactivo = df_str_f_data[~df_str_f_data["_camp_norm"].isin(active_camps)].drop(columns="_camp_norm")

                camps_sin_str = active_camps - set(df_str_f_data["_camp_norm"])

                c1, c2, c3 = st.columns(3)
                c1.metric("Términos STR de campañas activas",   len(df_str_activo))
                c2.metric("Términos STR de campañas inactivas", len(df_str_inactivo))
                c3.metric("Campañas activas sin tráfico en STR", len(camps_sin_str))

                st.markdown("#### Términos del STR provenientes de campañas activas")
                st.dataframe(df_str_activo, use_container_width=True)

                st.markdown("#### Términos del STR de campañas pausadas o no encontradas")
                df_gaps = df_str_inactivo
                st.dataframe(df_gaps, use_container_width=True)

                buf_gaps = io.BytesIO()
                df_gaps.to_excel(buf_gaps, index=False)
                st.download_button(
                    label=f"⬇️ Exportar {len(df_gaps)} términos de campañas inactivas",
                    data=buf_gaps.getvalue(),
                    file_name="str_campanas_inactivas.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True,
                )

                if camps_sin_str:
                    st.markdown("#### Campañas activas sin términos en el STR")
                    st.dataframe(pd.DataFrame(sorted(camps_sin_str), columns=["Campaign name"]), use_container_width=True)

                # ── Campañas Sugeridas ───────────────────────────────────────
                st.markdown("---")
                st.markdown("### Campañas Sugeridas")
                st.info("Nombres generados siguiendo el convention: Producto - ASIN - SP - KW - MatchType - Keyword")

                if str_term_col in df_gaps.columns and str_camp_col in df_gaps.columns and len(df_gaps) > 0:
                    match_type = st.selectbox("Match Type por defecto", ["Phrase", "Exact", "Broad"], key="match_type_sug")

                    def extract_producto_asin(camp_name):
                        """Extrae Producto y ASIN del nombre de campaña (formato: Producto - ASIN - ...)."""
                        m = re.match(r'^(.+?)\s*-\s*(B[0-9A-Z]{9})\b', str(camp_name), re.IGNORECASE)
                        if m:
                            return m.group(1).strip(), m.group(2).upper()
                        return None, None

                    rows = []
                    for _, row in df_gaps[[str_term_col, str_camp_col]].drop_duplicates(subset=str_term_col).iterrows():
                        term = str(row[str_term_col]).strip()
                        producto, asin = extract_producto_asin(row[str_camp_col])
                        if producto and asin:
                            suggested = f"{producto} - {asin} - SP - KW - {match_type} - {term.title()}"
                        else:
                            suggested = f"[Producto] - [ASIN] - SP - KW - {match_type} - {term.title()}"
                        rows.append({
                            "Customer Search Term": term,
                            "Campaña origen (inactiva)": row[str_camp_col],
                            "Producto inferido": producto or "—",
                            "ASIN inferido": asin or "—",
                            "Match Type": match_type,
                            "Nombre sugerido": suggested,
                        })

                    df_sugeridas = pd.DataFrame(rows)
                    st.dataframe(df_sugeridas, use_container_width=True)

                    buf_sug = io.BytesIO()
                    df_sugeridas.to_excel(buf_sug, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_sugeridas)} campañas sugeridas a Excel",
                        data=buf_sug.getvalue(),
                        file_name="campanas_sugeridas.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                else:
                    st.success("No hay términos de campañas inactivas para sugerir.")

                # ── Harvesting ───────────────────────────────────────────────
                st.markdown("---")
                st.markdown("### Harvesting")
                st.info("Términos del STR con ventas suficientes para cosechar como keywords.")

                orders_col  = "7 Day Total Orders (#)"
                sales_col_h = "7 Day Total Sales"
                acos_col_h  = "Total Advertising Cost of Sales (ACOS)"
                cvr_col     = "7 Day Conversion Rate"

                harvest_cols = [c for c in [str_term_col, "Impressions", "Clicks", orders_col,
                                            sales_col_h, "Spend", acos_col_h, cvr_col]
                                if c in df_str_f_data.columns]

                if orders_col not in df_str_f_data.columns:
                    st.warning(f"El STR no tiene la columna '{orders_col}'.")
                else:
                    min_ventas = st.number_input("Mínimo de órdenes para cosechar", min_value=1, value=3, step=1, key="min_harvest")

                    for c in [orders_col, sales_col_h, acos_col_h, cvr_col, "Impressions", "Clicks", "Spend"]:
                        if c in df_str_f_data.columns:
                            df_str_f_data[c] = pd.to_numeric(df_str_f_data[c], errors="coerce").fillna(0)

                    camp_agg = df_str_f_data.groupby(str_term_col)[str_camp_col].apply(
                        lambda x: " | ".join(sorted(x.dropna().unique()))
                    ).reset_index().rename(columns={str_camp_col: "Campaña origen"})

                    df_harvest_agg = (
                        df_str_f_data[harvest_cols]
                        .groupby(str_term_col, as_index=False)
                        .agg({c: "sum" for c in harvest_cols if c != str_term_col})
                        .merge(camp_agg, on=str_term_col, how="left")
                    )

                    # Mover "Campaña origen" como segunda columna
                    cols = df_harvest_agg.columns.tolist()
                    cols.insert(1, cols.pop(cols.index("Campaña origen")))
                    df_harvest_agg = df_harvest_agg[cols]

                    # Recalcular ACoS agregado
                    if sales_col_h in df_harvest_agg.columns and "Spend" in df_harvest_agg.columns:
                        df_harvest_agg[acos_col_h] = (
                            df_harvest_agg["Spend"] / df_harvest_agg[sales_col_h].replace(0, float("nan")) * 100
                        ).round(2)

                    df_harvest_agg = df_harvest_agg[df_harvest_agg[orders_col] >= min_ventas].copy()

                    def suggest_match(row):
                        orders = row[orders_col]
                        acos   = row.get(acos_col_h, 100)
                        if orders >= min_ventas * 3 or (orders >= min_ventas and acos <= 25):
                            return "Exact"
                        return "Phrase"

                    df_harvest_agg["Match Type Sugerido"] = df_harvest_agg.apply(suggest_match, axis=1)
                    df_harvest_agg = df_harvest_agg.sort_values(orders_col, ascending=False)

                    n_exact  = (df_harvest_agg["Match Type Sugerido"] == "Exact").sum()
                    n_phrase = (df_harvest_agg["Match Type Sugerido"] == "Phrase").sum()
                    h1, h2, h3 = st.columns(3)
                    h1.metric("Términos para cosechar", len(df_harvest_agg))
                    h2.metric("→ Exact",  n_exact)
                    h3.metric("→ Phrase", n_phrase)

                    st.markdown(f"**Criterio:** Exact si órdenes ≥ {min_ventas * 3} o (órdenes ≥ {min_ventas} y ACoS ≤ 25%) · Phrase en el resto")
                    st.dataframe(df_harvest_agg, use_container_width=True)

                    buf_harv = io.BytesIO()
                    df_harvest_agg.to_excel(buf_harv, index=False)
                    st.download_button(
                        label=f"⬇️ Exportar {len(df_harvest_agg)} términos para cosechar",
                        data=buf_harv.getvalue(),
                        file_name="harvesting.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
        else:
            st.markdown("#### Todas las campañas del Bulk")
            st.dataframe(df_bulk, use_container_width=True)

if selected == "🔬 Reportes Atom 11":
    st.header("🔬 Reportes Atom 11")
    st.caption("Subí 1 archivo para el resumen del periodo, o 2 archivos para comparación automática WoW / MoM.")
    st.divider()

    _cfg_col1, _cfg_col2 = st.columns([3, 1])
    with _cfg_col1:
        client_name = st.text_input("Nombre del cliente (aparece en el Excel)", placeholder="Ej: Dermaglos Argentina", key="atom11_client")
    with _cfg_col2:
        _lang_opt = st.radio("Idioma del Excel", ["Español", "English"], horizontal=True, key="atom11_lang")
    lang_code = "en" if _lang_opt == "English" else "es"

    col_u1, col_u2 = st.columns(2)
    with col_u1:
        file_a1 = st.file_uploader("Periodo 1 \u2014 anterior (o unico archivo)", type=["xlsx"], key="atom11_f1")
    with col_u2:
        file_a2 = st.file_uploader("Periodo 2 \u2014 actual (opcional, para comparacion)", type=["xlsx"], key="atom11_f2")

    if file_a1:
        try:
            df1, ec1, cm1, fmt1 = _parse_atom11(file_a1)
            tipo = _detect_atom11_type(ec1)
            metrics1 = list(dict.fromkeys(m for _, m, _ in cm1))
            periods1 = list(dict.fromkeys(p for _, _, p in cm1))

            # ── Two-file comparison ───────────────────────────────────────────
            if file_a2:
                df2, ec2, cm2, fmt2 = _parse_atom11(file_a2)
                tipo2 = _detect_atom11_type(ec2)
                metrics2 = list(dict.fromkeys(m for _, m, _ in cm2))
                periods2 = list(dict.fromkeys(p for _, _, p in cm2))

                if ec1[0].lower() != ec2[0].lower():
                    st.error(f"Los archivos son de tipos distintos ({tipo} vs {tipo2}). Subi dos archivos del mismo tipo.")
                else:
                    # Collapse each file to a single-period df
                    if fmt1 == "DateRange":
                        df1_s, per1 = _summarize_daterange(df1, ec1, cm1)
                    else:
                        per1 = periods1[-1] if fmt1 == "WoW" else periods1[0]
                        df1_s = _extract_period_df(df1, ec1, cm1, per1)

                    if fmt2 == "DateRange":
                        df2_s, per2 = _summarize_daterange(df2, ec2, cm2)
                    else:
                        per2 = periods2[-1] if fmt2 == "WoW" else periods2[0]
                        df2_s = _extract_period_df(df2, ec2, cm2, per2)

                    comp_lbl = "WoW" if "week" in per1.lower() or "week" in per2.lower() else "MoM"
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Comparacion {comp_lbl}:** {per1}  \u2192  {per2}")

                    merged = df1_s.merge(df2_s, on=ec1, how="outer",
                                         suffixes=(f" ({per1})", f" ({per2})"))
                    for c in merged.columns:
                        if c not in ec1:
                            merged[c] = pd.to_numeric(merged[c], errors="coerce").fillna(0)

                    display = merged[ec1].copy()
                    delta_cols = []
                    for metric in list(dict.fromkeys(metrics1 + metrics2)):
                        pc = f"{metric} ({per1})"; cc = f"{metric} ({per2})"
                        if pc in merged.columns and cc in merged.columns:
                            display[pc] = merged[pc]
                            display[cc] = merged[cc]
                            pct_v = ((merged[cc] - merged[pc]) / merged[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    # Derived ACoS & CPC
                    for suf in [per1, per2]:
                        sp_c = f"Spend ({suf})"; sl_c = f"Sales ({suf})"; cl_c = f"Clicks ({suf})"
                        if sp_c in display.columns and sl_c in display.columns:
                            display[f"ACoS ({suf})"] = (display[sp_c] / display[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in display.columns and cl_c in display.columns:
                            display[f"CPC ({suf})"] = (display[sp_c] / display[cl_c].replace(0, float("nan"))).round(2)

                    kc = _kpis(df2_s); kp = _kpis(df1_s)
                    per_c = per2; per_p = per1
                    df_curr = df2_s

            # ── Single file ───────────────────────────────────────────────────
            else:
                if fmt1 == "WoW":
                    prev_p = periods1[0]; curr_p = periods1[-1]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **WoW:** {prev_p}  \u2192  {curr_p}")
                    display = df1[ec1].copy()
                    delta_cols = []
                    for metric in metrics1:
                        pc = f"{metric}|{prev_p}"; cc = f"{metric}|{curr_p}"
                        if pc in df1.columns and cc in df1.columns:
                            display[f"{metric} ({prev_p})"] = df1[pc]
                            display[f"{metric} ({curr_p})"] = df1[cc]
                            pct_v = ((df1[cc] - df1[pc]) / df1[pc].replace(0, float("nan")) * 100).round(1)
                            d_col = f"{metric} \u0394%"
                            display[d_col] = pct_v
                            delta_cols.append(d_col)
                    for period in [prev_p, curr_p]:
                        sp_c = f"Spend|{period}"; sl_c = f"Sales|{period}"; cl_c = f"Clicks|{period}"
                        if sp_c in df1.columns and sl_c in df1.columns:
                            display[f"ACoS ({period})"] = (df1[sp_c] / df1[sl_c].replace(0, float("nan")) * 100).round(2)
                        if sp_c in df1.columns and cl_c in df1.columns:
                            display[f"CPC ({period})"] = (df1[sp_c] / df1[cl_c].replace(0, float("nan"))).round(2)
                    df_curr = _extract_period_df(df1, ec1, cm1, curr_p)
                    df_prev = _extract_period_df(df1, ec1, cm1, prev_p)
                    kc = _kpis(df_curr); kp = _kpis(df_prev)
                    per_c = curr_p; per_p = prev_p

                elif fmt1 == "MoM":
                    period = periods1[0]
                    st.info(f"**Tipo detectado:** {tipo}  \u00b7  **MoM:** {period}")
                    df_curr = _extract_period_df(df1, ec1, cm1, period)
                    display = df_curr.copy()
                    if "Spend" in display.columns and "Sales" in display.columns:
                        display["ACoS"] = (display["Spend"] / display["Sales"].replace(0, float("nan")) * 100).round(2)
                    if "Spend" in display.columns and "Clicks" in display.columns:
                        display["CPC"] = (display["Spend"] / display["Clicks"].replace(0, float("nan"))).round(2)
                    delta_cols = []
                    kc = _kpis(df_curr); kp = None
                    per_c = period; per_p = ""

                else:  # DateRange
                    two_weeks = _split_two_weeks(df1, ec1, cm1)
                    if two_weeks:
                        df_prev, df_curr, per_p, per_c = two_weeks
                        st.info(
                            f"**Tipo detectado:** {tipo}  \u00b7  "
                            f"**WoW auto-detectado (2 semanas):**  "
                            f"Sem 1: {per_p}  \u2192  Sem 2: {per_c}"
                        )
                        _sfx_prev = _I18N[lang_code]["col_prev_sfx"]
                        _sfx_curr = _I18N[lang_code]["col_curr_sfx"]
                        display    = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            if metric in df_prev.columns and metric in df_curr.columns:
                                display[f"{metric} {_sfx_prev}"] = df_prev[metric]
                                display[f"{metric} {_sfx_curr}"] = df_curr[metric]
                                pct_v = (
                                    (df_curr[metric] - df_prev[metric])
                                    / df_prev[metric].replace(0, float("nan")) * 100
                                ).round(1)
                                d_col = f"{metric} \u0394%"
                                display[d_col] = pct_v
                                delta_cols.append(d_col)
                        for suffix, df_s in [(_sfx_prev, df_prev), (_sfx_curr, df_curr)]:
                            if "Spend" in df_s.columns and "Sales" in df_s.columns:
                                display[f"ACoS {suffix}"] = (
                                    df_s["Spend"] / df_s["Sales"].replace(0, float("nan")) * 100
                                ).round(2)
                            if "Spend" in df_s.columns and "Clicks" in df_s.columns:
                                display[f"CPC {suffix}"] = (
                                    df_s["Spend"] / df_s["Clicks"].replace(0, float("nan"))
                                ).round(2)
                        kc = _kpis(df_curr)
                        kp = _kpis(df_prev)
                    else:
                        df_curr, period_lbl = _summarize_daterange(df1, ec1, cm1)
                        st.info(f"**Tipo detectado:** {tipo}  \u00b7  **Date Range:** {period_lbl}")
                        dates = periods1
                        display = df1[ec1].copy()
                        delta_cols = []
                        for metric in metrics1:
                            for date in dates:
                                col = f"{metric}|{date}"
                                if col in df1.columns:
                                    display[f"{metric} {date}"] = df1[col]
                            date_cols = [f"{metric}|{d}" for d in dates if f"{metric}|{d}" in df1.columns]
                            if date_cols:
                                display[f"{metric} Total"] = df1[date_cols].sum(axis=1)
                            if len(dates) >= 2:
                                fc = f"{metric}|{dates[0]}"; lc = f"{metric}|{dates[-1]}"
                                if fc in df1.columns and lc in df1.columns:
                                    d_col = f"{metric} \u0394%"
                                    display[d_col] = ((df1[lc] - df1[fc]) / df1[fc].replace(0, float("nan")) * 100).round(1)
                                    delta_cols.append(d_col)
                        kc = _kpis(df_curr); kp = None
                        per_c = period_lbl; per_p = ""

            # ── KPI cards ─────────────────────────────────────────────────────
            st.markdown("---")
            kpi_defs_display = [
                ("Impressions", "{:,.0f}",  False),
                ("Clicks",      "{:,.0f}",  False),
                ("Spend",       "${:,.2f}", False),
                ("Sales",       "${:,.2f}", False),
                ("ACoS",        "{:.1f}%",  True),
                ("ROAS",        "{:.2f}x",  False),
                ("CTR",         "{:.2f}%",  False),
                ("CVR",         "{:.2f}%",  False),
            ]
            _kpi_chunk_size = 4
            for _kpi_start in range(0, len(kpi_defs_display), _kpi_chunk_size):
                _kpi_chunk = kpi_defs_display[_kpi_start:_kpi_start + _kpi_chunk_size]
                kpi_row = st.columns(len(_kpi_chunk))
                for i, (label, fmt_str, lower_better) in enumerate(_kpi_chunk):
                    cv = kc.get(label, 0) or 0
                    val_str = fmt_str.format(cv)
                    if kp is not None:
                        pv = kp.get(label, 0) or 0
                        if pv != 0:
                            d = (cv - pv) / pv * 100
                            kpi_row[i].metric(label, val_str, delta=f"{d:+.1f}%",
                                              delta_color="inverse" if lower_better else "normal")
                        else:
                            kpi_row[i].metric(label, val_str)
                    else:
                        kpi_row[i].metric(label, val_str)

            # ── Comparison table ──────────────────────────────────────────────
            st.markdown("---")
            if delta_cols:
                styled = display.style.map(_color_pct, subset=delta_cols)
                st.dataframe(styled, use_container_width=True)
            else:
                st.dataframe(display, use_container_width=True)

            # ── Executive summary ─────────────────────────────────────────────
            top_rows = None
            if "Sales" in df_curr.columns and len(df_curr) > 0:
                top_rows = df_curr.nlargest(3, "Sales").to_dict("records")

            summary_text = _generate_summary(tipo, ec1[0], kc, kp or None, per_c, per_p, top_rows, lang=lang_code)

            _expander_lbl = "View Executive Summary" if lang_code == "en" else "Ver Resumen Ejecutivo del cliente"
            st.markdown("---")
            with st.expander(_expander_lbl, expanded=True):
                st.text(summary_text)

            # ── Parent Evolution — compute before export ───────────────────────
            _pe_df  = None
            _pe_err = None
            if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
                _pe_df, _pe_err = _build_parent_evolution(
                    df1, ec1, cm1, fmt1,
                    st.session_state["parent_child_map"],
                    st.session_state.get("parent_child_names", {}),
                    br_df=st.session_state.get("br_extra_df"),
                    lang=lang_code,
                )

            # ── Export ────────────────────────────────────────────────────────
            buf = _build_atom11_excel(display, kc, kp, tipo, per_c, per_p or "", delta_cols,
                                      client_name=client_name, entity_col=ec1[0], top_rows=top_rows,
                                      lang=lang_code, parent_evo_df=_pe_df)
            safe_name = per_c[:15].replace(" ", "_").replace(",", "").replace("\u2192", "-")
            st.download_button(
                label="⬇️ Descargar análisis completo — Excel con KPIs + Tabla + Resumen Ejecutivo",
                data=buf.getvalue(),
                file_name=f"atom11_{tipo.lower().replace(' ', '_')}_{safe_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="atom11_export",
                use_container_width=True,
            )

            # ── 🧬 Evolución por Parent ASIN ─────────────────────────────────
            st.markdown("---")
            st.markdown("### 🧬 Evolución por Parent ASIN")
            _t_pe = _I18N.get(lang_code, _I18N["es"])
            if "parent_child_map" not in st.session_state or not st.session_state["parent_child_map"]:
                st.info(_t_pe["pe_no_map"])
            elif _pe_err:
                st.warning(_pe_err)
            elif _pe_df is not None and not _pe_df.empty:
                st.caption(f"{len(_pe_df)} {_t_pe['pe_caption']}")
                _pe_pct_cols = [c for c in _pe_df.columns if "%" in c]
                _pe_styled = _pe_df.style.map(_color_pct, subset=_pe_pct_cols) if _pe_pct_cols else _pe_df.style
                st.dataframe(_pe_styled, use_container_width=True, hide_index=True)
                with st.expander(_t_pe["pe_expander_lbl"]):
                    st.code(_generate_parent_evo_summary(_pe_df, lang=lang_code), language=None)
            else:
                st.info(_t_pe["pe_no_rows"])

        except Exception as e:
            st.error(f"Error al procesar los archivos: {e}")
            import traceback
            st.code(traceback.format_exc())

    # ── Business Report — mapeo activo + input opcional para marca nueva ─────
    st.markdown("---")
    st.markdown("### 📂 Mapeo Parent-Child")

    # Estado del mapeo activo
    if "parent_child_map" in st.session_state and st.session_state["parent_child_map"]:
        _n_ch = len(st.session_state["parent_child_map"])
        _n_pr = len(set(st.session_state["parent_child_map"].values()))
        _src  = st.session_state.get("_cat_source_file", "archivo desconocido")
        _has_br_extra = (
            st.session_state.get("br_extra_df") is not None
            and not st.session_state["br_extra_df"].empty
        )
        _extra_note = f" · {len([c for c in _BR_OPTIONAL_COLS if c in st.session_state['br_extra_df'].columns])} métricas BR" if _has_br_extra else ""
        st.caption(f"📂 Mapeo activo: `{_src}` — {_n_pr} parents · {_n_ch} children{_extra_note}")
        _map_df = pd.DataFrame(
            [{"Child ASIN": k, "Parent ASIN": v}
             for k, v in st.session_state["parent_child_map"].items()]
        )
        _map_names = st.session_state.get("parent_child_names", {})
        if _map_names:
            _map_df["Título"] = _map_df["Child ASIN"].map(_map_names).fillna("")
        with st.expander(f"Ver mapeo completo ({len(_map_df)} children)", expanded=False):
            st.dataframe(_map_df, use_container_width=True, hide_index=True)
    else:
        st.warning(
            "No se encontró mapeo automático. "
            "Colocá el Business Report CSV en `data/business_report/` o subilo abajo."
        )

    # ── Input opcional para marca nueva ──────────────────────────────────────
    st.markdown("**¿Marca nueva?** Subí el Business Report aquí")
    _new_br_file = st.file_uploader(
        "Business Report (.csv o .xlsx)",
        type=["csv", "xlsx"],
        key="atom11_new_br",
        label_visibility="collapsed",
    )

    if _new_br_file:
        try:
            _new_bytes = _new_br_file.getvalue()
            _new_c_map, _new_n_map, _new_br_df = _parse_business_report_map(_new_br_file)

            # Actualizar mapeo en session_state
            st.session_state["parent_child_map"]   = _new_c_map
            st.session_state["parent_child_names"] = _new_n_map
            st.session_state["br_extra_df"]        = _new_br_df
            st.session_state["_cat_source_file"]   = _new_br_file.name

            _new_n_pr = len(set(_new_c_map.values()))
            _new_n_ch = len(_new_c_map)
            st.success(f"✅ Nuevo mapeo cargado: {_new_n_pr} parents · {_new_n_ch} children")

            # Proponer guardar permanentemente
            _save_ext    = os.path.splitext(_new_br_file.name)[1].lower() or ".csv"
            _save_prefix = (client_name.strip().replace(" ", "") if client_name.strip() else "Cliente")
            _save_name   = f"{_save_prefix}_Business_Report{_save_ext}"
            _save_path   = os.path.join(_BIZ_DIR, _save_name)

            st.info(
                f"¿Querés guardar este archivo en `data/business_report/` "
                f"para que quede permanente para esta marca?"
            )
            st.caption(f"Se guardaría como: `{_save_name}`")

            _btn_yes, _btn_no, _ = st.columns([1, 1, 3])

            if _btn_yes.button("💾 Sí, guardar", key="br_save_yes", use_container_width=True):
                os.makedirs(_BIZ_DIR, exist_ok=True)
                with open(_save_path, "wb") as _fout:
                    _fout.write(_new_bytes)
                st.session_state["_cat_source_file"] = _save_name
                st.success(f"✅ Guardado como `{_save_name}` en `data/business_report/`")

            if _btn_no.button("🚫 Solo esta sesión", key="br_save_no", use_container_width=True):
                st.info("Mapeo activo solo para esta sesión, no se guardó en disco.")

        except Exception as _new_e:
            st.error(f"Error al parsear el Business Report: {_new_e}")

if selected == "🛡️ Reportes MerchanSpring":
    st.header("🛡️ Reportes MerchanSpring")
    st.caption("Subí el reporte semanal de MerchanSpring (.xlsx o .pdf) para ver el dashboard y exportar el informe profesional.")
    st.divider()

    ms_client = st.text_input(
        "Nombre del cliente (aparece en el Excel)",
        placeholder="Ej: Love To Dream",
        key="ms_client",
    )
    ms_file = st.file_uploader(
        "Arrastrá el archivo MerchanSpring (.xlsx o .pdf)",
        type=["xlsx", "pdf"],
        key="ms_upload",
    )

    if ms_file:
        try:
            is_pdf = ms_file.name.lower().endswith(".pdf")

            if is_pdf:
                ms_data = _parse_merchanspring_pdf(ms_file)
            else:
                ms_data = _parse_merchanspring(ms_file)

            st.markdown(f"### {ms_data.get('title', '')}")
            st.caption(ms_data.get("period", ""))

            # ── KPI cards ────────────────────────────────────────────────
            kpis = ms_data.get("kpis", [])
            if kpis:
                _ms_chunk_size = 4
                for _ms_start in range(0, len(kpis), _ms_chunk_size):
                    _ms_chunk = kpis[_ms_start:_ms_start + _ms_chunk_size]
                    kpi_cols = st.columns(len(_ms_chunk))
                    for ki, kpi in enumerate(_ms_chunk):
                        delta_str = kpi["delta"].replace("vs prior: ", "")
                        with kpi_cols[ki]:
                            st.metric(label=kpi["name"], value=kpi["val"], delta=delta_str)

            st.divider()

            # ── Style helpers ─────────────────────────────────────────────
            def _s_acos(val):
                try:
                    v = float(val)
                    if v < 30:  return "background-color:#C6EFCE;color:#276221"
                    if v < 60:  return "background-color:#FFEB9C;color:#9C5700"
                    return "background-color:#FFC7CE;color:#9C0006"
                except: return ""

            def _s_margin(val):
                try:
                    v = float(val)
                    if v >= 40: return "background-color:#C6EFCE;color:#276221"
                    if v >= 20: return "background-color:#FFEB9C;color:#9C5700"
                    return "background-color:#FFC7CE;color:#9C0006"
                except: return ""

            def _s_delta(val):
                try:
                    v = float(val)
                    if v > 5:   return "background-color:#C6EFCE;color:#276221"
                    if v < -5:  return "background-color:#FFC7CE;color:#9C0006"
                    return "background-color:#FFEB9C;color:#9C5700"
                except: return ""

            def _s_eff(val):
                vl = str(val).lower()
                if "poor" in vl:              return "background-color:#FFC7CE;color:#9C0006"
                if "good" in vl or "great" in vl: return "background-color:#C6EFCE;color:#276221"
                if "average" in vl:           return "background-color:#FFEB9C;color:#9C5700"
                return ""

            def _s_stock(val):
                vl = str(val).lower()
                if "in stock"  in vl: return "background-color:#C6EFCE;color:#276221"
                if "slow"      in vl: return "background-color:#FFEB9C;color:#9C5700"
                if "no stock"  in vl or "out" in vl or "critical" in vl:
                    return "background-color:#FFC7CE;color:#9C0006"
                if "partial"   in vl: return "background-color:#FFE0B2;color:#BF360C"
                return ""

            if is_pdf:
                # ── Section detection log ──────────────────────────────────
                _slog = ms_data.get("sections_log", [])
                if _slog:
                    _all_ok  = all(ic == "✅" for ic, _, _ in _slog)
                    _has_err = any(ic == "❌" for ic, _, _ in _slog)
                    _exp_icon = "✅" if _all_ok else ("❌" if _has_err else "⚠️")
                    with st.expander(f"{_exp_icon} Secciones detectadas en el PDF ({len(_slog)} analizadas)", expanded=_has_err):
                        for _ic, _sec, _det in _slog:
                            st.markdown(f"{_ic} &nbsp; **{_sec}** — {_det}")

                # ── PDF dashboard ─────────────────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventory & Health", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Productos más vendidos en el período")
                    df = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.dataframe(df, use_container_width=True, hide_index=True)
                    else:
                        st.info("No se encontraron datos de top sellers.")

                with ms_t2:
                    st.warning("⚠️ Advertising no conectado en MerchantSpring")
                    st.info(
                        "Para ver datos de advertising, conectá tu cuenta de Amazon Ads en MerchantSpring:\n\n"
                        "**MerchantSpring → Settings → Integrations → Amazon Advertising**\n\n"
                        "Una vez conectado, los datos aparecerán automáticamente en el próximo reporte."
                    )

                with ms_t3:
                    # Inventario
                    df = ms_data.get("inv_df", pd.DataFrame()).copy()
                    if not df.empty:
                        st.caption("Inventario de productos")
                        style = df.style
                        if "Stock Status" in df.columns:
                            style = style.map(_s_stock, subset=["Stock Status"])
                        st.dataframe(style, use_container_width=True, hide_index=True)
                    st.divider()
                    # P&L métricas
                    pnl_m_tab = ms_data.get("pnl_metrics", {})
                    if pnl_m_tab:
                        m_cols = st.columns(4)
                        for i, (k, v) in enumerate(pnl_m_tab.items()):
                            with m_cols[i]:
                                st.metric(label=k, value=v)
                    pnl_df_tab = ms_data.get("pnl_df", pd.DataFrame())
                    if not pnl_df_tab.empty:
                        st.caption("P&L — Estado de Resultados")
                        st.dataframe(pnl_df_tab, use_container_width=True, hide_index=True)
                    pp_df_tab = ms_data.get("prod_profit_df", pd.DataFrame())
                    if not pp_df_tab.empty:
                        st.caption("Rentabilidad por producto")
                        st.dataframe(pp_df_tab, use_container_width=True, hide_index=True)
                    st.divider()
                    # Health
                    health_tab = ms_data.get("health_data", {})
                    if health_tab:
                        st.caption("Salud del Catálogo")
                        h_cols = st.columns(3)
                        for i, (k, v) in enumerate(health_tab.items()):
                            with h_cols[i % 3]:
                                st.metric(label=k, value=v)

                with ms_t4:
                    st.caption("Comparación semana a semana — Sales y Units disponibles desde PDF. TACoS / Ad Sales / Ad Spend requieren conexión de Amazon Ads.")
                    sum_wow = ms_data.get("summary_df", pd.DataFrame()).copy()
                    if not sum_wow.empty:
                        def _pw(tw, ws):
                            try:
                                p = float(str(ws).replace("%","").replace("+","").strip())
                                d = 1 + p / 100
                                if d == 0: return "-"
                                v = float(str(tw).replace("$","").replace(",","").strip())
                                return round(v / d, 2) if v else "-"
                            except: return "-"
                        wow_rows = []
                        for _, r in sum_wow.iterrows():
                            wow_rows.append({
                                "Product":            r.get("Product",""),
                                "ASIN":               r.get("ASIN",""),
                                "Sales (This Week)":  r.get("Total Sales ($)",""),
                                "Sales (Prior Week)": _pw(r.get("Total Sales ($)",0), r.get("Sales WoW (%)","−")),
                                "Sales Δ %":          r.get("Sales WoW (%)","-"),
                                "Units (This Week)":  r.get("Units Sold",""),
                                "Units (Prior Week)": _pw(r.get("Units Sold",0), r.get("Units WoW (%)","−")),
                                "Units Δ %":          r.get("Units WoW (%)","-"),
                                "Sessions":           "-",
                                "CVR":                "-",
                                "TACoS":              "—",
                                "Ad Sales":           "—",
                                "Organic Sales":      r.get("Total Sales ($)",""),
                                "Ad Spend":           "—",
                                "Profit Δ %":         "-",
                            })
                        wow_display = pd.DataFrame(wow_rows)
                        delta_cols_wow = ["Sales Δ %", "Units Δ %"]
                        style_wow = wow_display.style
                        for dc in delta_cols_wow:
                            if dc in wow_display.columns:
                                style_wow = style_wow.map(_s_delta, subset=[dc])
                        st.dataframe(style_wow, use_container_width=True, hide_index=True)
                    else:
                        st.info("No hay datos de WoW disponibles.")

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_ms_pdf_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export_pdf",
                    use_container_width=True,
                )

            else:
                # ── Excel dashboard (original) ────────────────────────────
                ms_t1, ms_t2, ms_t3, ms_t4 = st.tabs(
                    ["📊 Summary", "📣 Advertising", "📦 Inventario & Salud", "📈 WoW Comparison"]
                )

                with ms_t1:
                    st.caption("Tabla de productos — resumen de la semana analizada")
                    df = ms_data["summary_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "TACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["TACoS (%)"])
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t2:
                    st.caption("Análisis de publicidad por producto")
                    df = ms_data["adv_df"].copy()
                    style = df.style
                    if "ACoS (%)" in df.columns:
                        style = style.map(_s_acos, subset=["ACoS (%)"])
                    if "Ad Efficiency" in df.columns:
                        style = style.map(_s_eff, subset=["Ad Efficiency"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t3:
                    st.caption("Inventario y salud del producto")
                    df = ms_data["inv_df"].copy()
                    style = df.style
                    if "Profit Margin %" in df.columns:
                        style = style.map(_s_margin, subset=["Profit Margin %"])
                    if "Stock Status" in df.columns:
                        style = style.map(_s_stock, subset=["Stock Status"])
                    st.dataframe(style, use_container_width=True, hide_index=True)

                with ms_t4:
                    st.caption("Comparación semana a semana por producto")
                    df = ms_data["wow_df"].copy()
                    delta_cols = [c for c in df.columns if c.endswith("|Δ %")]
                    style = df.style
                    if delta_cols:
                        style = style.map(_s_delta, subset=delta_cols)
                    st.dataframe(style, use_container_width=True, hide_index=True)

                # ── Export ─────────────────────────────────────────────────
                st.divider()
                client_for_excel = ms_client or ms_data.get("title", "MerchanSpring")
                ms_buf = _build_merchanspring_excel(ms_data, client_name=client_for_excel)
                safe_ms = client_for_excel.replace(" ", "_").replace("/", "-")[:30]
                st.download_button(
                    label="⬇️ Descargar informe Excel profesional (4 hojas)",
                    data=ms_buf.getvalue(),
                    file_name=f"merchanspring_{safe_ms}.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="ms_export",
                    use_container_width=True,
                )

        except Exception as e:
            st.error(f"Error al procesar el archivo: {e}")
            import traceback
            st.code(traceback.format_exc())