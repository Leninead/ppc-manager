tipo: sop
actualizado: 2026-04-24
---

# SOP — Prompts de Arranque por Contexto de Trabajo

Guía de prompts para empezar sesiones de Claude según el tipo de trabajo.
Aplica tanto para Claude Code (terminal) como para Claude.ai (web chat dentro del Project).

## Principio general

El primer prompt de cada sesión tiene que hacer que Claude **lea el contexto relevante antes de actuar**. Sin eso, Claude opera ciego y te hace repetir información que ya existe en el vault.

Cada tipo de trabajo tiene distinto contexto. Este SOP define cuál para cada caso.

---

## 1. Arranque para trabajo con UNA MARCA específica

Cuando vas a sesionar con un solo cliente (estrategia, revisión, planeamiento).

### Prompt base

    Hola. Vamos a trabajar con [MARCA]. Leé en este orden:

    1. notes/CLAUDE.md (convenciones del vault)
    2. notes/state/STATE-agencia.md (sección [MARCA])
    3. notes/brands/[marca-kebab]/ (todo el contenido)
    4. Último daily en notes/daily/

    Dame un resumen de 3-5 bullets:
    - Estado operativo actual
    - Últimas decisiones tomadas
    - Bloqueos pendientes
    - Próximo paso lógico inmediato

    Después esperá mi siguiente instrucción.

### Ejemplos concretos

**Dermaglos:**
    Hola. Vamos a trabajar con Dermaglos. Leé notes/CLAUDE.md + 
    notes/state/STATE-agencia.md (sección Dermaglos) + 
    notes/brands/dermaglos/ completo + último daily.
    Dame resumen estado, decisiones, bloqueos, próximo paso.

**LTD:**
    Vamos con LTD. Leé notes/brands/ltd/LTD.md + 
    STATE-agencia sección LTD + último daily.
    Resumen y próximo paso.

**Setex:**
    Sesión Setex. Leé notes/brands/setex/setex.md + 
    STATE-agencia sección Setex.
    Foco: listing optimization nose pads y temple tips.

**M&B:**
    Trabajemos M&B. Leé notes/brands/mb/ + 
    STATE-agencia sección M&B.
    Prioridad: evaluación día 14 Elizabeth Greene.

---

## 2. Arranque para trabajo con MÚLTIPLES MARCAS

Cuando vas a tocar varios clientes en la misma sesión.

### Prompt base

    Hola. Hoy voy a trabajar [MARCA1], [MARCA2], [MARCA3]. Leé:

    1. notes/CLAUDE.md
    2. notes/state/STATE-agencia.md completo
    3. notes/brands/[marca1]/ + notes/brands/[marca2]/ + notes/brands/[marca3]/
    4. Último daily

    Dame un resumen por cliente (2-3 bullets cada uno).
    Prioridad: [MARCA PRINCIPAL] primero.

### Ejemplo

    Hoy trabajo Dermaglos, LTD, Setex y M&B. Leé STATE-agencia 
    completo + las 4 carpetas de brands + último daily. 
    Prioridad Dermaglos primero (ejecutar Rufus en heroes).

---

## 3. Arranque para trabajo TÉCNICO en el software

Cuando vas a modificar código del PPC Manager (módulos, features, fixes).

### Dónde se hace

Este tipo de trabajo SIEMPRE va en Claude Code (terminal), no en Claude.ai web.

### Prompt base

    Hola. Voy a trabajar en [MODULO/FEATURE]. Leé:

    1. CLAUDE.md (raíz del repo, NO el del vault)
    2. TASKS.md (prioridad actual)
    3. CHANGELOG.md (últimas implementaciones)
    4. El módulo específico: modules/pages/[archivo].py o core/[archivo].py
    5. INTELLIGENCE-INDEX.md si aplica

    Contame qué entendés del módulo y qué tenés cargado de contexto.
    No hagas cambios hasta que yo te diga específicamente qué hacer.

### Ejemplos

**Feature nueva en Campaign Builder:**
    Voy a agregar una feature al Campaign Builder (M10). 
    Leé CLAUDE.md raíz + TASKS.md + modules/pages/campaign_builder.py 
    completo. Resumí qué hace hoy el módulo.

**Bug fix:**
    Tengo un bug en [MODULO]. Leé el módulo, CLAUDE.md raíz, 
    y los últimos 3 commits con git log -3. 
    Contame qué cambió recientemente antes de debuggear.

