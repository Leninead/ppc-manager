import io

import streamlit as st
import pandas as pd

from core.helpers import kpi_card


# ── Helpers ─────────────────────────────────────────────────────────────────

def _to_num(series):
    """Coerce a series to numeric, stripping $, %, commas."""
    return pd.to_numeric(
        series.astype(str).str.replace(r"[\$%,]", "", regex=True),
        errors="coerce",
    ).fillna(0)


def _badge(text, level="ok"):
    """HTML badge. level: ok | warn | crit."""
    styles = {
        "ok":   "background:#e6f4ed;color:#2a6e4e;",
        "warn": "background:#fdf3e3;color:#c07a1a;",
        "crit": "background:#fbeae7;color:#c8402a;",
    }
    s = styles.get(level, styles["ok"])
    return (
        f"<span style='{s}padding:3px 10px;border-radius:6px;"
        f"font-weight:600;font-size:0.82rem;'>{text}</span>"
    )


# ── Parser ──────────────────────────────────────────────────────────────────

_METRIC_INT = ["Impressions", "Clicks", "Spend", "Sales", "Orders", "Units"]
_METRIC_PCT = ["ACOS", "Click-through Rate", "Conversion Rate", "CPC", "ROAS"]


def _numericize(df):
    """Numericize known metric columns in-place and return df."""
    for col in _METRIC_INT:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    for col in _METRIC_PCT:
        if col in df.columns:
            df[col] = _to_num(df[col])
    return df


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_bulk(data, name):
    """Parse Bulk File XLSX multi-sheet. Returns dict of DataFrames."""
    buf = io.BytesIO(data)
    xls = pd.ExcelFile(buf)
    result = {}

    # ── SP ──
    if "Sponsored Products Campaigns" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="Sponsored Products Campaigns")
        df.columns = df.columns.str.strip()
        _numericize(df)
        result["sp"] = df
        if "Entity" in df.columns:
            result["sp_campaigns"] = df[df["Entity"] == "Campaign"].copy()
            result["sp_adgroups"] = df[df["Entity"] == "Ad Group"].copy()
            result["sp_keywords"] = df[df["Entity"] == "Keyword"].copy()
            result["sp_pt"] = df[df["Entity"] == "Product Targeting"].copy()
            result["sp_bid_adj"] = df[df["Entity"] == "Bidding Adjustment"].copy()
            result["sp_neg_kw"] = df[df["Entity"] == "Negative Keyword"].copy()
            result["sp_neg_pt"] = df[df["Entity"] == "Negative Product Targeting"].copy()

    # ── SB ──
    if "Sponsored Brands Campaigns" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="Sponsored Brands Campaigns")
        df.columns = df.columns.str.strip()
        _numericize(df)
        result["sb"] = df
        if "Entity" in df.columns and len(df) > 0:
            result["sb_campaigns"] = df[df["Entity"] == "Campaign"].copy()
            result["sb_keywords"] = df[df["Entity"] == "Keyword"].copy()
        else:
            result["sb_campaigns"] = pd.DataFrame()
            result["sb_keywords"] = pd.DataFrame()

    # ── SD ──
    if "Sponsored Display Campaigns" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="Sponsored Display Campaigns")
        df.columns = df.columns.str.strip()
        _numericize(df)
        result["sd"] = df
        if "Entity" in df.columns and len(df) > 0:
            result["sd_campaigns"] = df[df["Entity"] == "Campaign"].copy()
        else:
            result["sd_campaigns"] = pd.DataFrame()

    # ── SP Search Term Report ──
    if "SP Search Term Report" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="SP Search Term Report")
        df.columns = df.columns.str.strip()
        _numericize(df)
        result["sp_str"] = df

    # ── SB Search Term Report ──
    if "SB Search Term Report" in xls.sheet_names:
        df = pd.read_excel(xls, sheet_name="SB Search Term Report")
        df.columns = df.columns.str.strip()
        _numericize(df)
        result["sb_str"] = df

    return result


# ── Metric aggregation helpers ──────────────────────────────────────────────

def _sum_metrics(df):
    """Return dict with Spend, Sales, Impressions, Clicks, Orders from df."""
    if df is None or len(df) == 0:
        return {"Spend": 0, "Sales": 0, "Impressions": 0, "Clicks": 0, "Orders": 0}
    return {
        "Spend": df["Spend"].sum() if "Spend" in df.columns else 0,
        "Sales": df["Sales"].sum() if "Sales" in df.columns else 0,
        "Impressions": df["Impressions"].sum() if "Impressions" in df.columns else 0,
        "Clicks": df["Clicks"].sum() if "Clicks" in df.columns else 0,
        "Orders": df["Orders"].sum() if "Orders" in df.columns else 0,
    }


def _acos(spend, sales):
    return (spend / sales * 100) if sales > 0 else 0


def _seg_row(label, df):
    """Build a segment metrics row dict from a DataFrame."""
    if df is None or len(df) == 0:
        return {
            "Segmento": label, "# Targets": 0, "Spend": 0, "Sales": 0,
            "ACoS": 0, "Clicks": 0, "Orders": 0, "Impressions": 0,
            "CTR": 0, "CVR": 0, "CPC": 0, "% Spend": 0,
        }
    s = df["Spend"].sum() if "Spend" in df.columns else 0
    sa = df["Sales"].sum() if "Sales" in df.columns else 0
    cl = df["Clicks"].sum() if "Clicks" in df.columns else 0
    im = df["Impressions"].sum() if "Impressions" in df.columns else 0
    od = df["Orders"].sum() if "Orders" in df.columns else 0
    return {
        "Segmento": label,
        "# Targets": len(df),
        "Spend": round(s, 2),
        "Sales": round(sa, 2),
        "ACoS": round(_acos(s, sa), 1),
        "Clicks": int(cl),
        "Orders": int(od),
        "Impressions": int(im),
        "CTR": round((cl / im * 100) if im > 0 else 0, 2),
        "CVR": round((od / cl * 100) if cl > 0 else 0, 2),
        "CPC": round((s / cl) if cl > 0 else 0, 2),
        "% Spend": 0,  # filled after
    }


def _color_acos(val):
    """Style callback for ACoS column."""
    try:
        v = float(val)
    except (ValueError, TypeError):
        return ""
    if v <= 0:
        return "color:#999"
    if v <= 30:
        return "background:#e6f4ed;color:#2a6e4e"
    if v <= 55:
        return "background:#fdf3e3;color:#c07a1a"
    return "background:#fbeae7;color:#c8402a"


def _build_segment_table(rows, total_spend):
    """Convert list of seg_row dicts to a styled DataFrame."""
    for r in rows:
        r["% Spend"] = round((r["Spend"] / total_spend * 100) if total_spend > 0 else 0, 1)
    df = pd.DataFrame(rows)
    col_order = [
        "Segmento", "# Targets", "Spend", "Sales", "ACoS",
        "Clicks", "Orders", "CTR", "CVR", "CPC", "% Spend",
    ]
    df = df[[c for c in col_order if c in df.columns]]
    return df


