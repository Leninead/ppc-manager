# CLAUDE.md — Módulos del Agency OS
## Contexto por módulo para agentes especializados
Última actualización: 2026-09-01

---

## Tab IA reusable — `core/ai_tab.py` (2026-09-01)

Capa intermedia entre el pipeline determinístico de un módulo y `ai/` (el
gateway al ai-provider): ciclo de vida del análisis (`decide_analysis_action`
pura + `resolve_analysis` con staleness de dos velocidades: archivo nuevo
re-dispara solo, cambio de parámetro pide click), polling (`render_analysis`),
kit de render localizado (`ai_labels`, `opinion_table_html`, `synthesis_html`,
`ai_chips_html`, `ai_notice_html`, `escape_ai_text`, `AI_CSS`) y chat con
espera (`mount_analysis_chat` sobre `core/ai_chat.py`). El contrato de uso
completo está en el docstring del módulo; tests en `tests/test_ai_tab.py`.
Keys de sesión: `<slug>_ai_*`. **Todo módulo con tab IA consume esta capa —
no implementa el wiring a mano.** Los primeros consumidores (STR y SQP) se
migran en sus propias ramas/tickets.

---

## M1 — Inicio
**Archivo:** modules/pages/inicio.py
**Sección sidebar:** —
**Session state prefix:** —

### Propósito
Dashboard de estado del Agency OS. Muestra 26 módulos agrupados por sección, Workflow Wizard piramidal (5 niveles), changelog y estado del Parent-Child map.

### Arquitectura
- 3 cards activas: PPC (10 módulos) + Account (7) + Research (7) + Intelligence (2)
- KB card full-width
- Flujo guiado 5 niveles: Subí datos → Analizá → Inteligencia → Ejecutá → Reportá
- Parent-Child map: detecta automáticamente si hay BR en data/business_report/

### Reglas de negocio
- No requiere uploads — es informativo
- Actualizar cada vez que se agrega un módulo nuevo

### Anti-patterns
- No agregar lógica de procesamiento de datos en inicio.py
- No hardcodear el conteo de módulos — leer de _PAGES

---

## M2 — Search Term Report (STR)
**Archivo:** modules/pages/search_term_report.py (~1,000 líneas)
**Sección sidebar:** PPC
**Session state prefix:** str_

### Propósito
Analizar search terms de campañas SP: negativizar, harvestear, clasificar por tipo y estado. Es el módulo más usado — punto de partida del flujo semanal.

### Arquitectura
5 tabs: Dashboard (12 KPIs + filtros + charts) | Negatives Mining (tiers dinámicos) | Harvest Candidates (anti-canibalización) | Análisis IA (Claude API) | Por Campaña (groupby)

### Reglas de negocio
- ACoS = Spend / Sales × 100
- Tiers negativización: LOW (<$12): 18 clicks | MID ($12-22): 22 clicks | HIGH (>$22): 28 clicks
- Escalar: 3+ orders AND ACoS < 50% target
- Winners: 2+ orders
- Term type: Brand (contiene brand terms) / Generic / Long-tail (3+ palabras)
- Columna _estado: Escalar / OK / Reducir / Revisar / Negativa?
- Anti-canibalización: cruza con Campaign CSV, marca duplicados Exact activos

### Inputs
- STR (.xlsx o .csv) — requerido
- Campaign CSV (.csv) — opcional (Tab 3 anti-canibalización)
- Target ACoS (slider) + Precio — Tab 2
- Brand terms (texto) — detección manual

### Anti-patterns
- Negativizar sin cruzar contra Exact activo en Campaign CSV
- No usar thresholds fijos — usar fórmula dinámica por CVR

---

## M3 — Search Query Performance (SQP)
**Archivo:** modules/pages/search_query_performance.py
**Sección sidebar:** PPC
**Session state prefix:** sqp_

### Propósito
Analizar el mercado total desde Brand Analytics: impression share, click share, purchase share por query.

### Arquitectura
4 tabs: Vista General | Market Share | Gap Analysis | Análisis IA

### Reglas de negocio
- read_sqp() con skiprows=1
- Brand extraída con extract_sqp_brand() desde row 0
- IS > 30% = Dominando | 10-30% = Competitivo | <10% = Oportunidad
- Gap: Total Impressions > 1000 AND Brand Impressions = 0

### Inputs
- SQP .xlsx

### Anti-patterns
- No usar skiprows=1 → headers mal detectados

---

## M4 — Análisis Cruzado STR vs SQP
**Archivo:** modules/pages/analisis_cruzado.py
**Sección sidebar:** PPC
**Session state prefix:** cruzado_

### Propósito
Cruzar STR (lo que capturan tus campañas) con SQP (lo que busca el mercado). Output: Plan de Acción bulk que es el input del Campaign Builder (M10).

### Arquitectura
3 tabs: Cruce (oportunidades) | Plan de Acción (ESCALAR/AGREGAR/HARVEST/BAJAR BID/MONITOREAR) | PPC Insights por ASIN (BR opcional)

### Reglas de negocio
- Opportunity Score = min-max de impresiones + clicks + purchase rate
- Acciones: ESCALAR (IS bajo + mercado comprando) | AGREGAR (solo en SQP) | HARVEST (en STR, buen ACoS) | BAJAR BID (ACoS > 2× target) | MONITOREAR
- Export bulk: formato Plan de Acción compatible con Campaign Builder

### Inputs
- STR (.xlsx, .csv) — requerido
- SQP (.xlsx) — requerido
- BR by ASIN (.csv, .xlsx) — opcional (Tab 3)

### Anti-patterns
- No detectar marca manualmente si SQP no la extrae automáticamente

---

## M5 — Tendencia Multi-Semana
**Archivo:** modules/pages/tendencia_multisemana.py
**Sección sidebar:** PPC
**Session state prefix:** tend_

### Propósito
Ver evolución de queries a lo largo de 2-4 semanas para detectar tendencias estacionales.

### Arquitectura
Upload hasta 4 SQPs → pivot por Search Query → clasificación ↑→↓

### Reglas de negocio
- ↑ >10% creciendo | → estable | ↓ >10% cayendo
- Bug histórico: KeyError al subir dos SQPs iguales — fix aplicado 2026-03-19

### Inputs
- 2-4 archivos SQP (.xlsx) — mismo formato, semanas distintas

### Anti-patterns
- Subir el mismo archivo dos veces — KeyError en pivot

---

## M6 — Bulk Campañas + Campaign Analyzer
**Archivo:** modules/pages/bulk_campanas.py
**Sección sidebar:** PPC
**Session state prefix:** bulk_

### Propósito
Visualizar el bulk de campañas y diagnosticar con semáforo automático (PAUSAR/REVISAR/ESCALAR/FANTASMA).

### Arquitectura
2 tabs: Vista General (raw) | Campaign Analyzer (diagnóstico semáforo con naming check y target graduation)

### Reglas de negocio
- Filtro por State == "ENABLED"
- PAUSAR: spend > threshold AND orders = 0
- REVISAR: ACoS > target × 2
- ESCALAR: ACoS < target × 0.5 con órdenes
- FANTASMAS: 0 impresiones activas
- Las pausas se ejecutan MANUALMENTE en Campaign Manager — no desde este bulk

### Inputs
- Campaign CSV con métricas (.csv) — requerido para Tab 2

### Anti-patterns
- Confundir bulk .xlsx (sin métricas) con Campaign CSV (con métricas)

---

## M7 — Business Report
**Archivo:** modules/pages/business_report.py
**Sección sidebar:** PPC
**Session state prefix:** br_

### Propósito
Analizar ventas, sesiones, CVR y BuyBox por ASIN desde el Business Report de Seller Central.

### Arquitectura
Visualizador raw. Punto de entrada del Parent-Child map (data/business_report/).

### Reglas de negocio
- Columnas requeridas: (Parent) ASIN, (Child) ASIN
- Auto-detect: Unit Session Percentage o Order Item Session Percentage

### Inputs
- BR by ASIN (.csv, .xlsx)

### Anti-patterns
- No precargar en data/business_report/ si no se quiere auto-load

---

## M8 — Análisis de Funnel
**Archivo:** modules/pages/analisis_funnel.py
**Sección sidebar:** PPC
**Session state prefix:** funnel_

### Propósito
Detectar brechas en el funnel Auto → Broad → Phrase → Exact por producto.

### Arquitectura
Inputs STR + Bulk → mapeo funnel → campañas sugeridas con naming convention

### Reglas de negocio
- Harvest a Phrase: 2+ órdenes AND ACoS ≤ target × 1.2
- Harvest a Exact: 3+ órdenes AND ACoS ≤ target

### Inputs
- STR (.xlsx, .csv) + Bulk (.csv)

### Anti-patterns
- Sin Bulk file → no puede detectar qué match types ya existen

---

## M9 — Bid Optimizer
**Archivo:** modules/pages/bid_optimizer.py
**Sección sidebar:** PPC
**Session state prefix:** bid_

