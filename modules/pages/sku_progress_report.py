"""
Modulo: SKU Progress Report (M28)
Fuente: porteado de .claude/porting-sources/sku-progress-report.html
Seccion: Account Health
Version: v1
Autor original: companero PPC (HTML standalone Gamboa)
Porteado: 2026-05-07

Tracker semanal de progreso por SKU. Multi-cliente. Persiste:
- Snapshots semanales en data/account-health/<cliente>/sku-progress/<YYYY-WW>.parquet
- Log append-only de optimizaciones en optimizations.parquet
- Config de SKUs trackeados en tracked-skus.json (excepcion documentada — JSON
  per-cliente fuera de _save_config porque _save_config es client-agnostic)

Caso 2 del porter (HTML con persistencia simple): la data embedded del HTML
original fue reemplazada por capa de persistencia centralizada via core.persistence.
Schema validado: data/_schemas/sku-progress-v1.json.
"""
from __future__ import annotations

import io
import json
import re
import shutil
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.helpers import kpi_card
from core.persistence import (
    DATA_ROOT,
    _append_log,
    _list_periods,
    _load_history,
    _load_log,
    _rebuild_history,
    _save_snapshot,
    _validate_against_schema,
)

try:
    import plotly.express as px
    import plotly.graph_objects as go
    _HAS_PLOTLY = True
except ImportError:
    _HAS_PLOTLY = False

try:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    _HAS_OPENPYXL = True
except ImportError:
    _HAS_OPENPYXL = False


# ── Constants ───────────────────────────────────────────────────────────

MODULE_SLUG = "sku-progress"
AREA = "account-health"
SCHEMA_VERSION = 1
YEAR_DEFAULT = 2026  # Decision Lenin v1: hardcoded 2026.

# Mapeo de columnas internas → header CSV (priority list, primer match gana).
# Espejo de CSV_PRIORITY del HTML L3236.
_CSV_PRIORITY: dict[str, list[str]] = {
    "sessions":              ["sessions - total", "sessions"],
    "page_views":            ["page views - total", "page views"],
    "units_ordered":         ["units ordered"],
    "total_order_items":     ["total order items"],
    "unit_session_pct":      [
        "unit session percentage",
        "unit session percentage - total",
        "order item session percentage",
    ],
    "ordered_product_sales": ["ordered product sales"],
    "_sku":                  ["sku"],
    "_asin":                 ["(child) asin", "child asin", "asin"],
}

# Columnas que el parser ignora (splits B2B/Mobile/Browser, métricas no relevantes).
# Espejo de CSV_IGNORE del HTML L3248.
_CSV_IGNORE: set[str] = {
    "sessions - mobile app", "sessions - mobile app - b2b",
    "sessions - browser", "sessions - browser - b2b",
    "sessions - total - b2b",
    "page views - mobile app", "page views - mobile app - b2b",
    "page views - browser", "page views - browser - b2b",
    "page views - total - b2b",
    "units ordered - b2b",
    "unit session percentage - b2b",
    "ordered product sales - b2b",
    "total order items - b2b",
    "session percentage - mobile app", "session percentage - mobile app - b2b",
    "session percentage - browser", "session percentage - browser - b2b",
    "session percentage - total", "session percentage - total - b2b",
    "page views percentage - mobile app", "page views percentage - mobile app - b2b",
    "page views percentage - browser", "page views percentage - browser - b2b",
    "page views percentage - total", "page views percentage - total - b2b",
    "featured offer (buy box) percentage", "featured offer (buy box) percentage - b2b",
    "(parent) asin", "parent asin", "title",
}

# KPIs que se grafican y muestran en la tabla
_KPI_KEYS = [
    "sessions", "page_views", "units_ordered", "total_order_items",
    "unit_session_pct", "ordered_product_sales", "avg_price",
]
_KPI_LABELS = {
    "sessions":              "Sessions",
    "page_views":            "Page Views",
    "units_ordered":         "Units Ordered",
    "total_order_items":     "Total Order Items",
    "unit_session_pct":      "Unit Session %",
    "ordered_product_sales": "Ordered Product Sales",
    "avg_price":             "Avg Price",
}

# Paleta para anotaciones de eventos en charts (espejo EVENT_COLORS HTML L2429)
_EVENT_COLORS = ["#FF3300", "#4F8CFF", "#34d399", "#f59e0b", "#a78bfa", "#f472b6"]

# Categorías de optimización (campo opcional en eventos). Default SIN_CATEGORIA.
SIN_CATEGORIA = "Sin categoría"
EVENT_CATEGORIES = [
    "Main Image", "Imágenes secundarias", "Título", "Bullets",
    "A+ Content", "Precio", "Otro",
]
CATEGORY_COLORS = {
    "Main Image":            "#FF3300",
    "Imágenes secundarias":  "#E85B03",
    "Título":                "#4F8CFF",
    "Bullets":               "#34d399",
    "A+ Content":            "#a78bfa",
    "Precio":                "#f59e0b",
    "Otro":                  "#999999",
    SIN_CATEGORIA:           "#666666",
}

# Meses en español para week_label (espejo monthNames HTML L3389)
_MONTH_NAMES_ES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun",
                   "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


# ── Helpers cliente / config ────────────────────────────────────────────

def _list_clientes() -> list[str]:
    """Escanea data/account-health/*/sku-progress/ y devuelve slugs de clientes
    que ya tienen carpeta del modulo creada."""
    base = DATA_ROOT / AREA
    if not base.exists():
        return []
    out = []
    for p in sorted(base.iterdir()):
        if not p.is_dir():
            continue
        if (p / MODULE_SLUG).is_dir():
            out.append(p.name)
    return out


def _tracked_skus_path(cliente: str) -> Path:
    """Path canonico al config JSON del cliente."""
    return DATA_ROOT / AREA / cliente / MODULE_SLUG / "tracked-skus.json"


def _load_tracked_skus(cliente: str) -> dict:
    """Lee el JSON de SKUs trackeados. Devuelve estructura vacia si no existe.

    Excepcion documentada: NO usa _load_config porque _save_config/_load_config son
    client-agnostic. tracked-skus.json es per-cliente, vive bajo el mismo arbol que
    los snapshots para que un borrado total del cliente sea atomico.
    """
    p = _tracked_skus_path(cliente)
    if not p.exists():
        return {"version": 1, "cliente": cliente, "skus": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"version": 1, "cliente": cliente, "skus": []}


