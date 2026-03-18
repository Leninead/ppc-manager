# CLAUDE.md

## 🦫 Proyecto: Amazon PPC Manager
**Agencia:** Capybaras Agency  
**Dev:** Lenin Acosta  
**Ruta local:** `C:\proyectos\ppc-manager`  
**Comando:** `python -m streamlit run app.py`  
**Stack:** Python + Streamlit + Pandas + OpenPyXL + pdfplumber  
**Arquitectura:** Modularizando — `app.py` (~3,257 líneas) + `core/` + `modules/`
## ⚙️ Setup
```bash
streamlit run app.py
pip install streamlit pandas openpyxl pdfplumber
```

No hay build step, test suite ni linter configurado.

---

## 📐 Estructura de navegación (Sidebar)

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

Navegación por `st.session_state["selected_page"]` + `_nav(page)` callback.  
`_PAGES` lista el orden completo. Sidebar agrupa por sección.

---

## 📋 Lógica por módulo

- **STR:** ACoS = `Spend / Sales * 100`. Columnas auto-detectadas por nombre.
- **SQP:** `read_sqp()` con `skiprows=1`. Marca extraída con `extract_sqp_brand()`.
- **Bulk:** Dataframe raw. Filtro por `State == "ENABLED"`.
- **Business Report:** Dataframe raw de ventas y sesiones.
- **Análisis Cruzado STR vs SQP:** Cruza `Customer Search Term` vs `Search Query`. Opportunity Score = min-max de impresiones + clicks + purchase rate. Filtros: impresiones, SQS, purchases, tipo Marca/Genérica.
- **Tendencia Multi-Semana:** Hasta 4 SQPs. Pivot por `Search Query`. ↑ >10%, ↓ >10%, → estable.
- **Análisis de Funnel:** Campañas ENABLED, brechas STR vs bulk, campañas sugeridas con naming convention, harvesting Exact/Phrase (Exact si órdenes ≥ min×3 o ACoS ≤ 25%).

---

## 🔑 Funciones helper globales (inicio del archivo)
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
- **`_BR_OPTIONAL_COLS`** — lista de columnas opcionales del BR que se agregan al Parent Evolution:
  Sessions, Page Views, Units Ordered, Total Order Items, Ordered Product Sales, Refund Rate, etc.
- **Columnas requeridas del BR:** `(Parent) ASIN`, `(Child) ASIN`
- **Columna opcional:** `Title`
- Sidebar muestra estado verde/naranja con cantidad de parents

---

## 🔬 Tab: Reportes Atom 11

**Archivos:** 1 archivo (single/WoW/MoM/DateRange) o 2 archivos (comparación WoW/MoM cross-file).

### Funciones internas
```python
_parse_atom11(file)
# → (df_flat, entity_cols, col_map, fmt)
# fmt: "WoW" | "MoM" | "DateRange"
# entity_cols: ["ASIN"] o ["Campaign", "CampaignType"] etc.
# col_map: [(col_idx, metric_name, period_label), ...]

_detect_atom11_type(entity_cols)   # → "ASIN" | "Portfolio" | "Keyword" | etc.
_extract_period_df(df, ec, cm, period)  # → df con entity_cols + métricas planas
_summarize_daterange(df, ec, cm)   # → (df_summed, "date1→date2")
_split_two_weeks(df, ec, cm)       # → (df_w1, df_w2, label_w1, label_w2) si hay 14 días exactos, o None

_kpis(df)
# → dict: Impressions, Clicks, Spend, Sales, Orders, ACoS, ROAS, CTR, CVR, CPC

_diag_items(kc, kp, lang)          # → [(status, text)] para diagnóstico
_rec_items(kc, kp, lang)           # → [texto] recomendaciones
_generate_summary(tipo, ec, kc, kp, per_c, per_p, top_rows, lang)  # → string ejecutivo
_color_pct(val)                    # → CSS color para celdas delta%

_build_atom11_excel(display_df, kc, kp, tipo, per_c, per_p, delta_cols,
                    client_name, entity_col, top_rows, lang, parent_evo_df)
# → BytesIO con 3 sheets (+ "Parent Evolution" si hay datos):
#   Sheet 1: "Informe Cliente" — branding + KPIs + top 3 + diagnóstico + recomendaciones
#   Sheet 2: "KPIs" — tabla comparativa de métricas
#   Sheet 3: "Datos" — tabla completa con delta% coloreado
#   Sheet 4 (opcional): "Parent Evolution"
```