### Propósito
Calcular bid óptimo por keyword: bid = CVR × precio × target_ACoS. Export bulk con bids modificados.

### Arquitectura
2 tabs: Bid Calculator (semáforo SUBIR/OK/BAJAR/PAUSAR) | Placements & Budget (tabla referencia placements + budget)

### Reglas de negocio
- bid_sugerido = (CVR / 100) × precio × (target_ACoS / 100)
- SUBIR: bid < sugerido × 0.7 | OK: 0.7-1.3× | BAJAR: > 1.3× | PAUSAR: clicks > 10 AND orders = 0

### Inputs
- STR (.xlsx, .csv) — requerido
- Inventory Report (.txt) — opcional (precio de lista exacto)

### Anti-patterns
- Usar ACoS del STR sin filtrar por ENABLED — incluye términos de campañas pausadas

---

## M10 — Campaign Builder
**Archivo:** modules/pages/campaign_builder.py (864 → 1121 líneas tras Sprint 1 2026-04-23)
**Sección sidebar:** PPC
**Session state prefix:** cb_ (SP) | cb_sb_v2_* (SB) | cb_sd_* (SD)

### Propósito
Generar bulk de nuevas campañas (SP/SB/SD) a partir del Plan de Acción. El naming Capybaras hardcoded es un contrato con M11 Atom11 Rules Builder — NO modificar.

### Arquitectura
Selector tipo (SP/SB/SD) con radio button → flujo en pasos (Paso 0-4 según tipo) → preview editable → validación estricta bloqueante → export bulk formato exacto Amazon

### Helpers principales
- `_generar_nombre_campana_sp()` — naming SP hardcoded (NO tocar — contrato con M11)
- `_generar_nombre_campana_sb()` — naming SB hardcoded (NO tocar — contrato con M11)
- `_SB_COLS_2026` — 29 columnas bulk Amazon Ads API 2026 (incluyendo `" Ad Group ID"` con espacio inicial — es correcto, es bug de Amazon documentado)
- `_sb_row_factory(**kwargs)` — builder de fila vacía para bulk SB
- `_build_sb_bulk_rows(...)` — genera 5 filas por campaña SB: Campaign → Bidding Adjustment → Ad Group → Ad → Keywords con bifurcación SBV/SBH
- `_render_sb()` — flujo completo SBV/SBH reescrito en Sprint 1 (2026-04-23)
- `_render_sd()` — flujo SD (preexistente)

### Reglas de negocio
- SP clustering: PAT / Spanish (prioridad) / Brand / Vitamin A / Discovery
- Max 5 keywords por campaña (regla Capybaras — NO negociable)
- SB Paso 0: selector SBV vs SBH (bifurca toda la lógica)
- SBV requiere: Brand Entity ID (obligatorio) + Video Asset ID (obligatorio) + Brand Name + Creative Headline + 3 ASINs creativos
- SBH requiere: Brand Entity ID (obligatorio) + Brand Logo Asset ID (obligatorio) + Logo Crop (Square/Rectangle) + Brand Name + Creative Headline + 3 ASINs creativos + Brand Logo URL (opcional)
- Brand Entity ID: obligatorio en Amazon Ads API 2026 — sin él el bulk es rechazado
- Validaciones estrictas bloqueantes: si falta cualquier campo requerido, muestra lista de errores en lugar del botón de descarga
- Naming SB: `[Marca] - [ASIN] - SB - KW - [Match] - [Cluster]` (ejemplo: `Dermaglos - B0CYLMJJJC - SB - KW - EXACT - Brand 1`)
- SD requiere: Product Targeting o Audience, bid optimization

### Gotcha crítico — Streamlit Markdown + LaTeX
- Patrón `**${variable}**` en st.info/st.markdown/st.error/st.warning rompe el render (Streamlit interpreta `$` como delimitador LaTeX)
- Fix: escapar con `\\$` o envolver negrita alrededor de frase completa: `**Precio: \\$X**`
- Afecta a cualquier string que combine `**` y `$` en el mismo bloque

### Inputs
- Plan de Acción bulk (de M4, .xlsx) — Paso 1
- Marca, ASIN, SKU, precio, CVR, target ACoS, budget — Paso 2
- Brand Entity ID — Paso 2 (requerido para SB)
- Video Asset ID (SBV) o Brand Logo Asset ID + Crop (SBH) — Paso 3

### Anti-patterns
- NO permitir bloques dinámicos de naming — rompen el contrato con M11 (Atom11 Rules Builder parsea Campaign Name para clasificar en DISCOVERY/RANKING/CONQUEST/etc)
- NO usar `**${var}**` en markdown de Streamlit — colisión con LaTeX
- No validar SKUs contra Inventory — Amazon rechaza ASIN en bulk SP
- No cruzar contra Exact activas — canibalización

### Sprint roadmap
| Sprint | Feature | Estado |
|--------|---------|--------|
| 1 | Rewrite `_render_sb()` con SBV + SBH + Brand Entity ID + 29 columnas 2026 | ✅ Completado 2026-04-23 |
| 2 | Modo B simplificado con XLSX custom + `st.data_editor` | Pendiente |
| 3 | DaypartingApp como módulo nuevo en Account Manager | Pendiente |

---

## M11 — Atom11 Rules Builder
**Archivo:** modules/pages/atom11_rules_builder.py
**Sección sidebar:** PPC
**Session state prefix:** atom11_

### Propósito
Generar 274 rules automáticas para importar en Atom11.

### Arquitectura
3 tabs: Config (marca, brand terms, ASINs + tiers), Campaign Groups (clasificación automática), Rules Generator (preview + export)

### Reglas de negocio
- Multi-marca: todo configurable
- Tiers: LOW (<$12, 18 clicks) | MID ($12-22, 22 clicks) | HIGH (>$22, 28 clicks)
- 6 objetivos: DISCOVERY (120% target) | RANKING (100%) | CONQUEST (86%) | DEFENSIVE (71%) | PROFIT (50%) | REMARKETING (71%)
- 274 rules = Bid Optimiser (126) + Placement (108) + Negate (18) + Hard-Stop (18) + Harvest (4)
- Thresholds v2026.2: DEC HARD > 1.86× target → PAUSE TARGET
- Parsea Campaign Name para clasificar objetivo — por eso el naming Capybaras en M10 es un contrato, NO un detalle cosmético

### Inputs
- Prefijo marca + brand terms + ASINs con precio
- Campaign CSV — clasificación automática

### Anti-patterns
- Hardcodear tiers sin pasarlos por editor
- Crear rules antes de 14 días de learning period

---

## M12 — Reportes Atom 11
**Archivo:** modules/pages/atom11.py
**Sección sidebar:** Account
**Session state prefix:** atom11_reports_

### Propósito
Parsear reportes Atom11 (WoW/MoM/DateRange) y generar Excel ejecutivo.

### Arquitectura
1 o 2 archivos → parsea automáticamente → 3-4 sheets Excel con branding

### Reglas de negocio
- Auto-detect: tipo reporte (ASIN, Portfolio, Keyword, etc.)
- Delta% coloreado: verde >0, rojo <0
- Parent Evolution: opcional si hay BR cargado

### Inputs
- Atom 11 .xlsx (1 o 2 archivos)
- Business Report — Tab "Parent Evolution"

### Anti-patterns
- Incluir campañas pausadas — Amazon retorna "Not Found"
- No confundir período: mismo WoW que en Weekly Report

---

## M13 — Reportes MerchanSpring
**Archivo:** modules/pages/merchanspring.py
**Sección sidebar:** Account
**Session state prefix:** merchanspring_

### Propósito
Parsear PDF o XLSX de MerchanSpring → Excel estructurado 4 hojas.

### Arquitectura
Detección automática PDF vs XLSX, parsers defensivos con try/except, export multi-sheet

### Reglas de negocio
- PDF: extrae 20+ secciones, robust contra cambios de formato
- XLSX: parsea Summary, Advertising, Inventory, WoW

### Inputs
- MerchanSpring .pdf o .xlsx

### Anti-patterns
- PDF con cambios de layout — agregar try/except nueva sección

---

## M14 — Weekly Client Report
**Archivo:** modules/pages/weekly_client_report.py
**Sección sidebar:** Account
**Session state prefix:** weekly_

### Propósito
Generar reporte semanal al cliente: WoW comparativo + Advertising + Changelog.

### Causa raíz que define el diseño
**El export "Detail Page Sales and Traffic By Child Item" de Amazon NO trae columna
de fecha**: es un único agregado del rango pedido. Por eso un solo by-Child no se
puede partir en dos semanas, y el período de esas columnas tiene que declararse
desde afuera. Ignorarlo produjo el bug de deuda técnica #24: los montos por ASIN
salían de 14 días bajo el encabezado "esta semana", ~2× lo real.

