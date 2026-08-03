# 🦫 SOP — Uso del Capybaras Agency OS

**Versión:** v3.3 — Abril 2026
**Dev:** Lenin Acosta
**Módulos activos:** 25

Guía operativa para usar el Agency OS semana a semana. Cubre flujo diario, uso módulo por módulo y tabla de archivos fuente.

---

## 🗓️ Flujo semanal recomendado

El flujo está diseñado para que cada día consuma los outputs del anterior. Respetá el orden.

### Lunes — Diagnóstico de search terms
1. **Search Term Report (M2)** — bajá STR de 30 días, corré Negatives Mining + Harvest
2. **Search Query Performance (M3)** — bajá SQP de la semana, analizá Market Share y gaps
3. **Análisis Cruzado STR vs SQP (M4)** — cruzá ambos, generá Plan de Acción

**Resultado del día:** listas de negativos + keywords a harvestear + Plan de Acción bulk.

### Martes — Contexto histórico y estructura
1. **Tendencia Multi-Semana (M5)** — cargá 2-4 SQPs para detectar estacionalidades
2. **Bulk Campañas + Campaign Analyzer (M6)** — bajá Campaign CSV, corré semáforo PAUSAR/REVISAR/ESCALAR

**Resultado del día:** mapa de tendencias + lista de campañas a pausar/escalar manualmente.

### Miércoles — Optimización y ejecución
1. **Bid Optimizer (M9)** — recalculá bids con CVR real + precio + target ACoS
2. **Campaign Builder (M10)** — usá el Plan de Acción del lunes como input, generá bulk listo para subir

**Resultado del día:** bulk de bids ajustados + bulk de campañas nuevas listos para upload.

### Jueves — Negocio y funnel
1. **Business Report (M7)** — bajá BR by ASIN, validá CVR, BuyBox y ventas por producto
2. **Análisis de Funnel (M8)** — detectá brechas Auto→Broad→Phrase→Exact y sugerí campañas

**Resultado del día:** validación de salud del catálogo + funnel completo por ASIN.

### Viernes — Reportes al cliente
1. **Reportes Atom 11 (M12)** — procesá reportes WoW/MoM de la semana
2. **Reportes MerchanSpring (M13)** — si el cliente usa MS, procesá el PDF/XLSX
3. **Weekly Client Report (M14)** — generá el Excel ejecutivo con changelog
4. **Account Pulse (M17)** — monitor de salud diaria con deltas y festivos MX

**Resultado del día:** reporte semanal enviado al cliente con changelog + salud de cuenta.

### Ocasional (cada 2-4 semanas)
1. **Listing Monitor (M15)** — revisá snapshots de ASINs clave (precio, rating, stock, badges)
2. **Gamboa Generator (M16)** — generá HTML integral para cliente (SQP mensual + BR semanal)

> **Research + Inteligencia + Knowledge:** módulos de uso ad-hoc según la marca y el proyecto (no son del flujo semanal fijo).

---

## 📋 Los 25 módulos — Uso detallado

### SECCIÓN: 📊 PPC (10 módulos)

---

## M1 — 🏠 Inicio

- 🎯 **Para qué sirve:** Dashboard del Agency OS con estado de 25 módulos, Workflow Wizard piramidal y changelog.
- 📂 **Archivo que necesitás:** Ninguno. Opcional: Business Report en `data/business_report/` para cargar Parent-Child map al iniciar.
- ▶️ **Pasos:**
  1. Abrí la app: `python -m streamlit run app.py`
  2. La página Inicio es la default
  3. Revisá el estado del Parent-Child map (verde/naranja)
  4. Leé el changelog para saber qué cambió
  5. Seguí el Workflow Wizard si es tu primera vez
- 📤 **Output:** Panorama de módulos y flujo guiado.
- ➡️ **Siguiente paso:** Search Term Report (M2) para arrancar el flujo semanal.

---

## M2 — 📊 Search Term Report (STR)

