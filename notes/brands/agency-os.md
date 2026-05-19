---
tipo: brand-history
brand: Capybaras Agency OS
actualizado: 2026-05-13
---

# Capybaras Agency OS — Brand History

Historial de evolución del Agency OS — el sistema operativo propio de Capybaras Agency. Esta nota acumula los hitos arquitectónicos, módulos lanzados y decisiones estratégicas que diferencian al Agency OS de cualquier stack genérico de agencia.

---

## 2026-05-12 — M29 Proposal Studio Sesión 2 (UI completa)

**Status:** UI funcional E2E. Listado + Wizard 3 pasos + Save persistente. Vista detalle y edición de blocks pendientes para Sesión 3.

Construido en branch `main` (workflow main-only post-merge S1), commit `aa2d873`. 1075 insertions, ~900 LOC en `modules/pages/proposal_studio.py` + edits en `app.py` + `core/constants.py`.

### Qué se agregó al Agency OS

- **Nueva sección sidebar** `📋 SALES DIRECTOR` entre ACCOUNT y KNOWLEDGE (28 módulos activos ahora, badge dinámico del Inicio se actualizó automáticamente).
- **Listado de propuestas** con filtros (cliente/arquetipo/status), cards visuales con badges color-coded por tier y status, tiempo relativo legible, acciones Abrir/Duplicar/Archivar con soft delete (2-click confirmation).
- **Wizard 3 pasos** con state machine en `session_state`, progress bar visual, validación por paso, debug expander.
- **Save persistente** vía `pp.save_proposal()` con auto-versionado + flag `ps_just_saved` para banner verde de éxito en Listado.

### Smoke test E2E (validado en chat con Lenin)

Propuesta de prueba "Gamboa" creada con arquetipo launch + es:
- 18 blocks instanciados desde `launch-new-brand.json`
- UUID v4 generado, version 1, status draft, ISO 8601 timestamps
- Validación del schema pasó (8 FIXED presentes, FK enforcement)
- Apareció correctamente en Listado con todos los metadatos
- Botones Abrir (placeholder S3) + Duplicar + Archivar funcionales

### Roadmap actualizado de las 6 sesiones

- ✅ S1: Schema + persistencia + templates + parser (2026-05-11)
- ✅ S2: UI Streamlit completa — Listado + Wizard 3 pasos + Save (2026-05-12)
- ⏳ S3: Vista detalle (botón Abrir) + 6 CORE Variables funcionales (V1-V6)
- ⏳ S4: 23 placeholders Tier 2-3 con toggle "Marcar como interesado"
- ⏳ S5: Templates Jinja2 + renderer HTML
- ⏳ S6: Playwright PDF + polish + smoke test E2E + update READMEs

### Por qué importa este hito

Con S2 cerrada, **un Sales Director puede crear y persistir propuestas reales** usando el módulo — no es una shell visual. El siguiente cuello de botella es la edición de los 6 CORE Variables (S3), que es lo que convierte propuestas "default del template" en propuestas customizadas por cliente real.

### Hardening post-cierre y comunicación pública (mismo día)

Después del commit de cierre `5a1a575`, el día tuvo 2 milestones adicionales:

**Commit `28a6d69` — fix Duplicar**: durante testing manual del Listado se detectó que click en "Duplicar" tiraba FK mismatch (proposal_id de blocks no matcheaba con el nuevo id de la propuesta padre). Fix quirúrgico: generar new_proposal_id ANTES del save y propagarlo a todos los blocks en una sola pasada. Lección operativa: validadores estrictos requieren que los IDs padre se generen antes, no después.

**Primer update público del módulo a toda la agencia**: comunicación a CEO + directores + ops + ventas + diseño en Slack, redactada en 6 iteraciones para encontrar el tono correcto. Decisiones clave:

- **Estructura por fases 1-6** con propósito de negocio (no detalles técnicos)
- **Objetivo cuantificable** como hook: 10 min vs 2-4 horas
- **Compromiso público de timeline**: fases 3+4 esta semana, fases 5+6 próxima
- **Distinción HTML interactivo (calls de venta) vs PDF estático (circulación interna)** — diferencial técnico que sin mencionarlo se perdía
- **Feedback async, sin oferta de demo en vivo** (mantiene el control de tiempo del autor)

