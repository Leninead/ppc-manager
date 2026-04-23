# CLAUDE.md — Módulos del Agency OS
## Contexto por módulo para agentes especializados
Última actualización: 2026-04-22

---

## M1 — Inicio
**Archivo:** modules/pages/inicio.py
**Sección sidebar:** —
**Session state prefix:** —

### Propósito
Dashboard de estado del Agency OS. Muestra 25 módulos agrupados por sección, Workflow Wizard piramidal (5 niveles), changelog y estado del Parent-Child map.

### Arquitectura
- 3 cards activas: PPC (10 módulos) + Account (6) + Research (7) + Intelligence (2)
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
Analizar mercado total (no solo ads propias). Detecta marca automáticamente.

### Arquitectura
4 tabs: General (raw SQP) | Market Share (IS/CS/PS) | Gap Analysis (oportunidades) | Análisis IA

### Reglas de negocio
- Impression Share = Brand Impressions / Total Impressions × 100
- Clasificación: IS >30% (Dominando) | 10-30% (Competitivo) | <10% (Oportunidad)
- Gap detection: Total Imp > 1000 AND Brand Imp = 0 → agregar keyword

### Inputs
- SQP (.xlsx o .csv) — requerido

### Anti-patterns
- Confundir Purchase Share con Conversion Rate — son métricas del mercado, no propias

---

## M4 — Análisis Cruzado STR vs SQP
**Archivo:** modules/pages/analisis_cruzado.py
**Sección sidebar:** PPC
**Session state prefix:** cruzado_

### Propósito
Cruzar STR + SQP para detectar gaps de cobertura y oportunidades de mercado.

### Arquitectura
3 tabs: Cruce (venn), Plan de Acción (recommendations), PPC Insights por ASIN (opcional BR)

### Reglas de negocio
- En ambos = ya tenés cobertura
- Solo SQP = oportunidad (agregar)
- Solo STR = validar si es relevante (bajar bid vs negar)
- Plan de Acción: AGREGAR / HARVEST / BAJAR BID / ESCALAR / MONITOREAR

### Inputs
- STR + SQP simultáneamente
- Opcional: BR by ASIN (Tab 3)
- Filtros: impresiones min, SQS, purchases, tipo Marca/Genérica

### Anti-patterns
- No filtrar por mercado real — mantener todos para contexto completo

---

## M5 — Tendencia Multi-Semana
**Archivo:** modules/pages/tendencia_multisemana.py
**Sección sidebar:** PPC
**Session state prefix:** tendencia_

### Propósito
Detectar estacionalidad y tendencias de queries a lo largo de semanas.

### Arquitectura
Carga hasta 4 SQPs, pivotea por Query, marca tendencia con ↑↓→

### Reglas de negocio
- ↑ >10% | → estable | ↓ >10%
- Auto-detección mes desde filename o columna "Reporting Range"

### Inputs
- SQP (hasta 4 archivos)

### Anti-patterns
- Cargar 2 SQPs iguales = KeyError (fixed en sesión anterior)

---

## M6 — Bulk Campañas + Campaign Analyzer
**Archivo:** modules/pages/bulk_campanas.py
**Sección sidebar:** PPC
**Session state prefix:** bulk_

### Propósito
Diagnosticar salud de campañas activas. Campaign Analyzer es el principal.

### Arquitectura
3 tabs: General (raw), Campaign Analyzer (semáforo), Auditoría PPC (naming + graduation)

### Reglas de negocio
- Semáforo: 🔴 PAUSAR (spend > threshold, 0 orders) | 🟡 REVISAR (ACoS > target×2) | ✅ ESCALAR (ACoS < target×0.5) | ⚫ FANTASMAS (0 impresiones)
- Spend recuperable = suma de campañas pausables
- Naming convention check: detecta patrón [Marca]-[ASIN]-[Tipo]-...

### Inputs
- Campaign CSV (.csv) con performance metrics — requerido
- Target ACoS + Precio — Tab 2

### Anti-patterns
- Subir bulk file (.xlsx) sin métricas — solo muestra General
- Confundir Campaign ID (numérico) con Campaign Name (texto)

---

## M7 — Business Report
**Archivo:** modules/pages/business_report.py
**Sección sidebar:** PPC
**Session state prefix:** br_

### Propósito
Analizar ventas orgánicas + paid por ASIN. Fuente del Parent-Child map.

### Arquitectura
Raw dataframe display con cálculo automático de CVR, BuyBox, etc.

### Inputs
- BR (.csv) By Date o By ASIN

### Anti-patterns
- No confundir columnas "Unit Session %" vs "Order Item Session %"

