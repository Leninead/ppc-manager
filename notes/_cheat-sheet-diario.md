---
tipo: cheat-sheet
actualizado: 2026-05-27
version: v1.0
tags: [workflow, multi-frente, diario, rutina]
---

# 🗓️ Cheat-sheet diario — workflow multi-frente

> **Abrir TODAS las mañanas antes de arrancar trabajo.**
>
> Este archivo es la mecánica operativa del día (tuya). NO reemplaza
> los arranques por marca/feature ([[arranque-dermaglos]], [[arranque-m29]],
> etc.) que contienen el contexto del cliente/feature y que vas a seguir
> usando para abrir cada chat.

## 🧭 Cómo se combinan los archivos del workflow

| Archivo | Para quién | Contenido | Cuándo se usa |
|---|---|---|---|
| **Este cheat-sheet** | Para vos | Mecánica del día: comandos, fases, cuándo cerrar | Todas las mañanas |
| **[[arranque-{marca}]]** | Para el chat | Contexto operativo del cliente (KPIs, contactos, naming) | Al abrir cada chat |
| **[[multi-frente-flow]]** | SOP madre | Reglas duras + anti-patrones | Cuando dudás de algo |
| **[[wip-handoff]]** | SOP | Cierre cuando NO terminás un frente | Al cerrar frente incompleto |
| **[[cierre-acotado]]** | Prompt para el chat | 5 bloques de cierre cuando SÍ terminás | Al cerrar frente terminado |
| **[[consolidador-fin-dia]]** | Prompt para chat #5 | Cierre del día completo | Al final del día |

**Lectura clave**: este cheat-sheet TE recuerda QUÉ hacer paso a paso. Los
arranques le dicen AL CHAT el contexto del cliente. Son complementarios.

---

## 📋 Mapa de marcas activas — sustituciones por cliente

> Cuando los comandos del cheat-sheet digan `{cliente}` o `{slug}`, sustituí
> con la fila correspondiente a la marca que vas a trabajar.

### Clientes activos

| Marca | Slug | Worktree path | Branch pattern | Arranque |
|---|---|---|---|---|
| **Dermaglos** | `dermaglos` | `C:\proyectos\ppc-manager-dermaglos` | `ops/dermaglos-YYYY-MM-DD` | [[arranque-dermaglos]] |
| **Setex** | `setex` | `C:\proyectos\ppc-manager-setex` | `ops/setex-YYYY-MM-DD` | [[arranque-setex]] |
| **Love To Dream (LTD)** | `ltd` | `C:\proyectos\ppc-manager-ltd` | `ops/ltd-YYYY-MM-DD` | [[arranque-ltd]] |
| **Mott & Bow** | `mb` | `C:\proyectos\ppc-manager-mb` | `ops/mb-YYYY-MM-DD` | [[arranque-mb]] |
| **360 Essentials** | `360essentials` | `C:\proyectos\ppc-manager-360essentials` | `ops/360essentials-YYYY-MM-DD` | (sin arranque dedicado todavía) |
| **Pura Vida Moringa** | `pura-vida-moringa` | `C:\proyectos\ppc-manager-pvm` | `ops/pvm-YYYY-MM-DD` | (sin arranque dedicado todavía) |

### Features de código activas

| Feature | Slug | Worktree path | Branch pattern | Arranque |
|---|---|---|---|---|
| **M27 Flat File Migrator** | `m27` | `C:\proyectos\ppc-manager-m27` | `feature/m27-{bloque}` | [[arranque-m27]] |
| **M29 Proposal Studio** | `m29` | `C:\proyectos\ppc-manager-m29` | `feature/m29-{bloque}` | [[arranque-m29]] |
| **M29 DataDive Mapper** | `m29-mapper` | `C:\proyectos\ppc-manager-m29-mapper` | `feature/m29-datadive-mapper` | (incluido en arranque-m29) |

### Contactos críticos por cliente

| Cliente | AM principal | Otros contactos |
|---|---|---|
| **Dermaglos** | Edu (también signs reports + comunica pricing) | — |
| **Setex** | Edu (sin confirmar formal) | — |
| **LTD** | Agustín (ops/inventory) | Adam (Sales Dir, escalations) · Aaron (compliance) |
| **Mott & Bow** | Cuki (owner desde 11/05) | Agustín (puntual via Slack) |

---

## ☀️ FASE 1 — Bootstrap matutino (5-10 min)

> Una sola vez al arrancar el día. PowerShell en el **principal**.

### Paso 1.1 — Abrir PowerShell

```powershell
cd C:\proyectos\ppc-manager
```

### Paso 1.2 — Verificar estado

```powershell
git status
git pull origin main
git log --oneline -5
```

