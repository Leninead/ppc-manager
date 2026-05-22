import pandas as pd

from core.i18n import _I18N


def _kpis(df):
    """Compute aggregate KPI dict from a single-period DataFrame."""
    def s(c):
        return float(pd.to_numeric(df[c], errors="coerce").fillna(0).sum()) if c in df.columns else 0.0
    im, cl, sp, sl, or_ = s("Impressions"), s("Clicks"), s("Spend"), s("Sales"), s("Orders")
    return {
        "Impressions": im,   "Clicks": cl,  "Spend": sp,  "Sales": sl,  "Orders": or_,
        "ACoS": round(sp / sl * 100, 2) if sl > 0 else 0.0,
        "ROAS": round(sl / sp,       2) if sp > 0 else 0.0,
        "CTR":  round(cl / im * 100, 2) if im > 0 else 0.0,
        "CVR":  round(or_ / cl * 100,2) if cl > 0 else 0.0,
        "CPC":  round(sp / cl,       2) if cl > 0 else 0.0,
    }

def _generate_summary(tipo, entity_col, kc, kp=None, per_c="", per_p="", top_rows=None, lang="es"):
    t = _I18N[lang]

    def pct_chg(curr, prev):
        return ((curr - prev) / prev * 100) if prev and prev != 0 else None

    sp, sl, cl, im, or_ = kc["Spend"], kc["Sales"], kc["Clicks"], kc["Impressions"], kc["Orders"]
    acos, roas, ctr, cvr, cpc = kc["ACoS"], kc["ROAS"], kc["CTR"], kc["CVR"], kc["CPC"]
    sep = "=" * 62
    L = [sep, f"  {t['s_title']} \u2014 {tipo.upper()}", sep,
         f"  {t['s_period']} {per_c}"]
    if per_p:
        L.append(f"  {t['s_comparison']} {per_p}")
    L += ["", f"  {t['s_metrics']}",
          f"    {t['s_spend']}  ${sp:>12,.2f}",
          f"    {t['s_sales']}  ${sl:>12,.2f}",
          f"    ACoS:                    {acos:>11.1f}%",
          f"    ROAS:                    {roas:>11.2f}x",
          f"    {t['s_impr']}  {im:>12,.0f}",
          f"    Clicks:                  {cl:>12,.0f}",
          f"    CTR:                     {ctr:>11.2f}%",
          f"    CVR:                     {cvr:>11.2f}%",
          f"    {t['s_cpc']}  ${cpc:>11.2f}", ""]

    if kp:
        sp_p, sl_p, cl_p, im_p = kp["Spend"], kp["Sales"], kp["Clicks"], kp["Impressions"]
        acos_p = kp["ACoS"]
        def fmt_d(curr, prev, inv=False):
            d = pct_chg(curr, prev)
            if d is None: return "  -"
            arrow = "^" if d > 0 else "v"
            good = (d > 0) != inv
            tag = "  OK" if good else "  !!"
            return f"{tag} {arrow} {abs(d):.1f}%"
        acos_delta = acos - acos_p
        L += [f"  {t['s_variation']}",
              f"    {t['s_inv_short']} {fmt_d(sp, sp_p)}",
              f"    {t['s_sal_short']} {fmt_d(sl, sl_p)}",
              f"    Clicks:       {fmt_d(cl, cl_p)}",
              f"    {t['s_impr_short']} {fmt_d(im, im_p)}",
              f"    ACoS:         {'  !!' if acos_delta > 0 else '  OK'} {'+' if acos_delta > 0 else ''}{acos_delta:.1f}pp", ""]

    L.append(f"  {t['s_diag']}")
    if sl == 0:
        L.append(f"    {t['s_no_sales']}")
    elif acos < 15:
        L.append(f"    {t['s_acos_great'].format(acos)}")
    elif acos < 25:
        L.append(f"    {t['s_acos_ok'].format(acos)}")
    elif acos < 40:
        L.append(f"    {t['s_acos_warn'].format(acos)}")
    else:
        L.append(f"    {t['s_acos_bad'].format(acos)}")
    if im > 0:
        if ctr < 0.2:
            L.append(f"    {t['s_ctr_vlow'].format(ctr)}")
        elif ctr < 0.5:
            L.append(f"    {t['s_ctr_low'].format(ctr)}")
        else:
            L.append(f"    {t['s_ctr_ok'].format(ctr)}")
    if cl > 0:
        if cvr < 5:
            L.append(f"    {t['s_cvr_low'].format(cvr)}")
        elif cvr < 15:
            L.append(f"    {t['s_cvr_ok'].format(cvr)}")
        else:
            L.append(f"    {t['s_cvr_high'].format(cvr)}")
    L.append("")

    if top_rows:
        n = min(3, len(top_rows))
        L.append(f"  TOP {n} {tipo.upper()} {t['s_top']}")
        for i, row in enumerate(top_rows[:n], 1):
            name = row.get(entity_col, "-")
            r_sl = row.get("Sales", 0) or 0
            r_sp = row.get("Spend", 0) or 0
            r_acos = (r_sp / r_sl * 100) if r_sl > 0 else 0
            L.append(f"    {i}. {name}: ${r_sl:,.2f} {t['s_sales_lbl']} | ACoS {r_acos:.1f}%")
        L.append("")

    L.append(f"  {t['s_recs']}")
    recs = []
    if acos > 40:
        recs += [t["sr_reduce_bids"], t["sr_negative"]]
    elif acos > 25:
        recs.append(t["sr_opt_bids"])
    elif acos < 10 and sp > 50:
        recs.append(t["sr_scale"])
    if ctr < 0.3 and im > 1000:
        recs += [t["sr_ab_test"], t["sr_relevance"]]
    if cvr < 5 and cl > 100:
        recs.append(t["sr_listing"])
    if kp:
        sl_d = pct_chg(sl, kp["Sales"]); sp_d = pct_chg(sp, kp["Spend"])
        if sl_d is not None and sl_d < -15:
            recs.append(t["sr_sales_down"].format(abs(sl_d)))
        if sp_d is not None and sl_d is not None and sp_d > 10 and sl_d < sp_d - 10:
            recs.append(t["sr_spend_grow"])
    if not recs:
        recs += [t["sr_maintain"], t["sr_longtail"]]
    for i, r in enumerate(recs, 1):
        L.append(f"    {i}. {r}")
    L += ["", sep, f"  {t['s_footer']}", sep]
    return "\n".join(L)



