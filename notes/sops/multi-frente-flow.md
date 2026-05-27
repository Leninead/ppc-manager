---
tipo: sop
actualizado: 2026-05-27
version: v1.0
tags: [multi-frente, worktrees, cierre, arranque, workflow]
---

# SOP — Flujo multi-frente diario

## Propósito

Orquesta los días con 2-5 frentes paralelos típicos de Capybaras (M{##}
features + 1-2 clientes ops + hotfix ocasional). Concentra en un solo lugar
las piezas que ya viven en el vault: [[worktrees-flow]], [[cierre-acotado]],
[[wip-handoff]], [[consolidador-fin-dia]].

## Cuándo aplica

- Días con 2-5 frentes paralelos
- **NO aplica** para días de 1 frente único → usar [[cierre-meta]] directo
  sin worktrees
- **NO aplica** para días de solo vault docs / notas → trabajar en principal

## Las 6 fases del día

### Fase 1 — Bootstrap del día (5 min, una vez al inicio)

```bash
cd C:\proyectos\ppc-manager   # worktree principal SIEMPRE
git status                     # ¿hay sorpresas heredadas?
git log --oneline -5           # ¿qué pasó ayer?
git pull origin main           # sincronizar
git worktree list              # ¿qué worktrees viven?
```

Identificar:
- Worktrees con WIP de ayer (mantener)
- Worktrees stale a destruir
- Frentes nuevos del día

### Fase 2 — Crear worktrees nuevos (1 min por frente)

Según [[worktrees-flow]] convención:

```bash
# Feature código (módulo M##)
git worktree add C:/proyectos/ppc-manager-m{##} \
                 -b feature/m{##}-{bloque} main

# Cliente operativo
git worktree add C:/proyectos/ppc-manager-{cliente} \
                 -b ops/{cliente}-YYYY-MM-DD main

# Hotfix urgente
git worktree add C:/proyectos/ppc-manager-hotfix \
                 -b hotfix/{descripcion-corta} main
```

### Fase 3 — Abrir N chats con sus arranques (2 min por chat)

Para cada frente:
1. Abrir chat nuevo en claude.ai (proyecto `ppc-manager` conectado)
2. Pegar el bloque XML estable del arranque correspondiente:
   - Feature: `notes/prompts/sesion/features/arranque-{slug}.md`
   - Cliente: `notes/prompts/sesion/clientes/arranque-{slug}.md`
3. APPENDEAR al prompt el "claim de worktree":
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAIM DE WORKTREE — REGLA DURA
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tu worktree dedicado:  C:\proyectos\ppc-manager-{slug}
Tu branch:             {branch-pattern}
Pre-flight obligatorio antes de tocar nada:
pwd && git branch --show-current && git status
Si NO estás en {worktree-path} con branch {branch-pattern}:
STOP. Reportar a Lenin antes de cualquier acción.
NO trabajar en principal (ppc-manager) — eso es del consolidador.
NO git add . — paths específicos siempre.
NO push — los commits quedan locales hasta consolidador.
NO tocar notes/state/STATE-agencia.md (eso es del consolidador).
NO tocar notes/daily/YYYY-MM-DD.md global (solo append vía cierre acotado).

4. Confirmar que el chat reporta worktree correcto antes de avanzar

### Fase 4 — Trabajo del frente

El chat opera SOLO en su worktree. Reglas duras [[worktrees-flow]] R1-R7.

### Fase 5 — Cierre del frente (depende de si terminó)

**Caso A — Frente TERMINÓ → cierre acotado** ([[cierre-acotado]]):

Pegar prompt corto → 5 bloques output:
1. Daily fragment → APPEND (Edit, NUNCA Write) al daily de hoy
2. Update arranque-{slug}.md (4 secciones dinámicas)
3. Brand note si es cliente
4. Git commit acotado en branch del worktree (sin push)
5. Resumen para consolidador → append a `resumenes-YYYY-MM-DD.txt`

**Caso B — Frente NO terminó → WIP-handoff** ([[wip-handoff]]):

Pegar prompt WIP → 4 bloques output:
1. Update arranque-{slug}.md sección "🔄 WIP — retomar mañana"
2. Commit WIP local en branch (sin push)
3. Confirmar worktree intacto y vivo
4. Prompt de retoma listo para mañana (guardar en notepad)

NO mezclar A y B en el mismo cierre.

### Fase 6 — Consolidador #5 (10 min al final del día)

Solo cuando los N frentes terminaron cierre acotado o WIP-handoff:

1. Abrir chat NUEVO (no reciclar uno del día)
2. Pegar prompt de [[consolidador-fin-dia]] + `resumenes-YYYY-MM-DD.txt`
3. Consolidador hace:
   - Merge del daily (append secciones faltantes)
   - Update STATE-agencia.md (1 bloque único con sub-secciones por frente)
   - SOPs nuevos si hubo learnings
   - Commit único + push
   - Cleanup worktrees mergeados (NO los con WIP)
4. Verificación final: `git log origin/main..main` debe ser vacío

## Reglas duras del día

| # | Regla |
|---|---|
| R1 | PRE-flight obligatorio en cada chat: `pwd && git branch --show-current && git status` |
| R2 | Un chat NUNCA escribe en otro worktree |
| R3 | STATE-agencia.md y daily compartido SOLO los toca el consolidador |
| R4 | Si un chat no llega al cierre del día → WIP-handoff obligatorio |
| R5 | Worktrees con WIP se mantienen entre días (no destruir) |
| R6 | Worktrees mergeados se destruyen mismo día tras consolidador |
| R7 | sop-writer SUSPENDIDO para STATE-agencia.md y archivos >500 líneas → usar Edit quirúrgico + validación textual |
| R8 | Push directo de docs prohibido a frentes → solo el consolidador pushea |

## Anti-patrones (lecciones de incidentes 25-26/05)

| Incidente | Cuándo | Costo |
|---|---|---|
| sop-writer destruyó STATE -1255 líneas | M4 fix BLOQUE 8 26/05 | Rollback + rehacer con Edit |
| M4 + M29 pushearon docs sin consolidador | 26/05 | Consolidador casi duplica bloques |
| Setex trabajó en principal sin commitear a branch | 26/05 | Foldear manual en consolidador |
| Chat trabajó sobre base vieja sin pull | Setex 26/05 mid-day | Hubiera duplicado +104 líneas |
| `git add .` con 2+ chats activos | Histórico | Cross-frente, recuperable solo si nadie pushea |

## Referencias cruzadas

- [[worktrees-flow]] — mecánica git de worktrees
- [[cierre-acotado]] — cierre por frente (5 bloques)
- [[cierre-meta]] — cierre solo días 1 frente
- [[wip-handoff]] — sesión incompleta
- [[consolidador-fin-dia]] — chat #5 fin de día
- [[feature-lifecycle]] — ciclo de vida de arranques

## Histórico

- **2026-05-27 — v1.0 creado.** Síntesis de lecciones de los días 25 y 26/05
  donde se evidenció que los SOPs existentes ([[worktrees-flow]],
  [[cierre-acotado]], [[cierre-meta]]) cubrían las piezas pero faltaba el
  orquestador que las conectara para el caso típico Capybaras.