def _analyze_target_graduation(sp_kw_df, sp_camp_df, brand_terms=None):
    """Analyze targets with 0 impressions in campaigns that DO have traffic."""
    if sp_kw_df is None or len(sp_kw_df) == 0:
        return pd.DataFrame()

    required = ["Campaign ID", "Impressions"]
    if not all(c in sp_kw_df.columns for c in required):
        return pd.DataFrame()

    # 1. Total impressions per campaign (across all entities in that campaign)
    camp_imp = sp_kw_df.groupby("Campaign ID")["Impressions"].sum()

    # 2. Targets with 0 impressions
    zero_imp = sp_kw_df[sp_kw_df["Impressions"] == 0].copy()
    if zero_imp.empty:
        return pd.DataFrame()

    # 3. Map campaign-level impressions
    zero_imp["Campaign Impressions"] = zero_imp["Campaign ID"].map(camp_imp).fillna(0)

    # 4. Only those in campaigns WITH traffic
    orphans = zero_imp[zero_imp["Campaign Impressions"] > 0].copy()
    if orphans.empty:
        return pd.DataFrame()

    # 5. Classify recommendation
    bt = [t.lower() for t in brand_terms] if brand_terms else []

    def _recommend(row):
        state = str(row.get("State", "")).lower()
        spend = float(row.get("Spend", 0) or 0)
        sales = float(row.get("Sales", 0) or 0)
        orders = float(row.get("Orders", 0) or 0)
        kw_text = str(row.get("Keyword Text", "")).lower()

        if state != "enabled":
            return "⏸️ YA PAUSADO"

        # Brand terms → always keep
        if bt and any(t in kw_text for t in bt):
            return "🛡️ MANTENER — keyword de marca"

        # Had sales historically → bid too low
        if sales > 0 or orders > 0:
            return "🔼 SUBIR BID — tuvo ventas, bid probable bajo"

        # Spent but never converted → pause
        if spend > 0 and orders == 0:
            return "🔴 PAUSAR — gastó sin convertir"

        # Never had anything → graduate
        return "🟡 GRADUAR A SKAG — mover a campaña propia con bid más alto"

    orphans["Recomendación"] = orphans.apply(_recommend, axis=1)
    return orphans


def _build_audit_excel(
    kpi_dict, seg_sp_df, seg_sb_df, seg_sd_df,
    top5_camps_df, classif_df, dupes_df,
    audit_mixed, audit_target_was, audit_st_was,
    graduation_df=None,
):
    """Generate multi-sheet audit Excel. Returns bytes."""
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        # Sheet 1 — Resumen KPIs
        kpi_rows = [[k, v] for k, v in kpi_dict.items()]
        pd.DataFrame(kpi_rows, columns=["Metrica", "Valor"]).to_excel(
            writer, sheet_name="Resumen KPIs", index=False,
        )

        # Sheet 2 — Performance Segmento
        parts = []
        if seg_sp_df is not None and len(seg_sp_df) > 0:
            parts.append(seg_sp_df)
        if seg_sb_df is not None and len(seg_sb_df) > 0:
            sep = pd.DataFrame([{"Segmento": ""}])
            parts.append(sep)
            parts.append(seg_sb_df)
        if seg_sd_df is not None and len(seg_sd_df) > 0:
            sep = pd.DataFrame([{"Segmento": ""}])
            parts.append(sep)
            parts.append(seg_sd_df)
        if parts:
            pd.concat(parts, ignore_index=True).to_excel(
                writer, sheet_name="Performance Segmento", index=False,
            )

        # Sheet 3 — Auditoría
        audit_rows = []
        audit_rows.append(["Check", "Resultado", "Detalle"])
        audit_rows.append(["Match Types Mixtos", audit_mixed[0], audit_mixed[1]])
        audit_rows.append(["Target WAS", audit_target_was[0], audit_target_was[1]])
        audit_rows.append(["Search Term WAS", audit_st_was[0], audit_st_was[1]])
        pd.DataFrame(audit_rows[1:], columns=audit_rows[0]).to_excel(
            writer, sheet_name="Auditoria", index=False,
        )

        # Sheet 4 — Top Campañas
        if top5_camps_df is not None and len(top5_camps_df) > 0:
            top5_camps_df.to_excel(writer, sheet_name="Top Campanas", index=False)

        # Sheet 5 — Clasificación Targets
        if classif_df is not None and len(classif_df) > 0:
            classif_df.to_excel(writer, sheet_name="Clasificacion Targets", index=False)

        # Sheet 6 — Duplicación Targets
        if dupes_df is not None and len(dupes_df) > 0:
            dupes_df.to_excel(writer, sheet_name="Duplicacion Targets", index=False)

        # Sheet 7 — Target Graduation
        if graduation_df is not None and len(graduation_df) > 0:
            grad_cols = [
                c for c in [
                    "Campaign Name", "Ad Group Name", "Keyword Text", "Match Type",
                    "Bid", "Spend", "Sales", "Orders", "Campaign Impressions",
                    "Recomendación",
                ] if c in graduation_df.columns
            ]
            graduation_df[grad_cols].to_excel(
                writer, sheet_name="Target Graduation", index=False,
            )

    return buf.getvalue()