### Idioma (i18n)
Toggle **Español / English** → `lang_code = "es" | "en"`.  
Dict `_I18N` con claves `"es"` y `"en"` contiene todos los labels, diagnósticos, recomendaciones y columnas de Parent Evolution.

### 🧬 Evolución por Parent ASIN
```python
_build_parent_evolution(df_flat, ec1, cm1, fmt1,
                        child_to_parent, asin_to_title,
                        br_df=None, lang="es")
# → (pe_df, error_str_or_None)
# Columnas output: Parent ASIN | Nombre | Ventas WoW (%) | Ventas últ. 7d | Ventas 7d ant.
#                 [+ Ventas últ. 30d] [+ Ventas últ. 90d] [+ BR optional cols agregados]
# Lógica DateRange: 14d → split 7+7; 30d+ → últimos 7d vs 7d anteriores; <14d → mitad/mitad
# Lógica WoW: periods[-1] = curr, periods[0] = prev
# Lógica MoM: single period, solo Ventas actuales

_generate_parent_evo_summary(pe_df, lang)
# → string ejecutivo copiable del portfolio
```

**Flujo en el tab:**
1. Si no hay `parent_child_map` → `st.info(pe_no_map)`
2. Llama `_build_parent_evolution(...)` antes del export
3. Muestra tabla con `_color_pct` en columnas con `%`
4. Expander con resumen ejecutivo
5. `_pe_df` se pasa al Excel como sheet "Parent Evolution"

### Sección Mapeo Parent-Child (al pie del tab)
- Muestra estado activo (fuente, N parents, N children, métricas BR disponibles)
- Permite subir nuevo Business Report para marca nueva
- Botones: "💾 Sí, guardar" (→ `data/business_report/`) vs "🚫 Solo esta sesión"

---

## 🛡️ Tab: Reportes MerchanSpring

**Acepta:** `.xlsx` o `.pdf`

### Flujo PDF
```python
_parse_merchanspring_pdf(file)
# Usa pdfplumber — concatena todas las páginas en full_text
# → dict con:
#   title, period, kpis (hasta 5)
#   summary_df (top sellers), inv_df (top + worst sellers combinados)
#   pnl_df, pnl_metrics (Profit%, Orders, Units, TACoS%, Estimated Payout, etc.)
#   prod_profit_df, health_data
#   adv_summary, adv_by_type_df, campaigns_df
#   top_product_ads_df, top_keywords_df
#   traffic_summary, tc_parent_df, tc_child_df
#   cancellations_data, sales_by_category_df, sales_by_country_df, sales_by_brand_df
#   top_bsr_df, review_data, shipping_data, buybox_snapshot
#   sections_log → [(icon, section_name, detail)] para debug en UI
#   wow_df = DataFrame() vacío (no hay WoW en PDF)

_build_ms_pdf_excel(data, client_name)
# → BytesIO Excel 4 hojas estilo NorseTradesman:
#   "📊 Summary" — KPI cards (filas 4-6) + top sellers (fila 8+)
#   "📣 Advertising" — banner advertencia Amazon Ads no conectado + headers vacíos
#   "📦 Inventory & Health" — 4 secciones: Inventario + P&L cards + P&L tabla + Salud
#   "📈 WoW Comparison" — 27 columnas: Product, ASIN + 9 grupos × (This/Prior/Δ%)
#     TACoS/Ad Sales/Ad Spend muestran "—" con nota al pie
```

### Flujo XLSX
```python
_parse_merchanspring(file)
# Lee 4 sheets del Excel de MerchanSpring
# → dict con: title, period, kpis, summary_df, adv_df, inv_df, wow_df, wow_metrics

_build_merchanspring_excel(data, client_name)
# → BytesIO Excel 4 hojas con color rules por ACoS/margin/delta/stock/efficiency
```

### Style helpers en el tab
```python
_s_acos(val)    # verde <30%, amarillo <60%, rojo ≥60%
_s_margin(val)  # verde ≥40%, amarillo ≥20%, rojo <20%
_s_delta(val)   # verde >5%, rojo <-5%, amarillo resto
_s_eff(val)     # poor/average/good/great
_s_stock(val)   # in stock/slow/no stock/partial
```

