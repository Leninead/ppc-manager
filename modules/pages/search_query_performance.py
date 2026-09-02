import hashlib
import io
import unicodedata

import numpy as np
import streamlit as st
import pandas as pd

from core.helpers import read_sqp, extract_sqp_brand


def _find_col(df, must_contain, must_not_contain=None):
    """Find first column matching all keywords in must_contain, excluding must_not_contain."""
    for c in df.columns:
        cl = c.lower()
        if all(k in cl for k in must_contain):
            if must_not_contain and any(k in cl for k in must_not_contain):
                continue
            return c
    return None


def _to_num(df, col):
    if col and col in df.columns:
        return pd.to_numeric(
            df[col].astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce").fillna(0)
    return pd.Series(0, index=df.index)


def _compute_market_share(df, query_col, precio):
    """Compute market share DataFrame from SQP data. Returns df_ms or None."""
    global_brand_clicks = df["_clk_b"].sum()
    global_brand_purch  = df["_pur_b"].sum()
    global_cvr = (global_brand_purch / global_brand_clicks) if global_brand_clicks > 0 else 0

    rows_ms = []
    for _, row in df.iterrows():
        query = str(row[query_col]).strip()
        imp_t = row["_imp_t"]; imp_b = row["_imp_b"]
        clk_t = row["_clk_t"]; clk_b = row["_clk_b"]
        pur_t = row["_pur_t"]; pur_b = row["_pur_b"]

        if imp_t == 0:
            continue

        is_pct = (imp_b / imp_t * 100) if imp_t > 0 else 0
        cs_pct = (clk_b / clk_t * 100) if clk_t > 0 else 0
        ps_pct = (pur_b / pur_t * 100) if pur_t > 0 else 0

        ctr_own = (clk_b / imp_t) if imp_t > 0 else 0
        cvr_own = (pur_b / clk_b) if clk_b > 0 else global_cvr
        rev_pot = imp_t * ctr_own * cvr_own * precio

        if is_pct > 30:
            estado = "🟢 Dominando"
        elif is_pct >= 10:
            estado = "🟡 Competitivo"
        else:
            estado = "🔴 Oportunidad"

        rows_ms.append({
            "Search Query": query,
            "Total Impressions": int(imp_t),
            "Impression Share %": round(is_pct, 1),
            "Click Share %": round(cs_pct, 1),
            "Purchase Share %": round(ps_pct, 1),
            "Revenue Potencial": round(rev_pot, 2),
            "Estado": estado,
        })

    if not rows_ms:
        return None
    return pd.DataFrame(rows_ms).sort_values("Revenue Potencial", ascending=False)


def _compute_gaps(df, query_col):
    """Compute gap analysis DataFrame from SQP data. Returns df_gap or None."""
    gaps = []
    for _, row in df.iterrows():
        query = str(row[query_col]).strip()
        imp_t = row["_imp_t"]; imp_b = row["_imp_b"]
        clk_b = row["_clk_b"]
        pur_t = row["_pur_t"]; pur_b = row["_pur_b"]

        is_pct     = (imp_b / imp_t * 100) if imp_t > 0 else 0
        market_cvr = (pur_t / imp_t * 100)  if imp_t > 0 else 0
        brand_cvr  = (pur_b / imp_b * 100)  if imp_b > 0 else 0

        matched = []

        # GAP 1 — No aparecés
        if imp_t > 1000 and imp_b == 0:
            matched.append(("🚫 No aparecés — agregar como keyword", "Alta"))

        # GAP 2 — Mercado convierte mejor
        if imp_b > 0 and market_cvr > 0 and brand_cvr > 0:
            if market_cvr > brand_cvr * 1.5:
                matched.append(("⚠️ Mercado convierte mejor — revisar listing o bid", "Media"))

        # GAP 3 — IS muy bajo en query con volumen
        if is_pct < 5 and imp_t > 2000 and imp_b > 0:
            matched.append(("📉 IS muy bajo — escalar bid", "Media"))

        if matched:
            best = min(matched, key=lambda x: 0 if x[1] == "Alta" else 1)
            all_labels = " | ".join(m[0] for m in matched)
            gaps.append({
                "Search Query": query,
                "Total Impressions": int(imp_t),
                "Brand IS%": round(is_pct, 1),
                "Market CVR%": round(market_cvr, 2),
                "Brand CVR%": round(brand_cvr, 2),
                "Tipo de Gap": all_labels,
                "Prioridad": best[1],
                "Acción sugerida": best[0],
            })

    if not gaps:
        return None
    df_gap = pd.DataFrame(gaps)
    prio_order = {"Alta": 0, "Media": 1}
    df_gap["_sort"] = df_gap["Prioridad"].map(prio_order)
    return df_gap.sort_values(["_sort", "Total Impressions"], ascending=[True, False]).drop(columns=["_sort"])


# AI-only signal layer; UI tabs never read these. Spec + thresholds rationale:
# notes/modules/m3-sqp-ai-signals-spec.md.
_DEFENSE_FLOOR = 80.0
_TOP_ROWS = 40
_GATE_MIN_BRAND_CLICKS = 10
_GATE_MIN_MARKET_PURCHASES = 5
_GEM_RATIO = 1.3
_GEM_MIN_BRAND_PURCHASES = 2
_AUTODILUTION_SHARE = 40.0
_INTEGRITY_TOL_PTS = 0.6
_SPEED_TIER_MIN_CLICKS = 20
# Brand View only lists queries the brand touched, so imp_b==0 barely exists;
# under 1% share with no own purchases the brand is effectively absent.
_INVISIBLE_SHARE = 1.0
_TIER_TARGET_SHARE = {"HEAD": 10.0, "TORSO": 15.0, "LONG_TAIL": 20.0, "SIN_DATO": 15.0}


def _norm_query(s):
    s = unicodedata.normalize("NFKD", str(s))
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.lower().split())