- 🎯 **Para qué sirve:** Analizar search terms de campañas SP para negativizar, harvestear y clasificar por estado. 5 tabs: General | Negatives Mining | Harvest Candidates | Análisis IA | Por Campaña.
- 📂 **Archivo que necesitás:** STR → Amazon Ads → Reports → Advertising Reports → SP Search Term (.xlsx o .csv, 30 días).
- ▶️ **Pasos:**
  1. Subí el STR
  2. Ingresá precio promedio del producto + brand terms + Target ACoS
  3. Revisá Tab 1 (12 KPIs), Tab 2 (Negatives), Tab 3 (Harvest con anti-canibalización)
  4. Opcional: subí Campaign CSV en Tab 3 para cruzar con Exact activos
  5. Descargá bulk de negativos y/o harvest
- 📤 **Output:** Bulk Amazon con negative keywords + bulk con harvest keywords + Excel multi-sheet.
- ➡️ **Siguiente paso:** Search Query Performance (M3) para validar contra datos del mercado.

---

## M3 — 🔍 Search Query Performance (SQP)

- 🎯 **Para qué sirve:** Medir market share, detectar gaps y oportunidades contra el mercado de Brand Analytics. 4 tabs: General | Market Share | Gap Analysis | Análisis IA.
- 📂 **Archivo que necesitás:** SQP → Brand Analytics → Search Query Performance (.xlsx semanal).
- ▶️ **Pasos:**
  1. Subí el SQP
  2. Confirmá o ingresá la marca detectada
  3. Revisá Dashboard, Market Share (Dominando/Competitivo/Oportunidad)
  4. En Gap Analysis detectá queries con alto volumen donde no aparecés
  5. Descargá tabla de gaps
- 📤 **Output:** Lista de queries con IS < 10% y purchase rate alto = oportunidades.
- ➡️ **Siguiente paso:** Análisis Cruzado STR vs SQP (M4).

---

## M4 — 🔗 Análisis Cruzado STR vs SQP

- 🎯 **Para qué sirve:** Cruzar lo que pasa en tus campañas (STR) contra lo que pasa en el mercado (SQP) y generar un Plan de Acción accionable. 3 tabs: Cruce | Plan de Acción | PPC Insights por ASIN.
- 📂 **Archivo que necesitás:** STR (.xlsx) + SQP (.xlsx). Opcional: BR by ASIN (.csv) para Tab 3.
- ▶️ **Pasos:**
  1. Subí STR y SQP
  2. Ingresá brand terms + Target ACoS
  3. Tab Cruce: revisá "En ambos", "Solo STR", "Solo SQP"
  4. Tab Plan de Acción: revisá columna Acción (AGREGAR / HARVEST / BAJAR BID / ESCALAR / MONITOREAR)
  5. Descargá Plan de Acción bulk
- 📤 **Output:** Plan de Acción bulk (input directo del Campaign Builder) + tabla de acciones priorizadas.
- ➡️ **Siguiente paso:** Campaign Builder (M10) para ejecutar, o Tendencia Multi-Semana (M5) para contexto.

---

## M5 — 📈 Tendencia Multi-Semana

- 🎯 **Para qué sirve:** Ver evolución de queries a lo largo de 2-4 semanas para detectar estacionalidades y cambios de demanda.
- 📂 **Archivo que necesitás:** 2 a 4 archivos SQP de semanas distintas (.xlsx).
- ▶️ **Pasos:**
  1. Subí entre 2 y 4 SQPs
  2. Confirmá el orden cronológico
  3. Revisá pivot por Search Query con tendencias ↑ → ↓
  4. Filtrá por threshold de cambio (10% default)
  5. Descargá el Excel con tendencias
- 📤 **Output:** Pivot con queries clasificadas Creciendo / Estable / Cayendo.
- ➡️ **Siguiente paso:** Bulk Campañas (M6) para ver cómo responden las campañas.

---

## M6 — 📁 Bulk Campañas + Campaign Analyzer

- 🎯 **Para qué sirve:** Ver estructura de campañas y diagnosticar estado con semáforo automático (pausar/revisar/escalar/fantasmas). 3 tabs: General | Campaign Analyzer | Auditoría PPC.
- 📂 **Archivo que necesitás:** Campaign CSV → Amazon Ads → Campaign Manager → Export con todas las métricas (.csv).
- ▶️ **Pasos:**
  1. Subí el Campaign CSV
  2. Ingresá Target ACoS + precio promedio
  3. Tab Campaign Analyzer: revisá semáforo (PAUSAR, REVISAR, ESCALAR, FANTASMA)
  4. Tab Auditoría: revisá naming convention y target graduation
  5. Descargá el Excel y pausá manualmente en Campaign Manager las rojas
