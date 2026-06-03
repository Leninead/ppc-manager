---
tipo: startup-prompt
target_session: M30 F3.4 (UI tabs + uploaders + filtros)
fecha_creacion: 2026-06-03
estado_previo:
  branch_m30_head: 880967e (F3.3 cerrada — scoring engine, reviewer MERGE 9.5/10)
  origin_m30_synced: pusheado 2026-06-03
uso: copiar lo que está entre los ``` y pegar al inicio del chat siguiente
---

# Startup prompt — M30 F3.4
Eres mi asistente de desarrollo para el proyecto Amazon PPC Manager de Capybaras Agency.
REGLAS: respondé en español rioplatense · edits quirúrgicos · snake_case + _prefijo ·
Lenin NO hace pasos manuales, todo vía mega-prompts a CC.
FLUJO GIT: al inicio git status del principal Y del worktree m30, sin git add . jamás ·
al final ritual de cierre vía mega-prompt único · si se rompe: git checkout . / git diff.
CONTEXTO: leé CLAUDE.md + notes/state/STATE-agencia.md + notes/modules/m30-pricing-dashboard.md.
Continuación: M30 Pricing Dashboard — F3.4 (UI: render + uploaders + tabs + filtros).
ESTADO AL ARRANCAR:

F3.1+F3.2+F3.3 cerradas y pusheadas. Branch feature/m30-pricing-port, HEAD 880967e.
modules/pages/pricing_dashboard.py tiene: 6 parsers + 3 lookups (F3.2) + scoring completo
(F3.3: _compute_ais, _compute_score, _enrich_record, _run_analysis). SIN render() todavía.
Tests: test_pricing_parsers.py (46) + test_pricing_scoring.py (35) + test_pricing_persistence.py (6).
Worktree C:\proyectos\ppc-manager-m30 SIN .venv propio. F3.4 corre streamlit → CREAR .venv en el
worktree (o correr explícito contra C:\proyectos\ppc-manager.venv).

CONTRATO INVIOLABLE (igual F3.2-F3.6):

modulo='pricing-dashboard' · version=1 int · config per-cliente _save_config(name=<cliente>)
core/persistence.py verbatim, NO helpers nuevos · snapshot_date 'YYYY-MM-DD'
47 columnas snapshot · strings Amazon verbatim.

FASE DE HOY (F3.4) — UI, port del HTML (.claude/porting-sources/pricing-dashboard.html):

render() + 6 uploaders (fba/fee/awd CSV + pl/maestro/izzi XLSX) + import JSON histórico
7 vistas internas: resumen + principal + awdfba + liquidar + sinmargen + ais + histórico
Filtros + styler de tabla principal + selector de cliente (catálogo built-in)
Patrón Streamlit Plan D (widgets con value= sin key=, st.button no form_submit, sin st.expander
anidado → usar st.popover, None→'' pre-DataFrame por Arrow). Layout cambia = restart full.

CRÍTICO F3.4 (de F3.3):

Pasar current_month EXPLÍCITO al scoring (o derivarlo una sola vez en render), o isOffSeason
cambia según el día. NO dejar el fallback date.today() implícito en el flujo real.
_save_config debe seedear SUBCAT_FEE_AVG per-cliente (replica HTML para gamboa la primera vez).

REGLAS F3.4:

Pre-flight en worktree m30 (cd explícito). data-persistence-specialist puede entrar si toca
guardar snapshots/config (persistencia real). code-reviewer Opus 4.7 read-only post-commit.
Commits acotados domain-separated. NO push mío — pedir mega-prompt CC. NO tocar notes/ del frente.

Pasame el guard block + mi plan F3.4 detallado.
