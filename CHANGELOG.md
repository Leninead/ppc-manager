# CHANGELOG — Agency OS Capybaras

Registro de cambios, mejoras y decisiones de diseño del PPC Manager.

---

## [Unreleased]

### Added — Integración API DataDive + Análisis IA en M21 (2026-09-01)
- **`core/datadive.py`** — cliente REST read-only de la API de DataDive (`GET /v1/niches` paginado, `GET /v1/niches/{id}/keywords`, `GET /v1/quota`) con retry/backoff honrando `Retry-After` (espejo de la semántica de `core/ads_api`), errores tipados en español y `keywords_to_mkl_df()` que normaliza el JSON al shape canónico de `parse_mkl` (relevancy 0-1 → escala UI ×10, `suggestedBid.median` centavos → dólares, `asinRanks` null → NaN, Launch Score = 0.0 porque el endpoint no lo expone). La key se lee de `DATADIVE_API_KEY` (env) con fallback a `st.secrets["datadive"]`; sin key la feature queda apagada y el módulo es idéntico a antes.
- **M21 tab 1 — fuente API** — radio `Archivo | API DataDive` (solo con key configurada), selector de niche ordenado por `latestResearchDate` con label `nicheLabel · marketplace`, botón "Traer de DataDive" con refresh targeted del cache (`_api_mkl.clear(niche_id)`). Cache compartido de proceso `@st.cache_data(ttl=3600)`. El DataFrame entra al tab por las mismas variables que un archivo subido — filtros, gaps y export intactos.
- **Agente IA `ai/agents/datadive/`** — primer agente de la plataforma `ai/` en main. Analiza la MKL (clusters de intención, gaps priorizados, síntesis canónica) sobre el top 120 por SV vía `core/ai_tab`, con chat flotante de repreguntas (`core/ai_chat`) montado fuera de los tabs.
- **`scripts/smoke_datadive_api.py`** — smoke read-only con key real: quota, niches, contrato de /keywords con distribución de relevancy, y sondas a `/roots` y `/ranking-juices` (candidatos a Launch Score en fase posterior).

- **M21 tabs 2 y 5 — fuente API** — con Fuente en API DataDive, el tab Competitors carga automáticamente los competidores del niche traído en el tab 1 (`GET /v1/niches/{id}/competitors`, normalizado a los labels del export con `competitors_to_df`; validado 9/9 ASINs idénticos al xlsx real), y Competitor Intel compara dos niches elegidos por selector (`Traer ambos de DataDive`). El análisis IA del tab 1 suma un documento de competidores (con la mediana del niche) cuando hay datos, de cualquiera de las dos fuentes.
- **Launch Score sostenible sin vigilancia** — la réplica de la fórmula deja de ser un pasivo a monitorear, con tres redes: (1) `scripts/check_launch_score_drift.py` corre en CI —stage `Launch Score drift`, en cada build y por cron semanal que no deploya— y **no necesita credenciales** porque el bundle del frontend y el spec de DataDive son públicos; marca UNSTABLE, nunca rompe el build. (2) `_launch_score_of` usa el campo oficial (`launchScore`) apenas DataDive lo exponga, así el fix definitivo se aplica solo. (3) `launch_score_drifted` audita contra cada export por archivo que suba el AM (0 falsos positivos sobre las 419 filas del export real), como respaldo — con el modo API por default los archivos casi no se suben, así que no alcanza sola.
- **Launch Score vía API** — el endpoint no lo expone, pero la fórmula vive en el bundle público del frontend de DataDive: `round(SV × 0.003 / relevancy)` si relevancy ≥ 0.4 ("estimated weekly sales needed to reach page one"). `keywords_to_mkl_df` la replica (`_launch_score`, con el redondeo de `Math.round`): validada **419/419 exacta** contra el export real. El MKL por API queda idéntico al export en todas las columnas. Semántica corroborada por el KB oficial de DataDive (jul-2026); el smoke incluye un **tripwire de drift** (verifica la fórmula en el bundle vivo y si `launchScore` apareció en el spec oficial).
- **M21 tabs 3 y 4 — Rank Radar por API (fase 2)** — selector de rank radar (46 de la org) + rango 30/60/90 días → serie diaria de rank orgánico server-side vía `GET /v1/niches/rank-radars[/{id}]`, normalizada al shape de `parse_rank_radar` (`rank_radar_to_df`: Search Term/SV/Relevance/Median Rank + columnas fecha). Reemplaza el hack de snapshots en session_state; el tab 4 reusa el radar traído para volatilidad + cruce SQP.
- **Chat con tools MCP de DataDive (fase 3)** — el agente `datadive` declara `tools: datadive` en su frontmatter y las repreguntas del chat viajan con `tools:["datadive"]` + `max_turns 8` al ai-provider, que monta un MCP server in-process con 5 tools read-only (list_niches, get_niche_keywords, get_niche_competitors, list_rank_radars, get_quota) con resultados truncados. El análisis sigue determinista; solo el chat es agéntico. E2E verificado contra el provider vivo (niches y radars reales). Requiere capybaras-ai-provider ≥ rama `feat/datadive-mcp-tools` con `DATADIVE_API_KEY`.