Tras este update, la cadencia esperada de M29 cambia: antes era "una sesión semanal según disponibilidad", ahora es "fases 3-6 en 7-10 días corridos". Mitigación: priorizar S3 (la compleja) primero, S4 puede caer en cualquier hueco.

---

## 2026-05-11 — M29 Proposal Studio Sesión 1 (Sales Director module)

**Status:** Schema + persistencia listos. UI pendiente para Sesión 2.

Construido en branch `feat/m29-proposal-studio` (commit `affc575`).

### Qué es M29 Proposal Studio

Módulo de la sección **Sales Director** del Agency OS. Reemplaza el workflow manual donde los Sales Directors armaban propuestas comerciales copiando/pegando slides de PowerPoints viejos. Output dual: HTML standalone (para presentar en vivo) y PDF (para enviar al cliente).

### Arquitectura

- **Schema canónico:** `data/_schemas/proposal-v1.json` — 5 entidades
- **Catálogo:** `data/sales/_catalog.json` — 37 módulos en 4 tiers (`fixed` / `core_variable` / `common_variable` / `specialized_variable`)
- **Templates:** 4 arquetipos de cliente (`launch` / `scale_seo` / `defense` / `cvr`) que pre-cargan blocks
- **Persistencia:** `core/proposal_persistence.py` con clase abstracta `ProposalStorage` + impl `LocalJsonStorage`. Preparada para swap a `SupabaseStorage` post-decisión Freddy.

### Por qué importa para Capybaras

1. **Monetiza el Agency OS como diferenciador comercial.** El pilar "Proprietary Operating System" en Why Capybaras v3 hace explícito lo que antes era invisible: tenemos infraestructura propia que ninguna agencia LATAM tiene.
2. **Captura Voice of Sales Director.** El toggle "Marcar como interesado" en bloques placeholders permite priorizar el roadmap del módulo basado en demanda real de los Sales Directors, no en lo que Lenin asume que necesitan.
3. **Bilingüe EN/ES desde día uno.** Habilita escalar a clientes US sin re-trabajo.
4. **Versionado por propuesta.** Cada cambio crea nueva versión — historial completo + auditoría.

### Roadmap de las 6 sesiones

- ✅ S1: Schema + persistencia + templates + parser (hecho)
- ⏳ S2: UI Streamlit (wizard creación + listado + sidebar)
- ⏳ S3: 6 CORE Variables funcionales (V1 Brand Overview, V2 Category Overview, V3 SEO Opportunity, V4 Listing Improvements, V5 Listing Comparison, V6 Growth Plan)
- ⏳ S4: 23 placeholders Tier 2-3 con toggle "Marcar como interesado"
- ⏳ S5: Templates Jinja2 + renderer HTML
- ⏳ S6: Playwright PDF + polish + smoke test E2E + update READMEs

### 5 propuestas seed analizadas como base de diseño

1. **Sunny Zebra (Feb 2026)** — cliente existente fly masks, foco main image + infographics
2. **Happy Mammoth (Feb 2026)** — supplements, foco SEO opportunity + PPC audit completo (5 sub-módulos)
3. **Garland Rug (May 2026)** — nueva marca rugs, foco launching plan modular (Amazon + Shopify + Meta + Marketplaces)
4. **Nandog (Apr 2026)** — dog beds, foco market trend + price sweet spot
5. **Nobl Travel (Apr 2026)** — luggage US, foco branded terms + defensive campaigns

---

## 2026-05-14 — M29 Proposal Studio B3-b cerrado + Sesión A.1 (skip-save guard)

### M29 Proposal Studio — B3-b cerrado (sesión PM)
- Editor V1_brand_overview funcional con Plan D (buffer mutable)
- 4to intento de fix fue el bueno — Streamlit 1.43.2 tiene anti-patterns documentados
- Skip-save guard suma capa de control: no se escriben versiones idénticas
- 39 tests verdes
- Pattern listo para B3-c (drop-in con `elif module_id == "V2_xxx"`)

---

## 2026-05-13 — M29 Proposal Studio Sesión 3 parcial (B1+B2)