- 📤 **Output:** Semáforo de campañas + lista de campañas fantasma + score de salud.
- ➡️ **Siguiente paso:** Business Report (M7) para cruzar con salud del catálogo.

---

## M7 — 💰 Business Report

- 🎯 **Para qué sirve:** Ver ventas, sesiones, CVR y BuyBox por ASIN. Es la fuente del Parent-Child map.
- 📂 **Archivo que necesitás:** Business Report → Seller Central → Reports → Business Reports → By Date o By ASIN (.csv).
- ▶️ **Pasos:**
  1. Subí el BR (By Date o By ASIN)
  2. Revisá métricas por ASIN (Sales, Sessions, CVR, BuyBox)
  3. Identificá ASINs con CVR bajo o BuyBox < 80%
  4. Guardá el BR en `data/business_report/` para cargar Parent-Child automáticamente
  5. Descargá el resumen si hace falta
- 📤 **Output:** Tabla por ASIN con métricas de venta + Parent-Child map actualizado.
- ➡️ **Siguiente paso:** Análisis de Funnel (M8).

---

## M8 — 🔻 Análisis de Funnel

- 🎯 **Para qué sirve:** Detectar brechas en el funnel Auto → Broad → Phrase → Exact por ASIN y sugerir campañas faltantes.
- 📂 **Archivo que necesitás:** STR (.xlsx/.csv) + Bulk file de campañas (.xlsx).
- ▶️ **Pasos:**
  1. Subí STR y Bulk
  2. Ingresá Target ACoS
  3. Revisá mapa de funnel actual por ASIN
  4. Revisá campañas sugeridas con naming Capybaras
  5. Descargá bulk con nuevas campañas
- 📤 **Output:** Mapa de funnel por ASIN + bulk con campañas que cierran brechas.
- ➡️ **Siguiente paso:** Bid Optimizer (M9).

---

## M9 — 🧠 Bid Optimizer

- 🎯 **Para qué sirve:** Calcular el bid óptimo por keyword usando CVR real, precio y target ACoS. Fórmula: `bid = CVR × precio × target_ACoS`. 2 tabs: Bids | Placements & Budget.
- 📂 **Archivo que necesitás:** STR (.xlsx/.csv). Opcional: Inventory Report (.txt) para precio exacto.
- ▶️ **Pasos:**
  1. Subí STR y opcionalmente Inventory Report
  2. Ingresá Target ACoS y precio default
  3. Revisá semáforo: SUBIR / OK / BAJAR / PAUSAR
  4. Tab Placements & Budget: referencia SOP por tipo de campaña
  5. Descargá bulk con bids modificados
- 📤 **Output:** Bulk Amazon con columna Max Bid actualizada.
- ➡️ **Siguiente paso:** Campaign Builder (M10).

---

## M10 — 🚀 Campaign Builder

- 🎯 **Para qué sirve:** Generar bulk listo para subir a Amazon con campañas SP/SB/SD nuevas clusterizadas por intención. SB reescrito en Sprint 1 (2026-04-23) con soporte SBV + SBH + Brand Entity ID.
- 📂 **Archivo que necesitás:** Plan de Acción bulk (output del M4, .xlsx).
- ▶️ **Pasos:**
  1. Subí el Plan de Acción bulk
  2. Seleccioná tipo: SP / SB / SD (radio button)
  3. **Para SB:** elegí SBV o SBH (Paso 0) → ingresá datos producto + Brand Entity ID (Paso 2) → creatividad (Paso 3: Video Asset ID para SBV, Brand Logo Asset ID + Crop para SBH)
  4. Revisá preview de campañas clusterizadas con validación estricta
  5. Descargá bulk formato exacto Amazon (29 columnas para SB)
- 📤 **Output:** Bulk .xlsx listo para subir a Campaign Manager → Bulk Operations.
- ➡️ **Siguiente paso:** Atom11 Rules Builder (M11) para automatizar las nuevas.

