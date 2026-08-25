#!/usr/bin/env python3
"""
Migración one-shot: HTML de "Reporte de Progreso por SKU" (formato de Marcos)
-> M28 SKU Progress Report (tracked-skus + snapshots semanales + optimizaciones).

Reutiliza las funciones REALES de persistencia del módulo, así el output
respeta el schema sku-progress-v1 exacto y pasa la validación.

ARGUMENTOS:
    --html      (obligatorio) Ruta al HTML del reporte.
    --cliente   (obligatorio) Slug del cliente en kebab-case. Ej: gamboa
    --year      (opcional)    Año calendario de la data. Default: 2026
    --dry-run   (opcional)    No escribe nada, solo muestra el plan.

USO (desde cualquier cwd, con el venv activo; el script se ubica solo):

    # 1) Dry-run: NO escribe nada, solo muestra el plan
    python scripts/migrate_m28_sku_progress_from_html.py \\
        --html "C:\\ruta\\Reporte_SKU.html" --cliente gamboa --dry-run

    # 2) En firme:
    python scripts/migrate_m28_sku_progress_from_html.py \\
        --html "C:\\ruta\\Reporte_SKU.html" --cliente gamboa

    # 3) Otro cliente y otro año calendario:
    python scripts/migrate_m28_sku_progress_from_html.py \\
        --html "C:\\ruta\\Reporte_SKU.html" --cliente otro-cliente --year 2027

Idempotencia:
  - tracked-skus: se reescribe entero (merge con lo existente por sku).
  - snapshots:    _save_snapshot sobreescribe por period -> seguro re-correr.
  - optimizations: append-only. El script chequea el log existente y NO
                   re-inserta un evento (sku, week_iso, year, label) ya presente.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

import pandas as pd

# --- Bootstrap: este script vive en scripts/, el repo es el directorio padre.
# Sin esto, `python scripts/migrate_...py` pone scripts/ en sys.path[0] y el
# import de `core` falla. El chdir (en main) es necesario aparte porque
# core.data_root.DATA_ROOT es relativo -- Path("data") -- salvo que se setee
# AGENCY_OS_DATA_DIR: sin el chdir la data del cliente caeria en el cwd del
# caller en vez de en data/ del repo.
_REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO_ROOT))

# --- Imports del proyecto (requiere el venv activo) -------------------------
try:
    from core.persistence import (
        _append_log,
        _load_client_config,
        _load_log,
        _rebuild_history,
        _save_client_config,
        _save_snapshot,
        _validate_against_schema,
    )
except ImportError as e:
    print("ERROR: no se pudieron importar los helpers del proyecto.")
    print("Corré este script desde la raíz del repo (o el worktree) con el venv activo.")
    print(f"Detalle: {e}")
    sys.exit(1)

# --- Constantes del módulo M28 (espejo de sku_progress_report.py) -----------
AREA = "account-health"
MODULE_SLUG = "sku-progress"
SCHEMA_VERSION = 1
SIN_CATEGORIA = "SIN_CATEGORIA"
# Decisión Lenin: la data histórica es toda 2026 (el "2025" del HTML era typo).
DEFAULT_YEAR = 2026

# Columnas del schema sku-progress-v1 (espejo de _build_snapshot_df)
INT_COLS = ["week_iso", "year", "sessions", "page_views",
            "units_ordered", "total_order_items"]
FLOAT_COLS = ["unit_session_pct", "ordered_product_sales", "avg_price"]
STR_COLS = ["sku", "asin", "title", "image_url", "link", "week_label"]

MONTHS_ES = ["", "Ene", "Feb", "Mar", "Abr", "May", "Jun",
             "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def _iso_week_dates(year: int, week_iso: int):
    """(lunes, domingo) de la semana ISO. Espejo de _iso_week_dates del módulo."""
    monday = date.fromisocalendar(year, week_iso, 1)
    sunday = date.fromisocalendar(year, week_iso, 7)
    return monday, sunday


def _week_label_es(year: int, week_iso: int) -> str:
    """Label 'Ene 4-10' / 'Mar 29-Abr 4'. Espejo EXACTO de _week_label_es del módulo
    (SIN prefijo 'Wk N —')."""
    start, end = _iso_week_dates(year, week_iso)
    m_start = MONTHS_ES[start.month]
    m_end = MONTHS_ES[end.month]
    if start.month == end.month:
        return f"{m_start} {start.day}-{end.day}"
    return f"{m_start} {start.day}-{m_end} {end.day}"


def _period_str(year: int, week_iso: int) -> str:
    return f"{year}-W{week_iso:02d}"


def _extract_asin(link: str) -> str:
    """Saca el ASIN de un link de Amazon (/gp/product/XXXX o /dp/XXXX)."""
    if not link:
        return ""
    m = re.search(r'/(?:product|dp)/([A-Z0-9]{10})', link)
    return m.group(1) if m else ""


def _load_html_data(path: str) -> dict:
    """Extrae el `const DATA = {...};` embebido en el HTML de Marcos."""
    with open(path, encoding="utf-8") as f:
        html = f.read()
    m = re.search(r'const DATA\s*=\s*(\{.*?\n\});', html, re.DOTALL)
    if not m:
        raise SystemExit("No se encontró `const DATA = {...};` en el HTML.")
    return json.loads(m.group(1))


def _build_tracked_skus(data: dict, existing: dict, year: int) -> dict:
    """Arma el config tracked-skus mergeando con lo que ya haya (por sku)."""
    by_sku = {s["sku"]: s for s in existing.get("skus", [])}
    for sku_key, d in data.items():
        weeks = sorted(int(w) for w in d.get("weeks", {}).keys())
        first_period = _period_str(year, weeks[0]) if weeks else _period_str(year, 1)
        entry = {
            "sku":       sku_key,
            "asin":      _extract_asin(d.get("link", "") or ""),
            "title":     d.get("title", sku_key) or sku_key,
            "image_url": d.get("image", "") or "",
            "link":      d.get("link", "") or "",
            "added_at":  first_period,
        }
        # Si ya existía, preservamos added_at previo (no lo pisamos)
        if sku_key in by_sku and by_sku[sku_key].get("added_at"):
            entry["added_at"] = by_sku[sku_key]["added_at"]
        by_sku[sku_key] = entry
    return {"skus": list(by_sku.values())}


def _build_week_snapshots(data: dict, year: int) -> dict[int, pd.DataFrame]:
    """Pivotea: {week_iso -> DataFrame con una fila por SKU con data esa semana}."""
    meta = {
        sku: {
            "asin":      _extract_asin(d.get("link", "") or ""),
            "title":     d.get("title", sku) or sku,
            "image_url": d.get("image", "") or "",
            "link":      d.get("link", "") or "",
        }
        for sku, d in data.items()
    }
    by_week: dict[int, list[dict]] = {}
    for sku, d in data.items():
        for wk_str, m in d.get("weeks", {}).items():
            wk = int(wk_str)
            by_week.setdefault(wk, []).append({
                "sku":                   sku,
                "asin":                  meta[sku]["asin"],
                "title":                 meta[sku]["title"],
                "image_url":             meta[sku]["image_url"],
                "link":                  meta[sku]["link"],
                "week_iso":              wk,
                "year":                  year,
                "week_label":            _week_label_es(year, wk),
                "sessions":              m.get("sessions", 0) or 0,
                "page_views":            m.get("page_views", 0) or 0,
                "units_ordered":         m.get("units_ordered", 0) or 0,
                "total_order_items":     m.get("total_order_items",
                                                m.get("units_ordered", 0)) or 0,
                "unit_session_pct":      m.get("unit_session_pct", 0.0) or 0.0,
                "ordered_product_sales": m.get("ordered_product_sales", 0.0) or 0.0,
                "avg_price":             m.get("avg_price", 0.0) or 0.0,
            })

    snapshots: dict[int, pd.DataFrame] = {}
    for wk, rows in by_week.items():
        df = pd.DataFrame(rows)
        for c in INT_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype("int64")
        for c in FLOAT_COLS:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0).astype("float64")
        for c in STR_COLS:
            df[c] = df[c].astype(str)
        snapshots[wk] = df
    return snapshots


def _collect_events(data: dict, year: int) -> list[dict]:
    """Lista de eventos de optimización a insertar en el log."""
    out = []
    for sku, d in data.items():
        for ev in d.get("events", []):
            out.append({
                "sku":      sku,
                "week_iso": int(ev["week"]),
                "year":     year,
                "label":    (ev.get("label", "") or "").strip(),
                "category": SIN_CATEGORIA,
            })
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Migrar HTML de Reporte de Progreso por SKU (Marcos) -> M28")
    ap.add_argument("--html", required=True, help="Ruta al HTML de Marcos")
    ap.add_argument("--cliente", required=True,
                    help="Slug del cliente (kebab-case), ej: gamboa")
    ap.add_argument("--year", type=int, default=DEFAULT_YEAR,
                    help=f"Año calendario de la data (default {DEFAULT_YEAR})")
    ap.add_argument("--dry-run", action="store_true",
                    help="No escribe nada, solo muestra el plan")
    args = ap.parse_args()

    cliente = args.cliente
    year = args.year

    # Resolver el HTML contra el cwd del caller ANTES del chdir, para que una
    # ruta relativa siga funcionando.
    html_path = Path(args.html).expanduser().resolve()
    if not html_path.is_file():
        raise SystemExit(f"No existe el HTML: {html_path}")
    os.chdir(_REPO_ROOT)

    print(f"Cliente: {cliente} | Año: {year}")
    print(f"Repo:    {_REPO_ROOT}")

    data = _load_html_data(str(html_path))
    print(f"HTML parseado: {len(data)} SKUs.\n")

    # 1) tracked-skus
    existing_cfg = _load_client_config(AREA, cliente, MODULE_SLUG, "tracked-skus")
    tracked = _build_tracked_skus(data, existing_cfg, year)
    print(f"[1] tracked-skus: {len(tracked['skus'])} SKUs")
    for s in tracked["skus"]:
        print(f"      {s['sku']:18s} asin={s['asin']:12s} added_at={s['added_at']}")

    # 2) snapshots por semana
    snapshots = _build_week_snapshots(data, year)
    weeks_sorted = sorted(snapshots.keys())
    print(f"\n[2] snapshots: {len(snapshots)} semanas (W{weeks_sorted[0]}-W{weeks_sorted[-1]})")
    for wk in weeks_sorted:
        df = snapshots[wk]
        print(f"      {_period_str(year, wk)}: {len(df)} SKUs")

    # Validar cada snapshot contra el schema ANTES de escribir
    print("\n    Validando snapshots contra schema...")
    any_error = False
    for wk in weeks_sorted:
        errors = _validate_against_schema(snapshots[wk], MODULE_SLUG, SCHEMA_VERSION)
        if errors:
            any_error = True
            print(f"      [ERR] W{wk}: {errors}")
    if any_error:
        print("\n    ABORT: hay errores de schema. No se escribe nada.")
        sys.exit(1)
    print("    [OK] Todos los snapshots pasan el schema.")

    # 3) optimizaciones
    events = _collect_events(data, year)
    print(f"\n[3] optimizaciones: {len(events)} eventos")

    # Dedup contra el log existente
    existing_log = _load_log(AREA, cliente, MODULE_SLUG, "optimizations")
    existing_keys = set()
    if existing_log is not None and not existing_log.empty:
        for _, r in existing_log.iterrows():
            existing_keys.add((str(r.get("sku")), int(r.get("week_iso")),
                               int(r.get("year")), str(r.get("label"))))
    to_insert = [e for e in events
                 if (e["sku"], e["week_iso"], e["year"], e["label"]) not in existing_keys]
    print(f"      nuevos a insertar: {len(to_insert)} "
          f"(ya existían {len(events) - len(to_insert)})")

    if args.dry_run:
        print("\n=== DRY-RUN: no se escribió nada. ===")
        return

    # ---- ESCRITURA EN FIRME ----
    print("\n>>> Escribiendo...")

    _save_client_config(tracked, AREA, cliente, MODULE_SLUG, "tracked-skus")
    print("    [OK] tracked-skus guardado.")

    for wk in weeks_sorted:
        period = _period_str(year, wk)
        _save_snapshot(snapshots[wk], AREA, cliente, MODULE_SLUG, period)
    print(f"    [OK] {len(weeks_sorted)} snapshots guardados.")

    for e in to_insert:
        _append_log(row=e, area=AREA, cliente=cliente,
                    modulo=MODULE_SLUG, log_name="optimizations")
    print(f"    [OK] {len(to_insert)} optimizaciones insertadas.")

    _rebuild_history(AREA, cliente, MODULE_SLUG)
    print("    [OK] history reconstruido.")

    print("\n=== Migración completa. ===")


if __name__ == "__main__":
    main()
