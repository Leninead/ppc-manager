# CLAUDE.md
## 🦫 Proyecto: Amazon PPC Manager
**Agencia:** Capybaras Agency  
**Dev:** Lenin Acosta  
**Ruta local:** `C:\proyectos\ppc-manager`  
**Comando:** `python -m streamlit run app.py`  
**Stack:** Python + Streamlit + Pandas + OpenPyXL + pdfplumber  
**Arquitectura:** Modularizando — `app.py` (~200 líneas router) + `core/` + `modules/`

## ⚙️ Setup
```bash
python -m streamlit run app.py
pip install streamlit pandas openpyxl pdfplumber
```
No hay build step, test suite ni linter configurado.

---

## 📐 Estructura de navegación (Sidebar) — Estado actual

| # | Página | Sección | Estado |
|---|--------|---------|--------|
| 1 | 🏠 Inicio | — | ✅ rediseñado 2026-03-27 (3 cards + flujo guiado + changelog) |
| 2 | 📊 Search Term Report | PPC | ✅ completo |
| 3 | 🔍 Search Query Performance | PPC | ✅ completo |
| 4 | 🔗 Análisis Cruzado STR vs SQP | PPC | ✅ + Plan de Acción 2026-03-21 |
| 5 | 📈 Tendencia Multi-Semana | PPC | ✅ completo |
| 6 | 📁 Bulk Campañas | PPC | ✅ + Campaign Analyzer 2026-03-21 |
| 7 | 💰 Business Report | PPC | ✅ completo |
| 8 | 🔻 Análisis de Funnel | PPC | ✅ completo |
| 9 | 🧠 Bid Optimizer | PPC | ✅ nuevo 2026-03-21 |
| 10 | 🚀 Campaign Builder | PPC | ✅ nuevo 2026-03-21 |
| 11 | 🧲 DataDive Analyzer | Research | ✅ conectado 2026-03-27 (4 tabs: MKL, Competitors, Rank Radar, Volatility) |
| 12 | 🧲 Helium 10 Analyzer | Research | ✅ conectado 2026-03-27 (3 tabs: Cerebro, KW Research, Competitor Gap) |
| 13 | 📢 SBH Recommendation | Research | ✅ conectado 2026-03-27 (targets SBH cruzando MKL+SQP+Campaign) |
| 14 | 🔎 PPC Insights | Research | ✅ conectado 2026-03-27 (health score por ASIN, 824 líneas) |
| 15 | 📈 PPC Forecast | Research | ✅ conectado 2026-03-27 (proyección ventas + estacionalidad) |
| 16 | 🛡️ PPC Audit | Research | ✅ conectado 2026-03-27 (auditoría integral score 0-100) |
| 17 | 📊 Account Pulse | Research | ✅ conectado 2026-03-27 (monitor salud diaria + festivos MX) |
| 18 | 🔬 Reportes Atom 11 | Account | ✅ completo |
| 19 | 🛡️ Reportes MerchanSpring | Account | ✅ completo |
| 20 | 📊 Weekly Client Report | Account | ✅ completo |
| 21 | ⚙️ Atom11 Rules Builder | PPC | ✅ nuevo 2026-03-23 |
| 22 | 📚 Knowledge Base | Knowledge | ✅ conectado 2026-03-27 (explorar + agregar notas .md) |
| 23 | 👁️ Listing Monitor | Account Manager | ✅ nuevo 2026-04-09 |
| 24 | 🛡️ Listing Compliance | Account Manager | ✅ nuevo 2026-04-16 — detector keywords weighted product |

Navegación por `st.session_state["selected_page"]` + `_nav(page)` callback.
Sidebar colapsable con `st.expander` por sección: PPC (expanded) | Research | Account | Knowledge.

---

## 🏗️ Estado de modularización (2026-03-18)

app.py original: 3,974 líneas → actual: ~200 líneas (router + sidebar oscuro)

### ✅ Módulos extraídos
- `core/i18n.py` — _I18N (dict ES/EN)
- `core/constants.py` — _BR_OPTIONAL_COLS, _PAGES
- `core/helpers.py` — _color_pct, read_sqp, extract_sqp_brand, kpi_card
- `core/business_report.py` — _BIZ_DIR, _parse_business_report_map, _auto_load_business_report_map
- `modules/atom11/parser.py` — _parse_atom11, _detect_atom11_type, _extract_period_df, _summarize_daterange, _split_two_weeks
- `modules/atom11/analysis.py` — _kpis, _generate_summary, _diag_items, _rec_items
- `modules/atom11/parent_evolution.py` — _build_parent_evolution, _generate_parent_evo_summary
- `modules/atom11/excel_export.py` — _build_atom11_excel
- `modules/merchanspring/parser.py` — _parse_merchanspring, _parse_merchanspring_pdf
- `modules/merchanspring/excel_export.py` — _build_merchanspring_excel, _build_ms_pdf_excel
- `modules/merchanspring/style_helpers.py` — _s_acos, _s_margin, _s_delta, _s_eff, _s_stock
- `modules/pages/inicio.py` — render()
- `modules/pages/search_term_report.py` — render()
- `modules/pages/search_query_performance.py` — render()
- `modules/pages/bulk_campanas.py` — render()
- `modules/pages/business_report.py` — render()
- `modules/pages/analisis_cruzado.py` — render()
- `modules/pages/tendencia_multisemana.py` — render()
- `modules/pages/analisis_funnel.py` — render()
- `modules/pages/atom11.py` — render()
- `modules/pages/merchanspring.py` — render()
- `modules/pages/weekly_client_report.py` — render() ✅ creado 17/03/2026
- `modules/pages/bid_optimizer.py` — render() ✅ creado 2026-03-21
- `modules/pages/campaign_builder.py` — render() ✅ creado 2026-03-21
- `modules/pages/atom11_rules_builder.py` — render() ✅ creado 2026-03-23
- `modules/pages/account_pulse.py` — render() ✅ conectado 2026-03-27
- `modules/pages/ppc_insights.py` — render() ✅ conectado 2026-03-27
- `modules/pages/ppc_forecast.py` — render() ✅ conectado 2026-03-27
- `modules/pages/ppc_audit.py` — render() ✅ conectado 2026-03-27
- `modules/pages/datadive_analyzer.py` — render() ✅ conectado 2026-03-27
- `modules/pages/helium10_analyzer.py` — render() ✅ conectado 2026-03-27
- `modules/pages/sbh_recommendation.py` — render() ✅ conectado 2026-03-27
- `modules/pages/knowledge_base.py` — render() ✅ conectado 2026-03-27
- `modules/pages/listing_monitor.py` — render() ✅ creado 2026-04-09
- `modules/pages/listing_compliance.py` — render() ✅ creado 2026-04-16 — detector keywords weighted product, scanea exports Seller Central, severidad CRITICAL/HIGH/MEDIUM, Excel 3 hojas

### 🔜 Pendiente arquitectura
- [ ] Reescribir app.py como router minimal (~100 líneas) — usar High effort
- [x] Bug: tendencia_multisemana.py KeyError cuando se suben dos SQPs iguales — fix aplicado 2026-03-19
- [x] Bug: datadive_analyzer.py return-in-tabs impedía que tabs 2-4 funcionen — fix aplicado 2026-03-27
- [x] @st.cache_data en todos los parsers de lectura de archivos — aplicado 2026-03-27

---

## 📋 Lógica por módulo — Resumen

- **STR:** ACoS = `Spend / Sales * 100`. Columnas auto-detectadas por nombre.
- **SQP:** `read_sqp()` con `skiprows=1`. Marca extraída con `extract_sqp_brand()`.
- **Bulk:** Dataframe raw. Filtro por `State == "ENABLED"`.
- **Business Report:** Dataframe raw de ventas y sesiones.
- **Análisis Cruzado STR vs SQP:** Cruza `Customer Search Term` vs `Search Query`. Opportunity Score = min-max de impresiones + clicks + purchase rate. Filtros: impresiones, SQS, purchases, tipo Marca/Genérica.
- **Tendencia Multi-Semana:** Hasta 4 SQPs. Pivot por `Search Query`. ↑ >10%, ↓ >10%, → estable.
- **Análisis de Funnel:** Campañas ENABLED, brechas STR vs bulk, campañas sugeridas con naming convention, harvesting Exact/Phrase (Exact si órdenes ≥ 3 o ACoS ≤ 25%).

---

## 🔑 Funciones helper globales
```python
read_sqp(file)                    # skiprows=1, lee SQP
extract_sqp_brand(file)           # extrae Brand=["..."] de row 0
_parse_business_report_map(path)  # → (child_to_parent, asin_to_title, br_df)
_auto_load_business_report_map()  # escanea data/business_report/ al iniciar
```

---

## 🧬 Sistema Parent-Child

- **Carpeta auto-load:** `data/business_report/` — carga primer CSV/XLSX al iniciar
- **`st.session_state` keys:**
  - `parent_child_map` → `{child_asin: parent_asin}`
  - `parent_child_names` → `{asin: titulo}`
  - `br_extra_df` → DataFrame completo del BR con métricas opcionales
  - `_cat_source_file` → nombre del archivo fuente
- **`_BR_OPTIONAL_COLS`** — Sessions, Page Views, Units Ordered, Total Order Items, Ordered Product Sales, Refund Rate, etc.
- **Columnas requeridas del BR:** `(Parent) ASIN`, `(Child) ASIN`
- Sidebar muestra estado verde/naranja con cantidad de parents

---

## 🔬 Tab: Reportes Atom 11

**Archivos:** 1 archivo (single/WoW/MoM/DateRange) o 2 archivos (comparación cross-file).

### Funciones internas
```python
_parse_atom11(file)           # → (df_flat, entity_cols, col_map, fmt)
_detect_atom11_type(ec)       # → "ASIN" | "Portfolio" | "Keyword" | etc.
_extract_period_df(df,ec,cm,period)
_summarize_daterange(df,ec,cm)
_split_two_weeks(df,ec,cm)

_kpis(df)                     # → dict: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC
_diag_items(kc, kp, lang)     # → [(status, text)]
_rec_items(kc, kp, lang)      # → [texto]
_generate_summary(...)        # → string ejecutivo
_color_pct(val)               # → CSS color para celdas delta%

_build_atom11_excel(...)
# → BytesIO 3-4 sheets:
#   "Informe Cliente" — branding + KPIs + top 3 + diagnóstico + recs
#   "KPIs" — tabla comparativa
#   "Datos" — tabla completa con delta% coloreado
#   "Parent Evolution" (opcional)

_build_parent_evolution(df_flat, ec1, cm1, fmt1, child_to_parent, asin_to_title, br_df, lang)
# → (pe_df, error_str_or_None)

_generate_parent_evo_summary(pe_df, lang)  # → string ejecutivo copiable
```

### Idioma (i18n)
Toggle ES/EN → `lang_code = "es" | "en"`. Dict `_I18N` con todos los labels.

---

## 🛡️ Tab: Reportes MerchanSpring

**Acepta:** `.xlsx` o `.pdf`

### Flujo PDF
```python
_parse_merchanspring_pdf(file)
# → dict: title, period, kpis, summary_df, inv_df, pnl_df, pnl_metrics,
#         prod_profit_df, health_data, adv_summary, adv_by_type_df, campaigns_df,
#         top_product_ads_df, top_keywords_df, traffic_summary, tc_parent_df,
#         tc_child_df, cancellations_data, sales_by_category_df,
#         sales_by_country_df, sales_by_brand_df, top_bsr_df, review_data,
#         shipping_data, buybox_snapshot, sections_log, wow_df (vacío)

_build_ms_pdf_excel(data, client_name)
# → BytesIO 4 hojas: Summary | Advertising | Inventory & Health | WoW Comparison
```

### Flujo XLSX
```python
_parse_merchanspring(file)
# → dict: title, period, kpis, summary_df, adv_df, inv_df, wow_df, wow_metrics

_build_merchanspring_excel(data, client_name)
# → BytesIO 4 hojas con color rules
```

### 🔜 Pendiente MerchanSpring
- [ ] WoW Completo PDF — mejorar hoja con: Sales/Units/Sessions/CVR/BuyBox/Ad Sales/Ad Spend/ACoS/TACoS/CM/Profit%
- [ ] Fix XLSX parser — IndexError cuando usuario elige elementos distintos
- [ ] Soporte formato NorseTradesman — pendiente decisión

---

## 📊 Tab: Weekly Client Report (2026-03-17)