> ⚠️ **SB — Campos obligatorios:** Brand Entity ID (sin él Amazon rechaza el bulk), Video Asset ID (SBV) o Brand Logo Asset ID + Logo Crop Square/Rectangle (SBH), Brand Name, Creative Headline, 3 ASINs creativos. El módulo muestra lista de errores bloqueante si falta alguno.

> ⚠️ **El naming Capybaras está hardcoded** — NO modificar el formato. Es un contrato con Atom11 Rules Builder (M11) que parsea el Campaign Name para clasificar en DISCOVERY/RANKING/CONQUEST.

---

## M11 — ⚙️ Atom11 Rules Builder

- 🎯 **Para qué sirve:** Generar rules de automatización para Atom11 (274 rules) con thresholds dinámicos por tier y objetivo.
- 📂 **Archivo que necesitás:** Campaign CSV (.csv) + tabla de ASINs con precio (input manual).
- ▶️ **Pasos:**
  1. Tab Config: ingresá prefijo marca, brand terms, target ACoS cuenta y ASINs con precio
  2. Tab Campaign Groups: subí Campaign CSV y revisá clasificación en 7 objetivos
  3. Tab Rules Generator: preview de 274 rules con thresholds por tier
  4. Editá thresholds si hace falta
  5. Descargá Excel multi-sheet para importar a Atom11
- 📤 **Output:** Excel con Campaign Groups + Excel con 274 rules importables.
- ➡️ **Siguiente paso:** Reportes Atom 11 (M12) para medir resultados.

---

### SECCIÓN: 👥 Account Manager (6 módulos)

---

## M12 — 🔬 Reportes Atom 11

- 🎯 **Para qué sirve:** Procesar reportes de Atom 11 (WoW/MoM/DateRange) con KPIs comparativos y branding Capybaras.
- 📂 **Archivo que necesitás:** Reporte Atom 11 → Atom 11 → Reports → Export (.xlsx). 1 o 2 archivos.
- ▶️ **Pasos:**
  1. Subí 1 archivo (WoW/MoM) o 2 archivos (cross-file)
  2. Confirmá detección automática de tipo (ASIN/Portfolio/Keyword)
  3. Toggle ES/EN según el cliente
  4. Revisá KPIs, diagnóstico y recomendaciones
  5. Descargá Excel multi-sheet con branding
- 📤 **Output:** Excel 3-4 hojas (Informe Cliente + KPIs + Datos + Parent Evolution opcional).
- ➡️ **Siguiente paso:** Reportes MerchanSpring (M13) o Weekly Client Report (M14).

---

## M13 — 🛡️ Reportes MerchanSpring

- 🎯 **Para qué sirve:** Procesar reportes MerchanSpring (.xlsx o .pdf) en Excel estructurado con branding.
- 📂 **Archivo que necesitás:** MerchanSpring → Reports → Export (.xlsx o .pdf).
- ▶️ **Pasos:**
  1. Subí el archivo (el sistema detecta formato)
  2. Revisá 5 tabs: Summary / Advertising / Inventory & Health / WoW / Details
  3. Validá parsers defensivos (algunas secciones pueden estar vacías)
  4. Opcional: cruzá con Atom 11 del mismo período
  5. Descargá Excel 4 hojas
- 📤 **Output:** Excel con Summary + Advertising + Inventory + WoW Comparison.
- ➡️ **Siguiente paso:** Weekly Client Report (M14).

---

## M14 — 📊 Weekly Client Report

- 🎯 **Para qué sirve:** Generar reporte semanal para el cliente con comparación WoW automática + changelog técnico. 4 hojas: WoW Comparison | Advertising | Reporte Ejecutivo | Changelog.
- 📂 **Archivo que necesitás:** BR daily 14d (.csv) + BR by Child (.csv) + Atom11 ASIN 14d (.xlsx) + Campaign CSV (.csv).
- ▶️ **Pasos:**
  1. Subí los 4 archivos
  2. Ingresá nombre del cliente y toggle ES/EN
  3. El sistema splitea automáticamente PW/TW
  4. Escribí el changelog en el text_area
  5. Descargá Excel 4 hojas + botón "Copiar Changelog para Slack"
