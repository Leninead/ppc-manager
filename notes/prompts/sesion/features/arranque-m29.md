---
tipo: prompt
actualizado: 2026-05-25
categoria: sesion
subcategoria: feature
version: v1
feature_slug: m29
feature_status: activa
modulo_id: M29
---

# Arranque M29 — Proposal Studio

## Cuándo usar

Al iniciar un chat para trabajar específicamente sobre M29 (Proposal Studio).
Si la sesión toca un cliente además del módulo, combinar con el bloque del
cliente correspondiente al arrancar.

Si la feature ya está en estado `shipped` o `archivada`, este arranque sirve
solo para consulta histórica — no para sesiones de desarrollo activo.

## Prompt copiable

```xml
<role>
Sos asistente senior de Capybaras Agency trabajando con Lenin Acosta sobre la
feature M29 — Proposal Studio del repo ppc-manager (Streamlit app de gestión
Amazon PPC). Conocés la arquitectura del Agency OS y el estado actual del módulo.
</role>

<tone>
Factual, conciso, en español rioplatense. No inventes funciones, helpers, ASINs
ni decisiones que no estén escritas en el vault o el código. Si la data no
alcanza para responder con certeza, decilo.
</tone>

<background>
Antes de responder, leé en este orden — sin pedir permiso:
1. notes/CLAUDE.md (convenciones del vault)
2. notes/state/STATE-agencia.md secciones M29 (estado editores + B7 importer)
3. notes/daily/2026-05-22.md sección "M29 Proposal Studio" (cierre más reciente)
4. notes/meetings/2026-05-22-ramiro-b7-sync.md (acuerdos V3/V5 + roadmap al 28/05)
5. Este archivo completo (secciones "Estado actual", "Pendientes activos",
   "Próxima sesión")
6. modules/sales/b7_importer.py (691 LOC — API pública del importer)
7. modules/pages/proposal_studio.py (~2200 LOC — NO leer entero; mirar firmas de
   los `_render_*` / `_tab_*` de la vista que vas a tocar)
</background>

<conocimiento_operativo_feature>
**Qué es la feature:**
M29 Proposal Studio genera propuestas comerciales estructuradas para prospectos
de la agencia (módulo de Sales, no PPC). Modelo dual-mode confirmado con Ramiro
(13/05): (1) edición manual estilo "Plan D" para los bloques CORE, y (2)
importer B7 que parsea HTMLs que produce Ramiro (skills de audit) y mergea sus
datos en la propuesta. Cada propuesta es un JSON versionado contra
`proposal-v1.json`; los bloques (V1..V6+) se renderizan editables (Plan D) o
readonly (Class B) según el caso.

**Dónde vive el código:**
- modules/pages/proposal_studio.py (~2200 LOC) — UI: `_tab_listado`, `_tab_nuevo`
  (wizard 3 pasos), vista detalle, `_render_block_editor`, editores V1..V6.
  Branding: `_NARANJA`, `_NEGRO`. Catálogo cacheado: `_load_catalog_cached`,
  `_catalog_module_lookup`.
- modules/sales/b7_importer.py (691 LOC) — importer B7 v1 (extract + merge).
- modules/sales/__init__.py — package marker.
- data/_schemas/proposal-v1.json — schema de propuesta.
- data/sales/_catalog.json — catálogo de módulos/bloques (OJO: vive en
  data/sales/, NO en data/_schemas/).
- tests/test_b7_importer.py (291 LOC, 10 tests) + fixtures b7_sample_v3v4.html /
  b7_sample_duplicate.html.

**B7 Importer v1 — API pública:**
- `extract_blocks(html_source, catalog) → ImportReport` — extractor puro
  HTML → BlockDraft. Convención `data-proposal-*` (§3). Override de valor:
  `data-proposal-value` > `<a>` href > `<img>` src > textContent. Validación §6:
  3 errores bloqueantes + 6 warnings.
- `merge_blocks(report, target, catalog) → MergeResult` — función pura, deepcopy
  del target, overwrite atómico SOLO de `block['data']` (preserva id, module_id,
  proposal_id, is_fixed, copy_overrides).
- Dataclasses exports: `ImportWarning`, `ImportError`, `BlockDraft`,
  `ImportReport`, `MergeResult`.

**Decisiones arquitectónicas cerradas:**
1. **Dual-mode** (Ramiro 13/05): manual Plan D + importer HTML B7.
2. **`merge_blocks` agnóstico al `target_proposal_id`** → resuelve D2 a nivel
   arquitectura (no necesita saber a qué propuesta mergea).
3. **Merge afecta SOLO `block['data']`** (§6 literal del contrato).
4. **Class B readonly pattern** replicado N=4 (V3+V4+V5+V6) → superó umbral N=3
   (señal para refactor genérico, ver deuda P3).
5. **`MergeResult.proposal_updated` siempre poblado** incluso con `ok=False`.
6. **Param `catalog` en `merge_blocks`** reservado para v1.1 (D3).
7. **Fix D6**: `duplicate_module_id` pasó de ERROR bloqueante a WARNING. Taxonomía:
   `duplicate_module_id_in_html` (warning, extract) + `duplicate_module_id`
   (warning, merge).

**Convenciones del módulo:**
- Editores CORE: V1 (brand_overview) + V2 (market_opportunity) editables Plan D;
  V3 (seo_opportunity) + V4 (listing_improvements) + V5 (listing_comparison) +
  V6 (growth_plan_phases) readonly Class B.
- Versionado de propuesta contra schema. Find-or-create inject script para los
  readonly.

**Dependencias internas:**
- M29 consume catálogo en data/sales/. V3 (SEO) se alimentará de la lógica de
  DataDive Analyzer (refactor de parser a `modules/parsers/`). V4 se alimenta de
  B7 HTML de la skill `digital-presence-audit` de Ramiro.
- Sub-agentes validados: data-persistence-specialist (Caso 1+2),
  html-to-streamlit-porter (Caso 1+2), code-reviewer Opus 4.7.
- Sub-agente PROHIBIDO: ppc-module-builder (4 hits de hallucination, último
  18/05 en B3-d).
</conocimiento_operativo_feature>

<bugs_y_gotchas>
**Bugs históricos resueltos** (para no re-introducir):
- **Botones Guardar V1+V2 rotos por commit `9a3eaad` (15/05)**: regresión
  detectada en smoke manual, NO por los 42/42 tests pytest (que pasaban verdes).
  Lesson: los tests pytest del módulo no cubren el flujo UI E2E → tests AppTest
  E2E quedan como DEUDA ALTA escalada el 15/05.
- **Fix D6 (22/05)**: `duplicate_module_id` detectaba pero abortaba con
  `ImportError` bloqueante críptico. Pasó a WARNING + rename
  `duplicate_module_id_in_html`.
- **B3-d-bis (`2c2a36d`)**: None literal en celdas readonly V3+V4 → convertir
  None→'' antes de armar el DataFrame.

**Gotchas activos a recordar:**
- `_catalog.json` vive en `data/sales/`, NO en `data/_schemas/`. Path frecuente
  de confundir.
- Merge solo toca `block['data']` — si algo no se actualiza, NO mutar metadata.
- Próxima sync Ramiro: el daily y el frontmatter del meeting dicen "viernes
  30/05", pero 30/05/2026 cae **sábado** (29/05 es viernes). Confirmar fecha
  exacta antes de comprometer entregables a esa reunión.

**Deuda blanda registrada:**
- P2: UI dispatcher del importer en `proposal_studio.py` (depende de D2 informal).
- P2: template launch desactualizado vs catálogo (`_DEMO_AgencyOS` tiene 20
  blocks vs 35 en catálogo — faltan V7-V16 + V23-V29).
- P3: refactor genérico Class B (`_render_class_b_readonly` con `item_renderer_fn`)
  — reduce ~400 LOC duplicadas a ~80.
- P3: cleanup de 44 versiones del proposal `6861bbce-...` (ruido de testing).
- P3: schema `items_schema: {}` vs `null` en `_catalog.json` (D6 catalog).
- P3: short-circuit en `_extract_block_data` cuando module_id ya procesado (~3 LOC).
- Imágenes V5 automáticas (SerpAPI / Helium 10 / scraping / Chrome extension) →
  post-ship.
- Tests AppTest E2E → DEUDA ALTA.
</bugs_y_gotchas>

<rituales_obligatorios>
1. **Repo guard al inicio**: `pwd && git remote -v && git branch --show-current`
2. **Checkpoint git** antes de cambios mayores
3. **Leer código antes de editar**: nunca editar funciones sin verlas primero
4. **Smoke test MANUAL después de cada bloque UI** (pytest no cubre el flujo de
   botones Guardar — lección del bug `9a3eaad`)
5. **Si tocás archivos compartidos con otro chat paralelo**: avisar y commitear
   con path específico, no `git add .`
</rituales_obligatorios>

<task>
Al final del bloque <background>, devolveme un briefing de 4-6 bullets:
- Estado actual del módulo (último commit + % avance si aplica)
- Pendientes activos prioritizados
- Próxima sesión propuesta (bloque concreto + estimación) — anclar al plan al 28/05
- Bloqueos o dependencias si los hay (incluir confirmación fecha sync Ramiro)
- Pregunta abierta: "¿Arrancamos con el UI dispatcher B7 (V3+V4) del lunes 25/05
  o tenés otra cosa en mente?"
</task>
```

