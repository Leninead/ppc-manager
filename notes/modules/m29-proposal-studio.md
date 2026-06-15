---
tipo: modulo
actualizado: 2026-06-12
---

# M29 — Proposal Studio

Módulo Sales Director del Agency OS. Generación de propuestas comerciales bilingües (ES/EN) en HTML + PDF.

## Estado al 2026-06-12

- **Rediseño visual PDF**: 100% del scope nuestro cerrado.
- **Persistencia**: LocalJsonStorage activo. SupabaseStorage codeada + testeada (10 tests con FakeTransport), esperando wiring productivo (pago Edu).
- **Suite**: 310 verde.

## Supabase swap day — el día que Edu pague

### Estado actual (2026-06-12)
- Clase `SupabaseStorage` operativa en `core/proposal_persistence.py` L221+.
- Cliente REST propio (`_RequestsTransport` L190-218), sin dependencia `supabase` SDK.
- 10 tests verdes en `tests/test_proposal_supabase_storage.py`.
- Auto-detección por credenciales en `_storage_config()` L328 — sin feature flag.
- En local sin env vars: corre `LocalJsonStorage` por default.

### Prerequisitos
- Plan Supabase Pro habilitado en workspace Capybaras (pendiente — espera pago Edu).
- URL del proyecto + ANON KEY (lectura/escritura con RLS off, o SERVICE_ROLE para bypass total).

### Paso 1 — DDL en Supabase

Pegar en SQL Editor de Supabase Dashboard. El DDL canónico vive en el docstring de `SupabaseStorage` (`core/proposal_persistence.py` L226-244):

```sql
create table if not exists proposals (
    id          text        not null,
    version     integer     not null,
    client_name text,
    status      text,
    archetype   text,
    updated_at  text,
    data        jsonb       not null,
    primary key (id, version)
);
create index if not exists proposals_id_idx on proposals (id);

create table if not exists proposal_votes (
    id          text        primary key,
    module_id   text        not null,
    voter_name  text,
    voted_at    text,
    proposal_id text
);
```

**Modelo de datos**:
- `proposals`: blob JSONB en `data` + 6 columnas denormalizadas (client_name, status, archetype, updated_at) para filtros futuros. PK compuesta `(id, version)` → upsert idempotente vía PostgREST `Prefer: resolution=merge-duplicates`.
- `proposal_votes`: append-only por interest tracking. Schema en `_VOTE_COLUMNS = ["id", "module_id", "voter_name", "voted_at", "proposal_id"]`.

### Paso 2 — Inyección de credenciales

**Local** — editar `.streamlit/secrets.toml`:
```toml
[supabase]
url = "https://xxxxx.supabase.co"
key = "eyJhbGc..."
```

**Streamlit Cloud** — Settings → Secrets, mismo formato TOML.

**Alternativa env vars**: `SUPABASE_URL` + `SUPABASE_KEY`. `_storage_config()` también las detecta.

### Paso 3 — Restart + smoke

```bash
streamlit run app.py
```

Verificación:
1. Abrir Proposal Studio → crear propuesta de prueba con datos triviales.
2. Supabase Dashboard → Table Editor → `proposals` → debe aparecer fila nueva.
3. Editar la propuesta → guardar → nueva fila con `version` incrementada (misma PK `id`).
4. (Opcional) Logs Streamlit deberían mostrar `_default_storage() → SupabaseStorage`.

### Paso 4 — Migración de propuestas locales (opcional, conservar histórico)

Script ad-hoc, correr una vez, NO commitear:

```python
import json
import glob
import os
from core.proposal_persistence import SupabaseStorage, _storage_config

# Forzar SupabaseStorage explícitamente
cfg = _storage_config()
assert cfg is not None, "Faltan credenciales — revisar secrets.toml"
storage = SupabaseStorage(cfg)

# Loop sobre todos los JSON locales
for path in sorted(glob.glob("data/sales/proposals/*.json")):
    with open(path, "r", encoding="utf-8") as f:
        proposal = json.load(f)
    storage.write_proposal(proposal)
    print(f"Migrado: {os.path.basename(path)}")

print("Migración completa.")
```

**Idempotente**: re-ejecutar el script es seguro (upsert por PK `(id, version)`). Si falla a mitad de camino, simplemente re-correr.

### Paso 5 — Cleanup post-migración

- Confirmar que las propuestas migradas se ven en UI (Listado de propuestas).
- Backup local: NO borrar `data/sales/proposals/*.json` por al menos 1 semana.
- Si Supabase falla post-swap, `LocalJsonStorage` vuelve a kick-in automáticamente removiendo las credenciales del `secrets.toml` (sin código).

### Rollback de emergencia

Comentar las líneas `[supabase]` del `secrets.toml`, restart. Sin código que cambiar.

### Pendientes después del swap

- Decisión RLS (Row Level Security): hoy single-tenant, RLS off aceptable. Si en algún momento se abre a multi-cliente, evaluar políticas por `client_name`.
- Tests E2E con instancia Supabase real (los actuales son 10 con FakeTransport).

## Roadmap pendiente del módulo

### Dependencias externas (no controlables hoy)
- **Chart V3 data real**: contrato v2 Ramiro (B7 importer DataDive → V3 block).
- **Galería V5 funcional**: contrato v2 Ramiro.
- **F3 marcas reales**: Freddy + compliance LTD/M&B/Setex.
- **Hidratado Tier 2-3 (V17-V22)**: inputs externos por cliente.

### Deuda técnica P3 (no urgente, ver `notes/daily/2026-06-12.md` sección "Deudas P3 silenciosas")
8 ítems listados, ~30-40 min CC en un turno corto cuando se decida cerrar.