def _safe_div(num, den):
    """num/den with NaN wherever den is 0/NaN — never inf, never silent 0."""
    den = den.astype(float).mask(den == 0)
    return (num.astype(float) / den).astype(float)


def _to_num_na(df, col):
    """Like _to_num but NaN-preserving: a missing column is unknown, not 0."""
    if col and col in df.columns:
        return pd.to_numeric(
            df[col].astype(str).str.replace(r"[MX$,%]", "", regex=True).str.replace(",", ""),
            errors="coerce")
    return pd.Series(np.nan, index=df.index, dtype="float64")


def _price_band(gap):
    if pd.isna(gap):
        return "SIN_DATO_PRECIO"
    if gap <= -15:
        return "DESCUENTO_AGRESIVO"
    if gap <= -5:
        return "VALUE"
    if gap < 5:
        return "PARIDAD"
    if gap <= 25:
        return "PREMIUM_NO_VERIFICADO"
    return "PREMIUM_RIESGO"


def _minmax_norm(s):
    s = s.astype(float).fillna(0)
    rng = s.max() - s.min()
    if not rng or pd.isna(rng):
        return pd.Series(0.0, index=s.index)
    return (s - s.min()) / rng


def _compute_funnel_signals(df, query_col, brand_terms):
    """Per-query engineered signals for the AI payload. Pure — does not mutate df.

    Returns (signals_df sorted by priority desc, thresholds dict) or
    (None, None) when the export lacks query + impression columns.
    Counts are ground truth (shares recomputed from them); the export's own
    Brand Share % columns act only as integrity oracle.
    """
    imp_t_c = _find_col(df, ["impression", "total"], ["share", "rate"])
    imp_b_c = _find_col(df, ["impression", "brand"], ["share", "rate"])
    if not (query_col and imp_t_c and imp_b_c):
        return None, None

    def cnt(stage_kw, side_kw):
        return _to_num(df, _find_col(df, [stage_kw, side_kw],
                                     ["share", "rate", "price", "shipping"]))

    imp_t, imp_b = cnt("impression", "total"), cnt("impression", "brand")
    clk_t, clk_b = cnt("click", "total"), cnt("click", "brand")
    cart_t, cart_b = cnt("cart add", "total"), cnt("cart add", "brand")
    pur_t, pur_b = cnt("purchase", "total"), cnt("purchase", "brand")

    imp_share = _safe_div(imp_b, imp_t) * 100
    click_share = _safe_div(clk_b, clk_t) * 100
    cart_share = _safe_div(cart_b, cart_t) * 100
    purchase_share = _safe_div(pur_b, pur_t) * 100

    # Integrity oracle: Amazon's own precomputed % vs our recomputation.
    integ_ok = pd.Series(True, index=df.index)
    for ours, stage_kw in [(imp_share, "impression"), (click_share, "click"),
                           (cart_share, "cart add"), (purchase_share, "purchase")]:
        exp = _to_num_na(df, _find_col(df, [stage_kw, "brand", "share"]))
        both = ours.notna() & exp.notna()
        integ_ok &= ~(both & ((ours - exp).abs() > _INTEGRITY_TOL_PTS))

    d1, d2, d3 = click_share - imp_share, cart_share - click_share, purchase_share - cart_share
    p25_d1, p25_d2, p25_d3 = d1.quantile(0.25), d2.quantile(0.25), d3.quantile(0.25)
    m1 = (d1 < 0) & (d1 < p25_d1)
    m2 = (d2 < 0) & (d2 < p25_d2)
    m3 = (d3 < 0) & (d3 < p25_d3)
    leak_stage = np.select([m1.fillna(False), m2.fillna(False), m3.fillna(False)],
                           ["ctr", "pdp", "checkout"], default="")

    # Brand vs market-without-the-brand: index < 1 = the problem is OURS.
    ctr_index = _safe_div(_safe_div(clk_b, imp_b), _safe_div(clk_t - clk_b, imp_t - imp_b))
    cart_index = _safe_div(_safe_div(cart_b, clk_b), _safe_div(cart_t - cart_b, clk_t - clk_b))
    purchase_index = _safe_div(_safe_div(pur_b, cart_b), _safe_div(pur_t - pur_b, cart_t - cart_b))
    idx_at_leak = pd.Series(np.select(
        [leak_stage == "ctr", leak_stage == "pdp", leak_stage == "checkout"],
        [ctr_index, cart_index, purchase_index], default=np.nan), index=df.index)
    leak_is_own = idx_at_leak < 1  # NaN comparison yields False: unknown is never "ours"

    def gap(stage_kw):
        mkt = _to_num_na(df, _find_col(df, [stage_kw, "price"], ["brand"]))
        own = _to_num_na(df, _find_col(df, [stage_kw, "brand", "price"]))
        return _safe_div(own - mkt, mkt) * 100

    gap_click, gap_cart, gap_purchase = gap("click"), gap("cart add"), gap("purchase")
    price_trend = gap_purchase - gap_click
    gap_base = gap_purchase.fillna(gap_click)
    price_band = gap_base.map(_price_band)
    price_self_diluted = (purchase_share > _AUTODILUTION_SHARE).fillna(False)

    queries = df[query_col].astype(str).str.strip()
    terms = [_norm_query(t) for t in (brand_terms or []) if str(t).strip()]
    qnorm = queries.map(_norm_query)
    is_brand = qnorm.map(lambda q: any(t in q for t in terms)) if terms \
        else pd.Series(False, index=df.index)

    breach_stage = pd.Series(np.select(
        [imp_share < _DEFENSE_FLOOR, click_share < _DEFENSE_FLOOR,
         cart_share < _DEFENSE_FLOOR, purchase_share < _DEFENSE_FLOOR],
        ["impresiones", "clicks", "cart adds", "purchases"], default=""),
        index=df.index).where(is_brand, "")
    breach_share = pd.Series(np.select(
        [imp_share < _DEFENSE_FLOOR, click_share < _DEFENSE_FLOOR,
         cart_share < _DEFENSE_FLOOR, purchase_share < _DEFENSE_FLOOR],
        [imp_share, click_share, cart_share, purchase_share], default=np.nan),
        index=df.index).where(is_brand)

    volume = _to_num_na(df, _find_col(df, ["query", "volume"]))
    vol_q90, vol_q50 = volume.quantile(0.90), volume.quantile(0.50)
    volume_tier = pd.Series(np.select(
        [volume.isna(), volume >= vol_q90, volume < vol_q50],
        ["SIN_DATO", "HEAD", "LONG_TAIL"], default="TORSO"), index=df.index)

    gate = (clk_b >= _GATE_MIN_BRAND_CLICKS) & (pur_t >= _GATE_MIN_MARKET_PURCHASES)

    p25_imp_share = imp_share.quantile(0.25)
    hidden_gem = ((purchase_share >= _GEM_RATIO * imp_share)
                  & (imp_share < p25_imp_share)
                  & (pur_b >= _GEM_MIN_BRAND_PURCHASES)
                  & gate).fillna(False)

    pos_pur = pur_t[pur_t > 0]
    p50_market_purchases = pos_pur.quantile(0.50) if len(pos_pur) else np.nan
    market_buys = (pur_t >= p50_market_purchases).fillna(False) if len(pos_pur) \
        else pd.Series(False, index=df.index)

    is_invisible = ((imp_b == 0)
                    | ((imp_share < _INVISIBLE_SHARE)
                       & (pur_b < _GEM_MIN_BRAND_PURCHASES))).fillna(False)

    share_state = pd.Series(np.select(
        [imp_share > 30, imp_share >= 10],
        ["dominando", "competitivo"], default="oportunidad"), index=df.index)

    target_share = pd.Series(np.where(
        is_brand, _DEFENSE_FLOOR, volume_tier.map(_TIER_TARGET_SHARE)),
        index=df.index).astype(float)
    pur_price = _to_num_na(df, _find_col(df, ["purchase", "price"], ["brand"]))
    opp_usd = ((target_share - purchase_share.fillna(0)).clip(lower=0) / 100
               * pur_t * pur_price).fillna(0).round(2)
    priority = 0.7 * _minmax_norm(opp_usd) + 0.3 * _minmax_norm(volume)

    def ship(stage_kw, tier_kw):
        return _to_num(df, _find_col(df, [stage_kw, tier_kw]))

    clk_same, clk_2d = ship("click", "same day"), ship("click", "2d")
    pur_same, pur_2d = ship("purchase", "same day"), ship("purchase", "2d")
    cvr_same = _safe_div(pur_same, clk_same.mask(clk_same < _SPEED_TIER_MIN_CLICKS))
    cvr_2d = _safe_div(pur_2d, clk_2d.mask(clk_2d < _SPEED_TIER_MIN_CLICKS))
    speed_premium = _safe_div(cvr_same, cvr_2d)

    signals = pd.DataFrame({
        "query": queries, "volume": volume, "volume_tier": volume_tier,
        "imp_t": imp_t.astype(int), "imp_b": imp_b.astype(int),
        "clk_t": clk_t.astype(int), "clk_b": clk_b.astype(int),
        "cart_t": cart_t.astype(int), "cart_b": cart_b.astype(int),
        "pur_t": pur_t.astype(int), "pur_b": pur_b.astype(int),
        "imp_share": imp_share.round(2), "click_share": click_share.round(2),
        "cart_share": cart_share.round(2), "purchase_share": purchase_share.round(2),
        "d1": d1.round(2), "d2": d2.round(2), "d3": d3.round(2),
        "leak_stage": leak_stage, "leak_is_own": leak_is_own,
        "ctr_index": ctr_index.round(2), "cart_index": cart_index.round(2),
        "purchase_index": purchase_index.round(2),
        "gap_click": gap_click.round(1), "gap_cart": gap_cart.round(1),
        "gap_purchase": gap_purchase.round(1), "price_trend": price_trend.round(1),
        "price_band": price_band, "price_self_diluted": price_self_diluted,
        "is_own_brand": is_brand,
        "defense_breach_stage": breach_stage, "defense_breach_share": breach_share.round(1),
        "sufficient_data": gate, "hidden_gem": hidden_gem,
        "is_invisible": is_invisible,
        "market_buys": market_buys, "share_state": share_state,
        "speed_premium": speed_premium.round(2),
        "opp_usd": opp_usd, "priority": priority.round(4),
        "integrity_ok": integ_ok,
    })
    thresholds = {
        "p25_d1": _r2(p25_d1), "p25_d2": _r2(p25_d2), "p25_d3": _r2(p25_d3),
        "p25_imp_share": _r2(p25_imp_share),
        "p50_market_purchases": _r2(p50_market_purchases),
        "vol_q90": _r2(vol_q90), "vol_q50": _r2(vol_q50),
    }
    return signals.sort_values("priority", ascending=False).reset_index(drop=True), thresholds