- 📤 **Output:** Excel (WoW + Advertising + Ejecutivo + Changelog) + texto Slack copiable.
- ➡️ **Siguiente paso:** Account Pulse (M17) para monitor de salud continuo.

---

## M15 — 👁️ Listing Monitor

- 🎯 **Para qué sirve:** Monitorear ASINs de Amazon y alertar cambios en precio, rating, stock, badges vs snapshot anterior. Scraping directo sin API key.
- 📂 **Archivo que necesitás:** Ninguno. Input: ASINs + marketplace.
- ▶️ **Pasos:**
  1. Tab Escanear: ingresá ASINs (separados por salto de línea)
  2. Seleccioná marketplace (MX/COM/ES/BR/CA)
  3. Configurá delay (8-10 segundos recomendado)
  4. Clickeá "Escanear" — guardá snapshot automáticamente
  5. Tab Alertas y Historial para ver cambios
- 📤 **Output:** Snapshots con precio, rating, stock, badges, título. Alertas por cambio.
- ➡️ **Siguiente paso:** Gamboa Generator (M16) o volver a flujo semanal.

---

## M16 — 📊 Gamboa Generator

- 🎯 **Para qué sirve:** Generar reportes HTML integrales tipo dashboard interactivo con SQP mensual + BR semanal. Listo para publicar en Hostinger o enviar al cliente.
- 📂 **Archivo que necesitás:** SQP multi-archivo (.xlsx) + BR semanal by ASIN (.xlsx/.csv). Opcional: Inventory Report.
- ▶️ **Pasos:**
  1. Subí SQP(s) — auto-detecta mes
  2. Subí BR semanal(s) — auto-detecta semana ISO
  3. Opcional: subí Inventory Report para mapeo SKU↔ASIN
  4. Opcional: subí o generá CSV categorías
  5. Descargá HTML (~5-10 MB) y publicá en Hostinger
- 📤 **Output:** HTML standalone con 2 paneles interactivos: Panel SQP (15 meses) + Panel WoW Category (68 semanas).
- ➡️ **Siguiente paso:** Volver a flujo semanal.

---

### SECCIÓN: 🧠 Intelligence (4 módulos)

---

## M17 — 📊 Account Pulse

- 🎯 **Para qué sirve:** Monitor de salud diaria con deltas WoW, festivos MX y detección de anomalías.
- 📂 **Archivo que necesitás:** BR Daily 14d (.csv) + BR by Child (opcional) + Campaign CSV (opcional).
- ▶️ **Pasos:**
  1. Subí BR daily (mínimo 14 días)
  2. Opcional: BR by Child + Campaign CSV
  3. Revisá portada naranja con KPIs + mensaje Slack
  4. Revisá ventas diarias (laboral/finde/festivo MX) y anomalías (caídas >30%)
  5. Descargá Excel 4 hojas (Resumen + Ventas + BuyBox + Campañas)
- 📤 **Output:** Excel con portada ejecutiva + mensaje copiable para Slack/cliente.
- ➡️ **Siguiente paso:** Weekly Client Report (M14) si no lo generaste ya.

---

## M18 — 🔎 PPC Insights Engine

- 🎯 **Para qué sirve:** Health score 0-100 por ASIN cruzando STR + SQP + BR + Campaign CSV.
- 📂 **Archivo que necesitás:** STR (requerido). Opcional: SQP, BR by ASIN, Campaign CSV.
- ▶️ **Pasos:**
  1. Subí STR (mínimo) + archivos opcionales para score confiable
  2. Ingresá brand terms + Target ACoS
  3. Revisá cards por ASIN con expanders (STR, SQP, BR, Campañas)
  4. Identificá bleeders (gasto sin conversión) y top keywords
  5. Descargá Excel multi-sheet con hasta 10 hojas por ASIN
- 📤 **Output:** Health score por ASIN (🟢 ≥80 / 🟡 60-79 / 🔴 <60) + Excel detallado.
- ➡️ **Siguiente paso:** PPC Forecast (M19) o PPC Audit (M20).

---

## M19 — 📈 PPC Forecast

