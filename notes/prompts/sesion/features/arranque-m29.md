---
tipo: prompt
actualizado: 2026-06-03
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
3. notes/daily/2026-06-03.md (cierre S6) sección "M29 Proposal Studio" (cierre más reciente)
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

**Último commit:** `a75fbf3` (branch `feature/m29-renderer-s5`, 4 commits sin mergear a main).

**Progreso:** S5 renderer HTML + S6 export PDF cerrados del lado del código. Suite 136 verde.

**Motor PDF:** xhtml2pdf 0.2.17 (weasyprint descartado por dependencia GTK en Windows).

**Arquitectura S6:** `core/proposal_pdf.py` (capa separada del renderer puro);
`_sanitize_html_for_pdf` adapta el HTML al motor (fonts remotas / `var()` /
letter-spacing em / flex del chart) SIN tocar el renderer ni el template.

**4 commits:** `fdf2b35` (pytest.ini testpaths), `66f104f` (S6 export PDF),
`9fe6b1f` (requirements xhtml2pdf), `a75fbf3` (sanitizado CSS).

**Pendiente:** QA local con Marcos + verificar chart V3 en PDF con datos reales +
merge a main (viernes).

---

## Pendientes activos

> Esta sección se actualiza al cierre. Ordenar por prioridad: P0 → P1 → P2 → P3.

**P0 — bloqueante:**
- (ninguno)

**P1 — alta:**
- QA local con Marcos (jueves).
- Verificar chart V3 en PDF con datos reales.
- Merge `feature/m29-renderer-s5` a main (viernes, post-QA).

**P2 — media:**
- [M27] `scripts/_scratch_M27/test_b5b_extract.py` con `sys.path.insert` hardcodeado —
  renombrar/limpiar desde el frente M27. Golpeó M29-S6 y M30 el mismo día (causa raíz
  del bug de tests del 03/06). Resuelto temporalmente con `pytest.ini testpaths=tests`.

**P3 — baja / deuda blanda:**
- `_sanitize_html_for_pdf` con regex frágil si cambia el template (fix futuro: variante
  print-friendly del template — toca S5).
- "List@" F8 + nombres de equipo F7 visibles en PDF client-facing (decisión pendiente).
- `requirements.txt` con `anthropic`/`python-dotenv` duplicados (preexistente).

---

## Próxima sesión propuesta

> Esta sección se actualiza al cierre con el bloque concreto a ejecutar la
> próxima vez que se trabaje esta feature.

**Jueves 2026-06-04:** (1) verificar chart V3 en PDF con datos reales — ayer no se
pudo, la data cruda en `block['data']` no llegó al render por el overlay
`_transform_v3_chart` (`core/proposal_renderer.py` ~L245); (2) QA local con Marcos
(setup: `pip install -r requirements.txt`, xhtml2pdf sin GTK); (3) según QA, fixes +
merge a main.

**Worktree:** `C:\proyectos\ppc-manager-s5`, branch `feature/m29-renderer-s5`.

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
- 2026-05-26 — D3+D4 mergeado a main (458fb4b) + DataDive mapper en branch (0aa5261, pendiente merge). E1→E5 cerrados, suite 95/95. [[2026-05-26]]
- 2026-06-03 — S5 renderer cerrado + S6 export PDF (xhtml2pdf, 4 commits, suite 136). Bug de discovery (scratch M27) resuelto con pytest.ini. [[2026-06-03]]

---

## Referencias cruzadas

- [[STATE-agencia]]
- [[CLAUDE]] (root vault)
- [[2026-05-22]] (cierre M29 más reciente)
- [[2026-05-22-ramiro-b7-sync]] (acuerdos V3/V5 + roadmap al 28/05)
- [[contrato-importer-b7-v1]] (contrato B7 draft)
- [[agency-os]] (brand note del producto interno)
- [[feature-lifecycle]] (SOP del ciclo de vida de features)