**Refactor:**
    Voy a refactorizar [AREA]. Leé CLAUDE.md raíz + 
    el archivo afectado + skills/module-architecture-standard.md. 
    Proponeme un plan antes de tocar código.

---

## 4. Arranque para ESCRITURA DE DOCUMENTOS (SOPs, reports)

Cuando vas a crear o actualizar documentación.

### Prompt base

    Hola. Necesito crear/actualizar [TIPO DE DOC] sobre [TEMA]. Leé:

    1. notes/CLAUDE.md (convenciones del vault)
    2. Si es SOP: notes/sops/ para ver patrones existentes
    3. Si es de cliente: notes/brands/[cliente]/
    4. Archivos similares existentes para mantener formato

    Antes de escribir, confirmame qué plantilla vas a usar y 
    qué secciones va a tener.

### Ejemplos

**SOP nuevo de proceso:**
    Necesito un SOP para [proceso]. Leé notes/sops/ + notes/CLAUDE.md. 
    Estructura: propósito, cuándo aplica, pasos, excepciones. 
    Mostrame outline antes de escribirlo.

**Report de cliente:**
    Necesito preparar un weekly report para [cliente]. 
    Leé notes/brands/[cliente]/ + últimos 2 dailies + 
    weekly_client_report.py (si existe en el repo).
    Proponé formato antes de llenar contenido.

---

## 5. Arranque para SESIÓN DE RESEARCH / KNOWLEDGE

Cuando querés investigar algo y guardarlo en el knowledge base.

### Prompt base

    Hola. Voy a investigar [TEMA]. Leé:

    1. notes/CLAUDE.md
    2. notes/knowledge/ (buscá si ya hay algo relacionado)
    3. notes/INTELLIGENCE-INDEX.md

    Si ya hay nota sobre esto, mostramela. Si no, 
    cuando terminemos la investigación, creamos 
    notes/knowledge/YYYY-MM-DD-slug.md con el hallazgo.

### Ejemplo

    Quiero investigar el nuevo Amazon Ads MCP Server. 
    Leé notes/knowledge/ + INTELLIGENCE-INDEX. 
    Si hay nota, mostramela. Si no, investiguemos 
    y guardamos como knowledge nuevo.

---

## 6. Arranque para REVISIÓN DE CHAT PREVIO

Cuando querés retomar una sesión que ya tuviste hace días.

### Prompt base

    Hola. Hace [N] días tuvimos una sesión sobre [TEMA]. 
    Buscá en notes/daily/ el daily correspondiente 
    (fecha aproximada YYYY-MM-DD). Leé ese daily + 
    cualquier archivo que referencie. 
    Contame dónde quedamos.

### Ejemplo

    El martes tuvimos sesión sobre el refactor del vault. 
    Buscá notes/daily/2026-04-24.md y contame qué 
    decidimos y qué quedó pendiente.

---

## 7. Arranque para CIERRE DE SESIÓN

Cuando terminás de trabajar y querés documentar todo.

### Prompt base

    Cerramos por hoy. Generá:

    1. notes/daily/YYYY-MM-DD.md con:
       - Contexto inicial (2-3 líneas)
       - Tareas completadas
       - Decisiones tomadas
       - Bloqueos encontrados
       - Próximos pasos concretos
       - Gotchas descubiertos si aplica

    2. Actualizá notes/state/STATE-[relevante].md si cambió 
       algo sustancial (cliente, agencia, proyecto).

    3. Si descubrimos algún concepto reutilizable, 
       creá notes/knowledge/YYYY-MM-DD-slug.md con 
       frontmatter + explicación + ejemplo.

    Usá las convenciones de notes/CLAUDE.md (wikilinks, kebab-case).
    NO hagas git push. Yo lo hago al final.

### Seguimiento obligatorio en terminal

    git add .
    git status           # verificar qué va al commit
    git diff --stat      # ver magnitud de cambios
    git commit -m "docs: cierre sesión [fecha] — [tema principal]"
    git push

---

## 8. Arranque para RESOLVER BLOQUEO O PREGUNTA PUNTUAL

Cuando solo querés una respuesta rápida sin contexto pesado.

### Prompt base

    Pregunta rápida sobre [TEMA]. 
    Solo leé [ARCHIVO ESPECÍFICO] si necesitás contexto.
    Respuesta corta.

### Ejemplo

    Pregunta rápida: qué ACoS está corriendo Dermaglos este mes? 
    Solo leé notes/state/STATE-agencia.md sección Dermaglos.

