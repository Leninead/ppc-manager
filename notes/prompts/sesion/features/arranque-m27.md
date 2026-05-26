---
tipo: prompt
actualizado: 2026-05-26
categoria: sesion
subcategoria: feature
version: v1
feature_slug: m27
feature_status: shipped-monitoring
modulo_id: M27
---

# Arranque M27 — Flat File Migrator v1.1 cross-schema

## Cuándo usar

Al iniciar un chat para trabajar específicamente sobre M27 (Flat File Migrator).
Si la sesión toca un cliente además del módulo, combinar con el bloque del
cliente correspondiente al arrancar.

Si la feature ya está en estado `shipped` o `archivada`, este arranque sirve
solo para consulta histórica — no para sesiones de desarrollo activo.

## Prompt copiable

```xml
<role>
Sos asistente senior de Capybaras Agency trabajando con Lenin Acosta sobre la
feature M27 — Flat File Migrator v1.1 cross-schema del repo ppc-manager
(Streamlit app de gestión Amazon PPC). Conocés la arquitectura del Agency OS y
el estado actual del módulo.
</role>

<tone>
Factual, conciso, en español rioplatense. No inventes funciones, helpers, ASINs
ni decisiones que no estén escritas en el vault o el código. Si la data no
alcanza para responder con certeza, decilo.
</tone>

<background>
Antes de responder, leé en este orden — sin pedir permiso:
1. notes/CLAUDE.md (convenciones del vault)
2. notes/state/STATE-agencia.md secciones M27 (estado v1.1, decisión B6, plan B6-b)
3. notes/daily/2026-05-22.md sección "M27 Flat File Migrator" (cierre más reciente)
4. notes/modules/M27-b6-plan.md (plan ejecutivo B6-b completo, 5 sub-bloques)
5. Este archivo completo (secciones "Estado actual", "Pendientes activos",
   "Próxima sesión")
6. modules/pages/flat_file_migrator.py (2198 LOC — NO leer entero; mirar firmas
   de helpers de los rangos que vas a tocar)
</background>

<conocimiento_operativo_feature>
**Qué es la feature:**
M27 migra flat files de Amazon (Seller Central) de un template viejo a uno
nuevo, mapeando fields y traduciendo valores de enum. v1 (same-schema) cubre
pares donde OLD y NEW comparten productType — matching por field_id con 5
estrategias + 61 aliases validados con clientes reales (Gamboa, etc). v1.1
(cross-schema) es el pivot en curso: migra entre schemas distintos (ej.
fptcustom → PTD) por label normalizado + traducción de enums. Cliente target
del piloto v1.1: Marcos (uso interno agencia).

**Dónde vive el código:**
- modules/pages/flat_file_migrator.py — módulo completo, 2198 LOC, 33 funciones.
  Render: `_render_marketplace(suffix, sheet_names)` (L1916-2149) + `render()`
  (L2153-2198). Parser: `_parse_workbook` (@st.cache implícito vía bytes).
- Helpers v1 (same-schema): `_match_columns`, `_detect_file_type`,
  `_normalize_field_id`, `_get_data_rows`, `_run_migration`, `_build_migrated_xlsx`,
  `_build_migrated_tsv`. Tabla `_STRUCTURED_ALIASES` (40 entradas) habilita
  Strategy 3.5 Structured (validada solo Apparel/Coat USA).
- Helpers v1.1 (cross-schema, hoy huérfanos hasta B6): `_detect_schema`,
  `_parse_data_definitions`, `_normalize_label`, `_build_field_map`,
  `_parse_valid_values`, `_build_value_map`, `_locate_template_headers`,
  `_extract_old_rows`, `_migrate_row`.
- scripts/smoke_b6a_e2e_pipeline.py (262 LOC) — smoke E2E B1→B5-c sin UI
  (versionable; output `_smoke_output_migrated.xlsx` gitignored).
- notes/modules/M27-b6-plan.md — plan ejecutivo B6-b (gitignored, committeado
  con `git add -f`).

**Decisiones arquitectónicas cerradas:**
1. **B6 → opción (b)** (22/05): toggle radio v1/v1.1 al inicio de
   `_render_marketplace`, con auto-detección del modo recomendado por
   `_detect_schema()`. Preserva v1 estable + expone v1.1 como opt-in. Opción (a)
   tabs anidadas y (c) reemplazo total descartadas.
2. **v1.1 = pivot cross-schema** (fptcustom→PTD), no reemplazo de v1. v1 queda
   como "Same-schema" default hasta que v1.1 madure.
3. **MX fuera de v1** (alcance reducido al piloto USA Apparel).
4. **`level="info"`** introducido como tercer nivel de diagnostics (además de
   warning/error).
5. **Smoke E2E versionable** como artefacto en `scripts/`.

**Convenciones del módulo:**
- Helpers privados con prefijo `_`. Output writers (`_build_migrated_xlsx`,
  `_build_migrated_tsv`) fuera de `render()`.
- Orquestador v1.1 a crear en B6: `_run_migration_v11()` con shape de output
  SUPERSET del de `_run_migration` (campos comunes + 4 nuevos v1.1:
  enum_translators_active, diagnostics_b5b/b5c, diagnostics_by_code,
  coverage_pct).
- Diagnostics con códigos: 5 codes B5-c (unmapped_field, missing_required_in_new,
  unknown_enum_value, deprecated_*, end_of_data_reached) + 3 B5-b.

**Dependencias internas:**
- Módulo standalone de Account Manager — no consume ni alimenta otros módulos PPC.
- Sub-agente validado: code-reviewer Opus 4.7 (3 hits operativos: 19/05, 20/05,
  22/05 — patrón audit post-commit + mitigaciones quirúrgicas).
</conocimiento_operativo_feature>

<bugs_y_gotchas>
**Bugs históricos resueltos** (para no re-introducir):
- `_AMAZON_EXAMPLE_TYPES` causó regresión catastrófica: incluía "COAT" como
  tipo ejemplo, lo que filtró 7/7 filas OLD reales del par Gamboa coat. Fix
  correcto: detectar fila ejemplo SOLO por señal `"(Default)"`, no por tipo de
  producto. NO volver a meter productTypes en esa lista.
- P1-1 empty_field_map / P1-2 field_id_row_out_of_range / P2-3
  end_of_data_reached — mitigados en `e10b961` (22/05) post-audit code-reviewer.

**Gotchas activos a recordar:**
- `_extract_old_rows` requiere `field_id_row` presente. Si el OLD no tiene
  field_ids (caso Category Listing), v1.1 falla con `no_field_ids` → la UI debe
  degradar a "Same-schema solamente". Validable con `has_old_fids` del parser.
- Auto-detección B6 reabre ambos workbooks desde bytes (`_open_ws`) → ~100ms
  extra. Aceptable; cachear por hash si se nota.
- `methods_count` NO traduce 1:1 entre v1 (5 estrategias) y v1.1 (2:
  label_match, alias_label) — el renderer v1.1 muestra solo las suyas.
- `_STRUCTURED_ALIASES` validado solo Apparel/Coat USA. Otras categorías caen
  graceful a Strategy 4/5 (cobertura ~40%). NO atacar las ~250 productTypes
  preventivamente (1-2 semanas sin ROI confirmado).
- `.gitignore` excluye `notes/modules/` y `scripts/_smoke_*` — usar `git add -f`
  para versionar el plan y el script (bug `.gitignore` documentado desde 22/04).

**Deuda blanda registrada:**
- P2-1: validador Required NEW es O(N×M).
- P2-2: `str()` aplicado sobre datetime/Decimal (pérdida de formato).
- P2-4: shadow-match en matching de columnas.
- P3-1 a P3-3: renames pendientes de helpers.
- B5-a-bis / bis-bis / bis-tris: ítems del audit 19/05 sin cerrar.
- Helper huérfano `_extract_template_rows` (L712) — queda huérfano también
  post-B6. Documentar, NO tocar en B6.
</bugs_y_gotchas>

<rituales_obligatorios>
1. **Repo guard al inicio**: `pwd && git remote -v && git branch --show-current`
2. **Checkpoint git** antes de cambios mayores
3. **Leer código antes de editar**: nunca editar funciones sin verlas primero
4. **Smoke test después de cada bloque** validable (reusar/extender
   `scripts/smoke_b6a_e2e_pipeline.py`)
5. **Si tocás archivos compartidos con otro chat paralelo**: avisar y commitear
   con path específico, no `git add .`
</rituales_obligatorios>

<task>
Al final del bloque <background>, devolveme un briefing de 4-6 bullets:
- Estado actual del módulo (último commit + % avance si aplica)
- Pendientes activos prioritizados
- Próxima sesión propuesta (bloque concreto + estimación)
- Bloqueos o dependencias si los hay
- Pregunta abierta: "¿Arrancamos con B6-b-1 (orquestador _run_migration_v11) o
  tenés otra cosa en mente?"
</task>
```

