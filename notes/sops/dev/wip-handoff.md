---
tipo: sop
actualizado: 2026-05-27
version: v1.0
tags: [wip, handoff, sesion-incompleta, multi-frente]
---

# SOP — WIP Handoff (sesión incompleta)

## Propósito

Cuando el trabajo del frente NO terminó hoy y necesitás retomarlo mañana
sin perder contexto. Reemplaza el [[cierre-acotado]] normal por uno
especial que deja el arranque del frente con TODO el contexto necesario
para retomar en frío.

## Cuándo usar

- Frente quedó a mitad de un bloque/feature
- Cliente operativo con bulks pendientes de upload mañana
- Bug en investigación que no se resolvió en el día
- Refactor parcialmente aplicado

## Cuándo NO usar

- Frente cerró objetivos del día → usar [[cierre-acotado]]
- Frente terminó por completo la feature → cierre acotado + cleanup worktree
- Pausa de pocos minutos (lunch break, etc) → no requiere handoff

## Prompt copiable para el chat del frente
Sesión incompleta. WIP handoff.
Generá los 4 bloques del WIP-handoff para retomar mañana:
BLOQUE 1 — Update arranque-{slug}.md sección "🔄 WIP — retomar [fecha]"
INSERTAR como sección NUEVA al inicio de las secciones dinámicas
del arranque (antes de "Estado actual"). Si ya existe sección WIP
de día anterior: REEMPLAZAR (no acumular).
Contenido:
📍 TIMESTAMP de pausa: YYYY-MM-DD HH:MM
📦 Último commit local: SHA + mensaje + branch
📝 Archivos modificados sin commit (si los hay): lista
▶️ PRÓXIMO PASO INMEDIATO (concreto, no genérico):
- Acción específica de la próxima sesión (ej: "Aplicar fix
L327 cambiando X por Y")
🚧 BLOQUEOS (si los hay): qué esperás de quién + por cuándo
🧠 CONTEXTO MENTAL CLAVE que NO está en código:
- Decisiones tomadas durante el día
- Hipótesis siendo testeadas
- Qué probaste y descartaste (para no repetir mañana)
- Numeros/IDs/SHAs relevantes en memoria
BLOQUE 2 — Commit WIP local (sin push)
cd C:\proyectos\ppc-manager-{slug}   # worktree del frente, NO principal
git status                            # verificar working tree
git add <paths-específicos>           # nunca git add .
git commit -m "wip({slug}): {1-línea descriptivo} — retomar mañana"
git log -1 --oneline   # confirmar SHA del commit WIP
BLOQUE 3 — Estado del worktree (verificación)
git status
git worktree list
Confirmar:

Worktree {slug} sigue vivo y limpio (todo commiteado)
Branch correcta checked-out
Sin archivos untracked excepto scratch documentado

BLOQUE 4 — Prompt de RETOMA para mañana
[Generar prompt completo listo para pegar en chat nuevo del mismo frente
mañana. Estructura:
Sos asistente senior de Capybaras Agency. Frente {slug} — RETOMA WIP
del [fecha-de-pausa].

[BLOQUE XML ESTABLE COMPLETO del arranque-{slug}.md]

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CONTEXTO DE RETOMA WIP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Pre-flight obligatorio:
cd C:\proyectos\ppc-manager-{slug}
pwd && git branch --show-current && git log -1 --oneline

Estado WIP al pausar:
- Último commit: {SHA} {mensaje}
- Próximo paso inmediato: {acción concreta}
- Bloqueos: {ninguno | espera por X}

Contexto mental no documentado:
{los bullets del Bloque 1 BLOQUE 1.5 contexto mental}

Tu tarea: leé el commit WIP {SHA}, leé las secciones dinámicas
actualizadas del arranque, confirmá pre-flight, y arrancá por el
próximo paso. NO releer todo el daily/STATE — el WIP-handoff de
ayer ya tiene la síntesis.

Devolveme un confirm-and-go: "WIP retomado en {worktree}.
Próximo paso: {acción}. ¿Arrancamos?"
]
NO commiteo a daily ni STATE (el frente está abierto, no cerrado).
NO push.
NO destruir worktree (sigue vivo hasta cerrar el frente).

## Output esperado

- `arranque-{slug}.md` con sección "🔄 WIP — retomar [fecha]" al inicio
  de las dinámicas
- 1 commit WIP local en branch del worktree
- Prompt de retoma listo (pegar a un notepad, archivo `.txt`, o pinear)
- Worktree intacto para mañana

## Reglas duras WIP

| # | Regla |
|---|---|
| W1 | Si el WIP dura >7 días → revisar si la feature sigue siendo prioritaria |
| W2 | No mezclar WIP con cierres normales en el mismo día (un chat = un modo) |
| W3 | El daily NO incluye fragments de frentes en WIP — solo los cerrados |
| W4 | Worktrees con WIP siguen vivos, NO destruir hasta cerrar el frente |
| W5 | El prompt de retoma se genera UNA vez y se guarda fuera del repo (notepad/archivo .txt) |
| W6 | Si retomás un WIP > 3 días viejo, validar que el contexto mental sigue siendo válido antes de seguir |

## Anti-patrón principal

❌ "Cierre acotado parcial" — generar daily fragment de un frente que
no terminó. Confunde al consolidador y produce STATE engañoso.
Solución: si no terminaste, usá WIP-handoff sí o sí.

## Referencias cruzadas

- [[multi-frente-flow]] — SOP madre que orquesta
- [[cierre-acotado]] — el cierre normal cuando SÍ terminás
- [[worktrees-flow]] — mecánica git

## Histórico

- **2026-05-27 — v1.0 creado.** Pedido directo de Lenin tras experiencia
  de sesiones que quedan incompletas y obligan a improvisar el arranque
  del día siguiente.
