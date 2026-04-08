# CLAUDE.md — Módulos del Agency OS
## Contexto por módulo para agentes especializados
Última actualización: 2026-04-08

---

## M1 — Inicio
**Archivo:** modules/pages/inicio.py
**Sección sidebar:** —
**Session state prefix:** —

### Propósito
Dashboard de estado del Agency OS. Muestra 22 módulos agrupados por sección, Workflow Wizard piramidal (5 niveles), changelog y estado del Parent-Child map.

### Arquitectura
- 3 cards activas: PPC (10 módulos) + Account (4) + Research (7)
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
- STR (.xlsx/.csv) — requerido
- Campaign CSV (.csv) — opcional (para anti-canibalización en Tab 3)
- Brand terms — input texto

### Anti-patterns
- NUNCA negativizar dentro de Exact Match propia
- NUNCA usar threshold fijo de clicks — siempre tiers dinámicos por precio
- Tab IA usa Claude API — no replicar con templates fijos

---

## M3 — Search Query Performance (SQP)
**Archivo:** modules/pages/search_query_performance.py
**Sección sidebar:** PPC
**Session state prefix:** sqp_

### Propósito
Analizar datos de Brand Analytics: market share, gaps de búsqueda y oportunidades orgánicas.

### Arquitectura
4 tabs: Dashboard | Market Share | Gap Analysis | Análisis IA

### Reglas de negocio
- Parser: read_sqp() con skiprows=1
- Marca extraída con extract_sqp_brand() desde row 0
- Market Share: Dominando (IS >30%) / Competitivo (10-30%) / Oportunidad (<10%)
- Gap: queries con alto volumen donde brand impressions = 0

### Inputs
- SQP (.xlsx) — requerido

### Anti-patterns
- No confundir SQP impression share con PPC impression share — son métricas distintas

---

## M4 — Análisis Cruzado STR vs SQP
**Archivo:** modules/pages/analisis_cruzado.py
**Sección sidebar:** PPC
**Session state prefix:** cruzado_

### Propósito
Cruzar STR contra SQP para detectar gaps y oportunidades. El Plan de Acción es el INPUT del Campaign Builder.

### Arquitectura
3 tabs: Cruce (En ambos / Solo STR / Solo SQP) | Plan de Acción (acciones sugeridas + bulk) | PPC Insights por ASIN (BR opcional)

### Reglas de negocio
- Opportunity Score = min-max normalizado de impresiones + clicks + purchase rate
- Acciones: AGREGAR (alta compra, no aparecés) / HARVEST (buen ACoS, agregar Exact) / BAJAR BID (ACoS > target × 2) / ESCALAR (IS bajo + mercado comprando) / MONITOREAR
- Detección marca: automática desde SQP, manual fallback con input texto

### Inputs
- STR (.xlsx/.csv) + SQP (.xlsx) — requeridos
- BR by ASIN (.csv/.xlsx) — opcional para Tab 3

### Anti-patterns
- El bulk del Plan de Acción NO se sube directo a Amazon — se sube al Campaign Builder

---

## M5 — Tendencia Multi-Semana
**Archivo:** modules/pages/tendencia_multisemana.py
**Sección sidebar:** PPC
**Session state prefix:** tendencia_

### Propósito
Ver evolución de queries a lo largo de 2-4 semanas para detectar estacionalidades.

### Arquitectura
Upload de 2-4 SQPs → pivot por Search Query → clasificación tendencia

### Reglas de negocio
- ↑ Creciendo: cambio > +10%
- → Estable: entre -10% y +10%
- ↓ Cayendo: cambio < -10%

### Inputs
- 2 a 4 archivos SQP de semanas distintas

### Anti-patterns
- No usar para comparar períodos > 4 semanas — pierde contexto

---

## M6 — Bulk Campañas + Campaign Analyzer
**Archivo:** modules/pages/bulk_campanas.py
**Sección sidebar:** PPC
**Session state prefix:** bulk_

### Propósito
Ver estructura de campañas y diagnosticar estado con semáforo automático.

### Arquitectura
3 tabs: Vista General (raw) | Campaign Analyzer (semáforo) | Auditoría PPC (naming + target graduation)

### Reglas de negocio
- Semáforo: PAUSAR (spend > threshold, 0 orders) / REVISAR (ACoS > target × 2) / ESCALAR (ACoS < target × 0.5 con orders) / FANTASMA (0 impressions)
- Naming check: verifica patrón [Marca] | [ASIN] | [MKT] | [Tipo]-[SubTipo] | [Match] | [Cluster]
- Target graduation: campañas con 0 impresiones que necesitan revisión
- Las pausas se hacen MANUALMENTE en Campaign Manager (requiere Campaign ID numérico)

### Inputs
- Campaign CSV (.csv) con métricas — requerido
- Target ACoS + precio promedio — inputs manuales

### Anti-patterns
- NO confundir Campaign CSV (métricas) con Bulk File (.xlsx multi-hoja)

---

## M7 — Business Report
**Archivo:** modules/pages/business_report.py
**Sección sidebar:** PPC
**Session state prefix:** br_

