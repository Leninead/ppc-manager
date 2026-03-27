import io
import re

import streamlit as st
import pandas as pd


# ═══════════════════════════════════════════════════════════════════════
# Cached parsers
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data
def _parse_mkl(data, name):
    """Parse DataDive MKL (Master Keyword List) — niche-*-keywords.xlsx.

    Structure: sheet 'keywords', merged headers in rows 1-2.
    Col B=Search Terms, C=SV, D=Relevance, E=Sugg. bid, F=Launch Score.
    Cols G+ = competitor ASINs with organic ranking.
    """
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    # --- Detect header row: find row containing "Search Term" in col B area ----
    header_row = None
    for i in range(min(5, len(raw))):
        row_vals = raw.iloc[i].astype(str).str.lower()
        if row_vals.str.contains("search.?term").any():
            header_row = i
            break
    if header_row is None:
        header_row = 1  # fallback

    # --- Extract ASIN columns from header row (B0... pattern) ----------------
    asin_pattern = re.compile(r'B0[A-Z0-9]{8}', re.IGNORECASE)
    asin_cols = {}  # col_index -> ASIN
    for ci in range(6, raw.shape[1]):
        for ri in range(min(3, len(raw))):
            val = str(raw.iloc[ri, ci]).strip()
            m = asin_pattern.search(val)
            if m:
                asin_cols[ci] = m.group(0).upper()
                break

    # --- Build data rows starting after header row ---------------------------
    data_start = header_row + 1
    rows = []
    for ri in range(data_start, len(raw)):
        term = str(raw.iloc[ri, 1]).strip() if pd.notna(raw.iloc[ri, 1]) else ""
        if not term or term.lower() in ("nan", ""):
            continue
        sv = pd.to_numeric(str(raw.iloc[ri, 2]).replace(",", ""), errors="coerce") or 0
        relevance = pd.to_numeric(raw.iloc[ri, 3], errors="coerce") or 0
        # Col E might have "bid & range" — take first numeric
        bid_raw = str(raw.iloc[ri, 4]).replace("$", "").replace(",", "").strip()
        bid_match = re.search(r'[\d.]+', bid_raw)
        sugg_bid = float(bid_match.group()) if bid_match else 0
        launch_score = pd.to_numeric(raw.iloc[ri, 5], errors="coerce") or 0

        row = {
            "Search Term": term,
            "SV": int(sv),
            "Relevance": round(relevance, 2),
            "Sugg. Bid": round(sugg_bid, 2),
            "Launch Score": round(launch_score, 1),
        }
        # Organic rank per competitor ASIN
        for ci, asin in asin_cols.items():
            rank_val = pd.to_numeric(raw.iloc[ri, ci], errors="coerce")
            row[asin] = int(rank_val) if pd.notna(rank_val) and rank_val > 0 else None
        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    competitor_asins = list(asin_cols.values())
    return df, competitor_asins


