"""Inyecta data demo en V5_listing_comparison_competitor de la propuesta _DEMO_AgencyOS.

Simula lo que va a hacer el importer HTML B7 cuando exista. V5 está FUERA
del contrato B7 v1.0 (notes/sales/contrato-importer-b7-v1.md) — su shape
definitiva se cierra en contrato v2 post-reunión 22/05. Este demo cubre los
4 paths del helper defensivo _render_v5_asset_list:
  - asset como string plano
  - asset como dict con url + caption
  - asset como dict con url sin caption
  - client_assets vacío (grupo a_plus)

Find-or-create:
  - Si V5 ya está en la propuesta → mutate data + bump version.
  - Si V5 NO está (template launch original no lo incluía) → crea block
    con shape canónico e inserta DESPUÉS del último V4* presente para
    mantener orden visual coherente (V1, V2, V3, V4, V5, ...).
  - Re-ejecutar el script es idempotente: la primera corrida crea, las
    siguientes solo actualizan data.

Uso: python scripts/inject_v5_demo.py
"""
# Target proposal: _DEMO_AgencyOS (id 01fbf5c2-1fd9-44dd-9806-742e5deb8f71)
# Renombrada el 2026-05-19 desde "Marca LATAM Premium (copia)" para
# evitar ambigüedad con "Marca LATAM Premium" (id 6861bbce-...).
import sys
import pathlib
import uuid
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

import core.proposals.persistence as pp

PROPOSAL_ID = "01fbf5c2-1fd9-44dd-9806-742e5deb8f71"

p = pp.get_proposal(PROPOSAL_ID)
if p is None:
    raise SystemExit(f"Propuesta {PROPOSAL_ID} no encontrada")

# Notas sobre el payload:
#  - Mezcla shapes deliberadamente para validar el helper defensivo:
#    main_image usa strings, infographics usa dict con caption, a_plus
#    mezcla dict sin caption + lista vacía del cliente.
#  - type sigue el enum del catálogo: 'main_image' | 'infographics' | 'a_plus'.
V5_DEMO_DATA = {
    "comparison_groups": [
        {
            "type": "main_image",
            "client_assets": [
                "https://m.media-amazon.com/images/I/example-client-main.jpg",
            ],
            "competitor_assets": [
                "https://m.media-amazon.com/images/I/example-competitor-main.jpg",
            ],
            "commentary": "El competidor usa fondo blanco saturado + texto overlay grande; nuestro main image queda visualmente más limpio pero con menos información de claim de producto.",
        },
        {
            "type": "infographics",
            "client_assets": [
                {"url": "https://m.media-amazon.com/images/I/client-info-1.jpg", "caption": "Slide 1 — Beneficios"},
                {"url": "https://m.media-amazon.com/images/I/client-info-2.jpg", "caption": "Slide 2 — Uso"},
            ],
            "competitor_assets": [
                {"url": "https://m.media-amazon.com/images/I/competitor-info-1.jpg", "caption": "Slide 1 — Comparativa"},
                {"url": "https://m.media-amazon.com/images/I/competitor-info-2.jpg", "caption": "Slide 2 — Reviews"},
                {"url": "https://m.media-amazon.com/images/I/competitor-info-3.jpg", "caption": "Slide 3 — Trust badges"},
            ],
            "commentary": "Competidor tiene 3 slides de infographics vs nuestras 2. Falta slide de trust signals (reviews/badges).",
        },
        {
            "type": "a_plus",
            "client_assets": [],
            "competitor_assets": [
                {"url": "https://m.media-amazon.com/images/A/competitor-aplus.jpg"},
            ],
            "commentary": "Cliente NO tiene A+ content. Competidor sí. Gap crítico de conversión.",
        },
    ]
}

v5 = next(
    (b for b in p["blocks"] if b["module_id"] == "V5_listing_comparison_competitor"),
    None,
)

if v5 is not None:
    # Caso 1: V5 ya está en la propuesta → solo mutar data.
    v5["data"] = V5_DEMO_DATA
    action = "ya existía, data actualizada"
else:
    # Caso 2: V5 no está → crear block con shape canónico e insertar
    # después del último V4* presente (mantiene orden visual V1→V2→V3→V4→V5).
    new_block = {
        "id": str(uuid.uuid4()),
        "module_id": "V5_listing_comparison_competitor",
        "proposal_id": p["id"],
        "is_fixed": False,
        "data": V5_DEMO_DATA,
        "copy_overrides": {},
    }
    last_v4_idx = max(
        (i for i, b in enumerate(p["blocks"]) if b.get("module_id", "").startswith("V4")),
        default=-1,
    )
    if last_v4_idx >= 0:
        insert_at = last_v4_idx + 1
        p["blocks"].insert(insert_at, new_block)
        action = f"creado en posición {insert_at} (después de V4 en índice {last_v4_idx})"
    else:
        p["blocks"].append(new_block)
        action = f"creado al final en posición {len(p['blocks']) - 1} (V4 no presente)"

saved = pp.save_proposal(p)
v5_idx = [i for i, b in enumerate(saved["blocks"]) if b["module_id"] == "V5_listing_comparison_competitor"][0]
print(
    f"Saved v{saved['version']} — V5 {action} — "
    f"comparison_groups count: {len(saved['blocks'][v5_idx]['data']['comparison_groups'])}"
)