def _r2(v):
    return None if pd.isna(v) else round(float(v), 2)


def _compute_account_rollup(signals, thresholds):
    """Account-level aggregates + warning pre-flags. The AI never sums anything:
    every number and every warning trigger in the report exists here first."""
    def wshare(b, t):
        tot = signals[t].sum()
        return round(signals[b].sum() / tot * 100, 2) if tot else None

    ws = {"imp": wshare("imp_b", "imp_t"), "click": wshare("clk_b", "clk_t"),
          "cart": wshare("cart_b", "cart_t"), "purchase": wshare("pur_b", "pur_t")}
    stages = ["imp", "click", "cart", "purchase"]
    wd = {f"d_{a}_{b}": round(ws[b] - ws[a], 2)
          if ws[a] is not None and ws[b] is not None else None
          for a, b in zip(stages, stages[1:])}

    gated = signals[signals["sufficient_data"]]
    leaks = gated[gated["leak_stage"] != ""]["leak_stage"]
    dominant_leak = leaks.mode().iloc[0] if len(leaks) else None

    n = len(signals)
    pct = lambda mask: round(float(mask.mean()) * 100, 1) if n else 0.0
    total_opp = float(signals["opp_usd"].sum())
    invisible_rows = signals[signals["is_invisible"]]
    invisible_opp = float(invisible_rows["opp_usd"].sum())
    # Coverage is judged only where the brand shows up: an absent brand is a
    # SIN_VISIBILIDAD diagnosis, not a thin-sample problem.
    brand_present = signals[~signals["is_invisible"]]
    pct_con_datos = (round(float(brand_present["sufficient_data"].mean()) * 100, 1)
                     if len(brand_present) else 0.0)
    gems = signals[signals["hidden_gem"]]
    breaches = signals[signals["defense_breach_stage"] != ""]
    premium_cluster = signals[(signals["price_band"] == "PREMIUM_RIESGO")
                          & signals["leak_stage"].isin(["pdp", "checkout"])
                          & signals["sufficient_data"]]

    tail = signals.iloc[_TOP_ROWS:]
    flags = {
        "DEFENSA_MARCA_ROTA": len(breaches) > 0,
        "GEMAS_OCULTAS": len(gems) > 0,
        "FUGA_CHECKOUT_HEAD_TERM": bool(((gated["volume_tier"] == "HEAD")
                                         & (gated["leak_stage"] == "checkout")).any()),
        "CLUSTER_PREMIUM_RIESGO": len(premium_cluster) >= 3,
        "VOLUMEN_SIN_VISIBILIDAD": total_opp > 0 and invisible_opp > 0.25 * total_opp,
        "COBERTURA_BAJA": pct_con_datos < 50,
        "SIN_DATO_PRECIO_MASIVO": pct(signals["price_band"] == "SIN_DATO_PRECIO") > 40,
        "INTEGRIDAD_EXPORT": pct(~signals["integrity_ok"]) > 2,
    }
    return {
        "n_queries": n,
        "weighted_shares": ws, "weighted_deltas": wd,
        "dominant_leak_stage": dominant_leak,
        "pct_rows_with_data": pct_con_datos,
        "pct_invisible": pct(signals["is_invisible"]),
        "pct_no_price_data": pct(signals["price_band"] == "SIN_DATO_PRECIO"),
        "pct_integrity_ok": pct(signals["integrity_ok"]),
        "total_opp_usd": round(total_opp, 2),
        "invisible": {"rows": len(invisible_rows), "opp_usd": round(invisible_opp, 2)},
        "gems": {"rows": len(gems),
                  "top_queries": gems.nlargest(5, "opp_usd")["query"].tolist()},
        "defense_broken": {"rows": len(breaches),
                         "queries": breaches["query"].head(5).tolist()},
        "premium_risk_leaking": len(premium_cluster),
        "tail": {"rows": len(tail), "opp_usd": round(float(tail["opp_usd"].sum()), 2),
                 "gems": int(tail["hidden_gem"].sum()),
                 "invisible": int(tail["is_invisible"].sum())},
        "thresholds": thresholds,
        "pre_flags": flags,
    }


