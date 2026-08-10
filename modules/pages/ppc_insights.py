import io
import streamlit as st
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import PatternFill, Font, Alignment, Border, Side
from openpyxl.utils import get_column_letter

from core.helpers import read_sqp, kpi_card

# Deteccion SIN importar: `core.ai_analyze` arrastra anthropic (~22 MB de RSS) y este
# modulo lo carga app.py en el boot. find_spec resuelve el modulo pero no lo ejecuta,
# asi que _HAS_AI conserva la misma semantica sin pagar el import. El import real va
# lazy en el handler del boton (mas abajo, "Generar Insights con IA").
from importlib.util import find_spec

_HAS_AI = find_spec("core.ai_analyze") is not None

# ── Paleta Capybaras ──────────────────────────────────────────────────────────
_ORG   = "E84000"; _ORG_P = "FFF3E0"
_BLK   = "1F1F1F"; _WHT   = "FAFAFA"
_GRN   = "1B6B2F"; _GRN_L = "E8F5E9"
_RED   = "B71C1C"; _RED_L = "FFEBEE"
_YEL   = "9C5700"; _YEL_L = "FFEB9C"
_DGRAY = "2D3748"; _MGRAY = "CBD5E0"
_WHITE = "FFFFFF"


# ── OpenPyXL helpers ─────────────────────────────────────────────────────────
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
        c.fill = _fill(_ORG)
        c.font = _font(True, _WHITE, 9)
        c.alignment = _al()
        c.border = _bd()
    ws.row_dimensions[rn].height = h


def _sec(ws, rn, text, ncols, bg=None, fg=None, h=16):
    bg = bg or _DGRAY
    fg = fg or _WHITE
    ws.merge_cells(start_row=rn, start_column=1, end_row=rn, end_column=ncols)
    c = ws.cell(row=rn, column=1, value=text)
    c.fill = _fill(bg)
    c.font = _font(True, fg, 10)
    c.alignment = _al("left")
    c.border = _bd()
    ws.row_dimensions[rn].height = h
    return rn + 1


def _autofit(ws, min_w=8, max_w=40):
    for col_cells in ws.columns:
        best = min_w
        for cell in col_cells:
            try:
                if cell.value:
                    best = max(best, min(max_w, len(str(cell.value)) + 2))
            except Exception:
                pass
        ws.column_dimensions[get_column_letter(col_cells[0].column)].width = best


# ── Column detection helper ───────────────────────────────────────────────────
def _find_col(df, keyword, exclude="b2b"):
    for c in df.columns:
        cl = c.lower()
        if keyword.lower() in cl:
            if exclude and exclude.lower() in cl:
                continue
            return c
    return None


def _clean_num(series):
    return pd.to_numeric(
        series.astype(str)
        .str.replace(r"[$%,]", "", regex=True)
        .str.strip(),
        errors="coerce",
    ).fillna(0)


# ── Parsers ───────────────────────────────────────────────────────────────────
@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_str(file_bytes, fname):
    try:
        buf = io.BytesIO(file_bytes)
        df = pd.read_excel(buf) if fname.endswith(".xlsx") else pd.read_csv(buf)
        df.columns = df.columns.str.strip()
        for col in df.columns:
            if df[col].dtype == object:
                try:
                    cleaned = df[col].astype(str).str.replace(r"[$%,]", "", regex=True).str.strip()
                    numeric = pd.to_numeric(cleaned, errors="coerce")
                    if numeric.notna().sum() / max(len(numeric), 1) > 0.5:
                        df[col] = numeric.fillna(0)
                except Exception:
                    pass
        return df, None
    except Exception as e:
        return None, str(e)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_sqp_cached(file_bytes, fname):
    try:
        buf = io.BytesIO(file_bytes)
        buf.name = fname
        df = pd.read_excel(buf, skiprows=1) if fname.endswith(".xlsx") else pd.read_csv(buf, skiprows=1)
        df.columns = df.columns.str.strip()
        return df, None
    except Exception as e:
        return None, str(e)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_br(file_bytes, fname):
    try:
        buf = io.BytesIO(file_bytes)
        df = pd.read_excel(buf) if fname.endswith(".xlsx") else pd.read_csv(buf)
        df.columns = df.columns.str.strip()
        return df, None
    except Exception as e:
        return None, str(e)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_campaigns(file_bytes):
    try:
        buf = io.BytesIO(file_bytes)
        df = pd.read_csv(buf)
        df.columns = df.columns.str.strip()
        return df, None
    except Exception as e:
        return None, str(e)


