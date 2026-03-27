---
name: Project Architecture Status
description: Module structure, routing, naming conventions, and session state keys
type: reference
---

## Verified at 2026-03-26

### Compilation Status
- **Result:** ALL 38 Python files compile successfully
- **Syntax errors:** NONE
- **Import errors:** NONE (all internal imports verified)

### Routing Verification
- **Pages in _PAGES:** 17 (core/constants.py)
- **Routes in app.py:** 18 (includes "📊 Weekly Client Report")
- **Status:** MISMATCH — Weekly Client Report not in _PAGES but routed in app.py
- **Fix required:** Add "📊 Weekly Client Report" to _PAGES list in core/constants.py line 9-27

### All 18 Pages
| Order | Page | Module | Route Status |
|-------|------|--------|--------------|
| 1 | 🏠 Inicio | inicio.py | ✓ Routed |
| 2 | 📊 Search Term Report | search_term_report.py | ✓ Routed |
| 3 | 🔍 Search Query Performance | search_query_performance.py | ✓ Routed |
| 4 | 📁 Bulk Campañas | bulk_campanas.py | ✓ Routed |
| 5 | 💰 Business Report | business_report.py | ✓ Routed |
| 6 | 🔗 Análisis Cruzado STR vs SQP | analisis_cruzado.py | ✓ Routed |
| 7 | 📈 Tendencia Multi-Semana | tendencia_multisemana.py | ✓ Routed |
| 8 | 🔻 Análisis de Funnel | analisis_funnel.py | ✓ Routed |
| 9 | 🔬 Reportes Atom 11 | atom11.py | ✓ Routed |
| 10 | 🛡️ Reportes MerchanSpring | merchanspring.py | ✓ Routed |
| 11 | 📊 Weekly Client Report | weekly_client_report.py | ✓ Routed but NOT in _PAGES |
| 12 | 🧠 Bid Optimizer | bid_optimizer.py | ✓ Routed |
| 13 | 🚀 Campaign Builder | campaign_builder.py | ✓ Routed |
| 14 | ⚙️ Atom11 Rules Builder | atom11_rules_builder.py | ✓ Routed (note: renamed in _PAGES to 🤖) |
| 15 | 📅 Account Pulse | account_pulse.py | ✓ Routed |
| 16 | 🔮 PPC Forecast | ppc_forecast.py | ✓ Routed |
| 17 | 🔎 PPC Insights Engine | ppc_insights.py | ✓ Routed |
| 18 | 📋 PPC Audit | ppc_audit.py | ✓ Routed |

### Naming Conventions
- **Function naming:** ✓ All non-public functions use `_snake_case()`
- **Render functions:** ✓ All page modules have `render()`
- **Constants:** ✓ All module-level constants use `_UPPER_SNAKE_CASE`
- **Violations:** NONE detected

### Session State Keys
- **Shared keys (intentional):** selected_page, parent_child_map, parent_child_names, br_extra_df, _cat_source_file, lang
- **Module-specific keys:** atom11_rb_* (atom11_rules_builder.py only)
- **Collisions:** NONE detected (proper namespacing with module prefixes)

### Import Structure
- **app.py imports:** 36 imports verified
  - core/ modules: 4
  - modules/atom11: 7
  - modules/merchanspring: 3
  - modules/pages: 14
- **Circular imports:** NONE detected
- **Unused imports:** NONE detected