**Estado:** ✅ completo y conectado en app.py — 2026-03-19

### Inputs (4 archivos, date range 14 días)
| Archivo | Dónde bajarlo | Para qué |
|---------|--------------|---------|
| BR diario 14d | By Date → Sales and Traffic | CUENTA TOTAL PW/TW |
| BR by Child | By ASIN → Child Item | Desglose por ASIN |
| Atom 11 ASIN | ASIN → DateRange 14d | Ad Spend/Sales split 7+7 |
| Campaign CSV | Campaign Manager → mismo date range | Impressions/CTR/DPV/NTB |

### Output Excel 3 hojas
- `📈 WoW Comparison` — fila azul CUENTA TOTAL + desglose por ASIN
- `📣 Advertising` — PW vs TW + top 10 camps + alarmas ACoS>60% + portfolios
- `📋 Reporte Ejecutivo` — análisis redactado, toggle ES/EN

### Funciones
```python
_parse_br_daily_wow(file)
_parse_br_wow(file)
_parse_atom11_wow(file)
_build_weekly_excel(br_tw, br_pw, atom_tw, atom_pw, client_name, lang, br_daily)
render()
```

### Fixes importantes
- `BuyBox_TW = None` si BR diario no tiene columna (ej: M&B)
- Detecta automáticamente `Unit Session Percentage` o `Order Item Session Percentage`
- BuyBox con 0 sesiones → ignorado (evita falsos positivos)

### Clientes probados
- **Love To Dream MX** — 56 ASINs, ACoS 22.7%, TACoS 17.4%, semana +43.9%
- **M&B (Mott & Bow)** — 159 ASINs, ACoS 8.6%, TACoS 5.4%, semana +58.3%

---

## 🗺️ PLAN MAESTRO 2026 — De "visor de reportes" a "sistema operativo de PPC"

### Nueva arquitectura de navegación propuesta

```
SECCIÓN 1: ANÁLISIS (existente + upgrades)
  🏠 Inicio
  📊 Search Term Report          ← UPGRADE: Negatives Mining + Harvest Engine
  🔍 Search Query Performance    ← UPGRADE: Market Share + Gap Analysis
  📁 Bulk Campañas               ← UPGRADE: Health Check + Budget Intel
  💰 Business Report             ← UPGRADE: CVR Intel + Velocity
  🔗 Análisis Cruzado STR+SQP    ← UPGRADE: Acción sugerida + Bulk output

SECCIÓN 2: ESTRATEGIA (tabs nuevas)
  🧠 Bid Optimizer               ← NUEVO
  ⚔️  Funnel Builder              ← UPGRADE del Análisis Funnel actual
  📅 Account Pulse               ← NUEVO (ya diseñado con Setex)

SECCIÓN 3: EJECUCIÓN (tabs nuevas — el diferenciador)
  🚀 Bulk Upload Builder         ← NUEVO: genera bulk listo para subir a Amazon
  🤖 Automation Rules Builder    ← NUEVO: genera rules para Atom 11

SECCIÓN 4: REPORTES
  📈 Tendencia Multi-Semana
  🔬 Reportes Atom 11
  🛡️  Reportes MerchanSpring
  📊 Weekly Client Report
```

---

## 📐 Detalle de upgrades — Tabs existentes

### 📊 STR → "STR + Intelligence Engine" (sub-tabs nuevos)

**Sub-tab: Negatives Mining**
```python
# Candidatos a negativo — thresholds 2026 correctos:

# Regla 1 — Irrelevancia obvia (acción inmediata)
irrelevante_obvio = True  # juicio del AM, 1-2 clicks

# Regla 2 — No conversión por CVR (threshold dinámico)
clicks_threshold = max(10, round((1 / cvr_producto) * 2))
# CVR 10% → 20 clicks | CVR 5% → 40 clicks | CVR 3% → 60 clicks

# Regla 3 — Gasto sin conversión
spend_threshold = precio_producto * 0.50  # 50% del precio de venta
# My Amazon Guy standard

# Regla 4 — ACoS extremo (ya con ventas, no es ranking KW)
# ACoS > 70% con < 5 órdenes → evaluar

# Regla 5 — CTR bajo por irrelevancia
impresiones_threshold = 2500  # NO 500
ctr_threshold = 0.18           # % — NO 0.1%

# Output: bulk-ready con columnas Amazon:
# Campaign | Ad Group | Keyword Text | Match Type (negativeExact/negativePhrase) | Status
```

**Sub-tab: Harvest Candidates**
```python
# Reglas de harvest (SOP Capybaras 2026)

# Regla principal
harvest_exact = orders >= 3 and acos <= 25.0

# Por CVR alto
harvest_cvr = cvr >= 10.0 and clicks >= 15

# Por volumen (ranking benefit)
harvest_vol = orders >= 5  # independiente del ACoS

# Bid sugerido para la nueva Exact
bid_sugerido = (cvr / 100) * precio_promedio * (target_acos / 100)

# Output: bulk-ready Amazon:
# Campaign Name | Ad Group | Keyword | Match Type (exact) | Max Bid | Status | Budget
```

### 🔍 SQP → "SQP + Market Intelligence" (sub-tabs nuevos)

**Sub-tab: Market Share**
```python
impression_share = brand_impressions / total_query_impressions * 100
click_share = brand_clicks / total_query_clicks * 100
purchase_share = brand_purchases / total_query_purchases * 100
revenue_potencial = total_impressions * cvr_propia * precio_avg

# Clasificación:
# IS > 30% → Dominando
# IS 10-30% → Competitivo
# IS < 10% → Oportunidad
```

**Sub-tab: Gap Analysis**
```python
# Queries donde Total Impressions > 1000 AND Brand Impressions == 0
# → "No aparecés — agregar como keyword"
# Queries donde Purchase Rate mercado > Purchase Rate propia
# → "Mercado convierte mejor — problema de listing o bid"
```

### 📁 Bulk → "Bulk + Health Check" (sub-tabs nuevos)

**Sub-tab: Health Check**
```python
# Detectar automáticamente:
# 1. Campañas sin ningún negativo
# 2. Ad groups con > 20 keywords activas
# 3. Keywords en Broad sin par en Exact
# 4. Canibalización: misma keyword en Broad + Phrase + Exact
# 5. Campañas activas con $0 spend en 30 días
# Score 0-100 de salud por cuenta
```

### 🔗 Análisis Cruzado → + Acción sugerida + Bulk output

```python
def _recomendar_accion(row, target_acos):
    if not en_str and sqp_purchase_rate > 5:
        return "🚀 AGREGAR — alta compra en mercado, no estás apareciendo"
    if en_str and not en_bulk_exact and acos_str < target_acos:
        return "✅ HARVEST — agregar como Exact Match"
    if en_str and acos_str > target_acos * 2:
        return "⬇️ BAJAR BID o negativizar"
    if impression_share < 5 and sqp_purchase_rate > 8:
        return "⚡ ESCALAR — gran oportunidad de mercado"
    return "👁️ MONITOREAR"

# Al pie: sección "📦 Campañas Sugeridas"
# Genera naming convention Capybaras listo para export bulk
```

---

## 📐 Detalle de tabs nuevas — Sección Estrategia

### 🧠 Bid Optimizer (tab nueva)
```python
# Inputs: STR cargado + Target ACoS (slider) + precio_promedio
# Fórmula:
bid_sugerido = (cvr / 100) * precio * (target_acos / 100)

# Clasificación:
# bid_actual > bid_sugerido × 1.3 → "BAJAR" (rojo)
# bid_actual < bid_sugerido × 0.7 → "SUBIR" (verde)
# entre 0.7x y 1.3x → "OK" (gris)
# clicks > 10 AND orders == 0 → "PAUSAR" (negro)

# Export bulk: solo columnas Max Bid modificadas
# → subís y Amazon actualiza todos los bids de una vez
```

### ⚔️ Funnel Builder (upgrade de Análisis Funnel)
```
Output (4 secciones):
1. Mapa del funnel actual (Auto → Broad → Phrase → Exact) por producto
2. Gaps detectados (qué falta en el funnel)
3. Campañas sugeridas con naming convention completo
4. Export bulk-ready con TODAS las entidades:
   Campaign | Ad Group | Keyword | Match Type | Bid | Status | Budget
   → Listo para subir, crea las campañas en Amazon directamente
```

### 📅 Account Pulse (tab nueva — ya diseñada con Setex)
```
Inputs: BR Daily CSV + Campaign CSV
Outputs:
1. Gráfico ventas diarias — marcado fines de semana y festivos MX/USA
2. Comparación semana a semana automática
3. Detección anomalías (caídas >30% del promedio) con causa probable
4. Semáforo BuyBox por ASIN con impacto económico estimado
5. Separación campañas nuevas vs antiguas
6. Resumen ejecutivo copiable para Slack/cliente

Paleta: E84000 (naranja) | 1F1F1F (negro) | FAFAFA (blanco roto)
Festivos MX hardcoded: (1,1) (2,3) (3,17) (5,1) (9,16) (11,2) (11,18) (12,25)
```

---

## 📐 Detalle de tabs nuevas — Sección Ejecución

### 🚀 Bulk Upload Builder (tab nueva)

Formato exacto Amazon para upload. Columnas requeridas:
```
Campaign Name | Ad Group Name | Keyword Text | Match Type | Max Bid |
Status | Campaign Daily Budget | Bidding Strategy | Targeting Type |
Start Date | Top of Search Modifier | Product Pages Modifier
```

Secciones del builder:
- **A) Nuevas campañas** — genera jerarquía completa con naming convention
- **B) Agregar keywords** — a campañas existentes del bulk cargado
- **C) Agregar negativos** — desde lista o desde STR Mining
- **D) Ajuste masivo de bids** — % de cambio sobre bulk actual

### 🤖 Automation Rules Builder (tab nueva)

Genera rules en formato Atom 11 para importar. Presets 2026:

```python
# Rule 1 — Negativización automática
IF clicks >= 5 AND orders == 0 AND spend > (precio * target_acos * 0.01):
    → Add as Negative Exact

# Rule 2 — Bid defense brand
IF impression_share < 70% AND is_brand_keyword:
    → subir bid 25%

# Rule 3 — Scale winner
IF acos <= target_acos * 0.7 AND orders >= 3 (últimos 7 días):
    → subir bid 15%

# Rule 4 — Pausa por performance
IF spend > $X AND orders == 0 AND days_active > 14:
    → Status = Paused

# Rule 5 — Reducción fines de semana (patrón Setex MX)
IF day_of_week in [Saturday, Sunday]:
    → bid multiplier -30%

Modos: Conservador (solo bajan bids) | Agresivo (sube, baja y pausa) | Custom
```

---

## 🗓️ Roadmap por sesiones

| Sesión | Qué hacemos | Tab | Resultado |
|--------|------------|-----|-----------|
| ~~**1**~~ | ~~Fix routing Weekly Report + bug SQPs duplicados~~ | ~~app.py~~ | ✅ Completado 2026-03-19 |
| ~~**2**~~ | ~~Negatives Mining en STR~~ | ~~STR~~ | ✅ Completado (detectado 2026-03-19) |
| ~~**3**~~ | ~~Harvest Engine en STR + Export bulk~~ | ~~STR~~ | ✅ Completado (detectado 2026-03-19) |
| ~~**4**~~ | ~~Market Share + Gap Analysis en SQP~~ | ~~SQP~~ | ✅ Completado (detectado 2026-03-19) |
| ~~**5**~~ | ~~Campaign Analyzer en Bulk Campañas~~ | ~~Bulk~~ | ✅ Completado 2026-03-21 |
| ~~**6**~~ | ~~Plan de Acción + fix marca en Análisis Cruzado~~ | ~~Cruzado~~ | ✅ Completado 2026-03-21 |
| ~~**7**~~ | ~~Bid Optimizer (módulo nuevo)~~ | ~~Automatización~~ | ✅ Completado 2026-03-21 |
| ~~**8**~~ | ~~Campaign Builder (módulo nuevo)~~ | ~~Automatización~~ | ✅ Completado 2026-03-21 |
| ~~**9**~~ | ~~Agency OS — rediseño inicio + sidebar oscuro~~ | ~~app.py + inicio.py~~ | ✅ Completado 2026-03-21 |
| ~~**10**~~ | ~~Atom11 Rules Builder~~ | ~~Nuevo~~ | ✅ Completado 2026-03-23 — módulo multi-marca, 3 tabs, 274 rules por objetivo |
| ~~**11**~~ | ~~Conectar 8 módulos + mejoras visuales~~ | ~~app.py + 8 módulos~~ | ✅ Completado 2026-03-27 |
| **12** | Testing completo 22 módulos con datos reales | Testing | Pendiente |
| **13** | SOP completo de todas las tabs | Docs | SOP Capybaras Agency OS |

