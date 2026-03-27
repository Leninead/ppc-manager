import io
import re
import datetime

import streamlit as st
import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side


# ── Helpers ─────────────────────────────────────────────────────────────────

def _clean_num(val):
    try:
        return float(str(val).replace("$", "").replace("%", "").replace(",", "").strip())
    except Exception:
        return 0.0


def _find_col(df, keyword):
    for c in df.columns:
        if keyword.lower() in c.lower() and "b2b" not in c.lower():
            return c
    return None


# ── Parsers ──────────────────────────────────────────────────────────────────

def _parse_str(file):
    fname = file.name if hasattr(file, "name") else ""
    try:
        df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer STR: {e}")
        return None


def _parse_campaigns(file):
    try:
        df = pd.read_csv(file)
        df.columns = df.columns.str.strip()
        state_col = _find_col(df, "State")
        if state_col:
            df = df[df[state_col].astype(str).str.lower().isin(["enabled", "active"])]
        return df
    except Exception as e:
        st.error(f"Error al leer Campaign CSV: {e}")
        return None


def _parse_br(file):
    fname = file.name if hasattr(file, "name") else ""
    try:
        df = pd.read_excel(file) if fname.endswith(".xlsx") else pd.read_csv(file)
        df.columns = df.columns.str.strip()
        return df
    except Exception as e:
        st.error(f"Error al leer BR: {e}")
        return None


# ── Analysis functions ───────────────────────────────────────────────────────

def _analyze_structure(camp_df):
    name_col = _find_col(camp_df, "Campaign Name") or _find_col(camp_df, "Campaign")
    type_col = _find_col(camp_df, "Campaign Type") or _find_col(camp_df, "Type")

    total_campaigns = len(camp_df)

    type_counts = {}
    if type_col:
        for _, row in camp_df.iterrows():
            t = str(row[type_col]).upper()
            if "SP" in t or "PRODUCT" in t:
                key = "SP"
            elif "SB" in t or "BRAND" in t:
                key = "SB"
            elif "SD" in t or "DISPLAY" in t:
                key = "SD"
            else:
                key = "Otro"
            type_counts[key] = type_counts.get(key, 0) + 1

    match_counts = {"Exact": 0, "Broad": 0, "Phrase": 0, "Auto": 0, "PAT": 0}
    if name_col:
        for name in camp_df[name_col].astype(str):
            n = name.lower()
            if "exact" in n:
                match_counts["Exact"] += 1
            elif "broad" in n:
                match_counts["Broad"] += 1
            elif "phrase" in n:
                match_counts["Phrase"] += 1
            elif "auto" in n:
                match_counts["Auto"] += 1
            elif "pat" in n or ("asin" in n and "camp" in n):
                match_counts["PAT"] += 1

    port_col = _find_col(camp_df, "Portfolio")
    portfolios = {}
    if port_col:
        for p in camp_df[port_col].astype(str):
            if p and p.lower() not in ["nan", ""]:
                portfolios[p] = portfolios.get(p, 0) + 1

    return {
        "total": total_campaigns,
        "by_type": type_counts,
        "by_match": match_counts,
        "portfolios": portfolios,
    }


def _check_naming(camp_df, brand):
    name_col = _find_col(camp_df, "Campaign Name") or _find_col(camp_df, "Campaign")
    if not name_col:
        return 0, 0, [], 0.0

    total = len(camp_df)
    good = 0
    bad_names = []

    for name in camp_df[name_col].astype(str):
        n = name.strip()
        has_pipes = "|" in n
        has_brand = brand.lower() in n.lower() if brand else True
        has_type = any(t in n.upper() for t in ["SP-", "SB-", "SD-", "SP ", "SBV"])

        if has_pipes and has_brand and has_type:
            good += 1
        else:
            bad_names.append(n)

    pct = round(good / total * 100, 1) if total > 0 else 0.0
    return good, total, bad_names[:20], pct


