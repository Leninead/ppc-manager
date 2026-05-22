---
modulo: M27
bloque: B6
estado: plan-pre-implementacion
fecha_plan: 2026-05-22
autor: chat-m27 + claude-code
sesion_target: proxima-m27
---

# Plan ejecutivo B6 — UI integration M27 v1.1

## Decisión arquitectónica

**Opción (b)** — toggle radio v1/v1.1 al inicio de `_render_marketplace` con auto-detección del modo recomendado por `_detect_schema()`.

### Justificación

- Preserva v1 estable (cobertura same-schema validada con clientes reales — Gamboa, etc.).
- v1.1 expuesto como opt-in con auto-detección guiando al AM (UX low-friction).
- Bajo costo de implementación: ~50-80 LOC.
- Diagnostics enriquecidos en modo v1.1 sin romper UX v1.
- Path de evolución linear: cuando v1.1 madure (más enum maps, más cobertura), se promueve a default y v1 queda como "Modo legacy" hasta deprecate explícito.

### Anti-recomendaciones explícitas

- **NO** opción (a) tabs anidadas → 10 tabs visibles arruina UX.
- **NO** opción (c) reemplazo total → riesgo regresión MUY alto, falta matriz cell-by-cell vs ~5-10 pares same-schema reales. Conversación v2.0 mínimo.

## Stats del smoke E2E (referencia)

Par real Gamboa coat (ALRBB093 fptcustom → COAT__5_ ptd):

- Cobertura B3: 69/164 fields OLD (42.1%)
- 3 enum translators activos (Update Delete, Parentage, Product ID Type)
- 7 rows OLD → 7 rows NEW
- 152 valores migrados (avg 21.7/row)
- B5-b: 149 missing_required_in_old + 1 end_of_data_reached (row 12)
- B5-c: 118 unmapped_field + 21 missing_required_in_new
- Codes deprecated_* y unknown_enum_value: 0 (data-dependiente)
- Performance: 1.27s E2E (openpyxl 925ms, pipeline <350ms)

## Diseño UI propuesto

### Cambios en `_render_marketplace(suffix, sheet_names)` (L1916-2149)

#### Paso 1 — Auto-detección post-parse

Después de parsear ambos uploaders (L1971-1999), si ambos están parseados, ejecutar `_detect_schema(wb)` sobre ambos workbooks. **Reabrir wb desde bytes** (patrón existente `_open_ws`).

```python
# Pseudocódigo, NO copiar literal
recommended_mode = "v1"  # default
auto_detect_note = None
if old_parsed is not None and new_parsed is not None:
    old_ws, old_wb = _open_ws(old_parsed)
    new_ws, new_wb = _open_ws(new_parsed)
    old_schema = _detect_schema(old_wb)
    new_schema = _detect_schema(new_wb)
    if old_schema != new_schema and old_schema != "unknown" and new_schema != "unknown":
        recommended_mode = "v1.1"
        auto_detect_note = f"Detectamos schema cross: {old_schema} → {new_schema}. Recomendamos Cross-schema."
    elif old_schema == new_schema:
        auto_detect_note = f"Detectamos schema same: ambos {old_schema}. Recomendamos Same-schema."
```

**Costo de la doble apertura**: ~100ms estimado (openpyxl load es lo caro). Aceptable.

#### Paso 2 — Radio con default auto-detectado

```python
mode = st.radio(
    "Modo de migración",
    options=["Same-schema (v1)", "Cross-schema (v1.1)"],
    index=0 if recommended_mode == "v1" else 1,
    key=k("migration_mode"),
    horizontal=True,
    help="Same-schema: 5 estrategias de matching por field_id (recomendado si ambos archivos comparten schema). Cross-schema: matching por label normalizado + traducción de enums (recomendado si los schemas difieren, ej. fptcustom → PTD).",
)
if auto_detect_note:
    st.caption(auto_detect_note)
```

**Posición exacta**: después del bloque uploaders (L1964), antes del `can_migrate` (L2003).

#### Paso 3 — Branch en "Ejecutar migración" (L2030)