def _save_tracked_skus(cliente: str, config: dict) -> None:
    """Escribe el JSON de SKUs trackeados. Crea el directorio si no existe."""
    p = _tracked_skus_path(cliente)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        json.dumps(config, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _delete_cliente(cliente: str) -> dict:
    """Borra recursivamente data/account-health/<cliente>/ entero.

    Operacion DESTRUCTIVA e IRREVERSIBLE. Borra:
    - Todos los snapshots Parquet semanales
    - optimizations.parquet (log append-only)
    - tracked-skus.json (config)

    Devuelve dict con counts pre-delete para confirmacion UI:
    {
        'cliente': str,
        'snapshots_count': int,
        'tracked_skus_count': int,
        'optimizations_count': int,
        'deleted': bool
    }

    NO va en core/persistence.py por contrato del skill data-persistence-standard
    (regla 'cero borrados automaticos'). Excepcion documentada en CLAUDE.md M28
    porque la accion es disparada explicitamente por el usuario en UI con
    type-to-confirm, no automatica.
    """
    base = Path("data") / "account-health" / cliente
    if not base.exists():
        return {'cliente': cliente, 'deleted': False, 'error': 'cliente no existe en disco'}

    # Conteos pre-delete para feedback UI
    # Los archivos del modulo viven en sub-carpeta sku-progress/
    module_dir = base / MODULE_SLUG
    snapshots_count = len(list(module_dir.glob('20*-W*.parquet'))) if module_dir.exists() else 0

    # Optimizations via core.persistence (cero I/O directa al Parquet)
    try:
        optimizations_count = len(_load_log(AREA, cliente, MODULE_SLUG, "optimizations"))
    except Exception:
        optimizations_count = 0

    tracked_skus_count = 0
    tracked_path = module_dir / 'tracked-skus.json'
    if tracked_path.exists():
        try:
            config = json.loads(tracked_path.read_text(encoding='utf-8'))
            tracked_skus_count = len(config.get('skus', []))
        except Exception:
            pass

    # Borrado recursivo del cliente entero (todo Account Health del cliente)
    shutil.rmtree(base)

    # Invalidar caches relevantes
    _list_periods.clear()
    _load_history.clear()
    _load_log.clear()

    return {
        'cliente': cliente,
        'snapshots_count': snapshots_count,
        'tracked_skus_count': tracked_skus_count,
        'optimizations_count': optimizations_count,
        'deleted': True,
    }


def _slugify_cliente(name: str) -> str:
    """Convierte un nombre de cliente arbitrario a slug kebab-case ASCII."""
    s = name.strip().lower()
    # Normalizar acentos basicos
    repl = {"á": "a", "é": "e", "í": "i", "ó": "o", "ú": "u", "ñ": "n"}
    for k, v in repl.items():
        s = s.replace(k, v)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "cliente"


# ── Helpers fechas / weeks ──────────────────────────────────────────────

def _period_str(year: int, week_iso: int) -> str:
    """Construye el string period canonico ('2026-W14')."""
    return f"{year}-W{week_iso:02d}"


def _parse_period_str(period: str) -> tuple[int, int]:
    """Parsea '2026-W14' -> (2026, 14). Devuelve (YEAR_DEFAULT, 0) si invalido."""
    m = re.match(r"^(\d{4})-W(\d{1,2})$", period)
    if not m:
        return (YEAR_DEFAULT, 0)
    return (int(m.group(1)), int(m.group(2)))


def _iso_week_dates(year: int, week_iso: int) -> tuple[date, date]:
    """Devuelve (lunes, domingo) de la semana ISO."""
    try:
        monday = date.fromisocalendar(year, week_iso, 1)
        sunday = monday + timedelta(days=6)
        return monday, sunday
    except (ValueError, OverflowError):
        return (date(year, 1, 1), date(year, 1, 7))


def _week_label_es(year: int, week_iso: int) -> str:
    """Genera label legible 'Mar 29-Abr 4' o 'Abr 5-11' (rango ES)."""
    start, end = _iso_week_dates(year, week_iso)
    m_start = _MONTH_NAMES_ES[start.month - 1]
    m_end = _MONTH_NAMES_ES[end.month - 1]
    if start.month == end.month:
        return f"{m_start} {start.day}-{end.day}"
    return f"{m_start} {start.day}-{m_end} {end.day}"


def _detect_week_from_filename(filename: str) -> int | None:
    """Detecta numero ISO de semana desde el nombre del archivo.

    Patrones soportados (en orden):
      - '2026-W14', '2026_W14', 'W14', 'wk14', 'week14', 'semana14'
    """
    if not filename:
        return None
    name = filename.lower()
    patterns = [
        r"\d{4}[-_]w(\d{1,2})",
        r"(?:^|[^a-z])w(?:k|eek)?(\d{1,2})",
        r"semana[\s_-]*(\d{1,2})",
    ]
    for pat in patterns:
        m = re.search(pat, name)
        if m:
            wk = int(m.group(1))
            if 1 <= wk <= 53:
                return wk
    return None


# ── Parser CSV (replica parseCSV + buildPreview consolidacion del HTML) ─

@st.cache_data(show_spinner=False)
def _parse_csv_bytes(raw: bytes, filename: str) -> dict:
    """Parsea CSV/TSV de 'Detail Page Sales and Traffic By Child Item'.

    Replica literal de parseCSV() del HTML L3267-3332. Devuelve dict con:
      {"rows": [{...}], "error": None}  o
      {"rows": [], "error": "mensaje"}.

    Cada row tiene keys: _sku/_asin, sessions, page_views, units_ordered,
    total_order_items, unit_session_pct, ordered_product_sales, _id.
    """
    try:
        # Intentar UTF-8 con BOM-strip; fallback latin-1
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = raw.decode("latin-1", errors="replace")
    except Exception as e:
        return {"rows": [], "error": f"No se pudo decodificar el archivo: {e}"}

    if not text.strip():
        return {"rows": [], "error": "Archivo vacio."}

    # Detectar delimitador (priorizamos tab si esta en la primera linea)
    first_line = text.split("\n", 1)[0]
    delim = "\t" if "\t" in first_line else ","

    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return {"rows": [], "error": "Archivo sin filas."}

    # Buscar header row en las primeras 6 lineas (HTML L3276)
    header_idx = -1
    for i in range(min(len(lines), 6)):
        low = lines[i].lower()
        if "session" in low or "sku" in low or "asin" in low:
            header_idx = i
            break
    if header_idx == -1:
        return {
            "rows": [],
            "error": (
                "No se encontro fila de encabezados. Asegurate de exportar el "
                "reporte 'Detail Page Sales and Traffic By Child Item'."
            ),
        }

    # Parse headers (strip BOM, lowercase)
    raw_headers = [
        h.strip().strip('"').lower()
        for h in _split_csv_line(lines[header_idx].lstrip("﻿"), delim)
    ]

    # Build colIndex
    col_index: dict[str, int] = {}
    for internal_key, candidates in _CSV_PRIORITY.items():
        for cand in candidates:
            if cand in raw_headers:
                col_index[internal_key] = raw_headers.index(cand)
                break

    if "_sku" not in col_index and "_asin" not in col_index:
        return {"rows": [], "error": "No se encontro columna SKU o ASIN en el CSV."}
    if "sessions" not in col_index:
        return {
            "rows": [],
            "error": "No se encontro columna 'Sessions - Total' en el CSV.",
        }

    # Parse data rows
    rows: list[dict] = []
    for i in range(header_idx + 1, len(lines)):
        cells = _split_csv_line(lines[i], delim)
        if len(cells) < 3:
            continue
        row: dict = {}
        for key, ci in col_index.items():
            raw_val = cells[ci].strip().strip('"') if ci < len(cells) else ""
            if key in ("_sku", "_asin"):
                if raw_val:
                    row[key] = raw_val
            else:
                # Sanear $, %, comas
                cleaned = re.sub(r"[$%,]", "", raw_val)
                try:
                    row[key] = float(cleaned)
                except (ValueError, TypeError):
                    pass

        identifier = row.get("_sku") or row.get("_asin")
        if not identifier or "sessions" not in row:
            continue
        row["_id"] = identifier
        rows.append(row)

    if not rows:
        return {"rows": [], "error": "No se pudieron leer filas de datos validos."}
    return {"rows": rows, "error": None}


def _split_csv_line(line: str, delim: str) -> list[str]:
    """Splitter manual que respeta campos quoted con commas internas.
    Replica splitCSVLine() del HTML L3335.
    """
    result: list[str] = []
    cur = []
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
        elif ch == delim and not in_q:
            result.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    result.append("".join(cur))
    return result


def _consolidate_rows_by_sku(
    rows: list[dict],
    tracked_skus: list[dict],
) -> tuple[list[dict], list[dict]]:
    """Replica buildPreview() del HTML L3433-3482: matchea rows del CSV contra
    SKUs trackeados (incluso variantes), suma metricas aditivas, recalcula
    derivadas (CVR, avg_price) post-consolidacion.

    Returns:
        (matched, unmatched) — listas de dicts.

    Match strategy (HTML L3442-3444):
      1. Equality (case-insensitive) entre CSV_id y SKU trackeado
      2. Substring bidireccional (puede generar falsos positivos — bug heredado)
    """
    # Solo SKUs con ASIN no vacío entran al matching (guard contra envenenamiento
    # del fallback substring: si un SKU tiene asin="" el dict tendría clave ""
    # y "" in cualquier_string == True, consolidando TODOS los ASINs del CSV bajo él)
    sku_keys_upper = {
        s["asin"].upper(): s["sku"]
        for s in tracked_skus
        if s.get("asin", "").strip()
    }
    matched_map: dict[str, dict] = {}
    unmatched: list[dict] = []

    # Length minima para substring matching: ASINs Amazon son 10 chars, SKUs internos
    # suelen ser 6+ chars. Bajo este umbral, "in" genera falsos positivos en cascada.
    MIN_MATCH_LEN = 6

    for row in rows:
        rid = row["_id"].upper()
        sku_key = sku_keys_upper.get(rid)
        if not sku_key and len(rid) >= MIN_MATCH_LEN:
            for tk_upper, tk_orig in sku_keys_upper.items():
                if len(tk_upper) < MIN_MATCH_LEN:
                    continue
                if rid in tk_upper or tk_upper in rid:
                    sku_key = tk_orig
                    break

        if not sku_key:
            unmatched.append({"csv_id": row["_id"]})
            continue

        if sku_key not in matched_map:
            matched_map[sku_key] = {
                "sku_key": sku_key,
                "csv_ids": [row["_id"]],
                "sessions":              row.get("sessions", 0) or 0,
                "page_views":            row.get("page_views", 0) or 0,
                "units_ordered":         row.get("units_ordered", 0) or 0,
                "total_order_items":     row.get("total_order_items",
                                                 row.get("units_ordered", 0) or 0) or 0,
                "ordered_product_sales": row.get("ordered_product_sales", 0) or 0,
            }
        else:
            e = matched_map[sku_key]
            e["csv_ids"].append(row["_id"])
            e["sessions"]              += row.get("sessions", 0) or 0
            e["page_views"]            += row.get("page_views", 0) or 0
            e["units_ordered"]         += row.get("units_ordered", 0) or 0
            e["total_order_items"]     += row.get("total_order_items",
                                                  row.get("units_ordered", 0) or 0) or 0
            e["ordered_product_sales"] += row.get("ordered_product_sales", 0) or 0

    # Compute derived post-consolidacion (HTML L3473-3481)
    matched: list[dict] = []
    for e in matched_map.values():
        e["unit_session_pct"] = (
            round(e["units_ordered"] / e["sessions"] * 100, 2)
            if e["sessions"] > 0 else 0.0
        )
        e["avg_price"] = (
            round(e["ordered_product_sales"] / e["units_ordered"], 2)
            if e["units_ordered"] > 0 else 0.0
        )
        matched.append(e)

    return matched, unmatched


def _build_snapshot_df(
    matched: list[dict],
    tracked_skus: list[dict],
    year: int,
    week_iso: int,
) -> pd.DataFrame:
    """Construye DataFrame con el schema sku-progress-v1.

    Una fila por SKU consolidado. Columnas matchean el schema exactamente.
    """
    label = _week_label_es(year, week_iso)
    by_sku = {s["sku"]: s for s in tracked_skus}

    out_rows = []
    for e in matched:
        meta = by_sku.get(e["sku_key"], {})
        out_rows.append({
            "sku":                   e["sku_key"],
            "asin":                  meta.get("asin", "") or "",
            "title":                 meta.get("title", e["sku_key"]) or e["sku_key"],
            "image_url":             meta.get("image_url", "") or "",
            "link":                  meta.get("link", "") or "",
            "week_iso":              int(week_iso),
            "year":                  int(year),
            "week_label":            label,
            "sessions":              int(e["sessions"]),
            "page_views":            int(e["page_views"]),
            "units_ordered":         int(e["units_ordered"]),
            "total_order_items":     int(e["total_order_items"]),
            "unit_session_pct":      float(e["unit_session_pct"]),
            "ordered_product_sales": float(e["ordered_product_sales"]),
            "avg_price":             float(e["avg_price"]),
        })

    df = pd.DataFrame(out_rows)
    if df.empty:
        return df

    # Forzar dtypes que el schema espera
    int_cols = ["week_iso", "year", "sessions", "page_views",
                "units_ordered", "total_order_items"]
    for c in int_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
    float_cols = ["unit_session_pct", "ordered_product_sales", "avg_price"]
    for c in float_cols:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype("float64")
    str_cols = ["sku", "asin", "title", "image_url", "link", "week_label"]
    for c in str_cols:
        df[c] = df[c].astype(str)

    return df


def _coalesce_category(optimizations: pd.DataFrame) -> pd.DataFrame:
    """Rellena category ausente/nula/vacía con SIN_CATEGORIA. NO reescribe parquet.
    Filas viejas sin la columna se completan en lectura."""
    if optimizations.empty:
        return optimizations
    if "category" not in optimizations.columns:
        optimizations["category"] = SIN_CATEGORIA
    else:
        optimizations["category"] = (
            optimizations["category"].fillna(SIN_CATEGORIA).replace("", SIN_CATEGORIA)
        )
    return optimizations


# ── Helpers de UI / formato ─────────────────────────────────────────────

def _fmt_value(val, key: str) -> str:
    """Formato display de valores segun KPI key (replica fmt() HTML L2415)."""
    if val is None or pd.isna(val):
        return "—"
    if key in ("ordered_product_sales", "avg_price"):
        return f"${val:,.2f}"
    if key == "unit_session_pct":
        return f"{val:.2f}%"
    try:
        return f"{int(val):,}"
    except (ValueError, TypeError):
        return str(val)


def _pct_change(a, b) -> tuple[str, float]:
    """Calcula % change. Devuelve (texto formateado, valor numerico)."""
    if a is None or pd.isna(a) or a == 0:
        return ("—", 0.0)
    p = ((b - a) / a) * 100
    sign = "+" if p > 0 else ""
    return (f"{sign}{p:.1f}%", float(p))


def _event_color(idx: int) -> str:
    return _EVENT_COLORS[idx % len(_EVENT_COLORS)]


def _header():
    """Header estandar Account Health con emoji 🏥."""
    st.markdown("## 🏥 SKU Progress Report")
    st.caption(
        "📥 Inputs: CSV semanal 'Detail Page Sales and Traffic By Child Item' · "
        "Output: tracker semanal multi-cliente con log de optimizaciones"
    )
    st.divider()


def _empty_state_no_clientes():
    """Empty state cuando no hay clientes trackeados todavia."""
    st.markdown(
        "<div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;"
        " text-align: center; background: #FFF8F0;'>"
        "<h3 style='color: #E84000; margin-top: 0;'>📂 No hay clientes trackeados todavia</h3>"
        "<p style='color: #6B7280; margin: 0;'>"
        "Agrega el primer cliente y los primeros SKUs desde el boton de abajo."
        "</p>"
        "</div>",
        unsafe_allow_html=True,
    )


def _empty_state_no_skus(cliente: str):
    """Empty state cuando hay cliente seleccionado pero sin SKUs."""
    st.markdown(
        f"<div style='border: 2px dashed #FFD9B3; border-radius: 12px; padding: 32px;"
        f" text-align: center; background: #FFF8F0;'>"
        f"<h3 style='color: #E84000; margin-top: 0;'>📂 Cliente {cliente} sin SKUs trackeados</h3>"
        f"<p style='color: #6B7280; margin: 0;'>"
        f"Usa el boton 'Agregar SKU' para empezar el tracking."
        f"</p>"
        f"</div>",
        unsafe_allow_html=True,
    )
    st.markdown("")
    st.markdown("**Cuando agregues SKUs**, podras subir CSVs semanales de Amazon:")
    st.caption(
        "📍 Donde bajarlos: Seller Central → Reports → Business Reports → "
        "Detail Page Sales and Traffic By Child Item → Download CSV"
    )


# ── Excel export ────────────────────────────────────────────────────────

def _build_sku_progress_excel(
    cliente: str,
    history: pd.DataFrame,
    optimizations: pd.DataFrame,
) -> bytes:
    """Genera Excel multi-hoja con todo el tracking del cliente.

    Hojas:
      1. Resumen — un row por SKU con ultima semana
      2. Detalle — todos los snapshots concatenados
      3. Optimizaciones — log completo
      4-N. Una hoja por SKU con su evolucion semanal completa
    """
    if not _HAS_OPENPYXL:
        raise RuntimeError("openpyxl no disponible")

    wb = Workbook()
    # Borrar default sheet
    wb.remove(wb.active)

    accent = "E84000"
    header_fill = PatternFill(start_color=accent, end_color=accent, fill_type="solid")
    header_font = Font(bold=True, color="FFFFFF", size=11)
    title_font = Font(bold=True, size=14, color="1A1A1A")

    # Sheet 1: Resumen
    ws_res = wb.create_sheet("Resumen")
    ws_res["A1"] = f"SKU Progress — {cliente}"
    ws_res["A1"].font = title_font
    ws_res["A2"] = f"Snapshot al {date.today().isoformat()}"
    ws_res["A2"].font = Font(italic=True, size=9, color="6B7280")

    if not history.empty:
        # Tomar ultima fila por SKU
        latest = (
            history.sort_values(["sku", "_period"])
            .groupby("sku", as_index=False)
            .tail(1)
            .reset_index(drop=True)
        )
        cols = ["sku", "title", "week_label", "sessions", "page_views",
                "units_ordered", "unit_session_pct", "ordered_product_sales",
                "avg_price"]
        cols = [c for c in cols if c in latest.columns]
        # Header
        for j, c in enumerate(cols, start=1):
            cell = ws_res.cell(row=4, column=j, value=c)
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="left")
        # Body
        for i, row in enumerate(latest[cols].itertuples(index=False), start=5):
            for j, val in enumerate(row, start=1):
                ws_res.cell(row=i, column=j, value=val)
    else:
        ws_res["A4"] = "Sin snapshots todavia."

    # Sheet 2: Detalle (history)
    ws_det = wb.create_sheet("Detalle")
    if not history.empty:
        for j, c in enumerate(history.columns, start=1):
            cell = ws_det.cell(row=1, column=j, value=c)
            cell.fill = header_fill
            cell.font = header_font
        for i, row in enumerate(history.itertuples(index=False), start=2):
            for j, val in enumerate(row, start=1):
                ws_det.cell(row=i, column=j, value=val)
    else:
        ws_det["A1"] = "Sin detalle todavia."

    # Sheet 3: Optimizaciones
    ws_opt = wb.create_sheet("Optimizaciones")
    if not optimizations.empty:
        for j, c in enumerate(optimizations.columns, start=1):
            cell = ws_opt.cell(row=1, column=j, value=c)
            cell.fill = header_fill
            cell.font = header_font
        for i, row in enumerate(optimizations.itertuples(index=False), start=2):
            for j, val in enumerate(row, start=1):
                ws_opt.cell(row=i, column=j, value=val)
    else:
        ws_opt["A1"] = "Sin optimizaciones registradas."

    # Sheets 4..N: una por SKU
    if not history.empty:
        for sku in sorted(history["sku"].unique()):
            sku_df = (history[history["sku"] == sku]
                      .sort_values("_period")
                      .reset_index(drop=True))
            sheet_name = sku[:31] if len(sku) > 31 else sku  # Excel limit
            sheet_name = re.sub(r"[\\/?*\[\]:]", "_", sheet_name)
            try:
                ws_sku = wb.create_sheet(sheet_name)
            except ValueError:
                ws_sku = wb.create_sheet(f"SKU_{sku[:25]}")
            cols = ["_period", "week_label"] + _KPI_KEYS
            cols = [c for c in cols if c in sku_df.columns]
            for j, c in enumerate(cols, start=1):
                cell = ws_sku.cell(row=1, column=j, value=c)
                cell.fill = header_fill
                cell.font = header_font
            for i, row in enumerate(sku_df[cols].itertuples(index=False), start=2):
                for j, val in enumerate(row, start=1):
                    ws_sku.cell(row=i, column=j, value=val)

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ── Dialogos (st.dialog) ────────────────────────────────────────────────