# SQP-only UI strings; everything shared comes from core/ai_tab's label base.
_SQP_LABELS = {
    "es": {"chat": "Análisis IA — SQP",
           "caption": "Diagnóstico de funnel, precio y oportunidad por query, "
                      "generado por IA sobre las señales calculadas",
           "disabled": "Análisis IA deshabilitado (AI_ENABLED=0).",
           "no_cols": "Necesitás columnas de Search Query e Impressions "
                      "Total/Brand en el SQP.",
           "no_rows": "El archivo no tiene filas con señales analizables.",
           "brand_terms": "Brand terms (separados por coma)",
           "brand_help": "Definen qué queries son de TU marca: activan el piso "
                         "de defensa y la clasificación BRANDED. Prefill: marca "
                         "detectada en el archivo.",
           "table_title": "Lectura IA por query (top por prioridad)",
           "col_item": "Query"},
    "en": {"chat": "AI Analysis — SQP",
           "caption": "Per-query funnel, price and opportunity diagnosis, "
                      "AI-generated over the computed signals",
           "disabled": "AI analysis disabled (AI_ENABLED=0).",
           "no_cols": "The SQP file needs Search Query and Impressions "
                      "Total/Brand columns.",
           "no_rows": "The file has no analyzable signal rows.",
           "brand_terms": "Brand terms (comma separated)",
           "brand_help": "Define which queries are YOUR brand: they enable the "
                         "defense floor and the BRANDED classification. "
                         "Prefill: brand detected in the file.",
           "table_title": "AI read per query (top by priority)",
           "col_item": "Query"},
}