### Propósito
Analizar ventas, sesiones, CVR y BuyBox por ASIN. Fuente del Parent-Child map.

### Arquitectura
Vista de datos crudos del BR. Se usa principalmente como input para Weekly Client Report.

### Reglas de negocio
- Detecta automáticamente Unit Session Percentage o Order Item Session Percentage
- BuyBox con 0 sesiones → ignorado

### Inputs
- Business Report (.csv/.xlsx) — By Date o By ASIN

### Anti-patterns
- No duplicar lógica de BR que ya está en core/business_report.py

---

## M8 — Análisis de Funnel
**Archivo:** modules/pages/analisis_funnel.py
**Sección sidebar:** PPC
**Session state prefix:** funnel_

### Propósito
Detectar brechas en el funnel de match types (Auto → Broad → Phrase → Exact) por ASIN.

### Arquitectura
Mapa de funnel actual + gaps detectados + campañas sugeridas

### Reglas de negocio
- Auto → Phrase: 2+ orders AND ACoS ≤ target × 1.2
- Phrase → Exact: 3+ orders AND ACoS ≤ target
- Campañas sugeridas con naming convention Capybaras
- Solo campañas ENABLED

### Inputs
- STR (.xlsx/.csv) + Bulk file de campañas — requeridos

### Anti-patterns
- No sugerir Exact para keywords con < 3 orders — insuficiente data

---

## M9 — Bid Optimizer
**Archivo:** modules/pages/bid_optimizer.py
**Sección sidebar:** PPC
**Session state prefix:** bid_

### Propósito
Calcular bid óptimo por keyword basado en CVR real, precio y target ACoS.

### Arquitectura
2 tabs: Bids (fórmula + semáforo) | Placements & Budget (referencia SOP + detección por naming)

### Reglas de negocio
- bid_sugerido = (CVR / 100) × precio × (target_ACoS / 100)
- SUBIR: bid actual < sugerido × 0.7
- OK: entre 0.7x y 1.3x
- BAJAR: bid actual > sugerido × 1.3
- PAUSAR: clicks > 10 AND orders = 0
- Placements SOP: Exact Ranking ToS+50%, Exact Harvest ToS+25%, PAT Competitor PDP+50%

### Inputs
- STR (.xlsx/.csv) — requerido
- Inventory Report (.txt) — opcional (precio exacto)
- Target ACoS (slider) + precio promedio

### Anti-patterns
- No optimizar bids antes de 14 días (learning period)
- No usar Fixed Bid después de warm-up — cambiar a Dynamic

---

## M10 — Campaign Builder
**Archivo:** modules/pages/campaign_builder.py
**Sección sidebar:** PPC / Ejecución
**Session state prefix:** cb_

### Propósito
Generar bulk listo para subir a Amazon con nuevas campañas SP.

### Arquitectura
Input: Plan de Acción bulk → datos producto → preview → export bulk Amazon

### Reglas de negocio
- Clustering: PAT (B0...) / Spanish (palabras ES) / Brand (nombre marca) / Discovery (resto)
- Spanish prioridad sobre Brand (mercado hispano USA)
- Max 5 KWs por campaña
- Bidding: Exact Brand/Ranking → Fixed Bid + ToS+50% | Exact Harvest → Dynamic Down + ToS+25% | Phrase → Dynamic Down + ToS+10% | Auto → Fixed, sin modifier
- Naming: [Marca] | [ASIN] | [MKT] | [Tipo]-[SubTipo] | [Match] | [Cluster]
- Start Date formato YYYYMMDD

### Inputs
- Plan de Acción bulk (.xlsx) — del Análisis Cruzado
- Datos producto: marca, ASIN, SKU, precio, CVR, target ACoS, budget

### Anti-patterns
- SIEMPRE verificar SKU (no ASIN) antes de subir
- SIEMPRE cruzar con campañas activas para evitar duplicados
- Hoy SOLO genera SP — SB/SBV/SD pendiente

---

## M11 — Atom11 Rules Builder
**Archivo:** modules/pages/atom11_rules_builder.py
**Sección sidebar:** PPC / Ejecución
**Session state prefix:** rules_

### Propósito
Generar rules de automatización para Atom11. Multi-marca configurable.

### Arquitectura
3 tabs: Configuración (prefijo, brand terms, ASINs, tiers) | Campaign Groups (clasificación automática) | Rules Generator (274 rules con thresholds dinámicos)

### Reglas de negocio
- Tiers: LOW (<$12) / MID ($12-22) / HIGH (>$22)
- Objetivos: DISCOVERY (120%) / RANKING (100%) / CONQUEST (~86%) / DEFENSIVE (~71%) / PROFIT (50%) / REMARKETING (~71%) / SCAVENGER (sin rules)
- 274 rules = Bid (126) + Placement (108) + Negate (18) + HardStop (18) + Harvest (4)
- Wait 3 days, lookback 14d (Bid) / 30d (Negate)

### Inputs
- Prefijo marca + Target ACoS + tabla ASINs con precio
- Campaign CSV — para clasificación de campañas

### Anti-patterns
- NUNCA hardcodear thresholds — siempre como % del target del objetivo
- SCAVENGER nunca tiene rules automáticas