**Status:** Vista detalle de propuestas funcional en modo readonly. Botón
"Abrir" del Listado ahora abre una pantalla detalle que reemplaza los tabs y
muestra todos los blocks de la propuesta con badges por tier (editable/locked/
próximamente). Edición real de los CORE Variables queda para B3-B6.

Construido en branch `main`. Commits: `6b0f2dc` (S3-B1 routing + state
machine + skeleton) + `5cc0fd3` (S3-B2 listado readonly de blocks con badges
por tier). Ambos sin push — acumulando hasta cierre de B6 según patrón S2.

### Qué se agregó al Agency OS

- **Vista detalle de propuestas** en `modules/pages/proposal_studio.py`. Click
  en "🔎 Abrir" desde el Listado reemplaza la pantalla por una vista dedicada
  con header completo (cliente, version, arquetipo, status, idioma, count de
  blocks, timestamps) + listado de los 15-18 blocks de la propuesta +
  expander de debug con el JSON crudo.
- **Badges visuales por tier + status**: los 6 CORE editables se destacan en
  naranja Capybaras, los placeholders S4 en amarillo con opacity reducida,
  el resto (FIXED + COMMON + SPECIALIZED active) en gris solo-lectura.
  Border-left de cada card pintado con el color del tier.
- **State machine de vista detalle** independiente de la del wizard:
  `ps_detail_active` (UUID o None) + `ps_detail_buffer` (dict para los edits
  pendientes de B3). Inicialización en `render()` con `_init_detail_state()`.
  Conviven sin interferencias con la state machine del wizard de creación.

### Hallazgos del smoke test

La validación visual con las 3 propuestas demo confirmó que **la composición
de CORE Variables varía por arquetipo**:

- Launch (18 blocks): V1, V2, V3, V4
- CVR (15 blocks): V1, V2, V5
- Scale+SEO (16 blocks): V1, V2, V3, V5, V6

Eso obliga a que B3 (forms editables) itere sobre los CORE PRESENTES en cada
propuesta, no sobre los 6 hardcodeados. Dispatch por `module_id`.

Primera aparición visible de COMMON tier (V13, V14, V16) y de placeholders
S4 (V27, V28, V29). Render correcto para los 4 tiers + 2 status combinables.

### Roadmap actualizado de las 6 sesiones

- ✅ S1: Schema + persistencia + templates + parser (2026-05-11)
- ✅ S2: UI Streamlit completa — Listado + Wizard 3 pasos + Save (2026-05-12)
- 🔄 S3: Vista detalle + 6 CORE Variables editables (en curso)
  - ✅ B1: routing vista detalle (2026-05-13)
  - ✅ B2: listado readonly de blocks (2026-05-13)
  - ⏳ B3-b: V1 Brand Overview end-to-end (próxima sesión)
  - ⏳ B3-c a B3-f: V2, V3, V4, V5, V6
  - ⏳ B5: botón Guardar funcional + version bump
  - ⏳ B6: polish + push acumulado
- ⏳ S4: 23 placeholders Tier 2-3 con toggle "Marcar como interesado"
- ⏳ S5: Templates Jinja2 + renderer HTML
- ⏳ S6: Playwright PDF + polish + smoke test E2E + update READMEs

### Por qué importa este hito

Con B1+B2 cerrados, el Sales Director ya puede **abrir y explorar** cualquier
propuesta del Listado. La pantalla detalle hace visible toda la información
del template aplicado: qué bloques tiene, en qué orden, de qué tier, qué se
puede editar y qué no. Es la transición de "lista opaca" a "explorador
funcional". B3 (la siguiente) es donde la herramienta empieza a "escribir
hacia atrás" y permite customizar el contenido por cliente.

### Compromiso público de timeline

El compromiso de Slack del 12/05 sigue en pie: fases 3+4 esta semana
(13-18 may). Sesión 3 está en curso dentro de plazo. Si B3-B6 no termina
antes del fin de semana (17-18 may), avisar al canal con reset de
expectativas.

---

## 2026-05-18 — M27 v1.1 cross-schema (B1-B3) + M29 B3-c validation + B3-d V3 readonly + pivot dual-mode

### M27 v1.1 cross-schema — 3 sub-bloques cerrados