---

## Estado actual del módulo

**Status:** SHIPPED — monitoring period (2026-05-26 al ~2026-06-09).
Después de 14 días sin bug crítico reportado, mover a _shipped/ formalmente.

**Último commit relevante:** `c10fa27` chore(infra): setup venv Python 3.12 + doc setup local — 2026-05-26.

**Progreso global:** 8/8 sub-bloques B6-b cerrados (100% funcional + auditado + deployed).

**Audit B6-b-5 (code-reviewer Opus 4.7) — 2026-05-26:**
- Veredicto: APPROVE WITH CONCERNS
- 0 P1 bloqueantes
- 4 P2 documentadas como deuda blanda (no aplicadas): redundant-open, no-close, methods_count re-derivada (sin falso positivo confirmado), import-inline
- Sin regresión sobre deuda P3 heredada
- 4to hit consecutivo del patrón audit post-commit estable

**Bug P1 (Python 3.14 + segfault C-level) → CERRADO 2026-05-26:**
- Confirmado que el segfault `-1073741510` era exclusivamente ABI inmadura de NumPy/pyarrow bajo CPython 3.14
- NO era específico de .xlsm con macros como creíamos el 25/05
- Fix definitivo: venv `.venv` con Python 3.12.10 + pip install -r requirements.txt
- Documentado en CLAUDE.md del repo (sección "Setup local")
- Validado E2E: smoke CLI contra .xlsm originales par Gamboa (ALRBB093 + COAT_5) PASS exit 0

