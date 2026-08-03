---
tipo: sop
modulo: M29
version: 1.0
fecha: 2026-05-28
autor: lenin-acosta
estado: activo
---

# SOP M29 · Proposal Studio

## 1. ¿Qué es M29?

M29 Proposal Studio es el módulo de la sección **Sales Director** del Agency OS
(Capybaras). Su función es generar y versionar propuestas comerciales para
leads/prospects a partir de un catálogo canónico de 37 módulos (8 FIXED + 29
variables) y 4 arquetipos pre-definidos (`launch`, `scale_seo`, `defense`, `cvr`,
más `custom` como escape hatch). El entry point es `modules/pages/proposal_studio.py`
y la persistencia vive en `core/proposal_persistence.py` (Fase 1: JSON local con
auto-versionado).

El flujo central tiene tres patas:
- **Wizard de creación** (steps 1–3) que mete cliente, idioma, arquetipo y dispara
  el template del arquetipo elegido.
- **Vista detalle por propuesta** que muestra los bloques cargados, ofrece
  editores manuales para V1/V2 y permite importar data desde HTML (B7) o MKL
  DataDive (E4) para V3 en particular.
- **Persistencia versionada en disco**: cada save crea
  `<uuid>__v<N>.json` con `N = max_actual + 1` (auto-bump, ignora la `version`
  del input).

El módulo se diseñó para que en el corto plazo (Fase 1) la persistencia local
sea reemplazable por Supabase sin tocar consumidores (ver `ProposalStorage`
ABC en `core/proposal_persistence.py`).

---

## 2. Arquitectura de bloques — los 6 CORE Variables

El catálogo (`data/sales/_catalog.json`) tiene 37 módulos. Los 6 que componen
el "core variable" (`tier: "core_variable"`) son los V1-V6 y son el corazón
editorial del módulo:

| ID | Título | Patrón render | Fuente principal de data | Editor |
|----|--------|--------------|-------------------------|--------|
| `V1_brand_overview` | Brand Overview | **Plan D editor** (`_render_v1_brand_overview_editor`, L1149) | Manual desde la vista detalle | ✅ Sí |
| `V2_category_overview` | Category Overview | **Plan D editor** (`_render_v2_category_overview_editor`, L1521) | Manual desde la vista detalle | ✅ Sí |
| `V3_seo_opportunity` | SEO Opportunity (Missing Keywords) | **Class B readonly** (`_render_v3_seo_opportunity_readonly`, L1870) | DataDive MKL **o** importer B7 HTML | ❌ No |
| `V4_listing_improvements_current_state` | Listing — Current State | **Class B readonly** (`_render_v4_current_state_readonly`, L1979) | Importer B7 HTML (skill `amazon-brand-audit`) | ❌ No |
| `V5_listing_comparison_competitor` | Listing — Side-by-Side vs Competitor | **Class B readonly** (`_render_v5_listing_comparison_readonly`, L2086) | Importer B7 HTML (skill TBD, ver §6) | ❌ No |
| `V6_growth_plan_phases` | Growth Plan en 3 fases | **Class B readonly** (`_render_v6_growth_plan_readonly`, L2245) | Seed / importer B7 (TBD) | ❌ No |

El **dispatcher** (`_render_block_editor`, L1099) mapea cada `module_id` al
renderer correspondiente. Devuelve `True` si rendereó un editor (para que el
caller no caiga al readonly de fallback) y `False` si no hay handler.

### Plan D vs Class B

- **Plan D (V1/V2)**: editor con buffer mutable en `st.session_state` —
  `_ensure_block_buffer(_v2)` hidrata el sub-dict del block una sola vez, los
  widgets leen/escriben en el buffer sin keys propias, y "Guardar" llama a
  `_commit_v1_to_disk` / `_commit_v2_to_disk` que persiste y limpia el buffer.
  Cero `st.form`, cero widget keys, cero `setdefault` adyacente.
- **Class B (V3/V4/V5/V6)**: solo render readonly. La data viaja al bloque
  vía importer (B7 HTML o DataDive). Hoy son intencionalmente readonly porque
  su shape la cierra la skill upstream, no el operador.

---

## 3. Las dos vías de entrada de data

### 3.a) Importer B7 (HTML drag-drop)

**Origen del HTML**: las skills de Ramiro `amazon-brand-audit` y
`digital-presence-audit` emiten HTMLs auditados con la convención
`data-proposal-*` definida en el contrato B7 v1.0 (`notes/sales/contrato-importer-b7-v1.md`).

