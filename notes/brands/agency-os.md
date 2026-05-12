---
tipo: brand-history
brand: Capybaras Agency OS
actualizado: 2026-05-12
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
