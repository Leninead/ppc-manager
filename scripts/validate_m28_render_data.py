"""
Validacion programatica M28 — Script 1: consolidacion de variantes / KPIs render.

Objetivo: confirmar que la consolidacion de las 2 variantes de GAMB-CREMA-200G
(y el resto de SKUs) produce KPIs numericamente correctos en el snapshot W18
persistido. Pre-valida la "Validacion Visual 1" (render del tab por SKU) sin UI.

Que valida:
  - El snapshot W18 (data render de la UI) consolida bien las 2 variantes de
    GAMB-CREMA-200G: sessions/page_views/units_ordered/total_order_items/sales
    sumadas == valores del Parquet.
  - Sanity check identico para GAMB-SERUM-50ML y GAMB-OIL-30ML (1 variante c/u).
  - Derivadas recalculadas (unit_session_pct, avg_price) coinciden.
  - No hay valores negativos ni _id NaN/vacio en las filas parseadas.
  - Los 2 SKUs no-trackeados del CSV quedan como unmatched (no contaminan).

Fuente de verdad cruzada: el CSV seed
'Gamboa_DetailPageSalesTraffic_2026-W18.csv' (Downloads) re-parseado y
consolidado con las funciones REALES del modulo vs. el snapshot ya persistido.

Usage:
    python scripts/validate_m28_render_data.py

Exit 0 si todo consistente; exit 1 al primer hallazgo inconsistente.
"""
from __future__ import annotations

import logging
import os
import sys
import warnings
from pathlib import Path


# ── Bootstrap: code root (worktree M28) + data root (repo con gamboa) ────────

def _bootstrap() -> tuple[Path, Path]:
    """Configura sys.path al worktree M28 y chdir al repo que tiene la data de
    gamboa. Devuelve (repo_root_codigo, data_repo). Sale 1 si no encuentra data.
    """
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    sys.path.insert(0, str(repo_root))

    rel = Path("data") / "account-health" / "gamboa" / "sku-progress"
    candidates = [repo_root, Path(r"C:/proyectos/ppc-manager")]
    data_repo = next((c for c in candidates if (c / rel).is_dir()), None)
    if data_repo is None:
        print("FATAL: no encontre data/account-health/gamboa/sku-progress en:")
        for c in candidates:
            print(f"   - {c}")
        sys.exit(1)
    os.chdir(data_repo)

    # Silenciar warnings de Streamlit fuera de runtime (funciones @st.cache_data).
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    return repo_root, data_repo


REPO_ROOT, DATA_REPO = _bootstrap()

from core.persistence import _load_snapshot  # noqa: E402
from modules.pages.sku_progress_report import (  # noqa: E402
    AREA,
    MODULE_SLUG,
    _consolidate_rows_by_sku,
    _load_tracked_skus,
    _parse_csv_bytes,
)

CLIENTE = "gamboa"
PERIOD = "2026-W18"
TOL = 0.01  # tolerancia para comparaciones float
_KPI_SUM_KEYS = [
    "sessions", "page_views", "units_ordered",
    "total_order_items", "ordered_product_sales",
]


# ── Helpers ──────────────────────────────────────────────────────────────

def _find_seed_csv() -> Path | None:
    """Localiza el CSV seed W18 (Downloads, con fallback glob)."""
    direct = Path(r"C:/Users/lenin/Downloads/Gamboa_DetailPageSalesTraffic_2026-W18.csv")
    if direct.is_file():
        return direct
    dl = Path(r"C:/Users/lenin/Downloads")
    if dl.is_dir():
        hits = sorted(dl.glob("Gamboa*DetailPage*W18*.csv"))
        if hits:
            return hits[0]
    return None


def _rows_for_sku(rows: list[dict], sku_meta: dict) -> list[dict]:
    """Devuelve las filas RAW del CSV que matchean este SKU, replicando la
    estrategia de match del modulo (equality upper, luego substring >= 6 chars).
    Sirve para mostrar las variantes individuales antes de consolidar.
    """
    key = (sku_meta.get("asin") or sku_meta.get("sku") or "").strip().upper()
    if not key:
        return []
    out = []
    MIN = 6
    for r in rows:
        rid = str(r.get("_id", "")).upper()
        if not rid:
            continue
        hit = rid == key
        if not hit and len(rid) >= MIN and len(key) >= MIN:
            hit = rid in key or key in rid
        if hit:
            out.append(r)
    return out


