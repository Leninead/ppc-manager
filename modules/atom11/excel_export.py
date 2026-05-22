import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.i18n import _I18N
from modules.atom11.analysis import _diag_items, _rec_items


def _build_atom11_excel(display_df, kc, kp, tipo, per_c, per_p, delta_cols,
                        client_name="", entity_col="", top_rows=None, lang="es",
                        parent_evo_df=None):
    """Build a professional 3-sheet Excel report. No formula-causing characters."""

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