---

## M8 — Análisis de Funnel
**Archivo:** modules/pages/analisis_funnel.py
**Sección sidebar:** PPC
**Session state prefix:** funnel_

### Propósito
Detectar brechas en el funnel Auto → Broad → Phrase → Exact por ASIN.

### Arquitectura
Carga STR + Bulk, mapea keywords por match type, sugiere campañas faltantes

### Reglas de negocio
- Harvest: Auto→Phrase 2+ orders AND ACoS ≤ target×1.2 | Phrase→Exact 3+ orders AND ACoS ≤ target
- Naming convention: [Marca]-[ASIN]-SP-KW-[MATCH]-[Descriptor]

### Inputs
- STR + Bulk file

### Anti-patterns
- Incluir campañas pausadas — filtrar por Status = ENABLED

---

## M9 — Bid Optimizer
**Archivo:** modules/pages/bid_optimizer.py
**Sección sidebar:** PPC
**Session state prefix:** bid_

### Propósito
Calcular bids óptimos por keyword basado en CVR real, precio y target ACoS.

### Arquitectura
2 tabs: Bids (semáforo + export bulk) | Placements & Budget (referencia + estimado)

### Reglas de negocio
- Fórmula: bid = CVR × precio × target_ACoS
- Clasificación: 🟢 SUBIR <0.7x | ⚫ OK 0.7-1.3x | 🔴 BAJAR >1.3x | ⛔ PAUSAR clicks>10 + 0 orders
- Placement modifiers: Exact +50% ToS | Harvest +25% ToS | PAT +50% PDP

### Inputs
- STR (.xlsx) — requerido
- Inventory Report (.txt) — extraer precio exacto
- Target ACoS (slider) + override manual

### Anti-patterns
- Subir bid sin validar que ASIN es correcto en Inventory
- Aplicar bids en warm-up < 14 días

---

## M10 — Campaign Builder
**Archivo:** modules/pages/campaign_builder.py (con soporte SP/SB/SD)
**Sección sidebar:** PPC
**Session state prefix:** campaign_

### Propósito
Generar bulk de nuevas campañas (SP/SB/SD) a partir del Plan de Acción.

### Arquitectura
Selector tipo (SP/SB/SD), clustering automático, preview editable, export bulk formato exacto Amazon

### Reglas de negocio
- SP clustering: PAT / Spanish (prioridad) / Brand / Vitamin A / Discovery
- Max 5 keywords por campaña (regla Capybaras)
- SB requiere: headline 50 chars, brand name, 3 ASINs creativos
- SD requiere: Product Targeting o Audience, bid optimization

### Inputs
- Plan de Acción bulk (de Módulo 4)
- Marca, ASIN, SKU, precio, CVR, target ACoS, budget

### Anti-patterns
- No validar SKUs contra Inventory — Amazon rechaza ASIN en bulk SP
- No cruzar contra Exact activas — canibalización

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

### Arquitectura
4 inputs (BR diario, BR by ASIN, Atom11, Campaign CSV) → 4 sheets Excel con branding Capybaras

### Reglas de negocio
- PW vs TW automático (12+2 días)
- Detección BuyBox faltante si BR no tiene columna
- Toggle ES/EN para redacción ejecutiva

### Inputs
- BR diario 14d + BR by ASIN + Atom11 ASIN + Campaign CSV
- Client name + Language (ES/EN)

### Anti-patterns
- No validar date range — debe ser idéntico en los 4 archivos
- BuyBox con 0 sesiones → ignorar

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
**Archivo:** modules/pages/datadive_analyzer.py (380+ líneas)
**Sección sidebar:** Research
**Session state prefix:** datadive_

### Propósito
Analizar exports DataDive (nicho, competidores, rank radar) para detectar oportunidades de mercado.

### Arquitectura
4 tabs (después 5 con Competitor Intel): MKL Keywords | Competitors | Rank Radar | Ranking Volatility+PPC IS | Competitor Intel

### Reglas de negocio
- Tab 1: SV, Relevance, Launch Score, ranking competidores. Color: verde Rel ≥3, amarillo ≥2, rojo <2
- Tab 3: tracking orgánico diario, tendencia ↑→↓, PPC coverage
- Tab 4: volatilidad (std dev), clasifica ESTABLE/VOLÁTIL/MUY VOLÁTIL, flags riesgo/oportunidad
- Tab 5: tu MKL + competidor, clasifica Ambos/Solo yo/Solo comp/Ninguno

### Inputs
- DataDive exports (.xlsx)

### Anti-patterns
- return-in-tabs bug — fijar con paréntesis en cada tab call

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
