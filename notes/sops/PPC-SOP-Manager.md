# 🦫 SOP — Capybaras PPC Manager
## Guía de uso completa por módulo
**Versión:** v3.2 — Abril 2026 | **Dev:** Lenin Acosta
**Módulos activos:** 25 | **Secciones:** PPC · Inteligencia · Research · Account Manager · Knowledge

---

## 0. Antes de arrancar

```bash
cd C:\proyectos\ppc-manager
python -m streamlit run app.py
```

La app abre en `http://localhost:8501`. Sidebar izquierdo oscuro = navegación principal.

**Secciones del sidebar:**

| Sección | Módulos | Descripción |
|---|---|---|
| 📊 PPC | 10 | Análisis, optimización y ejecución de campañas |
| 🧠 Inteligencia | 3 | Insights por ASIN, forecast y auditoría de cuenta |
| 🔬 Research | 3 | DataDive, Helium 10 y SBH targeting |
| 👥 Account | 6 | Reportes, rules, monitoreo y generación de dashboards |
| 📚 Knowledge | 1 | Repositorio de notas y aprendizajes |

**Archivos que vas a necesitar según la tarea:**

| Archivo | Dónde bajarlo en Amazon | Formato |
|---|---|---|
| STR (Search Term Report) | Reports → Advertising Reports → SP Search Term | .xlsx |
| SQP (Search Query Performance) | Brand Analytics → Search Query Performance | .xlsx |
| Campaign CSV | Campaign Manager → Columns: todas las métricas → Export | .csv |
| Bulk File | Campaign Manager → Bulk Operations → Download | .xlsx |
| Business Report | Seller Central → Reports → Business Reports → By Date o By ASIN | .csv |
| Inventory Report | Manage Inventory → Export | .txt/.csv |
| Atom 11 | Atom 11 → Reports → Export | .xlsx |
| MerchanSpring | MerchanSpring → Reports → Export | .xlsx o .pdf |
| DataDive MKL | DataDive → Niche → Keywords | .xlsx |
| DataDive Competitors | DataDive → Niche → Competitors | .xlsx |
| DataDive Rank Radar | DataDive → Rank Radar → Export | .xlsx |
| Helium 10 Cerebro | Helium 10 → Cerebro → Reverse ASIN | .xlsx |

---

## SECCIÓN: 📊 PPC (10 módulos)

---

## 1. 🏠 Inicio

**Para qué sirve:** Dashboard de estado del Agency OS. No requiere uploads.

**Qué muestra:**
- 22 módulos activos agrupados por sección
- Estado del Parent-Child map (verde si cargado, naranja si no)
- Flujo de trabajo visual por área (Workflow Wizard piramidal)
- Versión y changelog reciente
- 5 niveles: Subí datos → Analizá → Inteligencia → Ejecutá → Reportá

**Parent-Child map:** Subí un Business Report en `data/business_report/` — se carga automáticamente al iniciar.

---

## 2. 📊 Search Term Report (STR)

**Para qué sirve:** Analizar qué términos de búsqueda están generando spend, ventas y órdenes en tus campañas SP. Es el punto de partida para negativizar y harvestear.

**Input:** STR exportado desde Amazon Ads (.xlsx o .csv) — período recomendado: 30 días.

**Las 5 tabs:**

### Tab 1 — Vista General
- Muestra el STR completo con métricas totales (spend, sales, ACoS)
- 12 KPIs con kpi_card: Spend, Sales, ACoS con delta, ROAS, Impressions, Clicks, CTR, CVR, CPC, Orders, % Waste, % Con Ventas
- Filtros interactivos: campaña, match type, ACoS max, spend min
- Vistas rápidas: Todos / Winners (2+ orders) / Sin ventas / Top Sales / Top Spend
- Scatter chart Spend vs Sales con colores por term type
- Funnel de conversión horizontal: Impressions → Clicks → Orders
- Descarga el STR limpio en Excel

### Tab 2 — 🔴 Negatives Mining
- **Input adicional:** Precio promedio del producto (número) + Target ACoS (slider)
- **Lógica automática:**
  - R2: clicks ≥ threshold dinámico (basado en CVR) AND 0 órdenes → Negative Exact
  - R3: spend ≥ 50% del precio AND 0 órdenes → Negative Exact
  - R4: ACoS > 70% con < 5 órdenes → evaluar
  - R5: impresiones ≥ 2500 AND CTR < 0.18% → Negative Phrase
