"""
Módulo: Gamboa Generator — Orquestador
Toma DataFrames parseados (SQP + BR + Inventory + Categories) y produce el HTML final.
"""
import json
import re
from datetime import datetime
from pathlib import Path

import pandas as pd


# ══════════════════════════════════════════════════════════════════════════════
# TEMPLATE LOADER
# ══════════════════════════════════════════════════════════════════════════════

def _template_path() -> Path:
    """Ruta al template.html — está al lado de este archivo."""
    return Path(__file__).parent / "template.html"


def load_template() -> str:
    """Carga el template HTML desde modules/gamboa/template.html."""
    path = _template_path()
    if not path.exists():
        raise FileNotFoundError(f"Template no encontrado en {path}")
    return path.read_text(encoding="utf-8")


# ══════════════════════════════════════════════════════════════════════════════
# MONTH / WEEK HELPERS
# ══════════════════════════════════════════════════════════════════════════════

_MESES_ES_CORTO = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic']
_MESES_ES_LARGO = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                   'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']


def _month_label_short(mk: str) -> str:
    """'2026-01' → 'Ene 26'"""
    m = re.match(r"(\d{4})-(\d{2})", mk)
    if not m: return mk
    y, mo = int(m.group(1)), int(m.group(2))
    return f"{_MESES_ES_CORTO[mo-1]} {y%100:02d}"


def _month_label_long(mk: str) -> str:
    """'2026-01' → 'Enero 2026'"""
    m = re.match(r"(\d{4})-(\d{2})", mk)
    if not m: return mk
    y, mo = int(m.group(1)), int(m.group(2))
    return f"{_MESES_ES_LARGO[mo-1]} {y}"


def _week_date_label(wk: str) -> str:
    """'Wk3-26' → '12 Ene - 18 Ene 26'"""
    m = re.match(r"Wk(\d+)-(\d{2})", wk)
    if not m: return ""
    wk_num, yr = int(m.group(1)), int(m.group(2))
    full_year = 2000 + yr
    try:
        jan4 = datetime(full_year, 1, 4)
        week1_start = jan4 - pd.Timedelta(days=jan4.isoweekday() - 1)
        start = week1_start + pd.Timedelta(days=(wk_num - 1) * 7)
        end = start + pd.Timedelta(days=6)
        return (f"{start.day} {_MESES_ES_CORTO[start.month-1]} - "
                f"{end.day} {_MESES_ES_CORTO[end.month-1]} {yr:02d}")
    except Exception:
        return ""


def _week_sort_key(wk: str) -> tuple[int, int]:
    m = re.match(r"Wk(\d+)-(\d{2})", wk)
    if not m: return (0, 0)
    return (int(m.group(2)), int(m.group(1)))


# ══════════════════════════════════════════════════════════════════════════════
# DATA ENRICHMENT — aplicar categorías y SKUs a los DataFrames
# ══════════════════════════════════════════════════════════════════════════════

def enrich_sqp(sqp_df: pd.DataFrame, asin_category_map: dict[str, str]) -> pd.DataFrame:
    """
    El SQP no trae ASIN por query directamente. Las categorías se asignan a nivel de query
    via keyword-matching contra el catálogo del cliente, o quedan en "Sin Categorizar".

    Estrategia simple: si alguno de los tokens de la categoría aparece en la query,
    asigna esa categoría. Si ninguna matchea → "Sin Categorizar".
    """
    if sqp_df.empty:
        return sqp_df.copy()

    df = sqp_df.copy()
    categories = sorted(set(asin_category_map.values()))
    if not categories:
        df["cat"] = "Sin Categorizar"
        return df

    # Construir lookup categoría → lista de tokens (cada categoría es su propio token principal)
    cat_tokens = {c: c.lower().split() for c in categories}

    def match_cat(q: str) -> str:
        q_lower = str(q).lower()
        # Priorizar match más largo (ej: "hat band western" > "hat")
        matches = []
        for cat, tokens in cat_tokens.items():
            if all(t in q_lower for t in tokens):
                matches.append((len(cat), cat))
        if matches:
            matches.sort(reverse=True)
            return matches[0][1]
        return "Sin Categorizar"

    df["cat"] = df["q"].apply(match_cat)
    return df


def enrich_br(
    br_df: pd.DataFrame,
    asin_sku_map: dict[str, str],
    asin_category_map: dict[str, str],
) -> pd.DataFrame:
    """Aplica SKU (fallback ASIN) y categoría a cada fila del BR."""
    if br_df.empty:
        return br_df.copy()

    df = br_df.copy()
    df["sku"] = df["asin"].map(asin_sku_map).fillna(df["asin"])
    df["cat"] = df["asin"].map(asin_category_map).fillna("Sin Categorizar")
    return df


# ══════════════════════════════════════════════════════════════════════════════
# JSON BUILDERS — producen las estructuras que el template consume
# ══════════════════════════════════════════════════════════════════════════════

_SQP_FIELDS = ["q","cat","mk","score","vol","impT","impB","impBS","clkT","clkR",
               "clkB","clkBS","cartT","cartR","cartB","cartBS","purT","purR","purB","purBS"]


