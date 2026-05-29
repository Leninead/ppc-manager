"""
Validacion programatica M28 - Script 3: estructura del Excel "Excel completo".

Pre-valida la "Validacion Visual 3" (descarga del Excel multi-hoja) generando
el .xlsx con la funcion REAL del modulo y verificando su estructura con openpyxl,
sin abrir Streamlit.

Que valida:
  - _build_sku_progress_excel(cliente, history, optimizations) corre sin error.
  - Existen las 3 hojas base: Resumen, Detalle, Optimizaciones.
  - Existe 1 hoja por SKU presente en history (3 SKUs -> 3 hojas SKU).
  - Reporta filas/columnas/headers de cada hoja.
  - Detecta posible colision R2 (dos SKUs que truncan/sanitizan al mismo nombre
    de hoja de <=31 chars, o un SKU que colisiona con una hoja base).

El .xlsx se escribe en scripts/_m28_excel_validation_output.xlsx (output
reproducible, gitignored — no se versiona).

Usage:
    python scripts/validate_m28_excel_structure.py

Exit 0 si la estructura es correcta; exit 1 si falta una hoja esperada o hay
duplicados reales.
"""
from __future__ import annotations

import logging
import os
import re
import sys
import warnings
from pathlib import Path


def _bootstrap() -> tuple[Path, Path]:
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
    logging.getLogger("streamlit").setLevel(logging.CRITICAL)
    warnings.filterwarnings("ignore")
    return repo_root, data_repo


REPO_ROOT, DATA_REPO = _bootstrap()

from openpyxl import load_workbook  # noqa: E402

from core.persistence import _load_history, _load_log  # noqa: E402
from modules.pages.sku_progress_report import (  # noqa: E402
    AREA,
    MODULE_SLUG,
    _build_sku_progress_excel,
    _load_tracked_skus,
)

CLIENTE = "gamboa"
BASE_SHEETS = ["Resumen", "Detalle", "Optimizaciones"]
OUT_PATH = REPO_ROOT / "scripts" / "_m28_excel_validation_output.xlsx"


class _Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, cond: bool, msg: str) -> None:
        print(f"   [{'OK ' if cond else 'FAIL'}] {msg}")
        if not cond:
            self.failures.append(msg)


def _excel_sheet_name(sku: str) -> str:
    """Replica la sanitizacion de nombre de hoja del builder (L728-729)."""
    name = sku[:31] if len(sku) > 31 else sku
    return re.sub(r"[\\/?*\[\]:]", "_", name)


def main() -> int:
    print("=" * 72)
    print("VALIDACION M28 - Script 3: estructura del Excel completo")
    print("=" * 72)
    print(f"Codigo importado de : {REPO_ROOT}")
    print(f"Data leida de       : {DATA_REPO}")

    chk = _Checker()

    history = _load_history(AREA, CLIENTE, MODULE_SLUG)
    optimizations = _load_log(AREA, CLIENTE, MODULE_SLUG, "optimizations")
    if history.empty:
        print("FATAL: history vacia, no se puede generar Excel.")
        return 1
    tracked = _load_tracked_skus(CLIENTE).get("skus", [])
    skus_in_history = sorted(history["sku"].unique().tolist())
    print(f"SKUs trackeados     : {len(tracked)}")
    print(f"SKUs en history     : {skus_in_history}")
    print(f"Optimizaciones      : {len(optimizations)} fila(s)")

    # Generar el Excel con la funcion REAL
    try:
        xlsx_bytes = _build_sku_progress_excel(CLIENTE, history, optimizations)
    except Exception as e:  # noqa: BLE001
        print(f"FATAL: _build_sku_progress_excel fallo: {e}")
        return 1
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_bytes(xlsx_bytes)
    print(f"Excel escrito       : {OUT_PATH} ({len(xlsx_bytes):,} bytes)")

    # Abrir y listar hojas
    wb = load_workbook(OUT_PATH, read_only=True)
    sheets = wb.sheetnames
    print(f"\n--- Hojas ({len(sheets)} total) ---")
    for s in sheets:
        print(f"   - {s}")

    # Hojas base
    print("\n--- Hojas base esperadas ---")
    for base in BASE_SHEETS:
        chk.check(base in sheets, f"hoja base '{base}' presente")

    # Una hoja por SKU en history
    print("\n--- Hojas por SKU ---")
    expected_sku_sheets = {_excel_sheet_name(s): s for s in skus_in_history}
    for sheet_name, sku in expected_sku_sheets.items():
        present = sheet_name in sheets or f"SKU_{sku[:25]}" in sheets
        chk.check(present, f"hoja del SKU '{sku}' presente (esperada '{sheet_name}')")
    n_sku_sheets = len([s for s in sheets if s not in BASE_SHEETS])
    chk.check(
        n_sku_sheets == len(skus_in_history),
        f"{len(skus_in_history)} hoja(s) SKU (encontradas {n_sku_sheets})",
    )

    # Deteccion R2: colision de nombres truncados/sanitizados
    print("\n--- Deteccion colision R2 ---")
    truncated = [_excel_sheet_name(s) for s in skus_in_history]
    dup_among_skus = len(truncated) != len(set(truncated))
    chk.check(not dup_among_skus,
              f"sin colision entre SKUs al truncar a 31 chars ({truncated})")
    collide_base = set(truncated) & set(BASE_SHEETS)
    chk.check(not collide_base,
              f"ningun SKU colisiona con hoja base ({collide_base or 'ninguna'})")
    dup_in_file = len(sheets) != len(set(sheets))
    chk.check(not dup_in_file, "sin nombres de hoja duplicados en el archivo")

    # Reporte filas/cols/headers por hoja
    print("\n--- Filas / columnas / headers por hoja ---")
    wb2 = load_workbook(OUT_PATH, read_only=True)
    for s in wb2.sheetnames:
        ws = wb2[s]
        nrows, ncols = ws.max_row, ws.max_column
        # Headers: primera fila no vacia con varias celdas (el builder usa fila 1
        # o fila 4 segun la hoja Resumen).
        first_vals = [c.value for c in next(ws.iter_rows(min_row=1, max_row=1))]
        print(f"   [{s}] filas={nrows} cols={ncols} fila1={first_vals}")

    print("\n" + "=" * 72)
    if chk.failures:
        print(f"RESULTADO: FAIL - {len(chk.failures)} problema(s):")
        for f in chk.failures:
            print(f"   - {f}")
        print("=" * 72)
        return 1
    print("RESULTADO: PASS - estructura del Excel correcta.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