- **Output:** Lista de candidatos a negativizar con botón de descarga en formato bulk Amazon

### Tab 3 — 🟢 Harvest Candidates + Anti-canibalización
- **Lógica automática:**
  - Principal: orders ≥ 3 AND ACoS ≤ 25%
  - Por CVR: CVR ≥ 10% AND clicks ≥ 15
  - Por volumen: orders ≥ 5 (independiente del ACoS)
- Calcula bid sugerido: `CVR × precio × target_ACoS`
- **NUEVO — Anti-canibalización:** Sube opcionalmente un Campaign CSV para cruzar automáticamente con campañas Exact activas. Las keywords que ya están en Exact se marcan como "⚠️ Ya existe en Exact activo" y se excluyen del bulk por defecto.
- **Output:** Bulk Amazon listo con keywords en Exact Match + bid calculado

### Tab 4 — 🤖 Análisis IA
- Genera análisis ejecutivo con Claude basado en los candidatos detectados

### Tab 5 — 📊 Por Campaña
- Groupby por campaign: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC
- Clasificación Brand/No Brand automática por nombre de campaña
- 4 KPIs + tabla con color coding + download Excel

---

## 3. 🔍 Search Query Performance (SQP)

**Para qué sirve:** Ver qué busca el mercado total (no solo tus campañas) y cuánto share of voice tenés en cada query.

**Input:** SQP descargado desde Brand Analytics (.xlsx) — período recomendado: 30 días o trimestral.

**Las 4 tabs:**

### Tab 1 — Vista General
- SQP completo con métricas de mercado. Detecta marca automáticamente.

### Tab 2 — Market Share
- Impression share, click share y purchase share por query
- Clasifica: Dominando (IS >30%) / Competitivo (10-30%) / Oportunidad (<10%)

### Tab 3 — Gap Analysis
- Queries con alto volumen donde tu brand impressions = 0
- Queries donde el purchase rate del mercado supera el tuyo

### Tab 4 — 🤖 Análisis IA
- Análisis ejecutivo de market share con Claude

---

## 4. 🔗 Análisis Cruzado STR vs SQP

**Para qué sirve:** Cruzar STR contra SQP para detectar gaps y oportunidades.

**Inputs:** STR + SQP simultáneamente.

**Las 3 tabs:**

### Tab 1 — Cruce
- En ambos / Solo STR / Solo SQP
- Filtros: impresiones, SQS, purchases, tipo Marca/Genérica

### Tab 2 — Plan de Acción
- 🚀 AGREGAR — alta compra en mercado, no aparecés
- ✅ HARVEST — está en STR con buen ACoS
- ⬇️ BAJAR BID — ACoS > target × 2
- ⚡ ESCALAR — impression share bajo + mercado comprando
- 👁️ MONITOREAR
- **El bulk del Plan de Acción es el INPUT del Campaign Builder**

### Tab 3 — PPC Insights por ASIN (NUEVO 2026-03-26)
- **Input adicional:** BR by ASIN (opcional)
- Resumen por ASIN: spend, sales, top 5 keywords, gap detection
- Export Excel con insights por ASIN

---

## 5. 📈 Tendencia Multi-Semana

**Para qué sirve:** Ver evolución de queries a lo largo de varias semanas.

**Input:** Hasta 4 archivos SQP de distintas semanas.

Clasifica: ↑ creciendo (>10%), → estable, ↓ cayendo (>10%).

---

## 6. 📁 Bulk Campañas

**Para qué sirve:** Ver y diagnosticar el estado de todas las campañas activas.

**Input:** Campaign CSV exportado desde Campaign Manager con métricas (.csv).

**Las 3 tabs:**

### Tab 1 — Vista General
- Archivo raw completo

### Tab 2 — 🚦 Campaign Analyzer
- 🔴 PAUSAR — spend > threshold AND 0 órdenes
- 🟡 REVISAR — ACoS > target × 2
- ✅ ESCALAR — ACoS < target × 0.5 con órdenes
- ⚫ FANTASMAS — campañas con 0 impresiones

### Tab 3 — 📋 Auditoría PPC (NUEVO 2026-03-26)
- **Naming convention check:** verifica % de campañas que siguen el patrón Capybaras
- **Target graduation:** campañas con 0 impresiones que podrían necesitar revisión
- **Export multi-sheet** con diagnóstico completo