---

## 📋 Convención de naming de campañas
```
Producto - ASIN - Tipo - Match Type - Estrategia/KW
```
Ejemplo: `Body Lotion - B0CYLM4L23 - SP - KW - Phrase - Retinol Benefits`

| Tipo | Match Type |
|------|-----------|
| SP, SB, SD | KW - Broad / KW - Phrase / KW - Exact / PAT |

Función `extract_producto_asin(camp_name)` en Funnel tab extrae Producto y ASIN con regex.

---

## ⚙️ Columnas esperadas en archivos Amazon

**STR:** `Customer Search Term`, `Spend`, `Sales`, `7 Day Total Orders (#)`, `7 Day Total Sales`, `Total Advertising Cost of Sales (ACOS)`, `7 Day Conversion Rate`, `Campaign name`  
**SQP:** `Search Query`, `Impressions: Total Count`, `Search Query Score`, `Purchases: Total Count`, `Purchases: Purchase Rate %`, `Clicks: Total Count`, `Reporting Date`  
**Bulk:** `State`, `Campaign name`, `Type`, `Portfolio name`, `Campaign bid strategy`, `Campaign budget amount`, `Impressions`, `Clicks`, `CTR`, `Total cost`, `CPC`, `Purchases`, `Sales`, `ACOS`, `ROAS`  
**Business Report:** `(Parent) ASIN`, `(Child) ASIN`, `Title` (opcional) + `_BR_OPTIONAL_COLS`

---

## 🎨 Paleta de colores Excel

| Variable | Hex | Uso |
|----------|-----|-----|
| NAVY | `1F3864` (Atom) / `0D1B3E` (MS) | Headers principales |
| DGRAY | `424242` (Atom) / `2D3748` (MS) | Sub-headers |
| LGRAY | `F5F5F5` (Atom) / `F7FAFC` (MS) | Filas alternas |
| GRN | `E8F5E9/2E7D32` (Atom) / `C6EFCE/276221` (MS) | Positivo |
| RED | `FFEBEE/C62828` (Atom) / `FFC7CE/9C0006` (MS) | Negativo |
| YEL | `FFF8E1/F57F17` (Atom) / `FFEB9C/9C5700` (MS) | Neutral/warning |
| ORG | `FFE0B2/BF360C` | Advertising / alertas |

**Nota:** Delta arrows usan `^`/`v` en vez de `+`/`-` para evitar que Excel interprete como fórmulas.

---

## 🚧 Pendientes / Roadmap

**Próximo:**
- [ ] Agregar más secciones del PDF al dashboard MerchanSpring (tc_parent_df, sales_by_category, etc.)
- [ ] Mejorar parsing PDF para reportes con layouts distintos

**Futuro (post-aprobación jefe):**
- [ ] Módulo Diseño
- [ ] Módulo Tráfico Externo
- [ ] Módulo Supply Chain
- [ ] Módulo Sales Directors

---

## 💡 Cómo arrancar cada sesión con Claude

1. Pegar este `CLAUDE.md` al inicio del chat
2. Pegar solo el fragmento de código relevante (no todo `app.py`)
3. Indicar qué querés hacer y dónde te quedaste

## 🏗️ Claude Project — instrucciones para pegar en "Project Instructions"
```
Eres mi asistente de desarrollo para el proyecto Amazon PPC Manager de Capybaras Agency.
App Streamlit en Python (~4000 líneas, single file app.py).
Ruta: C:\proyectos\ppc-manager | Comando: python -m streamlit run app.py
Stack: Python + Streamlit + Pandas + OpenPyXL + pdfplumber

Respondé siempre en español.
Seguí el estilo de código existente (snake_case, helpers privados con _prefijo, paleta de colores consistente).
Usá edits quirúrgicos — nunca reescribas funciones completas si el cambio es pequeño.
Ante cualquier duda sobre arquitectura o estado del proyecto, referite al CLAUDE.md adjunto.
Cuando agregues features nuevas, recordame actualizar el CLAUDE.md al final.
```
## 🏗️ Estado de modularización (2026-03-17)