### Fixed
- **Robustez ante uploads inválidos** — un .xlsx corrupto o un archivo renombrado ya no vuelca traceback: `_parse_upload` captura el error de cualquiera de los 5 uploaders (MKL, Competitors, Rank Radar ×2, Competitor Intel) y muestra un mensaje claro. Un export válido pero equivocado (p.ej. Competitors en el uploader de MKL) parsea 0 SV y dispara una advertencia en vez de mostrar una tabla vacía sin explicación. Casos verificados en la app real: archivo corrupto, archivo equivocado, mismo niche vs sí mismo en Competitor Intel, doble-click en Traer, niche/radar/competitors vacíos, radar recién creado sin datos.
- **`list_niches` dedupea** — el endpoint `/v1/niches` declara paginación pero devuelve el set completo en cada página (medido: 6 páginas idénticas de 287 niches): el cliente dedupea por `nicheId` y corta apenas una página no aporta ids nuevos (antes: 6 requests y 1.722 filas con duplicados).

### Changed
- **Análisis IA de DataDive — prompt, contrato de datos y schema reescritos** tras una auditoría del output real (niche Coffee Thermos, ASIN challenger real, cifras cruzadas fila por fila). Cambios y su efecto medido en una corrida real posterior:
  - `ai/agents/_shared/chat.md` ahora declara que sus reglas rigen **solo los turnos de chat**: se concatenaba también al system del análisis, así que sus topes ("máximo 100 palabras", "3 bullets", `**negrita**`) contaminaban los campos del schema — y esa negrita salía literal en pantalla. Afecta a los tres agentes.
  - `launch_score` documentado como **costo de entrada** (más alto = más caro rankear), no como puntaje; `relevance` con las anclas reales del dominio (alta ≥3,0, no ≥7,0); `sugg_bid` con prohibición explícita de inventar bids, ACoS o presupuestos sin conocer precio y CVR del cliente.
  - **Gaps redefinidos**: ahora incluyen las filas donde el ASIN rankea pero está enterrado fuera de página 1, no solo donde no aparece. Eran las más baratas de atacar y el schema las excluía por completo (verificado: 7 de 10 gaps de la corrida nueva son de este tipo; antes, 0).
  - **Prioridad de clusters = atacabilidad, no tamaño**, y el orden del array es el orden de ataque: se acabó la contradicción de marcar "alta" al bloque más grande mientras la síntesis decía no atacarlo. Todos los row_ids se asignan a exactamente un cluster (verificado 120/120, 0 duplicados) con un cluster explícito de ruido.
  - **Schema que obliga a la decisión de PPC**: `match_type` por cluster, `via` (PPC_AHORA / LISTING_PRIMERO / NO_ATACABLE) y `confianza` por gap, `urgency` como enum, y los topes que el prompt enunciaba ahora se hacen cumplir (`maxItems`). Las acciones de la semana pasaron de ser solo de listing a incluir qué llevar a campaña y con qué match type.
  - **Muestreo con cupo para la cola** (`select_keywords`: 90 por SV + 30 por relevancia bajo el corte): el corte puro por SV dejaba afuera el long-tail barato y sesgaba el juicio hacia "niche caro". En la corrida nueva, los tres gaps más accionables salieron de la cola.
  - **Caveat de calidad de datos**: un ASIN tipeado que no está en el dive dejaba `mi_rank` vacío en las 120 filas y el agente emitía gaps sobre evidencia inexistente; ahora eso se declara y los gaps van vacíos.
  - El render muestra las cifras que las razones citan (relevance, launch_score, mi_rank), numera los clusters por orden de ataque y pinta `match_type` y `via`.