**Flujo UI** (`_render_b7_importer_section`, L2595):
1. `st.file_uploader` dentro de un expander, key `b7_uploader_{pid}`.
2. `extract_blocks(html_bytes, catalog)` → `ImportReport`. Función pura sin
   side effects (ver `modules/sales/b7_importer.py` L491).
3. Preview readonly del report: 3 KPIs (`Blocks detectados` / `Warnings` /
   `Errors bloqueantes`) + 2 tablas (errors en rojo, warnings en amarillo) +
   lista compacta de blocks con badges "✓ aplicará" / "⊘ skip".
4. Si `report.ok`, se pinta `_render_b7_apply_flow` (L2748) con el banner
   "Listo para aplicar" y el botón "Aplicar merge" + confirmación 2-clicks.
5. Click #1 (`b7_apply_btn_{pid}`) → setea `ps_b7_confirm_apply_{pid}=True`
   en session_state y rerun.
6. Click #2 (`b7_confirm_btn_{pid}`) → `_execute_b7_merge_and_save` (L2833)
   ejecuta `merge_blocks(report, proposal, catalog)` → `pp.save_proposal(...)`
   → banner verde con `vN → v(N+1)` → limpia flag → `st.rerun()`.
7. Botón "Cancelar" (`b7_cancel_btn_{pid}`) siempre disponible mientras el
   flag esté pendiente.

**Qué valida `extract_blocks`** (4 códigos relevantes):
- **Errors bloqueantes** (impiden el apply):
  - `contract_version_major_mismatch` — el HTML declara `data-proposal-contract-version`
    mayor que el major soportado (B7 v1.x).
  - `no_blocks` — el HTML no tiene ningún `data-proposal-block` reconocible.
  - `module_id_unknown` — el HTML referencia un module_id que no existe en
    `_catalog.json`.
- **Warnings no bloqueantes**:
  - `coercion_failed` (no se pudo coercionar valor a integer/number).
  - `enum_unknown` (valor fuera del enum del schema → se asigna `"unknown"`).
  - `field_unknown` (field del HTML no declarado en `items_schema`).
  - `required_missing` (field requerido ausente o vacío).
  - `array_empty` (array declarado pero llegó vacío).
  - `duplicate_module_id_in_html` (mismo module_id 2+ veces en el HTML → gana
    el primero, los siguientes se ignoran con warning, fix 2026-05-22).

**Qué valida `merge_blocks`** (`b7_importer.py` L573):
- `report_not_ok` (error): si el report viene con errors, aborta sin merge.
- `target_proposal_malformed` (error): si `target_proposal.blocks` no existe
  o no es lista.
- `block_not_in_target` (warning): module_id del HTML no está en la propuesta
  target → se skipea.
- `duplicate_module_id` (warning): la propuesta target tiene 2+ blocks con el
  mismo module_id → updatea el primero y warnea.

**Contrato §6 (regla crítica)**: el merge **solo afecta `block['data']`**.
Los campos `id`, `module_id`, `proposal_id`, `is_fixed` y `copy_overrides`
del block target se preservan intactos. Esto está cubierto por el test
`TestCopyOverridesPreserved` en `tests/test_b7_importer.py`.

### 3.b) DataDive → V3 (text_input + MKL)

**Origen del .xlsx**: export estándar de DataDive `niche-*-keywords.xlsx` (MKL,
Master Keyword List).

**Flujo UI** (`_render_datadive_importer_section`, L2950):
1. `st.text_input` para el ASIN del cliente, key `dd_v3_asin_{pid}`. Default:
   best-effort vía `_extract_asin_from_proposal` (L2932), que escanea el bloque
   V4 (`current_state_url` o `asin`) buscando regex `B0[A-Z0-9]{8}`.
2. Gate: si el ASIN no matchea `^B0[A-Z0-9]{8}$`, se muestra `st.info` y se
   retorna (el uploader no aparece).
3. `st.file_uploader` (`dd_v3_uploader_{pid}`) — tipo `.xlsx`.
4. `_dd_parse_mkl_cached(uploaded.getvalue(), uploaded.name)` — wrapper
   `@st.cache_data` sobre `modules.parsers.datadive.parse_mkl`, que devuelve
   `(mkl_df, competitor_asins)`.
5. `datadive_to_v3_block(mkl_df, competitor_asins, asin_input)` — mapper puro
   en `modules/sales/mappers/datadive_to_v3.py` (función `datadive_to_v3_block`,
   constante `V3_MODULE_ID = "V3_seo_opportunity"`, umbral
   `WEAK_RANK_THRESHOLD = 30`, cap `_MAX_MISSING_KEYWORDS = 50`).
