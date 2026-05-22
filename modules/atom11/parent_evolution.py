import pandas as pd

from core.i18n import _I18N
from core.constants import _BR_OPTIONAL_COLS


def _build_parent_evolution(df_flat, ec1, cm1, fmt1, child_to_parent, asin_to_title,
                            br_df=None, lang="es"):
    """Group Atom 11 ASIN-level PPC data by Parent ASIN.

    Crosses df_flat[entity_col] directly with child_to_parent by ASIN.
    Output columns:
      Parent ASIN | Nombre | Ventas WoW (%) | Ventas últ. 7d | Ventas 7d ant. |
      [Ventas últ. 30d] | [Ventas últ. 90d] | [BR optional cols aggregated]

    br_df: optional DataFrame with "__asin" + BR optional cols (already numeric).
    Returns (DataFrame, error_message_or_None).
    """
    t          = _I18N.get(lang, _I18N["es"])
    entity_col = ec1[0]

    df = df_flat.copy()
    df["__parent"] = df[entity_col].astype(str).map(child_to_parent)
    df_mapped = df.dropna(subset=["__parent"])

    if df_mapped.empty:
        return None, (
            "No se encontraron ASINs del reporte en el mapeo Parent-Child. "
            "Verificá que el Business Report CSV sea del mismo cliente que el reporte Atom 11."
        )

    # i18n column name aliases
    C_WOW  = t["col_sales_wow"]
    C_CURR = t["col_sales_current"]
    C_PREV = t["col_sales_prev"]
    C_30D  = t["col_sales_30d"]
    C_90D  = t["col_sales_90d"]

    def _sum(grp, cols):
        present = [c for c in cols if c in df.columns]
        if not present:
            return 0.0
        return float(pd.to_numeric(grp[present].values.flatten(), errors="coerce").sum())

    def _wow_pct(curr, prev):
        return round((curr - prev) / prev * 100, 1) if prev else None

    parent_rows = []

    if fmt1 == "DateRange":
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        try:
            periods_sorted = sorted(periods, key=lambda p: pd.to_datetime(p))
        except Exception:
            periods_sorted = periods
        n = len(periods_sorted)

        def sc(ps):
            return [f"Sales|{p}" for p in ps]

        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}

            if n >= 14:
                v7c = _sum(grp, sc(periods_sorted[-7:]))
                v7p = _sum(grp, sc(periods_sorted[-14:-7]))
                row[C_WOW]  = _wow_pct(v7c, v7p)
                row[C_CURR] = round(v7c, 2)
                row[C_PREV] = round(v7p, 2)
            elif n >= 2:
                mid = n // 2
                vc  = _sum(grp, sc(periods_sorted[mid:]))
                vp  = _sum(grp, sc(periods_sorted[:mid]))
                row[C_WOW]  = _wow_pct(vc, vp)
                row[C_CURR] = round(vc, 2)
                row[C_PREV] = round(vp, 2)
            else:
                row[C_CURR] = round(_sum(grp, sc(periods_sorted)), 2)

            if n >= 30:
                row[C_30D] = round(_sum(grp, sc(periods_sorted[-30:])), 2)
            if n >= 90:
                row[C_90D] = round(_sum(grp, sc(periods_sorted[-90:])), 2)

            parent_rows.append(row)

    elif fmt1 == "WoW":
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        curr_p  = periods[-1]
        prev_p  = periods[0] if len(periods) >= 2 else None

        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}
            cc  = f"Sales|{curr_p}"
            cv  = float(pd.to_numeric(grp[cc], errors="coerce").sum()) if cc in df.columns else 0.0
            if prev_p:
                pc = f"Sales|{prev_p}"
                pv = float(pd.to_numeric(grp[pc], errors="coerce").sum()) if pc in df.columns else 0.0
                row[C_WOW]  = _wow_pct(cv, pv)
                row[C_PREV] = round(pv, 2)
            row[C_CURR] = round(cv, 2)
            parent_rows.append(row)

    else:  # MoM / single period
        periods = list(dict.fromkeys(p for _, _, p in cm1))
        period  = periods[0] if periods else ""
        for parent, grp in df_mapped.groupby("__parent"):
            row = {"Parent ASIN": parent, "Nombre": asin_to_title.get(parent, "")}
            col = f"Sales|{period}"
            if col in df.columns:
                row[C_CURR] = round(
                    float(pd.to_numeric(grp[col], errors="coerce").sum()), 2
                )
            parent_rows.append(row)

    if not parent_rows:
        return None, "No se pudo generar la tabla de evolución por Parent ASIN."

    result = pd.DataFrame(parent_rows)

    # Merge BR optional metrics aggregated by parent
    if br_df is not None and not br_df.empty:
        br_copy = br_df.copy()
        br_copy["__parent"] = br_copy["__asin"].map(child_to_parent)
        br_copy = br_copy.dropna(subset=["__parent"])
        if not br_copy.empty:
            opt_cols = [c for c in _BR_OPTIONAL_COLS if c in br_copy.columns]
            if opt_cols:
                br_agg = (
                    br_copy.groupby("__parent")[opt_cols]
                    .sum(numeric_only=True)
                    .reset_index()
                    .rename(columns={"__parent": "Parent ASIN"})
                )
                result = result.merge(br_agg, on="Parent ASIN", how="left")

    return result, None


