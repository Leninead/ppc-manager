"""Parsers puros de exports DataDive — extraídos de modules/pages/datadive_analyzer.py.

Sin dependencia de Streamlit: estas funciones toman bytes crudos de un .xlsx y
devuelven structured data (DataFrame + metadata). El caching (@st.cache_data) y la
UI viven en datadive_analyzer.py, que delega acá.

Bodies extraídos 1:1 de los _parse_* originales (2026-05-26). Único cambio de
comportamiento: coerción NaN-safe en parse_mkl (_coerce_int_safe/_coerce_float_safe),
que reemplaza el patrón `pd.to_numeric(...) or 0` — NaN es truthy en Python, así que
ese patrón devolvía NaN y `int(NaN)` crasheaba (fix D4).
"""

from __future__ import annotations

import io
import re

import pandas as pd

# Nombres de columna canónicos del MKL parseado. Compartidos con el mapper a V3
# para evitar drift (si cambian acá, el mapper los importa).
COL_SEARCH_TERM = "Search Term"
COL_SV = "SV"
COL_RELEVANCE = "Relevance"
COL_SUGG_BID = "Sugg. Bid"
COL_LAUNCH_SCORE = "Launch Score"


def _coerce_int_safe(raw, default: int = 0) -> int:
    """Coerce a int de forma NaN-safe. NaN / no-numérico → default.

    Reemplaza el patrón `pd.to_numeric(...) or 0`, que NO captura NaN (NaN es
    truthy en Python) y hacía crashear `int(NaN)`.
    """
    v = pd.to_numeric(raw, errors="coerce")
    if pd.isna(v):
        return default
    return int(v)


def _coerce_float_safe(raw, default: float = 0.0) -> float:
    """Coerce a float de forma NaN-safe. NaN / no-numérico → default."""
    v = pd.to_numeric(raw, errors="coerce")
    if pd.isna(v):
        return default
    return float(v)


def parse_mkl(data: bytes, name: str) -> tuple[pd.DataFrame, list[str]]:
    """Parse DataDive MKL (Master Keyword List) — niche-*-keywords.xlsx."""
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    header_row = None
    for i in range(min(5, len(raw))):
        row_vals = raw.iloc[i].astype(str).str.lower()
        if row_vals.str.contains("search.?term").any():
            header_row = i
            break
    if header_row is None:
        header_row = 1

    asin_pattern = re.compile(r'B0[A-Z0-9]{8}', re.IGNORECASE)
    asin_cols = {}
    for ci in range(6, raw.shape[1]):
        for ri in range(min(3, len(raw))):
            val = str(raw.iloc[ri, ci]).strip()
            m = asin_pattern.search(val)
            if m:
                asin_cols[ci] = m.group(0).upper()
                break

    data_start = header_row + 1
    rows = []
    for ri in range(data_start, len(raw)):
        term = str(raw.iloc[ri, 1]).strip() if pd.notna(raw.iloc[ri, 1]) else ""
        if not term or term.lower() in ("nan", ""):
            continue
        sv = _coerce_int_safe(str(raw.iloc[ri, 2]).replace(",", ""))
        relevance = _coerce_float_safe(raw.iloc[ri, 3])
        bid_raw = str(raw.iloc[ri, 4]).replace("$", "").replace(",", "").strip()
        bid_match = re.search(r'[\d.]+', bid_raw)
        sugg_bid = float(bid_match.group()) if bid_match else 0
        launch_score = _coerce_float_safe(raw.iloc[ri, 5])

        row = {
            COL_SEARCH_TERM: term,
            COL_SV: sv,
            COL_RELEVANCE: round(relevance, 2),
            COL_SUGG_BID: round(sugg_bid, 2),
            COL_LAUNCH_SCORE: round(launch_score, 1),
        }
        for ci, asin in asin_cols.items():
            rank_val = pd.to_numeric(raw.iloc[ri, ci], errors="coerce")
            row[asin] = int(rank_val) if pd.notna(rank_val) and rank_val > 0 else None
        rows.append(row)

    df = pd.DataFrame(rows) if rows else pd.DataFrame()
    competitor_asins = list(asin_cols.values())
    return df, competitor_asins


