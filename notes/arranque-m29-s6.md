---
tipo: arranque-sesion
frente: M29-S6
last_session: 2026-06-03
branch: feature/m29-renderer-s5
---

# Arranque — Frente M29-S6 (jueves 2026-06-04)

Continuación de S6. Hoy: QA con Marcos + verificar chart V3 en PDF.

## DÓNDE QUEDAMOS (S6 export PDF — código CERRADO)
S6 completo del lado del código en branch `feature/m29-renderer-s5`, worktree
`C:\proyectos\ppc-manager-s5`, 4 commits sin mergear a main (HEAD `a75fbf3`). Suite 136 verde.
Branch pusheada a origin.
- Motor: xhtml2pdf 0.2.17 (weasyprint descartado por dependencia GTK en Windows).
- Arquitectura: `core/proposal_pdf.py` (capa separada del renderer puro) con
  `render_proposal_pdf(proposal, lang) -> bytes`. `_sanitize_html_for_pdf` adapta el HTML al
  motor (fonts remotas, var(), letter-spacing em, flex del chart) SIN tocar el template.
- Botón "Descargar PDF" en la pantalla de detalle, al lado del de HTML.
- 4 commits: fdf2b35 (pytest.ini), 66f104f (S6 export), 9fe6b1f (requirements), a75fbf3 (sanitizado CSS).

## OBJETIVO DE HOY
1. Verificar el chart V3 (barras CSS, "Dominación Page 1") en PDF CON DATOS REALES.
   Ayer no se pudo: inyectar datos crudos en `block['data']` no llegó al render porque el
   renderer hace overlay vía `_transform_v3_chart` / `_compute_bar_chart`
   (`core/proposal_renderer.py` ~L245). Hay que entender ese pipeline o usar una propuesta
   real con el V3 poblado. El header de cada barra usaba `display:flex` (ya neutralizado en el
   sanitizado); las barras (width %) deberían aparecer — confirmar visualmente.
2. QA local con Marcos: que pruebe el flujo completo (crear/editar propuesta → descargar PDF)
   en su Windows. Setup: `pip install -r requirements.txt` (xhtml2pdf ya pineado, sin GTK).
3. Según QA: fixes finales → merge a main (objetivo viernes).

## DEUDAS ABIERTAS
- **[M27]** `scripts/_scratch_M27/test_b5b_extract.py`: `sys.path.insert` hardcodeado al repo
  principal, renombrar a `_scratch_*.py` o quitar el insert, desde el frente M27 (NO desde S5).
  Causa raíz del bug de tests de ayer — golpeó M29-S6 Y M30 el mismo día. Prioridad real.
- **[M29]** `_sanitize_html_for_pdf` con regex: frágil si cambia el template. Fix futuro =
  variante print-friendly del template (toca S5).
- **[M29]** "List@" en F8 + nombres de equipo en F7 visibles en PDF client-facing: decisión
  de contenido del catálogo pendiente (Lenin difirió).
- **[M29]** `<table class="kv">` vacía con data={}: cosmético, confirmar que se llena con datos reales.
- **[higiene]** requirements.txt tiene anthropic/python-dotenv duplicados (preexistente).

## SETUP DEL FRENTE
- Mismo worktree/branch que S6: `cd C:\proyectos\ppc-manager-s5`, branch `feature/m29-renderer-s5`.
- venv: `C:/proyectos/ppc-manager/.venv/Scripts/python.exe` con cwd en el worktree.
- NO push automático (consolidador al cierre). Paths explícitos, NO `git add .`.
  CC prefija con `cd /c/proyectos/ppc-manager-s5 &&`.
- Edits SIEMPRE vía CC (no tocar código a mano). Diagnóstico read-only antes de cualquier edit.
  NUNCA borrar en root (mover a staging gitignoreado). `ppc-module-builder` PROHIBIDO.

## PRIMER PASO
Guard block (pwd, branch, status, log -5, `pytest -q` desde el worktree — debe dar 136).
Después PASO 0: decidir cómo verificar el chart V3 (entender `_transform_v3_chart` vs. usar
propuesta real). NO escribir hasta confirmar el approach.