@st.dialog("Agregar SKU")
def _dialog_add_sku(cliente: str):
    """Modal para agregar SKU al tracking. Replica openAddSku/confirmAddSku del HTML."""
    st.caption(f"Cliente: **{cliente}**")
    sku   = st.text_input("SKU *", key="sku_progress_add_sku", placeholder="DEMARPA0001S56")
    asin  = st.text_input("ASIN (opcional)", key="sku_progress_add_asin",
                          placeholder="B08XZRYLH6")
    title = st.text_input("Titulo del producto *", key="sku_progress_add_title")
    image_url = st.text_input("URL de imagen (opcional)", key="sku_progress_add_img",
                              placeholder="https://m.media-amazon.com/images/I/...")
    link  = st.text_input("Link Amazon (opcional)", key="sku_progress_add_link",
                          placeholder="https://www.amazon.com/gp/product/B08XZRYLH6")

    # Preview de imagen
    if image_url.strip():
        try:
            st.image(image_url.strip(), width=120)
        except Exception:
            st.caption("⚠️ No se pudo cargar la imagen.")

    col_cancel, col_ok = st.columns([1, 1])
    if col_cancel.button("Cancelar", key="sku_progress_add_cancel",
                         use_container_width=True):
        st.rerun()
    if col_ok.button("Agregar SKU", key="sku_progress_add_confirm",
                     type="primary", use_container_width=True):
        if not sku.strip():
            st.error("El SKU es obligatorio.")
            return
        if not title.strip():
            st.error("El titulo es obligatorio.")
            return
        config = _load_tracked_skus(cliente)
        if any(s["sku"] == sku.strip() for s in config["skus"]):
            st.error(f"El SKU '{sku.strip()}' ya existe en el tracking.")
            return
        # added_at en formato period (YYYY-WW de hoy)
        today = date.today()
        iso_year, iso_week, _ = today.isocalendar()
        added_period = _period_str(iso_year, iso_week)
        config["skus"].append({
            "sku":       sku.strip(),
            "asin":      asin.strip(),
            "title":     title.strip(),
            "image_url": image_url.strip(),
            "link":      link.strip(),
            "added_at":  added_period,
        })
        _save_tracked_skus(cliente, config)
        st.success(f"SKU '{sku.strip()}' agregado.")
        st.rerun()