---

## 🎯 Principios técnicos — Todo el roadmap

1. **Cada feature es un sub-tab dentro del módulo existente** — no funciones sueltas
2. **Siempre dos formatos de output:** tabla en UI + descarga bulk Excel
3. **Export bulk siempre en formato exacto Amazon** (ver columnas en Bulk Upload Builder)
4. **Target ACoS es un input global del sidebar** — como Parent-Child map, aplica a todas las tabs
5. **Modularizar todo** — cada feature nueva en `modules/pages/` o helper en `core/`
6. **Cache pesados:** agregar `@st.cache_data` a `_parse_atom11`, `_parse_merchanspring_pdf`, `_parse_merchanspring`

---

## 📊 SOP Capybaras — Thresholds correctos 2026

> Referencia para implementación en el código. SOP completo en `Capybaras_Launch_SOP_v2026.docx`

### Negativización (thresholds correctos)
```python
# Regla 2: threshold por CVR (el más importante)
clicks_neg_threshold = max(10, round((1 / cvr_producto) * 2))
# CVR 10% → 20 | CVR 5% → 40 | CVR 3% → 60 | mínimo absoluto: 10

# Regla 3: threshold por gasto
spend_neg_threshold = precio_producto * 0.50  # 50% del precio

# Regla 5: CTR bajo
imp_ctr_threshold = 2500   # impresiones mínimas (NO 500)
ctr_min_threshold = 0.18   # % CTR mínimo esperado (NO 0.1%)

# NUNCA negar dentro de campaña Exact Match propia
# NUNCA negar KW que está en Exact activo aunque tenga ACoS alto en Broad/Phrase
```

### Harvesting (se mantiene del SOP original + nuevo 2026)
```python
harvest_exact_main = orders >= 3 and acos <= 25.0      # regla Capybaras — se mantiene
harvest_exact_cvr  = cvr >= 10.0 and clicks >= 15       # por CVR alto
harvest_exact_vol  = orders >= 5                         # por volumen, ignora ACoS
```

### Placement Modifiers (nuevo 2026)
```
Exact Ranking:   ToS +50% | PDP  0%
Exact Harvest:   ToS +25% | PDP  0%
Phrase:          ToS +10% | PDP  0%
Broad/Auto:      ToS   0% | PDP  0%
PAT Competitor:  ToS   0% | PDP +50%
```

---

## 🧠 Contexto estratégico Amazon 2026

- **Rufus AI** procesa queries conversacionales — listings y keywords deben responder preguntas, no solo matchear términos
- **CPC promedio > $1.00** en 2025 — gestión manual de bids a escala es inviable
- **Learning periods** — no cambiar bids más de 1 vez/semana (resetea el algoritmo)
- **ASIN targeting** supera a keyword-only en muchas categorías para adquisición
- **SBV (Sponsored Brand Video)** es obligatorio en 2026, no opcional — mayor CTR del ecosistema
- **60%+ de búsquedas en Amazon** están personalizadas — relevancia de persona > relevancia de keyword
- **Métricas senior:** TACoS a 90 días > ACoS inmediato. Ranking velocity > eficiencia a corto plazo

---

## 🛡️ MerchanSpring — Estado (2026-03-17)

### ✅ Hecho
- Parser PDF defensivo (try/except en cada sección)
- 5 tabs UI: Summary | Advertising | Inventory & Health | WoW Comparison | Details
- Tab Details: Traffic by Parent/Child, Cancellations, Sales by Category/Country/Brand, BSR, BuyBox, Shipping, Reviews

### 🔜 Pendiente
- [ ] WoW Completo PDF — mejorar hoja con contribution margin
- [ ] Fix XLSX parser — IndexError con elementos distintos
- [ ] Soporte NorseTradesman — pendiente decisión

---

## 👥 Clientes activos (2026-03-18)

### 🛏️ Love To Dream MX
- **Categoría:** Sacos de dormir bebé (Swaddle UP) — Amazon México
- **KPIs mar 2026:** Sales +43.9%, ACoS 22.7%, TACoS 17.4%
- **Alarma activa:** SBV B09MG1PM6L — ACoS 148% (revisar/pausar)
- **BuyBox issues:** B005ULUZIQ (75.9%), B0F8P9GBZN (82.8%)
- **Doc:** `LTD.md`

### 👕 M&B (Mott & Bow) MX
- **Categoría:** Ropa (T-shirts, 159 ASINs) — Amazon México
- **KPIs mar 2026:** Sales +58.3%, ACoS 8.6%, TACoS 5.4%
- **BuyBox issues:** 21 ASINs — 3 críticos < 80%, patrón en packs de 3
- **Nota técnica:** BR diario sin columna BuyBox estándar (usa B2B variant)
- **Doc:** `MB.md`

### 🏢 Setex Technologies MX
- **Categoría:** Accesorios anteojos — Amazon México
- **AM:** Tatiana Velasquez
- **Campañas:** 43 heredadas de Perpetua + 53 nuevas (lanzadas 13/03/2026)
- **Insights:** Keywords EN = 0 impresiones en MX | fines de semana caen ~60%
- **Pendiente:** Revisión general 27/03 al cumplir 2 semanas
- **Doc:** `setex.md`

---

## 📅 Account Pulse — Especificaciones (ya diseñado, Setex 17/03/2026)

### Output Excel (4 hojas)
- `Resumen Ejecutivo` — portada naranja con capybara mascota, KPIs, diagnóstico, mensaje Slack
- `Ventas Diarias` — 43+ días con color tipo (laboral/finde/festivo MX)
- `BuyBox & ASINs` — ordenado por impacto económico (ventas perdidas estimadas)
- `Campañas` — separadas NUEVA (verde) vs HEREDADA (azul), ACoS semáforo

### Paleta
```
E84000 (naranja primario) | FF6B00 (naranja secundario) | FFF3E0 (naranja pálido)
1F1F1F (negro) | FAFAFA (blanco roto) | 1B6B2F/E8F5E9 (verde) | B71C1C/FFEBEE (rojo)
```

### Festivos MX hardcoded
```python
_FESTIVOS_MX = {
    (1,1):"Año Nuevo", (2,3):"Constitución", (3,17):"Juárez",
    (5,1):"Día del Trabajo", (9,16):"Independencia",
    (11,2):"Día de Muertos", (11,18):"Revolución", (12,25):"Navidad",
}
```

---

## Reglas de trabajo — Flujo de codigo

Claude (chat) nunca da codigo para copiar/pegar manualmente.
Siempre genera prompts para Claude Code en VS Code que ejecute los cambios.

### Flujo para cambios de codigo
1. Claude (chat) disena la logica y redacta el prompt
2. Lenin copia en Claude Code (VS Code)
3. Claude Code ejecuta con autonomia absoluta
4. Claude Code confirma que lineas modifico

### Post-implementación — siempre después de cada prompt de código

**Checklist de testing:**
- Testear el módulo nuevo con archivo real
- Testear que módulos adyacentes no se rompieron
- Verificar que los filtros/inputs cambian el output correctamente
- Verificar que los botones de descarga funcionan

**Git al terminar siempre:**
```bash
git add .
git commit -m "feat/fix/improve: [descripción]"
git push
```

No confirmar como terminado hasta que py_compile pase Y el test manual sea exitoso.

---

### 🔄 Cierre de sesión — Checklist completo

**Al FINAL de cada sesión de trabajo, en este orden:**

**1. Git commit:**
```bash
git add .
git commit -m "feat/fix/improve: [descripción de lo que hicimos]"
git push
```

**2. Actualizar .md de clientes** con pendientes y acciones ejecutadas
(DERMAGLOS.md, LTD.md, MB.md, setex.md según corresponda)

**3. Actualizar CLAUDE.md** con módulos nuevos, fixes y estado actual

**4. Subir archivos actualizados al proyecto de Claude**
Ir a claude.ai → proyecto → panel derecho → Archivos → reemplazar:
- `app.py`
- `CLAUDE.md`
- `DERMAGLOS.md` (o .md del cliente trabajado)
- Cualquier módulo nuevo o modificado en `modules/pages/`

Sin este paso, la próxima sesión arranca con contexto desactualizado.

---

### Flujo para actualizar archivos .md de clientes (DERMAGLOS, LTD, MB, setex, etc.)
1. Claude (chat) genera el contenido nuevo del archivo
2. Claude (chat) redacta UN prompt para Claude Code con el contenido completo
3. Lenin pega el prompt en Claude Code (10 segundos)
4. Claude Code escribe el archivo directamente en C:\proyectos\ppc-manager\notes\
5. Lenin hace git add + commit + push

NUNCA mas usar scripts update_X.py ni copiar manualmente archivos.
NUNCA descargar archivos intermedios para actualizar .md de clientes.
El prompt para Claude Code siempre incluye la ruta exacta y el contenido completo.

### Formato del prompt para actualizar un .md de cliente

Siempre usar este formato exacto cuando Claude Code tenga que escribir un archivo .md:

Crear o reemplazar el archivo C:\proyectos\ppc-manager\notes\[NombreCliente].md
con el siguiente contenido exacto (reemplazar todo el contenido existente):

---INICIO DEL CONTENIDO---
[contenido completo del archivo]
---FIN DEL CONTENIDO---

No tocar ningun otro archivo. Confirmar que el archivo fue escrito
y decir cuantas lineas tiene.

### Formato de prompt para cambios de codigo
- Incluir ruta exacta del archivo
- Cambios especificos sin preguntas
- Confirmar al terminar
- Nunca pausar por dudas — tomar la decision mas razonable

---

## 🔚 Git — Recordatorio de flujo

**Al INICIO de cada sesión:**
```bash
git add .
git commit -m "checkpoint: antes de [tarea de hoy]"
```

**Al FINAL de cada sesión:**
```bash
git add .
git commit -m "feat/fix/improve: [descripción de lo que hicimos]"
git push
```

**Si algo se rompe:**
```bash
git checkout .   # descarta cambios, vuelve al último commit
git diff app.py  # ver qué cambió antes de deshacer
```

---

## Dermaglos — Plan de ataque (2026-03-19)

### Contexto
Dos ASINs prioritarios para reestructurar completo:
- B0CYLMJJJC — Moisturizing Cream 1.76oz | $9.99 | 149 units | BSR 85k
- B0CYLM4L23 — Body Lotion 13.52oz | $18.89 | 65 units | BSR 122k

Analisis completo en: C:\proyectos\ppc-manager\notes\DERMAGLOS.md

### Fase 1 — Listing (en curso)
Optimizar titulos, bullets y backend keywords basado en analisis Rufus.
Diferencial clave: Vitamin A + Allantoin para uso nocturno y zonas secas.
No competir en el territorio de CeraVe/Vanicream (ceramidas).

### Fase 2 — Estructura de campanas
Lenin pasa la estructura deseada.
Claude genera bulk listo para subir al Campaign Manager.
Naming convention Capybaras standard.

### Fase 3 — Automatizacion
Rules para Atom 11 en formato bulk.
Listo para importar sin edicion manual.

### Flujo de trabajo
1. HOY: Titulos + bullets + backend keywords B0CYLMJJJC y B0CYLM4L23
2. LUEGO: Lenin pasa estructura campanas → Claude genera bulk Campaign Manager
3. AL FINAL: Claude genera rules Atom 11 en formato bulk para importar

---

## BUG ACTIVO — API key no carga (2026-03-19)

Sintoma: "API key no configurada" aunque este seteada en Windows y en .env
Lo intentado: load_dotenv path absoluto, SetEnvironmentVariable User, override=False, leer .env manualmente
Hipotesis: Streamlit corre en subproceso que no hereda variables de entorno del usuario Windows
Proximo paso: cerrar VS Code completamente, reabrir, y verificar:
python -c "import os; print(os.environ.get('ANTHROPIC_API_KEY', 'NO ENCONTRADA')[:20])"
Si dice NO ENCONTRADA — cerrar y reabrir VS Code resuelve.

## Nuevo cliente activo — Dermaglos USA (2026-03-19)