@st.cache_data
def _parse_competitors(data, name):
    """Parse DataDive Competitors — niche-*-competitors.xlsx.

    Structure: sheet 'competitors', vertical layout.
    Col B = metric name, Col D = Niche Median, Cols G+ = value per ASIN.
    """
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    # Find column with metric labels (look for "Brand" or "ASIN" text)
    label_col = 1  # default col B
    for ci in range(min(4, raw.shape[1])):
        col_vals = raw.iloc[:, ci].astype(str).str.lower()
        if col_vals.str.contains("^asin$").any() or col_vals.str.contains("^brand$").any():
            label_col = ci
            break

    # Find Niche Median column
    median_col = None
    for ci in range(label_col + 1, min(label_col + 6, raw.shape[1])):
        for ri in range(min(3, len(raw))):
            if "median" in str(raw.iloc[ri, ci]).lower():
                median_col = ci
                break
        if median_col is not None:
            break
    if median_col is None:
        median_col = 3  # fallback col D

    # Find ASIN value columns (G+ = index 6+, or after median)
    asin_start = max(median_col + 1, 5)
    # Detect actual ASIN identifiers from "ASIN" row
    asin_row_idx = None
    for ri in range(len(raw)):
        val = str(raw.iloc[ri, label_col]).strip().lower()
        if val == "asin":
            asin_row_idx = ri
            break

    asin_cols = {}
    asin_pattern = re.compile(r'B0[A-Z0-9]{8}', re.IGNORECASE)
    if asin_row_idx is not None:
        for ci in range(asin_start, raw.shape[1]):
            val = str(raw.iloc[asin_row_idx, ci]).strip()
            m = asin_pattern.search(val)
            if m:
                asin_cols[ci] = m.group(0).upper()
    else:
        # Fallback: try headers row 0
        for ci in range(asin_start, raw.shape[1]):
            val = str(raw.iloc[0, ci]).strip()
            m = asin_pattern.search(val)
            if m:
                asin_cols[ci] = m.group(0).upper()

    # Parse metrics
    target_metrics = [
        "brand", "asin", "sv on p1", "strength", "seller's country", "variations",
        "30d sales", "30d revenue", "price", "rating", "review count",
        "listing age", "kws on p1", "advertised kws", "category",
    ]

    result = {}  # asin -> {metric: value}
    median_data = {}

    for ri in range(len(raw)):
        metric_raw = str(raw.iloc[ri, label_col]).strip()
        metric_lower = metric_raw.lower()
        if not any(t in metric_lower for t in target_metrics):
            continue
        metric_name = metric_raw

        # Niche Median
        med_val = raw.iloc[ri, median_col] if median_col < raw.shape[1] else None
        median_data[metric_name] = med_val

        # Per ASIN
        for ci, asin in asin_cols.items():
            if asin not in result:
                result[asin] = {}
            result[asin][metric_name] = raw.iloc[ri, ci]

    # Build DataFrame: rows = ASINs, cols = metrics
    if not result:
        return pd.DataFrame(), median_data

    rows = []
    for asin, metrics in result.items():
        row = {"ASIN": asin}
        row.update(metrics)
        rows.append(row)

    df = pd.DataFrame(rows)

    # Clean numeric columns
    numeric_hints = ["sales", "revenue", "price", "rating", "review", "age", "kws", "sv", "strength", "variation", "advertised"]
    for col in df.columns:
        if col == "ASIN":
            continue
        if any(h in col.lower() for h in numeric_hints):
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[\$,]", "", regex=True),
                errors="coerce",
            )

    return df, median_data