@st.dialog("Editar SKU")
def _dialog_edit_sku(cliente: str, sku: str):
    """Modal para editar metadata del SKU. Replica openEditSku/confirmEditSku."""
    config = _load_tracked_skus(cliente)
    sku_obj = next((s for s in config["skus"] if s["sku"] == sku), None)
    if not sku_obj:
        st.error(f"SKU '{sku}' no encontrado.")
        return

    st.caption(f"Cliente: **{cliente}** · SKU: **{sku}**")
    title = st.text_input("Titulo", value=sku_obj.get("title", ""),
                          key="sku_progress_edit_title")
    asin  = st.text_input("ASIN", value=sku_obj.get("asin", ""),
                          key="sku_progress_edit_asin")
    image_url = st.text_input("URL de imagen",
                              value=sku_obj.get("image_url", ""),
                              key="sku_progress_edit_img")
    link  = st.text_input("Link Amazon", value=sku_obj.get("link", ""),
                          key="sku_progress_edit_link")

    if image_url.strip():
        try:
            st.image(image_url.strip(), width=120)
        except Exception:
            st.caption("⚠️ No se pudo cargar la imagen.")

    col_c, col_ok = st.columns([1, 1])
    if col_c.button("Cancelar", key="sku_progress_edit_cancel",
                    use_container_width=True):
        st.rerun()
    if col_ok.button("Guardar cambios", key="sku_progress_edit_confirm",
                     type="primary", use_container_width=True):
        sku_obj["title"]     = title.strip() or sku_obj.get("title", sku)
        sku_obj["asin"]      = asin.strip()
        sku_obj["image_url"] = image_url.strip()
        sku_obj["link"]      = link.strip()
        _save_tracked_skus(cliente, config)
        st.success("Cambios guardados.")
        st.rerun()