### Arquitectura
**5 inputs** → 4 sheets Excel con branding Capybaras.

| # | Input | Obligatorio | Notas |
|---|---|---|---|
| 1 | BR diario 14d (By Date) | sí | única fuente con fechas reales; de acá se derivan los períodos |
| 2 | BR by Child — esta semana | sí | sin fechas propias |
| 3 | BR by Child — semana anterior | **no** | sin este archivo NO hay WoW por producto |
| 4 | Atom 11 ASIN 14d | no | sí trae desglose diario: su split 7+7 es correcto |
| 5 | Campaign CSV | no | |

### Los dos modos
`_es_modo_wow(period_child_tw, period_child_pw)` es la única fuente de verdad y la
consultan tanto el Excel como la UI, para que no puedan discrepar.

- **MODO WOW** — exige DOS períodos by-Child de **7 días exactos**. Se mira `days`,
  no la presencia del dato: un período informado de 14d NO habilita el WoW.
  Rótulos "Esta semana / Semana anterior / Variación %", WoW por producto, TACoS
  por ASIN calculado.
- **MODO PERÍODO COMPLETO** — cualquier otro caso. SALES/UNITS/SESSIONS/CVR se
  rotulan "Período completo (Nd)", las columnas PW y de delta van a "—", la fila
  CUENTA TOTAL muestra el **mismo agregado** que los productos, y el TACoS por
  producto queda en "—". AD SALES y AD SPEND no cambian (vienen de Atom 11).

**Invariante:** una columna nunca mezcla períodos. Si los productos son de 14d, la
fila CUENTA TOTAL de esa columna también.

### Funciones clave
```python
_derivar_periodos(br_daily, hay_child_pw)  # -> (period_tw, period_pw). Extraido de render()
_periodo(fechas)                  # [ISO] -> {'start','end','days'} | None. days = fechas DISTINTAS
_es_modo_wow(p_tw, p_pw)          # única decisión de modo (7d + 7d)
_chequear_coherencia_child(...)   # suma del by-Child vs BR diario, tol 1%; avisa, NO bloquea
_calificar_trafico(se_d, cvr_d)   # cruza sesiones x conversión -> clave de texto
_trend_ejecutivo(s_d, u_d, se_d)  # 'pos'|'neg'|'flat'; las sesiones NO votan
_rango_legible(period, lang)      # '10–16 ago' / 'Aug 10–16'
_sufijo_periodo(...)              # sufijo del título con el período real
_L_EXEC                           # textos del ejecutivo, a NIVEL DE MÓDULO (testeable sin generar Excel)
```

### Reglas de negocio
- `_parse_br_wow` **consolida** filas del mismo (Child) ASIN: Amazon lista el mismo
  child bajo parents distintos tras merges de variaciones. Sessions/units/sales
  suman; CVR se recalcula del cociente de totales; BuyBox se pondera por sesiones.
  Metadata `_rows_merged` / `_parents` para trazabilidad.
- CVR de cuenta en el ejecutivo: **ponderado por sesiones** (`units/sessions`), en
  las DOS ramas (con BR diario y sin él). Nunca promedio simple por ASIN ni
  promedio de los porcentajes diarios — `br_daily["CVR_TW"]` es un `.mean()` de
  porcentajes y NO sirve para el total de cuenta (desvío medido: 8,22 puntos).
- El trend lo deciden ventas y unidades. Las sesiones son un input, no un resultado.
- Tráfico ↑ con CVR ↓ **no se felicita**: es diagnóstico de calidad de tráfico.
- BuyBox con 0 sesiones → ignorado.
- Toggle ES/EN para toda la redacción ejecutiva.

### Anti-patterns
- **Rotular una columna sin saber su período.** Todo rótulo temporal sale del modo.
- **Sumar filas de producto y llamarlas "esta semana"** sin BR diario ni MODO WOW.
- `result[asin] = {...}` en el loop de `_parse_br_wow` — pisa duplicados (last-wins).
- `br_pw={}` hardcodeado en el call site: era el origen del bug.
- Calificar una métrica en aislamiento, o dar dos causas distintas al mismo hecho.
- No validar date range — el by-Child debe cubrir el mismo rango que el BR diario
  (lo chequea `_chequear_coherencia_child`).

### Tests
`tests/test_m14_weekly_periodo.py` — 29 casos: dedup, contrato de período, WoW por
producto, coherencia, narrativa y encabezado.

---

## M15 — Listing Monitor
**Archivo:** modules/pages/listing_monitor.py (587 líneas)
**Sección sidebar:** Account Manager
**Session state prefix:** lm_

### Propósito
Monitorear ASINs de Amazon, alertar cambios precio/rating/stock/badges vs snapshot anterior. Scraping directo (sin API key).

### Arquitectura
3 tabs: Escanear ASINs | Ver Alertas | Historial con snapshots

### Reglas de negocio
- Scraper: requests + BeautifulSoup, delay configurable (8-10s por ASIN)
- Storage: JSON local `data/listing_snapshots/snapshots.json`
- Key: `{ASIN}_{MARKETPLACE}`
- Color alerts: 🔴 alerta | 🟡 info | 🟢 ok

### Inputs
- ASINs (texto libre, separados por salto)
- Marketplace selector (MX/COM/ES/BR/CA)
- Delay (segundos)

### Anti-patterns
- Amazon 503 bloqueo — aumentar delay a 10s mínimo
- Múltiples cargas → overwrite snapshot anterior (YAGNI por ahora)

---