def _analyze_efficiency(camp_df, target_acos):
    name_col = _find_col(camp_df, "Campaign Name") or _find_col(camp_df, "Campaign")
    spend_col = (
        _find_col(camp_df, "Spend")
        or _find_col(camp_df, "Total cost")
        or _find_col(camp_df, "Cost")
    )
    sales_col = _find_col(camp_df, "Sales") or _find_col(camp_df, "Total Sales")
    imp_col = _find_col(camp_df, "Impressions")
    orders_col = _find_col(camp_df, "Orders") or _find_col(camp_df, "Purchases")

    result = {
        "total_spend": 0.0,
        "total_sales": 0.0,
        "avg_acos": 0.0,
        "top_spend": [],
        "top_sales": [],
        "ghost_count": 0,
        "wasted_spend": 0.0,
        "wasted_campaigns": 0,
    }

    df = camp_df.copy()

    if spend_col:
        df["_spend"] = df[spend_col].apply(_clean_num)
        result["total_spend"] = df["_spend"].sum()
    else:
        df["_spend"] = 0.0

    if sales_col:
        df["_sales"] = df[sales_col].apply(_clean_num)
        result["total_sales"] = df["_sales"].sum()
    else:
        df["_sales"] = 0.0

    if imp_col:
        df["_imps"] = df[imp_col].apply(_clean_num)
        result["ghost_count"] = int(len(df[df["_imps"] == 0]))

    if orders_col:
        df["_orders"] = df[orders_col].apply(_clean_num)
    else:
        df["_orders"] = 0.0

    if result["total_sales"] > 0:
        result["avg_acos"] = round(result["total_spend"] / result["total_sales"] * 100, 1)

    if spend_col and name_col:
        top = df.nlargest(5, "_spend")
        result["top_spend"] = [
            (str(r[name_col])[:50], round(r["_spend"], 2)) for _, r in top.iterrows()
        ]

    if sales_col and name_col:
        top = df.nlargest(5, "_sales")
        result["top_sales"] = [
            (str(r[name_col])[:50], round(r["_sales"], 2)) for _, r in top.iterrows()
        ]

    if "_spend" in df.columns and "_orders" in df.columns:
        wasted = df[(df["_spend"] > 0) & (df["_orders"] == 0)]
        result["wasted_spend"] = round(wasted["_spend"].sum(), 2)
        result["wasted_campaigns"] = int(len(wasted))

    return result


def _analyze_coverage(camp_df):
    name_col = _find_col(camp_df, "Campaign Name") or _find_col(camp_df, "Campaign")
    if not name_col:
        return {}

    asin_pattern = re.compile(r'B0[A-Z0-9]{8,}')
    asin_coverage = {}

    for name in camp_df[name_col].astype(str):
        asins = asin_pattern.findall(name.upper())
        n = name.lower()
        match_type = None
        if "exact" in n:
            match_type = "Exact"
        elif "broad" in n:
            match_type = "Broad"
        elif "phrase" in n:
            match_type = "Phrase"
        elif "auto" in n:
            match_type = "Auto"
        elif "pat" in n or "asin" in n:
            match_type = "PAT"

        for asin in asins:
            if asin not in asin_coverage:
                asin_coverage[asin] = set()
            if match_type:
                asin_coverage[asin].add(match_type)

    return asin_coverage


def _analyze_buybox(br_df):
    asin_col = _find_col(br_df, "ASIN") or _find_col(br_df, "(Child) ASIN")
    bb_col = _find_col(br_df, "Featured Offer") or _find_col(br_df, "Buy Box")
    if not (asin_col and bb_col):
        return []

    df = br_df.copy()
    df["_bb"] = df[bb_col].apply(_clean_num)
    issues = df[df["_bb"] < 90].copy()
    issues = issues.sort_values("_bb")

    result = []
    for _, row in issues.head(20).iterrows():
        result.append({
            "ASIN": str(row[asin_col]),
            "BuyBox %": round(row["_bb"], 1),
        })
    return result


def _calc_account_score(structure, naming_pct, efficiency, coverage, target_acos):
    score = 0

    # Structure (20 pts)
    match_types_used = sum(1 for v in structure["by_match"].values() if v > 0)
    score += min(20, match_types_used * 4)

    # Naming (15 pts)
    score += round(naming_pct / 100 * 15)

    # Efficiency (25 pts)
    acos = efficiency["avg_acos"]
    if acos > 0:
        ratio = acos / target_acos if target_acos > 0 else 2.0
        if ratio <= 1.0:
            score += 25
        elif ratio <= 1.5:
            score += 18
        elif ratio <= 2.0:
            score += 10
        else:
            score += max(0, round(25 - ratio * 6))
    else:
        score += 12

    # Waste (20 pts)
    if efficiency["total_spend"] > 0:
        waste_pct = efficiency["wasted_spend"] / efficiency["total_spend"] * 100
        if waste_pct < 5:
            score += 20
        elif waste_pct < 15:
            score += 14
        elif waste_pct < 30:
            score += 8
        else:
            score += 2
    else:
        score += 10

    # Coverage (20 pts)
    if coverage:
        avg_types = sum(len(v) for v in coverage.values()) / len(coverage)
        score += min(20, round(avg_types * 5))
    else:
        score += 10

    return min(100, score)