**Esperás ver:**
- Working tree limpio
- Pull trae commits del consolidador de ayer (si hubo)
- HEAD == origin/main

### Paso 1.3 — Inventario de worktrees y branches

```powershell
git worktree list
git branch
```

**Decisiones según lo que ves:**
- Worktree con WIP de ayer → lo reusás hoy si vas a retomarlo
- Worktree stale (frente ya cerrado) → destruir ahora
- Branch sin worktree y mergeada a main → borrar

### Paso 1.4 — Cleanup stale (si los hay)

```powershell
git worktree remove C:/proyectos/ppc-manager-{slug-stale}
git branch -D {branch-stale}
```

### Paso 1.5 — Decidir frentes del día

Anotá en papel o sticky:

```
Hoy trabajo:
Tab 1 → Frente {nombre-1} → slug {slug-1}
Tab 2 → Frente {nombre-2} → slug {slug-2}
Tab 3 → Frente {nombre-3} → slug {slug-3}
```

### Paso 1.6 — Crear worktrees nuevos

Para cada frente que NO tiene worktree (consultá Mapa de marcas arriba):

```powershell
# Cliente operativo (sustituí {cliente} y YYYY-MM-DD)
git worktree add C:/proyectos/ppc-manager-{cliente} -b ops/{cliente}-YYYY-MM-DD main

# Feature código M## (sustituí {##} y {bloque})
git worktree add C:/proyectos/ppc-manager-m{##} -b feature/m{##}-{bloque} main

# Hotfix urgente
git worktree add C:/proyectos/ppc-manager-hotfix -b hotfix/{descripcion} main
```

### Paso 1.7 — Verificación final

```powershell
git worktree list
```

Esperás ver: principal + 1 worktree por frente activo + WIPs heredados.

---

## 🏃 FASE 2 — Abrir chats (2 min por frente)

### Paso 2.1 — Una tab por frente en claude.ai

Asegurate de que el proyecto **ppc-manager** esté conectado en cada tab.

### Paso 2.2 — Primer mensaje del chat: 2 partes

**Parte A — Bloque XML del arranque correspondiente**

Para cliente: copiar de `notes/prompts/sesion/clientes/arranque-{cliente}.md`
Para feature: copiar de `notes/prompts/sesion/features/arranque-m{##}.md`
Para WIP retomado: usar el `wip-{slug}-YYYY-MM-DD.txt` guardado de ayer

**Parte B — Claim de worktree (siempre el mismo formato, sustituí {slug} y {branch-pattern})**

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
CLAIM DE WORKTREE
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Tu worktree dedicado: C:\proyectos\ppc-manager-{slug}
Tu branch:            {branch-pattern}

Pre-flight obligatorio antes de tocar nada:
pwd && git branch --show-current && git status

Reglas duras (SOP multi-frente-flow.md):
- NO trabajar en principal (C:\proyectos\ppc-manager)
- NO git add . — paths específicos siempre
- NO push (consolidador lo hace al final del día)
- NO tocar STATE-agencia.md ni daily compartido
- Cierre: cierre-acotado (terminás) o wip-handoff (no terminás)

Confirmá pre-flight y arrancamos.
```

### Paso 2.3 — Validar pre-flight

El chat te pide correr 4 comandos en PowerShell:

```powershell
cd C:\proyectos\ppc-manager-{slug}
pwd
git branch --show-current
git status
```

Pegás el output al chat. Si todo matchea → arrancás trabajo. Si algo no
matchea → STOP, revisar.

---

## 💻 FASE 3 — Trabajo durante el día

### Regla mental única

**Cuando un chat te pida correr algo en PowerShell, primero `cd` a SU carpeta.**

```powershell
cd C:\proyectos\ppc-manager-{slug-del-chat-activo}
# después corrés lo que pidió
```

### Comandos del día (en worktree del frente)

```powershell
# Ver cambios
git status
git diff --stat

# Stage paths específicos (NUNCA git add .)
git add modules/pages/archivo.py
git add notes/brands/{cliente}/archivo.md

# Commit local (NO PUSH)
git commit -m "feat/fix/docs({slug}): mensaje descriptivo"

# Ver historial
git log --oneline -5
```

### ❌ Lo que NO hacés durante el día

- `git add .` (cross-frente si hay 2+ chats)
- `git push` (consolidador lo hace al final)
- Editar `notes/state/STATE-agencia.md` (es del consolidador)
- Editar `notes/daily/YYYY-MM-DD.md` global (es del consolidador)
- Trabajar en `C:\proyectos\ppc-manager` (principal)
- Cambiar de branch dentro del worktree

---

## 🌆 FASE 4 — Cierre de cada frente (5-10 min cada uno)

> Cada frente se cierra de UNA forma, no ambas. Elegí según corresponda.

### Caso A — TERMINASTE el frente → cierre-acotado

#### Paso 4A.1 — Pegale al chat

```
Sesión terminada. Cierre acotado.

