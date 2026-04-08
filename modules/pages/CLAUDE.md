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

---

## M12 — Reportes Atom 11
**Archivo:** modules/pages/atom11.py
**Sección sidebar:** Account
**Session state prefix:** atom_

### Propósito
Analizar performance con reportes de Atom 11 (WoW, MoM, DateRange). Comparación entre períodos.

### Arquitectura
Upload 1-2 archivos Atom11 → detección automática de tipo (ASIN/Portfolio/Keyword) → KPIs comparativos → Excel con branding

### Reglas de negocio
- _parse_atom11() detecta formato automáticamente
- _kpis(): Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC
- Delta% coloreado: verde si mejora, rojo si empeora
- Parent Evolution opcional si hay Parent-Child map cargado
- Toggle ES/EN → _I18N dict

### Inputs
- 1 o 2 archivos Atom11 (.xlsx)
- Parent-Child map (automático desde data/business_report/)

### Anti-patterns
- No confundir formato ASIN vs Portfolio vs Keyword — el parser los detecta automáticamente

---

## M13 — Reportes MerchanSpring
**Archivo:** modules/pages/merchanspring.py
**Sección sidebar:** Account
**Session state prefix:** ms_

### Propósito
Procesar reportes de MerchanSpring (.xlsx o .pdf) en Excel estructurado.

### Arquitectura
5 tabs: Summary | Advertising | Inventory & Health | WoW Comparison | Details

### Reglas de negocio
- Parser PDF defensivo (try/except en cada sección)
- Parser XLSX maneja estructura variable entre clientes
- Helpers de estilo: _s_acos, _s_margin, _s_delta, _s_eff, _s_stock

### Inputs
- MerchanSpring (.xlsx o .pdf)

### Anti-patterns
- IndexError con formatos distintos entre clientes — siempre manejar con try/except

---

## M14 — Weekly Client Report
**Archivo:** modules/pages/weekly_client_report.py
**Sección sidebar:** Account
**Session state prefix:** wcr_

### Propósito
Generar reporte semanal para el cliente con comparación WoW automática.

### Arquitectura
Upload BR (PW+TW) + BR by Child + Atom11 + Campaign CSV → Excel 3 hojas (WoW + Advertising + Ejecutivo) + changelog

### Reglas de negocio
- Split automático PW/TW de BR daily
- BuyBox_TW = None si BR no tiene columna (ej: M&B)
- Detecta Unit Session Percentage o Order Item Session Percentage
- Toggle ES/EN para reporte ejecutivo
- Changelog: st.text_area → hoja adicional en Excel

### Inputs
- BR Daily (.csv/.xlsx) — PW y TW
- BR by Child (.csv/.xlsx)
- Atom11 ASIN (.xlsx) — PW y TW
- Campaign CSV (.csv)

### Anti-patterns
- BuyBox con 0 sesiones → ignorar (evita falsos positivos)

---

## M15 — DataDive Analyzer
**Archivo:** modules/pages/datadive_analyzer.py
**Sección sidebar:** Research
**Session state prefix:** dd_

### Propósito
Procesar reportes DataDive: MKL keywords, competitors matrix, rank radar tracking y ranking volatility.

### Arquitectura
4 tabs: MKL Keywords (SV, Organic Rank, IQ Score, flags oportunidad) | Competitors (comparación vs Niche Median) | Rank Radar (ranking orgánico diario, tendencia) | Ranking Volatility (std dev + PPC IS cruzado con SQP)

### Reglas de negocio
- Flags: Oportunidad PPC (organic sin ads) / Depende de Ads (ads sin organic)
- Volatilidad: ESTABLE (std < 3) / VOLÁTIL (3-8) / MUY VOLÁTIL (> 8)
- Tab 4 cruza con SQP para PPC Impression Share
- Volátil sin PPC = RIESGO | Estable top 10 con PPC = oportunidad reducir spend

