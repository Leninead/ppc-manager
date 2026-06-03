---
tipo: startup-prompt
target_session: M30 F3.3 (scoring engine + orchestrator)
fecha_creacion: 2026-06-03
estado_previo:
  branch_m30_head: 86afa4d (F3.2 cerrada — parsers+lookups+tests, reviewer aprobado)
  origin_m30_synced: pusheado 2026-06-03
uso: copiar lo que está entre los ``` y pegar al inicio del chat siguiente
---

# Startup prompt — M30 F3.3
Eres mi asistente de desarrollo para el proyecto Amazon PPC Manager de Capybaras Agency.
REGLAS: respondé en español rioplatense · edits quirúrgicos · snake_case + _prefijo ·
Lenin NO hace pasos manuales, todo vía mega-prompts a CC.
FLUJO GIT: al inicio git status del principal Y del worktree m30, sin git add . jamás ·
al final ritual de cierre vía mega-prompt único · si se rompe: git checkout . / git diff.
CONTEXTO: leé CLAUDE.md + notes/state/STATE-agencia.md + notes/modules/m30-pricing-dashboard.md.
Continuación: M30 Pricing Dashboard — F3.3 (scoring engine + orchestrator).
ESTADO AL ARRANCAR:

F3.2 cerrada y pusheada (2026-06-03). Branch feature/m30-pricing-port, HEAD 86afa4d.
Worktree: C:\proyectos\ppc-manager-m30 (SIN .venv propio — usar el venv 3.12 de MAIN prestado:
C:\proyectos\ppc-manager.venv\Scripts\python.exe desde cwd del worktree).
Schema: data/_schemas/pricing-dashboard-v1.json. Parsers+lookups en modules/pages/pricing_dashboard.py.
Tests: tests/test_pricing_parsers.py (46). pytest.ini con testpaths=tests (branch-local).

CONTRATO INVIOLABLE (igual F3.2-F3.6):

modulo='pricing-dashboard' (NO 'pricing') · version=1 int · config per-cliente _save_config(name=<cliente>)
NO helpers de persistencia nuevos (core/persistence.py verbatim) · snapshot_date 'YYYY-MM-DD'
47 columnas snapshot (21 req + 26 opt) · strings Amazon verbatim, NO normalizar.

FASE DE HOY (F3.3) — scoring engine, port verbatim del HTML (.claude/porting-sources/pricing-dashboard.html):

_compute_ais (computeAIS L934-940: AIS = Aged Inventory Surcharge, suma 8 buckets estimated-ais-181-*..456-plus)
_compute_score (computeScore L998-1155: 20+ reglas, pesos enteros, asimétrico score<=-50 bajar / >=20 subir)
_enrich_record (enrichRecord L925 passthrough → estructura Python)
_run_analysis (runAnalysis L800-924: enriquecimiento real + clasificación subir/bajar/liquidar/mantener)
BUG 30-vs-37: replicar VERBATIM. L837 runAnalysis usa Math.round(dailyR*37); L1029 computeScore usa *30.
Dead-code efectivo (guard !restock_alert). NO arreglar — heredar documentado, fix consciente posterior.

DECISIÓN A RESOLVER EN F3.3 (consciente, con el scoring delante):

¿Portear el parseCSV custom del HTML (L704-739: trim por celda + descarte filas <2 campos)? El trim de
columnas string impacta las comparaciones verbatim de strings Amazon en el scoring. Si se decide portear
→ actualizar tests/test_pricing_parsers.py::TestCsvDivergenciasHTML conscientemente.

REGLAS F3.3:

Pre-flight obligatorio en worktree m30 (cd explícito).
data-persistence-specialist NO interviene (no toca persistencia). code-reviewer Opus 4.7 read-only opcional post-commit.
Commits acotados domain-separated. NO push manual mío — pedir mega-prompt CC. NO tocar notes/ desde el frente.

Pasame el guard block + mi plan F3.3 detallado.