app.py original: 3,974 líneas → actual: ~200 líneas (router + sidebar)

### ✅ Módulos extraídos
- `core/i18n.py` — _I18N (dict ES/EN)
- `core/constants.py` — _BR_OPTIONAL_COLS, _PAGES
- `core/helpers.py` — _color_pct, read_sqp, extract_sqp_brand
- `core/business_report.py` — _BIZ_DIR, _parse_business_report_map, _auto_load_business_report_map
- `modules/atom11/parser.py` — _parse_atom11, _ENTITY_TYPE_LABELS, _detect_atom11_type, _extract_period_df, _summarize_daterange, _split_two_weeks
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

### 🔜 Pendiente
- [ ] Reescribir app.py como router minimal (~100 líneas) — usar High effort
- [ ] Bug: tendencia_multisemana.py KeyError cuando se suben dos SQPs iguales

---

## 📊 Tab: Weekly Client Report (2026-03-17)

**Estado:** ✅ Módulo creado y funcionando

### Inputs (4 archivos, mismo date range 14 días)
| Archivo | Dónde bajarlo | Para qué |
|---------|--------------|---------|
| BR diario 14d | Sales Dashboard → By Date → Sales and Traffic | CUENTA TOTAL con PW/TW |
| BR by Child | By ASIN → Detail Page Sales and Traffic By Child Item | Desglose por ASIN |
| Atom 11 ASIN | Atom 11 → ASIN → DateRange 14 días | Ad Spend/Sales por ASIN, split 7+7 |
| Campaign CSV | Campaign Manager → mismo date range | Impressions/CTR/DPV/NTB |

### Lógica de split
- Atom 11: `TW = dates[-7:]`, `PW = dates[:-7]` — funciona con 13 o 14 fechas
- BR diario: `TW = últimos 7 días`, `PW = anteriores`
- BR by Child: snapshot sin fecha → solo TW, Sales PW muestra `—`
- Campaign CSV: debe bajarse con el mismo date range de 14 días (no lifetime)

### Output Excel 3 hojas
- `📈 WoW Comparison` — fila azul CUENTA TOTAL + desglose por ASIN
  - Columnas: Sales / Units / Sessions / CVR / BuyBox / Ad Sales / Ad Spend / ACoS / TACoS
- `📣 Advertising` — métricas PW vs TW + top 10 camps + alarmas ACoS>60% + portfolios
- `📋 Reporte Ejecutivo` — análisis redactado automático, toggle ES/EN

### Funciones en `modules/pages/weekly_client_report.py`
```python
_parse_br_daily_wow(file)   # BR diario → dict Sales/Units/Sessions/CVR/BuyBox TW+PW
_parse_br_wow(file)         # BR by Child → dict {asin: {Title, Sales, Units, Sessions, CVR, BuyBox}}
_parse_atom11_wow(file)     # Atom 11 wide → dict {asin: {Spend_TW/PW, Sales_TW/PW, Orders_TW/PW}}
_build_weekly_excel(br_tw, br_pw, atom_tw, atom_pw, client_name, lang, br_daily)  # → BytesIO 3 hojas
render()                    # página Streamlit con uploaders + preview + download
```

### Fixes importantes
- `BuyBox_TW = None` cuando el BR diario no tiene esa columna (ej: M&B)
- `_parse_br_daily_wow` detecta automáticamente `Unit Session Percentage` o `Order Item Session Percentage`
- BuyBox con 0 sesiones → se ignora (evita falsos positivos en el ejecutivo)
- `ACoS/TACoS` semáforo invertido (bajar es bueno) en la hoja Advertising

### Clientes probados
- **Love To Dream MX** — 56 ASINs, ACoS 22.7%, TACoS 17.4%, semana +43.9% ventas
- **M&B (Mott & Bow)** — 159 ASINs, ACoS 8.6%, TACoS 5.4%, semana +58.3% ventas
  - BR diario sin columna BuyBox estándar → BuyBox CUENTA TOTAL muestra `—`

---

## 🛡️ MerchanSpring — Estado actual (2026-03-17)