# ── Health score ──────────────────────────────────────────────────────────────
def _calc_health_score(acos, target_acos, cvr, buybox, funnel_complete, imp_share):
    # CVR score (25 pts)
    if cvr and cvr > 0:
        cvr_score = min(25, (cvr / 15) * 25)
    else:
        cvr_score = 12.0

    # BuyBox score (20 pts)
    if buybox is not None:
        bb_score = min(20, (buybox / 95) * 20) if buybox > 0 else 5.0
    else:
        bb_score = 10.0

    # ACoS score (25 pts)
    if acos is not None and acos > 0 and target_acos > 0:
        ratio = acos / target_acos
        if ratio <= 1:
            acos_score = 25
        elif ratio <= 1.5:
            acos_score = 18
        elif ratio <= 2:
            acos_score = 10
        else:
            acos_score = max(0, 25 - ratio * 8)
    else:
        acos_score = 12.0

    # Funnel score (15 pts)
    if funnel_complete is None:
        funnel_score = 7
    elif funnel_complete:
        funnel_score = 15
    else:
        funnel_score = 8

    # Impression share score (15 pts)
    if imp_share is not None:
        if imp_share >= 30:
            is_score = 15
        elif imp_share >= 10:
            is_score = 10
        elif imp_share > 0:
            is_score = 5
        else:
            is_score = 2
    else:
        is_score = 7

    return round(cvr_score + bb_score + acos_score + funnel_score + is_score)


