# 🦫 SOP DEFINITIVO — Capybaras Agency OS — PPC Manager
## Manual de uso completo · Módulo por módulo

**Versión:** Abril 2026 — v3.2
**Dev:** Lenin Acosta
**Stack:** Python + Streamlit + Pandas + OpenPyXL
**Módulos activos:** 25 módulos en 5 secciones
**Ruta local:** `C:\proyectos\ppc-manager`
**Comando:** `python -m streamlit run app.py`

---

## ÍNDICE

| # | Módulo | Sección |
|---|--------|---------|
| 0 | Antes de arrancar — Setup y archivos necesarios | Setup |
| 1 | Inicio — Dashboard de estado | — |
| 2 | Search Term Report (STR) — 5 tabs | PPC |
| 3 | Search Query Performance (SQP) — 4 tabs | PPC |
| 4 | Análisis Cruzado STR vs SQP — Plan de Acción | PPC |
| 5 | Tendencia Multi-Semana | PPC |
| 6 | Bulk Campañas + Campaign Analyzer | PPC |
| 7 | Business Report | PPC |
| 8 | Análisis de Funnel | PPC |
| 9 | Bid Optimizer | PPC |
| 10 | Campaign Builder | Ejecución |
| 11 | Atom11 Rules Builder | Ejecución |
| 12 | Reportes Atom 11 | Account |
| 13 | Reportes MerchanSpring | Account |
| 14 | Weekly Client Report | Account |
| 15 | Listing Monitor | Account |
| 16 | Gamboa Generator | Account |
| 17 | Account Pulse | Intelligence |
| 18 | PPC Insights | Intelligence |
| 19 | PPC Audit | Intelligence |
| 20 | PPC Forecast | Intelligence |
| 21 | DataDive Analyzer | Research |
| 22 | Helium 10 Analyzer | Research |
| 23 | SBH Recommendation | Research |
| 24 | Knowledge Base | Knowledge |
| A | Flujo de trabajo semanal recomendado | Apéndice |
| B | Reglas críticas de operación | Apéndice |
| C | Thresholds SOP Capybaras 2026 | Apéndice |
| D | Naming Convention | Apéndice |

---

---

## 0. Antes de arrancar

### Iniciar la aplicación

```bash
cd C:\proyectos\ppc-manager
python -m streamlit run app.py
```

La app abre en `http://localhost:8501`. Sidebar izquierdo oscuro con 5 secciones: PPC, Intelligence, Research, Account y Knowledge.

### Archivos que necesitás según la tarea

| Archivo | Dónde bajarlo en Amazon | Formato |
|---------|------------------------|---------|
| STR (Search Term Report) | Reports → Advertising Reports → SP Search Term | .xlsx |
| SQP (Search Query Performance) | Brand Analytics → Search Query Performance | .xlsx |
| Campaign CSV | Campaign Manager → Columns: todas las métricas → Export | .csv |
| Bulk File | Campaign Manager → Bulk Operations → Download | .xlsx |
| Business Report | Seller Central → Reports → Business Reports (By Date o By ASIN) | .csv |
| Atom 11 | Atom 11 → Reports → Export | .xlsx |
| MerchanSpring | MerchanSpring → Reports → Export | .xlsx / .pdf |
| Inventory Report | Reports → Fulfillment → Manage FBA Inventory | .txt / .csv |

> 💡 **Parent-Child Map:** Si querés agrupar ASINs por producto padre, colocá un Business Report en la carpeta `data/business_report/` — se carga automáticamente al iniciar la app.

---

---

## 1. 🏠 Inicio — Dashboard de estado

**Para qué sirve:** Dashboard principal del Agency OS.

**Input:** No requiere uploads.

**Qué muestra:**
- Estado del Parent-Child map (verde si cargado, naranja si no)
- Links rápidos a cada módulo
- Versión de la app

**Cuándo usarlo:** Al abrir la app para verificar que el mapa de ASINs está cargado correctamente antes de correr reportes.

---

---

## 2. 📊 Search Term Report (STR)

**Para qué sirve:** Analizar qué términos de búsqueda están generando spend, ventas y órdenes en tus campañas SP. Es el punto de partida para negativizar y harvestear.

**Input:** STR exportado desde Amazon Ads (.xlsx o .csv) — período recomendado: 30 días.

### Tab 1 — Vista General

Muestra el STR completo con métricas totales (spend, sales, ACoS). Descarga el STR limpio en Excel. Usalo para tener una visión rápida del estado general antes de analizar.

### Tab 2 — 🔴 Negatives Mining

**Input adicional:** Precio promedio del producto (número) + Target ACoS (slider).

**Lógica automática de detección:**

| Regla | Condición | Acción |
|-------|-----------|--------|
| R2 — Por CVR | clicks >= threshold dinámico (basado en CVR) AND 0 órdenes | Negative Exact |
| R3 — Por gasto | spend >= 50% del precio AND 0 órdenes | Negative Exact |
| R4 — ACoS extremo | ACoS > 70% con < 5 órdenes | Evaluar |
| R5 — CTR bajo | impresiones >= 2500 AND CTR < 0.18% | Negative Phrase |

