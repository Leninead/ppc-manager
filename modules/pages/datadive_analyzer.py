import hashlib
import io
from datetime import datetime, timedelta

import numpy as np
import streamlit as st
import pandas as pd

from core import datadive as dd_api
from core.helpers import read_sqp, kpi_card
from modules.parsers import datadive as _dd


# ═══════════════════════════════════════════════════════════════════════
# Cached parsers
# ═══════════════════════════════════════════════════════════════════════

@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_mkl(data, name):
    return _dd.parse_mkl(data, name)


# Short retries in the UI: a persistent 429/500 must not hang the script thread
# for minutes (st.cache_data never caches exceptions, so each rerun retries).
def _api_client():
    return dd_api.client_from_env(max_retries=3, retry_after_cap_s=5.0)


@st.cache_data(ttl=3600, show_spinner="Listando niches de DataDive...")
def _api_niches():
    client = _api_client()
    if client is None:
        raise dd_api.DataDiveError("DATADIVE_API_KEY no configurada.")
    return client.list_niches()


@st.cache_data(ttl=3600, max_entries=6, show_spinner="Trayendo keywords de DataDive...")
def _api_mkl(niche_id: str):
    client = _api_client()
    if client is None:
        raise dd_api.DataDiveError("DATADIVE_API_KEY no configurada.")
    payload = client.niche_keywords(niche_id)
    df, asins = dd_api.keywords_to_mkl_df(payload)
    return df, asins, dd_api.latest_research_date(payload)


@st.cache_data(ttl=3600, max_entries=6, show_spinner="Trayendo competidores de DataDive...")
def _api_competitors(niche_id: str):
    client = _api_client()
    if client is None:
        raise dd_api.DataDiveError("DATADIVE_API_KEY no configurada.")
    return dd_api.competitors_to_df(client.niche_competitors(niche_id))


@st.cache_data(ttl=3600, show_spinner="Listando rank radars de DataDive...")
def _api_rank_radars():
    client = _api_client()
    if client is None:
        raise dd_api.DataDiveError("DATADIVE_API_KEY no configurada.")
    return client.list_rank_radars()


@st.cache_data(ttl=3600, max_entries=6, show_spinner="Trayendo rank radar de DataDive...")
def _api_rank_radar(radar_id: str, start_date: str, end_date: str):
    client = _api_client()
    if client is None:
        raise dd_api.DataDiveError("DATADIVE_API_KEY no configurada.")
    return dd_api.rank_radar_to_df(
        client.rank_radar_keywords(radar_id, start_date, end_date))


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_competitors(data, name):
    return _dd.parse_competitors(data, name)


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def _parse_rank_radar(data, name):
    return _dd.parse_rank_radar(data, name)


def _parse_upload(parser, uploaded, what: str):
    """Parse an upload behind a friendly error: a corrupt xlsx or the wrong
    file must never dump a traceback into the tab."""
    try:
        return parser(uploaded.getvalue(), uploaded.name)
    except Exception:
        st.error(f"No se pudo leer «{uploaded.name}» como {what} de DataDive. "
                 "Verificá que sea el export .xlsx correcto y volvé a subirlo.")
        return None


# ═══════════════════════════════════════════════════════════════════════
# AI analysis (core/ai_tab layer over the ai/agents/datadive agent)
# ═══════════════════════════════════════════════════════════════════════

def _mkl_ai_records(df_top: pd.DataFrame, competitor_asins: list,
                    my_asin: str, nucleo_slots: int) -> list[dict]:
    """Serialize the capped frame for the AI agent — native types only.

    `bloque` records how the row got in (nucleo = by SV, cola = by relevance
    below that cut): without it the document looks SV-ordered end to end and
    the agent reads the tail as leftovers.
    """
    # Same rule as the tab's gap table: the own ASIN is not a competitor.
    comp_cols = [a for a in competitor_asins
                 if a in df_top.columns and a != my_asin]
    records = []
    for pos, (_, r) in enumerate(df_top.iterrows()):
        mi_rank = r["Mi Ranking"] if "Mi Ranking" in df_top.columns else None
        records.append({
            "term": str(r["Search Term"]),
            "sv": int(r["SV"]),
            "relevance": float(r["Relevance"]),
            "sugg_bid": float(r["Sugg. Bid"]) if "Sugg. Bid" in df_top.columns else 0.0,
            "launch_score": float(r["Launch Score"]) if "Launch Score" in df_top.columns else 0.0,
            "mi_rank": int(mi_rank) if pd.notna(mi_rank) else None,
            "comps_rankeando": int(r[comp_cols].notna().sum()) if comp_cols else 0,
            "bloque": "nucleo" if pos < nucleo_slots else "cola",
        })
    return records


def _num(value) -> float:
    x = pd.to_numeric(str(value).replace("$", "").replace(",", ""), errors="coerce")
    return 0.0 if pd.isna(x) else float(x)


def _mkl_ai_competitors(fuente: str):
    """Competitor records for the AI context, or None when there is no data."""
    try:
        if fuente == "API DataDive":
            active = st.session_state.get("dd_mkl_api_niche")
            if not active:
                return None
            df_c, medians = _api_competitors(active)
        else:
            up = st.session_state.get("dd_comp")
            if up is None:
                return None
            df_c, medians = _parse_competitors(up.getvalue(), up.name)
        if df_c is None or df_c.empty:
            return None
        records = []
        for _, r in df_c.head(30).iterrows():
            records.append({
                "asin": str(r.get("ASIN", "")),
                "brand": str(r.get("Brand", "")),
                "price": round(_num(r.get("Price")), 2),
                "rating": round(_num(r.get("Rating")), 1),
                "reviews": int(_num(r.get("Review Count"))),
                "sales_30d": int(_num(r.get("30d Sales"))),
                "revenue_30d": int(_num(r.get("30d Revenue"))),
                "kws_p1": int(_num(r.get("KWs on P1"))),
            })
        records.append({
            "asin": "MEDIANA_NICHE",
            "brand": "(mediana del niche)",
            "price": round(_num(medians.get("Price")), 2),
            "rating": round(_num(medians.get("Rating")), 1),
            "reviews": int(_num(medians.get("Review Count"))),
            "sales_30d": int(_num(medians.get("30d Sales"))),
            "revenue_30d": int(_num(medians.get("30d Revenue"))),
            "kws_p1": int(_num(medians.get("KWs on P1"))),
        })
        return records
    except Exception:
        # the MKL analysis runs fine without competitors; this never kills the tab
        return None


_AI_BADGE_COLORS = {
    "alta": "background-color:#FAECE7;color:#993C1D",
    "media": "background-color:#FFF8E1;color:#9C5700",
    "baja": "background-color:#F5F5F5;color:#616161",
    "PPC_AHORA": "background-color:#E8F5E9;color:#1B5E20",
    "LISTING_PRIMERO": "background-color:#FFF8E1;color:#9C5700",
    "NO_ATACABLE": "background-color:#FFEBEE;color:#B71C1C",
    "exact": "background-color:#EDE7F6;color:#4527A0",
    "phrase": "background-color:#EDE7F6;color:#4527A0",
    "broad": "background-color:#EDE7F6;color:#4527A0",
    "product_targeting": "background-color:#EDE7F6;color:#4527A0",
}


