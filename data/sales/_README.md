# `data/sales/` — Sales Proposals

Capa de persistencia del sistema **Sales Proposals** del Agency OS.

Toda I/O pasa por `core/proposal_persistence.py`. Nada se lee/escribe a mano desde módulos Streamlit ni scripts.

---

## Estructura

```
data/sales/
├── _README.md                ← este archivo (versionado)
├── _catalog.json             ← catálogo canónico de 37 módulos (versionado)
├── _templates/               ← 4 templates por arquetipo (versionado)
│   ├── launch-new-brand.json
│   ├── scale-seo-gap.json
│   ├── defense-brand-attack.json
│   └── cvr-listing-driven.json
├── _seed/                    ← propuestas semilla parseadas (versionado, referencia)
│   ├── sunny_zebra.json
│   ├── happy_mammoth.json
│   ├── garland_rug.json
│   ├── nandog.json
│   └── nobl_travel.json
├── proposals/                ← propuestas reales (GITIGNORED — data de cliente)
│   ├── <uuid>__v1.json
│   ├── <uuid>__v2.json
│   └── ...
└── interested-votes.parquet  ← log append-only de votos (GITIGNORED)
```

---

## Naming de archivos

| Tipo | Patrón | Ejemplo |
|---|---|---|
| Propuesta versionada | `<proposal_id>__v<N>.json` | `2f1d…__v3.json` |
| Template por arquetipo | `<archetype-slug>.json` | `launch-new-brand.json` |
| Seed file | `<seed_id>.json` | `garland_rug.json` |
| Catálogo | fijo | `_catalog.json` |
| Log de votos | fijo | `interested-votes.parquet` |

---

## API de persistencia (`core/proposal_persistence.py`)

```python
from core.proposal_persistence import (
    load_catalog,
    list_proposals,
    get_proposal,
    save_proposal,
    delete_proposal,
    list_templates,
    get_template,
    instantiate_proposal_from_template,
    log_interested_vote,
    get_module_vote_count,
    get_seed_proposal,
)
```

Diseñado con `ProposalStorage` abstracto + `LocalJsonStorage` concreto. Cuando llegue Fase 2/3 (Supabase), se implementa `SupabaseStorage` y los consumidores no se tocan.

---

## Reglas duras

1. Toda Proposal debe incluir los 8 módulos FIXED (F1–F8).
2. Cada `Block.module_id` debe existir en el catálogo (FK enforcement).
3. `copy_overrides` solo acepta keys `"en"` y `"es"`.
4. Auto-versionado: `save_proposal` con mismo `id` incrementa `version`.
5. Soft delete por default: `status="archived"` (no borra archivos).

---

## Tests

```bash
pytest tests/test_proposal_schema.py -v        # schema + catálogo + templates
pytest tests/test_proposal_persistence.py -v   # save/get/delete/votes
```

---

## Migración a Supabase (futuro)

Cuando se migre, solo cambia la implementación interna de `core/proposal_persistence.py`:

1. Implementar `SupabaseStorage(ProposalStorage)`.
2. Cambiar `_default_storage()` para devolver `SupabaseStorage`.
3. Las 11 funciones públicas (signatures) NO se tocan.
4. Los consumidores (módulos Streamlit, scripts, tests) NO se tocan.

Schema de tablas Supabase: derivar 1:1 de `data/_schemas/proposal-v1.json`.

---

## Referencias

- Schema: `data/_schemas/proposal-v1.json`
- Skill: `.claude/skills/data-persistence-standard.md`
- Paths: `core/proposal_paths.py`
