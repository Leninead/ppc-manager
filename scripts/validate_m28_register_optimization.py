"""
Validacion programatica M28 - Script 4: registrar optimizacion + persistencia.

Pre-valida la "Validacion Visual 4" (boton 'Registrar optimizacion') invocando
el helper REAL que usa el dialogo _dialog_add_event, sin abrir Streamlit.

Que valida:
  - _append_log(...) con log_name='optimizations' persiste la fila en disco
    (data/account-health/gamboa/sku-progress/optimizations.parquet).
  - Al re-cargar con _load_log(...) la nueva optimizacion aparece en la lista
    (sku / week_iso / year / label correctos).
  - _append_log agrega timestamp automaticamente (contrato del helper).

SEGURIDAD: backup recursivo de data/account-health/gamboa/ antes de mutar,
restaurado SIEMPRE (finally). gamboa NO tiene optimizations.parquet previo,
asi que el append lo crea y el restore lo elimina, dejando el estado original.

Usage:
    python scripts/validate_m28_register_optimization.py

Exit 0 si la optimizacion se persistio y se re-leyo OK; exit 1 si no.
"""
from __future__ import annotations

import logging
import os
import shutil
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

from core.persistence import DATA_ROOT, _append_log, _load_log  # noqa: E402
from modules.pages.sku_progress_report import AREA, MODULE_SLUG  # noqa: E402

CLIENTE = "gamboa"
SKU = "GAMB-SERUM-50ML"
YEAR = 2026
WEEK_ISO = 18
LABEL = "TEST automatizado"

_CLIENT_DIR = DATA_REPO / "data" / "account-health" / CLIENTE
_BKP_DIR = DATA_REPO / "data" / "account-health" / f"{CLIENTE}.bkp"
_OPT_PATH = DATA_ROOT / AREA / CLIENTE / MODULE_SLUG / "optimizations.parquet"


class _Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, cond: bool, msg: str) -> None:
        print(f"   [{'OK ' if cond else 'FAIL'}] {msg}")
        if not cond:
            self.failures.append(msg)


def _clear_log_cache() -> None:
    if hasattr(_load_log, "clear"):
        _load_log.clear()


def _run(chk: _Checker) -> None:
    # Estado inicial: cuantas optimizaciones hay (gamboa: 0)
    _clear_log_cache()
    before = _load_log(AREA, CLIENTE, MODULE_SLUG, "optimizations")
    n_before = len(before)
    print(f"\n--- Estado inicial: {n_before} optimizacion(es) ---")

    # Registrar optimizacion con el helper REAL (igual que _dialog_add_event)
    print(f"\n--- Registrar: sku={SKU} {YEAR}-W{WEEK_ISO} '{LABEL}' ---")
    _append_log(
        row={
            "sku": SKU,
            "week_iso": int(WEEK_ISO),
            "year": int(YEAR),
            "label": LABEL,
        },
        area=AREA,
        cliente=CLIENTE,
        modulo=MODULE_SLUG,
        log_name="optimizations",
    )

    # Persistencia en disco
    chk.check(_OPT_PATH.exists(), f"optimizations.parquet creado en disco ({_OPT_PATH.name})")

    # Re-cargar y verificar que la nueva opt esta en la lista
    _clear_log_cache()
    after = _load_log(AREA, CLIENTE, MODULE_SLUG, "optimizations")
    chk.check(len(after) == n_before + 1,
              f"log crece en 1 fila ({n_before} -> {len(after)})")

    if after.empty:
        chk.check(False, "log no vacio tras append")
        return

    match = after[
        (after["sku"] == SKU)
        & (after["label"] == LABEL)
        & (after["week_iso"] == WEEK_ISO)
        & (after["year"] == YEAR)
    ]
    chk.check(len(match) == 1, f"la optimizacion registrada aparece en _load_log ({len(match)} match)")
    chk.check("timestamp" in after.columns, "_append_log agrego columna timestamp")

    if not match.empty:
        row = match.iloc[0]
        print(f"   fila persistida: sku={row['sku']} year={row['year']} "
              f"week_iso={row['week_iso']} label='{row['label']}' "
              f"timestamp={row.get('timestamp', 'N/A')}")


def main() -> int:
    print("=" * 72)
    print("VALIDACION M28 - Script 4: registrar optimizacion + persistencia")
    print("=" * 72)
    print(f"Codigo importado de : {REPO_ROOT}")
    print(f"Data leida de       : {DATA_REPO}")

    if not _CLIENT_DIR.is_dir():
        print("FATAL: no existe el dir del cliente gamboa.")
        return 1

    if _BKP_DIR.exists():
        shutil.rmtree(_BKP_DIR)
    shutil.copytree(_CLIENT_DIR, _BKP_DIR)
    print(f"Backup creado       : {_BKP_DIR}")

    chk = _Checker()
    try:
        _run(chk)
    except Exception as e:  # noqa: BLE001
        import traceback
        print("\nEXCEPCION durante el flujo:")
        traceback.print_exc()
        chk.failures.append(f"excepcion: {e}")
    finally:
        if _CLIENT_DIR.exists():
            shutil.rmtree(_CLIENT_DIR)
        shutil.copytree(_BKP_DIR, _CLIENT_DIR)
        shutil.rmtree(_BKP_DIR)
        _clear_log_cache()
        print(f"\nBackup restaurado   : {_CLIENT_DIR} (bkp eliminado)")

    print("\n" + "=" * 72)
    if chk.failures:
        print(f"RESULTADO: FAIL - {len(chk.failures)} fallo(s):")
        for f in chk.failures:
            print(f"   - {f}")
        print("=" * 72)
        return 1
    print("RESULTADO: PASS - optimizacion registrada y persistida correctamente.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