## M17 — Account Pulse
**Archivo:** modules/pages/account_pulse.py (~430 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** pulse_

### Propósito
Monitor de salud diaria: ventas, units, sessions, CVR, ACoS con deltas WoW. Festivos MX integrados.

### Arquitectura
Upload BR diario + BR by Child + Campaign CSV → split PW/TW automático → Excel 4 hojas

### Reglas de negocio
- Festivos MX hardcoded: Año Nuevo, Constitución, Juárez, Trabajo, Independencia, Muertos, Revolución, Navidad
- Anomalía: caída >30% del promedio
- BuyBox ordenado por impacto económico
- Campañas: NUEVA (verde) vs HEREDADA (azul)
- Portada naranja con KPIs + diagnóstico + mensaje Slack

### Inputs
- BR Daily (.csv/.xlsx) — mínimo 14 días
- BR by Child (.csv/.xlsx) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- BuyBox con 0 sesiones → ignorar (falso positivo)

---

## M18 — PPC Insights Engine
**Archivo:** modules/pages/ppc_insights.py (~530 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** insights_

### Propósito
Health score 0-100 por ASIN cruzando STR + SQP + BR + Campaign CSV. Identifica ASINs problemáticos.

### Arquitectura
Carga múltiples reports → cruza datos → score compuesto + cards por ASIN con expanders

### Reglas de negocio
- Health Score (0-100): CVR (25 pts) + BuyBox (20 pts) + ACoS vs target (25 pts) + Funnel completo (15 pts) + Impression Share (15 pts)
- Por ASIN: Top keywords, bleeders, wasted spend, top campaigns

### Inputs
- STR (.xlsx, .csv) — requerido
- SQP (.xlsx, .csv) — opcional
- BR by ASIN (.xlsx, .csv) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- Cargar STR sin SQP — pierde contexto de mercado en score

---

## M19 — PPC Forecast
**Archivo:** modules/pages/ppc_forecast.py (~450 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** forecast_

### Propósito
Proyección de ventas con tendencia lineal + estacionalidad. Estima ventas futuras 7/14/30 días.

### Arquitectura
Input BR diario (mín 14d) → numpy polyfit → 3 escenarios (conservador/base/optimista) + gráfico + Excel

### Reglas de negocio
- Tendencia: numpy polyfit grado 1
- Estacionalidad: finde vs laboral, detección automática
- 3 escenarios con bandas de confianza

### Inputs
- BR Daily (.xlsx, .csv) — mínimo 14 días

### Anti-patterns
- Menos de 14 días → resultados no confiables
- Proyectar >30 días → pierde precisión

---

## M20 — PPC Audit Pro
**Archivo:** modules/pages/ppc_audit.py (~1,077 líneas)
**Sección sidebar:** Intelligence
**Session state prefix:** audit_

### Propósito
Auditoría integral desde Bulk File multi-hoja. Breakdown real SP/SB/SD, 10 segmentos, 5 deep checks.

### Arquitectura
Parser Bulk 5-hoja → 6 tabs Excel: KPIs, Auditoría Estructura, Performance Segmento, Deep Checks (5), Target Graduation, Export

### Reglas de negocio
- Parser: SP Campaigns, SB Campaigns, SD Campaigns, SP STR, SB STR
- Segmentación SP: 10 tipos (KW Exact/Phrase/Broad + PT ASIN/Category + AUTO Close/Loose/Substitutes/Complements)
- Match Type Mixto: >1 match por campaign → badge REVISAR
- Target WAS: spend>0, sales=0
- ACoS semáforo: verde ≤30%, amarillo 31-55%, rojo >55%

### Inputs
- Bulk File (.xlsx) — requerido (Campaign Manager → Bulk Operations)
- Business Report (.xlsx, .csv) — opcional (para TACoS, Revenue)
- Brand terms (texto) — clasificación targets

### Anti-patterns
- NO confundir Bulk File (.xlsx Campaign Manager) con Campaign CSV
- _build_audit_excel() DEBE estar fuera de render()

---

## M21 — DataDive Analyzer
**Archivo:** modules/pages/datadive_analyzer.py
**Sección sidebar:** Research
**Session state prefix:** widgets `dd_*` · IA `datadive_ai_*` (capa ai_tab)

### Propósito
Analizar niches de DataDive (keywords, competidores, rank radar) para detectar oportunidades de mercado. El tab 1 puede traer la MKL directo por API (sin export manual) y corre un análisis IA con chat de repreguntas.

### Arquitectura
5 tabs: MKL Keywords | Competitors | Rank Radar | Ranking Volatility+PPC IS | Competitor Intel.
Parsers puros en `modules/parsers/datadive.py` (shape canónico COL_*); cliente API en `core/datadive.py`; agente IA en `ai/agents/datadive/` consumido vía `core/ai_tab` (nunca wiring a mano).

### Fuente API — tabs 1-5 (2026-09-01)
- Gate: presencia de `DATADIVE_API_KEY` (env → `st.secrets["datadive"].api_key`). Sin key el módulo es idéntico al flujo solo-archivo.
- Tab 1: radio `API DataDive | Archivo` (API es el default con key) → selector de niche (label `nicheLabel · marketplace`, orden por `latestResearchDate` desc, key del widget = `nicheId`) + botón "Traer de DataDive" (refresh targeted `_api_mkl.clear(niche_id)`). Caption con fecha+hora UTC del último dive.
- Tab 2: carga automática de los competidores del MISMO niche traído en tab 1 (`competitors_to_df` → labels del export; benchmark → medianas). Validado 9/9 ASINs idénticos al xlsx real; la API suma columnas que el export no numericiza (Fulfillment, Outliers, TOS Ads) y NO trae "Strength".
- Tab 5: dos selectores de niche + "Traer ambos de DataDive"; el Gap se clasifica por el indicador del outer join (el shape MKL no tiene columnas "rank").
- Tabs 3-4: selector de rank radar + rango 30/60/90 días (`rank_radar_to_df` → Search Term/SV/Relevance/Median Rank + columnas fecha con el rank orgánico diario). El historial es server-side (el bloque de snapshots en session_state queda solo para archivos); el tab 4 reusa el radar traído en el 3. La API no trae las columnas PPC/SQ Score del export — el tab las guarda con `if col in df`.
- **`/v1/niches` devuelve el set completo en cada "página"** (paginación declarada pero no honrada, medido en vivo): `list_niches` dedupea por nicheId y corta cuando una página no aporta ids nuevos. Ante endpoints nuevos, asumir que la paginación puede mentir.
- `keywords_to_mkl_df()` produce el MISMO DataFrame canónico que `parse_mkl` — el resto del tab no distingue la fuente. **Launch Score no viene en ningún endpoint v1, pero se CALCULA** con la fórmula del frontend de DataDive (bundle público): `round(SV × 0.003 / relevancy)` si relevancy ≥ 0.4, si no 0 — replicada en `core/datadive.py::_launch_score` y validada 419/419 contra el export real. `rankingJuice` de /roots NO es el Launch Score (verificado 0/419).
- **Sostenibilidad del Launch Score, sin vigilancia manual** — la réplica se rompe en silencio si DataDive cambia su fórmula, así que hay tres redes, y la principal es automática:
  1. **CI, sin credenciales** (la red que no depende de nadie): `scripts/check_launch_score_drift.py` verifica que la fórmula siga en el bundle público y si `launchScore` apareció en el spec oficial. Corre en el stage `Launch Score drift` del Jenkinsfile — en cada build y por cron semanal (`H 6 * * 1`, que NO deploya porque el CD gatea en `SCMTrigger`). Marca el build UNSTABLE, nunca lo rompe: que un tercero recalibre una fórmula es una noticia, no un build roto.
  2. `_launch_score_of()` prefiere el campo oficial (`launchScore`/`launch_score`) si algún día aparece en el payload: el día que DataDive lo exponga, la réplica queda muerta sola, sin migración.
  3. `launch_score_drifted()` audita la fórmula contra cada export por archivo que suba el AM (el xlsx trae el valor verdadero) y avisa en el tab. Es red de respaldo: con el modo API por default los archivos casi no se suben, así que NO alcanza por sí sola.
  El fix permanente es que DataDive exponga el campo: no hay pedido público, y tienen canal de soporte y office hours.
- Los GET de DataDive no consumen tokens facturables (solo dives/rank radars/copywriter los gastan); el cache `st.cache_data(ttl=3600)` es compartido entre usuarios del proceso y el botón Traer fuerza fetch fresco.
- Smoke con key real: `scripts/smoke_datadive_api.py` (read-only; imprime distribución de relevancy y sondea /roots y /ranking-juices).

### Reglas de negocio
- Tab 1: SV, Relevance (escala UI 0-10), Launch Score, ranking competidores. Color: verde Rel ≥3, amarillo ≥2, rojo <2.
- **Relevancy es fracción 0-1 en la API Y en los exports frescos (2026-08+)** — parser y normalizer la llevan a 0-10 (×10). El parser solo rescala si TODO el archivo está en 0-1.
- **`parse_mkl` mapea columnas por nombre de header** (el export insertó "Type" en 2026-08 y rompió el layout posicional); el layout legacy queda como fallback.
- Tab 3: tracking orgánico diario, tendencia ↑→↓, PPC coverage
- Tab 4: volatilidad (std dev), clasifica ESTABLE/VOLÁTIL/MUY VOLÁTIL, flags riesgo/oportunidad
- Tab 5: tu MKL + competidor, clasifica Ambos/Solo yo/Solo comp/Ninguno

### Capa IA (tab 1)
- Agente `datadive` (primer agente de `ai/` en main): recibe Parámetros + top 120 keywords por SV (row_ids K01…) + opcionalmente los competidores del niche con su mediana (de la API o del archivo del tab 2), y emite clusters de intención, gaps priorizados y la síntesis canónica de `core/ai_tab`. Chat flotante montado FUERA de st.tabs.
- **Contrato del agente (v2, auditado contra output real)**: `launch_score` es COSTO de entrada (alto = caro), no puntaje; `relevance` se ancla en los cortes del tab (alta ≥3,0 — el grueso del niche vive bajo 3); `sugg_bid` no habilita a declarar bids/ACoS/presupuesto (no hay precio ni CVR del cliente en el payload). Los **gaps incluyen el ASIN enterrado** (mi_rank fuera de P1), no solo el ausente — son los más baratos. La **prioridad de cluster es atacabilidad, no tamaño**, y el orden del array es el orden de ataque. `select_keywords` manda 90 por SV + 30 por relevancia (la cola barata sesgaba a "niche caro" si se cortaba solo por SV) y marca cada fila con `bloque`. Si el ASIN declarado no está en el dive, Parámetros lo declara como CALIDAD DE DATOS y los gaps van vacíos.
- **Chat con tools (fase 3)**: el frontmatter del agente declara `tools: datadive` → `runtime.ask_followup` manda `tools:["datadive"]` + `max_turns 8` al provider, que expone 5 tools MCP read-only in-process (list_niches, get_niche_keywords, get_niche_competitors, list_rank_radars, get_quota; resultados truncados). Solo el CHAT es agéntico — el análisis nunca lleva tools. Server-side vive en capybaras-ai-provider (`app/datadive_tools.py`, rama feat/datadive-mcp-tools) con `DATADIVE_API_KEY` en su .env.
- La IA nunca recalcula cifras; el módulo joinea opiniones por row_id posicional contra los MISMOS records serializados.

### Inputs
- DataDive exports (.xlsx) o niche vía API (tab 1)

### Anti-patterns
- return-in-tabs bug — fijar con paréntesis en cada tab call
- NO parsear el MKL por posición de columna — DataDive re-layouta el export; headers son el contrato
- NO llamar a `ai/runtime` directo — todo por `core/ai_tab`
- NO llamar POSTs de DataDive (dives/redive/rank radars/copywriter) — consumen tokens reales de la organización

---

## M22 — Helium 10 Analyzer
**Archivo:** modules/pages/helium10_analyzer.py (350+ líneas)
**Sección sidebar:** Research
**Session state prefix:** h10_

### Propósito
Analizar exports Helium 10 Cerebro para reverse ASIN, research y competitor gap.

### Arquitectura
3 tabs: Cerebro Reverse ASIN | KW Research multi-competidor | Competitor Gap con export Plan de Acción

### Reglas de negocio
- Tab 1: SV, Organic Rank, Sponsored Rank, IQ Score. Flags: Oportunidad PPC (organic sin ads), Depende de Ads
- Tab 2: cruza 1-3 Cerebros competidores, Launch Priority Score = SV × (ranking comp/total) × (1/avg rank)
- Tab 3: tu Cerebro vs 1-2 competidores, detecta KWs donde rankean org y vos no. Botón "Exportar como Plan de Acción" para Campaign Builder

### Inputs
- Cerebro .xlsx: `US_AMAZON_cerebro_[ASIN]_[fecha].xlsx`

### Anti-patterns
- Cargar 1 archivo SQP en Cerebro parser → maneja "-" como NaN

---

## M23 — SBH Recommendation
**Archivo:** modules/pages/sbh_recommendation.py (230+ líneas)
**Sección sidebar:** Research
**Session state prefix:** sbh_

### Propósito
Recomendar targets para campañas Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV.

### Arquitectura
Carga 3 inputs → prioriza por SV + IS + mercado comprando → clustering automático + headlines sugeridos

### Reglas de negocio
- Prioridad ALTA: SV ≥1000, IS <10%, mercado comprando, no en SP actual
- MEDIA: SV ≥500, IS <20%
- BAJA: SV ≥300
- Clustering: root words comunes
- Headline sugerido por cluster

### Inputs
- DataDive MKL (.xlsx) — requerido
- SQP (.xlsx, .csv) — requerido
- Campaign CSV (.xlsx, .csv) — opcional

### Anti-patterns
- Sin Campaign CSV → no puede detectar keywords ya en SP

---

## M24 — Knowledge Base
**Archivo:** modules/pages/knowledge_base.py (~180 líneas)
**Sección sidebar:** Knowledge
**Session state prefix:** kb_

### Propósito
Repositorio de notas y documentación del equipo. Buscar, filtrar y crear notas .md.

### Arquitectura
2 tabs: Explorar notas (upload + búsqueda texto + filtro tags/categorías) | Agregar nota (formulario + preview + descarga)

### Reglas de negocio
- Categorías: ppc, amazon, ai, strategy, client
- Parsea headers/tags/categorías/fecha del filename
- Búsqueda full-text case-insensitive
- Badges de categoría estilo naranja

### Inputs
- Archivos .md o .txt

### Anti-patterns
- No procesar archivos que no sean texto plano (.md, .txt)

---

## M25 — Gamboa Generator
**Archivo:** modules/pages/gamboa_generator.py (383 líneas)
**Módulos internos:** `modules/gamboa/{__init__, parsers, generator, template.html}`
**Sección sidebar:** Account
**Session state prefix:** gamboa_

### Propósito
Generador de reportes HTML integrales tipo dashboard interactivo. Cruza SQP mensual + BR semanal, reutilizable para cualquier cliente Capybaras. Listo para publicar en Hostinger o enviar al cliente por email/WhatsApp.

### Arquitectura
5 archivos: __init__ (marker) + parsers (421 líneas: `parse_sqp_multi`, `parse_br_multi`, `parse_inventory`, `load_categories`/`save_categories`) + generator (278 líneas: `enrich_sqp`, `enrich_br`, `build_raw_json`, `build_wow_json`, `generate_html`) + template.html (874 líneas, 64KB con 12 placeholders y JS runtime)

UI Streamlit: expander `_how_to_use()` + `_header()` + `_empty_state()` + `_info_box()`

### Reglas de negocio
- **Categorías persistentes:** `notes/brands/{cliente-slug}/gamboa_categories.csv` — reutiliza arquitectura existente de notas
- **SKU opcional con fallback ASIN:** robustez, funciona sin Inventory Report
- **Template HTML separado:** mantenible por separado, no hardcodear lógica
- **Score SQP defensivo:** lee columna "Search Query Score" con fallback 0 — defensivo ante cuentas sin Brand Analytics
- **SQP multi-upload:** auto-detecta mes por filename O columna "Reporting Range" — Amazon BA baja archivo por mes O por rango, ambos casos soportados

### Parsers cacheados
```python
@st.cache_data — todos: parse_sqp_multi(), parse_br_multi(), parse_inventory()
```

### Inputs
- **SQP multi-archivo (.xlsx)** — requerido. Auto-detecta mes por filename o "Reporting Range"
- **BR semanal by ASIN (.xlsx o .csv)** — requerido. Auto-detecta semana ISO
- **Inventory Report (.txt, .csv)** — opcional. Mapeo SKU ↔ ASIN. Sin esto usa ASIN como identificador
- **CSV categorías** — auto-plantilla descargable. Persistente entre sesiones en `notes/brands/{cliente-slug}/gamboa_categories.csv`

### Output
HTML standalone (~5-10 MB) listo para publicar. 2 paneles interactivos con JS runtime:
- **Panel SQP mensual:** 15 meses de queries, filtros por categoría, funnel conversión, cards por categoría, tabla filtrable, 7 charts de tendencia (Search Query Score, Impressions, Clicks, Cart Adds, Purchases, Click-Through Rate, Conversion Rate)
- **Panel WoW Category (semanal):** 68 semanas de KPIs WoW/YoY, category cards con deltas, tabla detalle con sparklines por SKU, modal de tendencia por SKU

### Pendientes condicionales (YAGNI — NO tocar hasta feedback del AM con data real)
- **SI** el AM reporta >20% queries en "Sin Categorizar" → evaluar refactor usando "Top Clicked ASIN" del SQP crudo para auto-clasificación
- **SI** hay problemas con mapeo de categorías → evaluar agregar columna `sqp_keywords` al CSV categorías para fuzzy match

### Anti-patterns
- Cargar SQP sin crear categorías CSV primero — template mostrará muchas "Sin Categorizar" (YAGNI: no auto-clasificar)
- BR antiguo (sem 1-2 meses) sin datos recientes — usar único de semana actual
- No validar que ASIN en BR coincida con ASIN del producto (cruce de cuentas)

---

## M26 — Variation Builder
**Archivo:** modules/pages/variation_builder.py (913 líneas)
**Sección sidebar:** Account Manager
**Session state prefix:** vb_

### Propósito
Generador de flat files Amazon con variaciones (parent + N children). Agrupa por variation_theme configurable, preserva macros VBA y 10 hojas del template. Parser dinámico soporta hasta 220 columnas. Listo para subir a Seller Central.

### Arquitectura
- Parser dinámico que detecta columnas del template (hasta 220)
- Agrupa children automáticamente por variation_theme seleccionado
- Genera parent_sku derivado del primer child con sufijo
- Escribe .xlsm con openpyxl + keep_vba=True (preserva macros)
- Mantiene las 10 hojas del template (Template, Data Definitions, Valid Values, etc.)

### Reglas de negocio
- 1 parent + N children por SKU group
- variation_theme define qué columnas varían entre children
- parent_sku derivado del primer child con sufijo
- relationship_type = "Variation" para children, vacío para parent
- Columnasrequeridas: una con "ASIN" en el nombre, una con "Parent" en nombre o configuración

### Themes soportados (v1)
- Sabor
- Nombre del Tamano
- Scent
- FlavorName-SizeName
- Tamano del Sabor
- Nombre del Patron

### Marketplaces (v1)
Solo MX (MXN). Futuro: multi-marketplace (COM, ES, BR, CA).

### Inputs
- **Template .xlsm** — Amazon Seller Central → Inventory → Add Products via Upload → Download Template
- **Variation theme selector** — Sabor, Nombre del Tamano, Scent, FlavorName-SizeName, Tamano del Sabor, Nombre del Patron

### Outputs
- **.xlsm listo para subir a Seller Central**
- Preserva macros VBA y 10 hojas del template
- Agrupación automática por variation_theme

### Testing realizado
- End-to-end con archivo real Pet Food: parent + 15 children, generado exitosamente
- py_compile: verde
- Archivos modificados: app.py (3 edits quirúrgicos), core/constants.py (1 edit)

### Anti-patterns
- NO modificar el archivo del módulo (913 líneas, ya validado y tested)
- NO usar pandas.to_excel solo (perdería macros) → usar openpyxl con keep_vba=True
- NO asumir 50 columnas — el template Pet Food tiene 220
- NO hardcodear marketplaces — v1 solo MX, futuro multi-MP
- NO duplicar SKUs entre parent y children
- NO cambiar nombre de hojas — Amazon rechaza si no son exactos

---

## M27 — Flat File Migrator
**Archivo:** modules/pages/flat_file_migrator.py
**Sección sidebar:** Account Health
**Session state prefix:** ffm_
**Fuente:** porteado de `.claude/porting-sources/flat-file-migrator.html` (2026-05-06)

### Propósito
Migrar datos de un flat file viejo de Amazon a un template nuevo, mapeando columnas automáticamente con 5 estrategias en cascada (exact field ID → normalized → alias → base → header). Soporta 5 marketplaces independientes en tabs (US/DE/IT/FR/ES). **Stateless por diseño** — sin persistencia, procesamiento puro in-memory.

### Arquitectura
- 1 tab por marketplace (5 tabs total). Toda la lógica vive en `_render_marketplace(suffix, sheet_names)` parametrizado.
- Parser cacheado `_parse_workbook(file_bytes, file_name, sheet_names)` con `@st.cache_data(show_spinner=False)`. Cache key = bytes hash.
- Builders fuera de `render()`: `_build_migrated_xlsx(rows, sheet_name) → bytes` y `_build_migrated_tsv(rows) → bytes` con BOM UTF-8.
- Helpers porteados literal del HTML: `_detect_header_row`, `_get_headers`, `_is_amazon_internal_row`, `_get_data_rows`, `_detect_file_type`, `_normalize_field_id`, `_looks_like_field_ids`, `_norm_header`, `_match_columns`.
- `_run_migration(...)` orquesta el flujo completo: detecta header rows, extrae field_ids, aplica las 5 estrategias, construye output preservando rows pre-data del template nuevo.

### Reglas de negocio (porteadas literal del HTML)
- **Header row detection**: escanea primeras 11 rows, prioriza row con keywords típicas Amazon (`sku`, `item_sku`, `feed_product_type`, `seller sku`, `verkäufer-sku`, `sku venditore`, `référence vendeur`, `sku del vendedor`, etc.). Multi-idioma EN/DE/IT/FR/ES.
- **5 estrategias de matching en orden estricto**:
  1. Exact field ID (lowercase)
  2. Normalized field ID (sin brackets, hash, sufijos)
  3. Aliases bidireccionales (~40 mappings: `item_sku ↔ contribution_sku`, `brand ↔ brand_name`, `main_image_url ↔ main_product_image_locator`, `other_image_urlN ↔ other_product_image_locator_N`, etc.)
  4. Base name only
  5. Header normalizado (lowercase, sin spaces/underscores/dashes) — fallback cuando no hay field IDs
- **Filtro de filas internas Amazon**: regex `marketplace_id=` · `amzn1\.volt\.` · `#\d+\.value` · `\[language_tag=` + heurística "tipo SHIRT/SHOES con commas"
- **Skip example row** (default ON): saltea la primera data row del old (ejemplo Amazon)
- **Preserva rows pre-data del template nuevo**: header rows, field IDs, separadores se copian tal cual; luego una row vacía separadora; luego data del old mapeada a posiciones del new
- **Output**: XLSX (openpyxl) o TSV con BOM UTF-8 (`﻿` prefix)
- **Sheet matching**: 1) match exacto lowercase contra `sheetNames` esperados, 2) contains, 3) primer sheet del workbook
- **Header row override quirky logic** (HTML L997-998): si user pone `1` y auto > 0 → usa auto. Si user pone otro valor → usa user. **Replicado tal cual.**