**Fórmula threshold clicks:** `max(10, round((1 / CVR_producto) × 2))`
- CVR 10% → 20 clicks
- CVR 5% → 40 clicks
- CVR 3% → 60 clicks

**Output:** Lista de candidatos a negativizar con botón de descarga en formato bulk Amazon.

> ⚠️ **REGLA CRÍTICA:** Nunca negativizar dentro de una campaña Exact Match propia. Los negativos van en las campañas Auto/Broad/Phrase de origen.

### Tab 3 — 🟢 Harvest Candidates

**Lógica automática de harvest:**

| Regla | Condición | Match destino |
|-------|-----------|---------------|
| Principal (SOP Capybaras) | orders >= 3 AND ACoS <= 25% | Exact Match |
| Por CVR alto | CVR >= 10% AND clicks >= 15 | Exact Match |
| Por volumen | orders >= 5 (independiente del ACoS) | Exact Match |

**Bid sugerido:** `CVR × precio × target_ACoS`

**Output:** Bulk Amazon listo con keywords en Exact Match + bid calculado.

> ⚠️ **ANTES DE SUBIR HARVEST:** Cruzar keywords candidatas contra el Campaign CSV para detectar si ya están en campañas Exact activas con buen ACoS. Si ya existe cobertura → NO crear campaña nueva (canibalización de presupuesto).
>
> Proceso: exportar Campaign CSV → buscar la keyword en la columna Targeting → si existe en Exact con ACoS < target → remover del harvest.

### Tab 4 — 🤖 Análisis IA

**Input adicional:** Nombre del cliente + Target ACoS + precio promedio.

Genera análisis ejecutivo con Claude basado en los candidatos detectados. Útil para preparar el comentario de optimización del reporte semanal.

### Tab 5 — 📊 Por Campaña

Groupby por campaign: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC. Clasificación Brand/No Brand automática. 4 KPIs + tabla con color coding + download Excel.

---

---

## 3. 🔍 Search Query Performance (SQP)

**Para qué sirve:** Ver qué busca el mercado total (no solo tus campañas) y cuánto share of voice tenés en cada query.

**Input:** SQP descargado desde Brand Analytics (.xlsx) — período recomendado: 30 días o trimestral.

### Tab 1 — Vista General

Muestra el SQP completo con métricas de mercado. Detecta automáticamente la marca desde el archivo.

### Tab 2 — Market Share

Calcula tu impression share, click share y purchase share por query.

| Clasificación | Condición |
|---------------|-----------|
| Dominando | Impression Share > 30% |
| Competitivo | IS 10–30% |
| Oportunidad | IS < 10% |

**Cuándo usarlo:** Para identificar dónde el mercado compra pero vos no aparecés.

### Tab 3 — Gap Analysis

Detecta queries donde:
- Total Impressions > 1000 AND Brand Impressions = 0 → "No aparecés — agregar como keyword"
- Purchase Rate mercado > Purchase Rate propia → "Mercado convierte mejor — problema de listing o bid"

**Output:** Lista de keywords a agregar como nuevas campañas.

### Tab 4 — 🤖 Análisis IA

Genera análisis ejecutivo de market share con Claude.

---

---

## 4. 🔗 Análisis Cruzado STR vs SQP

**Para qué sirve:** Cruzar lo que tus campañas están capturando (STR) contra lo que busca el mercado (SQP) para detectar gaps y oportunidades.

**Inputs:** STR + SQP simultáneamente.

### Lógica del cruce

| Situación | Significado |
|-----------|-------------|
| En ambos (STR + SQP) | Ya estás capturando ese término con ads |
| Solo en STR | Pagás por ese término pero el mercado no lo busca tanto |
| Solo en SQP | El mercado lo busca pero tus campañas no lo capturan → **OPORTUNIDAD** |

**Filtros disponibles:** mínimo de impresiones, Search Query Score, purchases, tipo (Marca/Genérica).

### Plan de Acción (output principal)

Tabla con acción sugerida por keyword:

| Acción | Condición |
|--------|-----------|
| 🚀 AGREGAR | Alta compra en mercado, no aparecés |
| ✅ HARVEST | Está en STR con buen ACoS, agregar como Exact |
| ⬇️ BAJAR BID | ACoS > target × 2 |
| ⚡ ESCALAR | Impression share bajo + mercado comprando |
| 👁️ MONITOREAR | Sin acción inmediata necesaria |

> 💡 **El bulk descargado del Plan de Acción es el INPUT del Campaign Builder (Módulo 10).**

---

---

## 5. 📈 Tendencia Multi-Semana

**Para qué sirve:** Ver evolución de queries a lo largo de varias semanas para detectar tendencias estacionales.

**Input:** Hasta 4 archivos SQP de distintas semanas.

**Clasificación por query:**
- ↑ Creciendo (>10%)
- → Estable
- ↓ Cayendo (>10%)

Útil para planificar presupuesto estacional y detectar keywords que están ganando o perdiendo volumen.

---

---

## 6. 📁 Bulk Campañas + Campaign Analyzer

**Para qué sirve:** Ver y diagnosticar el estado de todas las campañas activas.

**Input:** Campaign CSV exportado desde Campaign Manager con métricas de performance (.csv).

