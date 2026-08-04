---
tipo: arranque
modulo: M29
actualizado: 2026-06-16
---

# Arranque M29 — Proposal Studio

Prompt de arranque rápido para sesiones de continuación de M29. Pegar al inicio de un nuevo chat.

## Estado al 2026-06-16

**M29 rediseño visual del PDF cerrado al 100% (2026-06-12) + Supabase PRODUCTIVO (2026-06-16).** Suite 312 verde.

Pendientes externos (no dependen de nosotros):
- Chart V3 data real + galería V5 (contrato v2 Ramiro).
- F3 con marcas reales (Freddy + compliance LTD/M&B/Setex).
- Hidratado Tier 2-3 (V17-V22) por cliente.

Deuda de seguridad (P2): Supabase RLS off + anon key expuesta. Rotar a service_role + RLS antes de exposición pública/multi-tenant.

8 deudas P3 silenciosas registradas en `notes/daily/2026-06-12.md` (no urgentes, ~30-40 min CC en turno corto).

## Lectura obligada para retomar M29

En este orden:
1. `notes/state/STATE-agencia.md` sección "Última sesión — 2026-06-12"
2. `notes/daily/2026-06-12.md` completo (especialmente "Aprendizajes operativos" y "Deudas P3 silenciosas")
3. `notes/modules/m29-proposal-studio.md` (estado + Supabase swap day playbook)
4. Si el trabajo toca el PDF: `notes/daily/2026-06-11.md` sección "Aprendizajes xhtml2pdf" (8 gotchas + la 9na de hoy en el daily 2026-06-12)

## Próximas sesiones triggereables

### Supabase (DONE 2026-06-16)
Wiring productivo ejecutado. Playbook en `notes/modules/m29-proposal-studio.md` sección "Supabase swap day — EJECUTADO" queda como referencia para futuros entornos. Próximo paso de seguridad: rotar key + RLS (deuda P2).

### Cuando llegue el contrato v2 de Ramiro
- Activar chart V3 con data real vía importer B7.
- Diseñar shape de galería V5 + implementación.

### Turno corto opcional — cerrar las 8 deudas P3 silenciosas
30-40 min CC en un solo turno. No urgentes. Ver lista completa en `notes/daily/2026-06-12.md` sección "Deudas P3 silenciosas".

## Protocolo de sesión M29

- Worktree: `C:\proyectos\ppc-manager` (main branch).
- Venv compartido: `C:\proyectos\ppc-manager\.venv\Scripts\python.exe` (Python 3.12.10).
- Guard de entrada en cada turno CC: `pwd`, `git branch --show-current`, `git log -1 --oneline`, `git status`.
- Paths explícitos en `git add` (NO `git add .`).
- Suite foreground (`pytest tests/ -q`).
- Triple verificación post-edit antes de commit.
- NO sub-agentes (especialmente NO `ppc-module-builder` — permanentemente prohibido).
- Verificación visual del PDF antes de cada commit del rediseño visual.

## Inventario xhtml2pdf 0.2.17 — 9 gotchas

1. `background` en `<section>/<div>` con múltiples children → fragmenta. Solución: bg en `<td>` wrapper.
2. `letter-spacing` en `em` → warning getSize. Usar `px`.
3. `text-align: right` en `<td>` falla a veces. Usar `align="right"` atributo HTML.
4. `line-height` del body se hereda y NO colapsa adjacent block margins. Solución: `<p>` con `margin: 0 0 X 0` + `line-height` explícito.
5. `border-spacing` en `<table>` SÍ funciona para grids de cards (bg + border + spacing OK).
6. `display: flex` / `grid` ignorados silenciosamente.
7. `var()` resuelve OK vía sanitizer, pero hex literales son zero-ambiguity en contextos críticos.
8. `@media print` con selector compound (`table.kv th`) no siempre honora — usar `th` simple.
9. `<span class="pill">` (display: inline-block + border-radius + padding) se colapsa a texto inline pegado, sin separación visual. NO usar para arrays — usar `| join(', ')`.

## Patrones validados

- **Cards table-based**: `<table border-collapse: separate; border-spacing: 12px 12px>` para grids 1×3, 2×2, 3×2. Cards con `background: #FFF3E0; border: 1px solid #FFD9B3`.
- **Empty-state premium**: eyebrow naranja + tagline conceptual + "Pendiente/Pending" en gris itálico (F3 patrón canónico).
- **Skip de bloques sin template propio**: `continue` en el renderer cuando `_template_exists(f"{module_id}.html")` es False. Sin `_placeholder.html` fallback.
- **Guard tabla kv vacía**: `{% if data.X or data.Y or ... %}` envolviendo `<table class="kv">` con todas las condiciones de fila espejadas.