```python
if mode.startswith("Same-schema"):
    result = _run_migration(old_parsed, new_parsed, ...)  # flow v1 actual sin cambios
else:
    result = _run_migration_v11(old_parsed, new_parsed, ...)  # flow v1.1 nuevo
```

#### Paso 4 — Nuevo `_run_migration_v11()` (orquestador v1.1)

Helper a crear, signature análoga a `_run_migration`. Orquesta B1→B5-c y retorna dict con shape SUPERSET del de `_run_migration`:

```python
{
    "output_rows": list[list],  # IGUAL que v1 — para reusar _build_migrated_xlsx
    "sheet_name": str,  # IGUAL
    "matched": list[str],  # IGUAL (display names)
    "not_in_new": list[str],  # IGUAL
    "only_in_new": list[str],  # IGUAL
    "data_rows_count": int,  # IGUAL
    "skipped_internal": int,  # 0 en v1.1 (no aplica)
    "dropped_example": int,  # IGUAL (si skip_example=True)
    "old_header_row_used": int,  # IGUAL (de _locate_template_headers)
    "new_header_row_used": int,  # IGUAL
    "has_old_fids": bool,  # IGUAL (siempre True en v1.1 porque _extract_old_rows requiere field_ids)
    "has_new_fids": bool,  # IGUAL
    "methods_count": dict,  # En v1.1: {"label_match": N, "alias_label": M}
    # NUEVOS v1.1:
    "enum_translators_active": int,  # len(value_map)
    "diagnostics_b5b": list[dict],  # output de _extract_old_rows
    "diagnostics_b5c": list[dict],  # acumulado de _migrate_row para cada row
    "diagnostics_by_code": dict[str, int],  # breakdown agregado
    "coverage_pct": float,  # len(field_map) / len(old_dd) * 100
}
```

**Reusa**: `_build_migrated_xlsx(output_rows, sheet_name)` y `_build_migrated_tsv(output_rows)` tal cual.

**Naming**: `_run_migration_v11()` (sub-versión 1.1). LOC esperadas: ~80-100.

#### Paso 5 — Renderer condicional de resultados

Branch en L2052+ (después de `_run_migration`):

```python
# Bloque común (kpi_cards principales) — reusa los 4 existentes
# Bloque extra v1.1 (si mode == "Cross-schema"):
if mode.startswith("Cross-schema"):
    # Nuevo expander "🔬 Diagnostics cross-schema (v1.1)"
    # Tabla de codes con counts (5 codes B5-c + 3 B5-b)
    # Si end_of_data_reached: warning bar
    # Si unmapped_field > 0: warning con preview de los primeros 10
    # Si missing_required_in_new > 0: warning con preview
    ...
```

LOC esperadas para el renderer v1.1: ~60-80.

### Cambios en `render()` (L2153-2198)

Mínimos. El expander "Cómo funciona" (L2162-2176) hoy describe solo las 5 estrategias v1. **Dividirlo en dos st.expander condicionales** o un single con dos secciones (preferida la segunda — menos clicks). LOC esperadas: ~30-40 (estructura unificada).

## Plan de implementación (próxima sesión M27)

### Bloque B6-b-1 — Orquestador v1.1 (commit aparte)

- Crear `_run_migration_v11(old_parsed, new_parsed, user_old_header_row_1, user_new_header_row_1, skip_example)`.
- Signature mismo shape que `_run_migration`.
- Output shape SUPERSET (campos comunes + 4 v1.1).
- Smoke inline (tempfile o reusar `scripts/smoke_b6a_e2e_pipeline.py` extendido).
- LOC: ~80-100.
- Test: par Gamboa coat → output shape válido + output_rows compatible con `_build_migrated_xlsx`.

### Bloque B6-b-2 — Auto-detección + radio toggle (commit aparte)

- Modificar `_render_marketplace`: auto-detección post-parse + radio con default auto.
- LOC: ~30-40.
- Test: smoke manual con Streamlit local sobre el par Gamboa coat — el toggle debe pre-seleccionar Cross-schema.

### Bloque B6-b-3 — Renderer v1.1 (commit aparte)