> ⚠️ Tiene que ser el Campaign CSV con columnas de performance (Total cost, Sales, Purchases, Impressions, ACOS). Si subís el bulk .xlsx sin métricas, solo verás la Vista General.

### Tab 1 — Vista General

Muestra el archivo raw completo. Usalo para revisar rápidamente la estructura de campañas.

### Tab 2 — 🚦 Campaign Analyzer

**Input adicional:** Target ACoS + precio promedio.

**Diagnóstico automático por campaña:**

| Semáforo | Condición | Acción |
|----------|-----------|--------|
| 🔴 PAUSAR | spend > threshold AND 0 órdenes | Pausar en Campaign Manager |
| 🟡 REVISAR | ACoS > target × 2 | Revisar bids / negativos |
| ✅ ESCALAR | ACoS < target × 0.5 con órdenes | Subir budget |
| ⚫ FANTASMAS | 0 impresiones activas | Verificar bid / status |

Muestra "Spend recuperable: $X" si pausás las campañas rojas.

> ⚠️ **Las pausas se ejecutan manualmente en Campaign Manager.** La app indica cuáles pausar pero no puede ejecutarlo (requiere Campaign ID numérico real).

---

---

## 7. 💰 Business Report

**Para qué sirve:** Analizar ventas, sesiones, CVR y BuyBox por ASIN.

**Input:** Business Report de Seller Central (.csv) — By Date (cuenta total) o By ASIN (desglose).

Muestra métricas de ventas orgánicas + paid combinadas. Se usa principalmente como input para el Weekly Client Report y como fuente del Parent-Child map.

---

---

## 8. 🔻 Análisis de Funnel

**Para qué sirve:** Ver si tenés el funnel completo (Auto → Broad → Phrase → Exact) para cada producto y detectar brechas.

**Inputs:** STR + Bulk file de campañas.

**Lo que detecta:**
- Qué match types existen por ASIN/producto
- Qué keywords del STR no tienen campaña Exact dedicada
- Campañas sugeridas con naming convention Capybaras

**Reglas de harvest del funnel:**
- Auto → Phrase: 2+ órdenes AND ACoS ≤ target × 1.2
- Phrase → Exact: 3+ órdenes AND ACoS ≤ target

---

---

## 9. 🧠 Bid Optimizer

**Para qué sirve:** Calcular el bid óptimo para cada keyword basado en CVR real, precio y target ACoS.

**Input:** STR cargado + Inventory Report (.txt) + Target ACoS (slider).

**Fórmula:** `bid_sugerido = (CVR / 100) × precio × (target_ACoS / 100)`

**Clasificación:**

| Semáforo | Condición | Acción |
|----------|-----------|--------|
| 🟢 SUBIR | bid actual < bid sugerido × 0.7 | Incrementar bid |
| ⚫ OK | bid entre 0.7x y 1.3x del sugerido | No tocar |
| 🔴 BAJAR | bid actual > bid sugerido × 1.3 | Reducir bid |
| ⛔ PAUSAR | clicks > 10 AND órdenes = 0 | Pausar keyword |

**Output:** Bulk con solo las columnas Max Bid modificadas → subís y Amazon actualiza todos los bids de una vez.

---

---

## 10. 🚀 Campaign Builder

**Para qué sirve:** Generar el archivo bulk listo para subir a Amazon con nuevas campañas SP/SB/SD, a partir del Plan de Acción del Análisis Cruzado.

### Versiones del módulo

| Versión | Fecha | Cambio principal |
|---------|-------|-----------------|
| v1.0 | 2026-03-21 | SP clustering + export bulk |
| v1.1 | 2026-04-08 | + soporte SB y SD (flujo básico) |
| SB v2.0 | 2026-04-23 | Rewrite SB: selector SBV/SBH + Brand Entity ID + 29 columnas API 2026 + validaciones estrictas |

### Flujo completo (paso a paso)

```
Análisis Cruzado → Plan de Acción → Descargar bulk
        ↓
  Campaign Builder → subís ese bulk como input
        ↓
Seleccioná tipo: SP / SB / SD
        ↓
Completá datos del producto
        ↓
Preview de campañas generadas con validación
        ↓
Descargar bulk Amazon → subir a Campaign Manager → Bulk Operations → Upload
```

### Clustering automático de keywords (SP)

- **PAT** — si la keyword es un ASIN (B0...)
- **Spanish** — si tiene palabras en español (crema, hidratante, para, piel...)
- **Vitamin A** — si menciona vitamin a, allantoin, retinol...
- **Brand** — si menciona el nombre de la marca
- **Discovery** — todo lo demás

### Bidding Strategy por tipo (SP)

| Tipo | Bid Strategy | Placement |
|------|-------------|-----------|
| Exact Brand/Ranking | Fixed Bid | ToS +50% |
| Exact Harvest/Profit | Dynamic Down-Only | ToS +25% |
| Phrase Discovery | Dynamic Down-Only | ToS +10% |
| Auto | Fixed Bid | Sin modifier |

### SB v2.0 — Sponsored Brands (NUEVO 2026-04-23)

