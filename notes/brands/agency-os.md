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