@st.dialog("Registrar optimizacion")
def _dialog_add_event(cliente: str, sku: str):
    """Modal para registrar/editar evento de optimizacion."""
    st.caption(f"Cliente: **{cliente}** · SKU: **{sku}**")

    periods = _list_periods(AREA, cliente, MODULE_SLUG)
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    current_period = _period_str(iso_year, iso_week)
    options = sorted(set(periods + [current_period]))

    default_idx = len(options) - 1 if options else 0
    period_sel = st.selectbox(
        "Semana de aplicacion",
        options=options,
        index=default_idx,
        format_func=lambda p: f"{p} — {_week_label_es(*_parse_period_str(p))}",
        key="sku_progress_event_period",
    )
    label = st.text_input(
        "Descripcion de la optimizacion *",
        placeholder="Cambio de imagenes / Update bullets / A+ Content nuevo",
        key="sku_progress_event_label",
    )
    category_sel = st.selectbox(
        "Categoría de la optimización",
        options=EVENT_CATEGORIES,
        index=EVENT_CATEGORIES.index("Otro"),
        key="sku_progress_event_category",
    )

    col_c, col_ok = st.columns([1, 1])
    if col_c.button("Cancelar", key="sku_progress_event_cancel",
                    use_container_width=True):
        st.rerun()
    if col_ok.button("Registrar", key="sku_progress_event_confirm",
                     type="primary", use_container_width=True):
        if not label.strip():
            st.error("La descripcion es obligatoria.")
            return
        year, week_iso = _parse_period_str(period_sel)
        _append_log(
            row={
                "sku":      sku,
                "week_iso": int(week_iso),
                "year":     int(year),
                "label":    label.strip(),
                "category": category_sel,
            },
            area=AREA,
            cliente=cliente,
            modulo=MODULE_SLUG,
            log_name="optimizations",
        )
        st.success(f"Optimizacion registrada en {period_sel}.")
        st.rerun()


@st.dialog("Confirmar borrado")
def _dialog_confirm_delete_sku(cliente: str, sku: str):
    """Modal de confirmacion para borrar SKU del tracking."""
    st.warning(
        f"¿Eliminar el SKU **{sku}** del tracking de **{cliente}**?\n\n"
        f"Esto borra el SKU del config. Los snapshots historicos (filas en "
        f"Parquet) NO se borran — el SKU desaparece de la UI pero la data "
        f"sigue en disco. Esta accion es reversible re-agregando el SKU."
    )
    col_c, col_ok = st.columns([1, 1])
    if col_c.button("Cancelar", key="sku_progress_del_sku_cancel",
                    use_container_width=True):
        st.rerun()
    if col_ok.button("Eliminar", key="sku_progress_del_sku_confirm",
                     type="primary", use_container_width=True):
        config = _load_tracked_skus(cliente)
        config["skus"] = [s for s in config["skus"] if s["sku"] != sku]
        _save_tracked_skus(cliente, config)
        st.success(f"SKU '{sku}' eliminado del tracking.")
        st.rerun()


@st.dialog("Agregar cliente nuevo")
def _dialog_add_cliente():
    """Modal para crear un nuevo cliente (genera carpeta data/account-health/<slug>/sku-progress/)."""
    name = st.text_input(
        "Nombre del cliente",
        placeholder="Ej: nombre de la marca o cliente",
        key="sku_progress_add_cliente_name",
    )
    if name.strip():
        slug = _slugify_cliente(name)
        st.caption(f"Slug generado: `{slug}`")
        existing = _list_clientes()
        if slug in existing:
            st.warning(f"El cliente '{slug}' ya existe.")

    col_c, col_ok = st.columns([1, 1])
    if col_c.button("Cancelar", key="sku_progress_add_cliente_cancel",
                    use_container_width=True):
        st.rerun()
    if col_ok.button("Crear cliente", key="sku_progress_add_cliente_confirm",
                     type="primary", use_container_width=True):
        if not name.strip():
            st.error("El nombre es obligatorio.")
            return
        slug = _slugify_cliente(name)
        if slug in _list_clientes():
            st.error(f"El cliente '{slug}' ya existe.")
            return
        # Crear estructura inicial
        _save_tracked_skus(slug, {"version": 1, "cliente": slug, "skus": []})
        st.success(f"Cliente '{slug}' creado. Ahora agregale SKUs.")
        st.rerun()


