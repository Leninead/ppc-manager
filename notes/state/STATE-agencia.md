---
tipo: state
actualizado: 2026-06-24
---

# STATE Agencia — Capybaras

Snapshot operativo de la agencia. Agregador por diseño (no nota atómica).

---

## 2026-07-02 — M31 Revenue Forecast integrado en main

**Estado:** MVP completo (F1→F5) en `main`, pusheado (commit `88b1abe`).

- **F1→F5 completo:** ingesta CSV/Excel, motor blend MoM/YoY + seasonality + OOS + derivación AOV/CVR, UI de forecast editable, export CSV.
- **Tests:** 187 verde.
- **Integración:** por rebase — `main` había divergido por M32 Fase 0; se rebaseó `feature/m31-forecast-port` sobre main antes del merge.

**Deuda post-MVP:**
- Persistencia dormida (`_PERSISTENCE_ENABLED = False`) — el backend Supabase existe pero está apagado tras flag.
- Fixtures reales gitignored — los tests corren contra data sintética; los fixtures de cuentas reales no entran al repo.
- Pendiente: F6, integración Keepa, persistencia Supabase (activar flag).

**M31 Persistencia (tarde):** encendida e integrada (merge `ca9737d` / `601fa6a`). `_PERSISTENCE_ENABLED = True`, hidratar + autosave + UI guardado. Probado end-to-end contra Supabase real.

**DEUDA CRÍTICA — leer antes de tocar M31:**
- ⚠ PROD NO PERSISTE TODAVÍA: falta `AGENCY_OS_FORECAST_BACKEND="supabase"` en Secrets de Streamlit Cloud. En local anda; en capybaras-os.streamlit.app NO hasta setear ese flag.
- ⚠ RLS se reactiva sola (gotcha conocido). Al guardar puede saltar 401. Hardening pendiente: investigar reactivación vs. RLS on + política service_role.
- Falta UI de creación de cliente no-demo.
- M29: 2 tests de apply v12→v13 rotos, preexistentes, deuda aparte.

---

## Última sesión — 2026-06-24 (consolidación multi-frente: merge M31 + M32 a main)

Cierre de día desde el chat consolidador. Tres frentes activos; mergeados dos, uno queda local por falta de tests.

**Mergeado a main (push único del día):**
- **M32 Case Study Studio** — Fase 0 (andamiaje navegable) cerrada y commiteada (f097aaf), mergeada con --no-ff (b5123e0). Módulo `modules/pages/case_study_studio.py` + 3 hooks en app.py. Discovery cerrado, decisión Opción 3 Híbrido (módulo propio Sales Director + importer V7_case_study a M29). **Gate Ramiro CERRADO 25/06:** pidió la herramienta generadora completa, no solo el bloque ("que puedan generar casos sin redactarlo, responden preguntas y se genera"). Doc maestro: notes/decisiones/M32-case-study-studio-decision.md (renombrado de M31→M32). Worktree feat/m32-case-study. Pendiente: Fase 1 (form + doble llamada Claude).
- **M31 Revenue Forecast** — Fases 1-3 commiteadas (7079823), mergeadas con --no-ff (a70daa4). Esqueleto + capa de persistencia PROPIA (core/forecast_persistence.py, flag AGENCY_OS_FORECAST_BACKEND, tabla forecast_clients) + ingesta CSV/Excel + motor de forecast con estacionalidad. Verificación D3 PASÓ: separación de Account Health intacta (cero core.persistence, cero ah_*). 478 tests M31 verdes. Conflicto en app.py resuelto a mano (ambos hooks de navegación conviven). Worktree feature/m31-forecast-port. Pendiente: F4 (UI editable) + F5 (estacionalidad UI + export CSV → cierre MVP).

**NO mergeado (queda local):**
- **M28 SKU Progress** — Bloque 1 de 4 codeado y commiteado local (c98bc83) pero pytest NO corrió (bloqueado por watcher de Streamlit sobre .venv compartido). El propio handoff pide NO mergear sin tests verdes. Queda en worktree feature/m28-sku-detail-view. Próxima sesión: cortar watcher → pytest -k "sku_progress or optimization or m28" → si verde, mergear. Diseño cerrado: campo category opcional (default "Sin categoría", sin migración parquet), set cerrado de 7 categorías. CTR descartado (BR orgánico sin impresiones); CVR viable.

**Numeración (confirmada):** M31 = Revenue Forecast · M32 = Case Study Studio.

---

## Última sesión — 2026-06-21 (M28 wired a Supabase — EN PRODUCCIÓN)

M28 SKU Progress vinculado a Supabase end-to-end y productivo. Se extendió la capa compartida core/persistence.py (borrado + logs ah_logs + client-configs ah_client_configs + list_clientes, en ambos backends, delete_cliente encadenado y acotado al módulo) y el módulo sku_progress_report.py quedó 100% backend-agnostic (cero I/O de disco). Smoke E2E verde contra Supabase real. 2 code-reviews MERGE. Suite 367 / mismos 3 known-env M29.

Mergeado a main por ff (6 commits, HEAD 28d2905). Como el flag global ya estaba activo en Cloud (de M30), el merge fue la activación productiva — sin swap-day separado. Las 4 tablas Account Health (ah_snapshots/configs/logs/client_configs) viven en capybaras-os-prod, RLS off.

Verificación visual en Cloud HECHA: cliente + SKU persiste post-reboot (fila en `ah_client_configs`); RLS disabled confirmado en las 4 tablas AH. **M28 cerrado al 100%.** Deuda nueva P2: el disable RLS vía DDL no toma confiable (pasó 2 veces hoy) → confirmar relrowsecurity=false post-create. Deudas viejas: test-isolation M29, .gitignore secrets.toml*.

**SOPs de uso in-app** embebidos en los 3 módulos productivos (SKU Progress Report, Pricing Dashboard, Proposal Studio): constante `_SOP_MD` + expander top-level `📘 Cómo usar este módulo` en `render()` (commits `2607b4e` + `797f7eb`), verificados en Cloud post-reboot. En Proposal Studio se dejó explícito que los bloques manuales (Brand/Category) y los de importación (SEO/Listing/comparativa/plan) son vías independientes por bloque, no todo-o-nada. Convención en `modules/pages/CLAUDE.md`; copias de equipo en `notes/sops/SOP_USER_*.md`.

Detalle: [[2026-06-21]] · [[m28-sku-progress-report]]

---

## Última sesión — 2026-06-17 (Wiring Supabase Account Health — Fase 1)

Capa de persistencia de Account Health vinculada a Supabase replicando el patrón M29 a nivel de la capa COMPARTIDA core/persistence.py (un swap sirve M28+M30+futuros). Backend-swap interno (_LocalBackend + _SupabaseBackend + selector), jsonb genérico (ah_snapshots + ah_configs), activación opt-in por flag (NO auto-on-creds — desacopla merge de activación). M30 verificado end-to-end contra Supabase real y mergeado a main DORMIDO (sin flag = todo local, cero regresión). Suite 327 verde / 3 known M29.

Commits (3, en main por ff): f8ea195 refactor _LocalBackend · e24ff24 feat _SupabaseBackend+transport · faf1ab6 test 18 fake-transport. HEAD main faf1ab6.

Pendiente: swap-day Cloud (flag backend="supabase" en secrets + reboot, 3 min). M28 el lunes (más pesado: 4 escrituras fuera de banda + helpers de borrado nuevos + ah_logs, ~2-2.5h). Deuda: test-isolation M29 (3 rojos por secrets vivas, sesión aparte), endurecer .gitignore a secrets.toml*.

Detalle: [[2026-06-17]] · [[m30-pricing-dashboard]]

---

## Última sesión — 2026-06-17 (Frentes cliente — LTD meeting precio + Setex Prime Day)

Día multi-frente (en paralelo al wiring Supabase). Dos frentes de cuenta cerrados: LTD (meeting dueño + setup Prime Day) y Setex (armado Prime Day). Ambos con automatización que se auto-revierte post-evento.

**LTD — meeting dueño (Aaron/Adam):** caída de ventas validada como **PRECIO, no PPC**. Semana -24.6% sales, tráfico plano (-4.1%), ACoS 19.8% en target; lo único que se desplomó fue conversión 3.28%→2.37% (-27.7%). Causa = precio post-Hot Sale (SQP relación precio↔share r=-0.80). Aplicado HOY (bulk F0 Success): pausadas 3 camps gasto/0 ventas (SwaddleMe + TOP20 conquest + SU-612M EXACT saco), bid-down `swaddle para bebe 0-3` $12→$8, 6 negative PT en Scavenger AUTO (incl. B0F8PCWD6J ASIN propio = auto-canibalización). Prime Day 23–30 jun AUTOMATIZADO (auto-revert 1/jul): campaña Grey `SU-PUSH | MX | SP | KW | GREY | PRIMEDAY` (bulk F1b Success, product ads B0081GIZ52 + B0081GIYTE) + Budget Rules schedule-based por UI (PT Category +33% → ~$698/d, Broad +30% → $455/d). Grey = B0081GIZ52 (identificación asumida, pendiente confirmación Agustín). Pendientes Agustín: ETA restock B09MG1PM6L (~18d runway → gatilla pull-back, bulk listo), confirmar Grey, verificar elegibilidad 2 product ads (fallback SKU `L20 01 002 GR M-stickerless`).

