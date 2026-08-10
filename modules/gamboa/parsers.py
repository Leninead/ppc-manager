"""
Módulo: Gamboa Generator — Parsers
Input: SQP.xlsx (Brand Analytics), BR.csv by ASIN semanal, Inventory Report, Categories CSV
Output: DataFrames normalizados listos para agregación
"""
import io
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st


# ══════════════════════════════════════════════════════════════════════════════
# SQP PARSER — Search Query Performance (Brand Analytics)
# ══════════════════════════════════════════════════════════════════════════════

# Mapeo defensivo de columnas SQP — Amazon cambia los nombres ocasionalmente
_SQP_COL_MAP = {
    "q":     ["Search Query"],
    "score": ["Search Query Score"],
    "vol":   ["Search Query Volume"],
    "impT":  ["Impressions: Total Count", "Impressions Total Count"],
    "impB":  ["Impressions: ASIN Count", "Impressions ASIN Count",
              "Impressions: Brand Count", "Impressions Brand Count"],
    "impBS": ["Impressions: ASIN Share %", "Impressions ASIN Share %",
              "Impressions: Brand Share %"],
    "clkT":  ["Clicks: Total Count", "Clicks Total Count"],
    "clkR":  ["Clicks: Click Rate %", "Click Rate %", "Clicks: Click Rate"],
    "clkB":  ["Clicks: ASIN Count", "Clicks ASIN Count", "Clicks: Brand Count"],
    "clkBS": ["Clicks: ASIN Share %", "Clicks ASIN Share %", "Clicks: Brand Share %"],
    "cartT": ["Cart Adds: Total Count", "Cart Adds Total Count"],
    "cartR": ["Cart Adds: Cart Add Rate %", "Cart Add Rate %", "Cart Adds: Cart Add Rate"],
    "cartB": ["Cart Adds: ASIN Count", "Cart Adds ASIN Count", "Cart Adds: Brand Count"],
    "cartBS": ["Cart Adds: ASIN Share %", "Cart Adds ASIN Share %", "Cart Adds: Brand Share %"],
    "purT":  ["Purchases: Total Count", "Purchases Total Count"],
    "purR":  ["Purchases: Purchase Rate %", "Purchase Rate %", "Purchases: Purchase Rate"],
    "purB":  ["Purchases: ASIN Count", "Purchases ASIN Count", "Purchases: Brand Count"],
    "purBS": ["Purchases: ASIN Share %", "Purchases ASIN Share %", "Purchases: Brand Share %"],
}


def _find_col(df: pd.DataFrame, candidates: list[str]) -> str | None:
    """Busca la primera columna que matchee alguno de los nombres candidatos (case-insensitive)."""
    norm = {c.strip().lower(): c for c in df.columns}
    for cand in candidates:
        key = cand.strip().lower()
        if key in norm:
            return norm[key]
    return None