- Branch en bloque resultados: KPIs v1 reusados + sección diagnostics nueva.
- LOC: ~60-80.
- Test: visual smoke en Streamlit local — kpi_cards renderizan, expander diagnostics se abre, tabla codes legible.

### Bloque B6-b-4 — Expander "Cómo funciona" (commit aparte, opcional)

- Dividir expander en dos modos o unificar con secciones.
- LOC: ~30-40.
- Bajo riesgo, puede diferirse a polish.

### Bloque B6-b-5 — Audit code-reviewer (post-commits)

Patrón validado: code-reviewer Opus 4.7 sobre B6-b-1 + B6-b-2 + B6-b-3 combinados. Audit read-only. Mitigaciones en commit aparte si aplica.

## Estimación de tiempo

- B6-b-1: 45-60 min (orquestador + smoke)
- B6-b-2: 20-30 min (radio + auto-detect)
- B6-b-3: 45-60 min (renderer diagnostics)
- B6-b-4: 15-20 min (expander)
- B6-b-5 audit + mitigaciones: 30-45 min
- **Total**: 2.5-3.5h. Cabe en una sesión.

## Riesgos identificados

1. **Doble apertura de workbooks para auto-detección** (~100ms extra). Aceptable, pero medible. Si se nota, cachear `_detect_schema` por `(file_bytes_hash,)`.
2. **El campo `methods_count` no traduce 1:1 entre v1 y v1.1**. v1 tiene 5 estrategias; v1.1 tiene 2 (label_match, alias_label). Renderer v1.1 muestra solo las suyas — NO reusar el kpi_card "Match por método" del v1.
3. **`_extract_old_rows` requiere field_id_row presente**. Si el OLD no tiene field_ids (caso Category Listing), v1.1 falla → emite `no_field_ids` error. UI debe degradar a "modo Same-schema solamente" cuando esto pase. Validable con `has_old_fids` del parser.
4. **`_extract_template_rows` (L712, huérfano)**. Documentar como deuda P3 en este plan, NO tocar en B6.

## Helpers v1.1 que se conectan en B6

Los 12 helpers v1.1 huérfanos hoy:

- `_detect_schema` — usado en auto-detección
- `_parse_data_definitions` — usado por `_build_field_map` y `_extract_old_rows` y `_migrate_row`
- `_normalize_label` — usado por `_build_field_map`
- `_build_field_map` — usado por orquestador v1.1
- `_parse_valid_values` — usado por `_build_value_map`
- `_build_value_map` — usado por orquestador v1.1 y `_migrate_row`
- `_looks_like_field_id` / `_looks_like_display_label` — usados por `_locate_template_headers`
- `_locate_template_headers` — usado por orquestador v1.1
- `_extract_old_rows` — usado por orquestador v1.1
- `_migrate_row` — usado por orquestador v1.1 (loop sobre rows)

`_extract_template_rows` queda huérfano post-B6 también. Deuda P3.

## Próxima sesión — arranque

Prompt para arranque CC próxima sesión:

```
# Tarea: M27 B6-b-1 — Orquestador v1.1 _run_migration_v11

Leé `notes/modules/M27-b6-plan.md` para el contexto completo del bloque B6.
Empezamos por B6-b-1: crear `_run_migration_v11` con shape de output
superset de `_run_migration`.

[completar con detalles concretos al arrancar]
```

## Estado al cierre B6-a

- Smoke E2E: PASS 12/12 (`scripts/smoke_b6a_e2e_pipeline.py` + `_smoke_output_migrated.xlsx`, untracked)
- Discovery UI: completado (mapa de 2198 LOC, 33 funciones)
- Decisión arquitectónica: **(b) toggle radio con auto-detección** — cerrada
- Plan B6-b: este documento

3 entregables untracked en working tree:
- `scripts/smoke_b6a_e2e_pipeline.py`
- `scripts/_smoke_output_migrated.xlsx`
- `notes/modules/M27-b6-plan.md` (este archivo)

Acción en M29 cierre: decidir si estos 3 se commitean o se .gitignorean. Recomendación: commitear el script y el plan (artefactos versionables); .gitignorear el XLSX (output reproducible).