@st.dialog("⚠️ Borrar cliente entero")
def _dialog_borrar_cliente(cliente: str):
    """Modal de confirmacion type-to-confirm para borrar todo el tracking
    del cliente. Operacion irreversible: borra snapshots Parquet,
    optimizations.parquet, tracked-skus.json y la carpeta del cliente."""
    base = Path("data") / "account-health" / cliente
    if not base.exists():
        st.warning(f"El cliente '{cliente}' no existe en disco.")
        return

    # Preview de lo que se va a borrar (paths dentro de sub-carpeta sku-progress/)
    module_dir = base / MODULE_SLUG
    snapshots_count = len(list(module_dir.glob('20*-W*.parquet'))) if module_dir.exists() else 0

    tracked_path = module_dir / 'tracked-skus.json'
    tracked_skus_count = 0
    if tracked_path.exists():
        try:
            config = json.loads(tracked_path.read_text(encoding='utf-8'))
            tracked_skus_count = len(config.get('skus', []))
        except Exception:
            pass

    # Optimizations via core.persistence (cero I/O directa al Parquet)
    try:
        optimizations_count = len(_load_log(AREA, cliente, MODULE_SLUG, "optimizations"))
    except Exception:
        optimizations_count = 0

    st.error(
        f"**Accion destructiva e irreversible.** Vas a borrar:\n\n"
        f"- **{tracked_skus_count}** SKU(s) trackeados\n"
        f"- **{snapshots_count}** snapshot(s) semanal(es)\n"
        f"- **{optimizations_count}** optimizacion(es) loggeada(s)\n"
        f"- Todos los archivos en `data/account-health/{cliente}/`"
    )

    st.markdown(f"Para confirmar, escribi el nombre del cliente exacto: **`{cliente}`**")
    confirm_input = st.text_input(
        "Confirmacion",
        key=f"sku_progress_borrar_cliente_confirm_{cliente}",
        placeholder=cliente,
        label_visibility="collapsed",
    )

    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Cancelar",
                     key=f"sku_progress_borrar_cliente_cancel_{cliente}",
                     use_container_width=True):
            st.rerun()
    with col2:
        confirm_match = confirm_input.strip().lower() == cliente.lower()
        if st.button(
            "Borrar definitivamente",
            key=f"sku_progress_borrar_cliente_confirm_btn_{cliente}",
            disabled=not confirm_match,
            type="primary",
            use_container_width=True,
        ):
            result = _delete_cliente(cliente)
            if result.get('deleted'):
                # Reset selector para que no apunte a cliente recien borrado
                st.session_state.pop('sku_progress_cliente', None)
                st.success(
                    f"Cliente '{cliente}' borrado: "
                    f"{result['snapshots_count']} snapshots, "
                    f"{result['tracked_skus_count']} SKUs, "
                    f"{result['optimizations_count']} optimizaciones."
                )
                st.rerun()
            else:
                st.error(f"Error al borrar: {result.get('error', 'desconocido')}")


# ── Render por SKU (tab content) ────────────────────────────────────────