- 🎯 **Para qué sirve:** Proyección de ventas a 7/14/30 días con tendencia lineal + estacionalidad finde/laboral.
- 📂 **Archivo que necesitás:** Business Report diario (.xlsx/.csv) — mínimo 14 días, ideal 30+.
- ▶️ **Pasos:**
  1. Subí BR diario
  2. Elegí horizonte de proyección (7/14/30d)
  3. Revisá gráfico histórico + proyección con 3 escenarios
  4. Revisá budget recommendation
  5. Descargá Excel 2 hojas
- 📤 **Output:** Proyección de ventas + budget recomendado + gráfico.
- ➡️ **Siguiente paso:** PPC Audit (M20).

---

## M20 — 🛡️ PPC Audit Pro

- 🎯 **Para qué sirve:** Auditoría profunda desde Bulk File multi-hoja con breakdown real SP/SB/SD, 10 segmentos y 5 deep checks.
- 📂 **Archivo que necesitás:** Bulk File → Campaign Manager → Bulk Operations → Download (.xlsx multi-hoja). Opcional: BR para TACoS.
- ▶️ **Pasos:**
  1. Subí Bulk File + opcionalmente BR
  2. Ingresá brand terms
  3. Revisá Tab 1 (KPIs Overview), Tab 2 (Estructura), Tab 3 (Performance 10 segmentos)
  4. Revisá Tab 4 Deep Checks (Top 5, Clasificación, Duplicación, Bid Adjustments, SKAG/Bolsa)
  5. Tab 5 Target Graduation: subir bid / pausar / graduar a SKAG
  6. Descargá Excel 6 hojas
- 📤 **Output:** Auditoría integral 0-100 + lista de targets a graduar + Excel 6 hojas.
- ➡️ **Siguiente paso:** Account Pulse (M17).

---

### SECCIÓN: 🔬 Research (7 módulos)

---

## M21 — 🧲 DataDive Analyzer

- 🎯 **Para qué sirve:** Procesar reportes DataDive: MKL keywords, competitors matrix, rank radar y volatilidad. 5 tabs: MKL | Competitors | Rank Radar | Volatility | Competitor Intel.
- 📂 **Archivo que necesitás:** DataDive → Niche → Keywords / Competitors / Rank Radar (.xlsx).
- ▶️ **Pasos:**
  1. Tab 1 MKL: subí niche-keywords y ajustá filtros SV + relevance
  2. Tab 2 Competitors: subí niche-competitors y compará contra Niche Median
  3. Tab 3 Rank Radar: subí [product].xlsx y revisá tendencia por keyword
  4. Tab 4 Volatility: cruzá con SQP para PPC Impression Share
  5. Tab 5 Competitor Intel: subí tu MKL + MKL competidor
- 📤 **Output:** Keyword gaps, comparación contra mercado, tracking de ranking, oportunidades de reducir spend.
- ➡️ **Siguiente paso:** Helium 10 Analyzer (M22) para cross-validation.

---

## M22 — 🧲 Helium 10 Analyzer

- 🎯 **Para qué sirve:** Procesar Cerebro (reverse ASIN) para KW research, competitor gap y oportunidades PPC. 3 tabs: Cerebro | KW Research | Competitor Gap.
- 📂 **Archivo que necesitás:** Helium 10 → Cerebro → Reverse ASIN (.xlsx). 1-3 archivos.
- ▶️ **Pasos:**
  1. Tab 1: subí 1 Cerebro de tu ASIN, ajustá filtros SV/Organic Rank/IQ Score
  2. Tab 2: subí 1-3 Cerebros de competidores para Launch Priority Score
  3. Tab 3 Competitor Gap: tu Cerebro vs 1-2 competidores, acción ATACAR/MONITOREAR/IGNORAR
  4. En Tab 3 usá "Exportar como Plan de Acción" si querés pipeline a Campaign Builder
  5. Descargá los packs
- 📤 **Output:** KW Research Pack, gap analysis con acciones, Plan de Acción compatible con M10.
- ➡️ **Siguiente paso:** SBH Recommendation (M23) o Campaign Builder (M10).

---

## M23 — 📢 SBH Target Recommendation