def build_raw_json(sqp_df: pd.DataFrame) -> list[dict]:
    """Convierte df enriquecido → lista de dicts con el shape que RAW espera."""
    if sqp_df.empty:
        return []

    df = sqp_df.copy()
    # Asegurar todas las columnas presentes
    for col in _SQP_FIELDS:
        if col not in df.columns:
            df[col] = 0 if col not in ("q","cat","mk") else ""

    df = df[_SQP_FIELDS]

    # Round numéricos para minimizar tamaño del JSON
    for col in ["impBS","clkR","clkBS","cartR","cartBS","purR","purBS"]:
        df[col] = df[col].astype(float).round(2)
    for col in ["score","vol","impT","impB","clkT","clkB","cartT","cartB","purT","purB"]:
        df[col] = df[col].astype(float).round(0).astype("Int64")

    return df.to_dict(orient="records")


_BR_FIELDS = ["wk","sku","asin","title","cat","sess","pv","units","usp","sales","items","bb"]


def build_wow_json(br_df: pd.DataFrame) -> dict:
    """
    Convierte df BR enriquecido → {rows, week_dates, week_order}.
    """
    if br_df.empty:
        return {"rows": [], "week_dates": {}, "week_order": []}

    df = br_df.copy()
    for col in _BR_FIELDS:
        if col not in df.columns:
            df[col] = "" if col in ("wk","sku","asin","title","cat") else 0

    df = df[_BR_FIELDS]

    # Round
    for col in ["usp","bb"]:
        df[col] = df[col].astype(float).round(2)
    for col in ["sess","pv","units","items"]:
        df[col] = df[col].astype(float).round(0).astype("Int64")
    df["sales"] = df["sales"].astype(float).round(2)

    rows = df.to_dict(orient="records")

    weeks = sorted(set(r["wk"] for r in rows if r["wk"]), key=_week_sort_key)
    week_dates = {wk: _week_date_label(wk) for wk in weeks}

    return {
        "rows": rows,
        "week_dates": week_dates,
        "week_order": weeks,
    }


# ══════════════════════════════════════════════════════════════════════════════
# MAIN GENERATOR
# ══════════════════════════════════════════════════════════════════════════════

def _slug_client(name: str) -> str:
    """'Acme Inc.' → 'acme-inc'"""
    s = re.sub(r"[^\w\s-]", "", name.lower()).strip()
    s = re.sub(r"[\s_]+", "-", s)
    return s or "cliente"


def generate_html(
    sqp_df: pd.DataFrame,
    br_df: pd.DataFrame,
    client_name: str,
    market: str = "US",
    generated_label: str | None = None,
) -> str:
    """
    Combina data + template → HTML final listo para descargar.

    Requiere que sqp_df y br_df YA estén enriquecidos con cat/sku vía enrich_*.
    """
    template = load_template()

    # Construir datasets
    raw = build_raw_json(sqp_df)
    wow = build_wow_json(br_df)

    # Meses presentes en RAW
    months = sorted(set(r["mk"] for r in raw if r["mk"]))
    month_labels = {mk: _month_label_short(mk) for mk in months}
    month_names = {mk: _month_label_long(mk) for mk in months}

    # Metadata del hero
    if generated_label is None:
        now = datetime.now()
        generated_label = f"{_MESES_ES_CORTO[now.month-1]} {now.year}"

    # WoW week summary
    weeks = wow["week_order"]
    if weeks:
        first_wk = weeks[0].replace("Wk", "Wk").replace("-", "/")
        last_wk = weeks[-1].replace("Wk", "Wk").replace("-", "/")
        wow_range = f"{first_wk} – {last_wk}"
        default_active_week = weeks[-1]  # última semana
    else:
        wow_range = "—"
        default_active_week = ""

    # Reemplazo de placeholders
    # NOTA: los JSON van como literales JS válidos (json.dumps los deja con " correctas).
    replacements = {
        "{{RAW_JSON}}": json.dumps(raw, ensure_ascii=False, default=str),
        "{{WOW_JSON}}": json.dumps(wow, ensure_ascii=False, default=str),
        "{{ALL_MONTHS_JSON}}": json.dumps(months),
        "{{MONTH_LABELS_JSON}}": json.dumps(month_labels, ensure_ascii=False),
        "{{MONTH_NAMES_JSON}}": json.dumps(month_names, ensure_ascii=False),
        "{{CLIENT_LABEL}}": f"{client_name.upper()} Analytics",
        "{{CLIENT_NAME}}": client_name.upper(),
        "{{MARKET}}": market,
        "{{GENERATED_DATE}}": generated_label,
        "{{WOW_WEEK_COUNT}}": str(len(weeks)),
        "{{WOW_WEEK_RANGE}}": wow_range,
        "{{DEFAULT_ACTIVE_WEEK}}": default_active_week,
    }

    html = template
    for ph, val in replacements.items():
        html = html.replace(ph, val)

    return html


def get_filename(client_name: str) -> str:
    """'Gamboa' → 'gamboa_reporte_integral_abril-2026.html'"""
    slug = _slug_client(client_name)
    now = datetime.now()
    mes = _MESES_ES_CORTO[now.month-1].lower()
    return f"{slug}_reporte_integral_{mes}-{now.year}.html"
