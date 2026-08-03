---
tipo: sop
actualizado: 2026-05-27
version: v1.0
tags: [consolidador, fin-dia, multi-frente, cierre-dia]
---

# SOP — Consolidador fin de día

## Propósito

Cierre del día multi-frente. Es siempre un chat NUEVO (chat #5), no uno
de los frentes del día. Su trabajo es consolidar daily + STATE + SOP y
hacer el único push del día a origin/main.

## Cuándo usar

- Final de día multi-frente, después de que TODOS los frentes hicieron
  cierre acotado o WIP-handoff
- NO usar para días de 1 frente único → ese frente hace su propio cierre
  completo con [[cierre-meta]]

## Pre-requisitos

- N frentes cerraron acotado (commits locales en sus branches)
  + posiblemente algunos en WIP-handoff (también commits locales)
- Existe `resumenes-YYYY-MM-DD.txt` en raíz del repo con N resúmenes
  (uno por frente que cerró acotado)
- Working tree del principal LIMPIO (sin sorpresas heredadas)

## Verificación pre-trabajo (3 min)

```bash
cd C:\proyectos\ppc-manager   # principal
git status                     # debe estar limpio
git log --oneline --since="YYYY-MM-DD 00:00" -30
git worktree list
cat resumenes-YYYY-MM-DD.txt | head -50
```

Verificar:
- ¿N frentes commiteron a sus branches?
- ¿Hay frentes en WIP (no aparecen en .txt)?
- ¿Algún frente pusheó algo directo a main? (caso anómalo — investigar)

## Prompt copiable para el chat consolidador
Soy Lenin. Cierre del día YYYY-MM-DD multi-frente.
Frentes trabajados hoy: [M{##}, cliente1, cliente2, ...]
Frentes en WIP (no cierran hoy): [opcional, listar]
Tu trabajo: cierre consolidado limpio en main desde
C:\proyectos\ppc-manager (worktree principal, NO worktrees feature).
══════════════════════════════════════════════════════════════════
CONTEXTO CRÍTICO PRE-COMMIT
══════════════════════════════════════════════════════════════════
PASO 1 — Verificación de estado
cd C:\proyectos\ppc-manager
pwd && git branch --show-current   # debe ser main
git fetch origin
git log --oneline --since="YYYY-MM-DD 00:00" -30
git status
cat resumenes-YYYY-MM-DD.txt
PASO 2 — Detección de pre-existencias (CRÍTICO)
Algún frente puede haber tocado daily/STATE/SOP en sus commits
ya pusheados. Verificá ANTES de escribir:
Headers del daily commiteado
git show HEAD:notes/daily/YYYY-MM-DD.md 2>/dev/null | grep "^## "
Headers del STATE commiteado (bloques 'Última sesión')
git show HEAD:notes/state/STATE-agencia.md | grep "^## Última sesión"
Si encontrás secciones/bloques pre-existentes para esta fecha:
MERGEAR dentro de ellos, NO duplicar headers.
Si encontrás trabajo uncommitted en working tree de algún frente
(setex.md, arranque-X, etc): foldear con permiso explícito.
══════════════════════════════════════════════════════════════════
ACCIONES (en orden)
══════════════════════════════════════════════════════════════════
ACCIÓN 1 — Daily YYYY-MM-DD.md
APPEND secciones faltantes por frente (las que el cierre acotado
dejó en working tree del principal o vienen en el .txt).
Edit quirúrgico, NUNCA Write completo.
ACCIÓN 2 — STATE-agencia.md
Crear/editar UN bloque único:
Última sesión — YYYY-MM-DD (multi-frente: F1 + F2 + ...)
con sub-secciones ### por frente debajo.
Si ya existe bloque parcial de algún frente (ej: alguno pusheó docs
antes): MERGEAR dentro de él, cambiar header, agregar sub-secciones.
ACCIÓN 3 — SOPs (solo si hubo learnings operativos nuevos)
Append a sops relevantes con learnings del día.
NO crear SOPs nuevos sin consulta a Lenin.
ACCIÓN 4 — Validación pre-commit OBLIGATORIA
git diff --stat
Esperable: notes/daily/* + notes/state/* + notes/sops/* (opcional)

notes/brands/{cliente}/ (si foldeo de cliente)
notes/prompts/sesion/{tipo}/arranque-{slug}.md (si foldeo)
~5-15 archivos modificados, +100 a +400 líneas neto

⚠️ STOP CONDITIONS (no commitear):

STATE-agencia.md muestra -200+ líneas (sop-writer rompió algo)
Archivos fuera del scope acordado modificados
Working tree tiene archivos que NO esperabas
Algún frente pusheó algo entre tu fetch y tu commit
(git fetch && git log HEAD..origin/main debe estar vacío)

ACCIÓN 5 — Commit ÚNICO + push
git add <paths-específicos>   # NUNCA git add .
git status   # confirmar staged area
git commit -m "docs: cierre día YYYY-MM-DD (consolidación multi-frente)

daily: append secciones {F1, F2, ...}
STATE-agencia: bloque único con sub-secciones por frente
SOPs: {learnings nuevos si aplica}
{brand notes / arranques foldados si aplica}

Refs commits del día: {SHAs separados por coma}"
git push origin main
Verificación post-push
git log -1 --oneline
git log origin/main..main --oneline   # debe ser vacío
ACCIÓN 6 — Cleanup worktrees mergeados
git worktree list
Para cada worktree del día que YA hizo cierre acotado:
git worktree remove C:/proyectos/ppc-manager-{slug}
git branch -D {branch-pattern}   # solo si mergeada o se descarta
NO TOCAR worktrees con WIP-handoff (siguen vivos para mañana).
══════════════════════════════════════════════════════════════════
RESTRICCIONES DURAS
══════════════════════════════════════════════════════════════════

NO mergear branches feature/* a main (lo hace Lenin manual con --no-ff)
NO destruir branches/worktrees con WIP
NO usar sop-writer para STATE-agencia.md ni archivos >500 líneas
NO git add . — paths específicos siempre
NO commitear si STOP CONDITION se cumple → reportar a Lenin

══════════════════════════════════════════════════════════════════
REPORTE FINAL ESPERADO
══════════════════════════════════════════════════════════════════

SHA del commit consolidación
Confirmación push (local == origin/main)
Worktrees vivos restantes (con label: cerrados pero pendiente cleanup
vs WIP activos vs principal)
Branches locales borrables vs mantener
Stop conditions detectadas (si las hubo)
Plan para mañana basado en frentes WIP + pendientes de cada arranque

Cerrar con: "Día YYYY-MM-DD consolidado. Próximo paso: {acción mañana}."

## Anti-patrones consolidador (lecciones 26/05)

| Anti-patrón | Costo |
|---|---|
| Asumir "nadie tocó STATE/daily" sin verificar | Casi duplicó bloque M4 |
| Sop-writer para reescribir STATE entero | -1255 líneas STATE |
| Hacer todo en un solo commit gigante sin validación | Rollback imposible |
| No leer resumenes-YYYY-MM-DD.txt antes de actuar | Pierde contexto de frentes |
| No verificar pre-existencias en HEAD | Headers duplicados en STATE |

## Referencias cruzadas

- [[multi-frente-flow]] — SOP madre
- [[cierre-acotado]] — qué dejan los frentes para el consolidador
- [[wip-handoff]] — frentes que NO entran a consolidación

## Histórico

- **2026-05-27 — v1.0 creado.** Formalización del rol del consolidador
  tras experiencia del 26/05 donde fue necesario improvisar reglas que
  conviene tener escritas (detección de pre-existencias, foldeo de
  uncommitted, stop conditions).