@st.cache_data
def _parse_rank_radar(data, name):
    """Parse DataDive Rank Radar — [product-name].xlsx.

    Structure: sheet 'keywords'.
    Row 1: section headers (SQP - Impressions, SQP - Clicks, PPC Data, etc.)
    Row 2: sub-headers (Search Terms, Tags, SV, Rel., Median Rank, ..., dates)
    Row 3: AGGREGATE totals
    Row 4: SIS Report totals
    Data from row 5+
    Date columns (X+) = daily organic ranking.
    """
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    if len(raw) < 5:
        return pd.DataFrame(), [], pd.DataFrame()

    # Row 2 (index 1) has the sub-headers
    headers = raw.iloc[1].astype(str).str.strip().tolist()

    # Detect date columns: match YYYY-MM-DD or similar date patterns
    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_cols = {}  # col_index -> date string
    for ci, h in enumerate(headers):
        if date_pattern.match(h):
            date_cols[ci] = h

    # Build main data columns (non-date)
    # Known sub-header names from DataDive Rank Radar
    known_cols = {
        "search terms": "Search Term",
        "tags": "Tags",
        "search volume": "SV",
        "sv": "SV",
        "rel.": "Relevance",
        "rel": "Relevance",
        "median rank": "Median Rank",
        "sq score": "SQ Score",
        "asin share": "ASIN Share",
        "asin ctr": "ASIN CTR",
        "asin count": "ASIN Count",
        "asin cvr": "ASIN CVR",
        "ex": "PPC Exact",
        "ph": "PPC Phrase",
        "br": "PPC Broad",
        "au": "PPC Auto",
        "ir": "IR",
        "sales": "PPC Sales",
        "spend": "PPC Spend",
        "ctr": "PPC CTR",
        "cpc": "PPC CPC",
        "cvr": "PPC CVR",
    }

    # Map column indices to names
    col_map = {}  # col_index -> clean name
    seen_names = {}
    for ci, h in enumerate(headers):
        hl = h.lower().strip()
        if ci in date_cols:
            continue
        if hl in known_cols:
            base = known_cols[hl]
            # Handle duplicate names (e.g., "ASIN Share" appears in both Impressions and Clicks sections)
            if base in seen_names:
                seen_names[base] += 1
                # Use section context from row 1
                section = str(raw.iloc[0, ci]).strip()
                if section and section.lower() != "nan":
                    short_section = section.split("-")[-1].strip()[:10]
                    col_map[ci] = f"{base} ({short_section})"
                else:
                    col_map[ci] = f"{base}_{seen_names[base]}"
            else:
                seen_names[base] = 1
                col_map[ci] = base
        elif hl and hl != "nan":
            col_map[ci] = h

    # Parse data rows (skip row 3=AGGREGATE, row 4=SIS, data from row 5 = index 4)
    aggregate_row = raw.iloc[2] if len(raw) > 2 else None
    data_start = 4  # index 4 = row 5

    rows = []
    for ri in range(data_start, len(raw)):
        # Skip empty rows
        first_val = str(raw.iloc[ri, 0]).strip() if pd.notna(raw.iloc[ri, 0]) else ""
        second_val = str(raw.iloc[ri, 1]).strip() if raw.shape[1] > 1 and pd.notna(raw.iloc[ri, 1]) else ""
        term = first_val or second_val
        if not term or term.lower() in ("nan", ""):
            # Try finding the search term column
            st_ci = next((ci for ci, n in col_map.items() if n == "Search Term"), None)
            if st_ci is not None:
                term = str(raw.iloc[ri, st_ci]).strip() if pd.notna(raw.iloc[ri, st_ci]) else ""
            if not term or term.lower() in ("nan", ""):
                continue

        row = {}
        for ci, col_name in col_map.items():
            row[col_name] = raw.iloc[ri, ci]
        for ci, date_str in date_cols.items():
            row[date_str] = pd.to_numeric(raw.iloc[ri, ci], errors="coerce")
        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()

    # Clean numeric columns
    numeric_cols = ["SV", "Relevance", "Median Rank", "SQ Score", "PPC Exact", "PPC Phrase",
                    "PPC Broad", "PPC Auto", "IR", "PPC Sales", "PPC Spend", "PPC CTR",
                    "PPC CPC", "PPC CVR"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[\$,%]", "", regex=True).str.replace(",", ""),
                errors="coerce",
            )

    # Date columns list sorted chronologically
    date_col_names = sorted(date_cols.values())

    # Aggregate row
    agg_data = {}
    if aggregate_row is not None:
        for ci, col_name in col_map.items():
            agg_data[col_name] = aggregate_row.iloc[ci]

    return df, date_col_names, agg_data


# ═══════════════════════════════════════════════════════════════════════
# Render
# ═══════════════════════════════════════════════════════════════════════