- Categoria: Skincare (Body Cream, Body Lotion, Facial Cleanser, Serums) — Amazon USA
- ACoS cuenta: 76.1% — CVR: 11.5% (excelente)
- Nicho ganador: vitamin a cream (SQP PS 16.1%)
- Audiencia: hispanohablante USA
- Hero ASINs: B0CYLMJJJC (Cream $9.99) | B0CYLM4L23 (Lotion $18.89)
- Fase 1 COMPLETADA: listing optimizado con STR + SQP + Rufus
- PDF entregado: Dermaglos_Listing_Optimization_2026.pdf
- Fase 2 COMPLETADA: campañas reestructuradas bulk Campaign Manager
- Fase 3 COMPLETADA: rules Atom 11 formato bulk
- Doc: notes/DERMAGLOS.md

## Claude API integrada (2026-03-19)

Modulo: core/ai_analyze.py
Modelo: claude-sonnet-4-6
Funciones: _claude_analyze, _build_str_prompt, _build_sqp_prompt
Integrado en: STR tab 4 + SQP tab 4 + Weekly Client Report
Costo: menos de $0.01 por analisis

---

## 🚀 Plan de implementación — Módulos nuevos 2026-03-20

### Contexto
Todo lo que se hizo manualmente el 20/03/2026 con Dermaglos (análisis STR+SQP+Bulk,
generación de bulks de campañas, diseño de Atom11 rules) se puede meter en el software.
Flujo de trabajo: Lenin + Claude (chat) diseñan la lógica → Claude Code implementa.

---

### SESIÓN 1 — STR: tab Negativizar (threshold por precio)
**Esfuerzo:** Bajo | **Impacto:** Alto — se usa cada semana

Tab nueva dentro del módulo Search Term Report:
```python
# Lógica central
def _calcular_threshold(precio, cvr):
    if precio < 12:   return 18, 15.00   # TIER LOW
    elif precio <= 22: return 22, 22.00  # TIER MID
    else:              return 28, 30.00  # TIER HIGH
    # Fórmula: clicks = round(1/CVR) × 2

# UI
# Input: precio del producto → auto-asigna tier y threshold
# Muestra: tabla de términos candidatos a negar (clicks > threshold, orders = 0)
# Checkbox: selección manual de cuáles negar
# Export: negative keywords en formato bulk Amazon
```

---

### SESIÓN 2 — Campaign Analyzer (diagnóstico semáforo)
**Esfuerzo:** Medio | **Impacto:** Alto — evita el problema de IDs al pausar

Upgrade del módulo Bulk Campañas. Input: Campaign CSV de Campaign Manager.

Diagnóstico automático:
- 🔴 PAUSAR — spend > threshold por precio con 0 órdenes
- 🟡 REVISAR — ACoS > target × 2
- ✅ ESCALAR — ACoS < target × 0.5 con órdenes confirmadas
- ⚫ FANTASMAS — campañas con 0 impresiones activas
- ⚠️ MAL PORTFOLIO — campañas en portfolio equivocado (detecta por ASIN en nombre)

Output:
- Tabla semáforo con diagnóstico por campaña
- Métrica "Spend recuperable: $X" si pausás las rojas
- Nota: las pausas se hacen manualmente en Campaign Manager (bulk update requiere Campaign ID numérico real)

---

### SESIÓN 3 — Análisis Cruzado → + Acción sugerida
**Esfuerzo:** Medio | **Impacto:** Alto — automatiza el análisis STR+SQP+Bulk

Ya estaba en el roadmap. Agregar al módulo existente:
```python
def _recomendar_accion(row, target_acos):
    # Brand Defensive → convierte bien en STR, es brand term
    # Vitamin A Core → PS% > 10% en SQP, cluster ganador
    # Spanish → query en español detectado en SQP
    # PAT → competitor ASIN identificado
    # PAUSAR → ACoS > target × 2 AND clicks > threshold_tier
    # ESCALAR → ACoS < target × 0.5 AND orders >= 2
```

Output adicional: tabla de acciones sugeridas + export bulk con negativos listos

---

### SESIÓN 4 — Campaign Builder (el corazón)
**Esfuerzo:** Alto | **Impacto:** Muy alto — automatiza todo el trabajo del 20/03

Módulo nuevo en sección EJECUCIÓN.

Inputs:
- STR (.xlsx)
- SQP (.csv)
- Bulk actual (.csv) — detecta qué ya existe para no duplicar
- Target ACoS (slider)
- Precio del producto + ASIN + SKU
- Tabla editable de competidores (ASIN, precio, revenue)

Proceso automático:
- Detecta clusters de keywords por intención (Brand / Vitamin A / Spanish / Discovery / PAT)
- Calcula bid = CVR × precio × target_ACoS
- Agrupa en campañas de MAX 5 keywords (regla Capybaras 2026)
- Genera cross-negatives automáticamente
- Detecta campañas existentes para no duplicar
- Naming convention: `[Producto] - [ASIN] - SP - KW - [MATCH] - [Descriptor]`

Output:
- Preview de campañas en UI (tabla editable antes de exportar)
- Bulk xlsx en formato exacto Amazon → listo para subir directo a Campaign Manager
- Nota: las operaciones UPDATE (pausar existentes) requieren Campaign ID numérico — hacer manualmente

---

### SESIÓN 5 — Atom11 Rules Builder
**Esfuerzo:** Alto | **Impacto:** Alto — aplicable a todas las marcas

Módulo nuevo en sección EJECUCIÓN.

Tab 1 — Configuración:
- Prefijo naming (DG, MB, STX...)
- Target ACoS cuenta
- Tabla ASINs con precio → auto-asigna tier (LOW/MID/HIGH)

Tab 2 — Preview rules:
- Muestra las 44 rules con nombre, condición, acción
- Editable — ajustar thresholds por marca
- Color coding: verde=increase / rojo=decrease / gris=stop

Tab 3 — Export:
- CSV importable a Atom11
- .md documentación para el repo

Sistema de tiers (hardcoded, editable por usuario):
- TIER LOW (<$12): clicks_neg=18, spend_stop=$15
- TIER MID ($12-$22): clicks_neg=22, spend_stop=$22
- TIER HIGH (>$22): clicks_neg=28, spend_stop=$30

---

### Nueva arquitectura de navegación
SECCIÓN ANÁLISIS (existente)
📊 Search Term Report       ← + tab Negativizar (Sesión 1)
🔍 Search Query Performance ← sin cambios
📁 Bulk Campañas            ← → Campaign Analyzer (Sesión 2)
💰 Business Report          ← sin cambios
SECCIÓN CRUCE (existente)
🔗 Análisis Cruzado         ← + Acción sugerida (Sesión 3)
📈 Tendencia Multi-Semana   ← sin cambios
SECCIÓN EJECUCIÓN (nueva)
🚀 Campaign Builder         ← Sesión 4
🤖 Atom11 Rules Builder     ← Sesión 5
SECCIÓN REPORTES (existente — sin cambios)
🔻 Análisis de Funnel
🔬 Reportes Atom 11
🛡️ Reportes MerchanSpring
📊 Weekly Client Report

---

### Regla de trabajo para estas sesiones
1. Lenin + Claude (chat) diseñan la lógica y validan contra datos reales
2. Claude (chat) genera el prompt detallado para Claude Code
3. Claude Code implementa el módulo completo
4. Lenin testea con archivos reales y reporta
Nunca implementar sin datos reales de validación primero.

---

## 📅 Sesión 2026-03-21 — Lo que hicimos

### Módulos nuevos
- **Campaign Analyzer** — tab nueva en Bulk Campañas. Input: Campaign CSV. Diagnóstico semáforo (PAUSAR/REVISAR/ESCALAR/FANTASMA/OK). Spend recuperable. Thresholds configurables por el AM.
- **Plan de Acción** — tab nueva en Análisis Cruzado. Clasifica keywords en: ESCALAR / AGREGAR / DEFENDER / NO ATACAR / BAJAR BID / MONITOREAR. Fix detección marca manual cuando SQP no la detecta. Export bulk accionables.
- **Bid Optimizer** — módulo nuevo en Automatización. Input: STR + Inventory Report (.txt). CVR de ads reales. Precio de lista exacto desde Inventory Report. Bid = CVR × precio × target ACoS. Ajuste % editable por ASIN.
- **Campaign Builder** — módulo nuevo en Automatización. Input: Plan de Acción bulk. Clustering automático: Brand / Vitamin A / Spanish / Discovery / PAT. Spanish prioridad sobre Brand (mercado hispano USA). Filtro confianza: LANZAR AHORA vs PROBAR. Max 5 KWs por campaña. Naming convention Capybaras. Export bulk formato exacto Amazon.

### UI/UX
- Sidebar rediseñado: fondo oscuro #1A1A1A, labels naranja #E84000, 180px de ancho
- Página Inicio rediseñada: 9 áreas Agency OS (2 activas + 7 próximamente), ownership por área, flujo de trabajo en card PPC
- Sidebar reordenado por flujo de trabajo: Analizar → Cruzar → Diagnosticar → Calcular → Ejecutar
- Secciones renombradas: PPC Manager + Account Manager

### Fixes
- fix: input manual de marca cuando SQP no detecta automáticamente
- fix: Campaign Builder — Spanish prioridad sobre Brand para mercado hispano
- fix: Bid Optimizer extrae ASIN del Campaign Name cuando no hay columna Advertised ASIN
- fix: Bid Optimizer cruza STR + Inventory Report para precio de lista exacto

### Archivos modificados hoy
- `app.py` — sidebar oscuro + reorden + nuevos módulos
- `modules/pages/inicio.py` — rediseño completo Agency OS
- `modules/pages/bulk_campanas.py` — + Campaign Analyzer tab
- `modules/pages/analisis_cruzado.py` — + Plan de Acción tab + fix marca
- `modules/pages/bid_optimizer.py` — NUEVO
- `modules/pages/campaign_builder.py` — NUEVO

---

## 📅 Sesión 2026-03-23 — Lo que hicimos

### Módulos nuevos
- **Atom11 Rules Builder** — módulo nuevo en Automatización (Sesión 10 del roadmap). 3 sub-tabs:
  - Tab 1: Configuración — prefijo marca, brand terms, target ACoS cuenta, tabla ASINs editable → auto-calcula tiers y targets por objetivo
  - Tab 2: Campaign Groups — sube Campaign CSV → clasifica campañas automáticamente en 11 grupos por objetivo (DISCOVERY/RANKING/CONQUEST/DEFENSIVE/PROFIT/REMARKETING/SCAVENGER) → export Excel multi-sheet para Atom11
  - Tab 3: Rules Generator — genera 274 rules con thresholds dinámicos por objetivo → preview por expander → export Excel
  - **Multi-marca:** todo configurable — prefijo, brand terms, ASINs, targets. No hardcoded a Dermaglos.

### Framework de clasificación de campañas (best practices 2026)
- **DISCOVERY** (Target: 120% cuenta) = AUTO + BROAD → comprando data
- **RANKING** (Target: 100% cuenta) = KWs Exact/Phrase → posicionando
- **CONQUEST** (Target: ~86% cuenta) = PAT / ASIN / Category → robando tráfico
- **DEFENSIVE** (Target: ~71% cuenta) = Brand KWs → protegiendo marca
- **PROFIT** (Target: 50% cuenta) = Harvested winners → eficiencia
- **REMARKETING** (Target: ~71% cuenta) = SD retargeting → recuperando visitantes
- **SCAVENGER** = Catch-all, sin rules automáticas

### Atom11 Rules — Diseño v2026.1
- 274 rules totales (6 objetivos × ~45 rules cada uno)
- Bid Optimiser: 7 niveles × 3 tiers × 6 objetivos = 126 rules
- Placement Optimiser: 6 niveles × 3 tiers × 6 objetivos = 108 rules
- Negate: 3 tiers × 6 objetivos = 18 rules
- Hard Stop: 3 tiers × 6 objetivos = 18 rules
- Harvest: 2 rules × 2 objetivos (solo DISCOVERY + RANKING) = 4 rules
- Thresholds calculados dinámicamente como % del target ACoS del objetivo
- Tiers por precio: LOW (<$12), MID ($12-22), HIGH (>$22)

### Trabajo con cliente Dermaglos
- Clasificación de 123 campañas en 11 grupos por objetivo
- 274 rules diseñadas alineadas al 70% target cuenta (DEFENSIVE en 50%)
- 2 Excel generados: DG_Atom11_Campaign_Groups.xlsx + DG_Atom11_Rules_Complete_v2026.xlsx
- Checklist de migración Atom11 en 3 fases (hoy/semana 1/semana 2)
- DERMAGLOS.md actualizado con toda la info nueva

