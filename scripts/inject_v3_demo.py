"""Inyecta data demo en V3_seo_opportunity de la propuesta Marca LATAM Premium.

Simula lo que va a hacer el importer HTML B7 cuando exista. Usa pp.save_proposal
para garantizar JSON sin BOM, version bump correcto, y validación de schema.

Uso: python scripts/inject_v3_demo.py
"""
import sys
import pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.proposal_persistence as pp

PROPOSAL_ID = "01fbf5c2-1fd9-44dd-9806-742e5deb8f71"

p = pp.get_proposal(PROPOSAL_ID)
if p is None:
    raise SystemExit(f"Propuesta {PROPOSAL_ID} no encontrada")

v3 = next(
    (b for b in p["blocks"] if b["module_id"] == "V3_seo_opportunity"),
    None,
)
if v3 is None:
    raise SystemExit("Block V3_seo_opportunity no existe en esta propuesta")

v3["data"] = {
    "missing_keywords": [
        {"keyword": "saco para dormir bebe", "sv": 46836, "current_rank": None, "opportunity_score": 0.92},
        {"keyword": "swaddle", "sv": 12450, "current_rank": 18, "opportunity_score": 0.78},
        {"keyword": "baby sleep sack", "sv": 8200, "current_rank": 45, "opportunity_score": 0.65},
        {"keyword": "saco verano bebe", "sv": 3100, "current_rank": None, "opportunity_score": 0.71},
    ],
    "launch_score_table": [
        {"asin": "B09MG1J3LC", "phase": "Launch", "score": 82, "status": "ready"},
        {"asin": "B0CK2KCBLS", "phase": "Launch", "score": 71, "status": "needs_listing"},
    ],
    "page1_domination_chart_data": [],
}

saved = pp.save_proposal(p)
print(f"Saved v{saved['version']} — V3 missing_keywords count: {len(saved['blocks'][[i for i, b in enumerate(saved['blocks']) if b['module_id'] == 'V3_seo_opportunity'][0]]['data']['missing_keywords'])}")
