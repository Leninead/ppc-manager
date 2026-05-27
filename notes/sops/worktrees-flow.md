---
tipo: sop
actualizado: 2026-05-27
version: v1.1
tags: [git, worktrees, multi-frente, parallel-agents]
---

# SOP — Flujo de worktrees multi-frente

## Propósito

Cómo trabajar 2+ frentes paralelos en `ppc-manager` sin colisiones de archivos
entre chats Claude Code. Reemplaza el flujo viejo de 4 chats web compartiendo
un único working directory que generaba incidentes cross-frente (cada chat
pisaba archivos del otro al no ver los cambios fuera de su contexto).

Cada frente vive en su propia carpeta hermana del repo principal, con su
propia branch checked-out. Los chats nunca se cruzan archivos porque cada uno
opera en un working tree físicamente distinto, aunque comparten el mismo
`.git/` (objetos, refs, historia).

## Cuándo aplica

- Días con 2+ frentes independientes (M29 + M27 + Setex + Dermaglos, etc.)
- **NO aplica** para sesiones de 1 frente único — overkill, trabajar directo en `main`
- **NO aplica** para sesiones de solo vault docs / notas — trabajar directo en `main`

## Convención de naming branches

| Tipo de frente | Branch pattern | Worktree path |
|---|---|---|
| Feature código (módulo M##) | `feature/m##-<bloque>` | `ppc-manager-m##` |
| Cliente operativo (PPC) | `ops/<cliente>-YYYY-MM-DD` | `ppc-manager-<cliente>` |
| Hotfix urgente | `hotfix/<descripcion-corta>` | `ppc-manager-hotfix` |
| Vault docs sin código | (sin branch, `main` directo) | `ppc-manager` (principal) |

## Comandos clave

### Crear worktree nuevo

```bash
git worktree add C:/proyectos/ppc-manager-<frente> -b <branch-pattern> main
```

Ejemplos reales:

```bash
git worktree add C:/proyectos/ppc-manager-m29-d3 -b feature/m29-b7-dispatcher-d3 main
git worktree add C:/proyectos/ppc-manager-setex  -b ops/setex-2026-05-26          main
git worktree add C:/proyectos/ppc-manager-hotfix -b hotfix/atom11-rule-stx-typo   main
```

El flag `-b <branch>` crea la branch desde `main` y la deja checked-out en el
worktree nuevo. El repo principal queda intacto en `main`.

### Listar worktrees activos

```bash
git worktree list
```

Output típico durante un día multi-frente:

```
C:/proyectos/ppc-manager         5a13ec2 [main]
C:/proyectos/ppc-manager-m29-d3  5a13ec2 [feature/m29-b7-dispatcher-d3]
C:/proyectos/ppc-manager-setex   5a13ec2 [ops/setex-2026-05-26]
```

### Destruir worktree al terminar

```bash
git worktree remove C:/proyectos/ppc-manager-<frente>
git branch -D <branch-pattern>   # solo si la branch quedó mergeada o se descarta
```

`git worktree remove` borra la carpeta física y limpia el registro interno.
Solo funciona si el working tree del frente está clean.

### Forzar remove (worktree con cambios sin commit)

```bash
git worktree remove --force C:/proyectos/ppc-manager-<frente>
```

Usar solo si confirmaste que los cambios pendientes se descartan
intencionalmente. Por defecto git protege contra esto.

## Reglas duras

1. **1 worktree = 1 frente.** Nunca trabajar 2 cosas distintas en el mismo
   worktree. Si aparece algo nuevo en mitad del día (hotfix, pedido del
   cliente, etc.), crear worktree nuevo. No mezclar.

2. **Branches NO compartidas entre worktrees.** Git lo bloquea por seguridad,
   pero no intentar forzarlo. Si necesitás trabajar la misma branch en 2
   lados, hay un problema de diseño del frente — pensarlo antes de seguir.

3. **Cleanup mismo día.** Cuando terminás un frente y mergeás a `main`,
   destruir worktree + branch en el mismo cierre acotado. No acumular
   worktrees stale entre días — generan ruido en `git worktree list` y
   confusión al abrir VS Code.

4. **NO push desde worktree de un frente.** El consolidador (chat #5 o sesión
   final del día) mergea a `main` y pushea. Cada worktree commitea local y
   queda esperando merge. Esto evita races contra `origin/main` cuando hay
   3+ frentes corriendo en paralelo.

5. **Working tree del repo principal limpio entre días.** Verificar con
   `git status` antes de cerrar el día. Si el principal está sucio, algo se
   filtró fuera de su worktree — investigar antes de hacer cualquier otra cosa.

6. **PRE-flight obligatorio en cada chat.** Cada chat debe ejecutar como primera
   acción al arrancar: `pwd && git branch --show-current && git status`. Si no
   está en su worktree dedicado → STOP, reportar a Lenin, NO trabajar en
   principal. Regla agregada tras incidente Setex 26/05.

7. **WIP-handoff vs cierre acotado son mutuamente excluyentes.** Si la sesión NO
   terminó → usar [[wip-handoff]]. Si terminó → usar [[cierre-acotado]]. Nunca
   ambos en el mismo cierre.

8. **sop-writer SUSPENDIDO para STATE-agencia.md y archivos >500 líneas.** Tras
   incidente del 26/05 (sop-writer destruyó -1255 líneas durante BLOQUE 8 de fix
   M4), regla operativa: usar Edit quirúrgico + validación textual (`git diff
   --stat` + lectura de headers post-edit) para STATE y archivos grandes.

## Cómo se combina con `dispatching-parallel-agents`

Cuando tenés 2+ frentes independientes en una misma sesión de Claude Code
Desktop, usar el skill `superpowers:dispatching-parallel-agents`. El skill
orquesta automáticamente:

- Creación de worktrees (uno por frente)
- Sub-agentes Claude Code uno por frente, cada uno apuntando a su worktree
- Shared task list con file locking para evitar races
- Reporte consolidado al final del run

Para días donde cada frente vive en su propio chat (no en una sola sesión
con dispatcher), aplicar este SOP manualmente.

Referencia: Superpowers v5.0.7 (Jesse Vincent), skill
`dispatching-parallel-agents`.

## Mantenimiento

### Listar worktrees stale (formato máquina-parseable)

```bash
git worktree list --porcelain
```

Útil para scripts de cleanup. Devuelve `worktree`, `HEAD`, `branch` y `locked`
por entrada, separados por línea en blanco.

### Prune (limpiar registros de worktrees borrados manualmente fuera de git)

```bash
git worktree prune
```

Necesario si alguna vez borrás una carpeta de worktree con `rm -rf` o desde
el explorador de Windows en lugar de `git worktree remove`. El registro
interno queda colgado hasta que se prunee.

## Histórico

- **2026-05-25 — v1.0 creado.** Migración desde flujo viejo multi-chat web
  (colisiones garantizadas) a worktrees aislados. Trigger: incidente del
  día 25/05 donde el commit `252f286` capturó -147 LOC cross-frente al no
  ver los cambios de otro chat sobre el mismo working tree.
- **2026-05-27 — v1.1.** Agregadas reglas R6 (PRE-flight obligatorio),
  R7 (WIP vs cierre exclusivos), R8 (sop-writer suspendido en STATE).
  Trigger: 3 incidentes operativos 25-26/05 que ya se documentaron en
  el daily correspondiente.

## Caveats descubiertos en producción 2026-05-26

Hallazgos del día multi-frente (M29 DataDive en worktree nuevo + consolidación).
Afectan a cualquier worktree fresco o clone limpio:

1. **`data/sales/proposals/` arranca vacío** en un worktree nuevo (solo `.gitkeep`;
   los proposals son gitignored). Todo smoke/test con proposals reales requiere copiar
   el `__vN.json` del principal primero.
2. **`.streamlit/secrets.toml` ausente** en el worktree → `app.py` lanza
   `FileNotFoundError: No secrets found` y la app no renderiza (gate de login). Copiar
   del principal / `~/.streamlit/` para smoke de UI. El smoke CLI lo esquiva.
3. **El venv no trae pytest por default** — instalarlo (`pip install pytest`) para correr
   la suite en un entorno nuevo.
4. **`SALES_ROOT` (data Sales) es relativo al cwd**, no a `__file__` → lanzar Streamlit/
   scripts desde la raíz del worktree, o los datos aterrizan en el árbol equivocado.
   Deuda P1 de fondo (afecta a todo el sistema Sales).
5. **`notes/*` está gitignored** (regla `notes/*` del `.gitignore`; los subfolders
   `daily/`, `sops/`, `state/` están re-incluidos, pero archivos en la raíz de `notes/` no).
   Planes/scratch en la raíz de `notes/` necesitan `git add -f` para versionarse.
6. **Dailies cross-frente generan conflicto add/add** cuando 2+ frentes escriben
   `notes/daily/YYYY-MM-DD.md` el mismo día. Propuesta: cada frente escribe
   `daily/YYYY-MM-DD-<frente>.md` y un consolidador único arma el `YYYY-MM-DD.md` final
   (o el consolidador es el único que toca el daily compartido). Hoy se resolvió a mano
   (un solo daily con secciones por frente).

## Referencias cruzadas

- [[cierre-acotado]] — cierre por frente sin push
- [[feature-lifecycle]] — ciclo de vida de features con arranques
- [[CLAUDE]] (vault) — convenciones generales