# ── Per-ASIN analysis ─────────────────────────────────────────────────────────
def _analyze_asins(str_df, sqp_df, br_df, camp_df, target_acos):
    asin_data = {}

    # Detect STR columns
    col_asin    = _find_col(str_df, "Advertised ASIN") or _find_col(str_df, "ASIN")
    col_term    = _find_col(str_df, "Customer Search Term") or _find_col(str_df, "Search Term")
    col_spend   = _find_col(str_df, "Spend")
    col_sales   = _find_col(str_df, "7 Day Total Sales") or _find_col(str_df, "Sales")
    col_orders  = _find_col(str_df, "7 Day Total Orders") or _find_col(str_df, "Orders")
    col_clicks  = _find_col(str_df, "Clicks")
    col_camp    = _find_col(str_df, "Campaign Name") or _find_col(str_df, "Campaign")

    # Clean numeric STR columns
    for col in [col_spend, col_sales, col_orders, col_clicks]:
        if col and str_df[col].dtype == object:
            str_df[col] = _clean_num(str_df[col])

    # Determine ASINs
    if col_asin and col_asin in str_df.columns:
        asins = str_df[col_asin].dropna().unique().tolist()
        asins = [a for a in asins if str(a).startswith("B0") or (len(str(a)) == 10 and str(a)[0] == "B")]
    else:
        # No ASIN column — treat entire STR as one group
        asins = ["ALL"]

    for asin in asins:
        if col_asin and col_asin in str_df.columns and asin != "ALL":
            adf = str_df[str_df[col_asin] == asin].copy()
        else:
            adf = str_df.copy()

        # STR metrics
        spend  = float(adf[col_spend].sum())  if col_spend  else 0.0
        sales  = float(adf[col_sales].sum())  if col_sales  else 0.0
        orders = float(adf[col_orders].sum()) if col_orders else 0.0
        clicks = float(adf[col_clicks].sum()) if col_clicks else 0.0

        acos = (spend / sales * 100) if sales > 0 else None
        cvr  = (orders / clicks * 100) if clicks > 0 else None

        # Top keywords by sales
        top_kws = pd.DataFrame()
        if col_term and col_sales and col_term in adf.columns:
            top_kws = (
                adf.groupby(col_term, as_index=False)
                .agg({
                    col_sales:  "sum",
                    col_spend:  "sum" if col_spend else None,
                    col_orders: "sum" if col_orders else None,
                })
                .dropna(subset=[col_sales])
                .nlargest(5, col_sales)
                .rename(columns={col_term: "Search Term", col_sales: "Sales",
                                  col_spend: "Spend", col_orders: "Orders"})
            )

        # Bleeders — spend with 0 orders
        bleeders = pd.DataFrame()
        if col_term and col_spend and col_orders and col_term in adf.columns:
            mask = (adf[col_spend] > 5) & (adf[col_orders] == 0)
            bleeders = (
                adf[mask][[col_term, col_spend]]
                .rename(columns={col_term: "Search Term", col_spend: "Spend"})
                .sort_values("Spend", ascending=False)
                .head(10)
            )
        wasted_spend = float(bleeders["Spend"].sum()) if not bleeders.empty else 0.0

        # SQP metrics
        imp_share     = None
        purchase_share = None
        sqp_gaps       = 0

        if sqp_df is not None:
            col_q   = _find_col(sqp_df, "Search Query")
            col_ti  = _find_col(sqp_df, "Total Impressions") or _find_col(sqp_df, "Impressions")
            col_bi  = next(
                (c for c in sqp_df.columns if "brand" in c.lower() and "impression" in c.lower()),
                None,
            )
            col_tp  = _find_col(sqp_df, "Total Purchases") or _find_col(sqp_df, "Total Purchase")
            col_bp  = next(
                (c for c in sqp_df.columns if "brand" in c.lower() and "purchase" in c.lower()),
                None,
            )

            if col_ti and col_bi:
                for col in [col_ti, col_bi, col_tp, col_bp]:
                    if col and sqp_df[col].dtype == object:
                        sqp_df[col] = _clean_num(sqp_df[col])
                total_imp = float(sqp_df[col_ti].sum()) if col_ti else 0
                brand_imp = float(sqp_df[col_bi].sum()) if col_bi else 0
                imp_share = (brand_imp / total_imp * 100) if total_imp > 0 else 0.0

                if col_tp and col_bp:
                    total_pur = float(sqp_df[col_tp].sum())
                    brand_pur = float(sqp_df[col_bp].sum())
                    purchase_share = (brand_pur / total_pur * 100) if total_pur > 0 else 0.0

                if col_q and col_ti and col_bi:
                    gap_mask = (sqp_df[col_ti] > 500) & (sqp_df[col_bi] == 0)
                    sqp_gaps = int(gap_mask.sum())

        # BR metrics
        sessions  = None
        buybox    = None
        br_units  = None
        br_cvr    = None

        if br_df is not None:
            col_br_asin = (_find_col(br_df, "(Child) ASIN") or
                           _find_col(br_df, "Child ASIN") or
                           _find_col(br_df, "ASIN"))
            if col_br_asin and asin != "ALL":
                br_row = br_df[br_df[col_br_asin].astype(str).str.strip() == str(asin)]
            else:
                br_row = br_df

            if not br_row.empty:
                col_sess = _find_col(br_row, "Sessions")
                col_bb   = next(
                    (c for c in br_row.columns
                     if ("buy box" in c.lower() or "buybox" in c.lower() or "featured offer" in c.lower())
                     and "b2b" not in c.lower()),
                    None,
                )
                col_units = _find_col(br_row, "Units Ordered")
                col_sales_br = _find_col(br_row, "Ordered Product Sales")

                if col_sess:
                    s = br_row[col_sess].iloc[0]
                    sessions = float(_clean_num(pd.Series([s])).iloc[0])
                if col_bb:
                    bb = br_row[col_bb].iloc[0]
                    buybox = float(_clean_num(pd.Series([bb])).iloc[0])
                if col_units and col_sess and sessions and sessions > 0:
                    units = float(_clean_num(pd.Series([br_row[col_units].iloc[0]])).iloc[0])
                    br_units = units
                    br_cvr = (units / sessions * 100)

        # Campaign coverage
        n_campaigns    = None
        campaign_types = None
        funnel_complete = None

        if camp_df is not None:
            col_cname  = _find_col(camp_df, "Campaign Name") or _find_col(camp_df, "Campaign")
            col_state  = _find_col(camp_df, "State") or _find_col(camp_df, "Status")
            col_target = _find_col(camp_df, "Targeting Type") or _find_col(camp_df, "Campaign Type")

            if col_cname:
                cdf = camp_df.copy()
                if col_state:
                    cdf = cdf[cdf[col_state].astype(str).str.lower() == "enabled"]

                if asin != "ALL":
                    mask = cdf[col_cname].astype(str).str.lower().str.contains(asin.lower(), na=False)
                    cdf = cdf[mask]

                n_campaigns = len(cdf)
                types_found = set()
                for cname in cdf[col_cname].astype(str):
                    nl = cname.lower()
                    if "auto" in nl or "discovery" in nl:
                        types_found.add("Auto")
                    if "broad" in nl:
                        types_found.add("Broad")
                    if "phrase" in nl:
                        types_found.add("Phrase")
                    if "exact" in nl:
                        types_found.add("Exact")
                    if "pat" in nl or "asin" in nl or "conq" in nl or "competitor" in nl:
                        types_found.add("PAT")

                if col_target:
                    for ttype in cdf[col_target].astype(str):
                        tl = ttype.lower()
                        if "auto" in tl:
                            types_found.add("Auto")
                        if "manual" in tl:
                            types_found.add("Manual")

                campaign_types = ", ".join(sorted(types_found)) if types_found else "—"
                funnel_complete = ("Auto" in types_found and "Exact" in types_found) or \
                                  ("Auto" in types_found and "Broad" in types_found and "Exact" in types_found)

        health_score = _calc_health_score(
            acos=acos,
            target_acos=target_acos,
            cvr=cvr if cvr is not None else br_cvr,
            buybox=buybox,
            funnel_complete=funnel_complete,
            imp_share=imp_share,
        )

        asin_data[asin] = {
            "spend":          spend,
            "sales":          sales,
            "orders":         orders,
            "clicks":         clicks,
            "acos":           acos,
            "cvr":            cvr if cvr is not None else br_cvr,
            "wasted_spend":   wasted_spend,
            "top_kws":        top_kws,
            "bleeders":       bleeders,
            "imp_share":      imp_share,
            "purchase_share": purchase_share,
            "sqp_gaps":       sqp_gaps,
            "sessions":       sessions,
            "buybox":         buybox,
            "br_units":       br_units,
            "n_campaigns":    n_campaigns,
            "campaign_types": campaign_types,
            "funnel_complete":funnel_complete,
            "health_score":   health_score,
        }

    return asin_data


