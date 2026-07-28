import pandas as pd
import re


def _parse_atom11(filepath):
    """Parse an Atom 11 Excel file into a flat DataFrame.

    Returns (df_flat, entity_cols, col_map, fmt) where:
      - df_flat: rows are entities, columns are entity names + "Metric|Period" keys
      - entity_cols: list of entity column names (e.g. ["ASIN"] or ["Portfolio", "CampaignType"])
      - col_map: list of (col_idx, metric_name, period_label)
      - fmt: "WoW" | "MoM" | "DateRange"
    """
    filepath_str = filepath.name if hasattr(filepath, "name") else str(filepath)
    if filepath_str.lower().endswith(".csv"):
        raw = pd.read_csv(filepath, header=None, dtype=str, encoding="utf-8-sig")
    else:
        raw = pd.read_excel(filepath, header=None, dtype=str)

    # Row 2 holds entity column names at the start; stop at first blank cell
    entity_cols = []
    for val in raw.iloc[2]:
        s = str(val).strip() if pd.notna(val) else ""
        if s and s.lower() != "nan":
            entity_cols.append(s)
        else:
            break
    n_entity = len(entity_cols)

    # Build col_map from rows 0 (metric) and 1 (period)
    current_metric = None
    col_map = []
    for ci in range(n_entity, len(raw.columns)):
        m = str(raw.iloc[0, ci]).strip() if pd.notna(raw.iloc[0, ci]) else ""
        p = str(raw.iloc[1, ci]).strip() if pd.notna(raw.iloc[1, ci]) else ""
        if m and m.lower() != "nan":
            current_metric = m
        if p and p.lower() != "nan" and current_metric:
            col_map.append((ci, current_metric, p))

    # Detect format from period labels
    periods = [p for _, _, p in col_map]
    if any("week" in p.lower() for p in periods):
        fmt = "WoW"
    elif any(re.match(r"\d{4}-\d{2}-\d{2}", p) for p in periods):
        fmt = "DateRange"
    else:
        fmt = "MoM"

    # Parse data rows (3+) with forward-fill on entity col 0
    rows = []
    last0 = None
    for ri in range(3, len(raw)):
        row = raw.iloc[ri]
        v0 = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else ""
        if v0 and v0.lower() != "nan":
            last0 = v0
        elif last0:
            v0 = last0
        if not v0 or v0.lower() == "nan":
            continue

        rec = {entity_cols[0]: v0}
        for i in range(1, n_entity):
            v = str(row.iloc[i]).strip() if pd.notna(row.iloc[i]) else ""
            rec[entity_cols[i]] = "" if v.lower() == "nan" else v
        for ci, metric, period in col_map:
            v = row.iloc[ci]
            rec[f"{metric}|{period}"] = pd.to_numeric(
                str(v) if pd.notna(v) else "", errors="coerce"
            )
        rows.append(rec)

    return pd.DataFrame(rows), entity_cols, col_map, fmt


# ── Atom 11 helpers ───────────────────────────────────────────────────────────
_ENTITY_TYPE_LABELS = {
    "asin":          "ASIN",
    "portfolioname": "Portfolio",
    "campaigntype":  "Campaign Type",
    "keyword":       "Keyword",
}

def _detect_atom11_type(entity_cols):
    return _ENTITY_TYPE_LABELS.get(entity_cols[0].lower(), entity_cols[0]) if entity_cols else "Desconocido"

def _extract_period_df(df_flat, entity_cols, col_map, period_label):
    """Return a DataFrame with entity_cols + plain metric columns for one period."""
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))
    result = df_flat[entity_cols].copy()
    for metric in metrics:
        col = f"{metric}|{period_label}"
        if col in df_flat.columns:
            result[metric] = df_flat[col]
    return result

def _summarize_daterange(df_flat, entity_cols, col_map):
    """Sum all date columns per metric. Returns (df, period_label)."""
    periods = list(dict.fromkeys(p for _, _, p in col_map))
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))
    result = df_flat[entity_cols].copy()
    for metric in metrics:
        date_cols = [f"{metric}|{p}" for p in periods if f"{metric}|{p}" in df_flat.columns]
        if date_cols:
            result[metric] = df_flat[date_cols].sum(axis=1)
    return result, f"{periods[0]}\u2192{periods[-1]}"


def _split_two_weeks(df_flat, entity_cols, col_map):
    """Detect if a DateRange file spans exactly 14 days and split into two 7-day weeks.

    Returns (df_w1, df_w2, label_w1, label_w2) or None if not a 14-day range.
    Week 1 (Valor Anterior) = days 1-7, Week 2 (Valor Actual) = days 8-14.
    """
    from datetime import timedelta
    periods = list(dict.fromkeys(p for _, _, p in col_map))
    parsed = []
    for p in periods:
        try:
            parsed.append((p, pd.to_datetime(p).date()))
        except Exception:
            return None
    if not parsed:
        return None
    parsed.sort(key=lambda x: x[1])
    first_date = parsed[0][1]
    last_date  = parsed[-1][1]
    if (last_date - first_date).days + 1 != 14:
        return None
    mid_date      = first_date + timedelta(days=7)
    week1_periods = [p for p, d in parsed if d < mid_date]
    week2_periods = [p for p, d in parsed if d >= mid_date]
    if not week1_periods or not week2_periods:
        return None
    metrics = list(dict.fromkeys(m for _, m, _ in col_map))

    def _sum_week(wperiods):
        res = df_flat[entity_cols].copy()
        for metric in metrics:
            dcols = [f"{metric}|{p}" for p in wperiods if f"{metric}|{p}" in df_flat.columns]
            if dcols:
                res[metric] = df_flat[dcols].sum(axis=1)
        return res

    df_w1   = _sum_week(week1_periods)
    df_w2   = _sum_week(week2_periods)
    label_w1 = f"{week1_periods[0]} \u2192 {week1_periods[-1]}"
    label_w2 = f"{week2_periods[0]} \u2192 {week2_periods[-1]}"
    return df_w1, df_w2, label_w1, label_w2