# ── Render ──────────────────────────────────────────────────────────────────

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🛡️</span>"
        "<div><div style='font-size:1.3rem;font-weight:700;'>PPC Audit Pro</div>"
        "<div style='font-size:0.82rem;color:#888;'>"
        "Auditoría profunda desde Bulk File de Amazon Advertising</div>"
        "</div></div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Auditoría completa de la estructura de campañas desde Bulk File multi-hoja. Breakdown real SP/SB/SD, 10 segmentos y 5 deep checks.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("Campaign Manager → Bulk Operations → Create Custom Spreadsheet (.xlsx). BR opcional para TACoS y Revenue total.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("PPC Insights (M18) para health score por ASIN o Bid Optimizer (M9) para ajustar bids.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el Bulk File (.xlsx) con las 5 hojas (SP/SB/SD Campaigns + SP/SB STR)\n"
            "2. Subí el BR opcional + ingresá brand terms para clasificar targets\n"
            "3. Revisá Tab 1 KPIs → Tab 2 Estructura → Tab 3 Performance → Tab 4 Deep Checks → Tab 6 Target Graduation\n"
            "4. Descargá el Excel con 6 hojas (KPIs + Segmentos + Auditoría + Top + Duplicados + Graduation)"
        )

    # ── Uploads ─────────────────────────────────────────────────
    col_u1, col_u2 = st.columns(2)
    with col_u1:
        bulk_file = st.file_uploader(
            "📦 Bulk File (.xlsx)", type=["xlsx"], key="audit_bulk",
        )
    with col_u2:
        br_file = st.file_uploader(
            "💰 Business Report (.xlsx/.csv) — opcional",
            type=["xlsx", "csv"], key="audit_br",
        )

    if not bulk_file:
        st.markdown(
            "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
            "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
            "<div style='font-size:1.5rem;'>📦</div>"
            "<div style='font-weight:600;margin-top:0.5rem;'>Subí el Bulk File</div>"
            "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
            "Amazon Advertising → Campaign Manager → Bulk Operations "
            "→ Create spreadsheet for download</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Parse bulk ──────────────────────────────────────────────
    bulk = _parse_bulk(bulk_file.getvalue(), bulk_file.name)

    # ── Brand terms ─────────────────────────────────────────────
    brand_input = st.text_input(
        "Brand terms (separados por coma)",
        placeholder="ej: 360 essentials, escape plus, freedom plus",
        key="audit_brand_terms",
    )
    brand_terms = (
        [t.strip().lower() for t in brand_input.split(",") if t.strip()]
        if brand_input else []
    )

    # ── Parse BR ────────────────────────────────────────────────
    br_df = None
    if br_file:
        buf_br = io.BytesIO(br_file.getvalue())
        br_df = (
            pd.read_excel(buf_br)
            if br_file.name.endswith(".xlsx")
            else pd.read_csv(buf_br)
        )
        br_df.columns = br_df.columns.str.strip()

    # ── Reference DataFrames ────────────────────────────────────
    sp_camps = bulk.get("sp_campaigns", pd.DataFrame())
    sp_kws = bulk.get("sp_keywords", pd.DataFrame())
    sp_pts = bulk.get("sp_pt", pd.DataFrame())
    sp_neg_kw = bulk.get("sp_neg_kw", pd.DataFrame())
    sp_str_df = bulk.get("sp_str", pd.DataFrame())

    sb_df = bulk.get("sb", pd.DataFrame())
    sb_camps = bulk.get("sb_campaigns", pd.DataFrame())
    sb_kws = bulk.get("sb_keywords", pd.DataFrame())
    sb_str_df = bulk.get("sb_str", pd.DataFrame())

    sd_df = bulk.get("sd", pd.DataFrame())
    sd_camps = bulk.get("sd_campaigns", pd.DataFrame())

    n_sp = len(sp_camps)
    n_sb = len(sb_camps)
    n_sd = len(sd_camps)

    st.success(
        f"✅ Bulk cargado — SP: {n_sp} campañas, {len(sp_kws)} keywords, "
        f"{len(sp_pts)} PT | SB: {n_sb} campañas | SD: {n_sd} campañas | "
        f"SP STR: {len(sp_str_df)} terms"
    )

    # ── Tabs ────────────────────────────────────────────────────
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "📊 KPIs Overview",
        "🛠️ Auditoría Estructura",
        "🎯 Performance Segmento",
        "🔍 Deep Checks",
        "📥 Export",
        "🎯 Target Graduation",
    ])

    # ════════════════════════════════════════════════════════════
    # TAB 1 — KPIs Overview
    # ════════════════════════════════════════════════════════════
    with tab1:
        sp_m = _sum_metrics(sp_camps)
        sb_m = _sum_metrics(sb_camps)
        sd_m = _sum_metrics(sd_camps)

        total_spend = sp_m["Spend"] + sb_m["Spend"] + sd_m["Spend"]
        total_sales = sp_m["Sales"] + sb_m["Sales"] + sd_m["Sales"]
        total_imps = sp_m["Impressions"] + sb_m["Impressions"] + sd_m["Impressions"]
        total_clicks = sp_m["Clicks"] + sb_m["Clicks"] + sd_m["Clicks"]
        total_orders = sp_m["Orders"] + sb_m["Orders"] + sd_m["Orders"]
        acos_overall = _acos(total_spend, total_sales)

        # BR-derived metrics
        revenue_total = 0
        has_br = br_df is not None and len(br_df) > 0
        if has_br:
            rev_col = None
            for candidate in [
                "Ordered Product Sales",
                "Ordered Product Sales Amount",
                "ordered product sales",
            ]:
                if candidate in br_df.columns:
                    rev_col = candidate
                    break
            if rev_col is None:
                for c in br_df.columns:
                    if "ordered" in c.lower() and "sales" in c.lower():
                        rev_col = c
                        break
            if rev_col:
                revenue_total = _to_num(br_df[rev_col]).sum()

        tacos = (total_spend / revenue_total * 100) if revenue_total > 0 else 0
        organic_sales = max(0, revenue_total - total_sales) if has_br else 0
        organic_pct = (organic_sales / revenue_total * 100) if revenue_total > 0 else 0

        if has_br and revenue_total > 0:
            # 6 cards
            r1 = st.columns(3)
            with r1[0]:
                st.markdown(
                    kpi_card("Revenue Total", f"${revenue_total:,.2f}"),
                    unsafe_allow_html=True,
                )
            with r1[1]:
                st.markdown(
                    kpi_card(
                        "Ventas Orgánicas",
                        f"${organic_sales:,.2f}",
                        delta=organic_pct,
                    ),
                    unsafe_allow_html=True,
                )
                st.caption(f"{organic_pct:.1f}% del revenue")
            with r1[2]:
                tacos_delta = tacos - 15  # benchmark 15%
                st.markdown(
                    kpi_card("TACoS", f"{tacos:.1f}%", delta=tacos_delta, delta_good=False),
                    unsafe_allow_html=True,
                )
                if tacos < 10:
                    st.markdown(_badge("Excelente", "ok"), unsafe_allow_html=True)
                elif tacos < 20:
                    st.markdown(_badge("Saludable", "ok"), unsafe_allow_html=True)
                elif tacos < 35:
                    st.markdown(_badge("Alto", "warn"), unsafe_allow_html=True)
                else:
                    st.markdown(_badge("Crítico", "crit"), unsafe_allow_html=True)

            r2 = st.columns(3)
        else:
            st.info(
                "💡 Subí el Business Report para ver TACoS, Revenue y Ventas Orgánicas."
            )
            r2 = st.columns(3)

        # ACoS / Impressions / Spend+Sales — always shown
        with r2[0]:
            st.markdown(
                kpi_card("ACoS Overall", f"{acos_overall:.1f}%"),
                unsafe_allow_html=True,
            )
            breakdown = []
            if sp_m["Sales"] > 0:
                breakdown.append(f"SP {_acos(sp_m['Spend'], sp_m['Sales']):.1f}%")
            if sb_m["Sales"] > 0:
                breakdown.append(f"SB {_acos(sb_m['Spend'], sb_m['Sales']):.1f}%")
            if sd_m["Sales"] > 0:
                breakdown.append(f"SD {_acos(sd_m['Spend'], sd_m['Sales']):.1f}%")
            if breakdown:
                st.caption(" | ".join(breakdown))

        with r2[1]:
            st.markdown(
                kpi_card("Impressions", f"{total_imps:,.0f}"),
                unsafe_allow_html=True,
            )
            parts = []
            if sp_m["Impressions"] > 0:
                parts.append(
                    f"SP {sp_m['Impressions'] / total_imps * 100:.0f}%"
                    if total_imps > 0 else "SP —"
                )
            if sb_m["Impressions"] > 0:
                parts.append(
                    f"SB {sb_m['Impressions'] / total_imps * 100:.0f}%"
                    if total_imps > 0 else "SB —"
                )
            if sd_m["Impressions"] > 0:
                parts.append(
                    f"SD {sd_m['Impressions'] / total_imps * 100:.0f}%"
                    if total_imps > 0 else "SD —"
                )
            if parts:
                st.caption(" | ".join(parts))

        with r2[2]:
            st.markdown(
                kpi_card("PPC Spend", f"${total_spend:,.2f}"),
                unsafe_allow_html=True,
            )
            st.caption(
                f"Sales: ${total_sales:,.2f} | "
                f"SP ${sp_m['Spend']:,.0f} / SB ${sb_m['Spend']:,.0f} / SD ${sd_m['Spend']:,.0f}"
            )

        # Extra row: Clicks, Orders, CTR/CVR
        st.markdown("")
        r3 = st.columns(4)
        with r3[0]:
            st.markdown(
                kpi_card("Clicks", f"{total_clicks:,.0f}"), unsafe_allow_html=True,
            )
        with r3[1]:
            st.markdown(
                kpi_card("Orders", f"{total_orders:,.0f}"), unsafe_allow_html=True,
            )
        with r3[2]:
            ctr_val = (total_clicks / total_imps * 100) if total_imps > 0 else 0
            st.markdown(
                kpi_card("CTR", f"{ctr_val:.2f}%"), unsafe_allow_html=True,
            )
        with r3[3]:
            cvr_val = (total_orders / total_clicks * 100) if total_clicks > 0 else 0
            st.markdown(
                kpi_card("CVR", f"{cvr_val:.2f}%"), unsafe_allow_html=True,
            )

    # ════════════════════════════════════════════════════════════
    # TAB 2 — Auditoría de Estructura
    # ════════════════════════════════════════════════════════════
    with tab2:
        c1, c2, c3 = st.columns(3)

        # ── Card 1: Match Types Mixtos ──────────────────────────
        with c1:
            st.markdown("**Match Types Mixtos**")

            mixed_camps = []
            if len(sp_kws) > 0 and "Campaign Name" in sp_kws.columns and "Match Type" in sp_kws.columns:
                mt_per_camp = (
                    sp_kws.groupby("Campaign Name")["Match Type"]
                    .nunique()
                    .reset_index()
                    .rename(columns={"Match Type": "n_match"})
                )
                mixed_camps = mt_per_camp[mt_per_camp["n_match"] > 1]["Campaign Name"].tolist()

            n_mixed = len(mixed_camps)
            if n_mixed == 0:
                st.markdown(_badge("OK — 0 campañas mixtas", "ok"), unsafe_allow_html=True)
            else:
                st.markdown(
                    _badge(f"REVISAR — {n_mixed} campañas mixtas", "warn"),
                    unsafe_allow_html=True,
                )
                with st.expander(f"Ver {n_mixed} campañas mixtas"):
                    for camp_name in mixed_camps[:20]:
                        st.caption(f"• {camp_name}")

            # Match type distribution
            st.markdown("")
            st.caption("Distribución SP Keywords:")
            if len(sp_kws) > 0 and "Match Type" in sp_kws.columns:
                mt_dist = sp_kws["Match Type"].value_counts()
                for mt, cnt in mt_dist.items():
                    st.caption(f"  {mt}: {cnt}")
            else:
                st.caption("  Sin datos")

            # SB match types
            if len(sb_kws) > 0 and "Match Type" in sb_kws.columns:
                st.caption("Distribución SB Keywords:")
                mt_dist_sb = sb_kws["Match Type"].value_counts()
                for mt, cnt in mt_dist_sb.items():
                    st.caption(f"  {mt}: {cnt}")

        # ── Card 2: Target WAS ──────────────────────────────────
        with c2:
            st.markdown("**Target WAS (Wasted Ad Spend)**")

            # SP Manual: keywords + product targeting with spend > 0 and sales == 0
            sp_manual_targets = pd.concat([sp_kws, sp_pts], ignore_index=True)
            sp_manual_was = 0
            sp_manual_spend = 0
            sp_was_count = 0
            if len(sp_manual_targets) > 0 and "Spend" in sp_manual_targets.columns and "Sales" in sp_manual_targets.columns:
                sp_manual_spend = sp_manual_targets["Spend"].sum()
                mask = (sp_manual_targets["Spend"] > 0) & (sp_manual_targets["Sales"] == 0)
                sp_manual_was = sp_manual_targets.loc[mask, "Spend"].sum()
                sp_was_count = mask.sum()

            # SB keywords
            sb_was = 0
            sb_was_count = 0
            if len(sb_kws) > 0 and "Spend" in sb_kws.columns and "Sales" in sb_kws.columns:
                mask_sb = (sb_kws["Spend"] > 0) & (sb_kws["Sales"] == 0)
                sb_was = sb_kws.loc[mask_sb, "Spend"].sum()
                sb_was_count = mask_sb.sum()

            # SD: ad groups + audience targeting
            sd_was = 0
            sd_was_count = 0
            if len(sd_df) > 0 and "Entity" in sd_df.columns and "Spend" in sd_df.columns and "Sales" in sd_df.columns:
                sd_targets = sd_df[sd_df["Entity"].isin(["Ad Group", "Audience Targeting"])]
                if len(sd_targets) > 0:
                    mask_sd = (sd_targets["Spend"] > 0) & (sd_targets["Sales"] == 0)
                    sd_was = sd_targets.loc[mask_sd, "Spend"].sum()
                    sd_was_count = mask_sd.sum()

            total_was = sp_manual_was + sb_was + sd_was
            total_target_spend = sp_manual_spend + (
                sb_kws["Spend"].sum() if len(sb_kws) > 0 and "Spend" in sb_kws.columns else 0
            )
            was_pct = (total_was / total_target_spend * 100) if total_target_spend > 0 else 0

            if was_pct < 20:
                st.markdown(_badge(f"OK — {was_pct:.1f}% waste", "ok"), unsafe_allow_html=True)
            elif was_pct < 40:
                st.markdown(_badge(f"REVISAR — {was_pct:.1f}% waste", "warn"), unsafe_allow_html=True)
            else:
                st.markdown(_badge(f"CRÍTICO — {was_pct:.1f}% waste", "crit"), unsafe_allow_html=True)

            st.markdown(f"**${total_was:,.2f}** desperdicio en targets")
            st.caption(f"SP: ${sp_manual_was:,.2f} ({sp_was_count} targets)")
            st.caption(f"SB: ${sb_was:,.2f} ({sb_was_count} targets)")
            st.caption(f"SD: ${sd_was:,.2f} ({sd_was_count} targets)")

        # ── Card 3: Search Term WAS ─────────────────────────────
        with c3:
            st.markdown("**Search Term WAS**")

            # SP STR
            sp_st_was = 0
            sp_st_was_count = 0
            sp_st_spend_total = 0
            if len(sp_str_df) > 0 and "Spend" in sp_str_df.columns and "Sales" in sp_str_df.columns:
                sp_st_spend_total = sp_str_df["Spend"].sum()
                mask_sp_st = (sp_str_df["Spend"] > 0) & (sp_str_df["Sales"] == 0)
                sp_st_was = sp_str_df.loc[mask_sp_st, "Spend"].sum()
                sp_st_was_count = mask_sp_st.sum()

            # SB STR
            sb_st_was = 0
            sb_st_was_count = 0
            if len(sb_str_df) > 0 and "Spend" in sb_str_df.columns and "Sales" in sb_str_df.columns:
                mask_sb_st = (sb_str_df["Spend"] > 0) & (sb_str_df["Sales"] == 0)
                sb_st_was = sb_str_df.loc[mask_sb_st, "Spend"].sum()
                sb_st_was_count = mask_sb_st.sum()

            total_st_was = sp_st_was + sb_st_was
            st_was_pct = (sp_st_was / sp_st_spend_total * 100) if sp_st_spend_total > 0 else 0

            if st_was_pct < 25:
                st.markdown(_badge(f"OK — {st_was_pct:.1f}% SP ST waste", "ok"), unsafe_allow_html=True)
            elif st_was_pct < 40:
                st.markdown(_badge(f"REVISAR — {st_was_pct:.1f}% SP ST waste", "warn"), unsafe_allow_html=True)
            else:
                st.markdown(_badge(f"CRÍTICO — {st_was_pct:.1f}% SP ST waste", "crit"), unsafe_allow_html=True)

            st.markdown(f"**${total_st_was:,.2f}** desperdicio en search terms")
            st.caption(f"SP: ${sp_st_was:,.2f} ({sp_st_was_count} terms)")
            st.caption(f"SB: ${sb_st_was:,.2f} ({sb_st_was_count} terms)")

            # Top 5 search terms sin ventas
            if sp_st_was_count > 0:
                st.markdown("")
                st.caption("Top 5 SP search terms sin ventas:")
                top5_cols = ["Customer Search Term", "Spend", "Clicks", "Impressions"]
                available = [c for c in top5_cols if c in sp_str_df.columns]
                if "Customer Search Term" not in sp_str_df.columns:
                    for c in sp_str_df.columns:
                        if "search" in c.lower() and "term" in c.lower():
                            available = [c] + [x for x in available if x != "Customer Search Term"]
                            break
                top5 = (
                    sp_str_df[(sp_str_df["Spend"] > 0) & (sp_str_df["Sales"] == 0)]
                    .sort_values("Spend", ascending=False)
                    .head(5)
                )
                if len(available) > 0 and len(top5) > 0:
                    display_cols = [c for c in available if c in top5.columns]
                    if display_cols:
                        st.dataframe(
                            top5[display_cols],
                            use_container_width=True,
                            hide_index=True,
                            height=min(38 + 35 * len(top5), 220),
                        )

    # ════════════════════════════════════════════════════════════
    # TAB 3 — Performance por Segmento
    # ════════════════════════════════════════════════════════════
    with tab3:
        sp_total_spend = sp_camps["Spend"].sum() if len(sp_camps) > 0 and "Spend" in sp_camps.columns else 0

        # ── SP Segments ─────────────────────────────────────────
        st.markdown(
            "<div style='background:#1d4b8f;color:white;padding:6px 14px;"
            "border-radius:8px;font-weight:600;margin-bottom:0.5rem;'>"
            "Sponsored Products</div>",
            unsafe_allow_html=True,
        )

        sp_seg_rows = []
        has_mt = "Match Type" in sp_kws.columns if len(sp_kws) > 0 else False
        if has_mt:
            sp_seg_rows.append(_seg_row("KW Exact", sp_kws[sp_kws["Match Type"] == "Exact"]))
            sp_seg_rows.append(_seg_row("KW Phrase", sp_kws[sp_kws["Match Type"] == "Phrase"]))
            sp_seg_rows.append(_seg_row("KW Broad", sp_kws[sp_kws["Match Type"] == "Broad"]))

        has_pte = "Product Targeting Expression" in sp_pts.columns if len(sp_pts) > 0 else False
        if has_pte:
            sp_seg_rows.append(_seg_row(
                "PT ASIN Targeting",
                sp_pts[sp_pts["Product Targeting Expression"].astype(str).str.contains("asin", case=False, na=False)],
            ))
            sp_seg_rows.append(_seg_row(
                "PT Category Targeting",
                sp_pts[sp_pts["Product Targeting Expression"].astype(str).str.contains("category", case=False, na=False)],
            ))

        # AUTO segments from SP STR
        auto_camp_ids = set()
        if len(sp_camps) > 0 and "Targeting Type" in sp_camps.columns and "Campaign ID" in sp_camps.columns:
            auto_camp_ids = set(
                sp_camps[sp_camps["Targeting Type"].astype(str).str.lower() == "auto"]["Campaign ID"].dropna()
            )
        elif len(sp_camps) > 0 and "Targeting Type" in sp_camps.columns and "Campaign Name" in sp_camps.columns:
            auto_camp_ids = set(
                sp_camps[sp_camps["Targeting Type"].astype(str).str.lower() == "auto"]["Campaign Name"].dropna()
            )

        if len(sp_str_df) > 0 and "Product Targeting Expression" in sp_str_df.columns:
            # Determine join key
            join_col = None
            if "Campaign ID" in sp_str_df.columns and len(auto_camp_ids) > 0:
                join_col = "Campaign ID"
            elif "Campaign Name" in sp_str_df.columns and len(auto_camp_ids) > 0:
                join_col = "Campaign Name"

            if join_col and auto_camp_ids:
                auto_str = sp_str_df[sp_str_df[join_col].isin(auto_camp_ids)]
            else:
                # Fallback: use PTE to detect auto terms
                auto_str = sp_str_df[sp_str_df["Product Targeting Expression"].astype(str).str.strip() != ""]

            pte = auto_str["Product Targeting Expression"].astype(str).str.lower().str.strip()
            sp_seg_rows.append(_seg_row("AUTO Close Match", auto_str[pte == "close-match"]))
            sp_seg_rows.append(_seg_row("AUTO Loose Match", auto_str[pte == "loose-match"]))
            sp_seg_rows.append(_seg_row("AUTO Substitutes", auto_str[pte.str.contains("substitutes", na=False)]))
            sp_seg_rows.append(_seg_row("AUTO Complements", auto_str[pte.str.contains("complements", na=False)]))

        # TOTAL SP row
        sp_seg_rows.append(_seg_row("TOTAL SP", sp_camps))

        seg_sp_df = _build_segment_table(sp_seg_rows, sp_total_spend)

        if len(seg_sp_df) > 0:
            styled_sp = seg_sp_df.style.map(_color_acos, subset=["ACoS"])
            st.dataframe(styled_sp, use_container_width=True, hide_index=True, height=min(38 + 35 * len(seg_sp_df), 500))
        else:
            st.caption("Sin datos SP")

        # ── SB Segments ─────────────────────────────────────────
        seg_sb_df = pd.DataFrame()
        if n_sb > 0:
            st.markdown("")
            st.markdown(
                "<div style='background:#6b2d8f;color:white;padding:6px 14px;"
                "border-radius:8px;font-weight:600;margin-bottom:0.5rem;'>"
                "Sponsored Brands</div>",
                unsafe_allow_html=True,
            )

            sb_seg_rows = []
            has_sb_mt = "Match Type" in sb_kws.columns if len(sb_kws) > 0 else False
            if has_sb_mt:
                sb_seg_rows.append(_seg_row("KW Exact", sb_kws[sb_kws["Match Type"] == "Exact"]))
                sb_seg_rows.append(_seg_row("KW Phrase", sb_kws[sb_kws["Match Type"] == "Phrase"]))
                sb_seg_rows.append(_seg_row("KW Broad", sb_kws[sb_kws["Match Type"] == "Broad"]))

            sb_total_spend = sb_camps["Spend"].sum() if len(sb_camps) > 0 and "Spend" in sb_camps.columns else 0
            sb_seg_rows.append(_seg_row("TOTAL SB", sb_camps))
            seg_sb_df = _build_segment_table(sb_seg_rows, sb_total_spend)

            styled_sb = seg_sb_df.style.map(_color_acos, subset=["ACoS"])
            st.dataframe(styled_sb, use_container_width=True, hide_index=True, height=min(38 + 35 * len(seg_sb_df), 300))
        else:
            st.caption("Sin datos de SB en este Bulk File")

        # ── SD Segments ─────────────────────────────────────────
        seg_sd_df = pd.DataFrame()
        if n_sd > 0:
            st.markdown("")
            st.markdown(
                "<div style='background:#2a6e4e;color:white;padding:6px 14px;"
                "border-radius:8px;font-weight:600;margin-bottom:0.5rem;'>"
                "Sponsored Display</div>",
                unsafe_allow_html=True,
            )

            sd_seg_rows = []
            if len(sd_df) > 0 and "Entity" in sd_df.columns and "Campaign Name" in sd_df.columns:
                # Classify by campaign name patterns
                sd_camp_entities = sd_df[sd_df["Entity"] == "Campaign"].copy()
                cn = sd_camp_entities["Campaign Name"].astype(str).str.lower()

                retarget_mask = cn.str.contains("retarget|remarketing", na=False)
                audience_mask = cn.str.contains("audience", na=False) & ~retarget_mask
                product_mask = ~retarget_mask & ~audience_mask

                sd_seg_rows.append(_seg_row("SD Retargeting", sd_camp_entities[retarget_mask]))
                sd_seg_rows.append(_seg_row("SD Audiences", sd_camp_entities[audience_mask]))
                sd_seg_rows.append(_seg_row("SD Product Targeting", sd_camp_entities[product_mask]))

            sd_total_spend = sd_camps["Spend"].sum() if len(sd_camps) > 0 and "Spend" in sd_camps.columns else 0
            sd_seg_rows.append(_seg_row("TOTAL SD", sd_camps))
            seg_sd_df = _build_segment_table(sd_seg_rows, sd_total_spend)

            styled_sd = seg_sd_df.style.map(_color_acos, subset=["ACoS"])
            st.dataframe(styled_sd, use_container_width=True, hide_index=True, height=min(38 + 35 * len(seg_sd_df), 300))
        else:
            st.caption("Sin datos de SD en este Bulk File")

    # ════════════════════════════════════════════════════════════
    # TAB 4 — Deep Checks
    # ════════════════════════════════════════════════════════════
    with tab4:

        # ── Check 1: Top 5 Campañas por Spend ──────────────────
        st.markdown("**Top 5 Campañas SP por Spend**")
        top5_camps_df = pd.DataFrame()
        if len(sp_camps) > 0 and "Spend" in sp_camps.columns:
            top5_cols_want = ["Campaign Name", "Targeting Type", "Spend", "Sales", "ACOS", "Orders"]
            top5_cols_avail = [c for c in top5_cols_want if c in sp_camps.columns]
            top5_camps_df = sp_camps.sort_values("Spend", ascending=False).head(5)[top5_cols_avail].copy()
            if len(top5_camps_df) > 0:
                st.dataframe(top5_camps_df, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin campañas SP con spend")
        else:
            st.caption("Sin datos de campañas SP")

        st.markdown("---")

        # ── Check 2: Clasificación de Targets ──────────────────
        st.markdown("**Clasificación de Targets**")
        classif_df = pd.DataFrame()
        if not brand_terms:
            st.info("Ingresá brand terms arriba para clasificar targets por tipo (own brand, competitor, generic)")
        else:
            # Gather all targets
            all_targets = []

            # Keywords
            if len(sp_kws) > 0 and "Keyword Text" in sp_kws.columns:
                kw_df = sp_kws[["Keyword Text", "Spend", "Sales", "Clicks", "Orders"]].copy()
                kw_df.columns = ["Target", "Spend", "Sales", "Clicks", "Orders"]
                kw_text_lower = kw_df["Target"].astype(str).str.lower()
                kw_df["Tipo"] = "generic"
                kw_df.loc[kw_text_lower.apply(lambda t: any(bt in t for bt in brand_terms)), "Tipo"] = "own_brand"
                all_targets.append(kw_df)

            # Product Targeting
            if len(sp_pts) > 0 and "Product Targeting Expression" in sp_pts.columns:
                pt_df = sp_pts[["Product Targeting Expression", "Spend", "Sales", "Clicks", "Orders"]].copy()
                pt_df.columns = ["Target", "Spend", "Sales", "Clicks", "Orders"]
                pte_lower = pt_df["Target"].astype(str).str.lower()

                # Detect own ASINs from BR
                own_asins = set()
                if br_df is not None and len(br_df) > 0:
                    for c in br_df.columns:
                        if "asin" in c.lower():
                            own_asins.update(br_df[c].dropna().astype(str).str.strip().str.upper())
                            break

                pt_df["Tipo"] = "generic"
                for idx, row in pt_df.iterrows():
                    expr = str(row["Target"]).lower()
                    if "asin" in expr:
                        # Extract ASIN
                        import re
                        asin_match = re.search(r"[A-Z0-9]{10}", str(row["Target"]).upper())
                        if asin_match:
                            asin_val = asin_match.group()
                            if asin_val in own_asins:
                                pt_df.at[idx, "Tipo"] = "own_asin"
                            else:
                                pt_df.at[idx, "Tipo"] = "competitor_asin"
                all_targets.append(pt_df)

            if all_targets:
                combined = pd.concat(all_targets, ignore_index=True)
                for col in ["Spend", "Sales", "Clicks", "Orders"]:
                    combined[col] = pd.to_numeric(combined[col], errors="coerce").fillna(0)

                classif_df = combined.groupby("Tipo").agg(
                    Targets=("Tipo", "count"),
                    Spend=("Spend", "sum"),
                    Sales=("Sales", "sum"),
                ).reset_index().rename(columns={"Tipo": "Tipo"})
                classif_df["ACoS"] = classif_df.apply(
                    lambda r: round(_acos(r["Spend"], r["Sales"]), 1), axis=1,
                )
                total_classif_spend = classif_df["Spend"].sum()
                classif_df["% Spend"] = classif_df["Spend"].apply(
                    lambda s: round((s / total_classif_spend * 100) if total_classif_spend > 0 else 0, 1),
                )
                classif_df = classif_df.sort_values("Spend", ascending=False)
                st.dataframe(
                    classif_df.style.map(_color_acos, subset=["ACoS"]),
                    use_container_width=True, hide_index=True,
                )
            else:
                st.caption("Sin keywords ni PT para clasificar")

        st.markdown("---")

        # ── Check 3: Duplicación de Targets ────────────────────
        st.markdown("**Duplicación de Targets (Keywords en 2+ campañas)**")
        dupes_df = pd.DataFrame()
        if len(sp_kws) > 0 and "Keyword Text" in sp_kws.columns and "Campaign Name" in sp_kws.columns and "Match Type" in sp_kws.columns:
            kw_dedup = sp_kws.copy()
            kw_dedup["_kw_lower"] = kw_dedup["Keyword Text"].astype(str).str.lower().str.strip()
            kw_dedup["_mt"] = kw_dedup["Match Type"].astype(str).str.strip()

            grouped = kw_dedup.groupby(["_kw_lower", "_mt"]).agg(
                n_camps=("Campaign Name", "nunique"),
                Spend_Total=("Spend", "sum"),
                Sales_Total=("Sales", "sum"),
            ).reset_index()
            dupes = grouped[grouped["n_camps"] >= 2].sort_values("Spend_Total", ascending=False).head(10)

            if len(dupes) > 0:
                dupes_df = dupes.rename(columns={
                    "_kw_lower": "Keyword", "_mt": "Match Type",
                    "n_camps": "# Campañas",
                }).copy()
                dupes_df["Spend_Total"] = dupes_df["Spend_Total"].round(2)
                dupes_df["Sales_Total"] = dupes_df["Sales_Total"].round(2)
                st.dataframe(dupes_df, use_container_width=True, hide_index=True)
            else:
                st.caption("No se detectaron keywords duplicadas entre campañas")
        else:
            st.caption("Sin datos suficientes de keywords SP")

        st.markdown("---")

        # ── Check 4: Bid Adjustments por Placement ─────────────
        st.markdown("**Bid Adjustments por Placement**")
        sp_bid_adj = bulk.get("sp_bid_adj", pd.DataFrame())
        if len(sp_bid_adj) > 0 and "Placement" in sp_bid_adj.columns and "Percentage" in sp_bid_adj.columns:
            sp_bid_adj["Percentage"] = pd.to_numeric(sp_bid_adj["Percentage"], errors="coerce").fillna(0)

            placement_agg = sp_bid_adj.groupby("Placement").agg(
                Campañas=("Placement", "count"),
                Promedio=("Percentage", "mean"),
                Min=("Percentage", "min"),
                Max=("Percentage", "max"),
            ).reset_index()
            placement_agg["Promedio"] = placement_agg["Promedio"].round(1)
            # Filter only rows with adjustments > 0
            placement_with_adj = sp_bid_adj[sp_bid_adj["Percentage"] > 0]
            if len(placement_with_adj) > 0:
                placement_active = placement_with_adj.groupby("Placement").agg(
                    Con_Ajuste=("Placement", "count"),
                ).reset_index()
                placement_agg = placement_agg.merge(placement_active, on="Placement", how="left")
                placement_agg["Con_Ajuste"] = placement_agg["Con_Ajuste"].fillna(0).astype(int)

            st.dataframe(placement_agg, use_container_width=True, hide_index=True)

            # Bidding Strategy distribution
            if "Bidding Strategy" in sp_bid_adj.columns:
                st.caption("Distribución Bidding Strategy:")
                bs_dist = sp_bid_adj["Bidding Strategy"].dropna().value_counts().reset_index()
                bs_dist.columns = ["Bidding Strategy", "Count"]
                st.dataframe(bs_dist, use_container_width=True, hide_index=True)
        else:
            st.caption("Sin datos de Bid Adjustments")

        st.markdown("---")

        # ── Check 5: SKAG vs Bolsa ─────────────────────────────
        st.markdown("**SKAG vs Bolsa (targets por campaña manual)**")
        if len(sp_kws) > 0 and "Campaign Name" in sp_kws.columns:
            # Combine KW + PT for manual campaigns
            manual_targets = pd.concat([sp_kws, sp_pts], ignore_index=True)
            if "Spend" in manual_targets.columns:
                active_targets = manual_targets[manual_targets["Spend"] > 0].copy()
            else:
                active_targets = manual_targets.copy()

            if len(active_targets) > 0 and "Campaign Name" in active_targets.columns:
                targets_per_camp = active_targets.groupby("Campaign Name").agg(
                    n_targets=("Campaign Name", "count"),
                    Spend=("Spend", "sum") if "Spend" in active_targets.columns else ("Campaign Name", "count"),
                ).reset_index()

                def _classify_skag(n):
                    if n == 1:
                        return "SKAG (1 target)"
                    if n <= 10:
                        return "Normal (2-10)"
                    return "Bolsa (11+)"

                targets_per_camp["Tipo"] = targets_per_camp["n_targets"].apply(_classify_skag)
                skag_summary = targets_per_camp.groupby("Tipo").agg(
                    Campañas=("Tipo", "count"),
                    Spend_Total=("Spend", "sum"),
                ).reset_index()
                total_skag_spend = skag_summary["Spend_Total"].sum()
                skag_summary["% Spend"] = skag_summary["Spend_Total"].apply(
                    lambda s: round((s / total_skag_spend * 100) if total_skag_spend > 0 else 0, 1),
                )
                skag_summary["Spend_Total"] = skag_summary["Spend_Total"].round(2)
                st.dataframe(skag_summary, use_container_width=True, hide_index=True)
            else:
                st.caption("Sin targets activos con spend")
        else:
            st.caption("Sin datos de keywords SP")

    # ════════════════════════════════════════════════════════════
    # TAB 5 — Export
    # ════════════════════════════════════════════════════════════
    with tab5:
        from datetime import date
        _today = date.today().isoformat()

        # Build KPI dict for export
        kpi_dict = {
            "Total PPC Spend": f"${total_spend:,.2f}",
            "Total PPC Sales": f"${total_sales:,.2f}",
            "ACoS Overall": f"{acos_overall:.1f}%",
            "Impressions": f"{total_imps:,.0f}",
            "Clicks": f"{total_clicks:,.0f}",
            "Orders": f"{total_orders:,.0f}",
            "SP Campañas": str(n_sp),
            "SB Campañas": str(n_sb),
            "SD Campañas": str(n_sd),
            "Fecha": _today,
        }
        if has_br and revenue_total > 0:
            kpi_dict["Revenue Total"] = f"${revenue_total:,.2f}"
            kpi_dict["TACoS"] = f"{tacos:.1f}%"
            kpi_dict["Ventas Orgánicas"] = f"${organic_sales:,.2f}"

        # Audit summary tuples for export
        audit_mixed = (
            f"{len(mixed_camps)} campañas mixtas",
            ", ".join(mixed_camps[:5]) + ("..." if len(mixed_camps) > 5 else "") if mixed_camps else "Ninguna",
        )
        audit_target_was = (
            f"${total_was:,.2f} ({was_pct:.1f}%)",
            f"SP: ${sp_manual_was:,.2f} | SB: ${sb_was:,.2f} | SD: ${sd_was:,.2f}",
        )
        audit_st_was = (
            f"${total_st_was:,.2f} ({st_was_pct:.1f}%)",
            f"SP: ${sp_st_was:,.2f} ({sp_st_was_count} terms) | SB: ${sb_st_was:,.2f} ({sb_st_was_count} terms)",
        )

        # Reuse seg DataFrames from tab3 scope — rebuild if needed
        # (they were computed in tab3 but Streamlit executes all tabs)
        try:
            _seg_sp = seg_sp_df
        except NameError:
            _seg_sp = pd.DataFrame()
        try:
            _seg_sb = seg_sb_df
        except NameError:
            _seg_sb = pd.DataFrame()
        try:
            _seg_sd = seg_sd_df
        except NameError:
            _seg_sd = pd.DataFrame()
        try:
            _top5 = top5_camps_df
        except NameError:
            _top5 = pd.DataFrame()
        try:
            _classif = classif_df
        except NameError:
            _classif = pd.DataFrame()
        try:
            _dupes = dupes_df
        except NameError:
            _dupes = pd.DataFrame()

        # Compute graduation for Excel (also used in tab6)
        _grad_df = _analyze_target_graduation(sp_kws, sp_camps, brand_terms)

        try:
            excel_bytes = _build_audit_excel(
                kpi_dict, _seg_sp, _seg_sb, _seg_sd,
                _top5, _classif, _dupes,
                audit_mixed, audit_target_was, audit_st_was,
                graduation_df=_grad_df,
            )
        except Exception as e:
            st.warning(f"Error generando Excel: {e}")
            buf_fallback = io.BytesIO()
            pd.DataFrame({"Error": [str(e)]}).to_excel(buf_fallback, index=False)
            excel_bytes = buf_fallback.getvalue()

        st.download_button(
            "\u2b07\ufe0f Descargar Auditoría Completa (Excel)",
            data=excel_bytes,
            file_name=f"PPC_Audit_{_today}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="audit_dl",
        )

    # ════════════════════════════════════════════════════════════
    # TAB 6 — Target Graduation
    # ════════════════════════════════════════════════════════════
    with tab6:
        st.markdown("#### Targets con 0 impresiones en campañas activas")
        st.caption(
            "Identifica keywords/targets que no reciben tráfico aunque su campaña sí. "
            "Posibles causas: bid muy bajo, keyword irrelevante o duplicada."
        )

        grad_df = _analyze_target_graduation(sp_kws, sp_camps, brand_terms)

        if grad_df.empty:
            st.markdown(
                "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
                "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
                "<div style='font-size:1.5rem;'>✅</div>"
                "<div style='font-weight:600;margin-top:0.5rem;'>Sin targets huérfanos</div>"
                "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
                "Todos los targets en campañas activas tienen impresiones</div>"
                "</div>", unsafe_allow_html=True,
            )
        else:
            # KPI cards
            total_orphans = len(grad_df)
            n_subir = (grad_df["Recomendación"].str.contains("SUBIR BID", na=False)).sum()
            n_pausar = (grad_df["Recomendación"].str.contains("PAUSAR", na=False)).sum()
            n_graduar = (grad_df["Recomendación"].str.contains("GRADUAR", na=False)).sum()
            n_mantener = (grad_df["Recomendación"].str.contains("MANTENER", na=False)).sum()

            k1, k2, k3, k4 = st.columns(4)
            with k1:
                st.markdown(kpi_card("Targets sin impresiones", str(total_orphans)), unsafe_allow_html=True)
            with k2:
                st.markdown(kpi_card("Subir Bid", str(n_subir)), unsafe_allow_html=True)
            with k3:
                st.markdown(kpi_card("Pausar", str(n_pausar)), unsafe_allow_html=True)
            with k4:
                label_4 = "Mantener (marca)" if n_mantener > 0 else "Graduar a SKAG"
                val_4 = str(n_mantener) if n_mantener > 0 else str(n_graduar)
                st.markdown(kpi_card(label_4, val_4), unsafe_allow_html=True)

            # Filter by recommendation
            rec_options = sorted(grad_df["Recomendación"].unique().tolist())
            selected_recs = st.multiselect(
                "Filtrar por recomendación",
                options=rec_options,
                default=rec_options,
                key="audit_grad_filter",
            )

            grad_filtered = grad_df[grad_df["Recomendación"].isin(selected_recs)].copy()

            # Display columns
            show_cols = [
                c for c in [
                    "Campaign Name", "Ad Group Name", "Keyword Text", "Match Type",
                    "Bid", "Spend", "Sales", "Campaign Impressions", "Recomendación",
                ] if c in grad_filtered.columns
            ]

            if show_cols:
                # Color coding by recommendation
                _GRAD_COLORS = {
                    "SUBIR BID": "background:#E8F5E9;",
                    "PAUSAR": "background:#FFEBEE;",
                    "GRADUAR": "background:#FFF8E1;",
                    "MANTENER": "background:#E3F2FD;",
                    "YA PAUSADO": "background:#F5F5F5;",
                }

                def _style_grad(row):
                    rec = str(row.get("Recomendación", ""))
                    style = ""
                    for key, css in _GRAD_COLORS.items():
                        if key in rec:
                            style = css
                            break
                    return [style] * len(row)

                styled = grad_filtered[show_cols].reset_index(drop=True).style.apply(
                    _style_grad, axis=1,
                )
                st.dataframe(styled, use_container_width=True, height=450)

                st.caption(f"Mostrando {len(grad_filtered)} de {total_orphans} targets")