def parse_competitors(data: bytes, name: str) -> tuple[pd.DataFrame, dict]:
    """Parse DataDive Competitors — niche-*-competitors.xlsx."""
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    label_col = 1
    for ci in range(min(4, raw.shape[1])):
        col_vals = raw.iloc[:, ci].astype(str).str.lower()
        if col_vals.str.contains("^asin$").any() or col_vals.str.contains("^brand$").any():
            label_col = ci
            break

    median_col = None
    for ci in range(label_col + 1, min(label_col + 6, raw.shape[1])):
        for ri in range(min(3, len(raw))):
            if "median" in str(raw.iloc[ri, ci]).lower():
                median_col = ci
                break
        if median_col is not None:
            break
    if median_col is None:
        median_col = 3

    asin_start = max(median_col + 1, 5)
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
        for ci in range(asin_start, raw.shape[1]):
            val = str(raw.iloc[0, ci]).strip()
            m = asin_pattern.search(val)
            if m:
                asin_cols[ci] = m.group(0).upper()

    target_metrics = [
        "brand", "asin", "sv on p1", "strength", "seller's country", "variations",
        "30d sales", "30d revenue", "price", "rating", "review count",
        "listing age", "kws on p1", "advertised kws", "category",
    ]

    result = {}
    median_data = {}

    for ri in range(len(raw)):
        metric_raw = str(raw.iloc[ri, label_col]).strip()
        metric_lower = metric_raw.lower()
        if not any(t in metric_lower for t in target_metrics):
            continue
        metric_name = metric_raw
        med_val = raw.iloc[ri, median_col] if median_col < raw.shape[1] else None
        median_data[metric_name] = med_val
        for ci, asin in asin_cols.items():
            if asin not in result:
                result[asin] = {}
            result[asin][metric_name] = raw.iloc[ri, ci]

    if not result:
        return pd.DataFrame(), median_data

    rows = []
    for asin, metrics in result.items():
        row = {"ASIN": asin}
        row.update(metrics)
        rows.append(row)

    df = pd.DataFrame(rows)
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


def parse_rank_radar(data: bytes, name: str) -> tuple[pd.DataFrame, list[str], dict]:
    """Parse DataDive Rank Radar — [product-name].xlsx."""
    buf = io.BytesIO(data)
    raw = pd.read_excel(buf, sheet_name=0, header=None)

    if len(raw) < 5:
        return pd.DataFrame(), [], {}

    headers = raw.iloc[1].astype(str).str.strip().tolist()

    date_pattern = re.compile(r'^\d{4}-\d{2}-\d{2}$')
    date_cols = {}
    for ci, h in enumerate(headers):
        if date_pattern.match(h):
            date_cols[ci] = h

    known_cols = {
        "search terms": "Search Term", "tags": "Tags",
        "search volume": "SV", "sv": "SV",
        "rel.": "Relevance", "rel": "Relevance",
        "median rank": "Median Rank", "sq score": "SQ Score",
        "asin share": "ASIN Share", "asin ctr": "ASIN CTR",
        "asin count": "ASIN Count", "asin cvr": "ASIN CVR",
        "ex": "PPC Exact", "ph": "PPC Phrase",
        "br": "PPC Broad", "au": "PPC Auto",
        "ir": "IR", "sales": "PPC Sales", "spend": "PPC Spend",
        "ctr": "PPC CTR", "cpc": "PPC CPC", "cvr": "PPC CVR",
    }

    col_map = {}
    seen_names = {}
    for ci, h in enumerate(headers):
        hl = h.lower().strip()
        if ci in date_cols:
            continue
        if hl in known_cols:
            base = known_cols[hl]
            if base in seen_names:
                seen_names[base] += 1
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

    data_start = 4
    rows = []
    for ri in range(data_start, len(raw)):
        first_val = str(raw.iloc[ri, 0]).strip() if pd.notna(raw.iloc[ri, 0]) else ""
        second_val = str(raw.iloc[ri, 1]).strip() if raw.shape[1] > 1 and pd.notna(raw.iloc[ri, 1]) else ""
        term = first_val or second_val
        if not term or term.lower() in ("nan", ""):
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

    numeric_cols = ["SV", "Relevance", "Median Rank", "SQ Score", "PPC Exact", "PPC Phrase",
                    "PPC Broad", "PPC Auto", "IR", "PPC Sales", "PPC Spend", "PPC CTR",
                    "PPC CPC", "PPC CVR"]
    for col in numeric_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(
                df[col].astype(str).str.replace(r"[\$,%]", "", regex=True).str.replace(",", ""),
                errors="coerce",
            )

    date_col_names = sorted(date_cols.values())
    agg_data = {}
    if len(raw) > 2:
        for ci, col_name in col_map.items():
            agg_data[col_name] = raw.iloc[2, ci]

    return df, date_col_names, agg_data