### Marketplaces v1
| Marketplace | Sheet names esperados (en orden) |
|---|---|
| 🇺🇸 USA | `Template` |
| 🇩🇪 Germany | `Vorlage`, `Template` |
| 🇮🇹 Italy | `Modello`, `Template` |
| 🇫🇷 France | `Modèle`, `Template` |
| 🇪🇸 Spain | `Plantilla`, `Template` |

Cada marketplace es totalmente independiente (state propio en widget keys con prefijo `ffm_{suffix}_`).

### Inputs
- **Old Flat File** (.xlsx, .xls, .xlsm, .tsv, .csv, .txt) — flat file viejo con datos
- **New Flat File** (.xlsx, .xls, .xlsm, .tsv, .csv, .txt) — template nuevo descargado de Seller Central → Catalog → Add Products via Upload → Download Template

### Outputs
- Stats: columnas migradas / solo en nuevo / no migradas / filas migradas / example row saltada / filas Amazon filtradas / match por método
- Listas color-coded en expander: 🟢 migradas · 🔴 no encontradas en nuevo · 🟠 solo en nuevo
- Download: `{base}_migrated.xlsx` o `{base}_migrated.tsv`

### Validación
- `py_compile` verde en `flat_file_migrator.py`, `app.py`, `core/constants.py`
- Stateless: no hay `st.session_state` para datos persistentes (solo widget keys)
- Empty state con borde dashed `#FFD9B3` y mensaje "📂 Subí los flat files para arrancar"
- Header `🏥 Flat File Migrator` con divider (patrón Account Health)

