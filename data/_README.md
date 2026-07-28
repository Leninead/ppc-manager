# `data/` — Capa de persistencia del Agency OS

Este directorio contiene todos los datos operativos persistidos por los módulos del Agency OS.

**Toda I/O pasa por `core/persistence.py`.** No leer ni escribir archivos directamente desde los módulos.

---

## Estructura canónica

```
data/
├── _README.md                      ← este archivo (versionado)
├── _schemas/                       ← schemas versionados (versionado)
│   ├── pricing-v1.json
│   ├── sku-progress-v1.json
│   └── ...
├── <area>/                         ← sección del sidebar (kebab-case)
│   ├── _README.md                  ← instrucciones por sección (versionado)
│   ├── _examples/                  ← datos sintéticos para testing (versionado)
│   ├── <cliente>/                  ← slug del cliente (NO versionado)
│   │   ├── <modulo>/
│   │   │   ├── 2026-W18.parquet    ← snapshot semanal
│   │   │   ├── _history.parquet    ← agregador cross-period
│   │   │   ├── optimizations.parquet  ← log append-only
│   │   │   └── events.parquet
│   │   └── ...
│   └── <modulo-agnostic>/          ← módulos client-agnostic
│       └── aliases-v1.json
└── ...
```

### Áreas activas

| Área | Estado | Descripción |
|---|---|---|
| `account-health/` | activa | Pricing, SKU Progress, Flat File Migrator, etc. |
| `ppc/` | reservado | Persistencia para módulos PPC cuando lo requieran |
| `supply-chain/` | reservado | — |
| `disenio/` | reservado | — |
| `rrhh/` | reservado | — |
| `sales/` | activa | M29 Proposal Studio. Owner: Sales Directors. Schema `proposal-v1`, 4 archetypes (launch / scale_seo / defense / cvr), catálogo de 37 módulos (8 FIXED + 29 VARIABLE). |
| `marketplaces/` | reservado | — |
| `direccion-general/` | reservado | — |

### Carpetas legacy (pre-skill)

Estas carpetas existen desde antes del `data-persistence-standard` y NO se renombran ni migran salvo refactor explícito:

- `data/business_report/` — BR de clientes cargados manualmente. Reusable por módulos Account Health.
- `data/atom11/` — exports Atom11 históricos.
- `data/listing_snapshots/snapshots.json` — M15 Listing Monitor (formato JSON legacy).
- `data/merchanspring/` — reportes MerchanSpring.

---

## Naming de archivos

| Tipo | Formato | Ejemplo |
|---|---|---|
| Snapshot semanal | `YYYY-WW.parquet` (ISO week) | `2026-W18.parquet` |
| Snapshot mensual | `YYYY-MM.parquet` | `2026-04.parquet` |
| Snapshot diario | `YYYY-MM-DD.parquet` | `2026-05-06.parquet` |
| Agregador histórico | `_history.parquet` | — |
| Log append-only | nombre semántico, sin fecha | `optimizations.parquet`, `events.parquet`, `decisions-log.parquet` |
| Config versionado | `<name>-v<N>.json` | `aliases-v1.json` |

Reglas duras:
- ASCII only, kebab-case, ISO 8601.
- Underscore prefix `_` reservado para archivos especiales (`_history`, `_schemas`, `_examples`, `_README`).

---

## Versionado en git

### Versionado (committed):
- `data/_README.md`
- `data/_schemas/**/*.json`
- `data/<area>/_README.md`
- `data/<area>/_examples/**`
- Configs de módulos client-agnostic (ej: `data/account-health/flat-file-migrator/aliases-v1.json`)

### NO versionado (gitignored):
- Todo dato real de cliente: `data/<area>/<cliente>/**`
- Carpetas legacy completas (`data/atom11/`, `data/business_report/`, etc.)

Razones: privacidad, tamaño, sync con Claude.ai, consistencia con migration path futuro a SQLite/Postgres.

---

## API de persistencia — `core/persistence.py`

10 helpers obligatorios:

```python
from core.persistence import (
    _save_snapshot,           # guardar snapshot semanal/mensual
    _load_snapshot,           # leer snapshot específico (cacheado)
    _load_history,            # leer agregador cross-period (cacheado)
    _rebuild_history,         # reconstruir _history.parquet
    _append_log,              # agregar 1 fila a log append-only
    _load_log,                # leer log con filtros opcionales (cacheado)
    _save_config,             # guardar config JSON versionado
    _load_config,             # leer config (cacheado)
    _list_periods,            # listar snapshots disponibles
    _validate_against_schema, # validar DataFrame contra schema
)
```

Ver `.claude/skills/data-persistence-standard.md` para contrato completo.

---

## Migration path

| Fase | Storage | Trigger |
|---|---|---|
| **1 — actual** | Parquet local en `data/` | Single-user (Marcos) |
| 2 | SQLite local en `data/agencyos.db` | Aparece 2do usuario operando en paralelo |
| 3 | Postgres cloud (Supabase/Neon/Render) | Equipo 3+ o dashboards live al cliente |

Cuando se migre, solo cambia la implementación interna de `core/persistence.py`. Las signatures de los 10 helpers se mantienen. Los módulos NO se tocan.

---

## Referencias

- Skill: `.claude/skills/data-persistence-standard.md`
- Skill complementario: `.claude/skills/account-health-standard.md`
- Agente: `.claude/agents/data-persistence-specialist.md`