_BADGE_COLORS = {
    "SIN_VISIBILIDAD": "background-color:#E3F2FD;color:#0D47A1",
    "FUGA_CTR": "background-color:#FFEBEE;color:#9C0006",
    "FUGA_PDP": "background-color:#FFEBEE;color:#9C0006",
    "FUGA_CHECKOUT": "background-color:#FFEBEE;color:#9C0006",
    "MERCADO_DEBIL": "background-color:#F5F5F5;color:#616161",
    "FUNNEL_SANO": "background-color:#E8F5E9;color:#2E7D32",
    "DOMINANTE": "background-color:#E1F5EE;color:#0F6E56",
    "DATOS_INSUFICIENTES": "background-color:#FAFAFA;color:#9E9E9E",
    "ESCALAR_BID": "background-color:#E8F5E9;color:#2E7D32",
    "AGREGAR_EXACT": "background-color:#E8F5E9;color:#2E7D32",
    "DEFENDER_MARCA": "background-color:#FFF3E0;color:#BF360C",
    "ARREGLAR_CREATIVO_SERP": "background-color:#FFF8E1;color:#9C5700",
    "ARREGLAR_PDP": "background-color:#FFF8E1;color:#9C5700",
    "REVISAR_PRECIO_OFERTA": "background-color:#FFF8E1;color:#9C5700",
    "REVISAR_LOGISTICA_BUYBOX": "background-color:#FFF8E1;color:#9C5700",
    "MONITOREAR": "background-color:#F5F5F5;color:#616161",
    "IGNORAR": "background-color:#FAFAFA;color:#9E9E9E",
}