### Anti-patterns
- NO arreglar bugs del HTML original durante el porting (regla del Caso 1 del porter)
- NO inventar marketplaces nuevos — los 5 son los que el HTML original soporta
- NO usar `pd.read_excel` para parsear — openpyxl preserva mejor la estructura de rows pre-data
- NO usar `aoa_to_sheet` equivalent en pandas — openpyxl `Workbook()` + `ws.append()` es más fiel al output del HTML
- NO eliminar el "Skip example row" checkbox — es comportamiento esperado por el AM
- NO traducir las keywords del header detection — están en 5 idiomas a propósito
- NO modificar el dict `_ALIASES` — es copia literal del HTML, fiel al comportamiento del compañero
- NO omitir el BOM `﻿` en el TSV — el HTML lo agrega y Amazon Seller Central lo espera
- NO permitir output XLSM ni preservar macros del template (el template Amazon flat file no tiene macros relevantes — divergencia respecto a M26 Variation Builder por diseño)

### Deuda técnica heredada del HTML (NO arreglada por regla del Caso 1)
- **Header row override quirky** (L997-998): comportamiento contraintuitivo cuando user pone `1` y hay auto-detect. Documentado, no arreglado.
- **`looksLikeFieldIds` regex frágil** (L1005): falsos positivos posibles en headers cortos. Documentado, no arreglado.
- **`aoa_to_sheet` no preserva data validations / formulas / macros** del new template — solo column widths en HTML, ni eso en el porting Python (openpyxl no lo provee con la misma facilidad). Si el AM reporta pérdida de validations al subir el migrado, evaluar refactor con `keep_vba=True` + copiado de `data_validations` (pero NO durante el porting, sí como sesión separada).
- **Mensaje de error mezcla idiomas** (`'Error al leer el archivo: ' + err.message` en el HTML — alert en español, código en inglés). Replicado en español como `st.error("Error al leer el archivo: ...")`.

### Propuestas no implementadas — para sesiones futuras
- **Preview de los datos migrados** antes de descargar (primeras 20 rows) — útil para validar el mapping a ojo antes de comprometerse al download
- **Editor manual del mapping** post-detección automática: tabla `st.data_editor` para que el AM corrija mappings que el algoritmo no pudo resolver
- **Persistir mappings custom por marketplace** en `data/account_health/flat_file_mappings.parquet` — si el AM aprende que `mi_kw_custom` siempre debe mapear a `generic_keyword`, recordarlo entre sesiones (Caso 2 — requiere coordinación con `data-persistence-specialist`)
- **Soporte input TSV / CSV directo** — el HTML acepta `.tsv` y `.csv` en el `accept` pero `XLSX.read` los parsea con auto-detect. En el porting Python `openpyxl.load_workbook` solo abre Excel — los TSV/CSV no van a funcionar como input. Documentado como limitación del v1.
- **Diff visual entre old → new column mapping** con flechas/líneas (cosmético)
- **Multi-archivo batch**: subir 5 old files al mismo tiempo y migrar a 5 templates distintos en una sola pasada
- **Detección de Category Listing vs Flat File más estricta**: usar el campo `feed_product_type` para mapear automáticamente la categoría correcta y avisar si old y new son de categorías distintas

---

## M28 — SKU Progress Report
**Archivo:** modules/pages/sku_progress_report.py
**Sección sidebar:** Account Health
**Session state prefix:** sku_progress_
**Fuente:** porteado de `.claude/porting-sources/sku-progress-report.html` (2026-05-07)
**Schema:** `data/_schemas/sku-progress-v1.json` (commit d9fd787)
**Persistencia:** `data/account-health/<cliente>/sku-progress/`

### Propósito
Tracker semanal de progreso por SKU. Multi-cliente. Reemplaza el HTML legacy de Gamboa (data embedded) por una capa de persistencia centralizada vía `core.persistence`. Cruza CSVs de "Detail Page Sales and Traffic By Child Item" semanales con un log append-only de optimizaciones aplicadas (cambio de imágenes, A+ Content, etc.) para correlacionar acción → impacto en CVR / sessions / sales.

