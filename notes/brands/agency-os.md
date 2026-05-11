---
tipo: brand-history
brand: Capybaras Agency OS
actualizado: 2026-05-11
---

# Capybaras Agency OS — Brand History

Historial de evolución del Agency OS — el sistema operativo propio de Capybaras Agency. Esta nota acumula los hitos arquitectónicos, módulos lanzados y decisiones estratégicas que diferencian al Agency OS de cualquier stack genérico de agencia.

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