### Organización de notas
- Nueva estructura: notes/brands/{marca}/ para separar notas por cliente
- Movidos: DERMAGLOS.md → brands/dermaglos/, LTD.md → brands/ltd/, MB.md → brands/mb/, setex.md → brands/setex/

### Archivos creados/modificados
- `modules/pages/atom11_rules_builder.py` — NUEVO (módulo completo)
- `app.py` — + import + sidebar button + routing para Atom11 Rules Builder
- `notes/brands/dermaglos/DERMAGLOS.md` — actualizado con clasificación campañas + rules v2026.1
- `notes/brands/dermaglos/Atom11_Rules.md` — rules originales v1
- `notes/brands/dermaglos/2026-03-23-checklist-migracion-atom11.md` — checklist migración

### ⚠️ Pendiente de esta sesión
- [ ] Testing completo del módulo con Campaign CSV real
- [ ] Actualizar Atom11.md con rules v2026.1 completas
- [ ] Subir archivos actualizados al proyecto de Claude

---

## 🤖 Agentes Claude Code (v2.0 — 2026-03-27)

9 agentes en `.claude/agents/`, optimizados para escalar el Agency OS.

| Agente | Modelo | Color | Propósito |
|--------|--------|-------|-----------|
| ppc-module-builder | Sonnet | 🟠 orange | Crear/modificar módulos en modules/pages/, tabs, kpi_cards, headers, empty states |
| code-reviewer | Sonnet | 🔴 red | Review de código: 8 checks incluyendo PPC logic, return-in-tabs, keys únicas |
| excel-export-builder | Sonnet | 🟠 orange | Funciones _build_*_excel() con branding Capybaras, semáforo ACoS, portada |
| atom11-specialist | Opus | 🟢 green | Rules v2026.2 AGRESIVO, clasificación campañas, thresholds por tier/objetivo |
| client-notes-updater | Haiku | 🟣 purple | Actualizar .md de clientes en notes/brands/, cierre de sesión |
| ui-designer | Sonnet | 🔵 blue | Design system Capybaras, componentes visuales, layouts para nuevas secciones |
| sop-writer | Haiku | 🟢 green | Auto-documentación en PPC-SOP-Manager.md y CLAUDE.md |
| testing-agent | Sonnet | 🟡 yellow | QA: compilación, imports, smoke test, checklist 8 puntos, report patterns |
| client-onboarding | Sonnet | 🟣 purple | Setup marca nueva: notas, ASINs, tiers, naming convention, target cascade |

### Cuándo usar cada uno
- **Crear/modificar módulo** → ppc-module-builder
- **Review después de cambios** → code-reviewer
- **Export Excel nuevo** → excel-export-builder
- **Rules Atom11** → atom11-specialist
- **Actualizar notas cliente** → client-notes-updater
- **Diseño UI nueva sección** → ui-designer
- **Documentar en SOP/CLAUDE.md** → sop-writer
- **Testear módulos** → testing-agent
- **Onboardear marca nueva** → client-onboarding

### Cambios v2.0 vs v1.0
- code-reviewer: Haiku → Sonnet (detecta bugs de lógica PPC)
- ppc-module-builder: +kpi_card, +empty states, +headers v2, +bug prevention
- Template de memoria reducido ~70% en todos los agentes (contenido > boilerplate)
- 4 agentes nuevos: ui-designer, sop-writer, testing-agent, client-onboarding
- Todos los MEMORY.md empiezan vacíos — se llenan con uso

---

## 📂 Nueva estructura de notas (2026-03-23)

```
notes/
├── knowledge/           ← inteligencia general (tendencias, SOPs, AI)
├── brands/
│   ├── dermaglos/       ← DERMAGLOS.md + Atom11_Rules.md + checklists
│   ├── ltd/             ← LTD.md
│   ├── mb/              ← MB.md
│   └── setex/           ← setex.md
├── Biblioteca.md        ← SOP biblioteca de conocimiento
├── INTELLIGENCE-INDEX.md
└── Slack #learnings-implementations.md
```

---

## 🔑 Cambiar cuenta de Claude Code

### Desde terminal normal (fuera de Claude Code)
```bash
claude auth logout
claude login
```

### Desde dentro de Claude Code
```
/login
```

Seleccionar opción **1 — Claude account with subscription** → browser → ingresar con la cuenta deseada.

### Cuentas
| Cuenta | Uso |
|--------|-----|
| lenin.acosta@capybaras.agency | Agencia — PPC Manager, clientes |
| cuenta personal | Proyectos personales |

---

## 📅 Sesión 2026-03-23b — Atom11 Rules v2026.2 AGRESIVO

### Cambios de thresholds
- Multiplicadores DEC más agresivos: SOFT 1.14× | RISK 1.36× | CTRL 1.57× | HARD 1.86× (PAUSE TARGET)
- Antes: 1.3× | 1.5× | 1.8× | 2.2× (bid -40%)
- DEC HARD ahora pausa el keyword en vez de bajar bid — corta el sangrado

### Fase 1 COMPLETA — 20 rules activas en Atom11
- 6 RANKING SP Bid (target 70%, 41 camps) — creadas manual
- 6 DEFENSIVE SP Bid (target 50%, 23 camps) — creadas Cowork
- 4 Negate (RANKING/DEFENSIVE/DISCOVERY/CONQUEST, clicks>21, orders=0) — Cowork
- 4 Hard-Stop (spend>$22, orders=0, clicks>21, decrease 50%) — Cowork
- 24 rules viejas pausadas (14 RANKING + 10 DEFENSIVE)
- Todas: TIER MID, Wait 3d, Tue+Fri 06:00

### B0CYLDSQ5L Body Cream — reducción fuerte ejecutada
- 15 campañas pausadas (DISCOVERY + RANKING genéricos + CONQUEST)
- 5 campañas mantenidas con bid $0.50 (Brand Defensive + Core Hero)

### Claude in Chrome + Cowork
- Automatización de Atom11 via Cowork funciona — creó 14 rules automáticamente
- Flujo: Create Custom Rule → llenar form → JS para seleccionar campañas → Create Rule
- Clonar rules funciona para mismo objetivo (cambiar solo nombre + condiciones)
- Limitación: campañas Manual vs Automatic targeting se seleccionan por separado

### Archivos generados
- DG_Atom11_CheatSheet_v2_AGRESIVO.xlsx — 52 rules, 3 fases
- DG_Atom11_Rules_Complete_v2026_2_AGRESIVO.xlsx — 256 rules referencia
- TASKS.md — tareas del día para Cowork

### Pendiente Fase 2 (16 rules) — ver TASKS.md
- 6 DISCOVERY SP Bid (target 84%)
- 6 CONQUEST SP Bid (target 60%)
- 4 Harvest (DISCOVERY + RANKING)

# INSTRUCCIONES PARA CLAUDE CODE
# Agregar esta sección al final del CLAUDE.md existente en C:\proyectos\ppc-manager\CLAUDE.md
# (justo después de la sección "Sesión 2026-03-23 — Lo que hicimos" existente)
# NO borrar nada existente — solo AGREGAR al final.

---

## 📅 Sesión 2026-03-23b — Lo que hicimos (continuación tarde)

### Atom11 Rules — Migración a v2026.2 AGRESIVO
- **Thresholds recalculados** — multiplicadores DEC más agresivos para cuenta sangrando a 76% ACoS:
  - DEC SOFT: 1.30× → **1.14×** del target
  - DEC RISK: 1.50× → **1.36×** del target
  - DEC CTRL: 1.80× → **1.57×** del target
  - DEC HARD: 2.20× (bid -40%) → **1.86× (PAUSE TARGET)** ← cambio más importante
- **6 rules RANKING SP creadas en Atom11** — Bid Optimiser MID, 41 campañas, thresholds v2026.2:
  - INC AGG <35% (+15%) | INC SOFT 35-60% (+8%) | FLAT 60-70% | DEC SOFT >80% (-10%) | DEC RISK >95% (-15%) | DEC CTRL >110% (-25%) | DEC HARD >130% (PAUSE TARGET)
- **Rules viejas pausadas:**
  - 14 rules RANKING SP (Bid + Placement, thresholds v1 desactualizados, 23 campañas → ahora son 41)
  - 10 rules DEFENSIVE SP (Bid + Placement, thresholds v1, 13 campañas → ahora son 23)
- **2 Excel regenerados** con thresholds agresivos:
  - `DG_Atom11_CheatSheet_v2_AGRESIVO.xlsx` — 52 rules en 3 fases, listo para copiar en Atom11
  - `DG_Atom11_Rules_Complete_v2026_2_AGRESIVO.xlsx` — 256 rules referencia completa (3 tiers × 6 objetivos)

### Thresholds v2026.2 por objetivo (todos PAUSE TARGET en DEC HARD)
| Objetivo | Target | INC AGG < | INC SOFT | Flat Zone | DEC SOFT > | DEC RISK > | DEC CTRL > | DEC HARD > (PAUSE) |
|----------|--------|-----------|----------|-----------|------------|------------|------------|-------------------|
| RANKING | 70% | 35% | 35-60% | 60-70% | 80% | 95% | 110% | 130% |
| DEFENSIVE | 50% | 25% | 25-42% | 42-50% | 57% | 68% | 78% | 93% |
| DISCOVERY | 84% | 42% | 42-71% | 71-84% | 96% | 114% | 132% | 156% |
| CONQUEST | 60% | 30% | 30-51% | 51-60% | 68% | 82% | 94% | 112% |
| PROFIT | 35% | 18% | 18-30% | 30-35% | 40% | 48% | 55% | 65% |
| REMARKETING | 50% | 25% | 25-42% | 42-50% | 57% | 68% | 78% | 93% |

### Cliente Dermaglos — Acciones ejecutadas
- **B0CYLDSQ5L Body Cream $13.49** — cliente pidió "reducción fuerte de ads":
  - 15 campañas identificadas para PAUSAR (DISCOVERY + RANKING genéricos + CONQUEST)
  - 5 campañas para MANTENER con bids bajos $0.50 (Brand Defensive + Core Hero)
  - 3 campañas para REVISAR (PAT related + Phrase Core + KWS Validation)
  - Resultado estimado: cortar ~70-80% del spend de Body Cream
- **Rules existentes en Atom11 auditadas:** 51 rules totales (Feb 2026), 9 problemas detectados:
  1. No segmentadas por tier
  2. Thresholds desactualizados
  3. DEFENSIVE sin INC rules
  4. Campañas faltantes (23→41 RANKING, 13→23 DEFENSIVE)
  5. DISCOVERY/CONQUEST/PROFIT sin rules (0 de 36 campañas)
  6. Negate con threshold fijo (25) en vez de tiers
  7. Harvest PAUSED
  8. Anti-Drain genérica
  9. SB rules custom (mantener)

### Claude in Chrome — Intentado automatización Atom11
- **Conectado exitosamente** a Chrome de trabajo (perfil "Lenin Capybaras")
- **Navegó a Atom11** — puede ver rules, tomar screenshots, leer DOM
- **Problemas encontrados:**
  - Kebab menu (⋮) fuera del viewport visible (x=1785, viewport=1713)
  - Menú usa group-hover CSS, difícil de disparar programáticamente
  - Google Sheets interacción compleja para copiar campañas
  - Cada rule tiene ~15 interacciones (dropdowns, inputs, selects, file upload)
- **Conclusión:** automatización parcial posible pero no eficiente para esta sesión
- **Alternativa propuesta:** Cowork (Claude Desktop) con proyecto dedicado

### Decisión: Migrar flujo de automatización a Cowork
- Crear proyecto "Atom11 Automation" en Claude Desktop / Cowork
- Archivos de contexto: CLAUDE.md + Atom11_Rules.md + CheatSheet + Campaign Groups
- Tareas: crear rules automáticamente en Atom11 via Claude in Chrome

### Estado actual Atom11 Dermaglos (al cerrar sesión)
| Grupo | Rules nuevas v2026.2 | Rules viejas pausadas | Pendiente |
|-------|---------------------|----------------------|-----------|
| RANKING SP | 6 Bid ✅ | 14 (Bid + Placement) | Placement, Negate, HardStop |
| DEFENSIVE SP | 0 | 10 (Bid + Placement) | 6 Bid + Negate + HardStop |
| DISCOVERY SP | 0 | 0 | 6 Bid + Negate + HardStop + Harvest |
| CONQUEST SP | 0 | 0 | 6 Bid + Negate + HardStop |
| PROFIT SP | 0 | 0 | 6 Bid + Negate + HardStop |
| REMARKETING SD | 0 | 0 (activas viejas) | 6 Bid + Negate + HardStop |
| SB | — | 0 (activas viejas) | Mantener separadas |
| SD DEFENSIVE | — | 0 (activas viejas) | Mantener separadas |