# ── Excel export ─────────────────────────────────────────────────────────────

def _hdr_style():
    fill = PatternFill("solid", fgColor="E84000")
    font = Font(bold=True, color="FFFFFF", size=10)
    align = Alignment(horizontal="center", vertical="center", wrap_text=True)
    return fill, font, align


def _thin_border():
    side = Side(style="thin", color="DDDDDD")
    return Border(left=side, right=side, top=side, bottom=side)


def _set_header_row(ws, headers):
    fill, font, align = _hdr_style()
    border = _thin_border()
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=1, column=col_idx, value=h)
        cell.fill = fill
        cell.font = font
        cell.alignment = align
        cell.border = border


def _auto_width(ws):
    for col in ws.columns:
        max_len = 0
        col_letter = col[0].column_letter
        for cell in col:
            try:
                max_len = max(max_len, len(str(cell.value or "")))
            except Exception:
                pass
        ws.column_dimensions[col_letter].width = min(max_len + 4, 55)


def _build_audit_excel(
    score, structure, naming_pct, bad_names, efficiency, coverage,
    buybox_issues, brand, target_acos
):
    wb = Workbook()

    # ── Sheet 1: Portada ────────────────────────────────────────────────────
    ws_portada = wb.active
    ws_portada.title = "Portada"

    header_fill = PatternFill("solid", fgColor="E84000")
    dark_fill = PatternFill("solid", fgColor="1F1F1F")
    white_bold = Font(bold=True, color="FFFFFF", size=14)
    orange_big = Font(bold=True, color="E84000", size=36)
    grey_font = Font(color="888888", size=10)

    ws_portada.merge_cells("A1:D1")
    c = ws_portada["A1"]
    c.value = "CAPYBARAS AGENCY — PPC AUDIT"
    c.font = Font(bold=True, color="FFFFFF", size=16)
    c.fill = header_fill
    c.alignment = Alignment(horizontal="center", vertical="center")
    ws_portada.row_dimensions[1].height = 36

    ws_portada.merge_cells("A2:D2")
    c2 = ws_portada["A2"]
    c2.value = f"Marca: {brand or '—'}   |   Target ACoS: {target_acos}%   |   Fecha: {datetime.date.today().strftime('%d/%m/%Y')}"
    c2.font = Font(color="AAAAAA", size=10)
    c2.fill = dark_fill
    c2.alignment = Alignment(horizontal="center")
    ws_portada.row_dimensions[2].height = 22

    ws_portada.merge_cells("A4:D4")
    score_cell = ws_portada["A4"]
    score_cell.value = score
    score_cell.font = orange_big
    score_cell.alignment = Alignment(horizontal="center")
    ws_portada.row_dimensions[4].height = 60

    ws_portada.merge_cells("A5:D5")
    label_map = {
        (80, 101): "EXCELENTE",
        (60, 80): "BUENO",
        (40, 60): "MEJORABLE",
        (0, 40): "CRITICO",
    }
    label = next((v for (lo, hi), v in label_map.items() if lo <= score < hi), "—")
    ws_portada["A5"].value = f"Score de cuenta — {label}"
    ws_portada["A5"].font = Font(bold=True, color="E84000", size=13)
    ws_portada["A5"].alignment = Alignment(horizontal="center")

    summaries = [
        ("Campañas totales", str(structure["total"])),
        ("Tipos de match activos", str(sum(1 for v in structure["by_match"].values() if v > 0))),
        ("Naming convention", f"{naming_pct}%"),
        ("ACoS promedio", f"{efficiency['avg_acos']:.1f}%"),
        ("Spend total", f"${efficiency['total_spend']:,.2f}"),
        ("Sales total", f"${efficiency['total_sales']:,.2f}"),
        ("Spend sin ventas", f"${efficiency['wasted_spend']:,.2f}"),
        ("Campañas fantasma", str(efficiency.get("ghost_count", 0))),
        ("ASINs con funnel", str(len(coverage))),
    ]
    row = 7
    for label_txt, val_txt in summaries:
        ws_portada.cell(row=row, column=1, value=label_txt).font = Font(color="555555", size=10)
        cell_v = ws_portada.cell(row=row, column=2, value=val_txt)
        cell_v.font = Font(bold=True, color="1F1F1F", size=10)
        row += 1

    _auto_width(ws_portada)

    # ── Sheet 2: Estructura ─────────────────────────────────────────────────
    ws_est = wb.create_sheet("Estructura")
    _set_header_row(ws_est, ["Dimensión", "Categoría", "Cantidad"])
    row = 2
    alt = PatternFill("solid", fgColor="FFF3E0")
    for k, v in structure["by_type"].items():
        ws_est.cell(row=row, column=1, value="Tipo de Ad")
        ws_est.cell(row=row, column=2, value=k)
        ws_est.cell(row=row, column=3, value=v)
        if row % 2 == 0:
            for col in range(1, 4):
                ws_est.cell(row=row, column=col).fill = alt
        row += 1
    for k, v in structure["by_match"].items():
        if v > 0:
            ws_est.cell(row=row, column=1, value="Match Type")
            ws_est.cell(row=row, column=2, value=k)
            ws_est.cell(row=row, column=3, value=v)
            if row % 2 == 0:
                for col in range(1, 4):
                    ws_est.cell(row=row, column=col).fill = alt
            row += 1
    for k, v in structure["portfolios"].items():
        ws_est.cell(row=row, column=1, value="Portfolio")
        ws_est.cell(row=row, column=2, value=k)
        ws_est.cell(row=row, column=3, value=v)
        if row % 2 == 0:
            for col in range(1, 4):
                ws_est.cell(row=row, column=col).fill = alt
        row += 1
    ws_est.freeze_panes = "A2"
    _auto_width(ws_est)

    # ── Sheet 3: Eficiencia ─────────────────────────────────────────────────
    ws_eff = wb.create_sheet("Eficiencia")
    _set_header_row(ws_eff, ["Métrica", "Valor"])
    kpi_rows = [
        ("Spend Total", f"${efficiency['total_spend']:,.2f}"),
        ("Sales Total", f"${efficiency['total_sales']:,.2f}"),
        ("ACoS Promedio", f"{efficiency['avg_acos']:.1f}%"),
        ("Target ACoS", f"{target_acos}%"),
        ("vs Target (pp)", f"{efficiency['avg_acos'] - target_acos:+.1f}"),
        ("Spend sin ventas (WAS)", f"${efficiency['wasted_spend']:,.2f}"),
        ("Campañas sin ventas", str(efficiency.get("wasted_campaigns", 0))),
        ("Campañas fantasma (0 imps)", str(efficiency.get("ghost_count", 0))),
    ]
    for i, (label_txt, val_txt) in enumerate(kpi_rows, 2):
        ws_eff.cell(row=i, column=1, value=label_txt)
        ws_eff.cell(row=i, column=2, value=val_txt)
        if i % 2 == 0:
            for col in range(1, 3):
                ws_eff.cell(row=i, column=col).fill = alt

    row = len(kpi_rows) + 3
    ws_eff.cell(row=row, column=1, value="Top 5 por Spend").font = Font(bold=True, color="E84000")
    row += 1
    _set_header_row_at(ws_eff, row, ["Campaña", "Spend ($)"])
    row += 1
    for name, val in efficiency["top_spend"]:
        ws_eff.cell(row=row, column=1, value=name)
        ws_eff.cell(row=row, column=2, value=val)
        ws_eff.cell(row=row, column=2).number_format = "$#,##0.00"
        row += 1

    row += 1
    ws_eff.cell(row=row, column=1, value="Top 5 por Sales").font = Font(bold=True, color="E84000")
    row += 1
    _set_header_row_at(ws_eff, row, ["Campaña", "Sales ($)"])
    row += 1
    for name, val in efficiency["top_sales"]:
        ws_eff.cell(row=row, column=1, value=name)
        ws_eff.cell(row=row, column=2, value=val)
        ws_eff.cell(row=row, column=2).number_format = "$#,##0.00"
        row += 1

    ws_eff.freeze_panes = "A2"
    _auto_width(ws_eff)

    # ── Sheet 4: Cobertura ──────────────────────────────────────────────────
    ws_cov = wb.create_sheet("Cobertura")
    _set_header_row(ws_cov, ["ASIN", "Auto", "Broad", "Phrase", "Exact", "PAT", "Tipos", "Completo"])
    green_fill = PatternFill("solid", fgColor="E8F5E9")
    red_fill = PatternFill("solid", fgColor="FFEBEE")
    for i, (asin, types) in enumerate(sorted(coverage.items()), 2):
        ws_cov.cell(row=i, column=1, value=asin)
        ws_cov.cell(row=i, column=2, value="Si" if "Auto" in types else "No")
        ws_cov.cell(row=i, column=3, value="Si" if "Broad" in types else "No")
        ws_cov.cell(row=i, column=4, value="Si" if "Phrase" in types else "No")
        ws_cov.cell(row=i, column=5, value="Si" if "Exact" in types else "No")
        ws_cov.cell(row=i, column=6, value="Si" if "PAT" in types else "No")
        ws_cov.cell(row=i, column=7, value=len(types))
        complete = len(types) >= 3
        ws_cov.cell(row=i, column=8, value="Completo" if complete else "Incompleto")
        row_fill = green_fill if complete else red_fill
        for col in range(1, 9):
            ws_cov.cell(row=i, column=col).fill = row_fill
    ws_cov.freeze_panes = "A2"
    _auto_width(ws_cov)

    # ── Sheet 5: Naming Issues ──────────────────────────────────────────────
    ws_nam = wb.create_sheet("Naming")
    _set_header_row(ws_nam, ["Campanas sin naming convention correcto"])
    for i, name in enumerate(bad_names, 2):
        ws_nam.cell(row=i, column=1, value=name)
        if i % 2 == 0:
            ws_nam.cell(row=i, column=1).fill = alt
    ws_nam.freeze_panes = "A2"
    _auto_width(ws_nam)

    # ── Sheet 6: BuyBox (optional) ──────────────────────────────────────────
    if buybox_issues:
        ws_bb = wb.create_sheet("BuyBox")
        headers_bb = list(buybox_issues[0].keys()) if buybox_issues else ["ASIN", "BuyBox %"]
        _set_header_row(ws_bb, headers_bb)
        for i, row_data in enumerate(buybox_issues, 2):
            for col_idx, key in enumerate(headers_bb, 1):
                ws_bb.cell(row=i, column=col_idx, value=row_data.get(key, ""))
            if i % 2 == 0:
                for col in range(1, len(headers_bb) + 1):
                    ws_bb.cell(row=i, column=col).fill = alt
        ws_bb.freeze_panes = "A2"
        _auto_width(ws_bb)

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf


def _set_header_row_at(ws, row_idx, headers):
    fill = PatternFill("solid", fgColor="2D3748")
    font = Font(bold=True, color="FFFFFF", size=9)
    for col_idx, h in enumerate(headers, 1):
        cell = ws.cell(row=row_idx, column=col_idx, value=h)
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center")


# ── Render ───────────────────────────────────────────────────────────────────

def render():
    st.header("Auditoria PPC")
    st.caption("Auditoria integral de cuenta — estructura, eficiencia, desperdicio, cobertura y naming.")
    st.divider()

    # ── Inputs ───────────────────────────────────────────────────────────────
    c1, c2 = st.columns(2)
    with c1:
        target_acos = st.slider(
            "Target ACoS (%)",
            min_value=5, max_value=80, value=25, step=1,
            key="audit_target",
        )
    with c2:
        brand = st.text_input(
            "Marca (para verificar naming convention)",
            placeholder="Ej: Dermaglos",
            key="audit_brand",
        )

    st.markdown("---")

    col_l, col_r = st.columns(2)
    with col_l:
        file_str = st.file_uploader(
            "Search Term Report (.xlsx o .csv) — REQUERIDO",
            type=["csv", "xlsx"],
            key="audit_str",
        )
        file_camp = st.file_uploader(
            "Campaign CSV (.csv) — REQUERIDO",
            type=["csv"],
            key="audit_camp",
        )
    with col_r:
        file_br = st.file_uploader(
            "BR by ASIN (.csv o .xlsx) — opcional (BuyBox)",
            type=["csv", "xlsx"],
            key="audit_br",
        )

    ready = file_str is not None and file_camp is not None

    if not ready:
        st.markdown(
            "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
            "border-radius:12px;margin:1rem 0;'>"
            "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
            "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Sube el STR y el Campaign CSV para ejecutar la auditoría.</div>"
            "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
            "Arrastrá o hacé click en los uploaders de arriba</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    if st.button("Ejecutar Auditoria", type="primary"):
        with st.spinner("Analizando cuenta..."):
            # Parse
            str_df = _parse_str(file_str)
            camp_df = _parse_campaigns(file_camp)
            br_df = _parse_br(file_br) if file_br else None

            if str_df is None or camp_df is None:
                st.error("No se pudieron procesar los archivos. Revisa el formato.")
                return

            # Analysis
            structure = _analyze_structure(camp_df)
            good, total_names, bad_names, naming_pct = _check_naming(camp_df, brand)
            efficiency = _analyze_efficiency(camp_df, target_acos)
            coverage = _analyze_coverage(camp_df)
            buybox_issues = _analyze_buybox(br_df) if br_df is not None else []

            score = _calc_account_score(structure, naming_pct, efficiency, coverage, target_acos)

        # ── Score display ─────────────────────────────────────────────────
        if score >= 80:
            score_color, score_label = "#1B6B2F", "EXCELENTE"
        elif score >= 60:
            score_color, score_label = "#E65100", "BUENO"
        elif score >= 40:
            score_color, score_label = "#E84000", "MEJORABLE"
        else:
            score_color, score_label = "#B71C1C", "CRITICO"

        st.markdown(
            f"""
            <div style='text-align:center;padding:2rem;background:#1A1A1A;
                        border-radius:12px;margin-bottom:1.5rem;'>
                <div style='font-size:5rem;font-weight:900;color:{score_color};
                            line-height:1;'>{score}</div>
                <div style='font-size:1.3rem;color:{score_color};
                            font-weight:700;margin-top:0.5rem;'>{score_label}</div>
                <div style='font-size:0.85rem;color:#888;margin-top:0.4rem;'>
                    Score de cuenta / 100</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        # ── Score breakdown pills ─────────────────────────────────────────
        match_types_used = sum(1 for v in structure["by_match"].values() if v > 0)
        pts_structure = min(20, match_types_used * 4)
        pts_naming = round(naming_pct / 100 * 15)
        acos = efficiency["avg_acos"]
        if acos > 0:
            ratio = acos / target_acos if target_acos > 0 else 2.0
            if ratio <= 1.0: pts_eff = 25
            elif ratio <= 1.5: pts_eff = 18
            elif ratio <= 2.0: pts_eff = 10
            else: pts_eff = max(0, round(25 - ratio * 6))
        else:
            pts_eff = 12
        if efficiency["total_spend"] > 0:
            waste_pct_val = efficiency["wasted_spend"] / efficiency["total_spend"] * 100
            if waste_pct_val < 5: pts_waste = 20
            elif waste_pct_val < 15: pts_waste = 14
            elif waste_pct_val < 30: pts_waste = 8
            else: pts_waste = 2
        else:
            pts_waste = 10
        if coverage:
            avg_t = sum(len(v) for v in coverage.values()) / len(coverage)
            pts_cov = min(20, round(avg_t * 5))
        else:
            pts_cov = 10

        bp1, bp2, bp3, bp4, bp5 = st.columns(5)
        bp1.metric("Estructura", f"{pts_structure}/20")
        bp2.metric("Naming", f"{pts_naming}/15")
        bp3.metric("Eficiencia", f"{pts_eff}/25")
        bp4.metric("Desperdicio", f"{pts_waste}/20")
        bp5.metric("Cobertura", f"{pts_cov}/20")

        st.divider()

        # ── Expanders ────────────────────────────────────────────────────

        with st.expander("Estructura de campanas", expanded=True):
            ec1, ec2, ec3 = st.columns(3)
            with ec1:
                st.markdown("**Por tipo de ad**")
                if structure["by_type"]:
                    for k, v in structure["by_type"].items():
                        st.markdown(f"- {k}: **{v}** campanas")
                else:
                    st.caption("No se detectaron tipos (sin columna Campaign Type).")
            with ec2:
                st.markdown("**Por match type (desde nombre)**")
                for k, v in structure["by_match"].items():
                    if v > 0:
                        st.markdown(f"- {k}: **{v}** campanas")
            with ec3:
                st.markdown("**Portfolios**")
                if structure["portfolios"]:
                    for k, v in structure["portfolios"].items():
                        st.markdown(f"- {k}: **{v}**")
                else:
                    st.caption("Sin portfolios detectados.")

        with st.expander("Naming Convention"):
            st.metric(
                "Cumplimiento naming",
                f"{naming_pct}%",
                delta=f"{good} de {total_names} campanas correctas",
                delta_color="normal" if naming_pct >= 70 else "inverse",
            )
            if not brand:
                st.info("Ingresa el nombre de la marca para mejorar la deteccion de naming.")
            if bad_names:
                st.warning(f"{len(bad_names)} campanas no siguen la naming convention (mostrando hasta 20).")
                st.dataframe(
                    pd.DataFrame({"Campana": bad_names}),
                    use_container_width=True,
                    hide_index=True,
                )
            else:
                st.success("Todas las campanas siguen la naming convention.")

        with st.expander("Eficiencia"):
            e1, e2, e3, e4 = st.columns(4)
            e1.metric("Spend Total", f"${efficiency['total_spend']:,.2f}")
            e2.metric("Sales Total", f"${efficiency['total_sales']:,.2f}")
            e3.metric("ACoS Promedio", f"{efficiency['avg_acos']:.1f}%")
            delta_pp = efficiency["avg_acos"] - target_acos
            e4.metric(
                "vs Target",
                f"{delta_pp:+.1f} pp",
                delta_color="inverse" if delta_pp > 0 else "normal",
            )

            if efficiency["top_spend"]:
                st.markdown("**Top 5 por Spend**")
                st.dataframe(
                    pd.DataFrame(efficiency["top_spend"], columns=["Campana", "Spend ($)"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Spend ($)": st.column_config.NumberColumn(format="$%.2f")},
                )

            if efficiency["top_sales"]:
                st.markdown("**Top 5 por Sales**")
                st.dataframe(
                    pd.DataFrame(efficiency["top_sales"], columns=["Campana", "Sales ($)"]),
                    use_container_width=True,
                    hide_index=True,
                    column_config={"Sales ($)": st.column_config.NumberColumn(format="$%.2f")},
                )

        with st.expander("Desperdicio"):
            d1, d2, d3 = st.columns(3)
            d1.metric("Spend sin ventas (WAS)", f"${efficiency['wasted_spend']:,.2f}")
            d2.metric("Campanas sin ventas", str(efficiency.get("wasted_campaigns", 0)))
            d3.metric("Campanas fantasma (0 imps)", str(efficiency.get("ghost_count", 0)))
            if efficiency["total_spend"] > 0:
                waste_ratio = efficiency["wasted_spend"] / efficiency["total_spend"] * 100
                if waste_ratio > 30:
                    st.error(f"Desperdicio critico: {waste_ratio:.1f}% del spend sin retorno.")
                elif waste_ratio > 15:
                    st.warning(f"Desperdicio elevado: {waste_ratio:.1f}% del spend sin retorno.")
                else:
                    st.success(f"Desperdicio bajo: {waste_ratio:.1f}% del spend sin retorno.")

        with st.expander("Cobertura de Funnel por ASIN"):
            if coverage:
                rows = []
                for asin, types in sorted(coverage.items()):
                    rows.append({
                        "ASIN": asin,
                        "Auto": "Si" if "Auto" in types else "No",
                        "Broad": "Si" if "Broad" in types else "No",
                        "Phrase": "Si" if "Phrase" in types else "No",
                        "Exact": "Si" if "Exact" in types else "No",
                        "PAT": "Si" if "PAT" in types else "No",
                        "Tipos activos": len(types),
                        "Funnel completo": "Si" if len(types) >= 3 else "No",
                    })
                st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
            else:
                st.info("No se detectaron ASINs en los nombres de campana (patron B0XXXXXXXXX).")

        if br_df is not None:
            with st.expander("BuyBox"):
                if buybox_issues:
                    st.warning(f"{len(buybox_issues)} ASINs con BuyBox < 90%")
                    st.dataframe(
                        pd.DataFrame(buybox_issues),
                        use_container_width=True,
                        hide_index=True,
                    )
                else:
                    st.success("Todos los ASINs con BuyBox >= 90%.")

        # ── Excel download ────────────────────────────────────────────────
        st.divider()
        excel_buf = _build_audit_excel(
            score, structure, naming_pct, bad_names, efficiency,
            coverage, buybox_issues, brand or "", target_acos,
        )
        filename = f"PPC_Audit_{brand or 'cuenta'}_{datetime.date.today().strftime('%Y%m%d')}.xlsx"
        st.download_button(
            label="Descargar Reporte de Auditoria (.xlsx)",
            data=excel_buf,
            file_name=filename,
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="audit_dl",
        )
