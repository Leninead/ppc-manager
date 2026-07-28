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

    Every section is wrapped in try/except so one broken section never crashes
    the whole parse. sections_log reports what was found and what failed.
    """
    import pdfplumber
    import warnings
    warnings.filterwarnings("ignore")

    with pdfplumber.open(file) as pdf:
        pages = [page.extract_text() or "" for page in pdf.pages]

    full_text  = "\n".join(pages)
    result     = {}
    slog       = []   # [(icon, section_name, detail)]

    # Pre-init accumulators used across sections
    top_sellers   = []
    worst_sellers = []
    adv_sum_m     = None   # used by Advertising Products section

    # ── Shared helpers ──────────────────────────────────────────────────────

    _ASIN_SKU_RE = re.compile(r'ASIN:\s*(\w+)\s*\|\s*SKU:\s*(.+)')
    _ASIN_ONLY_RE = re.compile(r'ASIN:\s*([A-Z0-9]{10})')
    _SKIP_PREFIXES = ('ASIN:', 'http', '3/')

    def _product_blocks(text, data_re, asin_re=None):
        """Walk lines in triplets: product-name / data-line / ASIN-line."""
        if asin_re is None:
            asin_re = _ASIN_SKU_RE
        out, lines, i = [], text.split('\n'), 0
        while i < len(lines):
            ln = lines[i].strip()
            if not ln or any(ln.startswith(p) for p in _SKIP_PREFIXES):
                i += 1; continue
            if i + 2 < len(lines):
                dm = data_re.match(lines[i + 1].strip())
                am = asin_re.match(lines[i + 2].strip())
                if dm and am:
                    asin = am.group(1).strip()
                    sku  = am.group(2).strip() if am.lastindex and am.lastindex >= 2 else ""
                    out.append((ln, dm, asin, sku))
                    i += 3; continue
            i += 1
        return out

    def _fval(s):
        try: return float(str(s).replace("$", "").replace(",", ""))
        except: return None

    def _slog_df(rows, section_m, section_name):
        """Standard slog entry for a table section."""
        if rows:
            slog.append(("✅", section_name, f"{len(rows)} rows"))
        elif section_m:
            slog.append(("⚠️", section_name, "Section found but no rows matched"))
        else:
            slog.append(("❌", section_name, "Section not found"))

    # ── Title & period ──────────────────────────────────────────────────────
    try:
        title_m = re.search(r'^(WoW .+)$', full_text, re.MULTILINE)
        result["title"] = title_m.group(1).strip() if title_m else "MerchanSpring Report"

        period_m   = re.search(r'Time period:\s*(.+)',      full_text)
        comp_m     = re.search(r'Comparison period:\s*(.+)', full_text)
        period_str = period_m.group(1).strip() if period_m else ""
        comp_str   = comp_m.group(1).strip()   if comp_m   else ""
        result["period"] = f"{period_str}  vs  {comp_str}" if comp_str else period_str
        slog.append(("✅" if period_str else "⚠️", "Header / Period",
                     period_str if period_str else "Not detected"))
    except Exception as _exc:
        result.setdefault("title", "MerchanSpring Report")
        result.setdefault("period", "")
        slog.append(("❌", "Header / Period", f"Parse error: {_exc}"))

    # ── KPIs ────────────────────────────────────────────────────────────────
    try:
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
    except Exception as _exc:
        result.setdefault("kpis", [])
        slog.append(("❌", "KPI Summary", f"Parse error: {_exc}"))

    # ── Traffic and conversion summary (overall) ────────────────────────────
    try:
        tc_sum_m = re.search(
            r'Traffic and conversion summary\b(.*?)(?=Traffic and conversion by product|Top sellers|Worst sellers|P&L|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        traffic_summary = {}
        if tc_sum_m:
            tsb = tc_sum_m.group(1)
            def _tc_metric(text, val_pat, is_ppt=False):
                vm = re.search(val_pat, text, re.IGNORECASE)
                if not vm: return "-", "-"
                val = vm.group(1)
                window = text[vm.end(): vm.end() + 200]
                if is_ppt:
                    dm = re.search(r'([\+\-]?\d+(?:\.\d+)?\s*ppt)', window, re.IGNORECASE)
                else:
                    dm = re.search(r'([\+\-]\d+(?:\.\d+)?%)', window)
                return val, (dm.group(1) if dm else "-")

            for key, pat, is_ppt in [
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
            ]:
                val, delta = _tc_metric(tsb, pat, is_ppt)
                traffic_summary[key] = val
                traffic_summary[key + " delta"] = delta
        result["traffic_summary"] = traffic_summary
        _ts_found = sum(1 for k, v in traffic_summary.items() if not k.endswith(" delta") and v != "-")
        slog.append(("✅" if _ts_found > 0 else "❌",
                     "Traffic & Conversion Summary",
                     f"{_ts_found} metrics found" if _ts_found > 0 else "Section not found"))
    except Exception as _exc:
        result.setdefault("traffic_summary", {})
        slog.append(("❌", "Traffic & Conversion Summary", f"Parse error: {_exc}"))

    # ── Top sellers ─────────────────────────────────────────────────────────
    try:
        top_sec_m = re.search(
            r'(?:Top sellers\b|PRODUCT\s+SALES\s+UNITS SOLD\s+INVENTORY)(.*?)(?=\nWorst sellers|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        top_section = top_sec_m.group(1) if top_sec_m else ""
        top_pat = re.compile(
            r'^(\$[\d,\.]+)\s+([\-\+\d]+%|-)\s+(\d+)\s+([\-\+\d]+%|-)\s+([\d,]+)\s*in\s*stock$',
            re.IGNORECASE
        )
        for name, dm, asin, sku in _product_blocks(top_section, top_pat):
            try:
                sales_val = float(dm.group(1).replace("$", "").replace(",", ""))
                inv_val   = int(dm.group(5).replace(",", ""))
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
        _slog_df(top_sellers, top_sec_m, "Top Sellers")
    except Exception as _exc:
        slog.append(("❌", "Top Sellers", f"Parse error: {_exc}"))

    # ── Worst sellers ───────────────────────────────────────────────────────
    try:
        worst_sec_m = re.search(
            r'Worst sellers.*?(?:LAST SALE|INVENTORY)\s*\n(.*?)(?=\nAdvertising performance|\nP&L|\nProfit|\nParent products|\nSales performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        worst_section = worst_sec_m.group(1) if worst_sec_m else ""
        worst_pat = re.compile(r'^(\d+\+?)\s+(?:.*?)?([\d,]+)\s*in\s*stock$', re.IGNORECASE)
        for name, dm, asin, sku in _product_blocks(worst_section, worst_pat):
            try:
                inv_val = int(dm.group(2).replace(",", ""))
            except:
                inv_val = 0
            worst_sellers.append({
                "Product":              name,
                "ASIN":                 asin,
                "Days Since Last Sale": dm.group(1),
                "Inventory":            inv_val,
            })
        _slog_df(worst_sellers, worst_sec_m, "Worst Sellers")
    except Exception as _exc:
        slog.append(("❌", "Worst Sellers", f"Parse error: {_exc}"))

    # ── Parent Products ─────────────────────────────────────────────────────
    try:
        parent_prod_m = re.search(
            r'Parent products\b.*?(?:PARENTS|PARENT)\s+SALES\s+UNITS\s+SOLD\s+AVG\.?\s*UNIT\s*PRICE\s*\n(.*?)(?=\nTop products|\nTop sellers|\nWorst sellers|\nAdvertising|\nChild products|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        parent_products = []
        if parent_prod_m:
            pp_block = parent_prod_m.group(1)
            pp_lines = pp_block.split('\n')
            i = 0
            while i < len(pp_lines):
                ln = pp_lines[i].strip()
                if not ln or ln.startswith('http') or ln.startswith('3/'):
                    i += 1; continue
                if i + 2 < len(pp_lines):
                    data_m = re.match(
                        r'^(-?[\$\d,\.]+)\s+([\-\+\d]+%|-)\s+(\d+)\s+([\-\+\d]+%|-)\s+(-?[\$\d,\.]+)\s+([\-\+\d]+%|-)\s*$',
                        pp_lines[i + 1].strip()
                    )
                    asin_m = re.match(r'([A-Z0-9]{10})\s*\|\s*(\d+)\s*SKUs?\s*\|\s*(.+)', pp_lines[i + 2].strip())
                    if data_m and asin_m:
                        parent_products.append({
                            "Product":            ln,
                            "Parent ASIN":        asin_m.group(1),
                            "SKUs":               int(asin_m.group(2)),
                            "Brand":              asin_m.group(3).strip(),
                            "Sales ($)":          _fval(data_m.group(1)),
                            "Sales WoW (%)":      data_m.group(2),
                            "Units Sold":         int(data_m.group(3)) if data_m.group(3).isdigit() else 0,
                            "Units WoW (%)":      data_m.group(4),
                            "Avg Unit Price ($)": _fval(data_m.group(5)),
                            "Price WoW (%)":      data_m.group(6),
                        })
                        i += 3; continue
                i += 1
        result["parent_products_df"] = pd.DataFrame(parent_products) if parent_products else pd.DataFrame()
        _slog_df(parent_products, parent_prod_m, "Parent Products")
    except Exception as _exc:
        result["parent_products_df"] = pd.DataFrame()
        slog.append(("❌", "Parent Products", f"Parse error: {_exc}"))

    # ── P&L / Channel profit ───────────────────────────────────────────────
    try:
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
        for display_name, key in pnl_items:
            val = _pnl_val(pnl_text, key)
            if val != "-":
                pnl_found += 1
            pct_m = re.search(
                rf'{re.escape(key)}\s+(?:-?[\$\d,\.]+|-)\s+(-?[\d\.]+%|-)', pnl_text, re.IGNORECASE
            )
            pnl_rows.append({"Item": display_name, "Amount ($)": val,
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
                     f"{pnl_found} line items found" if pnl_found > 0 else "Section not found"))
    except Exception as _exc:
        result.setdefault("pnl_df", pd.DataFrame())
        result.setdefault("pnl_metrics", {})
        slog.append(("❌", "P&L", f"Parse error: {_exc}"))

    # ── Product-level profitability ─────────────────────────────────────────
    try:
        prod_sec_m = re.search(
            r'(?:Product-level profitability\b.*?\n|PRODUCT\s+SHIPPED PRODUCT SALES.*?\n)(.*?)(?=HEALTH STATUS|ACTIVE PRODUCTS|Seller health|Advertising performance|Buy Box|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        prod_section = prod_sec_m.group(1) if prod_sec_m else ""
        prod_pat = re.compile(
            r'^(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(-?[\$\d,\.]+|-)\s+(\d+)$'
        )
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
        _slog_df(prod_profit, prod_sec_m, "Product Profitability")
    except Exception as _exc:
        result["prod_profit_df"] = pd.DataFrame()
        slog.append(("❌", "Product Profitability", f"Parse error: {_exc}"))

    # ── Seller health / Health status ───────────────────────────────────────
    try:
        health_block_m = re.search(
            r'(?:HEALTH STATUS|Seller health)\b(.*?)(?=Traffic and conversion|Top sellers|Worst sellers|Advertising|Policy compliance|\Z)',
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
                     "Catalog health metrics found" if health_found else "Section not found"))
    except Exception as _exc:
        result["health_data"] = {}
        slog.append(("❌", "Health Status", f"Parse error: {_exc}"))

    # ── Traffic and conversion by product – Parent ──────────────────────────
    try:
        tc_parent_m = re.search(
            r'Traffic and conversion by product\s*[-\u2013]?\s*Parent\b(.*?)(?=Traffic and conversion by product\s*[-\u2013]?\s*Child|Cancellations|Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        tc_parent_rows = []
        if tc_parent_m:
            tc_block = tc_parent_m.group(1)
            # Extended regex: PV PV_wow% Rev Rev_wow% Units Units_wow% Conv Conv_delta BB BB_delta
            tc_row_ext = re.compile(
                r'^(.+?)\s+([\d,]+)\s+([\-\+\d]+%|\+?\d+%|-)\s+(-?[\$\d,\.]+)\s+([\-\+\d]+%|-)\s+(\d+)\s+([\-\+\d]+%|-)\s+([\d\.]+%)\s+([\d\.]+\s*ppt|-)\s+([\d\.]+%)\s+([\d\.]+\s*ppt|-)',
                re.MULTILINE
            )
            # Fallback: 6-group (original)
            tc_row_base = re.compile(
                r'^(.+?)\s+([\d,]+)\s+(-?[\$\d,\.]+)\s+(\d+)\s+([\d\.]+%)\s+([\d\.]+%)',
                re.MULTILINE
            )
            for m in tc_row_ext.finditer(tc_block):
                tc_parent_rows.append({
                    "Product":          m.group(1).strip(),
                    "Page Views":       m.group(2),
                    "PV WoW (%)":       m.group(3),
                    "Ordered Revenue":  m.group(4),
                    "Rev WoW (%)":      m.group(5),
                    "Ordered Units":    m.group(6),
                    "Units WoW (%)":    m.group(7),
                    "Conversion":       m.group(8),
                    "Conv Delta":       m.group(9),
                    "Buybox Win %":     m.group(10),
                    "BB Delta":         m.group(11),
                })
            if not tc_parent_rows:
                for m in tc_row_base.finditer(tc_block):
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
        _slog_df(tc_parent_rows, tc_parent_m, "Traffic by Product - Parent")
    except Exception as _exc:
        result["tc_parent_df"] = pd.DataFrame()
        result["traffic_by_product_parent_df"] = pd.DataFrame()
        slog.append(("❌", "Traffic by Product - Parent", f"Parse error: {_exc}"))

    # ── Traffic and conversion by product – Child ───────────────────────────
    try:
        tc_child_m = re.search(
            r'Traffic and conversion by product\s*[-\u2013]?\s*Child\b(.*?)(?=Cancellations|Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        tc_child_rows = []
        if tc_child_m:
            tc_block = tc_child_m.group(1)
            tc_row_ext = re.compile(
                r'^(.+?)\s+([\d,]+)\s+([\-\+\d]+%|\+?\d+%|-)\s+(-?[\$\d,\.]+)\s+([\-\+\d]+%|-)\s+(\d+)\s+([\-\+\d]+%|-)\s+([\d\.]+%)\s+([\d\.]+\s*ppt|-)\s+([\d\.]+%)\s+([\d\.]+\s*ppt|-)',
                re.MULTILINE
            )
            tc_row_base = re.compile(
                r'^(.+?)\s+([\d,]+)\s+(-?[\$\d,\.]+)\s+(\d+)\s+([\d\.]+%)\s+([\d\.]+%)',
                re.MULTILINE
            )
            for m in tc_row_ext.finditer(tc_block):
                tc_child_rows.append({
                    "Product":         m.group(1).strip(),
                    "Page Views":      m.group(2),
                    "PV WoW (%)":      m.group(3),
                    "Ordered Revenue": m.group(4),
                    "Rev WoW (%)":     m.group(5),
                    "Ordered Units":   m.group(6),
                    "Units WoW (%)":   m.group(7),
                    "Conversion":      m.group(8),
                    "Conv Delta":      m.group(9),
                    "Buybox Win %":    m.group(10),
                    "BB Delta":        m.group(11),
                })
            if not tc_child_rows:
                for m in tc_row_base.finditer(tc_block):
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
        _slog_df(tc_child_rows, tc_child_m, "Traffic by Product - Child")
    except Exception as _exc:
        result["tc_child_df"] = pd.DataFrame()
        result["traffic_by_product_child_df"] = pd.DataFrame()
        slog.append(("❌", "Traffic by Product - Child", f"Parse error: {_exc}"))

    # ── Cancellations and Refunds Summary ───────────────────────────────────
    try:
        def _cr_val(text, label):
            m = re.search(rf'{re.escape(label)}\s+(-?[\$\d,\.]+%?|-)', text, re.IGNORECASE)
            return m.group(1) if m else "-"

        cr_m = re.search(
            r'Cancellations and Refunds Summary(.*?)(?=Cancellations and Refunds Performance|Sales by category|Sales by country|Sales by brand|Top products|Review status|Advertising performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        cr_data = {}
        if cr_m:
            cr_block = cr_m.group(1)
            for lbl in ["Gross Sales", "Net Sales", "Cancelled Sales", "Refunded Sales", "Cancel Rate", "Refund Rate"]:
                cr_data[lbl] = _cr_val(cr_block, lbl)
        result["cancellations_data"] = cr_data
        result["cancellations_summary"] = cr_data
        _n_cr = sum(1 for v in cr_data.values() if v != '-')
        slog.append(("✅" if _n_cr > 0 else "❌", "Cancellations & Refunds Summary",
                     f"{_n_cr} metrics found" if cr_data else "Section not found"))
    except Exception as _exc:
        result["cancellations_data"] = {}
        result["cancellations_summary"] = {}
        slog.append(("❌", "Cancellations & Refunds Summary", f"Parse error: {_exc}"))

    # ── Cancellations by Product ────────────────────────────────────────────
    try:
        cr_prod_m = re.search(
            r'Cancellations and Refunds Performance by Product\b.*?(?:REFUND RATE\s*(?:\(UNITS\))?\s*\n)(.*?)(?=\nSales performance|\nParent products|\nSales by category|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        cr_prod_rows = []
        if cr_prod_m:
            crp_block = cr_prod_m.group(1)
            crp_pat = re.compile(r'^(-?[\$\d,\.]+%?|-)\s+(-?[\$\d,\.]+%?|-)\s+(-?[\$\d,\.]+%?|-)\s+(-?[\$\d,\.]+%?|-)\s+(-?[\$\d,\.]+%?|-)\s+(-?[\$\d,\.]+%?|-)$')
            for name, dm, asin, sku in _product_blocks(crp_block, crp_pat):
                cr_prod_rows.append({
                    "Product":           name,
                    "ASIN":              asin,
                    "Cancelled Revenue": dm.group(1),
                    "Cancel Rate":       dm.group(2),
                    "Refunded Revenue":  dm.group(3),
                    "Refund Rate":       dm.group(4),
                    "Refunded Units":    dm.group(5),
                    "Refund Rate (Units)": dm.group(6),
                })
        result["cancellations_by_product_df"] = pd.DataFrame(cr_prod_rows) if cr_prod_rows else pd.DataFrame()
        _slog_df(cr_prod_rows, cr_prod_m, "Cancellations by Product")
    except Exception as _exc:
        result["cancellations_by_product_df"] = pd.DataFrame()
        slog.append(("❌", "Cancellations by Product", f"Parse error: {_exc}"))

    # ── Sales by category ───────────────────────────────────────────────────
    try:
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
        _slog_df(cat_rows, cat_m, "Sales by Category")
    except Exception as _exc:
        result["sales_by_category_df"] = pd.DataFrame()
        slog.append(("❌", "Sales by Category", f"Parse error: {_exc}"))

    # ── Sales by country ────────────────────────────────────────────────────
    try:
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
        _slog_df(cty_rows, cty_m, "Sales by Country")
    except Exception as _exc:
        result["sales_by_country_df"] = pd.DataFrame()
        slog.append(("❌", "Sales by Country", f"Parse error: {_exc}"))

    # ── Sales by brand ──────────────────────────────────────────────────────
    try:
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
        _slog_df(brand_rows, brand_m, "Sales by Brand")
    except Exception as _exc:
        result["sales_by_brand_df"] = pd.DataFrame()
        slog.append(("❌", "Sales by Brand", f"Parse error: {_exc}"))

    # ── Top products by BSR ─────────────────────────────────────────────────
    try:
        bsr_m = re.search(
            r'Top products by BSR\b(.*?)(?=Review status|Advertising performance|Shipping performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        bsr_rows = []
        if bsr_m:
            bsr_block = bsr_m.group(1)
            bsr_re = re.compile(r'^(.+?)\s+#?([\d,]+)\s+(-?[\$\d,\.]+)\s+([\d,]+)', re.MULTILINE)
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
        _slog_df(bsr_rows, bsr_m, "Top Products by BSR")
    except Exception as _exc:
        result["top_bsr_df"] = pd.DataFrame()
        slog.append(("❌", "Top Products by BSR", f"Parse error: {_exc}"))

    # ── Review status ───────────────────────────────────────────────────────
    try:
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
    except Exception as _exc:
        result["review_data"] = {}
        result["review_status"] = {}
        slog.append(("❌", "Review Status", f"Parse error: {_exc}"))

    # ── Advertising performance summary ─────────────────────────────────────
    try:
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
    except Exception as _exc:
        result["adv_summary"] = {}
        slog.append(("❌", "Advertising Performance Summary", f"Parse error: {_exc}"))

    # ── Advertising performance by campaign type ────────────────────────────
    try:
        adv_type_m = re.search(
            r'Advertising performance by campaign type\b(.*?)(?=Advertising campaign performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        adv_type_rows = []
        if adv_type_m:
            atb = adv_type_m.group(1)
            for ctype in ["Sponsored Products", "Sponsored Brands", "Sponsored Display"]:
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
        _slog_df(adv_type_rows, adv_type_m, "Advertising by Campaign Type")
    except Exception as _exc:
        result["adv_by_type_df"] = pd.DataFrame()
        slog.append(("❌", "Advertising by Campaign Type", f"Parse error: {_exc}"))

    # ── Advertising campaign performance ────────────────────────────────────
    try:
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
        _slog_df(campaigns_rows, adv_camp_m, "Advertising Campaign Performance")
    except Exception as _exc:
        result["campaigns_df"] = pd.DataFrame()
        slog.append(("❌", "Advertising Campaign Performance", f"Parse error: {_exc}"))

    # ── Top performing product ads ──────────────────────────────────────────
    try:
        prod_ads_m = re.search(
            r'Top performing product ads\b(.*?)(?=Top performing keywords|Shipping performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        prod_ads_rows = []
        if prod_ads_m:
            pab = prod_ads_m.group(1)
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
        _slog_df(prod_ads_rows, prod_ads_m, "Top Performing Product Ads")
    except Exception as _exc:
        result["top_product_ads_df"] = pd.DataFrame()
        slog.append(("❌", "Top Performing Product Ads", f"Parse error: {_exc}"))

    # ── Top performing keywords ─────────────────────────────────────────────
    try:
        top_kw_m = re.search(
            r'Top performing keywords\b(.*?)(?=Shipping performance|Buy Box|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        top_kw_rows = []
        if top_kw_m:
            tkb = top_kw_m.group(1)
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
        _slog_df(top_kw_rows, top_kw_m, "Top Performing Keywords")
    except Exception as _exc:
        result["top_keywords_df"] = pd.DataFrame()
        slog.append(("❌", "Top Performing Keywords", f"Parse error: {_exc}"))

    # ── Shipping performance ────────────────────────────────────────────────
    try:
        ship_m = re.search(
            r'Shipping performance\b(.*?)(?=Buy Box|Review status|Cancellation rate|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        shipping_data = {}
        if ship_m:
            sb = ship_m.group(1)
            for lbl in ["Late shipment rate", "Invoice defect rate", "On time delivery rate",
                        "Valid order tracking rate", "Cancellation rate"]:
                m = re.search(rf'{re.escape(lbl)}\s*(?:\([^)]*\))?\s*([\d\.]+%|-)', sb, re.IGNORECASE)
                shipping_data[lbl] = m.group(1) if m else "-"
        result["shipping_data"] = shipping_data
        result["shipping_performance"] = shipping_data
        slog.append(("✅" if any(v != "-" for v in shipping_data.values()) else "❌",
                     "Shipping Performance",
                     f"{sum(1 for v in shipping_data.values() if v != '-')} metrics found" if shipping_data else "Section not found"))
    except Exception as _exc:
        result["shipping_data"] = {}
        result["shipping_performance"] = {}
        slog.append(("❌", "Shipping Performance", f"Parse error: {_exc}"))

    # ── Buy Box summary snapshot ────────────────────────────────────────────
    try:
        bb_snap_m = re.search(
            r'Buy Box summary\s*\(?snapshot\)?\b(.*?)(?=Buybox products|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        buybox_data = {}
        if bb_snap_m:
            bbs = bb_snap_m.group(1)
            bb_map = {
                "Active Products": r'ACTIVE PRODUCTS\s+(?:OVERALL STATUS\s+)?(\d+)',
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
    except Exception as _exc:
        result["buybox_snapshot"] = {}
        result["buybox_summary"] = {}
        slog.append(("❌", "Buy Box Summary", f"Parse error: {_exc}"))

    # ── Buybox products - Winning ───────────────────────────────────────────
    try:
        bb_win_m = re.search(
            r'Buybox products\s*[-\u2013]?\s*Winning\b.*?BUY BOX PRICE\s*\n(.*?)(?=\nBuybox products\s*[-\u2013]?\s*Losing|HEALTH STATUS|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        bb_win_rows = []
        if bb_win_m:
            bbw_pat = re.compile(r'^(\d+)\s+(-?[\$\d,\.]+)\s*$')
            for name, dm, asin, sku in _product_blocks(bb_win_m.group(1), bbw_pat):
                bb_win_rows.append({
                    "Product":       name,
                    "ASIN":          asin,
                    "Sellers":       int(dm.group(1)),
                    "Buy Box Price": dm.group(2),
                })
        result["buybox_winning_df"] = pd.DataFrame(bb_win_rows) if bb_win_rows else pd.DataFrame()
        _slog_df(bb_win_rows, bb_win_m, "Buybox Winning")
    except Exception as _exc:
        result["buybox_winning_df"] = pd.DataFrame()
        slog.append(("❌", "Buybox Winning", f"Parse error: {_exc}"))

    # ── Buybox products - Losing ────────────────────────────────────────────
    try:
        bb_lose_m = re.search(
            r'Buybox products\s*[-\u2013]?\s*Losing\b.*?BUY BOX PRICE\s*\n(.*?)(?=\nHEALTH STATUS|\nPolicy compliance|\nShipping performance|\Z)',
            full_text, re.DOTALL | re.IGNORECASE
        )
        bb_lose_rows = []
        if bb_lose_m:
            bbl_pat = re.compile(r'^(\d+)\s+(-?[\$\d,\.]+)\s*$')
            for name, dm, asin, sku in _product_blocks(bb_lose_m.group(1), bbl_pat):
                bb_lose_rows.append({
                    "Product":       name,
                    "ASIN":          asin,
                    "Sellers":       int(dm.group(1)),
                    "Buy Box Price": dm.group(2),
                })
        result["buybox_losing_df"] = pd.DataFrame(bb_lose_rows) if bb_lose_rows else pd.DataFrame()
        _slog_df(bb_lose_rows, bb_lose_m, "Buybox Losing")
    except Exception as _exc:
        result["buybox_losing_df"] = pd.DataFrame()
        slog.append(("❌", "Buybox Losing", f"Parse error: {_exc}"))

    # ── DataFrames for dashboard ────────────────────────────────────────────
    try:
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
                "Stock Status":         "\U0001f7e2 In Stock" if inv > 0 else "\U0001f534 Out of Stock",
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
                "Stock Status":         "\U0001f534 No Stock" if inv == 0 else "\U0001f7e1 Slow Mover",
                "Segment":              "Worst Seller",
            })
        result["inv_df"] = pd.DataFrame(inv_rows) if inv_rows else pd.DataFrame()
    except Exception as _exc:
        result.setdefault("summary_df", pd.DataFrame())
        result.setdefault("inv_df", pd.DataFrame())

    # ── Advertising Products (adv_df) ───────────────────────────────────────
    try:
        _adv_search_start = adv_sum_m.start() if adv_sum_m else 0
        adv_prod_sec_m = re.search(
            r'(?:^|\n)Products?\s*\n(.*?)(?=Advertising performance by campaign|Advertising campaign performance|Top performing product|Shipping performance|Buy Box|Review status|\Z)',
            full_text[_adv_search_start:], re.DOTALL | re.IGNORECASE
        )
        adv_prod_rows = []
        if adv_prod_sec_m:
            apb = adv_prod_sec_m.group(1)
            # Format A: product_blocks (name / data / ASIN:|SKU:)
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
            # Format B: inline with ASIN column
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
            # Format C: name / $sales $spend acos% conv / ASIN: XXXX (no SKU)
            if not adv_prod_rows:
                ap_data_re = re.compile(r'^(-?[\$\d,\.]+)\s+(-?[\$\d,\.]+)\s+([\d\.]+%|-)\s+([\d\.]+)')
                for name, dm, asin, sku in _product_blocks(apb, ap_data_re, asin_re=_ASIN_ONLY_RE):
                    adv_prod_rows.append({
                        "Product":  name,
                        "ASIN":     asin,
                        "Ad Sales": dm.group(1),
                        "Spend":    dm.group(2),
                        "ACoS":     dm.group(3),
                        "Conv":     dm.group(4),
                    })
        result["adv_df"] = pd.DataFrame(adv_prod_rows) if adv_prod_rows else pd.DataFrame()
        _slog_df(adv_prod_rows, adv_prod_sec_m, "Advertising Products")
    except Exception as _exc:
        result.setdefault("adv_df", pd.DataFrame())
        slog.append(("❌", "Advertising Products", f"Parse error: {_exc}"))

    result["wow_df"]       = pd.DataFrame()
    result["wow_metrics"]  = []
    result["sections_log"] = slog
    return result