def render():
    st.header("🔬 DataDive Analyzer")
    st.caption("Análisis de exports de DataDive: MKL Keywords, Competitors y Rank Radar.")
    st.divider()

    tab1, tab2, tab3 = st.tabs([
        "📖 MKL Keywords",
        "⚔️ Competitors",
        "📡 Rank Radar",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MKL Keywords
    # ══════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("📖 Master Keyword List")
        st.caption("Archivo: niche-*-keywords.xlsx de DataDive")

        file_mkl = st.file_uploader(
            "Sube tu MKL (.xlsx)", type=["xlsx"], key="dd_mkl",
        )
        if not file_mkl:
            st.info("Subí el archivo niche-*-keywords.xlsx exportado desde DataDive.")
            return

        df_mkl, competitor_asins = _parse_mkl(file_mkl.getvalue(), file_mkl.name)
        if df_mkl.empty:
            st.warning("No se pudieron extraer keywords del archivo. Verificá el formato.")
            return

        st.success(f"✅ {len(df_mkl)} keywords · {len(competitor_asins)} competidores detectados")

        # User ASIN input
        my_asin = st.text_input(
            "Tu ASIN (para detectar gaps)", placeholder="B0XXXXXXXXX", key="dd_mkl_asin",
        ).strip().upper()

        # Filters
        fc1, fc2 = st.columns(2)
        min_sv = fc1.number_input("SV mínimo", min_value=0, value=100, step=50, key="dd_mkl_sv")
        min_rel = fc2.slider("Relevancia mínima", 0.0, 10.0, 1.0, 0.5, key="dd_mkl_rel")

        df_filtered = df_mkl[
            (df_mkl["SV"] >= min_sv) & (df_mkl["Relevance"] >= min_rel)
        ].copy()

        # Ranking info for user ASIN
        if my_asin and my_asin in df_filtered.columns:
            df_filtered["Mi Ranking"] = df_filtered[my_asin]
            df_filtered["Rankeado"] = df_filtered["Mi Ranking"].notna().map(
                {True: "✅ Sí", False: "❌ No"}
            )
        elif my_asin:
            df_filtered["Mi Ranking"] = None
            df_filtered["Rankeado"] = "❌ No"

        # KPIs
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Keywords", len(df_filtered))
        k2.metric("SV total", f"{df_filtered['SV'].sum():,.0f}")
        k3.metric("SV promedio", f"{df_filtered['SV'].mean():,.0f}" if len(df_filtered) else "—")
        if my_asin:
            ranked_count = df_filtered["Mi Ranking"].notna().sum() if "Mi Ranking" in df_filtered.columns else 0
            k4.metric(f"Rankeadas ({my_asin[:10]})", f"{ranked_count}/{len(df_filtered)}")
        else:
            k4.metric("Competidores", len(competitor_asins))

        # Display columns
        display_cols = ["Search Term", "SV", "Relevance", "Launch Score", "Sugg. Bid"]
        if "Mi Ranking" in df_filtered.columns:
            display_cols += ["Mi Ranking", "Rankeado"]

        df_show = df_filtered[
            [c for c in display_cols if c in df_filtered.columns]
        ].sort_values("SV", ascending=False).reset_index(drop=True)

        def _color_ranked(val):
            if "Sí" in str(val):
                return "background-color: #E8F5E9; color: #1B5E20"
            if "No" in str(val):
                return "background-color: #FFEBEE; color: #B71C1C"
            return ""

        styled = df_show.style
        if "Rankeado" in df_show.columns:
            styled = styled.map(_color_ranked, subset=["Rankeado"])
        st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_show), 600))

        # ── KW Gaps ────────────────────────────────────────────────────
        if my_asin and "Mi Ranking" in df_filtered.columns:
            st.markdown("---")
            st.markdown("#### 🕳️ Keyword Gaps")
            st.caption(f"Keywords donde tu ASIN ({my_asin}) NO rankea pero competidores sí.")

            df_gaps = df_filtered[df_filtered["Mi Ranking"].isna()].copy()
            # Count how many competitors rank on each keyword
            comp_cols = [c for c in competitor_asins if c in df_gaps.columns and c != my_asin]
            if comp_cols:
                df_gaps["Competidores rankeados"] = df_gaps[comp_cols].notna().sum(axis=1)
                df_gaps = df_gaps[df_gaps["Competidores rankeados"] > 0]

            if not df_gaps.empty:
                df_gaps = df_gaps.sort_values("SV", ascending=False)
                g1, g2 = st.columns(2)
                g1.metric("Gaps detectados", len(df_gaps))
                g2.metric("SV perdido", f"{df_gaps['SV'].sum():,.0f}")

                gap_cols = ["Search Term", "SV", "Relevance", "Launch Score"]
                if "Competidores rankeados" in df_gaps.columns:
                    gap_cols.append("Competidores rankeados")
                st.dataframe(
                    df_gaps[[c for c in gap_cols if c in df_gaps.columns]].reset_index(drop=True),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_gaps), 500),
                )
            else:
                st.success("✅ No se detectaron gaps — tu ASIN rankea en todas las keywords filtradas.")

        # ── Export ──────────────────────────────────────────────────────
        st.markdown("---")
        buf_mkl = io.BytesIO()
        df_filtered.to_excel(buf_mkl, index=False)
        st.download_button(
            f"⬇️ Exportar {len(df_filtered)} keywords (Excel)",
            data=buf_mkl.getvalue(),
            file_name="datadive_mkl_keywords.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dd_mkl_dl",
        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — Competitors
    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("⚔️ Competitor Analysis")
        st.caption("Archivo: niche-*-competitors.xlsx de DataDive")

        file_comp = st.file_uploader(
            "Sube tu Competitors (.xlsx)", type=["xlsx"], key="dd_comp",
        )
        if not file_comp:
            st.info("Subí el archivo niche-*-competitors.xlsx exportado desde DataDive.")
            return

        df_comp, median_data = _parse_competitors(file_comp.getvalue(), file_comp.name)
        if df_comp.empty:
            st.warning("No se pudieron extraer datos de competidores. Verificá el formato.")
            return

        st.success(f"✅ {len(df_comp)} competidores detectados")

        # User ASIN highlight
        my_asin_comp = st.text_input(
            "Tu ASIN (para destacar)", placeholder="B0XXXXXXXXX", key="dd_comp_asin",
        ).strip().upper()

        # Sort by 30d Revenue if available
        revenue_col = next((c for c in df_comp.columns if "revenue" in c.lower()), None)
        sales_col = next((c for c in df_comp.columns if "30d sales" in c.lower() or "sales" in c.lower()), None)
        price_col = next((c for c in df_comp.columns if "price" in c.lower()), None)
        rating_col = next((c for c in df_comp.columns if "rating" in c.lower()), None)
        review_col = next((c for c in df_comp.columns if "review" in c.lower()), None)
        kws_col = next((c for c in df_comp.columns if "kws on p1" in c.lower() or "kws" in c.lower()), None)

        sort_col = revenue_col or sales_col
        if sort_col and sort_col in df_comp.columns:
            df_comp = df_comp.sort_values(sort_col, ascending=False).reset_index(drop=True)

        # Niche Median comparison
        if my_asin_comp and my_asin_comp in df_comp["ASIN"].values:
            my_row = df_comp[df_comp["ASIN"] == my_asin_comp].iloc[0]
            st.markdown("#### Tu ASIN vs Niche Median")
            mc1, mc2, mc3, mc4 = st.columns(4)

            def _compare(col, label, fmt="${:.2f}", col_obj=None):
                if col and col in my_row.index:
                    my_val = pd.to_numeric(str(my_row[col]).replace("$", "").replace(",", ""), errors="coerce")
                    med_val = pd.to_numeric(str(median_data.get(col, "")).replace("$", "").replace(",", ""), errors="coerce")
                    if pd.notna(my_val):
                        delta = None
                        if pd.notna(med_val) and med_val != 0:
                            delta = f"{((my_val - med_val) / med_val * 100):+.0f}% vs median"
                        col_obj.metric(label, fmt.format(my_val), delta=delta)

            _compare(price_col, "Tu Precio", "${:.2f}", mc1)
            _compare(rating_col, "Tu Rating", "{:.1f} ⭐", mc2)
            _compare(review_col, "Tus Reviews", "{:.0f}", mc3)
            _compare(kws_col, "Tus KWs en P1", "{:.0f}", mc4)
            st.markdown("---")

        # Highlight user ASIN row
        def _highlight_my_asin(row):
            if my_asin_comp and row.get("ASIN") == my_asin_comp:
                return ["background-color: #FFF3E0"] * len(row)
            return [""] * len(row)

        styled_comp = df_comp.style.apply(_highlight_my_asin, axis=1)
        st.dataframe(styled_comp, use_container_width=True, height=min(38 + 35 * len(df_comp), 600))

        # Export
        st.markdown("---")
        buf_comp = io.BytesIO()
        df_comp.to_excel(buf_comp, index=False)
        st.download_button(
            f"⬇️ Exportar {len(df_comp)} competidores (Excel)",
            data=buf_comp.getvalue(),
            file_name="datadive_competitors.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dd_comp_dl",
        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — Rank Radar
    # ══════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("📡 Rank Radar")
        st.caption("Archivo: [product-name].xlsx de DataDive Rank Radar")

        file_rr = st.file_uploader(
            "Sube tu Rank Radar (.xlsx)", type=["xlsx"], key="dd_rr",
        )
        if not file_rr:
            st.info("Subí el archivo de Rank Radar exportado desde DataDive.")
            return

        df_rr, date_cols, agg_data = _parse_rank_radar(file_rr.getvalue(), file_rr.name)
        if df_rr.empty:
            st.warning("No se pudieron extraer datos del Rank Radar. Verificá el formato.")
            return

        st.success(f"✅ {len(df_rr)} keywords · {len(date_cols)} días de ranking")

        # ── Trend calculation ────────────────────────────────────────
        if len(date_cols) >= 2:
            first_dates = date_cols[:min(7, len(date_cols) // 2)]
            last_dates = date_cols[max(len(date_cols) // 2, len(date_cols) - 7):]

            def _calc_trend(row):
                old_vals = [row.get(d) for d in first_dates if pd.notna(row.get(d))]
                new_vals = [row.get(d) for d in last_dates if pd.notna(row.get(d))]
                if not old_vals or not new_vals:
                    return "—"
                avg_old = sum(old_vals) / len(old_vals)
                avg_new = sum(new_vals) / len(new_vals)
                if avg_old == 0:
                    return "—"
                # Lower rank = better, so if new < old, improving
                if avg_new < avg_old * 0.9:
                    return "↑ Mejorando"
                elif avg_new > avg_old * 1.1:
                    return "↓ Cayendo"
                return "→ Estable"

            df_rr["Tendencia"] = df_rr.apply(_calc_trend, axis=1)

            # Current rank = most recent date with data
            for d in reversed(date_cols):
                if d in df_rr.columns and df_rr[d].notna().any():
                    df_rr["Rank Actual"] = df_rr[d]
                    break

        # ── PPC Coverage ─────────────────────────────────────────────
        ppc_cols = ["PPC Exact", "PPC Phrase", "PPC Broad", "PPC Auto"]
        ppc_available = [c for c in ppc_cols if c in df_rr.columns]
        if ppc_available:
            df_rr["PPC Activo"] = df_rr[ppc_available].fillna(0).sum(axis=1).apply(
                lambda x: "✅ Sí" if x > 0 else "❌ No"
            )

        # ── KPIs ─────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Keywords", len(df_rr))
        if "Tendencia" in df_rr.columns:
            k2.metric("↑ Mejorando", (df_rr["Tendencia"] == "↑ Mejorando").sum())
            k3.metric("↓ Cayendo", (df_rr["Tendencia"] == "↓ Cayendo").sum())
        if "PPC Activo" in df_rr.columns:
            k4.metric("Con PPC", (df_rr["PPC Activo"] == "✅ Sí").sum())

        # ── Main table ───────────────────────────────────────────────
        display_cols_rr = ["Search Term", "SV", "Relevance", "Median Rank"]
        if "Rank Actual" in df_rr.columns:
            display_cols_rr.append("Rank Actual")
        if "Tendencia" in df_rr.columns:
            display_cols_rr.append("Tendencia")
        if "PPC Activo" in df_rr.columns:
            display_cols_rr.append("PPC Activo")
        for pc in ppc_available:
            display_cols_rr.append(pc)
        if "SQ Score" in df_rr.columns:
            display_cols_rr.append("SQ Score")

        available_display = [c for c in display_cols_rr if c in df_rr.columns]
        df_rr_show = df_rr[available_display].copy()

        if "SV" in df_rr_show.columns:
            df_rr_show = df_rr_show.sort_values("SV", ascending=False).reset_index(drop=True)

        def _color_trend(val):
            if "Mejorando" in str(val):
                return "background-color: #E8F5E9; color: #1B5E20"
            if "Cayendo" in str(val):
                return "background-color: #FFEBEE; color: #B71C1C"
            if "Estable" in str(val):
                return "background-color: #F5F5F5; color: #666"
            return ""

        def _color_ppc(val):
            if "Sí" in str(val):
                return "background-color: #E8F5E9"
            if "No" in str(val):
                return "background-color: #FFF8E1"
            return ""

        styled_rr = df_rr_show.style
        if "Tendencia" in df_rr_show.columns:
            styled_rr = styled_rr.map(_color_trend, subset=["Tendencia"])
        if "PPC Activo" in df_rr_show.columns:
            styled_rr = styled_rr.map(_color_ppc, subset=["PPC Activo"])
        st.dataframe(styled_rr, use_container_width=True, height=min(38 + 35 * len(df_rr_show), 600))

        # ── Ranking trend chart ──────────────────────────────────────
        if date_cols and "Search Term" in df_rr.columns:
            st.markdown("---")
            st.markdown("#### 📈 Ranking diario (top keywords)")
            st.caption("Rank más bajo = mejor posición. Seleccioná keywords para ver su evolución.")

            # Pick top keywords by SV for chart
            chart_candidates = df_rr.copy()
            if "SV" in chart_candidates.columns:
                chart_candidates = chart_candidates.nlargest(20, "SV")

            term_col = "Search Term"
            available_terms = chart_candidates[term_col].dropna().unique().tolist()[:20]
            selected_terms = st.multiselect(
                "Keywords para el gráfico",
                options=available_terms,
                default=available_terms[:5],
                key="dd_rr_chart_kws",
            )

            if selected_terms:
                chart_data = df_rr[df_rr[term_col].isin(selected_terms)][
                    [term_col] + [d for d in date_cols if d in df_rr.columns]
                ].set_index(term_col).T
                chart_data.index.name = "Date"
                # Invert for display (lower rank = higher on chart)
                st.line_chart(chart_data, use_container_width=True)
                st.caption("Nota: valores más altos en el gráfico = peor posición. Rank 1 = mejor.")

        # ── PPC Coverage analysis ────────────────────────────────────
        if "PPC Activo" in df_rr.columns:
            st.markdown("---")
            st.markdown("#### 🎯 PPC Coverage")
            n_with_ppc = (df_rr["PPC Activo"] == "✅ Sí").sum()
            n_without_ppc = (df_rr["PPC Activo"] == "❌ No").sum()
            pc1, pc2 = st.columns(2)
            pc1.metric("Con PPC activo", n_with_ppc)
            pc2.metric("Sin PPC (oportunidades)", n_without_ppc)

            if n_without_ppc > 0:
                with st.expander(f"Ver {n_without_ppc} keywords sin PPC"):
                    no_ppc = df_rr[df_rr["PPC Activo"] == "❌ No"]
                    no_ppc_cols = [c for c in ["Search Term", "SV", "Relevance", "Rank Actual", "Tendencia"] if c in no_ppc.columns]
                    st.dataframe(
                        no_ppc[no_ppc_cols].sort_values("SV", ascending=False) if "SV" in no_ppc.columns else no_ppc[no_ppc_cols],
                        use_container_width=True,
                        hide_index=True,
                    )

        # ── Export ──────────────────────────────────────────────────────
        st.markdown("---")
        buf_rr = io.BytesIO()
        export_cols = [c for c in df_rr.columns if c not in date_cols]
        # Add last 7 dates for context
        recent_dates = date_cols[-7:] if len(date_cols) >= 7 else date_cols
        export_cols += [d for d in recent_dates if d in df_rr.columns]
        df_rr[[c for c in export_cols if c in df_rr.columns]].to_excel(buf_rr, index=False)
        st.download_button(
            f"⬇️ Exportar Rank Radar ({len(df_rr)} keywords)",
            data=buf_rr.getvalue(),
            file_name="datadive_rank_radar.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dd_rr_dl",
        )