def _generate_parent_evo_summary(pe_df, lang="es"):
    """Build a copiable executive summary from a Parent Evolution DataFrame.

    Uses i18n keys from _I18N so the output matches the ES/EN toggle.
    """
    t        = _I18N.get(lang, _I18N["es"])
    C_WOW    = t["col_sales_wow"]
    C_CURR   = t["col_sales_current"]
    C_PREV   = t["col_sales_prev"]
    C_ORD1   = t["col_total_orders"]   # "Total Order Items"
    C_ORD2   = t["col_units_ordered"]  # "Units Ordered"

    sep   = "=" * 62
    lines = [sep, f"  {t['pe_summary_title']}", sep, ""]

    total_curr   = 0.0
    total_prev   = 0.0
    total_orders = 0
    has_prev     = C_PREV in pe_df.columns
    has_wow      = C_WOW  in pe_df.columns

    for _, row in pe_df.iterrows():
        raw_name = row.get("Nombre", "") or row.get("Parent ASIN", "")
        name     = str(raw_name).strip()
        if not name or name.lower() == "nan":
            name = str(row.get("Parent ASIN", "")).strip()
        if len(name) > 45:
            name = name[:42] + "..."

        curr = float(row.get(C_CURR, 0) or 0)
        prev = float(row.get(C_PREV, 0) or 0) if has_prev else None
        wow  = row.get(C_WOW) if has_wow else None

        orders = 0
        for oc in [C_ORD1, C_ORD2]:
            if oc in row.index:
                v = row.get(oc)
                if pd.notna(v):
                    try:
                        orders = int(float(v))
                        break
                    except (ValueError, TypeError):
                        pass

        total_curr   += curr
        total_orders += orders
        if prev is not None:
            total_prev += prev

        if prev is not None and pd.notna(wow):
            w = float(wow)
            if w >= 0:
                lines.append("  " + t["pe_summary_wow_pos"].format(
                    name=name, pct=abs(w), curr=f"{curr:,.2f}",
                    prev=f"{prev:,.2f}", orders=orders))
            else:
                lines.append("  " + t["pe_summary_wow_neg"].format(
                    name=name, pct=w, curr=f"{curr:,.2f}",
                    prev=f"{prev:,.2f}", orders=orders))
        else:
            lines.append("  " + t["pe_summary_no_prev"].format(
                name=name, curr=f"{total_curr:,.2f}", orders=orders))

    lines.append("")
    ts = f"{total_curr:,.2f}"
    if total_prev > 0:
        tw = round((total_curr - total_prev) / total_prev * 100, 1)
        lines.append("  " + t["pe_summary_total_wow"].format(
            total_sales=ts, total_orders=total_orders, wow=tw))
    else:
        lines.append("  " + t["pe_summary_total"].format(
            total_sales=ts, total_orders=total_orders))

    lines.append(sep)
    return "\n".join(lines)
