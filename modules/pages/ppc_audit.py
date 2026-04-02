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


@st.cache_data
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
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📊 KPIs Overview",
        "🛠️ Auditoría Estructura",
        "🎯 Performance Segmento",
        "🔍 Deep Checks",
        "📥 Export",
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
    # TAB 3 — Performance Segmento (placeholder)
    # ════════════════════════════════════════════════════════════
    with tab3:
        st.info("🎯 Performance por Segmento — Próximamente")

    # ════════════════════════════════════════════════════════════
    # TAB 4 — Deep Checks (placeholder)
    # ════════════════════════════════════════════════════════════
    with tab4:
        st.info("🔍 Deep Checks — Próximamente")

    # ════════════════════════════════════════════════════════════
    # TAB 5 — Export (placeholder)
    # ════════════════════════════════════════════════════════════
    with tab5:
        st.info("📥 Export — Próximamente")