def _share_pill(label, value):
    return f"{label} —" if pd.isna(value) else f"{label} {value}%"


def _sqp_ai_rows(signal_records, opinions):
    """Display rows for core/ai_tab.opinion_table_html.

    Positional row_id join against the SAME records that were serialized into
    the analysis payload — never against a recomputed frame.
    """
    from ai.agents.sqp.context import QUERY_PREFIX, make_ids
    ops = {o.get("row_id"): o for o in opinions}
    rows = []
    for rid, rec in zip(make_ids(QUERY_PREFIX, len(signal_records)),
                        signal_records):
        o = ops.get(rid, {})
        rows.append({
            "item": rec["query"],
            "type_tag": o.get("query_type", ""),
            "metrics": [
                _share_pill("imp", rec["imp_share"]),
                _share_pill("clk", rec["click_share"]),
                _share_pill("cart", rec["cart_share"]),
                _share_pill("pur", rec["purchase_share"]),
                f"opp ${rec['opp_usd']:,.0f}",
            ],
            "badges": [o.get("funnel_diagnosis", ""), o.get("action", "")],
            "confidence": str(o.get("confidence", "")),
            "warning": o.get("warning") or "",
            "reasoning": o.get("reasoning", ""),
        })
    return rows


def _render_sqp_ai_result(result, analysis, signal_records, labels):
    from core import ai_tab
    synthesis = result.get("synthesis") or {}
    opinions = result.get("queries") or []
    n_warnings = sum(1 for o in opinions if o.get("warning"))
    with st.container(border=True):
        head_l, head_r = st.columns([5, 1])
        with head_l:
            st.markdown(ai_tab.ai_chips_html(
                n_warnings,
                f"{len(opinions)} queries · "
                f"{len(synthesis.get('risks', []))} {labels['risks_title'].lower()}",
                analysis.elapsed, labels), unsafe_allow_html=True)
        with head_r:
            with st.popover(labels["copy_btn"], use_container_width=True):
                st.code(synthesis.get("executive_summary", ""), language=None)
        st.markdown(ai_tab.synthesis_html(synthesis, labels),
                    unsafe_allow_html=True)
    st.markdown(ai_tab.opinion_table_html(
        _sqp_ai_rows(signal_records, opinions), labels["table_title"],
        labels, _BADGE_COLORS), unsafe_allow_html=True)