- **El chat responde sin esperar al análisis** — un agente con tools (`tools:` en su frontmatter) ya no contesta el mensaje enlatado "el análisis todavía está corriendo": abre su propia sesión y responde de verdad, porque sus tools no necesitan el análisis (p.ej. "¿cuánta cuota queda?"). Cuando el análisis termina, la sesión del análisis toma el relevo para las repreguntas con contexto de filas. Los agentes sin tools mantienen el comportamiento anterior. Verificado en vivo: pregunta contestada en 7s con datos reales (`resumed=False` en el log) mientras el análisis seguía corriendo.
- **Caption del niche traído por API** — muestra fecha y hora (UTC) del último dive.

### Fixed
- **Tab 5 Competitor Intel crasheaba al subir ambos MKL** — `_parse_mkl` retorna una tupla y el tab la asignaba directo (`AttributeError` pre-existente; el tab nunca llegó a correr). Además la clasificación de Gap buscaba columnas "rank" que el shape MKL no tiene (todo daba "Ninguno"): ahora la presencia en cada niche la decide el indicador del outer join. El default del filtro de gap ya no explota cuando ese valor no está entre las opciones.

### Fixed
- **`parse_mkl` roto con exports frescos de DataDive** — el export actual (2026-08) insertó la columna "Type" y corrió todo el layout; el parser mapeaba por posición fija y dejaba SV=0 en todas las filas (tab 1 vacío con el filtro default). Ahora mapea columnas por nombre de header con fallback al layout posicional legacy, y lleva la relevancy fraccional 0-1 de los exports nuevos a la escala UI 0-10. Verificado E2E con el export real SEVEN_SERUM: 419 keywords parseadas (antes 0).

### Tooling — Account Health setup (2026-05-06)
- **Skills nuevos (2):**
  - `data-persistence-standard.md` — convenciones bloqueadas de persistencia para todo el Agency OS. Estructura paths `data/<area>/<cliente>/<modulo>/`, naming `YYYY-WW.parquet`, schemas evolutivos en `data/_schemas/`, API mínima de `core/persistence.py` con 10 helpers, migration path Parquet→SQLite→Postgres, `.gitignore` por defecto para datos cliente.
  - `account-health-standard.md` — convenciones nueva sección Account Health: paleta 6 severidades unificadas (crítico/importante/saludable/menor/info/logístico), terminología bilingüe Amazon (~40 términos en inglés sin traducir), conceptos has_backup/aging/AIS, header con emoji 🏥, naming Excel exports `{Cliente}_{Modulo}_{Periodo}.xlsx`.
- **Agentes nuevos (2):**
  - `data-persistence-specialist.md` (Opus 4.7, color violet) — dueño de `core/persistence.py` y `data/` schemas. NO construye módulos enteros, coordina con `html-to-streamlit-porter` o `ppc-module-builder`.
  - `html-to-streamlit-porter.md` (Opus 4.7, color cyan) — porter de HTMLs standalone a módulos Streamlit. 6 fases obligatorias: análisis estructural, mapeo HTML→Streamlit, coordinación con persistence specialist, implementación, integración router, validación end-to-end.
- **Model fixes — issue AGENT-001 cerrado:**
  - Promociones a Opus 4.7 (lógica pura): `ppc-module-builder`, `code-reviewer`, `atom11-specialist`.
  - Snapshot fix Sonnet 4.5 estable: `excel-export-builder`, `ui-designer`, `testing-agent`, `client-onboarding`.
  - Sin cambios (ya estaban correctos): `sop-writer`, `client-notes-updater`.
