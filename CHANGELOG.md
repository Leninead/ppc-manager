# CHANGELOG — Agency OS Capybaras

Registro de cambios, mejoras y decisiones de diseño del PPC Manager.

---

## [Unreleased]

### Added
- **Variation Builder (M26)** — módulo nuevo en Account Manager. Generador de flat files Amazon con variaciones (parent + N children). 913 líneas, parser dinámico soporta hasta 220 columnas. Agrupa por variation_theme (Sabor, Nombre del Tamano, Scent, FlavorName-SizeName, Tamano del Sabor, Nombre del Patron). Preserva macros VBA y 10 hojas del template. v1 solo MX (MXN). Tested end-to-end con Pet Food real.
- **Gamboa Generator (M25)** — módulo nuevo en Account Manager. Reportes HTML integrales combinando SQP mensual + BR semanal. Dashboard interactivo con filtros runtime, agregaciones por mes, comparación WoW. Categorización persistente de keywords por cliente. 5 archivos: `modules/gamboa/__init__.py`, `parsers.py` (421L), `generator.py` (278L), `template.html` (874L/64KB), `modules/pages/gamboa_generator.py` (383L).
- **Campaign Builder v2.0 — Sprint 1: SBV/SBH rewrite** — nuevo flujo 4-pasos para crear campañas Sponsored Brand 2026. Selector SBV (video) vs SBH (headline). Brand Entity ID obligatorio. Video Asset ID (SBV) / Brand Logo Asset ID + Logo Crop (SBH). 29 columnas bulk SB 2026. Validaciones estrictas bloqueantes. Nombre Capybaras hardcoded preservado (contrato con M11 Atom11 Rules Builder). Parsing de Plan de Acción como input. Testing: SBV end-to-end ✅.

### Fixed
- **Bulk Amazon 2026 compliance** — incrementadas columnas de 30 a 31. Agregado helper `_fila_vacia_bulk()` en `campaign_builder.py` para generar filas con todos los campos. Validación en Batch ID `cee6c2f5-520f-45d2-b769-c70f49e95776` (21/04/2026, flujo asíncrono).
- **Streamlit Markdown LaTeX gotcha** — patrón `**${variable}**` en `st.info/markdown/error/warning/success` rompe render (Streamlit interpreta `$` como delimitador LaTeX). Fix: escapar con `\\$` o envolver negrita alrededor de frase completa. Aplicado en 3 líneas de `modules/pages/campaign_builder.py` (L245, L480, L896).

### Changed
- `modules/pages/campaign_builder.py` — rewrite `_render_sb()`: 864 → 1121 líneas (+257 netas). Nuevos helpers: `_SB_COLS_2026` (29 cols), `_sb_row_factory()`, `_build_sb_bulk_rows()`. Flujo SBV vs SBH con campos específicos por tipo.

### Documentation
- `CLAUDE.md` — Sesión 2026-04-23 documentada con detalle técnico de Sprint 1, bugs conocidos (sub-agent alucinaciones, LaTeX gotcha), decisiones de arquitectura.
- `modules/pages/CLAUDE.md` — M10 Campaign Builder reescrito con helpers SB 2026 y contrato con M11. M25 Gamboa Generator agregado.
- `SOP_Uso_AgencyOS.md` — v3.3: flujo M10 con Paso 0 selector SBV/SBH, campos específicos por tipo.
- `sopppcmanagerdefinitivo.md` — sección Campaign Builder con tabla de versiones, subsección SB v2.0 completa con 29 columnas y validaciones.

---

## v3.3 — 22 Apr 2026
**Gamboa Generator integrado + Sprint 1 Campaign Builder**

### Added
- Gamboa Generator — reportes HTML integrales
- Campaign Builder SBV/SBH (Sprint 1)
- 31 columnas bulk Amazon 2026

### Fixed
- LaTeX markdown gotcha (3 líneas)
- Bulk compliance validado

---

## v3.2 — 15 Apr 2026
**Deploy + Equipo onboarding**

### Added
- Deploy live en capybaras-os.streamlit.app
- 21 usuarios del equipo en secrets.toml
- Expanders de ayuda en 15/15 módulos
- Login con streamlit-authenticator