def _diag_items(kc, kp=None, lang="es"):
    """Return list of (status, text) diagnostic items based on KPI values."""
    t    = _I18N[lang]
    acos = kc.get("ACoS", 0) or 0
    ctr  = kc.get("CTR",  0) or 0
    cvr  = kc.get("CVR",  0) or 0
    sl   = kc.get("Sales",0) or 0
    items = []
    if sl == 0:
        items.append(("error", t["d_no_sales"]))
    elif acos < 15:
        items.append(("ok",    t["d_acos_great"].format(acos)))
    elif acos < 30:
        items.append(("ok",    t["d_acos_ok"].format(acos)))
    elif acos < 60:
        items.append(("warn",  t["d_acos_warn"].format(acos)))
    else:
        items.append(("error", t["d_acos_bad"].format(acos)))
    if ctr > 0:
        if ctr < 0.2:   items.append(("error", t["d_ctr_vlow"].format(ctr)))
        elif ctr < 0.5: items.append(("warn",  t["d_ctr_low"].format(ctr)))
        else:           items.append(("ok",    t["d_ctr_ok"].format(ctr)))
    if cvr > 0:
        if cvr < 5:    items.append(("warn",  t["d_cvr_low"].format(cvr)))
        elif cvr < 15: items.append(("ok",    t["d_cvr_ok"].format(cvr)))
        else:          items.append(("ok",    t["d_cvr_high"].format(cvr)))
    if kp:
        sl_p = kp.get("Sales", 0) or 0; acos_p = kp.get("ACoS", 0) or 0
        if sl_p > 0:
            sl_d = (sl - sl_p) / sl_p * 100; ad = acos - acos_p
            if sl_d > 10:    items.append(("ok",    t["d_sales_up"].format(sl_d)))
            elif sl_d < -10: items.append(("error", t["d_sales_down"].format(abs(sl_d))))
            if ad < -3:      items.append(("ok",    t["d_acos_better"].format(abs(ad))))
            elif ad > 3:     items.append(("warn",  t["d_acos_worse"].format(ad)))
    return items


def _rec_items(kc, kp=None, lang="es"):
    """Return list of recommendation strings based on KPI values."""
    t    = _I18N[lang]
    acos = kc.get("ACoS", 0) or 0; ctr = kc.get("CTR", 0) or 0
    cvr  = kc.get("CVR",  0) or 0; sp  = kc.get("Spend", 0) or 0
    im   = kc.get("Impressions", 0) or 0; cl = kc.get("Clicks", 0) or 0
    recs = []
    if acos > 40:
        recs += [t["r_reduce_bids"], t["r_negative"]]
    elif acos > 25:
        recs.append(t["r_opt_bids"])
    elif acos < 10 and sp > 50:
        recs.append(t["r_scale"])
    if ctr < 0.3 and im > 1000:
        recs += [t["r_ab_test"], t["r_relevance"]]
    if cvr < 5 and cl > 100:
        recs.append(t["r_listing"])
    if kp:
        sl_d = ((kc["Sales"] - kp["Sales"]) / kp["Sales"] * 100) if kp.get("Sales") else None
        sp_d = ((kc["Spend"] - kp["Spend"]) / kp["Spend"] * 100) if kp.get("Spend") else None
        if sl_d is not None and sl_d < -15:
            recs.append(t["r_sales_down"].format(abs(sl_d)))
        if sp_d is not None and sl_d is not None and sp_d > 10 and sl_d < sp_d - 10:
            recs.append(t["r_spend_grow"])
    if not recs:
        recs += [t["r_maintain"], t["r_longtail"]]
    return recs
