import io
import re
from collections import Counter

import streamlit as st
import pandas as pd

from core.helpers import read_sqp, extract_sqp_brand, kpi_card
from modules.pages.datadive_analyzer import _parse_mkl


# ═══════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data
def _load_campaign_csv(data, name):
    buf = io.BytesIO(data)
    return pd.read_excel(buf) if name.endswith(".xlsx") else pd.read_csv(buf)


def _extract_root_words(phrase):
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
        "<span style='font-size:2rem;'>📢</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>SBH Target Recommendation</div>"
        "<div style='font-size:0.82rem;color:#888;'>Recomendar keywords target para Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    # ── Inputs ────────────────────────────────────────────────────────
    ic1, ic2, ic3 = st.columns(3)
    with ic1:
        file_mkl = st.file_uploader("DataDive MKL (.xlsx)", type=["xlsx"], key="sbh_mkl")
    with ic2:
        file_sqp = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sbh_sqp")
    with ic3:
        file_camp = st.file_uploader("Campaign CSV (.xlsx o .csv)", type=["xlsx", "csv"], key="sbh_camp")

    if not file_mkl or not file_sqp:
        st.markdown(
            "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
            "border-radius:12px;margin:1rem 0;'>"
            "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
            "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí al menos el MKL de DataDive y el SQP de Amazon para generar recomendaciones.</div>"
            "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
            "Arrastrá o hacé click en los uploaders de arriba</div>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    # ── Parse MKL ─────────────────────────────────────────────────────
    df_mkl, _ = _parse_mkl(file_mkl.getvalue(), file_mkl.name)
    if df_mkl.empty:
        st.warning("No se pudieron parsear keywords del MKL.")
        return

    # ── Parse SQP ─────────────────────────────────────────────────────
    df_sqp = read_sqp(file_sqp)
    file_sqp.seek(0)
    brand = extract_sqp_brand(file_sqp)

    sqp_query_col = next((c for c in df_sqp.columns if "search query" in c.lower()), None)
    imp_total_col = next((c for c in df_sqp.columns if "impression" in c.lower() and "total" in c.lower() and "count" in c.lower()), None)
    imp_brand_col = next((c for c in df_sqp.columns if "impression" in c.lower() and "brand" in c.lower() and "count" in c.lower()), None)
    pur_total_col = next((c for c in df_sqp.columns if "purchase" in c.lower() and "total" in c.lower() and "count" in c.lower()), None)
    pur_brand_col = next((c for c in df_sqp.columns if "purchase" in c.lower() and "brand" in c.lower() and "count" in c.lower()), None)

    if not sqp_query_col:
        st.warning("No se encontró columna 'Search Query' en el SQP.")
        return

    # Build SQP lookup: keyword_lower -> {is_pct, ps_pct, total_imps, total_purchases}
    for c in [imp_total_col, imp_brand_col, pur_total_col, pur_brand_col]:
        if c and c in df_sqp.columns:
            df_sqp[c] = pd.to_numeric(df_sqp[c], errors="coerce").fillna(0)

    sqp_data = {}
    for _, row in df_sqp.iterrows():
        q = str(row[sqp_query_col]).strip().lower()
        imp_t = row.get(imp_total_col, 0) if imp_total_col else 0
        imp_b = row.get(imp_brand_col, 0) if imp_brand_col else 0
        pur_t = row.get(pur_total_col, 0) if pur_total_col else 0
        pur_b = row.get(pur_brand_col, 0) if pur_brand_col else 0
        sqp_data[q] = {
            "is_pct": round(imp_b / imp_t * 100, 1) if imp_t > 0 else 0,
            "ps_pct": round(pur_b / pur_t * 100, 1) if pur_t > 0 else 0,
            "total_imps": int(imp_t),
            "total_purchases": int(pur_t),
        }

    # ── Parse Campaign CSV (optional) ─────────────────────────────────
    sp_keywords = set()
    if file_camp:
        df_camp = _load_campaign_csv(file_camp.getvalue(), file_camp.name)
        kw_col = next((c for c in df_camp.columns if "keyword" in c.lower() and "text" in c.lower()), None)
        if not kw_col:
            kw_col = next((c for c in df_camp.columns if "targeting" in c.lower() and "type" not in c.lower()), None)
        state_col = next((c for c in df_camp.columns if c.lower() in ("state", "status")), None)
        if kw_col:
            df_kw = df_camp.copy()
            if state_col:
                df_kw = df_kw[df_kw[state_col].astype(str).str.lower().str.strip().isin(["enabled", "active"])]
            sp_keywords = set(df_kw[kw_col].dropna().astype(str).str.lower().str.strip())
        if sp_keywords:
            st.success(f"✅ Campaign CSV: {len(sp_keywords)} keywords SP activas detectadas")

    st.success(f"✅ MKL: {len(df_mkl)} keywords · SQP: {len(sqp_data)} queries" +
               (f" · Marca: **{brand}**" if brand else ""))

    # ── Build recommendations ─────────────────────────────────────────
    rows = []
    for _, mkl_row in df_mkl.iterrows():
        term = str(mkl_row.get("Search Term", "")).strip()
        term_lower = term.lower()
        sv = mkl_row.get("SV", 0)
        relevance = mkl_row.get("Relevance", 0)
        launch_score = mkl_row.get("Launch Score", 0)

        sqp_info = sqp_data.get(term_lower, {})
        is_pct = sqp_info.get("is_pct", 0)
        ps_pct = sqp_info.get("ps_pct", 0)
        market_buying = sqp_info.get("total_purchases", 0) > 0
        in_sp = term_lower in sp_keywords

        # Priority classification
        if sv >= 1000 and is_pct < 10 and market_buying and not in_sp:
            priority = "🔴 ALTA"
        elif sv >= 500 and is_pct < 20 and (not in_sp or is_pct < 5):
            priority = "🟡 MEDIA"
        elif sv >= 300:
            priority = "🟢 BAJA"
        else:
            continue

        rows.append({
            "Keyword": term,
            "SV": int(sv),
            "Relevance": round(relevance, 1),
            "IS %": is_pct,
            "PS %": ps_pct,
            "En SP": "✅" if in_sp else "❌",
            "Market Buying": "✅" if market_buying else "❌",
            "Prioridad": priority,
            "Launch Score": round(launch_score, 1),
        })

    if not rows:
        st.info("No hay keywords que cumplan los criterios mínimos (SV >= 300).")
        return

    df_sbh = pd.DataFrame(rows)
    prio_order = {"🔴 ALTA": 0, "🟡 MEDIA": 1, "🟢 BAJA": 2}
    df_sbh["_sort"] = df_sbh["Prioridad"].map(prio_order)
    df_sbh = df_sbh.sort_values(["_sort", "SV"], ascending=[True, False]).drop(columns=["_sort"]).reset_index(drop=True)

    # ── Clustering ────────────────────────────────────────────────────
    word_counter = Counter()
    kw_roots = {}
    for _, row in df_sbh.iterrows():
        roots = _extract_root_words(row["Keyword"])
        kw_roots[row["Keyword"]] = roots
        word_counter.update(roots)

    common_roots = {w for w, c in word_counter.items() if c >= 3}
    if common_roots:
        def _cluster(kw):
            roots = kw_roots.get(kw, [])
            matches = [r for r in roots if r in common_roots]
            return max(matches, key=lambda w: word_counter[w]) if matches else "other"
        df_sbh["Cluster"] = df_sbh["Keyword"].apply(_cluster)
    else:
        df_sbh["Cluster"] = "general"

    # Headline suggestion per cluster
    cluster_headlines = {}
    for cluster_name in df_sbh["Cluster"].unique():
        cluster_kws = df_sbh[df_sbh["Cluster"] == cluster_name]["Keyword"].tolist()[:5]
        # Use the most common meaningful words as headline basis
        all_words = []
        for kw in cluster_kws:
            all_words.extend(_extract_root_words(kw))
        top_words = [w for w, _ in Counter(all_words).most_common(4)]
        headline = " ".join(w.title() for w in top_words) if top_words else cluster_name.title()
        cluster_headlines[cluster_name] = headline

    df_sbh["Headline Sugerido"] = df_sbh["Cluster"].map(cluster_headlines)

    # ── KPIs ──────────────────────────────────────────────────────────
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        st.markdown(kpi_card("Targets totales", str(len(df_sbh))), unsafe_allow_html=True)
    with k2:
        st.markdown(kpi_card("Alta prioridad", str((df_sbh["Prioridad"] == "🔴 ALTA").sum())), unsafe_allow_html=True)
    with k3:
        st.markdown(kpi_card("Media prioridad", str((df_sbh["Prioridad"] == "🟡 MEDIA").sum())), unsafe_allow_html=True)
    with k4:
        st.markdown(kpi_card("Clusters", str(df_sbh["Cluster"].nunique())), unsafe_allow_html=True)

    # ── Filter ────────────────────────────────────────────────────────
    prio_filter = st.multiselect(
        "Filtrar por prioridad",
        options=["🔴 ALTA", "🟡 MEDIA", "🟢 BAJA"],
        default=["🔴 ALTA", "🟡 MEDIA"],
        key="sbh_prio_filter",
    )
    df_show = df_sbh[df_sbh["Prioridad"].isin(prio_filter)] if prio_filter else df_sbh

    # ── Table ─────────────────────────────────────────────────────────
    def _color_prio(val):
        if "ALTA" in str(val):
            return "background-color: #FFEBEE; color: #B71C1C"
        if "MEDIA" in str(val):
            return "background-color: #FFF8E1; color: #F57F17"
        if "BAJA" in str(val):
            return "background-color: #E8F5E9; color: #1B5E20"
        return ""

    styled = df_show.style.map(_color_prio, subset=["Prioridad"])
    st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_show), 600))

    # ── Clusters breakdown ────────────────────────────────────────────
    st.markdown("---")
    st.markdown("#### Clusters + Headline sugerido")
    st.caption("Agrupá keywords por tema para headlines de SBH coherentes.")

    cluster_df = (
        df_sbh.groupby("Cluster")
        .agg(KWs=("Keyword", "count"), SV_Total=("SV", "sum"),
             Alta=("Prioridad", lambda x: (x == "🔴 ALTA").sum()),
             Headline=("Headline Sugerido", "first"))
        .sort_values("SV_Total", ascending=False)
        .reset_index()
    )
    def _color_alta(val):
        try:
            v = int(val)
            if v >= 3:
                return "background-color: #FFEBEE; color: #B71C1C"
            if v >= 1:
                return "background-color: #FFF8E1; color: #F57F17"
            return ""
        except (ValueError, TypeError):
            return ""

    styled_cluster = cluster_df.style
    if "Alta" in cluster_df.columns:
        styled_cluster = styled_cluster.map(_color_alta, subset=["Alta"])
    st.dataframe(styled_cluster, use_container_width=True, hide_index=True)

    for cluster_name in cluster_df["Cluster"].tolist()[:10]:
        cluster_kws = df_sbh[df_sbh["Cluster"] == cluster_name].nlargest(5, "SV")
        headline = cluster_headlines.get(cluster_name, "")
        with st.expander(f"📢 {cluster_name.title()} — \"{headline}\" ({len(cluster_kws)} KWs)"):
            st.dataframe(
                cluster_kws[["Keyword", "SV", "IS %", "Prioridad"]].reset_index(drop=True),
                use_container_width=True, hide_index=True,
            )

    # ── Export ────────────────────────────────────────────────────────
    st.markdown("---")
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_sbh.to_excel(writer, sheet_name="SBH Targets", index=False)
        cluster_df.to_excel(writer, sheet_name="Clusters", index=False)
    st.download_button(
        f"⬇️ Exportar SBH Target Pack ({len(df_sbh)} keywords)",
        data=buf.getvalue(),
        file_name="sbh_target_pack.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="sbh_dl",
    )
