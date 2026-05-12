---
tipo: state
actualizado: 2026-05-09
---

# STATE Agencia — Capybaras

Snapshot operativo de la agencia. Agregador por diseño (no nota atómica).

---

## Ultima sesion — 2026-05-09

**Resumen**: Validacion E2E de M28 SKU Progress Report con CSV real de Dermaglos US (B0CYLMJJJC, W19). 5/5 features funcionales pasaron smoke test inicial. 4 bugs cerrados en el dia: 1 fixeado en sesion (commit 841b230) + 3 detectados por audit del code-reviewer Opus 4.7 (commit 0c7dbf4). Primera invocacion operacional real del code-reviewer = PASS, encontro bug C2 (envenenamiento ASIN vacio) no detectado por flujo humano. M28 queda production-ready local con triple validacion.

**Commits** (3):
- 841b230 fix(M28): matching CSV usa s["asin"] como clave del dict
- 0c7dbf4 fix(M28): cierra 3 bugs detectados por code-reviewer audit (C1+C2+I1)
- b4d84e9 docs(vault): daily 2026-05-09 + cierre validacion M28

**Estado M28**: production-ready local. Bloqueado para uso compartido con equipo por filesystem efimero de Streamlit Community Cloud (decision de arquitectura persistencia pendiente, esperando respuesta de Freddy).

Detalle completo en `notes/daily/2026-05-09.md` (173 lineas).

---

## Última sesión — 2026-05-08 (Dermaglos PPC)

**Foco**: Deep optimization Dermaglos US — análisis triple (STR + SQP + Campañas) + auditoría cross-negation + ejecución de 6 bulks Amazon SP en Bulk Operations.

**Output operativo**:
- 374 cambios aplicados en Amazon (333 negativos + 18 brand defense + 4 SQP adds + 8 bid adjusts + 8 pausas + 3 spanish ES) — 6/6 bulks SUCCESS, 0 errores
- 7 campañas pausadas (6 OOS B0F6VZMF2V + 1 AUTO B0F548KTXD sangrante)
- Cross-negation pattern auditado y confirmado PRO (5 KWs críticas, 0 errores) — sistema histórico manual de calidad, NO TOCAR
- Catálogo ASIN expandido a 10 productos (Micellar Water B0CY2XC91Z descubierto, diferido por cliente)

**Decisiones cerradas**:
- `vitamin e cream` y `allantoin` NO se negativizan global (industry standards 2026 + ROAS 49x en B0CYLM4L23)
- Threshold negativos Capybaras: $25-35 spend / 0 sales (calibrado vs 15-20 clicks industria)
- Self-canibalización ACoS 15.3% es brand defense cross-sell — mantener, no negativizar
- Listing fix B0CYLMJJJC asumido 30+ días, mitigation con bid down ya implementado

**Pendientes manuales nuevos (E bucket)**:
1. E.1 Listing fix B0CYLMJJJC Cream (URGENTE, 6 evidencias) — Cliente/Adam
2. E.2 Restock B0F6VZMF2V Skincare Set (URGENTE) — Cliente
3. E.3 Validación tattoo/scar/wrinkle target (30d) — Cliente/Agustín
4. E.4 Listings ES disponibilidad (14d) — Cliente/Agustín
5. E.5 Listing-copying audit search terms (14d) — Aaron/Adam
6. E.6 Micellar B0CY2XC91Z decisión (60d, diferido) — Cliente
7. E.7 Atom11 v2026.3 ETA (7d) — Lenin/Neha
8. E.8 Atomización B0CYL1RLNQ Night Cream Spanish Core (30d) — Lenin

**Métricas proyectadas**: ahorro neto ~$140/mes + sales lift potencial ~$180/mes, riesgo $0.

**Próxima evaluación Dermaglos**: 2026-05-22 (14d post-bulks).

**Aprendizajes para vault**:
- Validación Bulk Operations export antes de plan reduce 50% del trabajo planificado (detectó 50% duplicados en plan original Lenin)
- Auditoría cross-negation por KW crítica evita pisar ventas (caso `vitamin e cream`)
- Hojas auxiliares en bulks Amazon rompen validación — solo `Sponsored Products Campaigns`
- Script `STR_analizado` filtra Auto/PT (62% del business) — patch documentado, deferido

Detalle completo en `notes/daily/2026-05-08.md` (sección "Sesión 2026-05-08 (Dermaglos PPC)") y en `notes/brands/dermaglos/DERMAGLOS.md` (sección "Sesión 2026-05-08 — Deep Optimization + Bulk Execution").

---

## Última sesión — 2026-05-12

**Foco**: M29 Proposal Studio Sesión 2/6 — UI completa funcional E2E. Construcción incremental en 7 sub-bloques validados visualmente paso a paso.

**Output principal**:
- `modules/pages/proposal_studio.py` (módulo nuevo, ~900 LOC, 25 funciones)
- 3 edits quirúrgicos en `app.py` (import + sidebar SALES DIRECTOR + router branch)
- 1 edit en `core/constants.py` (entry `📋 Proposal Studio` en `_PAGES`)

**Commit**: `aa2d873` en `main` (3 files changed, 1075 insertions).

**Validación E2E completa**:
- Wizard 3 pasos navega correctamente (Anterior / Cancelar / Siguiente con validación por paso)
- Paso 1 form con auto-save + warning rojo cuando faltan campos obligatorios
- Paso 2 preview readonly con KPI bar + agrupación por tier + cache por signature de inputs
- Paso 3 review + save persistente vía `pp.save_proposal()` con auto-versionado
- Smoke test propuesta "Gamboa" launch/es → 18 blocks instanciados, UUID generado, aparece en Listado con todos los metadatos