# ── Excel export ──────────────────────────────────────────────────────────────
def _build_insights_excel(asin_data, client_name, target_acos):
    wb = Workbook()

    # ── Sheet 1: Resumen ──────────────────────────────────────────────────────
    ws = wb.active
    ws.title = "Resumen"
    ws.freeze_panes = "A3"

    # Title row
    ws.merge_cells("A1:L1")
    title_cell = ws.cell(row=1, column=1, value=f"PPC Insights Engine — {client_name}")
    title_cell.fill = _fill(_ORG)
    title_cell.font = _font(True, _WHITE, 13)
    title_cell.alignment = _al("left")
    ws.row_dimensions[1].height = 22

    hdr_cols = [
        "ASIN", "Health Score", "Spend", "Sales", "ACoS %",
        "CVR %", "BuyBox %", "Imp Share %", "Wasted Spend",
        "Campañas", "Funnel", "SQP Gaps",
    ]
    _hdr(ws, 2, hdr_cols, h=15)

    sorted_asins = sorted(asin_data.keys(), key=lambda a: asin_data[a]["spend"], reverse=True)

    for i, asin in enumerate(sorted_asins, 3):
        d = asin_data[asin]
        score = d["health_score"]
        acos  = d["acos"]
        score_bg = _GRN_L if score >= 70 else (_YEL_L if score >= 40 else _RED_L)
        acos_bg  = None
        if acos is not None:
            acos_bg = _GRN_L if acos <= target_acos else (_YEL_L if acos <= target_acos * 1.5 else _RED_L)

        row_bg = "F7F7F7" if i % 2 == 0 else _WHITE

        _cell(ws, i, 1,  asin,                                      bg=row_bg, left=True)
        _cell(ws, i, 2,  score,                                      bg=score_bg, bold=True)
        _cell(ws, i, 3,  d["spend"],                                 bg=row_bg, fmt="$#,##0.00")
        _cell(ws, i, 4,  d["sales"],                                 bg=row_bg, fmt="$#,##0.00")
        _cell(ws, i, 5,  round(acos, 1) if acos is not None else None, bg=acos_bg, fmt="0.0")
        _cell(ws, i, 6,  round(d["cvr"], 1) if d["cvr"] is not None else None, bg=row_bg, fmt="0.0")
        _cell(ws, i, 7,  round(d["buybox"], 1) if d["buybox"] is not None else None, bg=row_bg, fmt="0.0")
        _cell(ws, i, 8,  round(d["imp_share"], 1) if d["imp_share"] is not None else None, bg=row_bg, fmt="0.0")
        _cell(ws, i, 9,  d["wasted_spend"],                          bg=row_bg, fmt="$#,##0.00")
        _cell(ws, i, 10, d["n_campaigns"],                           bg=row_bg)
        _cell(ws, i, 11, "Completo" if d["funnel_complete"] else ("Parcial" if d["funnel_complete"] is not None else "—"),
              bg=row_bg)
        _cell(ws, i, 12, d["sqp_gaps"],                              bg=row_bg)

    _autofit(ws)

    # ── Sheets per ASIN (max 10) ──────────────────────────────────────────────
    for asin in sorted_asins[:10]:
        d = asin_data[asin]
        ws2 = wb.create_sheet(title=f"ASIN_{asin[:8]}")
        r = 1

        # Title
        ws2.merge_cells(f"A{r}:F{r}")
        tc = ws2.cell(row=r, column=1, value=f"Insights — {asin} — {client_name}")
        tc.fill = _fill(_ORG)
        tc.font = _font(True, _WHITE, 12)
        tc.alignment = _al("left")
        ws2.row_dimensions[r].height = 20
        r += 1

        # KPI Summary
        r = _sec(ws2, r, "KPI Summary", 6, bg=_DGRAY)
        _hdr(ws2, r, ["Métrica", "Valor"], h=13)
        r += 1
        kpi_rows = [
            ("Spend",         f"${d['spend']:,.2f}"),
            ("Sales",         f"${d['sales']:,.2f}"),
            ("ACoS",          f"{d['acos']:.1f}%" if d["acos"] is not None else "—"),
            ("CVR",           f"{d['cvr']:.1f}%" if d["cvr"] is not None else "—"),
            ("Orders",        f"{d['orders']:.0f}"),
            ("Clicks",        f"{d['clicks']:.0f}"),
            ("Wasted Spend",  f"${d['wasted_spend']:,.2f}"),
            ("BuyBox %",      f"{d['buybox']:.1f}%" if d["buybox"] is not None else "—"),
            ("Sessions",      f"{d['sessions']:,.0f}" if d["sessions"] is not None else "—"),
            ("Imp Share %",   f"{d['imp_share']:.1f}%" if d["imp_share"] is not None else "—"),
            ("Purchase Share %", f"{d['purchase_share']:.1f}%" if d["purchase_share"] is not None else "—"),
            ("SQP Gaps",      str(d["sqp_gaps"])),
            ("Campañas",      str(d["n_campaigns"]) if d["n_campaigns"] is not None else "—"),
            ("Tipos Campañas",str(d["campaign_types"]) if d["campaign_types"] else "—"),
            ("Funnel",        "Completo" if d["funnel_complete"] else ("Parcial" if d["funnel_complete"] is not None else "—")),
            ("Health Score",  str(d["health_score"])),
        ]
        for label, val in kpi_rows:
            bg = "F7F7F7" if r % 2 == 0 else _WHITE
            _cell(ws2, r, 1, label, bg=bg, left=True, bold=True)
            _cell(ws2, r, 2, val,   bg=bg, left=True)
            r += 1

        r += 1

        # Top Keywords
        if not d["top_kws"].empty:
            r = _sec(ws2, r, "Top Keywords (por Ventas)", 6, bg=_GRN, fg=_WHITE)
            kw_cols = list(d["top_kws"].columns)
            _hdr(ws2, r, kw_cols)
            r += 1
            for _, krow in d["top_kws"].iterrows():
                bg = "F0FFF4" if r % 2 == 0 else _WHITE
                for ci, val in enumerate(krow.values, 1):
                    _cell(ws2, r, ci, val, bg=bg, left=(ci == 1))
                r += 1
            r += 1

        # Bleeders
        if not d["bleeders"].empty:
            r = _sec(ws2, r, "Bleeders — Gasto sin Conversión", 6, bg=_RED, fg=_WHITE)
            bl_cols = list(d["bleeders"].columns)
            _hdr(ws2, r, bl_cols)
            r += 1
            for _, brow in d["bleeders"].iterrows():
                bg = "FFF5F5" if r % 2 == 0 else _WHITE
                for ci, val in enumerate(brow.values, 1):
                    _cell(ws2, r, ci, val, bg=bg, left=(ci == 1))
                r += 1

        _autofit(ws2)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