### Archivos generados hoy
- `DG_Atom11_CheatSheet_v2_AGRESIVO.xlsx` — 52 rules, 3 fases, TIER MID only
- `DG_Atom11_Rules_Complete_v2026_2_AGRESIVO.xlsx` — 256 rules referencia completa
- (anteriores de la mañana: DG_Atom11_Campaign_Groups.xlsx + DG_Atom11_Rules_Complete_v2026.xlsx)

### ⚠️ Pendiente próxima sesión
- [ ] Crear 6 rules DEFENSIVE SP en Atom11 (cheat sheet #7-#12)
- [ ] Crear 8 rules Negate + HardStop en Atom11 (cheat sheet #13-#20)
- [ ] Crear 12 rules DISCOVERY + CONQUEST en Atom11 (cheat sheet #21-#32, Fase 2)
- [ ] Crear 4 Harvest rules (cheat sheet #33-#36, Fase 2)
- [ ] Pausar campañas B0CYLDSQ5L (15 campañas RANKING/DISCOVERY/CONQUEST)
- [ ] Bajar bids a $0.50 en campañas B0CYLDSQ5L que se mantengan
- [ ] Probar automatización Atom11 desde Cowork (Claude Desktop)
- [ ] Testing módulo Atom11 Rules Builder con Campaign CSV real
- [ ] Actualizar Atom11_Rules.md con v2026.2 thresholds
- [ ] Sesión 11: Account Pulse (roadmap)

---

## 📅 Sesión 2026-03-26 — Lo que hicimos

### Sub-agents creados (.claude/agents/)
- **ppc-module-builder** — Sonnet, orange, project memory
- **excel-export-builder** — Sonnet, orange, project memory
- **atom11-specialist** — Opus, purple, project memory
- **client-notes-updater** — Haiku, green, project memory
- **code-reviewer** — Haiku, red, project memory (read-only)

### Upgrades implementados (5 módulos)
- **Bid Optimizer** — nueva tab "Placements & Budget": `_PLACEMENT_RULES`, `_detect_campaign_type()`, tabla referencia placements por tipo campaña, budget estimado, export
- **Campaign Analyzer** — upgrade a Auditoría PPC: `_check_naming()`, naming convention check, target graduation (0 impressions), export multi-sheet
- **Weekly Client Report** — changelog: `st.text_area` + hoja "Changelog" en Excel
- **STR Harvest** — anti-canibalización: cruce con Campaign CSV, marca duplicados Exact activos, checkbox incluir/excluir
- **Análisis Cruzado** — nueva tab "PPC Insights por ASIN": BR uploader opcional, resumen por ASIN, top 5 keywords, gap detection, export
- **Account Pulse** — módulo nuevo en Account Manager. Input: BR diario 14d + BR by Child + Campaign CSV. Split PW/TW automático. Excel 4 hojas: Resumen Ejecutivo (portada naranja), Ventas Diarias (laboral/finde/festivo MX), BuyBox & ASINs (ordenado por ventas perdidas), Campañas (NUEVA vs HEREDADA). 430+ líneas.

### Módulos nuevos — Sección INTELIGENCIA (3 módulos)
- **PPC Insights Engine** — módulo nuevo. Cruza STR + SQP + BR + Campaign CSV por ASIN. Health score 0-100 (CVR 25% + BuyBox 20% + ACoS 25% + Funnel 15% + Impression Share 15%). Cards por ASIN con expanders. Botón IA opcional. Excel multi-sheet con hasta 10 hojas por ASIN. 530 líneas.
- **PPC Forecast** — módulo nuevo. Input: BR diario (mín 14d). Tendencia lineal (numpy polyfit), estacionalidad finde/laboral, proyección 7/14/30d. Budget recommendation. Gráfico histórico + proyección. Excel 2 hojas. 450 líneas.
- **PPC Audit** — módulo nuevo. Input: STR + Campaign CSV (mín). Report card de cuenta 0-100. Estructura (tipos, match types, portfolios), naming convention check, eficiencia (ACoS, top campaigns), desperdicio (WAS, fantasmas), cobertura funnel por ASIN, BuyBox. Excel 5-6 hojas con portada Capybaras. 530 líneas.

### Archivos modificados
- `modules/pages/bid_optimizer.py`
- `modules/pages/bulk_campanas.py`
- `modules/pages/weekly_client_report.py`
- `modules/pages/search_term_report.py`
- `modules/pages/analisis_cruzado.py`
- `modules/pages/account_pulse.py` — NUEVO
- `modules/pages/ppc_insights.py` — NUEVO
- `modules/pages/ppc_forecast.py` — NUEVO
- `modules/pages/ppc_audit.py` — NUEVO
- `app.py` — + sección sidebar INTELIGENCIA + imports + routing
- `core/constants.py` — + 3 páginas nuevas
- `.claude/agents/` (5 archivos nuevos)

### ⚠️ Pendiente
- [ ] Testing con archivos reales de cada módulo modificado
- [x] Account Pulse — módulo nuevo ✅ completado 2026-03-26
- [x] PPC Insights Engine — módulo nuevo ✅ completado 2026-03-26
- [x] PPC Forecast — módulo nuevo ✅ completado 2026-03-26
- [x] PPC Audit — módulo nuevo ✅ completado 2026-03-26
- [x] Actualizar PPC-SOP-Manager.md con nuevos features ✅ 2026-03-26
- [x] Rediseñar inicio.py con 18 módulos + changelog ✅ 2026-03-26
- [x] Code review — 38 archivos compilados, 2 fixes aplicados ✅ 2026-03-26
- [ ] Git push final

---

## 📅 Sesión 2026-03-27 — Lo que hicimos

### Módulos nuevos
- **DataDive Analyzer** — módulo nuevo en sección Research. 3 tabs:
  - Tab 1: MKL Keywords — parser niche-*-keywords.xlsx, detecta ASINs competidores, keyword gaps vs tu ASIN, filtro SV + relevance
  - Tab 2: Competitors — parser niche-*-competitors.xlsx (estructura vertical → tabla horizontal), comparación tu ASIN vs Niche Median
  - Tab 3: Rank Radar — parser [product].xlsx, ranking orgánico diario, tendencia ↑→↓, PPC coverage, gráfico de evolución por keyword
  - 3 parsers cacheados con @st.cache_data

### Performance & cleanup
- **@st.cache_data agregado** a todos los parsers de lectura de archivos:
  - `core/helpers.py` → `read_sqp()` (cubre SQP, Cruzado, Tendencia)
  - `search_term_report.py` → `_load_str()`
  - `bulk_campanas.py` → `_load_bulk()`
  - `business_report.py` → `_load_br()`
  - `analisis_cruzado.py` → `_load_str_file()`
  - `analisis_funnel.py` → `_load_file()`
- **9 download_buttons sin key** → keys únicos agregados (analisis_cruzado, tendencia, funnel×3, forecast, atom11_rules×2, audit)
- **Verificación**: todos los 21 file_uploaders ya tenían keys únicos — 0 cambios necesarios

### Archivos creados/modificados
- `modules/pages/datadive_analyzer.py` — NUEVO (380+ líneas)
- `modules/pages/helium10_analyzer.py` — NUEVO (350+ líneas, 3 tabs, Cerebro parser)
- `app.py` — + import + sidebar sección RESEARCH (DataDive + H10) + routing
- `core/constants.py` — + DataDive + Helium 10 en _PAGES (20 páginas)
- `modules/pages/inicio.py` — v2.1, 20 módulos, sección Research con 2 módulos
- `core/helpers.py` — + import streamlit, @st.cache_data en read_sqp
- `modules/pages/search_term_report.py` — + _load_str() cached
- `modules/pages/bulk_campanas.py` — + _load_bulk() cached, fix import io
- `modules/pages/business_report.py` — + _load_br() cached
- `modules/pages/analisis_cruzado.py` — + _load_str_file() cached, + key cruzado_dl_opp
- `modules/pages/tendencia_multisemana.py` — + key tendencia_dl
- `modules/pages/analisis_funnel.py` — + _load_file() cached, + 3 keys
- `modules/pages/ppc_forecast.py` — + key forecast_dl
- `modules/pages/atom11_rules_builder.py` — + 2 keys
- `modules/pages/ppc_audit.py` — + key audit_dl
- `CLAUDE.md` — + DataDive en tabla navegación + módulos + sesión 2026-03-27

### Helium 10 Analyzer — detalle
- **Tab 1 — Cerebro Reverse ASIN**: parser `_parse_cerebro()` con @st.cache_data, maneja "-" como NaN, detecta ASIN del filename. Filtros SV + Organic Rank + IQ Score. Flags: Oportunidad PPC (organic sin ads), Depende de Ads (ads sin organic).
- **Tab 2 — KW Research**: 1-3 Cerebros de competidores, cruza keywords, calcula Launch Priority Score = SV × (comps ranking / total) × (1 / avg rank). Clustering automático por root word. Export "KW Research Pack".
- **Tab 3 — Competitor Gap**: tu Cerebro vs 1-2 competidores. Detecta KWs donde competidor rankea orgánicamente y vos no. Acción sugerida: ATACAR (SV≥500, rank≤15) / MONITOREAR / IGNORAR. Export con acciones.

### Nuevos módulos y features (batch 2)
- **DataDive Tab 4 — Ranking + PPC IS**: volatilidad del ranking orgánico (std dev de posiciones diarias). Clasifica ESTABLE/VOLÁTIL/MUY VOLÁTIL. Cruza con SQP para PPC Impression Share. Flags: volátil sin PPC = RIESGO, estable top 10 con PPC = oportunidad de reducir spend.
- **SBH Target Recommendation** — módulo #21. Cruza MKL + SQP + Campaign CSV. Prioridad ALTA: SV>1000 + IS<10% + mercado comprando + no en SP. Clustering + headline sugerido por cluster. Export "SBH Target Pack" multi-sheet.
- **Workflow Wizard** — sección piramidal en Inicio. 5 niveles: Subí datos → Analizá → Inteligencia → Ejecutá → Reportá. Cada nivel lista módulos y archivos necesarios.
- **Knowledge Base** — módulo #22. Sube .md, parsea headers/tags/categorías/fecha del filename. Búsqueda full-text, filtro por tags y categoría. Tab para crear notas nuevas y descargar como .md.

### Archivos creados/modificados (batch 2)
- `modules/pages/datadive_analyzer.py` — REESCRITO: fix return-in-tabs bug + tab 4 Ranking Volatility
- `modules/pages/sbh_recommendation.py` — NUEVO (230+ líneas)
- `modules/pages/knowledge_base.py` — NUEVO (180+ líneas)
- `modules/pages/inicio.py` — v3.0, 22 módulos, Workflow Wizard piramidal, sección Knowledge
- `app.py` — + 2 imports, + sección KNOWLEDGE en sidebar, + 2 routings
- `core/constants.py` — + SBH + Knowledge Base en _PAGES (22 páginas)
- `CLAUDE.md` — filas 21-22 en tabla, módulos en lista, sesión actualizada

---

## 📅 Sesión 2026-03-27b — Lo que hicimos (conexión + mejoras visuales)

### Módulos conectados al router (8 nuevos)
- **DataDive Analyzer** — 4 tabs: MKL keywords, Competitors matrix, Rank Radar tracking, Ranking Volatility + PPC IS cruzado con SQP
- **Helium 10 Analyzer** — 3 tabs: Cerebro reverse ASIN con oportunidades PPC, KW Research multi-competidor, Competitor Gap Analysis
- **SBH Recommendation** — Targets para Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV. Clustering automático + headlines sugeridos
- **Knowledge Base** — 2 tabs: Explorar notas .md con búsqueda por texto/tags/categorías + Agregar nota con preview y descarga
- **PPC Insights** — Health score 0-100 por ASIN cruzando STR + SQP + BR + Campaign CSV. Top keywords, bleeders, wasted spend
- **PPC Forecast** — Proyección de ventas con tendencia lineal + estacionalidad. Export Excel con escenarios
- **PPC Audit** — Auditoría integral: estructura, naming, eficiencia, desperdicio, cobertura. Score 0-100 desglosado
- **Account Pulse** — Monitor de salud diaria: ventas, units, sessions, CVR, ACoS con WoW deltas. Festivos MX integrados

### Mejoras visuales transversales
- **kpi_card helper** — core/helpers.py → cards naranja #FFF3E0 con borde #FFD9B3, delta con flechas ↑↓→ y color verde/rojo
- **48 st.metric migrados a kpi_card** en: PPC Insights (4), Account Pulse (5), SBH Recommendation (4), DataDive (14), Helium 10 (11), PPC Forecast (4), PPC Audit (5), Knowledge Base (1)
- **14 empty states** reemplazados por cards visuales con icono 📂 y borde dashed
- **8 headers unificados** con layout flex: emoji 2rem + título 1.3rem bold + caption 0.82rem
- **Color coding en tablas** — DataDive: Relevance + Launch Score + Rating. Helium 10: Frequency/Competitor Count
- **Sidebar colapsable** — 4 secciones con st.expander: PPC (expanded) | Research | Account | Knowledge
- **Inicio reorganizado** — 3 cards activas (PPC 10 módulos + Account 4 + Research 7) + KB full-width + flujo guiado 5 niveles actualizado

### Archivos modificados
- `app.py` — +8 imports, +sidebar RESEARCH y KNOWLEDGE con expanders, +8 routing ifs, CSS expanders
- `modules/pages/inicio.py` — 3 cards activas, flujo guiado actualizado, KB card, changelog
- `modules/pages/datadive_analyzer.py` — header, empty states, kpi_cards (14), color coding
- `modules/pages/helium10_analyzer.py` — header, empty states, kpi_cards (11), color coding
- `modules/pages/sbh_recommendation.py` — header, empty states, kpi_cards (4), color clusters
- `modules/pages/knowledge_base.py` — header, empty states, badges categoría
- `modules/pages/ppc_insights.py` — header, empty states, kpi_cards (4)
- `modules/pages/ppc_forecast.py` — header, empty states, kpi_cards (4)
- `modules/pages/ppc_audit.py` — header, empty states, kpi_cards (5)
- `modules/pages/account_pulse.py` — header, empty states, kpi_cards (5)
- `core/helpers.py` — +kpi_card()

### Regla operativa nueva
- Después de cada prompt de código, Claude siempre indica qué tabs revisar y el comando git

### ⚠️ Pendiente próxima sesión
- [ ] Testing completo de los 8 módulos nuevos con archivos reales
- [ ] Atom11 Rules Builder — verificar que está conectado en app.py
- [ ] Account Pulse — testing con BR Daily real
- [ ] PPC Audit — testing con STR + Campaign CSV real
- [ ] PPC Insights — testing con STR + SQP + BR + Campaign CSV
- [ ] Actualizar PPC-SOP-Manager.md con los 8 módulos nuevos

---

## 📅 Sesión 2026-04-02 — Lo que hicimos

### Proyecto 1 — STR Upgrade (features del STR Analyzer externo)

Un compañero de PPC creó un STR Analyzer standalone (HTML/JS, 1183 líneas). Lo pasamos por el agente code-reviewer para analizar qué features aportan valor nuevo. De 10 features, 3 eran genuinamente nuevas, 6 parciales, 1 ya cubierta.

**Decisión: NO crear módulo nuevo. Integrar lo mejor como upgrade al search_term_report.py existente.**

#### Cambios implementados en search_term_report.py (489 → ~1,000 líneas):

- **Filtro portfolio transversal** — st.multiselect arriba de todas las tabs, detecta columna Portfolio Name del STR, filtra df antes de pasar a cualquier tab
- **Tab1 enriquecida:**
  - 12 KPIs con kpi_card (antes 4 st.metric): Spend, Sales, ACoS con delta, ROAS, Impressions, Clicks, CTR, CVR, CPC, Orders, % Waste, % Con Ventas
  - Input brand terms → clasificación _term_type: Brand/Generic/Long-tail
  - Filtros interactivos: campaña, match type, ACoS max, spend min
  - Vistas rápidas: Todos / Winners (2+ orders) / Sin ventas / Top Sales / Top Spend
  - Columna _estado automática: Escalar (3+ orders, ACoS < 50% target) / OK / Reducir / Revisar / Negativa?
  - Scatter chart Spend vs Sales (plotly) con colores por term type
  - Funnel de conversión horizontal: Impressions → Clicks → Orders con % de paso
  - Tabla distribución term type con % Spend
  - Excel multi-sheet: STR Analizado + Resumen KPIs + Por Estado + Por Tipo Término
- **Tab5 nueva "📊 Por Campaña":**
  - Groupby por campaign: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC
  - Clasificación Brand/No Brand automática por nombre de campaña
  - 4 KPIs + tabla con color coding + download Excel
- **Thresholds alineados al SOP:**
  - Escalar: 3+ orders (antes cualquier orden)
  - Winners: 2+ orders (antes 1 sola orden)
- **Fix bug Excel:** "At least one sheet must be visible" — extraída función _build_str_excel() fuera de render() para aislar del runtime de Streamlit
- **Tabs 2/3/4 sin cambios** — solo reciben df filtrado por portfolio

#### Lo que NO se copió del HTML:
- Lógica de negatives (threshold fijo clicks>=3 — nuestros tiers dinámicos por CVR son superiores)
- Clasificación brand naive (busca "brand" literal — nuestra detección por SQP + input manual es mejor)
- Proyección 30 días (números inventados — nuestro PPC Forecast hace cálculo real)
- Insights locales (templates fijos — nuestra tab IA con Claude API es superior)

---

### Proyecto 2 — PPC Audit Pro (features del sistema de auditoría del PPC leader)

El PPC leader creó un sistema de auditoría PPC: prompt para Claude + HTML estático + specs de diseño. Lo pasamos por code-reviewer. De 20 features, 10 eran genuinamente nuevas — todas desbloqueadas por UN cambio: soporte del Bulk File XLSX multi-hoja.

**Decisión: REEMPLAZAR ppc_audit.py completo con nuevo módulo que trabaja con Bulk File.**

#### PPC Audit Pro — ppc_audit.py reescrito (839 → 1,077 líneas):

**Input nuevo:** Bulk File XLSX (Campaign Manager → Bulk Operations) + Business Report opcional

**Parser _parse_bulk():**
- Parsea 5 hojas: SP Campaigns, SB Campaigns, SD Campaigns, SP Search Term Report, SB Search Term Report
- Subcategoriza SP por Entity: Campaign, Ad Group, Keyword, Product Targeting, Bidding Adjustment, Negative Keyword
- Numericiza todas las métricas (Spend, Sales, Clicks, Impressions, Orders, ACOS, CPC, ROAS)
- @st.cache_data

**Tab 1 — KPIs Overview:**
- ACoS Overall con breakdown real SP/SB/SD (desde hojas del Bulk, no heurística)
- Impressions con % por tipo
- PPC Spend + Sales con breakdown
- Clicks, Orders, CTR, CVR
- Si hay BR: Revenue Total, Ventas Orgánicas, TACoS

**Tab 2 — Auditoría de Estructura (3 cards):**
- Match Types Mixtos: agrupa keywords por Campaign ID, detecta >1 match type por campaña. Badge OK/REVISAR
- Target WAS: SP keywords + PT + SD targets donde Spend>0 AND Sales=0. Monto y % por tipo
- Search Term WAS: SP STR + SB STR waste. Top 5 terms sin ventas. Alert CRÍTICO si >40%

**Tab 3 — Performance por Segmento:**
- SP: 10 segmentos — KW Exact/Phrase/Broad + PT ASIN/Category + AUTO Close/Loose/Substitutes/Complements + TOTAL SP
- SB: KW Exact/Phrase/Broad + TOTAL SB
- SD: Retargeting/Audiences/Product Targeting + TOTAL SD
- Headers coloreados: SP azul #1d4b8f, SB violeta #6b2d8f, SD verde #2a6e4e
- ACoS coloreado: verde ≤30%, amarillo 31-55%, rojo >55%
- AUTO targets detectados cruzando Campaign ID con campañas Targeting Type = "Auto"

**Tab 4 — Deep Checks (5 checks):**
1. Top 5 Campañas SP por Spend con Targeting Type, Sales, ACoS, Orders
2. Clasificación de Targets: own_brand/own_asin/competitor_asin/generic (requiere brand terms input)
3. Duplicación de Targets: keywords en 2+ campañas, top 10 por spend combinado
4. Bid Adjustments por Placement: distribución de ajustes Top/Product Page/Rest of Search + Bidding Strategy
5. SKAG vs Bolsa: ratio targets/campaña (1=SKAG, 2-10=Normal, 11+=Bolsa)

**Tab 5 — Export:**
- Excel 6 hojas: Resumen KPIs, Performance Segmento, Auditoría, Top Campañas, Clasificación Targets, Duplicación Targets
- Función _build_audit_excel() fuera de render() (patrón anti-bug openpyxl)

#### Lo que se mantiene aparte:
- Prompt de insights narrativos del PPC leader → sigue como herramienta independiente (Claude en contexto libre supera botón de IA)

#### Elementos visuales adoptados del HTML del PPC leader:
- Badges OK/REVISAR/CRÍTICO con colores verde/amarillo/rojo
- Headers coloreados por tipo SP/SB/SD

---

### Archivos modificados 2026-04-02
- `modules/pages/search_term_report.py` — REESCRITO: 489 → ~1,000 líneas (5 tabs, 12 KPIs, filtros, charts, Excel multi-sheet)
- `modules/pages/ppc_audit.py` — REESCRITO: 839 → 1,077 líneas (5 tabs, parser Bulk multi-hoja, 10 segmentos, 5 deep checks)

### Proceso de integración de herramientas externas (nuevo SOP)
1. Compañero comparte herramienta → Lenin la sube al chat
2. Claude (chat) analiza features y solapamiento con módulos existentes
3. Code-reviewer (agente) hace análisis formal: mapa 🔴/🟡/✅ + recomendaciones INTEGRAR/SKIP/MANTENER APARTE
4. Claude (chat) genera mensaje para PPC leader con análisis + plan de integración
5. Claude (chat) genera prompt para ppc-module-builder
6. Implementación + testing con datos reales

### ⚠️ Pendiente próxima sesión
- [ ] Testing PPC Audit Pro con Business Report (para TACoS y Revenue)
- [ ] Testing PPC Audit Pro con Bulk de otros clientes (LTD, M&B, Setex)
- [ ] Escribir brand terms para 360 Essentials y verificar clasificación de targets
- [ ] Formatear números en Tab3 Performance (muchos decimales — redondear a 2)
- [ ] SKAG vs Bolsa vacío — revisar lógica de conteo de targets por campaña
- [ ] Actualizar PPC-SOP-Manager.md con nuevos features
- [ ] Actualizar inicio.py con módulos actualizados
- [ ] Reconectar los 9 módulos que faltan en app.py (Research + Knowledge + Rules Builder)
- [ ] Subir archivos actualizados al proyecto de Claude

---

## 📅 Sesión 2026-04-08 — Lo que hicimos

### Bloque A — 3 Skills core creados (.claude/skills/)
- **ppc-reporting-standard.md** — paleta Capybaras, kpi_card, semáforos ACoS, Excel branding, fórmulas PPC, benchmarks, formato numérico, terminología ES/EN
- **module-architecture-standard.md** — patrón render(), header, empty states, tabs (sin return adentro), parsers @st.cache_data, _build_*_excel() fuera de render(), checklist pre-commit
- **client-communication-tone.md** — tono Capybaras, estructura reporte ejecutivo, changelog técnico, formato Slack, reglas por mercado MX/US, toggle ES/EN, alarmas por severidad

### Bloque B — 9 agentes upgradeados a v3 (.claude/agents/)
Todos los agentes ahora tienen: frontmatter completo (name, description, tools, model, color, skills), secciones Rol/Activación/Tools/Proceso/Output obligatorio/Reglas, y principio de mínimo privilegio en tools.

| Agente | Modelo | Tools | Skills asignados |
|--------|--------|-------|------------------|
| ppc-module-builder | Sonnet | All | ppc-reporting-standard, module-architecture-standard |
| excel-export-builder | Sonnet | All | ppc-reporting-standard |
| ui-designer | Sonnet | All | ppc-reporting-standard, module-architecture-standard |
| code-reviewer | Sonnet | Read-only (Glob, Grep, Read) | module-architecture-standard, ppc-reporting-standard |
| testing-agent | Sonnet | All + Bash | module-architecture-standard |
| atom11-specialist | Sonnet | All | ppc-reporting-standard |
| sop-writer | Haiku | Glob, Grep, Read, Write (.md only) | client-communication-tone |
| client-notes-updater | Haiku | Glob, Grep, Read, Write (.md only) | client-communication-tone |
| client-onboarding | Sonnet | All | ppc-reporting-standard, client-communication-tone |

### Bloque C — CLAUDE.md por módulo
- Creado `modules/pages/CLAUDE.md` con 22 secciones (M1–M22)
- Cada sección: Propósito, Arquitectura, Reglas de negocio, Inputs, Anti-patterns
- Los agentes ahora leen este archivo cuando trabajan en un módulo específico

### Bloque 1 — Campaign Builder SB/SBV/SD
- `campaign_builder.py` — selector de tipo (SP/SB/SD) con radio button
- SP: lógica existente sin cambios
- SB: inputs extra (headline 50 chars, brand name, creative ASINs ×3, landing page type/URL), naming [Marca]-[ASIN]-SB-KW-[Match]-[Cluster], bulk formato SB Amazon
- SD: inputs extra (Product Targeting o Audience, bid optimization, ASINs competidores), naming [Marca]-[ASIN]-SD-[PT/AUD]-[SubTipo], bulk formato SD Amazon
- ⚠️ Pendiente: validar columnas exactas del bulk SB/SD contra formato real de Amazon

### Bloque 2 — Target Graduation + Pausado Inteligente
- `ppc_audit.py` — Tab 6 nueva "🎯 Target Graduation"
- Analiza targets con 0 impresiones en campañas que SÍ tienen tráfico
- Clasificación: 🔼 SUBIR BID (tuvo ventas, bid bajo) / 🔴 PAUSAR (gastó sin convertir) / 🟡 GRADUAR A SKAG (mover a campaña propia) / 🛡️ MANTENER (keyword de marca)
- 4 kpi_cards + tabla con color coding + filtro por recomendación
- Hoja "Target Graduation" agregada al Excel de export

### Bloque 3 — Competitor Gap → Campaign Builder Pipeline
- `helium10_analyzer.py` — botón "Exportar como Plan de Acción" en Tab 3 Competitor Gap
- Convierte keywords con acción ATACAR al formato Plan de Acción compatible con Campaign Builder
- Pipeline completo: H10 Cerebro → Competitor Gap → Plan de Acción → Campaign Builder → bulk Amazon

### Bloque 4 — Competitor Intelligence Unificado
- `datadive_analyzer.py` — Tab 5 nueva "🏆 Competitor Intel"
- Upload tu MKL + MKL competidor → merge outer por keyword
- Clasificación: 🤝 Ambos rankean / ✅ Solo yo / 🔴 Solo competidor / ⚫ Ninguno
- 4 kpi_cards + filtro por gap type + tabla + export Excel
- Opcionalmente acepta Cerebro H10 del competidor

### Bloque 5 — Comunicación Técnica (Slack)
- `weekly_client_report.py` — botón "📋 Copiar Changelog para Slack"
- Genera formato: emoji + marca + fecha + cambios + nota de adjunto
- Renderizado en st.code con botón copiar nativo de Streamlit

### Bloque 6 — Ranking Tracking Mejorado
- `datadive_analyzer.py` Tab 3 Rank Radar — historial de ranking en session_state
- Guarda hasta 5 snapshots por sesión
- Cuando hay 2+ snapshots: muestra delta de posiciones, tendencia (🟢 Subió / 🔴 Bajó), kpi_cards con subieron/bajaron/delta promedio
- Comparación entre archivos cargados en la misma sesión

### Cobertura PPC
- Antes: 75% (14 completas + 5 parciales + 3 sin cobertura)
- Después: ~95% (22/22 funciones cubiertas)
- Pendiente 5%: envío automático Slack/email (API) + tracking persistente entre sesiones (DB) → Etapa 11

### Archivos creados hoy
- `.claude/skills/ppc-reporting-standard.md` — NUEVO
- `.claude/skills/module-architecture-standard.md` — NUEVO
- `.claude/skills/client-communication-tone.md` — NUEVO
- `modules/pages/CLAUDE.md` — NUEVO (22 secciones)

### Archivos modificados hoy
- `.claude/agents/` — 9 archivos reescritos (v3 con frontmatter + skills)
- `modules/pages/campaign_builder.py` — + soporte SB y SD
- `modules/pages/ppc_audit.py` — + Tab 6 Target Graduation
- `modules/pages/helium10_analyzer.py` — + export Plan de Acción en Competitor Gap
- `modules/pages/datadive_analyzer.py` — + Tab 5 Competitor Intel + ranking tracking en Tab 3
- `modules/pages/weekly_client_report.py` — + botón Slack changelog

### Metodología implementada (claude-methodology.md)
- 3 Skills core cubriendo: formato reportes, arquitectura módulos, tono comunicación
- 9 agentes con frontmatter, skills asignados, mínimo privilegio
- CLAUDE.md por módulo (22 secciones) para contexto enfocado por agente
- Flujo: agente lee CLAUDE.md raíz + Skills + CLAUDE.md módulo automáticamente

### ⚠️ Pendiente próxima sesión
- [ ] Validar columnas bulk SB/SD contra formato real de Amazon Ads
- [ ] Testing Campaign Builder SB con datos reales
- [ ] Testing Campaign Builder SD con datos reales
- [ ] Testing Target Graduation con Bulk File real
- [ ] Testing Competitor Intel con 2 MKL reales
- [ ] Testing Rank Radar tracking con 2 archivos distintos
- [ ] Actualizar inicio.py con features nuevas
- [ ] Subir archivos actualizados al proyecto de Claude

---

## 📅 Sesión 2026-04-09 — Listing Monitor

### Módulo nuevo: listing_monitor.py
- **Archivo:** `modules/pages/listing_monitor.py` — 587 líneas
- **Sección sidebar:** 👥 Account Manager
- **Página:** `👁️ Listing Monitor`

### Qué hace
Monitorea ASINs de Amazon y alerta cuando algo cambia vs el snapshot anterior.
Scrapea Amazon directamente con requests + BeautifulSoup (sin API key).

### Campos monitoreados por ASIN
precio - rating - cantidad de reseñas - badge (Best Seller / Amazon's Choice) - bullets - stock - título del producto

### Arquitectura
- **Tab 1 — Escanear ASINs:** input de ASINs, selector marketplace (MX/COM/ES/BR/CA), delay configurable, guardado automático de snapshot
- **Tab 2 — Ver Alertas:** comparación vs snapshot anterior, color coding (🔴 alerta / 🟡 info / 🟢 ok), filtro rápido
- **Tab 3 — Historial:** tabla de todos los snapshots con columna Producto

### Storage
Snapshots guardados como JSON local en `data/listing_snapshots/snapshots.json`
Clave: `{ASIN}_{MARKETPLACE}` (ej: `B0C5JWKLZG_COM`)

### Dependencias nuevas
```bash
pip install requests beautifulsoup4
```

### Mejoras aplicadas en la misma sesión
1. Fix SessionState — `lm_marketplace` → `lm_marketplace_result` para evitar conflicto con widget key
2. `kpi_card()` en vez de `st.metric` — 8 reemplazos
3. Imports sin usar eliminados (`date`, `Optional`)
4. Título del producto extraído en scraper (`#productTitle`) y mostrado en expanders e historial

### Review de 3 agentes — Pendientes P1/P2
| # | Mejora | Prioridad |
|---|--------|-----------|
| 1 | Export Excel del historial (Tab 3) | P1 |
| 2 | Header estándar flex + st.divider() | P2 |
| 3 | Empty states con patrón visual dashed #FFD9B3 | P2 |
| 4 | Asociación ASIN-Cliente/Marca (tag Propio/Competidor) | P3 |
| 5 | Presets de ASINs por marca | P4 |
| 6 | Comparación de precio numérica con delta % | P4 |
| 7 | Banner de stock crítico en Tab 2 | P4 |
| 8 | Historial multi-fecha (hoy sobreescribe el último) | P4 |

### Contexto técnico
- Amazon a veces retorna 503 (bloqueo). Workaround: aumentar delay a 8-10s
- Para uso intensivo (20+ ASINs diarios) → migrar scraper a Firecrawl
- HTML crudo en expander titles: bug visual menor pendiente de fix

### Archivos modificados hoy
- `app.py` — +import, +sidebar entry, +routing if
- `modules/pages/listing_monitor.py` — NUEVO (587 líneas)


---

## 📅 Sesión 2026-04-14 — Deploy + UX

- Deploy live: capybaras-os.streamlit.app (2026-04-14)
- Login implementado con streamlit-authenticator (usuario: lenin)
- requirements.txt actualizado: anthropic, python-dotenv, plotly agregados
- runtime.txt: Python 3.11
- Fix: f-string backslash Python 3.11 en weekly_client_report.py line 917
- Expanders de ayuda agregados en 10 módulos PPC (search_term_report, search_query_performance, analisis_cruzado, tendencia_multisemana, bulk_campanas, business_report, analisis_funnel, bid_optimizer, campaign_builder, atom11_rules_builder)
- SOP_Uso_AgencyOS.md creado (432 líneas) con flujo semanal + 22 módulos documentados

---

## 📅 Sesión 2026-04-15 — Onboarding equipo + cobertura expanders

- Deploy live confirmado en capybaras-os.streamlit.app ✅
- 21 usuarios del equipo agregados a `.streamlit/secrets.toml` (contraseña inicial: `Capybaras2026!`)
- Expanders de ayuda implementados en 15/15 módulos restantes (cobertura 100%):
  - Account/Research: atom11, merchanspring, weekly_client_report, datadive_analyzer, helium10_analyzer, sbh_recommendation, ppc_insights, ppc_forecast, ppc_audit, account_pulse
  - Nuevos: knowledge_base, listing_monitor
  - Ya tenían: bid_optimizer, campaign_builder, atom11_rules_builder
  - Todos compilan sin errores (py_compile OK en los 15)
- Fix requirements.txt: agregado `requests` y `beautifulsoup4` para que Listing Monitor funcione en Streamlit Cloud
- Pendiente: verificar Listing Monitor en producción tras Reboot — si persiste el error, revisar logs de Streamlit Cloud
- Pendiente: decidir si credenciales se comunican individualmente o con usuario compartido

---

## 📅 Sesión 2026-04-21 — Campaign Builder bulk 2026 compliant

### Fixes aplicados a `modules/pages/campaign_builder.py` (flujo SP)
- Ahora es compliant con `AmazonBulkUploadGuide.md` (8 reglas) + columna **Sites** (update Q2 2026)
- Helper `_BULK_COLUMNS_2026` (31 columnas, orden exacto) + `_fila_vacia_bulk()` agregados a nivel módulo — reusable desde cualquier otro módulo que necesite generar bulks SP
- **Fix crítico (Regla #3):** Campaign ID / Ad Group ID en filas `create` siempre deben ser los nombres, nunca vacíos — sin esto Amazon falla con "Missing Parent ID"
- **Regla #4:** Start Date ya estaba en `yyyyMMdd` (no requirió cambio — verificado)
- **Regla #5:** Bidding Strategy ya estaba en `"Dynamic bids - down only"` (verificado)
- **Regla #7:** No hay filas vacías separadoras (verificado)
- Reescritas las 4 filas del loop SP con patrón `_fila_vacia_bulk() + .update()` — más legible, imposible olvidar una columna
- DataFrame ahora usa `pd.DataFrame(rows, columns=_BULK_COLUMNS_2026)` para orden garantizado
- Eliminado dict local `_EXTRA` (8 cols) — ahora cubierto por el helper

### Validación post-fix
Smoke test reproduce el loop con 3 keywords (Vitamin A + Spanish + PAT) → 12 filas, 31 cols, última "Sites":
- Campaign ID == Campaign Name en todas las filas Campaign
- Campaign ID == Campaign Name AND Ad Group ID == Ad Group Name en Ad Group/Product Ad/Keyword/PT
- Start Date = `20260421` (string 8 dígitos)
- Bidding Strategy = `Dynamic bids - down only`
- PAT usa `Product Targeting Expression = asin="B0..."` con Keyword Text / Match Type / Product Targeting ID vacíos (Regla #6)

### Fuera de scope de esta sesión
- `_render_sb()` y `_render_sd()` siguen con su formato anterior (columnas propias, no las 31 de SP) — pendiente migrar cuando Amazon documente formato bulk exacto para SB/SD 2026