def _render_sku_tab(cliente: str, sku_meta: dict, history: pd.DataFrame,
                    optimizations: pd.DataFrame) -> None:
    """Renderiza el contenido de un tab por SKU.

    Replica buildTab() del HTML L2457-2578: hero, KPI cards, charts, tabla.
    """
    sku = sku_meta["sku"]
    sku_history = (history[history["sku"] == sku]
                   .sort_values(["year", "week_iso"])
                   .reset_index(drop=True)) if not history.empty else pd.DataFrame()
    sku_events = (optimizations[optimizations["sku"] == sku]
                  .sort_values(["year", "week_iso"])
                  .reset_index(drop=True)) if not optimizations.empty else pd.DataFrame()

    # Hero — imagen + titulo + acciones
    hero_l, hero_r = st.columns([1, 4])
    with hero_l:
        if sku_meta.get("image_url"):
            try:
                st.image(sku_meta["image_url"], width=130)
            except Exception:
                st.caption("📷 (imagen no disponible)")
        else:
            st.markdown(
                "<div style='width:130px;height:130px;background:#FAFAFA;"
                "border-radius:12px;display:flex;align-items:center;"
                "justify-content:center;color:#9CA3AF;'>📦</div>",
                unsafe_allow_html=True,
            )

    with hero_r:
        st.markdown(f"### {sku}")
        st.caption(sku_meta.get("title", sku))

        # Botones de accion
        col_evt, col_edit, col_del, col_link = st.columns([1.5, 1, 1, 1.2])
        if col_evt.button("➕ Registrar optimizacion",
                          key=f"sku_progress_btn_evt_{sku}",
                          use_container_width=True):
            _dialog_add_event(cliente, sku)
        if col_edit.button("✏️ Editar SKU",
                           key=f"sku_progress_btn_edit_{sku}",
                           use_container_width=True):
            _dialog_edit_sku(cliente, sku)
        if col_del.button("🗑️ Borrar",
                          key=f"sku_progress_btn_del_{sku}",
                          use_container_width=True):
            _dialog_confirm_delete_sku(cliente, sku)
        if sku_meta.get("link"):
            col_link.markdown(
                f"<a href='{sku_meta['link']}' target='_blank' "
                f"style='display:inline-block;padding:0.4rem 0.6rem;"
                f"background:#FFF3E0;border:1px solid #FFD9B3;border-radius:6px;"
                f"text-decoration:none;color:#E84000;font-size:0.78rem;"
                f"font-weight:600;text-align:center;width:100%;'>"
                f"🔗 Ver en Amazon</a>",
                unsafe_allow_html=True,
            )

    # Badges de eventos
    if not sku_events.empty:
        st.markdown("**Optimizaciones registradas:**")
        badges_html = "<div style='display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 16px 0;'>"
        for i, ev in enumerate(sku_events.itertuples(index=False)):
            col = CATEGORY_COLORS.get(getattr(ev, "category", None) or SIN_CATEGORIA, _event_color(i))
            wk_label = _week_label_es(int(ev.year), int(ev.week_iso))
            badges_html += (
                f"<div style='padding:4px 10px;border-radius:100px;"
                f"background:{col}18;border:1px solid {col}55;"
                f"color:{col};font-size:0.75rem;font-weight:600;'>"
                f"<span style='display:inline-block;width:6px;height:6px;"
                f"border-radius:50%;background:{col};margin-right:6px;"
                f"vertical-align:middle;'></span>"
                f"{ev.label} — {wk_label} (W{int(ev.week_iso)})"
                f"</div>"
            )
        badges_html += "</div>"
        st.markdown(badges_html, unsafe_allow_html=True)

    st.divider()

    # Empty state si no hay datos semanales
    if sku_history.empty:
        st.info(
            "📭 Sin datos semanales todavia. Sube un CSV de Amazon en la tab "
            "**Importar CSV** para que aparezcan los KPIs y graficos."
        )
        return

    # KPI cards: ultima semana vs primera y vs anterior
    first = sku_history.iloc[0]
    last = sku_history.iloc[-1]
    prev = sku_history.iloc[-2] if len(sku_history) >= 2 else None

    st.markdown(f"**Ultima semana cargada:** {last['week_label']} "
                f"(W{int(last['week_iso'])})  ·  "
                f"**Total semanas:** {len(sku_history)}")

    # 7 KPI cards en 2 filas
    kpi_grid_keys = _KPI_KEYS  # 7 keys
    cols_a = st.columns(4)
    cols_b = st.columns(4)
    all_cols = cols_a + cols_b
    for i, k in enumerate(kpi_grid_keys):
        if i >= len(all_cols):
            break
        text_first, _ = _pct_change(first[k], last[k])
        text_prev, val_prev = _pct_change(prev[k], last[k]) if prev is not None else ("—", 0.0)
        with all_cols[i]:
            st.markdown(
                kpi_card(
                    label=_KPI_LABELS[k],
                    value=_fmt_value(last[k], k),
                    delta=val_prev if prev is not None else None,
                    delta_good=True,
                ),
                unsafe_allow_html=True,
            )
            st.caption(f"vs primera: {text_first}  ·  vs anterior: {text_prev}")

    st.markdown("")

    # Charts (Plotly si esta disponible)
    if _HAS_PLOTLY:
        st.markdown("### 📈 Evolucion semanal")

        # Featured: CVR + Avg Price + Sessions cruzado
        labels = [f"W{int(w)}" for w in sku_history["week_iso"]]
        fig_feat = go.Figure()
        fig_feat.add_trace(go.Scatter(
            x=labels, y=sku_history["unit_session_pct"],
            name="CVR (%)", mode="lines+markers",
            line=dict(color="#E84000", width=3),
            yaxis="y",
        ))
        fig_feat.add_trace(go.Scatter(
            x=labels, y=sku_history["avg_price"],
            name="Avg Price ($)", mode="lines+markers",
            line=dict(color="#4F8CFF", width=2, dash="dot"),
            yaxis="y2",
        ))
        fig_feat.add_trace(go.Bar(
            x=labels, y=sku_history["sessions"],
            name="Sessions", opacity=0.25,
            marker=dict(color="#9CA3AF"),
            yaxis="y3",
        ))
        # Anotaciones por evento
        for i, ev in enumerate(sku_events.itertuples(index=False)):
            wk_label = f"W{int(ev.week_iso)}"
            if wk_label in labels:
                fig_feat.add_vline(
                    x=labels.index(wk_label),
                    line=dict(color=_event_color(i), width=1.5, dash="dash"),
                    annotation_text=ev.label[:20],
                    annotation_position="top",
                )
        fig_feat.update_layout(
            title="CVR / Avg Price / Sessions — evolucion cruzada",
            yaxis=dict(title="CVR (%)", side="left"),
            yaxis2=dict(title="Avg Price ($)", overlaying="y", side="right"),
            yaxis3=dict(overlaying="y", side="right", showgrid=False,
                        showticklabels=False, range=[0, sku_history["sessions"].max() * 3]),
            height=380,
            hovermode="x unified",
            legend=dict(orientation="h", y=-0.2),
            margin=dict(l=40, r=40, t=40, b=40),
        )
        st.plotly_chart(fig_feat, use_container_width=True)

        # 4 charts en grid 2x2
        chart_pairs = [
            ("sessions", "page_views"),
            ("units_ordered", "ordered_product_sales"),
            ("unit_session_pct", "avg_price"),
            ("total_order_items", None),
        ]
        c1, c2 = st.columns(2)
        c3, c4 = st.columns(2)
        slots = [c1, c2, c3, c4]
        for slot, (k1, k2) in zip(slots, chart_pairs):
            with slot:
                fig = go.Figure()
                fig.add_trace(go.Scatter(
                    x=labels, y=sku_history[k1],
                    name=_KPI_LABELS[k1],
                    mode="lines+markers",
                    line=dict(color="#E84000", width=2),
                ))
                if k2 is not None and k2 in sku_history.columns:
                    fig.add_trace(go.Scatter(
                        x=labels, y=sku_history[k2],
                        name=_KPI_LABELS[k2],
                        mode="lines+markers",
                        line=dict(color="#4F8CFF", width=2),
                        yaxis="y2",
                    ))
                title = (
                    f"{_KPI_LABELS[k1]} / {_KPI_LABELS[k2]}"
                    if k2 else _KPI_LABELS[k1]
                )
                fig.update_layout(
                    title=title,
                    yaxis=dict(title=_KPI_LABELS[k1], side="left"),
                    yaxis2=dict(title=_KPI_LABELS[k2] if k2 else "",
                                overlaying="y", side="right"),
                    height=280,
                    hovermode="x unified",
                    legend=dict(orientation="h", y=-0.25),
                    margin=dict(l=40, r=40, t=40, b=40),
                )
                # Anotar eventos
                for i, ev in enumerate(sku_events.itertuples(index=False)):
                    wk_label_ev = f"W{int(ev.week_iso)}"
                    if wk_label_ev in labels:
                        fig.add_vline(
                            x=labels.index(wk_label_ev),
                            line=dict(color=_event_color(i),
                                      width=1.2, dash="dash"),
                        )
                st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("Plotly no esta instalado — los graficos no se muestran.")

    # Tabla detallada (replica buildTab() L2554)
    st.markdown("### 📋 Datos semanales detallados")
    table_cols = ["week_iso", "week_label"] + _KPI_KEYS
    table_cols = [c for c in table_cols if c in sku_history.columns]
    display_df = sku_history[table_cols].copy()
    display_df = display_df.rename(columns={
        "week_iso":              "Semana ISO",
        "week_label":            "Fechas",
        "sessions":              _KPI_LABELS["sessions"],
        "page_views":            _KPI_LABELS["page_views"],
        "units_ordered":         _KPI_LABELS["units_ordered"],
        "total_order_items":     _KPI_LABELS["total_order_items"],
        "unit_session_pct":      _KPI_LABELS["unit_session_pct"],
        "ordered_product_sales": _KPI_LABELS["ordered_product_sales"],
        "avg_price":             _KPI_LABELS["avg_price"],
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True)


# ── Render Tab Importar CSV ─────────────────────────────────────────────

def _render_import_tab(cliente: str, tracked_skus: list[dict]):
    """Tab para subir CSV semanal y consolidar/persistir snapshot."""
    st.markdown("### 📤 Importar snapshot semanal")
    st.caption(
        "Sube el CSV de Seller Central → Reports → Business Reports → "
        "**Detail Page Sales and Traffic By Child Item**"
    )

    if not tracked_skus:
        st.warning(
            "Primero agrega SKUs al tracking. La importacion consolida "
            "rows del CSV contra la lista de SKUs trackeados."
        )
        return

    file = st.file_uploader(
        "CSV o TSV semanal",
        type=["csv", "tsv", "txt"],
        key="sku_progress_csv_uploader",
    )
    st.caption(
        "Subí el CSV tal cual lo exportás de Seller Central (Business Reports → "
        "Detail Page Sales and Traffic By Child Item). No lo abras ni lo re-guardes "
        "como .xlsx — el importador solo lee CSV / TSV / TXT."
    )
    if not file:
        st.info("Sube un archivo para previsualizar la importacion.")
        return

    raw = file.getvalue()
    parsed = _parse_csv_bytes(raw, file.name)
    if parsed["error"]:
        st.error(f"⚠ {parsed['error']}")
        return

    st.success(f"✓ {len(parsed['rows'])} filas leidas del CSV.")

    # Detectar week_iso del filename, sino pedirla
    auto_week = _detect_week_from_filename(file.name)
    today = date.today()
    iso_year, iso_week, _ = today.isocalendar()
    default_week = auto_week or iso_week

    col_y, col_w, col_lbl = st.columns([1, 1, 2])
    with col_y:
        year = st.number_input(
            "Año",
            min_value=2024, max_value=2030,
            value=YEAR_DEFAULT, step=1,
            key="sku_progress_import_year",
            help="V1 hardcoded a 2026 — editable por si el usuario carga retro.",
        )
    with col_w:
        week_iso = st.number_input(
            "Semana ISO",
            min_value=1, max_value=53,
            value=int(default_week), step=1,
            key="sku_progress_import_week",
            help=("Auto-detectada del filename" if auto_week else
                  "Sin auto-detect — defaulteada a la semana actual."),
        )
    with col_lbl:
        st.markdown(f"**Label:** `{_week_label_es(int(year), int(week_iso))}`")
        st.caption(f"Period: `{_period_str(int(year), int(week_iso))}`")

    # Consolidar
    matched, unmatched = _consolidate_rows_by_sku(parsed["rows"], tracked_skus)

    st.markdown("---")
    st.markdown(
        f"**Preview:** {len(matched)} SKU(s) reconocidos · "
        f"{len(unmatched)} no reconocidos"
    )

    if matched:
        prev_df = pd.DataFrame([{
            "SKU":           e["sku_key"],
            "Variantes":     len(e["csv_ids"]),
            "Sessions":      e["sessions"],
            "Page Views":    e["page_views"],
            "Units":         e["units_ordered"],
            "CVR%":          f"{e['unit_session_pct']:.2f}%",
            "Sales":         f"${e['ordered_product_sales']:,.2f}",
            "Avg Price":     f"${e['avg_price']:,.2f}",
        } for e in matched])
        st.dataframe(prev_df, use_container_width=True, hide_index=True)

    if unmatched:
        with st.expander(f"⚠️ {len(unmatched)} SKUs no reconocidos (se descartan)"):
            for u in unmatched:
                st.caption(f"• `{u['csv_id']}` — sin match en tracked-skus")

    if not matched:
        st.warning("No hay SKUs para importar. Verifica que los SKUs del CSV "
                   "coincidan con los trackeados.")
        return

    # Boton confirmar
    period = _period_str(int(year), int(week_iso))
    existing = _list_periods(AREA, cliente, MODULE_SLUG)
    overwrite_warning = (
        f"⚠️ Ya existe snapshot para **{period}** — el archivo sera sobrescrito."
        if period in existing else ""
    )
    if overwrite_warning:
        st.warning(overwrite_warning)

    if st.button("✓ Confirmar import", type="primary",
                 key="sku_progress_btn_confirm_import",
                 use_container_width=False):
        df = _build_snapshot_df(matched, tracked_skus, int(year), int(week_iso))
        # Validar contra schema
        errors = _validate_against_schema(df, MODULE_SLUG, SCHEMA_VERSION)
        if errors:
            st.error("⚠️ El snapshot no respeta el schema:")
            for e in errors:
                st.caption(f"• {e}")
            return
        _save_snapshot(df, AREA, cliente, MODULE_SLUG, period)
        try:
            _rebuild_history(AREA, cliente, MODULE_SLUG)
        except FileNotFoundError:
            pass
        st.success(
            f"✓ Snapshot {period} guardado · {len(df)} SKU(s) consolidados."
        )
        st.rerun()


# ── Render Tab Admin (semanas + SKUs) ───────────────────────────────────

def _render_admin_tab(cliente: str, tracked_skus: list[dict]):
    """Tab admin: lista semanas + SKUs trackeados con accion de borrar.

    Replica openDelWeeks del HTML pero como tab dedicada (no modal).
    """
    st.markdown("### ⚙️ Administrar semanas y SKUs")

    col_left, col_right = st.columns(2)

    with col_left:
        st.markdown("#### Semanas con snapshot")
        periods = _list_periods(AREA, cliente, MODULE_SLUG)
        if not periods:
            st.caption("Sin snapshots todavia.")
        else:
            for p in periods:
                col_info, col_del = st.columns([3, 1])
                year, week_iso = _parse_period_str(p)
                col_info.markdown(
                    f"**{p}** — {_week_label_es(year, week_iso)}"
                )
                if col_del.button("🗑️", key=f"sku_progress_del_period_{p}",
                                  help="Borrar este snapshot"):
                    target = (DATA_ROOT / AREA / cliente / MODULE_SLUG /
                              f"{p}.parquet")
                    if target.exists():
                        target.unlink()
                        try:
                            _rebuild_history(AREA, cliente, MODULE_SLUG)
                        except FileNotFoundError:
                            # Si era el unico, borrar history tambien
                            hist = (DATA_ROOT / AREA / cliente / MODULE_SLUG /
                                    "_history.parquet")
                            if hist.exists():
                                hist.unlink()
                        # Invalidar caches que apuntaban al snapshot borrado
                        _list_periods.clear()
                        _load_history.clear()
                        st.success(f"Snapshot {p} eliminado.")
                        st.rerun()

    with col_right:
        st.markdown("#### SKUs trackeados")
        if not tracked_skus:
            st.caption("Sin SKUs todavia. Usa 'Agregar SKU'.")
        else:
            for s in tracked_skus:
                col_info, col_del = st.columns([3, 1])
                col_info.markdown(f"**{s['sku']}** — {s.get('title', s['sku'])[:50]}")
                if col_del.button("🗑️", key=f"sku_progress_del_sku_{s['sku']}",
                                  help="Quitar SKU del tracking"):
                    _dialog_confirm_delete_sku(cliente, s["sku"])


# ── Render principal ────────────────────────────────────────────────────

def render() -> None:
    """Punto de entrada del modulo. Llamado desde app.py.

    UN solo return: solo se hace early-return si no hay clientes o no hay SKUs.
    """
    _header()

    # Selector de cliente al tope
    clientes = _list_clientes()

    col_sel, col_add, col_del = st.columns([5, 2, 2])
    with col_sel:
        if clientes:
            cliente = st.selectbox(
                "Cliente",
                options=clientes,
                key="sku_progress_cliente",
                format_func=lambda c: f"📦 {c}",
            )
        else:
            cliente = None
            st.caption("No hay clientes trackeados todavia.")
    with col_add:
        st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
        if st.button("➕ Cliente nuevo",
                     key="sku_progress_btn_add_cliente",
                     use_container_width=True):
            _dialog_add_cliente()
    with col_del:
        st.markdown("&nbsp;", unsafe_allow_html=True)  # spacer
        if cliente and st.button("🗑️ Borrar cliente",
                                  key="sku_progress_btn_borrar_cliente",
                                  use_container_width=True,
                                  help="Borrar todo el tracking de este cliente (irreversible)"):
            _dialog_borrar_cliente(cliente)

    if not clientes or not cliente:
        _empty_state_no_clientes()
        return

    st.divider()

    # Cargar config y data del cliente seleccionado
    config = _load_tracked_skus(cliente)
    tracked_skus = config.get("skus", [])

    history = _load_history(AREA, cliente, MODULE_SLUG)
    optimizations = _load_log(AREA, cliente, MODULE_SLUG, "optimizations")
    optimizations = _coalesce_category(optimizations)  # coalesce category en lectura

    # Botones top-bar (Agregar SKU + Export)
    col_a, col_b, col_c = st.columns([1.5, 1.5, 4])
    with col_a:
        if st.button("➕ Agregar SKU",
                     key="sku_progress_btn_add_sku",
                     use_container_width=True,
                     type="primary"):
            _dialog_add_sku(cliente)
    with col_b:
        if not history.empty:
            try:
                xlsx_bytes = _build_sku_progress_excel(
                    cliente, history, optimizations
                )
                today = date.today()
                iso_year, iso_week, _ = today.isocalendar()
                fname = (
                    f"{cliente}_SKU-Progress_"
                    f"{_period_str(iso_year, iso_week)}.xlsx"
                )
                st.download_button(
                    "⬇️ Excel completo",
                    data=xlsx_bytes,
                    file_name=fname,
                    mime=("application/vnd.openxmlformats-officedocument."
                          "spreadsheetml.sheet"),
                    key="sku_progress_dl_excel",
                    use_container_width=True,
                )
            except Exception as e:
                st.caption(f"⚠️ Error generando Excel: {e}")
        else:
            st.button("⬇️ Excel completo", disabled=True,
                      use_container_width=True,
                      key="sku_progress_dl_excel_disabled",
                      help="Sin datos todavia.")

    if not tracked_skus:
        _empty_state_no_skus(cliente)
        # Permitir usar la tab Admin para borrar cliente o seguir
        return

    # Tabs principales: una por SKU + Importar CSV + Admin
    tab_labels = [f"📦 {s['sku']}" for s in tracked_skus]
    tab_labels.append("📤 Importar CSV")
    tab_labels.append("⚙️ Admin")

    tabs = st.tabs(tab_labels)

    # Tabs por SKU
    for i, sku_meta in enumerate(tracked_skus):
        with tabs[i]:
            _render_sku_tab(cliente, sku_meta, history, optimizations)

    # Tab importar
    with tabs[len(tracked_skus)]:
        _render_import_tab(cliente, tracked_skus)

    # Tab admin
    with tabs[len(tracked_skus) + 1]:
        _render_admin_tab(cliente, tracked_skus)
