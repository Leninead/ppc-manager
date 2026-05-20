---
tipo: state
actualizado: 2026-05-15
---

# STATE Agencia — Capybaras

Snapshot operativo de la agencia. Agregador por diseño (no nota atómica).

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
| Dermaglos | Amazon USA 🇺🇸 | 58.0% (↓ de 76.1%) | Meta ≤55%, escalar vitamin A + allantoin + tattoo ES | Rufus analysis 4 heroes + confirmación equipo Atom11 ejecutó entregable | [[DERMAGLOS]] · [[DERMAGLOS_DATA]] · [[atom11-rules]] |
| Mott & Bow | Amazon US 🇺🇸 | 10.6% TW (26 abr-2 may, sano) | Full-Funnel Women — Fase 2 en espera del cliente (SBV White Tee + SP Exact Premium Cotton) · transición de owner a Cuki 2026-05-11 | Video creativo + Brand Store Women — espera respuesta cliente para lanzar Fase 2 | [[MB]] |
| Love To Dream | Amazon MX 🇲🇽 | 16.1% | Plan 6 Fases ejecutado (5 de 6) — Fase 6 pendiente esta semana (Adam→Aaron, Agustín→cliente) | Mismatch producto/KW sistémico — auditoría dedicada esta semana · B09MG1J3LC sigue OOS · 5 EXACT heroes Delivering desde hoy | [[LTD]] |
| Setex Technologies | Amazon MX 🇲🇽 | 20.5% (↓ proyectado 16-17% post-bulks 12/05) | 🏆 Best Seller badge B081GB8F89 (lock-in) + push estratégico familia Thin (B0F3PSP82K, 1839u) — 5 EXACT nuevas SKU XG9G515 +$145/d · 154 negativos cross-camp anti-canibalización · pausa preventiva B086H3TZ6B (1u, 19 ads) | 4 urgencias Tati Slack 12/05: B086H3TZ6B 1u · B0F63LTD92 1u · Temple Tips OOS · audit listing EN B081GB8F89 (PS 0% queries anglo) | [[setex]] · [[PENDIENTES_RESTOCK]] |
| 360 Essentials | Amazon USA 🇺🇸 | 23.0% (✅ target 35%) | SBV FreedomPlus branded + test incrementalidad + relanzar SD bid $1 | Video creativo FreedomPlus para SBV (3 camps) | [[360ESSENTIALS]] |
| Pura Vida Moringa | Amazon MX 🇲🇽 | 45.5% marzo (proyectado 48-52% post-opt) | Bajar ACoS a 40-45% · consolidar rank orgánico top 2-5 | Sin crédito Atom11 — optimización manual | [[Puravidamoringa]] |

**Patrón cross-client**: todos los USA con cuenta madura (Dermaglos, M&B, 360 Essentials) corrieron Atom11 v2026.2 en marzo. Los MX (LTD, Setex, PVM) manuales — LTD con 38 rules vía Cowork, Setex sin Atom11, PVM sin crédito.

---

## LTD
status: 5/6 fases ejecutadas (ejecución bulks completa 2026-05-20)
last_session: 2026-05-20
bulks_aplicados: 9 ✅ + 1 manual (PAT SwaddleMe)
acos_actual: 15.6%
acos_target_junio: 11-12%
tacos_actual: 17.4%
tacos_target_junio: 10-12%
heroes_oficiales: 10 (pendiente update a 19 con Agustín)
heroes_detectados_str: 19

## Pendiente LTD
- Stock alerts (Agustín): B0F8PB4NHX, B09S14W4SS, B0088HVGHS, TOG 2.5 línea
- Validar ASINs MX para 3 PAT pausadas (Halo, Swaddelini, Kyte Baby) — próxima sesión
- Heroes oficiales: confirmar update 10 → 19 con Agustín
- B09MG2CVCR SBV PROBLEM: sin owner asignado
- Seguimientos: 21/05 winners TimeInBudget, 22/05 SwaddleMe PAT impressions, 23/05 EXACT orders, 25/05 STR semanal

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