- **Convención de modelos del repo formalizada**: Opus alias estable para lógica pura, Sonnet snapshot fijo para implementación, Haiku snapshot fijo para markdown.
- **Setup motivado por integración futura**: 3 HTMLs del compañero Marcos (Pricing Dashboard v3, SKU Progress Report v4, Flat File Migrator) van a portearse a la sección Account Health en próximas sesiones, usando estos skills/agents como infra base.

### Added
- **Variation Builder (M26)** — módulo nuevo en Account Manager. Generador de flat files Amazon con variaciones (parent + N children). 913 líneas, parser dinámico soporta hasta 220 columnas. Agrupa por variation_theme (Sabor, Nombre del Tamano, Scent, FlavorName-SizeName, Tamano del Sabor, Nombre del Patron). Preserva macros VBA y 10 hojas del template. v1 solo MX (MXN). Tested end-to-end con Pet Food real.
- **Gamboa Generator (M25)** — módulo nuevo en Account Manager. Reportes HTML integrales combinando SQP mensual + BR semanal. Dashboard interactivo con filtros runtime, agregaciones por mes, comparación WoW. Categorización persistente de keywords por cliente. 5 archivos: `modules/gamboa/__init__.py`, `parsers.py` (421L), `generator.py` (278L), `template.html` (874L/64KB), `modules/pages/gamboa_generator.py` (383L).
- **Campaign Builder v2.0 — Sprint 1: SBV/SBH rewrite** — nuevo flujo 4-pasos para crear campañas Sponsored Brand 2026. Selector SBV (video) vs SBH (headline). Brand Entity ID obligatorio. Video Asset ID (SBV) / Brand Logo Asset ID + Logo Crop (SBH). 29 columnas bulk SB 2026. Validaciones estrictas bloqueantes. Nombre Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder). Parsing de Plan de Acción como input. Testing: SBV end-to-end ✅.

### Fixed
- **Bulk Amazon 2026 compliance** — incrementadas columnas de 30 a 31. Agregado helper `_fila_vacia_bulk()` en `campaign_builder.py` para generar filas con todos los campos. Validación en Batch ID `cee6c2f5-520f-45d2-b769-c70f49e95776` (21/04/2026, flujo asíncrono).
- **Streamlit Markdown LaTeX gotcha** — patrón `**${variable}**` en `st.info/markdown/error/warning/success` rompe render (Streamlit interpreta `$` como delimitador LaTeX). Fix: escapar con `\\$` o envolver negrita alrededor de frase completa. Aplicado en 3 líneas de `modules/pages/campaign_builder.py` (L245, L480, L896).

### Changed
- `modules/pages/campaign_builder.py` — rewrite `_render_sb()`: 864 → 1121 líneas (+257 netas). Nuevos helpers: `_SB_COLS_2026` (29 cols), `_sb_row_factory()`, `_build_sb_bulk_rows()`. Flujo SBV vs SBH con campos específicos por tipo.

### Documentation
- `CLAUDE.md` — Sesión 2026-04-23 documentada con detalle técnico de Sprint 1, bugs conocidos (sub-agent alucinaciones, LaTeX gotcha), decisiones de arquitectura.
- `modules/pages/CLAUDE.md` — M10 Campaign Builder reescrito con helpers SB 2026 y contrato con M11. M25 Gamboa Generator agregado.
- `SOP_Uso_AgencyOS.md` — v3.3: flujo M10 con Paso 0 selector SBV/SBH, campos específicos por tipo.
- `sopppcmanagerdefinitivo.md` — sección Campaign Builder con tabla de versiones, subsección SB v2.0 completa con 29 columnas y validaciones.

---

## v3.3 — 22 Apr 2026
**Gamboa Generator integrado + Sprint 1 Campaign Builder**

### Added
- Gamboa Generator — reportes HTML integrales
- Campaign Builder SBV/SBH (Sprint 1)
- 31 columnas bulk Amazon 2026

### Fixed
- LaTeX markdown gotcha (3 líneas)
- Bulk compliance validado

---

## v3.2 — 15 Apr 2026
**Deploy + Equipo onboarding**