6. El report producido se entrega a **el mismo** `_render_b7_apply_flow` que
   usa B7 — reusa la confirmación 2-clicks y el save con auto-bump. El flag
   `ps_b7_confirm_apply_{pid}` se comparte (edge case si el operador tiene
   los dos expanders abiertos simultáneamente, registrado como deuda en el
   docstring de `_render_datadive_importer_section`).

**Reglas de mapeo del MKL → V3** (decisiones Lenin 2026-05-26, docstring del
mapper):
- `D1` `opportunity_score = min(launch_score / 10, 1.0)` (`None` si no hay
  launch_score).
- `D3` "missing keyword" = `current_rank > 30` **OR** `current_rank` ausente
  (NaN/None).
- `D6` `launch_score_table` y `page1_domination_chart_data` quedan `[]` en v1.
- `D8` cap interno a top 50 missing por SV descendente.

**Errores posibles del mapper**:
- `invalid_asin` (error): client_asin no matchea `^B0[A-Z0-9]{8}$`.
- `client_asin_not_in_mkl` (warning): el ASIN no aparece como columna de rank
  en el MKL (no se puede leer rank del cliente; igual emite el block).

El bloque resultante tiene exactamente el shape de
`schema.missing_keywords` del catálogo: `{keyword, sv, current_rank, opportunity_score}`.

---

## 4. Flujo operativo paso a paso

Cómo Lenin (o cualquier Sales Director con acceso a M29) genera una propuesta
de punta a punta:

1. **Abrir la sección Sales Director** → cargar la página Proposal Studio.
   `render()` (L3051) inicializa los state machines del wizard y del detail
   y muestra los tabs `📋 Mis propuestas` + `✨ Nueva propuesta`.
2. **Crear una propuesta nueva** (`tab_nuevo` → wizard step 1–3):
   - Step 1: `client_name`, `client_industry`, `language` (`en|es`).
   - Step 2: arquetipo (`launch`, `scale_seo`, `defense`, `cvr`, `custom`).
   - Step 3: revisión + "Crear propuesta" (`_do_save_proposal` L597 →
     `pp.instantiate_proposal_from_template(...)` → `save_proposal`).
3. **Abrir la vista detalle** (`_open_detail` L479 setea
   `ps_detail_active=pid` → `render` redirige a `_render_detail_screen` L2493).
4. **Importar data si aplica** (los dos expanders al tope del detail):
   - **B7**: subir HTML emitido por las skills de Ramiro → preview → apply
     2-clicks → V3/V4/V5/V6 quedan poblados según lo que traiga el HTML.
   - **DataDive → V3**: ingresar ASIN del cliente + subir MKL → apply 2-clicks →
     V3 queda poblado con las missing keywords filtradas.
5. **Editar manualmente V1 y V2** (expansibles dentro del listado de blocks):
   - Cargar buffer (idempotente), modificar widgets, click **Guardar**
     (`_save_v1_brand_overview` L1461 / `_save_v2_category_overview` L1773).
   - "Descartar" invalida el buffer sin tocar disco.
6. **Avanzar el status** (cuando aplique): `draft` → `ready_for_review` →
   `sent` → (`won` | `lost` | `archived`). Cada save bumpea version, así que
   el historial completo queda en disco.
