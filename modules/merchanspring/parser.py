import re

import pandas as pd


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