### Inputs
- DataDive MKL (.xlsx) — Tab 1
- DataDive Competitors (.xlsx) — Tab 2
- DataDive Rank Radar (.xlsx) — Tab 3
- SQP (.xlsx) — opcional para Tab 4

### Anti-patterns
- Parsers son específicos por tipo de export DataDive — no intercambiar

---

## M16 — Helium 10 Analyzer
**Archivo:** modules/pages/helium10_analyzer.py
**Sección sidebar:** Research
**Session state prefix:** h10_

### Propósito
Procesar Cerebro (reverse ASIN) para KW research, competitor gap y oportunidades PPC.

### Arquitectura
3 tabs: Cerebro Reverse ASIN (filtros + flags) | KW Research Launch Pack (multi-competidor, Launch Priority Score) | Competitor Gap (tu ASIN vs competidores)

### Reglas de negocio
- _parse_cerebro(): maneja "-" como NaN, detecta ASIN del filename
- Launch Priority Score = SV × (comps ranking / total) × (1 / avg rank)
- Clustering automático por root word
- Competitor Gap acciones: ATACAR (SV≥500, rank≤15) / MONITOREAR / IGNORAR

### Inputs
- Helium 10 Cerebro (.xlsx) — 1 archivo para Tab 1, 1-3 para Tab 2, 2-3 para Tab 3

### Anti-patterns
- No confundir Cerebro con Magnet — son exports distintos

---

## M17 — SBH Target Recommendation
**Archivo:** modules/pages/sbh_recommendation.py
**Sección sidebar:** Research
**Session state prefix:** sbh_

### Propósito
Recomendar keywords target para Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV.

### Arquitectura
Upload MKL + SQP + Campaign CSV → priorización → clustering → headlines sugeridos

### Reglas de negocio
- Prioridad ALTA: SV ≥1000, IS <10%, mercado comprando, no en SP
- Prioridad MEDIA: SV ≥500, IS <20%
- Prioridad BAJA: SV ≥300
- Clustering por root words + headline sugerido por cluster

### Inputs
- DataDive MKL (.xlsx) — requerido
- SQP (.xlsx/.csv) — requerido
- Campaign CSV (.csv) — opcional

### Anti-patterns
- No incluir brand keywords en SBH targets — son para Defensive SP

---

## M18 — PPC Insights Engine
**Archivo:** modules/pages/ppc_insights.py (~530 líneas)
**Sección sidebar:** Research
**Session state prefix:** insights_

### Propósito
Health score 0-100 por ASIN cruzando todos los reportes. Identifica ASINs problemáticos y wasted spend.

### Arquitectura
Cards por ASIN con expanders (STR, SQP, BR, Campañas) + botón IA opcional + Excel multi-sheet (hasta 10 hojas por ASIN)

### Reglas de negocio
- Health Score = CVR (25 pts) + BuyBox (20 pts) + ACoS vs target (25 pts) + Funnel completo (15 pts) + Impression Share (15 pts)
- Top keywords por ventas + bleeders (gasto sin conversión)
- Score emoji: ≥80 🟢 | 60-79 🟡 | <60 🔴

### Inputs
- STR (.xlsx/.csv) — requerido
- SQP (.xlsx/.csv) — opcional
- BR by ASIN (.csv/.xlsx) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- No calcular health score con solo STR — mínimo 2 fuentes para score confiable

---

## M19 — PPC Forecast
**Archivo:** modules/pages/ppc_forecast.py (~450 líneas)
**Sección sidebar:** Research
**Session state prefix:** forecast_

### Propósito
Proyección de ventas con tendencia lineal + estacionalidad. Budget recommendation.

### Arquitectura
Upload BR diario → tendencia (numpy polyfit) → ajuste estacionalidad finde/laboral → proyección 7/14/30d → gráfico + Excel

### Reglas de negocio
- Mínimo 14 días de data, ideal 30+
- Tendencia: numpy polyfit grado 1
- Estacionalidad: ratio finde vs laboral
- 3 escenarios: conservador / base / optimista

