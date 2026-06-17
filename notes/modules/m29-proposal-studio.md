---
tipo: modulo
actualizado: 2026-06-16
---

# M29 — Proposal Studio

Módulo Sales Director del Agency OS. Generación de propuestas comerciales bilingües (ES/EN) en HTML + PDF.

## Estado al 2026-06-16

- **Rediseño visual PDF**: 100% del scope nuestro cerrado (2026-06-12).
- **Persistencia**: **Supabase PRODUCTIVO** en local + Cloud (wired 2026-06-16). 60 propuestas migradas (62 filas, 6 únicas). LocalJsonStorage queda como fallback automático si se quitan las credenciales.
- **Suite**: 312 verde (310 + 2 tests de regresión render fresh).

## Supabase swap day — EJECUTADO 2026-06-16

> Este playbook se ejecutó con éxito el 2026-06-16. Se conserva como referencia operativa y para futuros entornos (staging, re-setup, otro proyecto). Funcionó casi al pie de la letra; la única sorpresa fue RLS (ver Paso 1.5 agregado abajo).

### Estado post-wiring (2026-06-16)
- Clase `SupabaseStorage` PRODUCTIVA en local + Cloud.
- Cliente REST propio (`_RequestsTransport` L190-218), sin dependencia `supabase` SDK.
- 10 tests verdes en `tests/test_proposal_supabase_storage.py` (FakeTransport).
- Auto-detección por credenciales en `_storage_config()` — sin feature flag.
- Proyecto: `capybaras-os-prod` (org Capybaras PRO, region West US Oregon, MICRO).
- 60 propuestas migradas (62 filas con versiones, 6 únicas en UI).
- **RLS deshabilitado** en ambas tablas (decisión single-tenant — ver deuda de seguridad).

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

### Paso 1.5 — RLS (sorpresa no documentada originalmente)

**Tablas nuevas en Supabase tienen RLS activado por default.** Con RLS on y sin políticas, las lecturas (GET) funcionan pero las escrituras (POST/upsert) fallan con PostgREST `42501` que PostgREST traduce a **HTTP 401** (engañoso — parece auth pero es RLS).

Dos caminos:
- **Single-tenant (lo que hicimos 2026-06-16)**: deshabilitar RLS. Table Editor → cada tabla → Edit table → uncheck "Enable Row Level Security" → Save. Hacerlo en `proposals` Y `proposal_votes`.
- **Multi-tenant / exposición pública**: mantener RLS on + crear políticas INSERT/SELECT, o usar service_role key (server-side only).

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

- **Deuda de seguridad (P2)**: hoy RLS off + anon key. La anon key se compartió en un chat de trabajo durante el wiring. Rotar a service_role + RLS con políticas antes de cualquier exposición pública o multi-tenant.
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