def _render_mkl_ai_result(result: dict, analysis, records: list, labels: dict) -> None:
    from core import ai_tab
    ids = {f"K{i + 1:02d}": rec for i, rec in enumerate(records)}
    clusters = result.get("clusters") or []
    gaps = result.get("gaps") or []
    warnings = sum(1 for g in gaps if g.get("advertencia"))
    st.markdown(
        ai_tab.ai_chips_html(warnings, f"{len(clusters)} clusters · {len(gaps)} gaps",
                             analysis.elapsed, labels),
        unsafe_allow_html=True)
    st.markdown(ai_tab.synthesis_html(result.get("synthesis") or {}, labels),
                unsafe_allow_html=True)

    cluster_rows = []
    for i, c in enumerate(clusters, 1):
        matched = [ids[rid] for rid in c.get("row_ids", []) if rid in ids]
        cluster_rows.append({
            # The array order is the attack order; numbering makes that visible.
            "item": f"{i}. {c.get('nombre', '')}",
            "type_tag": f"{len(matched)} kws",
            "metrics": [f"SV {sum(rec['sv'] for rec in matched):,}"],
            "badges": [c.get("prioridad", ""), c.get("match_type", "")],
            "reasoning": c.get("racional", ""),
        })
    if cluster_rows:
        st.markdown(ai_tab.opinion_table_html(cluster_rows, "Clusters de intención",
                                              labels, _AI_BADGE_COLORS),
                    unsafe_allow_html=True)

    gap_rows = []
    for g in gaps:
        rec = ids.get(str(g.get("row_id", "")))
        if rec is None:
            continue
        # The metrics the reasons cite must be on screen, or the AM cannot audit
        # the judgement against their own table.
        metrics = [f"SV {rec['sv']:,}", f"rel {rec['relevance']:.1f}",
                   f"{rec['comps_rankeando']} comps"]
        if rec.get("launch_score"):
            metrics.append(f"launch {rec['launch_score']:.0f}")
        metrics.append(f"mi rank {rec['mi_rank']}" if rec.get("mi_rank")
                       else "no rankeo")
        gap_rows.append({
            "row_id": str(g.get("row_id", "")),
            "item": rec["term"],
            "metrics": metrics,
            "badges": [g.get("via", "")],
            "confidence": str(g.get("confianza", "")).upper(),
            "warning": g.get("advertencia") or "",
            "reasoning": g.get("razon", ""),
        })
    if gap_rows:
        st.markdown(ai_tab.opinion_table_html(gap_rows, "Gaps priorizados",
                                              labels, _AI_BADGE_COLORS),
                    unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════
# Style helpers
# ═══════════════════════════════════════════════════════════════════════

def _color_score(val, green_thresh, yellow_thresh):
    try:
        v = float(val)
        if v >= green_thresh:
            return "background-color: #E8F5E9; color: #1B5E20"
        elif v >= yellow_thresh:
            return "background-color: #FFF8E1; color: #F57F17"
        else:
            return "background-color: #FFEBEE; color: #B71C1C"
    except (ValueError, TypeError):
        return ""


# ═══════════════════════════════════════════════════════════════════════
# Render
# ═══════════════════════════════════════════════════════════════════════

def render():
    st.markdown(
        "<div style='display:flex;align-items:center;gap:0.75rem;margin-bottom:0.25rem;'>"
        "<span style='font-size:2rem;'>🧲</span>"
        "<div>"
        "<div style='font-size:1.3rem;font-weight:800;color:#1F1F1F;'>DataDive Analyzer</div>"
        "<div style='font-size:0.82rem;color:#888;'>Análisis de exports de DataDive: MKL Keywords, Competitors, Rank Radar y Ranking Volatility.</div>"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Research de competidores: keywords de mercado, matriz comparativa, rank tracking y volatilidad cruzada con PPC IS.")
        with col2:
            st.markdown("**📂 Archivos necesarios**")
            st.caption("DataDive → Export: MKL Keywords, Competitors, Rank Radar (.xlsx). SQP opcional para cruzar con PPC IS en Tab 4.")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Helium 10 Analyzer (M16) o Campaign Builder (M10) con keywords detectadas.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Tab 1: subí MKL → detectá ASINs competidores y keyword gaps\n"
            "2. Tab 2: subí Competitors → comparación tu ASIN vs Niche Median\n"
            "3. Tab 3: subí Rank Radar → ranking orgánico diario y tendencias\n"
            "4. Tab 4: cruzá Rank Radar + SQP → detectá volátiles sin PPC (RIESGO)\n"
            "5. Tab 5: subí tu MKL + MKL competidor → gap analysis unificado"
        )

    ai_analysis = None
    ai_labels_dd = None
    api_niches_by_id = {}

    def _niche_label(niche_id):
        n = api_niches_by_id.get(niche_id, {})
        return f"{n.get('nicheLabel') or niche_id} · {n.get('marketplace') or ''}"

    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "📖 MKL Keywords",
        "⚔️ Competitors",
        "📡 Rank Radar",
        "📊 Ranking + PPC IS",
        "🏆 Competitor Intel",
    ])

    # ══════════════════════════════════════════════════════════════════
    # TAB 1 — MKL Keywords
    # ══════════════════════════════════════════════════════════════════
    with tab1:
        st.subheader("📖 Master Keyword List")

        df_mkl = None
        competitor_asins = []
        mkl_signature = ""
        mkl_label = ""
        mkl_marketplace = ""

        fuente = "Archivo"
        if dd_api.client_from_env() is not None:
            fuente = st.radio("Fuente", ["API DataDive", "Archivo"],
                              horizontal=True, key="dd_mkl_source")

        if fuente == "API DataDive":
            niches = None
            try:
                niches = _api_niches()
            except dd_api.DataDiveError as e:
                st.error(str(e))
            if niches is not None and not niches:
                st.caption("La organización no tiene niches en DataDive.")
            elif niches:
                ordered = sorted(niches,
                                 key=lambda n: str(n.get("latestResearchDate") or ""),
                                 reverse=True)
                by_id = {n["nicheId"]: n for n in ordered if n.get("nicheId")}
                api_niches_by_id = by_id  # compartido con tabs 2 y 5
                sel_col, btn_col = st.columns([3, 1], vertical_alignment="bottom")
                selected_id = sel_col.selectbox(
                    "Niche",
                    options=list(by_id),
                    format_func=lambda i: (f"{by_id[i].get('nicheLabel') or i}"
                                           f" · {by_id[i].get('marketplace') or ''}"),
                    key="dd_mkl_niche",
                )
                if btn_col.button("Traer de DataDive", key="dd_mkl_fetch", type="primary"):
                    _api_mkl.clear(selected_id)
                    st.session_state["dd_mkl_api_niche"] = selected_id
                active_id = st.session_state.get("dd_mkl_api_niche")
                if active_id and active_id in by_id:
                    try:
                        df_mkl, competitor_asins, research_date = _api_mkl(active_id)
                        niche = by_id[active_id]
                        mkl_label = str(niche.get("nicheLabel") or active_id)
                        mkl_marketplace = str(niche.get("marketplace") or "")
                        # Content signature: a re-fetch with different keywords
                        # re-fires the AI analysis even when the date is unchanged.
                        content_hash = hashlib.sha1(
                            df_mkl.to_csv(index=False).encode("utf-8")).hexdigest()[:16]
                        mkl_signature = f"api:{active_id}:{content_hash}"
                        fecha_dive = (research_date[:16].replace("T", " ") + " UTC"
                                      if research_date else "s/f")
                        st.caption(f"Niche {mkl_label} · último dive: {fecha_dive}")
                    except dd_api.DataDiveError as e:
                        st.error(str(e))
                elif active_id:
                    st.caption("El niche traído ya no aparece en la lista de "
                               "DataDive — volvé a elegirlo.")
                else:
                    st.caption("Elegí un niche y presioná Traer de DataDive. "
                               "El uploader de archivo sigue disponible en Fuente → Archivo.")
        else:
            st.caption("Archivo: niche-*-keywords.xlsx de DataDive")
            file_mkl = st.file_uploader("Sube tu MKL (.xlsx)", type=["xlsx"], key="dd_mkl")
            if file_mkl:
                parsed_mkl = _parse_upload(_parse_mkl, file_mkl, "MKL Keywords")
                if parsed_mkl is not None:
                    df_mkl, competitor_asins = parsed_mkl
                    mkl_label = file_mkl.name
                    mkl_signature = "file:" + hashlib.sha1(file_mkl.getvalue()).hexdigest()[:16]
            else:
                st.markdown(
                    "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                    "border-radius:12px;margin:1rem 0;'>"
                    "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                    "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo niche-*-keywords.xlsx exportado desde DataDive.</div>"
                    "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                    "Arrastrá o hacé click en el uploader de arriba</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        if df_mkl is not None:
            if df_mkl.empty:
                st.warning("No se pudieron extraer keywords del archivo."
                           if fuente == "Archivo"
                           else "El niche no devolvió keywords.")
            else:
                st.success(f"✅ {len(df_mkl)} keywords · {len(competitor_asins)} competidores detectados")
                if df_mkl["SV"].sum() == 0:
                    st.warning("Ninguna keyword trae SV: puede que el archivo no "
                               "sea un export MKL o que DataDive haya cambiado "
                               "el formato. Verificá el archivo antes de seguir.")
                # The export carries the real Launch Score, so every file audits
                # the formula the API mode relies on.
                elif fuente == "Archivo" and dd_api.launch_score_drifted(df_mkl):
                    st.warning(
                        "El Launch Score de este archivo ya no coincide con la "
                        "fórmula que usa el modo API: DataDive probablemente la "
                        "recalibró. Avisale al equipo técnico — los valores por "
                        "API quedaron desactualizados (el resto del módulo no "
                        "se ve afectado)."
                    )

                my_asin = st.text_input(
                    "Tu ASIN (para detectar gaps)", placeholder="B0XXXXXXXXX", key="dd_mkl_asin",
                ).strip().upper()

                fc1, fc2 = st.columns(2)
                min_sv = fc1.number_input("SV mínimo", min_value=0, value=100, step=50, key="dd_mkl_sv")
                min_rel = fc2.slider("Relevancia mínima", 0.0, 10.0, 1.0, 0.5, key="dd_mkl_rel")

                df_filtered = df_mkl[
                    (df_mkl["SV"] >= min_sv) & (df_mkl["Relevance"] >= min_rel)
                ].copy()

                if my_asin and my_asin in df_filtered.columns:
                    df_filtered["Mi Ranking"] = df_filtered[my_asin]
                    df_filtered["Rankeado"] = df_filtered["Mi Ranking"].notna().map({True: "✅ Sí", False: "❌ No"})
                elif my_asin:
                    df_filtered["Mi Ranking"] = None
                    df_filtered["Rankeado"] = "❌ No"

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(kpi_card("Keywords", str(len(df_filtered))), unsafe_allow_html=True)
                with k2:
                    st.markdown(kpi_card("SV total", f"{df_filtered['SV'].sum():,.0f}"), unsafe_allow_html=True)
                with k3:
                    st.markdown(kpi_card("SV promedio", f"{df_filtered['SV'].mean():,.0f}" if len(df_filtered) else "—"), unsafe_allow_html=True)
                with k4:
                    if my_asin:
                        ranked_count = df_filtered["Mi Ranking"].notna().sum() if "Mi Ranking" in df_filtered.columns else 0
                        st.markdown(kpi_card(f"Rankeadas ({my_asin[:10]})", f"{ranked_count}/{len(df_filtered)}"), unsafe_allow_html=True)
                    else:
                        st.markdown(kpi_card("Competidores", str(len(competitor_asins))), unsafe_allow_html=True)

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
                if "Relevance" in df_show.columns:
                    styled = styled.map(lambda v: _color_score(v, 3, 2), subset=["Relevance"])
                if "Launch Score" in df_show.columns:
                    styled = styled.map(lambda v: _color_score(v, 7, 4), subset=["Launch Score"])
                if "Rankeado" in df_show.columns:
                    styled = styled.map(_color_ranked, subset=["Rankeado"])
                st.dataframe(styled, use_container_width=True, height=min(38 + 35 * len(df_show), 600))

                if my_asin and "Mi Ranking" in df_filtered.columns:
                    st.markdown("---")
                    st.markdown("#### 🕳️ Keyword Gaps")
                    st.caption(f"Keywords donde tu ASIN ({my_asin}) NO rankea pero competidores sí.")
                    df_gaps = df_filtered[df_filtered["Mi Ranking"].isna()].copy()
                    comp_cols = [c for c in competitor_asins if c in df_gaps.columns and c != my_asin]
                    if comp_cols:
                        df_gaps["Competidores rankeados"] = df_gaps[comp_cols].notna().sum(axis=1)
                        df_gaps = df_gaps[df_gaps["Competidores rankeados"] > 0]
                    if not df_gaps.empty:
                        df_gaps = df_gaps.sort_values("SV", ascending=False)
                        g1, g2 = st.columns(2)
                        with g1:
                            st.markdown(kpi_card("Gaps detectados", str(len(df_gaps))), unsafe_allow_html=True)
                        with g2:
                            st.markdown(kpi_card("SV perdido", f"{df_gaps['SV'].sum():,.0f}"), unsafe_allow_html=True)
                        gap_cols = ["Search Term", "SV", "Relevance", "Launch Score"]
                        if "Competidores rankeados" in df_gaps.columns:
                            gap_cols.append("Competidores rankeados")
                        st.dataframe(
                            df_gaps[[c for c in gap_cols if c in df_gaps.columns]].reset_index(drop=True),
                            use_container_width=True, height=min(38 + 35 * len(df_gaps), 500),
                        )
                    else:
                        st.success("✅ No se detectaron gaps.")

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

                st.markdown("---")
                st.subheader("Análisis IA")
                from ai.config import AI_ENABLED
                if not AI_ENABLED:
                    st.caption("Análisis IA deshabilitado (AI_ENABLED=0).")
                elif df_filtered.empty:
                    st.caption("Sin keywords tras el filtro — nada para analizar.")
                else:
                    from core import ai_tab
                    from ai.agents.datadive import context as dd_ctx

                    df_top = dd_ctx.select_keywords(df_filtered)
                    records = _mkl_ai_records(df_top, competitor_asins, my_asin,
                                              dd_ctx._SV_SLOTS)
                    payload = dd_ctx.MklData(
                        niche_label=mkl_label,
                        fuente=fuente,
                        marketplace=mkl_marketplace,
                        my_asin=my_asin,
                        min_sv=int(min_sv),
                        min_rel=float(min_rel),
                        total_keywords=len(df_filtered),
                        competitor_asins=list(competitor_asins),
                        keywords=records,
                        competitors=_mkl_ai_competitors(fuente),
                        # A typed ASIN absent from the dive leaves mi_rank empty in
                        # EVERY row: that is missing data, not a set of gaps.
                        my_asin_en_niche=bool(my_asin) and my_asin in df_mkl.columns,
                    )
                    ai_labels_dd = ai_tab.ai_labels(
                        "es", {"chat": "Análisis IA — DataDive"})
                    st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
                    ai_analysis = ai_tab.resolve_analysis(
                        slug="datadive", payload=payload,
                        file_signature=mkl_signature, labels=ai_labels_dd)
                    if ai_analysis is not None:
                        # A STALE analysis cites row_ids from ITS payload, not from
                        # this rerun: keeping the records per digest stops the join
                        # from ever crossing the wrong keywords.
                        from ai import runtime as ai_runtime
                        rec_store = st.session_state.setdefault(
                            "dd_ai_records_store", {})
                        current = ai_runtime.peek("datadive", payload)
                        if current is not None and current.digest == ai_analysis.digest:
                            rec_store[ai_analysis.digest] = records
                            for old_digest in list(rec_store)[:-8]:
                                del rec_store[old_digest]
                        render_records = rec_store.get(ai_analysis.digest, records)

                        def _render_result(result, a, _rec=render_records,
                                           _lab=ai_labels_dd):
                            _render_mkl_ai_result(result, a, _rec, _lab)

                        ai_tab.render_analysis(
                            ai_analysis, slug="datadive", labels=ai_labels_dd,
                            render_result=_render_result)

    # ══════════════════════════════════════════════════════════════════
    # TAB 2 — Competitors
    # ══════════════════════════════════════════════════════════════════
    with tab2:
        st.subheader("⚔️ Competitor Analysis")

        df_comp = None
        median_data = {}
        if fuente == "API DataDive":
            active_comp_id = st.session_state.get("dd_mkl_api_niche")
            if active_comp_id and active_comp_id in api_niches_by_id:
                try:
                    df_comp, median_data = _api_competitors(active_comp_id)
                    st.caption(f"Competidores del niche {_niche_label(active_comp_id)} "
                               "· vía API DataDive")
                except dd_api.DataDiveError as e:
                    st.error(str(e))
            else:
                st.caption("Traé primero un niche en el tab MKL Keywords — "
                           "los competidores salen del mismo niche.")
        else:
            st.caption("Archivo: niche-*-competitors.xlsx de DataDive")
            file_comp = st.file_uploader("Sube tu Competitors (.xlsx)", type=["xlsx"], key="dd_comp")
            if file_comp:
                parsed_comp = _parse_upload(_parse_competitors, file_comp, "Competitors")
                if parsed_comp is not None:
                    df_comp, median_data = parsed_comp
            else:
                st.markdown(
                    "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                    "border-radius:12px;margin:1rem 0;'>"
                    "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                    "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo niche-*-competitors.xlsx exportado desde DataDive.</div>"
                    "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                    "Arrastrá o hacé click en el uploader de arriba</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        if df_comp is not None:
            if df_comp.empty:
                st.warning("No se pudieron extraer datos de competidores.")
            else:
                st.success(f"✅ {len(df_comp)} competidores detectados")
                my_asin_comp = st.text_input(
                    "Tu ASIN (para destacar)", placeholder="B0XXXXXXXXX", key="dd_comp_asin",
                ).strip().upper()

                revenue_col = next((c for c in df_comp.columns if "revenue" in c.lower()), None)
                sales_col = next((c for c in df_comp.columns if "30d sales" in c.lower() or "sales" in c.lower()), None)
                price_col = next((c for c in df_comp.columns if "price" in c.lower()), None)
                rating_col = next((c for c in df_comp.columns if "rating" in c.lower()), None)
                review_col = next((c for c in df_comp.columns if "review" in c.lower()), None)
                kws_col = next((c for c in df_comp.columns if "kws on p1" in c.lower() or "kws" in c.lower()), None)

                sort_col = revenue_col or sales_col
                if sort_col and sort_col in df_comp.columns:
                    df_comp = df_comp.sort_values(sort_col, ascending=False).reset_index(drop=True)

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

                def _highlight_my_asin(row):
                    if my_asin_comp and row.get("ASIN") == my_asin_comp:
                        return ["background-color: #FFF3E0"] * len(row)
                    return [""] * len(row)

                styled_comp = df_comp.style.apply(_highlight_my_asin, axis=1)
                if rating_col and rating_col in df_comp.columns:
                    styled_comp = styled_comp.map(lambda v: _color_score(v, 4.5, 4.0), subset=[rating_col])
                st.dataframe(styled_comp, use_container_width=True, height=min(38 + 35 * len(df_comp), 600))

                st.markdown("---")
                buf_comp = io.BytesIO()
                df_comp.to_excel(buf_comp, index=False)
                st.download_button(
                    f"⬇️ Exportar {len(df_comp)} competidores (Excel)",
                    data=buf_comp.getvalue(), file_name="datadive_competitors.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_comp_dl",
                )

    # ══════════════════════════════════════════════════════════════════
    # TAB 3 — Rank Radar
    # ══════════════════════════════════════════════════════════════════
    with tab3:
        st.subheader("📡 Rank Radar")

        df_rr = None
        date_cols_rr = []
        agg_data = {}
        rr_source_name = None
        if fuente == "API DataDive":
            radars = None
            try:
                radars = _api_rank_radars()
            except dd_api.DataDiveError as e:
                st.error(str(e))
            if radars is not None and not radars:
                st.caption("La organización no tiene rank radars en DataDive.")
            elif radars:
                by_radar = {r["id"]: r for r in radars if r.get("id")}

                def _radar_label(radar_id):
                    r = by_radar.get(radar_id, {})
                    title = str(r.get("title") or radar_id)
                    title = title[:60] + ("…" if len(title) > 60 else "")
                    return (f"{title} · {r.get('marketplace') or ''} · "
                            f"{r.get('keywordCount') or 0} kws")

                sel_col, days_col, btn_col = st.columns([4, 1, 1],
                                                        vertical_alignment="bottom")
                radar_sel = sel_col.selectbox(
                    "Rank radar", options=list(by_radar),
                    format_func=_radar_label, key="dd_rr_radar")
                days_sel = days_col.selectbox(
                    "Rango", [30, 60, 90],
                    format_func=lambda d: f"{d} días", key="dd_rr_days")
                if btn_col.button("Traer de DataDive", key="dd_rr_fetch", type="primary"):
                    end_d = datetime.now().date()
                    start_d = end_d - timedelta(days=days_sel)
                    _api_rank_radar.clear(radar_sel, start_d.isoformat(), end_d.isoformat())
                    st.session_state["dd_rr_api_sel"] = (
                        radar_sel, start_d.isoformat(), end_d.isoformat())
                rr_sel = st.session_state.get("dd_rr_api_sel")
                if rr_sel and rr_sel[0] in by_radar:
                    try:
                        df_rr, date_cols_rr, agg_data = _api_rank_radar(*rr_sel)
                        st.caption(f"Radar: {_radar_label(rr_sel[0])} · "
                                   f"{rr_sel[1]} → {rr_sel[2]} · vía API DataDive")
                    except dd_api.DataDiveError as e:
                        st.error(str(e))
                elif rr_sel:
                    st.caption("El radar traído ya no aparece en la lista — volvé a elegirlo.")
                else:
                    st.caption("Elegí un rank radar y presioná Traer de DataDive.")
        else:
            st.caption("Archivo: [product-name].xlsx de DataDive Rank Radar")
            file_rr = st.file_uploader("Sube tu Rank Radar (.xlsx)", type=["xlsx"], key="dd_rr")
            if file_rr:
                parsed_rr = _parse_upload(_parse_rank_radar, file_rr, "Rank Radar")
                if parsed_rr is not None:
                    df_rr, date_cols_rr, agg_data = parsed_rr
                    rr_source_name = file_rr.name
            else:
                st.markdown(
                    "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                    "border-radius:12px;margin:1rem 0;'>"
                    "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                    "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el archivo de Rank Radar exportado desde DataDive.</div>"
                    "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                    "Arrastrá o hacé click en el uploader de arriba</div>"
                    "</div>",
                    unsafe_allow_html=True,
                )

        if df_rr is not None:
            if df_rr.empty:
                st.warning("No se pudieron extraer datos del Rank Radar.")
            else:
                st.success(f"✅ {len(df_rr)} keywords · {len(date_cols_rr)} días de ranking")

                if len(date_cols_rr) >= 2:
                    first_dates = date_cols_rr[:min(7, len(date_cols_rr) // 2)]
                    last_dates = date_cols_rr[max(len(date_cols_rr) // 2, len(date_cols_rr) - 7):]

                    def _calc_trend(row):
                        old_vals = [row.get(d) for d in first_dates if pd.notna(row.get(d))]
                        new_vals = [row.get(d) for d in last_dates if pd.notna(row.get(d))]
                        if not old_vals or not new_vals:
                            return "—"
                        avg_old = sum(old_vals) / len(old_vals)
                        avg_new = sum(new_vals) / len(new_vals)
                        if avg_old == 0:
                            return "—"
                        if avg_new < avg_old * 0.9:
                            return "↑ Mejorando"
                        elif avg_new > avg_old * 1.1:
                            return "↓ Cayendo"
                        return "→ Estable"

                    df_rr["Tendencia"] = df_rr.apply(_calc_trend, axis=1)
                    for d in reversed(date_cols_rr):
                        if d in df_rr.columns and df_rr[d].notna().any():
                            df_rr["Rank Actual"] = df_rr[d]
                            break

                ppc_cols = ["PPC Exact", "PPC Phrase", "PPC Broad", "PPC Auto"]
                ppc_available = [c for c in ppc_cols if c in df_rr.columns]
                if ppc_available:
                    df_rr["PPC Activo"] = df_rr[ppc_available].fillna(0).sum(axis=1).apply(
                        lambda x: "✅ Sí" if x > 0 else "❌ No"
                    )

                # ── Historial de ranking entre cargas ────────────────────
                _RANK_HISTORY_KEY = "dd_rank_history"
                if _RANK_HISTORY_KEY not in st.session_state:
                    st.session_state[_RANK_HISTORY_KEY] = []

                rr_kw_col = "Search Term" if "Search Term" in df_rr.columns else (
                    "Keyword Phrase" if "Keyword Phrase" in df_rr.columns else None
                )
                rr_rank_cols = [c for c in df_rr.columns if "Rank" in c and "Actual" in c]
                if not rr_rank_cols and "Median Rank" in df_rr.columns:
                    rr_rank_cols = ["Median Rank"]

                # Cross-upload history is for files only: over the API the history
                # is already server-side (the date range is a parameter).
                if rr_source_name and rr_kw_col and rr_rank_cols:
                    rr_rank_col = rr_rank_cols[0]
                    existing_names = [s["filename"] for s in st.session_state[_RANK_HISTORY_KEY]]
                    if rr_source_name not in existing_names:
                        st.session_state[_RANK_HISTORY_KEY].append({
                            "fecha": datetime.now().strftime("%Y-%m-%d %H:%M"),
                            "filename": rr_source_name,
                            "data": df_rr[[rr_kw_col, rr_rank_col]].copy().rename(
                                columns={rr_rank_col: "Rank"}
                            ),
                        })
                        if len(st.session_state[_RANK_HISTORY_KEY]) > 5:
                            st.session_state[_RANK_HISTORY_KEY].pop(0)

                    history = st.session_state[_RANK_HISTORY_KEY]
                    if len(history) >= 2:
                        st.markdown("---")
                        st.markdown("#### 📊 Evolución de ranking entre cargas")
                        prev_snap = history[-2]["data"]
                        curr_snap = history[-1]["data"]

                        df_delta = pd.merge(
                            prev_snap, curr_snap,
                            on=rr_kw_col, how="outer", suffixes=("_prev", "_curr"),
                        )
                        df_delta["Delta"] = df_delta["Rank_prev"] - df_delta["Rank_curr"]

                        def _trend_label(d):
                            if pd.isna(d):
                                return "🆕 Nuevo"
                            if d > 0:
                                return "🟢 Subió"
                            if d < 0:
                                return "🔴 Bajó"
                            return "→ Igual"

                        df_delta["Cambio"] = df_delta["Delta"].apply(_trend_label)

                        n_subio = (df_delta["Delta"] > 0).sum()
                        n_bajo = (df_delta["Delta"] < 0).sum()
                        avg_delta = df_delta["Delta"].mean()

                        rk1, rk2, rk3 = st.columns(3)
                        with rk1:
                            st.markdown(kpi_card("Subieron", str(n_subio)), unsafe_allow_html=True)
                        with rk2:
                            st.markdown(kpi_card("Bajaron", str(n_bajo)), unsafe_allow_html=True)
                        with rk3:
                            delta_str = f"{avg_delta:+.1f} pos" if pd.notna(avg_delta) else "—"
                            st.markdown(kpi_card("Delta promedio", delta_str), unsafe_allow_html=True)

                        st.caption(
                            f"Comparando: {history[-2]['filename']} vs {history[-1]['filename']}"
                        )
                        st.dataframe(
                            df_delta.sort_values("Delta", ascending=False, na_position="last"),
                            use_container_width=True, height=400,
                        )
                        st.info(
                            f"📚 {len(history)} snapshots guardados en esta sesión. "
                            "Subí otro archivo Rank Radar para ver la evolución."
                        )
                        st.markdown("---")

                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(kpi_card("Keywords", str(len(df_rr))), unsafe_allow_html=True)
                if "Tendencia" in df_rr.columns:
                    with k2:
                        st.markdown(kpi_card("Mejorando", str((df_rr["Tendencia"] == "↑ Mejorando").sum())), unsafe_allow_html=True)
                    with k3:
                        st.markdown(kpi_card("Cayendo", str((df_rr["Tendencia"] == "↓ Cayendo").sum())), unsafe_allow_html=True)
                if "PPC Activo" in df_rr.columns:
                    with k4:
                        st.markdown(kpi_card("Con PPC", str((df_rr["PPC Activo"] == "✅ Sí").sum())), unsafe_allow_html=True)

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

                def _color_ppc_rr(val):
                    if "Sí" in str(val):
                        return "background-color: #E8F5E9"
                    if "No" in str(val):
                        return "background-color: #FFF8E1"
                    return ""

                styled_rr = df_rr_show.style
                if "Tendencia" in df_rr_show.columns:
                    styled_rr = styled_rr.map(_color_trend, subset=["Tendencia"])
                if "PPC Activo" in df_rr_show.columns:
                    styled_rr = styled_rr.map(_color_ppc_rr, subset=["PPC Activo"])
                st.dataframe(styled_rr, use_container_width=True, height=min(38 + 35 * len(df_rr_show), 600))

                if date_cols_rr and "Search Term" in df_rr.columns:
                    st.markdown("---")
                    st.markdown("#### 📈 Ranking diario (top keywords)")
                    chart_candidates = df_rr.nlargest(20, "SV") if "SV" in df_rr.columns else df_rr.head(20)
                    available_terms = chart_candidates["Search Term"].dropna().unique().tolist()[:20]
                    selected_terms = st.multiselect(
                        "Keywords para el gráfico", options=available_terms,
                        default=available_terms[:5], key="dd_rr_chart_kws",
                    )
                    if selected_terms:
                        chart_data = df_rr[df_rr["Search Term"].isin(selected_terms)][
                            ["Search Term"] + [d for d in date_cols_rr if d in df_rr.columns]
                        ].set_index("Search Term").T
                        chart_data.index.name = "Date"
                        st.line_chart(chart_data, use_container_width=True)

                if "PPC Activo" in df_rr.columns:
                    st.markdown("---")
                    st.markdown("#### 🎯 PPC Coverage")
                    n_with_ppc = (df_rr["PPC Activo"] == "✅ Sí").sum()
                    n_without_ppc = (df_rr["PPC Activo"] == "❌ No").sum()
                    pc1, pc2 = st.columns(2)
                    with pc1:
                        st.markdown(kpi_card("Con PPC activo", str(n_with_ppc)), unsafe_allow_html=True)
                    with pc2:
                        st.markdown(kpi_card("Sin PPC (oportunidades)", str(n_without_ppc)), unsafe_allow_html=True)
                    if n_without_ppc > 0:
                        with st.expander(f"Ver {n_without_ppc} keywords sin PPC"):
                            no_ppc = df_rr[df_rr["PPC Activo"] == "❌ No"]
                            no_ppc_cols = [c for c in ["Search Term", "SV", "Relevance", "Rank Actual", "Tendencia"] if c in no_ppc.columns]
                            st.dataframe(
                                no_ppc[no_ppc_cols].sort_values("SV", ascending=False) if "SV" in no_ppc.columns else no_ppc[no_ppc_cols],
                                use_container_width=True, hide_index=True,
                            )

                st.markdown("---")
                buf_rr = io.BytesIO()
                export_cols = [c for c in df_rr.columns if c not in date_cols_rr]
                recent_dates = date_cols_rr[-7:] if len(date_cols_rr) >= 7 else date_cols_rr
                export_cols += [d for d in recent_dates if d in df_rr.columns]
                df_rr[[c for c in export_cols if c in df_rr.columns]].to_excel(buf_rr, index=False)
                st.download_button(
                    f"⬇️ Exportar Rank Radar ({len(df_rr)} keywords)",
                    data=buf_rr.getvalue(), file_name="datadive_rank_radar.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_rr_dl",
                )

    # ══════════════════════════════════════════════════════════════════
    # TAB 4 — Ranking Volatility + PPC Impression Share
    # ══════════════════════════════════════════════════════════════════
    with tab4:
        st.subheader("📊 Ranking Volatility + PPC Impression Share")
        st.caption("Cruzá el Rank Radar (ranking orgánico diario) con SQP (impression share) para detectar riesgos y oportunidades.")

        df_v = None
        date_cols_v = []
        if fuente == "API DataDive":
            rr_sel_v = st.session_state.get("dd_rr_api_sel")
            if rr_sel_v:
                try:
                    df_v, date_cols_v, _ = _api_rank_radar(*rr_sel_v)
                    st.caption("Usando el rank radar traído en el tab Rank Radar "
                               "· vía API DataDive")
                except dd_api.DataDiveError as e:
                    st.error(str(e))
            else:
                st.caption("Traé primero un rank radar en el tab Rank Radar.")
            file_sqp_v = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"],
                                          key="dd_vol_sqp")
        else:
            vc1, vc2 = st.columns(2)
            with vc1:
                file_rr_v = st.file_uploader("Rank Radar (.xlsx)", type=["xlsx"], key="dd_vol_rr")
            with vc2:
                file_sqp_v = st.file_uploader("SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="dd_vol_sqp")
            if file_rr_v:
                parsed_v = _parse_upload(_parse_rank_radar, file_rr_v, "Rank Radar")
                if parsed_v is not None:
                    df_v, date_cols_v, _ = parsed_v

        if df_v is None:
            st.markdown(
                "<div style='text-align:center;padding:3rem 1rem;border:2px dashed #DDD;"
                "border-radius:12px;margin:1rem 0;'>"
                "<div style='font-size:2.5rem;margin-bottom:0.5rem;'>📂</div>"
                "<div style='font-size:0.95rem;color:#666;font-weight:600;'>Subí el Rank Radar de DataDive — o traelo por API en el tab Rank Radar — y opcionalmente el SQP de Amazon.</div>"
                "<div style='font-size:0.78rem;color:#999;margin-top:0.3rem;'>"
                "Arrastrá o hacé click en el uploader de arriba</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            if df_v.empty:
                st.warning("No se pudieron extraer datos del Rank Radar.")
            else:
                # ── Parse SQP if provided ────────────────────────────
                sqp_is = {}  # keyword_lower -> impression share %
                if file_sqp_v:
                    df_sqp_v = read_sqp(file_sqp_v)
                    sqp_query_col = next((c for c in df_sqp_v.columns if "search query" in c.lower()), None)
                    sqp_is_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "brand" in c.lower() and "share" in c.lower()), None)
                    if not sqp_is_col:
                        # Try count-based: Brand / Total
                        imp_total_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "total" in c.lower() and "count" in c.lower()), None)
                        imp_brand_col = next((c for c in df_sqp_v.columns if "impression" in c.lower() and "brand" in c.lower() and "count" in c.lower()), None)
                        if imp_total_col and imp_brand_col and sqp_query_col:
                            df_sqp_v[imp_total_col] = pd.to_numeric(df_sqp_v[imp_total_col], errors="coerce").fillna(0)
                            df_sqp_v[imp_brand_col] = pd.to_numeric(df_sqp_v[imp_brand_col], errors="coerce").fillna(0)
                            for _, r in df_sqp_v.iterrows():
                                q = str(r[sqp_query_col]).strip().lower()
                                t = r[imp_total_col]
                                b = r[imp_brand_col]
                                if t > 0:
                                    sqp_is[q] = round(b / t * 100, 1)
                    elif sqp_query_col and sqp_is_col:
                        df_sqp_v[sqp_is_col] = pd.to_numeric(df_sqp_v[sqp_is_col], errors="coerce").fillna(0)
                        for _, r in df_sqp_v.iterrows():
                            q = str(r[sqp_query_col]).strip().lower()
                            sqp_is[q] = round(r[sqp_is_col], 1)
                    if sqp_is:
                        st.success(f"✅ SQP cargado — {len(sqp_is)} queries con impression share")

                # ── Volatility calculation ────────────────────────────
                date_cols_available = [d for d in date_cols_v if d in df_v.columns]
                if len(date_cols_available) < 3:
                    st.warning("Se necesitan al menos 3 días de ranking para calcular volatilidad.")
                else:
                    st.success(f"✅ {len(df_v)} keywords · {len(date_cols_available)} días de datos")

                    ppc_cols_v = ["PPC Exact", "PPC Phrase", "PPC Broad", "PPC Auto"]
                    ppc_avail_v = [c for c in ppc_cols_v if c in df_v.columns]

                    rows_vol = []
                    for _, row in df_v.iterrows():
                        term = str(row.get("Search Term", "")).strip()
                        if not term or term.lower() == "nan":
                            continue

                        ranks = [row[d] for d in date_cols_available if pd.notna(row.get(d))]
                        ranks_numeric = [r for r in ranks if isinstance(r, (int, float)) and r > 0]

                        if not ranks_numeric:
                            continue

                        std_val = float(np.std(ranks_numeric)) if len(ranks_numeric) >= 2 else 0
                        current_rank = ranks_numeric[-1] if ranks_numeric else None
                        avg_rank = sum(ranks_numeric) / len(ranks_numeric)

                        if std_val < 2:
                            volatility = "🟢 ESTABLE"
                        elif std_val <= 5:
                            volatility = "🟡 VOLÁTIL"
                        else:
                            volatility = "🔴 MUY VOLÁTIL"

                        has_ppc = False
                        if ppc_avail_v:
                            ppc_sum = sum(row.get(c, 0) or 0 for c in ppc_avail_v)
                            has_ppc = ppc_sum > 0

                        ppc_is_val = sqp_is.get(term.lower(), None)
                        sv = row.get("SV", 0)
                        sv = sv if pd.notna(sv) else 0

                        # Flags
                        flag = ""
                        if "VOLÁTIL" in volatility and not has_ppc:
                            flag = "⚠️ RIESGO — volátil sin PPC"
                        elif "ESTABLE" in volatility and current_rank and current_rank <= 10 and has_ppc:
                            flag = "💰 OPORTUNIDAD — estable top 10 con PPC activo"

                        rows_vol.append({
                            "Keyword": term,
                            "SV": int(sv),
                            "Rank Actual": int(current_rank) if current_rank else None,
                            "Avg Rank": round(avg_rank, 1),
                            "Std Dev": round(std_val, 2),
                            "Volatilidad": volatility,
                            "PPC Activo": "✅" if has_ppc else "❌",
                            "PPC IS %": ppc_is_val,
                            "Flag": flag,
                        })

                    if not rows_vol:
                        st.info("No hay keywords con datos de ranking suficientes.")
                    else:
                        df_vol = pd.DataFrame(rows_vol).sort_values("SV", ascending=False).reset_index(drop=True)

                        # KPIs
                        n_risk = (df_vol["Flag"].str.contains("RIESGO", na=False)).sum()
                        n_opp = (df_vol["Flag"].str.contains("OPORTUNIDAD", na=False)).sum()
                        vk1, vk2, vk3, vk4 = st.columns(4)
                        with vk1:
                            st.markdown(kpi_card("Keywords analizadas", str(len(df_vol))), unsafe_allow_html=True)
                        with vk2:
                            st.markdown(kpi_card("Estables", str((df_vol["Volatilidad"] == "🟢 ESTABLE").sum())), unsafe_allow_html=True)
                        with vk3:
                            st.markdown(kpi_card("Muy volátiles", str((df_vol["Volatilidad"] == "🔴 MUY VOLÁTIL").sum())), unsafe_allow_html=True)
                        with vk4:
                            st.markdown(kpi_card("Riesgos / Oportunidades", f"{n_risk} / {n_opp}"), unsafe_allow_html=True)

                        # Filter
                        vol_filter = st.multiselect(
                            "Filtrar por volatilidad",
                            options=["🟢 ESTABLE", "🟡 VOLÁTIL", "🔴 MUY VOLÁTIL"],
                            default=["🟡 VOLÁTIL", "🔴 MUY VOLÁTIL"],
                            key="dd_vol_filter",
                        )
                        df_vol_show = df_vol[df_vol["Volatilidad"].isin(vol_filter)] if vol_filter else df_vol

                        def _color_vol(val):
                            if "ESTABLE" in str(val):
                                return "background-color: #E8F5E9; color: #1B5E20"
                            if "MUY VOLÁTIL" in str(val):
                                return "background-color: #FFEBEE; color: #B71C1C"
                            if "VOLÁTIL" in str(val):
                                return "background-color: #FFF8E1; color: #F57F17"
                            return ""

                        def _color_flag(val):
                            if "RIESGO" in str(val):
                                return "background-color: #FFEBEE; color: #B71C1C"
                            if "OPORTUNIDAD" in str(val):
                                return "background-color: #E8F5E9; color: #1B5E20"
                            return ""

                        styled_vol = df_vol_show.style.map(_color_vol, subset=["Volatilidad"])
                        if "Flag" in df_vol_show.columns:
                            styled_vol = styled_vol.map(_color_flag, subset=["Flag"])
                        st.dataframe(styled_vol, use_container_width=True, height=min(38 + 35 * len(df_vol_show), 600))

                        # Export
                        st.markdown("---")
                        buf_vol = io.BytesIO()
                        df_vol.to_excel(buf_vol, index=False)
                        st.download_button(
                            f"⬇️ Exportar Ranking Volatility ({len(df_vol)} keywords)",
                            data=buf_vol.getvalue(),
                            file_name="datadive_ranking_volatility.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                            key="dd_vol_dl",
                        )

    # ══════════════════════════════════════════════════════════════════
    # TAB 5 — Competitor Intelligence
    # ══════════════════════════════════════════════════════════════════
    with tab5:
        st.subheader("🏆 Competitor Intelligence — Vista Unificada")
        st.caption(
            "Subí tu MKL + el de un competidor para comparación directa. "
            "Opcionalmente agregá Cerebro de H10."
        )

        df_my = None
        df_comp = None
        if fuente == "API DataDive":
            if not api_niches_by_id:
                st.caption("Cargá la lista de niches en el tab MKL Keywords "
                           "(Fuente → API DataDive).")
            else:
                col_n1, col_n2 = st.columns(2)
                ci_my_id = col_n1.selectbox(
                    "Tu niche", options=list(api_niches_by_id),
                    format_func=_niche_label, key="dd_ci_my_niche")
                ci_comp_id = col_n2.selectbox(
                    "Niche competidor", options=list(api_niches_by_id),
                    format_func=_niche_label, key="dd_ci_comp_niche")
                if st.button("Traer ambos de DataDive", key="dd_ci_fetch", type="primary"):
                    st.session_state["dd_ci_api_pair"] = (ci_my_id, ci_comp_id)
                ci_pair = st.session_state.get("dd_ci_api_pair")
                if ci_pair and all(p in api_niches_by_id for p in ci_pair):
                    try:
                        df_my, _, _ = _api_mkl(ci_pair[0])
                        df_comp, _, _ = _api_mkl(ci_pair[1])
                        st.caption(f"{_niche_label(ci_pair[0])} vs "
                                   f"{_niche_label(ci_pair[1])} · vía API DataDive")
                    except dd_api.DataDiveError as e:
                        st.error(str(e))
            h10_file = st.file_uploader(
                "Cerebro H10 del competidor (opcional)", type=["xlsx"], key="dd_ci_h10",
            )
        else:
            col_u1, col_u2 = st.columns(2)
            with col_u1:
                my_mkl = st.file_uploader("Tu MKL Keywords (.xlsx)", type=["xlsx"], key="dd_ci_my_mkl")
            with col_u2:
                comp_mkl = st.file_uploader("MKL Competidor (.xlsx)", type=["xlsx"], key="dd_ci_comp_mkl")

            h10_file = st.file_uploader(
                "Cerebro H10 del competidor (opcional)", type=["xlsx"], key="dd_ci_h10",
            )

            if my_mkl and comp_mkl:
                parsed_my_ci = _parse_upload(_parse_mkl, my_mkl, "MKL Keywords")
                parsed_comp_ci = _parse_upload(_parse_mkl, comp_mkl, "MKL Keywords")
                if parsed_my_ci is not None and parsed_comp_ci is not None:
                    # parse_mkl returns (df, asins); only the df is used here
                    df_my, _ = parsed_my_ci
                    df_comp, _ = parsed_comp_ci

        if df_my is None or df_comp is None:
            st.markdown(
                "<div style='border:2px dashed #FFD9B3;border-radius:12px;padding:2rem;"
                "text-align:center;background:#FFF3E0;margin-top:1rem;'>"
                "<div style='font-size:1.5rem;'>🏆</div>"
                "<div style='font-weight:600;margin-top:0.5rem;'>Subí ambos MKL — o traé dos niches por API — para comparar</div>"
                "<div style='font-size:0.82rem;color:#888;margin-top:0.25rem;'>"
                "DataDive → Niche → Keywords → Export para tu ASIN y el competidor</div>"
                "</div>",
                unsafe_allow_html=True,
            )
        else:
            if df_my.empty or df_comp.empty:
                st.error("❌ No se pudo parsear uno de los MKL. Verificá el formato.")
            else:
                # Detect keyword column
                kw_col = "Search Term"
                if kw_col not in df_my.columns:
                    for c in df_my.columns:
                        if "keyword" in c.lower() or "search" in c.lower() or "term" in c.lower():
                            kw_col = c
                            break

                # Merge outer
                df_merged = pd.merge(
                    df_my, df_comp,
                    on=kw_col, how="outer",
                    suffixes=("_mine", "_comp"),
                    indicator=True,
                )

                # Detect rank columns
                rank_cols_mine = [c for c in df_merged.columns if "rank" in c.lower() and "_mine" in c.lower()]
                rank_cols_comp = [c for c in df_merged.columns if "rank" in c.lower() and "_comp" in c.lower()]
                rank_mine = rank_cols_mine[0] if rank_cols_mine else None
                rank_comp = rank_cols_comp[0] if rank_cols_comp else None

                # SV columns
                sv_cols_mine = [c for c in df_merged.columns if "sv" in c.lower() and "_mine" in c.lower()]
                sv_cols_comp = [c for c in df_merged.columns if "sv" in c.lower() and "_comp" in c.lower()]
                sv_mine = sv_cols_mine[0] if sv_cols_mine else None
                sv_comp = sv_cols_comp[0] if sv_cols_comp else None

                # Classify gap
                def _classify_gap(row):
                    # The MKL shape has no "rank" columns (ranks are per ASIN):
                    # without them the outer join itself decides presence in each
                    # niche.
                    if not rank_mine or not rank_comp:
                        side = row.get("_merge")
                        if side == "both":
                            return "🤝 Ambos rankean"
                        if side == "left_only":
                            return "✅ Solo yo"
                        return "🔴 Solo competidor"
                    has_mine = pd.notna(row.get(rank_mine)) and row.get(rank_mine, 0) > 0
                    has_comp = pd.notna(row.get(rank_comp)) and row.get(rank_comp, 0) > 0
                    if has_mine and has_comp:
                        return "🤝 Ambos rankean"
                    elif has_mine and not has_comp:
                        return "✅ Solo yo"
                    elif not has_mine and has_comp:
                        return "🔴 Solo competidor"
                    return "⚫ Ninguno"

                df_merged["Gap"] = df_merged.apply(_classify_gap, axis=1)
                df_merged = df_merged.drop(columns=["_merge"])

                # If H10 Cerebro provided, add extra columns
                if h10_file:
                    try:
                        df_h10 = pd.read_excel(io.BytesIO(h10_file.getvalue()))
                        df_h10.columns = df_h10.columns.str.strip()
                        h10_kw_col = None
                        for c in df_h10.columns:
                            if "keyword" in c.lower():
                                h10_kw_col = c
                                break
                        if h10_kw_col:
                            h10_cols_to_add = []
                            for c in ["Search Volume", "Organic Rank", "Sponsored Rank"]:
                                if c in df_h10.columns:
                                    h10_cols_to_add.append(c)
                            if h10_cols_to_add:
                                df_h10_slim = df_h10[[h10_kw_col] + h10_cols_to_add].copy()
                                df_h10_slim = df_h10_slim.rename(columns={
                                    h10_kw_col: kw_col,
                                    **{c: f"H10_{c}" for c in h10_cols_to_add},
                                })
                                df_merged = pd.merge(df_merged, df_h10_slim, on=kw_col, how="left")
                                st.success(f"✅ Cerebro H10 integrado — {len(df_h10_slim)} keywords cruzadas")
                    except Exception as e:
                        st.warning(f"⚠️ Error procesando Cerebro H10: {e}")

                # KPI cards
                gap_counts = df_merged["Gap"].value_counts()
                k1, k2, k3, k4 = st.columns(4)
                with k1:
                    st.markdown(
                        kpi_card("Ambos rankean", str(gap_counts.get("🤝 Ambos rankean", 0))),
                        unsafe_allow_html=True,
                    )
                with k2:
                    st.markdown(
                        kpi_card("Solo yo", str(gap_counts.get("✅ Solo yo", 0))),
                        unsafe_allow_html=True,
                    )
                with k3:
                    st.markdown(
                        kpi_card("Solo competidor", str(gap_counts.get("🔴 Solo competidor", 0))),
                        unsafe_allow_html=True,
                    )
                with k4:
                    st.markdown(
                        kpi_card("Total keywords", str(len(df_merged))),
                        unsafe_allow_html=True,
                    )

                # Filter by gap type
                gap_options = sorted(df_merged["Gap"].unique().tolist())
                gap_filter = st.multiselect(
                    "Filtrar por gap",
                    options=gap_options,
                    default=[o for o in gap_options if o == "🔴 Solo competidor"],
                    key="dd_ci_gap_filter",
                )

                df_show = df_merged[df_merged["Gap"].isin(gap_filter)] if gap_filter else df_merged

                # Color coding
                def _color_gap(val):
                    if "Solo competidor" in str(val):
                        return "background:#FFEBEE;color:#B71C1C"
                    if "Solo yo" in str(val):
                        return "background:#E8F5E9;color:#1B5E20"
                    if "Ambos" in str(val):
                        return "background:#FFF8E1;color:#F57F17"
                    return "background:#F5F5F5;color:#888"

                styled_ci = df_show.reset_index(drop=True).style.map(_color_gap, subset=["Gap"])
                st.dataframe(styled_ci, use_container_width=True, height=500)

                # Export
                st.markdown("---")
                buf_ci = io.BytesIO()
                df_merged.to_excel(buf_ci, index=False)
                st.download_button(
                    f"⬇️ Exportar Competitor Intel ({len(df_merged)} keywords)",
                    data=buf_ci.getvalue(),
                    file_name="competitor_intelligence.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="dd_ci_dl",
                )

    # Outside st.tabs so the bubble shows on every tab of the module.
    if ai_analysis is not None:
        from core import ai_tab
        ai_tab.mount_analysis_chat("datadive", ai_analysis, lang="es",
                                   labels=ai_labels_dd)