- 🎯 **Para qué sirve:** Recomendar keywords target para Sponsored Brand Headline cruzando MKL + SQP + Campaign CSV.
- 📂 **Archivo que necesitás:** DataDive MKL (.xlsx) + SQP (.xlsx). Opcional: Campaign CSV.
- ▶️ **Pasos:**
  1. Subí MKL y SQP
  2. Opcional: subí Campaign CSV para filtrar keywords ya en SP
  3. Revisá prioridad ALTA/MEDIA/BAJA
  4. Revisá clustering + headline sugerido por cluster
  5. Descargá SBH Target Pack multi-sheet
- 📤 **Output:** Lista de targets SBH priorizados con clusters y headlines sugeridos.
- ➡️ **Siguiente paso:** Campaign Builder (M10) con tipo SB.

---

### SECCIÓN: 📚 Knowledge (1 módulo)

---

## M24 — 📚 Knowledge Base

- 🎯 **Para qué sirve:** Repositorio de notas y aprendizajes del equipo. Buscar, filtrar y crear notas .md.
- 📂 **Archivo que necesitás:** Archivos .md o .txt (notas existentes o nuevas).
- ▶️ **Pasos:**
  1. Tab Explorar: subí notas .md
  2. Buscá por texto, filtrá por tags y categorías (ppc / amazon / ai / strategy / client)
  3. Tab Agregar: completá formulario con headers + tags + categoría
  4. Previsualizá antes de descargar
  5. Descargá como .md y guardá en `notes/knowledge/`
- 📤 **Output:** Notas indexadas + archivo .md listo para commitear al repo.
- ➡️ **Siguiente paso:** Volver a Inicio o al módulo correspondiente al proyecto actual.

---

## 📦 Guía rápida de archivos fuente

| Archivo | Herramienta | Dónde bajarlo | Formato |
|---------|-------------|---------------|---------|
| STR (Search Term Report) | Amazon Ads | Reports → Advertising Reports → SP Search Term | .xlsx / .csv |
| SQP (Search Query Performance) | Amazon Brand Analytics | Brand Analytics → Search Query Performance | .xlsx |
| Campaign CSV | Amazon Ads | Campaign Manager → Columns: todas → Export | .csv |
| Bulk File | Amazon Ads | Campaign Manager → Bulk Operations → Download | .xlsx multi-hoja |
| Business Report (By Date) | Seller Central | Reports → Business Reports → By Date → Sales and Traffic | .csv |
| Business Report (By ASIN) | Seller Central | Reports → Business Reports → By ASIN → Detail Page Sales | .csv |
| Inventory Report | Seller Central | Manage Inventory → Export | .txt / .csv |
| Atom 11 Report | Atom 11 | Reports → WoW / MoM / DateRange → Export | .xlsx |
| MerchanSpring Report | MerchanSpring | Reports → Weekly / Monthly → Export | .xlsx / .pdf |
| DataDive MKL (niche keywords) | DataDive | Niche → Keywords → Export | .xlsx |
| DataDive Competitors | DataDive | Niche → Competitors → Export | .xlsx |
| DataDive Rank Radar | DataDive | Rank Radar → [Product] → Export | .xlsx |
| Helium 10 Cerebro | Helium 10 | Cerebro → Reverse ASIN → Export | .xlsx |
| Plan de Acción bulk | Agency OS | Output del Análisis Cruzado (M4) | .xlsx |

---

## 🗺️ Roadmap Campaign Builder v2.0 — Sprints

| Sprint | Feature | Estado | Fecha |
|--------|---------|--------|-------|
| 1 | Rewrite `_render_sb()` — SBV + SBH + Brand Entity ID + 29 columnas Amazon Ads API 2026 | ✅ Completado | 2026-04-23 |
| 2 | Modo B simplificado — XLSX custom + `st.data_editor` para input manual de keywords | Pendiente | — |
| 3 | DaypartingApp — módulo nuevo en Account Manager para ajustes de bid por hora/día | Pendiente | — |

> **Decisión arquitectónica registrada (2026-04-23):** Los bloques dinámicos de naming propuestos en el HTML del PPC compañero fueron descartados. El naming Capybaras hardcoded es un contrato con Atom11 Rules Builder (M11) que parsea el Campaign Name para clasificar en DISCOVERY/RANKING/CONQUEST/etc. Modificarlo rompe la automatización completa.
