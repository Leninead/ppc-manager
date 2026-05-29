"""
Validacion programatica M28 - Script 2: flujo del tab Admin sin UI.

Pre-valida la "Validacion Visual 2" (tab Admin) ejecutando el ciclo completo:
  1. Estado inicial: snapshot W18 presente + 3 SKUs trackeados.
  2. Borrar snapshot W18 con la secuencia REAL del handler de Admin
     (R3: unlink directo inline + _rebuild_history + clear caches; no existe
     funcion standalone, se replica la secuencia exacta del modulo).
  3. Re-importar el CSV seed con la cadena REAL de import
     (_parse_csv_bytes -> _consolidate_rows_by_sku -> _build_snapshot_df ->
      _validate_against_schema -> _save_snapshot -> _rebuild_history).
  4. Borrar el SKU GAMB-OIL-30ML del tracking con los helpers REALES
     (_load_tracked_skus / _save_tracked_skus). Verificar que el snapshot W18
     en disco queda intacto y SIGUE conteniendo la fila del SKU borrado
     (la data del Parquet NO se elimina al des-trackear un SKU).

SEGURIDAD: hace backup recursivo de data/account-health/gamboa/ antes de
mutar y lo restaura SIEMPRE (finally), pase o falle.

Usage:
    python scripts/validate_m28_admin_flow.py

Exit 0 si todos los asserts pasan; exit 1 al primer fallo (con mensaje claro).
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

from core.persistence import (  # noqa: E402
    DATA_ROOT,
    _list_periods,
    _load_history,
    _load_snapshot,
    _rebuild_history,
    _save_snapshot,
    _validate_against_schema,
)
from modules.pages.sku_progress_report import (  # noqa: E402
    AREA,
    MODULE_SLUG,
    SCHEMA_VERSION,
    _build_snapshot_df,
    _consolidate_rows_by_sku,
    _load_tracked_skus,
    _parse_csv_bytes,
    _save_tracked_skus,
)

CLIENTE = "gamboa"
PERIOD = "2026-W18"
DEL_SKU = "GAMB-OIL-30ML"

_CLIENT_DIR = DATA_REPO / "data" / "account-health" / CLIENTE
_BKP_DIR = DATA_REPO / "data" / "account-health" / f"{CLIENTE}.bkp"


class _Checker:
    def __init__(self) -> None:
        self.failures: list[str] = []

    def check(self, cond: bool, msg: str) -> None:
        print(f"   [{'OK ' if cond else 'FAIL'}] {msg}")
        if not cond:
            self.failures.append(msg)


def _clear_caches() -> None:
    """Invalida los caches @st.cache_data para leer estado fresco de disco."""
    for fn in (_list_periods, _load_history, _load_snapshot):
        if hasattr(fn, "clear"):
            fn.clear()


def _find_seed_csv() -> Path | None:
    direct = Path(r"C:/Users/lenin/Downloads/Gamboa_DetailPageSalesTraffic_2026-W18.csv")
    if direct.is_file():
        return direct
    dl = Path(r"C:/Users/lenin/Downloads")
    if dl.is_dir():
        hits = sorted(dl.glob("Gamboa*DetailPage*W18*.csv"))
        if hits:
            return hits[0]
    return None


def _snapshot_path(period: str) -> Path:
    return DATA_ROOT / AREA / CLIENTE / MODULE_SLUG / f"{period}.parquet"


def _run(chk: _Checker) -> None:
    # ── Paso 1: estado inicial ───────────────────────────────────────────
    print("\n--- Paso 1: estado inicial ---")
    _clear_caches()
    periods0 = _list_periods(AREA, CLIENTE, MODULE_SLUG)
    chk.check(PERIOD in periods0, f"snapshot {PERIOD} presente (periods={periods0})")
    chk.check(_snapshot_path(PERIOD).exists(), f"archivo {PERIOD}.parquet en disco")
    tracked0 = _load_tracked_skus(CLIENTE).get("skus", [])
    chk.check(len(tracked0) == 3, f"3 SKUs trackeados (={len(tracked0)})")

    # ── Paso 2: borrar snapshot (secuencia REAL del handler Admin, R3) ────
    print("\n--- Paso 2: borrar snapshot W18 (secuencia real Admin) ---")
    target = _snapshot_path(PERIOD)
    if target.exists():
        target.unlink()                      # R3: unlink directo (igual que la UI)
    try:
        _rebuild_history(AREA, CLIENTE, MODULE_SLUG)
    except FileNotFoundError:
        # Era el unico snapshot -> borrar el _history tambien (igual que la UI)
        hist = DATA_ROOT / AREA / CLIENTE / MODULE_SLUG / "_history.parquet"
        if hist.exists():
            hist.unlink()
    _clear_caches()

    chk.check(not target.exists(), f"archivo {PERIOD}.parquet ya NO existe")
    periods1 = _list_periods(AREA, CLIENTE, MODULE_SLUG)
    chk.check(PERIOD not in periods1, f"{PERIOD} fuera de _list_periods (periods={periods1})")
    hist1 = _load_history(AREA, CLIENTE, MODULE_SLUG)
    has_w18 = (not hist1.empty) and ("_period" in hist1) and (PERIOD in set(hist1["_period"]))
    chk.check(not has_w18, "history rebuild sin W18 (estado correcto post-borrado)")

    # ── Paso 3: re-importar el CSV (cadena REAL de import) ────────────────
    print("\n--- Paso 3: re-importar CSV seed (cadena real de import) ---")
    csv_path = _find_seed_csv()
    if csv_path is None:
        chk.check(False, "CSV seed Gamboa_*W18*.csv encontrado en Downloads")
        return
    print(f"   CSV: {csv_path}")
    parsed = _parse_csv_bytes(csv_path.read_bytes(), csv_path.name)
    chk.check(not parsed["error"], f"parser sin error ({parsed['error']})")
    tracked_now = _load_tracked_skus(CLIENTE).get("skus", [])
    matched, _unmatched = _consolidate_rows_by_sku(parsed["rows"], tracked_now)
    df = _build_snapshot_df(matched, tracked_now, 2026, 18)
    errors = _validate_against_schema(df, MODULE_SLUG, SCHEMA_VERSION)
    chk.check(not errors, f"snapshot valida contra schema ({errors})")
    _save_snapshot(df, AREA, CLIENTE, MODULE_SLUG, PERIOD)
    try:
        _rebuild_history(AREA, CLIENTE, MODULE_SLUG)
    except FileNotFoundError:
        pass
    _clear_caches()

    chk.check(_snapshot_path(PERIOD).exists(), f"{PERIOD}.parquet vuelve a existir")
    periods2 = _list_periods(AREA, CLIENTE, MODULE_SLUG)
    chk.check(PERIOD in periods2, f"{PERIOD} vuelve a _list_periods (periods={periods2})")
    hist2 = _load_history(AREA, CLIENTE, MODULE_SLUG)
    chk.check(len(hist2) == 3, f"history reconstruida con 3 filas (={len(hist2)})")

    # ── Paso 4: borrar SKU del tracking (helpers REALES) ──────────────────
    print(f"\n--- Paso 4: des-trackear SKU {DEL_SKU} (helpers reales) ---")
    config = _load_tracked_skus(CLIENTE)
    config["skus"] = [s for s in config["skus"] if s["sku"] != DEL_SKU]
    _save_tracked_skus(CLIENTE, config)

    tracked_after = _load_tracked_skus(CLIENTE).get("skus", [])
    skus_after = {s["sku"] for s in tracked_after}
    chk.check(DEL_SKU not in skus_after, f"{DEL_SKU} fuera del tracking (quedan {sorted(skus_after)})")
    chk.check(len(tracked_after) == 2, f"tracking con 2 SKUs (={len(tracked_after)})")

    # El snapshot en disco NO se toca al des-trackear: data del SKU sigue ahi
    chk.check(_snapshot_path(PERIOD).exists(), f"{PERIOD}.parquet intacto en disco tras des-trackear")
    _clear_caches()
    snap_after = _load_snapshot(AREA, CLIENTE, MODULE_SLUG, PERIOD)
    still_has = (snap_after is not None) and (DEL_SKU in set(snap_after["sku"]))
    chk.check(still_has, f"fila de {DEL_SKU} SIGUE en el Parquet (data no se borra)")


def main() -> int:
    print("=" * 72)
    print("VALIDACION M28 - Script 2: flujo Admin (borrar/reimportar/des-trackear)")
    print("=" * 72)
    print(f"Codigo importado de : {REPO_ROOT}")
    print(f"Data leida de       : {DATA_REPO}")
    print(f"Cliente dir         : {_CLIENT_DIR}")

    if not _CLIENT_DIR.is_dir():
        print("FATAL: no existe el dir del cliente gamboa.")
        return 1

    # Backup recursivo antes de mutar
    if _BKP_DIR.exists():
        shutil.rmtree(_BKP_DIR)
    shutil.copytree(_CLIENT_DIR, _BKP_DIR)
    print(f"Backup creado       : {_BKP_DIR}")

    chk = _Checker()
    try:
        _run(chk)
    except Exception as e:  # noqa: BLE001 — cualquier excepcion = fallo de validacion
        import traceback
        print("\nEXCEPCION durante el flujo:")
        traceback.print_exc()
        chk.failures.append(f"excepcion: {e}")
    finally:
        # Restaurar SIEMPRE el estado original
        if _CLIENT_DIR.exists():
            shutil.rmtree(_CLIENT_DIR)
        shutil.copytree(_BKP_DIR, _CLIENT_DIR)
        shutil.rmtree(_BKP_DIR)
        _clear_caches()
        print(f"\nBackup restaurado   : {_CLIENT_DIR} (bkp eliminado)")

    print("\n" + "=" * 72)
    if chk.failures:
        print(f"RESULTADO: FAIL - {len(chk.failures)} fallo(s):")
        for f in chk.failures:
            print(f"   - {f}")
        print("=" * 72)
        return 1
    print("RESULTADO: PASS - flujo Admin completo consistente.")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