---

## 7. 💰 Business Report

**Para qué sirve:** Analizar ventas, sesiones, CVR y BuyBox por ASIN.

**Input:** Business Report de Seller Central (.csv).

---

## 8. 🔻 Análisis de Funnel

**Para qué sirve:** Ver si tenés el funnel completo (Auto → Broad → Phrase → Exact) por producto.

**Inputs:** STR + Bulk file de campañas.

---

## 9. 🧠 Bid Optimizer

**Para qué sirve:** Calcular el bid óptimo para cada keyword basado en CVR real, precio y target ACoS.

**Input:** STR + Target ACoS (slider) + precio promedio. Opcionalmente: Inventory Report para precio de lista exacto.

**Fórmula:** `bid_sugerido = (CVR / 100) × precio × (target_ACoS / 100)`

**Las 2 tabs:**

### Tab 1 — Bids
- 🟢 SUBIR — bid actual < bid sugerido × 0.7
- ⚫ OK — bid entre 0.7x y 1.3x del sugerido
- 🔴 BAJAR — bid actual > bid sugerido × 1.3
- ⛔ PAUSAR — clicks > 10 AND órdenes = 0
- Export bulk con Max Bid modificadas

### Tab 2 — Placements & Budget (NUEVO 2026-03-26)
- **Tabla de referencia placements** por tipo de campaña (SOP Capybaras):
  - Exact Ranking: ToS +50%, PDP 0%
  - Exact Harvest: ToS +25%, PDP 0%
  - PAT Competitor: ToS 0%, PDP +50%
  - etc.
- **Budget estimado** por campaña basado en tipo
- **Detección automática** del tipo de campaña por naming convention

---

## 10. 🚀 Campaign Builder

**Para qué sirve:** Generar bulk listo para subir a Amazon con nuevas campañas.

**Input:** Plan de Acción bulk (del Análisis Cruzado) + datos del producto.

**Clustering automático:** PAT / Spanish / Brand / Discovery
**Bidding Strategy por tipo:** Fixed Bid o Dynamic Down-Only + placement modifiers
**Max 5 KWs por campaña** (regla Capybaras 2026)

**Soporte para 3 tipos de campaña (NUEVO 2026-04-08):**
- **SP (Sponsored Products)** — lógica existente
- **SB (Sponsored Brands)** — headline, 3 ASINs creativos, landing page
- **SD (Sponsored Display)** — Product Targeting o Audience Targeting

---

## 11. ⚙️ Atom11 Rules Builder

**Para qué sirve:** Generar rules de automatización para Atom11.

**Inputs:** Prefijo de marca + Target ACoS + tabla de ASINs con precio.

**274 rules por cuenta** con thresholds dinámicos por objetivo y tier.

---

## SECCIÓN: 👥 ACCOUNT MANAGER (6 módulos)