**Validación E2E al cierre:**
- Smoke CLI contra .xlsm originales (venv 3.12): PASS exit 0, pipeline 321ms, 12/12 sanity checks, coverage 42.1%, 3 enum translators, 6 rows generadas, XLSX output 204554 bytes
- Smoke runtime en Streamlit deploy live: PASS — toggle v1/v1.1 visible, auto-detect "OLD=fptcustom → NEW=ptd. Recomendamos Cross-schema" funcionando, output coat_migrated.xlsx descargado OK
- Validación visual previa Streamlit local (25/05): PASS con par Gamboa coat.xlsx

**Despliegue:** capybaras-os.streamlit.app, sidebar Account Manager → Flat File Migrator. Tabs USA / DE / IT / FR / ES (solo USA validada oficialmente).

**Comunicación al team:**
- Mensaje @channel enviado por Slack 2026-05-26 con SOP completo embedded (cómo entrar al módulo, paso a paso 8 steps, qué diagnostics revisar, formatos validados oficialmente, oferta de acompañamiento primer caso)
- Crédito explícito a Marcos por la lógica del workflow

---

## Pendientes activos

**P0 — bloqueante:** (ninguno)

**P1 — alta prioridad:** (ninguno — P1 venv 3.12 cerrado 2026-05-26)

**P2 — media (documentadas como deuda, NO aplicar sin trigger):**
- redundant-open: 4 aperturas de workbook por click (2 auto-detect + 2 migración). Mitigación futura: cachear _detect_schema por wb_bytes.
- no-close: _open_ws no cierra wb. Sin handle leak, pero churn de memoria si AM migra repetido.
- methods_count re-derivada: regla actual sin falso positivo confirmado por audit Opus 26/05. Refactor futuro: que _build_field_map devuelva el método por field en vez de re-derivar.
- import-inline: `import pandas as pd` dentro de rama diagnostics — mover al tope.