### ✅ Hecho hoy
- Parser PDF completamente defensivo (try/except en cada sección)
- 5 tabs en UI: Summary, Advertising, Inventory & Health, WoW Comparison, Details
- Tab Details muestra: Traffic by Parent/Child, Cancellations, Sales by Category/Country/Brand, BSR, BuyBox Winning/Losing, Shipping, Review Status
- Tab Advertising muestra datos reales si Amazon Ads está conectado en MerchanSpring

### 🔜 Pendiente MerchanSpring
- [ ] WoW Completo PDF — mejorar hoja "📈 WoW Comparison" con:
  Product | ASIN | Sales Δ% | Units Δ% | Sessions Δ% | CVR Δ% | BuyBox% |
  Ad Sales Δ% | Ad Spend Δ% | ACoS | TACoS | Contribution Margin ($) | Contribution Margin (%) | Profit %
  - Contribution Margin = Shipped Sales - Selling Fees - Fulfilment - Advertising
  - Datos a nivel Parent (usando tc_parent_df del parser PDF)
  - Testear con PDF (no XLSX) — el XLSX de Dermaglos no tiene Advertising conectado
- [ ] Fix XLSX parser — IndexError: list index out of range cuando el usuario elige elementos distintos en MerchanSpring
- [ ] Soporte formato NorseTradesman (XLSX custom del AM) — pendiente decisión

## 🗂️ Features en evaluación / Backlog

### 📅 Tab: "Account Pulse" — Monitor de Salud Diaria
**Origen:** Análisis Setex MX, 17/03/2026
**Problema que resuelve:** Contextualizar caídas de ventas sin análisis manual.
**Inputs:** Business Report Daily CSV + Campaign file
**Outputs:** Dashboard + resumen ejecutivo copiable para cliente

**Funcionalidades planeadas:**
1. Gráfico ventas diarias con marcado de fines de semana y festivos MX/USA
2. Comparación semana a semana automática
3. Detección de anomalías (caídas >30% del promedio) con posible causa
4. Tabla semáforo de BuyBox por ASIN
5. Separación campañas nuevas vs antiguas por fecha de inicio
6. Resumen ejecutivo copiable para responder al cliente

---

## 📌 Reglas de trabajo — Flujo de código (2026-03-17)

**IMPORTANTE:** Claude (chat) nunca da código para copiar/pegar manualmente.
Siempre genera **prompts para Claude Code en VS Code** que ejecute los cambios de forma autónoma.

### Flujo correcto
1. Claude (chat) diseña la lógica y redacta el prompt
2. Lenin copia el prompt en Claude Code (VS Code)
3. Claude Code ejecuta los cambios con autonomía absoluta
4. Claude Code confirma qué líneas modificó

### Formato de prompt para Claude Code
- Incluir: ruta exacta del archivo, cambios específicos, sin preguntas, confirmar al terminar
- Nunca pausar por dudas — tomar la decisión más razonable y continuar

---

## 🚧 Pendiente al arrancar próxima sesión (2026-03-17)

### ⚠️ Weekly Client Report — FALTA CONECTAR EN app.py

El módulo existe y funciona:
- `modules/pages/weekly_client_report.py` ✅ — 678 líneas, creado por Claude Code
- Import ya agregado en `app.py` línea 29 ✅

**Faltan 2 cambios en `app.py`** — usar este prompt en Claude Code:
```
Modificar app.py en C:\proyectos\ppc-manager

Hacer exactamente estos 2 cambios sin tocar nada más:

1. Encontrar la línea del sidebar que contiene el for loop con "Reportes Atom 11"
   y "Reportes MerchanSpring". Agregar "📊 Weekly Client Report" al final de esa
   lista, antes del corchete de cierre ].

2. Al final del archivo, después del último bloque "if selected ==", agregar:

if selected == "📊 Weekly Client Report":
    render_weekly()

No crear archivos nuevos. No modificar nada más. Solo esos 2 cambios en app.py.
Confirmar qué líneas modificaste al terminar.
```

**Después de aplicar:** correr la app y verificar que aparece "📊 Weekly Client Report" en el sidebar.

### Estado de módulos
- `modules/pages/weekly_client_report.py` ✅ creado
- `app.py` import ✅ línea 29
- `app.py` sidebar ❌ falta agregar tab
- `app.py` routing ❌ falta `if selected ==`

### Git pendiente
```bash
git add .
git commit -m "feat: Weekly Client Report — módulo completo + routing app.py"
git push
```