---

## Estado actual del módulo

> Esta sección se actualiza automáticamente al cierre de cada sesión que toque
> esta feature.

**Último commit relevante:** `093e686` — feat(M29): B7 UI dispatcher D2 -
expander + uploader + ImportReport preview — 2026-05-25 (chat #1/4 multi-frente).

**Progreso global:** 6/6 editores CORE cerrados. B7 Importer v1 cerrado. UI
dispatcher B7: D1 (discovery) + D2 (skeleton+preview) cerrados; D3+D4
pendientes. Ship target: jueves 28/05.

**Sub-bloques cerrados:**
- V1 (brand_overview) + V2 (market_opportunity) — editables Plan D
- V3 (seo_opportunity) + V4 (listing_improvements) + V5 (listing_comparison) +
  V6 (growth_plan_phases) — readonly Class B
- B7 Importer v1: `extract_blocks` (capa 1) + `merge_blocks` (capa 2) + fix D6
- UI dispatcher B7 D1: discovery cerrado (catalog crudo confirmado para
  importer; `pp.save_proposal` auto-bumpea version e ignora input; naming
  `<uuid>__v<N>.json`)
- UI dispatcher B7 D2: expander en `_render_detail_screen` + file_uploader +
  parser → ImportReport preview (counts, tablas warning/error, cards
  apply/skip, debug expander, footer condicional `report.ok`). +168 LOC en
  `_render_b7_importer_section`. Smoke E2E con `b7_sample_v3v4.html` PASS
  (Blocks=2, Warnings=6, Errors=0).

**Sub-bloques pendientes (hacia ship 28/05):**
- UI dispatcher B7 D3 (apply + 2-clicks + save) — 60min
- UI dispatcher B7 D4 (hardening + smoke E2E final) — 40min
- Refactor DataDive parsers → `modules/parsers/` + mapper V3 — 3-4h (martes)
- Editor manual V5 (URLs pareadas) + testing + smoke — 3-4h (miércoles)
- Testing E2E + bugfixing + SOP + ship — 3h (jueves)

**Tests:** B7 importer 10/10 verde (`tests/test_b7_importer.py`, suite 0.20s).
FALTA: tests AppTest E2E del flujo UI (deuda ALTA — agudizada por incidente
"edits fantasma" del 25/05 que el smoke manual no detectó hasta el commit).

**Smoke status:** D2 dispatcher UI PASS con fixture canónica
`tests/fixtures/b7_sample_v3v4.html` (25/05). B7 extract 10/10 + merge 5/5 +
fix D6 3 hitos verde (22/05).

---

## Pendientes activos

> Esta sección se actualiza al cierre. Ordenar por prioridad: P0 → P1 → P2 → P3.

**P0 — bloqueante:**
- (ninguno)

**P1 — alta prioridad (camino al ship 28/05):**
- UI dispatcher B7 D3 (apply + 2-clicks + save) — bloque inmediato martes
- UI dispatcher B7 D4 (hardening + smoke E2E final)
- Refactor DataDive parsers → `modules/parsers/` + mapper V3
- Editor manual V5 (URLs pareadas)
- Testing E2E + SOP + ship
- Tests AppTest E2E (deuda ALTA — agravada por incidente fantasma 25/05)

**P2 — media:**
- Validar con consolidador #5 si el commit `252f286` (mensaje M27, contenido
  -147 LOC en flat_file_migrator.py, ex-`64e3d6f` mal etiquetado M29) era
  intencional del chat #2 o accidente capturado