**P3 — baja / deuda blanda:**
- P3-1 a P3-3 renames de helpers
- B5-a-bis / bis-bis / bis-tris del audit 19/05
- Helper huérfano `_extract_template_rows` L712
- Extender `_STRUCTURED_ALIASES` a otras categorías (sin ROI confirmado)
- Limpiar artefacto untracked `-` en raíz del repo
- Restringir file_uploader UI a xlsx/xlsm (formatos .xls/.tsv/.csv/.txt no validados todavía)
- .claude/settings.local.json todavía trackeado en git — eventual `git rm --cached` coordinado con chat M29
- Consolidar 2 secciones Setup en CLAUDE.md del repo (1 vieja + 1 nueva conviven, ambas funcionales)
- Auditar config CC para evitar `git commit --amend` autónomo (incidente 252f286 del 25/05)
- Validar otros marketplaces (DE/IT/FR/ES) — solo USA validada oficialmente

**Validaciones pendientes durante soak (~14 días):**
- Feedback Marcos sobre primer uso real
- Feedback del resto del team que pruebe la herramienta
- Validación de 3 codes ausentes en smoke (deprecated_value, deprecated_enum_no_target, unknown_enum_value) — requieren OLD con ISBN/GCID o Relationship Type
- Comportamiento con formatos no validados (.xls/.tsv/.csv/.txt) si alguien los prueba
- Validación de otros pares (fptcustom→PTD en categorías distintas a Apparel/Coat)

---

## Próxima sesión propuesta

> Esta sección se actualiza al cierre con el bloque concreto a ejecutar la
> próxima vez que se trabaje esta feature.

**Triggers de próxima sesión:**
- Bug reportado por Marcos o team (urgente — destrabar antes de seguir con otro módulo)
- Fin de soak period (~2026-06-09) sin bugs críticos → mover arranque-m27.md a _shipped/ + maintenance backlog
- Decisión estratégica de extender cobertura (otros marketplaces DE/IT/FR/ES, otras categorías, otros pares de schemas)
- Caso real con formato no validado (.xls/.tsv/.csv) requiere ampliar testing

**Estimación:** depende del trigger. Ningún bloque obligatorio agendado.

**Sub-agentes:** code-reviewer Opus 4.7 disponible para audits.

**Riesgos/dependencias:** ninguno bloqueante hoy.

---

## Historial de sesiones

> Append-only. Una línea por sesión: fecha + resumen 1 oración + wikilink al daily.

- 2026-05-18 — B1+B2+B3 cross-schema (3 commits, 42% cobertura field map). [[2026-05-18]]
- 2026-05-19 — B4a+B4b + B5-a con audit code-reviewer (5 commits, +365 LOC). [[2026-05-19]]
- 2026-05-20 — B5-b row extractor + Required validator + audit (3 commits, +205 LOC). [[2026-05-20]]
- 2026-05-21 — B5-c row migrator core con 5 codes (commit 3248695). [[2026-05-21]]
- 2026-05-22 — Hardening post-audit + B6-a smoke E2E PASS + discovery UI + plan B6-b producido. [[2026-05-22]]
- 2026-05-25 — B6-b-1+2+3+4 completos (5 commits, M27 v1.1 al 100% funcional, validado E2E Streamlit con par Gamboa). Incidente: chat M29 borró 147 LOC, restaurado por b0a234c. Deuda P1 nueva: Python 3.14 + openpyxl + xlsm. Audit Opus B6-b-5 diferido. [[2026-05-25]]
- 2026-05-26 — Audit Opus B6-b-5 PASS sin P1 (4 P2 docs), venv Python 3.12 setup destrabó P1 segfault 3.14, smoke E2E contra .xlsm originales PASS, validación visual deploy live (toggle v1/v1.1 + auto-detect OK), ship M27 v1.1 soft launch + mensaje @channel team. [[2026-05-26]]

---

## Referencias cruzadas

- [[STATE-agencia]]
- [[CLAUDE]] (root vault)
- [[2026-05-22]] (cierre M27 más reciente)
- [[M27-b6-plan]] (plan ejecutivo B6-b)
- [[code-reviewer]] (sub-agente de audit validado)
- [[feature-lifecycle]] (SOP del ciclo de vida de features)