### Added
- Deploy live en capybaras-os.streamlit.app
- 21 usuarios del equipo en secrets.toml
- Expanders de ayuda en 15/15 módulos
- Login con streamlit-authenticator

### Fixed
- Python 3.11 f-string backslash (weekly_client_report.py L917)
- requirements.txt: agregado requests + beautifulsoup4

---

## v3.1 — 09 Apr 2026
**Listing Monitor + module-architecture-standard mejorado**

### Added
- Listing Monitor (M23) — scraper Amazon + alertas precio/rating/stock
- 3 agentes v3 con frontmatter: ppc-module-builder, excel-export-builder, ui-designer

### Changed
- Sidebar colapsable con expanders por sección (PPC/Research/Account/Knowledge)

---

## v3.0 — 27 Mar 2026
**8 módulos Research/Account conectados + mejoras visuales**

### Added
- DataDive Analyzer (M11) — 4 tabs: MKL, Competitors matrix, Rank Radar, Volatility
- Helium 10 Analyzer (M12) — 3 tabs: Cerebro, KW Research, Competitor Gap
- SBH Recommendation (M13) — targets para Sponsored Brand Headline
- Knowledge Base (M22) — explorar + agregar notas .md
- PPC Insights (M14) — health score 0-100 por ASIN
- PPC Forecast (M15) — proyección ventas + estacionalidad
- PPC Audit (M16) — auditoría integral score 0-100
- Account Pulse (M17) — monitor salud diaria + festivos MX

### Changed
- 48 st.metric migrados a kpi_card helper
- 14 empty states reemplazados por visual cards
- 8 headers unificados con layout flex
- Color coding en 6 tablas (DataDive, H10, SBH, etc.)
- Inicio v3.0 — 22 módulos visualizados

### Documentation
- Agentes v2.0 creados (9 agentes Sonnet/Haiku/Opus con skills asignados)
- Skills core: ppc-reporting-standard.md, module-architecture-standard.md, client-communication-tone.md
- modules/pages/CLAUDE.md — 22 secciones por módulo

---

## v2.0 — 23 Mar 2026
**Atom11 Rules Builder v2026.2 AGRESIVO**

### Added
- Atom11 Rules Builder (M21) — módulo con 274 rules dinámicas
- Campaign classification en 11 grupos por objetivo (DISCOVERY/RANKING/etc.)
- Thresholds v2026.2 AGRESIVO (DEC HARD = PAUSE TARGET)

### Changed
- 6 rules RANKING SP creadas en Atom11 real (cliente Dermaglos)
- Rules viejas v1 pausadas (14 RANKING + 10 DEFENSIVE)

---

## v1.5 — 21 Mar 2026
**Campaign Builder + Bid Optimizer + UI rediseño**

### Added
- Campaign Builder (M10) — generador campañas con Plan de Acción input
- Bid Optimizer (M9) — calculadora bids con CVR × precio × target ACoS
- Plan de Acción tab en Análisis Cruzado (M4)
- Campaign Analyzer en Bulk Campañas (diagnóstico semáforo)

### Changed
- Sidebar rediseñado oscuro (#1A1A1A, naranja #E84000)
- Página Inicio rediseñada (9 áreas Agency OS, ownership, flujo PPC)

---

## v1.0 — 18 Mar 2026
**Arquitectura modularizada completa + 22 módulos**

### Modules
- 22 módulos en modules/pages/ (inicio, STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11, MerchanSpring, Weekly, Bid Optimizer, Campaign Builder, Atom11 Rules)
- Sidebar categorizado: PPC (expanded) | Research | Account | Knowledge
- Router app.py minimal (~200 líneas)

---

## v0.5 — 01 Mar 2026
**Primeros 8 módulos + setup inicial**

### Added
- Stack: Python + Streamlit + Pandas + OpenPyXL + pdfplumber
- Setup CI/CD: no test suite, no linter (custom SOP)
- Primeros módulos: STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11

---

**Formato:** Keep a Changelog (https://keepachangelog.com/)
**Agencia:** Capybaras Agency | **Dev:** Lenin Acosta | **Última actualización:** 2026-04-26