---

## 9. Arranque para TRABAJO MULTI-AGENTE

Cuando vas a usar sub-agents (sop-writer, ppc-module-builder, etc).

### Prompt base

    Voy a usar el agente [NOMBRE]. Leé primero:

    1. .claude/agents/[nombre-agente].md (para ver sus instrucciones)
    2. .claude/skills/ relacionados con la tarea
    3. Contexto mínimo que el agente va a necesitar

    Después ejecutá el agente con la tarea: [TAREA].

### Regla clave post-agente

    Después de que termine el sub-agente, VALIDÁ con:
    git status
    git diff --stat [archivos mencionados]

    No confíes en las métricas que reporta el agente. 
    Medí el cambio real con git.

---

## Reglas transversales

### Reglas duras al arrancar cualquier sesión

1. **No saltarse la lectura inicial.** Si Claude empieza a trabajar sin resumen de contexto, pausá y pedile que lea primero.

2. **El prompt de arranque siempre incluye `notes/CLAUDE.md`** si vas a tocar el vault.

3. **El prompt de arranque siempre incluye `CLAUDE.md` de raíz** si vas a tocar código.

4. **Nunca empieces "directo al grano".** El grano sale rápido pero el contexto perdido hace que la sesión tome el doble.

### Reglas duras al cerrar

1. **Siempre daily.** Aunque la sesión haya sido corta. Mañana-vos te lo va a agradecer.

2. **STATE se actualiza solo si cambió algo sustancial.** No cada daily.

3. **Commit local obligatorio. Push al final del día.**

4. **Nunca hacer push durante la sesión.** Solo al cierre total.

### Reglas de validación

1. **Después de cualquier sub-agent:** `git status` + `git diff --stat`.

2. **Antes de aceptar un reporte de cambios:** verificar con herramientas reales, no con la narrativa del agente.

3. **Si el agente reporta métricas (líneas cambiadas, archivos modificados):** validar con `git diff --stat`.

---

## Anti-patrones a evitar

### ❌ Empezar sin contexto

    Mal: "Arreglá el bug del Campaign Builder"
    Bien: "Leé CLAUDE.md + modules/pages/campaign_builder.py. 
    Cuando hayas leído, cuento el bug."

### ❌ Dar contexto todo junto en el primer prompt

    Mal: prompt de 500 palabras explicando todo.
    Bien: prompt de 50 palabras apuntando a archivos del vault.
    El vault tiene el contexto, no hay que repetirlo en el prompt.

### ❌ Confiar en el reporte de sub-agents

    Mal: "Listo, el agente dice que actualizó 6 archivos, sigamos"
    Bien: `git status` → verificar uno por uno → seguir.

### ❌ Cerrar sin daily

    Mal: "Listo, nos vemos mañana"
    Bien: "Generá el daily antes de irnos. Commit y push."

### ❌ Push automático

    Mal: darle permiso al agente de pushear.
    Bien: agente commitea, vos pusheás. Gate humano siempre.

---

## Cheatsheet rápida

| Situación | Arranque |
|-----------|----------|
| Trabajar con 1 marca | `Leé notes/brands/[marca]/ + STATE + último daily` |
| Trabajar con varias marcas | `Leé STATE completo + las N carpetas + último daily` |
| Código nuevo/fix | `Leé CLAUDE.md raíz + el módulo + TASKS.md` |
| Documentación | `Leé notes/CLAUDE.md + ejemplos similares en sops/` |
| Research | `Leé notes/knowledge/ + INTELLIGENCE-INDEX` |
| Retomar sesión vieja | `Leé daily de fecha YYYY-MM-DD` |
| Pregunta rápida | `Solo leé [archivo específico]` |
| Multi-agent | `Leé el agent.md + skills relacionados` |
| Cierre | `Generá daily + actualizá STATE si cambió` |

---

## Evolución del SOP

Este SOP va a evolucionar con el uso. Cuando encuentres un nuevo tipo 
de sesión recurrente, agregá el caso aquí.

Última actualización: 2026-04-24 — Versión inicial tras sesión de 
setup completa (vault + GitHub + Obsidian + Claude.ai).

Cómo guardarlo
Opción rápida por PowerShell (después de copiar todo el bloque):

Abrí VS Code en el proyecto:

   code notes/sops/prompts-arranque-sesion.md

Pegá todo el contenido del bloque (desde --- hasta la última línea).
Ctrl+S.