Leé notes/prompts/sesion/cierre-acotado.md y ejecutá el bloque <role>...</task>
para ESTE frente.

Reglas duras:
- NO tocar notes/state/STATE-agencia.md
- NO push
- NO git add . — paths específicos
- Generar 5 bloques de output

Confirmá que trabajaste en C:\proyectos\ppc-manager-{slug} antes de generar.
```

#### Paso 4A.2 — El chat devuelve 5 bloques

| Bloque | Qué hacer |
|---|---|
| **1. Daily fragment** | Edit en `notes/daily/YYYY-MM-DD.md` (del worktree) — NUNCA Write |
| **2. Update arranque-{slug}** | Edit en `notes/prompts/sesion/{tipo}/arranque-{slug}.md` |
| **3. Brand note** (cliente) | Append a `notes/brands/{cliente}/` |
| **4. Git commit acotado** | PowerShell en worktree del frente (SIN push) |
| **5. Resumen consolidador** | Append a `resumenes-YYYY-MM-DD.txt` (en principal) |

#### Paso 4A.3 — Comandos del Bloque 4

```powershell
cd C:\proyectos\ppc-manager-{slug}

git add notes/daily/YYYY-MM-DD.md
git add notes/prompts/sesion/{tipo}/arranque-{slug}.md
# Si es cliente:
git add notes/brands/{cliente}/

git status   # verificar que solo lo del frente

git commit -m "docs({slug}): cierre {frente} YYYY-MM-DD"
# NO PUSH
```

---

### Caso B — NO TERMINASTE el frente → wip-handoff

#### Paso 4B.1 — Pegale al chat

```
Sesión incompleta. WIP handoff.

Leé notes/sops/wip-handoff.md y generá los 4 bloques del WIP-handoff
para retomar mañana.

Confirmá que trabajaste en C:\proyectos\ppc-manager-{slug} antes de generar.
```

#### Paso 4B.2 — El chat devuelve 4 bloques

| Bloque | Qué hacer |
|---|---|
| **1. Update arranque WIP** | Edit en arranque-{slug}.md sección "🔄 WIP — retomar" |
| **2. Git commit WIP** | PowerShell en worktree (SIN push) |
| **3. Verif worktree vivo** | Confirmar status |
| **4. PROMPT DE RETOMA** | Guardar en `.txt` fuera del repo |

#### Paso 4B.3 — Comandos del Bloque 2

```powershell
cd C:\proyectos\ppc-manager-{slug}

git status
git add <paths-específicos>

git commit -m "wip({slug}): {1-línea} — retomar mañana"
# NO PUSH
git log -1 --oneline   # anotá SHA del commit WIP
```

#### Paso 4B.4 — Guardar prompt de retoma

Pegá el bloque 4 a un archivo fuera del repo:

```
C:\Users\lenin\Desktop\wip-{slug}-YYYY-MM-DD.txt
```

**Eso es lo que vas a pegar mañana cuando retomes el frente.**

> ⚠️ Un frente en WIP NO entra al consolidador del día. NO genera resumen
> en `resumenes-*.txt`. NO tiene daily fragment. Solo queda con commit
> WIP local + arranque actualizado + `.txt` de retoma.

---

## 🌙 FASE 5 — Consolidador del día (10-15 min)

> Solo cuando TODOS los frentes terminaron (acotado o WIP).
> Chat NUEVO, no reciclás ninguno.

### Paso 5.1 — Pre-verificación

```powershell
cd C:\proyectos\ppc-manager   # principal
git status
git fetch origin
git log --oneline --since="YYYY-MM-DD 00:00" -30
cat resumenes-YYYY-MM-DD.txt
git worktree list
```

### Paso 5.2 — Abrir chat consolidador (tab nueva)

Pegale este prompt (sustituí YYYY-MM-DD y listas de frentes):

```
Soy Lenin. Cierre del día YYYY-MM-DD multi-frente.

Frentes cerrados acotado hoy: [lista, ej: Dermaglos, LTD]
Frentes en WIP (no cierran hoy): [lista, ej: M29 DataDive]

Leé notes/sops/consolidador-fin-dia.md y ejecutá el flujo completo.

Pre-flight ya verificado:
- Principal limpio (o foldeo: {detalle})
- resumenes-YYYY-MM-DD.txt tiene N resúmenes
- N worktrees vivos: {listar}

Procedé con consolidación + push.