3 commits sobre `flat_file_migrator.py` (+220 LOC, 5 helpers nuevos + 1 constante):
- B1 schema detector (fptcustom vs PTD)
- B2 Data Definitions parser (164 old fields, 225 new fields)
- B3 cross-schema field mapper (69/164 = 42% cobertura con _LABEL_ALIASES iterativo)

Decisión estratégica: v1 same-schema descartado, pivot a v1.1 cross-schema (PTD migration). MX fuera de v1. B4 dividido en B4a (valid values parser, schema-agnostic) + B4b (enum translator, hardcoded).

### M29 Proposal Studio — Sesión 4 cerrada con pivot estratégico

**Estado de los 6 CORE editores** (actualizado):
- ✅ V1_brand_overview (Plan D, B3-b, 14/05)
- ✅ V2_category_overview (Plan D, B3-c, validado E2E hoy 18/05 con propuesta `01fbf5c2` v1→v5)
- ✅ V3_seo_opportunity (READONLY B3-d, viene de importer B7 — implementado hoy, fix Int64 visual con bug pendiente)
- ⏳ V4_listing_improvements_current_state (B3-e, próxima sesión, descubrimiento schema pendiente)
- ⏳ V5_listing_comparison_competitor
- ⏳ V6_growth_plan_phases (último por complejidad — array anidado de fases bilingüe)

**Pivot dual-mode confirmado** post-reunión con Ramiro 13/05:

M29 tendrá DOS planos de entrada por propuesta:
1. **Manual** — editores Plan D (V1, V2, V4-V6 cuando estén).
2. **Importer HTML B7** — drag-drop de HTMLs generados por skills `amazon-brand-audit` y `digital-presence-audit` de Ramiro, autohidrata `ps_buffer__{pid}`. Bloque nuevo en roadmap.

Las dos rutas terminan en el mismo commit pipeline (`_build_v*_payload` → `_commit_v*_to_disk` → `pp.save_proposal`).

**Clasificación de blocks** descubierta:
- **Class A — campos planos** (V1, V2, probablemente V4): pattern Plan D actual.
- **Class B — arrays<object> importados** (V3, posiblemente V6): readonly hasta B7, prefilled por importer.

Próxima reunión Ramiro: viernes 22 a las 3 PM. Para esa fecha hay que tener: V4 cerrado, contrato `data-*` mini-doc para Ramiro, plan B7 timeline.

### Por qué importa este hito

Con B3-c validado E2E y B3-d como readonly architecturally-honest, el bucle "editar manual → guardar versionado → render visible" está cerrado para Class A. La ruta del importer queda definida como bloque futuro con contrato técnico claro, no como vapor estratégico.

### Roadmap actualizado M29

- ✅ S1: Schema + persistencia + templates + parser (11/05)
- ✅ S2: UI Streamlit completa — Listado + Wizard 3 pasos + Save (12/05)
- 🔄 S3: Vista detalle + 6 CORE Variables editables (en curso, 3 de 6)
  - ✅ B1+B2: routing + listado readonly (13/05)
  - ✅ B3-b: V1 Plan D (14/05)
  - ✅ A.1: skip-save guard (14/05)
  - ✅ B3-c: V2 Plan D validación E2E (18/05)
  - ✅ B3-d: V3 readonly + Int64 fix (18/05, visual bug pendiente)
  - ⏳ B3-e: V4 (próxima sesión)
  - ⏳ B3-f: V5
  - ⏳ B3-g: V6 (último)
  - ⏳ B5: botón Guardar global + confirmación 2-clicks
  - ⏳ B6: polish + push acumulado
- 🆕 B7: HTML importer (post-B6, contrato `data-*` con Ramiro como dependencia)
- ⏳ S4: 23 placeholders Tier 2-3 con toggle "Marcar como interesado"
- ⏳ S5: Templates Jinja2 + renderer HTML
- ⏳ S6: Playwright PDF + polish + smoke test E2E + READMEs

---

## 2026-05-19 — M27 v1.1 B4 cerrado + B5-a con audit code-reviewer

### M27 v1.1 cross-schema — 2 sub-bloques cerrados (B4) + 1 arrancado (B5-a)