- Template launch desactualizado vs catálogo (`_DEMO_AgencyOS` 20 vs 35 blocks)

**P3 — baja / deuda blanda:**
- Refactor genérico Class B (`_render_class_b_readonly`) — ~400→~80 LOC
- Cleanup 44 versiones del proposal `6861bbce-...`
- Schema `items_schema: {}` vs `null` en `_catalog.json` (D6 catalog)
- Short-circuit en `_extract_block_data` (~3 LOC)
- Imágenes V5 automáticas → post-ship

---

## Próxima sesión propuesta

> Esta sección se actualiza al cierre con el bloque concreto a ejecutar la
> próxima vez que se trabaje esta feature.

**Bloque a ejecutar:** Martes 26/05 — UI dispatcher B7 D3 + D4 (cierre del
bloque). D3 = apply quirúrgico: botón "Aplicar merge" con confirmación
2-clicks (flag `ps_b7_confirm_apply_{pid}` en session_state), llamada a
`merge_blocks(report, proposal, catalog)`, persistencia vía
`pp.save_proposal(merge_result.proposal_updated)` que auto-bumpea version,
banner verde post-save con vN→v(N+1), `st.rerun()`. D4 = smoke E2E con casos
edge (b7_sample_duplicate.html para validar fix D6 en UI; HTML inválido para
validar error path). Una vez cerrado, pivot al bloque "Refactor DataDive
parsers → modules/parsers/ + mapper V3" del plan al 28/05.