> PPC Insights, PPC Forecast, PPC Audit y Account Pulse se documentan en la sección RESEARCH & INTELLIGENCE (#18-#21).

---

## 12. 🔬 Reportes Atom 11

**Para qué sirve:** Analizar performance con el formato de reporte de Atom 11 (WoW, MoM, DateRange).

**Input:** 1 o 2 archivos .xlsx de Atom 11.

**Output Excel (3-4 hojas):** Informe Cliente + KPIs + Datos + Parent Evolution (opcional).

---

## 13. 🛡️ Reportes MerchanSpring

**Para qué sirve:** Procesar reportes de MerchanSpring en Excel estructurado.

**Input:** .xlsx o .pdf de MerchanSpring.

**Output Excel (4 hojas):** Summary + Advertising + Inventory & Health + WoW Comparison.

---

## 14. 📊 Weekly Client Report

**Para qué sirve:** Reporte semanal para el cliente con comparación WoW automática.

> **📋 Nota — BR tolerante a subset (2026-05-04):** El BR puede exportarse con cualquier subset de columnas que incluya las core mínimas (lista abajo). El parser tolera dashes unicode (`–` en-dash, `—` em-dash), doble espacio, falta de guión y splits Mobile App + Browser sin Total. Si falta una col core, muestra mensaje canónico orientando a re-exportar desde Seller Central.

**Inputs (4 archivos, date range 14 días):**

| Archivo | Bajarlo desde | Para qué |
|---|---|---|
| BR diario 14d | Business Reports → By Date | CUENTA TOTAL PW vs TW |
| BR by Child ASIN | Business Reports → By ASIN | Desglose por ASIN |
| Atom 11 ASIN | Atom 11 → ASIN → DateRange 14d | Ad Spend/Sales split 7+7 |
| Campaign CSV | Campaign Manager → mismo date range | Impressions/CTR/NTB |

### Columnas BR — core mínimas vs opcionales

**BR diario (By Date — Sales and Traffic) — core mínimo:**
- `Date`
- `Sessions - Total` (o `Sessions - Mobile App` + `Sessions - Browser` — el parser suma)
- `Units Ordered`
- `Ordered Product Sales`

**BR by Child (Detail Page Sales and Traffic By Child Item) — core mínimo:**
- `(Child) ASIN`
- `Sessions - Total` (o split Mobile App + Browser)
- `Units Ordered`
- `Ordered Product Sales`

**Opcionales (se incluyen si vienen, se omiten si no):**
- `Featured Offer (Buy Box) Percentage` — recomendado para WoW
- `Unit Session Percentage` o `Order Item Session Percentage` (CVR — fallback automático)
- `(Parent) ASIN`, `Title`
- `Page Views - Total` y splits Mobile/Browser
- `Total Order Items`, `Units Refunded`, `Refund Rate`
- `Shipped Product Sales`, `Units Shipped`, `Orders Shipped`
- Variantes B2B de cualquier columna (filtradas por defecto, info disponible vía flag)

**Output Excel (4 hojas):**
- 📈 WoW Comparison — fila azul CUENTA TOTAL + desglose por ASIN
- 📣 Advertising — PW vs TW + top 10 campañas + alarmas ACoS>60%
- 📋 Reporte Ejecutivo — análisis redactado con toggle ES/EN
- 📝 Changelog — notas del AM sobre cambios de la semana

---

## 15. 👁️ Listing Monitor

**Para qué sirve:** Monitorear ASINs de Amazon y alertar cuando algo cambia vs el snapshot anterior. Scrapea directamente desde Amazon (sin API key).

**Campos monitoreados:** precio, rating, reviews count, badges (Best Seller/Amazon's Choice), bullets, stock, título

**Arquitectura:**
- **Tab 1 — Escanear ASINs:** input ASINs, selector marketplace (MX/COM/ES/BR/CA), delay configurable, guardado automático de snapshot
- **Tab 2 — Ver Alertas:** comparación vs snapshot anterior, color coding (🔴 alerta / 🟡 info / 🟢 ok)
- **Tab 3 — Historial:** tabla de todos los snapshots con columna Producto

**Storage:** Snapshots en `data/listing_snapshots/snapshots.json` con clave `{ASIN}_{MARKETPLACE}`

---

## 16. 📊 Gamboa Generator

**Para qué sirve:** Generar reportes HTML integrales tipo dashboard interactivo con SQP mensual + BR semanal. Listo para publicar en Hostinger o enviar al cliente.

**Inputs:**
- **SQP multi-archivo** (Brand Analytics → Search Query Performance) — auto-detecta mes por filename o columna "Reporting Range"
- **BR semanal by ASIN** (Business Reports → By ASIN → Child Item) — un archivo por semana, auto-detecta ISO week
- **Inventory Report (opcional)** — mapeo SKU ↔ ASIN. Sin esto usa ASIN como identificador
- **CSV de categorías (auto-generado)** — plantilla descargable, persistente en `notes/brands/{cliente-slug}/gamboa_categories.csv`

**Output:** HTML standalone (~5-10 MB) con 2 paneles interactivos:
- **Panel SQP mensual:** 15 meses de queries, filtros, funnel conversión, cards por categoría, tabla filtrable, 7 charts de tendencia (SV, Impressions, Clicks, Cart Adds, Purchases, CTR, Conversion Rate)
- **Panel WoW Category (semanal):** 68 semanas de KPIs WoW/YoY, category cards, tabla con sparklines, modal de tendencia por SKU

**Decisiones técnicas:**
- SKU opcional con fallback a ASIN — robustez, funciona sin Inventory Report
- Score SQP lee columna "Search Query Score" con fallback 0 — defensivo ante cuentas sin Brand Analytics
- SQP multi-upload con auto-detección de mes — Amazon BA baja archivo por mes o por rango, ambos casos soportados
- Categorías persistentes en CSV — reutiliza arquitectura existente, evita re-trabajo entre sesiones

---

## SECCIÓN: 🔬 RESEARCH & INTELLIGENCE (7 módulos — 2026-03-27)

---

## 17. 🧲 DataDive Analyzer

**Para qué sirve:** Analizar exports de DataDive (nicho, competidores, rank radar) para entender el mercado y detectar oportunidades.

**Input:** Archivos exportados desde DataDive (.xlsx)

**4 tabs:**
- **Tab 1 — MKL (Master Keyword List):** Keywords del nicho con SV, Relevance, Launch Score y ranking por ASIN competidor. Color coding: verde (Relevance ≥3), amarillo (≥2), rojo (<2).
- **Tab 2 — Competitors:** Matriz de competidores con métricas: Brand, 30d Sales, Revenue, Price, Rating, Reviews. Color en Rating.
- **Tab 3 — Rank Radar:** Tracking de ranking orgánico diario por keyword. Detecta subidas/bajadas y cobertura PPC.
- **Tab 4 — Ranking Volatility + PPC IS:** Cruza Rank Radar con SQP. Clasifica keywords: ESTABLE / VOLÁTIL / MUY VOLÁTIL. Flags: "RIESGO — volátil sin PPC" y "OPORTUNIDAD — estable top 10 con PPC".
- **Tab 5 — Competitor Intel (NUEVO):** Sube tu MKL + MKL competidor → comparación directa. Clasifica cada keyword.

**Export:** Excel por tab.

---

## 18. 🧲 Helium 10 Analyzer

**Para qué sirve:** Analizar exports de Helium 10 Cerebro para reverse ASIN, research de keywords y competitor gap.

**Input:** Archivo Cerebro exportado desde Helium 10 (.xlsx): `US_AMAZON_cerebro_[ASIN]_[fecha].xlsx`

**3 tabs:**
- **Tab 1 — Cerebro Reverse ASIN:** Keywords con SV, Organic Rank, Sponsored Rank, Cerebro IQ. Clasifica: 🟢 Oportunidad PPC (organic sin sponsored), 🟡 Depende de Ads, ✅ Ambos.
- **Tab 2 — KW Research (Launch Pack):** Sube 1-3 Cerebros de competidores, cruza keywords por frecuencia. Las que aparecen en 3/3 = alta prioridad.
- **Tab 3 — Competitor Gap:** Tu Cerebro vs 1-2 competidores. Detecta keywords donde ellos rankean orgánico y vos no. Acción: 🚀 ATACAR / 👁️ MONITOREAR / ⏭️ IGNORAR. Botón "Exportar como Plan de Acción" para enviar a Campaign Builder.

**Export:** Excel por tab.

---

## 19. 📢 SBH Target Recommendation

**Para qué sirve:** Recomendar keywords target para campañas Sponsored Brand Headline (SBH) cruzando DataDive MKL + SQP + Campaign CSV.

**Input:**
- DataDive MKL (.xlsx) — requerido
- SQP (.xlsx o .csv) — requerido
- Campaign CSV (.xlsx o .csv) — opcional (para detectar keywords ya en SP)

**Lógica:** Prioriza keywords con alto SV, bajo Impression Share, mercado comprando y sin cobertura SP actual.
- 🔴 ALTA: SV ≥1000, IS <10%, mercado comprando, no en SP
- 🟡 MEDIA: SV ≥500, IS <20%
- 🟢 BAJA: SV ≥300

**Clustering automático:** Agrupa keywords por root words comunes y sugiere headlines por cluster.

**Export:** Excel 2 hojas (SBH Targets + Clusters).

---

## 20. 🔎 PPC Insights Engine

**Para qué sirve:** Health score 0-100 por ASIN cruzando todos los reportes disponibles. Identifica ASINs problemáticos y wasted spend.

**Input:**
- STR (.xlsx o .csv) — requerido
- SQP (.xlsx o .csv) — opcional
- Business Report by ASIN (.csv o .xlsx) — opcional
- Campaign CSV (.csv) — opcional

**Health Score (0-100):** CVR (25 pts) + BuyBox (20 pts) + ACoS vs target (25 pts) + Funnel completo (15 pts) + Impression Share (15 pts).

**Por ASIN:** Top keywords, bleeders (gasto sin conversión), métricas SQP, BuyBox, campañas activas.

**Export:** Excel con branding Capybaras.

---

## 21. 📈 PPC Forecast

**Para qué sirve:** Proyección de ventas con tendencia lineal y estacionalidad. Estima ventas futuras basado en histórico.

**Input:** Business Report diario (.xlsx o .csv) — mínimo 14 días, ideal 30+.

**Output:** Proyección con escenarios (conservador / base / optimista), tendencia diaria, ratio de crecimiento.

**Export:** Excel con proyecciones.

---

## 22. 🛡️ PPC Audit

**Para qué sirve:** Auditoría integral de la cuenta desde Bulk File multi-hoja. Breakdown real SP/SB/SD, 10 segmentos, 5 deep checks.

**Input:**
- Bulk File (.xlsx) — requerido (Campaign Manager → Bulk Operations)
- Business Report (.csv o .xlsx) — opcional (para TACoS y Revenue)
- Brand terms — input texto (para clasificación de targets)

**5 tabs:**
1. KPIs Overview — breakdown real SP/SB/SD
2. Auditoría Estructura — Match Types Mixtos, Target WAS, Search Term WAS
3. Performance por Segmento — 10 segmentos SP + SB + SD con ACoS semáforo
4. Deep Checks — Top campañas, clasificación targets, duplicación, bid adjustments, SKAG vs Bolsa
5. Target Graduation — targets con 0 impresiones en campañas con tráfico. Acciones: SUBIR BID / PAUSAR / GRADUAR SKAG / MANTENER
6. Export Excel — 6 hojas

**Score 0-100** desglosado. Headers coloreados: SP azul, SB violeta, SD verde.

---

## 23. 📊 Account Pulse

**Para qué sirve:** Monitor de salud diaria: ventas, units, sessions, CVR, ACoS con deltas WoW. Incluye detección de festivos MX.

**Input:** Business Report diario (.xlsx o .csv) — mínimo 14 días.

**Paleta:** E84000 (naranja) | 1F1F1F (negro) | FAFAFA (blanco roto)

**Festivos MX detectados automáticamente:** Año Nuevo, Constitución, Juárez, Día del Trabajo, Independencia, Día de Muertos, Revolución, Navidad.

**Export:** Excel 4 hojas (Resumen Ejecutivo, Ventas Diarias, BuyBox & ASINs, Campañas).

---

## SECCIÓN: 📚 KNOWLEDGE (1 módulo — 2026-03-27)

---

## 24. 📚 Knowledge Base

**Para qué sirve:** Repositorio de notas y documentación del equipo. Buscar por texto, tags y categorías.

**Input:** Archivos .md o .txt

**2 tabs:**
- **Tab 1 — Explorar notas:** Sube archivos .md, busca por texto libre, filtra por tags y categorías (ppc, amazon, ai, strategy, client). Badges de categoría con estilo naranja.
- **Tab 2 — Agregar nota:** Formulario con título, tags, categoría, contenido Markdown. Preview en vivo + descarga como .md.

**Export:** Archivo .md descargable.

---

## 25. Flujo de trabajo semanal recomendado

```
LUNES (análisis + diagnóstico)
  1. PPC Audit → correr auditoría → ver score y prioridades
  2. STR → Tab 2 Negatives Mining → negativizar lo urgente
  3. STR → Tab 3 Harvest Candidates → identificar nuevos términos
  4. Bulk Campañas → Campaign Analyzer → detectar campañas a pausar/escalar

MARTES (reportes + forecast)
  5. Weekly Client Report → generar y enviar al cliente
  6. PPC Forecast → proyectar ventas y budget próxima semana
  7. Account Pulse → check de salud diaria

MIÉRCOLES (inteligencia + acción)
  8. PPC Insights Engine → health score por ASIN → priorizar ASINs
  9. Bid Optimizer → ajustar bids con Tab Placements
  10. DataDive Ranking Volatility → detectar riesgos orgánicos

QUINCENAL
  11. SQP → Market Share + Gap Analysis → detectar oportunidades
  12. Análisis Cruzado STR vs SQP → Plan de Acción + Insights por ASIN
  13. Campaign Builder → generar bulk de nuevas campañas → subir a Amazon
  14. Helium 10 Cerebro → reverse ASIN → KW Research + Competitor Gap
  15. DataDive MKL + Competitors → keyword gaps + nicho
  16. SBH Recommendation → targets para Sponsored Brand Headline

MENSUAL
  17. Atom 11 Reports → análisis MoM
  18. Atom11 Rules Builder → revisar rules si cambiaron precios/objetivos
  19. PPC Audit → comparar score vs mes anterior
  20. Knowledge Base → documentar aprendizajes del mes

OCASIONAL (cada 2-4 semanas)
  21. Listing Monitor → revisar snapshots de ASINs clave
  22. Gamboa Generator → generar HTML integral para cliente (SQP + BR mensual)
```

---

## 26. Reglas críticas de operación

| Regla | Detalle |
|---|---|
| Cruzar STR con campañas activas antes de subir bulk | Si la keyword ya está en Exact activo con ACoS < target → no crear campaña nueva |
| Nunca negativizar dentro de una Exact Match propia | Los negativos van en Auto/Broad/Phrase de origen |
| Fixed Bid primeras 2 semanas | Toda campaña nueva arranca con Fixed Bid — no Dynamic |
| No optimizar bids antes de 14 días | Esperar el learning period antes de tocar bids |
| SKU ≠ ASIN | El bulk de Amazon requiere SKU, no ASIN. Buscar en Seller Central → Manage Inventory |
| Naming convention Capybaras | `[Marca] \| [ASIN] \| [MKT] \| [Tipo]-[SubTipo] \| [Match] \| [Cluster]` |
| Pausas requieren Campaign ID numérico | No se pueden pausar campañas desde el bulk generado |

---

## 27. Actualizaciones 2026-04-08

### Campaign Builder — Soporte SB y SD
El Campaign Builder ahora soporta 3 tipos de campaña:
- **SP (Sponsored Products)** — lógica existente sin cambios
- **SB (Sponsored Brands)** — requiere headline (50 chars), brand name, 3 ASINs creativos, landing page. Genera bulk formato SB de Amazon.
- **SD (Sponsored Display)** — soporta Product Targeting (ASINs competidores) y Audience Targeting (remarketing). Genera bulk formato SD de Amazon.

Selector tipo radio button al inicio del módulo. Cada tipo tiene su naming convention:
- SP: `[Marca] - [ASIN] - SP - KW - [MATCH] - [Cluster] [N]`
- SB: `[Marca] - [ASIN] - SB - KW - [MATCH] - [Cluster] [N]`
- SD: `[Marca] - [ASIN] - SD - [PT/AUD] - [SubTipo] [N]`

### PPC Audit Pro — Tab 6 Target Graduation
Nueva tab en PPC Audit que analiza targets con 0 impresiones en campañas que SÍ tienen tráfico:
- 🔼 SUBIR BID — tuvo ventas históricas, bid probablemente bajo
- 🔴 PAUSAR — gastó sin convertir nunca
- 🟡 GRADUAR A SKAG — mover a campaña propia con bid más alto
- 🛡️ MANTENER — keyword de marca (si se ingresaron brand terms)

### Helium 10 — Pipeline a Campaign Builder
Tab 3 Competitor Gap ahora tiene botón "Exportar como Plan de Acción" que genera un archivo compatible con Campaign Builder. Pipeline completo: H10 Cerebro → Competitor Gap → Plan de Acción → Campaign Builder → bulk Amazon.

### DataDive — Competitor Intelligence
Nueva Tab 5 en DataDive Analyzer: sube tu MKL + MKL de un competidor → comparación directa. Clasifica cada keyword en: Ambos rankean / Solo yo / Solo competidor / Ninguno.

### DataDive — Ranking Tracking
Tab 3 Rank Radar ahora guarda historial de rankings en session_state (hasta 5 snapshots). Cuando hay 2+ cargas, muestra delta de posiciones con tendencia por keyword.

### Weekly Client Report — Slack Changelog
Botón "Copiar Changelog para Slack" que genera formato listo para pegar: emoji + marca + fecha + cambios realizados + nota de adjunto.

### Metodología Claude Code implementada
- 3 Skills en `.claude/skills/`: ppc-reporting-standard, module-architecture-standard, client-communication-tone
- 9 agentes en `.claude/agents/` upgradeados con frontmatter, skills asignados y principio de mínimo privilegio
- `modules/pages/CLAUDE.md` con 22 secciones — contexto enfocado por módulo para agentes

---

Capybaras Agency — v3.2 — Abril 2026
