"""Paths canónicos del sistema Sales Proposals.

Todas las rutas del módulo Sales viven acá. Ningún consumidor (módulo Streamlit,
scripts, tests) hardcodea rutas — todo pasa por estas constantes.

Esto facilita la migración Fase 1 (local JSON) → Fase 2 (SQLite) → Fase 3 (Supabase):
cuando cambien las rutas o el backend, sólo se toca este archivo + la implementación
de `core/proposal_persistence.py`. Los consumidores no se enteran.
"""

from __future__ import annotations

from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Raíz de la sección Sales dentro de data/
# ─────────────────────────────────────────────────────────────────────────────

SALES_ROOT = Path("data") / "sales"

# ─────────────────────────────────────────────────────────────────────────────
# Archivos versionados en git (estructura del producto)
# ─────────────────────────────────────────────────────────────────────────────

CATALOG_FILE = SALES_ROOT / "_catalog.json"
"""Catálogo canónico de módulos (37 módulos). Versionado."""

TEMPLATES_DIR = SALES_ROOT / "_templates"
"""4 templates por arquetipo (launch, scale_seo, defense, cvr). Versionado."""

SEED_DIR = SALES_ROOT / "_seed"
"""Propuestas semilla de los 5 PDFs/DOCX. Versionado como referencia histórica."""

SCHEMAS_DIR = Path("data") / "_schemas"
"""Schemas versionados. proposal-v1.json vive acá (compartido con el resto del Agency OS)."""

PROPOSAL_SCHEMA_FILE = SCHEMAS_DIR / "proposal-v1.json"

# ─────────────────────────────────────────────────────────────────────────────
# Archivos NO versionados (data de cliente / operacional)
# ─────────────────────────────────────────────────────────────────────────────

PROPOSALS_DIR = SALES_ROOT / "proposals"
"""Propuestas reales del equipo. Una por versión, nombre: `<id>__v<N>.json`. Gitignored."""

VOTES_LOG_FILE = SALES_ROOT / "interested-votes.parquet"
"""Log append-only de votos 'Marcar como interesado'. Gitignored."""

# ─────────────────────────────────────────────────────────────────────────────
# Helpers de path
# ─────────────────────────────────────────────────────────────────────────────


def proposal_file(proposal_id: str, version: int) -> Path:
    """Construye el path canónico de una versión específica de una propuesta."""
    return PROPOSALS_DIR / f"{proposal_id}__v{version}.json"


def template_file(archetype: str) -> Path:
    """Construye el path canónico de un template por arquetipo.

    Mapping de archetype → nombre de archivo:
      - launch       → launch-new-brand.json
      - scale_seo    → scale-seo-gap.json
      - defense      → defense-brand-attack.json
      - cvr          → cvr-listing-driven.json
    """
    mapping = {
        "launch": "launch-new-brand.json",
        "scale_seo": "scale-seo-gap.json",
        "defense": "defense-brand-attack.json",
        "cvr": "cvr-listing-driven.json",
    }
    if archetype not in mapping:
        raise ValueError(
            f"archetype '{archetype}' no tiene template. "
            f"Valores válidos: {list(mapping.keys())} (note: 'custom' no tiene template)."
        )
    return TEMPLATES_DIR / mapping[archetype]


def seed_file(seed_id: str) -> Path:
    """Path de una propuesta semilla por su id (ej: 'sunny_zebra', 'garland_rug')."""
    return SEED_DIR / f"{seed_id}.json"


def ensure_dirs() -> None:
    """Crea todos los directorios necesarios si no existen. Idempotente."""
    for d in (SALES_ROOT, TEMPLATES_DIR, SEED_DIR, PROPOSALS_DIR, SCHEMAS_DIR):
        d.mkdir(parents=True, exist_ok=True)