- **M29 Proposal Studio (Sales Director module)** — Sesión 3 en curso
  (B1+B2 cerrados, B3-B6 pendientes). Commits hoy: `6b0f2dc` (S3-B1 routing
  vista detalle + state machine + skeleton) + `5cc0fd3` (S3-B2 listado
  readonly de blocks con badges por tier). Ambos en `main`, SIN push —
  acumulando hasta cierre de B6 según patrón S2 (3 commits sin push).
  Click "🔎 Abrir" desde Listado ahora abre vista detalle funcional con
  todos los blocks de la propuesta visibles, badges por tier
  (editable/locked/próximamente). Smoke test E2E con las 3 propuestas
  demo: composición CORE varía por arquetipo (Launch=4, CVR=3,
  Scale+SEO=5). Próximo: Sesión 3 — B3-b V1 Brand Overview end-to-end con
  save funcional → si valida patrón, replicar a V2-V6 → B5 botón Guardar
  → B6 polish + push acumulado. Compromiso Slack (12/05): fases 3+4 esta
  semana. Owner: Lenin (dev). Ver [[brands/agency-os]] y [[daily/2026-05-13]].
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
- **OPTIPET FlavorBoost** (cliente personal Lenin, NO Capybaras): post upload v5+v6 del 2026-05-19. Pollo creado limpio (B0H2CFM37X, review 48h hasta ~2026-05-21). Pulmón creado pero con ASIN viejo heredado (B00ZCVB3Z8) — UPC 663064 ya estaba en catálogo Amazon vinculado a otro producto. Hígado peso corregido a 297g vía PartialUpdate quirúrgico, sigue Inactive por compliance. UPCs del pool ADAM REQUEST que Mario asignó (951536+934935) confirmados contaminados en GS1 (8541 con Cat Treats Inactive). Descubiertas 5 gotchas nuevas para knowledge (14-18). Pendiente investigar B00ZCVB3Z8 (próxima sesión). Mensaje a Mario sobre activación inventario POSTERGADO hasta confirmar destrabe completo. Seguimiento en [[daily/2026-05-19]] · [[optipet]] · [[arranque-optipet]].
- 🔴 **Decision arquitectura persistencia compartida** (Supabase / R2 / Railway / Neon): bloqueante para uso real con equipo + porting M29 Pricing Dashboard. Esperando respuesta de Freddy sobre aprobacion $25/mes Supabase Pro (mensaje enviado 2026-05-09 con desglose costos). Streamlit Community Cloud filesystem efimero NO sobrevive redeploys.
- **Dermaglos**: ✅ Sesión 28/04 cierre completo — análisis cruzado + plan maestro + 3 bulks ejecutados (93/94 + 46/46 + 7/10 success) + 10 campañas P0 pausadas ($932 net waste detenido / $132/d budget liberado). 7 campañas nuevas live ($200/d budget). ⏳ Pendientes manuales próxima sesión (ver [[2026-04-28]]): Portfolio ID assignment a las 7 nuevas, allantoin 0.5% cream resolver, bid SD Views Retargeting 30D ($1→$0.50), budget B0CYLDSQ5L SP ASIN Related ($5→$15), mensaje corregido a Neha, listing opt Tattoo + Cleanser + Body Cream, restock B0F6V para activar push diferido. Atom11 v2026.2 EN REVISIÓN — Neha trabajando en v2026.3 con 4 fixes (1 corregido en diagnóstico hoy: bug del comma era falso positivo, problema real es rule HARD-STOP que no dispara). Cambio de status: B0F548KTXD sale de heroes (ROAS 0.61×). Estrella oculta identificada: B0F6VZMF2V (ROAS 6.20× OOS desde 09/04).
- **LTD progreso 25/04 cierre completo**: ✅ Fases 1+3+4+5 ejecutadas (sesiones 1+2 mismo día) · ⏳ Fase 6 pendiente esta semana — delegada a equipo (Adam con Aaron compliance B005ULUZIQ, Agustín con cliente ETA restock B09MG1J3LC + summary + lista heroes 3ra solicitud). Push Heroes Fase 4: 5 EXACT Delivering desde hoy +$200/d. Brand Defense expandido a 5 ad groups. Auditoría sistémica match producto/KW pendiente esta semana sin owner asignado. Outputs: bulk xlsx + HTML internal brief para Adam y Agustín.
- **M&B Fase 2 en espera del cliente (requisito creativo)**: ventana original 26-30 abril vencida, pendiente desde 27/04 (14+ días). Mensaje gate AM con pregunta cerrada (Brand Store Women + video SBV listos sí/no) sigue siendo primera tarea próxima sesión Cuki. Mientras: las 3 EXACT HW non-branded ($30/d) cubren funnel mid sin esperar al cliente. Eval día 14 NB HW venció 11/05.
- **M&B Traspaso a Cuki (2026-05-11)**: Owner saliente Lenin Acosta · Owner entrante Cuki · disponible para handoff primera semana, después escalations vía Adam/Agustín. Documento `TRASPASO_MottBow.md` (root del repo, 20 secciones). Outputs sesión: `MB_WoW_Analisis_Traspaso_Cuki_11May2026.html` + `MB_OffAmazon_Research_11May2026.html`.
- **M&B SQP abril 2026 procesado (2026-05-11)**: Purchase Brand Share branded 77.3% → 23% de compras branded se fugan a competencia con brand defense activa (~$2,800/mes). Imp Brand Share 40.6%. **Gap masivo identificado: jeans branded** (14,070 vol/mes con 11.8% imp share, 27.3% purchase share) — no hay catálogo. Caso de negocio para apertura jeans Amazon respaldado por data dura. La incrementalidad branded NO es baja — la palanca real es catálogo, no reducir spend.
- **M&B Research off-Amazon (2026-05-11)**: los problemas de calidad están confirmados en TODOS los canales (Trustpilot 13K+ reviews, BBB 94 complaints). NO es problema Amazon — es estructural. Driggs thin documentado off-Amazon, manufacturing split (Honduras/Peru/Vietnam) probable root cause. Carlton heavyweight 235g recibe mejor feedback que Driggs → evaluar como hero Amazon. Jeans con mejor reputación off-Amazon que t-shirts → refuerza apertura catálogo.
- **M&B WoW TW (26 abr-2 may, revisado 11/05)**: Sales totales +9.6% ($32,886 → $36,030) pero Ad Sales -6.8% ($14,902 → $13,886). ACoS 10.6% / TACoS 4.1% / ROAS 9.45x / CVR 10.79% / BuyBox 99.6%. WTC 28.1%→9% y WTV 15%→8.6% post-cleanup 27/04. SCAVENGER bajó a 32.5% pero sigue lejos del 3.4% histórico (audit pendiente). Estrella oculta WTV B005ULUZIQ SP-PR EXACT DEFEND BRAND ASINS ROAS 28x (escalar budget si capeado). Bleeders 3-Pack VN B0FY3X2KCT + B0FXBTNRT9 (pausar). PPC bajó pero ventas subieron → confirma Meta como motor real.
- **Setex pendientes post-12/05** (actualizado, supersedes 29/04): ✅ Sesión 12/05 cierre completo — 9 bulks, 275 cambios, 100% Success · cambio estratégico Thin push activo · pausa preventiva 19 ads B086H3TZ6B · bug fix bid `antideslizante para lentes` ($21.80 → $7.50) · 154 negativos cross-campaign anti-canibalización · 5 EXACT nuevas Thin SKU XG9G515 (+$145/d). Brand Hub Heroes ya subido $3→$5 en Bulk #1 (cierra pendiente del 29/04). ⏳ Pendientes activos: (1) **4 urgencias Tati Slack 12/05**: restock B086H3TZ6B (1u, child badge), restock B0F63LTD92 (1u, Ear Hook), ETA Temple Tips OOS, audit listing EN B081GB8F89 · (2) Verificación visual post-bulks en Amazon Ads (que se aplicaron los 275 cambios) · (3) Asignación manual portfolios a 4 RANKING revividas + 5 nuevas Thin · (4) **Atom11 rules file para Neha** — Setex ya añadido a Atom pero sin rules (sesión dedicada próxima) · (5) **SBV B08PZF22R1 — owner Adam** (heredado 15/04, push Thin family cobra urgencia) · (6) Si llega restock B086H3TZ6B → reactivar 19 Product Ads pausados (Bulk #2 UUID `afde8719`) · (7) Coordinar con Nicki: 5 SKUs duplicados Closed (heredado 29/04) · (8) Listing opt B081GB8F89 lock-in del badge (lleva pendiente desde 29/04). Diferidos hasta restock: 5 campañas nuevas Temple/Ear Hook + 12 KWs harvest documentados en [[PENDIENTES_RESTOCK]]. Próximas evals: 15/05 (día 3 impressions 5 EXACT Thin) · 19/05 (día 7 performance) · 26/05 (día 14 review completo). Ver detalle completo en [[2026-05-12]] (sección "Sesión Setex 12/05/2026") y [[setex]].
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