### Arquitectura
- **Multi-cliente** via `st.selectbox` al tope. El selector lista clientes que tengan carpeta en `data/account-health/<cliente>/sku-progress/`. Si no hay clientes → empty state + botón "➕ Cliente nuevo" que crea la carpeta y el `tracked-skus.json` vacío.
- **Tabs por SKU dentro del cliente seleccionado** + 2 tabs fijas: `📤 Importar CSV` y `⚙️ Admin`. Una tab por SKU recargable: hero (imagen + título + botones), badges de eventos, KPI cards (7), 1 chart cruzado (CVR + Avg Price + Sessions con anotaciones de eventos) + 4 charts en grid 2x2 (Plotly), tabla detallada.
- **Modals via `st.dialog()`**: agregar SKU, editar SKU, registrar/editar evento, confirmar borrado, agregar cliente nuevo.
- **Parser CSV cacheado**: `_parse_csv_bytes(raw, filename)` con `@st.cache_data(show_spinner=False)`. Replica literal de `parseCSV()` del HTML L3267-3332.
- **Consolidación variants**: `_consolidate_rows_by_sku()` replica `buildPreview()` L3433. Una row consolidada por SKU; CVR y avg_price recalculadas POST-consolidación. Decisión bloqueada en el schema (`consolidation_rule.additive_columns` + `derived_post_consolidation`).
- **Excel export**: `_build_sku_progress_excel()` fuera de `render()` (patrón openpyxl-bug-prevention). Hojas: Resumen, Detalle, Optimizaciones, una por SKU.

### Helpers principales
- `_list_clientes()` — escanea `data/account-health/*/sku-progress/`
- `_load_tracked_skus(cliente)` / `_save_tracked_skus(cliente, config)` — JSON per-cliente (excepción documentada abajo)
- `_period_str(year, week_iso)` — `"2026-W14"` canonical
- `_parse_period_str(period)` — inverse
- `_iso_week_dates(year, week_iso)` — devuelve (lunes, domingo)
- `_week_label_es(year, week_iso)` — `"Mar 29-Abr 4"` (ES)
- `_detect_week_from_filename(filename)` — soporta `2026-W14`, `W14`, `wk14`, `semana14`
- `_parse_csv_bytes` / `_split_csv_line` — replica literal del parser JS
- `_consolidate_rows_by_sku` — replica de buildPreview con consolidación de variants
- `_build_snapshot_df` — construye DataFrame con schema sku-progress-v1
- `_render_sku_tab` / `_render_import_tab` / `_render_admin_tab` — sub-renders
- `_dialog_add_sku` / `_dialog_edit_sku` / `_dialog_add_event` / `_dialog_confirm_delete_sku` / `_dialog_add_cliente` — modals via `@st.dialog`

### Reglas de negocio (porteadas literal del HTML)
- **CSV_PRIORITY**: priority list de headers (espejo HTML L3236) — `sessions - total > sessions`, `unit session percentage > order item session percentage`, etc.
- **CSV_IGNORE**: ~30 columnas descartadas siempre (splits B2B / Mobile / Browser, percentages no relevantes). Espejo HTML L3248.
- **Year=2026 hardcoded en v1** (decisión Lenin). El campo `year` es editable en el form de import por si el AM carga retro.
- **Una fila consolidada por SKU** en el snapshot. Variants se agregan ANTES de escribir Parquet — additive: sessions, page_views, units_ordered, total_order_items, ordered_product_sales. Derived post-consolidación: `unit_session_pct = units_ordered / sessions * 100` y `avg_price = ordered_product_sales / units_ordered`.
- **Match SKU**: equality case-insensitive primero, fallback a substring bidireccional (heredado del HTML — bug documentado abajo).
- **Eventos = log append-only**: cada evento es 1 row inmutable en `optimizations.parquet`. Editar/borrar eventos NO existe en v1 — el HTML sí los permitía pero el modelo append-only del agency OS lo prohíbe. Si se quiere "borrar" un evento, agregar uno nuevo con label `"REVERT: <label original>"` (deuda técnica documentada abajo).

### Inputs
- **CSV semanal "Detail Page Sales and Traffic By Child Item"** (Seller Central → Reports → Business Reports). UTF-8 con BOM o latin-1 fallback.
- **Cliente** (selectbox al tope) — auto-discover de `data/account-health/*/sku-progress/`.
- **SKU agregado vía modal**: SKU obligatorio, ASIN/title/image_url/link opcionales.
- **Evento agregado vía modal**: SKU + week (period) + label libre.

### Outputs
- **Snapshot Parquet semanal** en `data/account-health/<cliente>/sku-progress/<YYYY-WW>.parquet` validado contra schema sku-progress-v1.
- **Log Parquet append-only** en `optimizations.parquet`.
- **Excel multi-hoja** descargable: Resumen + Detalle + Optimizaciones + una hoja por SKU con su evolución completa.

### Excepción documentada — `tracked-skus.json` NO usa `_save_config` / `_load_config`

`core.persistence._save_config()` y `_load_config()` son **client-agnostic por diseño** (path: `data/<area>/<modulo>/<name>-v<version>.json`, sin nivel cliente). El config de SKUs trackeados de SKU Progress es **per-cliente** y debe vivir junto a los snapshots para que un borrado total del cliente sea atómico (carpeta única `data/account-health/<cliente>/sku-progress/`).

Por eso el módulo define helpers locales:
```python
_load_tracked_skus(cliente: str) -> dict        # lee data/account-health/<cliente>/sku-progress/tracked-skus.json
_save_tracked_skus(cliente: str, config: dict)  # escribe en el mismo path
```

**Regla del skill data-persistence-standard**: "los casos especiales matan el patrón". NO se promueve esta excepción a la API global hasta que aparezca un M30+ con la misma necesidad de config per-cliente. Si eso pasa, el `data-persistence-specialist` evalúa agregar `_save_client_config` / `_load_client_config` a `core/persistence.py`.

### Excepción 2 — `shutil.rmtree()` para borrar cliente entero

Helper privado `_delete_cliente()` en el módulo usa `shutil.rmtree()` directo sobre `data/account-health/<cliente>/`. NO se delegó a `core/persistence.py` porque:

- El skill `data-persistence-standard` tiene regla dura "cero borrados automáticos" (apunta al código corriendo solo, no al usuario clickeando un botón en UI).
- La acción está protegida por type-to-confirm en `_dialog_borrar_cliente`: el usuario debe escribir el slug exacto del cliente para habilitar el botón "Borrar definitivamente".
- El borrado es atómico (carpeta única `data/account-health/<cliente>/`) — todo el tracking del cliente se va de una vez, sin estados parciales.
- Counts pre-delete se muestran en el dialog para feedback explícito antes del confirmar.

Trigger de promoción a `core/persistence.py`: si aparece un 2do módulo Account Health con la misma necesidad de borrar cliente entero (ej: M29 Pricing Dashboard cuando se portee), promover a `_delete_cliente_data(area, cliente)` (~12 líneas, retrocompatible). Hasta entonces, vive como helper local del módulo M28.

### Validación end-to-end
- `py_compile` verde en `sku_progress_report.py`, `app.py`, `core/constants.py`
- No hay `pd.read_parquet` ni `pd.to_parquet` directo en el módulo (todo via `core.persistence`)
- No hay `pd.read_csv` en el módulo (parser custom byte-level porque el HTML usa parser JS custom — preserva paridad con el HTML legacy)
- El JSON de config se gestiona localmente con `json.loads/dumps` (excepción documentada arriba)
- Empty states correctos: sin clientes → mensaje + botón "Cliente nuevo"; cliente sin SKUs → mensaje + indicación dónde bajar el CSV
- Header `🏥 SKU Progress Report` con divider (patrón Account Health)
- Excel builder fuera de `render()` (patrón anti-bug openpyxl)
- 1 solo `return` dentro de `render()` — para early-exit cuando no hay clientes

### Deuda técnica heredada del HTML (NO arreglada por regla del Caso 2)
- **Match SKU substring bidireccional** (HTML L3444): el matching `id.includes(k.toUpperCase()) || k.toUpperCase().includes(id)` puede generar falsos positivos. Ej: SKU "ABC" matchea row del CSV con id "ABC123" (y viceversa). Documentado, no arreglado para preservar paridad. Si el AM reporta cruces incorrectos, escalar a sesión separada.
- **`splitCSVLine` no maneja escaped quotes** (HTML L3335): un campo con `""` adentro (escape de comilla) no se parsea correctamente. Limitación del parser JS replicada literal en Python. Mitigación: el CSV de Amazon "Detail Page Sales..." rara vez tiene quotes anidadas — si aparece, el AM verá warning de fila descartada.
- **`weekLabel` JS hardcodea año 2025** (HTML L3386): inconsistente con el contexto del módulo (2026). En el porting Python NO se replica — usamos `date.fromisocalendar(year, week_iso, 1)` que es correcto. Esta es la **única divergencia funcional** del porting (la otra es exportHTML, que se reemplaza por persistencia).
- **Subtítulo del header HTML hardcodea 2025** (L3563): no aplica al porting (no hay subtítulo dinámico).
- **`confirm()` browser native** (HTML L2991, L3052, L3069): UX inconsistente. En el porting se reemplaza por `st.dialog()` con botones explícitos (mejor UX, pero divergencia documentada).
- **Validación URL imagen** (HTML `onerror`/`onload`): en Streamlit `st.image()` muestra placeholder/error si la URL no carga, sin bloqueo del flow. Equivalente funcional.
- **No se permite editar/borrar eventos individuales** (divergencia con HTML que sí los permite): el modelo append-only del Agency OS los hace inmutables. El HTML usaba splice/index access que no es compatible con Parquet append-only. Documentado como deuda funcional.