def _extract_month_key(df: pd.DataFrame, filename: str) -> str | None:
    """
    Intenta extraer el mes del reporte (formato 'YYYY-MM').
    Busca en:
    1) Columna 'Reporting Range' (Amazon la incluye cuando bajás por rango)
    2) Nombre del archivo (ej: 'SQP_2026-01.xlsx' o 'January_2026_SQP.xlsx')
    3) Primera cell con formato fecha en top rows
    """
    # 1) Columna Reporting Range
    for col in df.columns:
        if "report" in col.lower() and "range" in col.lower():
            val = str(df[col].iloc[0]) if len(df) > 0 else ""
            m = re.search(r"(\d{4})-(\d{2})", val)
            if m:
                return f"{m.group(1)}-{m.group(2)}"
            m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", val)
            if m:
                return f"{m.group(3)}-{int(m.group(1)):02d}"

    # 2) Nombre del archivo
    m = re.search(r"(\d{4})[-_]?(\d{2})", filename)
    if m:
        y, mo = int(m.group(1)), int(m.group(2))
        if 2020 <= y <= 2035 and 1 <= mo <= 12:
            return f"{y}-{mo:02d}"

    # 3) Mes textual en filename
    months_es = {'enero':1,'febrero':2,'marzo':3,'abril':4,'mayo':5,'junio':6,
                 'julio':7,'agosto':8,'septiembre':9,'octubre':10,'noviembre':11,'diciembre':12}
    months_en = {'january':1,'february':2,'march':3,'april':4,'may':5,'june':6,
                 'july':7,'august':8,'september':9,'october':10,'november':11,'december':12}
    fn_lower = filename.lower()
    for mdict in (months_es, months_en):
        for name, num in mdict.items():
            if name in fn_lower:
                year_m = re.search(r'(20\d{2})', fn_lower)
                if year_m:
                    return f"{year_m.group(1)}-{num:02d}"
    return None


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def parse_sqp_file(raw_bytes: bytes, filename: str) -> tuple[pd.DataFrame, str | None]:
    """
    Parsea un archivo SQP individual. Retorna (df_normalizado, month_key).
    El df tiene columnas: q, cat, mk, score, vol, impT, impB, impBS, ... (20 campos)
    cat queda vacío acá — se llena después con el mapeo de categorías.
    """
    # SQP de Brand Analytics tiene header en fila 2 (skiprows=1 como en read_sqp core)
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw_bytes), skiprows=1)
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes), skiprows=1)
    except Exception:
        # Fallback sin skiprows
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw_bytes))
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes))

    # Detectar mes
    mk = _extract_month_key(df, filename)

    # Mapeo columnas → estructura estándar Gamboa
    out = pd.DataFrame()
    for target, candidates in _SQP_COL_MAP.items():
        src_col = _find_col(df, candidates)
        if src_col is not None:
            out[target] = df[src_col]
        else:
            # score defaultea 0 si no viene
            out[target] = 0 if target == "score" else None

    # Filtrar filas sin query
    if "q" in out.columns:
        out = out[out["q"].notna() & (out["q"].astype(str).str.strip() != "")]

    # Coerce a numérico
    for col in ["score","vol","impT","impB","impBS","clkT","clkR","clkB","clkBS",
                "cartT","cartR","cartB","cartBS","purT","purR","purB","purBS"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out["q"] = out["q"].astype(str).str.strip()
    out["mk"] = mk or ""
    out["cat"] = ""  # se asigna luego
    return out, mk


def parse_sqp_multi(files: list) -> tuple[pd.DataFrame, list[str], list[str]]:
    """
    Parsea N archivos SQP y los consolida en un único df con todos los meses detectados.
    Retorna (df, months_found, warnings).
    """
    dfs = []
    months = set()
    warnings = []

    for f in files:
        try:
            raw = f.read() if hasattr(f, "read") else f
            df, mk = parse_sqp_file(raw, getattr(f, "name", "sqp.xlsx"))
            if mk is None:
                warnings.append(f"⚠️ No pude detectar mes en `{getattr(f, 'name', '?')}` — ignorado")
                continue
            if mk in months:
                warnings.append(f"ℹ️ Mes {mk} ya cargado desde otro archivo — se usa el primero")
                continue
            months.add(mk)
            dfs.append(df)
        except Exception as e:
            warnings.append(f"❌ Error en `{getattr(f, 'name', '?')}`: {e}")

    if not dfs:
        return pd.DataFrame(), [], warnings

    full = pd.concat(dfs, ignore_index=True)
    return full, sorted(months), warnings


# ══════════════════════════════════════════════════════════════════════════════
# BR PARSER — Business Report by ASIN (weekly)
# ══════════════════════════════════════════════════════════════════════════════

_BR_COL_MAP = {
    "asin":  ["(Child) ASIN", "Child ASIN", "ASIN", "(Parent) ASIN", "Parent ASIN"],
    "title": ["Title", "Product Name", "(Child) Product Name"],
    "sess":  ["Sessions – Total", "Sessions - Total", "Sessions"],
    "pv":    ["Page Views – Total", "Page Views - Total", "Page Views"],
    "units": ["Units Ordered"],
    "usp":   ["Unit Session Percentage", "Unit Session Percentage (New)",
              "Order Item Session Percentage", "Order Item Session Percentage (New)"],
    "sales": ["Ordered Product Sales", "Ordered Product Sales (new)", "Ordered Product Sales – B2B"],
    "items": ["Total Order Items"],
    "bb":    ["Featured Offer (Buy Box) Percentage", "Buy Box Percentage",
              "Featured Offer Percentage"],
}


def _extract_week_key(filename: str, df: pd.DataFrame | None = None) -> str | None:
    """
    Extrae week key formato 'WkN-YY' desde filename o columna de rango.
    Ej: 'BR_2026-W03.csv' → 'Wk3-26'; 'Jan01-Jan07_2026.csv' → 'Wk1-26'
    """
    # 1) Pattern explícito WkN-YY o WkN_YY
    m = re.search(r"[Ww]k?\s*(\d{1,2})[\s_-]+(\d{2,4})", filename)
    if m:
        wk = int(m.group(1))
        yr = int(m.group(2))
        yr_short = yr % 100
        if 1 <= wk <= 53:
            return f"Wk{wk}-{yr_short:02d}"

    # 2) Fecha en el archivo: extraer primer rango y calcular ISO week
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", filename)
    if m:
        try:
            d = datetime(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            iso = d.isocalendar()
            return f"Wk{iso[1]}-{iso[0]%100:02d}"
        except Exception:
            pass

    # 3) Fecha dentro del df (columna Date o similar)
    if df is not None:
        for col in df.columns:
            if "date" in col.lower():
                try:
                    val = pd.to_datetime(df[col].iloc[0])
                    iso = val.isocalendar()
                    return f"Wk{iso[1]}-{iso[0]%100:02d}"
                except Exception:
                    continue
    return None


def _week_date_label(wk_key: str) -> str:
    """Convierte 'Wk3-26' → '12 Ene - 18 Ene 26' (rango de fechas legible)."""
    m = re.match(r"Wk(\d+)-(\d{2})", wk_key)
    if not m:
        return ""
    wk, yr = int(m.group(1)), int(m.group(2))
    full_year = 2000 + yr
    try:
        # ISO week: jueves de esa semana define el año
        jan4 = datetime(full_year, 1, 4)
        week1_start = jan4 - pd.Timedelta(days=jan4.isoweekday() - 1)
        start = week1_start + pd.Timedelta(days=(wk - 1) * 7)
        end = start + pd.Timedelta(days=6)
        meses_es = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
        return f"{start.day} {meses_es[start.month-1]} - {end.day} {meses_es[end.month-1]} {yr:02d}"
    except Exception:
        return ""


@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def parse_br_file(raw_bytes: bytes, filename: str) -> tuple[pd.DataFrame, str | None]:
    """
    Parsea un BR semanal by ASIN. Retorna (df, week_key).
    """
    try:
        if filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw_bytes))
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes))
    except Exception:
        df = pd.read_csv(io.BytesIO(raw_bytes), encoding="latin-1")

    wk = _extract_week_key(filename, df)

    out = pd.DataFrame()
    for target, candidates in _BR_COL_MAP.items():
        src_col = _find_col(df, candidates)
        if src_col is not None:
            out[target] = df[src_col]
        else:
            out[target] = "" if target in ("asin", "title") else 0

    # Cleanup currency strings ($1,234.56) → float
    if "sales" in out.columns:
        out["sales"] = (out["sales"].astype(str)
                        .str.replace(r"[$,]", "", regex=True)
                        .str.replace("%", "", regex=False))
        out["sales"] = pd.to_numeric(out["sales"], errors="coerce").fillna(0)

    # Percent strings "12.34%" → 12.34
    for col in ("usp", "bb"):
        if col in out.columns:
            out[col] = (out[col].astype(str)
                        .str.replace("%", "", regex=False)
                        .str.replace(",", "", regex=False))
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    # Numérico
    for col in ("sess", "pv", "units", "items"):
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(0)

    out["asin"] = out["asin"].astype(str).str.strip()
    out["title"] = out["title"].astype(str).str.strip()
    out = out[out["asin"].ne("") & out["asin"].notna()]
    out["wk"] = wk or ""
    out["cat"] = ""    # se completa con el mapeo de categorías
    out["sku"] = ""    # se completa con Inventory (o fallback a ASIN)
    return out, wk