Si encontrás algún STOP CONDITION del SOP, parame y reportá.
```

### Paso 5.3 — El consolidador reporta

- SHA del commit consolidación
- Confirmación push (local == origin/main)
- Worktrees vivos restantes
- Stop conditions detectadas (si las hubo)

### Paso 5.4 — Cleanup post-consolidador (si el chat no lo hizo)

```powershell
cd C:\proyectos\ppc-manager
git worktree list

# Para cada frente que cerró acotado (NO WIP):
git worktree remove C:/proyectos/ppc-manager-{slug}
git branch -D {branch-pattern}
```

**NO destruir worktrees con WIP** — siguen vivos para mañana.

### Paso 5.5 — Verificación final del día

```powershell
git status                              # principal limpio
git log -1 --oneline                    # último = consolidador
git log origin/main..main --oneline     # vacío (todo pusheado)
git worktree list                       # solo principal + WIPs
```

✅ Día cerrado.

### Paso 5.6 — Refresh del Claude project

Andá a claude.ai → tu proyecto → "Add content from GitHub" y refrescá los
archivos que modificó el consolidador (típicamente: daily nuevo, STATE
actualizado, arranques que tocaron los frentes).

**Sin esto, mañana arrancás con contexto desactualizado.**

---

## 🎯 Resumen visual — el día en 5 momentos

```
☀️ 08:00  BOOTSTRAP                              (5 min, principal)
git pull → worktree list → crear nuevos

🏃 08:10  ABRIR CHATS                            (2 min × N)
1 tab por frente → arranque + claim

💻 08:30  TRABAJO                                (todo el día)
Cada chat en su carpeta → commits locales

🌆 17:00  CIERRE POR FRENTE                      (5-10 min × N)
Terminé → cierre-acotado (5 bloques)
No terminé → wip-handoff (4 bloques)

🌙 18:30  CONSOLIDADOR                           (10-15 min, chat nuevo)
Daily + STATE + push → cleanup worktrees
```

---

## 📍 Cosas para tener siempre a mano

### Carpetas fijas

```
C:\proyectos\ppc-manager                ← principal
C:\proyectos\ppc-manager-{slug-1}       ← chat 1
C:\proyectos\ppc-manager-{slug-2}       ← chat 2
C:\proyectos\ppc-manager-{slug-3}       ← chat 3
```

### Archivos de soporte fuera del repo

```
C:\Users\lenin\Desktop
└─ wip-{slug}-YYYY-MM-DD.txt          ← prompts de retoma
```

### SOPs de referencia cuando dudes

- [[multi-frente-flow]] — SOP madre
- [[worktrees-flow]] — mecánica git
- [[wip-handoff]] — frente incompleto
- [[consolidador-fin-dia]] — chat #5
- [[cierre-acotado]] — cierre por frente
- [[cierre-meta]] — solo días 1 frente único

---

## ⚠️ Errores comunes (primeras 2 semanas)

| Error | Detección | Fix |
|---|---|---|
| Trabajaste en principal | `git status` principal tiene cambios | `git stash` → `cd` worktree correcto → `git stash pop` |
| Olvidaste `cd` antes del comando | Chat dice "branch no matchea" | `cd` correcto + repetir |
| Confundiste 2 chats | Chat dice "esto no es mío" | Copiar al chat correcto, ignorar |
| Te olvidaste guardar prompt de retoma WIP | Mañana no tenés cómo retomar | Abrís arranque-{slug} → sección WIP tiene el contexto |
| Cerraste acotado un frente no-terminado | Daily reporta cierre pero hay trabajo en la cabeza | Mañana editás manualmente el arranque |

---

## 🚫 Cuándo NO usar este flujo

Este flujo es para **días de 2-5 frentes paralelos reales**. Para casos
simples:

- **1 solo frente del día** → no necesitás worktrees. Trabajás en principal,
  cerrás con [[cierre-meta]] (no acotado).
- **Solo vault docs / SOPs** → trabajás en principal, commit + push directo.
- **Hotfix urgente <30 min** → opcional. Si lo hacés rápido en principal
  con commit único, también está bien.

---

## 📅 Última revisión del flujo

**2026-05-27 — v1.0 creado.** Primera versión post incidentes 25-26/05.
Si encontrás fricción real durante 2-3 semanas, anotala y iteramos. NO
improvises en el momento — los SOPs son vivos, las improvisaciones
generan deudas.

---

## 🔗 Referencias cruzadas

- [[multi-frente-flow]] — SOP madre del flujo
- [[worktrees-flow]] — mecánica git de worktrees
- [[wip-handoff]] — protocolo sesión incompleta
- [[consolidador-fin-dia]] — chat #5 fin de día
- [[cierre-acotado]] — cierre de un frente terminado
- [[cierre-meta]] — cierre meta de día único
- [[CLAUDE]] (vault) — convenciones del vault
- `notes/README.md` — índice de entrada del vault