### Propuestas no implementadas — para sesiones futuras
- **Migración de la data Gamboa actual del HTML legacy**: el HTML tiene 21 SKUs × 15 semanas (Ene-Abr 2026) + eventos ya cargados. La migración no se hace en esta sesión por decisión Lenin (validar primero módulo vacío). Plan: script `scripts/migrate_gamboa_sku_progress.py` que parsee el `DATA = {...}` const del HTML, construya 15 snapshots Parquet + N filas en optimizations.parquet + 1 tracked-skus.json. Sesión separada.
- **Edit/delete de eventos individuales**: hoy el log es append-only. Para "deshacer" un evento, agregar uno nuevo con label `"REVERT: <label original>"`. Mejor UX: agregar columna `_deleted: bool` al schema (v2) y filtrar en `_load_log` con flag `include_deleted=False`. Discutible si vale la pena romper la inmutabilidad.
- **Vista cross-SKU del cliente** (dashboard de salud agregado): hoy cada SKU es una tab; falta una vista "total cliente" con todos los SKUs en una matriz CVR×Sales. Útil cuando el cliente tenga >10 SKUs.
- **Filtro temporal en tabs SKU**: hoy se muestran todas las semanas con datos. Útil agregar slider "últimas N semanas" para vistas focalizadas.
- **Detección automática de week del CSV**: hoy detecta del filename con regex. Si falla, usa la semana actual. Mejora: parsear la columna "Reporting Range" del CSV (Amazon a veces la incluye).
- **Comparativa entre 2 clientes**: para detectar patterns cross-clientes (ej: "Gamboa y Dermaglos cayeron en CVR la misma semana — ¿problema Amazon?"). Requiere multi-cliente desktop view.
- **Heatmap de optimizaciones aplicadas**: vista calendario que muestra qué semanas tuvieron eventos y cuáles no. Útil para identificar gaps de actividad del AM.
- **Export PDF para cliente**: hoy solo Excel. Para presentaciones cliente-facing, un PDF con gráficos embebidos es mejor.

### Anti-patterns
- ❌ NO usar `pd.read_csv` directo — el parser custom byte-level (replicando JS) es deliberado para preservar paridad con el HTML legacy.
- ❌ NO promover `_load_tracked_skus`/`_save_tracked_skus` a `core/persistence.py` hasta que aparezca M30+ con la misma necesidad.
- ❌ NO arreglar bugs del HTML durante el porting (regla del Caso 2): match substring bidireccional, escape quotes, etc. Documentar, no fixear.
- ❌ NO replicar `exportHTML()`: los datos viven en `data/`. Cambio de UX deliberado, decisión bloqueada en daily 2026-05-06.
- ❌ NO hardcodear años (excepto YEAR_DEFAULT=2026 que es decisión bloqueada v1).
- ❌ NO usar `pd.read_parquet`/`pd.to_parquet` directo — todo I/O via `core.persistence`.
- ❌ NO permitir borrar/editar eventos via UI individual del badge (modelo append-only).
- ❌ NO usar `st.metric` — usar `kpi_card` de `core.helpers`.
- ❌ NO portar el CSS dark del HTML — el Agency OS es light theme.
- ❌ NO mezclar lógica I/O en `render()` — pasar todo por `_save_snapshot`/`_append_log`/`_rebuild_history` después de la acción del usuario.


---

## M30 — Pricing Dashboard
**Archivo:** modules/pages/pricing_dashboard.py
**Sección sidebar:** Account Health (label `💲 Pricing Dashboard`)
**Session state prefix:** m30_ (m30_resultados, m30_aviso_backup, m30_filtros)
**Fuente:** porteado de `.claude/porting-sources/pricing-dashboard.html` (Caso 2, port verbatim)
**Schema:** `data/_schemas/pricing-dashboard-v1.json` (47 col, 21 required, primary_key sku)
**Persistencia:** `data/account-health/<cliente>/pricing-dashboard/<YYYY-MM-DD>.parquet` + config `data/account-health/pricing-dashboard/<cliente>-v1.json`

### Propósito
Scoring de pricing semanal por SKU: clasifica cada SKU en bajar / subir / liquidar / mantener con precio sugerido y rationale, cruzando FBA inventory + fees + P&L (COGS) + maestro de productos. Espejo fiel del HTML standalone del compañero.

### Arquitectura (F3.1–F3.6)
- **F3.1** schema v1 + test persistencia. **F3.2** 6 parsers (`_parse_fba/_fee/_awd/_pl/_maestro/_izzi`, bytes→DataFrame, `@st.cache_data`) + 3 lookups (`_build_cogs/_fee/_maestro_lookup`). **F3.3** scoring (`_compute_ais`, `_compute_score` 20+ reglas umbrales asimétricos, `_enrich_record`, `_run_analysis`). **F3.4** UI: render() + selector cliente + 6 uploaders + `st.tabs` (Resumen/Principal/AWD-FBA/Liquidar/Sin Margen/AIS/Histórico) + styler + filtros + persistencia/import JSON. **F3.6** integración router.
- **Config per-cliente** vía `core.persistence._save_config/_load_config` (`_load_or_seed_config` seedea SUBCAT_FEE_AVG verbatim del HTML la primera vez; NUNCA persiste current_month).
- **Snapshots/histórico** vía `core.persistence` verbatim (`_save_snapshot/_load_history/_list_periods/_rebuild_history/_validate_against_schema`). `_build_snapshot_df` mapea record_key→schema_col (los nombres DIFIEREN: Modelo→modelo, fulfillment_fee→ff, suggestedPrice→suggested_price, reasons_* list→JSON string, etc.) y coacciona dtypes a las 47 col exactas.
- **Import JSON** (`_importar_historico_json`): array `{date, skus:{...}}` del HTML; 2-pasadas (build+valida todo en memoria, recién después persiste + rebuild) → all-or-nothing.

### Reglas de negocio (porteadas literal del HTML)
- **Umbrales asimétricos**: `score <= -50` → bajar; `score >= 20` → subir; is_liquidar PRECEDE a la clasificación por score.
- **Bug 30-vs-37 (heredado, NO arreglar)**: `_enrich_record` setea restock con PATH-37 (`round(daily_rate*37)`, msg "a FBA desde"); el PATH-30 de `_compute_score` (`*30`, "desde", guard `not restock_alert`) queda dead-code.
- **Rounding**: `_round_half_up` (=floor(x+0.5)) replica `Math.round` (NO `round()` nativo). `_to_fixed`/`_js_num` para strings.
- **Separador CSV** autodetectado (;/, en primera línea) + utf-8-sig; NO replica el parseCSV custom del HTML (trim/descarte <2 campos) — divergencia conocida congelada en `TestCsvDivergenciasHTML`.
- **current_month** desde config (fallback `date.today().month`) para isOffSeason determinístico.

### Deuda / gaps conocidos
- **AWD/Izzi sin builder**: `_parse_awd/_parse_izzi` devuelven DataFrame crudo; no hay builder df→lookup `{sku: unidades}`. La tab AWD/FBA es un panel pendiente (`st.warning`), backup stock = 0. Diferido (F3.2→F3.3 nunca lo construyó).
- **F3.5 (export XLSX) pendiente**.

### Anti-patterns / reglas
- ❌ NO tocar parsers/lookups/scoring de F3.2-F3.3 (cerrados, reviewer-aprobados).
- ❌ NO crear helpers de persistencia nuevos — todo I/O via `core.persistence` verbatim.
- ❌ NO normalizar strings de Amazon ('Excess','Invierno'...) — verbatim.
- ❌ NO usar `round()` nativo donde el HTML usa `Math.round` — usar `_round_half_up`.
- ❌ NO persistir current_month en el config.


---

## SOP in-app por módulo (convención, 2026-06-21)
Cada módulo de cara al usuario embebe su guía de uso como:
- Constante módulo-level `_SOP_MD` = string markdown triple-quoted, ubicada junto a las otras constantes del tope del archivo.
- En `render()`, apenas debajo del header del módulo: un `st.expander("📘 Cómo usar este módulo", expanded=False)` con `st.markdown(_SOP_MD)` adentro. TOP-LEVEL, nunca anidado dentro de otro expander/popover.
Aplicado en: sku_progress_report.py, pricing_dashboard.py, proposal_studio.py (commits 2607b4e + 797f7eb).
La copia de equipo (fuera de la app) vive en notes/sops/SOP_USER_*.md. El `_SOP_MD` del módulo es la fuente de verdad; los .md se mantienen en sync con él.