**Setex — Prime Day (23–30/06, −20%):** armado con Bulk A (conservación Negro) + Bulk B (budget ceilings subidos), ambos Success. Tati aprobó budget de evento $1.300–1.400/día. B08C2T72ND (1mm Negro, #2 en ventas) SIN restock → modo conservación (solo orgánico), se agota ~arranque del evento. STANDBY: re-consultar reposición a Tati; al reponer, re-activar Bulk A (20 product ads → enabled). Thick PAT MOCOFLY corregida: pausados 3 product ads (el 123% era colapso de junio, no estructural), queda el converter B09HW4VWQR.

**Setex — pendientes vivos:** Componente C (bids + ToS) BLOQUEADO por inventario (falta runway B081GB8F89 + stock B08SNRCL63). Clearance overstock Thin (1.280u B08PZF22R1): sin vehículo (no hay Thin AUTO) + falta OK de Tati. ~22/06: re-activar product ad B0BQ8FNGR5 en Thick PAT MOCOFLY.

**Aprendizajes de bulk (de ambos frentes — PENDIENTE promover a CLAUDE.md raíz):** (1) celdas vacías de `Start Date`/`State` en filas Entity=Campaign → upload Failed; poblar con el valor REAL aunque no se cambie (Start Date como TEXTO yyyyMMdd, State actual); aplica también a updates de budget. (2) Budget Rules por UI (Add budget rule → Schedule → date range → % increase), NO por bulk (hoja "Budget Rules" del BSE viene vacía + enums no confiables → riesgo Failed).

Detalle: [[LTD]] · [[setex]] · [[2026-06-17]]

---

## Última sesión — 2026-06-16 (M29 Supabase wiring productivo + hotfix Cloud)

**Supabase wiring PRODUCTIVO cerrado end-to-end (local + Cloud). Pendiente externo #1 de M29 resuelto antes de lo esperado. 1 commit técnico + 1 docs. HEAD post-cierre.**

- **Hotfix Cloud**: incidente `TemplateNotFound: '_placeholder.html'` en propuesta fresh post-rediseño. Causa raíz = deploy stale (módulo cacheado en memoria del proceso Cloud). Fix = Reboot de la app. NO era bug de código (reproducción local imposible).
- **Test de regresión** (`8b4400c`): 2 tests nuevos cubren render con propuesta fresh + blocks vacío. Suite 310 → 312 verde. Cierra el blindspot que causó el incidente.
- **Supabase wiring productivo**: proyecto `capybaras-os-prod` creado, DDL ejecutado (tablas `proposals` + `proposal_votes`), credenciales en secrets.toml local + Streamlit Cloud. Incidente 401 = RLS activado sin política INSERT para anon (PostgREST traduce a 401). Resuelto deshabilitando RLS (single-tenant). 60 propuestas migradas (62 filas, 6 únicas en UI). Verificado: local + Cloud leen/escriben Supabase, persistencia sobrevive redeploys.

**Deuda de seguridad (P2)**: RLS off + anon key expuesta en chat de trabajo. Rotar a service_role + RLS con políticas antes de exposición pública/multi-tenant.

**Pendientes M29 restantes** (dependencias externas): chart V3 data (Ramiro B7), galería V5 (Ramiro contrato v2), F3 marcas reales (Freddy + compliance), hidratado Tier 2-3.

Detalle en `notes/daily/2026-06-16.md`. Swap day playbook (que funcionó) en `notes/modules/m29-proposal-studio.md`.

---

## Última sesión — 2026-06-12 (M29 rediseño visual PDF Turno 2 + cierre al 100%)

**M29 cerró el rediseño visual al 100% del scope nuestro. 5 commits acumulados en main local, NO pusheados (consolidador del día). HEAD `e9ece76`.**

- **Commit `bcf29db` — F3/F4 cards rediseñadas**: F3 brand stages como tabla 1×3 de cards naranja-pálidas con empty-state premium (eyebrow + tagline + Pendiente/Pending). Taglines bilingües hardcoded (estructura fija, decisión documentada). F4 operation pillars como tabla 2×2 con `loop.index0 % 2` para tr open/close. Default canónico del catálogo (4 pilares) consume vía `_effective_data` overlay. Violations xhtml2pdf saneadas: `display: grid` → tabla, `var()` color → hex literales, `<p>` con `line-height` explícito.
- **Commit `8e4864f` — 3 deudas P3 cerradas**: V2 con guard `{% if ... %}` envolviendo `<table class="kv">` (warning "table is empty" desaparece). `_base.html` con selector `th` simple en `@media print` (todos los th del documento van mono, verificado). F6 con `page-break-after: avoid` en `<h3>` del loop de pillars ("El Fin de la Improvisación" + cuerpo juntos).
- **Commit `ecf3a61` — V1 cierre deudas**: hallazgo visual en Turno 2 (arrays sin separador → "Cat ACat B"). Discovery reveló causa: loops con `<span class="pill">` que xhtml2pdf no renderiza. Fix: `{{ data.X | join(', ') }}` plano + `<span class="mono">` para hero_asins. Guard tabla kv aplicado (mismo patrón que V2).
- **Commit `9bf251a` — Skip bloques sin template propio**: 7 secciones mostraban "contenido pendiente" textual (V17-V22 + F5). Opción B (renderer skip) en `proposal_renderer.py`: `continue` en lugar de fallback `_placeholder.html`. F5 envuelta en `{% if data.selected_cases %}`. Test reescrito. PDF de 14598 → 12854 bytes. Secciones de 18 → 11.
- **Commit `e9ece76` — Cleanup dead code _placeholder**: constante `_PLACEHOLDER_TEMPLATE` + archivo `_placeholder.html` + 2 docstrings stale eliminados.

**Suite 310 verde** en cada checkpoint. PDF verificado visualmente: F1 cover, F2 cards, F3 cards, F4 pilares, V1 con join, V2 con guard, F6 page-break OK, sin "contenido pendiente", sin warnings stderr.

**Pendientes M29 restantes** (NO dependen de nosotros):
- Supabase wiring productivo: depende del pago de Edu. Código + tests listos, playbook documentado en `notes/modules/m29-proposal-studio.md` sección "Supabase swap day".
- Chart V3 data real: contrato v2 Ramiro (B7).
- Galería V5: contrato v2 Ramiro.
- F3 marcas reales: Freddy + compliance LTD/M&B/Setex.
- Hidratado Tier 2-3: inputs externos por cliente.

**Deudas P3 silenciosas** (no rompen hoy, registradas en `notes/daily/2026-06-12.md`):
F5 grid+var dentro del `{% if %}`, F4 par/impar pillars, heading F2 hardcoded, bug visual títulos colapsados pág 3, F7 roles incorrectos en seed, F6 flex pre-existente, .pill no renderiza en PDF (bug latente otros bloques), naming test_template_split misleading.

**xhtml2pdf 0.2.17 — 9 gotchas inventariadas** (8 del 11/06 + 1 nueva: `.pill` no renderiza). Patrón table-based con `border-spacing` validado para grids 3×2, 1×3 y 2×2.

**Lessons learned operativas del día**:
1. CC auto-aplicó Opción B antes de ejecutar safety check S1+S2 (transparente al reportarlo). Approach correcto, sin reversión. Reforzar wording de safety check en próximos prompts.
2. Régimen de commits mixto en una iteración (CC vs terminal). Sin pérdida funcional.

Detalle en `notes/daily/2026-06-12.md` y `prompts/sesion/features/arranque-m29.md` (actualizado).

---

## Última sesión — 2026-06-11 (M29 rediseño visual PDF Fases 1+2)

**M29 avanzó del 95% al 97%. 3 commits acumulados en main local, NO pusheados (consolidador del día). HEAD `7695310`.**

- **Commit `f5ee8c4` — paleta + cover dark hero**: `_base.html` con paleta Capybaras canónica expandida (semáforos success/warn/danger, surface-soft callouts, accent-strong, text-soft, border-accent), 4 clases utilitarias nuevas (.eyebrow .callout .metric .status-badge.{success,warn,danger,neutral}), border-top naranja en `.doc`, @media print con Helvetica/Courier core + letter-spacing -0.2px. F1_cover.html cover dark hero con canvas continuo via `<table><td bg #1F1F1F>` (cliente protagonista en h1 blanco, eyebrow naranja con fecha, footer mono).
- **Commit `7695310` — pulida spacing + F2 cards**: padding .block 2.4→3rem. F1 con `<p>` + line-height explícito (fix inheritance). F2_about_stats rediseñado completamente como grid 3x2 de cards naranja-pálidas via `<table border-spacing>`. Campos shape real (monthly_revenue_usd, monthly_ad_spend_usd, conversion_rate_advantage). Heading hardcodeado bilingüe.
- **Suite 310 verde** en cada checkpoint (3 corridas). PDF generado y verificado visualmente.

**Aprendizajes xhtml2pdf** suman 4 nuevos al inventario: (1) `background` en section/div con múltiples children fragmenta — solución bg en td wrapper; (2) inheritance de line-height del body NO colapsa adjacent block margins en xhtml2pdf — solución `<p>` con margin/line-height explícitos; (3) `text-align: right` en td falla a veces, usar `align="right"` atributo HTML; (4) `border-spacing` en table SÍ funciona para grids de cards. Patrón table-based para layouts horizontales validado.

**Pendientes M29 restantes**:
- Turno 2 mañana (Fases 3-4): F3 Crear/Lanzar/Escalar como 3 cards + F4 Cómo Operamos 4 Pilares como cards 2x2 (~45 min CC).
- Después: M29 ~98%. Restantes son externos: Supabase wiring (viernes), chart V3 data source (B7 Ramiro), galería V5 (contrato v2 Ramiro), hidratado Tier 2-3.

**Deudas anotadas durante el run** (P3 baja):
- Warning xhtml2pdf "<table> is empty" en tablas kv vacías. Ruido en logs, benigno.
- Bug paginación F6 pre-existente: "El Fin de la Improvisación" se separa del primer pillar en page break.
- Mono inconsistente en `<th>` de table.kv (selector compound `table.kv th` en @media print no siempre honora). No bloqueante.
- Heading F2 cambió de configurable ({{ title or module_id }} del catálogo) a hardcodeado bilingüe. Reversible.

Detalle en `daily/2026-06-11.md` y `prompts/sesion/features/arranque-m29.md` (actualizar mañana al cierre del Turno 2).

---

### Última sesión — 2026-06-10 (LTD WoW post Hot Sale)

Análisis WoW sobre weekly report del cliente. Sin cambios en cuenta. Diagnóstico:
-31.9% sales WoW / -49% ad sales explicado 100% por comparador Hot Sale México
(PW = TW del WoW 04/06 con +33.3% boost) + pausas intencionales (15 ASINs con
-100% ad sales coinciden 1:1 con pull-back 04/06 + bulks 08/06, ~MX$33K
pausados deliberadamente = 89% de la caída de ad sales).

Salud subyacente confirmada: CVR -11.8% vs sessions -30.7% (calidad sostenida),
BuyBox 99.63%, eficiencia spend mantenida, TACoS 12.1% (cerca target Junio).
Winners reales: B0F8P9GBZN (hero #1 OAT S) ad sales +325% post bid up 08/06 ·
B005ULUZIQ +42% post desaparición competidor -20% · B0DJSGBR4P +103%.

Deliverable: `LTD_WoW_2026-06-10.html` (HTML bilingüe ES/EN, 7 causas ranqueadas,
5 recos operativas). Distribución directa Adam/Aaron/Agustín. NO en repo (patrón
WoW 04/06).

Pendientes: ETA restock (Agustín) · monitoreo B005ULUZIQ 7-14d antes reactivar
ad groups pausados · evaluación D+7 (15/06) impacto bulks 08/06 · cerrar reporte
gray market 7 ASINs con Adam/Edu.

---

## Última sesión — 2026-06-08 (M30 Pricing Dashboard — F3.5 cerrada, BUILD 6/6)

**Foco**: M30 Pricing Dashboard — F3.5 (exports XLSX), última fase del build.

**Estado**: **BUILD 6/6 COMPLETO** (F3.1 schema · F3.2 parsers+lookups · F3.3 scoring · F3.4 UI C1-C4b · F3.5 exports · F3.6 router). Navegable en Account Health → `💲 Pricing Dashboard`.

**Output** (`feature/m30-pricing-port`, pusheado, HEAD `12e7eb7`): `1d420a4` _build_resumen_excel (port verbatim exportResumen) + botón · `0755206` _build_vista_excel + 4 botones por vista · `12e7eb7` refactor menores reviewer. 16 tests verde. code-reviewer Opus 4.7 **MERGE, 0 bloqueantes**.

**Discovery F3.5**: de los 4 "exports" del HTML, solo `exportResumen` era real+wireado; `exportTracker` bloqueado (depende de un 7º source no porteado); `exportAllInOne`/`exportTable` eran botones fantasma. Scope real = exportResumen verbatim + 4 export-por-vista reconstruidos. Desviación consciente: filename `Gamboa_`→`{cliente}`.

**Learning operativo**: contención por concurrencia (pytest solapados + Defender post-kills) infló `import streamlit` de ~1.6s a 28min. Regla: UNA corrida pytest a la vez, no solapar, no relanzar sobre una en background.

**Deuda viva (fuera del build)**: builders awd/izzi `{sku: unidades}` (restock PATH-37, panel awdfba) → próxima sesión.

---

### Última sesión — 2026-06-19 (Dermaglos US — 360° + ejecución pre-Prime)

- **Estado**: 5 bulks ejecutados (Success). Cuenta lista para Prime 23–30/06 (20% off). ACoS baseline 58.9%, objetivo 45%.
- Cuenta limitada por BID no budget (uso 5% del techo $803/d). Cirugía a nivel target/placement aplicada sobre bleeders del build 28/04.
- Conquest Hipoglós reactivada (233664018879908, $15/d, dynamic down-only, end 20260630).
- **BLOQUEOS/PENDIENTES**:
  - B0F6VZMF2V (Facial Set) OOS → push diferido hasta restock.
  - Unfulfillable a recuperar: 30u hero Cream B0CYLMJJJC + 11 Night + 10 2pk Cream.
  - Gate de listing micellar/cleanser (B0CYK4G2Y8, CVR 5.8%) → fix de listing, no PPC. Para cliente.
  - Demanda de marca no listada: protector solar, niacinamida serum → conversación revenue con Agustín/cliente.
- **PRÓXIMA EVAL**: STR fresco post-30/06 → medir delta ACoS y performance Hipoglós/escalado en Prime.
- **LEARNING**: cruzar BSE en todos los estados (no solo enabled) antes de dar una campaña por inexistente — el grep enabled-only generó un CREATE duplicado que rebotó.

Detalle en [[daily/2026-06-19]] + [[DERMAGLOS]] sección 2026-06-19. Previa: 2026-06-08 análisis 360° + 9 bulks F8 ([[daily/2026-06-08]]).

---

### Última sesión — 2026-06-04 (LTD pull-back inventario)

Directiva de Aaron (LTD): restock congelado (inbound 0 cuenta completa), frenar ads en
thin-stock + reasignar a stock profundo. Ejecutado bulk Product Ad pull-back (22 filas →
paused, Success 13:42 ART) — sin pausar campañas, solo product ads en cajones compartidos.
Thin: B09S14W4SS + B0F8PB4NHX (brand defense viva). Waste: B0FHHV9CZN. B005ULUZIQ: solo
ad groups $0 (es BB 84.4%/precio, no stock → Adam/Edu).
Hallazgo estructural: 84% del spend en 4 campañas catálogo-completo, sin campañas por-ASIN.
Deliverables no commiteados: WoW HTML bilingüe + bulk xlsx.
Pendientes: SBV B09MG2CVCR (SB aparte) · B005 precio · restock ETA Agustín · TIB 48–72h.
Bloqueos: B005 BB 84.4% · thin-stock sin reposición (inbound 0).

---

## Última sesión — 2026-06-03

**Foco**: M30 Pricing Dashboard — F3.2 (parsers + lookups) CERRADA.

**Output** (branch `feature/m30-pricing-port`, pusheado): `cfaa83d` parsers+lookups · `6b173b8` 3 fixes
verbatim (izzi sheet + cogs hint + csv sep) · `a89fc4b` chore landmine · `86afa4d` blindaje 2 MAYOR. HEAD 86afa4d.

**code-reviewer Opus 4.7 read-only**: APROBABLE, 0 bloqueantes, 2 MAYOR blindados.

**Fix real F3.2**: izzi leía la primera hoja; el HTML lee 'Inventario 2526' con fallback + header=None.
Sin el fix arrastraba hoja equivocada a F3.3.

**Landmine pytest RESUELTO (branch-local)**: `pytest.ini testpaths=tests` neutraliza la contaminación de
`sys.modules` de los scripts con `sys.path.insert` (scratch_M27, smoke_b6a). Vive solo en m30 → propaga al
merge, o aplicar a main aparte.

**Deuda pre-existente confirmada (no M30)**: 4 failed/2 errors en tests/ por fixtures ausentes (P2 ya
documentada: v12 gitignored + secrets en worktree). Fix: fixtures trackeados.

**Estado M30**: 2/6 fases de build cerradas (F3.1+F3.2). F3.3 (scoring engine) pendiente. Bug 30-vs-37 y
decisión parseCSV-trim a resolver en F3.3. Ship objetivo: viernes 2026-06-05.

Detalle en `daily/2026-06-03.md` y `modules/m30-pricing-dashboard.md`.

**F3.3 CERRADA (misma sesión)**: scoring engine pusheado — `84765f5` _compute_ais · `fb7a030`
_compute_score · `880967e` _enrich_record+_run_analysis. HEAD 880967e. code-reviewer MERGE 9.5/10,
0 bloqueantes. Estado M30: **3/6 fases de build cerradas**. Falta F3.4 (UI) + F3.5+F3.6. Ship viernes intacto.

### Frente M29 — Proposal Studio: S5+S6 CERRADO, mergeado a main, deploy operativo

**M29-S5/S6 CERRADO** — mergeado a main (`--no-ff`, `3a999ac`) y deploy operativo en **capybaras-os.streamlit.app**. HEAD de main: `2e50695`. Ciclo S5 (renderer HTML) + S6 (export PDF) completo.

**Chart V3 (Dominación Page 1):** bug de barras invisibles en PDF resuelto con patrón **table-cell** (`9328d29`) — el `<div>` vacío con `height`+`background` colapsaba en xhtml2pdf/reportlab. Verificado con datos reales (barras proporcionales, cliente en `--accent`).

**Fix deploy (`2e50695`):** Streamlit Cloud rompía con "Error installing requirements" — `xhtml2pdf` → `svglib 1.6.0` → `rlpycairo` → `pycairo` (no compila sin libcairo). Pin `svglib==1.5.0` (última pre-rlpycairo, satisface `>=1.2.1`) saca pycairo del grafo. Verificado en venv limpio (dry-run). De paso dedup `anthropic`/`python-dotenv`.

**Motor PDF: xhtml2pdf 0.2.17** — weasyprint descartado (dependencia GTK en Windows). Arquitectura: capa PDF separada en `core/proposal_pdf.py` (`_sanitize_html_for_pdf` adapta fonts remotas / `var()` / letter-spacing em / flex del chart) sin tocar el renderer puro ni los templates. **Suite 136 verde.**

**M29 LISTO para demo Ramiro.** Pendientes restantes son **post-demo** (no bloquean): (1) dato fuente del chart V3 (`page1_domination_chart_data` vacío en prod → importer B7 o carga manual); (2) persistencia efímera (propuestas untracked + FS efímero Cloud → no sobreviven redeploys; pendiente `SupabaseStorage`, capa abstracta lista); (3) contrato v2 Ramiro (desbloquea V5 asset gallery); (4) rediseño visual del template (color/tipografía Capybaras).

Detalle en `daily/2026-06-08.md` (sección "M29 — Cierre") y `prompts/sesion/features/arranque-m29.md`.

---

## Última sesión — 2026-06-02

**Foco**: doble frente — LTD-MX (sesión paralela) + M30 Pricing Dashboard.

### Frente M30 — Pricing Dashboard

**Output**:
- `f93a37d` docs(porting): README pricing-dashboard M29 → M30
- `8d79e9e` feat(M30): schema v1 + test persistencia (en feature/m30-pricing-port)
- `a4d159a` docs(M30): daily appendeado + módulo M30 en notes/

**Agentes**: `data-persistence-specialist` Caso 2 (6/6) + `code-reviewer` Opus 4.7 (APROBADO).

**Bug heredado registrado**: restock 30-vs-37 días en HTML L837 + L1029. Replicar verbatim en F3.3, fix consciente posterior.

**Decisiones arquitectónicas M30** (5 cerradas en F2):
1. Snapshot HTML self-contained eliminado
2. SAMPLE_DATA Gamboa no porteada
3. SUBCAT_FEE_AVG hardcoded → config per-cliente
4. enrichRecord passthrough → _enrich_record Python
5. Year hardcoded 2026 en v1

**Estado M30**: 1/6 sesiones completas. F3.2 (parsers + lookups) pendiente. Branch `feature/m30-pricing-port` HEAD `8d79e9e`.

Detalle completo en `daily/2026-06-02.md` (sección M30 al final) y `modules/m30-pricing-dashboard.md`.

---

## Última sesión — 2026-05-26 (4 frentes: M4 fix + M29 D3+D4+DataDive + M27 ship + Setex)

> Día multi-frente (worktrees-flow v1.0). Una sub-sección por frente.

### M4 — Análisis Cruzado (14 bugs) — ✅ main `b2763cb`+`bf205f7`

Sesión de fix completo de M4 (`modules/pages/analisis_cruzado.py`). Commit `b2763cb` (+313/-33). Audit doble code-reviewer (intermedio + final) PASS + 2 smokes reales PASS (Setex 22/05 + Dermaglos 08/05).

**Resueltos (commit b2763cb):**
- BUG-1 M4: mitigación visual con panel diagnóstico cobertura Match Type (fix REAL pendiente C-2).
- BUG-2, BUG-3, BUG-4, BUG-5, BUG-6, BUG-7, BUG-8, BUG-9, BUG-10 (todos M4).
- 4 adicionales del audit: Opportunity Score disponible en Tab 2, `precio=0` vestigial removido del classifier, NaN-or trap arreglado con helper `_br_num`, dedupe SQP sin mutar `df_sqp` original.
- Bonus: acción nueva `🏆 BRAND PURE OK` + reorden bloque BRAND antes de ESCALAR/AGREGAR (FIX B post-audit).

**Movido a próxima sesión / C-2:**
- BUG-1 fix REAL en M2 (`search_term_report.py` L325-345): la merma AUTO/PT (~70% del spend) viene de la vista Winners / filtro upstream, NO de M4. M4 lee el STR raw sin filtrar.

**Deuda técnica registrada (no bugs):**
- M4: columna residual `_asin_ext` en `df_str` (scope local Tab 3, sin impacto en exports). Aplicar `df_str_t3 = df_str.copy()` solo si se reordenan los tabs en el futuro.
- M4: `_br_num` no maneja separador de miles europeo (`1.234`). YAGNI — Amazon US/MX exporta con coma de miles.

**Learning operativo — Python NaN-or trap:**
En expresiones tipo `expr or default` donde `expr` puede devolver NaN, NaN es *truthy* en Python → `NaN or 0` devuelve NaN, no 0. Siempre usar `pd.isna()` check explícito. Detectado por code-reviewer en B4.4 (parser BR de M4). Aplicar en futuras refactors de parsers similares.

### M29 — Proposal Studio — ✅ D3+D4 main (`458fb4b`) · ⏸️ DataDive mapper branch (`0aa5261`)

B7 UI dispatcher D3+D4 (apply 2-clicks + merge + save con auto-bump) mergeado a main. DataDive → V3 mapper en branch `feature/m29-datadive-mapper` (E1→E5: parsers a `modules/parsers/` + mapper `datadive_to_v3_block` ImportReport-driven, suite 95/95 bajo venv 3.12, **pendiente merge mañana**).

**Deudas nuevas M29:**
- **P2 — fixture trackeado:** `test_b7_importer` + el test de integración del mapper dependen del proposal gitignored `01fbf5c2…__v12.json` → `FileNotFoundError` en worktree/clone limpio. Mover a `tests/fixtures/`. ANTES del merge.
- **P3 — flag-collision DataDive vs B7:** ambos usan `ps_b7_confirm_apply_{pid}`. Parametrizar `flag_key` en `_render_b7_apply_flow`.

### M27 — Flat File Migrator v1.1 — ✅ SHIPPED main (`5fa3e02`)

v1.1 soft launch (soak 14 días) + setup venv Python 3.12 (`c10fa27`, destraba P1 segfault 3.14 = ABI NumPy/pyarrow, no era el .xlsm) + audit B6-b-5 PASS sin P1. Validado E2E contra .xlsm originales + deploy live. Mensaje team Slack enviado.

### Setex — hallazgo categoría B08PZF22R1

Análisis de imagen Inventory de Tati + hallazgo P0 de categoría mal seteada en familia Thin. Mensaje a Tati enviado vía Slack 26/05. Bid hold Thin family hasta corrección.

**Pendientes activos (P0 → P1):**
- **P0 — Categoría B08PZF22R1 (Thin 5p Transp)** mal seteada en Ropa/Gafas en lugar de Salud y Cuidado Personal. Bloqueador estructural Thin family. Acción en Tati (flag 26/05 vía Slack). Validar también B09T7BF9TK (Kids Negros, Deportes y Aire Libre).
- **P1 — Bid hold Thin family** hasta corrección categoría. Push 25/05 corriendo, sin escalado adicional.
- **P1 — Fase 2 Temple bulk reactivación rank** programada sesión 01/06. Stock validado 49u (B0C7WPFVGV) + 96u (B0B94KBY8H), $0 sales 30d.
- **P1 — Re-pull SQP D+7 post-fix categoría** para validar reframe diagnóstico CS/PS técnicos.

**Aprendizaje — Categoría incorrecta como bloqueador estructural (26/05):**
- Cuando un child ASIN tiene Sales rank en categoría distinta a sus hermanos del mismo parent, validar breadcrumb PDP antes de invertir en PPC sobre ese ASIN
- Síntoma diagnóstico previo (SQP CS 100% / PS 0% en queries técnicas) puede ser disonancia categórica, no problema de copy
- AUTO targeting opera sobre browse node → categoría incorrecta = waste estructural en AUTO
- Antes de subir bid sobre un ASIN con waste alto en AUTO, validar categoría primaria

**Evento de cuenta:**
- 2026-05-26 — Hallazgo P0 categoría B08PZF22R1 (Thin 5p Transp 1300u stock) en Ropa › Hombres › Gafas en lugar de Salud. Frente abierto vía Tati. Bid hold Thin family hasta corrección. Mensaje Slack enviado.

---

## Última sesión — 2026-05-15

Sesión multi-frente. Logros, bloqueos y plan próxima semana:

**M27 — Cerrado v2 con extensión Strategy 3.5 (113→256)**
- Tabla `_STRUCTURED_ALIASES` (40 entradas) agregada a `flat_file_migrator.py`
- Cobertura Apparel/Coat USA: 41% → 50.7%, críticos 7/9 → 9/9
- Validado offline con archivos reales de Marcos
- Pendiente: Marcos prueba local + feedback

**M29 — Bug crítico botones Guardar V1 y V2 (sin resolver)**
- Regresión V1 introducida en commit `9a3eaad` (15/05)
- Auditoría forense ejecutada, pendiente de leer
- Compromiso público Slack en riesgo (fases 3+4 vencen domingo 18/05)

**Atom11 MCP — Diferido a próxima semana**
- 25 tools custom disponibles via `api.atom11.co/mcp`
- Sesión dedicada ~45 min planificada
- No bloquea ningún cliente urgente

Detalle: [[2026-05-15]] · [[2026-05-15-m27-strategy-3-5-structured]] · [[2026-05-15-m29-bug-save-buttons]] · [[2026-05-15-atom11-mcp-integration]]

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

## Última sesión — 2026-05-13

**Foco principal**: M29 Proposal Studio Sesión 3 (parcial) — B1 routing vista
detalle + B2 listado readonly de blocks con badges por tier.

**Output principal**:
- `modules/pages/proposal_studio.py`: 274 LOC nuevas (139 B1 + 135 B2).
  6 helpers nuevos: `_init_detail_state`, `_open_detail`, `_close_detail`,
  `_is_detail_active`, `_render_detail_screen`, `_render_blocks_section`.
  Branch S3 inyectado en `render()`.
- Sin nuevos archivos creados. Sin imports nuevos.

**Commits del día**: `6b0f2dc` (S3-B1) + `5cc0fd3` (S3-B2). Ambos en `main`,
SIN push (acumulando hasta B6).

**Sub-bloques ejecutados** (2 de 6 del plan S3):
- B1 routing vista detalle (state machine + skeleton + branch en render)
- B2 listado readonly con badges editable/locked/coming-soon + border-left
  por tier

**Smoke test E2E**: 3 propuestas demo abiertas (Launch/CVR/Scale+SEO) →
header completo + 15-18 blocks renderizados correctamente → badges por tier
visibles + 4 colores de border-left + placeholders S4 con opacity reducida
→ Volver al listado + abrir otra propuesta → state machine resetea
correctamente. Sin warnings ni errores en consola.

**Hallazgos de catálogo**: composición CORE varía por arquetipo. B3 obliga
a iterar sobre CORE PRESENTES en cada propuesta, no sobre 6 hardcodeados.
Primera aparición de tier COMMON (V13, V14, V16) y de 3 placeholders S4
(V27, V28, V29). Render correcto para 4 tiers × 2 status combinables.

**Decisiones cerradas**:
- Routing vista detalle: opción B (reemplazo de pantalla), no tab nuevo ni
  expander inline. Consistencia con patrón del wizard.
- Buffer híbrido en `ps_detail_buffer` + save explícito. Confirmación
  2-clicks al Volver con cambios pendientes (a implementar en B5).
- Bilingüe en edición: solo idioma activo + expander colapsado para el otro.
- B3 partido en sub-bloques B3-b a B3-f: V1 end-to-end primero para validar
  el patrón antes de replicarlo a V2-V6. V6 último por complejidad (array
  anidado de fases bilingüe).

**Lección aprendida (CC vs chat)**: hallazgo crítico del CC en el prompt de
descubrimiento: `pp.load_proposal` NO existe — la función real es
`pp.get_proposal(proposal_id, version=None)` y devuelve `None` cuando no
encuentra (no raisea). Sin ese catch del CC, B1 fallaba al primer test.
Refuerza el patrón de "CC primero descubre, chat después diseña".

**Pendientes para próxima sesión** (S3 continuación):
- B3-b: V1_brand_overview form completo + save funcional → valida patrón
- B3-c a B3-f: replicar patrón a V2, V3, V4, V5, V6 (V6 último)
- B5: botón "Guardar cambios" activo + version bump automático +
  confirmación 2-clicks al Volver con buffer no vacío
- B6: polish (autocomplete=off + fix badge "Sesión 2 (skeleton)" +
  info-box dinámico "los N CORE" + git renormalize por deuda recurrente #5)
- B6 final: push acumulado a `origin/main` (3 commits acumulados como
  mínimo: B1 + B2 + B3-B6)

Detalle completo en `notes/daily/2026-05-13.md` y `notes/brands/agency-os.md`
(sección 2026-05-13).

---

### Última sesión — 2026-05-22 (M27 v1.1 — B5-b/c + hardening + plan B6)

**Sesión cierre arrastrado 21/05 + sesión completa 22/05 (~4h).**

**M27 Flat File Migrator v1.1 cross-schema — row pipeline cerrado + decisión B6 tomada:**

- 3 commits sobre `modules/pages/flat_file_migrator.py` (+333 LOC):
  - `f274122` — B5-b `_extract_old_rows` row extractor + Required validator (+143 LOC, 21/05)
  - `3248695` — B5-c `_migrate_row` row migrator core + 5 diagnostic codes (+148 LOC, 21/05)
  - `e10b961` — hardening post-audit: P1-1 empty_field_map + P1-2 field_id_row_out_of_range + P2-3 end_of_data_reached (+42 LOC, 22/05)

**Audit code-reviewer (Opus 4.7)** sobre B5-b + B5-c (21/05, post-commit): **APPROVE 8/8, 0 bugs activos**. 11 trayectorias críticas trazadas limpio. 9 findings advisory (2 P1 + 4 P2 + 3 P3). Las 3 mitigaciones de mayor señal aplicadas en `e10b961`.

**Pipeline row-level cross-schema OLD→NEW operativo end-to-end**, validado via `scripts/smoke_b6a_e2e_pipeline.py` (smoke E2E PASS 12/12 sanity checks, 1.27s, 7 rows → 152 new_fields, 0 crashes). Performance: openpyxl load 925ms + pipeline <350ms.

**5 diagnostic codes implementados en B5-c**: `unmapped_field`, `deprecated_enum_no_target`, `deprecated_value`, `unknown_enum_value` (pasthrough con flag), `missing_required_in_new` (warning, no error). Más 3 codes en B5-b: `missing_required_in_old`, `no_field_ids`, `end_of_data_reached` (level=info), `field_id_row_out_of_range`.

**Discovery UI v1 completo** (B6-a paso 2, read-only): mapa estructural de 2198 LOC, 33 funciones, anatomía exhaustiva de `_render_marketplace` (234 LOC, 8 widgets, 6 branches), pipeline v1 same-schema mapeado (11 funciones), cross-pollination v1 vs v1.1 (12 helpers v1.1 huérfanos hoy, todos se conectan en B6).

**Decisión arquitectónica B6 cerrada**: **opción (b) toggle radio v1/v1.1 al inicio de `_render_marketplace` con auto-detección del modo recomendado por `_detect_schema()`**. Justificación: preserva v1 estable (5 estrategias + 61 aliases validados con clientes reales) + expone v1.1 como opt-in con auto-detect guiando al AM + bajo costo implementación (~50-80 LOC) + path evolución linear sin big-bang. Opción (a) descartada (10 tabs anidadas arruinan UX). Opción (c) descartada (riesgo regresión MUY alto).

**Plan B6-b producido**: `notes/modules/M27-b6-plan.md` (240 LOC, gitignored por bug `.gitignore` documentado desde 2026-04-22). Documento estructura B6-b en 5 sub-bloques (B6-b-1 orquestador `_run_migration_v11` / B6-b-2 auto-detect + radio / B6-b-3 renderer diagnostics / B6-b-4 expander cómo funciona / B6-b-5 audit + mitigaciones). Estimación: 2.5-3.5h cabe en una sesión.

**Estado al cierre:**
- ✅ 7/8 sub-bloques M27 v1.1 cerrados (87%)
- ⏸️ Único bloque pendiente: **B6 UI integration** con plan ejecutivo en disco

**Deuda activa M27 (post-audit, NO aplicado, blanda):**
- P2-1: validación Required NEW O(N×M)
- P2-2: `str()` ingenuo sobre datetime/Decimal
- P2-4: shadow-match `old_label == ""`
- P3-1: rename `_extract_old_rows` (colisión nominal con `_extract_template_rows`)
- P3-2: rename codes `deprecated_value` / `deprecated_enum_no_target`
- P3-3: detectar `field_overwrite_in_new`
- Heredada audit 19/05 (B5-a): B5-a-bis (P3 #7), B5-a-bis-bis (P1 #1), B5-a-bis-tris (P1 #2)
- Discovery B6-a: `_extract_template_rows` (L712) helper huérfano; doble apertura workbooks auto-detect (~100ms)

**Validaciones data-dependientes pendientes:**
3 codes ausentes en smoke (deprecated_value, deprecated_enum_no_target, unknown_enum_value) requieren OLD file con ISBN/GCID o Relationship Type. Capturar en B6 cuando se haga smoke E2E completo con archivo de cliente real.

**Próxima sesión M27:** B6-b según plan en `notes/modules/M27-b6-plan.md`. Secuencia: B6-b-1 orquestador → B6-b-2 radio + auto-detect → B6-b-3 renderer diagnostics → B6-b-4 expander (opcional) → B6-b-5 audit + mitigaciones. Total estimado: 2.5-3.5h.

Ver: [[2026-05-22]] [[2026-05-21]] [[M27-flat-file-migrator]] [[M27-b6-plan]] [[code-reviewer]]

---

### Última sesión — 2026-05-26 (M27 v1.1 SHIP — soft launch + mensaje team)

**Sesión foco único M27.** Cierre formal de M27 Flat File Migrator v1.1
con audit Opus + fix infra venv 3.12 + validación E2E contra .xlsm originales
+ ship deployed live + mensaje a @channel del team.

**Commits del día:**
- `c10fa27` chore(infra): setup venv Python 3.12 + doc setup local (destraba P1 segfault 3.14)
- (commit final de cierre docs por crear en este reporte)

**Trabajo realizado:**

**Paso 1 — Audit code-reviewer Opus 4.7 sobre delta B6-b (f71bfdf~1..b9d9264):**
- Veredicto: APPROVE WITH CONCERNS
- 0 P1 bloqueantes
- 4 P2 documentadas como deuda blanda (no aplicadas): redundant-open, no-close, methods_count re-derivada (sin falso positivo confirmado), import-inline
- Sin regresión sobre deuda P3 heredada
- Decisión Lenin: no mitigar los P2 hoy, patrón "P1 se mitiga, P2/P3 se documenta" replicado (consistente con B5-a 19/05 y B5-b 20/05)

**Paso 2 — Setup venv Python 3.12 (destrabó P1):**
- Python 3.12.10 instalado vía `winget install Python.Python.3.12` (Python 3.14 sigue como default global, sin interferencia)
- venv `.venv` creado con `py -3.12 -m venv .venv`
- `pip install -r requirements.txt`: exit 0, todo prebuilt wheels (pandas 2.2.3 + openpyxl 3.1.5 + numpy 2.4.6 + pyarrow 24.0.0)
- Smoke pipeline B1→B5-c PASS 12/12 (335ms)
- Smoke wrapper B6-b-1 PASS (lo que segfaulteaba con `-1073741510` en 3.14)
- Documentado en `CLAUDE.md` del repo (sección "Setup local Python 3.12 obligatorio")
- `.gitignore` updated (+`.venv/` +`.claude/settings.local.json`)

**Paso 2.5 — Commit limpio:**
- `git add .gitignore CLAUDE.md` (selectivo, sin tocar analisis_cruzado.py del chat M29)
- Commit `c10fa27`: chore(infra): setup venv Python 3.12 + doc setup local (destraba P1 segfault 3.14)

**Paso 2.6 — Validación contra .xlsm originales:**
- Descubrimiento clave: `scripts/smoke_b6a_e2e_pipeline.py` ya targeteaba los .xlsm originales en L41-42 hardcoded, NO .xlsx convertidos como asumimos del daily 25/05
- Re-run explícito contra `ALRBB093_p_USA_2026__1_.xlsm` + `COAT__5_.xlsm`: PASS exit 0, byte-idéntico al run del Paso 2 salvo Δ1 byte de jitter del zip (nondeterminismo de timestamps internos del .xlsx output)
- P1 del 25/05 CERRADO al 100%: bug era exclusivamente Python 3.14 ABI, NO específico de .xlsm con macros como creíamos
- **Lección importante:** la "conversión .xlsm → .xlsx" nunca fue el fix real; era placebo. El fix real era venv 3.12.

**Paso 3 — Ship soft launch:**
- Validación visual del deploy live (capybaras-os.streamlit.app): PASS — Lenin confirmó toggle v1/v1.1 visible, auto-detect "Detectamos schemas distintos: OLD=fptcustom → NEW=ptd. Recomendamos Cross-schema." funcionando, output coat_migrated.xlsx descargado OK
- arranque-m27.md status: activa → shipped-monitoring (soak 14 días, deadline ~2026-06-09)
- Mensaje a @channel del team enviado por Slack con SOP completo embebido:
  * Crédito explícito a Marcos por la lógica del workflow
  * 8 pasos paso-a-paso (marketplace tab → uploaders → header rows → toggle modo → migrar)
  * Diagnostics explicados (unmapped_field, missing_required_in_new, deprecated_value)
  * Formatos validados oficialmente (.xlsm, .xlsx) vs los que NO testeamos (.xls/.tsv/.csv/.txt)
  * Oferta de acompañamiento primer caso

**Estado del proyecto al cierre:**

| Módulo | Status |
|---|---|
| M27 Flat File Migrator v1.1 | ✅ SHIPPED soft launch — 8/8 sub-bloques cerrados, audit Opus PASS, deployed live confirmado, mensaje @channel OK. Soak hasta ~2026-06-09. |
| M29 Proposal Studio | Chat paralelo activo. UI dispatcher B7 D1+D2 cerrados (25/05). D3+D4 + ship target jueves 28/05. |
| Pricing Dashboard (HTML #3 Marcos) | 🔴 0% sin arrancar. Bloqueado por persistencia cloud (decisión Freddy) + renumeración M30 en `_README.md` pendiente. |

**Deuda nueva descubierta hoy (M27 SHIP):**
- P3: Restringir file_uploader UI a xlsx/xlsm (formatos .xls/.tsv/.csv/.txt no validados visibles en UI — riesgo de uso ciego por team)
- P3: Consolidar 2 secciones Setup en CLAUDE.md del repo (1 vieja sin venv + 1 nueva con venv 3.12 conviven)
- P3: Decidir si `.claude/settings.local.json` se destrackea con `git rm --cached` (coordinado con chat M29 paralelo para evitar conflictos)

**Lecciones M27 SHIP:**
- **Pre-validar contadores Y paths en specs antes de aceptar.** El bug del 25/05 ("convertir .xlsm a .xlsx era workaround") era diagnóstico equivocado del placebo. CC corrigió leyendo el código real (L41-42 hardcoded apuntando ya a los .xlsm). Patrón a aplicar: cuando el vault dice "X es el workaround", verificar contra código antes de seguir asumiéndolo.
- **venv pythonización ahorra horas.** El Setup CLAUDE.md previene que este P1 vuelva a aparecer. ROI altísimo: 5 min de winget install + 2 min de venv = 100% confiabilidad future-proof.
- **Soft launch > Formal launch para módulos single-tenant interno:** mantiene el prompt activo durante soak sin overhead de archivar/desarchivar. Replica patrón M28.
- **4to hit audit Opus sin generar P1 reales** — patrón super estable, mantener pre-ship como ritual no negociable.
- **Crédito a Marcos por la lógica del workflow** (no por código) — patrón replicable para futuras herramientas que automatizan know-how de AMs. Buen team-building + claridad de roles.

**Próxima sesión M27:** trigger-based. Sin bloque obligatorio. Triggers documentados en arranque-m27.md sección "Próxima sesión propuesta".

Ver [[2026-05-26]] [[arranque-m27]] [[code-reviewer]]

---

### Última sesión — 2026-05-25 (consolidador 3 frentes paralelos)

**Sesión multi-frente — Setex Hot Sale + M27 v1.1 cierre + M29 dispatcher B7.**
3 chats paralelos consolidados. 11 commits locales listos para push al cierre.

**Commits representativos del día:**
- `093e686` feat(M29): B7 UI dispatcher D2 — skeleton + preview (+168 LOC en
  `proposal_studio.py`, helper `_render_b7_importer_section`)
- `2d8101e` docs(setex): cierre Hot Sale push táctico (daily + arranque-setex +
  brand note)
- `da59dfb` docs(M27): cierre B6-b 8/8 (daily + arranque-m27)
- `9d0274a` docs(m29): cierre chat #1/4 (daily + arranque-m29)

**Incidente cross-frente del día (resuelto, cero pérdida funcional):**
`64e3d6f → 252f286 → b0a234c`. El contenido de `252f286` resultó ser rollback
intencional del chat M27. `b0a234c` restauró sus B6-b-2 + B6-b-3. Validación
con CC del chat M27 confirmó alcance correcto.

---

**Frente 1 — Setex Hot Sale push táctico (Tati avisó 10:39):**

- 6 bulks ejecutados 100% Success (UUIDs registrados en daily + brand note).
- KPIs cuenta pre-bulks: **ACoS 18.5% · ROAS 5.41× · 448 orders/30d · CVR 11.45%**
  (mejora vs 22/05: ACoS -0.9pp, ROAS +0.26×, orders +55, CVR +1pp).
- 86 → 78 camps ENABLED post-cierre.
- Push agresivo Thin family aprovechando deals activos (Standard 1mm + Thick +
  Ultra Thin).
- **Decisión opción B B09F7P8GBZ (stock 6u, trip wire 3u activo)** — mantener
  push controlado, monitor lunes.
- Corrección diagnóstico listing EN B081GB8F89: re-clasificado como **baja
  prioridad** (la hipótesis de funnel break EN no se sostiene con SQP fresco).
- Mensaje Tati posteado: flag B09F7P8GBZ + nuevos flags **B0F63LTD92** y
  **B0C7WPFVGV** (restocked pero 0 sales 30d — perdieron rank por OOS, hay que
  reactivar).

---

**Frente 2 — M27 Flat File Migrator v1.1 — 100% funcional:**

- **8/8 sub-bloques B6-b cerrados** (B6-b-1 a B6-b-4). Llegamos al 100% v1.1.
- Validado E2E en Streamlit con par real Gamboa `coat.xlsx` (fptcustom OLD →
  PTD NEW).
- 5 commits de código + 1 commit docs.
- **Decisión próxima sesión M27 (3 caminos):**
  - **A** — audit code-reviewer Opus B6-b-5 (deuda P3, no bloqueante)
  - **B** — fix infra venv Python 3.12 (resolver bug P1 del .xlsm)
  - **C** — ship formal v1.1 (mensaje Marcos + closing loop)
  - **Recomendación:** priorizar **B** (fix infra venv Python 3.12, 45-60 min)
    porque destraba `.xlsm` y habilita smoke CLI completo. A y C pueden esperar.
- **Bug P1 nuevo (alcance acotado):** entorno Python 3.14 + openpyxl 3.1.5 +
  archivos `.xlsm` produce crash silencioso. **NO afecta `.xlsx`** — el smoke
  CLI `scripts/smoke_b6a_e2e_pipeline.py` pasó OK con `.xlsx` convertido. Lección
  para vault: el smoke E2E que bypassa `_parse_workbook` no detecta bugs de UI
  Streamlit.
- Audit Opus B6-b-5 **diferido como deuda P3** (módulo es estable y se usa solo
  internamente por Marcos).

---

**Frente 3 — M29 Proposal Studio — UI dispatcher B7 (chat #1/4):**

- **D1 (discovery) + D2 (skeleton + preview) cerrados.**
- `+168 LOC` en `modules/pages/proposal_studio.py` (helper privado
  `_render_b7_importer_section`).
- Smoke E2E con fixture `b7_sample_v3v4.html`: **PASS — Blocks=2 / Warnings=6 /
  Errors=0**.
- **D3 + D4 pendientes martes 26/05** (camino al ship jueves 28/05).
- **Refactor DataDive parsers → `modules/parsers/` + mapper V3** agendado para
  martes post-D4.
- **Ship target M29: jueves 28/05.**

---

**Contador bugs M4 cross-cliente actualizado: 5 → 8 (+3 nuevos Setex):**

- ⊕ `ppc_insights_asin` corrupto (output con campos vacíos en filas válidas)
- ⊕ `plan_accion_bulk` falsos positivos en clasificación ESCALAR / DEFENDER / NaN
- ⊕ Sin mapping Campaign / AdGroup / MaxBid en algunos outputs
- Bugs preexistentes: 5 ya documentados en sesiones previas (Dermaglos 08/05
  + Setex 22/05). Detalle consolidado en doc entregable Ramiro.
- **Entregable Ramiro pendiente** — consolidar los 8 en un doc único para el
  patch coordinado.

---

**Lecciones operativas multi-frente (nuevas):**

- `git add modules/` es tan peligroso como `git add .` cuando hay subarchivos
  modificados por otros chats paralelos. Siempre `git add <path-específico>`
  cuando hay paralelismo activo.
- **IDE cerrado del lado del chat que NO edita** un archivo compartido (evita
  save conflicts entre VS Code y CC).
- **Pre-validar contadores numéricos en specs antes de aceptar:** CC validó que
  `_LABEL_ALIASES` real son 3 entradas, no 40 como decía el spec heredado del
  daily 18/05. Patrón: nunca confiar en números de notas viejas sin
  `Select-String -Count` actual.
- **Smoke E2E que bypassa `_parse_workbook` no detecta bugs de UI Streamlit.**
  Caso concreto: el smoke CLI M27 pasó OK con `.xlsx` pero el bug P1 del `.xlsm`
  solo aparece vía UI completa.
- **Bug "edits fantasma" en CC (1er hit):** CC reporta éxito de edit + smoke
  manual PASS, pero el archivo en disco queda sin cambios. Pattern recovery
  validado: verificación triple post-edit (`Select-String` + `git status` +
  `git diff --stat`). Hermano nominal del bug "ppc-module-builder hallucination"
  (4 hits acumulados).

---

**Próximo milestone: ship M29 jueves 28/05.**
**Reunión Ramiro próxima viernes 29/05** (corrección del arranque previo que
decía "30/05" — esa fecha cae sábado).

Ver: [[2026-05-25]] · [[setex]] · [[M27-flat-file-migrator]] · [[agency-os]] ·
[[arranque-setex]] · [[arranque-m27]] · [[arranque-m29]]

---

### Última sesión — 2026-05-22 (M29 — B7 Importer v1 completo)

**Sesión partida 21+22/05** — código del 21/05 sin commit por salida imprevista;
consolidación completa el 22/05.

**Commits del día (4):**
- `8e13409` feat(M29): B7 Importer v1 - extractor puro HTML → BlockDraft
- `c714123` feat(M29): B7 Importer v1 - merge_blocks layer (capa 2)
- `fc6fc88` fix(M29): duplicate_module_id ERROR → WARNING (fix D6)
- `02303bd` test(M29): cobertura pytest formal (4 gaps P2)

**Archivos:** modules/sales/__init__.py + modules/sales/b7_importer.py
(691 LOC) + tests/fixtures/b7_sample_*.html (2) + tests/test_b7_importer.py
(291 LOC).

**Estado al cierre:**
- ✅ B7 Importer v1 extractor + merge + fix D6 + 10 tests pytest verde
- ✅ API pública: extract_blocks + merge_blocks + dataclasses exports
- ⏸️ UI dispatcher pendiente lunes 25/05 (depende D2 informal)
- ⏸️ Capa save pendiente (no es scope B7)

**Reunión Ramiro 22/05 15:00:**
- Acuerdos de dirección (no lock contractual):
  - V3 → lógica DataDive como source (refactor parser Research)
  - V5 → buscar forma de traer imágenes automatizadas (opciones abiertas)
  - Contrato B7 v1.0 sigue draft
- Próxima sync: viernes 30/05 con M29 shippeado el día anterior

**Plan al jueves 28/05:**
- Lunes: UI dispatcher B7 (V3+V4)
- Martes: refactor DataDive parsers + mapper V3
- Miércoles: editor manual V5 + testing
- Jueves: E2E + ship M29

**Deuda activa M29:**
- P2 UI dispatcher (depende D2)
- P3 Refactor genérico Class B (4 refs V3-V6)
- P3 Cleanup 44 versiones proposal 6861bbce-...
- P3 Schema items_schema {} vs null (D6 catalog)
- P3 Short-circuit en _extract_block_data (~3 LOC)
- Imágenes V5 automáticas (post-jueves)

Ver: [[2026-05-22]] [[2026-05-22-ramiro-b7-sync]]

---

### Última sesión — 2026-05-20 (M29 6 CORE editores cerrados + M27 v1.1 B5-b cerrado + LTD bulks + SPP submit)

**M29 Proposal Studio — sesión 2026-05-20:**

- Commits del día (2):
  - `293ae74` feat(M29): B3-f V5_listing_comparison_competitor readonly + find-or-create inject script
  - `6cf581a` feat(M29): B3-g V6_growth_plan_phases readonly + find-or-create inject script
- Archivos modificados:
  - `modules/pages/proposal_studio.py` +305 LOC (V5 helpers + V6 helpers + 2 elif dispatcher)
  - `scripts/inject_v5_demo.py` (nuevo, 116 LOC, find-or-create idempotente)
  - `scripts/inject_v6_demo.py` (nuevo, 109 LOC, find-or-create idempotente)
- Propuesta `_DEMO_AgencyOS` (01fbf5c2): v10 → v12, 19 → 20 blocks, V1-V6 contiguos

**Estado M29 al cierre:**

- ✅ **6 CORE editores cerrados:** V1+V2 Plan D + V3+V4+V5+V6 readonly Class B
- Pattern Class B replicado 4 veces (V3, V4, V5, V6) → umbral N=3 superado
- 42/42 tests pasan, sin regresión
- Smoke runtime visual OK (V5 + V6 verificados en `_DEMO_AgencyOS`)

**Deuda activa M29 (actualización):**

- **P2 nueva** — Template launch desactualizado vs catálogo: `_DEMO_AgencyOS` tiene 20 blocks vs 35 en catálogo. Faltan V7-V16 + V23-V29. Find-or-create cubre por ahora. Decisión arquitectónica pendiente post-Ramiro.
- **P3 nueva** — Refactor genérico Class B: con 4 referencias reales (V3+V4+V5+V6) corresponde refactor a `_render_class_b_readonly(... item_renderer_fn)`. Reduce ~400 LOC duplicación a ~80. Sesión dedicada.
- **P3 nueva** — Smoke runtime ANTES del commit: hoy commiteamos V5 sin smoke previo, debug post-commit por confusión de propuesta (Marca LATAM Premium vs _DEMO_AgencyOS). Reforzar workflow.
- **P3 nueva** — Git ignore semantics aprendido: whitelist quirúrgico bajo `notes/*` requiere patrón "open-then-narrow" de 3 líneas (`!notes/sub/` + `notes/sub/*` + `!notes/sub/archivo`). Detectado por CC en cierre 20/05 cuando whitelist mono-línea falló silenciosa.
- **P2 — Whitelist notes/sales/ resuelto parcial**: agregada whitelist quirúrgica solo del contrato B7 v1.0. Otros archivos sales/ siguen ignored.

**Próxima sesión M29:** decisión arquitectónica V6 post-Ramiro
(skill Capybaras manual vs skill audit Ramiro). Si manual → refactor
V6 a Plan D editor en sesión dedicada. Discovery: revisar shape de
V6 emisión en función del output esperado de la skill.

---

**M27 Flat File Migrator v1.1 — sesión 2026-05-20 (B5-b cerrado con audit code-reviewer):**

- 3 commits sobre `modules/pages/flat_file_migrator.py` (+205 LOC):
  - `fc31af8` — checkpoint pre-B5-b
  - `dcfdc9d` — B5-b `_extract_template_rows` + initial Required validator (+180 LOC)
  - `0f82d90` — fix mitigaciones post-audit B5-b F1+F5 (+25 LOC)
- Discovery D3 ejecutado con script ad-hoc + 2 archivos reales Gamboa/coat (OLD fptcustom + NEW PTD). Reveló asimetría de valores Required entre schemas: OLD usa Optional/Required/Preferred; PTD agrega "Conditionally Required" (78 fields, 35% del schema PTD) y "Recommended".
- Decisión D3 cerrada con data real: trigger Required = igualdad exacta `== "required"` lowercased. "Conditionally Required" queda como deuda futura (no scope B5-b initial validator).
- Hallazgo crítico mid-implementación: row 6 del PTD (`['ABC123', 'SHIRT', '(Default) Create or Replace', ...]`) y banner emoji row 7 → 5 filtros en `_extract_template_rows` en vez de los 4 originalmente planeados.
- Primera versión D4 con `_AMAZON_EXAMPLE_TYPES` causó regresión catastrófica (7/7 OLD rows filtradas porque `_AMAZON_EXAMPLE_TYPES` contiene "COAT" y coincide con `feed_product_type=coat` legítimo). Fix correcto: solo señal `"(Default)"` (valid value contractual del dropdown `::record_action`).
- Audit code-reviewer Opus 4.7 sobre B5-b (3er hit operativo): APPROVE WITH CONCERNS, 0 bugs activos, 4 P1 + 4 P2 + 4 P3. Mitigaciones F1 (P1, fail-silent si field_ids vacío) + F5 (P2, docstring tipos no-str) aplicadas en `0f82d90`.

**Estado del proyecto al cierre:**

| Módulo | Status |
|---|---|
| M27 v1.1 | 6/8 sub-bloques cerrados (B1+B2+B3+B4a+B4b+B5-a+B5-b). B5-c + B6 pendientes. Progreso 87.5%. |
| M29 Proposal Studio | 6/6 CORE editores cerrados. Refactor genérico Class B habilitado (4 refs). |
| Pricing Dashboard (HTML #3 de Marcos) | 🔴 0% sin arrancar. Bloqueado por persistencia cloud + slot M29 tomado por Proposal Studio. |

**Deuda activa actualizada (M27):**

Nueva del audit B5-b (no aplicadas, documentadas):
- **F2 (P1)**: `data_start_1idx > len(all_rows)` no distingue "template vacío legítimo" de error de offset.
- **F3 (P1)**: Field IDs duplicados entre cols → última col gana sin warning. Sin saving grace si Amazon mete dups.
- **F4 (P1)**: Trayectoria fallback emite warning informativo + procede normal — Required validation puede tener desalineaciones silenciosas.
- **F6 (P2)**: Substring `"(Default)"` en cells legítimas (improbable). Escalar a D5 si aparece.
- **F7 (P2)**: `ord >= 0x2600` cubre CJK/Dingbats. Mitigado por AND `rest_empty`.
- **F8 (P2)**: Umbral `<3` cells filtra updates parciales legítimos si scope se expande.
- **F9-F12 (P3)**: housekeeping cosmético (naming, docstring "Raises", comentarios, Required ausentes del template no warneados).

Nueva descubierta no-audit:
- **P2 — openpyxl hang con `read_only=False` sobre .xlsm Amazon**: discovery se cuelga >2min con `read_only=False`, completa <2s con `read_only=True`. Causa probable: carga de data_validations + named ranges del .xlsm. Workaround documentado en docstring del helper.
- **P2 — Asimetría DD vs Template OLD**: fptcustom Template tiene 227 cols con field_id pero DD documenta solo 164. Los 63 extra son cols históricas sin entry en DD. Comportamiento del helper es correcto (los fids sin DD lookup no triggean Required validation). Documentable como contexto para B5-c.

Heredada B5-a y previas (sigue activa):
- B5-a-bis (P3 #7): colisión naming `_looks_like_field_id` vs `_looks_like_field_ids`.
- B5-a P1 #1, P1 #2: mitigadas por cross-validation, sin caso real aún.
- CLAUDE.md performance flag (>40k chars).
- Deuda B3 heredada (Other Image URL numbering + group name old tooltip 252 chars).

**Próxima sesión M27:** B5-c row-level value translator. Helper que compone B5-b output + B4b `_build_value_map` para traducir enum values OLD→NEW row-by-row, emitiendo warnings por values deprecated/sin mapping. Discovery previo recomendado: script ad-hoc que listee qué cols del template OLD contienen enum values reales (no schema-defined sino contenido del cliente Gamboa).

Detalle completo en `notes/daily/2026-05-20.md` y `notes/brands/agency-os.md` sección 2026-05-20.

---

### Última sesión — 2026-05-19 (M27 v1.1 B4 cerrado + B5-a con audit code-reviewer)

**Trabajo realizado:**

**M27 Flat File Migrator v1.1 cross-schema:**
- 5 commits sobre `modules/pages/flat_file_migrator.py` (+365 LOC):
  - 9c85e06 — B4a `_parse_valid_values` (schema-agnostic, +39 LOC)
  - c11faf0 — B4b `_ENUM_VALUE_MAP` + `_build_value_map` + `_DEPRECATED_OLD_ENUMS` (+130 LOC)
  - 07e79fb — B5-a `_locate_template_headers` con D1+fallback (+191 LOC)
  - 64f25db — fix mitigaciones post-audit B5-a (+6/-1 LOC)
  - 7aac33c — checkpoint
- Decisión `_ENUM_VALUE_MAP` scope conservador (A1+/B2/C1): cubre 3 enums críticos con mapping limpio, ISBN/GCID/Relationship Type/Variation Theme quedan como deprecated/schema gaps para revisión manual en B5.
- Decisión D1+fallback en header locator: auto-detección row-by-row con cross-validation B2 + safety net hardcoded por schema. Justificado por asimetría OLD/NEW (3 vs 5 header rows).
- Audit code-reviewer Opus 4.7 sobre B5-a: APPROVE WITH CONCERNS, 0 bugs activos, mitigaciones P2 #4 + P1 #3 aplicadas, P1 #1/P1 #2/P3 #7 documentadas como deuda blanda.

**Estado del proyecto al cierre:**

| Módulo | Status |
|---|---|
| M27 v1.1 | 5/8 sub-bloques cerrados (B1+B2+B3+B4a+B4b+B5-a). B5-b/B5-c + B6 pendientes. Progreso 75%. |
| M29 Proposal Studio | Chat paralelo activo. Sin cambios desde este chat (commits propios). |
| Pricing Dashboard (HTML #3 de Marcos) | 🔴 0% sin arrancar. Bloqueado por persistencia cloud (Freddy) + slot M29 tomado por Proposal Studio. Renumeración M30 pendiente en `_README.md`. |

**Deuda activa actualizada (M27):**

- **B5-a-bis (P3 #7)**: colisión naming `_looks_like_field_id` (singular B5-a) vs `_looks_like_field_ids` (plural porting legacy L910). Refactor estético, prioridad baja.
- **B5-a P1 #1**: falsos positivos en `_looks_like_field_id` con display labels exóticos. Mitigado por B2 cross-validation. Refinar si aparece caso real.
- **B5-a P1 #2**: cross-validation frágil ante sufijos PTD desalineados. Mitigación futura: aplicar `_normalize_field_id` antes de comparar.
- **CLAUDE.md performance flag** — CC reportó >40k chars, impact performance. Sesión de limpieza vault deferrable.
- **Deuda B3 heredada** (sigue pendiente): numbering issue `Other Image URL1..8` vs `Other Image URL + locators 1..8`, group name old con tooltip 252 chars.

**Próxima sesión M27:** B5-b row extractor + initial validator. Helper que toma `wb` + headers (de B5-a) → list de dicts `{field_id: value}` por data row + warnings por Required vacíos. ~80-120 LOC esperadas. Sin discovery previo necesario (B5-a + B2 ya cubren todo el contexto).

**Pricing Dashboard (recordatorio):** 0% sin arrancar, 10 días sin respuesta de Freddy sobre Supabase Pro $25/mes (mensaje 09/05). Renumeración M30 pendiente en `.claude/porting-sources/_README.md` (sigue diciendo "M29 = Pricing Dashboard" desactualizado desde pivot 08/05).

Detalle completo en `notes/daily/2026-05-19.md` y `notes/brands/agency-os.md` sección 2026-05-19.

---

### Última sesión — 2026-05-19 (M29 cierre PM)

**M29 cerrado al fin de jornada:**
- V1+V2 editores Plan D ✅
- V3+V4 readonly + banner B7 ✅
- Schema canónico extendido con `items_schema` formal (commit `757292d`)
- Propuesta demo renombrada a `_DEMO_AgencyOS` (id `01fbf5c2`)
- Fix B3-d-bis None→'' aplicado en celdas readonly
- Contrato Importer B7 v1.0 drafteado en `notes/sales/contrato-importer-b7-v1.md`

**Commits M29 (5):**
- `2f436a0` feat: B3-e V4 readonly + banner B7
- `2c2a36d` fix: B3-d-bis None→'' pre-DataFrame
- `64cf644` docs: inject scripts apuntan a _DEMO_AgencyOS
- `757292d` feat: items_schema formal V3+V4 + convención proposal-v1

**M27 chat paralelo:** cerró v1.1 B4a + B4b + B5-a + audit (detalle arriba en sub-sección M27). Sin colisiones — archivos distintos.

**Próxima sesión:**
1. B3-f V5_competitor_comparison (primera Class A real post-V1/V2)
2. Briefing reunión Ramiro 22/05 — debe estar listo antes del jueves 21
3. Validar fix B3-d-bis en renderers readonly futuros

**Bloqueantes:** ninguno. Todo verde para arrancar B3-f cuando Lenin
tenga sesión dedicada (~2-3h).

**Reuniones agendadas:** Ramiro viernes 22/05 15:00 — lock contrato B7 v1.0.

---

## Sesión anterior — 2026-05-12 (día completo)

**Foco principal**: M29 Proposal Studio Sesión 2/6 — UI completa (Listado + Wizard 3 pasos).

**Output principal**:
- `modules/pages/proposal_studio.py` (~923 LOC, 25 funciones) — módulo nuevo Sales Director
- 3 edits quirúrgicos: import + router + sidebar SALES DIRECTOR en `app.py`
- 1 edit en `core/constants.py`: entry "📋 Proposal Studio" en `_PAGES` (total 28 módulos)
- Fix bug Duplicar (commit 28a6d69) — hardening post-S2
- 3 propuestas demo persistidas en `data/sales/proposals/`

**Commits del día**: `aa2d873` (código S2) + `5a1a575` (docs S2) + `28a6d69` (fix Duplicar). Todos en main, pusheados a origin/main.

**Sub-bloques ejecutados** (5 validables independientemente):
- B1 skeleton + B2 wire al Agency OS + B3 Listado funcional + B4a state machine + B4b paso 1 form + B4c-i paso 2 preview + B4c-ii paso 3 save

**Smoke test E2E final**: Crear propuesta Gamboa launch ES → 18 blocks instanciados → save persistido en `data/sales/proposals/<uuid>__v1.json` → banner verde + card poblada en Listado. Duplicar funcional post-fix. Abrir muestra placeholder S3.

**Hardening adicional (mismo día, post-cierre formal)**:
- Bug Duplicar detectado durante testing manual + fix aplicado (FK consistency en blocks)
- Limpieza de dataset de testing y creación de 3 propuestas demo (Marca LATAM Premium / US Wellness Brand / Tech Accessories Co) cubriendo 3 arquetipos para futuros screenshots

**Comunicación pública**:
- Primer update del módulo a toda la agencia mandado por Slack (CEO + directores + ops + ventas + diseño)
- 6 iteraciones del mensaje hasta versión final
- Decisiones: estructura por fases con propósito de negocio (no técnico), objetivo cuantificable (10 min vs 2-4h), distinción HTML interactivo vs PDF, feedback async
- **Compromiso público de timeline**: fases 3+4 esta semana, fases 5+6 próxima
- 2 screenshots adjuntos: Listado poblado + Landing wizard con 4 arquetipos

**Decisiones cerradas**:
- Cliente como text_input libre (NO selectbox de clientes existentes — M29 es para leads/prospects)
- Paso 2 readonly en S2, edición de blocks va a S3
- Soft delete por default para Archivar
- Cache por signature tuple del paso 1 preserva block ids entre navegación
- Banner verde post-save en Listado vía flag `ps_just_saved` (Streamlit no permite cambiar tab programáticamente)
- Patrón de generación de IDs padre: ANTES del save (no después) cuando hay validadores estrictos de FK

**Sin invocación de sub-agentes**: el `ppc-module-builder` con model fix pendiente de validación operacional queda para sesión más chica. ~900 LOC de Python sin retries.

**Pendientes Sesión 3 (esta semana)**:
- Vista detalle de propuesta (botón Abrir funcional)
- Edición funcional de los 6 CORE Variables (V1-V6) con form dinámico desde schema
- Aprovechar refactor del form para cerrar deuda #9 (autocomplete="off")

**Pendientes Sesión 4-6 (esta semana / próxima)**:
- S4 (esta semana): 23 placeholders Tier 2-3 con toggle "Marcar como interesado"
- S5 (próxima semana): Renderer HTML interactivo (templates Jinja2)
- S6 (próxima semana): Playwright PDF + polish + smoke test E2E + update READMEs

**Riesgos a vigilar**: el compromiso público de timeline crea presión sobre las próximas sesiones. Si S3 se desborda, comunicar al canal Slack ANTES del 17-18 de mayo (no después del deadline). Status check informal mid-week recomendado.

Detalle completo en [[daily/2026-05-12]] y [[brands/agency-os]] (sección 2026-05-12).

---

## Última sesión — 2026-05-12 (Setex)

**Instrucciones Tati**: recuperar badge B081GB8F89 + focus PPC familia Thin (B0F3PSP82K, 1,839u stock).

**Ejecutado**: 9 bulks, 275 cambios, 100% Success en Amazon Ads Console.
- #1 RevivirFantasmas (43 filas, UUID `3624deb3-e466-4fe2-864a-519db8693ab8`)
- #2 PausarB086H3TZ6B (19 filas, UUID `afde8719-00dd-476f-9c48-364bd625bf64`) — pausa preventiva 19 Product Ads (1u stock, child del badge)
- #3 ActivarUltraThinEXACTs (6 filas, UUID `4ee7ccd1-28f5-4311-a1eb-170b65acb914`)
- #4 EscalarThin (19 filas, UUID `1cfa06e7-0db9-42fa-b4a0-c2e22cb19766`) — incluye DEFENSIVE OWN Thin PDPs (ROAS 211× → bid +100%)
- #5 FixAntideslizante (1 fila, UUID `f1062364-670e-421a-8889-d63db0646803`) — bug fix bid $21.80 → $7.50
- #6 NegativosCross (154 filas, UUID `4e33ffb2-8a76-4994-b0df-0ddf0af921db`) — 11 terms × 14-16 camps anti-canibalización
- #7 BorderlineOptimize (5 filas, UUID `71d75edb-37d7-4748-86f6-409f2795e5cd`)
- #8 PausasYArchivado (3 filas, UUID `99ab9b63-2a4e-4cea-9b53-3b7c0e34b913`) — archivado campaña typo "almoadillas"
- #9 Crear5EXACTThin (25 filas, UUID `39f88428-3780-451e-8d1d-2357a5903bb7`) — 5 EXACT nuevas SKU XG9G515 (B08PZF22R1, 1317u stock) portfolio 06mm Nose Pads (ID 197371337016358), +$145/d

**Impacto esperado 4 semanas**: ACoS cuenta 19.5% → 16-17%, ROAS 5.12× → 5.8-6.0×, Thin sales $12k → $22-25k MXN/mes, recuperación waste +$1,500/mes.

**Hallazgos críticos**:
- Bid set `antideslizante para lentes` $21.80 (no $9.41 CPC efectivo) → ACoS 73.6% — bug oculto.
- B086H3TZ6B (1u) estaba como advertised product en 19 ad groups Setex 1mm — riesgo perder badge.
- Brand surge post-badge confirmado: `setex` IS 67.9%, `setex nosepads`/`setex gecko grip` PS 100%.
- Canibalización 9 query winners → AUTOs robaban 25-30% del tráfico a EXACT dedicadas.
- Leak listing inglés B081GB8F89: SQP muestra PS 0% en queries anglo con CS 60% (`nose pads for glasses`, `nose pads`).

**Urgencias Tati pendientes (Slack enviado 12/05)**:
1. Restock B086H3TZ6B (1u, child badge, 19 ads pausados)
2. Restock B0F63LTD92 (1u, Ear Hook, -3u vs 4u del 29/04)
3. ETA Temple Tips (B0C7WPFVGV + B0B94KBY8H, OOS desde 18-23 abril)
4. Audit listing EN B081GB8F89 (PS 0% queries anglo)

**Próximas evaluaciones**: 15/05 (día 3 impressions), 19/05 (día 7 performance), 26/05 (día 14 review).

**Sin invocación de sub-agentes**: ejecución manual con análisis Lenin + Claude chat. 275 cambios en bulks XLSX generados localmente, validados contra BulkSheetExport 5,749 filas antes de subir.

Detalle completo en [[daily/2026-05-12]] (sección "Sesión Setex 12/05/2026") y [[setex]] (sección "2026-05-12").

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
| Dermaglos | Amazon USA 🇺🇸 | 58.9% (objetivo 45%, 360° 19/06) | 360 completo + 5 bulks pre-Prime ejecutados (Success) — listo para Prime 23–30/06 · AM Edu · próx eval 01/07 (STR post-Prime) | Facial Set OOS · unfulfillable recovery · listing fix micellar/cleanser | [[DERMAGLOS]] · [[DERMAGLOS_DATA]] · [[atom11-rules]] |
| Mott & Bow | Amazon US 🇺🇸 | 10.6% TW (26 abr-2 may, sano) | Full-Funnel Women — Fase 2 en espera del cliente (SBV White Tee + SP Exact Premium Cotton) · transición de owner a Cuki 2026-05-11 | Video creativo + Brand Store Women — espera respuesta cliente para lanzar Fase 2 | [[MB]] |
| Love To Dream | Amazon MX 🇲🇽 | 15.4% paid · TACoS 10.8% ✅ target | Post-bulks 02/06 — recovery $6K/mes · escalado +$810/d · próx: monitoreo 48-72h + fix M4 viernes | B005ULUZIQ BB 83% (flag 16/04) · 5 INACTIVE_BLOCKED (B0BKB7CJFQ 23u recuperable) · B09MG1J3LC missing del catálogo | [[LTD]] |
| Setex Technologies | Amazon MX 🇲🇽 | 20.5% (↓ proyectado 16-17% post-bulks 12/05) | 🏆 Best Seller badge B081GB8F89 (lock-in) + push estratégico familia Thin (B0F3PSP82K, 1839u) — 5 EXACT nuevas SKU XG9G515 +$145/d · 154 negativos cross-camp anti-canibalización · pausa preventiva B086H3TZ6B (1u, 19 ads) · **Prime Day 23–30/06 (−20%) armado 17/06** (Bulk A conservación Negro + Bulk B ceilings, Tati OK $1.3–1.4K/d) | B08C2T72ND standby restock (modo conservación, se agota ~arranque evento) · Componente C (bids+ToS) bloqueado por inventario (runway B081GB8F89 + stock B08SNRCL63) · clearance Thin overstock 1.280u B08PZF22R1 sin vehículo + falta OK Tati · 4 urgencias Tati Slack 12/05: B086H3TZ6B 1u · B0F63LTD92 1u · Temple Tips OOS · audit listing EN B081GB8F89 (PS 0% queries anglo) | [[setex]] · [[PENDIENTES_RESTOCK]] |
| 360 Essentials | Amazon USA 🇺🇸 | 23.0% (✅ target 35%) | SBV FreedomPlus branded + test incrementalidad + relanzar SD bid $1 | Video creativo FreedomPlus para SBV (3 camps) | [[360ESSENTIALS]] |
| Pura Vida Moringa | Amazon MX 🇲🇽 | 45.5% marzo (proyectado 48-52% post-opt) | Bajar ACoS a 40-45% · consolidar rank orgánico top 2-5 | Sin crédito Atom11 — optimización manual | [[Puravidamoringa]] |

**Patrón cross-client**: todos los USA con cuenta madura (Dermaglos, M&B, 360 Essentials) corrieron Atom11 v2026.2 en marzo. Los MX (LTD, Setex, PVM) manuales — LTD con 38 rules vía Cowork, Setex sin Atom11, PVM sin crédito.

---

## LTD (Love To Dream) — MX

- **AM**: Agustín | **Escalación**: Adam (Sales Director), Aaron (compliance)
- **Estado**: saludable post 360° 08/06 — Sales +12.4%, TACoS 9.4% (under target Junio 10-12%). 3 EXACT nuevas live 09/06.
- **Última sesión**: 2026-06-17 — meeting dueño (caída = PRECIO, no PPC) + bulk F0 (3 pausas, bid-down, 6 negative PT) + setup Prime Day automatizado ([[daily/2026-06-17]] · [[brands/ltd/LTD]]). Previa: 2026-06-08 análisis 360° + 5 bulks ([[daily/2026-06-08]])
- **Prime Day 23–30/06 (auto-revert 1/jul)**: campaña Grey `SU-PUSH | MX | SP | KW | GREY | PRIMEDAY` (B0081GIZ52 + B0081GIYTE) + Budget Rules UI (PT Category +33% ~$698/d · Broad +30% $455/d). Grey = B0081GIZ52 pendiente confirmación Agustín
- **Próxima acción**: confirmar Grey + elegibilidad 2 product ads con Agustín · ETA restock B09MG1PM6L (~18d runway → gatilla pull-back, bulk listo) · monitor evento · auditoría tog 0.5 (35 KWs) con fix M4
- **Heroes count**: 35 (actualizado de 10, ver brands/ltd/LTD.md sección 🦸 Heroes oficiales canónico)
- **Stock alerts** (a Agustín): B09MG1PM6L (hero #2, runway 3.7 sem, 0 inbound) · B0DJSF2N6P (6.2 sem) · B09S14W4SS (1.5 sem). Inbound 0 cuenta completa.
- **Bloqueos pendientes**:
  - B005ULUZIQ BuyBox 86% subiendo — competidor -20% desapareció, monitor 7-14d antes de reactivar ad groups
  - Patrón competidor -20% en 7 ASINs (gray market/MAP) — escalación Adam (no PPC)
  - B0BKB7CJFQ 23u UNFULFILLABLE + Inactive desde 01/06 — revisión bloqueo + recovery
  - B09MG1J3LC missing del catálogo (esperando confirmación Agustín)

## API Integration — SPP Case · 20/05/2026
**Status**: SUBMITTED · esperando review Amazon
**Owner**: Freddy (contact) + Lenin (technical)
**Detalles**: `notes/api-integration/spp-case/README.md`
- 12 non-Restricted roles solicitados (NO Restricted)
- 8 use cases descritos en submission; 4 bullets de amendment listos en
  `amendment-bullets.md` para respuesta reactiva si Amazon pregunta
- Próxima acción: monitoring freddy@capybaras.agency
- IRP formal vigente: `notes/sops/incident-response-plan.md`

---

## Estado Atom11 por cliente

| Cliente | Rules activas | Versión | Coverage campañas | Próxima evaluación |
|---|---|---|---|---|
| Dermaglos | 83 | v2026.2 AGRESIVO | 117/123 (95%) | 11/04 realizada, 14 días desde confirmación equipo |
| 360 Essentials | 49 | v2026.2 | 110/131 + 23★ pendientes | 16/04 (primera evaluación) |
| LTD | 38 | custom (via Cowork) | 99 camps en 6 grupos | pendiente schedule oficial |
| M&B | TBD | activa (siempre tuvo) | TBD | TBD primer touchpoint Cuki (owner saliente Lenin, entrante Cuki 2026-05-11) |
| Setex | — | sin Atom11 | 92 camps ENABLED | pendiente gestión con Guille |
| Pura Vida Moringa | — | sin Atom11 (sin crédito) | 14 camps manual | 16/04 evaluación manual |

**Corrección 2026-05-04:** M&B figuraba históricamente como "sin Atom11 — optimización manual" pero los exports analizados en sesión 2026-05-04 prueban que sí tiene reporting Atom11. Coverage agencia ahora: **5/6 clientes con Atom11** (faltan Setex y PVM). Coverage exacto, rules activas y versión bajo Atom11 — TBD próxima sesión M&B con datos del cliente.

---

## Proyectos en curso — Agency OS (PPC Manager)

Todos commiteados a `main`, pendientes de push.

- **M29 Proposal Studio (Sales Director module)** — branch `feature/m29-datadive-mapper`
  LISTA PARA SHIP. 28/05 chat paralelo cerró: tests E2E AppTest del flujo UI
  (deuda "edits fantasma" del 25/05 tapada en el path apply), propuesta de shape
  V5 redactada para sync con Ramiro 30/05, SOP M29 v1.0 completo escrito (módulo
  + 2 vías de import + editores + gotchas + tests + deuda). Suite 98/98 verde.
  Convergencia de branches confirmada: `feature/m29-datadive-mapper` contiene todo
  el frente (B7 D2-D4 + DataDive E1-E5 + lo de hoy); `origin/feature/m29-b7-d3-d4`
  es redundante y queda histórica.

  Commits nuevos del 28/05 (3, fast-forward limpio sobre origin previo):
  - `78ba2eb`  test(M29): E2E AppTest flujo UI - B7 importer apply + DataDive V3
  - `0dcf8c3`  docs(M29): propuesta shape V5 assets para sync Ramiro 30/05
  - `b7fd965`  docs(M29): SOP v1.0 modulo completo - importer B7 + DataDive + editores

  Push + merge a main = acciones manuales de Lenin (sesión 28/05 PM).

  Pendientes M29 ordenados:
  - **P0**: Reunión Ramiro 30/05 — llevar `notes/modules/M29-V5-shape-proposal.md`,
    capturar respuestas, cerrar contrato v2 de shape V5.
  - **P1**: Post-v2, construir editor manual V5 (1 sesión + tests).
  - **P2**: Verificar 4 templates en `data/sales/_templates/*.json` con 0 blocks
    (¿esperado o deuda?). Portear harness AppTest a botones Guardar V1/V2 para
    cerrar 100% la deuda "edits fantasma".
  - **P3**: Refactor Class B genérico (cuando haya N=4 readonly V3-V6). Cleanup
    versiones `__vN.json` acumuladas en save_proposal. Renderer HTML/PDF para
    S5/S6 (hoy solo JSON crudo en debug expander).

  Flags vivos a retener (del handoff del chat M29):
  - Templates `data/sales/_templates/*.json` con 0 blocks — verificar si es esperado
    del wizard por arquetipo o deuda silenciosa.
  - Discrepancia numérica "20 vs 35 blocks" del planning vs realidad ("20 demo vs
    37 catálogo") — ya no debería bloquear pero anotada.
  - `_DEMO_AgencyOS` es client_name de la propuesta seed, NO un template.
- **Variation Builder M26 (2026-04-26 en curso)**. Módulo nuevo Account Manager para generar flat files Amazon (1 parent + N children). `modules/pages/variation_builder.py` (929L). 4 tabs: Parent / Children+Theme / Preview / Descargar. Tema Variation (Sabor, Tamano, Scent, etc). Bug abierto: `data_editor` requiere doble entrada para persistir — fix diseñado (3 keys pattern) pendiente de aplicar. End-to-end validado con template cliente `PET_FOOD__1_.xlsm`. **Casos de éxito acumulados (3)**: VITALPET 27/04 (4/4), OPTIPET_ADULT 08/05 (4/4), OPTIPET_FLAVORBOOST 09/05 PARCIAL (2/4 — primer caso "listing rico desde cero", 7 hallazgos técnicos nuevos VB-004 a VB-011). Knowledge: `notes/knowledge/2026-05-08-variation-builder-flat-file-format.md`.
- **Sprint 1 Campaign Builder v2.0 — SB rewrite (cerrado 2026-04-23)**. `_render_sb()` reescrito 864→1121 líneas en `modules/pages/campaign_builder.py`. Selector SBV/SBH. Brand Entity ID obligatorio. 29 columnas bulk SB 2026. Validaciones estrictas. Naming Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder).
- **Gamboa Generator M25 (integrado 2026-04-22)**. Módulo Account para reportes HTML integrales (SQP mensual + BR semanal). 5 archivos en `modules/gamboa/` + `modules/pages/gamboa_generator.py` (383L). Live en producción.
- **Bulk Amazon 2026 compliance (2026-04-21)**. 30→31 columnas, helper `_fila_vacia_bulk()`. Validado con Batch ID UUID. Ver [[PPC-SOP-Manager]] sección Campaign Builder + [[amazon-bulk-upload-guide]].
  - 2026-04-28: 8 learnings nuevos sumados (Negative vs Campaign Negative Keyword, Campaign IDs numéricos para campañas existentes, Start Date como texto, Google Sheets corrompe IDs, caracteres especiales rechazados, campaign analyzer puede mostrar zombies, SD schema 47 cols vs SP 31 cols, hoja única obligatoria). Ver sección "Learnings 2026-04-28" en [[amazon-bulk-upload-guide]].
- **Vault Obsidian versionado (hoy 2026-04-24)**. `.gitignore` fix `notes/` → `notes/*` + excepciones por carpeta. Estructura 8 directorios (`brands/`, `daily/`, `knowledge/`, `personal/`, `prompts/`, `sops/`, `state/`, `.obsidian/`). 6 brand notes + 9 archivos sueltos reorganizados con `git mv`.
- **Sprint 2 Campaign Builder Modo B (TBD ~4-5h)**. XLSX custom + `st.data_editor` para flujo rápido power-user.
- **Sprint 3 DaypartingApp (TBD ~2h)**. Módulo nuevo Account Manager — automatización bids por día/hora.
- **M28 SKU Progress Report (Account Health)** — WIP — soak local en preparación.
  28/05 sesión de validación E2E parcial. Cliente de prueba `gamboa` creado con 3
  SKUs (GAMB-SERUM-50ML, GAMB-CREMA-200G, GAMB-OIL-30ML) y fixture CSV sintético
  validado contra parser + consolidación + saneo de símbolos + auto-detect de semana
  del filename + detección de snapshot duplicado + save Parquet. Pendiente para
  próxima sesión: validar tab Admin (borrar snapshot, borrar SKU), Excel completo
  (multi-hoja), registrar optimización en flujo limpio, render del tab GAMB-CREMA-200G
  con los datos importados (consolidación de 2 variantes en pantalla). Después del
  cierre de las 4 validaciones → armar instructivo de setup local para Marcos
  (Python 3.12 + venv + repo + streamlit run). Plan de soak: Marcos prueba en SU PC
  (no deploy cloud) durante una semana; recién con esa validación se decide pasar a
  Supabase para uso compartido.

  Worktree activo: `C:\proyectos\ppc-manager-m28` (branch `feature/m28-soak-local`).
  No hay código modificado en esta sesión — el código de M28 está estable.

  Riesgos detectados (deuda P3, no bloquean soak):
  - R1: `_delete_cliente` y `_dialog_borrar_cliente` usan `Path("data")` relativo;
    el resto del módulo usa `DATA_ROOT`. Inconsistencia a limpiar.
  - R2: posible colisión de nombres de hoja Excel si dos SKUs truncan al mismo
    string de 31 chars (edge case improbable).
  - R3: `unlink()` directo en `_render_admin_tab` fuera de `core.persistence`.
  - Observación UX para soak: el file_uploader rechaza .xlsx en silencio (ícono
    rojo sin mensaje). Marcos puede confundirse si Excel le re-guarda el CSV como
    xlsx. Candidato a mensaje de error explícito.

---

## Iniciativas cliente en curso

- **Dermaglos plan ejecución 28/04** — propagación 30 días. 7 campañas live desde 28/04 ($200/d budget). 46 negativos aplicados. 10 P0 pausadas ($3,960/mes recuperable). Targets: ACoS 56.3%→42-45% / Sales/d $76→$110-130 / Brand IS 0%→60-80%. Re-correr STR 15/05 para medir delta. Re-evaluar B0F548KTXD post-30 días con bids ajustados.
- **Setex cierre completo 29/04** — sesión de mayor impacto histórica de la cuenta. 5 bulks ejecutados (141 movimientos exitosos): #1 Defensivo (39 filas, UUID `7096ec9c-9528-4c22-a18f-328d56cb2a29`) · #2 Ofensivo (12 filas, UUID `5944afce-052e-4c7c-9084-545195cd8929`) · #5 Negativos quirúrgicos (9 filas, UUID `23877dc3-80de-489a-bbb1-12d35ff16385`) · #4 Campañas Nuevas (75 filas, UUID `ad5d988d-a835-43a1-912e-0bdb79991a2a`) · #3 Reducir (6 filas, UUID `426473c9-8e81-4b57-92c6-8817be3012fa`). Net cuenta: ~MX$23k/mes redirigidos. **Best Seller badge confirmado** post-sesión en B081GB8F89 (categoría "Kits de Reparación para Lentes y Anteojos") — validó retroactivamente toda la estrategia. **Framework "Decomposición orgánico vs paid"** descubierto y aplicado: caída -14% WoW era 68% orgánica (OOS Temple+Ear), no PPC. 9 campañas nuevas con naming Capybaras/Atom11-friendly creadas (8 hero=B081GB8F89 + 1 multi-target Brand Hub). Pendiente urgente: reposición FBA Temple Tips + Ear Hooks + B086H3TZ6B (1u, child del badge). Próximas evals: 06/05 (4d), 09/05 (1sem), 13/05 (10d), 20/05 (3sem). Ver [[setex]] y [[2026-04-29-WoW-organic-vs-paid-decomp]].

---

## Bloqueos y pendientes críticos

- **Variation Builder M26**: `data_editor` bug abierto — fix necesario antes de release. Seguimiento en [[daily/2026-04-26]].
- **OPTIPET FlavorBoost** (cliente personal Lenin, NO Capybaras): post upload v5+v6 del 2026-05-19. Pollo creado limpio (B0H2CFM37X, review 48h hasta ~2026-05-21). Pulmón creado pero con ASIN viejo heredado (B00ZCVB3Z8) — UPC 663064 ya estaba en catálogo Amazon vinculado a otro producto. Hígado peso corregido a 297g vía PartialUpdate quirúrgico, sigue Inactive por compliance. UPCs del pool ADAM REQUEST que Mario asignó (951536+934935) confirmados contaminados en GS1 (8541 con Cat Treats Inactive). Descubiertas 5 gotchas nuevas para knowledge (14-18). Pendiente investigar B00ZCVB3Z8 (próxima sesión). Mensaje a Mario sobre activación inventario POSTERGADO hasta confirmar destrabe completo. Seguimiento en [[daily/2026-05-19]] · [[optipet]] · [[arranque-optipet]].
- 🔴 **Decision arquitectura persistencia compartida** (Supabase / R2 / Railway / Neon): bloqueante para uso real con equipo + porting M29 Pricing Dashboard. Esperando respuesta de Freddy sobre aprobacion $25/mes Supabase Pro (mensaje enviado 2026-05-09 con desglose costos). Streamlit Community Cloud filesystem efimero NO sobrevive redeploys.
- **Dermaglos**: ✅ Sesión 28/04 cierre completo — análisis cruzado + plan maestro + 3 bulks ejecutados (93/94 + 46/46 + 7/10 success) + 10 campañas P0 pausadas ($932 net waste detenido / $132/d budget liberado). 7 campañas nuevas live ($200/d budget). ⏳ Pendientes manuales próxima sesión (ver [[2026-04-28]]): Portfolio ID assignment a las 7 nuevas, allantoin 0.5% cream resolver, bid SD Views Retargeting 30D ($1→$0.50), budget B0CYLDSQ5L SP ASIN Related ($5→$15), mensaje corregido a Neha, listing opt Tattoo + Cleanser + Body Cream, restock B0F6V para activar push diferido. Atom11 v2026.2 EN REVISIÓN — Neha trabajando en v2026.3 con 4 fixes (1 corregido en diagnóstico hoy: bug del comma era falso positivo, problema real es rule HARD-STOP que no dispara). Cambio de status: B0F548KTXD sale de heroes (ROAS 0.61×). Estrella oculta identificada: B0F6VZMF2V (ROAS 6.20× OOS desde 09/04).
- **LTD progreso 25/04 cierre completo**: ✅ Fases 1+3+4+5 ejecutadas (sesiones 1+2 mismo día) · ⏳ Fase 6 pendiente esta semana — delegada a equipo (Adam con Aaron compliance B005ULUZIQ, Agustín con cliente ETA restock B09MG1J3LC + summary + lista heroes 3ra solicitud). Push Heroes Fase 4: 5 EXACT Delivering desde hoy +$200/d. Brand Defense expandido a 5 ad groups. Auditoría sistémica match producto/KW pendiente esta semana sin owner asignado. Outputs: bulk xlsx + HTML internal brief para Adam y Agustín.
- **M&B Fase 2 en espera del cliente (requisito creativo)**: ventana original 26-30 abril vencida, pendiente desde 27/04 (14+ días). Mensaje gate AM con pregunta cerrada (Brand Store Women + video SBV listos sí/no) sigue siendo primera tarea próxima sesión Cuki. Mientras: las 3 EXACT HW non-branded ($30/d) cubren funnel mid sin esperar al cliente. Eval día 14 NB HW venció 11/05.
- **M&B Traspaso a Cuki (2026-05-11)**: Owner saliente Lenin Acosta · Owner entrante Cuki · disponible para handoff primera semana, después escalations vía Adam/Agustín. Documento `TRASPASO_MottBow.md` (root del repo, 20 secciones). Outputs sesión: `MB_WoW_Analisis_Traspaso_Cuki_11May2026.html` + `MB_OffAmazon_Research_11May2026.html`.
- **M&B SQP abril 2026 procesado (2026-05-11)**: Purchase Brand Share branded 77.3% → 23% de compras branded se fugan a competencia con brand defense activa (~$2,800/mes). Imp Brand Share 40.6%. **Gap masivo identificado: jeans branded** (14,070 vol/mes con 11.8% imp share, 27.3% purchase share) — no hay catálogo. Caso de negocio para apertura jeans Amazon respaldado por data dura. La incrementalidad branded NO es baja — la palanca real es catálogo, no reducir spend.
- **M&B Research off-Amazon (2026-05-11)**: los problemas de calidad están confirmados en TODOS los canales (Trustpilot 13K+ reviews, BBB 94 complaints). NO es problema Amazon — es estructural. Driggs thin documentado off-Amazon, manufacturing split (Honduras/Peru/Vietnam) probable root cause. Carlton heavyweight 235g recibe mejor feedback que Driggs → evaluar como hero Amazon. Jeans con mejor reputación off-Amazon que t-shirts → refuerza apertura catálogo.
- **M&B WoW TW (26 abr-2 may, revisado 11/05)**: Sales totales +9.6% ($32,886 → $36,030) pero Ad Sales -6.8% ($14,902 → $13,886). ACoS 10.6% / TACoS 4.1% / ROAS 9.45x / CVR 10.79% / BuyBox 99.6%. WTC 28.1%→9% y WTV 15%→8.6% post-cleanup 27/04. SCAVENGER bajó a 32.5% pero sigue lejos del 3.4% histórico (audit pendiente). Estrella oculta WTV B005ULUZIQ SP-PR EXACT DEFEND BRAND ASINS ROAS 28x (escalar budget si capeado). Bleeders 3-Pack VN B0FY3X2KCT + B0FXBTNRT9 (pausar). PPC bajó pero ventas subieron → confirma Meta como motor real.
- **2026-05-22**: Lenin ad hoc setup Amazon Attribution Meta Facebook para
  M&B (ayudando Agustín). 6 tags V0 generados y entregados. Instagram +
  Email + BRB enrollment + V1 granular pendientes según respuesta cliente.
  Owner sigue siendo Cuki. SOP nuevo creado en [[amazon-attribution-setup]].
- **Setex Technologies (Amazon MX)** — Status: 🟢 OK — full sesión 21-22/05
  - Última sesión: 22/05 (cierre ejecución 2 días 21+22/05)
  - 5 bulks ejecutados 22/05 (157 cambios / 33 camps / +$223/d budget winners)
  - Atom11 Rules v2026.3 enviado a Neha (52 rules / 5 sheets / esperando confirmación)
  - ACoS cuenta pre-bulks: 19.4% · TACoS 14% (target 18%)
  - Net efecto esperado: -$400/mo spend / +$25k/mo sales
  - Pendientes Tati: listing audit B081GB8F89 (ES+EN) + ETAs restocks
    (B0F63LTD92 / Temple Tips)
  - Flags Seller Central nuevas: B09F7YB74Y (3u+10u inbound) / B0DW9Z2H2W
    (Missing offer) / B0CC6THCDS (precio Kids 15p vs 5p)
  - Próxima sesión: jueves 29/05 — eval día 7 + Fase 1 Atom11
  - Histórico 12/05 (9 bulks, 275 cambios) y pendientes restock heredados:
    ver [[2026-05-12]] y [[PENDIENTES_RESTOCK]]

Ver: [[2026-05-22]] [[setex]] [[atom11-rules]]
- **360 Essentials SBV**: espera video creativo FreedomPlus para lanzar 3 campañas SBV ($45/d).
- **Git**: 2 commits locales sin push (`fbae212`, `3f04fb1`) + los que se agreguen hoy. Push manual al cerrar sesión.
- **Repo deuda técnica**: `INTELLIGENCE-INDEX.md` stale (dice 1 nota, M&B listado como MX en vez de US, sin 360 Essentials ni PVM).
- **AmazonBulkUploadGuide.md stale (4 puntos críticos descubiertos 27/04)**: (1) caracteres prohibidos en Keyword Text no documentados (`%`, `$`, `#`, `@`, `*`, etc.) — el `&` SÍ se permite en negativeExact, (2) comportamiento secuencial stop-on-error 2026 no documentado — UI muestra Failed pero filas anteriores ya creadas (verificación visual obligatoria), (3) estrategia re-subida con cambio de 1 letra del naming, (4) Regla #2 lista 30 cols pero el código en producción usa 31 (Sites). Próxima sesión: actualizar guía. Riesgo si no se hace: bulks futuros van a fallar igual y el equipo va a perder horas.
- **Patrón Streamlit a documentar (29/04)**: `st.expander` no se puede anidar dentro de otro `st.expander` (`_check_nested_element_violation`). Bug intermitente — solo crashea cuando se ejecuta el branch que crea el expander interno, por eso pasa code review básico. Reemplazo standard: `st.popover` (Streamlit ≥1.28). Documentar en `notes/sops/` o `module-architecture-standard.md`.
- **Listing Monitor fix aplicado 29/04 + 2 sospechosos pendientes**: `modules/pages/listing_monitor.py` L563 — `st.expander("Ver bullets actuales")` anidado dentro de expander padre L508 → fix aplicado con `st.popover` (1 línea). Live en producción, validado con ASIN B01M6DFC5W (Medix 5.5, marketplace MX). Diagnóstico via agente `code-reviewer` reveló 2 sospechosos del mismo bug que NO se atacaron (scope): `modules/pages/gamboa_generator.py` L322+L370 y `modules/pages/atom11.py` L261+L303. Verificar indentación próxima sesión y aplicar mismo fix preventivo si confirma.
- **Reviews Intelligence (esperando decisión CEO)** — feedback del CEO pendiente sobre cancelar tarjeta Apify o dejarla. Caminos posibles: (a) export manual Seller Central + automatizar procesamiento, (b) probar Bright Data ($15-30/mes), (c) pausar el módulo. Mensaje al CEO ya enviado el 2026-05-05.
- **OPTIPET Adult variation family — A+ Content track abierto 2026-05-21** (cliente personal Lenin, NO Capybaras): A+ Premium creado para child Vitality (B0G6VWT7RB) con patrón "A+ por child" (no parent). Skin and Coat + Healthy Gut quedan pendiente A+ propio (esperan arte equivalente al de Vitality). Inbound 72u FBA consolidado (179u totales). Primera venta Adult registrada: Vitality 1u en 30d window. FBM zombi OPTIPETSKINCOATFBA (15u FBM viola regla 1 ASIN ≠ 2 children) sigue Active, pendiente Close.

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

**Hallazgo (2026-05-09, ampliado 2026-05-12):** Sesión OPTIPET FlavorBoost del 2026-05-09 descubrió 7 deudas técnicas nuevas (VB-004 a VB-011). El 2026-05-12 se descubrió un caso de estudio adicional: el listing del Hígado pasó a Inactive el 2026-05-10 por compliance policy `GRLKLZ6WQ9R259LC` (Amazon MX Pet Consumables), no por bug del módulo M26. Esto agrega un requerimiento operativo NUEVO al refactor M26: el módulo debería validar pre-feed que el seller tenga paquete de compliance preparado para categorías reguladas (Pet Food MX, supplements). Estimación refactor sube a 2-2.5 sesiones.

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
- **VB-012** (nueva, 2026-05-12, 1h, riesgo bajo): pre-flight check de compliance categórico. Para categorías reguladas (Pet Food MX, supplements, alimentos, dietary supplements), antes de generar el flat file, mostrar warning visual con link a la política Amazon aplicable + checklist de docs típicos requeridos. Bloquea la generación hasta que el seller confirme "Tengo el paquete de compliance preparado".

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

### 10. Script de seed de propuestas demo no commiteado (prioridad BAJA)

**Hallazgo (2026-05-12)**: durante prep de screenshots para update Slack, Lenin creó un script Python temporal (`_seed_demos.py`) para crear 3 propuestas demo de una sola corrida. El script se ejecutó vía `notepad` + `python` + `Remove-Item` sin quedar persistido en el repo.

**Impacto**: cada vez que se necesite "limpiar y resembrar" el dataset de testing (para demos, screenshots, validación E2E), Lenin tiene que reescribir el script desde cero. Estimado: 10-15 min de fricción cada vez.

**Fix sugerido**: crear `scripts/seed_demos.py` commiteado con CLI (`--reset` y `--archetypes launch,scale_seo,defense,cvr`), que sea reutilizable. Incluir en README cómo correrlo. Path sugerido: `scripts/seed_demos.py`.

**Trigger**: la 2da o 3ra vez que necesitemos resembrar dataset. Si solo pasa una vez más, no vale la pena el commit.

### 11. Compromiso público de timeline M29 (prioridad ALTA — vigilancia activa)

**Contexto (2026-05-12)**: Lenin se comprometió públicamente en Slack a la agencia entera con un timeline específico de M29:
- **Esta semana (13-18 mayo)**: Fases 3 + 4
- **Próxima semana (19-25 mayo)**: Fases 5 + 6

**Riesgo**: si Sesión 3 se desborda (es la fase más compleja, requiere form dinámico desde schema para los 6 CORE Variables), el deadline público no se cumple. Hay obligación social de comunicar proactivamente al canal antes de que se cumpla la fecha (no después de que se pase).

**Mitigación operativa**:
- Priorizar S3 al máximo esta semana (la más compleja)
- S4 (sistema de votos) puede caer en cualquier hueco — es chica
- Status check informal mid-week (15-16 mayo): si S3 está atorada, mandar mensaje preventivo a Slack: "S3 me está tomando más de lo esperado, ajusto deadline a X"

**Cierre de la deuda**: cuando S6 esté completada y mergeada a main (commit de cierre + push + refresh proyecto Claude.ai), se puede cerrar esta deuda con nota de retrospectiva: ¿se cumplió? ¿qué se aprendió del compromiso público vs interno?

**No es deuda técnica clásica** — es deuda de delivery/comunicación. Pero amerita estar en STATE para que próximas sesiones operen con conciencia del compromiso.

### 12. OPTIPET Compliance & UPCs nuevos (prioridad ALTA, cliente personal Lenin)

> Renumerada de "6" a "12" durante el escribe del 2026-05-12 para evitar colisión con la sección 6 ya existente (M29 Proposal Studio — deudas Sesión 1).

**Hallazgo (2026-05-12):** El cliente personal OPTIPET tiene 2 bloqueos paralelos:

1. **Compliance Amazon MX Pet Food** del Hígado del Flavor Boost (ASIN B0H16T5H18). Listing removed el 2026-05-10. Esperando docs específicos del producto (COA, etiqueta, ficha técnica, Non-GMO).

2. **UPCs nuevos del fabricante** para crear los 2 sabores faltantes (Pulmón + Pollo) del Flavor Boost. Cliente confirmó NO eliminar Cat Treats Inactive — única salida es asignación de UPCs nuevos por PETSA.

**Estado al 2026-05-12**: comunicación con Adam (conector con INASA) activa. Lenin va a escribir directo a Mario (lado fabricante PETSA) y Abraham (lado marca INASA) en el chat INASA una vez que Adam confirme framing.

**Trigger para destrabar**: respuesta de Mario con UPCs nuevos + entrega de docs específicos de producto por parte de INASA.

**Datos validados que entran al vault esta sesión**:
- Master Sheet INASA (hoja OptiPet) confirmada como fuente de verdad de datos de producto
- Pricing oficial Flavor Boost: $349 MXN / $303.48 MXN real
- Peso paquete real: 297g (no 360g como se usó en v4)
- Ingredientes reales Pulmón y Pollo confirmados
- Línea OPTICAT identificada (3 SKUs, no lanzada todavía)

Detalle completo en `notes/daily/2026-05-12.md` (sección "Continuación del día — OPTIPET").

### 13. Gotchas operativos Setex sesión 12/05 (prioridad MEDIA, actualizar SOPs)

**Contexto (2026-05-12)**: Durante la sesión exhaustiva Setex con 9 bulks ejecutados se descubrieron 2 gotchas operativos nuevos que ameritan actualización de SOPs.

- **[bulk-upload] Bid set vs CPC efectivo pueden diferir 100%+**. En Setex el keyword `antideslizante para lentes` tenía bid set $21.80 vs CPC efectivo $9.41 — confusión que veníamos arrastrando interpretando el problema como bid bajo en lugar de bid inflado. **Regla**: SIEMPRE verificar bid en BulkSheetExport, NO asumir desde STR CPC. Actualizar [[amazon-bulk-upload-guide]] con este learning.

- **[bulk-upload] Portfolio ID numérico se puede incluir directo en bulk de CREATE**. Validado en Bulk #9 Setex con `Portfolio ID = 197371337016358` (06mm Nose Pads) — 5 campañas Success. **Esto contradice el SOP anterior** que decía "siempre dejar Portfolio ID vacío al crear y asignarlo manualmente después". Actualizar [[amazon-bulk-upload-guide]] con la regla nueva: si conocés el Portfolio ID numérico real (extraído de Campaign Manager o BulkSheetExport), podés incluirlo en CREATE.

**Bonus gotcha (validar próxima sesión)**: typos en keyword interna pueden propagarse silenciosamente. Campaña fantasma de Setex tenía keyword `almoadillas para lentes` (sin la 'h'), 0 impresiones, archivada el 12/05. Patrón: verificar campañas con 0 imp + nombre raro contra typos en KW interna. Si se confirma como patrón cross-cliente, agregar al SOP.

**Trigger para atacar**: próxima sesión donde se toque [[amazon-bulk-upload-guide]] (probablemente la del Atom11 rules Setex). Bajo riesgo de regresión si se difiere — los 2 gotchas son aditivos, no breaking.

Detalle completo en `notes/daily/2026-05-12.md` (sección "Sesión Setex 12/05/2026" — Bugs/gotchas nuevos descubiertos).

---

### 14. Tests E2E con `streamlit.testing.v1.AppTest` para M29 (prioridad ALTA)

**Hallazgo (2026-05-15):** El bug de botones Guardar V1+V2 que se introdujo en commit `9a3eaad` y rompió V1 (regresión real) pasó por encima de 42/42 tests pytest verdes. Los tests ejercitan `save_proposal()` y normalización de payloads a nivel de API, pero NO el dispatch de botones de Streamlit ni el lifecycle de session_state entre reruns.

**Por qué sube de prioridad MEDIANO PLAZO → ALTA:** caso real ya ocurrido. Cada vez que se toca código compartido entre editores V1-V6 hay riesgo de regresión silenciosa hasta que un humano haga smoke test manual.

**Plan**: agregar tests AppTest E2E que cubran al menos:
1. Abrir editor V1 → editar `brand_name` → click "💾 Guardar V1" → verificar que `data/sales/proposals/<uuid>__vN+1.json` existe con el cambio
2. Mismo flujo para V2 cuando esté estable
3. Round-trip: cerrar y reabrir → cambios persisten

**Trigger inmediato**: incluir en Sesión A.2 ya planificada (tests pytest con monkeypatch + tests AppTest E2E juntos).

Detalle: [[2026-05-15-m29-bug-save-buttons]]

---

### 15. `_STRUCTURED_ALIASES` de M27 validado solo para Apparel/Coat USA (prioridad BAJA, on-demand)

**Hallazgo (2026-05-15):** La tabla `_STRUCTURED_ALIASES` (40 mappings) que habilita Strategy 3.5 de M27 v2 fue diseñada y validada **solo** con flat files de Apparel/Coat USA. Otras categorías (electrónica, comida/grocery, beauty, supplements, pet food) usan nombres de subfields distintos en feedType 256 que NO están en la tabla.

**Hoy no rompe nada**: M27 cae graceful a Strategy 4 (base) o Strategy 5 (header) cuando el mapping estructurado no existe. La cobertura puede bajar a ~40% en otras categorías pero el módulo no falla.

**Plan de extensión bajo demanda** (no preventivo):
1. Cliente reporta caso 113→256 en otra categoría
2. Lenin inspecciona los 2 archivos con script offline (template: `tests/test_m27_v2_structured.py`)
3. Agregar entradas faltantes a `_STRUCTURED_ALIASES`
4. Test fixture nueva + commit + actualizar [[2026-05-15-m27-strategy-3-5-structured]]

**No se debe atacar preventivamente**: cubrir los ~250 productTypes de Amazon sería 1-2 semanas de trabajo sin ROI confirmado. El módulo cumple su función con Apparel hoy.

Detalle: [[2026-05-15-m27-strategy-3-5-structured]]

### 16. M31 Forecast — parser F2 no maneja Business Report real (🔴 BLOQUEANTE pre-MVP)
El motor de forecast (F3) está verificado SOLO contra el demo Dermaglos (ISO, números limpios, mensual). NUNCA se probó contra datos reales de Amazon. Validado en sesión 24/06 con CSV real de Setex MX que el parser de F2 rompe:
- Moneda como "MX$5,121.00" (prefijo MX$ + separador de miles con coma + entrecomillado) → el parser da cero / rompe.
- Nombres de columna reales difieren del demo: "Ordered Product Sales" (no revenue), "Units Ordered" (no units), "Sessions - Total" (no sessions), "Order Item Session Percentage" (no cvr). El mapeo fuzzy no los cubre.
- Export real es DIARIO (By Day); la herramienta trabaja MENSUAL → falta agregación día→mes, o exportar "By Month" desde Seller Central.
- Faltan columnas pageViews y buyBox en el reporte real (Sales and Traffic by Date) — el shape las espera.
CONSECUENCIA: antes del MVP usable hay que cerrar un fix del parser F2 contra BR real. CSV de prueba: BusinessReport-6-24-26 (Setex MX) — uso interno, datos de cliente real, NO versionar.
Nota descartada: fechas MX NO son riesgo — Seller Central MX exporta en M/D/Y (formato US), el parser las lee bien.

### 17. Watcher de Streamlit bloquea pytest en sesiones multi-frente (🟠 INFRA)
El watcher de Streamlit respawnea sobre el .venv compartido (C:\proyectos\ppc-manager\.venv) y bloquea correr pytest en cualquier worktree. Impacto concreto en sesión 24/06: M28 no pudo verificar Bloque 1 (c98bc83 commiteado sin tests). Workaround: cortar el watcher con Ctrl+C en la terminal fuente (NO Stop-Process) antes de correr pytest una sola pasada. Resolver la raíz antes de la próxima corrida multi-frente.

### 18. _PAGES en core/constants.py stale — emojis desincronizados del router real (🟢 MENOR)
_PAGES en core/constants.py tiene emojis desincronizados del router real en 4 módulos (PPC Insights, Forecast, Audit, DataDive). NO load-bearing: la navegación real son los hooks hardcodeados en app.py, no _PAGES. Decidir si se elimina _PAGES o se re-sincroniza. No urgente. (Relacionado con deuda residual #7 _PAGES/inicio.py.)

---

## Próximos pasos inmediatos

### Próxima semana (26-31/05) — orden de prioridad

**1. M29 D3 + D4 dispatcher B7 — martes 26/05**
- Camino al ship jueves 28/05
- D3 (commit pipeline) + D4 (validación + diagnostics UI)
- Bloqueante si se atrasa: el ship target se mueve

**2. M27 decisión A / B / C — cuándo Lenin pueda**
- A: audit Opus B6-b-5 (deuda P3, no urgente)
- B: fix infra venv Python 3.12 (resolver bug P1 .xlsm) — **recomendado**
- C: ship formal v1.1 + mensaje Marcos closing loop

**3. Refactor DataDive parsers → `modules/parsers/` + mapper V3 — martes
   post-D4**

**4. Editor manual V5 (URLs pareadas) — miércoles 27/05**

**5. Testing E2E + SOP + ship M29 — jueves 28/05**
- Target público comprometido

**6. Setex eval día 7 Hot Sale — lunes 01/06**
- Validar performance bulks 25/05 con 7d data

**7. Monitor B09F7P8GBZ stock cada lunes (trip wire 3u)**
- Si baja a 3u → pausar push family

**8. Bug list M4 consolidado (8 bugs) → entregable Ramiro**
- Doc único con los 8 bugs + repro steps + propuesta de patch

**9. Atom11 v2026.3 confirmación Neha (3er día sin respuesta)**
- Bump al canal o DM directo si sigue sin respuesta el lunes

**Reuniones agendadas:**
- Viernes 29/05 — sync Ramiro post-ship M29 (corrección: NO sábado 30/05)

### Backlog general

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
17. **Setex** (post 12/05) — (1) Esperar respuesta Tati Slack 12/05 con las 4 urgencias: restock B086H3TZ6B + B0F63LTD92, ETA Temple Tips, audit listing EN B081GB8F89. (2) Verificación visual post-bulks en Campaign Manager (275 cambios). (3) Asignación manual portfolios a 4 RANKING revividas + 5 nuevas Thin (9 campañas total). (4) **Atom11 rules file para Neha — sesión dedicada próxima** (Setex ya añadido a Atom pero sin rules). (5) **SBV B08PZF22R1 — owner Adam** (heredado 15/04, push Thin family cobra urgencia). (6) Evaluaciones programadas: 15/05 día 3 (impressions 5 EXACT Thin, si KWs PS 100% <300 imp → bid $3→$4) · 19/05 día 7 (performance EXACT iniciales + decisión escalar/pausar) · 26/05 día 14 (review completo + plan v2). (7) Si llega restock B086H3TZ6B → reactivar 19 Product Ads pausados (Bulk #2 UUID `afde8719-00dd-476f-9c48-364bd625bf64`). (8) Si llega restock Temple/Ear Hook → ejecutar [[PENDIENTES_RESTOCK]] playbook (5 campañas + 12 KWs + bid +25-30%). (9) Listing opt B081GB8F89 lock-in del badge (sigue heredado de 29/04). (10) Coordinar con Nicki: 5 SKUs duplicados Closed (heredado 29/04).


---

## Conocimiento operativo agencia

- **2026-05-22**: Amazon Attribution setup documentado en
  [[amazon-attribution-setup]]. Primera implementación M&B exitosa.
  Replicable para cualquier cliente con Brand Registry + canales externos
  activos. Aplica a LTD, Dermaglos, M&B. Gotcha crítico documentado:
  bulk Beta no completa jerarquía Ads/Tags, default = Create manually.

- **2026-05-22**: NotebookLM adoption — SOP v1.0 commiteado (notes/sops/SOP_NotebookLM_Capybaras_2026.md). Pilot personal de Lenin días 1-7 con notebook `intel-agencia-q2-2026`. 4 notebooks pre-armados con fuentes en Drive. Go/No-Go preliminar día 7, formal día 60 (2026-07-22).
