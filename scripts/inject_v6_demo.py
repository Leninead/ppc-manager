"""Inyecta data demo en V6_growth_plan_phases de la propuesta _DEMO_AgencyOS.

Simula lo que va a hacer el importer HTML B7 cuando exista. V6 está FUERA
del contrato B7 v1.0 (notes/sales/contrato-importer-b7-v1.md) — su shape
definitiva se cierra en contrato v2 post-reunión 22/05. La emisión (skill
Capybaras manual vs skill de Ramiro) también se decide en esa reunión —
si es "skill manual Capybaras", V6 se refactoriza a Plan D editor.

Find-or-create:
  - Si V6 ya está en la propuesta → mutate data + bump version.
  - Si V6 NO está (template launch original no lo incluía) → crea block
    con shape canónico e inserta DESPUÉS del último V5* presente para
    mantener orden visual coherente (V1, V2, V3, V4, V5, V6, ...).
  - Re-ejecutar el script es idempotente: la primera corrida crea, las
    siguientes solo actualizan data.

Uso: python scripts/inject_v6_demo.py
"""
# Target proposal: _DEMO_AgencyOS (id 01fbf5c2-1fd9-44dd-9806-742e5deb8f71)
# Renombrada el 2026-05-19 desde "Marca LATAM Premium (copia)" para
# evitar ambigüedad con "Marca LATAM Premium" (id 6861bbce-...).
import sys
import pathlib
import uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.proposal_persistence as pp

PROPOSAL_ID = "01fbf5c2-1fd9-44dd-9806-742e5deb8f71"

p = pp.get_proposal(PROPOSAL_ID)
if p is None:
    raise SystemExit(f"Propuesta {PROPOSAL_ID} no encontrada")

# Notas sobre el payload:
#  - 3 fases exactas (cumple constraint min_items=max_items=3 del schema).
#  - Cada fase tiene number int, name bilingüe, duration string,
#    narrative bilingüe (markdown con **bold** para validar render).
#  - en + es presentes en todas las fases (no testea fallback de lang).
V6_DEMO_DATA = {
    "phases": [
        {
            "number": 1,
            "name": {"en": "Foundations", "es": "Fundaciones"},
            "duration": "Mes 1-2",
            "narrative": {
                "en": "**Phase 1 — Foundations.** Stabilize core ASINs, fix listing hygiene (titles, bullets, A+ baseline), set up brand registry, deploy initial PPC structure (exact match harvested terms + auto discovery). Target: positive contribution margin per ASIN by week 6.",
                "es": "**Fase 1 — Fundaciones.** Estabilizar ASINs core, corregir higiene de listing (títulos, bullets, A+ baseline), setup de brand registry, deploy de estructura PPC inicial (match exacto de términos cosechados + auto discovery). Meta: margen de contribución positivo por ASIN antes de la semana 6."
            }
        },
        {
            "number": 2,
            "name": {"en": "Expansion", "es": "Expansión"},
            "duration": "Mes 3-6",
            "narrative": {
                "en": "**Phase 2 — Expansion.** Scale spend on winning ASINs (200-400% MoM), launch Sponsored Brands video + Sponsored Display retargeting, expand keyword footprint by 3x via search term harvest, introduce variants/bundles. Target: 30% MoM revenue growth, ACoS within target band.",
                "es": "**Fase 2 — Expansión.** Escalar spend en ASINs ganadores (200-400% MoM), lanzar Sponsored Brands video + Sponsored Display retargeting, expandir footprint de keywords 3x vía search term harvest, introducir variantes/bundles. Meta: 30% crecimiento MoM en revenue, ACoS dentro del target."
            }
        },
        {
            "number": 3,
            "name": {"en": "DSP & Off-Amazon", "es": "DSP & Off-Amazon"},
            "duration": "Mes 7-12",
            "narrative": {
                "en": "**Phase 3 — DSP & Off-Amazon.** Activate Amazon DSP for prospecting + retargeting, integrate off-Amazon traffic (Meta/TikTok → Amazon attribution), test Brand Tailored Promotions, evaluate Vine + early reviewer programs. Target: 40%+ of new revenue from non-search channels.",
                "es": "**Fase 3 — DSP & Off-Amazon.** Activar Amazon DSP para prospecting + retargeting, integrar tráfico off-Amazon (Meta/TikTok → Amazon attribution), testear Brand Tailored Promotions, evaluar Vine + programas de early reviewers. Meta: 40%+ del revenue nuevo desde canales no-search."
            }
        }
    ]
}

v6 = next(
    (b for b in p["blocks"] if b["module_id"] == "V6_growth_plan_phases"),
    None,
)

if v6 is not None:
    # Caso 1: V6 ya está en la propuesta → solo mutar data.
    v6["data"] = V6_DEMO_DATA
    action = "ya existía, data actualizada"
else:
    # Caso 2: V6 no está → crear block con shape canónico e insertar
    # después del último V5* presente (mantiene orden visual V1→...→V5→V6).
    new_block = {
        "id": str(uuid.uuid4()),
        "module_id": "V6_growth_plan_phases",
        "proposal_id": p["id"],
        "is_fixed": False,
        "data": V6_DEMO_DATA,
        "copy_overrides": {},
    }
    last_v5_idx = max(
        (i for i, b in enumerate(p["blocks"]) if b.get("module_id", "").startswith("V5")),
        default=-1,
    )
    if last_v5_idx >= 0:
        insert_at = last_v5_idx + 1
        p["blocks"].insert(insert_at, new_block)
        action = f"creado en posición {insert_at} (después de V5 en índice {last_v5_idx})"
    else:
        p["blocks"].append(new_block)
        action = f"creado al final en posición {len(p['blocks']) - 1} (V5 no presente)"

saved = pp.save_proposal(p)
v6_idx = [i for i, b in enumerate(saved["blocks"]) if b["module_id"] == "V6_growth_plan_phases"][0]
print(
    f"Saved v{saved['version']} — V6 {action} — "
    f"phases count: {len(saved['blocks'][v6_idx]['data']['phases'])}"
)