**Paso 0:** Selector SBV (Sponsored Brand Video) vs SBH (Sponsored Brand Headline)

**Campos comunes SBV + SBH:**
- Brand Entity ID — **obligatorio** (Amazon Ads API 2026, sin él el bulk es rechazado)
- Brand Name
- Creative Headline (máx 50 chars)
- 3 ASINs creativos

**Campos específicos SBV:**
- Video Asset ID — obligatorio (formato: `BVIDEO_XXXXXXXXXX`)
- Landing Page type + URL

**Campos específicos SBH:**
- Brand Logo Asset ID — obligatorio
- Logo Crop — obligatorio: `Square` o `Rectangle`
- Brand Logo URL — opcional
- Landing Page type + URL

**Bulk SB 2026 — 29 columnas:**
```
Campaign ID | Campaign Name | Ad Group Name | Ad Group ID | Ad ID |
Keyword | Match Type | Start Date | End Date | Status |
Daily Budget | Bid | Bidding Strategy | Brand Entity ID | Brand Name |
Creative Headline | Creative ASINs | Video Asset ID | Logo Asset ID |
Logo Crop | Logo URL | Landing Page URL | Landing Page Type |
Portfolio ID | Impressions | Clicks | Spend | Sales | Orders
```

> ⚠️ La columna `" Ad Group ID"` tiene un espacio inicial — es un bug conocido de Amazon documentado. NO quitar el espacio.

**Validaciones estrictas bloqueantes:** Si falta cualquier campo obligatorio, el módulo muestra lista de errores en lugar del botón de descarga.

**Naming SB (hardcoded — NO modificar):**
```
[Marca] - [ASIN] - SB - KW - [Match] - [Cluster]
Ejemplo: Dermaglos - B0CYLMJJJC - SB - KW - EXACT - Brand 1
```

> ⚠️ **El naming Capybaras está hardcoded por diseño.** Es un contrato con Atom11 Rules Builder (M11): el módulo parsea el Campaign Name para clasificar campañas en DISCOVERY/RANKING/CONQUEST/DEFENSIVE/etc. Modificar el naming rompe la automatización completa.

### SD — Sponsored Display (preexistente)

- **Product Targeting** — ASIN de competidores
- **Audience** — retargeting de visitantes
- Naming: `[Marca]-[ASIN]-SD-[PT/AUD]-[SubTipo]`

> ⚠️ **ANTES DE DESCARGAR — verificar siempre:**
> 1. Cruzar keywords con campañas activas (ver regla crítica en STR Tab 3)
> 2. Confirmar SKUs — tienen que ser los SKUs reales de Seller Central, no los ASINs
> 3. Confirmar Start Date en formato YYYYMMDD
> 4. Las campañas Brand que ya existen con buen ACoS → remover del bulk
>
> **Las pausas de campañas existentes NO se pueden hacer desde el bulk generado** — requieren Campaign ID numérico. Hacerlas manualmente en Campaign Manager.

---

---

## 11. ⚙️ Atom11 Rules Builder

**Para qué sirve:** Generar las rules de automatización para importar en Atom11. Multi-marca: todo configurable con prefijo, brand terms, ASINs y targets por cuenta.

**Inputs:** Prefijo de marca (LTD, DG, MB...) + Target ACoS + tabla de ASINs con precio (asigna tier automáticamente).

### Tab 1 — Configuración

- Prefijo de marca
- Brand terms a excluir del Negate
- Target ACoS de la cuenta
- Tabla de ASINs editable con precio → auto-calcula tiers y targets por objetivo

**Tiers automáticos por precio:**

| Tier | Rango | Clicks Negate | Spend Hard-Stop | CVR ref |
|------|-------|---------------|-----------------|---------|
| LOW | < $12 | 18 clicks | $15 | ~11% |
| MID | $12–$22 | 22 clicks | $22 | ~10% |
| HIGH | > $22 | 28 clicks | $30 | ~8% |

### Tab 2 — Campaign Groups

Sube Campaign CSV → clasifica campañas automáticamente en grupos por objetivo:

| Objetivo | Target ACoS (relativo a cuenta) | Tipo campañas |
|----------|--------------------------------|---------------|
| DISCOVERY | 120% del target | AUTO + BROAD |
| RANKING | = target cuenta | KW Exact + Phrase |
| CONQUEST | ~86% del target | PAT + ASIN targeting |
| DEFENSIVE | ~71% del target | Brand KWs |
| PROFIT | 50% del target | Harvested winners |
| REMARKETING | ~71% del target | SD retargeting |
| SCAVENGER | Sin rules | Catch-all |

Export Excel multi-sheet para Atom11 (una sheet por grupo con Campaign Names).

### Tab 3 — Rules Generator

Genera hasta 274 rules con thresholds dinámicos:

| Tipo de rule | Cantidad | Descripción |
|-------------|----------|-------------|
| Bid Optimiser | 7 niveles × 3 tiers × 6 objetivos = 126 | INC AGG/SOFT, FLAT, DEC SOFT/RISK/CTRL/HARD |
| Placement Optimiser | 6 × 3 × 6 = 108 | TOS INC/DEC, PP INC/DEC |
| Search Term Negator | 3 × 6 = 18 | Clicks > threshold, 0 orders |
| Hard Stop Anti-Drain | 3 × 6 = 18 | Spend > threshold, 0 orders |
| Harvester | 2 × 2 = 4 | Solo DISCOVERY + RANKING |

