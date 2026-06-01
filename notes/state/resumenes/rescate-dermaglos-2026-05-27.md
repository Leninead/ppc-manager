---
fecha_origen: 2026-05-27
fecha_rescate: 2026-05-29
fuente: chat-history-Claude (archivo original `resumenes-2026-05-27.txt`
  perdido por Remove-Item el 29/05)
estado: backup-permanente
---

# Dermaglos — pendientes operativos rescatados del cierre 27/05

Este archivo es un rescate parcial del cierre operativo del 27/05/2026 que se
perdió por borrado accidental el 29/05. Contenido reconstruido desde el chat
history de Claude — no es la versión completa.

## Resumen 1 oración
Análisis 360° integral ejecutado en Amazon Ads cuenta Dermaglos USA — 91
cambios en 8 bulks aplicados live, 17 bugs documentados en módulos analítica
M2/M3/M4/M6, hallazgos cliente críticos identificados (B0F6VZMF2V desaparecido,
E.1 listing fix urgente reforzado por CVR organic 8.6%).

## SHA commit (worktree ops/dermaglos-2026-05-27)
- e82e6ce (cierre Análisis 360)
- backfill SHA self-refs en c3e617f

## P0 (críticos)
- Mensaje a Adam por E.1 listing fix B0CYLMJJJC (borrador en DERMAGLOS.md,
  validar + enviar)
- Status B0F6VZMF2V (cliente / Adam)
- B0F4KXZVNM: 67 unfulfillable (Agustín)

## P1
- Monitoreo speed cuenta 2-3 días post-bulks (alert > $5/d)
- Estrategia Micellar / Cleanser sale paid (E.6 update)
- Audit-fix M2/M3/M4/M6 — sesiones separadas con worktree dedicado

## Deliverables Adam pendientes (coordinador de decisiones)

**(a) SOP-Análisis-360**
Primera ejecución del SOP — generó aprendizajes candidatos. Propuesta:
el consolidador crea `notes/sops/sop-analisis-360.md` v1.0 con las 10
fases documentadas.

**(b) Mega-prompt audit-fix módulos**
Generado como `audit-modulos-post-analisis-360.md` (384 líneas, archivo,
generado en chat Dermaglos pero NO commiteado al repo todavía porque
review vive en outputs sandbox).

**(c) STATE-agencia.md updates a consolidar (consolidador only)**
- E.7 Dermaglos Atom11 v2026.3: CERRAR (confirmado live 27/05)
- E.1 Listing fix B0CYLMJJJC: PRIORIDAD MÁX (19d sin resolver, hero de cuenta,
  palanca #1 económica)
- E.6 Micellar: UPDATE — cliente activó sale unilateral, HOLD pad hasta
  decisión
- E.9 Emulsion / E.10 Protector solar / E.11 Stretch marks: AGREGAR como
  pendientes cliente para validar
- B0F6VZMF2V desaparecido: AGREGAR como issue P0 cliente

## Notas operacionales del frente

- Sesión arrancada en worktree principal por error (pre-flight inicial).
  Corregido a worktree dedicado antes de cualquier edición. Cero residuos
  en main.
- Streamlit upgrade 1.43.2 → 1.55.7.0 forzado por incompat Python 3.13 +
  Streamlit pre-1.55.5 (PR #1437 PEP 649). Memoria userMemories tenía 1.43.2
  cargada, realidad ya 1.55. Update pendiente en CLAUDE.md (consolidador o
  sesión próxima).
- Primera vez SOP "Análisis 360°" → aprendizajes para iterar:
  - F7 deberá tener pre-flight check Harvest vs bulk sheet (BUG-LENIN-AI)
  - "Bidding Strategy" from Amazon exact: `Dynamic bids - down only`
    (NO `Dynamic bidding (down only)`)
  - "Negative Product Targeting" requires Ad Group ID (no es campaign-level)
  - Bulks XLSX viven en outputs sandbox, NO entran al repo

## Estado al cierre 27/05
Frente Dermaglos cerrado y commiteado local en `ops/dermaglos-2026-05-27`.
Push pendiente consolidador.

## Notas del rescate
- Contenido del 28/05 (`resumenes-2026-05-28.txt`, 1884 bytes) perdido completo,
  no recuperable. Probablemente reflejado en commits del 28/05 — ver
  `git log --since='2026-05-28' --until='2026-05-29' --stat` en este repo y en
  worktrees Dermaglos para reconstruir si necesario.
