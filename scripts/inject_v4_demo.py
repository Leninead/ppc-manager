"""Inyecta data demo en V4_listing_improvements_current_state de la propuesta _DEMO_AgencyOS.

Simula lo que va a hacer el importer HTML B7 cuando exista (skills
`amazon-brand-audit` / `digital-presence-audit` de Ramiro). Usa pp.save_proposal
para garantizar JSON sin BOM, version bump correcto, y validación de schema.

Uso: python scripts/inject_v4_demo.py
"""
# Target proposal: _DEMO_AgencyOS (id 01fbf5c2-1fd9-44dd-9806-742e5deb8f71)
# Renombrada el 2026-05-19 desde "Marca LATAM Premium (copia)" para
# evitar ambigüedad con "Marca LATAM Premium" (id 6861bbce-...).
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.proposal_persistence as pp

PROPOSAL_ID = "01fbf5c2-1fd9-44dd-9806-742e5deb8f71"

p = pp.get_proposal(PROPOSAL_ID)
if p is None:
    raise SystemExit(f"Propuesta {PROPOSAL_ID} no encontrada")

v4 = next(
    (b for b in p["blocks"] if b["module_id"] == "V4_listing_improvements_current_state"),
    None,
)
if v4 is None:
    raise SystemExit("Block V4_listing_improvements_current_state no existe en esta propuesta")

# Notas:
#  - "A+ content" tiene notes=None deliberadamente para reproducir el bug
#    B3-d-bis (None literal en celdas) y validar el fix de Entregable 2.
#  - status sigue el enum del schema: 'missing' | 'present' | 'weak'.
v4["data"] = {
    "current_state_url": "https://m.media-amazon.com/images/I/example-screenshot.jpg",
    "items": [
        {"name": "Main image", "status": "present", "notes": "1500x1500, white bg OK"},
        {"name": "Infographics", "status": "weak", "notes": "Only 2 of 7 slots used"},
        {"name": "Bullets", "status": "present", "notes": "All 5 filled, keyword-dense"},
        {"name": "A+ content", "status": "missing", "notes": None},
        {"name": "Storefront", "status": "missing", "notes": "No brand store linked"},
        {"name": "Video", "status": "weak", "notes": "1 video, low-res, 720p"},
    ],
}

saved = pp.save_proposal(p)
v4_idx = [i for i, b in enumerate(saved["blocks"]) if b["module_id"] == "V4_listing_improvements_current_state"][0]
print(f"Saved v{saved['version']} — V4 items count: {len(saved['blocks'][v4_idx]['data']['items'])}")