def render():
    st.header("🔍 Search Query Performance")
    st.caption("Datos de rendimiento de búsqueda orgánica exportados desde Amazon Brand Analytics.")
    st.divider()

    with st.expander("❓ ¿Cómo usar este módulo?", expanded=False):
        col1, col2, col3 = st.columns(3)
        with col1:
            st.markdown("**🎯 Para qué sirve**")
            st.caption("Medir market share, detectar gaps y oportunidades orgánicas contra el mercado de Brand Analytics.")
        with col2:
            st.markdown("**📂 Archivo necesario**")
            st.caption("SQP → Brand Analytics → Search Query Performance (.xlsx semanal).")
        with col3:
            st.markdown("**➡️ Siguiente paso**")
            st.caption("Análisis Cruzado STR vs SQP (M4) para generar Plan de Acción.")
        st.markdown("**▶️ Pasos:**")
        st.markdown(
            "1. Subí el SQP\n"
            "2. Confirmá o ingresá la marca detectada\n"
            "3. Revisá Dashboard, Market Share (Dominando/Competitivo/Oportunidad)\n"
            "4. En Gap Analysis detectá queries con alto volumen donde no aparecés\n"
            "5. Descargá tabla de gaps"
        )

    file_sqp = st.file_uploader("Sube tu SQP (.xlsx o .csv)", type=["xlsx", "csv"], key="sqp")
    if not file_sqp:
        return

    df = read_sqp(file_sqp)
    file_sqp.seek(0)
    brand = extract_sqp_brand(file_sqp)
    st.success(f"✅ {len(df)} filas cargadas" + (f" · Marca: **{brand}**" if brand else ""))

    # Auto-detect columns
    query_col    = _find_col(df, ["search query"], ["score", "volume"])
    imp_total    = _find_col(df, ["impression", "total"])
    imp_brand    = _find_col(df, ["impression", "brand"])
    click_total  = _find_col(df, ["click", "total"], ["rate"])
    click_brand  = _find_col(df, ["click", "brand"], ["rate"])
    purch_total  = _find_col(df, ["purchase", "total"], ["rate"])
    purch_brand  = _find_col(df, ["purchase", "brand"], ["rate"])

    # Numeric series
    df["_imp_t"]   = _to_num(df, imp_total)
    df["_imp_b"]   = _to_num(df, imp_brand)
    df["_clk_t"]   = _to_num(df, click_total)
    df["_clk_b"]   = _to_num(df, click_brand)
    df["_pur_t"]   = _to_num(df, purch_total)
    df["_pur_b"]   = _to_num(df, purch_brand)

    # Pre-compute data for tabs 2, 3 and 4
    has_cols = bool(imp_total and imp_brand and query_col)
    df_ms  = None
    df_gap = None
    analysis = None  # AI run; the floating chat mount after the tabs reads it

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Vista General", "📈 Market Share", "🕳️ Gap Analysis", "🤖 Análisis IA",
    ])

    # ── TAB 1: Vista General (código original) ──────────────────────
    with tab1:
        st.dataframe(df, use_container_width=True)

    # ── TAB 2: Market Share ─────────────────────────────────────────
    with tab2:
        st.subheader("📈 Market Share")
        st.caption("Tu share of voice vs el mercado total por search query")

        if not has_cols:
            st.warning("No se encontraron columnas de Impressions Total/Brand o Search Query en el archivo SQP.")
        else:
            precio_sqp = st.number_input("Precio promedio ($)", min_value=1.0, value=30.0, step=1.0, key="sqp_precio")
            df_ms = _compute_market_share(df, query_col, precio_sqp)

            if df_ms is not None:
                n_dom  = (df_ms["Estado"] == "🟢 Dominando").sum()
                n_comp = (df_ms["Estado"] == "🟡 Competitivo").sum()
                n_opp  = (df_ms["Estado"] == "🔴 Oportunidad").sum()
                avg_is = df_ms["Impression Share %"].mean()

                sm1, sm2, sm3, sm4 = st.columns(4)
                sm1.metric("🟢 Dominando", n_dom)
                sm2.metric("🟡 Competitivo", n_comp)
                sm3.metric("🔴 Oportunidad", n_opp)
                sm4.metric("IS promedio", f"{avg_is:.1f}%")

                def _color_estado(val):
                    if "Dominando" in str(val):   return "background-color: #C6EFCE; color: #276221"
                    if "Competitivo" in str(val):  return "background-color: #FFEB9C; color: #9C5700"
                    if "Oportunidad" in str(val):  return "background-color: #FFC7CE; color: #9C0006"
                    return ""

                st.dataframe(
                    df_ms.style.applymap(_color_estado, subset=["Estado"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_ms), 800),
                )

                buf_ms = io.BytesIO()
                df_ms.to_excel(buf_ms, index=False)
                st.download_button(
                    "⬇️ Descargar Market Share (Excel)",
                    data=buf_ms.getvalue(),
                    file_name="sqp_market_share.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="ms_dl",
                )
            else:
                st.info("No hay datos de impresiones para calcular market share.")

    # ── TAB 3: Gap Analysis ─────────────────────────────────────────
    with tab3:
        st.subheader("🕳️ Gap Analysis")
        st.caption("Queries donde el mercado convierte bien pero vos no aparecés o rendís por debajo")

        if not has_cols:
            st.warning("No se encontraron columnas de Impressions o Search Query en el archivo SQP.")
        else:
            df_gap = _compute_gaps(df, query_col)

            if df_gap is not None:
                n_total   = len(df_gap)
                n_no_show = df_gap["Tipo de Gap"].str.contains("No aparecés").sum()
                n_mkt_cvr = df_gap["Tipo de Gap"].str.contains("Mercado convierte").sum()
                n_low_is  = df_gap["Tipo de Gap"].str.contains("IS muy bajo").sum()

                gm1, gm2, gm3, gm4 = st.columns(4)
                gm1.metric("Total gaps", n_total)
                gm2.metric("🚫 No aparecés", n_no_show)
                gm3.metric("⚠️ Mercado > vos", n_mkt_cvr)
                gm4.metric("📉 IS bajo", n_low_is)

                def _color_gap_prio(val):
                    if val == "Alta":  return "background-color: #FFC7CE; color: #9C0006"
                    return "background-color: #FFEB9C; color: #9C5700"

                st.dataframe(
                    df_gap.style.applymap(_color_gap_prio, subset=["Prioridad"]),
                    use_container_width=True,
                    height=min(38 + 35 * len(df_gap), 800),
                )

                buf_gap = io.BytesIO()
                df_gap.to_excel(buf_gap, index=False)
                st.download_button(
                    "⬇️ Descargar Gap Analysis (Excel)",
                    data=buf_gap.getvalue(),
                    file_name="sqp_gap_analysis.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    use_container_width=True, key="gap_dl",
                )
            else:
                st.info("No se encontraron gaps con los criterios actuales.")

    # ── TAB 4: Análisis IA — capa core/ai_tab sobre el agente ai/agents/sqp ──
    with tab4:
        st.subheader("🤖 Análisis IA")
        # Language comes from the app-wide selector in the sidebar (app_lang).
        ai_lang = "en" if st.session_state.get("app_lang") == "English" else "es"
        sqp_labels = _SQP_LABELS.get(ai_lang, _SQP_LABELS["es"])
        st.caption(sqp_labels["caption"])

        from ai.config import AI_ENABLED
        if not AI_ENABLED:
            st.caption(sqp_labels["disabled"])
        elif not has_cols:
            st.info(sqp_labels["no_cols"])
        else:
            from core import ai_tab
            from ai import runtime as ai_runtime
            from ai.agents.sqp.context import SqpData

            brand_terms_raw = st.text_input(
                sqp_labels["brand_terms"], value=brand or "",
                help=sqp_labels["brand_help"], key="sqp_ai_brand_terms",
            )
            ai_brand_terms = [t.strip() for t in brand_terms_raw.split(",") if t.strip()]

            signals, thresholds = _compute_funnel_signals(df, query_col, ai_brand_terms)
            if signals is None or signals.empty:
                st.info(sqp_labels["no_rows"])
            else:
                rollup = _compute_account_rollup(signals, thresholds)
                signal_records = signals.head(_TOP_ROWS).to_dict("records")

                week_col = _find_col(df, ["reporting date"])
                report_week = (str(df[week_col].dropna().iloc[0])
                               if week_col is not None and df[week_col].notna().any()
                               else "no declarada")

                ai_data = SqpData(
                    brand=brand or "no detectada",
                    brand_terms=ai_brand_terms,
                    week=report_week,
                    rollup=rollup,
                    signal_rows=signal_records,
                    language=ai_lang,
                    defense_floor=_DEFENSE_FLOOR,
                )
                ai_labels_sqp = ai_tab.ai_labels(ai_lang, sqp_labels)
                st.markdown(ai_tab.AI_CSS, unsafe_allow_html=True)
                analysis = ai_tab.resolve_analysis(
                    slug="sqp", payload=ai_data,
                    file_signature=hashlib.sha256(file_sqp.getvalue()).hexdigest()[:16],
                    labels=ai_labels_sqp)
                if analysis is not None:
                    # A STALE analysis cites row_ids from ITS payload, not this
                    # rerun's: records are kept per digest so the positional
                    # join never crosses the wrong queries.
                    rec_store = st.session_state.setdefault("sqp_ai_records_store", {})
                    current = ai_runtime.peek("sqp", ai_data)
                    if current is not None and current.digest == analysis.digest:
                        rec_store[analysis.digest] = signal_records
                        for old_digest in list(rec_store)[:-8]:
                            del rec_store[old_digest]
                    render_records = rec_store.get(analysis.digest, signal_records)

                    def _render_result(result, a, _rec=render_records,
                                       _lab=ai_labels_sqp):
                        _render_sqp_ai_result(result, a, _rec, _lab)

                    ai_tab.render_analysis(analysis, slug="sqp",
                                           labels=ai_labels_sqp,
                                           render_result=_render_result)

    # Outside st.tabs so the bubble shows on every tab of the module.
    if analysis is not None:
        from core import ai_tab
        ai_tab.mount_analysis_chat("sqp", analysis, lang=ai_lang,
                                   labels=ai_labels_sqp)