**Decisiones clave**:
- Workflow main-only confirmado (no más branches feature/* para M29). Reduce overhead de merge.
- Cliente del wizard es `text_input` libre (no `selectbox` con clientes existentes) — M29 es para leads/prospects nuevos.
- Cards visuales en el Listado en lugar de `st.dataframe` para incluir botones de acción por fila.
- Confirmación 2-clicks para Archivar.

**Deudas detectadas (no bloqueantes)**:
- Autocomplete del browser sugiere valores históricos en los `text_input` del paso 1 → evaluar `autocomplete="off"` en S3
- Vista detalle de propuesta (botón "Abrir") es placeholder hasta S3
- Edición de blocks individuales pendiente S3 (V1-V6) y S4 (placeholders V23-V29)
- Tests E2E automatizados: hoy validado solo manualmente

**Próximas evaluaciones programadas**: ninguna específica. Próxima sesión abierta a Sesión 3 de M29 cuando Lenin agende.

Detalle completo en `notes/daily/2026-05-12.md` y `notes/brands/agency-os.md` (sección 2026-05-12).

---

## Última sesión — 2026-05-08 (continuación, vespertina)

**Foco**: Pitch deck M29 Proposal Studio — pivot estratégico de "construir módulo Streamlit" a "construir pitch HTML que presenta el módulo" para validar concepto con Sales Directors antes de invertir en Streamlit.

**Output principal**:
- ``presentations/m29-proposal-studio-pitch/index.html`` (~75 KB, 2628 líneas, 9 slides standalone con Chart.js + Google Fonts CDN)
- ``presentations/m29-proposal-studio-pitch/README.md`` (contexto, decisiones de diseño, próximos pasos)
- Append a ``notes/daily/2026-05-08.md`` con sección "(continuación)"

**Decisiones cerradas**:
- v1 output = HTML standalone (principal) + PDF via Playwright (futuro). Sin link hosteado en v1.
- Paleta + tipografía: dark + naranja Capybaras + Bricolage Grotesque/Geist/JetBrains Mono
- Stack render del módulo M29 a futuro: HTML modular en ``templates/proposal_modules/`` + JSON schema en ``data/_schemas/proposal-v1.json`` + Playwright para PDF
- 27 módulos confirmados (7 FIXED + 20 VARIABLE) basados en Excel ``Capybaras_Proposal_Module_Template.xlsx``

**Pendientes propuesta de M29 Proposal Studio**:
1. Lenin presenta pitch a Sales Directors semana 12-16 mayo
2. Feedback define cuál VARIABLE arranca el MVP (candidatos: Listing Audit Main Image, Pricing/Scope, o Brand Overview)
3. Confirmar 3 propuestas próximas que van a usar M29 como validación real
4. Generar PDF del pitch con Playwright (sesión separada, instalar Chromium ~150 MB)
5. Post-feedback: mover ``index.html`` a ``.claude/porting-sources/m29-pitch.html`` → arrancar Fase 1 del módulo Streamlit con ``html-to-streamlit-porter`` Caso 2 + ``data-persistence-specialist`` Caso 2

**Sin push todavía**: commit local pendiente de push por Lenin al cierre.

---

## Última sesión — 2026-05-08

**Foco**: M28 SKU Progress Report — primer porting Caso 2 (HTML con persistencia simple) del Agency OS.

**Output principal**:
- `data/_schemas/sku-progress-v1.json` (205 lineas, schema con 3 entidades)
- `modules/pages/sku_progress_report.py` (1549 lineas, 36+ funciones)
- 3 edits router (app.py + core/constants.py + modules/pages/CLAUDE.md +119 lineas)

**Commits**: d9fd787 (schema), 5318b12 (modulo).

**Agentes validados**:
- `data-persistence-specialist` Caso 2 — primera invocacion real, 6/6 al primer intento
- `html-to-streamlit-porter` Caso 2 — primera invocacion con Fase 3 ACTIVA, 3 desviaciones senior aplicadas correctamente

**Smoke test**: PASS con SKU real Dermaglos PVENUS0782 incluyendo flujo "Borrar cliente entero" agregado intra-sesion. Funcionalidades no probadas (importar CSV, tab Admin, Excel, registrar optimizacion) flageadas como pendientes de validacion con uso real, no bloquean v1.

**Estado del Agency OS al cierre**:
- 27 modulos activos en 6 secciones (Account Health ahora con 2 modulos: M27 + M28)
- Branch feat/agency-os-rebrand merged-not-deleted (24h post-merge sin issues, pendiente purga)
- 2 commits en main por encima de origin/main, listos para push

Detalle completo en `daily/2026-05-08.md`.

---

## Última sesión — 2026-05-07

**Cliente tocado**: ninguno. Sesión de tooling/desarrollo sobre infraestructura del repo.

**Foco**: ejecución del plan de 3 bloques bloqueado en sesión anterior — rebrand visual del repo a Agency OS + bootstrap real de `core/persistence.py` + porting del primer HTML del compañero Marcos (Flat File Migrator → M27 sección Account Health). Validación en operación real de los 2 agentes Opus 4.7 nuevos (`data-persistence-specialist` y `html-to-streamlit-porter`) creados en la sesión anterior.

**Acciones ejecutadas** (7 commits pusheados a main, merge commit `e49dc52`):
- `e93121f` rebrand UI: page_title + header sidebar + expander Account Health activado
- `f00de3c` bootstrap `core/persistence.py` con 10 helpers + schemas + roundtrip test (415 líneas)
- `64279c3` setup `.claude/porting-sources/` con README versionado e ignorado de `*.html` fuente
- `fd192c8` portar Flat File Migrator → M27 (1075 líneas, 21 funciones, 5 marketplaces US/DE/IT/FR/ES, 5 tabs)
- `acdffae` registrar commit hash de M27 en inventario `porting-sources/_README.md`
- `9d9ef17` cleanup strings Capybaras/PPC Manager residuales (login form + card PPC; footers con Lenin se respetaron)
- `e49dc52` merge `feat/agency-os-rebrand` → main `--no-ff` (10 archivos, 1775 insertions, 8 deletions)

**Validaciones de agentes en operación real** (primera vez):
- `data-persistence-specialist` Caso 1: 6/6 verdes (roundtrip, schema check, cache invalidation, path coherence, gitignore, module import). Output estructurado al primer intento.
- `html-to-streamlit-porter` Caso 1 (HTML stateless): 6 fases ejecutadas, Fase 3 skipped por stateless confirmado en Fase 1. Output estructurado al primer intento. Deuda técnica heredada del HTML (5 ítems) documentada en CLAUDE.md de M27 sin arreglar.

**Decisiones tardías post-merge** (sin ejecutar, deuda menor):
- Footers con "Capybaras Agency" en autoría de Lenin Acosta se respetan en cleanup. Si en futuro se busca 0 menciones de Capybaras en UI, son 2 edits triviales en `app.py L262-264` y `inicio.py L311-313`.
- Branch `feat/agency-os-rebrand` merged-not-deleted como red de seguridad. Lenin decide cuándo purgarla.

**Próximas evaluaciones programadas**: ninguna específica. Próxima sesión abierta a (a) validar otros agentes con model fix, (b) avanzar M28 SKU Progress Report con persistence-specialist Caso 2, (c) tareas de cliente pendientes (Dermaglos, Variation Builder M26, Setex).

---

## Última sesión — 2026-05-06

**Cliente tocado**: ninguno. Sesión de tooling/meta-trabajo sobre infraestructura del repo.

**Foco**: setup completo de Account Health tooling + persistence layer. Compañero de la agencia (Marcos) compartió 11 archivos .md de su proyecto Catalog + 3 HTMLs operativos (Pricing Dashboard v3, SKU Progress Report v4, Flat File Migrator) — candidatos a integrar como módulos M27/M28/M29 en sección Account Health del Agency OS.

**Acciones ejecutadas** (commit f386bfe pusheado a main):
- 2 skills nuevos: data-persistence-standard, account-health-standard
- 2 agentes nuevos Opus 4.7: data-persistence-specialist (color violet), html-to-streamlit-porter (color cyan)
- 7 model fixes en agentes existentes — issue AGENT-001 cerrado tras semanas con string deprecated:
  * Promociones a Opus 4.7 (lógica pura): ppc-module-builder, code-reviewer, atom11-specialist
  * Snapshot fix Sonnet 4.5 estable: excel-export-builder, ui-designer, testing-agent, client-onboarding
- Convención de modelos formalizada: Opus alias estable para lógica pura (5), Sonnet snapshot fijo para implementación (4), Haiku snapshot fijo para markdown (2)
- CLAUDE.md raíz con snapshot tooling 2026-05-06 (tablas consolidadas)
- CHANGELOG.md entry en [Unreleased]
- daily 2026-05-06 con todo el razonamiento

**Decisiones tardías post-commit** (no ejecutadas, próxima sesión):
- Rebrand visual: "PPC Manager" → "Agency OS", quitar "Capybaras" de UI
- Sección Account Health pasa de "Próximamente" a activa, owner Marcos
- Persistencia automática como justificación del porting (data en disco vs HTML embedded export)

**Próximas evaluaciones programadas**: ninguna específica. Próxima sesión va a ejecutar 3 bloques: rebrand visual + bootstrap core/persistence.py + portar Flat File Migrator como M27.

---

## Última sesión — 2026-04-27

**Cliente tocado**: M&B (Mott & Bow USA). Sesión sin cambios en repo Streamlit — todo análisis + ejecución en Amazon Ads Console.

**Hallazgo crítico**: Las 9 campañas non-branded del 07/04 (Marcy) + 13/04 (Elizabeth Greene) nunca arrancaron — bid $0.02 + ToS +900% no superó bid floor de Amazon. Pivot ejecutivo a arquitectura clásica EXACT con multi-child.

**Acciones ejecutadas**:
- Cleanup quirúrgico: 8 campañas pausadas, 2 bid -50%, 4 acciones internas en ad groups SD/SBV (descubrimiento Purchases:90 con 80% CVR, KW "women t shirt" singular winner aislado).
- 3 EXACT non-branded HW lanzadas (Batch UUID `b09c8dd1-00c5-4b2c-a86b-af169ac7ac49`): NB CR HW A ($15/d, 5 KWs validadas, M+L+S White), NB VN HW A ($8/d, 1 KW HOT, M+L+XL Crimson), NB VN HW B ($7/d, 3 KWs expansión, M+L+XL Crimson). Total $30/d, eval 11/05.
- Bid up PAT Premium 21/04: 24 targets de $0.60 → $1.10 (bulk action).
- Verificado vs Campaign_Apr_27_2026__3_.csv: cleanup ejecutado al 100%.

**Saga bulk**: 4 intentos hasta success. v2 falló por `%` en KW pero CREÓ campañas parcialmente (UI engañosa). v3 falló "already exists". v4 con naming HV→HW + fecha 27 = success.

**Pendiente bloqueante**: mensaje gate AM Fase 2 (Brand Store Women + video SBV) NO se redactó hoy. Ventana original 26-30 abril ya pasó.

**Próximas evaluaciones M&B**: 05/05 PAT Premium día 14 (con bid up $1.10) · 11/05 NB HW día 14.

---

## Clientes activos

| Cliente | Mercado | ACoS cuenta | Focus Q2 | Bloqueo principal | Brand note |
|---|---|---|---|---|---|
| Dermaglos | Amazon USA 🇺🇸 | 58.0% (↓ de 76.1%) | Meta ≤55%, escalar vitamin A + allantoin + tattoo ES | Rufus analysis 4 heroes + confirmación equipo Atom11 ejecutó entregable | [[DERMAGLOS]] · [[DERMAGLOS_DATA]] · [[atom11-rules]] |
| Mott & Bow | Amazon US 🇺🇸 | 11.7% (sano) | Full-Funnel Women — Fase 2 (SBV White Tee + SP Exact Premium Cotton) | Video creativo + Brand Store Women actualizado para lanzar Fase 2 26-30 abril | [[MB (2)]] |
| Love To Dream | Amazon MX 🇲🇽 | 16.1% | Plan 6 Fases ejecutado (5 de 6) — Fase 6 pendiente esta semana (Adam→Aaron, Agustín→cliente) | Mismatch producto/KW sistémico — auditoría dedicada esta semana · B09MG1J3LC sigue OOS · 5 EXACT heroes Delivering desde hoy | [[LTD]] |
| Setex Technologies | Amazon MX 🇲🇽 | 20.9% (↓ de 25.5%) | 🏆 Best Seller badge en B081GB8F89 — lock-in del badge + protección B086H3TZ6B (1u stock, child) + reactivación post-restock Temple/Ear Hook | ETA reposición FBA Temple Tips + Ear Hooks · B086H3TZ6B URGENTE 1u · portfolios manuales 9 nuevas | [[setex]] · [[PENDIENTES_RESTOCK]] |
| 360 Essentials | Amazon USA 🇺🇸 | 23.0% (✅ target 35%) | SBV FreedomPlus branded + test incrementalidad + relanzar SD bid $1 | Video creativo FreedomPlus para SBV (3 camps) | [[360ESSENTIALS]] |
| Pura Vida Moringa | Amazon MX 🇲🇽 | 45.5% marzo (proyectado 48-52% post-opt) | Bajar ACoS a 40-45% · consolidar rank orgánico top 2-5 | Sin crédito Atom11 — optimización manual | [[Puravidamoringa]] |

**Patrón cross-client**: todos los USA con cuenta madura (Dermaglos, M&B, 360 Essentials) corrieron Atom11 v2026.2 en marzo. Los MX (LTD, Setex, PVM) manuales — LTD con 38 rules vía Cowork, Setex sin Atom11, PVM sin crédito.

---

## Estado Atom11 por cliente

| Cliente | Rules activas | Versión | Coverage campañas | Próxima evaluación |
|---|---|---|---|---|
| Dermaglos | 83 | v2026.2 AGRESIVO | 117/123 (95%) | 11/04 realizada, 14 días desde confirmación equipo |
| 360 Essentials | 49 | v2026.2 | 110/131 + 23★ pendientes | 16/04 (primera evaluación) |
| LTD | 38 | custom (via Cowork) | 99 camps en 6 grupos | pendiente schedule oficial |
| M&B | TBD | activa (siempre tuvo) | TBD | TBD próxima sesión M&B |
| Setex | — | sin Atom11 | 92 camps ENABLED | pendiente gestión con Guille |
| Pura Vida Moringa | — | sin Atom11 (sin crédito) | 14 camps manual | 16/04 evaluación manual |

**Corrección 2026-05-04:** M&B figuraba históricamente como "sin Atom11 — optimización manual" pero los exports analizados en sesión 2026-05-04 prueban que sí tiene reporting Atom11. Coverage agencia ahora: **5/6 clientes con Atom11** (faltan Setex y PVM). Coverage exacto, rules activas y versión bajo Atom11 — TBD próxima sesión M&B con datos del cliente.

---

## Proyectos en curso — Agency OS (PPC Manager)

Todos commiteados a `main`, pendientes de push.

- **M29 Proposal Studio (Sales Director module)** — Sesión 2/6 completada (UI completa: Listado + Wizard 3 pasos + Save persistente). Branch `main` (workflow main-only post-merge S1), último commit `aa2d873`. 37 módulos en catálogo (8 FIXED + 29 VARIABLE), 4 arquetipos (launch / scale_seo / defense / cvr). Capa de persistencia abstracta (`ProposalStorage` + `LocalJsonStorage`) preparada para swap a Supabase post-decisión Freddy. Smoke test E2E validado (propuesta Gamboa launch/es, 18 blocks, UUID generado, persistida). Nueva sección sidebar `📋 SALES DIRECTOR` (28 módulos activos en Agency OS ahora). Próximo: Sesión 3 — Vista detalle de propuesta (botón Abrir) + 6 CORE Variables funcionales (V1 Brand Overview, V2 Category, V3 SEO, V4 Listing Current State, V5 Listing Comparison, V6 Growth Plan). Owner: Lenin (dev) + Sales Directors (validación). Ver [[brands/agency-os]] y [[daily/2026-05-12]].
- **Variation Builder M26 (2026-04-26 en curso)**. Módulo nuevo Account Manager para generar flat files Amazon (1 parent + N children). `modules/pages/variation_builder.py` (929L). 4 tabs: Parent / Children+Theme / Preview / Descargar. Tema Variation (Sabor, Tamano, Scent, etc). Bug abierto: `data_editor` requiere doble entrada para persistir — fix diseñado (3 keys pattern) pendiente de aplicar. End-to-end validado con template cliente `PET_FOOD__1_.xlsm`. **Casos de éxito acumulados (3)**: VITALPET 27/04 (4/4), OPTIPET_ADULT 08/05 (4/4), OPTIPET_FLAVORBOOST 09/05 PARCIAL (2/4 — primer caso "listing rico desde cero", 7 hallazgos técnicos nuevos VB-004 a VB-011). Knowledge: `notes/knowledge/2026-05-08-variation-builder-flat-file-format.md`.
- **Sprint 1 Campaign Builder v2.0 — SB rewrite (cerrado 2026-04-23)**. `_render_sb()` reescrito 864→1121 líneas en `modules/pages/campaign_builder.py`. Selector SBV/SBH. Brand Entity ID obligatorio. 29 columnas bulk SB 2026. Validaciones estrictas. Naming Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder).
- **Gamboa Generator M25 (integrado 2026-04-22)**. Módulo Account para reportes HTML integrales (SQP mensual + BR semanal). 5 archivos en `modules/gamboa/` + `modules/pages/gamboa_generator.py` (383L). Live en producción.
- **Bulk Amazon 2026 compliance (2026-04-21)**. 30→31 columnas, helper `_fila_vacia_bulk()`. Validado con Batch ID UUID. Ver [[PPC-SOP-Manager]] sección Campaign Builder + [[amazon-bulk-upload-guide]].
  - 2026-04-28: 8 learnings nuevos sumados (Negative vs Campaign Negative Keyword, Campaign IDs numéricos para campañas existentes, Start Date como texto, Google Sheets corrompe IDs, caracteres especiales rechazados, campaign analyzer puede mostrar zombies, SD schema 47 cols vs SP 31 cols, hoja única obligatoria). Ver sección "Learnings 2026-04-28" en [[amazon-bulk-upload-guide]].
- **Vault Obsidian versionado (hoy 2026-04-24)**. `.gitignore` fix `notes/` → `notes/*` + excepciones por carpeta. Estructura 8 directorios (`brands/`, `daily/`, `knowledge/`, `personal/`, `prompts/`, `sops/`, `state/`, `.obsidian/`). 6 brand notes + 9 archivos sueltos reorganizados con `git mv`.
- **Sprint 2 Campaign Builder Modo B (TBD ~4-5h)**. XLSX custom + `st.data_editor` para flujo rápido power-user.
- **Sprint 3 DaypartingApp (TBD ~2h)**. Módulo nuevo Account Manager — automatización bids por día/hora.
- **M28 SKU Progress Report (Account Health)** — production-ready local con 4 bugs cerrados (commits 841b230 + 0c7dbf4 + b4d84e9). Triple validacion: audit code-reviewer + diff visual + smoke E2E con Dermaglos. Bloqueado para uso compartido por filesystem efimero de Streamlit Cloud.

---

## Iniciativas cliente en curso

- **Dermaglos plan ejecución 28/04** — propagación 30 días. 7 campañas live desde 28/04 ($200/d budget). 46 negativos aplicados. 10 P0 pausadas ($3,960/mes recuperable). Targets: ACoS 56.3%→42-45% / Sales/d $76→$110-130 / Brand IS 0%→60-80%. Re-correr STR 15/05 para medir delta. Re-evaluar B0F548KTXD post-30 días con bids ajustados.
- **Setex cierre completo 29/04** — sesión de mayor impacto histórica de la cuenta. 5 bulks ejecutados (141 movimientos exitosos): #1 Defensivo (39 filas, UUID `7096ec9c-9528-4c22-a18f-328d56cb2a29`) · #2 Ofensivo (12 filas, UUID `5944afce-052e-4c7c-9084-545195cd8929`) · #5 Negativos quirúrgicos (9 filas, UUID `23877dc3-80de-489a-bbb1-12d35ff16385`) · #4 Campañas Nuevas (75 filas, UUID `ad5d988d-a835-43a1-912e-0bdb79991a2a`) · #3 Reducir (6 filas, UUID `426473c9-8e81-4b57-92c6-8817be3012fa`). Net cuenta: ~MX$23k/mes redirigidos. **Best Seller badge confirmado** post-sesión en B081GB8F89 (categoría "Kits de Reparación para Lentes y Anteojos") — validó retroactivamente toda la estrategia. **Framework "Decomposición orgánico vs paid"** descubierto y aplicado: caída -14% WoW era 68% orgánica (OOS Temple+Ear), no PPC. 9 campañas nuevas con naming Capybaras/Atom11-friendly creadas (8 hero=B081GB8F89 + 1 multi-target Brand Hub). Pendiente urgente: reposición FBA Temple Tips + Ear Hooks + B086H3TZ6B (1u, child del badge). Próximas evals: 06/05 (4d), 09/05 (1sem), 13/05 (10d), 20/05 (3sem). Ver [[setex]] y [[2026-04-29-WoW-organic-vs-paid-decomp]].

---

## Bloqueos y pendientes críticos

- **Variation Builder M26**: `data_editor` bug abierto — fix necesario antes de release. Seguimiento en [[daily/2026-04-26]].
- **OPTIPET FlavorBoost** (cliente personal Lenin, NO Capybaras): respuesta cliente sobre eliminación Cat Treats Inactive (libera UPCs Pulmón/Pollo). Sin esto no se completa Variation Family #2. Seguimiento en [[daily/2026-05-09]] · [[optipet]].
- 🔴 **Decision arquitectura persistencia compartida** (Supabase / R2 / Railway / Neon): bloqueante para uso real con equipo + porting M29 Pricing Dashboard. Esperando respuesta de Freddy sobre aprobacion $25/mes Supabase Pro (mensaje enviado 2026-05-09 con desglose costos). Streamlit Community Cloud filesystem efimero NO sobrevive redeploys.
- **Dermaglos**: ✅ Sesión 28/04 cierre completo — análisis cruzado + plan maestro + 3 bulks ejecutados (93/94 + 46/46 + 7/10 success) + 10 campañas P0 pausadas ($932 net waste detenido / $132/d budget liberado). 7 campañas nuevas live ($200/d budget). ⏳ Pendientes manuales próxima sesión (ver [[2026-04-28]]): Portfolio ID assignment a las 7 nuevas, allantoin 0.5% cream resolver, bid SD Views Retargeting 30D ($1→$0.50), budget B0CYLDSQ5L SP ASIN Related ($5→$15), mensaje corregido a Neha, listing opt Tattoo + Cleanser + Body Cream, restock B0F6V para activar push diferido. Atom11 v2026.2 EN REVISIÓN — Neha trabajando en v2026.3 con 4 fixes (1 corregido en diagnóstico hoy: bug del comma era falso positivo, problema real es rule HARD-STOP que no dispara). Cambio de status: B0F548KTXD sale de heroes (ROAS 0.61×). Estrella oculta identificada: B0F6VZMF2V (ROAS 6.20× OOS desde 09/04).
- **LTD progreso 25/04 cierre completo**: ✅ Fases 1+3+4+5 ejecutadas (sesiones 1+2 mismo día) · ⏳ Fase 6 pendiente esta semana — delegada a equipo (Adam con Aaron compliance B005ULUZIQ, Agustín con cliente ETA restock B09MG1J3LC + summary + lista heroes 3ra solicitud). Push Heroes Fase 4: 5 EXACT Delivering desde hoy +$200/d. Brand Defense expandido a 5 ad groups. Auditoría sistémica match producto/KW pendiente esta semana sin owner asignado. Outputs: bulk xlsx + HTML internal brief para Adam y Agustín.
- **M&B Fase 2 bloqueada (escalada pendiente)**: ventana original 26-30 abril vencida. Mensaje gate AM con pregunta cerrada (Brand Store Women + video SBV listos sí/no) NO se hizo hoy — primera tarea próxima sesión. Mientras: las 3 EXACT HW non-branded ($30/d) cubren funnel mid sin esperar al cliente. Eval 11/05.
- **Setex pendientes post-29/04**: ✅ Sesión 29/04 cierre completo — 141 movimientos en 5 bulks (todos UUIDs registrados) · Best Seller badge confirmado en B081GB8F89 · framework Decomposición orgánico vs paid descubierto. ⏳ Pendientes: (1) **B086H3TZ6B URGENTE — 1u stock, child del Best Seller, riesgo perder badge** · (2) ETA reposición FBA Temple Tips (B0C7WPFVGV + B0B94KBY8H, OOS desde 18-23/04) · (3) ETA reposición Ear Hooks B0F63LTD92 (4u runway 3-4d) · (4) Asignación manual portfolios RANKING/CONQUEST/DEFENSIVE a las 9 campañas nuevas · (5) Subir bid Brand Hub Heroes $3→$5 post-badge · (6) Crear KWs "best nose pads", "amazon choice nose pads" · (7) Listing optimization B081GB8F89 lock-in del badge · (8) Coordinar con Nicki: 5 SKUs duplicados Closed · (9) SBV B08PZF22R1 sin owner (heredado 15/04). Diferidos hasta restock: 5 campañas nuevas Temple/Ear Hook + 12 KWs harvest documentados en [[PENDIENTES_RESTOCK]]. Ver detalle completo en [[2026-04-29]] y [[setex]].
- **360 Essentials SBV**: espera video creativo FreedomPlus para lanzar 3 campañas SBV ($45/d).
- **Git**: 2 commits locales sin push (`fbae212`, `3f04fb1`) + los que se agreguen hoy. Push manual al cerrar sesión.
- **Repo deuda técnica**: `INTELLIGENCE-INDEX.md` stale (dice 1 nota, M&B listado como MX en vez de US, sin 360 Essentials ni PVM).
- **AmazonBulkUploadGuide.md stale (4 puntos críticos descubiertos 27/04)**: (1) caracteres prohibidos en Keyword Text no documentados (`%`, `$`, `#`, `@`, `*`, etc.) — el `&` SÍ se permite en negativeExact, (2) comportamiento secuencial stop-on-error 2026 no documentado — UI muestra Failed pero filas anteriores ya creadas (verificación visual obligatoria), (3) estrategia re-subida con cambio de 1 letra del naming, (4) Regla #2 lista 30 cols pero el código en producción usa 31 (Sites). Próxima sesión: actualizar guía. Riesgo si no se hace: bulks futuros van a fallar igual y el equipo va a perder horas.
- **Patrón Streamlit a documentar (29/04)**: `st.expander` no se puede anidar dentro de otro `st.expander` (`_check_nested_element_violation`). Bug intermitente — solo crashea cuando se ejecuta el branch que crea el expander interno, por eso pasa code review básico. Reemplazo standard: `st.popover` (Streamlit ≥1.28). Documentar en `notes/sops/` o `module-architecture-standard.md`.
- **Listing Monitor fix aplicado 29/04 + 2 sospechosos pendientes**: `modules/pages/listing_monitor.py` L563 — `st.expander("Ver bullets actuales")` anidado dentro de expander padre L508 → fix aplicado con `st.popover` (1 línea). Live en producción, validado con ASIN B01M6DFC5W (Medix 5.5, marketplace MX). Diagnóstico via agente `code-reviewer` reveló 2 sospechosos del mismo bug que NO se atacaron (scope): `modules/pages/gamboa_generator.py` L322+L370 y `modules/pages/atom11.py` L261+L303. Verificar indentación próxima sesión y aplicar mismo fix preventivo si confirma.
- **Reviews Intelligence (esperando decisión CEO)** — feedback del CEO pendiente sobre cancelar tarjeta Apify o dejarla. Caminos posibles: (a) export manual Seller Central + automatizar procesamiento, (b) probar Bright Data ($15-30/mes), (c) pausar el módulo. Mensaje al CEO ya enviado el 2026-05-05.

---

## Aprendizajes técnicos

- **2026-05-05** — Amazon bloqueó globalmente el scraping de text reviews (USA y MX confirmados, alineado con [[knowledge/2026-03-21-amazon-agent-policy-bsa-march-2026|Agent Policy del 4-mar-2026]]). Implicación: módulo de Reviews Intelligence en [[ppc-manager]] requiere replanteo completo. Setup de Apify queda configurado por si se usa para otro caso no-Amazon. Detalle: [[daily/2026-05-05]].
- **2026-05-11** — PowerShell no expande wildcards de paths. El comando `pytest tests/test_X_*.py` falla con "no tests ran" cuando se corre desde PowerShell (Windows), porque el shell no resuelve el `*` y pytest recibe el string literal. Usar `pytest tests/ -k "X"` (filtro por keyword sobre nombres) en Windows. Bash sí expande wildcards, PowerShell no. Regla general: cualquier comando que use `*` o `?` en path desde PowerShell — reescribir con flags equivalentes o usar `Get-ChildItem | ForEach-Object`. Detectado al correr los tests M29 Sesión 1. Detalle: [[daily/2026-05-11]].

---

## Deuda técnica

### 1. Dashes unicode pendientes en M17 / M18 / M19 / M20 (prioridad MEDIA)

**Hallazgo (2026-05-04):** El fix de tolerancia a variantes Amazon (dashes unicode `–` en-dash, `—` em-dash, doble espacio, falta de guión, splits Mobile/Browser sin Total) se aplicó solo a M14 Weekly Client Report — los parsers BR de los siguientes módulos siguen con el mismo bug latente:

- **M17 Account Pulse** (`modules/pages/account_pulse.py`) — parsea BR diario + BR by Child
- **M18 PPC Insights** (`modules/pages/ppc_insights.py`) — BR by ASIN opcional
- **M19 PPC Forecast** (`modules/pages/ppc_forecast.py`) — BR diario para tendencia
- **M20 PPC Audit Pro** (`modules/pages/ppc_audit.py`) — BR opcional para TACoS

**Síntoma**: si Amazon devuelve cualquier variante rara de separador (dash unicode o split Mobile+Browser sin Total), el match flexible por substring falla y los parsers retornan métricas en 0 silencioso. El AM no se entera hasta ver el output con datos faltantes.

**Plan sugerido**:
1. Extraer `_normalizar_col_br`, `_detectar_columnas_br` y `_validar_cols_core_br` desde `modules/pages/weekly_client_report.py` a un módulo común `core/br_parser.py` (o `core/business_report.py` extendido).
2. Reemplazar los matchers ad-hoc (`_n(col)` o helpers internos similares) en M17/M18/M19/M20 por llamadas al detector centralizado.
3. Mantener firmas de retorno actuales para no romper downstream.
4. Agregar `@st.cache_data(show_spinner=False)` a parsers BR si no lo tienen.
5. Tests sintéticos por módulo (5+ casos: completo / mínimo / dash unicode / split / col core ausente).

**Esfuerzo estimado**: ~2h por módulo si se extrae el helper común. Total ~3-4h con tests.

**Trigger para atacarlo**: cuando un cliente reporte el primer caso de output con datos faltantes en alguno de los 4 módulos. Hasta entonces, riesgo aceptable porque hoy los AMs validan visualmente los Excel antes de enviar.

---

### 2. Asimetría CVR sin columnas — by_child vs by_date (prioridad BAJA)

**Hallazgo (2026-05-04):** En el refactor de M14, `_parse_br_wow` (by_child) propaga `None` cuando faltan TANTO `Unit Session Percentage` como `Order Item Session Percentage`. Pero `_parse_br_daily_wow` (by_date) retorna `0` silencioso en el mismo caso (legacy de `_a()` sobre col=None que devuelve 0).

**Hoy no rompe nada** porque el daily se usa solo para display de % en celdas únicas del Excel (formato `0.00`) y la UI/builder ya manejan ambos casos (`if avg_cvr_tw > 0` filtra el 0 sin error).

**Riesgo a futuro**: si se usa `CVR_TW` del daily para alertas automatizadas, scoring o comparaciones (ej: "CVR cayó >X%"), `0` se confunde con CVR realmente cero — falso positivo de "caída total".

**Fix sugerido cuando se ataque**: paridad propagando `None` en daily también, junto con verificación de que `_build_weekly_excel` maneja `CVR_TW=None` correctamente en las celdas L458-460 (`_tot(12, bd["CVR_TW"], '0.00')` puede romper si `bd["CVR_TW"]=None`).

**Trigger**: cuando se construya el primer alert/score basado en CVR del daily.

---

### 3. Bug 30 vs 37 días en Pricing Dashboard heredado (prioridad BAJA, post-port)

**Hallazgo (2026-05-06):** El Pricing Dashboard v3 del compañero Marcos tiene discrepancia entre `runAnalysis` (cubre 37 días) y `computeScore` (cubre 30 días) para `restock_alert` AWD→FBA. La decisión bloqueada del compañero dice 30 días pero el código no es consistente.

**Hoy no rompe nada** — el dashboard se usa estable.

**Plan de fix**: cuando se portee el Pricing Dashboard como M29 (sesión futura después de M27 Flat File y M28 SKU Progress), el agente html-to-streamlit-porter está obligado a NO arreglar bugs durante porting (regla dura). El bug se hereda documentado y se arregla en sesión consciente posterior, con decisión explícita del equipo.

**Trigger**: después del porting de M29.

---

### 4. M26 Refactor post-OPTIPET FlavorBoost (10 bloques) (prioridad MEDIA)

**Hallazgo (2026-05-09):** Sesión OPTIPET FlavorBoost descubrió 7 deudas técnicas nuevas (VB-004 a VB-011) sumadas a las 3 viejas (VB-001 a VB-003). Agrupar refactor M26 después de los 3 casos validados Variation Builder (VITALPET 27/04, OPTIPET_ADULT 08/05, OPTIPET_FLAVORBOOST 09/05 parcial). Estimación: 1.5-2 sesiones de trabajo.

Bloques ordenados por prioridad y riesgo:
- **VB-001** (deuda vieja, 30 min, riesgo bajo): refactor 3 returns en tab_download a helper `_render_download_tab()`
- **VB-002** (15 min, riesgo bajo): cambiar update_delete hardcoded "Actualizar" → "Update" en `_build_parent_row` y "PartialUpdate" en `_build_child_row`
- **VB-003** (30 min, riesgo medio): refactorizar `_build_child_row` a minimal payload (9 cols solo) para casos PartialUpdate
- **VB-004** (15 min, riesgo bajo): validar ningún valor contiene `\n` `\t` `\r` crudos antes de escribir TSV
- **VB-005** (15 min, riesgo bajo): para Pet Food MX, populate automático de `max_order_quantity=999` y `number_of_items=1` si no se especifican
- **VB-006** (30 min, riesgo bajo): validar `external_product_id_type` matchee longitud (UPC=12, EAN=13, ASIN=10 alfanumérico)
- **VB-007** (10 min, riesgo bajo): documentar en UI que "FBM 0" del parent post-feed es transitorio (warning informativo, no error)
- **VB-008** (15 min, riesgo bajo): mejorar mensajes de error 99001 explicando posible falso positivo por feed_product_type
- **VB-009** (45 min, riesgo medio): cargar valores válidos enum desde hoja "Valores válidos" del template y validarlos antes de escribir
- **VB-010** (1h, riesgo medio): pre-flight check de UPC contra catálogo Amazon (requiere SP-API call) para detectar collision antes de subir
- **VB-011** (15 min, riesgo bajo): documentar en UI que listings Inactive NO liberan UPCs (warning visual cuando se escribe un UPC)

Bug `data_editor` 3 keys (pendiente desde 26/04): aplicar fix patrón de 3 keys o fallback `st.form` en tab Children.

**Smoke test**: regenerar `OPTIPET_FlavorBoost` con módulo y comparar contra v4 manual del 09/05 byte por byte.

**Trigger**: alcance final a decidir en próxima sesión cuando estemos con código en frente.

Detalle completo en `notes/daily/2026-05-09.md` (sección "Sesión 2 — OPTIPET FlavorBoost") y `notes/knowledge/2026-05-08-variation-builder-flat-file-format.md` (Caso de éxito #3).

---

### 5. Bug recurrente git renormalize en `notes/daily/2026-04-24.md` (prioridad MEDIA)

**Hallazgo (2026-05-09):** El archivo `notes/daily/2026-04-24.md` aparece como modificado cada vez que git toca el repo (3 veces durante la sesion 2026-05-09: al inicio, durante aplicacion de fixes via super-prompt, y al cierre para escribir el daily). Workaround actual: `git checkout notes/daily/2026-04-24.md`.

**Causa probable**: inconsistencia entre line endings en disco (CRLF) y regla de normalizacion de git (LF segun `core.autocrlf` o `.gitattributes`). El warning `LF will be replaced by CRLF the next time Git touches it` confirma el sintoma.

**Hoy no rompe nada** funcional — solo agrega friccion al guard de repo en cada sesion.

**Fix sugerido**: `git add --renormalize` + commit del archivo, o regla explicita en `.gitattributes` con `*.md text eol=lf`. Sesion separada chica.

**Trigger**: cuando aparezca el sintoma en mas de un archivo o cuando el guard de repo bloquee 2+ veces seguidas en una misma sesion (ya paso el 2026-05-09).

Detalle en `notes/daily/2026-05-09.md` (item 7 de "Deuda tecnica anotada").

### 6. M29 Proposal Studio — deudas Sesión 1 (prioridad BAJA, arreglar en Sesión 6)

Tres deudas detectadas al cerrar Sesión 1 de M29. Ninguna bloqueante, todas se atacan en la Sesión 6 (cierre M29):

- **[M29] `copy_overrides` actual es `dict[str,str]`**; futuro multi-campo (override solo del título sin tocar el body de un bloque) requiere `dict[str,dict[str,str]]`. Anotado para Sesión 4 cuando aparezcan los placeholders con copy editable por subcampo.
- **[M29] `PROPOSALS_DIR` hardcoded en `core/proposal_paths.py`** — sin env var. Migrar a env var post-Supabase (Fase 2/3), cuando los tests CI necesiten redirigir el path sin monkeypatch.
- **[M29] `data/_README.md` sección "API de persistencia" no documenta los 11 helpers nuevos** de `core/proposal_persistence.py` (solo lista los 10 de `core/persistence.py`). Arreglar en Sesión 6 junto con el resto del polish de docs.

Detalle completo en `notes/daily/2026-05-11.md`.

### 7. Fix badge inicio — deudas residuales detectadas 2026-05-11 (prioridad BAJA, sesión separada)

Cuatro deudas detectadas durante el descubrimiento de Fase 1 del fix del badge (commit `74597bc`). El fix atendió el bug principal (badge hardcoded → dinámico) y la deuda crítica (Listing Monitor faltante en `_PAGES`), pero estos 4 hallazgos quedan abiertos por scope:

- **[inicio.py] Counts por sección hardcoded** (líneas 123 / 132 / 142): `count=10` PPC, `count=4` Account Manager, `count=7` Research. El de PPC dice 10 pero la lista visible tiene 9 items. El de Account Manager dice 4 pero ignora Listing Monitor + Listing Compliance + Gamboa Generator + Variation Builder + SKU Progress Report + Flat File Migrator (que están en sección Account/Account Health en el sidebar). Necesita registry por sección para evitar rotar manualmente con cada módulo nuevo. Detectado durante fix del badge 2026-05-11.
- **[constants.py vs app.py] Emoji inconsistencies** entre `_PAGES` y las routes de `app.py` (mismo módulo, distinto emoji, no rompe routing porque `_PAGES` no se usa para match): Account Pulse (📅 vs 📊), PPC Forecast (🔮 vs 📈), PPC Audit (📋 vs 🛡️), DataDive Analyzer (🔬 vs 🧲). Detectado 2026-05-11.
- **[constants.py vs app.py] Naming inconsistency**: `_PAGES` dice `"PPC Insights Engine"` pero la route en `app.py` dice `"PPC Insights"`. Es el mismo módulo (`ppc_insights.py`), dos labels distintos. Detectado 2026-05-11.
- **[arquitectura] `_PAGES` se importa en `app.py` pero NO se usa para routing real**. Las routes son strings hardcoded en `if selected == "..."`. Convertir `_PAGES` en single source of truth (iterar routes desde `_PAGES`) requiere refactor de 1-2h. Vale la pena para evitar inconsistencias futuras como las 3 anteriores. Anotado 2026-05-11 durante fix badge.

Detalle del descubrimiento en [[daily/2026-05-11]] (sección fix badge — Fase 1).

### 8. Deudas de UI/UX detectadas durante M29 Sesión 2 (prioridad BAJA-MEDIA)

Detectadas durante el smoke test visual del 2026-05-12. No bloquean Sesión 3 ni el roadmap de M29, pero deberían atacarse en sesiones separadas chicas:

- **[Inicio Agency OS] Página sobrecargada visualmente** (prioridad MEDIA, sesión con `ui-designer`): el dashboard tiene demasiados elementos compitiendo — Áreas activas con bordes naranjas en todas las cards, Próximamente con 10 cards en 2 filas, Changelog reciente con tipografía monoespaciada densa, Flujo de trabajo guiado con layout distinto al resto. Necesita pasada de jerarquía visual + decisión sobre qué información priorizar arriba del fold. Anotado por Lenin durante S2 cuando vio el Inicio entre tests.

- **[proposal_studio.py paso 1] Autocomplete del browser sugiere histórico cruzado** (prioridad BAJA): los `st.text_input` del paso 1 (cliente, industria, sales director) muestran sugerencias de otros forms del Agency OS (Dermaglos, M&B, Love To Dream). No es bug del módulo — es comportamiento HTML default. Workaround: agregar `autocomplete="off"` vía atributo HTML cuando se refactore visualmente en S3.

- **[Listado proposal_studio.py] Cards no usan `kpi_card()` standard** (prioridad BAJA): el render de filas del Listado usa HTML/CSS custom en lugar de los helpers de `core.helpers`. Funciona pero rompe consistencia visual con otros módulos. Anotado para pasada de `ui-designer` post-Sesión 6 de M29.

Detalle completo en `notes/daily/2026-05-12.md`.

---

## Próximos pasos inmediatos

1. **Validar otros agentes con model fix en operación real**: `ppc-module-builder`, `atom11-specialist`, `excel-export-builder`, `ui-designer`, `testing-agent`, `client-onboarding`. Los 2 agentes Opus 4.7 nuevos (`data-persistence-specialist`, `html-to-streamlit-porter`) ya fueron validados al primer intento (Caso 1 en sesión 2026-05-07, Caso 2 en sesión 2026-05-08). `code-reviewer` validado en sesion 2026-05-09 (detalle en `notes/daily/2026-05-09.md`).

2. **Coordinar con Marcos sobre M27**: mensaje enviado 2026-05-08 con pedido de flat file real de su workflow. Esperando respuesta. Pendientes: validar v1 con datos reales + decidir si MX se agrega como 6to marketplace o queda fuera del scope.

3. **M28 funcionalidades no probadas en smoke test** (importar CSV semanal end-to-end, tab Admin con borrar snapshot Path.unlink, Excel completo del cliente, registrar optimizacion end-to-end). Validar con uso real cuando Marcos arranque, NO bloquean v1.

4. **Pasada UX/UI a M28** con agente `ui-designer`. Incluye: fix mensaje empty state duplicado + boton "🗑️ Borrar cliente" pulido + revisión general del módulo (paleta Account Health, severidades, kpi_cards).

5. **Migración data Gamboa legacy del HTML a Parquet** — script one-shot `scripts/migrate_gamboa_sku_progress.py` (~2-3h). Parsea `weekDates + DATA + skuOrder + events` del HTML legacy y genera 15 snapshots Parquet + N filas optimizations.parquet + tracked-skus.json para cliente "gamboa". Sesión separada.

6. ~~**Badge "módulos activos" del Inicio Agency OS marca 23**~~ ✅ **RESUELTO 2026-05-11** (commit `74597bc` + merge `0c32550`). `_TOTAL_MODULOS` ahora se calcula dinámicamente desde `_PAGES` (single source of truth). Badge muestra 27 (28 entries en `_PAGES` menos Inicio). Listing Monitor agregado a `_PAGES` (deuda 2026-04-22 también cerrada). Tests blindando regresión en `tests/test_inicio_badge.py` (3 verdes). Detalle: [[daily/2026-05-11]]. Deudas residuales detectadas durante el fix → ver "Deuda técnica → 7. Fix badge inicio 2026-05-11".

7. **Variation Builder M26**: fix de 3 keys al `data_editor` de tab Children. Testing end-to-end. Sigue pendiente de sesión anterior.

8. **Dermaglos**: Rufus en 4 heroes (B0CYLMJJJC, B0CYLM4L23, B0F4KXZVNM, B0F548KTXD) + negativizaciones (18 términos) + harvest 7 KWs + escalar `dermaglos facial` / `dermaglos moisturizing cream` (0% brand share). Verificar equipo Atom11 ejecutó entregable `DG_Atom11_v2026_2_ENTREGABLE.xlsx`. Sigue pendiente de sesión anterior.
9. **M&B** — (1) Redactar mensaje gate AM Fase 2 (NO se hizo 27/04) — pregunta cerrada Brand Store Women + video SBV. (2) 05/05 eval día 14 PAT Premium (bid $1.10 desde 27/04) — si no impresiona en 72h escalada $1.50/creative/re-validar ASINs. (3) 11/05 eval día 14 NB HW (3 EXACT $30/d). (4) Investigar catálogo Jeans M&B — fuga branded 60-70% en queries "mott and bow jeans" (~$300+/mes). (5) Research PAT Conquest MTC vs TrueClassic ($69.99/541 purchases mercado/0% share) + Goodfellow + Lacoste + Polo RL — resuelve scope Men pendiente desde 21/04.
10. **LTD** — Fase 6 esta semana (delegada a equipo): Adam con Aaron por flag B005ULUZIQ, Agustín con cliente por ETA restock B09MG1J3LC + summary Fases 1+3+4+5 + lista heroes definitiva (3ra solicitud) + verificar movimiento precio $859→$809 B09MG1PM6L. Lenin pendiente: asignar portfolios manualmente a las 5 EXACT recién creadas (SU-NB / SU-M ×2 / SU-T / SU-S) + programar auditoría sistémica match producto/KW. Evaluaciones día 7 (02/05) y día 14 (09/05) anotadas en [[LTD]].
11. **360 Essentials** — Revisar evaluación Atom11 del 16/04 (pasó) y ejecutar plan PPC 2026: 3 camps SBV FreedomPlus ($45/d), test incrementalidad PHRASE KWS, relanzar SD RET VIEWS bid $1. Gate: video creativo FreedomPlus con cliente.
12. **Setex** — Listing optimization con STR+SQP keywords de mayor conversión para nose pads (B081GB8F89) y temple tips (B0B94KBY8H). Definir dueño del video SBV B08PZF22R1.
13. **Pura Vida Moringa** — 16/04 próxima evaluación: re-evaluar campañas HARVEST sesiones 1-3 (14+ días data). Negativizar b0dqr3ldwn y b08bbdc9c7 nuevos en AUTO DISCOVERY. Bajar bid RANK moringa capsulas.
14. **Repo** — decidir Sprint 2 (Campaign Builder Modo B, ~4-5h) vs Sprint 3 (DaypartingApp, ~2h) según prioridad. Actualizar [[INTELLIGENCE-INDEX]] stale (1 nota reportada, falta incluir 360 Essentials + PVM + corregir MB → US). Push de commits locales + cambios de hoy. Branch `feat/agency-os-rebrand` merged-not-deleted (24h+ post-merge sin issues, pendiente purga cuando Lenin decida).
15. **Outputs LTD sesión 25/04**: Bulk `LTD_Fase4_Bulk_M4_Push_Heroes_25Abr2026.xlsx` subido a Amazon (Batch UUID 10d5a6ef). HTML internal brief `LTD_Sesion_25Abr2026_InternalBrief.html` generado para distribución interna Adam+Agustín. Ambos en /mnt/user-data/outputs (compartidos con Lenin desde Claude chat).
16. **Biblioteca de prompts v5 (2026-04-27)** — refrescar 7 archivos en proyecto Claude vía "Add content from GitHub". Después validar `cierre-meta` en sesión real durante esta misma conversación. Crear archivos de `codigo/` cuando aparezca el primer módulo nuevo. Actualizar [[CLAUDE]] del vault + [[Biblioteca]] con la nueva carpeta.
17. **Setex** — (1) Esperar respuesta Tati con ETA reposición FBA Temple Tips + Ear Hooks + B086H3TZ6B. (2) Asignación manual portfolios RANKING/CONQUEST/DEFENSIVE a las 9 nuevas en Campaign Manager. (3) 06/05 chequeo impressions de las 9 nuevas (4d). (4) 09/05 review performance EXACT iniciales (1sem). (5) Cuando llegue restock: ejecutar [[PENDIENTES_RESTOCK]] playbook (5 campañas + 12 KWs + bid +25-30%). (6) Próxima sesión también: subir bid Brand Hub Heroes $3→$5 + crear KWs "best nose pads" + listing opt B081GB8F89 + conectar Atom11 con Guille (pre-requisito ✓ cumplido).