### Fixed
- Python 3.11 f-string backslash (weekly_client_report.py L917)
- requirements.txt: agregado requests + beautifulsoup4

---

## v3.1 — 09 Apr 2026
**Listing Monitor + module-architecture-standard mejorado**

### Added
- Listing Monitor (M23) — scraper Amazon + alertas precio/rating/stock
- 3 agentes v3 con frontmatter: ppc-module-builder, excel-export-builder, ui-designer

### Changed
- Sidebar colapsable con expanders por sección (PPC/Research/Account/Knowledge)

---

## v3.0 — 27 Mar 2026
**8 módulos Research/Account conectados + mejoras visuales**

### Added
- DataDive Analyzer (M11) — 4 tabs: MKL, Competitors matrix, Rank Radar, Volatility
- Helium 10 Analyzer (M12) — 3 tabs: Cerebro, KW Research, Competitor Gap
- SBH Recommendation (M13) — targets para Sponsored Brand Headline
- Knowledge Base (M22) — explorar + agregar notas .md
- PPC Insights (M14) — health score 0-100 por ASIN
- PPC Forecast (M15) — proyección ventas + estacionalidad
- PPC Audit (M16) — auditoría integral score 0-100
- Account Pulse (M17) — monitor salud diaria + festivos MX

### Changed
- 48 st.metric migrados a kpi_card helper
- 14 empty states reemplazados por visual cards
- 8 headers unificados con layout flex
- Color coding en 6 tablas (DataDive, H10, SBH, etc.)
- Inicio v3.0 — 22 módulos visualizados

### Documentation
- Agentes v2.0 creados (9 agentes Sonnet/Haiku/Opus con skills asignados)
- Skills core: ppc-reporting-standard.md, module-architecture-standard.md, client-communication-tone.md
- modules/pages/CLAUDE.md — 22 secciones por módulo

---

## v2.0 — 23 Mar 2026
**Atom11 Rules Builder v2026.2 AGRESIVO**

### Added
- Atom11 Rules Builder (M21) — módulo con 274 rules dinámicas
- Campaign classification en 11 grupos por objetivo (DISCOVERY/RANKING/etc.)
- Thresholds v2026.2 AGRESIVO (DEC HARD = PAUSE TARGET)

### Changed
- 6 rules RANKING SP creadas en Atom11 real (cliente Dermaglos)
- Rules viejas v1 pausadas (14 RANKING + 10 DEFENSIVE)

---

## v1.5 — 21 Mar 2026
**Campaign Builder + Bid Optimizer + UI rediseño**

### Added
- Campaign Builder (M10) — generador campañas con Plan de Acción input
- Bid Optimizer (M9) — calculadora bids con CVR × precio × target ACoS
- Plan de Acción tab en Análisis Cruzado (M4)
- Campaign Analyzer en Bulk Campañas (diagnóstico semáforo)

### Changed
- Sidebar rediseñado oscuro (#1A1A1A, naranja #E84000)
- Página Inicio rediseñada (9 áreas Agency OS, ownership, flujo PPC)

---

## v1.0 — 18 Mar 2026
**Arquitectura modularizada completa + 22 módulos**

### Modules
- 22 módulos en modules/pages/ (inicio, STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11, MerchanSpring, Weekly, Bid Optimizer, Campaign Builder, Atom11 Rules)
- Sidebar categorizado: PPC (expanded) | Research | Account | Knowledge
- Router app.py minimal (~200 líneas)

---

## v0.5 — 01 Mar 2026
**Primeros 8 módulos + setup inicial**

### Added
- Stack: Python + Streamlit + Pandas + OpenPyXL + pdfplumber
- Setup CI/CD: no test suite, no linter (custom SOP)
- Primeros módulos: STR, SQP, Bulk, BR, Cruzado, Tendencia, Funnel, Atom11

---

**Formato:** Keep a Changelog (https://keepachangelog.com/)
**Agencia:** Capybaras Agency | **Dev:** Lenin Acosta | **Última actualización:** 2026-04-26