# ── UI helpers ────────────────────────────────────────────────────────────────
def _score_emoji(score):
    if score >= 70:
        return "🟢"
    if score >= 40:
        return "🟡"
    return "🔴"


def _fmt_opt(val, fmt=".1f", suffix="", none_str="—"):
    if val is None:
        return none_str
    try:
        return f"{val:{fmt}}{suffix}"
    except Exception:
        return str(val)


# ── render ────────────────────────────────────────────────────────────────────
def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🔎</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>PPC Insights</div>"
        "<div style='font-size:0.82rem;color:#888;'>Análisis integral por ASIN — cruza STR, SQP, BR y Campañas para un health score completo.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Health score 0-100 por ASIN cruzando STR + SQP + BR + Campañas. Detecta wasted spend y bleeders.")
        with col2:
            st.markdown("**📂 Archivos necesarios**")
            st.caption("STR (requerido). SQP + BR by ASIN + Campaign CSV (opcionales — mínimo 2 fuentes para score confiable).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("PPC Audit (M20) para auditoría estructural o Bid Optimizer (M9) para ajustar bids.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Configurá Target ACoS + precio promedio + nombre del cliente\n"
            "2. Subí el STR (requerido) y todos los archivos opcionales que tengas\n"
            "3. Revisá los cards por ASIN — score 🟢 ≥80 / 🟡 60-79 / 🔴 <60\n"
            "4. Expandí cada ASIN para ver top keywords, bleeders y funnel\n"
            "5. Descargá el Excel multi-sheet (hasta 10 hojas por ASIN)"
        )

    # ── Global inputs ─────────────────────────────────────────────────────────
    col_a, col_b = st.columns(2)
    with col_a:
        target_acos = st.slider(
            "Target ACoS (%)",
            min_value=5, max_value=80, value=25, step=1,
            key="insights_target_acos",
        )
    with col_b:
        precio_promedio = st.number_input(
            "Precio promedio del producto ($)",
            min_value=1.0, value=15.0, step=0.5,
            key="insights_precio",
        )

    client_name = st.text_input(
        "Nombre del cliente (para el Excel)",
        value="Cliente",
        key="insights_client",
    )

    st.markdown("---")

    # ── File uploaders ────────────────────────────────────────────────────────
    st.markdown("**Archivos**")
    c1, c2 = st.columns(2)
    with c1:
        f_str  = st.file_uploader("Search Term Report (REQUERIDO)", type=["xlsx", "csv"], key="insights_str")
        f_sqp  = st.file_uploader("Search Query Performance (opcional)", type=["xlsx", "csv"], key="insights_sqp")
    with c2:
        f_br   = st.file_uploader("Business Report by ASIN (opcional)", type=["csv", "xlsx"], key="insights_br")
        f_camp = st.file_uploader("Campaign CSV (opcional)", type=["csv"], key="insights_camp")

    if not f_str:
        st.markdown(
            "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
            "border-radius:12px;margin:1rem 0;'>"
            "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
            "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Sube el Search Term Report para comenzar el análisis.</div>"
            "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
            "Arrastrá o hacé click en el uploader de arriba</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if not st.button("Generar Insights", type="primary", key="insights_run"):
        return

    # ── Parse files ───────────────────────────────────────────────────────────
    with st.spinner("Procesando archivos..."):
        str_df, err = _parse_str(f_str.read(), f_str.name)
        if err or str_df is None:
            st.error(f"Error al leer el STR: {err}")
            return

        sqp_df = None
        if f_sqp:
            sqp_df, sqp_err = _parse_sqp_cached(f_sqp.read(), f_sqp.name)
            if sqp_err:
                st.warning(f"No se pudo leer el SQP: {sqp_err}")
                sqp_df = None

        br_df = None
        if f_br:
            br_df, br_err = _parse_br(f_br.read(), f_br.name)
            if br_err:
                st.warning(f"No se pudo leer el BR: {br_err}")
                br_df = None

        camp_df = None
        if f_camp:
            camp_df, camp_err = _parse_campaigns(f_camp.read())
            if camp_err:
                st.warning(f"No se pudo leer el Campaign CSV: {camp_err}")
                camp_df = None

        try:
            asin_data = _analyze_asins(str_df, sqp_df, br_df, camp_df, target_acos)
        except Exception as e:
            st.error(f"Error durante el análisis: {e}")
            return

    if not asin_data:
        st.warning("No se encontraron ASINs en el STR.")
        return

    sorted_asins = sorted(asin_data.keys(), key=lambda a: asin_data[a]["spend"], reverse=True)

    # ── Summary metrics ───────────────────────────────────────────────────────
    total_spend     = sum(d["spend"] for d in asin_data.values())
    total_wasted    = sum(d["wasted_spend"] for d in asin_data.values())
    avg_score       = sum(d["health_score"] for d in asin_data.values()) / len(asin_data)
    n_asins         = len(asin_data)

    st.markdown("### Resumen de cuenta")
    mc1, mc2, mc3, mc4 = st.columns(4)
    with mc1:
        st.markdown(kpi_card("ASINs analizados", str(n_asins)), unsafe_allow_html=True)
    with mc2:
        st.markdown(kpi_card("Health Score prom.", f"{avg_score:.0f}/100"), unsafe_allow_html=True)
    with mc3:
        st.markdown(kpi_card("Spend total", f"${total_spend:,.2f}"), unsafe_allow_html=True)
    with mc4:
        pct = float(total_wasted / total_spend * 100) if total_spend > 0 else 0
        st.markdown(kpi_card("Wasted spend", f"${total_wasted:,.2f}", delta=-pct, delta_good=False), unsafe_allow_html=True)

    st.divider()

    # ── Per-ASIN cards ────────────────────────────────────────────────────────
    st.markdown("### Análisis por ASIN")

    for asin in sorted_asins:
        d = asin_data[asin]
        score = d["health_score"]
        emoji = _score_emoji(score)

        c1, c2, c3, c4 = st.columns([3, 1, 1, 1])
        with c1:
            st.markdown(f"**{emoji} {asin}**")
        with c2:
            st.metric("Health Score", f"{score}/100", label_visibility="visible")
        with c3:
            st.metric("ACoS", _fmt_opt(d["acos"], suffix="%"))
        with c4:
            st.metric("Spend", f"${d['spend']:,.2f}")

        with st.expander(f"Detalle {asin}"):
            tab_str, tab_sqp, tab_br, tab_camp = st.tabs(
                ["STR", "SQP", "Business Report", "Campañas"]
            )

            with tab_str:
                dc1, dc2, dc3, dc4 = st.columns(4)
                dc1.metric("Spend",    f"${d['spend']:,.2f}")
                dc2.metric("Sales",    f"${d['sales']:,.2f}")
                dc3.metric("ACoS",     _fmt_opt(d["acos"],  suffix="%"))
                dc4.metric("CVR",      _fmt_opt(d["cvr"],   suffix="%"))
                dc1b, dc2b, dc3b, dc4b = st.columns(4)
                dc1b.metric("Orders",  f"{d['orders']:.0f}")
                dc2b.metric("Clicks",  f"{d['clicks']:.0f}")
                dc3b.metric("Wasted",  f"${d['wasted_spend']:,.2f}")
                dc4b.metric("", "")

                if not d["top_kws"].empty:
                    st.markdown("**Top Keywords por ventas**")
                    st.dataframe(d["top_kws"], use_container_width=True, hide_index=True)

                if not d["bleeders"].empty:
                    st.markdown("**Bleeders — gasto sin conversion**")
                    st.dataframe(d["bleeders"], use_container_width=True, hide_index=True)

            with tab_sqp:
                if sqp_df is None:
                    st.info("No se subio el archivo SQP.")
                else:
                    dc1, dc2, dc3 = st.columns(3)
                    dc1.metric("Imp Share",      _fmt_opt(d["imp_share"],      suffix="%"))
                    dc2.metric("Purchase Share", _fmt_opt(d["purchase_share"], suffix="%"))
                    dc3.metric("Gaps detectados", str(d["sqp_gaps"]))

            with tab_br:
                if br_df is None:
                    st.info("No se subio el Business Report.")
                else:
                    dc1, dc2, dc3 = st.columns(3)
                    dc1.metric("Sessions",  _fmt_opt(d["sessions"], ".0f"))
                    dc2.metric("BuyBox %",  _fmt_opt(d["buybox"],   suffix="%"))
                    dc3.metric("CVR (BR)",  _fmt_opt(
                        (d["br_units"] / d["sessions"] * 100)
                        if d["br_units"] is not None and d["sessions"] and d["sessions"] > 0
                        else None,
                        suffix="%",
                    ))

            with tab_camp:
                if camp_df is None:
                    st.info("No se subio el Campaign CSV.")
                else:
                    dc1, dc2 = st.columns(2)
                    dc1.metric("Campañas (ENABLED)", str(d["n_campaigns"]) if d["n_campaigns"] is not None else "—")
                    dc2.metric("Tipos detectados", d["campaign_types"] or "—")
                    if d["funnel_complete"] is not None:
                        if d["funnel_complete"]:
                            st.success("Funnel completo detectado (Auto + Exact presentes).")
                        else:
                            st.warning("Funnel incompleto — revisar cobertura de match types.")

        st.divider()

    # ── AI analysis ───────────────────────────────────────────────────────────
    if _HAS_AI:
        st.markdown("### Analisis con IA")
        if st.button("Generar Insights con IA", key="insights_ai"):
            top5 = sorted_asins[:5]
            lines = []
            for asin in top5:
                d = asin_data[asin]
                lines.append(
                    f"ASIN {asin}: score={d['health_score']}/100, "
                    f"spend=${d['spend']:.2f}, acos={_fmt_opt(d['acos'], suffix='%')}, "
                    f"cvr={_fmt_opt(d['cvr'], suffix='%')}, "
                    f"buybox={_fmt_opt(d['buybox'], suffix='%')}, "
                    f"imp_share={_fmt_opt(d['imp_share'], suffix='%')}, "
                    f"wasted=${d['wasted_spend']:.2f}, sqp_gaps={d['sqp_gaps']}, "
                    f"funnel={'completo' if d['funnel_complete'] else ('parcial' if d['funnel_complete'] is not None else 'sin datos')}"
                )
            resumen = "\n".join(lines)

            prompt = (
                f"Sos un experto senior en Amazon PPC analizando la cuenta de {client_name}.\n"
                f"Target ACoS: {target_acos}%. Precio promedio: ${precio_promedio:.2f}.\n"
                f"Total ASINs: {n_asins}. Health score promedio: {avg_score:.0f}/100.\n"
                f"Total spend: ${total_spend:,.2f}. Wasted spend: ${total_wasted:,.2f}.\n\n"
                f"TOP ASINs por spend:\n{resumen}\n\n"
                "Genera recomendaciones priorizadas por ASIN en espanol. "
                "Para cada ASIN menciona la accion mas urgente. "
                "Maximo 300 palabras. Sin generalidades. Directo y accionable."
            )

            with st.spinner("Analizando con IA..."):
                from core.ai_analyze import _claude_analyze  # lazy: anthropic ~22 MB
                result = _claude_analyze(prompt, max_tokens=1000)
            st.markdown(result)

    # ── Excel export ──────────────────────────────────────────────────────────
    st.markdown("---")
    st.markdown("### Exportar")

    try:
        excel_bytes = _build_insights_excel(asin_data, client_name, target_acos)
        st.download_button(
            label="Descargar Insights Excel",
            data=excel_bytes,
            file_name=f"PPC_Insights_{client_name}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="insights_dl",
        )
    except Exception as e:
        st.error(f"Error al generar el Excel: {e}")