def parse_br_multi(files: list) -> tuple[pd.DataFrame, list[str], list[str]]:
    """Parsea N archivos BR semanales y los consolida."""
    dfs = []
    weeks = set()
    warnings = []

    for f in files:
        try:
            raw = f.read() if hasattr(f, "read") else f
            df, wk = parse_br_file(raw, getattr(f, "name", "br.csv"))
            if wk is None:
                warnings.append(f"⚠️ No pude detectar semana en `{getattr(f, 'name', '?')}` — ignorado")
                continue
            if wk in weeks:
                warnings.append(f"ℹ️ Semana {wk} ya cargada — se usa el primero")
                continue
            weeks.add(wk)
            dfs.append(df)
        except Exception as e:
            warnings.append(f"❌ Error en `{getattr(f, 'name', '?')}`: {e}")

    if not dfs:
        return pd.DataFrame(), [], warnings

    full = pd.concat(dfs, ignore_index=True)
    return full, sorted(weeks, key=_week_sort_key), warnings


def _week_sort_key(wk: str) -> tuple[int, int]:
    """Sort key para ordenar semanas cronológicamente: Wk52-25 antes que Wk1-26."""
    m = re.match(r"Wk(\d+)-(\d{2})", wk)
    if not m: return (0, 0)
    return (int(m.group(2)), int(m.group(1)))