5 commits sobre `flat_file_migrator.py` (+365 LOC):
- B4a (9c85e06) — `_parse_valid_values` schema-agnostic
- B4b (c11faf0) — `_ENUM_VALUE_MAP` (3 enums conservador A1+) + `_build_value_map` + `_DEPRECATED_OLD_ENUMS`
- B5-a (07e79fb) — `_locate_template_headers` con D1+fallback (auto-detección + safety net hardcoded)
- 64f25db — mitigaciones post-audit code-reviewer (P2 #4 + P1 #3)

Progreso M27 v1.1: 62% → 75% (5/8 sub-bloques). Falta B5-b/B5-c + B6 (~2-3 sesiones).

### Decisiones de diseño cerradas

**`_ENUM_VALUE_MAP` conservador (A1+/B2/C1)**: cubre 3 enums críticos con mapping 1:1 identidad o rewording confirmado (update_delete↔listing_action, parentage↔parentage_level, product_id_type parcial). ISBN y GCID quedan como `None` (deprecated, B5 flagea para revisión manual). `Relationship Type` y `Variation Theme` van a `_DEPRECATED_OLD_ENUMS` (PTD schema gap). Justificación: Marcos único usuario hoy + Capybaras no maneja books + mappings agresivos no escalan al equipo amplio.

**D1+fallback en header locator**: justificado empíricamente — fptcustom tiene 3 rows header (data row 4), PTD tiene 5 rows header (data row 6). La asimetría prueba que Amazon NO es consistente entre schemas → auto-detección compra resiliencia a cambios futuros sin perder el safety net hardcoded.

### Audit code-reviewer en uso operativo (2do hit)

`code-reviewer` (Opus 4.7) invocado POST-commit sobre B5-a. Veredicto: APPROVE WITH CONCERNS — 0 bugs activos, 3 P1 robustez, 2 P2 edge cases, 2 P3 no-issues. Trazó manualmente las 3 trayectorias del helper (fptcustom auto, ptd auto, fallback) confirmando los asserts.

Aplicamos 2 mitigaciones (guard banner walk-up + docstring fail-closed). Otras 2 (P1 #1, P1 #2) quedan documentadas como deuda blanda — mitigadas hoy por B2 cross-validation, especulativas hasta caso real.

Patrón consolidado: audit post-commit > audit during-commit. CC ejecuta libre + reviewer audita estático en read-only + fix quirúrgico en commit separado si aplica. Validado en M28 (09/05) y replicado hoy con resultado limpio.

### Coordinación chat paralelo M29

Sin colisiones en este día. M29 chat paralelo committeó `2f436a0` (B3-e V4 readonly) + `2c2a36d` (B3-d-bis None fix) en su scope (`proposal_studio.py`, `scripts/inject_v4_demo.py`). Ningún archivo de los nuestros tocado.

### Por qué importa este hito

Con B4 cerrado y B5-a verde, las 5 piezas de "knowledge extraction" del módulo están completas: schema detector, data definitions parser, field mapper, valid values parser, value translator, header locator. B5-b/B5-c son la traducción row-level — composición de las piezas existentes con lógica row-by-row. B6 es UI Streamlit puro. La parte difícil (descubrimiento del schema cross-format) terminó.

---

### M29 Proposal Studio — sesión PM 2026-05-19

**5 commits locales sobre main:**
- `2f436a0` — B3-e V4_listing_improvements_current_state readonly (Class B + banner B7)
- `2c2a36d` — B3-d-bis fix None literal en celdas readonly V3+V4
- `64cf644` — inject scripts apuntan a _DEMO_AgencyOS (housekeeping)
- `757292d` — items_schema formal V3+V4 + convención proposal-v1 (pre-B7 contract)

**Vault deliverable:**
- `notes/sales/contrato-importer-b7-v1.md` v1.0 (Draft pre-reunión 22/05)

**Estado M29 al cierre:**
- V1 (Plan D, 14/05) ✅
- V2 (Plan D, B3-c, 18/05) ✅
- V3 (readonly B3-d, 18/05) ✅
- V4 (readonly B3-e, 19/05) ✅
- V5+ pendientes
- Importer B7: contrato cerrado, implementación pendiente

**Pattern Class B confirmado replicable** con 2 referencias reales
(V3+V4). Banner B7 + tabla readonly + JSON fallback + try/except defensivo.

**Decisión arquitectónica:** refactor genérico de helpers V*-específicos
postponed hasta 3 referencias reales Class A (hoy solo V1+V2).
