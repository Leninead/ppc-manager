"""Paths canónicos del módulo Supply Chain (M37).

Todas las rutas del módulo Supply viven acá. Ningún consumidor (módulo Streamlit,
scripts, tests) hardcodea rutas — todo pasa por estas constantes.

Esto facilita la migración Fase 1 (local JSON) → Fase 2 (SQLite) → Fase 3 (Supabase):
cuando cambien las rutas o el backend, sólo se toca este archivo + la implementación
de `core/supply/persistence.py`. Los consumidores no se enteran.
"""

from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Raíz de la sección Supply Chain dentro de data/
# ─────────────────────────────────────────────────────────────────────────────

from core.data_root import DATA_ROOT  # data root, configurable via AGENCY_OS_DATA_DIR

SUPPLY_ROOT = DATA_ROOT / "supply"

# ─────────────────────────────────────────────────────────────────────────────
# Archivos NO versionados (data de cliente / operacional)
# ─────────────────────────────────────────────────────────────────────────────

PROVEEDORES_FILE = SUPPLY_ROOT / "proveedores.json"
"""Maestro de proveedores del cliente. Un único JSON con la lista completa. Gitignored."""

OCS_DIR = SUPPLY_ROOT / "ocs"
"""Órdenes de compra reales. Una por archivo, nombre: `<oc_id>.json`. Gitignored."""

EVENTOS_LOG_FILE = SUPPLY_ROOT / "eventos.parquet"
"""Log append-only de cambios de estado de las OC. Alimenta lead time medido
y fill rate por proveedor. Gitignored."""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers de path
# ─────────────────────────────────────────────────────────────────────────────


def oc_file(oc_id: str) -> Path:
    """Construye el path canónico de una orden de compra por su id."""
    return OCS_DIR / f"{oc_id}.json"


def ensure_dirs() -> None:
    """Crea todos los directorios necesarios si no existen. Idempotente."""
    for d in (SUPPLY_ROOT, OCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