# ══════════════════════════════════════════════════════════════════════════════
# INVENTORY PARSER — para mapeo ASIN ↔ SKU
# ══════════════════════════════════════════════════════════════════════════════

@st.cache_data(max_entries=3, ttl=3600, show_spinner=False)
def parse_inventory(raw_bytes: bytes, filename: str) -> dict[str, str]:
    """
    Parsea Inventory Report y devuelve mapping {asin: sku}.
    Columnas posibles: 'asin'/'ASIN', 'sku'/'SKU'/'seller-sku'.
    """
    try:
        if filename.lower().endswith((".tsv", ".txt")):
            df = pd.read_csv(io.BytesIO(raw_bytes), sep="\t", encoding="latin-1")
        elif filename.lower().endswith(".csv"):
            df = pd.read_csv(io.BytesIO(raw_bytes))
        else:
            df = pd.read_excel(io.BytesIO(raw_bytes))
    except Exception:
        df = pd.read_csv(io.BytesIO(raw_bytes), sep="\t", encoding="latin-1")

    asin_col = _find_col(df, ["asin", "ASIN", "asin1"])
    sku_col = _find_col(df, ["sku", "SKU", "seller-sku", "Seller SKU", "merchant-sku"])
    if not (asin_col and sku_col):
        return {}

    df = df[[asin_col, sku_col]].dropna()
    df[asin_col] = df[asin_col].astype(str).str.strip()
    df[sku_col] = df[sku_col].astype(str).str.strip()
    df = df[df[asin_col].ne("") & df[sku_col].ne("")]
    return dict(zip(df[asin_col], df[sku_col]))


# ══════════════════════════════════════════════════════════════════════════════
# CATEGORIES — mapeo persistente ASIN → Categoría
# ══════════════════════════════════════════════════════════════════════════════

def _categories_path(client_slug: str) -> Path:
    """Ruta al CSV de categorías para un cliente. Relativa a cwd."""
    return Path("notes") / "brands" / client_slug / "gamboa_categories.csv"


def load_categories(client_slug: str) -> dict[str, str]:
    """
    Carga mapeo {asin: category} desde notes/brands/{client}/gamboa_categories.csv.
    Retorna {} si no existe.
    """
    path = _categories_path(client_slug)
    if not path.exists():
        return {}
    try:
        df = pd.read_csv(path)
        asin_col = _find_col(df, ["asin", "ASIN"])
        cat_col = _find_col(df, ["category", "categoria", "cat"])
        if not (asin_col and cat_col):
            return {}
        df = df[[asin_col, cat_col]].dropna()
        df[asin_col] = df[asin_col].astype(str).str.strip()
        df[cat_col] = df[cat_col].astype(str).str.strip()
        df = df[df[asin_col].ne("") & df[cat_col].ne("")]
        return dict(zip(df[asin_col], df[cat_col]))
    except Exception:
        return {}


def save_categories(client_slug: str, mapping: dict[str, str]) -> Path:
    """Guarda mapeo {asin: category} en el CSV persistente. Crea el directorio si no existe."""
    path = _categories_path(client_slug)
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame([{"asin": a, "category": c} for a, c in sorted(mapping.items())])
    df.to_csv(path, index=False, encoding="utf-8")
    return path


def generate_category_template(client_slug: str, asins: list[str]) -> bytes:
    """
    Genera una plantilla CSV vacía para que el usuario complete categorías.
    No pisa archivo existente — solo devuelve bytes para descarga.
    """
    existing = load_categories(client_slug)
    rows = [{"asin": a, "category": existing.get(a, "")} for a in sorted(set(asins))]
    df = pd.DataFrame(rows)
    buf = io.BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8")
    return buf.getvalue()