class _Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, cond: bool, msg: str) -> None:
        flag = "OK " if cond else "FAIL"
        print(f"   [{flag}] {msg}")
        if not cond:
            self.failures.append(msg)


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> int:
    print("=" * 72)
    print("VALIDACION M28 — Script 1: consolidacion variantes / KPIs render")
    print("=" * 72)
    print(f"Codigo importado de : {REPO_ROOT}")
    print(f"Data leida de       : {DATA_REPO}")
    print(f"Cliente / period    : {CLIENTE} / {PERIOD}")

    chk = _Checker()

    # 1. Cargar snapshot persistido (lo que la UI renderiza)
    snap = _load_snapshot(AREA, CLIENTE, MODULE_SLUG, PERIOD)
    if snap is None or snap.empty:
        print(f"FATAL: snapshot {PERIOD} no existe o esta vacio.")
        return 1
    snap_by_sku = {r["sku"]: r for _, r in snap.iterrows()}

    # 2. Localizar y parsear el CSV seed con las funciones REALES
    csv_path = _find_seed_csv()
    if csv_path is None:
        print("FATAL: no encontre el CSV seed Gamboa_*W18*.csv en Downloads.")
        return 1
    print(f"CSV seed            : {csv_path}")
    parsed = _parse_csv_bytes(csv_path.read_bytes(), csv_path.name)
    if parsed["error"]:
        print(f"FATAL: parser fallo: {parsed['error']}")
        return 1
    rows = parsed["rows"]
    print(f"Filas parseadas     : {len(rows)}")

    # 3. Sanidad de filas parseadas (sin _id vacio, sin negativos)
    print("\n--- Sanidad de filas RAW parseadas ---")
    bad_id = [r for r in rows if not str(r.get("_id", "")).strip()]
    chk.check(not bad_id, f"sin filas con _id vacio/NaN ({len(bad_id)} malas)")
    neg_cells = []
    for r in rows:
        for k in _KPI_SUM_KEYS:
            v = r.get(k)
            if v is not None and isinstance(v, (int, float)) and v < 0:
                neg_cells.append((r.get("_id"), k, v))
    chk.check(not neg_cells, f"sin valores negativos en filas RAW ({len(neg_cells)} celdas)")

    # 4. Consolidar con la funcion REAL contra los SKUs trackeados
    config = _load_tracked_skus(CLIENTE)
    tracked = config.get("skus", [])
    chk.check(len(tracked) == 3, f"3 SKUs trackeados (encontrados: {len(tracked)})")
    matched, unmatched = _consolidate_rows_by_sku(rows, tracked)
    matched_by_sku = {e["sku_key"]: e for e in matched}

    print("\n--- Matching ---")
    chk.check(len(matched) == 3, f"3 SKUs reconocidos (matched={len(matched)})")
    chk.check(len(unmatched) == 2,
              f"2 SKUs NO trackeados quedan unmatched (unmatched={len(unmatched)})")
    if unmatched:
        print(f"   unmatched: {[u['csv_id'] for u in unmatched]}")

    # 5. Por cada SKU: mostrar variantes, sumar, comparar contra snapshot
    print("\n--- Consolidacion por SKU (recompute CSV vs snapshot Parquet) ---")
    for sku_meta in tracked:
        sku = sku_meta["sku"]
        print(f"\n  SKU: {sku}  ({sku_meta.get('title', '')})")
        variants = _rows_for_sku(rows, sku_meta)
        print(f"    Variantes en CSV: {len(variants)}")
        for i, v in enumerate(variants, 1):
            print(
                f"      variante {i}: sessions={v.get('sessions')} "
                f"page_views={v.get('page_views')} units={v.get('units_ordered')} "
                f"toi={v.get('total_order_items')} sales={v.get('ordered_product_sales')}"
            )

        if sku == "GAMB-CREMA-200G":
            chk.check(len(variants) == 2,
                      f"{sku} tiene exactamente 2 variantes (encontradas {len(variants)})")

        if sku not in snap_by_sku:
            chk.check(False, f"{sku} presente en snapshot")
            continue
        if sku not in matched_by_sku:
            chk.check(False, f"{sku} reconocido en consolidacion")
            continue

        e = matched_by_sku[sku]
        srow = snap_by_sku[sku]
        # Comparar sumas aditivas recomputadas vs snapshot
        for k in _KPI_SUM_KEYS:
            recomputed = float(e.get(k, 0) or 0)
            persisted = float(srow[k])
            ok = abs(recomputed - persisted) < TOL
            chk.check(
                ok,
                f"{sku}.{k}: recompute={recomputed:g} == snapshot={persisted:g}",
            )
        # Derivadas
        for k in ("unit_session_pct", "avg_price"):
            ok = abs(float(e.get(k, 0) or 0) - float(srow[k])) < TOL
            chk.check(ok, f"{sku}.{k}: derivada recomputada == snapshot")

        # Snapshot sin negativos
        snap_neg = [k for k in _KPI_SUM_KEYS + ["unit_session_pct", "avg_price"]
                    if float(srow[k]) < 0]
        chk.check(not snap_neg, f"{sku}: snapshot sin metricas negativas")

    # 6. Veredicto
    print("\n" + "=" * 72)
    if chk.failures:
        print(f"RESULTADO: FAIL — {len(chk.failures)} inconsistencia(s):")
        for f in chk.failures:
            print(f"   - {f}")
        print("=" * 72)
        return 1
    print("RESULTADO: PASS — consolidacion de variantes y KPIs correctos.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