### Inputs
- Business Report diario (.xlsx/.csv) — mínimo 14 días

### Anti-patterns
- No proyectar con menos de 14 días — resultados no confiables
- No usar para predicción > 30 días — pierde precisión

---

## M20 — PPC Audit Pro
**Archivo:** modules/pages/ppc_audit.py (~1,077 líneas)
**Sección sidebar:** Research
**Session state prefix:** audit_

### Propósito
Auditoría profunda desde Bulk File multi-hoja. Breakdown real SP/SB/SD, 10 segmentos, 5 deep checks.

### Arquitectura
5 tabs: KPIs Overview (breakdown SP/SB/SD) | Auditoría Estructura (3 cards badges) | Performance por Segmento (10 SP + SB + SD) | Deep Checks (5 análisis) | Export Excel (6 hojas)

### Reglas de negocio
- Parser _parse_bulk(): 5 hojas (SP Campaigns, SB Campaigns, SD Campaigns, SP STR, SB STR)
- Tab 2: Match Types Mixtos (>1 match por campaign) / Target WAS (Spend>0, Sales=0) / Search Term WAS
- Tab 3: 10 segmentos SP (KW Exact/Phrase/Broad + PT ASIN/Category + AUTO Close/Loose/Substitutes/Complements)
- Tab 4: Top 5 campañas / Clasificación targets (own_brand/own_asin/competitor/generic) / Duplicación targets / Bid Adjustments / SKAG vs Bolsa
- ACoS semáforo: verde ≤30%, amarillo 31-55%, rojo >55%
- Headers coloreados: SP azul #1d4b8f, SB violeta #6b2d8f, SD verde #2a6e4e

### Inputs
- Bulk File (.xlsx) — requerido (Campaign Manager → Bulk Operations)
- Business Report (.xlsx/.csv) — opcional (para TACoS y Revenue)
- Brand terms — input texto (para clasificación de targets)

### Anti-patterns
- NO confundir Bulk File con Campaign CSV — son formatos distintos
- _build_audit_excel() DEBE estar fuera de render()

---

## M21 — Account Pulse
**Archivo:** modules/pages/account_pulse.py (~430 líneas)
**Sección sidebar:** Research
**Session state prefix:** pulse_

### Propósito
Monitor de salud diaria: ventas, units, sessions, CVR, ACoS con deltas WoW. Festivos MX.

### Arquitectura
Upload BR diario + BR by Child + Campaign CSV → split PW/TW automático → Excel 4 hojas

### Reglas de negocio
- Festivos MX: Año Nuevo, Constitución, Juárez, Trabajo, Independencia, Muertos, Revolución, Navidad
- Anomalía: caída >30% del promedio
- BuyBox ordenado por impacto económico (ventas perdidas estimadas)
- Campañas: NUEVA (verde) vs HEREDADA (azul)
- Portada naranja con KPIs + diagnóstico + mensaje Slack

### Inputs
- BR Daily (.csv/.xlsx) — mínimo 14 días
- BR by Child (.csv/.xlsx) — opcional
- Campaign CSV (.csv) — opcional

### Anti-patterns
- BuyBox con 0 sesiones → ignorar

---

## M22 — Knowledge Base
**Archivo:** modules/pages/knowledge_base.py (~180 líneas)
**Sección sidebar:** Knowledge
**Session state prefix:** kb_

### Propósito
Repositorio de notas y documentación del equipo. Buscar, filtrar y crear notas .md.

### Arquitectura
2 tabs: Explorar notas (upload + búsqueda texto + filtro tags/categorías) | Agregar nota (formulario + preview + descarga .md)

### Reglas de negocio
- Categorías: ppc, amazon, ai, strategy, client
- Parsea headers/tags/categorías/fecha del filename
- Búsqueda full-text case-insensitive
- Badges de categoría estilo naranja

### Inputs
- Archivos .md o .txt

### Anti-patterns
- No procesar archivos que no sean texto plano (.md, .txt)