---

## Próximos pasos inmediatos

### Próxima semana (18-24/05) — orden de prioridad

**1. M29 fix bug Guardar V1/V2 — sábado 16 o domingo 17/05 (URGENTE)**
- Leer output de auditoría forense
- Implementar fix
- Smoke test ambos editores
- Si toma >2h sin progreso → mensaje preventivo Slack ajustando deadline 18/05

**2. M29 continuar S3-B3-c, B3-d, B3-e — semana 18-24/05**
- 5 editores CORE pendientes después del fix del bug
- Cierre fases 3+4 (compromiso público)
- Sesión A.2 tests pytest con monkeypatch (deuda activa)

**3. M27 closing loop con Marcos — lunes 18/05**
- Mensaje Slack: "M27 v2 listo, probá local con tus 2 archivos"
- Esperar feedback visual del output v2
- Decisión post-feedback: ¿extender a otras categorías o queda en Apparel?

**4. Atom11 MCP discovery — semana 18-25/05 (sesión dedicada ~45 min)**
- No bloquea M29 ni M27
- Alcance acotado: documentar workflows en `notes/knowledge/`
- Hipótesis previa: NO reemplaza M14, NO necesita módulo nuevo
- Trigger: cuando M29 fases 3+4 estén cerradas

Detalle Atom11: [[2026-05-15-atom11-mcp-integration]]
Detalle M27: [[2026-05-15-m27-strategy-3-5-structured]]
Detalle M29 bug: [[2026-05-15-m29-bug-save-buttons]]

---

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