### Multiplicadores v2026.2 (thresholds por nivel)

| Nivel | Multiplicador | Acción |
|-------|--------------|--------|
| INC AGG | < 0.50× target | Increase Bid 15%, until $2.00 |
| INC SOFT | 0.50×–0.85× target | Increase Bid 8%, until $2.00 |
| FLAT | 0.85×–1.0× target | No tocar |
| DEC SOFT | > 1.14× target | Decrease Bid 10%, until $0.15 |
| DEC RISK | > 1.36× target | Decrease Bid 15%, until $0.15 |
| DEC CTRL | > 1.57× target | Decrease Bid 25%, until $0.15 |
| DEC HARD | > 1.86× target | PAUSE TARGET |

### Config global recomendada

- Frecuencia: Martes + Viernes 06:00 AM (timezone de la cuenta)
- Wait: 3 días entre ejecuciones sobre el mismo keyword
- Lookback: 14 días (Bid Optimiser / Hard Stop) | 30 días (Negate / Harvest)
- Bid máximo INC: $2.00 | Bid mínimo DEC: $0.15
- Excluir brand terms del Negate siempre

### Thresholds precalculados (ejemplo target cuenta 70%)

| Objetivo | Target | INC AGG < | INC SOFT | DEC SOFT > | DEC RISK > | DEC CTRL > | DEC HARD > |
|----------|--------|-----------|----------|------------|------------|------------|------------|
| RANKING | 70% | 35% | 35–60% | 80% | 95% | 110% | 130% |
| DEFENSIVE | 50% | 25% | 25–42% | 57% | 68% | 78% | 93% |
| DISCOVERY | 84% | 42% | 42–71% | 96% | 114% | 132% | 156% |
| CONQUEST | 60% | 30% | 30–51% | 68% | 82% | 94% | 112% |
| PROFIT | 35% | 18% | 18–30% | 40% | 48% | 55% | 65% |
| REMARKETING | 50% | 25% | 25–42% | 57% | 68% | 78% | 93% |

---

---

## 12. 🔬 Reportes Atom 11

**Para qué sirve:** Analizar performance de campañas con el formato de reporte de Atom 11 (WoW, MoM, DateRange).

**Input:** 1 o 2 archivos .xlsx exportados desde Atom 11.

**Modos de análisis:**
- 1 archivo: análisis single period, WoW interno, MoM, o DateRange
- 2 archivos: comparación cross-file entre dos períodos

**Output Excel (3-4 hojas):**
- **Informe Cliente** — branding + KPIs + top 3 + diagnóstico + recomendaciones
- **KPIs** — tabla comparativa PW vs TW
- **Datos** — tabla completa con delta% coloreado
- **Parent Evolution** (opcional si el BR está cargado)

**Toggle ES/EN** para generar el informe en español o inglés.

### Funciones internas

```python
_parse_atom11(file)           # → (df_flat, entity_cols, col_map, fmt)
_detect_atom11_type(ec)       # → "ASIN" | "Portfolio" | "Keyword" | etc.
_kpis(df)                     # → dict: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC
_generate_summary(...)        # → string ejecutivo
_build_atom11_excel(...)      # → BytesIO 3-4 sheets
```

---

---

## 13. 🛡️ Reportes MerchanSpring

**Para qué sirve:** Procesar los reportes de MerchanSpring (P&L, inventory, advertising) en un Excel estructurado.

**Input:** .xlsx o .pdf exportado desde MerchanSpring.

**Output Excel (4 hojas):**
- **Summary** — KPIs generales del período
- **Advertising** — métricas de ads por tipo
- **Inventory & Health** — stock, BuyBox, velocidad
- **WoW Comparison** — comparación semana a semana

### Flujo PDF

El parser PDF extrae 20+ secciones con try/except defensivo en cada una. Incluye: P&L, inventory, advertising by type, campaigns, top products, traffic by parent/child, cancellations, sales by category/country/brand, BSR, reviews, shipping, BuyBox.

### Flujo XLSX

```python
_parse_merchanspring(file)              # → dict: title, period, kpis, summary_df, adv_df, inv_df, wow_df, wow_metrics
_build_merchanspring_excel(data, name)  # → BytesIO 4 hojas con color rules
```

---

---

## 14. 📊 Weekly Client Report

**Para qué sirve:** Generar el reporte semanal para el cliente con comparación WoW automática.

### Inputs (4 archivos, mismo date range de 14 días)

| Archivo | Bajarlo desde | Para qué |
|---------|--------------|----------|
| BR diario 14d | Business Reports → By Date → Sales and Traffic | CUENTA TOTAL PW vs TW |
| BR by Child ASIN | Business Reports → By ASIN → Child Item | Desglose por ASIN |
| Atom 11 ASIN | Atom 11 → ASIN → DateRange 14d | Ad Spend/Sales split 7+7 |
| Campaign CSV | Campaign Manager → mismo date range | Impressions / CTR / DPV / NTB |

