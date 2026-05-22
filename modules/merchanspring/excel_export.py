import io

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Border, Side, Alignment
from openpyxl.utils import get_column_letter


def _build_ms_pdf_excel(data, client_name=""):
    """Generate a 4-sheet Excel matching NorseTradesman structure from parsed MerchantSpring PDF."""

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

    # Column spec: (header, width, fmt, is_delta, is_orange_group)
    WOW_COLS = [
        ("Product",                  42, "@",        False, False),
        ("ASIN",                     14, "@",        False, False),
        ("Sales TW",                 13, "$#,##0.00",False, False),
        ("Sales PW",                 13, "$#,##0.00",False, False),
        ("Sales \u0394%",            10, "0.0",      True,  False),
        ("Units TW",                 10, "#,##0",    False, False),
        ("Units PW",                 10, "#,##0",    False, False),
        ("Units \u0394%",            10, "0.0",      True,  False),
        ("Sessions TW",              12, "#,##0",    False, False),
        ("Sessions PW",              12, "#,##0",    False, False),
        ("Sessions \u0394%",         10, "0.0",      True,  False),
        ("CVR TW",                   10, "0.0%",     False, False),
        ("CVR PW",                   10, "0.0%",     False, False),
        ("CVR \u0394%",              10, "0.0",      True,  False),
        ("BuyBox %",                 10, "0.0%",     False, False),
        ("Ad Sales TW",              13, "$#,##0.00",False, True),
        ("Ad Sales PW",              13, "$#,##0.00",False, True),
        ("Ad Sales \u0394%",         10, "0.0",      True,  True),
        ("Ad Spend TW",              13, "$#,##0.00",False, True),
        ("Ad Spend PW",              13, "$#,##0.00",False, True),
        ("Ad Spend \u0394%",         10, "0.0",      True,  True),
        ("ACoS",                     10, "0.0%",     False, True),
        ("TACoS",                    10, "0.0%",     False, True),
        ("Contrib. Margin ($)",      15, "$#,##0.00",False, False),
        ("Contrib. Margin (%)",      15, "0.0%",     False, False),
        ("Profit %",                 10, "0.0%",     False, False),
    ]
    n4 = len(WOW_COLS)
    _title_block(ws4, title, period, n4)

    # Group header row (row 3): merge groups
    GRP_SPANS = [
        ("",         1, 2,  False),
        ("SALES",    3, 5,  False),
        ("UNITS",    6, 8,  False),
        ("SESSIONS", 9, 11, False),
        ("CVR",      12, 14, False),
        ("BUYBOX",   15, 15, False),
        ("AD SALES", 16, 18, True),
        ("AD SPEND", 19, 21, True),
        ("ACOS/TACOS",22, 23, True),
        ("MARGIN & PROFIT", 24, 26, False),
    ]
    ws4.row_dimensions[3].height = 16
    for grp_name, c_start, c_end, is_orange in GRP_SPANS:
        if not grp_name:
            continue
        grp_fill = ORG_L if is_orange else DGRAY
        grp_fc   = ORG_D if is_orange else WHITE
        if c_end > c_start:
            ws4.merge_cells(start_row=3, start_column=c_start, end_row=3, end_column=c_end)
        c = ws4.cell(row=3, column=c_start, value=grp_name)
        c.fill = _fill(grp_fill); c.font = _font(True, grp_fc, 9)
        c.alignment = _al("center"); c.border = _bd()

    # Row 4: column headers
    _hdr(ws4, 4, [col[0] for col in WOW_COLS])

    # Column widths
    for ci_w, (_, w, *_rest) in enumerate(WOW_COLS, 1):
        ws4.column_dimensions[get_column_letter(ci_w)].width = w

    # ── Build row data from tc_parent_df + prod_profit_df + adv data ─────
    tc_df     = data.get("tc_parent_df", pd.DataFrame())
    pp_df     = data.get("prod_profit_df", pd.DataFrame())
    adv_sum   = data.get("adv_summary", {})
    adv_df    = data.get("adv_df", pd.DataFrame())
    pnl_met   = data.get("pnl_metrics", {})

    # Build profit lookup by product name (fuzzy — first 30 chars)
    profit_lookup = {}
    if not pp_df.empty:
        for _, prow in pp_df.iterrows():
            pname = str(prow.get("Product", ""))[:30].lower().strip()
            if pname:
                profit_lookup[pname] = prow

    # Build ad lookup by ASIN if available
    ad_lookup = {}
    if not adv_df.empty and "ASIN" in adv_df.columns:
        for _, arow in adv_df.iterrows():
            asin = str(arow.get("ASIN", "")).strip()
            if asin and asin != "-":
                ad_lookup[asin] = arow

    data_start_row = 5
    n_rows = 0

    if not tc_df.empty:
        tc_df = tc_df.reset_index(drop=True)
        has_wow = "Rev WoW (%)" in tc_df.columns

        # Totals accumulators
        t_sales_tw = 0; t_sales_pw = 0
        t_units_tw = 0; t_units_pw = 0
        t_pv_tw = 0;    t_pv_pw = 0
        t_ad_sales = 0;  t_ad_spend = 0
        t_cm = 0;        t_shipped = 0

        for ri in range(len(tc_df)):
            rn  = data_start_row + ri
            row = tc_df.iloc[ri]
            ws4.row_dimensions[rn].height = 15
            row_bg = WHITE if ri % 2 == 0 else LGRAY

            product = str(row.get("Product", ""))
            # Try to extract ASIN from product name or from the ASIN field
            asin_val = str(row.get("ASIN", "")) if "ASIN" in tc_df.columns else "-"

            # Parse numeric values
            rev_tw  = _num(row.get("Ordered Revenue", 0)) or 0
            units_tw = _num(row.get("Ordered Units", 0)) or 0
            pv_tw    = _num(row.get("Page Views", 0)) or 0
            conv_tw  = _num(str(row.get("Conversion", "0")).replace("%", "")) or 0
            bb_pct   = _num(str(row.get("Buybox Win %", "0")).replace("%", "")) or 0

            # Prior period from WoW deltas
            rev_wow  = _parse_wow_pct(row.get("Rev WoW (%)", "-")) if has_wow else None
            units_wow = _parse_wow_pct(row.get("Units WoW (%)", "-")) if has_wow else None
            pv_wow   = _parse_wow_pct(row.get("PV WoW (%)", "-")) if has_wow else None

            rev_pw   = _calc_prior(rev_tw, row.get("Rev WoW (%)", "-")) if has_wow else "-"
            units_pw = _calc_prior(units_tw, row.get("Units WoW (%)", "-")) if has_wow else "-"
            pv_pw    = _calc_prior(pv_tw, row.get("PV WoW (%)", "-")) if has_wow else "-"

            # CVR prior: derive from prior sessions and units
            cvr_pw = None
            if isinstance(pv_pw, (int, float)) and pv_pw > 0 and isinstance(units_pw, (int, float)):
                cvr_pw = units_pw / pv_pw * 100
            cvr_delta = (conv_tw - cvr_pw) if cvr_pw is not None else None

            # Ad data for this product
            ad_row = ad_lookup.get(asin_val)
            ad_sales_tw = _num(ad_row.get("Ad Sales", 0)) if ad_row is not None else None
            ad_spend_tw = _num(ad_row.get("Spend", 0)) if ad_row is not None else None
            acos_val = None
            if ad_sales_tw and ad_sales_tw > 0 and ad_spend_tw is not None:
                acos_val = ad_spend_tw / ad_sales_tw * 100
            tacos_val = None
            if rev_tw > 0 and ad_spend_tw is not None:
                tacos_val = ad_spend_tw / rev_tw * 100

            # Profit data
            p_key = product[:30].lower().strip()
            p_row = profit_lookup.get(p_key)
            shipped   = _num(p_row.get("Shipped Sales ($)", 0)) if p_row is not None else None
            sell_fees = _num(p_row.get("Selling Fees ($)", 0)) if p_row is not None else None
            fulfil    = _num(p_row.get("Fulfilment ($)", 0)) if p_row is not None else None
            ad_cost   = ad_spend_tw if ad_spend_tw else 0
            cm = None; cm_pct = None; profit_pct_val = None
            if shipped is not None and sell_fees is not None and fulfil is not None:
                cm = shipped - (abs(sell_fees) + abs(fulfil) + abs(ad_cost))
                cm_pct = (cm / shipped * 100) if shipped > 0 else 0
            profit_val = _num(p_row.get("Profit ($)", 0)) if p_row is not None else None
            if profit_val is not None and shipped and shipped > 0:
                profit_pct_val = profit_val / shipped * 100

            # Accumulate totals
            t_sales_tw += rev_tw
            t_units_tw += int(units_tw)
            t_pv_tw    += int(pv_tw)
            if isinstance(rev_pw, (int, float)): t_sales_pw += rev_pw
            if isinstance(units_pw, (int, float)): t_units_pw += int(units_pw)
            if isinstance(pv_pw, (int, float)): t_pv_pw += int(pv_pw)
            if ad_sales_tw: t_ad_sales += ad_sales_tw
            if ad_spend_tw: t_ad_spend += ad_spend_tw
            if cm is not None: t_cm += cm
            if shipped: t_shipped += shipped

            # Write cells
            vals = [
                product, asin_val,
                rev_tw, rev_pw if isinstance(rev_pw, (int, float)) else "-", rev_wow,
                int(units_tw), units_pw if isinstance(units_pw, (int, float)) else "-", units_wow,
                int(pv_tw), pv_pw if isinstance(pv_pw, (int, float)) else "-", pv_wow,
                conv_tw / 100 if conv_tw else 0, (cvr_pw / 100) if cvr_pw is not None else "-", cvr_delta,
                bb_pct / 100 if bb_pct else 0,
                ad_sales_tw if ad_sales_tw else "-", "-", "-",
                ad_spend_tw if ad_spend_tw else "-", "-", "-",
                (acos_val / 100) if acos_val is not None else "-",
                (tacos_val / 100) if tacos_val is not None else "-",
                cm if cm is not None else "-",
                (cm_pct / 100) if cm_pct is not None else "-",
                (profit_pct_val / 100) if profit_pct_val is not None else "-",
            ]

            for ci, ((_hdr_name, _w, fmt, is_delta, _is_orn), val) in enumerate(zip(WOW_COLS, vals), 1):
                bg4, fg4 = row_bg, "000000"
                if is_delta and isinstance(val, (int, float)):
                    if val > 5:    bg4, fg4 = GRN_L, GRN_D
                    elif val < -5: bg4, fg4 = RED_L, RED_D
                    else:          bg4, fg4 = YEL_L, YEL_D
                display = val if val != "-" else "-"
                _cell(ws4, rn, ci, display, bg=bg4, fg=fg4,
                      fmt=fmt if val != "-" else None,
                      left=(ci <= 2))

        n_rows = len(tc_df)

        # ── TOTALS row ──────────────────────────────────────────────────
        tot_rn = data_start_row + n_rows
        ws4.row_dimensions[tot_rn].height = 18

        sales_delta_tot = ((t_sales_tw - t_sales_pw) / t_sales_pw * 100) if t_sales_pw > 0 else "-"
        units_delta_tot = ((t_units_tw - t_units_pw) / t_units_pw * 100) if t_units_pw > 0 else "-"
        pv_delta_tot    = ((t_pv_tw - t_pv_pw) / t_pv_pw * 100) if t_pv_pw > 0 else "-"
        cvr_tw_tot      = (t_units_tw / t_pv_tw * 100) if t_pv_tw > 0 else 0
        cvr_pw_tot      = (t_units_pw / t_pv_pw * 100) if t_pv_pw > 0 else 0
        cvr_d_tot       = cvr_tw_tot - cvr_pw_tot if cvr_pw_tot else "-"
        acos_tot        = (t_ad_spend / t_ad_sales * 100) if t_ad_sales > 0 else "-"
        tacos_tot       = (t_ad_spend / t_sales_tw * 100) if t_sales_tw > 0 else "-"
        cm_pct_tot      = (t_cm / t_shipped * 100) if t_shipped > 0 else "-"
        profit_pct_str  = pnl_met.get("Profit %", "-")
        profit_pct_tot  = _num(str(profit_pct_str).replace("%", ""))

        tot_vals = [
            "TOTALS", "",
            t_sales_tw, t_sales_pw if t_sales_pw else "-", sales_delta_tot,
            t_units_tw, t_units_pw if t_units_pw else "-", units_delta_tot,
            t_pv_tw, t_pv_pw if t_pv_pw else "-", pv_delta_tot,
            cvr_tw_tot / 100 if cvr_tw_tot else 0, cvr_pw_tot / 100 if cvr_pw_tot else "-", cvr_d_tot,
            "-",
            t_ad_sales if t_ad_sales else "-", "-", "-",
            t_ad_spend if t_ad_spend else "-", "-", "-",
            (acos_tot / 100) if isinstance(acos_tot, (int, float)) else "-",
            (tacos_tot / 100) if isinstance(tacos_tot, (int, float)) else "-",
            t_cm if t_cm else "-",
            (cm_pct_tot / 100) if isinstance(cm_pct_tot, (int, float)) else "-",
            (profit_pct_tot / 100) if profit_pct_tot is not None else "-",
        ]

        for ci, ((_hdr_name, _w, fmt, is_delta, _is_orn), val) in enumerate(zip(WOW_COLS, tot_vals), 1):
            bg4, fg4 = NAVY, WHITE
            if is_delta and isinstance(val, (int, float)):
                if val > 5:    bg4, fg4 = GRN_L, GRN_D
                elif val < -5: bg4, fg4 = RED_L, RED_D
                else:          bg4, fg4 = YEL_L, YEL_D
            _cell(ws4, tot_rn, ci, val if val != "-" else "-", bg=bg4, fg=fg4,
                  bold=True, fmt=fmt if val != "-" else None, left=(ci == 1))

        n_rows += 1

    else:
        _no_data_row(ws4, data_start_row, n4,
                     "No traffic data available — tc_parent_df is empty")

    # Note row
    note_rn = data_start_row + n_rows + 1
    ws4.merge_cells(start_row=note_rn, start_column=1, end_row=note_rn, end_column=n4)
    nc = ws4.cell(row=note_rn, column=1,
                  value="* Ad Sales PW / Ad Spend PW require historical ad data. Contribution Margin = Shipped Sales - Selling Fees - Fulfilment - Ad Spend.")
    nc.fill = _fill(YEL_L); nc.font = _font(False, YEL_D, 8)
    nc.alignment = Alignment(horizontal="left", vertical="center", wrap_text=True)
    ws4.row_dimensions[note_rn].height = 20
    ws4.freeze_panes = "C5"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _build_merchanspring_excel(data, client_name=""):
    """Generate professional MerchanSpring-style Excel with 4 sheets."""

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