**Pre-flight:**
- Leer firma exacta de `merge_blocks(report, target_proposal, catalog) →
  MergeResult` en `modules/sales/b7_importer.py` (la firma estuvo en chat
  durante D1 pero conviene re-verificar en disco antes de cablear)
- Confirmar shape de `MergeResult.applied_blocks` / `skipped_blocks` /
  `warnings` para el summary post-merge
- Releer el helper `_render_b7_importer_section` ya en disco para entender
  dónde insertar el botón apply (después del footer condicional)
- Verificar que `_DEMO_AgencyOS` siga siendo la propuesta canónica de smoke
  (`pp.get_proposal(id)` con id `01fbf5c2...`); si subió de v12 por testing
  D3 no importa — `save_proposal` versiona limpio

**Estimación:** 1.5-2h (60min D3 + 40min D4).

**Sub-agentes Claude Code que podrían usarse:** code-reviewer (Opus 4.7) para
audit post-D4 antes de commit final. NO usar ppc-module-builder.

**Riesgos/dependencias:**
- Riesgo: bug en `_validate_proposal` si el merge produce un dict que pierde
  FK válida contra catalog (baja probabilidad — merge solo toca `block['data']`)
- Si el incidente "edits fantasma" se repite en D3, revisar si Streamlit
  está corriendo contra un buffer stale: matar proceso + re-ejecutar antes
  de smoke
- Sync Ramiro: viernes 30/05 (corregido del arranque previo). M29 debería
  estar shippeado el jueves 28/05 — un día antes de la sync

---

## Historial de sesiones

> Append-only. Una línea por sesión: fecha + resumen 1 oración + wikilink al daily.

- 2026-05-12 — S2 UI completa (Listado + Wizard 3 pasos). [[2026-05-12]]
- 2026-05-13 — S3 parcial B1+B2 vista detalle. [[2026-05-13]]
- 2026-05-14 — B3-b V1_brand_overview cerrado Plan D. [[2026-05-14]]
- 2026-05-15 — Bug Guardar V1+V2 + M29 fix Strategy 3.5 chat paralelo. [[2026-05-15]]
- 2026-05-18 — B3-c V2 validado E2E + B3-d V3 readonly + pivot dual-mode. [[2026-05-18]]
- 2026-05-20 — B3-f V5 + B3-g V6 readonly (Class B N=4). [[2026-05-20]]
- 2026-05-22 — B7 Importer v1 completo (extract + merge + fix D6 + 10 tests) + sync Ramiro. [[2026-05-22]]
- 2026-05-25 — UI dispatcher B7 D1 discovery + D2 skeleton/preview cerrados (chat #1/4 multi-frente; incidente fantasma de edits + bug commit cross-frente documentados). [[2026-05-25]]

---

## Referencias cruzadas

- [[STATE-agencia]]
- [[CLAUDE]] (root vault)
- [[2026-05-22]] (cierre M29 más reciente)
- [[2026-05-22-ramiro-b7-sync]] (acuerdos V3/V5 + roadmap al 28/05)
- [[contrato-importer-b7-v1]] (contrato B7 draft)
- [[agency-os]] (brand note del producto interno)
- [[feature-lifecycle]] (SOP del ciclo de vida de features)
