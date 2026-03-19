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

| # | Página | Estado |
|---|--------|--------|
| 1 | 🏠 Inicio | ✅ completo |
| 2 | 📊 Search Term Report | ✅ completo |
| 3 | 🔍 Search Query Performance | ✅ completo |
| 4 | 📁 Bulk Campañas | ✅ completo |
| 5 | 💰 Business Report | ✅ completo |
| 6 | 🔗 Análisis Cruzado STR vs SQP | ✅ completo |
| 7 | 📈 Tendencia Multi-Semana | ✅ completo |
| 8 | 🔻 Análisis de Funnel | ✅ completo |
| 9 | 🔬 Reportes Atom 11 | ✅ completo |
| 10 | 🛡️ Reportes MerchanSpring | ✅ completo |
| 11 | 📊 Weekly Client Report | ✅ completo |

Navegación por `st.session_state["selected_page"]` + `_nav(page)` callback.  
`_PAGES` lista el orden completo. Sidebar agrupa por sección.

---

## 🏗️ Estado de modularización (2026-03-18)

app.py original: 3,974 líneas → actual: ~200 líneas (router + sidebar)

### ✅ Módulos extraídos
- `core/i18n.py` — _I18N (dict ES/EN)
- `core/constants.py` — _BR_OPTIONAL_COLS, _PAGES
- `core/helpers.py` — _color_pct, read_sqp, extract_sqp_brand
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

### 🔜 Pendiente arquitectura
- [ ] Reescribir app.py como router minimal (~100 líneas) — usar High effort
- [x] Bug: tendencia_multisemana.py KeyError cuando se suben dos SQPs iguales — fix aplicado 2026-03-19

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
| **5** | Acción sugerida + Bulk output en Cruzado | Cruzado | Campañas nuevas listas |
| **6** | Health Check en Bulk | Bulk | Diagnóstico de estructura |
| **7** | Bid Optimizer (tab nueva) | Nuevo | Bids calculados en bulk |
| **8** | Account Pulse (tab nueva) | Nuevo | Monitor de salud diaria |
| **9** | Funnel Builder (upgrade Análisis Funnel) | Upgrade | Funnel completo exportable |
| **10** | Bulk Upload Builder (tab nueva) | Nuevo | Constructor de bulk visual |
| **11** | Automation Rules Builder (tab nueva) | Nuevo | Rules Atom 11 exportables |

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
