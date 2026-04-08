import io
import re
from collections import Counter
from datetime import datetime

import streamlit as st
import pandas as pd

from core.helpers import kpi_card


# ═══════════════════════════════════════════════════════════════════════
# Parser
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data
def _parse_cerebro(data, name):
    """Parse Helium 10 Cerebro reverse-ASIN export.

    File: US_AMAZON_cerebro_[ASIN]_[date].xlsx  —  sheet "Table"
    Handles "-" as NaN throughout.
    """
    buf = io.BytesIO(data)
    df = pd.read_excel(buf, sheet_name=0, na_values=["-", "—", "N/A", ""])

    # Normalise column names (strip whitespace)
    df.columns = df.columns.str.strip()

    # Coerce known numeric columns
    num_cols = [
        "ABA Total Click Share", "ABA Total Conv. Share", "Keyword Sales",
        "Cerebro IQ Score", "Search Volume", "Search Volume Trend",
        "H10 PPC Sugg. Bid", "H10 PPC Sugg. Min Bid", "H10 PPC Sugg. Max Bid",
        "Sponsored ASINs", "Competing Products", "CPR", "Title Density",
        "Amazon Rec. Rank", "Sponsored Rank", "Organic Rank",
        "Sponsored", "Organic",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")

    # Extract ASIN from filename  e.g. US_AMAZON_cerebro_B0FKGJYFC8_20260327
    asin_match = re.search(r'(B0[A-Z0-9]{8})', name, re.IGNORECASE)
    asin = asin_match.group(1).upper() if asin_match else None

    return df, asin


def _extract_root_words(phrase, stop_words=None):
    """Extract meaningful root words from a keyword phrase."""
    if stop_words is None:
        stop_words = {"for", "the", "and", "with", "a", "an", "in", "on", "to", "of",
                      "de", "para", "con", "en", "el", "la", "los", "las", "y", "del"}
    words = re.findall(r'[a-z]+', str(phrase).lower())
    return [w for w in words if w not in stop_words and len(w) > 2]


# ═══════════════════════════════════════════════════════════════════════
# Render
# ═══════════════════════════════════════════════════════════════════════

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🧲</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>Helium 10 Analyzer</div>"
        "<div style='font-size:0.82rem;color:#888;'>Análisis de exports de Helium 10 Cerebro: reverse ASIN, KW research y competitor gap.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    tab1, tab2, tab3 = st.tabs([
        "🔍 Cerebro Reverse ASIN",
        "🚀 KW Research",
        "⚔️ Competitor Gap",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — Cerebro Reverse ASIN
    # ══════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("🔍 Cerebro Reverse ASIN")
        st.caption("Archivo: US_AMAZON_cerebro_[ASIN]_[fecha].xlsx")

        file_cb = st.file_uploader(
            "Sube tu Cerebro export (.xlsx)", type=["xlsx"], key="h10_cerebro",
        )
        if not file_cb:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo Cerebro exportado desde Helium 10.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        df_cb, detected_asin = _parse_cerebro(file_cb.getvalue(), file_cb.name)
        if df_cb.empty:
            st.warning("No se pudieron extraer datos del archivo.")
            return

        if detected_asin:
            st.success(f"✅ {len(df_cb):,} keywords · ASIN detectado: **{detected_asin}**")
        else:
            st.success(f"✅ {len(df_cb):,} keywords cargadas")

        # ── Filters ──────────────────────────────────────────────────
        fc1, fc2, fc3 = st.columns(3)
        min_sv = fc1.number_input("SV mínimo", min_value=0, value=100, step=50, key="h10_cb_sv")
        max_org_rank = fc2.number_input(
            "Organic Rank máximo (0 = sin filtro)", min_value=0, value=0, step=5, key="h10_cb_rank",
        )
        min_iq = fc3.number_input("Cerebro IQ mínimo", min_value=0, value=0, step=1, key="h10_cb_iq")

        df_f = df_cb.copy()
        if "Search Volume" in df_f.columns:
            df_f = df_f[df_f["Search Volume"].fillna(0) >= min_sv]
        if max_org_rank > 0 and "Organic Rank" in df_f.columns:
            df_f = df_f[df_f["Organic Rank"].fillna(9999) <= max_org_rank]
        if min_iq > 0 and "Cerebro IQ Score" in df_f.columns:
            df_f = df_f[df_f["Cerebro IQ Score"].fillna(0) >= min_iq]

        if "Search Volume" in df_f.columns:
            df_f = df_f.sort_values("Search Volume", ascending=False).reset_index(drop=True)

        # ── Opportunity flags ────────────────────────────────────────
        has_org = "Organic" in df_f.columns
        has_spon = "Sponsored" in df_f.columns
        if has_org and has_spon:
            df_f["Oportunidad"] = df_f.apply(
                lambda r: "🟢 Oportunidad PPC"
                if r.get("Organic") == 1 and r.get("Sponsored") != 1
                else ("🟡 Depende de Ads"
                      if r.get("Sponsored") == 1 and r.get("Organic") != 1
                      else ("✅ Ambos" if r.get("Organic") == 1 and r.get("Sponsored") == 1
                            else "⚪ Ninguno")),
                axis=1,
            )

        # ── KPIs ─────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(kpi_card("Keywords", f"{len(df_f):,}"), unsafe_allow_html=True)
        if "Organic Rank" in df_f.columns:
            with k2:
                st.markdown(kpi_card("Con Organic Rank", str(int(df_f["Organic Rank"].notna().sum()))), unsafe_allow_html=True)
        if "Sponsored Rank" in df_f.columns:
            with k3:
                st.markdown(kpi_card("Con Sponsored Rank", str(int(df_f["Sponsored Rank"].notna().sum()))), unsafe_allow_html=True)
        if "Search Volume" in df_f.columns:
            with k4:
                st.markdown(kpi_card("SV promedio", f"{df_f['Search Volume'].mean():,.0f}"), unsafe_allow_html=True)

        if "Oportunidad" in df_f.columns:
            opp_counts = df_f["Oportunidad"].value_counts()
            o1, o2, o3 = st.columns(3)
            with o1:
                st.markdown(kpi_card("Oportunidad PPC", str(opp_counts.get("🟢 Oportunidad PPC", 0))), unsafe_allow_html=True)
            with o2:
                st.markdown(kpi_card("Depende de Ads", str(opp_counts.get("🟡 Depende de Ads", 0))), unsafe_allow_html=True)
            with o3:
                st.markdown(kpi_card("Ambos (Org+Spon)", str(opp_counts.get("✅ Ambos", 0))), unsafe_allow_html=True)

        # ── Table ────────────────────────────────────────────────────
        display_cols = [c for c in [
            "Keyword Phrase", "Search Volume", "Cerebro IQ Score",
            "Organic Rank", "Sponsored Rank", "Oportunidad",
            "H10 PPC Sugg. Bid", "Keyword Sales", "Competing Products",
            "Search Volume Trend", "CPR", "Title Density",
        ] if c in df_f.columns]

        def _color_opp(val):
            if "Oportunidad PPC" in str(val):
                return "background-color: #E8F5E9; color: #1B5E20"
            if "Depende de Ads" in str(val):
                return "background-color: #FFF8E1; color: #F57F17"
            if "Ambos" in str(val):
                return "background-color: #E3F2FD; color: #1565C0"
            return ""

        styled = df_f[display_cols].style
        if "Oportunidad" in display_cols:
            styled = styled.map(_color_opp, subset=["Oportunidad"])
        st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_f), 600))

        # ── Export ───────────────────────────────────────────────────
        st.markdown("---")
        buf = io.BytesIO()
        df_f.to_excel(buf, index=False)
        st.download_button(
            f"⬇️ Exportar {len(df_f):,} keywords (Excel)",
            data=buf.getvalue(),
            file_name=f"cerebro_{detected_asin or 'export'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="h10_cb_dl",
        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — KW Research (multi-competitor cross)
    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("🚀 KW Research — Launch Pack")
        st.caption("Subí 1-3 Cerebros de competidores para cruzar keywords y encontrar las más relevantes del nicho.")

        files_kw = []
        cols_up = st.columns(3)
        for i in range(3):
            f = cols_up[i].file_uploader(
                f"Competidor {i + 1}", type=["xlsx"], key=f"h10_kw_{i}",
            )
            if f:
                files_kw.append(f)

        if len(files_kw) < 1:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí al menos 1 archivo Cerebro de un competidor.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en los uploaders de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        # Parse all
        parsed = []
        for f in files_kw:
            df_p, asin_p = _parse_cerebro(f.getvalue(), f.name)
            if not df_p.empty:
                parsed.append((df_p, asin_p or f.name))

        if not parsed:
            st.warning("No se pudieron parsear los archivos.")
            return

        n_comp = len(parsed)
        st.success(f"✅ {n_comp} competidor(es) cargados")

        # ── Filters ──────────────────────────────────────────────────
        kf1, kf2 = st.columns(2)
        kw_min_sv = kf1.number_input("SV mínimo", min_value=0, value=300, step=50, key="h10_kw_sv")
        kw_min_comp = kf2.number_input(
            "Mín. competidores rankeando", min_value=1, max_value=n_comp,
            value=min(2, n_comp), step=1, key="h10_kw_mincomp",
        )

        # ── Cross keywords ───────────────────────────────────────────
        # Build a dict: keyword -> {asins that rank, best SV, avg organic rank}
        kw_data = {}
        for df_p, asin_label in parsed:
            kw_col = next((c for c in df_p.columns if "keyword" in c.lower() and "phrase" in c.lower()), None)
            sv_col = "Search Volume" if "Search Volume" in df_p.columns else None
            or_col = "Organic Rank" if "Organic Rank" in df_p.columns else None
            iq_col = "Cerebro IQ Score" if "Cerebro IQ Score" in df_p.columns else None
            bid_col = "H10 PPC Sugg. Bid" if "H10 PPC Sugg. Bid" in df_p.columns else None

            if not kw_col:
                continue

            for _, row in df_p.iterrows():
                kw = str(row[kw_col]).strip().lower()
                if not kw or kw == "nan":
                    continue
                sv = row[sv_col] if sv_col and pd.notna(row.get(sv_col)) else 0
                org_rank = row[or_col] if or_col and pd.notna(row.get(or_col)) else None
                iq = row[iq_col] if iq_col and pd.notna(row.get(iq_col)) else 0
                bid = row[bid_col] if bid_col and pd.notna(row.get(bid_col)) else 0

                if kw not in kw_data:
                    kw_data[kw] = {
                        "keyword": row[kw_col],
                        "sv": sv, "ranks": [], "asins": set(),
                        "iq_scores": [], "bids": [],
                    }
                # Keep max SV across files
                if sv > kw_data[kw]["sv"]:
                    kw_data[kw]["sv"] = sv
                    kw_data[kw]["keyword"] = row[kw_col]  # preserve original case
                if org_rank and org_rank > 0:
                    kw_data[kw]["ranks"].append(org_rank)
                kw_data[kw]["asins"].add(asin_label)
                if iq > 0:
                    kw_data[kw]["iq_scores"].append(iq)
                if bid > 0:
                    kw_data[kw]["bids"].append(bid)

        # Build result df
        rows_kw = []
        for kw, d in kw_data.items():
            n_ranking = len(d["asins"])
            sv = d["sv"]
            avg_rank = sum(d["ranks"]) / len(d["ranks"]) if d["ranks"] else 999
            avg_iq = sum(d["iq_scores"]) / len(d["iq_scores"]) if d["iq_scores"] else 0
            avg_bid = sum(d["bids"]) / len(d["bids"]) if d["bids"] else 0

            if sv < kw_min_sv or n_ranking < kw_min_comp:
                continue

            # Launch Priority Score = SV × (competitors ranking / total) × (1 / avg_rank)
            launch_score = sv * (n_ranking / n_comp) * (1 / max(avg_rank, 1))

            rows_kw.append({
                "Keyword": d["keyword"],
                "Search Volume": int(sv),
                "Competidores": n_ranking,
                "Avg Organic Rank": round(avg_rank, 1) if avg_rank < 999 else None,
                "Avg IQ Score": round(avg_iq, 1),
                "Avg Sugg. Bid": round(avg_bid, 2),
                "Launch Priority": round(launch_score, 1),
            })

        if not rows_kw:
            st.info("No hay keywords que cumplan los filtros. Bajá el SV mínimo o el mínimo de competidores.")
            return

        df_kw = pd.DataFrame(rows_kw).sort_values("Launch Priority", ascending=False).reset_index(drop=True)

        # ── Clusters by root word ────────────────────────────────────
        word_counter = Counter()
        kw_to_roots = {}
        for _, row in df_kw.iterrows():
            roots = _extract_root_words(row["Keyword"])
            kw_to_roots[row["Keyword"]] = roots
            word_counter.update(roots)

        # Top root words (appearing in 3+ keywords)
        common_roots = {w for w, c in word_counter.items() if c >= 3}
        if common_roots:
            def _assign_cluster(kw):
                roots = kw_to_roots.get(kw, [])
                matches = [r for r in roots if r in common_roots]
                if matches:
                    return max(matches, key=lambda w: word_counter[w])
                return "other"
            df_kw["Cluster"] = df_kw["Keyword"].apply(_assign_cluster)
        else:
            df_kw["Cluster"] = "—"

        # ── KPIs ─────────────────────────────────────────────────────
        k1, k2, k3, k4 = st.columns(4)
        with k1:
            st.markdown(kpi_card("Keywords relevantes", str(len(df_kw))), unsafe_allow_html=True)
        with k2:
            st.markdown(kpi_card("SV total", f"{df_kw['Search Volume'].sum():,.0f}"), unsafe_allow_html=True)
        with k3:
            st.markdown(kpi_card("Clusters", str(df_kw["Cluster"].nunique())), unsafe_allow_html=True)
        with k4:
            st.markdown(kpi_card("Launch Priority max", f"{df_kw['Launch Priority'].max():,.0f}"), unsafe_allow_html=True)

        # ── Table ────────────────────────────────────────────────────
        def _color_comp_count(val):
            try:
                v = int(val)
                if v >= n_comp:
                    return "background-color: #E8F5E9; color: #1B5E20"
                elif v >= 2:
                    return "background-color: #FFF8E1; color: #F57F17"
                else:
                    return "background-color: #F5F5F5; color: #666"
            except (ValueError, TypeError):
                return ""

        styled_kw = df_kw.style
        if "Competidores" in df_kw.columns:
            styled_kw = styled_kw.map(_color_comp_count, subset=["Competidores"])
        st.dataframe(
            styled_kw,
            use_container_width=True,
            height=min(38 + 35 * len(df_kw), 600),
        )

        # ── Clusters breakdown ───────────────────────────────────────
        if common_roots:
            st.markdown("---")
            st.markdown("#### Clusters de keywords")
            cluster_summary = (
                df_kw.groupby("Cluster")
                .agg(KWs=("Keyword", "count"), SV_Total=("Search Volume", "sum"),
                     Avg_Priority=("Launch Priority", "mean"))
                .sort_values("SV_Total", ascending=False)
                .reset_index()
            )
            cluster_summary["Avg_Priority"] = cluster_summary["Avg_Priority"].round(1)
            st.dataframe(cluster_summary, use_container_width=True, hide_index=True)

        # ── Export ───────────────────────────────────────────────────
        st.markdown("---")
        buf_kw = io.BytesIO()
        df_kw.to_excel(buf_kw, index=False)
        st.download_button(
            f"⬇️ Exportar KW Research Pack ({len(df_kw)} keywords)",
            data=buf_kw.getvalue(),
            file_name="h10_kw_research_pack.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="h10_kw_dl",
        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — Competitor Gap
    # ══════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("⚔️ Competitor Gap Analysis")
        st.caption("Tu Cerebro vs 1-2 competidores — detectá keywords donde ellos rankean y vos no.")

        gc1, gc2 = st.columns([1, 2])
        with gc1:
            file_mine = st.file_uploader(
                "Tu Cerebro (.xlsx)", type=["xlsx"], key="h10_gap_mine",
            )
        with gc2:
            gap_files_comp = []
            gc_cols = st.columns(2)
            for i in range(2):
                f = gc_cols[i].file_uploader(
                    f"Competidor {i + 1}", type=["xlsx"], key=f"h10_gap_comp_{i}",
                )
                if f:
                    gap_files_comp.append(f)

        if not file_mine:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí tu archivo Cerebro y al menos 1 competidor.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en los uploaders de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return
        if not gap_files_comp:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí al menos 1 archivo Cerebro de un competidor.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en los uploaders de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
            return

        df_mine, my_asin = _parse_cerebro(file_mine.getvalue(), file_mine.name)
        if df_mine.empty:
            st.warning("No se pudo parsear tu archivo Cerebro.")
            return

        competitors = []
        for f in gap_files_comp:
            df_c, asin_c = _parse_cerebro(f.getvalue(), f.name)
            if not df_c.empty:
                competitors.append((df_c, asin_c or f.name))

        if not competitors:
            st.warning("No se pudieron parsear los archivos de competidores.")
            return

        if my_asin:
            st.success(f"✅ Tu ASIN: **{my_asin}** vs {len(competitors)} competidor(es)")
        else:
            st.success(f"✅ {len(competitors)} competidor(es) cargados")

        # ── Filters ──────────────────────────────────────────────────
        gf1, gf2 = st.columns(2)
        gap_min_sv = gf1.number_input("SV mínimo", min_value=0, value=100, step=50, key="h10_gap_sv")
        gap_max_rank = gf2.number_input(
            "Organic Rank máx. del competidor (0 = sin filtro)", min_value=0, value=30, step=5,
            key="h10_gap_rank",
        )

        # ── Build gap ────────────────────────────────────────────────
        kw_col_mine = next((c for c in df_mine.columns if "keyword" in c.lower() and "phrase" in c.lower()), None)
        or_col = "Organic Rank"
        sv_col = "Search Volume"
        bid_col = "H10 PPC Sugg. Bid"

        if not kw_col_mine:
            st.error("No se encontró columna 'Keyword Phrase' en tu archivo.")
            return

        # My keywords with organic rank
        my_organic_kws = set()
        my_kw_data = {}
        for _, row in df_mine.iterrows():
            kw = str(row[kw_col_mine]).strip().lower()
            if not kw or kw == "nan":
                continue
            my_kw_data[kw] = row
            org_rank = row.get(or_col)
            if pd.notna(org_rank) and org_rank > 0:
                my_organic_kws.add(kw)

        # Competitor keywords with organic rank
        comp_kw_data = {}
        for df_c, asin_c in competitors:
            kw_col_c = next((c for c in df_c.columns if "keyword" in c.lower() and "phrase" in c.lower()), None)
            if not kw_col_c:
                continue
            for _, row in df_c.iterrows():
                kw = str(row[kw_col_c]).strip().lower()
                if not kw or kw == "nan":
                    continue
                org_r = row.get(or_col)
                if not pd.notna(org_r) or org_r <= 0:
                    continue
                if gap_max_rank > 0 and org_r > gap_max_rank:
                    continue

                if kw not in comp_kw_data:
                    comp_kw_data[kw] = {
                        "keyword": row[kw_col_c],
                        "sv": row.get(sv_col, 0) if pd.notna(row.get(sv_col)) else 0,
                        "bid": row.get(bid_col, 0) if pd.notna(row.get(bid_col)) else 0,
                        "comp_ranks": {},
                    }
                comp_kw_data[kw]["comp_ranks"][asin_c] = org_r
                # Keep max SV
                sv_val = row.get(sv_col, 0) if pd.notna(row.get(sv_col)) else 0
                if sv_val > comp_kw_data[kw]["sv"]:
                    comp_kw_data[kw]["sv"] = sv_val

        # Gaps = competitor ranks organic, I don't
        gap_rows = []
        for kw, cd in comp_kw_data.items():
            if kw in my_organic_kws:
                continue  # I already rank — not a gap
            if cd["sv"] < gap_min_sv:
                continue

            best_comp_rank = min(cd["comp_ranks"].values())
            n_comps_ranking = len(cd["comp_ranks"])

            # My data (may have sponsored but no organic)
            my_row = my_kw_data.get(kw)
            my_spon_rank = None
            if my_row is not None:
                sr = my_row.get("Sponsored Rank")
                if pd.notna(sr) and sr > 0:
                    my_spon_rank = sr

            # Action suggestion
            sv = cd["sv"]
            if sv >= 500 and best_comp_rank <= 15:
                action = "🚀 ATACAR"
            elif sv >= 200 or best_comp_rank <= 20:
                action = "👁️ MONITOREAR"
            else:
                action = "⏭️ IGNORAR"

            gap_rows.append({
                "Keyword": cd["keyword"],
                "Search Volume": int(sv),
                "Competidor Best Rank": int(best_comp_rank),
                "Competidores": n_comps_ranking,
                "Mi Sponsored Rank": int(my_spon_rank) if my_spon_rank else None,
                "Sugg. Bid": round(cd["bid"], 2) if cd["bid"] else None,
                "Acción": action,
            })

        if not gap_rows:
            st.success("✅ No se encontraron gaps — tu ASIN rankea orgánicamente en todas las keywords del competidor (con los filtros aplicados).")
            return

        df_gap = pd.DataFrame(gap_rows).sort_values("Search Volume", ascending=False).reset_index(drop=True)

        # ── KPIs ─────────────────────────────────────────────────────
        action_counts = df_gap["Acción"].value_counts()
        gk1, gk2, gk3, gk4 = st.columns(4)
        with gk1:
            st.markdown(kpi_card("Gaps totales", str(len(df_gap))), unsafe_allow_html=True)
        with gk2:
            st.markdown(kpi_card("Atacar", str(action_counts.get("🚀 ATACAR", 0))), unsafe_allow_html=True)
        with gk3:
            st.markdown(kpi_card("Monitorear", str(action_counts.get("👁️ MONITOREAR", 0))), unsafe_allow_html=True)
        with gk4:
            st.markdown(kpi_card("SV en gaps", f"{df_gap['Search Volume'].sum():,.0f}"), unsafe_allow_html=True)

        # ── Filter by action ─────────────────────────────────────────
        action_filter = st.multiselect(
            "Filtrar por acción",
            options=sorted(df_gap["Acción"].unique()),
            default=["🚀 ATACAR", "👁️ MONITOREAR"],
            key="h10_gap_action_filter",
        )
        df_gap_show = df_gap[df_gap["Acción"].isin(action_filter)] if action_filter else df_gap

        # ── Table ────────────────────────────────────────────────────
        def _color_action(val):
            if "ATACAR" in str(val):
                return "background-color: #E8F5E9; color: #1B5E20"
            if "MONITOREAR" in str(val):
                return "background-color: #FFF8E1; color: #F57F17"
            if "IGNORAR" in str(val):
                return "background-color: #F5F5F5; color: #999"
            return ""

        styled_gap = df_gap_show.style.map(_color_action, subset=["Acción"])
        st.dataframe(styled_gap, use_container_width=True, height=min(38 + 35 * len(df_gap_show), 600))

        # ── Export Gap ────────────────────────────────────────────────
        st.markdown("---")
        buf_gap = io.BytesIO()
        df_gap.to_excel(buf_gap, index=False)
        st.download_button(
            f"⬇️ Exportar Gap Analysis ({len(df_gap)} keywords)",
            data=buf_gap.getvalue(),
            file_name=f"h10_gap_{my_asin or 'analysis'}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="h10_gap_dl",
        )

        # ── Export Plan de Acción ────────────────────────────────────
        st.markdown("---")
        st.markdown("#### 🚀 Exportar como Plan de Acción")
        st.caption(
            "Genera un archivo compatible con Campaign Builder. "
            "Las keywords con acción ATACAR se convierten en keywords accionables."
        )

        n_atacar = df_gap["Acción"].str.contains("ATACAR", na=False).sum()
        if n_atacar > 0:
            df_plan = df_gap[df_gap["Acción"].str.contains("ATACAR", na=False)].copy()

            # Rename to match Plan de Acción format
            rename_map = {}
            if "Keyword Phrase" in df_plan.columns:
                rename_map["Keyword Phrase"] = "Keyword"
            elif "Keyword" not in df_plan.columns:
                # Try first text-like column
                for col in df_plan.columns:
                    if "keyword" in col.lower() or "query" in col.lower():
                        rename_map[col] = "Keyword"
                        break
            if "Search Volume" in df_plan.columns:
                rename_map["Search Volume"] = "Impressions mercado"
            if rename_map:
                df_plan = df_plan.rename(columns=rename_map)

            df_plan["Acción sugerida"] = "➕ AGREGAR keyword"

            if "Purchases mercado" not in df_plan.columns:
                df_plan["Purchases mercado"] = 0
            if "Brand Share %" not in df_plan.columns:
                df_plan["Brand Share %"] = 0

            buf_plan = io.BytesIO()
            df_plan.to_excel(buf_plan, index=False)
            st.download_button(
                f"⬇️ Descargar Plan de Acción ({n_atacar} keywords para Campaign Builder)",
                data=buf_plan.getvalue(),
                file_name=f"plan_accion_competitor_gap_{datetime.now().strftime('%Y%m%d')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="h10_gap_plan_dl",
            )
        else:
            st.info("No hay keywords con acción ATACAR para exportar como Plan de Acción.")