### Output Excel (4 hojas)

- **📈 WoW Comparison** — fila azul CUENTA TOTAL + desglose por ASIN
- **📣 Advertising** — PW vs TW + top 10 campañas + alarmas ACoS>60% + portfolios
- **📋 Reporte Ejecutivo** — análisis redactado con toggle ES/EN
- **📝 Changelog** — notas del AM sobre cambios de la semana

### Funciones internas

```python
_parse_br_daily_wow(file)
_parse_br_wow(file)
_parse_atom11_wow(file)
_build_weekly_excel(br_tw, br_pw, atom_tw, atom_pw, client_name, lang, br_daily)
```

### Fixes importantes

- `BuyBox_TW = None` si BR diario no tiene columna (ej: M&B)
- Detecta automáticamente `Unit Session Percentage` o `Order Item Session Percentage`
- BuyBox con 0 sesiones → ignorado (evita falsos positivos)

---

---

## 15. 👁️ Listing Monitor

**Para qué sirve:** Monitorear ASINs de Amazon y alertar cuando algo cambia vs el snapshot anterior.

**Campos monitoreados:** precio, rating, reviews count, badges (Best Seller/Amazon's Choice), bullets, stock, título.

**Arquitectura:**
- **Tab 1 — Escanear ASINs:** input ASINs, selector marketplace (MX/COM/ES/BR/CA), delay configurable, guardado automático de snapshot
- **Tab 2 — Ver Alertas:** comparación vs snapshot anterior, color coding (🔴 alerta / 🟡 info / 🟢 ok)
- **Tab 3 — Historial:** tabla de todos los snapshots con columna Producto

**Storage:** Snapshots en `data/listing_snapshots/snapshots.json` con clave `{ASIN}_{MARKETPLACE}`

---

---

## 16. 📊 Gamboa Generator

**Para qué sirve:** Generar reportes HTML integrales tipo dashboard interactivo con SQP mensual + BR semanal. Listo para publicar en Hostinger o enviar al cliente.

### Inputs

- **SQP multi-archivo** (Brand Analytics → Search Query Performance) — auto-detecta mes por filename o columna "Reporting Range"
- **BR semanal by ASIN** (Business Reports → By ASIN → Child Item) — un archivo por semana, auto-detecta ISO week
- **Inventory Report (opcional)** — mapeo SKU ↔ ASIN. Sin esto usa ASIN como identificador
- **CSV de categorías (auto-generado)** — plantilla descargable, persistente en `notes/brands/{cliente-slug}/gamboa_categories.csv`

### Output

HTML standalone (~5-10 MB) con 2 paneles interactivos:
- **Panel SQP mensual:** 15 meses de queries, filtros, funnel conversión, cards por categoría, tabla filtrable, 7 charts de tendencia (SV, Impressions, Clicks, Cart Adds, Purchases, CTR, Conversion Rate)
- **Panel WoW Category (semanal):** 68 semanas de KPIs WoW/YoY, category cards, tabla con sparklines, modal de tendencia por SKU

### Decisiones técnicas

- SKU opcional con fallback a ASIN — robustez, funciona sin Inventory Report
- Score SQP defensivo (fallback 0 si no existe columna "Search Query Score")
- SQP multi-upload con auto-detección de mes — Amazon BA baja archivo por mes o por rango, ambos casos soportados
- Categorías persistentes en CSV — reutiliza arquitectura existente, evita re-trabajo entre sesiones
- Template HTML separado de lógica Python — 64KB template mantenible por separado

---

---

## 17. 📅 Account Pulse

**Para qué sirve:** Monitor de salud diaria de la cuenta.

**Inputs:** BR Daily CSV + Campaign CSV.

**Output Excel (4 hojas):**
- **Resumen Ejecutivo** — portada naranja con KPIs, diagnóstico, mensaje para Slack/cliente
- **Ventas Diarias** — 43+ días con color por tipo (laboral/finde/festivo MX)
- **BuyBox & ASINs** — ordenado por impacto económico (ventas perdidas estimadas)
- **Campañas** — separadas NUEVA (verde) vs HEREDADA (azul), ACoS semáforo

**Paleta:** E84000 (naranja) | 1F1F1F (negro) | FAFAFA (blanco roto)

**Festivos MX hardcoded:**

```python
_FESTIVOS_MX = {
    (1,1):"Año Nuevo", (2,3):"Constitución", (3,17):"Juárez",
    (5,1):"Día del Trabajo", (9,16):"Independencia",
    (11,2):"Día de Muertos", (11,18):"Revolución", (12,25):"Navidad",
}
```

**Lo que detecta:**
- Gráfico ventas diarias — marcado fines de semana y festivos MX/USA
- Comparación semana a semana automática
- Detección anomalías (caídas >30% del promedio) con causa probable
- Semáforo BuyBox por ASIN con impacto económico estimado
- Separación campañas nuevas vs antiguas
- Resumen ejecutivo copiable para Slack/cliente

---

---

## 18. 📊 PPC Insights

**Para qué sirve:** Análisis profundo de performance PPC con múltiples dimensiones: por campaña, por keyword, por match type, por placement. Genera insights automáticos sobre tendencias y anomalías.

**Inputs:** Campaign CSV + STR.

**Lo que genera:**
- Análisis de performance por dimensión (campaña, keyword, match type, placement)
- Detección automática de tendencias y anomalías
- Insights accionables con prioridad
- Comparación entre períodos

---

---

## 19. 🔍 PPC Audit

**Para qué sirve:** Auditoría completa de la estructura de campañas desde Bulk File multi-hoja.

**Inputs:**
- Bulk File (.xlsx) — requerido (Campaign Manager → Bulk Operations)
- Business Report (.csv o .xlsx) — opcional (para TACoS y Revenue)
- Brand terms — input texto (para clasificación de targets)

**Output:** 6 hojas Excel con KPIs, auditoría, performance por segmento, deep checks, target graduation.

**Score 0-100** desglosado. Headers coloreados: SP azul, SB violeta, SD verde.

---

---

## 20. 📈 PPC Forecast

**Para qué sirve:** Proyecciones de spend, sales y ACoS basadas en data histórica.

**Input:** Campaign CSV con múltiples períodos.

**Lo que genera:**
- Modelado de escenarios: conservador, base, agresivo
- Ajustes de budget y bid por escenario
- Proyección de revenue y ACoS a 30/60/90 días
- Visualización de tendencias con bandas de confianza

---

---

## 21. 🔬 DataDive Analyzer

**Para qué sirve:** Procesador de reportes DataDive (herramienta de research de competidores en Amazon).

**Input:** Reporte DataDive exportado.

**4 tabs:**
- MKL Keywords con SV, Relevance, Launch Score
- Competitors con matriz comparativa
- Rank Radar con tracking orgánico diario
- Ranking Volatility + PPC IS cruzado

---

---

## 22. 🔎 Helium 10 Analyzer

**Para qué sirve:** Procesador de reportes Helium 10 (Cerebro, Magnet, X-Ray).

**Input:** Reporte Cerebro / Magnet exportado.

**3 tabs:**
- Cerebro Reverse ASIN con oportunidades PPC
- KW Research multi-competidor
- Competitor Gap Analysis con acciones sugeridas

---

---

## 23. 📢 SBH Recommendation

**Para qué sirve:** Generador de recomendaciones de Sponsored Brand Headlines (SBH).

**Inputs:** DataDive MKL + SQP + Campaign CSV (opcional).

**Lo que genera:**
- Targets prioritarios por SV e Impression Share
- Clustering automático de keywords
- Headlines sugeridos por cluster

---

---

## 24. 📚 Knowledge Base

**Para qué sirve:** Base de conocimiento interna de la agencia.

**Lo que incluye:**
- SOPs y frameworks propios de Capybaras
- Análisis de tendencias Amazon 2026
- Learnings de campañas por cliente
- Notas de research (Rufus AI, SBV, DSP, etc.)

**Conectado al sistema de notas en Obsidian:**

```
C:\proyectos\ppc-manager\notes\
├── knowledge\          ← BIBLIOTECA
│   └── YYYY-MM-DD-tema-corto.md
├── brands\
│   ├── dermaglos\
│   ├── ltd\
│   ├── mb\
│   └── setex\
├── Biblioteca.md
├── INTELLIGENCE-INDEX.md
└── Slack #learnings-implementations.md
```

Permite búsqueda por categoría, fecha y tags.

---

---

## Apéndice A — Flujo de trabajo semanal recomendado

```
LUNES (análisis)
  1. STR → Tab 2 Negatives Mining → negativizar lo urgente
  2. STR → Tab 3 Harvest Candidates → identificar nuevos términos
  3. Bulk Campañas → Campaign Analyzer → detectar campañas a pausar/escalar

MARTES (reportes)
  4. Weekly Client Report → generar y enviar al cliente

QUINCENAL
  5. SQP → Market Share + Gap Analysis → detectar oportunidades de mercado
  6. Análisis Cruzado STR vs SQP → Plan de Acción
  7. Campaign Builder → generar bulk de nuevas campañas → subir a Amazon

MENSUAL
  8. Atom 11 Reports → análisis MoM
  9. Atom11 Rules Builder → revisar y actualizar rules si cambiaron precios/objetivos
  10. PPC Audit → health score de la cuenta
  11. PPC Forecast → proyección siguiente trimestre

OCASIONAL (cada 2-4 semanas)
  12. Listing Monitor → revisar snapshots de ASINs clave
  13. Gamboa Generator → generar HTML integral para cliente (SQP + BR mensual)
```

---

---

## Apéndice B — Reglas críticas de operación

| Regla | Detalle |
|-------|---------|
| Cruzar STR con campañas activas antes de subir bulk | Si la keyword ya está en Exact activo con ACoS < target → no crear campaña nueva |
| Nunca negativizar dentro de una Exact Match propia | Los negativos van en Auto/Broad/Phrase de origen |
| Fixed Bid primeras 2 semanas | Toda campaña nueva arranca con Fixed Bid — no Dynamic |
| No optimizar bids antes de 14 días | Esperar el learning period antes de tocar bids |
| SKU ≠ ASIN | El bulk de Amazon requiere SKU, no ASIN. Buscar en Seller Central → Manage Inventory |
| Naming convention Capybaras | `[Marca] \| [ASIN] \| [MKT] \| [Tipo]-[SubTipo] \| [Match] \| [Cluster]` |
| Pausas requieren Campaign ID numérico | No se pueden pausar campañas desde el bulk generado. Hacerlo manual en Campaign Manager |
| Nunca negar brand terms | Agregar marca + variantes con acento en "Exclude Keywords" del Negate |
| Max 1 cambio de bid/semana | Cambiar bids más de 1 vez reinicia el learning period de Amazon |
| Solo campañas ENABLED en Atom11 | Las pausadas dan "Not Found" — filtrar antes de subir xlsx |

---

---

## Apéndice C — Thresholds SOP Capybaras 2026

### Negativización (thresholds correctos)

| Regla | Fórmula / Threshold | Ejemplo |
|-------|---------------------|---------|
| R2 — Clicks por CVR | `max(10, round(1/CVR × 2))` | CVR 10% → 20 \| CVR 5% → 40 \| CVR 3% → 60 |
| R3 — Gasto sin conversión | `precio × 0.50` | Producto $30 → negativizar si gastó $15 sin ventas |
| R5 — CTR bajo | `imp >= 2500 AND CTR < 0.18%` | NO usar 500 imp ni 0.1% CTR |

```python
# NUNCA negar dentro de campaña Exact Match propia
# NUNCA negar KW que está en Exact activo aunque tenga ACoS alto en Broad/Phrase
```

### Harvesting

| Regla | Condición |
|-------|-----------|
| Principal (se mantiene) | orders >= 3 AND ACoS <= 25% |
| Por CVR alto | CVR >= 10% AND clicks >= 15 |
| Por volumen | orders >= 5 (ignora ACoS) |

### Placement Modifiers

| Match Type | Top of Search | Product Pages |
|-----------|---------------|---------------|
| Exact — Ranking (sem 1-4) | +50% | 0% |
| Exact — Harvest/Profit (sem 5+) | +25% | 0% |
| Phrase — Discovery | +10% | 0% |
| Broad / Auto | 0% | 0% |
| PAT Competitor | 0% | +50% |

### Tiers por precio (Atom11)

| Tier | Rango | Clicks Negate | Spend Hard-Stop | CVR ref |
|------|-------|---------------|-----------------|---------|
| LOW | < $12 | 18 clicks | $15 | ~11% |
| MID | $12–$22 | 22 clicks | $22 | ~10% |
| HIGH | > $22 | 28 clicks | $30 | ~8% |

**Fórmula:** `clicks = round(1 / CVR_estimado) × 2`

### Métricas objetivo pre-lanzamiento

| Métrica | Fórmula | Ejemplo |
|---------|---------|---------|
| Break-Even ACoS | (Precio - COGS - FBA fees) / Precio | Precio $50, COGS $15, FBA $8 → BE ACoS = 54% |
| Target ACoS Launch (sem 1-4) | Hasta 1.5× Break-Even ACoS | BE 54% → Target launch hasta 81% |
| Target ACoS Profit (sem 5+) | ≤ Break-Even ACoS | ≤ 54% |

---

---

## Apéndice D — Naming Convention — Capybaras Standard

### Formato

```
[Marca] | [ASIN/Producto] | [Marketplace] | [Tipo]-[SubTipo] | [Match/Target] | [Cluster/Tema] | [KW/Target]
```

### Ejemplos por tipo

| Tipo | Ejemplo |
|------|---------|
| SP Exact Ranking | `Setex \| B081GB8F89 \| MX \| SP-KWS \| EXACT \| almohadillas lentes \| almohadillas para anteojos` |
| SP Auto Close Match | `LTD \| B09MG1PM6L \| MX \| SP-AUTO \| CLOSE \| swaddle discovery` |
| SP PAT Competitor | `M&B \| B0F6LB9T22 \| MX \| SP-PAT \| ASIN \| COMP TOP15` |
| SP Phrase Expansion | `Setex \| B081GB8F89 \| MX \| SP-KWS \| PHRASE \| nose pads cluster` |
| SBV Brand | `LTD \| MX \| SBV \| BRAND \| sacos dormir bebe` |
| SD Retargeting | `M&B \| MX \| SD \| RETARGET \| visitors 14d` |

### Portfolios recomendados

| Portfolio | Tipo de campaña | Bid Strategy | Target ACoS | KPI principal |
|-----------|----------------|-------------|-------------|---------------|
| [Marca] \| RANKING | SP Exact ranking, SP PAT | Fixed Bid | Hasta 1.5× BE ACoS | Ranking position + velocity |
| [Marca] \| PROFIT | SP Exact harvest, Phrase refinadas | Dynamic Down-Only | ≤ BE ACoS | ACoS + ROAS |
| [Marca] \| BRAND DEFENSE | SP Exact brand, SB/SBV brand | Fixed Bid | < 10% ACoS | Impression Share en brand terms |
| [Marca] \| DISCOVERY | SP Auto (4 camps), SP Broad | Fixed → Down-Only | Tolerante (harvest) | Nuevos search terms + nuevos ASINs |

---

---
