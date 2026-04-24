---
tipo: sop
actualizado: 2026-04-24
---

# Prompts de arranque de sesión

## Cuándo aplica

Al iniciar una conversación nueva con Claude (Claude.ai Project con integración GitHub, o Claude Code standalone) sobre el PPC Manager o cualquier marca gestionada por la agencia. Evita el overhead de explicar contexto cada vez.

## Requisitos previos (setup one-time)

Para que estos prompts funcionen en **Claude.ai Project**:

1. **Integración GitHub activa** en el Project — conecta el repo `ppc-manager` para que Claude lea directo del código.
2. **Indexación con selección curada** — indexar 59 archivos (ver criterio abajo). NO indexar todo el repo.
3. **Project Knowledge limpio** — solo artefactos que no estén en el repo (PDFs de clientes, imágenes, exports de herramientas externas). Capacidad objetivo: < 30%.

Criterio de curado para la indexación GitHub:
- ✅ Incluir: `CLAUDE.md`, `TASKS.md`, `CHANGELOG.md`, `INTELLIGENCE-INDEX.md`, `SOP_Uso_AgencyOS.md`, todo `notes/` (brands, state, daily, sops, knowledge, personal, prompts), `.claude/skills/`, `.claude/agents/`.
- ❌ Excluir: `data/`, `modules/`, `core/`, `app.py`, backups, `__pycache__/`, cualquier código fuente de la app (Claude.ai no necesita ejecutar, solo documentación y estado).

## Prompts tipo — copiar literal según contexto

### Prompt A — tarea libre (sin cliente específico)

```
Leé en este orden:
1. notes/Biblioteca.md
2. notes/state/STATE-agencia.md
3. Último daily en notes/daily/ (el más reciente por fecha en el nombre)

Resumí en 3-5 bullets: dónde quedó el trabajo, qué está bloqueado, cuál es el siguiente paso lógico. Después esperá mi tarea.
```

### Prompt B — tarea con cliente específico

```
Vamos a trabajar con [CLIENTE].

Leé en este orden:
1. notes/state/STATE-[cliente].md (si existe)
2. notes/brands/[cliente]/* (todos los .md)
3. Último daily que mencione [CLIENTE] en notes/daily/

Resumí en 3-5 bullets: estado actual del cliente, bloqueos, próximo paso lógico. Después esperá mi tarea.
```

Slugs válidos de cliente (carpetas en `notes/brands/`): `dermaglos`, `ltd`, `mb`, `setex`, `360essentials`, `pura-vida-moringa`.

### Prompt C — continuar sesión anterior

```
Leé el daily más reciente en notes/daily/ y el STATE-agencia.

Identificá los pendientes abiertos y proponé por cuál arrancar, en orden de urgencia/impacto. No ejecutes nada, solo proponé.
```

### Prompt D — reporte semanal / review

```
Leé los últimos 5-7 dailies en notes/daily/.

Generá un reporte ejecutivo de la semana: qué se completó, qué quedó bloqueado, patrones recurrentes (bugs, decisiones), y recomendaciones para la próxima semana. Max 300 palabras.
```

## Flujo de cierre — después de cada sesión

Ya documentado en [[CLAUDE]] del vault. Resumen:

1. Crear/actualizar `notes/daily/YYYY-MM-DD.md` con: contexto, commits del día, decisiones, gotchas, pendientes próxima sesión.
2. Actualizar `notes/state/STATE-agencia.md` si cambió algo sustancial (clientes, proyectos, bloqueos).
3. `git add . && git commit -m "..."` con mensaje descriptivo.
4. Push manual al cerrar — nunca automático (regla durable de la agencia).

## Excepciones

- **Sesión corta (< 15 min)** sin cambios sustanciales: el daily puede omitirse. Decidir por valor, no por ritual.
- **"Sesión rápida"** o **"solo una pregunta"**: no forzar el flujo completo de context loading.
- **Claude Code standalone** (sin Claude.ai Project): el vault se lee desde filesystem local via Read/Grep tools. Mismo flujo, distinto medio.
- **Primera vez con una marca nueva**: usar `client-onboarding` agent en lugar de Prompt B.

## Referencia cruzada

- [[CLAUDE]] — convenciones del vault (frontmatter, wikilinks, estructura de carpetas)
- [[STATE-agencia]] — fuente de verdad del estado operativo
- `notes/daily/` — historial cronológico de sesiones

## Histórico

- **2026-04-24** — creado tras setup inicial de Claude.ai Project con GitHub integration y curado a 59 archivos (capacity 101% → 15%).
