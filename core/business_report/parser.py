import os
import pandas as pd
import streamlit as st

from core.constants import _BR_OPTIONAL_COLS

# Three levels up from core/business_report/parser.py is the repo root.
_BIZ_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data",
                        "business_report")


def _parse_business_report_map(filepath_or_file):
    """Parse a Business Report CSV/XLSX for Parent-Child ASIN mapping.

    Required columns : "(Parent) ASIN", "(Child) ASIN"
    Optional column  : "Title"
    Extra optional   : any column in _BR_OPTIONAL_COLS
    Standalones      : rows where (Parent) ASIN == (Child) ASIN treated as own parent
    CSV format       : BOM-aware (utf-8-sig), numbers may contain $, commas, %

    Returns:
        child_to_parent : dict  {child_asin: parent_asin}
        asin_to_title   : dict  {asin: title}
        br_df           : DataFrame with "__asin" + present optional cols (numeric), or None
    """
    COL_PARENT = "(Parent) ASIN"
    COL_CHILD  = "(Child) ASIN"
    COL_TITLE  = "Title"

    # ── Detect extension robustly ─────────────────────────────────────────────
    if isinstance(filepath_or_file, str):
        _ext = os.path.splitext(filepath_or_file)[1].lower()
    elif hasattr(filepath_or_file, "name"):
        _ext = os.path.splitext(filepath_or_file.name)[1].lower()
    else:
        _ext = ".csv"   # BytesIO or unknown → assume CSV

    try:
        if _ext == ".csv":
            df = pd.read_csv(filepath_or_file, dtype=str, encoding="utf-8-sig")
        else:
            df = pd.read_excel(filepath_or_file, dtype=str)
    except Exception as e:
        raise ValueError(f"No se pudo leer el archivo: {e}")

    # Strip BOM and whitespace from column names
    df.columns = [str(c).lstrip("\ufeff").strip() for c in df.columns]

    missing_required = [c for c in [COL_PARENT, COL_CHILD] if c not in df.columns]
    if missing_required:
        raise ValueError(
            f"Columnas requeridas no encontradas: {missing_required}. "
            f"Columnas disponibles: {list(df.columns[:20])}"
        )

    has_title    = COL_TITLE in df.columns
    present_opts = [c for c in _BR_OPTIONAL_COLS if c in df.columns]

    # ── Build mapping dicts ───────────────────────────────────────────────────
    child_to_parent = {}
    asin_to_title   = {}

    for _, row in df.iterrows():
        parent = str(row[COL_PARENT]).strip() if pd.notna(row[COL_PARENT]) else ""
        child  = str(row[COL_CHILD]).strip()  if pd.notna(row[COL_CHILD])  else ""

        if not parent or parent.lower() == "nan":
            continue
        if not child or child.lower() == "nan":
            continue

        if has_title:
            t = str(row[COL_TITLE]).strip() if pd.notna(row[COL_TITLE]) else ""
            if t and t.lower() != "nan":
                asin_to_title[child]  = t
                asin_to_title[parent] = t

        child_to_parent[child] = parent

    # ── Build optional-metrics DataFrame with proper numeric conversion ───────
    br_df = None
    if present_opts:
        keep  = [COL_CHILD] + present_opts
        br_df = df[[c for c in keep if c in df.columns]].copy()
        br_df = br_df.rename(columns={COL_CHILD: "__asin"})

        for c in present_opts:
            if c not in br_df.columns:
                continue
            # Clean Amazon number formats: "$1,408.59" / "1,162" / "30.90%"
            cleaned = (
                br_df[c].astype(str)
                .str.replace(r"[$,%]", "", regex=True)
                .str.replace(",", "", regex=False)
                .str.strip()
            )
            br_df[c] = pd.to_numeric(cleaned, errors="coerce")

        br_df = br_df.dropna(subset=["__asin"])
        br_df["__asin"] = br_df["__asin"].str.strip()

    return child_to_parent, asin_to_title, br_df


def _auto_load_business_report_map():
    """Scan _BIZ_DIR for the first CSV/XLSX and load the parent-child map."""
    if not os.path.isdir(_BIZ_DIR):
        return False
    for fname in sorted(os.listdir(_BIZ_DIR)):
        if fname.lower().endswith((".csv", ".xlsx")):
            try:
                c_map, n_map, br_df = _parse_business_report_map(
                    os.path.join(_BIZ_DIR, fname)
                )
                st.session_state["parent_child_map"]   = c_map
                st.session_state["parent_child_names"] = n_map
                st.session_state["br_extra_df"]        = br_df
                st.session_state["_cat_source_file"]   = fname
                return True
            except Exception:
                continue
    return False