7. **Render visible**: el debug expander de la pantalla detalle ("🔍 Ver
   propuesta cruda") muestra el JSON completo. El renderer HTML/PDF
   (S5/S6 del roadmap) **no está implementado todavía** — esto es deuda
   declarada (ver §8).

---

## 5. Reglas críticas / gotchas

### 5.1 Merge B7 afecta SOLO `block['data']`

`merge_blocks` (L573) hace overwrite quirúrgico: `updated_blocks[idx]["data"] =
copy.deepcopy(draft.data)`. Los campos `id`, `module_id`, `proposal_id`,
`is_fixed` y `copy_overrides` del block target nunca se tocan. Si necesitás
cambiar identidad de un block, NO usar el importer — editar a mano o crear un
bloque nuevo. La regla está cubierta por `TestCopyOverridesPreserved` y por
`test_b7_importer_apply_happy_path` (asserts de identity fields).

### 5.2 `save_proposal` auto-bumpea version e ignora el input

`pp.save_proposal(proposal)` (`core/proposal_persistence.py` L318) hace
`proposal["version"] = storage.max_version_for(id) + 1`. Cualquier `version`
del input se sobreescribe. El archivo en disco queda con naming
`<uuid>__v<N>.json` en `data/sales/proposals/` (PROPOSALS_DIR, gitignored).

Implicaciones:
- No hay "modo overwrite" de una versión existente — cada save es una versión
  nueva e inmutable.
- Para la última versión: `pp.get_proposal(pid)` (sin pasar version).
- Para una versión específica: `pp.get_proposal(pid, version=N)`.
- Cleanup de versiones viejas: hoy no existe job automático (ver §8 deuda).

### 5.3 Smoke manual obligatorio tras cambios en UI

Lección del **incidente "edits fantasma" del 2026-05-25**: pytest unit cubría
extract_blocks / merge_blocks / mapper como funciones puras, pero NO el path UI
de los botones "Guardar" (Plan D V1/V2) ni "Aplicar merge" (B7/DataDive). Un
cambio que rompió silenciosamente la transición widget→buffer pasó verde
porque ningún test tocaba la UI.

Estado actual:
- **El path apply (B7 + DataDive)** ya tiene cobertura E2E vía
  `tests/test_m29_ui_e2e.py` (3 tests con `streamlit.testing.v1.AppTest`,
  commit `78ba2eb`).
- **Los botones Guardar de V1/V2** siguen sin cobertura automatizada.

Regla de oro hasta cerrar esa cobertura: tras cualquier cambio en
`_render_v1_*` / `_render_v2_*` / `_commit_v*_to_disk`, hacer **smoke manual**
en la vista detalle: editar un campo en V1 y V2, guardar, refrescar la página
y verificar que el cambio quedó en disco con version bumpeada.

### 5.4 V5 readonly, shape de assets pendiente de contrato v2

`_render_v5_listing_comparison_readonly` (L2086) muestra el banner
*"V5 está fuera del contrato B7 v1.0 — la shape definitiva de los assets se
cierra en contrato v2 (post-reunión 22/05)"* (texto literal en L2127-2128).
El renderer asume triple-fallback defensivo en los assets (str pelado |
dict con `url|image_url|href` | otro). La propuesta de shape canónica vive
en `notes/modules/M29-V5-shape-proposal.md` (commit `0dcf8c3`, 2026-05-30).

**No construir editor V5 ni hardcodear shape de asset hasta que la reunión
con Ramiro (30/05) cierre el contrato v2.**

### 5.5 Templates desactualizados vs catálogo *(verificar)*

El catálogo tiene **37 módulos** (8 fixed + 6 core_variable + 23 Tier 2-3).
La única propuesta poblada en disco (`01fbf5c2-…__v12.json`, `client_name`
literal `_DEMO_AgencyOS`) tiene **20 blocks** (F1-F8 + V1-V6 + V17-V22). Los
4 templates en `data/sales/_templates/*.json` (`launch-new-brand.json`,
`scale-seo-gap.json`, `defense-brand-attack.json`, `cvr-listing-driven.json`)
tienen **0 blocks cada uno** — son placeholders vacíos.

Esto significa que crear una propuesta desde wizard hoy probablemente
arranca con una shell vacía y se puebla 100% a mano + import. Hay que
**verificar**:
- Si el wizard espera que los templates traigan blocks pre-llenos o si la
  intención es que el bootstrapping se haga desde el catálogo.
- La discrepancia entre la frase coloquial "20 vs 35 blocks" usada en
  planning y los números reales del repo (20 demo vs 37 catálogo).

### 5.6 Flag de confirmación compartido entre B7 y DataDive

El flag de session_state `ps_b7_confirm_apply_{pid}` se usa tanto en
`_render_b7_apply_flow` (B7) como en `_render_datadive_importer_section`
(DataDive reusa el mismo apply flow). Edge case conocido: si el operador
deja los dos expanders abiertos con report válido y le da "Aplicar merge"
en uno, el otro también muestra "Confirmar aplicación" hasta clickear o
cancelar. Documentado en el docstring del DataDive importer, deuda de baja
prioridad.

---

## 6. Tests

### 6.1 Tests unit puros (no UI)

- `tests/test_b7_importer.py` — 4 grupos de tests sobre `extract_blocks` y
  `merge_blocks`:
  - `TestContractVersionMismatch` — major version 2 emite error;
    `1.5` pasa; falta de versión cae al default `"1.0"`.
  - `TestNoBlocks` — HTML vacío / HTML con divs no relacionados emite error
    `no_blocks`.
  - `TestDuplicateModuleIdInHtml` — duplicate emite warning (no error),
    primer block gana, 3 duplicados → 2 warnings.
  - `TestCopyOverridesPreserved` — merge preserva `copy_overrides` y los
    identity fields (`id`, `proposal_id`, `is_fixed`, `module_id`).
- `tests/test_datadive_parser.py` — parser puro DataDive (no inspeccionado en
  detalle en este SOP — *verificar si cubre los 3 parsers `parse_mkl`,
  `parse_competitors`, `parse_rank_radar` o solo MKL*).
- `tests/test_datadive_to_v3_mapper.py` — 9 tests sobre el mapper:
  ASIN inválido / cliente no en MKL / filtra solo weak ranks / excluye
  strong ranks / opportunity_score clamped a 1.0 / MKL vacío / sort por SV
  desc / cap a top 50 / integración con merge_blocks.
- `tests/test_proposal_schema.py` y `tests/test_proposal_persistence.py` —
  schema y CRUD persistencia.
- `tests/test_inicio_badge.py` — guarda la invariante del badge dinámico
  del módulo Inicio.

### 6.2 Tests E2E UI (los que cierran la deuda del 2026-05-25)

- `tests/test_m29_ui_e2e.py` — 3 tests con `streamlit.testing.v1.AppTest`:
  - `test_b7_importer_apply_happy_path` — upload v3v4 → 2-clicks → V3
    overwriteado con `moringa powder organic` + version 12→13 en disco +
    identity preservados.
  - `test_b7_importer_duplicate_warning_does_not_break` — fixture duplicate
    → warning visible en dataframe + apply habilitado + sin crash.
  - `test_datadive_v3_apply_path` — text_input ASIN + parser monkeypatched →
    apply 2-clicks → V3 prefilled con `missing kw alpha` y `missing kw beta`.

Patrón clave del harness E2E (documentado en el header del archivo de tests):
AppTest 1.43.2 NO expone `file_uploader` interactivo, así que se monkeypatcha
`streamlit.file_uploader` para devolver un `_FakeUploadedFile`. Sigue siendo
E2E porque `extract_blocks` / `merge_blocks` / `save_proposal` corren reales
y los botones se clickean vía AppTest. `PROPOSALS_DIR` se redirige a
`tmp_path` para aislamiento de disco.

### 6.3 Cómo correr

```bash
pytest tests/ -q
# Estado al 2026-05-28: 98 passed in ~5s
```

Si algún test falla tras un cambio en `proposal_studio.py`, `b7_importer.py`
o `datadive_to_v3.py`, **no marcarlo skip** para forzar verde: investigar el
fallo y fixearlo o reportarlo. Ese fue el camino que llevó al incidente
"edits fantasma".

---

## 7. Deuda abierta priorizada

1. **Editor manual de V5** — depende del cierre del contrato v2 con Ramiro
   el 30/05. Propuesta de shape ya escrita en
   `notes/modules/M29-V5-shape-proposal.md`. Alcance del editor estimado:
   una sesión completa de implementación + tests post-aprobación.
2. **Cobertura E2E de los botones Guardar de V1 y V2** — el harness AppTest
   ya está montado para B7/DataDive; portear el mismo patrón a V1/V2 cierra
   completamente la deuda del incidente 2026-05-25.
3. **Refactor a Class B genérico (N=4)** — los 4 readonly renderers
   (V3/V4/V5/V6) repiten estructura (header + caption + banner + grupo de
   campos + JSON fallback expander). Hay espacio para un `_render_class_b(block,
   layout_spec)` que reduzca duplicación. Bajo riesgo, alto beneficio cuando
   entren más Tier 2-3 readonly.
4. **Cleanup de versiones viejas** — `save_proposal` deja un `__v<N>.json`
   por cada save. Sin job de cleanup, una propuesta editada agresivamente
   genera N archivos. Decisión pendiente: ¿tope automático (ej: keep last 10)
   o cleanup manual?
5. **Templates** — *verificar* si los 4 archivos en `_templates/` deben tener
   blocks pre-llenos. Hoy están vacíos y el wizard probablemente arma la
   propuesta sin ninguna estructura por arquetipo. Si esto es deuda real, hay
   que poblar los templates desde el catálogo (filtrando módulos por
   `applicable_archetypes`).
6. **Renderer HTML/PDF** — S5/S6 del roadmap original. Hoy la única vista de
   la propuesta es el JSON crudo del debug expander. Es la pata pendiente
   para que la propuesta sea efectivamente "shippable" al cliente.
7. **Imágenes V5 automáticas** — post-v2 contract, las skills de audit
   podrían entregar URLs directamente; si entregan archivos binarios o
   capturas, habría que decidir storage (S3 / Supabase storage / etc.). Fuera
   de scope hasta tener v2 firmado.
